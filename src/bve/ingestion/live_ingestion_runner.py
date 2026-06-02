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
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
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


# ---------------------------------------------------------------------------
# Item-type → text mapping for 8-K items (used to build classifiable text)
# ---------------------------------------------------------------------------

_8K_ITEM_PHRASES: dict[str, str] = {
    "1.01": "enters material definitive agreement partnership licensing deal",
    "1.02": "material agreement terminated",
    "2.05": "announces restructuring cost exit disposal plan",
    "2.06": "reports material impairment charge write-down",
    "7.01": "regulation FD disclosure financial results guidance",
    "8.01": "other events material announcement",
    "9.01": "financial statements exhibits",
}

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

    def fetch(
        self,
        ticker: str,
        profile_data: dict[str, Any],
        lookback_days: int,
    ) -> list[RawIngestionItem]:
        import requests

        ticker = ticker.upper()
        cik = self._resolve_cik(ticker)
        if not cik:
            logger.debug("SEC: no CIK found for %s", ticker)
            return []

        url = f"{self._EDGAR_BASE}/submissions/CIK{cik}.json"
        try:
            r = requests.get(url, headers=self._HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            logger.warning("SEC: fetch failed for %s: %s", ticker, exc)
            return []

        recent = data.get("filings", {}).get("recent", {})
        forms    = recent.get("form", [])
        dates    = recent.get("filingDate", [])
        accnos   = recent.get("accessionNumber", [])
        pri_docs = recent.get("primaryDocument", [])
        items_list = recent.get("items", [""] * len(forms))

        cutoff = date.today() - timedelta(days=lookback_days)
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
        return results

    def _resolve_cik(self, ticker: str) -> str | None:
        import requests
        if ticker in self._TICKER_CACHE:
            return self._TICKER_CACHE[ticker]
        try:
            r = requests.get(self._TICKERS_URL, headers=self._HEADERS, timeout=30)
            r.raise_for_status()
            for entry in r.json().values():
                sym = str(entry.get("ticker", "")).upper()
                if sym:
                    self._TICKER_CACHE[sym] = str(entry["cik_str"]).zfill(10)
        except Exception:
            pass
        return self._TICKER_CACHE.get(ticker)

    @staticmethod
    def _items_to_text(items_str: str, ticker: str) -> str:
        phrases = [
            _8K_ITEM_PHRASES[item]
            for item in items_str.strip().split()
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
    ) -> list[RawIngestionItem]:
        from bve.ingestion.ctgov_client import search_trials

        sponsor = profile_data.get("name") or ticker
        lead_asset = profile_data.get("lead_asset", "")
        drug_name = lead_asset or sponsor

        cutoff = date.today() - timedelta(days=lookback_days)
        results: list[RawIngestionItem] = []

        try:
            raw_events = search_trials(
                drug_name=drug_name,
                limit=20,
            )
        except Exception as exc:
            logger.warning("CTGov: fetch failed for %s: %s", ticker, exc)
            return []

        for ev in raw_events:
            payload = ev.payload
            last_update_str = payload.get("last_update_submitted", "")
            try:
                last_update = date.fromisoformat(last_update_str[:10])
            except (ValueError, TypeError):
                last_update = date.today()

            if last_update < cutoff:
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

    def fetch(
        self,
        ticker: str,
        profile_data: dict[str, Any],
        lookback_days: int,
    ) -> list[RawIngestionItem]:
        from bve.ingestion.fda_client import fetch_approvals

        lead_asset = profile_data.get("lead_asset", "")
        if not lead_asset:
            return []

        cutoff = date.today() - timedelta(days=lookback_days)
        results: list[RawIngestionItem] = []

        try:
            raw_events = fetch_approvals(drug_name=lead_asset, limit=10)
        except Exception as exc:
            logger.warning("FDA: fetch failed for %s: %s", ticker, exc)
            return []

        for ev in raw_events:
            payload = ev.payload
            submissions = payload.get("submissions", [])
            # Find the most recent approval-action submission
            approval_date = self._latest_approval_date(submissions)
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
        return results

    @staticmethod
    def _latest_approval_date(submissions: list[dict]) -> date | None:
        best: date | None = None
        for sub in submissions:
            action = sub.get("submission_type", "")
            action_date_str = sub.get("submission_status_date", "")
            if action in ("ORIG-1", "SUPPL") and action_date_str:
                try:
                    d = date.fromisoformat(action_date_str[:10])
                    if best is None or d > best:
                        best = d
                except ValueError:
                    pass
        return best


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
        classifier: Optional[Callable] = None,
        materiality_est: Optional[Callable] = None,
        context_engine: Optional[Callable] = None,
        clusterer: Optional[Callable] = None,
        review_gate: Optional[Callable] = None,
    ) -> None:
        self._sec = sec_source or SecEightKSource().fetch
        self._ctgov = ctgov_source or CTGovSource().fetch
        self._fda = fda_source or FDASource().fetch

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

    def run(
        self,
        targets: dict[str, Any],   # ticker → TargetProfileEnriched (or dict)
        acquirers: dict[str, Any],  # ticker → AcquirerProfileEnriched (or dict)
        ledger: Any,                # EvidenceLedger
        as_of_date: date,
        lookback_days: int = 14,
        output_dir: Optional[Path] = None,
        dry_run: bool = False,
    ) -> IngestionRunResult:
        """
        Run the full ingestion pipeline for all tickers in the universe.

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

        # Collect all raw items
        items: list[tuple[RawIngestionItem, str]] = []  # (item, role)
        source_breakdown: dict[str, int] = {"sec_filing": 0, "clinicaltrials_gov": 0, "fda_website": 0}

        for ticker, (role, pdata) in all_profiles.items():
            for fetch_fn, src_key in [
                (self._sec,   "sec_filing"),
                (self._ctgov, "clinicaltrials_gov"),
                (self._fda,   "fda_website"),
            ]:
                try:
                    raw_items = fetch_fn(ticker, pdata, lookback_days)
                    for item in raw_items:
                        items.append((item, role))
                        source_breakdown[src_key] = source_breakdown.get(src_key, 0) + 1
                except Exception as exc:
                    logger.warning("Source %s failed for %s: %s", src_key, ticker, exc)

        # Process pipeline
        events_rows: list[dict] = []
        items_classified = 0
        records_appended = 0
        duplicates_skipped = 0
        unclassified_count = 0

        for item, role in items:
            row, appended = self._process_item(
                item=item,
                role=role,
                ledger=ledger,
                dry_run=dry_run,
                profile_data=all_profiles[item.ticker][1],
            )
            if row is None:
                unclassified_count += 1
                continue
            items_classified += 1
            events_rows.append(row)
            if not dry_run:
                if appended:
                    records_appended += 1
                else:
                    duplicates_skipped += 1

        # Write outputs
        output_paths: list[str] = []
        if not dry_run and output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            csv_path = output_dir / "new_events.csv"
            self._write_events_csv(events_rows, csv_path)
            output_paths.append(str(csv_path))

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
