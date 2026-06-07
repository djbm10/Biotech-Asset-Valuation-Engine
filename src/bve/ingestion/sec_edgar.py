"""
SEC EDGAR XBRL/filing ingestion.

Uses the EDGAR full-text search and company facts APIs to extract:
- Cash and cash equivalents (from balance sheet)
- R&D expense and operating expenses
- Share count (diluted)
- Pipeline disclosures (10-K Item 1 text)

API docs: https://www.sec.gov/developer
"""
from __future__ import annotations

import time
import re
from typing import Any, Optional

import requests

EDGAR_BASE = "https://data.sec.gov"
EFTS_BASE = "https://efts.sec.gov/LATEST/search-index"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

_HEADERS = {
    "User-Agent": "BVE Analytics research@bve.local",
    "Accept-Encoding": "gzip, deflate",
}

_TICKER_TO_CIK_CACHE: dict[str, str] | None = None
_COMPANY_NAME_TO_CIK_CACHE: dict[str, str] | None = None


def _get(url: str, params: dict | None = None, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=_HEADERS, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    return {}


def _normalize_company_name(name: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()
    for suffix in (
        " inc",
        " incorporated",
        " corp",
        " corporation",
        " ltd",
        " limited",
        " plc",
        " nv",
        " therapeutics",
        " biosciences",
        " pharmaceuticals",
        " pharma",
    ):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return re.sub(r"\s+", " ", text).strip()


def _score_display_name(
    display_name: str,
    *,
    ticker: str,
    company_name: str | None,
) -> int:
    score = 0
    display_upper = display_name.upper()
    normalized_display = _normalize_company_name(display_name)
    if ticker and re.search(rf"\b{re.escape(ticker.upper())}\b", display_upper):
        score += 20
    if company_name:
        normalized_company = _normalize_company_name(company_name)
        if normalized_company and normalized_company == normalized_display:
            score += 100
        elif normalized_company and normalized_company in normalized_display:
            score += 80
    return score


def _pick_cik_from_search_hits(
    hits: list[dict[str, Any]],
    *,
    ticker: str,
    company_name: str | None,
) -> Optional[str]:
    scored: list[tuple[int, str]] = []
    for hit in hits:
        source = hit.get("_source", {}) or {}
        display_names = list(source.get("display_names") or [])
        ciks = list(source.get("ciks") or [])
        if display_names and len(display_names) == len(ciks):
            for display_name, cik in zip(display_names, ciks, strict=False):
                if cik:
                    scored.append(
                        (
                            _score_display_name(
                                str(display_name),
                                ticker=ticker,
                                company_name=company_name,
                            ),
                            str(cik).zfill(10),
                        )
                    )
            continue
        if ciks:
            joined_display = " ".join(str(item) for item in display_names)
            scored.append(
                (
                    _score_display_name(
                        joined_display,
                        ticker=ticker,
                        company_name=company_name,
                    ),
                    str(ciks[0]).zfill(10),
                )
            )
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return scored[0][1]


def get_cik(ticker: str, company_name: str | None = None) -> Optional[str]:
    """Resolve ticker → SEC CIK (zero-padded to 10 digits)."""
    global _TICKER_TO_CIK_CACHE, _COMPANY_NAME_TO_CIK_CACHE

    normalized = ticker.upper()
    if _TICKER_TO_CIK_CACHE is None:
        data = _get(COMPANY_TICKERS_URL)
        cache: dict[str, str] = {}
        company_cache: dict[str, str] = {}
        for row in data.values():
            if not isinstance(row, dict):
                continue
            row_ticker = row.get("ticker")
            cik = row.get("cik_str")
            title = row.get("title")
            if row_ticker and cik is not None:
                cache[str(row_ticker).upper()] = str(cik).zfill(10)
            if title and cik is not None:
                normalized_title = _normalize_company_name(str(title))
                if normalized_title:
                    company_cache[normalized_title] = str(cik).zfill(10)
        _TICKER_TO_CIK_CACHE = cache
        _COMPANY_NAME_TO_CIK_CACHE = company_cache

    if company_name:
        for query in (f"\"{company_name}\"", company_name):
            search = _get(
                EFTS_BASE,
                params={"q": query, "dateRange": "custom", "startdt": "2020-01-01"},
            )
            hits = search.get("hits", {}).get("hits", [])
            cik = _pick_cik_from_search_hits(
                hits,
                ticker=normalized,
                company_name=company_name,
            )
            if cik:
                return cik

    cik = _TICKER_TO_CIK_CACHE.get(normalized)
    if cik:
        return cik

    if company_name:
        normalized_name = _normalize_company_name(company_name)
        if normalized_name and _COMPANY_NAME_TO_CIK_CACHE is not None:
            company_cik = _COMPANY_NAME_TO_CIK_CACHE.get(normalized_name)
            if company_cik:
                return company_cik

    for query in [normalized]:
        search = _get(
            EFTS_BASE,
            params={"q": query, "dateRange": "custom", "startdt": "2020-01-01"},
        )
        hits = search.get("hits", {}).get("hits", [])
        cik = _pick_cik_from_search_hits(
            hits,
            ticker=normalized,
            company_name=company_name,
        )
        if cik:
            return cik
    return None


def get_company_facts(cik: str) -> dict[str, Any]:
    """
    Fetch XBRL company facts for a CIK.
    Returns the raw facts dict (us-gaap and dei namespaces).
    """
    data = _get(f"{EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json")
    return data.get("facts", {})


def extract_cash(facts: dict) -> Optional[float]:
    """
    Extract most recent CashAndCashEquivalentsAtCarryingValue in USD millions.
    Falls back to CashCashEquivalentsAndShortTermInvestments.
    """
    gaap = facts.get("us-gaap", {})
    for concept in [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
        "CashAndCashEquivalentsAndShortTermInvestments",
    ]:
        units = gaap.get(concept, {}).get("units", {}).get("USD", [])
        if units:
            # filter to 10-Q and 10-K, pick most recent
            annual = [u for u in units if u.get("form") in ("10-K", "10-Q") and u.get("val")]
            if annual:
                latest = max(annual, key=lambda u: u.get("end", ""))
                return round(latest["val"] / 1e6, 2)
    return None


def extract_rd_expense(facts: dict) -> Optional[float]:
    """Extract most recent annual R&D expense in USD millions."""
    gaap = facts.get("us-gaap", {})
    for concept in ["ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"]:
        units = gaap.get(concept, {}).get("units", {}).get("USD", [])
        if units:
            annual = [u for u in units if u.get("form") == "10-K" and u.get("val")]
            if annual:
                latest = max(annual, key=lambda u: u.get("end", ""))
                return round(latest["val"] / 1e6, 2)
    return None


def extract_sgna_expense(facts: dict) -> Optional[float]:
    """Extract most recent annual SG&A expense in USD millions."""
    gaap = facts.get("us-gaap", {})
    for concept in [
        "SellingGeneralAndAdministrativeExpense",
        "SellingGeneralAndAdministrativeExpenseResearchAndDevelopment",
        "GeneralAndAdministrativeExpense",
    ]:
        units = gaap.get(concept, {}).get("units", {}).get("USD", [])
        if units:
            annual = [u for u in units if u.get("form") == "10-K" and u.get("val")]
            if annual:
                latest = max(annual, key=lambda u: u.get("end", ""))
                return round(latest["val"] / 1e6, 2)
    return None


def extract_shares_outstanding(facts: dict) -> Optional[float]:
    """Extract most recent diluted share count in millions."""
    gaap = facts.get("us-gaap", {})
    for concept in ["CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"]:
        units = gaap.get(concept, {}).get("units", {}).get("shares", [])
        if units:
            recent = [u for u in units if u.get("val")]
            if recent:
                latest = max(recent, key=lambda u: u.get("end", ""))
                return round(latest["val"] / 1e6, 3)
    return None


def get_financials_by_ticker(ticker: str) -> dict[str, Any]:
    """
    High-level helper: resolve ticker → financials dict.

    Returns dict with keys: cash_millions, rd_expense_millions,
    sgna_expense_millions, shares_outstanding_millions
    """
    cik = get_cik(ticker)
    if not cik:
        raise ValueError(f"Could not resolve CIK for ticker: {ticker}")
    facts = get_company_facts(cik)
    return {
        "ticker": ticker,
        "cik": cik,
        "cash_millions": extract_cash(facts),
        "rd_expense_millions": extract_rd_expense(facts),
        "sgna_expense_millions": extract_sgna_expense(facts),
        "shares_outstanding_millions": extract_shares_outstanding(facts),
    }
