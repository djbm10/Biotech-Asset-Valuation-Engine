"""
PubMed connector — Wave 1C.

Fetches scientific literature abstracts from NCBI PubMed using the E-utilities
REST API.  No API key is required for low-volume access (≤ 3 req/s); supply
NCBI_API_KEY for higher rate limits (10 req/s).

Design decisions
----------------
- Only abstracts are fetched (not full text) to keep payload size manageable
  for the downstream LLM extraction pipeline.
- Topic filtering is applied client-side to reduce noise: an abstract must
  contain at least one of the configured topic keywords to be returned.
  Default keywords focus on clinical-stage evidence; basic science is excluded.
- Rate limiting: conservative 0.4s sleep between E-fetch calls when no API key.
  With API key (NCBI_API_KEY env var), rate is relaxed to 0.1s.
- Documents are returned as ``RawDocument`` objects compatible with the
  existing ``SignalExtractor`` pipeline — no special handling needed.
- ``source_url`` is set to the canonical PubMed article URL so traceability
  links directly to the abstract page.

Configuration in watchlist.yaml
--------------------------------
    connectors:
      pubmed:
        enabled: true
        limit: 50
        options:
          max_ids_per_fetch: 20      # batch size for efetch (max 200)
          topic_keywords:            # override default filter list
            - clinical trial
            - phase
            - efficacy
            - safety

Usage
-----
    connector = PubMedConnector(api_key=os.getenv("NCBI_API_KEY"))
    result = connector.fetch(entity_hints, since=datetime(...), limit=50)
    for doc in result.documents:
        signal = extractor.extract(doc)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from bve.connectors.base import FetchResult
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument

_LOG = logging.getLogger("bve.connectors.pubmed")

_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_PUBMED_BASE = "https://pubmed.ncbi.nlm.nih.gov"

# HTTP 429 backoff: wait this many seconds × 2^attempt (capped at _MAX_BACKOFF_S).
_INITIAL_BACKOFF_S: float = 2.0
_MAX_BACKOFF_S: float = 60.0
_MAX_RETRIES: int = 4

# Default topic filter — abstract must contain at least one of these tokens.
_DEFAULT_TOPIC_KEYWORDS: tuple[str, ...] = (
    "clinical trial",
    "phase 1",
    "phase 2",
    "phase 3",
    "phase i",
    "phase ii",
    "phase iii",
    "randomized",
    "randomised",
    "efficacy",
    "safety",
    "adverse",
    "mechanism",
    "pharmacokinetic",
    "endpoint",
    "overall survival",
    "progression-free",
    "response rate",
)


class PubMedConnector:
    """
    Source connector for PubMed literature abstracts.

    Implements the ``SourceConnector`` protocol (structural — no inheritance).

    Parameters
    ----------
    api_key:
        NCBI API key for higher rate limits.  If None, the connector
        operates in anonymous mode (3 req/s limit).
    topic_keywords:
        Abstract filter keywords.  An abstract must contain at least one.
        Defaults to ``_DEFAULT_TOPIC_KEYWORDS``.
    tool, email:
        NCBI courtesy identification fields (recommended by NCBI).
    """

    source_type: str = "pubmed"

    def __init__(
        self,
        api_key: Optional[str] = None,
        topic_keywords: Optional[tuple[str, ...]] = None,
        tool: str = "biotech-valuation-engine",
        email: str = "bve@example.com",
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.api_key = api_key
        self.topic_keywords = topic_keywords or _DEFAULT_TOPIC_KEYWORDS
        self.tool = tool
        self.email = email
        self.logger = logger or _LOG
        # Rate limit: 0.4s between calls (anonymous), 0.1s with key.
        self._sleep_between_calls = 0.1 if api_key else 0.4

    def fetch(
        self,
        entity_hints: EntityHints,
        since: Optional[datetime] = None,
        limit: int = 50,
        max_ids_per_fetch: int = 20,
        topic_keywords: Optional[tuple[str, ...]] = None,
    ) -> FetchResult:
        """
        Search PubMed for abstracts matching drug_name + indication, then
        fetch and filter abstracts by topic keywords.

        Parameters
        ----------
        entity_hints:
            Asset identity (uses ``drug_name`` and ``indication``).
        since:
            Only return articles published after this date.
        limit:
            Maximum number of documents to return after topic filtering.
        max_ids_per_fetch:
            Batch size for efetch calls (NCBI max = 200).
        topic_keywords:
            Per-call override for topic filter.

        Returns
        -------
        FetchResult
            Never raises; errors collected in ``fetch_errors``.
        """
        keywords = topic_keywords or self.topic_keywords
        drug_name = entity_hints.drug_name or ""
        indication = entity_hints.indication or ""

        if not drug_name and not indication:
            return FetchResult(
                source=self.source_type,
                fetch_errors=["PubMedConnector: drug_name and indication are both empty"],
            )

        pmids, search_error = self._search(
            drug_name=drug_name,
            indication=indication,
            since=since,
            limit=limit * 3,  # over-fetch to account for topic filtering
        )
        errors: list[str] = []
        if search_error:
            errors.append(search_error)
        if not pmids:
            return FetchResult(source=self.source_type, fetch_errors=errors)

        documents: list[RawDocument] = []
        for batch_start in range(0, len(pmids), max_ids_per_fetch):
            batch = pmids[batch_start : batch_start + max_ids_per_fetch]
            batch_docs, batch_errs = self._fetch_abstracts(
                pmids=batch,
                entity_hints=entity_hints,
                keywords=keywords,
            )
            documents.extend(batch_docs)
            errors.extend(batch_errs)
            if len(documents) >= limit:
                break
            time.sleep(self._sleep_between_calls)

        return FetchResult(
            documents=documents[:limit],
            fetch_errors=errors,
            source=self.source_type,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _base_params(self) -> dict:
        params: dict = {"tool": self.tool, "email": self.email}
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def _get_with_backoff(self, url: str, params: dict, timeout: int) -> requests.Response:
        """
        GET *url* with exponential backoff on HTTP 429 (rate-limit) responses.

        NCBI limits: 3 req/s anonymous, 10 req/s with API key.
        On 429, back off for _INITIAL_BACKOFF_S × 2^attempt (capped at _MAX_BACKOFF_S),
        then retry up to _MAX_RETRIES times before raising.
        """
        backoff = _INITIAL_BACKOFF_S
        for attempt in range(_MAX_RETRIES + 1):
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code != 429:
                resp.raise_for_status()
                return resp
            wait = min(backoff, _MAX_BACKOFF_S)
            self.logger.warning(
                "PubMed HTTP 429 (rate limit) — waiting %.1fs before retry %d/%d",
                wait, attempt + 1, _MAX_RETRIES,
            )
            time.sleep(wait)
            backoff *= 2
        # Final attempt after last backoff
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp

    def _search(
        self,
        drug_name: str,
        indication: str,
        since: Optional[datetime],
        limit: int,
    ) -> tuple[list[str], Optional[str]]:
        """Run esearch; return (pmid_list, error_or_None)."""
        query_parts: list[str] = []
        if drug_name:
            query_parts.append(f'"{drug_name}"[Title/Abstract]')
        if indication:
            query_parts.append(f'"{indication}"[Title/Abstract]')
        query = " AND ".join(query_parts)

        params = {
            **self._base_params(),
            "db": "pubmed",
            "term": query,
            "retmax": min(limit, 500),
            "retmode": "json",
            "sort": "relevance",
        }
        if since:
            # NCBI date filter: mindate/maxdate in YYYY/MM/DD format.
            params["mindate"] = since.strftime("%Y/%m/%d")
            params["datetype"] = "pdat"

        try:
            resp = self._get_with_backoff(_ESEARCH_URL, params=params, timeout=15)
            data = resp.json()
            pmids = data.get("esearchresult", {}).get("idlist", [])
            return pmids, None
        except Exception as exc:
            return [], f"PubMed esearch failed: {exc}"

    def _fetch_abstracts(
        self,
        pmids: list[str],
        entity_hints: EntityHints,
        keywords: tuple[str, ...],
    ) -> tuple[list[RawDocument], list[str]]:
        """Fetch abstracts for a batch of PMIDs; apply topic filter."""
        params = {
            **self._base_params(),
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "abstract",
            "retmode": "xml",
        }
        errors: list[str] = []
        try:
            time.sleep(self._sleep_between_calls)
            resp = self._get_with_backoff(_EFETCH_URL, params=params, timeout=30)
            return self._parse_xml_abstracts(resp.text, entity_hints, keywords), errors
        except Exception as exc:
            errors.append(f"PubMed efetch failed for {len(pmids)} PMIDs: {exc}")
            return [], errors

    def _parse_xml_abstracts(
        self,
        xml_text: str,
        entity_hints: EntityHints,
        keywords: tuple[str, ...],
    ) -> list[RawDocument]:
        """Parse PubMed XML efetch response into RawDocument objects."""
        import xml.etree.ElementTree as ET

        documents: list[RawDocument] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            self.logger.warning("PubMed XML parse error: %s", exc)
            return documents

        for article in root.findall(".//PubmedArticle"):
            try:
                pmid_el = article.find(".//PMID")
                pmid = pmid_el.text.strip() if pmid_el is not None else ""
                if not pmid:
                    continue

                # Title
                title_el = article.find(".//ArticleTitle")
                title = title_el.text or "" if title_el is not None else ""
                title = title.strip()

                # Abstract text (may be structured with sections)
                abstract_parts: list[str] = []
                for ab_text in article.findall(".//AbstractText"):
                    label = ab_text.get("Label", "")
                    text = ab_text.text or ""
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)
                abstract = " ".join(abstract_parts).strip()

                if not abstract:
                    continue

                full_text = f"{title}\n\n{abstract}"

                # Topic filter — must contain at least one keyword.
                lower = full_text.lower()
                if keywords and not any(kw.lower() in lower for kw in keywords):
                    continue

                # Publication date
                pub_date_el = article.find(".//PubDate")
                published_at: Optional[datetime] = None
                if pub_date_el is not None:
                    year_el = pub_date_el.find("Year")
                    month_el = pub_date_el.find("Month")
                    if year_el is not None:
                        try:
                            year = int(year_el.text or "0")
                            month_str = (month_el.text or "Jan") if month_el is not None else "Jan"
                            # Month may be text ("Jan") or number ("01")
                            try:
                                month = int(month_str)
                            except ValueError:
                                from datetime import datetime as _dt
                                month = _dt.strptime(month_str[:3], "%b").month
                            published_at = datetime(year, month, 1, tzinfo=timezone.utc)
                        except (ValueError, AttributeError):
                            pass

                source_url = f"{_PUBMED_BASE}/{pmid}/"

                import uuid as _uuid
                doc = RawDocument.from_text(
                    id=f"pubmed-{pmid}-{_uuid.uuid4().hex[:8]}",
                    source="pubmed",
                    title=title or f"PubMed {pmid}",
                    raw_text=full_text,
                    entity_hints=entity_hints,
                    source_url=source_url,
                    published_at=published_at,
                )
                documents.append(doc)

            except Exception as exc:
                self.logger.debug("PubMed article parse error: %s", exc)

        return documents
