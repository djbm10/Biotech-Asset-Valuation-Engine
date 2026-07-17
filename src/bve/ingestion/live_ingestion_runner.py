"""
Live ingestion runner: real sources → normalised items → classified events → deduped ledger.

Pipeline (per item)::

    RawIngestionItem
    → classify_headline_multi(text, ticker, source_type)
    → skip if UNCLASSIFIED
    → MaterialityEstimator.estimate()
    → _build_context_profile() from target/acquirer profile
    → ContextModifierEngine.apply()   (sign-aware delta scaling)
    → EventClusterer.assign_cluster_id()
    → ReviewGate.needs_review()
    → build EvidenceRecord
    → EvidenceLedger.append_if_not_duplicate()

Sources wired by default::

    SecEightKSource     — EDGAR 8-K filings (lookback window)
    CTGovSource         — ClinicalTrials.gov trial status changes
    FDASource           — openFDA NDA/BLA approvals

All sources are injectable for tests (pass mocks to LiveIngestionRunner.__init__).

Output files::

    outputs/intelligence/evidence_ledger.jsonl   (append-only)
    outputs/weekly/YYYY-MM-DD/new_events.csv      (debug view)

Usage::

    from bve.ingestion.live_ingestion_runner import LiveIngestionRunner
    from bve.ingestion.evidence_ledger import EvidenceLedger

    runner = LiveIngestionRunner()
    result = runner.run(
        targets=target_profiles,
        acquirers=acquirer_profiles,
        ledger=EvidenceLedger(),
        as_of_date=date.today(),
        lookback_days=14,
        output_dir=Path("outputs/weekly/2026-06-02"),
    )
"""
from __future__ import annotations

import csv
import hashlib
import inspect
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Core data containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RawIngestionItem:
    """Normalised container produced by every source adapter."""
    ticker: str
    text: str
    source_type: str                          # sec_filing | clinicaltrials_gov | fda_website
    source_url: str | None
    published_date: date
    raw_payload: dict[str, Any] = field(default_factory=dict)


def _invoke_source_fetch(
    fetch_fn: Callable[..., Any],
    ticker: str,
    profile_data: dict[str, Any],
    lookback_days: int,
    as_of_date: date,
) -> Any:
    """Call a source with the run date while supporting legacy three-argument callables."""
    try:
        signature = inspect.signature(fetch_fn)
    except (TypeError, ValueError):
        # Some extension/builtin callables do not expose a signature. Preserve
        # the historical injection contract rather than guessing and possibly
        # issuing a duplicate request after a TypeError.
        return fetch_fn(ticker, profile_data, lookback_days)

    parameters = signature.parameters
    as_of_parameter = parameters.get("as_of_date")
    if as_of_parameter is not None:
        if as_of_parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            return fetch_fn(ticker, profile_data, lookback_days, as_of_date)
        return fetch_fn(
            ticker,
            profile_data,
            lookback_days,
            as_of_date=as_of_date,
        )
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        return fetch_fn(
            ticker,
            profile_data,
            lookback_days,
            as_of_date=as_of_date,
        )
    if any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in parameters.values()):
        return fetch_fn(ticker, profile_data, lookback_days, as_of_date)
    return fetch_fn(ticker, profile_data, lookback_days)


# Verdict thresholds for SourceHealth. A handful of unclassified records is
# normal noise (especially for news); only an abnormally high rate over a
# meaningful sample is treated as a classifier problem.
_HIGH_UNCLASSIFIED_RATE = 0.9
_MIN_SAMPLE_FOR_UNCLASSIFIED_FLAG = 5


@dataclass(frozen=True)
class SourceHealth:
    """
    Per-source health for a single ingestion run.

    Answers "did this source actually work, or silently return nothing?" via
    a four-state ``verdict`` derived from the counts.
    """
    source_key: str
    tickers_attempted: int = 0
    fetch_failures: int = 0
    failure_samples: tuple[str, ...] = ()
    processing_failures: int = 0
    processing_failure_samples: tuple[str, ...] = ()
    records_fetched: int = 0
    records_classified: int = 0
    records_appended: int = 0
    duplicates_skipped: int = 0
    unclassified: int = 0
    expected_unclassified: int = 0
    request_diagnostics: tuple[dict[str, Any], ...] = ()
    rejection_reasons: tuple[tuple[str, int], ...] = ()

    @property
    def verdict(self) -> str:
        # Every attempt raised → the source is down.
        if self.tickers_attempted > 0 and self.fetch_failures >= self.tickers_attempted:
            return "FAILED"
        # Data arrived but every item failed downstream processing → this
        # source's end-to-end path was unusable for the run.
        if (
            self.records_fetched > 0
            and self.processing_failures >= self.records_fetched
        ):
            return "FAILED"
        # Some fetches or item-processing attempts failed → partial outage.
        if self.fetch_failures > 0 or self.processing_failures > 0:
            return "DEGRADED"
        # Nothing fetched and nothing failed → legitimately quiet window.
        if self.records_fetched == 0:
            return "NO_DATA"
        # Fetched plenty but the classifier resolved almost none → classifier problem.
        actionable_unclassified = self.unclassified - self.expected_unclassified
        if (
            self.records_fetched >= _MIN_SAMPLE_FOR_UNCLASSIFIED_FLAG
            and actionable_unclassified / self.records_fetched >= _HIGH_UNCLASSIFIED_RATE
        ):
            return "DEGRADED"
        return "OK"

    @property
    def verdict_reason(self) -> str:
        if self.tickers_attempted > 0 and self.fetch_failures >= self.tickers_attempted:
            return "all source requests failed"
        if self.records_fetched and self.processing_failures >= self.records_fetched:
            return "all fetched records failed during processing"
        if self.fetch_failures or self.processing_failures:
            return "one or more source or processing attempts failed"
        if self.records_fetched == 0:
            return "requests completed successfully but returned no records"
        actionable_unclassified = self.unclassified - self.expected_unclassified
        if self.records_fetched >= _MIN_SAMPLE_FOR_UNCLASSIFIED_FLAG and actionable_unclassified / self.records_fetched >= _HIGH_UNCLASSIFIED_RATE:
            return "records were fetched but the classifier rejected an abnormally high share"
        return "records fetched and classifier processed them normally"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "verdict": self.verdict,
            "tickers_attempted": self.tickers_attempted,
            "fetch_failures": self.fetch_failures,
            "failure_samples": list(self.failure_samples),
            "processing_failures": self.processing_failures,
            "processing_failure_samples": list(self.processing_failure_samples),
            "records_fetched": self.records_fetched,
            "records_classified": self.records_classified,
            "records_appended": self.records_appended,
            "duplicates_skipped": self.duplicates_skipped,
            "unclassified": self.unclassified,
            "expected_unclassified": self.expected_unclassified,
            "rejected": self.unclassified - self.expected_unclassified,
            "request_diagnostics": list(self.request_diagnostics),
            "rejection_reasons": dict(self.rejection_reasons),
            "verdict_reason": self.verdict_reason,
        }


@dataclass(frozen=True)
class IngestionRunResult:
    as_of_date: date
    lookback_days: int
    items_seen: int
    items_classified: int
    records_appended: int
    duplicates_skipped: int
    unclassified_count: int
    source_breakdown: dict[str, int]
    output_paths: list[str]
    # Per-source health (optional for backward compat with older callers/tests).
    source_health: dict[str, SourceHealth] = field(default_factory=dict)
    processing_failures: int = 0
    processing_failure_samples: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Item-type → text mapping for 8-K items (used to build classifiable text)
# ---------------------------------------------------------------------------

_8K_ITEM_PHRASES: dict[str, str] = {
    # Use classifier vocabulary, not merely a human-readable item label.
    "1.01": "enters into license agreement collaboration agreement partnership agreement",
    "1.02": "termination of collaboration agreement",
    "2.02": "announces quarterly financial results earnings revenue guidance",
    "2.05": "announces restructuring cost exit disposal plan",
    "2.06": "reports material impairment charge write-down",
    "7.01": "regulation FD disclosure financial results guidance",
    "8.01": "other events material announcement",
    "9.01": "financial statements exhibits",
}

_SEC_ACQUISITION_SIGNAL_RE = re.compile(
    r"\b(?:acqui(?:re|red|sition)|merger|definitive agreement|license agreement|"
    r"collaboration|partnership|strategic review|strategic alternatives|"
    r"asset sale|divestiture|offering|private placement|registered direct|"
    r"tender offer|business development)\b",
    re.IGNORECASE,
)


def _is_expected_sec_non_event(item: RawIngestionItem) -> bool:
    """Return true only for routine 2.02/9.01 filings without BD signals."""
    item_codes = set(re.findall(r"\d+\.\d+", str(item.raw_payload.get("items", ""))))
    return (
        bool(item_codes)
        and item_codes <= {"2.02", "9.01"}
        and not _SEC_ACQUISITION_SIGNAL_RE.search(item.text)
    )

# Trial status → signal text (for CT.gov adapter)
_CTGOV_STATUS_TEXT: dict[str, str] = {
    "TERMINATED":          "trial discontinued terminated withdrawn",
    "WITHDRAWN":           "trial discontinued terminated withdrawn",
    "SUSPENDED":           "trial suspended placed on hold delay",
    "RECRUITING":          "trial initiates begins recruiting enrollment",
    "NOT_YET_RECRUITING":  "trial initiates new study registered",
    "COMPLETED":           "trial completed primary endpoint",
    "ACTIVE_NOT_RECRUITING": "trial active enrollment complete",
}


# ---------------------------------------------------------------------------
# Source adapters
# ---------------------------------------------------------------------------

class SecEightKSource:
    """
    Fetches recent 8-K filings from EDGAR for a single ticker.

    Uses the EDGAR submissions API (CIK-based) to pull form metadata and
    constructs classifiable text from 8-K item numbers.
    """

    _EDGAR_BASE = "https://data.sec.gov"
    _TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    _HEADERS = {"User-Agent": "BVE Analytics research@bve.local"}
    _TICKER_CACHE: dict[str, str] = {}

    def __init__(self) -> None:
        self.diagnostics: list[dict[str, Any]] = []

    def fetch(
        self,
        ticker: str,
        profile_data: dict[str, Any],
        lookback_days: int,
        as_of_date: date | None = None,
    ) -> list[RawIngestionItem]:
        import requests

        ticker = ticker.upper()
        anchor_date = as_of_date or date.today()
        cik = self._resolve_cik(ticker)
        if not cik:
            logger.debug("SEC: no CIK found for %s", ticker)
            return []

        url = f"{self._EDGAR_BASE}/submissions/CIK{cik}.json"
        r = requests.get(url, headers=self._HEADERS, timeout=30)
        self.diagnostics.append({"url": r.url, "status": r.status_code, "records_returned": 0})
        r.raise_for_status()
        data = r.json()

        recent = data.get("filings", {}).get("recent", {})
        forms    = recent.get("form", [])
        dates    = recent.get("filingDate", [])
        accnos   = recent.get("accessionNumber", [])
        pri_docs = recent.get("primaryDocument", [])
        items_list = recent.get("items", [""] * len(forms))

        cutoff = anchor_date - timedelta(days=lookback_days)
        results: list[RawIngestionItem] = []

        for form, filing_date_str, accno, pri_doc, items_str in zip(
            forms, dates, accnos, pri_docs, items_list
        ):
            if form != "8-K":
                continue
            try:
                filing_date = date.fromisoformat(filing_date_str)
            except ValueError:
                continue
            if filing_date > anchor_date:
                continue
            if filing_date < cutoff:
                break  # EDGAR returns newest-first

            text = self._items_to_text(items_str or "", ticker)
            acc_clean = accno.replace("-", "")
            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}"
                f"/{acc_clean}/{pri_doc}"
            )
            results.append(RawIngestionItem(
                ticker=ticker,
                text=text,
                source_type="sec_filing",
                source_url=filing_url,
                published_date=filing_date,
                raw_payload={
                    "form_type": form,
                    "accession_number": accno,
                    "filing_date": filing_date_str,
                    "items": items_str,
                },
            ))
        self.diagnostics[-1]["records_returned"] = len(results)
        self.diagnostics[-1]["records_parsed"] = len(results)
        return results

    def _resolve_cik(self, ticker: str) -> str | None:
        import requests
        if ticker in self._TICKER_CACHE:
            return self._TICKER_CACHE[ticker]
        r = requests.get(self._TICKERS_URL, headers=self._HEADERS, timeout=30)
        r.raise_for_status()
        for entry in r.json().values():
            sym = str(entry.get("ticker", "")).upper()
            if sym:
                self._TICKER_CACHE[sym] = str(entry["cik_str"]).zfill(10)
        return self._TICKER_CACHE.get(ticker)

    @staticmethod
    def _items_to_text(items_str: str, ticker: str) -> str:
        # SEC submissions uses comma-separated item numbers (for example
        # ``2.02,9.01``); older fixtures used whitespace.  Accept both.
        import re
        item_numbers = re.findall(r"\d+\.\d+", items_str)
        phrases = [
            _8K_ITEM_PHRASES[item]
            for item in item_numbers
            if item in _8K_ITEM_PHRASES
        ]
        if phrases:
            return f"{ticker} " + " ".join(phrases)
        return f"{ticker} filed Form 8-K regulatory report"


class CTGovSource:
    """
    Fetches recent trial status changes from ClinicalTrials.gov.

    Searches by sponsor (company name) and returns items for trials
    updated within the lookback window.
    """

    def fetch(
        self,
        ticker: str,
        profile_data: dict[str, Any],
        lookback_days: int,
        as_of_date: date | None = None,
    ) -> list[RawIngestionItem]:
        from bve.ingestion.ctgov_client import search_trials

        sponsor = profile_data.get("name") or ticker
        lead_asset = profile_data.get("lead_asset", "")
        drug_name = lead_asset or sponsor

        anchor_date = as_of_date or date.today()
        cutoff = anchor_date - timedelta(days=lookback_days)
        results: list[RawIngestionItem] = []

        raw_events = search_trials(drug_name=drug_name, limit=20)
        if lead_asset and sponsor and sponsor != lead_asset:
            sponsor_events = search_trials(drug_name=sponsor, limit=20)
            seen_nct = {
                str(ev.payload.get("nct_id") or "")
                for ev in raw_events
                if getattr(ev, "payload", None)
            }
            for ev in sponsor_events:
                nct_id = str(ev.payload.get("nct_id") or "")
                if nct_id and nct_id in seen_nct:
                    continue
                raw_events.append(ev)
                if nct_id:
                    seen_nct.add(nct_id)

        for ev in raw_events:
            payload = ev.payload
            last_update_str = payload.get("last_update_submitted", "")
            try:
                last_update = date.fromisoformat(last_update_str[:10])
            except (ValueError, TypeError):
                last_update = anchor_date

            if last_update < cutoff or last_update > anchor_date:
                continue

            status = payload.get("status", "")
            phase_list = payload.get("phases", [])
            phase_str = " ".join(phase_list).replace("PHASE", "Phase ")
            title = payload.get("brief_title", "")
            nct_id = payload.get("nct_id", "")
            status_text = _CTGOV_STATUS_TEXT.get(status, f"trial status {status}")

            text = f"{ticker} {phase_str} {status_text} {title} {nct_id}".strip()
            results.append(RawIngestionItem(
                ticker=ticker,
                text=text,
                source_type="clinicaltrials_gov",
                source_url=ev.source_url,
                published_date=last_update,
                raw_payload=payload,
            ))
        return results


class FDASource:
    """
    Fetches FDA approval actions from openFDA for a ticker's lead asset.

    Matches on drug name; filters by approval date within lookback window.
    """

    def __init__(self) -> None:
        self.diagnostics: list[dict[str, Any]] = []

    def fetch(
        self,
        ticker: str,
        profile_data: dict[str, Any],
        lookback_days: int,
        as_of_date: date | None = None,
    ) -> list[RawIngestionItem]:
        from bve.ingestion.fda_client import fetch_approvals

        lead_asset = profile_data.get("lead_asset", "")
        if not lead_asset:
            return []

        anchor_date = as_of_date or date.today()
        cutoff = anchor_date - timedelta(days=lookback_days)
        results: list[RawIngestionItem] = []

        raw_events = fetch_approvals(
            drug_name=lead_asset, limit=10, diagnostics=self.diagnostics
        )

        for ev in raw_events:
            payload = ev.payload
            submissions = payload.get("submissions", [])
            # Find the most recent approval-action submission
            approval_date = self._latest_approval_date(
                submissions,
                as_of_date=anchor_date,
            )
            if approval_date is None or approval_date < cutoff:
                continue

            brand_names = [
                p.get("brand_name", "") for p in payload.get("products", []) if p.get("brand_name")
            ]
            drug_label = brand_names[0] if brand_names else lead_asset
            text = f"{ticker} FDA approves {drug_label} NDA BLA approval granted"

            results.append(RawIngestionItem(
                ticker=ticker,
                text=text,
                source_type="fda_website",
                source_url=ev.source_url,
                published_date=approval_date,
                raw_payload=payload,
            ))
        if self.diagnostics:
            self.diagnostics[-1]["records_parsed"] = len(raw_events)
            self.diagnostics[-1]["records_selected"] = len(results)
            if not results:
                if raw_events:
                    self.diagnostics[-1]["zero_match_reason"] = "outside_date_window"
                elif "zero_match_reason" not in self.diagnostics[-1]:
                    self.diagnostics[-1]["zero_match_reason"] = "no_match"
        return results

    @staticmethod
    def _latest_approval_date(
        submissions: list[dict],
        as_of_date: date | None = None,
    ) -> date | None:
        best: date | None = None
        for sub in submissions:
            action = sub.get("submission_type", "")
            action_date_str = sub.get("submission_status_date", "")
            if action in ("ORIG", "ORIG-1", "SUPPL") and action_date_str:
                try:
                    d = date.fromisoformat(action_date_str[:10])
                    if as_of_date is not None and d > as_of_date:
                        continue
                    if best is None or d > best:
                        best = d
                except ValueError:
                    pass
        return best


def _parse_event_date(raw: Any) -> date | None:
    if not raw:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    text = str(raw).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _raw_event_to_item(
    *,
    event: Any,
    ticker: str,
    source_type: str,
    default_date: date,
) -> RawIngestionItem:
    payload = dict(getattr(event, "payload", {}) or {})
    title = payload.get("title") or payload.get("entity_name") or ""
    summary = payload.get("summary") or ""
    form_type = payload.get("form_type") or ""
    text = f"{ticker} {title} {summary} {form_type}".strip()
    published = (
        _parse_event_date(payload.get("published"))
        or _parse_event_date(payload.get("filing_date"))
        or _parse_event_date(payload.get("period_of_report"))
        or default_date
    )
    return RawIngestionItem(
        ticker=ticker.upper(),
        text=text,
        source_type=source_type,
        source_url=getattr(event, "source_url", None),
        published_date=published,
        raw_payload=payload,
    )


class PressReleaseSource:
    """
    Fetches official/company press-release-like records.

    This uses the existing SEC full-text press release client and converts its
    RawEvent objects into the runner's RawIngestionItem shape.
    """

    def fetch(
        self,
        ticker: str,
        profile_data: dict[str, Any],
        lookback_days: int,
        as_of_date: date | None = None,
    ) -> list[RawIngestionItem]:
        from bve.ingestion.news_client import fetch_sec_press_releases

        anchor_date = as_of_date or date.today()
        cutoff = anchor_date - timedelta(days=lookback_days)
        raw_events = fetch_sec_press_releases(ticker=ticker, limit=10)

        items: list[RawIngestionItem] = []
        for event in raw_events:
            item = _raw_event_to_item(
                event=event,
                ticker=ticker,
                source_type="press_release",
                default_date=anchor_date,
            )
            if cutoff <= item.published_date <= anchor_date:
                items.append(item)
        return items


class NewsArticleSource:
    """
    Fetches broader company news.

    Uses NEWS_API_KEY when available; otherwise falls back to BioSpace RSS.
    Kept as a separate opt-in source because broad news is noisier than
    official press releases, SEC filings, CT.gov, or FDA.
    """

    def fetch(
        self,
        ticker: str,
        profile_data: dict[str, Any],
        lookback_days: int,
        as_of_date: date | None = None,
    ) -> list[RawIngestionItem]:
        from bve.ingestion.news_client import fetch_biospace_news, fetch_newsapi_articles

        company = profile_data.get("name") or ticker
        api_key = os.getenv("NEWS_API_KEY", "")
        anchor_date = as_of_date or date.today()
        cutoff = anchor_date - timedelta(days=lookback_days)
        if api_key:
            raw_events = fetch_newsapi_articles(
                query=f'"{company}" OR {ticker}',
                api_key=api_key,
                ticker=ticker,
                limit=10,
            )
        else:
            raw_events = fetch_biospace_news(ticker=ticker, limit=10)

        items: list[RawIngestionItem] = []
        for event in raw_events:
            item = _raw_event_to_item(
                event=event,
                ticker=ticker,
                source_type="news_article",
                default_date=anchor_date,
            )
            if cutoff <= item.published_date <= anchor_date:
                items.append(item)
        return items


# Synthetic fallback text used when the real filing document cannot be fetched.
# Carries the generic earnings keywords so downstream classification still has
# a signal, but it can never produce a directional guidance verdict.
_EARNINGS_FALLBACK_TEXT = (
    "reports quarterly earnings financial results revenue cash runway guidance"
)

# Cap on how much filing body text we keep for classification. Guidance /
# results language appears in the first page or two; this bounds memory and
# keeps the regex pass fast.
_FILING_TEXT_MAX_CHARS = 4000


def fetch_filing_text(url: str) -> str:
    """
    Best-effort fetch of an SEC filing's primary document as plain text.

    Strips HTML tags, collapses whitespace, and truncates. Returns "" on any
    failure so callers can fall back to a synthetic stub. Never raises.
    """
    if not url:
        return ""
    try:
        import re as _re

        import requests

        r = requests.get(
            url,
            headers={"User-Agent": "BVE Analytics research@bve.local"},
            timeout=30,
        )
        r.raise_for_status()
        body = _re.sub(r"<[^>]+>", " ", r.text)
        body = _re.sub(r"\s+", " ", body).strip()
        return body[:_FILING_TEXT_MAX_CHARS]
    except Exception as exc:  # noqa: BLE001 — best-effort, fall back to stub
        logger.debug("Earnings: document fetch failed for %s: %s", url, exc)
        return ""


class EarningsReleaseSource:
    """
    Fetches earnings-related 8-Ks as an explicit source.

    This reuses SEC 8-K metadata and keeps only Item 2.02 filings, which are
    commonly used for results of operations / financial condition.

    The synthetic 8-K item-number text is too generic to classify guidance
    direction, so this source fetches the actual filing document body (via the
    injectable ``doc_fetcher``) and classifies that. If the document cannot be
    retrieved, it falls back to a generic earnings stub.
    """

    def __init__(
        self,
        sec_source: Optional[SecEightKSource] = None,
        doc_fetcher: Optional[Callable[[str], str]] = None,
    ) -> None:
        self._sec_source = sec_source or SecEightKSource()
        self._doc_fetcher = doc_fetcher or fetch_filing_text

    def fetch(
        self,
        ticker: str,
        profile_data: dict[str, Any],
        lookback_days: int,
        as_of_date: date | None = None,
    ) -> list[RawIngestionItem]:
        anchor_date = as_of_date or date.today()
        items = _invoke_source_fetch(
            self._sec_source.fetch,
            ticker,
            profile_data,
            lookback_days,
            anchor_date,
        )
        results: list[RawIngestionItem] = []
        for item in items:
            item_numbers = str(item.raw_payload.get("items", ""))
            if "2.02" not in item_numbers:
                continue
            body = self._doc_fetcher(item.source_url or "")
            if body:
                text = f"{item.ticker} earnings: {body}"
            else:
                text = f"{item.ticker} {_EARNINGS_FALLBACK_TEXT}"
            results.append(RawIngestionItem(
                ticker=item.ticker,
                text=text,
                source_type="earnings_release",
                source_url=item.source_url,
                published_date=item.published_date,
                raw_payload=item.raw_payload,
            ))
        return results


# ---------------------------------------------------------------------------
# Context profile builder
# ---------------------------------------------------------------------------

def _build_context_profile(
    profile_data: dict[str, Any],
    raw_text: str,
    event_type: str,
) -> Any:  # returns ContextProfile
    from bve.ingestion.context_modifiers import ContextProfile

    text_lower = raw_text.lower()
    phase = profile_data.get("lead_asset_phase", "")
    late_stage = phase in ("phase_3", "commercial", "approved", "nda_filed")

    return ContextProfile(
        safety_flag=(
            "safety" in text_lower
            or "toxicity" in text_lower
            or "adverse" in text_lower
            or "serious" in text_lower
        ),
        is_lead_asset=True,  # all events assumed to involve the lead asset by default
        biomarker_only=(
            "biomarker" in text_lower
            or "subgroup" in text_lower
            or "selected patients" in text_lower
        ),
        open_label=(
            "open-label" in text_lower
            or "open label" in text_lower
        ),
        pivotal_design=(
            "pivotal" in text_lower
            or "confirmatory" in text_lower
            or "registration" in text_lower
        ),
        late_stage_pipeline=late_stage,
    )


# ---------------------------------------------------------------------------
# EvidenceRecord builder (bridges MultiLabelClassification → EvidenceRecord)
# ---------------------------------------------------------------------------

def _build_evidence_record(
    mlc: Any,
    event_date: str,
    source_url: str,
    modified_deltas: dict[str, float],
    published_date: str | None = None,
) -> Any:  # returns EvidenceRecord
    """
    Build an EvidenceRecord from a MultiLabelClassification result.

    Uses modified_deltas (post-context-modifier) rather than the raw combined deltas.
    Replicates the hash logic from EvidenceLedger._compute_event_hash.
    """
    from bve.ingestion.evidence_ledger import EvidenceRecord

    norm_text = " ".join(mlc.raw_text.lower().split())[:200]
    raw = f"{mlc.ticker.upper()}|{norm_text}|{event_date}|{mlc.primary_event}"
    evt_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]

    return EvidenceRecord(
        ticker=mlc.ticker,
        event_date=event_date,
        event_type=mlc.primary_event,
        direction=mlc.direction,
        phase_detected=mlc.phase_detected,
        source_type=mlc.source_type,
        source_url=source_url,
        raw_text=mlc.raw_text,
        confidence=mlc.confidence,
        match_reasons=mlc.match_reasons,
        score_deltas=modified_deltas,
        published_date=published_date or event_date,
        event_hash=evt_hash,
    )


# ---------------------------------------------------------------------------
# Company role helper
# ---------------------------------------------------------------------------

def _company_role(
    ticker: str,
    target_tickers: frozenset[str],
    acquirer_tickers: frozenset[str],
) -> str:
    is_target = ticker in target_tickers
    is_acquirer = ticker in acquirer_tickers
    if is_target and is_acquirer:
        return "both"
    if is_acquirer:
        return "acquirer"
    return "target"


# ---------------------------------------------------------------------------
# new_events.csv columns
# ---------------------------------------------------------------------------

_NEW_EVENTS_FIELDS = [
    "ticker",
    "company_role",
    "event_type",
    "direction",
    "confidence",
    "materiality",
    "novelty",
    "source_type",
    "published_date",
    "source_url",
    "event_cluster_id",
    "human_review_required",
    "score_deltas",
    "raw_text",
]


# ---------------------------------------------------------------------------
# LiveIngestionRunner
# ---------------------------------------------------------------------------

class LiveIngestionRunner:
    """
    Orchestrates the full live ingestion pipeline.

    All collaborators are injectable so tests can run with zero network calls.

    Parameters
    ----------
    sec_source        : callable(ticker, profile_data, lookback_days) → list[RawIngestionItem]
    ctgov_source      : callable(ticker, profile_data, lookback_days) → list[RawIngestionItem]
    fda_source        : callable(ticker, profile_data, lookback_days) → list[RawIngestionItem]
    press_source      : callable(ticker, profile_data, lookback_days) → list[RawIngestionItem]
    earnings_source   : callable(ticker, profile_data, lookback_days) → list[RawIngestionItem]
    news_source       : callable(ticker, profile_data, lookback_days) → list[RawIngestionItem]
    classifier        : callable(text, ticker, source_type) → MultiLabelClassification
    materiality_est   : callable(event_type, source_type, context_hints) → MaterialityEstimate
    context_engine    : callable(deltas, event_type, profile) → dict[str,float]
    clusterer         : callable(record) → str  (returns cluster_id)
    review_gate       : callable(materiality_score) → bool  (needs_review?)
    """

    def __init__(
        self,
        sec_source: Optional[Callable] = None,
        ctgov_source: Optional[Callable] = None,
        fda_source: Optional[Callable] = None,
        press_source: Optional[Callable] = None,
        earnings_source: Optional[Callable] = None,
        news_source: Optional[Callable] = None,
        classifier: Optional[Callable] = None,
        materiality_est: Optional[Callable] = None,
        context_engine: Optional[Callable] = None,
        clusterer: Optional[Callable] = None,
        review_gate: Optional[Callable] = None,
    ) -> None:
        self._sec = sec_source or SecEightKSource().fetch
        self._ctgov = ctgov_source or CTGovSource().fetch
        self._fda = fda_source or FDASource().fetch
        self._press = press_source or PressReleaseSource().fetch
        self._earnings = earnings_source or EarningsReleaseSource().fetch
        self._news = news_source or NewsArticleSource().fetch

        if classifier is None:
            from bve.ingestion.event_classifier import classify_headline_multi
            classifier = classify_headline_multi
        self._classify = classifier

        if materiality_est is None:
            from bve.ingestion.materiality_estimator import MaterialityEstimator
            materiality_est = MaterialityEstimator().estimate
        self._mat = materiality_est

        if context_engine is None:
            from bve.ingestion.context_modifiers import ContextModifierEngine
            context_engine = ContextModifierEngine().apply
        self._ctx = context_engine

        if clusterer is None:
            from bve.ingestion.event_cluster import EventClusterer
            clusterer = EventClusterer().assign_cluster_id
        self._cluster = clusterer

        if review_gate is None:
            from bve.ingestion.review_gate import ReviewGate
            review_gate = ReviewGate().needs_review
        self._review = review_gate

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Canonical mapping: CLI flag name → (fetch_fn, source_type_key)
    _SOURCE_REGISTRY: dict[str, tuple[str, str]] = {
        "sec":            ("_sec",                 "sec_filing"),
        "clinicaltrials": ("_ctgov",               "clinicaltrials_gov"),
        "fda":            ("_fda",                 "fda_website"),
        "press_releases": ("_press",               "press_release"),
        "earnings_calls": ("_earnings",            "earnings_release"),
        "news_articles":  ("_news",                "news_article"),
    }

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        targets: dict[str, Any],   # ticker → TargetProfileEnriched (or dict)
        acquirers: dict[str, Any],  # ticker → AcquirerProfileEnriched (or dict)
        ledger: Any,                # EvidenceLedger
        as_of_date: date,
        lookback_days: int = 14,
        output_dir: Optional[Path] = None,
        dry_run: bool = False,
        sources: Optional[list[str]] = None,
    ) -> IngestionRunResult:
        """
        Run the full ingestion pipeline for all tickers in the universe.

        Parameters
        ----------
        sources:
            List of source names to run. Accepted values: ``sec``,
            ``clinicaltrials``, ``fda``, ``press_releases``,
            ``earnings_calls``, ``news_articles``. Pass ``None`` (default) to
            run the three core live sources (sec, clinicaltrials, fda).
            Unknown names and an empty list are configuration errors.

        Returns an IngestionRunResult with counts and output paths.
        """
        target_tickers = frozenset(targets.keys())
        acquirer_tickers = frozenset(acquirers.keys())
        all_profiles: dict[str, tuple[str, dict[str, Any]]] = {}  # ticker → (role, profile_data)

        for ticker, profile in targets.items():
            all_profiles[ticker] = (
                _company_role(ticker, target_tickers, acquirer_tickers),
                self._profile_to_dict(profile),
            )
        for ticker, profile in acquirers.items():
            if ticker not in all_profiles:
                all_profiles[ticker] = ("acquirer", self._profile_to_dict(profile))

        # Build the ordered list of (fetch_fn, src_key) pairs based on the sources filter
        _default_sources = ["sec", "clinicaltrials", "fda"]
        requested = sources if sources is not None else _default_sources
        if not requested:
            raise ValueError("At least one live ingestion source must be requested")
        unknown_sources = [name for name in requested if name not in self._SOURCE_REGISTRY]
        if unknown_sources:
            accepted = ", ".join(self._SOURCE_REGISTRY)
            unknown = ", ".join(str(name) for name in unknown_sources)
            raise ValueError(
                f"Unknown live ingestion source(s): {unknown}. Accepted sources: {accepted}"
            )

        active_sources: list[tuple[Any, str]] = []
        for name in requested:
            attr_name, src_key = self._SOURCE_REGISTRY[name]
            fn = getattr(self, attr_name)
            active_sources.append((fn, src_key))
        if not active_sources:
            raise ValueError("No active live ingestion sources were configured")

        # Collect all raw items
        items: list[tuple[RawIngestionItem, str, str]] = []  # (item, role, src_key)
        source_breakdown: dict[str, int] = {src_key: 0 for _, src_key in active_sources}

        # Per-source health accumulators (mutable; frozen into SourceHealth later).
        health: dict[str, dict[str, Any]] = {
            src_key: {
                "attempted": 0, "failures": 0, "samples": [], "fetched": 0,
                "classified": 0, "appended": 0, "duplicates": 0, "unclassified": 0,
                "processing_failures": 0, "processing_samples": [],
                "request_diagnostics": [], "rejection_reasons": {},
                "expected_unclassified": 0,
            }
            for _, src_key in active_sources
        }

        for ticker, (role, pdata) in all_profiles.items():
            for fetch_fn, src_key in active_sources:
                h = health[src_key]
                h["attempted"] += 1
                try:
                    raw_items = _invoke_source_fetch(
                        fetch_fn,
                        ticker,
                        pdata,
                        lookback_days,
                        as_of_date,
                    )
                    diagnostics_owner = getattr(fetch_fn, "__self__", None)
                    source_diagnostics = getattr(diagnostics_owner, "diagnostics", None)
                    if source_diagnostics:
                        h["request_diagnostics"].extend(source_diagnostics[-1:])
                    for item in raw_items:
                        items.append((item, role, src_key))
                        source_breakdown[src_key] = source_breakdown.get(src_key, 0) + 1
                        h["fetched"] += 1
                except Exception as exc:
                    h["failures"] += 1
                    if len(h["samples"]) < 5:
                        h["samples"].append(f"{ticker}: {exc}")
                    logger.warning("Source %s failed for %s: %s", src_key, ticker, exc)

        # Process pipeline
        events_rows: list[dict] = []
        items_classified = 0
        records_appended = 0
        duplicates_skipped = 0
        unclassified_count = 0
        processing_failures = 0
        processing_failure_samples: list[str] = []

        for item, role, src_key in items:
            h = health[src_key]
            try:
                profile_data = all_profiles[item.ticker][1]
                row, appended = self._process_item(
                    item=item,
                    role=role,
                    ledger=ledger,
                    dry_run=dry_run,
                    profile_data=profile_data,
                )
            except Exception as exc:
                processing_failures += 1
                h["processing_failures"] += 1
                item_ticker = str(getattr(item, "ticker", "<unknown>"))
                item_url = str(getattr(item, "source_url", "") or "")
                item_identity = f"{item_ticker} {item_url}".strip()
                sample = f"{item_identity}: {type(exc).__name__}: {exc}"
                if len(h["processing_samples"]) < 5:
                    h["processing_samples"].append(sample)
                if len(processing_failure_samples) < 10:
                    processing_failure_samples.append(f"{src_key}: {sample}")
                logger.warning(
                    "Item processing failed for %s from %s: %s",
                    item_identity,
                    src_key,
                    exc,
                )
                continue
            if row is None:
                unclassified_count += 1
                h["unclassified"] += 1
                item_code = str(item.raw_payload.get("items", "")).strip()
                expected_non_event = (
                    src_key == "sec_filing" and _is_expected_sec_non_event(item)
                )
                if expected_non_event:
                    h["expected_unclassified"] += 1
                reason = (
                    f"expected_non_event:item={item_code}"
                    if expected_non_event else
                    f"classifier:unclassified:item={item_code}"
                    if item_code else "classifier:unclassified"
                )
                h["rejection_reasons"][reason] = h["rejection_reasons"].get(reason, 0) + 1
                continue
            items_classified += 1
            h["classified"] += 1
            events_rows.append(row)
            if not dry_run:
                if appended:
                    records_appended += 1
                    h["appended"] += 1
                else:
                    duplicates_skipped += 1
                    h["duplicates"] += 1

        # Write outputs
        output_paths: list[str] = []
        if not dry_run and output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            csv_path = output_dir / "new_events.csv"
            self._write_events_csv(events_rows, csv_path)
            output_paths.append(str(csv_path))

        source_health = {
            src_key: SourceHealth(
                source_key=src_key,
                tickers_attempted=h["attempted"],
                fetch_failures=h["failures"],
                failure_samples=tuple(h["samples"]),
                processing_failures=h["processing_failures"],
                processing_failure_samples=tuple(h["processing_samples"]),
                request_diagnostics=tuple(h["request_diagnostics"]),
                rejection_reasons=tuple(sorted(h["rejection_reasons"].items())),
                expected_unclassified=h["expected_unclassified"],
                records_fetched=h["fetched"],
                records_classified=h["classified"],
                records_appended=h["appended"],
                duplicates_skipped=h["duplicates"],
                unclassified=h["unclassified"],
            )
            for src_key, h in health.items()
        }

        return IngestionRunResult(
            as_of_date=as_of_date,
            lookback_days=lookback_days,
            items_seen=len(items),
            items_classified=items_classified,
            records_appended=records_appended,
            duplicates_skipped=duplicates_skipped,
            unclassified_count=unclassified_count,
            source_breakdown=source_breakdown,
            output_paths=output_paths,
            source_health=source_health,
            processing_failures=processing_failures,
            processing_failure_samples=tuple(processing_failure_samples),
        )

    # ------------------------------------------------------------------
    # Per-item pipeline
    # ------------------------------------------------------------------

    def _process_item(
        self,
        item: RawIngestionItem,
        role: str,
        ledger: Any,
        dry_run: bool,
        profile_data: dict[str, Any],
    ) -> tuple[dict | None, bool]:
        """
        Run a single RawIngestionItem through the pipeline.

        Returns (csv_row_dict | None, was_appended).
        None means the item was unclassified and should be skipped.
        """
        from bve.ingestion.event_classifier import UNCLASSIFIED

        # 1. Classify
        mlc = self._classify(item.text, item.ticker, item.source_type)
        if mlc.primary_event == UNCLASSIFIED:
            return None, False

        event_date = item.published_date.isoformat()

        # 2. Materiality
        context_hints = {
            "safety_flag": "safety" in item.text.lower(),
            "is_lead_asset": True,
        }
        mat_est = self._mat(mlc.primary_event, item.source_type, context_hints)

        # 3. Context profile + modifier
        ctx_profile = _build_context_profile(profile_data, item.text, mlc.primary_event)
        modified_deltas = self._ctx(mlc.combined_score_deltas, mlc.primary_event, ctx_profile)

        # 4. Cluster ID
        cluster_id = self._cluster(mlc)

        # 5. Review flag
        human_review = self._review(mat_est.materiality)

        # 6. Build EvidenceRecord
        record = _build_evidence_record(
            mlc=mlc,
            event_date=event_date,
            source_url=item.source_url or "",
            modified_deltas=modified_deltas,
            published_date=event_date,
        )

        # 7. Append to ledger (dry_run never writes)
        appended = False
        if not dry_run:
            appended = ledger.append_if_not_duplicate(record)

        row = {
            "ticker": item.ticker,
            "company_role": role,
            "event_type": mlc.primary_event,
            "direction": mlc.direction,
            "confidence": round(mlc.confidence, 4),
            "materiality": round(mat_est.materiality, 4),
            "novelty": round(mat_est.novelty, 4),
            "source_type": item.source_type,
            "published_date": event_date,
            "source_url": item.source_url or "",
            "event_cluster_id": cluster_id,
            "human_review_required": human_review,
            "score_deltas": str(modified_deltas),
            "raw_text": item.text[:200],
        }
        return row, appended

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _profile_to_dict(profile: Any) -> dict[str, Any]:
        """Convert a profile dataclass or dict to a plain dict."""
        if isinstance(profile, dict):
            return profile
        try:
            from dataclasses import asdict
            return asdict(profile)
        except TypeError:
            # Not a dataclass — try __dict__
            return vars(profile) if hasattr(profile, "__dict__") else {}

    @staticmethod
    def _write_events_csv(rows: list[dict], path: Path) -> None:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_NEW_EVENTS_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
