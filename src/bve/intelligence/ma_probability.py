"""Deterministic M&A probability scanner built on acquirer fit and vulnerability signals."""
from __future__ import annotations

import logging
import json
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from pydantic import BaseModel, Field, model_validator

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
    classify_watchlist_type,
    compute_acquirer_fit_decomposed,
    compute_deal_likelihood,
    compute_target_attractiveness,
)
from bve.intelligence.vulnerability_signals import (
    ExternalDealActivitySignal,
    TargetVulnerabilitySignal,
    VulnerabilitySignalLoader,
)
from bve.intelligence.ma_eligibility import TargetEligibilityInput, evaluate_layer0
from bve.intelligence.ma_pair_asset_control import (
    PairAssetControlInput,
    PairAssetControlResult,
    PairAdjustedModifiers,
    combine_layer0_and_3b,
    compute_pair_asset_control,
)
from bve.intelligence.ma_pair_affordability import (
    AcquirerCapacityInput,
    compute_pair_affordability,
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
    # Sprint 20: first version where de-risking stage AND scarcity both have
    # non-zero weight so the Sprint 20 component improvements are visible in
    # the composite probability score.
    "v1.4": {
        "acquisition_discount": 0.00,
        "strategic_fit": 0.65,
        "derisking_stage": 0.20,
        "capital_vulnerability": 0.05,
        "scarcity": 0.10,
    },
}

_VALUATION_COMPONENT_MODES: dict[str, str] = {
    "v1.0": "positive",
    "v1.1": "inverted",
    "v1.2": "inverted",
    "v1.3": "inverted",
    "v1.4": "inverted",
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
    "phase_3_or_later": 0.62,   # was 0.82; Phase 3 alone does not auto-max
    "phase_2_poc": 0.50,        # was 0.70
    "phase_2_pre_poc": 0.30,    # was 0.45
    "pre_phase_2": 0.08,        # was 0.10
    "unknown": 0.20,            # was 0.30
}

_STAGE_FALLBACK_SCORES = {
    # Keys use _normalize() output format (underscores converted to spaces).
    # _derisking_stage_score calls _normalize(stage) before this lookup.
    "preclinical": 0.00,
    "phase 1": 0.18,    # was 0.25
    "phase 2": 0.42,    # was 0.50
    "phase 3": 0.62,    # was 0.80
    "nda bla": 0.65,    # was 0.82
    "approved": 0.58,   # was 0.75
    "commercial": 0.50, # was 0.70
    # Aliases to tolerate underscored values from non-normalised callers
    "phase_1": 0.18,
    "phase_2": 0.42,
    "phase_3": 0.62,
    "nda_bla": 0.65,
}

# Quality-penalty modifiers applied in _derisking_stage_score.
# These require optional attributes on acquisition_row set by the screener.
_DERISKING_QUALITY_PENALTIES = {
    "safety_overhang": -0.12,         # was -0.10; serious safety event
    "prior_phase3_failure": -0.18,    # was -0.15; prior Phase 3 for same indication failed
    "label_uncertainty": -0.08,       # was -0.05; regulatory label scope contested
    "prior_phase2_failure": -0.10,    # NEW: prior Phase 2 failure in same indication
    "regulatory_risk": -0.08,         # NEW: heightened FDA review complexity flagged
    "endpoint_in_dispute": -0.07,     # NEW: primary endpoint contested by regulators/KOLs
}

# Quality bonuses applied in _derisking_stage_score.
_DERISKING_QUALITY_BONUSES = {
    "breakthrough_designation": 0.06,  # FDA BTD validates regulatory pathway
}

# Hard cap on _derisking_stage_score — lowered to prevent auto-saturation.
# Phase 3 OS RCT + BTD + strong POS uplift peaks at ~0.86, clamped to this cap.
_DERISKING_STAGE_SCORE_CAP = 0.80  # was 0.90

# ---------------------------------------------------------------------------
# Strategic-fit score — quality penalties, hard cap, and urgency weighting
# (Sprint 21: penalties + cap; Sprint 22: acquirer-specific urgency multiplier)
# ---------------------------------------------------------------------------
# A perfect TA+modality+strategic+budget match scores _STRATEGIC_FIT_HARD_CAP,
# never 1.0.  Each penalty reflects a concrete quality deficit that reduces the
# intrinsic strategic value of the acquirer-target pairing.
_STRATEGIC_FIT_HARD_CAP = 0.70          # lowered Sprint 22: high urgency still caps here
_STRATEGIC_FIT_PENALTY_WEAK_TA = 0.10   # TA score < 0.50 → weak commercial overlap
_STRATEGIC_FIT_PENALTY_POOR_MODALITY = 0.10   # modality score < 0.50 → platform mismatch
_STRATEGIC_FIT_PENALTY_NO_PIPELINE_GAP = 0.15  # strategic priority < 0.50 → no urgency
_STRATEGIC_FIT_PENALTY_POOR_DEAL_SIZE = 0.10   # budget score < 0.40 → deal too big/small
_STRATEGIC_FIT_WEAK_TA_THRESHOLD = 0.50
_STRATEGIC_FIT_POOR_MODALITY_THRESHOLD = 0.50
_STRATEGIC_FIT_NO_GAP_THRESHOLD = 0.50
_STRATEGIC_FIT_POOR_DEAL_SIZE_THRESHOLD = 0.40
STRATEGIC_FIT_REASON_WEAK_TA = "weak_commercial_overlap"
STRATEGIC_FIT_REASON_POOR_MODALITY = "poor_modality_fit"
STRATEGIC_FIT_REASON_NO_GAP = "no_pipeline_gap"
STRATEGIC_FIT_REASON_POOR_DEAL_SIZE = "poor_deal_size_fit"

# Gap urgency multipliers (Sprint 22) — scale the TA component by how urgently
# the acquirer needs this area.  "medium" (most common) gives base ≈ 0.68 for
# all-good sub-scores, below the 0.70 cap.  "high" allows ≈ 0.80 → still capped.
# "none" (no matched gap) uses a very low multiplier — TA overlap is incidental.
_GAP_URGENCY_MULTIPLIERS: dict[str, float] = {
    "high": 1.00,    # active pipeline gap, management commentary confirms urgency
    "medium": 0.55,  # TA overlap present but no explicit pipeline gap stated
    "low": 0.28,     # tangential exposure; acquirer has internal assets already
}
_GAP_URGENCY_NONE_MULTIPLIER = 0.15  # no matched gap → TA relevance is incidental

# BD pattern recency adjustment (Sprint 22) — acquirers with 3+ recent deals
# show confirmed BD activity; zero deals suggests internal-build preference.
_BD_PATTERN_BONUS_3_PLUS = 0.03   # ≥3 recent deals: confirmed BD activity
_BD_PATTERN_PENALTY_ZERO = -0.12  # 0 recent deals: no BD precedent

# ---------------------------------------------------------------------------
# Transaction-likelihood gate on mna_probability_score (Sprint 21)
# ---------------------------------------------------------------------------
# When both financing_not_pressured AND no_buyer_urgency fire on the vulnerability
# assessment, the final mna_probability_score is capped.  This gate mirrors the
# compute_mna_composite_score dual-gate but applies to the main scoring path.
_MNA_PROB_DUAL_GATE_CAP = 0.55       # cap when both low-pressure signals fire (Sprint 22: tightened from 0.60)
_MNA_PROB_NO_TRIGGER_CAP = 0.55      # cap when no transaction trigger fires at all (Sprint 22)
_MNA_PROB_HIGH_SCORE_FLOOR = 0.75    # scores above this require TWO transaction drivers (Sprint 22)
# Minimum sub-score thresholds for each transaction trigger
_TRIGGER_FINANCING_MIN = 0.35
_TRIGGER_EXTERNAL_MIN = 0.30
_TRIGGER_CATALYST_MIN = 0.35
_TRIGGER_ACTIVIST_MIN = 0.30
_TRIGGER_VALUATION_MIN = 0.45
_TRIGGER_DERISKING_MIN = 0.50        # valuation distress requires de-risked asset

_DESIGN_TIER_ADJUSTMENTS = {
    "os_rct": 0.08,     # was 0.10; gold-standard endpoint
    "pfs": 0.04,        # was 0.05
    "standard": 0.00,
    "surrogate": -0.12, # was -0.10; surrogate endpoints add approval risk
    "single_arm": -0.20,
}

_SCARCITY_STAGE_ELIGIBLE = {"phase 2", "phase 3", "nda bla", "approved", "commercial"}

# Therapeutic-area competitive pressure sets used by _compute_scarcity_modifiers.
# High-competition TAs have many approved drugs and active pipelines — genuine scarcity
# is harder to establish even if the asset is unique within our tracked universe.
_HIGH_COMPETITION_TAS: frozenset[str] = frozenset({
    "oncology", "immuno oncology", "immunotherapy", "cancer",
    "inflammation", "inflammatory", "immunology", "autoimmune", "rheumatology",
    "depression", "anxiety", "psychiatry", "cns", "central nervous system",
    "diabetes", "type 2 diabetes", "metabolic", "obesity", "nash", "nafld", "fatty liver",
    "cardiovascular", "heart failure", "hypertension",
    "hematology", "infectious disease", "antiviral",
})

# Medium-competition TAs: meaningful competition but less saturated than the above.
_MEDIUM_COMPETITION_TAS: frozenset[str] = frozenset({
    "fibrosis", "pulmonary", "respiratory", "musculoskeletal",
    "dermatology", "skin", "neurology", "alzheimer", "parkinson",
    "hepatology", "liver", "kidney", "renal", "urology", "pain", "endocrinology",
})


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
    max_approved_revenue_share: float = Field(default=0.50, ge=0.0)


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
    mna_targetability_score: float | None = None
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

    # Transaction-likelihood gate reason codes (Sprint 22)
    transaction_gate_reason_codes: list[str] = Field(default_factory=list)
    gap_urgency: str | None = None
    bd_pattern_adjustment: float | None = None
    transaction_driver_count: int | None = None
    canonical_acquirer_id: str | None = None

    # C4: Layer 0 + 3A + 3B modifier diagnostics (always populated after C4 wiring)
    layer3_modifier_multiplier: float = 1.0
    layer3_modifier_cap: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def _sync_probability_aliases(cls, data):
        if isinstance(data, dict):
            if "mna_probability_score" not in data and "mna_targetability_score" in data:
                data["mna_probability_score"] = data["mna_targetability_score"]
            if "mna_targetability_score" not in data and "mna_probability_score" in data:
                data["mna_targetability_score"] = data["mna_probability_score"]
        return data


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
    mna_targetability_score: float | None = None
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

    # C4: Layer 0 + 3A + 3B combined modifier applied to the formula score.
    # Pre-modifier score = mna_probability_score / layer3_modifier_multiplier
    # (useful for formula-version verification; 1.0 means no modifier applied)
    layer3_modifier_multiplier: float = 1.0

    # Calibration layer — logistic model output, does not affect ranking order
    p_takeout_calibrated: float | None = None

    # Three-model decomposition (Sprint 17 — diagnostics only, does not affect ranking)
    target_attractiveness_score: float | None = None
    deal_likelihood_score: float | None = None
    acquirer_fit_score: float | None = None
    transaction_driver_count: int | None = None
    gap_urgency: str | None = None
    bd_pattern_adjustment: float | None = None
    canonical_acquirer_id: str | None = None
    watchlist_type: str | None = None

    # Block 1–4 enrichment fields (optional; populated by enrich_row_with_buyer_thesis)
    buyer_thesis_tier: str | None = None               # UnderwriteThesis.value
    transaction_realism_label: str | None = None       # e.g. "HIGH", "MODERATE"
    recommended_deal_structure: str | None = None      # RecommendedStructure.value
    probability_band_display: str | None = None        # human-readable band or RANK_ONLY text

    @model_validator(mode="before")
    @classmethod
    def _sync_probability_aliases(cls, data):
        if isinstance(data, dict):
            if "mna_probability_score" not in data and "mna_targetability_score" in data:
                data["mna_probability_score"] = data["mna_targetability_score"]
            if "mna_targetability_score" not in data and "mna_probability_score" in data:
                data["mna_targetability_score"] = data["mna_probability_score"]
        return data


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
    transaction_driver_count: int | None = None
    gap_urgency: str | None = None
    watchlist_type: str | None = None


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
        self.knowledge._ensure_column(
            "ma_probability_snapshots",
            "transaction_driver_count",
            "INTEGER",
        )
        self.knowledge._ensure_column("ma_probability_snapshots", "gap_urgency", "TEXT")
        self.knowledge._ensure_column("ma_probability_snapshots", "watchlist_type", "TEXT")
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
            transaction_driver_count=row.transaction_driver_count,
            gap_urgency=row.gap_urgency,
            watchlist_type=row.watchlist_type,
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
                run_id, created_at, p_takeout_calibrated,
                transaction_driver_count, gap_urgency, watchlist_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    snapshot.transaction_driver_count,
                    snapshot.gap_urgency,
                    snapshot.watchlist_type,
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
                   run_id, created_at, p_takeout_calibrated,
                   transaction_driver_count, gap_urgency, watchlist_type
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
                transaction_driver_count=(
                    int(row["transaction_driver_count"])
                    if row["transaction_driver_count"] is not None
                    else None
                ),
                gap_urgency=row["gap_urgency"],
                watchlist_type=row["watchlist_type"],
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
            "run_id, created_at, p_takeout_calibrated, "
            "transaction_driver_count, gap_urgency, watchlist_type "
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
                transaction_driver_count=(
                    int(row["transaction_driver_count"])
                    if row["transaction_driver_count"] is not None
                    else None
                ),
                gap_urgency=row["gap_urgency"],
                watchlist_type=row["watchlist_type"],
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
            watchlist_type = classify_watchlist_type(
                transaction_driver_count=best.transaction_driver_count,
                gate_reason_codes=best.transaction_gate_reason_codes,
            )
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
                    layer3_modifier_multiplier=best.layer3_modifier_multiplier,
                    above_alert_threshold=(
                        best.mna_probability_score / best.layer3_modifier_multiplier
                        if best.layer3_modifier_multiplier > 0.0
                        else best.mna_probability_score
                    ) >= self.config.alert_threshold,
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
                    transaction_driver_count=best.transaction_driver_count,
                    gap_urgency=best.gap_urgency,
                    bd_pattern_adjustment=best.bd_pattern_adjustment,
                    canonical_acquirer_id=best.canonical_acquirer_id,
                    watchlist_type=watchlist_type,
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
                if row.above_alert_threshold
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
        strategic_fit_score = self._strategic_fit_score(fit_row, acquirer=acquirer)
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

        # Transaction-likelihood gate (Sprint 22): dual gate + no-trigger cap +
        # two-driver requirement applied to the main scoring path.
        mna_probability_score, gate_reason_codes, n_triggers = _apply_transaction_likelihood_gate(
            mna_probability_score,
            financing_pressure=vulnerability.cash_runway_pressure_score,
            external_deal_activity=vulnerability.external_deal_pressure_score,
            activist_signal=vulnerability.target_signal_score,
            catalyst_days=getattr(acquisition_row, "days_to_catalyst", None),
            valuation_discount=valuation_discount_score,
            de_risking_stage=de_risking_stage_score,
        )

        # ── C4: Layer 0 + 3A + 3B modifiers ──────────────────────────────────
        # Run target-level Layer 0 assessment from acquisition_row signals.
        _l0_input = _build_target_eligibility_input(acquisition_row)
        _l0 = evaluate_layer0(_l0_input)

        # Layer 3B: pair-specific asset-control (only when Layer 0 flags it).
        _pair_3b: Optional[PairAssetControlResult] = None
        if "pair_asset_control_adjustment" in _l0.required_downstream_checks:
            _pair_3b = compute_pair_asset_control(PairAssetControlInput(
                acquirer_id=acquirer.acquirer_id,
                target_id=getattr(acquisition_row, "asset_id", ""),
                target_asset_control=_l0.encumbrance,
                acquirer_is_existing_partner=_acquirer_is_existing_partner(
                    acquirer, acquisition_row
                ),
                rofr_blocks_this_acquirer=getattr(
                    acquisition_row, "has_right_of_first_refusal", False
                ),
                acquirer_manufacturing_fit=getattr(
                    acquirer, "manufacturing_fit_score", 0.70
                ),
            ))

        # Layer 3A: pair affordability — only when target EV is known.
        # Missing EV does NOT hard-fail: multiplier stays 1.0, reason code noted.
        _afford_mult = 1.0
        _l3_reason_codes: list[str] = []
        _target_ev = getattr(acquisition_row, "enterprise_value_millions", None)
        if _target_ev is not None:
            _afford = compute_pair_affordability(
                _target_ev, _build_acquirer_capacity_input(acquirer)
            )
            _afford_mult = _afford.score_multiplier
        else:
            _l3_reason_codes.append("affordability_data_required")

        # Combine all modifiers → effective_multiplier and effective_cap.
        _mods: PairAdjustedModifiers = combine_layer0_and_3b(
            layer0_score_multiplier=_l0.score_multiplier,
            layer0_score_cap=_l0.score_cap,
            target_max_mna_score_cap=_l0.encumbrance.max_mna_score_cap,
            pair_result=_pair_3b,
            affordability_score_multiplier=_afford_mult,
        )

        # Apply modifiers BEFORE targetability.multiplier.
        # targetability.multiplier covers only commercial-franchise / mega-cap
        # penalties — it does NOT overlap with encumbrance / affordability / 3B.
        mna_probability_score = round(
            mna_probability_score * _mods.effective_multiplier, 6
        )
        if _mods.effective_cap is not None:
            mna_probability_score = min(mna_probability_score, _mods.effective_cap)
        # ── end C4 ────────────────────────────────────────────────────────────

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
        urgency = _gap_urgency_for_match(acquirer, fit_row.matched_therapeutic_gap)
        bd_adjustment = _bd_pattern_adjustment(acquirer)

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
            transaction_gate_reason_codes=list(gate_reason_codes) + _l3_reason_codes,
            gap_urgency=urgency,
            bd_pattern_adjustment=round(bd_adjustment, 6),
            transaction_driver_count=n_triggers,
            canonical_acquirer_id=getattr(acquirer, "canonical_acquirer_id", None)
            or acquirer.acquirer_id,
            layer3_modifier_multiplier=_mods.effective_multiplier,
            layer3_modifier_cap=_mods.effective_cap,
        )

    def _strategic_fit_score(
        self,
        fit_row: AcquirerFitRow,
        *,
        acquirer: Optional[AcquirerProfile] = None,
    ) -> float:
        """Compute strategic fit score with acquirer-specific urgency weighting.

        Base score: weighted average of TA (urgency-adjusted), modality,
        strategic priority, budget (Sprint 22).

        Urgency multiplier scales the TA component by how urgently the acquirer
        needs this area (from _gap_urgency_for_match → _GAP_URGENCY_MULTIPLIERS):
          - high (1.00): TA component unchanged; base can reach ~0.80 → capped at 0.70
          - medium (0.55): typical case; all-good sub-scores → base ≈ 0.68, below cap
          - low (0.28): tangential overlap; base ≈ 0.61
          - no match (0.15): incidental TA relevance; base ≈ 0.56

        BD pattern adjustment (Sprint 22): ≥3 recent deals → +0.03; 0 deals → −0.12.

        Quality penalties (Sprint 21):
          - weak_commercial_overlap: TA score < 0.50 → -0.10
          - poor_modality_fit: modality score < 0.50 → -0.10
          - no_pipeline_gap: strategic priority < 0.50 → -0.15
          - poor_deal_size_fit: budget score < 0.40 → -0.10
        Hard cap: _STRATEGIC_FIT_HARD_CAP (0.70).
        """
        fit_weights = self.fit_engine.scorer.config.resolved_weights()
        strategic_weight = (
            fit_weights["therapeutic_area"]
            + fit_weights["modality"]
            + fit_weights["strategic_priority"]
            + fit_weights["budget"]
        )
        if strategic_weight <= 0:
            return 0.0

        # Urgency multiplier on the TA component (Sprint 22)
        urgency = _gap_urgency_for_match(acquirer, fit_row.matched_therapeutic_gap)
        urgency_mult = _GAP_URGENCY_MULTIPLIERS.get(
            urgency or "", _GAP_URGENCY_NONE_MULTIPLIER
        )
        adjusted_ta_component = fit_row.therapeutic_area_component * urgency_mult

        strategic_component = (
            adjusted_ta_component
            + fit_row.modality_component
            + fit_row.strategic_priority_component
            + fit_row.budget_component
        )
        base = min(max(strategic_component / strategic_weight, 0.0), 1.0)

        # BD pattern recency adjustment (Sprint 22)
        bd_adj = _bd_pattern_adjustment(acquirer)
        base = min(max(base + bd_adj, 0.0), 1.0)

        # Quality penalty deductions (Sprint 21)
        penalty = 0.0
        if fit_row.therapeutic_area_score < _STRATEGIC_FIT_WEAK_TA_THRESHOLD:
            penalty += _STRATEGIC_FIT_PENALTY_WEAK_TA
        if fit_row.modality_score < _STRATEGIC_FIT_POOR_MODALITY_THRESHOLD:
            penalty += _STRATEGIC_FIT_PENALTY_POOR_MODALITY
        if fit_row.strategic_priority_score < _STRATEGIC_FIT_NO_GAP_THRESHOLD:
            penalty += _STRATEGIC_FIT_PENALTY_NO_PIPELINE_GAP
        if fit_row.budget_score < _STRATEGIC_FIT_POOR_DEAL_SIZE_THRESHOLD:
            penalty += _STRATEGIC_FIT_PENALTY_POOR_DEAL_SIZE

        penalized = max(base - penalty, 0.0)
        return round(min(penalized, _STRATEGIC_FIT_HARD_CAP), 6)

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
            base_score, bucket = _scarcity_score_from_peer_count(peer_count)
            modifier = _compute_scarcity_modifiers(prepared.context)
            score = round(min(max(base_score + modifier, 0.0), 0.80), 6)
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


def _gap_urgency_for_match(
    acquirer: Optional[AcquirerProfile],
    matched_gap: Optional[str],
) -> Optional[str]:
    """Return the exposure_level (urgency) for the matched therapeutic gap.

    Matches by the same label produced by acquirer_fit._gap_label():
        "<therapeutic_area>:<sub_area>" when sub_area is present, else "<therapeutic_area>".
    Returns None if no match is found or if acquirer / matched_gap are absent.
    """
    if acquirer is None or matched_gap is None:
        return None
    for gap in acquirer.therapeutic_area_gaps:
        label = (
            f"{gap.therapeutic_area}:{gap.sub_area}"
            if gap.sub_area
            else str(gap.therapeutic_area)
        )
        if label == matched_gap:
            return gap.exposure_level
    return None


def _bd_pattern_adjustment(acquirer: Optional[AcquirerProfile]) -> float:
    """Return a BD-pattern recency adjustment based on count of recent deals.

    ≥3 deals: +_BD_PATTERN_BONUS_3_PLUS   (confirmed active acquirer)
    0 deals:  +_BD_PATTERN_PENALTY_ZERO   (no BD precedent; likely internal-build)
    1-2 deals: 0.0                         (neutral)
    """
    if acquirer is None:
        return 0.0
    n_deals = len(acquirer.recent_deal_history)
    if n_deals >= 3:
        return _BD_PATTERN_BONUS_3_PLUS
    if n_deals == 0:
        return _BD_PATTERN_PENALTY_ZERO
    return 0.0


def _apply_transaction_likelihood_gate(
    score: float,
    *,
    financing_pressure: float,
    external_deal_activity: float,
    activist_signal: float,
    catalyst_days: Optional[int],
    valuation_discount: float,
    de_risking_stage: float,
) -> tuple[float, list[str], int]:
    """Apply transaction-likelihood caps to the main mna_probability_score.

    Returns (capped_score, reason_codes, n_triggers) where reason_codes lists any caps applied.

    Three gates (Sprint 22):
    1. No-trigger cap: if no transaction trigger fires at all, cap at
       _MNA_PROB_NO_TRIGGER_CAP (0.55).  Reason: "missing_trigger:all".
    2. Dual gate: financing_not_pressured AND no_buyer_urgency → cap at
       _MNA_PROB_DUAL_GATE_CAP (0.55).  Reason: "dual_gate:low_pressure".
       'Not pressured' = financing_pressure < 0.25.
       'No buyer urgency' = external_deal_activity < 0.20.
    3. High-score two-driver requirement: score > 0.75 requires at least TWO
       transaction triggers to be present.  If only one fires, score is capped
       at _MNA_PROB_HIGH_SCORE_FLOOR (0.75).  Reason: "missing_trigger:second".
       Transaction triggers:
         - financing pressure ≥ 0.35
         - external deal activity ≥ 0.30
         - catalyst within range (days ≤ 90)
         - activist signal ≥ 0.30
         - valuation distress (discount ≥ 0.45 AND de_risking ≥ 0.50)
    """
    reason_codes: list[str] = []

    catalyst_close = (
        catalyst_days is not None
        and catalyst_days >= 0
        and catalyst_days <= 90
    )
    valuation_distress = (
        valuation_discount >= _TRIGGER_VALUATION_MIN
        and de_risking_stage >= _TRIGGER_DERISKING_MIN
    )

    # Count fired triggers
    trigger_flags = [
        financing_pressure >= _TRIGGER_FINANCING_MIN,
        external_deal_activity >= _TRIGGER_EXTERNAL_MIN,
        catalyst_close,
        activist_signal >= _TRIGGER_ACTIVIST_MIN,
        valuation_distress,
    ]
    n_triggers = sum(trigger_flags)

    # Gate 1: no trigger at all → no-trigger cap
    if n_triggers == 0 and score > _MNA_PROB_NO_TRIGGER_CAP:
        score = _MNA_PROB_NO_TRIGGER_CAP
        reason_codes.append("missing_trigger:all")

    # Gate 2: dual low-pressure gate
    financing_not_pressured = financing_pressure < 0.25
    no_buyer_urgency = external_deal_activity < 0.20
    if financing_not_pressured and no_buyer_urgency and score > _MNA_PROB_DUAL_GATE_CAP:
        score = _MNA_PROB_DUAL_GATE_CAP
        reason_codes.append("dual_gate:low_pressure")

    # Gate 3: high-score requires two transaction drivers
    if score > _MNA_PROB_HIGH_SCORE_FLOOR and n_triggers < 2:
        score = _MNA_PROB_HIGH_SCORE_FLOOR
        if n_triggers == 0:
            reason_codes.append("missing_trigger:all")
        else:
            reason_codes.append("missing_trigger:second")

    return round(min(max(score, 0.0), 1.0), 6), reason_codes, n_triggers


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
    """Score representing how de-risked the asset is as an acquisition target.

    Base scores are capped at 0.90 (below the saturation threshold of 0.95) to
    ensure the saturation penalty in _score_acquirer_candidate does not fire
    solely due to a Phase 3 / NDA asset being in the watchlist.  Quality
    penalties for safety overhang, prior Phase 3 failure, and label uncertainty
    can reduce the score further.  The design-tier adjustment and POS uplift can
    raise it back up, subject to the same 0.90 cap.
    """
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

    # Optional quality penalties set by the acquisition screener.
    for attr, penalty in _DERISKING_QUALITY_PENALTIES.items():
        if bool(getattr(acquisition_row, attr, False)):
            score += penalty

    # Optional quality bonuses (e.g. FDA Breakthrough Designation).
    for attr, bonus in _DERISKING_QUALITY_BONUSES.items():
        if bool(getattr(acquisition_row, attr, False)):
            score += bonus

    return min(max(round(score, 6), 0.0), _DERISKING_STAGE_SCORE_CAP)


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
    """Base scarcity score derived from same-indication-mechanism peer count.

    Base scores are substantially lower than historical values because in a
    curated watchlist every asset appears unique within the tracked universe,
    meaning peer_count=0 is the norm rather than the exception.  The multi-factor
    modifiers in _compute_scarcity_modifiers then differentiate based on broader
    competitive context (TA crowding, modality, orphan status, validated MoA).

    Maximum base score is 0.55; modifiers can push up to the hard cap of 0.80.
    """
    if peer_count == 0:
        return 0.55, "very_high"
    if peer_count <= 3:
        return 0.38, "high"
    if peer_count <= 6:
        return 0.22, "medium"
    if peer_count <= 9:
        return 0.12, "low"
    return 0.05, "very_low"


# ---------------------------------------------------------------------------
# Scarcity multi-factor modifiers
# ---------------------------------------------------------------------------

_ORPHAN_RARE_INDICATIONS: frozenset[str] = frozenset({
    "rare disease",
    "orphan",
    "ultra-rare",
    "lysosomal storage",
    "gaucher",
    "fabry",
    "pompe",
    "spinal muscular atrophy",
    "hemophilia",
    "hereditary angioedema",
    "transthyretin amyloidosis",
    # Short abbreviations (sma, hae, attr) removed: substring false-positives
    # (e.g. "sma" matches "non-small cell"; "attr" matches "attribute").
    # Full disease names above are sufficient for matching.
})

_SCARCE_MODALITIES: frozenset[str] = frozenset({
    "gene therapy",
    "gene editing",
    "cell therapy",
    "car-t",
    "cart",
    "mrna",
    "antisense oligonucleotide",
    "aso",
    "rnai",
    "crispr",
    "epigenetic",
    "protein degrader",
    "protac",
    "antibody drug conjugate",
    "adc",
    "bispecific",
    "bispecific antibody",
})


def _compute_scarcity_modifiers(context) -> float:
    """Compute additive scarcity modifier from asset-level context.

    Bonuses (increase scarcity):
    - Orphan / rare disease indication:          +0.20  (was +0.05)
    - Novel / scarce modality (ADC, gene therapy, etc.):  +0.15  (was +0.04)
    - Named validated mechanism of action:       +0.10  (was +0.02)

    Penalties (decrease scarcity due to broader market competition):
    - High-competition TA (oncology, immuno, diabetes, CVD, etc.):  -0.15
    - Medium-competition TA (neurology, fibrosis, dermatology, etc.): -0.07

    Returns a float in [-0.20, +0.30].  The caller caps the final score at 0.80.
    """
    asset = getattr(context, "asset", None)
    if asset is None:
        return 0.0

    modifier = 0.0

    indication = _normalize(getattr(asset, "indication", None)) or ""
    therapeutic_area = _normalize(getattr(asset, "therapeutic_area", None)) or ""
    ta_combined = indication + " " + therapeutic_area

    # Orphan / rare disease (strong scarcity signal for acquirers)
    if any(kw in indication or kw in therapeutic_area for kw in _ORPHAN_RARE_INDICATIONS):
        modifier += 0.20

    # Novel / scarce modality
    modality_val = getattr(asset, "modality", None)
    modality_str = _normalize(
        getattr(modality_val, "value", None) if modality_val is not None else None
    ) or ""
    if any(kw in modality_str for kw in _SCARCE_MODALITIES):
        modifier += 0.15

    # Explicitly named mechanism of action (validated science)
    moa = _normalize(getattr(asset, "mechanism_of_action", None))
    if moa is not None and len(moa) >= 4:
        modifier += 0.10

    # TA competitive pressure penalties: high competition → lower genuine scarcity
    if any(kw in ta_combined for kw in _HIGH_COMPETITION_TAS):
        modifier -= 0.15
    elif any(kw in ta_combined for kw in _MEDIUM_COMPETITION_TAS):
        modifier -= 0.07

    return round(min(max(modifier, -0.20), 0.30), 4)


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


# ---------------------------------------------------------------------------
# C4 private helpers — Layer 0 / 3A / 3B wiring
# ---------------------------------------------------------------------------

_VALID_MFG_COMPLEXITY = frozenset({"low", "medium", "high"})
_VALID_RIGHTS_SCOPE = frozenset({"global", "regional_split", "licensed_in", "unknown"})


def _build_target_eligibility_input(acquisition_row) -> TargetEligibilityInput:
    """Build a TargetEligibilityInput from a live acquisition row using safe defaults.

    All optional encumbrance fields default to False / None so that missing
    data on the acquisition_row produces the most conservative (clean) assumption
    at Layer 0, exactly as intended — callers that want precise 0D-T scoring must
    populate the corresponding fields on their acquisition_row objects.

    Data-completeness flags (has_*) are auto-derived from value presence where
    possible, and also read from the row when explicitly set.  This prevents Gate 6
    (financial going-concern) from firing just because the row doesn't carry every
    has_* boolean explicitly.
    """
    mfg = getattr(acquisition_row, "manufacturing_complexity", "low")
    if mfg not in _VALID_MFG_COMPLEXITY:
        mfg = "low"
    rights = getattr(acquisition_row, "asset_rights_scope", "global")
    if rights not in _VALID_RIGHTS_SCOPE:
        rights = "global"

    mc = getattr(acquisition_row, "market_cap_millions", None)
    ev = getattr(acquisition_row, "enterprise_value_millions", None)
    stage = getattr(acquisition_row, "stage", None)

    return TargetEligibilityInput(
        ticker=getattr(acquisition_row, "ticker", None) or "UNKNOWN",
        lead_asset_stage=stage,
        market_cap_millions=mc,
        enterprise_value_millions=ev,
        asset_rights_scope=rights,
        has_existing_partnership=getattr(acquisition_row, "has_existing_partnership", False),
        has_right_of_first_refusal=getattr(acquisition_row, "has_right_of_first_refusal", False),
        manufacturing_complexity=mfg,
        royalty_stack_rate=getattr(acquisition_row, "royalty_stack_rate", None),
        has_co_development_obligation=getattr(
            acquisition_row, "has_co_development_obligation", False
        ),
        has_ip_dispute=getattr(acquisition_row, "has_ip_dispute", False),
        has_manufacturing_dependency=getattr(
            acquisition_row, "has_manufacturing_dependency", False
        ),
        has_asset_ownership_data=getattr(acquisition_row, "has_asset_ownership_data", False),
        has_partner_rights_data=getattr(acquisition_row, "has_partner_rights_data", False),
        # 0G data-completeness: auto-derived from value presence + explicit row flags
        has_market_cap=mc is not None,
        has_enterprise_value=ev is not None,
        has_clinical_stage=stage is not None,
        has_cash_debt=getattr(acquisition_row, "has_cash_debt", False),
        has_quarterly_burn=getattr(acquisition_row, "has_quarterly_burn", False),
        has_revenue_mix=getattr(acquisition_row, "has_revenue_mix", False),
        has_trial_status=getattr(acquisition_row, "has_trial_status", False),
        has_patent_loe_data=getattr(acquisition_row, "has_patent_loe_data", False),
        has_acquirer_profile_data=getattr(acquisition_row, "has_acquirer_profile_data", False),
    )


def _build_acquirer_capacity_input(acquirer: AcquirerProfile) -> AcquirerCapacityInput:
    """Build an AcquirerCapacityInput from an AcquirerProfile.

    Uses acquisition_capacity_millions when set (the curated capacity ceiling),
    falling back to cash_billions × 1000.  Market cap is passed when available
    so the formula path can estimate the stock deal component.
    """
    if acquirer.acquisition_capacity_millions is not None:
        cash_avail = acquirer.acquisition_capacity_millions
    elif acquirer.cash_billions is not None:
        cash_avail = acquirer.cash_billions * 1000.0
    elif acquirer.budget is not None:
        cash_avail = acquirer.budget.net_cash_millions or 0.0
    else:
        cash_avail = 0.0
    cap_millions = (
        acquirer.market_cap_billions * 1000.0
        if acquirer.market_cap_billions is not None
        else None
    )
    return AcquirerCapacityInput(
        acquirer_id=acquirer.acquirer_id,
        cash_available_millions=cash_avail,
        acquirer_market_cap_millions=cap_millions,
    )


def _acquirer_is_existing_partner(
    acquirer: AcquirerProfile,
    acquisition_row,
) -> bool:
    """Return True if acquirer has an active partnership with this target.

    Matches against ExistingPartnership.target (ticker or company name) using
    a case-insensitive substring check.  Returns False when no ticker/asset_id
    is available on the acquisition_row.
    """
    target_ticker = (_upper(getattr(acquisition_row, "ticker", None)) or "")
    target_id = (getattr(acquisition_row, "asset_id", None) or "").lower()
    if not target_ticker and not target_id:
        return False
    for p in acquirer.existing_partnerships:
        p_upper = (p.target or "").upper()
        if target_ticker and target_ticker in p_upper:
            return True
        if target_id and target_id in p_upper.lower():
            return True
    return False


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


# ---------------------------------------------------------------------------
# Block 1–4 enrichment layer
# ---------------------------------------------------------------------------

def enrich_row_with_buyer_thesis(
    row: "MAProbabilityRow",
    *,
    mandate_inputs: dict,
    conflict_inputs: dict,
    relationship_inputs: dict,
    realism_inputs: dict,
    segment_outcomes: list[int] | None = None,
    segment_label: str = "",
    minimum_n: int = 10,
) -> "MAProbabilityRow":
    """
    Enrich a MAProbabilityRow with Block 1–4 outputs.

    Computes:
      - BuyerTargetThesis (Block 1) → buyer_thesis_tier
      - TransactionRealismScore (Block 2) → transaction_realism_label
      - DealStructureRationale (Block 3) → recommended_deal_structure
      - CalibratedProbabilityBand (Block 4) → probability_band_display
        (only when segment_outcomes is provided; RANK_ONLY when N < minimum_n)

    Does NOT modify any existing scoring fields. Returns a new row via model_copy.
    """
    from bve.intelligence.ma_buyer_mandate import compute_buyer_mandate_score
    from bve.intelligence.ma_internal_conflict import compute_internal_conflict
    from bve.intelligence.ma_relationship_history import compute_relationship_history
    from bve.intelligence.ma_buyer_thesis import build_buyer_target_thesis
    from bve.intelligence.ma_transaction_realism import compute_transaction_realism
    from bve.intelligence.ma_deal_structure_rationale import build_deal_structure_rationale
    from bve.intelligence.ma_calibrated_probability_band import compute_probability_band

    # Block 1: Buyer thesis
    mandate = compute_buyer_mandate_score(mandate_inputs)
    conflict = compute_internal_conflict(conflict_inputs)
    relationship = compute_relationship_history(relationship_inputs)
    thesis = build_buyer_target_thesis(
        mandate_score=mandate,
        conflict_score=conflict,
        relationship_score=relationship,
    )

    # Block 2: Transaction realism
    realism = compute_transaction_realism(realism_inputs)

    # Block 3: Deal structure rationale
    structure_rationale = build_deal_structure_rationale(thesis=thesis, realism=realism)

    # Block 4: Probability band (optional)
    band_display: str | None = None
    if segment_outcomes is not None:
        band = compute_probability_band(
            segment_outcomes,
            minimum_n=minimum_n,
            segment_label=segment_label,
        )
        band_display = band.label_text

    return row.model_copy(update={
        "buyer_thesis_tier": thesis.underwrite_thesis.value,
        "transaction_realism_label": realism.realism_label,
        "recommended_deal_structure": structure_rationale.recommended_structure.value,
        "probability_band_display": band_display,
    })
