"""
SEC EDGAR source connector.

Fetches 8-K, 10-K, and 10-Q filings for a given company from the SEC EDGAR
submissions API and normalizes them into ``RawDocument`` objects.

Wraps ``bve.ingestion.sec_edgar`` for CIK resolution and financial facts.
Uses the EDGAR REST API for filing metadata and document retrieval.

Text extraction
---------------
Only the first ``_MAX_FILING_CHARS`` characters of each filing are extracted.
SEC filings are large; truncation is intentional at this stage — the extraction
pipeline further truncates to ``_MAX_TEXT_CHARS`` in the prompt builder.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import requests

from bve.connectors.base import FetchResult
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument

_MAX_FILING_CHARS = 40_000
_EDGAR_BASE       = "https://data.sec.gov"
_HEADERS          = {"User-Agent": "bve-intelligence research@bve.dev"}
_TAG_RE           = re.compile(r"<[^>]+>")
_WS_RE            = re.compile(r"\s+")


def _strip_tags(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", text).strip()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SECEdgarConnector:
    """
    Fetches recent SEC filings from EDGAR for a given company ticker.

    Parameters
    ----------
    form_types:
        List of form types to retrieve.  Default: ``["8-K", "10-Q"]``.
    max_filings_per_type:
        Maximum filings to fetch per form type.  Default: 3.
    """

    def __init__(
        self,
        form_types: Optional[list[str]] = None,
        max_filings_per_type: int = 3,
    ) -> None:
        self._form_types = form_types or ["8-K", "10-Q"]
        self._max_per_type = max_filings_per_type

    @property
    def source_type(self) -> str:
        return "sec_filing"

    def fetch(
        self,
        entity_hints: EntityHints,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> FetchResult:
        now    = _utcnow()
        docs: list[RawDocument] = []
        errors: list[str]       = []

        ticker = entity_hints.ticker
        if not ticker:
            return FetchResult(
                source=self.source_type,
                fetch_errors=["entity_hints.ticker is required for SECEdgarConnector"],
            )

        # Resolve CIK
        try:
            from bve.ingestion.sec_edgar import get_cik
            cik = get_cik(ticker.upper())
            if not cik:
                return FetchResult(
                    source=self.source_type,
                    fetch_errors=[f"CIK not found for ticker {ticker!r}"],
                )
        except Exception as exc:
            return FetchResult(
                source=self.source_type,
                fetch_errors=[f"CIK resolution failed for {ticker!r}: {exc}"],
            )

        # Fetch submissions metadata
        try:
            cik_padded = str(cik).zfill(10)
            url = f"{_EDGAR_BASE}/submissions/CIK{cik_padded}.json"
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
            submissions = resp.json()
        except Exception as exc:
            return FetchResult(
                source=self.source_type,
                fetch_errors=[f"EDGAR submissions fetch failed: {exc}"],
            )

        company_name = submissions.get("name", ticker)
        recent       = submissions.get("filings", {}).get("recent", {})
        forms        = recent.get("form", [])
        dates        = recent.get("filingDate", [])
        accessions   = recent.get("accessionNumber", [])

        # Build index of recent filings by form type
        count_by_form: dict[str, int] = {f: 0 for f in self._form_types}
        for form, filing_date_str, accession in zip(forms, dates, accessions):
            if form not in count_by_form:
                continue
            if count_by_form[form] >= self._max_per_type:
                continue
            if len(docs) >= limit:
                break

            # Parse filing date
            try:
                filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                filing_date = None

            if since and filing_date and filing_date < since:
                continue

            count_by_form[form] += 1

            # Fetch the filing index
            try:
                acc_clean   = accession.replace("-", "")
                index_url   = (
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                    f"{acc_clean}/{accession}-index.json"
                )
                idx_resp    = requests.get(index_url, headers=_HEADERS, timeout=15)
                idx_resp.raise_for_status()
                idx_data    = idx_resp.json()
            except Exception as exc:
                errors.append(f"Filing index fetch failed ({accession}): {exc}")
                continue

            # Find primary document URL
            doc_url: Optional[str] = None
            for filing_doc in idx_data.get("documents", []):
                doc_type = filing_doc.get("type", "")
                doc_name = filing_doc.get("name", "")
                if doc_type == form or (doc_type == "8-K" and "8-k" in doc_name.lower()):
                    doc_url = (
                        f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                        f"{acc_clean}/{doc_name}"
                    )
                    break

            if not doc_url:
                # Fall back to first .htm document
                for filing_doc in idx_data.get("documents", []):
                    name = filing_doc.get("name", "")
                    if name.endswith(".htm") or name.endswith(".html"):
                        doc_url = (
                            f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                            f"{acc_clean}/{name}"
                        )
                        break

            # Fetch document text
            raw_text_content: str = ""
            if doc_url:
                try:
                    doc_resp = requests.get(doc_url, headers=_HEADERS, timeout=30)
                    doc_resp.raise_for_status()
                    raw_text_content = _strip_tags(doc_resp.text)[:_MAX_FILING_CHARS]
                except Exception as exc:
                    errors.append(f"Filing document fetch failed ({doc_url}): {exc}")
                    # Fall back to filing summary
                    raw_text_content = (
                        f"SEC {form} filing — {company_name} — {filing_date_str}\n"
                        f"Accession: {accession}\n"
                        f"[Document text unavailable: {exc}]"
                    )
            else:
                raw_text_content = (
                    f"SEC {form} filing — {company_name} — {filing_date_str}\n"
                    f"Accession: {accession}"
                )

            if not raw_text_content.strip():
                raw_text_content = f"SEC {form} — {company_name} — {filing_date_str}"

            title    = f"{form} — {company_name} ({ticker}) — {filing_date_str}"
            index_url_public = (
                f"https://www.sec.gov/cgi-bin/browse-edgar"
                f"?action=getcompany&CIK={cik_padded}&type={form}&dateb=&owner=include&count=10"
            )

            doc = RawDocument.from_text(
                id=str(uuid.uuid4()),
                source=self.source_type,
                title=title,
                raw_text=raw_text_content,
                entity_hints=entity_hints,
                retrieved_at=now,
                source_url=doc_url or index_url_public,
                published_at=filing_date,
            )
            docs.append(doc)

        return FetchResult(
            documents=docs,
            fetch_errors=errors,
            source=self.source_type,
            fetched_at=now,
        )
