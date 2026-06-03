"""
PubMed / NCBI ingestion client.

Uses the NCBI E-utilities API (esearch + efetch) to retrieve abstracts
and article metadata for a drug or topic.

Set NCBI_API_KEY env var for higher rate limits (10 req/s vs 3 req/s).
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

import requests

from bve.ingestion.raw_event import RawEvent

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

_API_KEY = os.environ.get("NCBI_API_KEY", "")
_BASE_DELAY = 0.34 if _API_KEY else 1.0  # seconds between requests


def _get_text(url: str, params: dict[str, Any], retries: int = 4) -> str:
    delay = _BASE_DELAY
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(min(delay * (2**attempt), 60))
                continue
            r.raise_for_status()
            return r.text
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(delay * (2**attempt))
    return ""


def _parse_articles(xml_text: str) -> list[dict[str, Any]]:
    """Parse PubMed XML into a list of article dicts."""
    if not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    articles = []
    for article_node in root.iter("PubmedArticle"):
        medline = article_node.find("MedlineCitation")
        if medline is None:
            continue
        pmid_node = medline.find("PMID")
        pmid = pmid_node.text if pmid_node is not None else ""

        article = medline.find("Article")
        if article is None:
            continue

        title_node = article.find("ArticleTitle")
        title = "".join(title_node.itertext()) if title_node is not None else ""

        # Abstract text
        abstract_texts = []
        abstract_node = article.find("Abstract")
        if abstract_node is not None:
            for text_node in abstract_node.iter("AbstractText"):
                label = text_node.get("Label", "")
                text = "".join(text_node.itertext())
                if label:
                    abstract_texts.append(f"{label}: {text}")
                else:
                    abstract_texts.append(text)
        abstract = " ".join(abstract_texts)

        # Journal + date
        journal_node = article.find("Journal")
        journal = ""
        pub_year = ""
        if journal_node is not None:
            journal_title = journal_node.find("Title")
            journal = journal_title.text if journal_title is not None else ""
            issue = journal_node.find("JournalIssue")
            if issue is not None:
                pub_date = issue.find("PubDate")
                if pub_date is not None:
                    year_node = pub_date.find("Year")
                    pub_year = year_node.text if year_node is not None else ""

        # Authors
        author_list = article.find("AuthorList")
        authors = []
        if author_list is not None:
            for auth in author_list.findall("Author"):
                last = auth.find("LastName")
                first = auth.find("ForeName")
                if last is not None:
                    name = last.text or ""
                    if first is not None:
                        name = f"{first.text} {name}"
                    authors.append(name)

        # MeSH headings
        mesh_list = medline.find("MeshHeadingList")
        mesh_terms = []
        if mesh_list is not None:
            for heading in mesh_list.findall("MeshHeading"):
                descriptor = heading.find("DescriptorName")
                if descriptor is not None:
                    mesh_terms.append(descriptor.text or "")

        articles.append(
            {
                "pmid": pmid,
                "title": title,
                "abstract": abstract,
                "journal": journal,
                "pub_year": pub_year,
                "authors": authors[:10],  # cap at 10
                "mesh_terms": mesh_terms,
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            }
        )
    return articles


def search_and_fetch(
    query: str,
    max_results: int = 20,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """
    Search PubMed for a query, fetch abstracts, return one RawEvent per article.

    record_type="pubmed_abstract"
    """
    search_params: dict[str, Any] = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "usehistory": "y",
    }
    if _API_KEY:
        search_params["api_key"] = _API_KEY

    search_text = _get_text(ESEARCH_URL, search_params)
    if not search_text:
        return []

    import json

    try:
        search_data = json.loads(search_text)
    except json.JSONDecodeError:
        return []

    result = search_data.get("esearchresult", {})
    ids = result.get("idlist", [])
    web_env = result.get("webenv", "")
    query_key = result.get("querykey", "")

    if not ids:
        return []

    # Fetch full records
    fetch_params: dict[str, Any] = {
        "db": "pubmed",
        "retmode": "xml",
        "rettype": "abstract",
        "retmax": max_results,
    }
    if web_env and query_key:
        fetch_params["WebEnv"] = web_env
        fetch_params["query_key"] = query_key
    else:
        fetch_params["id"] = ",".join(ids)
    if _API_KEY:
        fetch_params["api_key"] = _API_KEY

    time.sleep(_BASE_DELAY)
    xml_text = _get_text(EFETCH_URL, fetch_params)
    articles = _parse_articles(xml_text)

    events: list[RawEvent] = []
    for art in articles:
        events.append(
            RawEvent(
                source="pubmed",
                record_type="pubmed_abstract",
                source_url=art["pubmed_url"],
                fetched_at=datetime.now(timezone.utc),
                payload=art,
                entity_ids=entity_ids or [],
            )
        )
    return events


def fetch_by_pmid(
    pmid: str,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """Fetch a single PubMed article by PMID."""
    params: dict[str, Any] = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "xml",
        "rettype": "abstract",
    }
    if _API_KEY:
        params["api_key"] = _API_KEY
    xml_text = _get_text(EFETCH_URL, params)
    articles = _parse_articles(xml_text)
    events: list[RawEvent] = []
    for art in articles:
        events.append(
            RawEvent(
                source="pubmed",
                record_type="pubmed_abstract",
                source_url=art["pubmed_url"],
                fetched_at=datetime.now(timezone.utc),
                payload=art,
                entity_ids=entity_ids or [],
            )
        )
    return events
