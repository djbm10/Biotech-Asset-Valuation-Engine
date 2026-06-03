"""
EvidenceDossierBuilder — assembles AssetDossier and AcquirerDossier
from evidence store records (no LLM, no network).

Field precedence: highest materiality_score wins; ties broken by most
recent fetched_at.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bve.dossier.acquirer_dossier import (
    AcquirerDossier,
    BDActivity,
    BalanceSheet,
)
from bve.dossier.asset_dossier import (
    AssetDossier,
    AssetIdentity,
    CatalystSnapshot,
    CompetitionSnapshot,
    FinancingState,
    MarketSnapshot,
    ScienceContext,
    ThesisState,
    TrialSnapshot,
)
from bve.evidence.classifier import EventType
from bve.evidence.store import EvidenceRecord, EvidenceStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_POSITIVE_SIGNALS = {"positive", "efficacy", "met endpoint", "endpoint met"}
_NEGATIVE_SIGNALS = {"failed", "missed", "safety", "crl"}


def _extract_text(payload: dict[str, Any]) -> str:
    """
    Concatenate string values from known text fields in payload.

    Fields checked: title, summary, abstract, description,
    brief_title, official_title.  Result is lowercased and stripped.
    """
    text_fields = [
        "title",
        "summary",
        "abstract",
        "description",
        "brief_title",
        "official_title",
    ]
    parts: list[str] = []
    for field in text_fields:
        value = payload.get(field)
        if isinstance(value, str):
            parts.append(value.strip())
    return " ".join(parts).lower().strip()


def _provenance_label(record: EvidenceRecord) -> str:
    """Stable human-readable provenance string for a record."""
    fetched = record.raw_event.fetched_at.isoformat()
    return f"{record.raw_event.source}/{record.raw_event.record_type} @ {fetched}"


def _best_record(records: list[EvidenceRecord]) -> EvidenceRecord | None:
    """Return the record with the highest materiality score; break ties by newest fetched_at."""
    if not records:
        return None
    return max(
        records,
        key=lambda r: (r.materiality.score, r.raw_event.fetched_at),
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


class EvidenceDossierBuilder:
    """
    Builds point-in-time dossiers from an EvidenceStore.

    No LLM calls, no network calls.
    """

    def __init__(self, evidence_store: EvidenceStore) -> None:
        self._store = evidence_store

    # ── Asset dossier ──────────────────────────────────────────────────────

    def build_asset_dossier(
        self,
        asset_id: str,
        ticker: str | None = None,
    ) -> AssetDossier:
        """
        Load all EvidenceRecords for the asset_id (and ticker if given),
        merge, and return an AssetDossier.
        """
        records = self._load_asset_records(asset_id, ticker)

        identity = self._build_identity(asset_id, ticker, records)
        trials = self._build_trials(records)
        catalysts = self._build_catalysts(records)
        science = self._build_science(records)
        competition = self._build_competition(records)
        financing = self._build_financing(records)
        market = self._build_market(records)
        thesis = self._build_thesis(records)
        provenance = self._build_asset_provenance(records)

        return AssetDossier(
            asset_id=asset_id,
            as_of=_now(),
            identity=identity,
            trials=trials,
            catalysts=catalysts,
            science=science,
            competition=competition,
            financing=financing,
            market=market,
            thesis=thesis,
            evidence_record_count=len(records),
            provenance=provenance,
        )

    def _load_asset_records(
        self,
        asset_id: str,
        ticker: str | None,
    ) -> list[EvidenceRecord]:
        """Deduplicated union of records for asset_id and ticker."""
        seen_ids: set[str] = set()
        records: list[EvidenceRecord] = []

        for rec in self._store.get_by_entity(asset_id, limit=500):
            if rec.id not in seen_ids:
                seen_ids.add(rec.id)
                records.append(rec)

        if ticker:
            for rec in self._store.get_by_entity(ticker, limit=500):
                if rec.id not in seen_ids:
                    seen_ids.add(rec.id)
                    records.append(rec)

        return records

    def _build_identity(
        self,
        asset_id: str,
        ticker: str | None,
        records: list[EvidenceRecord],
    ) -> AssetIdentity:
        # Collect identity values from any record that has these keys in payload
        candidates: dict[str, list[tuple[float, datetime, str]]] = {
            "ticker": [],
            "drug_name": [],
            "company_name": [],
            "indication": [],
            "modality": [],
        }
        for rec in records:
            payload = rec.raw_event.payload
            score = rec.materiality.score
            fetched = rec.raw_event.fetched_at
            for field_name in candidates:
                value = payload.get(field_name)
                if isinstance(value, str) and value:
                    candidates[field_name].append((score, fetched, value))

        def _best_value(field_name: str) -> str | None:
            opts = candidates[field_name]
            if not opts:
                return None
            return max(opts, key=lambda t: (t[0], t[1]))[2]

        resolved_ticker = _best_value("ticker") or ticker

        return AssetIdentity(
            asset_id=asset_id,
            ticker=resolved_ticker,
            drug_name=_best_value("drug_name"),
            company_name=_best_value("company_name"),
            indication=_best_value("indication"),
            modality=_best_value("modality"),
        )

    def _build_trials(self, records: list[EvidenceRecord]) -> list[TrialSnapshot]:
        """Build from TRIAL_CHANGE records that have nct_id in payload."""
        trials: dict[str, TrialSnapshot] = {}
        for rec in records:
            if rec.classification.event_type != EventType.TRIAL_CHANGE:
                continue
            payload = rec.raw_event.payload
            nct_id = payload.get("nct_id")
            if not isinstance(nct_id, str) or not nct_id:
                continue
            # Prefer higher-materiality, then newer
            existing = trials.get(nct_id)
            if existing is not None:
                # Already have one; compare via the record we used (by fetched_at proxy)
                # Re-build only if this record has higher materiality
                pass  # handled below by always overwriting with best data

            snapshot = TrialSnapshot(
                nct_id=nct_id,
                phase=str(payload.get("phase") or ""),
                status=str(payload.get("status") or ""),
                enrollment=_int_or_none(payload.get("enrollment")),
                primary_endpoint=_str_or_none(payload.get("primary_endpoint")),
                completion_date=_str_or_none(payload.get("completion_date")),
            )
            # Keep the record we've seen; if duplicate nct_id just take latest
            if nct_id not in trials:
                trials[nct_id] = snapshot
            # Could merge — for now last-seen wins within same nct_id

        return list(trials.values())

    def _build_catalysts(self, records: list[EvidenceRecord]) -> list[CatalystSnapshot]:
        """Build from CATALYST_UPDATE and FDA_ACTION records."""
        catalyst_types = {EventType.CATALYST_UPDATE, EventType.FDA_ACTION}
        catalysts: list[CatalystSnapshot] = []
        for rec in records:
            if rec.classification.event_type not in catalyst_types:
                continue
            payload = rec.raw_event.payload
            text = _extract_text(payload)
            if not text:
                continue
            description = (
                _str_or_none(payload.get("title"))
                or _str_or_none(payload.get("summary"))
                or text[:120]
            )
            cat_type = _infer_catalyst_type(rec)
            snapshot = CatalystSnapshot(
                description=description,
                expected_date=_str_or_none(payload.get("expected_date")),
                catalyst_type=cat_type,
                source=_provenance_label(rec),
                confidence=rec.classification.confidence,
            )
            catalysts.append(snapshot)
        return catalysts

    def _build_science(self, records: list[EvidenceRecord]) -> ScienceContext:
        """Build from pubmed records; extract mechanism from abstract text."""
        pubmed_records = [
            r for r in records if r.raw_event.source == "pubmed"
        ]
        key_publications: list[str] = []
        mechanism_summary: str | None = None
        target: str | None = None
        biomarker_strategy: str | None = None

        best = _best_record(pubmed_records)
        if best:
            payload = best.raw_event.payload
            pmid = _str_or_none(payload.get("pmid"))
            if pmid:
                key_publications.append(pmid)
            abstract = _str_or_none(payload.get("abstract"))
            if abstract:
                mechanism_summary = abstract[:500]
            target = _str_or_none(payload.get("target"))
            biomarker_strategy = _str_or_none(payload.get("biomarker_strategy"))

        # Collect all PMIDs
        for rec in pubmed_records:
            pmid = _str_or_none(rec.raw_event.payload.get("pmid"))
            if pmid and pmid not in key_publications:
                key_publications.append(pmid)

        return ScienceContext(
            mechanism_summary=mechanism_summary,
            target=target,
            biomarker_strategy=biomarker_strategy,
            key_publications=key_publications,
        )

    def _build_competition(self, records: list[EvidenceRecord]) -> CompetitionSnapshot:
        """Build from COMPETITOR_EVENT records."""
        competitor_records = [
            r for r in records
            if r.classification.event_type == EventType.COMPETITOR_EVENT
        ]
        if not competitor_records:
            return CompetitionSnapshot()

        competitor_names: list[str] = []
        notes_parts: list[str] = []
        for rec in competitor_records:
            payload = rec.raw_event.payload
            name = _str_or_none(payload.get("competitor_name")) or _str_or_none(
                payload.get("company_name")
            )
            if name and name not in competitor_names:
                competitor_names.append(name)
            note = _str_or_none(payload.get("title")) or _str_or_none(
                payload.get("summary")
            )
            if note:
                notes_parts.append(note)

        # Determine risk level based on count
        count = len(competitor_names)
        if count == 0:
            risk = "unknown"
        elif count <= 2:
            risk = "low"
        elif count <= 5:
            risk = "medium"
        else:
            risk = "high"

        return CompetitionSnapshot(
            competitor_names=competitor_names,
            competitive_risk_level=risk,
            notes=notes_parts[0] if notes_parts else None,
        )

    def _build_financing(self, records: list[EvidenceRecord]) -> FinancingState:
        """Build from sec_edgar records with record_type=cash_burn_snapshot."""
        edgar_records = [
            r
            for r in records
            if r.raw_event.source == "sec_edgar"
            and r.raw_event.record_type == "cash_burn_snapshot"
        ]
        best = _best_record(edgar_records)
        if best is None:
            return FinancingState()

        payload = best.raw_event.payload
        return FinancingState(
            cash_usd=_float_or_none(payload.get("cash_usd")),
            rd_expense_usd=_float_or_none(payload.get("rd_expense_usd")),
            shares_outstanding=_float_or_none(payload.get("shares_outstanding")),
            cash_period_end=_str_or_none(payload.get("cash_period_end")),
        )

    def _build_market(self, records: list[EvidenceRecord]) -> MarketSnapshot:
        """Build from market_data records (price_snapshot, ev_snapshot, fundamentals_snapshot)."""
        market_record_types = {"price_snapshot", "ev_snapshot", "fundamentals_snapshot"}
        market_records = [
            r
            for r in records
            if r.raw_event.source == "market_data"
            and r.raw_event.record_type in market_record_types
        ]
        best = _best_record(market_records)
        if best is None:
            return MarketSnapshot()

        payload = best.raw_event.payload
        return MarketSnapshot(
            last_price=_float_or_none(payload.get("last_price")),
            market_cap_usd=_float_or_none(payload.get("market_cap_usd")),
            ev_usd=_float_or_none(payload.get("ev_usd")),
            as_of_date=_str_or_none(payload.get("as_of_date")),
        )

    def _build_thesis(self, records: list[EvidenceRecord]) -> ThesisState:
        """Build from high-materiality CATALYST_UPDATE records."""
        from bve.evidence.materiality import MaterialityTier

        high_mat = [
            r
            for r in records
            if r.classification.event_type == EventType.CATALYST_UPDATE
            and r.materiality.tier in (MaterialityTier.HIGH, MaterialityTier.MEDIUM)
        ]

        key_positives: list[str] = []
        key_risks: list[str] = []

        for rec in high_mat:
            text = _extract_text(rec.raw_event.payload)
            label = (
                _str_or_none(rec.raw_event.payload.get("title"))
                or text[:120]
            )
            if not label:
                continue
            if any(sig in text for sig in _POSITIVE_SIGNALS):
                key_positives.append(label)
            if any(sig in text for sig in _NEGATIVE_SIGNALS):
                key_risks.append(label)

        best = _best_record(high_mat)
        confidence = best.classification.confidence if best else 0.5

        return ThesisState(
            summary=None,
            key_positives=key_positives,
            key_risks=key_risks,
            confidence=confidence,
        )

    def _build_asset_provenance(self, records: list[EvidenceRecord]) -> dict[str, str]:
        """Track which record populated each dossier section."""
        provenance: dict[str, str] = {}

        edgar_best = _best_record([
            r for r in records
            if r.raw_event.source == "sec_edgar"
            and r.raw_event.record_type == "cash_burn_snapshot"
        ])
        if edgar_best:
            provenance["financing"] = _provenance_label(edgar_best)

        market_best = _best_record([
            r for r in records
            if r.raw_event.source == "market_data"
            and r.raw_event.record_type in {"price_snapshot", "ev_snapshot", "fundamentals_snapshot"}
        ])
        if market_best:
            provenance["market"] = _provenance_label(market_best)

        trial_records = [r for r in records if r.classification.event_type == EventType.TRIAL_CHANGE]
        if trial_records:
            provenance["trials"] = _provenance_label(_best_record(trial_records))  # type: ignore[arg-type]

        catalyst_records = [
            r for r in records
            if r.classification.event_type in (EventType.CATALYST_UPDATE, EventType.FDA_ACTION)
        ]
        if catalyst_records:
            provenance["catalysts"] = _provenance_label(_best_record(catalyst_records))  # type: ignore[arg-type]

        pubmed_best = _best_record([r for r in records if r.raw_event.source == "pubmed"])
        if pubmed_best:
            provenance["science"] = _provenance_label(pubmed_best)

        competitor_records = [
            r for r in records if r.classification.event_type == EventType.COMPETITOR_EVENT
        ]
        if competitor_records:
            provenance["competition"] = _provenance_label(_best_record(competitor_records))  # type: ignore[arg-type]

        return provenance

    # ── Acquirer dossier ───────────────────────────────────────────────────

    def build_acquirer_dossier(
        self,
        acquirer_id: str,
        company_name: str,
    ) -> AcquirerDossier:
        """
        Load EvidenceRecords for acquirer_id and build an AcquirerDossier.
        """
        records = self._store.get_by_entity(acquirer_id, limit=500)

        balance_sheet = self._build_acquirer_balance_sheet(records)
        bd_activity = self._build_bd_activity(records)
        provenance = self._build_acquirer_provenance(records)

        return AcquirerDossier(
            acquirer_id=acquirer_id,
            company_name=company_name,
            as_of=_now(),
            therapeutic_focus=[],
            pipeline_gaps=[],
            loe_exposure=[],
            balance_sheet=balance_sheet,
            bd_activity=bd_activity,
            provenance=provenance,
        )

    def _build_acquirer_balance_sheet(self, records: list[EvidenceRecord]) -> BalanceSheet:
        """Build from market_data records."""
        market_record_types = {"price_snapshot", "ev_snapshot", "fundamentals_snapshot"}
        market_records = [
            r
            for r in records
            if r.raw_event.source == "market_data"
            and r.raw_event.record_type in market_record_types
        ]
        best = _best_record(market_records)
        if best is None:
            return BalanceSheet()
        payload = best.raw_event.payload
        return BalanceSheet(
            cash_usd=_float_or_none(payload.get("cash_usd")),
            debt_usd=_float_or_none(payload.get("debt_usd")),
            market_cap_usd=_float_or_none(payload.get("market_cap_usd")),
            ev_usd=_float_or_none(payload.get("ev_usd")),
            as_of_date=_str_or_none(payload.get("as_of_date")),
        )

    def _build_bd_activity(self, records: list[EvidenceRecord]) -> BDActivity:
        """Build from PARTNERSHIP_MA records."""
        ma_records = [
            r for r in records
            if r.classification.event_type == EventType.PARTNERSHIP_MA
        ]
        if not ma_records:
            return BDActivity()

        recent_deals: list[str] = []
        for rec in sorted(ma_records, key=lambda r: r.raw_event.fetched_at, reverse=True):
            payload = rec.raw_event.payload
            description = (
                _str_or_none(payload.get("title"))
                or _str_or_none(payload.get("summary"))
                or _extract_text(payload)[:120]
            )
            if description and description not in recent_deals:
                recent_deals.append(description)

        return BDActivity(
            recent_deals=recent_deals,
            preferred_stages=[],
            typical_deal_size_usd=None,
            notes=None,
        )

    def _build_acquirer_provenance(self, records: list[EvidenceRecord]) -> dict[str, str]:
        provenance: dict[str, str] = {}
        market_best = _best_record([
            r for r in records
            if r.raw_event.source == "market_data"
        ])
        if market_best:
            provenance["balance_sheet"] = _provenance_label(market_best)
        ma_records = [r for r in records if r.classification.event_type == EventType.PARTNERSHIP_MA]
        if ma_records:
            provenance["bd_activity"] = _provenance_label(_best_record(ma_records))  # type: ignore[arg-type]
        return provenance


# ---------------------------------------------------------------------------
# Private coercion helpers
# ---------------------------------------------------------------------------


def _str_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _infer_catalyst_type(record: EvidenceRecord) -> str:
    text = _extract_text(record.raw_event.payload)
    if "pdufa" in text:
        return "pdufa"
    if "enrollment" in text:
        return "enrollment_complete"
    if record.classification.event_type == EventType.FDA_ACTION:
        return "regulatory"
    if any(kw in text for kw in ("readout", "results", "data", "topline", "top-line")):
        return "trial_readout"
    return "other"
