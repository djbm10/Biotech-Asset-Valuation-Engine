"""
Append-only JSONL evidence ledger.

Every event that changes a score is persisted here with full provenance:
  - Source, date, event type, raw text that generated it
  - Confidence level and match reasons (why the classifier fired)
  - Score deltas actually applied (bounded, confidence-weighted)

This ledger enables:
  1. Full audit trail — every score delta has a dated, sourced reason
  2. Score replay — reconstruct score state at any historical date
  3. Evidence export — show the model's reasoning for any target score
  4. Drift detection — compare scores at t-1 and t-0

File: outputs/intelligence/evidence_ledger.jsonl
Format: one JSON object per line, append-only, never overwritten.

Usage::

    from bve.ingestion.evidence_ledger import EvidenceLedger, EvidenceRecord
    from bve.ingestion.event_classifier import classify_headline

    ledger = EvidenceLedger()
    ev = classify_headline("Phase 3 trial met primary endpoint", ticker="RVMD")
    rec = EvidenceRecord.from_classification(ev, event_date="2025-06-01", source_url="https://...")
    ledger.append(rec)

    # Current score state for a ticker
    scores = ledger.compute_score_state("RVMD")

    # Score history (one row per event, ordered by date)
    history = ledger.get_score_history("RVMD")
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from bve.ingestion.event_classifier import EventClassification

_DEFAULT_LEDGER_PATH = (
    Path(__file__).resolve().parents[3] / "outputs" / "intelligence" / "evidence_ledger.jsonl"
)

# Default starting scores when no evidence history exists for a ticker.
# These are neutral priors — not strong claims.
# Low-information names should not look like real targets; see compute_evidence_coverage().
DEFAULT_SEED_SCORES: dict[str, float] = {
    "asset_quality":       0.40,
    "seller_willingness":  0.30,
    "acquirer_fit":        0.50,   # legacy composite key — kept for backward compat
    "acquirer_appetite":   0.50,   # willingness to do deals now
    "integration_capacity": 0.70,  # most large acquirers can integrate
    "acquirer_urgency":    0.30,   # pipeline gap / patent cliff pressure
    "catalyst_timing":     0.30,
}

# Source priority for deduplication — higher = preferred authority.
# If two records share the same event_hash, keep the one with higher priority.
SOURCE_PRIORITY: dict[str, int] = {
    "fda_website":        100,
    "sec_filing":         90,
    "clinicaltrials_gov": 85,
    "pubmed":             80,
    "press_release":      60,
    "news_article":       40,
    "manual":             50,
}

# ---------------------------------------------------------------------------
# Phase 5 signal type vocabulary
# ---------------------------------------------------------------------------

#: Canonical signal_type values for Phase-5 evidence records.
#: These are semantic categories that span both the acquirer and target side of
#: an M&A pair and can be used alongside the lower-level event_type classifier.
VALID_SIGNAL_TYPES: frozenset[str] = frozenset({
    # Acquirer-side signals
    "acquirer_bd_appetite",         # earnings/PR confirms active deal-seeking
    "acquirer_pipeline_gap",        # gap document / TA gap identified from filing
    "acquirer_cash_capacity",       # balance-sheet cash / deal capacity signal
    "acquirer_recent_deal_pattern", # deal history reveals strategic preference
    # Target-side signals
    "target_positive_trial_data",   # Phase 2/3 trial met primary endpoint
    "target_negative_trial_data",   # trial failed or missed primary endpoint
    "target_regulatory_catalyst",   # PDUFA / FDA approval / complete response
    "target_cash_pressure",         # cash runway concern / equity raise / distress
    "target_strategic_review",      # management announces strategic alternatives
    "target_partner_encumbrance",   # partner rights that reduce deal feasibility
    "target_market_cap_feasibility",# deal size within buyer's capacity
    # Pair-specific signals
    "pair_specific_synergy",        # identified positive fit between this pair
    "pair_specific_conflict",       # identified negative fit (constraint/overlap)
})

#: Entity types for Phase-5 evidence records.
VALID_ENTITY_TYPES: frozenset[str] = frozenset({"target", "acquirer", "pair"})

# Stale evidence decay: half-life in days per event type.
# Events with no entry here do NOT decay (e.g. clinical failures persist).
DECAY_HALF_LIFE_DAYS: dict[str, float] = {
    "acquirer_bd_appetite": 90.0,   # BD appetite comments fade quickly
    "acquirer_large_deal":  180.0,  # integration burden fades as deal closes
    "pdufa":                30.0,   # PDUFA date passes; no longer a catalyst
    "equity_raise":         180.0,  # cash infusion fades from awareness
    "partnership":          365.0,  # partnerships persist but matter less over time
    "trial_start":          365.0,  # trial start is old news after ~a year
}


def _compute_event_hash(ticker: str, text: str, event_date: str, event_type: str) -> str:
    """
    Stable 16-char hex hash for deduplication.
    Normalises whitespace and truncates text to first 200 chars before hashing.
    """
    norm_text = " ".join(text.lower().split())[:200]
    raw = f"{ticker.upper()}|{norm_text}|{event_date}|{event_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# EvidenceRecord
# ---------------------------------------------------------------------------


@dataclass
class EvidenceRecord:
    """One persisted evidence event."""

    # Identity
    ticker: str
    event_date: str              # ISO date (YYYY-MM-DD) the event occurred

    # Classification
    event_type: str
    direction: str               # positive | negative | mixed | neutral | unknown
    phase_detected: Optional[str]

    # Source provenance
    source_type: str             # clinicaltrials_gov | sec_filing | press_release | ...
    source_url: str
    raw_text: str

    # Extraction quality
    confidence: float            # 0.0–1.0
    match_reasons: list[str]

    # Score impact — bounded deltas that were (or will be) applied
    score_deltas: dict[str, float]

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ledger_version: str = "1"

    # No-lookahead date discipline:
    # published_date = when this became public knowledge (use for backtest filtering)
    # event_date     = when the underlying event actually occurred
    # If published_date is None, fall back to event_date for filtering.
    published_date: Optional[str] = None   # ISO date: YYYY-MM-DD

    # Deduplication hash: sha256(ticker + normalised_text + event_date + event_type)[:16]
    event_hash: str = ""

    # ---------------------------------------------------------------------------
    # Phase 5 fields — all optional; default None for backward-compat with
    # existing JSONL records that were written before these fields existed.
    # ---------------------------------------------------------------------------

    #: "target" | "acquirer" | "pair" — which side of the pair this record concerns
    entity_type: Optional[str] = None

    #: Semantic signal category from VALID_SIGNAL_TYPES (coarser than event_type)
    signal_type: Optional[str] = None

    #: Signal strength 0.0–1.0 (semantic weight; separate from detection confidence)
    strength: Optional[float] = None

    #: Human-readable one-line explanation of what the record captures
    summary: Optional[str] = None

    #: For entity_type="pair": second ticker in the pair (e.g. "TVTX" if primary is "VRTX")
    pair_entity: Optional[str] = None

    @classmethod
    def from_classification(
        cls,
        classification: EventClassification,
        event_date: str,
        source_url: str,
        published_date: Optional[str] = None,
    ) -> "EvidenceRecord":
        """
        Build an EvidenceRecord from an EventClassification.

        Parameters
        ----------
        published_date:
            When this information became publicly available (ISO date YYYY-MM-DD).
            Used for no-lookahead filtering in backtests. Defaults to event_date.
        """
        evt_hash = _compute_event_hash(
            classification.ticker,
            classification.raw_text,
            event_date,
            classification.event_type,
        )
        return cls(
            ticker=classification.ticker,
            event_date=event_date,
            event_type=classification.event_type,
            direction=classification.direction,
            phase_detected=classification.phase_detected,
            source_type=classification.source_type,
            source_url=source_url,
            raw_text=classification.raw_text,
            confidence=classification.confidence,
            match_reasons=classification.match_reasons,
            score_deltas=classification.score_deltas,
            published_date=published_date or event_date,
            event_hash=evt_hash,
        )

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_jsonl(cls, line: str) -> "EvidenceRecord":
        return cls(**json.loads(line))


# ---------------------------------------------------------------------------
# EvidenceLedger
# ---------------------------------------------------------------------------


class EvidenceLedger:
    """
    Append-only evidence ledger backed by a JSONL file.

    Thread-safety: append() uses line-at-a-time writes which are atomic on
    POSIX filesystems for lines shorter than PIPE_BUF (~4KB). Suitable for
    single-writer use. For concurrent writes, add an external file lock.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_LEDGER_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Write ──────────────────────────────────────────────────────────────

    def append(self, record: EvidenceRecord) -> None:
        """Append one evidence record to the ledger."""
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(record.to_jsonl() + "\n")

    # ── Read ───────────────────────────────────────────────────────────────

    def get_records(
        self,
        ticker: Optional[str] = None,
        since_date: Optional[date] = None,
        until_date: Optional[date] = None,
        event_types: Optional[list[str]] = None,
        use_published_date: bool = False,
    ) -> list[EvidenceRecord]:
        """
        Read records matching the given filters.

        Parameters
        ----------
        ticker:
            Only records for this ticker. None = all tickers.
        since_date:
            Only records on or after this date (inclusive).
        until_date:
            Only records on or before this date (inclusive).
        event_types:
            Only records with one of these event_type values.
        use_published_date:
            When True, apply date filters against published_date (if set) instead
            of event_date. Use this for no-lookahead backtesting — information
            is only available once published, not when the event occurred.
        """
        if not self._path.exists():
            return []

        since_str = str(since_date) if since_date else None
        until_str = str(until_date) if until_date else None

        results: list[EvidenceRecord] = []
        with self._path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if ticker and obj.get("ticker") != ticker:
                    continue

                # No-lookahead: prefer published_date for date gating
                if use_published_date:
                    filter_date = obj.get("published_date") or obj.get("event_date", "")
                else:
                    filter_date = obj.get("event_date", "")

                if since_str and filter_date and filter_date < since_str:
                    continue
                if until_str and filter_date and filter_date > until_str:
                    continue

                if event_types and obj.get("event_type") not in event_types:
                    continue

                # Forward-compat: ignore unknown keys
                known_fields = EvidenceRecord.__dataclass_fields__.keys()
                filtered = {k: v for k, v in obj.items() if k in known_fields}
                results.append(EvidenceRecord(**filtered))

        return results

    # ── Score replay ───────────────────────────────────────────────────────

    def compute_score_state(
        self,
        ticker: str,
        as_of_date: Optional[date] = None,
        seed_scores: Optional[dict[str, float]] = None,
        use_published_date: bool = False,
        apply_decay: bool = False,
    ) -> dict[str, float]:
        """
        Replay the ledger for a ticker up to as_of_date to compute current scores.

        Each event's score_deltas are applied in chronological order.
        Scores are clamped to [0.0, 1.0] after each delta.

        Parameters
        ----------
        ticker:
            Target or acquirer ticker.
        as_of_date:
            Replay up to and including this date. None = all history.
        seed_scores:
            Starting score values. None = DEFAULT_SEED_SCORES.
        use_published_date:
            When True, filter by published_date instead of event_date.
            Use for no-lookahead backtesting.
        apply_decay:
            When True, apply exponential half-life decay to stale events
            (only for event types listed in DECAY_HALF_LIFE_DAYS).

        Returns
        -------
        dict of feature → score (0.0–1.0)
        """
        import math

        scores = dict(seed_scores if seed_scores is not None else DEFAULT_SEED_SCORES)
        records = self.get_records(
            ticker=ticker,
            until_date=as_of_date,
            use_published_date=use_published_date,
        )
        records.sort(key=lambda r: r.event_date)

        reference_date = as_of_date or date.today()

        for record in records:
            decay_weight = 1.0
            if apply_decay:
                half_life = DECAY_HALF_LIFE_DAYS.get(record.event_type)
                if half_life is not None:
                    try:
                        age_days = (reference_date - date.fromisoformat(record.event_date)).days
                        if age_days > 0:
                            decay_weight = math.exp(-math.log(2) * age_days / half_life)
                    except (ValueError, OverflowError):
                        decay_weight = 1.0

            for feature, delta in record.score_deltas.items():
                if feature in scores:
                    scores[feature] = max(0.0, min(1.0, scores[feature] + delta * decay_weight))

        return scores

    def get_score_history(
        self,
        ticker: str,
        features: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Return a time series of score snapshots for a ticker, one entry per event.

        Each entry contains event_date, event_type, direction, confidence,
        plus the score for each requested feature after that event was applied.

        Returns
        -------
        list[dict] ordered by event_date ascending.
        """
        target_features = features or list(DEFAULT_SEED_SCORES.keys())
        records = self.get_records(ticker=ticker)
        records.sort(key=lambda r: r.event_date)

        scores = dict(DEFAULT_SEED_SCORES)
        history: list[dict] = []

        for record in records:
            for feature, delta in record.score_deltas.items():
                if feature in scores:
                    scores[feature] = max(0.0, min(1.0, scores[feature] + delta))

            entry: dict = {
                "event_date":  record.event_date,
                "event_type":  record.event_type,
                "direction":   record.direction,
                "confidence":  record.confidence,
                "source_type": record.source_type,
                "raw_text":    record.raw_text[:120],  # truncate for display
            }
            for f in target_features:
                entry[f] = round(scores.get(f, 0.0), 4)
            history.append(entry)

        return history

    # ── Summary helpers ────────────────────────────────────────────────────

    def ticker_summary(self, ticker: str) -> dict:
        """Return a brief summary dict for a ticker."""
        records = self.get_records(ticker=ticker)
        if not records:
            return {
                "ticker":    ticker,
                "n_events":  0,
                "scores":    {k: round(v, 4) for k, v in DEFAULT_SEED_SCORES.items()},
            }
        records_sorted = sorted(records, key=lambda r: r.event_date)
        scores = self.compute_score_state(ticker)
        return {
            "ticker":            ticker,
            "n_events":          len(records),
            "first_event_date":  records_sorted[0].event_date,
            "last_event_date":   records_sorted[-1].event_date,
            "scores":            {k: round(v, 4) for k, v in scores.items()},
        }

    # ── Deduplication ──────────────────────────────────────────────────────

    def is_duplicate(self, record: EvidenceRecord) -> bool:
        """
        Return True if a record with the same event_hash already exists in the ledger.

        Uses the 16-char SHA-256 hash computed from ticker + text + event_date + event_type.
        Empty event_hash (legacy records) are never treated as duplicates.
        """
        if not record.event_hash or not self._path.exists():
            return False
        with self._path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("event_hash") == record.event_hash:
                    return True
        return False

    def append_if_not_duplicate(self, record: EvidenceRecord) -> bool:
        """
        Append the record only if its event_hash is not already present.

        Returns True if appended, False if skipped as a duplicate.

        Source priority: if a higher-priority source already recorded this event,
        the new record is still skipped (same hash). To override with a higher-
        priority source, callers should delete and re-insert (not yet supported).
        """
        if self.is_duplicate(record):
            return False
        self.append(record)
        return True

    # ── Evidence coverage ──────────────────────────────────────────────────

    def compute_evidence_coverage(self, ticker: str) -> dict[str, float]:
        """
        Compute per-domain evidence coverage for a ticker (0.0 – 1.0).

        Scores indicate how well the model's features are backed by real evidence.
        Low-coverage names should have their raw M&A probability suppressed.

        Domains:
          clinical    — clinical events (any phase outcome, trial status)
          regulatory  — FDA/regulatory events
          financial   — financial / BD events (raises, cash, restructuring)
          acquirer    — acquirer-side signals
          overall     — composite (mean of domains)

        Returns
        -------
        dict with keys: clinical, regulatory, financial, acquirer, overall, n_events
        """
        _CLINICAL_TYPES = {
            "clinical_positive_ph3", "clinical_positive_ph2", "clinical_positive_ph1",
            "clinical_positive", "clinical_mixed",
            "clinical_negative_ph3", "clinical_negative_ph2", "clinical_negative_ph1",
            "clinical_negative", "trial_start", "trial_delay", "trial_discontinuation",
        }
        _REGULATORY_TYPES = {
            "fda_approval", "crl", "btd", "fast_track", "orphan",
            "adcom_positive", "adcom_negative", "pdufa", "nda_accepted",
        }
        _FINANCIAL_TYPES = {
            "equity_raise", "cash_low", "restructuring", "strategic_review",
            "licensing_deal", "partnership", "asset_sale",
        }
        _ACQUIRER_TYPES = {"acquirer_bd_appetite", "acquirer_large_deal", "patent_cliff"}

        records = self.get_records(ticker=ticker)
        n = len(records)
        if n == 0:
            return {
                "clinical": 0.0, "regulatory": 0.0,
                "financial": 0.0, "acquirer": 0.0,
                "overall": 0.0, "n_events": 0,
            }

        types = {r.event_type for r in records}

        def _domain_score(domain_types: set[str]) -> float:
            hits = len(types & domain_types)
            # Saturates at ~5 distinct event types per domain
            return min(1.0, hits / 5.0)

        clin = _domain_score(_CLINICAL_TYPES)
        reg = _domain_score(_REGULATORY_TYPES)
        fin = _domain_score(_FINANCIAL_TYPES)
        acq = _domain_score(_ACQUIRER_TYPES)
        overall = round((clin + reg + fin + acq) / 4, 4)

        return {
            "clinical": round(clin, 4),
            "regulatory": round(reg, 4),
            "financial": round(fin, 4),
            "acquirer": round(acq, 4),
            "overall": overall,
            "n_events": n,
        }

    def all_tickers(self) -> list[str]:
        """Return sorted list of all tickers that have at least one ledger entry."""
        if not self._path.exists():
            return []
        seen: set[str] = set()
        with self._path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    t = obj.get("ticker")
                    if t:
                        seen.add(t)
                except json.JSONDecodeError:
                    continue
        return sorted(seen)


# ---------------------------------------------------------------------------
# SeedRecordLoader — Phase 5D
# ---------------------------------------------------------------------------

_CONFIDENCE_TO_FLOAT: dict[str, float] = {
    "high":   0.90,
    "medium": 0.60,
    "low":    0.30,
}


class SeedRecordLoader:
    """
    Load source-backed evidence records from a YAML seed file.

    The seed file uses a compact schema optimised for human authoring:

        - entity        : ticker
        - entity_type   : "acquirer" | "target" | "pair"
        - signal_type   : one of VALID_SIGNAL_TYPES
        - direction     : positive | negative | mixed | neutral
        - strength      : 0.0–1.0
        - source_type   : earnings_release | press_release | sec_filing | manual
        - source_date   : YYYY-MM-DD  (becomes event_date + published_date)
        - source_url    : verifiable primary source
        - summary       : one-line explanation (becomes raw_text)
        - confidence    : "high" | "medium" | "low"  (converted to float)
        - pair_entity   : (pair records only) second ticker

    Seed records use ``event_type="manual"`` and an empty ``score_deltas``
    dict — they provide structural evidence context, not automated score bumps.

    Usage::

        from bve.ingestion.evidence_ledger import SeedRecordLoader
        records = SeedRecordLoader.load("research/evidence/seed_records.yaml")
        for rec in records:
            ledger.append_if_not_duplicate(rec)
    """

    @staticmethod
    def load(path: "str | Path") -> list[EvidenceRecord]:
        """
        Parse *path* and return a list of EvidenceRecord instances.

        Parameters
        ----------
        path:
            Path to a YAML file containing a list of seed record dicts.
        """
        try:
            import yaml  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "PyYAML is required by SeedRecordLoader. "
                "Install it with: pip install pyyaml"
            ) from exc

        path = Path(path)
        with path.open(encoding="utf-8") as fh:
            raw_entries = yaml.safe_load(fh)

        if not raw_entries:
            return []

        return [SeedRecordLoader._convert(entry) for entry in raw_entries]

    @staticmethod
    def _convert(entry: dict) -> EvidenceRecord:
        ticker = str(entry["entity"]).upper()
        signal_type = entry.get("signal_type") or ""
        summary = entry.get("summary") or ""
        source_date = str(entry["source_date"])

        confidence_raw = entry.get("confidence", "medium")
        if isinstance(confidence_raw, str):
            confidence = _CONFIDENCE_TO_FLOAT.get(confidence_raw.lower(), 0.60)
        else:
            confidence = float(confidence_raw)

        evt_hash = _compute_event_hash(ticker, summary, source_date, "manual")

        return EvidenceRecord(
            ticker=ticker,
            event_date=source_date,
            event_type="manual",
            direction=str(entry.get("direction", "neutral")),
            phase_detected=None,
            source_type=str(entry.get("source_type", "manual")),
            source_url=str(entry.get("source_url", "")),
            raw_text=summary,
            confidence=confidence,
            match_reasons=["seed_record", signal_type] if signal_type else ["seed_record"],
            score_deltas={},
            published_date=source_date,
            event_hash=evt_hash,
            entity_type=entry.get("entity_type"),
            signal_type=signal_type or None,
            strength=float(entry["strength"]) if "strength" in entry else None,
            summary=summary,
            pair_entity=entry.get("pair_entity"),
        )
