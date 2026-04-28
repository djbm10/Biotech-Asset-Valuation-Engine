"""Deterministic M&A probability scanner built on acquirer fit and vulnerability signals."""
from __future__ import annotations

import logging
import json
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from pydantic import BaseModel, Field

from bve.intelligence.acquirer_fit import (
    AcquirerFitEngine,
    AcquirerFitIntegrationConfig,
    AcquirerFitRow,
)
from bve.intelligence.acquirer_profiles import AcquirerProfile, AcquirerProfileLoader
from bve.intelligence.capital_structure import CapitalRiskLevel, compute_capital_risk_as_of
from bve.intelligence.comparable_deals import ComparableDealLoader
from bve.intelligence.knowledge_layer import OpportunityAlertRecord
from bve.intelligence.ma_scoring import (
    apply_saturation_penalty,
    compute_acquirer_fit_decomposed,
    compute_deal_likelihood,
    compute_target_attractiveness,
)
from bve.intelligence.vulnerability_signals import (
    ExternalDealActivitySignal,
    TargetVulnerabilitySignal,
    VulnerabilitySignalLoader,
)


import math as _math


_LOG = logging.getLogger("bve.intelligence.ma_probability")
_DEFAULT_TARGETABILITY_RULES_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "targetability_rules.yaml"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _extract_calibration_features(
    row: "MAProbabilityRow",
    feature_names: list[str],
) -> dict[str, float]:
    """Map a MAProbabilityRow to the feature dict expected by MALogisticFitResult.predict().

    Features not available at live scoring time (ta_heat_score, single_asset_flag,
    market_exceeds_model_flag) default to 0.0 — the model was trained with standardised
    inputs so a missing feature defaults to its training mean.
    """
    ev = row.enterprise_value_millions
    feature_map: dict[str, float] = {
        "stored_probability": float(row.p_acquisition),
        "strategic_fit_score": float(row.strategic_fit_score),
        "valuation_discount_score": float(row.valuation_discount_score),
        "capital_vulnerability_score": float(row.capital_vulnerability_score),
        "de_risking_stage_score": float(row.de_risking_stage_score),
        "log_enterprise_value": _math.log1p(max(float(ev) if ev is not None else 0.0, 0.0)),
        "ta_heat_score": 0.0,
        "single_asset_flag": 0.0,
        "market_exceeds_model_flag": 0.0,
    }
    return {name: feature_map.get(name, 0.0) for name in feature_names}


SCORE_VERSIONS: dict[str, dict[str, float]] = {
    "v1.0": {
        "acquisition_discount": 0.30,
        "strategic_fit": 0.30,
        "derisking_stage": 0.25,
        "capital_vulnerability": 0.15,
        "scarcity": 0.0,
    },
    "v1.1": {
        "acquisition_discount": 0.30,
        "strategic_fit": 0.30,
        "derisking_stage": 0.25,
        "capital_vulnerability": 0.15,
        "scarcity": 0.0,
    },
    "v1.2": {
        "acquisition_discount": 0.00,
        "strategic_fit": 1.00,
        "derisking_stage": 0.00,
        "capital_vulnerability": 0.00,
        "scarcity": 0.0,
    },
    "v1.3": {
        "acquisition_discount": 0.00,
        "strategic_fit": 0.85,
        "derisking_stage": 0.00,
        "capital_vulnerability": 0.00,
        "scarcity": 0.15,
    },
}

_VALUATION_COMPONENT_MODES: dict[str, str] = {
    "v1.0": "positive",
    "v1.1": "inverted",
    "v1.2": "inverted",
    "v1.3": "inverted",
}

VULNERABILITY_WEIGHTS: dict[str, float] = {
    "cash_runway_pressure": 0.50,
    "target_signals": 0.30,
    "external_deal_pressure": 0.20,
}

_SIGNAL_STRENGTH_SCORES = {
    "low": 0.25,
    "medium": 0.55,
    "high": 0.85,
}

_RUNWAY_RISK_SCORES = {
    CapitalRiskLevel.LOW: 0.10,
    CapitalRiskLevel.MEDIUM: 0.55,
    CapitalRiskLevel.HIGH: 0.85,
    CapitalRiskLevel.CRITICAL: 1.00,
}

_DERISKING_BUCKET_SCORES = {
    "phase_3_or_later": 1.00,
    "phase_2_poc": 0.75,
    "phase_2_pre_poc": 0.45,
    "pre_phase_2": 0.10,
    "unknown": 0.30,
}

_STAGE_FALLBACK_SCORES = {
    "preclinical": 0.00,
    "phase_1": 0.25,
    "phase_2": 0.50,
    "phase_3": 1.00,
    "nda_bla": 1.00,
    "approved": 1.00,
    "commercial": 1.00,
}

_DESIGN_TIER_ADJUSTMENTS = {
    "os_rct": 0.10,
    "pfs": 0.05,
    "standard": 0.00,
    "surrogate": -0.10,
    "single_arm": -0.20,
}

_SCARCITY_STAGE_ELIGIBLE = {"phase 2", "phase 3", "nda bla", "approved", "commercial"}


class MAProbabilityConfig(BaseModel):
    """Configuration for the M&A probability scanner."""

    score_version: str = "v1.2"
    top_n: int = Field(default=15, ge=1)
    alert_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    hard_fail_penalty_multiplier: float = Field(default=0.50, ge=0.0, le=1.0)
    missing_valuation_penalty_multiplier: float = Field(default=0.75, ge=0.0, le=1.0)
    vulnerability_signals_path: str = "research/mna/vulnerability_signals.yaml"
    persist_daily_snapshots: bool = True
    enable_monitor: bool = True
    use_stored_screen_context: bool = False
    enforce_company_recency_gate: bool = True
    targetability_rules_path: str = str(_DEFAULT_TARGETABILITY_RULES_PATH)
    mega_cap_exclusion_ev_millions: float = Field(default=15000.0, gt=0.0)
    multi_franchise_penalty_ev_millions: float = Field(default=5000.0, gt=0.0)
    multi_franchise_penalty_multiplier: float = Field(default=0.40, ge=0.0, le=1.0)
    monitor: "MAProbabilityMonitorConfig" = Field(default_factory=lambda: MAProbabilityMonitorConfig())
    fit_integration_config: AcquirerFitIntegrationConfig = Field(
        default_factory=AcquirerFitIntegrationConfig
    )
    # Optional path to a fitted MALogisticFitResult JSON written by the backfiller.
    # When set, the scanner loads the model and populates p_takeout_calibrated on every
    # row. calibration_policy controls whether that calibrated layer only displays,
    # filters, or tie-breaks the live ranked output.
    calibration_model_path: str | None = None
    calibration_policy: str = "display_only"
    calibration_threshold: float = Field(default=0.10, ge=0.0, le=1.0)

    def resolved_weights(self) -> dict[str, float]:
        try:
            return dict(SCORE_VERSIONS[self.score_version])
        except KeyError as exc:
            raise ValueError(
                f"Unknown score version {self.score_version!r}. Valid: {sorted(SCORE_VERSIONS)}"
            ) from exc

    def resolved_valuation_component_mode(self) -> str:
        try:
            return _VALUATION_COMPONENT_MODES[self.score_version]
        except KeyError as exc:
            raise ValueError(
                f"Unknown score version {self.score_version!r}. Valid: {sorted(SCORE_VERSIONS)}"
            ) from exc


class VulnerabilityAssessment(BaseModel):
    """Target-side vulnerability context used in acquisition probability scoring."""

    asset_id: str
    cash_runway_quarters: float | None = None
    cash_runway_pressure_score: float = 0.0
    cash_runway_risk_level: str | None = None
    runway_gap_months: float | None = None
    nearest_catalyst_date: date | None = None
    target_signal_score: float = 0.0
    external_deal_pressure_score: float = 0.0
    capital_vulnerability_score: float = 0.0
    vulnerability_score: float = 0.0
    target_signal_ids: list[str] = Field(default_factory=list)
    external_deal_signal_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TargetabilityAssessment(BaseModel):
    """Universe-level targetability gate applied before final M&A ranking."""

    asset_id: str
    passes_hard_filters: bool = True
    multiplier: float = 1.0
    single_asset: bool | None = None
    hard_fail_reasons: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ExplicitTargetabilityRule(BaseModel):
    """Ticker-level override for obvious buyers / non-targets."""

    ticker: str
    reason: str
    note: str | None = None


class TargetabilityHardFailRules(BaseModel):
    """Hard disqualifiers for obvious non-targets."""

    max_market_cap_billions: float = Field(default=100.0, gt=0.0)
    excluded_tickers: list[str] = Field(default_factory=list)
    max_approved_revenue_share: float = Field(default=0.50, ge=0.0, le=1.0)


class TargetabilitySoftPenaltyRules(BaseModel):
    """Soft penalties applied to still-eligible but less targetable names."""

    multi_product_commercial_penalty: float = Field(default=0.50, ge=0.0, le=1.0)
    market_cap_penalty_start_billions: float = Field(default=20.0, ge=0.0)
    market_cap_penalty_end_billions: float = Field(default=100.0, gt=0.0)


class TargetabilityRuleset(BaseModel):
    """Full targetability rules config with legacy override support."""

    hard_fails: TargetabilityHardFailRules = Field(default_factory=TargetabilityHardFailRules)
    soft_penalties: TargetabilitySoftPenaltyRules = Field(default_factory=TargetabilitySoftPenaltyRules)
    explicit_hard_fails: list[ExplicitTargetabilityRule] = Field(default_factory=list)


class TargetabilityExclusion(BaseModel):
    """One asset excluded from the M&A ranking before scoring."""

    asset_id: str
    ticker: str | None = None
    reasons: list[str] = Field(default_factory=list)


class TargetabilityFilter:
    """Apply explicit hard fails and soft penalties before ranking."""

    def __init__(self, rules_path: str | None = None) -> None:
        self.rules_path = rules_path or str(_DEFAULT_TARGETABILITY_RULES_PATH)
        self.rules = self._load_rules(self.rules_path)
        self._excluded_tickers = {
            ticker
            for ticker in (_upper(item) for item in self.rules.hard_fails.excluded_tickers)
            if ticker is not None
        }
        self._explicit_rules = {
            rule.ticker.upper(): rule for rule in self.rules.explicit_hard_fails
        }

    def assess(
        self,
        *,
        asset_id: str,
        ticker: str | None,
        market_cap_billions: float | None,
        approved_revenue_share: float | None,
        stage: str | None,
        single_asset: bool | None,
        is_known_acquirer: bool = False,
    ) -> TargetabilityAssessment:
        hard_fail_reasons: list[str] = []
        notes: list[str] = []
        multiplier = 1.0

        target_ticker = _upper(ticker)
        if target_ticker is not None and target_ticker in self._excluded_tickers:
            hard_fail_reasons.append(f"excluded_ticker:{target_ticker}")

        explicit_rule = (
            self._explicit_rules.get(target_ticker)
            if target_ticker is not None
            else None
        )
        if explicit_rule is not None:
            hard_fail_reasons.append(explicit_rule.reason)
            if explicit_rule.note:
                notes.append(explicit_rule.note)

        if is_known_acquirer and target_ticker is not None:
            hard_fail_reasons.append(f"self_acquirer:{target_ticker}")

        if (
            market_cap_billions is not None
            and market_cap_billions > self.rules.hard_fails.max_market_cap_billions
        ):
            hard_fail_reasons.append(f"mega_cap:{market_cap_billions:.1f}B")

        normalized_stage = _normalize(stage)
        if (
            approved_revenue_share is not None
            and approved_revenue_share > self.rules.hard_fails.max_approved_revenue_share
        ):
            hard_fail_reasons.append(f"commercial_franchise:{approved_revenue_share:.0%}")
        elif approved_revenue_share is None and normalized_stage in {"approved", "commercial"} and single_asset is False:
            hard_fail_reasons.append("commercial_franchise:unknown_share")

        if not hard_fail_reasons and single_asset is False:
            multiplier *= self.rules.soft_penalties.multi_product_commercial_penalty
            notes.append("multi_product_commercial_penalty")

        market_cap_penalty = self._market_cap_penalty(market_cap_billions)
        if not hard_fail_reasons and market_cap_penalty < 1.0:
            multiplier *= market_cap_penalty
            notes.append(f"market_cap_penalty:{market_cap_billions:.1f}B")

        return TargetabilityAssessment(
            asset_id=asset_id,
            passes_hard_filters=not hard_fail_reasons,
            multiplier=round(multiplier, 6),
            single_asset=single_asset,
            hard_fail_reasons=list(dict.fromkeys(hard_fail_reasons)),
            notes=list(dict.fromkeys(notes)),
        )

    def _market_cap_penalty(self, market_cap_billions: float | None) -> float:
        if market_cap_billions is None:
            return 1.0

        start = self.rules.soft_penalties.market_cap_penalty_start_billions
        end = self.rules.soft_penalties.market_cap_penalty_end_billions
        if end <= start or market_cap_billions <= start:
            return 1.0

        scale = (end - market_cap_billions) / (end - start)
        return min(max(max(0.3, scale), 0.0), 1.0)

    @staticmethod
    def _load_rules(path: str) -> TargetabilityRuleset:
        import yaml

        rules_path = Path(path).expanduser()
        if not rules_path.exists():
            return TargetabilityRuleset()

        raw = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            return TargetabilityRuleset()
        return TargetabilityRuleset.model_validate(raw)


class ScarcityAssessment(BaseModel):
    """Target scarcity based on same-indication late-stage competition."""

    asset_id: str
    score: float = 0.0
    peer_count: int = 0
    bucket: str = "unknown"
    match_basis: str = "unknown"


class MAAcquirerCandidate(BaseModel):
    """One acquirer-specific acquisition-probability candidate for a target."""

    acquirer_id: str
    acquirer_name: str
    mna_probability_score: float
    p_acquisition: float
    raw_probability: float
    strategic_fit_score: float
    valuation_discount_score: float
    de_risking_stage_score: float
    capital_vulnerability_score: float
    scarcity_score: float
    scarcity_peer_count: int
    scarcity_bucket: str
    fit_score: float
    passes_hard_filters: bool
    hard_fail_reasons: list[str] = Field(default_factory=list)
    matched_therapeutic_gap: str | None = None
    matched_modality: str | None = None
    matched_priorities: list[str] = Field(default_factory=list)
    estimated_deal_value_low_millions: float | None = None
    estimated_deal_value_high_millions: float | None = None
    estimated_deal_value_source: str | None = None
    explanation: str

    # Three-model decomposition (Sprint 17 — diagnostics only)
    target_attractiveness_score: float | None = None
    deal_likelihood_score: float | None = None
    acquirer_fit_score: float | None = None


class MAProbabilityRow(BaseModel):
    """Final ranked M&A probability row for one target."""

    rank: int = 0
    asset_id: str
    company_id: str | None = None
    ticker: str | None = None
    stage: str | None = None
    therapeutic_area: str | None = None
    acquisition_ready: bool | None = None
    enterprise_value_millions: float | None = None
    acquisition_discount: float | None = None
    days_to_catalyst: int | None = None

    mna_probability_score: float
    p_acquisition: float
    raw_probability: float
    above_alert_threshold: bool
    score_version: str

    best_acquirer_id: str
    best_acquirer_name: str
    best_acquirer_fit_score: float
    runner_up_acquirer_id: str | None = None

    valuation_discount_score: float
    strategic_fit_score: float
    de_risking_stage_score: float
    capital_vulnerability_score: float
    scarcity_score: float
    scarcity_peer_count: int
    scarcity_bucket: str
    vulnerability_score: float

    model_rnpv_millions: float | None = None
    peak_sales_millions: float | None = None
    estimated_deal_value_low_millions: float | None = None
    estimated_deal_value_high_millions: float | None = None
    estimated_deal_value_source: str | None = None

    cash_runway_quarters: float | None = None
    cash_runway_pressure_score: float = 0.0
    cash_runway_risk_level: str | None = None
    runway_gap_months: float | None = None
    nearest_catalyst_date: date | None = None
    target_signal_score: float = 0.0
    external_deal_pressure_score: float = 0.0
    target_signal_ids: list[str] = Field(default_factory=list)
    external_deal_signal_ids: list[str] = Field(default_factory=list)
    targetability_multiplier: float = 1.0
    targetability_reasons: list[str] = Field(default_factory=list)
    company_action_policy: str | None = None
    company_action_reason: str | None = None
    company_snapshot_date: date | None = None
    company_recency_gate_failed: bool = False

    hard_fail_reasons: list[str] = Field(default_factory=list)
    matched_therapeutic_gap: str | None = None
    matched_modality: str | None = None
    matched_priorities: list[str] = Field(default_factory=list)
    explanation: str

    acquirer_candidates: list[MAAcquirerCandidate] = Field(default_factory=list)

    # Calibration layer — logistic model output, does not affect ranking order
    p_takeout_calibrated: float | None = None

    # Three-model decomposition (Sprint 17 — diagnostics only, does not affect ranking)
    target_attractiveness_score: float | None = None
    deal_likelihood_score: float | None = None
    acquirer_fit_score: float | None = None


class MAProbabilityResult(BaseModel):
    """Watchlist-level M&A probability scan output."""

    scanned_at: datetime = Field(default_factory=_utcnow)
    as_of_date: date
    score_version: str
    alert_threshold: float
    calibration_policy: str = "display_only"
    calibration_threshold: float | None = None
    n_assets: int
    n_ranked: int
    n_excluded: int = 0
    n_above_alert_threshold: int
    alerts_emitted: list[OpportunityAlertRecord] = Field(default_factory=list)
    alerts_suppressed_as_duplicate: int = 0
    snapshots_written: int = 0
    reference_snapshot_date: str | None = None
    excluded_assets: list[TargetabilityExclusion] = Field(default_factory=list)
    rows: list[MAProbabilityRow] = Field(default_factory=list)


class MAProbabilitySnapshotRecord(BaseModel):
    """One persisted M&A probability snapshot row."""

    snapshot_date: date
    asset_id: str
    ticker: str | None = None
    stage: str | None = None
    therapeutic_area: str | None = None
    probability: float
    rank: int
    best_acquirer_id: str
    best_acquirer_name: str | None = None
    acquirer_candidates: list[MAAcquirerCandidate] = Field(default_factory=list)
    above_alert_threshold: bool
    strategic_fit_score: float | None = None
    valuation_discount_score: float | None = None
    de_risking_stage_score: float | None = None
    capital_vulnerability_score: float | None = None
    scarcity_score: float | None = None
    scarcity_peer_count: int | None = None
    scarcity_bucket: str | None = None
    enterprise_value_millions: float | None = None
    acquisition_discount: float | None = None
    days_to_catalyst: int | None = None
    estimated_deal_value_low_millions: float | None = None
    estimated_deal_value_high_millions: float | None = None
    run_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)

    # Calibration layer — logistic model output, does not affect ranking order
    p_takeout_calibrated: float | None = None


class MAProbabilitySnapshotStore:
    """SQLite-backed store for daily M&A probability snapshots."""

    def __init__(self, knowledge_store) -> None:
        self.knowledge = knowledge_store
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.knowledge._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ma_probability_snapshots (
                snapshot_date TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                ticker TEXT,
                stage TEXT,
                therapeutic_area TEXT,
                probability REAL NOT NULL,
                rank INTEGER NOT NULL,
                best_acquirer_id TEXT NOT NULL,
                best_acquirer_name TEXT,
                acquirer_candidates_json TEXT,
                above_alert_threshold INTEGER NOT NULL,
                strategic_fit_score REAL,
                valuation_discount_score REAL,
                de_risking_stage_score REAL,
                capital_vulnerability_score REAL,
                scarcity_score REAL,
                scarcity_peer_count INTEGER,
                scarcity_bucket TEXT,
                enterprise_value_millions REAL,
                acquisition_discount REAL,
                days_to_catalyst INTEGER,
                estimated_deal_value_low_millions REAL,
                estimated_deal_value_high_millions REAL,
                run_id TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY(snapshot_date, asset_id)
            )
            """
        )
        self.knowledge._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ma_probability_snapshots_rank
                ON ma_probability_snapshots(snapshot_date, rank)
            """
        )
        self.knowledge._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ma_probability_snapshots_asset
                ON ma_probability_snapshots(asset_id, snapshot_date)
            """
        )
        self.knowledge._ensure_column("ma_probability_snapshots", "ticker", "TEXT")
        self.knowledge._ensure_column("ma_probability_snapshots", "stage", "TEXT")
        self.knowledge._ensure_column("ma_probability_snapshots", "therapeutic_area", "TEXT")
        self.knowledge._ensure_column("ma_probability_snapshots", "best_acquirer_name", "TEXT")
        self.knowledge._ensure_column(
            "ma_probability_snapshots",
            "acquirer_candidates_json",
            "TEXT",
        )
        self.knowledge._ensure_column("ma_probability_snapshots", "strategic_fit_score", "REAL")
        self.knowledge._ensure_column("ma_probability_snapshots", "valuation_discount_score", "REAL")
        self.knowledge._ensure_column("ma_probability_snapshots", "de_risking_stage_score", "REAL")
        self.knowledge._ensure_column(
            "ma_probability_snapshots",
            "capital_vulnerability_score",
            "REAL",
        )
        self.knowledge._ensure_column("ma_probability_snapshots", "scarcity_score", "REAL")
        self.knowledge._ensure_column("ma_probability_snapshots", "scarcity_peer_count", "INTEGER")
        self.knowledge._ensure_column("ma_probability_snapshots", "scarcity_bucket", "TEXT")
        self.knowledge._ensure_column(
            "ma_probability_snapshots",
            "enterprise_value_millions",
            "REAL",
        )
        self.knowledge._ensure_column("ma_probability_snapshots", "acquisition_discount", "REAL")
        self.knowledge._ensure_column("ma_probability_snapshots", "days_to_catalyst", "INTEGER")
        self.knowledge._ensure_column(
            "ma_probability_snapshots",
            "estimated_deal_value_low_millions",
            "REAL",
        )
        self.knowledge._ensure_column(
            "ma_probability_snapshots",
            "estimated_deal_value_high_millions",
            "REAL",
        )
        self.knowledge._ensure_column(
            "ma_probability_snapshots",
            "p_takeout_calibrated",
            "REAL",
        )
        self.knowledge._ensure_column(
            "ma_probability_snapshots",
            "target_attractiveness_score",
            "REAL",
        )
        self.knowledge._ensure_column(
            "ma_probability_snapshots",
            "deal_likelihood_score",
            "REAL",
        )
        self.knowledge._ensure_column(
            "ma_probability_snapshots",
            "acquirer_fit_score",
            "REAL",
        )
        self.knowledge._conn.commit()

    @staticmethod
    def from_row(
        row: MAProbabilityRow,
        *,
        snapshot_date: date,
        run_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> MAProbabilitySnapshotRecord:
        return MAProbabilitySnapshotRecord(
            snapshot_date=snapshot_date,
            asset_id=row.asset_id,
            ticker=row.ticker,
            stage=row.stage,
            therapeutic_area=row.therapeutic_area,
            probability=float(row.p_acquisition),
            rank=int(row.rank),
            best_acquirer_id=row.best_acquirer_id,
            best_acquirer_name=row.best_acquirer_name,
            acquirer_candidates=list(row.acquirer_candidates),
            above_alert_threshold=bool(row.above_alert_threshold),
            strategic_fit_score=float(row.strategic_fit_score),
            valuation_discount_score=float(row.valuation_discount_score),
            de_risking_stage_score=float(row.de_risking_stage_score),
            capital_vulnerability_score=float(row.capital_vulnerability_score),
            scarcity_score=float(row.scarcity_score),
            scarcity_peer_count=int(row.scarcity_peer_count),
            scarcity_bucket=row.scarcity_bucket,
            enterprise_value_millions=(
                float(row.enterprise_value_millions)
                if row.enterprise_value_millions is not None
                else None
            ),
            acquisition_discount=(
                float(row.acquisition_discount)
                if row.acquisition_discount is not None
                else None
            ),
            days_to_catalyst=row.days_to_catalyst,
            estimated_deal_value_low_millions=(
                float(row.estimated_deal_value_low_millions)
                if row.estimated_deal_value_low_millions is not None
                else None
            ),
            estimated_deal_value_high_millions=(
                float(row.estimated_deal_value_high_millions)
                if row.estimated_deal_value_high_millions is not None
                else None
            ),
            run_id=run_id,
            created_at=created_at or _utcnow(),
            p_takeout_calibrated=(
                float(row.p_takeout_calibrated)
                if row.p_takeout_calibrated is not None
                else None
            ),
        )

    def write_snapshots(
        self,
        rows: list[MAProbabilityRow],
        *,
        snapshot_date: date,
        run_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> int:
        timestamp = created_at or _utcnow()
        snapshots = [
            self.from_row(
                row,
                snapshot_date=snapshot_date,
                run_id=run_id,
                created_at=timestamp,
            )
            for row in rows
        ]
        # Snapshot backfills rewrite the full cross-section for one date. Delete
        # the existing slice first so newly excluded assets do not linger as
        # stale rows from earlier score versions or filter regimes.
        self.knowledge._conn.execute(
            "DELETE FROM ma_probability_snapshots WHERE snapshot_date = ?",
            (snapshot_date.isoformat(),),
        )
        self.knowledge._conn.executemany(
            """
            INSERT OR REPLACE INTO ma_probability_snapshots(
                snapshot_date, asset_id, ticker, stage, therapeutic_area,
                probability, rank, best_acquirer_id, best_acquirer_name,
                acquirer_candidates_json,
                above_alert_threshold, strategic_fit_score, valuation_discount_score,
                de_risking_stage_score, capital_vulnerability_score,
                scarcity_score, scarcity_peer_count, scarcity_bucket,
                enterprise_value_millions, acquisition_discount, days_to_catalyst,
                estimated_deal_value_low_millions, estimated_deal_value_high_millions,
                run_id, created_at, p_takeout_calibrated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    snapshot.snapshot_date.isoformat(),
                    snapshot.asset_id,
                    snapshot.ticker,
                    snapshot.stage,
                    snapshot.therapeutic_area,
                    snapshot.probability,
                    snapshot.rank,
                    snapshot.best_acquirer_id,
                    snapshot.best_acquirer_name,
                    json.dumps(
                        [item.model_dump(mode="json") for item in snapshot.acquirer_candidates]
                    ),
                    int(snapshot.above_alert_threshold),
                    snapshot.strategic_fit_score,
                    snapshot.valuation_discount_score,
                    snapshot.de_risking_stage_score,
                    snapshot.capital_vulnerability_score,
                    snapshot.scarcity_score,
                    snapshot.scarcity_peer_count,
                    snapshot.scarcity_bucket,
                    snapshot.enterprise_value_millions,
                    snapshot.acquisition_discount,
                    snapshot.days_to_catalyst,
                    snapshot.estimated_deal_value_low_millions,
                    snapshot.estimated_deal_value_high_millions,
                    snapshot.run_id,
                    self.knowledge._coerce_datetime(snapshot.created_at).isoformat(),
                    snapshot.p_takeout_calibrated,
                )
                for snapshot in snapshots
            ],
        )
        self.knowledge._conn.commit()
        return len(snapshots)

    def get_snapshot_map(
        self,
        *,
        snapshot_date: date,
    ) -> dict[str, MAProbabilitySnapshotRecord]:
        rows = self.knowledge._conn.execute(
            """
            SELECT snapshot_date, asset_id, ticker, stage, therapeutic_area,
                   probability, rank, best_acquirer_id, best_acquirer_name,
                   acquirer_candidates_json,
                   above_alert_threshold, strategic_fit_score, valuation_discount_score,
                   de_risking_stage_score, capital_vulnerability_score,
                   scarcity_score, scarcity_peer_count, scarcity_bucket,
                   enterprise_value_millions, acquisition_discount, days_to_catalyst,
                   estimated_deal_value_low_millions, estimated_deal_value_high_millions,
                   run_id, created_at, p_takeout_calibrated
            FROM ma_probability_snapshots
            WHERE snapshot_date = ?
            ORDER BY rank ASC, asset_id ASC
            """,
            (snapshot_date.isoformat(),),
        ).fetchall()
        return {
            row["asset_id"]: MAProbabilitySnapshotRecord(
                snapshot_date=date.fromisoformat(row["snapshot_date"]),
                asset_id=row["asset_id"],
                ticker=row["ticker"],
                stage=row["stage"],
                therapeutic_area=row["therapeutic_area"],
                probability=float(row["probability"]),
                rank=int(row["rank"]),
                best_acquirer_id=row["best_acquirer_id"],
                best_acquirer_name=row["best_acquirer_name"],
                acquirer_candidates=[
                    MAAcquirerCandidate.model_validate(item)
                    for item in json.loads(row["acquirer_candidates_json"] or "[]")
                ],
                above_alert_threshold=bool(row["above_alert_threshold"]),
                strategic_fit_score=(
                    float(row["strategic_fit_score"])
                    if row["strategic_fit_score"] is not None
                    else None
                ),
                valuation_discount_score=(
                    float(row["valuation_discount_score"])
                    if row["valuation_discount_score"] is not None
                    else None
                ),
                de_risking_stage_score=(
                    float(row["de_risking_stage_score"])
                    if row["de_risking_stage_score"] is not None
                    else None
                ),
                capital_vulnerability_score=(
                    float(row["capital_vulnerability_score"])
                    if row["capital_vulnerability_score"] is not None
                    else None
                ),
                scarcity_score=(
                    float(row["scarcity_score"])
                    if row["scarcity_score"] is not None
                    else None
                ),
                scarcity_peer_count=(
                    int(row["scarcity_peer_count"])
                    if row["scarcity_peer_count"] is not None
                    else None
                ),
                scarcity_bucket=row["scarcity_bucket"],
                enterprise_value_millions=(
                    float(row["enterprise_value_millions"])
                    if row["enterprise_value_millions"] is not None
                    else None
                ),
                acquisition_discount=(
                    float(row["acquisition_discount"])
                    if row["acquisition_discount"] is not None
                    else None
                ),
                days_to_catalyst=(
                    int(row["days_to_catalyst"])
                    if row["days_to_catalyst"] is not None
                    else None
                ),
                estimated_deal_value_low_millions=(
                    float(row["estimated_deal_value_low_millions"])
                    if row["estimated_deal_value_low_millions"] is not None
                    else None
                ),
                estimated_deal_value_high_millions=(
                    float(row["estimated_deal_value_high_millions"])
                    if row["estimated_deal_value_high_millions"] is not None
                    else None
                ),
                run_id=row["run_id"],
                created_at=self.knowledge._coerce_datetime(row["created_at"]),
                p_takeout_calibrated=(
                    float(row["p_takeout_calibrated"])
                    if row["p_takeout_calibrated"] is not None
                    else None
                ),
            )
            for row in rows
        }

    def list_snapshots(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[MAProbabilitySnapshotRecord]:
        clauses: list[str] = []
        params: list[object] = []
        if start_date is not None:
            clauses.append("snapshot_date >= ?")
            params.append(start_date.isoformat())
        if end_date is not None:
            clauses.append("snapshot_date <= ?")
            params.append(end_date.isoformat())

        sql = (
            "SELECT snapshot_date, asset_id, ticker, stage, therapeutic_area, "
            "probability, rank, best_acquirer_id, best_acquirer_name, "
            "acquirer_candidates_json, "
            "above_alert_threshold, strategic_fit_score, valuation_discount_score, "
            "de_risking_stage_score, capital_vulnerability_score, "
            "scarcity_score, scarcity_peer_count, scarcity_bucket, "
            "enterprise_value_millions, acquisition_discount, days_to_catalyst, "
            "estimated_deal_value_low_millions, estimated_deal_value_high_millions, "
            "run_id, created_at, p_takeout_calibrated "
            "FROM ma_probability_snapshots"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY snapshot_date ASC, rank ASC, asset_id ASC"

        rows = self.knowledge._conn.execute(sql, params).fetchall()
        return [
            MAProbabilitySnapshotRecord(
                snapshot_date=date.fromisoformat(row["snapshot_date"]),
                asset_id=row["asset_id"],
                ticker=row["ticker"],
                stage=row["stage"],
                therapeutic_area=row["therapeutic_area"],
                probability=float(row["probability"]),
                rank=int(row["rank"]),
                best_acquirer_id=row["best_acquirer_id"],
                best_acquirer_name=row["best_acquirer_name"],
                acquirer_candidates=[
                    MAAcquirerCandidate.model_validate(item)
                    for item in json.loads(row["acquirer_candidates_json"] or "[]")
                ],
                above_alert_threshold=bool(row["above_alert_threshold"]),
                strategic_fit_score=(
                    float(row["strategic_fit_score"])
                    if row["strategic_fit_score"] is not None
                    else None
                ),
                valuation_discount_score=(
                    float(row["valuation_discount_score"])
                    if row["valuation_discount_score"] is not None
                    else None
                ),
                de_risking_stage_score=(
                    float(row["de_risking_stage_score"])
                    if row["de_risking_stage_score"] is not None
                    else None
                ),
                capital_vulnerability_score=(
                    float(row["capital_vulnerability_score"])
                    if row["capital_vulnerability_score"] is not None
                    else None
                ),
                scarcity_score=(
                    float(row["scarcity_score"])
                    if row["scarcity_score"] is not None
                    else None
                ),
                scarcity_peer_count=(
                    int(row["scarcity_peer_count"])
                    if row["scarcity_peer_count"] is not None
                    else None
                ),
                scarcity_bucket=row["scarcity_bucket"],
                enterprise_value_millions=(
                    float(row["enterprise_value_millions"])
                    if row["enterprise_value_millions"] is not None
                    else None
                ),
                acquisition_discount=(
                    float(row["acquisition_discount"])
                    if row["acquisition_discount"] is not None
                    else None
                ),
                days_to_catalyst=(
                    int(row["days_to_catalyst"])
                    if row["days_to_catalyst"] is not None
                    else None
                ),
                estimated_deal_value_low_millions=(
                    float(row["estimated_deal_value_low_millions"])
                    if row["estimated_deal_value_low_millions"] is not None
                    else None
                ),
                estimated_deal_value_high_millions=(
                    float(row["estimated_deal_value_high_millions"])
                    if row["estimated_deal_value_high_millions"] is not None
                    else None
                ),
                run_id=row["run_id"],
                created_at=self.knowledge._coerce_datetime(row["created_at"]),
                p_takeout_calibrated=(
                    float(row["p_takeout_calibrated"])
                    if row["p_takeout_calibrated"] is not None
                    else None
                ),
            )
            for row in rows
        ]

    def latest_snapshot_date_before(self, snapshot_date: date) -> Optional[date]:
        row = self.knowledge._conn.execute(
            """
            SELECT MAX(snapshot_date) AS snapshot_date
            FROM ma_probability_snapshots
            WHERE snapshot_date < ?
            """,
            (snapshot_date.isoformat(),),
        ).fetchone()
        if row is None or row["snapshot_date"] is None:
            return None
        return date.fromisoformat(row["snapshot_date"])


class MAProbabilityMonitorConfig(BaseModel):
    """Thresholds for change-based M&A probability alerts."""

    top_n: int = Field(default=10, ge=1)
    probability_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    alert_window_days: int = Field(default=1, ge=1)


class MAProbabilityMonitorResult(BaseModel):
    """Output from one M&A probability monitor pass."""

    monitored_at: datetime
    reference_snapshot_date: str | None = None
    alerts_emitted: list[OpportunityAlertRecord] = Field(default_factory=list)
    alerts_suppressed_as_duplicate: int = 0


class MAProbabilityMonitor:
    """Compares current M&A probabilities against the most recent prior snapshot."""

    def __init__(
        self,
        *,
        knowledge_store,
        config: Optional[MAProbabilityMonitorConfig] = None,
        snapshot_store: Optional[MAProbabilitySnapshotStore] = None,
    ) -> None:
        self.knowledge = knowledge_store
        self.config = config or MAProbabilityMonitorConfig()
        self.snapshot_store = snapshot_store or MAProbabilitySnapshotStore(knowledge_store)

    def evaluate(
        self,
        rows: list[MAProbabilityRow],
        *,
        monitored_at: Optional[datetime] = None,
        run_id: Optional[str] = None,
    ) -> MAProbabilityMonitorResult:
        monitored_at = monitored_at or _utcnow()
        snapshot_date = monitored_at.date()
        previous_date = self.snapshot_store.latest_snapshot_date_before(snapshot_date)
        if previous_date is None:
            return MAProbabilityMonitorResult(monitored_at=monitored_at)

        previous = self.snapshot_store.get_snapshot_map(snapshot_date=previous_date)
        alerts: list[OpportunityAlertRecord] = []
        suppressed = 0
        current_rows = sorted(rows, key=lambda row: row.rank)

        threshold = self.config.probability_threshold or 0.70
        for row in current_rows:
            prev = previous.get(row.asset_id)
            for record in self._alerts_for_row(
                row,
                previous_snapshot=prev,
                monitored_at=monitored_at,
                probability_threshold=threshold,
                run_id=run_id,
            ):
                if self.knowledge.add_opportunity_alert(record):
                    alerts.append(record)
                else:
                    suppressed += 1

        return MAProbabilityMonitorResult(
            monitored_at=monitored_at,
            reference_snapshot_date=previous_date.isoformat(),
            alerts_emitted=alerts,
            alerts_suppressed_as_duplicate=suppressed,
        )

    def _alerts_for_row(
        self,
        row: MAProbabilityRow,
        *,
        previous_snapshot: Optional[MAProbabilitySnapshotRecord],
        monitored_at: datetime,
        probability_threshold: float,
        run_id: Optional[str],
    ) -> list[OpportunityAlertRecord]:
        records: list[OpportunityAlertRecord] = []
        window = self._window_key(monitored_at, days=self.config.alert_window_days)

        if row.rank <= self.config.top_n and (
            previous_snapshot is None or previous_snapshot.rank > self.config.top_n
        ):
            records.append(
                self._record(
                    asset_id=row.asset_id,
                    event_type="ma_probability_top_n_entry",
                    window=window,
                    monitored_at=monitored_at,
                    run_id=run_id,
                    payload={
                        "asset_id": row.asset_id,
                        "current_rank": row.rank,
                        "previous_rank": (
                            previous_snapshot.rank if previous_snapshot is not None else None
                        ),
                        "p_acquisition": round(float(row.p_acquisition), 6),
                        "best_acquirer_id": row.best_acquirer_id,
                        "best_acquirer_name": row.best_acquirer_name,
                        "threshold": probability_threshold,
                    },
                )
            )

        if previous_snapshot is not None:
            crossing = self._threshold_crossing(
                previous_snapshot.probability,
                row.p_acquisition,
                threshold=probability_threshold,
            )
            if crossing is not None:
                records.append(
                    self._record(
                        asset_id=row.asset_id,
                        event_type="ma_probability_threshold_cross",
                        window=window,
                        monitored_at=monitored_at,
                        run_id=run_id,
                        payload={
                            "asset_id": row.asset_id,
                            "direction": crossing,
                            "threshold": probability_threshold,
                            "current_probability": round(float(row.p_acquisition), 6),
                            "previous_probability": round(
                                float(previous_snapshot.probability), 6
                            ),
                            "current_rank": row.rank,
                            "previous_rank": previous_snapshot.rank,
                            "best_acquirer_id": row.best_acquirer_id,
                        },
                    )
                )

        return records

    @staticmethod
    def _record(
        *,
        asset_id: str,
        event_type: str,
        window: str,
        monitored_at: datetime,
        run_id: Optional[str],
        payload: dict[str, object],
    ) -> OpportunityAlertRecord:
        return OpportunityAlertRecord(
            asset_id=asset_id,
            event_type=event_type,
            window=window,
            run_id=run_id,
            created_at=monitored_at,
            payload_json=payload,
        )

    @staticmethod
    def _threshold_crossing(
        previous_probability: float,
        current_probability: float,
        *,
        threshold: float,
    ) -> Optional[str]:
        prev_over = float(previous_probability) >= threshold
        curr_over = float(current_probability) >= threshold
        if prev_over == curr_over:
            return None
        return "entered" if curr_over else "exited"

    @staticmethod
    def _window_key(ts: datetime, *, days: int) -> str:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        start_dt = datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc)
        end_dt = start_dt + timedelta(days=days)
        return f"{start_dt.isoformat()}__{end_dt.isoformat()}"


class MAProbabilityScanner:
    """Rank watchlist assets by acquisition likelihood across all configured acquirers."""

    def __init__(
        self,
        *,
        knowledge_store=None,
        context_provider=None,
        config: Optional[MAProbabilityConfig] = None,
        fit_engine: Optional[AcquirerFitEngine] = None,
    ) -> None:
        self.config = config or MAProbabilityConfig()
        self._calibration_model = self._load_calibration_model(self.config.calibration_model_path)
        self.fit_engine = fit_engine or AcquirerFitEngine(
            knowledge_store=knowledge_store,
            context_provider=context_provider,
            integration_config=self.config.fit_integration_config,
        )
        self.knowledge = knowledge_store or getattr(self.fit_engine.acquisition_screener, "knowledge", None)
        self._targetability_metadata_cache: dict[str, dict[str, object]] = {}
        self.targetability_filter = TargetabilityFilter(self.config.targetability_rules_path)
        use_snapshot_store = self.knowledge is not None and (
            self.config.persist_daily_snapshots or self.config.enable_monitor
        )
        self.snapshot_store = (
            MAProbabilitySnapshotStore(self.knowledge) if use_snapshot_store else None
        )
        resolved_monitor_config = self.config.monitor.model_copy(
            update={
                "probability_threshold": (
                    self.config.alert_threshold
                    if self.config.monitor.probability_threshold is None
                    else self.config.monitor.probability_threshold
                )
            }
        )
        self.monitor = (
            MAProbabilityMonitor(
                knowledge_store=self.knowledge,
                config=resolved_monitor_config,
                snapshot_store=self.snapshot_store,
            )
            if self.knowledge is not None and self.config.enable_monitor and self.snapshot_store is not None
            else None
        )

    def scan_from_watchlist_config(
        self,
        watchlist_config,
        *,
        snapshot_date: Optional[date] = None,
        top_n: Optional[int] = None,
        run_id: Optional[str] = None,
        scanned_at: Optional[datetime] = None,
    ) -> MAProbabilityResult:
        return self.scan_watchlist(
            list(getattr(watchlist_config, "watchlist", [])),
            snapshot_date=snapshot_date,
            top_n=top_n,
            run_id=run_id,
            scanned_at=scanned_at,
        )

    def scan_watchlist(
        self,
        watchlist: list[object],
        *,
        snapshot_date: Optional[date] = None,
        top_n: Optional[int] = None,
        run_id: Optional[str] = None,
        scanned_at: Optional[datetime] = None,
    ) -> MAProbabilityResult:
        as_of = snapshot_date or (scanned_at.date() if scanned_at is not None else date.today())
        resolved_scanned_at = scanned_at or datetime.combine(as_of, dtime.min, tzinfo=timezone.utc)
        acquirer_dataset = AcquirerProfileLoader.load(
            self.config.fit_integration_config.acquirer_profiles_path
        )
        vulnerability_dataset = VulnerabilitySignalLoader.load(
            self.config.vulnerability_signals_path
        )
        comparable_deals = ComparableDealLoader.load(
            self.config.fit_integration_config.comparable_deals_path
        ).deals

        acquisition_result = self.fit_engine.acquisition_screener.screen_watchlist(
            watchlist,
            snapshot_date=as_of,
            persist=self.config.fit_integration_config.persist_acquisition_snapshots,
            comparable_deals=comparable_deals,
        )
        asset_by_id = {getattr(asset, "asset_id"): asset for asset in watchlist}

        prepared_targets: list[SimpleNamespace] = []
        excluded_assets: list[TargetabilityExclusion] = []
        for acquisition_row in acquisition_result.rows:
            asset = asset_by_id[acquisition_row.asset_id]
            context = self._safe_get_context(asset)
            screen_context = self._stored_screen_context(
                asset_id=acquisition_row.asset_id,
                ticker=acquisition_row.ticker,
                as_of=as_of,
            )
            company_sotp_context = self._stored_company_sotp_context(
                ticker=acquisition_row.ticker,
                as_of=as_of,
            )
            if (
                self.config.enforce_company_recency_gate
                and company_sotp_context is not None
                and not bool(company_sotp_context.get("balance_sheet_passes_recency_gate", False))
            ):
                snapshot_text = company_sotp_context.get("snapshot_date")
                exclusion_reason = "company_recency_gate_failed"
                if snapshot_text is not None:
                    exclusion_reason = f"{exclusion_reason}:{snapshot_text}"
                excluded_assets.append(
                    TargetabilityExclusion(
                        asset_id=acquisition_row.asset_id,
                        ticker=getattr(acquisition_row, "ticker", None),
                        reasons=[exclusion_reason],
                    )
                )
                continue
            prepared_row = self._apply_screen_context(
                acquisition_row=acquisition_row,
                screen_context=screen_context,
            )
            prepared_targets.append(
                SimpleNamespace(
                    asset=asset,
                    context=context,
                    acquisition_row=prepared_row,
                    screen_context=screen_context,
                    company_sotp_context=company_sotp_context,
                    targetability=self._assess_targetability(
                        asset=asset,
                        acquisition_row=prepared_row,
                        acquirer_dataset=acquirer_dataset.acquirers,
                        screen_context=screen_context,
                        context=context,
                    ),
                    vulnerability=self._assess_vulnerability(
                        asset=asset,
                        acquisition_row=prepared_row,
                        context=context,
                        vulnerability_dataset=vulnerability_dataset,
                        as_of=as_of,
                        screen_context=screen_context,
                    ),
                )
            )
        eligible_targets: list[SimpleNamespace] = []
        for prepared in prepared_targets:
            targetability = prepared.targetability
            if targetability.passes_hard_filters:
                eligible_targets.append(prepared)
                continue
            excluded_assets.append(
                TargetabilityExclusion(
                    asset_id=prepared.acquisition_row.asset_id,
                    ticker=getattr(prepared.acquisition_row, "ticker", None),
                    reasons=list(targetability.hard_fail_reasons) + list(targetability.notes),
                )
            )

        if excluded_assets:
            _LOG.info("Excluded %s assets from M&A scan:", len(excluded_assets))
            for exclusion in excluded_assets[:10]:
                _LOG.info(
                    "  %s: %s",
                    exclusion.ticker or exclusion.asset_id,
                    ", ".join(exclusion.reasons),
                )

        scarcity_by_asset = self._assess_scarcity(eligible_targets)

        rows: list[MAProbabilityRow] = []
        for prepared in eligible_targets:
            asset = prepared.asset
            context = prepared.context
            acquisition_row = prepared.acquisition_row
            targetability = prepared.targetability
            vulnerability = prepared.vulnerability
            scarcity = scarcity_by_asset.get(
                acquisition_row.asset_id,
                ScarcityAssessment(asset_id=acquisition_row.asset_id),
            )
            candidates = [
                self._score_acquirer_candidate(
                    acquirer=acquirer,
                    acquisition_row=acquisition_row,
                    fit_row=self.fit_engine._build_row(
                        acquirer=acquirer,
                        asset=asset,
                        acquisition_row=acquisition_row,
                        comparable_deals=comparable_deals,
                    ),
                    vulnerability=vulnerability,
                    targetability=targetability,
                    scarcity=scarcity,
                )
                for acquirer in acquirer_dataset.acquirers
            ]
            candidates.sort(
                key=lambda item: (
                    -item.mna_probability_score,
                    -item.strategic_fit_score,
                    item.acquirer_id,
                )
            )
            best = candidates[0]
            runner_up = candidates[1].acquirer_id if len(candidates) > 1 else None
            rows.append(
                MAProbabilityRow(
                    asset_id=acquisition_row.asset_id,
                    company_id=acquisition_row.company_id,
                    ticker=acquisition_row.ticker,
                    stage=acquisition_row.stage,
                    therapeutic_area=acquisition_row.therapeutic_area,
                    acquisition_ready=acquisition_row.acquisition_ready,
                    enterprise_value_millions=acquisition_row.enterprise_value_millions,
                    acquisition_discount=acquisition_row.acquisition_discount,
                    days_to_catalyst=(
                        getattr(acquisition_row, "days_to_catalyst", None)
                        if getattr(acquisition_row, "days_to_catalyst", None) is not None
                        else (
                            (vulnerability.nearest_catalyst_date - as_of).days
                            if vulnerability.nearest_catalyst_date is not None
                            else None
                        )
                    ),
                    model_rnpv_millions=acquisition_row.model_rnpv_millions,
                    peak_sales_millions=acquisition_row.peak_sales_millions,
                    mna_probability_score=best.mna_probability_score,
                    p_acquisition=best.p_acquisition,
                    raw_probability=best.raw_probability,
                    above_alert_threshold=best.mna_probability_score >= self.config.alert_threshold,
                    score_version=self.config.score_version,
                    best_acquirer_id=best.acquirer_id,
                    best_acquirer_name=best.acquirer_name,
                    best_acquirer_fit_score=best.fit_score,
                    runner_up_acquirer_id=runner_up,
                    valuation_discount_score=best.valuation_discount_score,
                    strategic_fit_score=best.strategic_fit_score,
                    de_risking_stage_score=best.de_risking_stage_score,
                    capital_vulnerability_score=vulnerability.capital_vulnerability_score,
                    scarcity_score=best.scarcity_score,
                    scarcity_peer_count=best.scarcity_peer_count,
                    scarcity_bucket=best.scarcity_bucket,
                    vulnerability_score=vulnerability.vulnerability_score,
                    estimated_deal_value_low_millions=best.estimated_deal_value_low_millions,
                    estimated_deal_value_high_millions=best.estimated_deal_value_high_millions,
                    estimated_deal_value_source=best.estimated_deal_value_source,
                    cash_runway_quarters=vulnerability.cash_runway_quarters,
                    cash_runway_pressure_score=vulnerability.cash_runway_pressure_score,
                    cash_runway_risk_level=vulnerability.cash_runway_risk_level,
                    runway_gap_months=vulnerability.runway_gap_months,
                    nearest_catalyst_date=vulnerability.nearest_catalyst_date,
                    target_signal_score=vulnerability.target_signal_score,
                    external_deal_pressure_score=vulnerability.external_deal_pressure_score,
                    target_signal_ids=vulnerability.target_signal_ids,
                    external_deal_signal_ids=vulnerability.external_deal_signal_ids,
                    targetability_multiplier=targetability.multiplier,
                    targetability_reasons=(
                        list(targetability.hard_fail_reasons) + list(targetability.notes)
                    ),
                    company_action_policy=(
                        str(prepared.company_sotp_context.get("action_policy"))
                        if prepared.company_sotp_context
                        and prepared.company_sotp_context.get("action_policy")
                        else None
                    ),
                    company_action_reason=(
                        str(prepared.company_sotp_context.get("action_reason"))
                        if prepared.company_sotp_context
                        and prepared.company_sotp_context.get("action_reason")
                        else None
                    ),
                    company_snapshot_date=(
                        prepared.company_sotp_context.get("snapshot_date")
                        if prepared.company_sotp_context is not None
                        else None
                    ),
                    company_recency_gate_failed=False,
                    hard_fail_reasons=list(best.hard_fail_reasons),
                    matched_therapeutic_gap=best.matched_therapeutic_gap,
                    matched_modality=best.matched_modality,
                    matched_priorities=list(best.matched_priorities),
                    explanation=_build_row_explanation(best=best, vulnerability=vulnerability),
                    acquirer_candidates=candidates,
                    target_attractiveness_score=best.target_attractiveness_score,
                    deal_likelihood_score=best.deal_likelihood_score,
                    acquirer_fit_score=best.acquirer_fit_score,
                )
            )

        rows.sort(
            key=lambda row: (
                -row.mna_probability_score,
                -row.strategic_fit_score,
                row.asset_id,
            )
        )
        all_ranked_rows = [
            row.model_copy(update={"rank": idx + 1})
            for idx, row in enumerate(rows)
        ]
        # Calibration layer: score every row with the logistic model if one is loaded.
        # This populates p_takeout_calibrated before any live ranking policy is applied.
        if self._calibration_model is not None:
            calibration_model = self._calibration_model
            all_ranked_rows = [
                row.model_copy(
                    update={
                        "p_takeout_calibrated": round(
                            calibration_model.predict(
                                _extract_calibration_features(row, calibration_model.feature_names)
                            ),
                            4,
                        )
                    }
                )
                for row in all_ranked_rows
            ]
        policy_rows = self._apply_calibration_policy(all_ranked_rows)
        limit = top_n or self.config.top_n
        ranked_rows = [
            row.model_copy(update={"rank": idx + 1})
            for idx, row in enumerate(policy_rows[:limit])
        ]
        snapshots_written = 0
        monitor_result = MAProbabilityMonitorResult(monitored_at=resolved_scanned_at)
        if self.snapshot_store is not None and self.config.persist_daily_snapshots:
            snapshots_written = self.snapshot_store.write_snapshots(
                all_ranked_rows,
                snapshot_date=as_of,
                run_id=run_id,
                created_at=resolved_scanned_at,
            )
        if self.monitor is not None:
            monitor_result = self.monitor.evaluate(
                ranked_rows,
                monitored_at=resolved_scanned_at,
                run_id=run_id,
            )
        return MAProbabilityResult(
            scanned_at=resolved_scanned_at,
            as_of_date=as_of,
            score_version=self.config.score_version,
            alert_threshold=self.config.alert_threshold,
            calibration_policy=self._effective_calibration_policy(),
            calibration_threshold=(
                self.config.calibration_threshold
                if self._calibration_model is not None
                else None
            ),
            n_assets=len(all_ranked_rows),
            n_ranked=len(ranked_rows),
            n_excluded=len(excluded_assets),
            n_above_alert_threshold=sum(
                1
                for row in all_ranked_rows
                if row.mna_probability_score >= self.config.alert_threshold
            ),
            alerts_emitted=monitor_result.alerts_emitted,
            alerts_suppressed_as_duplicate=monitor_result.alerts_suppressed_as_duplicate,
            snapshots_written=snapshots_written,
            reference_snapshot_date=monitor_result.reference_snapshot_date,
            excluded_assets=excluded_assets,
            rows=ranked_rows,
        )

    def _effective_calibration_policy(self) -> str:
        if self._calibration_model is None:
            return "display_only"
        return self.config.calibration_policy

    def _apply_calibration_policy(
        self,
        rows: list[MAProbabilityRow],
    ) -> list[MAProbabilityRow]:
        policy = self._effective_calibration_policy()
        if policy == "display_only":
            return list(rows)
        if policy == "threshold_filter":
            filtered = [
                row
                for row in rows
                if row.p_takeout_calibrated is not None
                and row.p_takeout_calibrated >= self.config.calibration_threshold
            ]
            return filtered
        if policy == "tie_breaker":
            return sorted(
                rows,
                key=lambda row: (
                    -row.mna_probability_score,
                    -(row.p_takeout_calibrated or 0.0),
                    -row.strategic_fit_score,
                    row.asset_id,
                ),
            )
        _LOG.warning("Unknown calibration policy %s; falling back to display_only", policy)
        return list(rows)

    def _score_acquirer_candidate(
        self,
        *,
        acquirer: AcquirerProfile,
        acquisition_row,
        fit_row: AcquirerFitRow,
        vulnerability: VulnerabilityAssessment,
        targetability: TargetabilityAssessment,
        scarcity: ScarcityAssessment,
    ) -> MAAcquirerCandidate:
        weights = self.config.resolved_weights()
        valuation_discount_score = _valuation_discount_score(fit_row.acquisition_discount)
        valuation_component_score = _valuation_component_score(
            valuation_discount_score,
            mode=self.config.resolved_valuation_component_mode(),
        )
        strategic_fit_score = self._strategic_fit_score(fit_row)
        de_risking_stage_score = _derisking_stage_score(acquisition_row)
        capital_vulnerability_score = vulnerability.capital_vulnerability_score
        estimated_low, estimated_high, estimated_source = _estimate_deal_value_range(
            acquisition_row=acquisition_row,
            fit_row=fit_row,
        )

        raw_mna_score = round(
            (valuation_component_score * weights["acquisition_discount"])
            + (strategic_fit_score * weights["strategic_fit"])
            + (de_risking_stage_score * weights["derisking_stage"])
            + (capital_vulnerability_score * weights["capital_vulnerability"])
            + (scarcity.score * weights["scarcity"]),
            6,
        )

        # Saturation penalty: when multiple sub-scores are simultaneously at cap,
        # reduce the composite to keep <10% of names at exact maximum.
        mna_probability_score = apply_saturation_penalty(
            raw_mna_score,
            sub_scores=[
                valuation_component_score,
                strategic_fit_score,
                de_risking_stage_score,
                capital_vulnerability_score,
                scarcity.score,
            ],
        )

        adjusted_probability = mna_probability_score * targetability.multiplier
        combined_hard_fails = list(fit_row.hard_fail_reasons)
        combined_hard_fails.extend(targetability.hard_fail_reasons)
        if targetability.notes:
            combined_hard_fails.extend(targetability.notes)
        if targetability.hard_fail_reasons:
            adjusted_probability = 0.0

        # Three-model decomposition (diagnostics only, not used in ranking)
        ta_score = compute_target_attractiveness(
            de_risking_stage_score=de_risking_stage_score,
            valuation_discount_score=valuation_discount_score,
            scarcity_score=scarcity.score,
            peak_sales_millions=getattr(acquisition_row, "peak_sales_millions", None),
        )
        dl_score = compute_deal_likelihood(
            cash_runway_pressure_score=vulnerability.cash_runway_pressure_score,
            external_deal_pressure_score=vulnerability.external_deal_pressure_score,
            target_signal_score=vulnerability.target_signal_score,
            days_to_catalyst=getattr(acquisition_row, "days_to_catalyst", None),
        )
        af_score = compute_acquirer_fit_decomposed(
            therapeutic_area_score=fit_row.therapeutic_area_score,
            modality_score=fit_row.modality_score,
            strategic_priority_score=fit_row.strategic_priority_score,
            budget_score=fit_row.budget_score,
            matched_partnership=fit_row.matched_partnership_target,
        )

        return MAAcquirerCandidate(
            acquirer_id=acquirer.acquirer_id,
            acquirer_name=acquirer.company_name,
            mna_probability_score=min(max(adjusted_probability, 0.0), 1.0),
            p_acquisition=min(max(adjusted_probability, 0.0), 1.0),
            raw_probability=min(max(mna_probability_score, 0.0), 1.0),
            strategic_fit_score=round(strategic_fit_score, 6),
            valuation_discount_score=round(valuation_discount_score, 6),
            de_risking_stage_score=round(de_risking_stage_score, 6),
            capital_vulnerability_score=round(capital_vulnerability_score, 6),
            scarcity_score=round(scarcity.score, 6),
            scarcity_peer_count=scarcity.peer_count,
            scarcity_bucket=scarcity.bucket,
            fit_score=fit_row.fit_score,
            passes_hard_filters=fit_row.passes_hard_filters and not targetability.hard_fail_reasons,
            hard_fail_reasons=list(dict.fromkeys(combined_hard_fails)),
            matched_therapeutic_gap=fit_row.matched_therapeutic_gap,
            matched_modality=fit_row.matched_modality,
            matched_priorities=list(fit_row.matched_priorities),
            estimated_deal_value_low_millions=estimated_low,
            estimated_deal_value_high_millions=estimated_high,
            estimated_deal_value_source=estimated_source,
            explanation=fit_row.explanation,
            target_attractiveness_score=ta_score.score,
            deal_likelihood_score=dl_score.score,
            acquirer_fit_score=af_score.score,
        )

    def _strategic_fit_score(self, fit_row: AcquirerFitRow) -> float:
        fit_weights = self.fit_engine.scorer.config.resolved_weights()
        strategic_weight = (
            fit_weights["therapeutic_area"]
            + fit_weights["modality"]
            + fit_weights["strategic_priority"]
            + fit_weights["budget"]
        )
        if strategic_weight <= 0:
            return 0.0
        strategic_component = (
            fit_row.therapeutic_area_component
            + fit_row.modality_component
            + fit_row.strategic_priority_component
            + fit_row.budget_component
        )
        return min(max(strategic_component / strategic_weight, 0.0), 1.0)

    def _assess_vulnerability(
        self,
        *,
        asset: object,
        acquisition_row,
        context,
        vulnerability_dataset,
        as_of: date,
        screen_context: Optional[dict[str, object]] = None,
    ) -> VulnerabilityAssessment:
        company = getattr(context, "company", None)
        cash_runway_quarters = getattr(company, "cash_runway_quarters", None)
        nearest_catalyst = self._nearest_catalyst(
            asset_id=acquisition_row.asset_id,
            ticker=acquisition_row.ticker,
            as_of=as_of,
            screen_context=screen_context,
        )

        cash_score, risk_level, gap_months, notes = self._cash_runway_pressure(
            company=company,
            cash_runway_quarters=cash_runway_quarters,
            nearest_catalyst=nearest_catalyst,
            as_of=as_of,
        )
        target_signals = VulnerabilitySignalLoader.get_target_signals(
            vulnerability_dataset,
            asset_id=acquisition_row.asset_id,
            company_id=acquisition_row.company_id,
            ticker=acquisition_row.ticker,
            as_of=as_of,
        )
        external_signals = self._matched_external_signals(
            vulnerability_dataset=vulnerability_dataset,
            acquisition_row=acquisition_row,
            context=context,
            as_of=as_of,
        )
        target_signal_score = _target_signal_score(target_signals)
        external_pressure_score = _external_deal_signal_score(external_signals)
        return VulnerabilityAssessment(
            asset_id=acquisition_row.asset_id,
            cash_runway_quarters=round(float(cash_runway_quarters), 6)
            if cash_runway_quarters is not None
            else None,
            cash_runway_pressure_score=round(cash_score, 6),
            cash_runway_risk_level=risk_level,
            runway_gap_months=round(gap_months, 6) if gap_months is not None else None,
            nearest_catalyst_date=getattr(nearest_catalyst, "expected_date", None),
            target_signal_score=round(target_signal_score, 6),
            external_deal_pressure_score=round(external_pressure_score, 6),
            capital_vulnerability_score=round(cash_score, 6),
            vulnerability_score=round(cash_score, 6),
            target_signal_ids=[signal.signal_id for signal in target_signals],
            external_deal_signal_ids=[signal.signal_id for signal in external_signals],
            notes=notes,
        )

    @staticmethod
    def _cash_runway_pressure(
        *,
        company,
        cash_runway_quarters: Optional[float],
        nearest_catalyst,
        as_of: date,
    ) -> tuple[float, Optional[str], Optional[float], list[str]]:
        notes: list[str] = []
        if cash_runway_quarters is None:
            return 0.0, None, None, ["missing_cash_runway"]

        burn_rate_quarterly = getattr(company, "burn_rate_millions_per_quarter", None)
        burn_rate_monthly = (
            float(burn_rate_quarterly) / 3.0
            if burn_rate_quarterly is not None and burn_rate_quarterly > 0
            else 0.0
        )
        if nearest_catalyst is not None:
            risk, gap_months = compute_capital_risk_as_of(
                nearest_catalyst.expected_date,
                float(cash_runway_quarters),
                burn_rate_monthly,
                as_of=as_of,
            )
            notes.append("runway_vs_nearest_catalyst")
            return (
                _RUNWAY_RISK_SCORES[risk],
                risk.value,
                round(gap_months, 6),
                notes,
            )

        runway_quarters = float(cash_runway_quarters)
        notes.append("runway_without_catalyst")
        if runway_quarters <= 2.0:
            return 1.0, "critical", None, notes
        if runway_quarters <= 4.0:
            return 0.85, "high", None, notes
        if runway_quarters <= 6.0:
            return 0.60, "medium", None, notes
        if runway_quarters <= 8.0:
            return 0.35, "medium", None, notes
        if runway_quarters <= 12.0:
            return 0.15, "low", None, notes
        return 0.0, "low", None, notes

    def _matched_external_signals(
        self,
        *,
        vulnerability_dataset,
        acquisition_row,
        context,
        as_of: date,
    ) -> list[ExternalDealActivitySignal]:
        target_ta = _normalize(acquisition_row.therapeutic_area)
        raw_modality = getattr(getattr(getattr(context, "asset", None), "modality", None), "value", None)
        target_modality = _normalize(raw_modality)

        matches: list[ExternalDealActivitySignal] = []
        for signal in vulnerability_dataset.external_deal_activity:
            if VulnerabilitySignalLoader.is_stale(
                event_date=signal.event_date,
                signal_type=signal.signal_type,
                dataset=vulnerability_dataset,
                as_of=as_of,
            ):
                continue
            signal_ta = _normalize(signal.therapeutic_area)
            signal_modality = _normalize(signal.modality)
            if (
                target_ta is not None
                and signal_ta is not None
                and target_ta == signal_ta
            ) or (
                target_modality is not None
                and signal_modality is not None
                and target_modality == signal_modality
            ):
                matches.append(signal)
        return matches

    def _safe_get_context(self, asset: object):
        try:
            return self.fit_engine.acquisition_screener._get_context(asset)
        except Exception:
            return None

    def _stored_screen_context(
        self,
        *,
        asset_id: str | None = None,
        ticker: str | None,
        as_of: date,
    ) -> Optional[dict[str, object]]:
        if not self.config.use_stored_screen_context or self.knowledge is None:
            return None
        try:
            if asset_id:
                asset_row = self.knowledge.get_screen_snapshot_for_asset_on_or_before(
                    asset_id=asset_id,
                    as_of=as_of,
                )
                if asset_row is not None:
                    return asset_row
            if not ticker:
                return None
            return self.knowledge.get_screen_snapshot_for_ticker_on_or_before(
                ticker=ticker,
                as_of=as_of,
            )
        except Exception:
            return None

    def _stored_company_sotp_context(
        self,
        *,
        ticker: str | None,
        as_of: date,
    ) -> Optional[dict[str, object]]:
        if self.knowledge is None or not ticker:
            return None
        try:
            return self.knowledge.get_company_sotp_snapshot_for_ticker_on_or_before(
                ticker=ticker,
                as_of=as_of,
            )
        except Exception:
            return None

    def _apply_screen_context(
        self,
        *,
        acquisition_row,
        screen_context: Optional[dict[str, object]],
    ):
        if not screen_context:
            return acquisition_row

        acquisition_discount_pct = screen_context.get("acquisition_discount_pct")
        acquisition_discount = None
        if acquisition_discount_pct is not None:
            acquisition_discount = round(1.0 + (float(acquisition_discount_pct) / 100.0), 6)

        update: dict[str, object] = {}
        if screen_context.get("stage") is not None:
            update["stage"] = str(screen_context["stage"])
        if screen_context.get("ta") is not None:
            update["therapeutic_area"] = str(screen_context["ta"])
        if screen_context.get("rnpv_millions") is not None:
            update["model_rnpv_millions"] = round(float(screen_context["rnpv_millions"]), 6)
        if screen_context.get("ev_millions") is not None:
            update["enterprise_value_millions"] = round(float(screen_context["ev_millions"]), 6)
        if acquisition_discount is not None:
            update["acquisition_discount"] = acquisition_discount
            update["passes_threshold"] = acquisition_discount >= self.config.fit_integration_config.acquisition_threshold
            if getattr(acquisition_row, "exclusion_reason", None) == "missing_market_cap":
                update["exclusion_reason"] = None
        if screen_context.get("days_to_catalyst") is not None:
            update["days_to_catalyst"] = int(screen_context["days_to_catalyst"])
        return acquisition_row.model_copy(update=update)

    def _assess_scarcity(
        self,
        prepared_targets: list[SimpleNamespace],
    ) -> dict[str, ScarcityAssessment]:
        key_members: dict[tuple[str, str, str], list[str]] = {}
        descriptors: dict[str, tuple[str, str, str] | None] = {}

        for prepared in prepared_targets:
            descriptor = self._scarcity_descriptor(
                acquisition_row=prepared.acquisition_row,
                context=prepared.context,
            )
            descriptors[prepared.acquisition_row.asset_id] = descriptor
            if descriptor is None:
                continue
            _, _, stage = descriptor
            if stage not in _SCARCITY_STAGE_ELIGIBLE:
                continue
            key = descriptor[:2]
            key_members.setdefault(key, []).append(prepared.acquisition_row.asset_id)

        assessments: dict[str, ScarcityAssessment] = {}
        for prepared in prepared_targets:
            asset_id = prepared.acquisition_row.asset_id
            descriptor = descriptors.get(asset_id)
            if descriptor is None:
                assessments[asset_id] = ScarcityAssessment(asset_id=asset_id)
                continue
            basis, match_key, stage = descriptor
            eligible_members = key_members.get((basis, match_key), []) if stage in _SCARCITY_STAGE_ELIGIBLE else []
            peer_count = max(len(eligible_members) - 1, 0)
            score, bucket = _scarcity_score_from_peer_count(peer_count)
            assessments[asset_id] = ScarcityAssessment(
                asset_id=asset_id,
                score=score,
                peer_count=peer_count,
                bucket=bucket,
                match_basis=basis,
            )
        return assessments

    def _scarcity_descriptor(
        self,
        *,
        acquisition_row,
        context,
    ) -> tuple[str, str, str] | None:
        stage = _normalize(getattr(acquisition_row, "stage", None)) or "unknown"
        indication_key = _normalize(getattr(acquisition_row, "indication", None))
        if indication_key is None:
            indication_key = _normalize(getattr(getattr(context, "asset", None), "indication", None))
        therapeutic_area_key = _normalize(getattr(acquisition_row, "therapeutic_area", None))
        mechanism_key = _scarcity_mechanism_key(context)
        if mechanism_key is None:
            return None
        if indication_key is not None:
            return "indication_mechanism", f"{indication_key}|{mechanism_key}", stage
        if therapeutic_area_key is not None:
            return "ta_mechanism", f"{therapeutic_area_key}|{mechanism_key}", stage
        return None

    def _assess_targetability(
        self,
        *,
        asset: object,
        acquisition_row,
        acquirer_dataset: list[AcquirerProfile],
        screen_context: Optional[dict[str, object]],
        context,
    ) -> TargetabilityAssessment:
        target_ticker = _upper(getattr(acquisition_row, "ticker", None))
        acquirer_tickers = {
            ticker
            for ticker in (_upper(getattr(acquirer, "ticker", None)) for acquirer in acquirer_dataset)
            if ticker is not None
        }
        single_asset = self._resolve_single_asset_flag(
            asset=asset,
            screen_context=screen_context,
        )
        market_cap_billions = self._resolve_market_cap_billions(
            asset=asset,
            acquisition_row=acquisition_row,
            context=context,
        )
        approved_revenue_share = self._resolve_approved_revenue_share(asset=asset)
        return self.targetability_filter.assess(
            asset_id=getattr(acquisition_row, "asset_id"),
            ticker=target_ticker,
            market_cap_billions=market_cap_billions,
            approved_revenue_share=approved_revenue_share,
            stage=getattr(acquisition_row, "stage", None),
            single_asset=single_asset,
            is_known_acquirer=target_ticker in acquirer_tickers if target_ticker is not None else False,
        )

    @staticmethod
    def _load_calibration_model(path: Optional[str]):
        """Load a MALogisticFitResult from JSON if path is provided and file exists."""
        if path is None:
            return None
        cal_path = Path(path)
        if not cal_path.exists():
            return None
        try:
            from bve.intelligence.ma_calibration import MALogisticFitResult
            return MALogisticFitResult.load_json(cal_path)
        except Exception:
            return None

    def _resolve_single_asset_flag(
        self,
        *,
        asset: object,
        screen_context: Optional[dict[str, object]],
    ) -> bool | None:
        if screen_context is not None and screen_context.get("single_asset") is not None:
            return bool(screen_context["single_asset"])
        metadata = self._load_targetability_metadata(asset)
        value = metadata.get("single_asset")
        return bool(value) if value is not None else None

    def _resolve_approved_revenue_share(
        self,
        *,
        asset: object,
    ) -> float | None:
        metadata = self._load_targetability_metadata(asset)
        value = metadata.get("approved_revenue_share")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _resolve_market_cap_billions(
        self,
        *,
        asset: object,
        acquisition_row,
        context,
    ) -> float | None:
        candidates = (
            getattr(acquisition_row, "market_cap_millions", None),
            getattr(asset, "market_cap_millions", None),
            getattr(getattr(context, "company", None), "market_cap_millions", None),
        )
        for value in candidates:
            if value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if numeric > 0:
                return round(numeric / 1000.0, 6)
        return None

    def _load_targetability_metadata(
        self,
        asset: object,
    ) -> dict[str, object]:
        raw_config_path = getattr(asset, "valuation_config", None)
        if not raw_config_path:
            return {}

        config_path = str(Path(raw_config_path).expanduser().resolve())
        if config_path in self._targetability_metadata_cache:
            return self._targetability_metadata_cache[config_path]

        metadata: dict[str, object] = {}
        try:
            import yaml

            payload = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
            if isinstance(payload, dict):
                meta = payload.get("_meta")
                company = payload.get("company")
                for container in (meta, company, payload):
                    if not isinstance(container, dict):
                        continue
                    for key in ("single_asset", "approved_revenue_share"):
                        if container.get(key) is not None and metadata.get(key) is None:
                            metadata[key] = container[key]
        except Exception:
            metadata = {}

        self._targetability_metadata_cache[config_path] = metadata
        return metadata

    def _nearest_catalyst(
        self,
        *,
        asset_id: str,
        ticker: str | None,
        as_of: date,
        screen_context: Optional[dict[str, object]] = None,
    ):
        if screen_context is not None and screen_context.get("catalyst_date") is not None:
            try:
                expected_date = date.fromisoformat(str(screen_context["catalyst_date"]))
                if expected_date >= as_of:
                    return SimpleNamespace(expected_date=expected_date, id=f"screen:{ticker or asset_id}")
            except ValueError:
                pass
        if self.knowledge is None:
            return None
        try:
            events = self.knowledge.get_catalyst_events(asset_id=asset_id, active_only=True)
        except Exception:
            return None
        active_upcoming = [event for event in events if event.expected_date >= as_of]
        if not active_upcoming:
            return None
        return min(active_upcoming, key=lambda event: (event.expected_date, event.id))


def _valuation_discount_score(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    ratio = float(value)
    if ratio >= 3.0:
        return 1.0
    if ratio >= 2.5:
        return 0.9
    if ratio >= 2.0:
        return 0.8
    if ratio >= 1.5:
        return 0.7
    if ratio >= 1.2:
        return 0.55
    if ratio >= 1.0:
        return 0.4
    if ratio >= 0.75:
        return 0.25
    return 0.1


def _valuation_component_score(score: float, *, mode: str) -> float:
    bounded = min(max(float(score), 0.0), 1.0)
    if mode == "positive":
        return bounded
    if mode == "inverted":
        return 1.0 - bounded
    raise ValueError(f"Unknown valuation component mode: {mode}")


def _derisking_stage_score(acquisition_row) -> float:
    readiness_bucket = getattr(acquisition_row, "acquisition_readiness_bucket", None)
    stage = _normalize(getattr(acquisition_row, "stage", None))
    design_tier = _normalize(getattr(acquisition_row, "acquisition_readiness_design_tier", None))
    prior_pos = getattr(acquisition_row, "acquisition_readiness_prior_pos", None)
    posterior_pos = getattr(acquisition_row, "acquisition_readiness_posterior_pos", None)
    low_power = bool(getattr(acquisition_row, "acquisition_readiness_low_power", False))

    base = _DERISKING_BUCKET_SCORES.get(readiness_bucket or "", None)
    if base is None:
        base = _STAGE_FALLBACK_SCORES.get(stage or "", 0.30)

    score = float(base)
    score += _DESIGN_TIER_ADJUSTMENTS.get(design_tier or "", 0.0)
    if (
        prior_pos is not None
        and posterior_pos is not None
        and float(posterior_pos) > float(prior_pos)
    ):
        score += min(0.10, (float(posterior_pos) - float(prior_pos)) * 0.5)
    if low_power:
        score -= 0.15
    return min(max(round(score, 6), 0.0), 1.0)


def _estimate_deal_value_range(
    *,
    acquisition_row,
    fit_row: AcquirerFitRow,
) -> tuple[Optional[float], Optional[float], Optional[str]]:
    band_low = getattr(fit_row, "valuation_reference_band_low_millions", None)
    band_high = getattr(fit_row, "valuation_reference_band_high_millions", None)
    if band_low is not None and band_high is not None:
        return round(float(band_low), 6), round(float(band_high), 6), fit_row.valuation_source

    peak_sales = getattr(acquisition_row, "peak_sales_millions", None)
    comps_min = getattr(acquisition_row, "comps_peer_min_ev_to_peak_sales", None)
    comps_max = getattr(acquisition_row, "comps_peer_max_ev_to_peak_sales", None)
    if (
        peak_sales is not None
        and peak_sales > 0
        and comps_min is not None
        and comps_max is not None
    ):
        low = float(peak_sales) * float(comps_min)
        high = float(peak_sales) * float(comps_max)
        return round(low, 6), round(high, 6), "comparable_deals"

    enterprise_value = getattr(acquisition_row, "enterprise_value_millions", None)
    model_rnpv = getattr(acquisition_row, "model_rnpv_millions", None)
    if enterprise_value is not None and model_rnpv is not None:
        low = min(float(enterprise_value), float(model_rnpv))
        high = max(float(enterprise_value), float(model_rnpv))
        return round(low, 6), round(high, 6), "ev_to_model_rnpv"

    return None, None, None


def _target_signal_score(signals: list[TargetVulnerabilitySignal]) -> float:
    total = 0.0
    for signal in signals:
        base = _SIGNAL_STRENGTH_SCORES.get(signal.signal_strength, 0.25)
        if signal.signal_effect == "increase":
            total += base
        else:
            total -= base * 0.5
    return min(max(total, 0.0), 1.0)


def _external_deal_signal_score(signals: list[ExternalDealActivitySignal]) -> float:
    if not signals:
        return 0.0
    return min(
        1.0,
        max(_SIGNAL_STRENGTH_SCORES.get(signal.signal_strength, 0.25) for signal in signals),
    )


def _scarcity_mechanism_key(context) -> str | None:
    asset = getattr(context, "asset", None)
    if asset is None:
        return None
    moa = _normalize(getattr(asset, "mechanism_of_action", None))
    if moa is not None:
        return moa
    modality = _normalize(getattr(getattr(asset, "modality", None), "value", None))
    return modality


def _scarcity_score_from_peer_count(peer_count: int) -> tuple[float, str]:
    if peer_count <= 1:
        return 1.0, "very_high"
    if peer_count <= 3:
        return 0.8, "high"
    if peer_count <= 6:
        return 0.55, "medium"
    if peer_count <= 9:
        return 0.3, "low"
    return 0.1, "very_low"


def _normalize(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().lower().replace("_", " ").split())
    return normalized or None


def _upper(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def _build_row_explanation(
    *,
    best: MAAcquirerCandidate,
    vulnerability: VulnerabilityAssessment,
) -> str:
    parts = [
        f"best acquirer {best.acquirer_id} at {best.mna_probability_score:.3f}",
        f"strategic fit {best.strategic_fit_score:.3f}",
        f"acquisition discount {best.valuation_discount_score:.3f}",
        f"derisking {best.de_risking_stage_score:.3f}",
        f"capital vulnerability {vulnerability.capital_vulnerability_score:.3f}",
        f"scarcity {best.scarcity_score:.3f} ({best.scarcity_peer_count} peers)",
    ]
    if (
        best.estimated_deal_value_low_millions is not None
        and best.estimated_deal_value_high_millions is not None
    ):
        parts.append(
            "deal range "
            f"${best.estimated_deal_value_low_millions:,.0f}M-"
            f"${best.estimated_deal_value_high_millions:,.0f}M"
        )
    if vulnerability.cash_runway_risk_level:
        parts.append(f"runway risk {vulnerability.cash_runway_risk_level}")
    if vulnerability.target_signal_ids:
        parts.append(f"target signals {', '.join(vulnerability.target_signal_ids)}")
    if vulnerability.external_deal_signal_ids:
        parts.append(f"same-space deals {', '.join(vulnerability.external_deal_signal_ids)}")
    if best.hard_fail_reasons:
        parts.append("hard fails " + ", ".join(best.hard_fail_reasons))
    return "; ".join(parts)
