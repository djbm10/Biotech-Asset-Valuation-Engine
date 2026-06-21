"""Persist classified evidence-ledger records into the KnowledgeStore.

Completes the live scanner score-update contract's first stage: the live ingestion
pipeline classifies events and appends them to the JSONL evidence ledger (unchanged),
and this module mirrors those records into the SQLite ``KnowledgeStore`` as ``Event``
+ ``StructuredSignal`` rows — the form the weekly scanner's score-context builder
reads. Without this, the gate/contract is a no-op because no StructuredSignals exist.

Scope: persistence + a deterministic ledger→typed-signal translation only. No
scoring/gating logic, no rNPV path, no event_router/continuous_monitoring changes.
The evidence ledger remains the source of truth and is not modified here.

Idempotent: Event/StructuredSignal ids are derived from the ledger ``event_hash`` so
re-running upserts the same rows rather than duplicating.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from bve.entities.trial import TrialPhase
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace
from bve.intelligence.schemas.signals import Event, StructuredSignal
from bve.intelligence.taxonomy import EventType

# ── Ledger event_type (classifier vocab) → taxonomy EventType ─────────────────────
_EVENTTYPE_MAP: dict[str, EventType] = {
    "clinical_positive": EventType.TRIAL_READOUT,
    "clinical_positive_ph1": EventType.TRIAL_READOUT,
    "clinical_positive_ph2": EventType.TRIAL_READOUT,
    "clinical_positive_ph3": EventType.TRIAL_READOUT,
    "clinical_negative": EventType.TRIAL_READOUT,
    "clinical_negative_ph1": EventType.TRIAL_READOUT,
    "clinical_negative_ph2": EventType.TRIAL_READOUT,
    "clinical_negative_ph3": EventType.TRIAL_READOUT,
    "clinical_mixed": EventType.TRIAL_READOUT,
    "trial_start": EventType.ENROLLMENT_UPDATE,
    "trial_delay": EventType.ENROLLMENT_UPDATE,
    "trial_discontinuation": EventType.PROGRAM_DISCONTINUATION,
    "fda_approval": EventType.FDA_APPROVAL,
    "crl": EventType.FDA_REJECTION,
    "btd": EventType.FDA_DESIGNATION,
    "fast_track": EventType.FDA_DESIGNATION,
    "orphan": EventType.FDA_DESIGNATION,
    "pdufa": EventType.FDA_DESIGNATION,
    "nda_accepted": EventType.FDA_DESIGNATION,
    "adcom_positive": EventType.FDA_DESIGNATION,
    "adcom_negative": EventType.FDA_DESIGNATION,
    "equity_raise": EventType.FINANCING,
    "cash_low": EventType.FINANCING,
    "going_concern": EventType.FINANCING,
    "restructuring": EventType.SEC_FILING,
    "strategic_review": EventType.PARTNERSHIP,
    "licensing_deal": EventType.PARTNERSHIP,
    "partnership": EventType.PARTNERSHIP,
    "asset_sale": EventType.PARTNERSHIP,
    "deal_terminated": EventType.PARTNERSHIP,
    "pending_acquisition": EventType.PARTNERSHIP,
    "delisting_notice": EventType.SEC_FILING,
    "guidance_raised": EventType.SEC_FILING,
    "guidance_lowered": EventType.SEC_FILING,
    "patent_cliff": EventType.PATENT_EVENT,
}

# Phase string ("Phase 3") → TrialPhase.
_PHASE_MAP: dict[str, TrialPhase] = {
    "phase 1": TrialPhase.PHASE_1, "phase 2": TrialPhase.PHASE_2, "phase 3": TrialPhase.PHASE_3,
    "ph1": TrialPhase.PHASE_1, "ph2": TrialPhase.PHASE_2, "ph3": TrialPhase.PHASE_3,
}


def _map_event_type(ledger_type: str) -> EventType:
    return _EVENTTYPE_MAP.get((ledger_type or "").lower(), EventType.SEC_FILING)


def _map_phase(phase_detected: Optional[str]) -> Optional[TrialPhase]:
    if not phase_detected:
        return None
    return _PHASE_MAP.get(phase_detected.strip().lower())


def _signal_clinical_fields(ledger_type: str, direction: str) -> dict:
    """Deterministic ledger (type, direction) → the StructuredSignal typed fields the
    score-context builder reads (primary_endpoint_met / fda_action_type /
    enrollment_status). Types with no clear scoring cue contribute nothing.
    """
    t, d = (ledger_type or "").lower(), (direction or "").lower()
    if t.startswith("clinical_positive"):
        return {"primary_endpoint_met": True}
    if t.startswith("clinical_negative"):
        return {"primary_endpoint_met": False}
    if t == "fda_approval":
        return {"fda_action_type": "approval"}
    if t == "crl":
        return {"fda_action_type": "crl"}
    if t == "trial_discontinuation":
        return {"enrollment_status": "terminated"}
    if t == "clinical_mixed":
        return {}  # neutral — recorded but no scoring cue
    # Fall back to direction for any other clinically-shaped event.
    if d == "positive":
        return {"primary_endpoint_met": True}
    if d == "negative":
        return {"primary_endpoint_met": False}
    return {}


def _event_id(event_hash: str, ticker: str, event_date: str, event_type: str) -> str:
    if event_hash:
        return f"evt-{event_hash}"
    # Deterministic fallback when a legacy record lacks a hash.
    import hashlib
    raw = f"{ticker}|{event_date}|{event_type}"
    return "evt-" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def record_to_event(record, *, asset_id: str, company_id: str, indication_id: Optional[str]) -> Event:
    """Map one EvidenceRecord → an intelligence-layer ``Event`` (idempotent id)."""
    eid = _event_id(getattr(record, "event_hash", ""), record.ticker,
                    record.event_date, record.event_type)
    observed = datetime.fromisoformat(record.event_date) if len(record.event_date) > 7 \
        else datetime.fromisoformat(record.event_date + "-01")
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return Event(
        id=eid,
        event_type=_map_event_type(record.event_type),
        asset_id=asset_id,
        company_id=company_id,
        indication_id=indication_id,
        observed_at=observed,
        ingested_at=datetime.now(timezone.utc),
        source_url=getattr(record, "source_url", "") or "",
        source_type=getattr(record, "source_type", "manual") or "manual",
        headline=(getattr(record, "summary", None) or (record.raw_text or "")[:200] or record.event_type),
        raw_text=getattr(record, "raw_text", None),
        confidence=float(getattr(record, "confidence", 1.0) or 1.0),
    )


def record_to_signal(record, event: Event, *, asset_id: str, company_id: str) -> StructuredSignal:
    """Map one EvidenceRecord → a ``StructuredSignal`` carrying the typed cue fields."""
    from datetime import date as _date

    sig_date = (_date.fromisoformat(record.event_date) if len(record.event_date) > 7
                else _date.fromisoformat(record.event_date + "-01"))
    fields = _signal_clinical_fields(record.event_type, getattr(record, "direction", ""))
    return StructuredSignal(
        id=f"sig-{event.id}",
        event_id=event.id,
        asset_id=asset_id,
        company_id=company_id,
        event_type=event.event_type,
        signal_date=sig_date,
        trial_phase=_map_phase(getattr(record, "phase_detected", None)),
        extraction_model="ledger_sync",
        extraction_confidence=float(getattr(record, "confidence", 0.0) or 0.0),
        created_at=datetime.now(timezone.utc),
        **fields,
    )


def persist_records(
    records: Iterable,
    store: KnowledgeStore,
    ticker_map: dict[str, tuple[str, str, Optional[str]]],
    *,
    source_ref: str = "bve-ingest-live",
) -> tuple[int, int, int]:
    """Persist evidence records into the store as Event + StructuredSignal.

    ``ticker_map`` maps an upper-case ticker → (asset_id, company_id, indication_id).
    Records whose ticker is not in the map are skipped (only universe assets feed the
    scanner). Returns (n_events, n_signals, n_skipped). Idempotent via stable ids.
    """
    trace = SourceTrace(source_type="bve-ingest-live", source_ref=source_ref)
    n_events = n_signals = n_skipped = 0
    for rec in records:
        key = (getattr(rec, "ticker", "") or "").upper()
        mapping = ticker_map.get(key)
        if mapping is None:
            n_skipped += 1
            continue
        asset_id, company_id, indication_id = mapping
        event = record_to_event(rec, asset_id=asset_id, company_id=company_id,
                                indication_id=indication_id)
        signal = record_to_signal(rec, event, asset_id=asset_id, company_id=company_id)
        try:
            store.add_event(event, trace, signal_id=signal.id)
            store.add_structured_signal(signal, trace, extraction_result_id=f"xr-{event.id}")
            n_events += 1
            n_signals += 1
        except Exception:
            n_skipped += 1
    return n_events, n_signals, n_skipped


def universe_ticker_map() -> dict[str, tuple[str, str, Optional[str]]]:
    """Build ticker → (asset_id, company_id, indication) from the tracked universe."""
    from bve.ops.universe_data import UNIVERSE

    out: dict[str, tuple[str, str, Optional[str]]] = {}
    for u in UNIVERSE:
        ticker = (u.get("ticker") or "").upper()
        if ticker and ticker not in out:
            out[ticker] = (u["asset_id"], u.get("company_id") or f"co-{ticker.lower()}",
                           u.get("indication"))
    return out
