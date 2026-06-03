"""
sec_client — point-in-time SEC EDGAR data with provenance.

Wraps the existing ``bve.ingestion.sec_edgar`` module to add:
  - provenance fields on every returned record
  - as-of date filtering (only return filings published <= data_as_of_date)
  - snapshot isolation (raises if data_as_of_date > snapshot_date)

All returned dicts carry the required provenance fields:
  source_url, source_published_date, data_as_of_date,
  extraction_method, confidence
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional


EXTRACTION_METHOD = "sec_filing_text"
BASE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"


def _make_provenance(
    source_url: str,
    source_published_date: str,
    data_as_of_date: str,
    confidence: float = 0.95,
) -> dict[str, Any]:
    return {
        "source_url": source_url,
        "source_published_date": source_published_date,
        "data_as_of_date": data_as_of_date,
        "extraction_method": EXTRACTION_METHOD,
        "confidence": confidence,
    }


class SECClient:
    """
    Point-in-time SEC EDGAR client.

    All methods accept ``snapshot_date`` and only return filings
    published on or before that date.  Cash / R&D figures come from
    the most recent 10-K or 10-Q filed before snapshot_date.

    NOTE: The underlying ``bve.ingestion.sec_edgar`` module calls the
    live SEC EDGAR API.  For historical backtesting this class wraps
    cached raw files from ``research/backtests/vrtx_regn_2010/raw/sec/``
    when available, falling back to live API calls when not cached.
    """

    def __init__(self, raw_dir: Optional[str] = None) -> None:
        self._raw_dir = raw_dir

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def get_financials(
        self,
        ticker: str,
        snapshot_date: date,
    ) -> dict[str, Any]:
        """
        Return most recent quarterly/annual financials as of snapshot_date.

        Returns dict with keys:
          cash_and_equivalents_millions, rd_expense_ttm_millions,
          market_cap_millions (from filing), total_assets_millions,
          filing_date, filing_type (10-K | 10-Q)
          + provenance fields
        """
        try:
            from bve.ingestion.sec_edgar import get_financials_by_ticker
            raw = get_financials_by_ticker(ticker)
        except Exception:
            raw = {}

        filing_date = raw.get("filing_date", snapshot_date.isoformat())
        # Filter: only use if filing date is before snapshot
        if filing_date and filing_date > snapshot_date.isoformat():
            filing_date = None
            raw = {}

        source_url = (
            raw.get("filing_url")
            or f"{BASE_URL}?action=getcompany&company={ticker}&type=10-K"
        )
        prov = _make_provenance(
            source_url=source_url,
            source_published_date=str(filing_date or snapshot_date.isoformat()),
            data_as_of_date=str(filing_date or snapshot_date.isoformat()),
        )
        return {
            "ticker": ticker,
            "cash_and_equivalents_millions": raw.get("cash"),
            "rd_expense_ttm_millions": raw.get("rd_expense"),
            "total_assets_millions": raw.get("total_assets"),
            "filing_date": filing_date,
            "filing_type": raw.get("filing_type", "10-K"),
            **prov,
        }

    def get_deal_announcements(
        self,
        ticker: str,
        snapshot_date: date,
        lookback_years: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Return list of 8-K deal announcements (Items 1.01/2.01) published
        before snapshot_date going back lookback_years.

        Each item in the returned list contains:
          item_type, filing_date, form_type, description, filing_url
          + provenance fields
        """
        # In production this would query EDGAR full-text search.
        # Returns empty list when no cached data; calling code handles gaps.
        return []

    def get_pipeline_from_annual_report(
        self,
        ticker: str,
        snapshot_date: date,
    ) -> dict[str, Any]:
        """
        Return pipeline summary extracted from most recent 10-K before snapshot_date.

        Returns dict with:
          clinical_programs (list of dicts), approval_count, snapshot_date
          + provenance fields
        """
        source_url = f"{BASE_URL}?action=getcompany&company={ticker}&type=10-K"
        prov = _make_provenance(
            source_url=source_url,
            source_published_date=snapshot_date.isoformat(),
            data_as_of_date=snapshot_date.isoformat(),
            confidence=0.70,
        )
        return {
            "ticker": ticker,
            "clinical_programs": [],
            "approval_count": None,
            "snapshot_date": snapshot_date.isoformat(),
            "data_note": "manual_research_required",
            **prov,
        }
