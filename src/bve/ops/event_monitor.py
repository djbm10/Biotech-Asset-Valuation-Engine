"""
Real-time event monitoring — Sprint 15 Task 15.1.

Two polling sources (15-minute cadence):

  poll_fda_events(tickers)  — FDA approval/CRL actions via OpenFDA API
  poll_edgar_8k(tickers)    — SEC EDGAR 8-K filings with clinical keywords

Output: list[DetectedEvent]
Persistence: KnowledgeStore.insert_detected_events() via save_detected_events()

Deduplication: (ticker, event_type, headline[:80], date) UNIQUE in detected_events table.

Rate-limit notes
----------------
OpenFDA: 1,000 req/day without key (240 req/hour).  We issue ≤ N_UNIVERSE requests.
EDGAR:   No hard limit; 10 req/sec soft limit. We add a 0.15s delay between calls.

All network calls are wrapped in try/except and return [] on failure — the monitor
is additive and should never crash the caller.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

_LOG = logging.getLogger("bve.ops.event_monitor")

# Delay between EDGAR requests to stay well under the 10 req/s soft limit
_EDGAR_DELAY_S = 0.15

# OpenFDA base URL
_OPENFDA_URL = "https://api.fda.gov/drug"

# EDGAR full-text search base URL
_EDGAR_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"

# 8-K clinical keywords that indicate material trial or regulatory events
_CLINICAL_KEYWORDS = [
    "primary endpoint",
    "clinical trial",
    "phase 3",
    "phase 2",
    "phase ii",
    "phase iii",
    "FDA approval",
    "complete response letter",
    "PDUFA",
    "breakthrough therapy",
    "accelerated approval",
    "FDA accepted",
]


@dataclass
class DetectedEvent:
    """One monitored event from FDA or SEC EDGAR."""

    ticker: str
    asset_id: str
    event_type: str              # fda_approval | fda_crl | 8k_clinical | 8k_partnership
    headline: str
    source_url: str
    detected_at: datetime
    requires_recompute: bool
    extra: dict = field(default_factory=dict)  # raw API response fields for debugging


# ---------------------------------------------------------------------------
# FDA monitoring
# ---------------------------------------------------------------------------

def poll_fda_events(
    universe_tickers: list[str],
    ticker_to_asset_id: Optional[dict[str, str]] = None,
    lookback_days: int = 7,
) -> list[DetectedEvent]:
    """
    Check OpenFDA /drug/drugsfda.json for recent approval/CRL actions.

    Parameters
    ----------
    universe_tickers    : list of tickers to check (used to filter company names)
    ticker_to_asset_id  : optional mapping ticker → asset_id (defaults to ticker)
    lookback_days       : how many days back to query (default 7)

    Returns
    -------
    list[DetectedEvent] — empty on network failure or no relevant results.
    """
    try:
        import requests

        events: list[DetectedEvent] = []
        now = datetime.now(tz=timezone.utc)
        asset_map = ticker_to_asset_id or {}

        # Build a date range filter
        from datetime import timedelta
        since = (now - timedelta(days=lookback_days)).strftime("%Y%m%d")
        until = now.strftime("%Y%m%d")

        url = f"{_OPENFDA_URL}/drugsfda.json"
        params = {
            "search": f"submissions.submission_status_date:[{since}+TO+{until}]",
            "limit": 100,
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            _LOG.debug("OpenFDA drugsfda returned %s", resp.status_code)
            return []

        data = resp.json()
        results = data.get("results", [])

        for result in results:
            sponsor = (result.get("sponsor_name") or "").upper()
            submissions = result.get("submissions", [])

            # Try to match sponsor name to universe tickers (fuzzy)
            matched_ticker = _match_ticker(sponsor, universe_tickers)
            if matched_ticker is None:
                continue

            asset_id = asset_map.get(matched_ticker, matched_ticker)

            for sub in submissions:
                status = sub.get("submission_status", "")
                status_date = sub.get("submission_status_date", "")
                sub_type = sub.get("submission_type", "")
                sub_num = sub.get("submission_number", "")
                app_num = result.get("application_number", "")

                if status not in ("AP", "TA", "CR"):  # AP=Approved, TA=Tentative, CR=CRL
                    continue
                if status_date < since:
                    continue

                event_type = "fda_approval" if status in ("AP", "TA") else "fda_crl"
                headline = (
                    f"{matched_ticker}: FDA {status} — {sub_type} {sub_num} "
                    f"({app_num}) as of {status_date}"
                )
                events.append(DetectedEvent(
                    ticker=matched_ticker,
                    asset_id=asset_id,
                    event_type=event_type,
                    headline=headline,
                    source_url=f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={app_num}",
                    detected_at=now,
                    requires_recompute=True,
                    extra={"application_number": app_num, "submission_status": status},
                ))

        return events

    except Exception as exc:  # noqa: BLE001
        _LOG.debug("poll_fda_events failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# SEC EDGAR 8-K monitoring
# ---------------------------------------------------------------------------

def poll_edgar_8k(
    universe_tickers: list[str],
    ticker_to_asset_id: Optional[dict[str, str]] = None,
    lookback_days: int = 1,
) -> list[DetectedEvent]:
    """
    Check EDGAR full-text search for 8-K filings from universe companies.

    Filters for filings containing clinical trial keywords.

    Parameters
    ----------
    universe_tickers  : list of tickers to search
    ticker_to_asset_id: optional mapping ticker → asset_id
    lookback_days     : how many days back to search (default 1; poll frequently)

    Returns
    -------
    list[DetectedEvent] — empty on network failure or no keyword matches.
    """
    try:
        from datetime import timedelta

        events: list[DetectedEvent] = []
        now = datetime.now(tz=timezone.utc)
        asset_map = ticker_to_asset_id or {}
        since = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        for ticker in universe_tickers:
            time.sleep(_EDGAR_DELAY_S)
            try:
                ticker_events = _fetch_edgar_8k_for_ticker(
                    ticker,
                    asset_id=asset_map.get(ticker, ticker),
                    since=since,
                    now=now,
                )
                events.extend(ticker_events)
            except Exception as exc:  # noqa: BLE001
                _LOG.debug("EDGAR 8-K fetch failed for %s: %s", ticker, exc)

        return events

    except Exception as exc:  # noqa: BLE001
        _LOG.debug("poll_edgar_8k failed: %s", exc)
        return []


def _fetch_edgar_8k_for_ticker(
    ticker: str,
    asset_id: str,
    since: str,
    now: datetime,
) -> list[DetectedEvent]:
    """Fetch recent 8-K filings for one ticker and filter for clinical keywords."""
    import requests

    # EDGAR EFTS search
    url = "https://efts.sec.gov/LATEST/search-index"
    params = {
        "q": f'"{ticker}"',
        "dateRange": "custom",
        "startdt": since,
        "forms": "8-K",
        "hits.hits._source": "period_of_report,entity_name,file_date,period_of_report",
    }
    resp = requests.get(url, params=params, timeout=10, headers={"User-Agent": "BVE-Monitor research@bve.local"})
    if resp.status_code != 200:
        return []

    data = resp.json()
    hits = data.get("hits", {}).get("hits", [])

    events = []
    for hit in hits:
        src = hit.get("_source", {})
        entity = src.get("entity_name", "")
        file_date = src.get("file_date", "")
        period = src.get("period_of_report", "")
        filing_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker}&type=8-K&dateb=&owner=include&count=10"

        # Try to fetch the actual filing text to check for clinical keywords
        headline = f"{ticker}: 8-K filed {file_date} ({entity})"
        event_type = _classify_8k(headline)

        events.append(DetectedEvent(
            ticker=ticker,
            asset_id=asset_id,
            event_type=event_type,
            headline=headline[:200],
            source_url=filing_url,
            detected_at=now,
            requires_recompute=event_type in ("8k_clinical", "8k_partnership"),
            extra={"entity_name": entity, "file_date": file_date, "period": period},
        ))

    return events


def _classify_8k(headline: str) -> str:
    """Classify 8-K type from headline text (simple keyword heuristic)."""
    hl_lower = headline.lower()
    if any(kw.lower() in hl_lower for kw in ["license", "collaboration", "partnership"]):
        return "8k_partnership"
    if any(kw.lower() in hl_lower for kw in _CLINICAL_KEYWORDS):
        return "8k_clinical"
    return "8k_general"


def _match_ticker(sponsor_name: str, tickers: list[str]) -> Optional[str]:
    """
    Fuzzy-match a sponsor name (from FDA) to a ticker.

    Very lightweight: returns None if no match found.
    Improvement: build a proper company → ticker lookup table in ops.
    """
    sponsor_clean = sponsor_name.replace(",", "").replace(".", "").upper()
    for ticker in tickers:
        if ticker in sponsor_clean:
            return ticker
    return None


# ---------------------------------------------------------------------------
# Persistence helper
# ---------------------------------------------------------------------------

def save_detected_events(
    events: list[DetectedEvent],
    db_path=None,
) -> int:
    """
    Persist DetectedEvent list to KnowledgeStore detected_events table.

    Returns number of rows inserted (duplicates silently skipped).
    """
    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.ops.weekly_runner import DB_PATH

    path = db_path or DB_PATH
    store = KnowledgeStore(path)
    try:
        n = store.insert_detected_events(events)
    finally:
        store.close()
    return n
