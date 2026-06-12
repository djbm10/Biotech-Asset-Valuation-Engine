"""
Company news / press release ingestion client.

Sources:
1. BioSpace RSS feed (biotech-focused)
2. SEC EDGAR 8-K full-text search (PR-style filings)
3. Generic RSS via feedparser (fallback)

Returns typed RawEvent records with record_type="news_article" or "press_release".
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree as ET

import requests

from bve.ingestion.raw_event import RawEvent

BIOSPACE_RSS = "https://www.biospace.com/rss/news"
SEC_EFTS = "https://efts.sec.gov/LATEST/search-index"
NEWSAPI_EVERYTHING = "https://newsapi.org/v2/everything"

_HEADERS = {
    "User-Agent": "BVE Analytics research@bve.local",
    "Accept": "application/xml, text/xml, */*",
}


def _get_text(url: str, params: dict | None = None, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=_HEADERS, timeout=30)
            r.raise_for_status()
            return r.text
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    return ""


def _get_json(url: str, params: dict | None = None, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=_HEADERS, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    return {}


def _parse_rss(xml_text: str) -> list[dict[str, Any]]:
    """Parse a generic RSS feed into a list of item dicts."""
    if not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    # Handle both <rss> and <feed> (Atom) formats
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []

    # RSS 2.0
    for item in root.iter("item"):
        title_node = item.find("title")
        link_node = item.find("link")
        desc_node = item.find("description")
        pubdate_node = item.find("pubDate")
        items.append(
            {
                "title": title_node.text if title_node is not None else "",
                "url": link_node.text if link_node is not None else "",
                "summary": re.sub(
                    r"<[^>]+>", "", desc_node.text or "" if desc_node is not None else ""
                ),
                "published": pubdate_node.text if pubdate_node is not None else "",
            }
        )

    # Atom
    if not items:
        for entry in root.findall("atom:entry", ns):
            title_node = entry.find("atom:title", ns)
            link_node = entry.find("atom:link", ns)
            summary_node = entry.find("atom:summary", ns)
            updated_node = entry.find("atom:updated", ns)
            items.append(
                {
                    "title": title_node.text if title_node is not None else "",
                    "url": link_node.get("href", "") if link_node is not None else "",
                    "summary": summary_node.text if summary_node is not None else "",
                    "published": updated_node.text if updated_node is not None else "",
                }
            )
    return items


def _normalize_date(date_str: str) -> str:
    """Try to parse and return ISO date string, or return original."""
    if not date_str:
        return ""
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.isoformat()
    except Exception:
        return date_str


def fetch_biospace_news(
    ticker: str,
    limit: int = 20,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """
    Fetch biotech news from BioSpace RSS filtered by ticker/company mention.

    Returns RawEvent with record_type="news_article".
    """
    xml_text = _get_text(BIOSPACE_RSS)
    items = _parse_rss(xml_text)
    ticker_upper = ticker.upper()
    events: list[RawEvent] = []
    for item in items:
        # Filter to items that mention the ticker
        combined = f"{item.get('title', '')} {item.get('summary', '')}".upper()
        if ticker_upper not in combined:
            continue
        payload: dict[str, Any] = {
            "ticker": ticker,
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "url": item.get("url", ""),
            "published": _normalize_date(item.get("published", "")),
            "source_name": "biospace",
        }
        events.append(
            RawEvent(
                source="news",
                record_type="news_article",
                source_url=item.get("url", BIOSPACE_RSS),
                fetched_at=datetime.now(timezone.utc),
                payload=payload,
                entity_ids=entity_ids or [],
            )
        )
        if len(events) >= limit:
            break
    return events


def fetch_sec_press_releases(
    ticker: str,
    limit: int = 10,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """
    Fetch recent 8-K press releases from SEC EDGAR full-text search.

    Returns RawEvent with record_type="press_release".
    """
    params = {
        "q": ticker,
        "dateRange": "custom",
        "forms": "8-K",
        "_source": "hits",
        "hits.hits._source": "period_of_report,entity_name,file_date,form_type,period_of_report",
    }
    data = _get_json(SEC_EFTS, params=params)
    hits = data.get("hits", {}).get("hits", [])
    events: list[RawEvent] = []
    for hit in hits[:limit]:
        src = hit.get("_source", {})
        filing_date = src.get("file_date", "")
        entity_name = src.get("entity_name", "")
        period = src.get("period_of_report", "")
        url = f"https://www.sec.gov{hit.get('_id', '')}" if hit.get("_id") else SEC_EFTS
        payload: dict[str, Any] = {
            "ticker": ticker,
            "entity_name": entity_name,
            "form_type": "8-K",
            "filing_date": filing_date,
            "period_of_report": period,
            "filing_url": url,
        }
        events.append(
            RawEvent(
                source="news",
                record_type="press_release",
                source_url=url,
                fetched_at=datetime.now(timezone.utc),
                payload=payload,
                entity_ids=entity_ids or [],
            )
        )
    return events


def fetch_newsapi_articles(
    query: str,
    api_key: str,
    ticker: str | None = None,
    limit: int = 20,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """
    Fetch company news from NewsAPI's /everything endpoint.

    Returns RawEvent with record_type="news_article". This is intentionally
    opt-in because broad news feeds are noisier than official sources.
    """
    if not api_key:
        return []

    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": min(max(limit, 1), 100),
        "apiKey": api_key,
    }
    data = _get_json(NEWSAPI_EVERYTHING, params=params)
    articles = data.get("articles", [])
    events: list[RawEvent] = []
    for article in articles[:limit]:
        title = article.get("title") or ""
        description = article.get("description") or ""
        url = article.get("url") or NEWSAPI_EVERYTHING
        source = article.get("source") or {}
        payload: dict[str, Any] = {
            "ticker": ticker or "",
            "title": title,
            "summary": description,
            "url": url,
            "published": article.get("publishedAt") or "",
            "source_name": source.get("name") or "newsapi",
        }
        events.append(
            RawEvent(
                source="newsapi",
                record_type="news_article",
                source_url=url,
                fetched_at=datetime.now(timezone.utc),
                payload=payload,
                entity_ids=entity_ids or [],
            )
        )
    return events


def fetch_rss(
    feed_url: str,
    ticker: str | None = None,
    limit: int = 20,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """
    Generic RSS ingestion from any feed URL.

    Optionally filters items by ticker mention.
    Returns RawEvent with record_type="news_article".
    """
    xml_text = _get_text(feed_url)
    items = _parse_rss(xml_text)
    events: list[RawEvent] = []
    for item in items[:limit]:
        if ticker:
            combined = f"{item.get('title', '')} {item.get('summary', '')}".upper()
            if ticker.upper() not in combined:
                continue
        payload: dict[str, Any] = {
            "ticker": ticker or "",
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "url": item.get("url", ""),
            "published": _normalize_date(item.get("published", "")),
            "source_name": feed_url,
        }
        events.append(
            RawEvent(
                source="news",
                record_type="news_article",
                source_url=item.get("url", feed_url),
                fetched_at=datetime.now(timezone.utc),
                payload=payload,
                entity_ids=entity_ids or [],
            )
        )
    return events
