"""
SEC EDGAR ingestion client.

Returns typed RawEvent records normalised from the EDGAR APIs.
Wraps the lower-level sec_edgar module with source URL + checksum tracking.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

from bve.ingestion.raw_event import RawEvent

EDGAR_BASE = "https://data.sec.gov"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
EFTS_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

_HEADERS = {
    "User-Agent": "BVE Analytics research@bve.local",
    "Accept-Encoding": "gzip, deflate",
}

_TICKER_CACHE: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get(url: str, params: dict | None = None, retries: int = 3) -> dict:
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


def _resolve_cik(ticker: str) -> str | None:
    """Return zero-padded 10-digit CIK for a ticker, or None if not found."""
    global _TICKER_CACHE
    ticker = ticker.upper()
    if ticker in _TICKER_CACHE:
        return _TICKER_CACHE[ticker]
    data = _get(COMPANY_TICKERS_URL)
    for entry in data.values():
        sym = str(entry.get("ticker", "")).upper()
        if sym:
            cik = str(entry["cik_str"]).zfill(10)
            _TICKER_CACHE[sym] = cik
    return _TICKER_CACHE.get(ticker)


# ---------------------------------------------------------------------------
# Public client functions
# ---------------------------------------------------------------------------


def fetch_company_facts(ticker: str) -> list[RawEvent]:
    """
    Fetch XBRL company facts (financials) for a ticker.

    Returns one RawEvent with record_type="company_facts" containing the raw
    XBRL facts dict.
    """
    cik = _resolve_cik(ticker)
    if not cik:
        return []
    url = f"{EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
    data = _get(url)
    if not data:
        return []
    facts = data.get("facts", {})
    payload: dict[str, Any] = {
        "ticker": ticker,
        "cik": cik,
        "entity_name": data.get("entityName", ""),
        "facts": facts,
    }
    return [
        RawEvent(
            source="sec_edgar",
            record_type="company_facts",
            source_url=url,
            fetched_at=datetime.now(timezone.utc),
            payload=payload,
        )
    ]


def fetch_recent_filings(
    ticker: str,
    form_types: list[str] | None = None,
    limit: int = 10,
) -> list[RawEvent]:
    """
    Fetch recent SEC filings for a ticker via EDGAR full-text search.

    form_types: e.g. ["10-K", "8-K"]. Defaults to ["10-K", "10-Q", "8-K"].
    Returns one RawEvent per filing.
    """
    if form_types is None:
        form_types = ["10-K", "10-Q", "8-K"]
    cik = _resolve_cik(ticker)
    if not cik:
        return []
    # Use the submissions API for reliable form listing
    url = f"{EDGAR_BASE}/submissions/CIK{cik}.json"
    data = _get(url)
    if not data:
        return []

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    accessions = filings.get("accessionNumber", [])
    dates = filings.get("filingDate", [])
    primary_docs = filings.get("primaryDocument", [])

    events: list[RawEvent] = []
    for form, accession, date_str, primary_doc in zip(
        forms, accessions, dates, primary_docs
    ):
        if form not in form_types:
            continue
        acc_clean = accession.replace("-", "")
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}"
            f"/{acc_clean}/{primary_doc}"
        )
        payload: dict[str, Any] = {
            "ticker": ticker,
            "cik": cik,
            "form_type": form,
            "accession_number": accession,
            "filing_date": date_str,
            "primary_document": primary_doc,
            "filing_url": filing_url,
        }
        events.append(
            RawEvent(
                source="sec_edgar",
                record_type=form.lower().replace("-", "_"),
                source_url=filing_url,
                fetched_at=datetime.now(timezone.utc),
                payload=payload,
            )
        )
        if len(events) >= limit:
            break

    return events


def fetch_cash_and_burn(ticker: str) -> list[RawEvent]:
    """
    Extract cash, R&D expense, and share count from XBRL facts.

    Returns one RawEvent with record_type="cash_burn_snapshot" summarising
    the most recent values for each metric.
    """
    events = fetch_company_facts(ticker)
    if not events:
        return []
    facts = events[0].payload.get("facts", {})
    us_gaap = facts.get("us-gaap", {})

    def _latest(concept: str) -> dict[str, Any] | None:
        units = us_gaap.get(concept, {}).get("units", {})
        usd_entries = units.get("USD", [])
        if not usd_entries:
            return None
        # Pick the entry with the latest end date
        dated = [e for e in usd_entries if e.get("form") in ("10-K", "10-Q")]
        if not dated:
            dated = usd_entries
        return max(dated, key=lambda e: e.get("end", ""), default=None)

    def _latest_shares(concept: str) -> dict[str, Any] | None:
        units = us_gaap.get(concept, {}).get("units", {})
        share_entries = units.get("shares", [])
        if not share_entries:
            return None
        dated = [e for e in share_entries if e.get("form") in ("10-K", "10-Q")]
        if not dated:
            dated = share_entries
        return max(dated, key=lambda e: e.get("end", ""), default=None)

    cash_entry = _latest("CashAndCashEquivalentsAtCarryingValue")
    rd_entry = _latest("ResearchAndDevelopmentExpense")
    shares_entry = _latest_shares("CommonStockSharesOutstanding")

    cik = _resolve_cik(ticker)
    source_url = f"{EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json" if cik else ""

    payload: dict[str, Any] = {
        "ticker": ticker,
        "cash_usd": cash_entry.get("val") if cash_entry else None,
        "cash_period_end": cash_entry.get("end") if cash_entry else None,
        "rd_expense_usd": rd_entry.get("val") if rd_entry else None,
        "rd_period_end": rd_entry.get("end") if rd_entry else None,
        "shares_outstanding": shares_entry.get("val") if shares_entry else None,
        "shares_period_end": shares_entry.get("end") if shares_entry else None,
    }
    return [
        RawEvent(
            source="sec_edgar",
            record_type="cash_burn_snapshot",
            source_url=source_url,
            fetched_at=datetime.now(timezone.utc),
            payload=payload,
        )
    ]
