"""
Layer 3 — Pair-Specific Deal Realism Engine (Institutional-Grade).

Answers: "For this specific acquirer-target pair, is the deal actually
executable, or should the Layer 2 BD Action Score be capped because
something makes the pairing unrealistic?"

Diagnostic weighted score (for reporting):
    pair_feasibility_score =
        0.20 × affordability_financing_realism
      + 0.15 × consideration_realism
      + 0.20 × rights_control_fit
      + 0.15 × integration_capability
      + 0.15 × antitrust_feasibility
      + 0.10 × strategic_conflict_feasibility
      + 0.05 × process_closing_feasibility

Final BD score adjustment (enforcement logic):
    if hard_fail:
        adjusted_bd_score = 0.0
    else:
        adjusted_bd_score = min(
            upstream_layer2_score × combined_layer3_multiplier,
            pair_level_cap,
        )

Layer 3 deliberately does NOT answer:
    • Is this asset attractive?              → Layer 1
    • Should BD act now?                     → Layer 2
    • What deal structure to use?            → Layer 4
    • Calibrated acquisition probability?    → Layer 5
    • Is the target eligible at all?         → Layer 0

Anti-double-counting ownership map:
    Target-level encumbrance facts        → Layer 0 / ma_asset_control_target
    Target strategic attractiveness       → Layer 1 / ma_layer1_attractiveness
    BD action priority                    → Layer 2 / ma_layer2_bd_priority
    Pair affordability (3A)               → this module + ma_pair_affordability
    Consideration realism (3B)            → this module only
    Rights/control pair fit (3C)          → this module + ma_pair_asset_control
    Integration capability (3D)           → this module + ma_integration_complexity
    Antitrust feasibility (3E)            → this module only
    Strategic conflict (3F)               → this module only
    Process / closing risk (3G)           → this module only
    Diligence blockers (3H)               → this module only
    Deal structure routing                → Layer 4
    Calibration                           → Layer 5
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from bve.intelligence.deal_type_classification import DealStructureRoute
from bve.intelligence.ma_pair_affordability import AffordabilityBand, AffordabilityResult
from bve.intelligence.ma_pair_asset_control import PairAssetControlResult
from bve.intelligence.ma_integration_complexity import PairIntegrationAdjustment


# ---------------------------------------------------------------------------
# Weight constants
# ---------------------------------------------------------------------------

L3_WEIGHTS: dict[str, float] = {
    "affordability":          0.20,
    "consideration_realism":  0.15,
    "rights_control_fit":     0.20,
    "integration_capability": 0.15,
    "antitrust_feasibility":  0.15,
    "strategic_conflict":     0.10,
    "process_closing":        0.05,
}
assert abs(sum(L3_WEIGHTS.values()) - 1.0) < 1e-9, "L3_WEIGHTS must sum to 1.0"

_CONSIDERATION_WEIGHTS: dict[str, float] = {
    "cash_stock_mix_feasibility":          0.30,
    "target_shareholder_acceptability":    0.20,
    "acquirer_shareholder_acceptability":  0.15,
    "cvr_milestone_suitability":           0.15,
    "tax_efficiency":                      0.10,
    "precedent_consistency":               0.10,
}

_ANTITRUST_WEIGHTS: dict[str, float] = {
    "current_product_overlap":      0.25,
    "pipeline_overlap":             0.20,
    "market_concentration":         0.20,
    "innovation_competition_risk":  0.15,
    "divestiture_complexity":       0.10,
    "jurisdictional_complexity":    0.10,
}

_CONFLICT_WEIGHTS: dict[str, float] = {
    "product_cannibalization":       0.30,
    "pipeline_cannibalization":      0.20,
    "channel_conflict":              0.15,
    "partner_conflict":              0.15,
    "pricing_contracting_conflict":  0.10,
    "organizational_conflict":       0.10,
}

_PROCESS_WEIGHTS: dict[str, float] = {
    "target_board_alignment":              0.20,
    "shareholder_approval_likelihood":     0.15,
    "management_retention_feasibility":    0.15,
    "financing_process_readiness":         0.15,
    "diligence_package_readiness":         0.10,
    "cross_border_execution_feasibility":  0.10,
    "timeline_feasibility":                0.10,
    "litigation_risk_inverse":             0.05,
}

_CONFIDENCE_WEIGHTS: dict[str, float] = {
    "affordability":          0.20,
    "consideration_realism":  0.15,
    "rights_control_fit":     0.20,
    "integration_capability": 0.15,
    "antitrust_feasibility":  0.15,
    "strategic_conflict":     0.10,
    "process_closing":        0.05,
}

_NEUTRAL: float = 0.50


def _CLAMP(v: float) -> float:  # noqa: N802  (kept UPPER for grep-compatibility)
    return max(0.0, min(1.0, float(v)))


# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------

def _multiplier_for_severity(severity: str) -> float:
    """Return the score multiplier for a named severity tier."""
    return {"none": 1.00, "mild": 0.90, "meaningful": 0.75, "severe": 0.55, "fatal": 0.00}.get(
        severity, 1.00
    )


# ---------------------------------------------------------------------------
# Shared diagnostic models
# ---------------------------------------------------------------------------

class Layer3Cap(BaseModel):
    """A named cap applied to the pair-level BD score."""
    model_config = ConfigDict(frozen=True)

    name: str
    cap_value: float = Field(..., ge=0.0, le=1.0)
    reason: str
    triggered_by: str
    owning_layer: str = "Layer 3"
    severity: str  # mild / meaningful / severe / fatal


class Layer3HardFail(BaseModel):
    """A hard fail that zeros the adjusted BD score for this pair."""
    model_config = ConfigDict(frozen=True)

    name: str
    reason: str
    triggered_by: str
    remediation_possible: bool = True
    layer4_routing_hint: Optional[str] = None


class Layer3Blocker(BaseModel):
    """A diligence blocker flagged during 3H checklist evaluation."""
    model_config = ConfigDict(frozen=True)

    blocker_name: str
    severity: str  # minor / moderate / major / fatal
    confidence: float = Field(default=0.70, ge=0.0, le=1.0)
    source: Optional[str] = None
    owning_layer: str = "Layer 3"
    remediation_path: Optional[str] = None
    cap_or_fail: Optional[str] = None  # e.g. "cap_0.55" or "hard_fail"


class Layer3RemediationPath(BaseModel):
    """A suggested remediation for a cap or blocker."""
    model_config = ConfigDict(frozen=True)

    issue: str
    remediation: str
    likely_deal_structure: Optional[str] = None
    feasibility: float = Field(default=0.50, ge=0.0, le=1.0)
    rationale: str = ""


# ---------------------------------------------------------------------------
# Component input models
# ---------------------------------------------------------------------------

class ConsiderationRealismInputs(BaseModel):
    """3B — consideration form feasibility."""
    model_config = ConfigDict(frozen=True)

    acquirer_stock_quality: float = Field(default=_NEUTRAL, ge=0.0, le=1.0,
        description="Stock currency strength: 0=bad/volatile, 1=premium/stable")
    target_requires_cash_certainty: bool = False
    cvr_suitability: float = Field(default=_NEUTRAL, ge=0.0, le=1.0,
        description="Suitability of a CVR/milestone structure for this binary asset")
    cvr_needed_but_milestone_definition_unclear: bool = Field(default=False,
        description="CVR/milestone structure appears needed but milestone definition is unclear")
    target_shareholder_acceptability: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    acquirer_shareholder_acceptability: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    precedent_consistency: float = Field(default=_NEUTRAL, ge=0.0, le=1.0,
        description="Consistency with recent comparable deal structures")
    tax_efficiency: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    data_confidence: float = Field(default=0.60, ge=0.0, le=1.0)


class AntitrustInputs(BaseModel):
    """3E — product / pipeline / market-concentration antitrust risk."""
    model_config = ConfigDict(frozen=True)

    current_product_overlap: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Direct product market overlap between buyer and target")
    pipeline_overlap: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Competing pipeline assets in same indication / mechanism")
    market_concentration: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Post-merger HHI or qualitative market concentration risk")
    innovation_competition_risk: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Risk of regulator blocking on innovation competition grounds")
    divestiture_complexity: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Difficulty of required divestitures")
    jurisdictional_complexity: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Multi-jurisdiction filing complexity (US/EU/China)")
    required_divestiture_removes_core_value: bool = Field(default=False,
        description="True if required divestiture destroys the primary deal rationale")
    data_confidence: float = Field(default=0.60, ge=0.0, le=1.0)


class StrategicConflictInputs(BaseModel):
    """3F — internal strategic conflict / cannibalization risk."""
    model_config = ConfigDict(frozen=True)

    product_cannibalization: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Target cannibalizes buyer's existing commercial product")
    pipeline_cannibalization: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Target's pipeline competes with buyer's internal program")
    channel_conflict: float = Field(default=0.0, ge=0.0, le=1.0)
    partner_conflict: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Conflict with existing co-development or licensing partner")
    pricing_contracting_conflict: float = Field(default=0.0, ge=0.0, le=1.0)
    organizational_conflict: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Internal priority conflict / resource competition")
    directly_cannibalizes_core_franchise: bool = Field(default=False,
        description="Target directly cannibalizes buyer's core franchise without clear replacement logic")
    has_exclusive_partnership_conflict: bool = Field(default=False,
        description="Buyer has existing exclusive partnership that conflicts with this deal")
    requires_killing_high_priority_internal_program: bool = Field(default=False)
    data_confidence: float = Field(default=0.60, ge=0.0, le=1.0)


class ProcessClosingInputs(BaseModel):
    """3G — process, governance, and closing risk."""
    model_config = ConfigDict(frozen=True)

    target_board_alignment: float = Field(default=_NEUTRAL, ge=0.0, le=1.0,
        description="Board/management alignment with a sale process")
    shareholder_approval_likelihood: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    management_retention_feasibility: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    financing_process_readiness: float = Field(default=_NEUTRAL, ge=0.0, le=1.0,
        description="Buyer's acquisition financing / bridge process readiness")
    diligence_package_readiness: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    cross_border_execution_feasibility: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    timeline_feasibility: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    litigation_risk: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Material ongoing litigation that could block close")
    # Cap triggers
    shareholder_approval_unlikely: bool = False
    founder_controlled_and_unwilling: bool = False
    unresolved_litigation_blocks_close: bool = False
    management_retention_required_and_unlikely: bool = False
    data_confidence: float = Field(default=0.60, ge=0.0, le=1.0)


class DiligenceFlagInputs(BaseModel):
    """3H — diligence blocker checklist."""
    model_config = ConfigDict(frozen=True)

    ip_ownership_uncertainty: bool = False
    undisclosed_royalty_stack: bool = False
    unfavorable_coc_clause: bool = False
    trial_data_integrity_issue: bool = False
    cmc_package_incomplete: bool = False
    gmp_inspection_issue: bool = False
    supply_dependency_severe: bool = False
    material_litigation: bool = False
    compliance_fcpa_issue: bool = False
    sanctions_export_control: bool = False
    key_employee_retention_risk: bool = False


# ---------------------------------------------------------------------------
# Component output models
# ---------------------------------------------------------------------------

class Layer3AffordabilityOutput(BaseModel):
    """3A — pair-specific affordability result."""
    model_config = ConfigDict(frozen=True)

    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(default=0.70, ge=0.0, le=1.0)
    affordability_ratio: Optional[float] = None
    treatment: str = "unknown"
    expected_acquisition_cost_millions: Optional[float] = None
    deal_capacity_millions: Optional[float] = None
    positive_drivers: list[str] = Field(default_factory=list)
    negative_drivers: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


class Layer3ConsiderationOutput(BaseModel):
    """3B — consideration form / payment mix feasibility."""
    model_config = ConfigDict(frozen=True)

    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(default=0.60, ge=0.0, le=1.0)
    likely_consideration_mix: str = "mixed"
    cvr_suitability: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    positive_drivers: list[str] = Field(default_factory=list)
    negative_drivers: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


class Layer3RightsControlOutput(BaseModel):
    """3C — pair-specific rights / ROFR / regional fit."""
    model_config = ConfigDict(frozen=True)

    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(default=0.70, ge=0.0, le=1.0)
    rofr_impact: str = "none"
    regional_rights_fit: float = Field(default=1.0, ge=0.0, le=1.0)
    existing_partner_status: bool = False
    positive_drivers: list[str] = Field(default_factory=list)
    negative_drivers: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


class Layer3IntegrationOutput(BaseModel):
    """3D — pair-specific integration capability."""
    model_config = ConfigDict(frozen=True)

    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(default=0.60, ge=0.0, le=1.0)
    buyer_integration_capability: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    raw_integration_complexity_score: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    adjusted_integration_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    treatment: str = "unknown"
    positive_drivers: list[str] = Field(default_factory=list)
    negative_drivers: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


class Layer3AntitrustOutput(BaseModel):
    """3E — antitrust / competition feasibility."""
    model_config = ConfigDict(frozen=True)

    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(default=0.60, ge=0.0, le=1.0)
    antitrust_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    current_product_overlap: float = Field(default=0.0, ge=0.0, le=1.0)
    pipeline_overlap: float = Field(default=0.0, ge=0.0, le=1.0)
    jurisdiction_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    positive_drivers: list[str] = Field(default_factory=list)
    negative_drivers: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


class Layer3StrategicConflictOutput(BaseModel):
    """3F — strategic conflict / cannibalization feasibility."""
    model_config = ConfigDict(frozen=True)

    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(default=0.60, ge=0.0, le=1.0)
    conflict_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    cannibalization_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    partner_conflict: float = Field(default=0.0, ge=0.0, le=1.0)
    positive_drivers: list[str] = Field(default_factory=list)
    negative_drivers: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


class Layer3ProcessClosingOutput(BaseModel):
    """3G — process, governance, and closing feasibility."""
    model_config = ConfigDict(frozen=True)

    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(default=0.60, ge=0.0, le=1.0)
    governance_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    shareholder_approval_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    closing_timeline_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    positive_drivers: list[str] = Field(default_factory=list)
    negative_drivers: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level input / output
# ---------------------------------------------------------------------------

class PairRealismInputs(BaseModel):
    """All inputs for Layer 3 pair-realism evaluation.

    Pre-computed pair results from existing modules (3A, 3C, 3D) are accepted
    directly.  New component inputs (3B, 3E, 3F, 3G, 3H) are defined here.
    """
    model_config = ConfigDict(frozen=True)

    target_id: str
    acquirer_id: str
    upstream_layer2_score: float = Field(..., ge=0.0, le=1.0,
        description="Layer 2 BD Action Score for this target")

    # Pre-computed pair results from existing modules
    affordability: Optional[AffordabilityResult] = Field(default=None,
        description="From compute_pair_affordability() in ma_pair_affordability")
    rights_control: Optional[PairAssetControlResult] = Field(default=None,
        description="From compute_pair_asset_control() in ma_pair_asset_control")
    integration: Optional[PairIntegrationAdjustment] = Field(default=None,
        description="From compute_pair_integration_adjustment() in ma_integration_complexity")

    # 3A extended affordability triggers (not captured in AffordabilityResult)
    acquirer_credit_stress_high: bool = Field(default=False,
        description="Acquirer is under credit / rating stress")
    deal_requires_large_debt: bool = Field(default=False,
        description="Transaction requires substantial debt financing")
    target_requires_cash_deal: bool = Field(default=False,
        description="Target (board/shareholders) requires cash-certain consideration")
    buyer_cash_insufficient: bool = Field(default=False,
        description="Acquirer does not have sufficient cash for a cash deal")

    # 0B deal-structure route — passed to Layer 3B pair-asset-control if invoked here
    deal_structure_route: Optional[DealStructureRoute] = Field(default=None,
        description="Layer 0B deal-structure route for this pair. Forwarded to "
                    "compute_pair_asset_control() so Layer 3B scoring is route-aware.")

    # New component inputs
    consideration: ConsiderationRealismInputs = Field(
        default_factory=ConsiderationRealismInputs)
    antitrust: AntitrustInputs = Field(default_factory=AntitrustInputs)
    strategic_conflict: StrategicConflictInputs = Field(default_factory=StrategicConflictInputs)
    process_closing: ProcessClosingInputs = Field(default_factory=ProcessClosingInputs)
    diligence_flags: DiligenceFlagInputs = Field(default_factory=DiligenceFlagInputs)


class PairRealismOutput(BaseModel):
    """Full Layer 3 pair-specific deal realism output.

    Pair-level scope: hard fails and caps apply only to this acquirer-target
    pair.  The target remains eligible for other acquirers.
    """
    model_config = ConfigDict(frozen=True)

    target_id: str
    acquirer_id: str
    upstream_layer2_score: float

    # Component sub-results
    affordability: Layer3AffordabilityOutput
    consideration_realism: Layer3ConsiderationOutput
    rights_control_fit: Layer3RightsControlOutput
    integration_capability: Layer3IntegrationOutput
    antitrust_feasibility: Layer3AntitrustOutput
    strategic_conflict: Layer3StrategicConflictOutput
    process_closing_feasibility: Layer3ProcessClosingOutput
    diligence_blockers: list[Layer3Blocker]

    # Aggregate scores and adjustments
    pair_feasibility_score: float = Field(..., ge=0.0, le=1.0,
        description="Diagnostic weighted score across all 7 components")
    pair_feasibility_multiplier: float = Field(..., ge=0.0, le=1.0,
        description="Product of all component multipliers applied to L2 score")
    pair_level_cap: float = Field(..., ge=0.0, le=1.0,
        description="Most restrictive cap across all components (1.0 = no cap)")
    hard_fail: bool
    adjusted_bd_score: float = Field(..., ge=0.0, le=1.0,
        description="Final adjusted BD score: 0.0 on hard fail, else min(L2*mult, cap)")

    # Diagnostics
    active_caps: list[Layer3Cap]
    hard_fail_reasons: list[Layer3HardFail]
    remediation_paths: list[Layer3RemediationPath]
    layer4_routing_hints: list[str]

    # Confidence
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_label: str
    missing_data: list[str]
    plain_english_summary: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _w_sum(weights: dict[str, float], values: dict[str, float]) -> float:
    return _CLAMP(sum(weights[k] * values.get(k, _NEUTRAL) for k in weights))


# ---------------------------------------------------------------------------
# 3A — Affordability
# ---------------------------------------------------------------------------

_BAND_SCORE: dict[AffordabilityBand, float] = {
    AffordabilityBand.NO_PENALTY:     0.90,
    AffordabilityBand.MILD_PENALTY:   0.65,
    AffordabilityBand.SEVERE_PENALTY: 0.35,
    AffordabilityBand.HARD_FAIL:      0.0,
}

_BAND_REMEDIATION: dict[AffordabilityBand, Layer3RemediationPath] = {
    AffordabilityBand.MILD_PENALTY: Layer3RemediationPath(
        issue="Mild balance sheet stretch",
        remediation="Explore stock component or partnership financing",
        likely_deal_structure="mixed_cash_stock",
        feasibility=0.80,
    ),
    AffordabilityBand.SEVERE_PENALTY: Layer3RemediationPath(
        issue="Severely stretched affordability",
        remediation="Asset license, option deal, co-development, or partner financing",
        likely_deal_structure="option_or_license",
        feasibility=0.55,
    ),
    AffordabilityBand.HARD_FAIL: Layer3RemediationPath(
        issue="Acquisition cost exceeds realistic buyer capacity",
        remediation="License, option-to-acquire, co-development, or wait for acquirer firepower refresh",
        likely_deal_structure="license_or_option",
        feasibility=0.35,
    ),
}


def _score_affordability(
    aff: Optional[AffordabilityResult],
    *,
    acquirer_credit_stress_high: bool = False,
    deal_requires_large_debt: bool = False,
    target_requires_cash_deal: bool = False,
    buyer_cash_insufficient: bool = False,
) -> tuple[Layer3AffordabilityOutput, list[Layer3Cap], list[Layer3HardFail], list[Layer3RemediationPath]]:
    caps: list[Layer3Cap] = []
    fails: list[Layer3HardFail] = []
    remediations: list[Layer3RemediationPath] = []

    if aff is None:
        return (
            Layer3AffordabilityOutput(
                score=_NEUTRAL, confidence=0.30, treatment="unknown",
                missing_data=["affordability_result_not_provided"],
            ),
            caps, fails, remediations,
        )

    band = aff.band
    ratio = aff.affordability_ratio
    score = _BAND_SCORE.get(band, _NEUTRAL)
    confidence = 0.80 if ratio < float("inf") else 0.30

    if band == AffordabilityBand.HARD_FAIL:
        fails.append(Layer3HardFail(
            name="affordability_hard_fail",
            reason=f"Affordability ratio {ratio:.2f} > 1.10: acquisition cost exceeds buyer capacity",
            triggered_by="3A_affordability",
            remediation_possible=True,
            layer4_routing_hint="consider_asset_license_or_option_deal",
        ))
        remediations.append(_BAND_REMEDIATION[AffordabilityBand.HARD_FAIL])
    elif band == AffordabilityBand.SEVERE_PENALTY:
        caps.append(Layer3Cap(
            name="affordability_severe_cap",
            cap_value=0.60,
            reason=f"Affordability ratio {ratio:.2f} between 0.85–1.10: stretched balance sheet",
            triggered_by="3A_affordability",
            severity="severe",
        ))
        remediations.append(_BAND_REMEDIATION[AffordabilityBand.SEVERE_PENALTY])
    elif band == AffordabilityBand.MILD_PENALTY:
        caps.append(Layer3Cap(
            name="affordability_mild_cap",
            cap_value=0.80,
            reason=f"Affordability ratio {ratio:.2f}: mild balance sheet stretch",
            triggered_by="3A_affordability",
            severity="mild",
        ))
        remediations.append(_BAND_REMEDIATION[AffordabilityBand.MILD_PENALTY])

    # Secondary 3A triggers (pair-level, independent of ratio band)
    if acquirer_credit_stress_high and deal_requires_large_debt:
        caps.append(Layer3Cap(
            name="credit_stress_large_debt_cap",
            cap_value=0.55,
            reason="Acquirer has credit stress and the transaction requires substantial debt financing.",
            triggered_by="3A_affordability",
            severity="severe",
        ))
        remediations.append(Layer3RemediationPath(
            issue="Credit stress + large debt requirement",
            remediation="Explore equity-only structure, partner financing, or smaller tranche",
            likely_deal_structure="equity_or_partner_financed",
            feasibility=0.45,
        ))

    if target_requires_cash_deal and buyer_cash_insufficient:
        caps.append(Layer3Cap(
            name="cash_required_buyer_insufficient_cap",
            cap_value=0.50,
            reason="Target requires cash certainty but buyer does not have sufficient cash capacity.",
            triggered_by="3A_affordability",
            severity="severe",
        ))
        remediations.append(Layer3RemediationPath(
            issue="Cash deal required; buyer cash insufficient",
            remediation="Arrange bridge financing, committed backstop, or restructure as contingent payment",
            likely_deal_structure="bridge_or_contingent",
            feasibility=0.40,
        ))

    pos = [f"ratio={ratio:.2f}: within capacity"] if band == AffordabilityBand.NO_PENALTY else []
    neg = [f"ratio={ratio:.2f}: stretches buyer capacity"] if band in (
        AffordabilityBand.SEVERE_PENALTY, AffordabilityBand.HARD_FAIL
    ) else []

    return (
        Layer3AffordabilityOutput(
            score=round(score, 4),
            confidence=confidence,
            affordability_ratio=round(ratio, 4) if ratio < float("inf") else None,
            treatment=band.value,
            expected_acquisition_cost_millions=aff.expected_acquisition_cost_millions,
            deal_capacity_millions=aff.deal_capacity_millions,
            positive_drivers=pos,
            negative_drivers=neg,
        ),
        caps, fails, remediations,
    )


# ---------------------------------------------------------------------------
# 3B — Consideration Realism
# ---------------------------------------------------------------------------

def _score_consideration(
    inp: ConsiderationRealismInputs,
) -> tuple[Layer3ConsiderationOutput, list[Layer3Cap], list[Layer3HardFail], list[Layer3RemediationPath]]:
    caps: list[Layer3Cap] = []
    fails: list[Layer3HardFail] = []
    remediations: list[Layer3RemediationPath] = []

    # cash_stock_mix_feasibility: penalized when target needs cash but stock quality is low
    mix_feasibility = inp.acquirer_stock_quality
    if inp.target_requires_cash_certainty and inp.acquirer_stock_quality < 0.50:
        mix_feasibility = inp.acquirer_stock_quality * 0.60
        caps.append(Layer3Cap(
            name="consideration_cash_certainty_cap",
            cap_value=0.65,
            reason="Target requires cash certainty; acquirer stock quality is low",
            triggered_by="3B_consideration",
            severity="meaningful",
        ))
        remediations.append(Layer3RemediationPath(
            issue="Target needs cash certainty but acquirer stock is weak",
            remediation="Require majority-cash structure or bridge financing commitment",
            likely_deal_structure="cash_dominant",
            feasibility=0.55,
        ))

    # Low acquirer stock quality for stock-heavy deals
    if inp.acquirer_stock_quality < 0.40:
        caps.append(Layer3Cap(
            name="consideration_stock_quality_cap",
            cap_value=0.65,
            reason="Acquirer stock quality < 0.40: stock consideration unlikely to be accepted",
            triggered_by="3B_consideration",
            severity="meaningful",
        ))

    # CVR/milestone structure needed but definition unclear
    if inp.cvr_needed_but_milestone_definition_unclear:
        caps.append(Layer3Cap(
            name="unclear_cvr_milestone_cap",
            cap_value=0.70,
            reason="CVR or milestone structure appears needed, but milestone definition is unclear.",
            triggered_by="3B_consideration",
            severity="meaningful",
        ))
        remediations.append(Layer3RemediationPath(
            issue="CVR/milestone structure needed; milestone definition unclear",
            remediation="Define clear, objective, measurable milestone triggers before signing",
            likely_deal_structure="cvr_milestone",
            feasibility=0.60,
        ))

    raw = _w_sum(_CONSIDERATION_WEIGHTS, {
        "cash_stock_mix_feasibility":          mix_feasibility,
        "target_shareholder_acceptability":    inp.target_shareholder_acceptability,
        "acquirer_shareholder_acceptability":  inp.acquirer_shareholder_acceptability,
        "cvr_milestone_suitability":           inp.cvr_suitability,
        "tax_efficiency":                      inp.tax_efficiency,
        "precedent_consistency":               inp.precedent_consistency,
    })

    # Determine likely deal structure
    if inp.cvr_suitability > 0.70:
        mix = "cvr_milestone"
    elif inp.acquirer_stock_quality > 0.70 and not inp.target_requires_cash_certainty:
        mix = "mixed_cash_stock"
    elif inp.target_requires_cash_certainty or inp.acquirer_stock_quality < 0.40:
        mix = "cash_dominant"
    else:
        mix = "mixed"

    pos = []
    neg = []
    if inp.acquirer_stock_quality >= 0.70:
        pos.append(f"strong acquirer stock quality ({inp.acquirer_stock_quality:.2f})")
    if inp.cvr_suitability >= 0.70:
        pos.append("CVR/milestone structure suitable for binary asset")
    if inp.acquirer_stock_quality < 0.40:
        neg.append(f"weak acquirer stock currency ({inp.acquirer_stock_quality:.2f})")
    if inp.target_requires_cash_certainty:
        neg.append("target requires cash certainty")

    return (
        Layer3ConsiderationOutput(
            score=round(raw, 4),
            confidence=inp.data_confidence,
            likely_consideration_mix=mix,
            cvr_suitability=inp.cvr_suitability,
            positive_drivers=pos,
            negative_drivers=neg,
        ),
        caps, fails, remediations,
    )


# ---------------------------------------------------------------------------
# 3C — Rights / Control Fit
# ---------------------------------------------------------------------------

def _score_rights_control(
    rc: Optional[PairAssetControlResult],
) -> tuple[Layer3RightsControlOutput, list[Layer3Cap], list[Layer3HardFail], list[Layer3RemediationPath]]:
    caps: list[Layer3Cap] = []
    fails: list[Layer3HardFail] = []
    remediations: list[Layer3RemediationPath] = []

    if rc is None:
        return (
            Layer3RightsControlOutput(
                score=_NEUTRAL, confidence=0.30,
                missing_data=["pair_asset_control_not_provided"],
            ),
            caps, fails, remediations,
        )

    score = rc.pair_asset_control_score
    pos: list[str] = []
    neg: list[str] = []

    if rc.pair_level_fail:
        fails.append(Layer3HardFail(
            name="rights_control_pair_fail",
            reason=f"Pair-level asset control fail (ROFR/rights: {rc.rofr_impact})",
            triggered_by="3C_rights_control",
            remediation_possible=True,
            layer4_routing_hint="consider_license_or_wait_for_rofr_expiry",
        ))
        remediations.append(Layer3RemediationPath(
            issue="ROFR or consent blocks this buyer",
            remediation="Partner waiver, regional license, or option-to-acquire",
            likely_deal_structure="license_or_option",
            feasibility=0.40,
        ))
    elif rc.pair_cap is not None:
        caps.append(Layer3Cap(
            name="rights_control_cap",
            cap_value=rc.pair_cap,
            reason=f"Rights/encumbrance pair cap: rofr={rc.rofr_impact}, "
                   f"mfg_adj={rc.manufacturing_adjustment_applied}",
            triggered_by="3C_rights_control",
            severity="severe" if rc.pair_cap <= 0.55 else "meaningful",
        ))
        if rc.rofr_impact == "blocking":
            remediations.append(Layer3RemediationPath(
                issue="ROFR blocks non-partner acquirer",
                remediation="Negotiate partner waiver or await ROFR expiry",
                likely_deal_structure="option_or_wait",
                feasibility=0.45,
            ))

    if rc.existing_partner_match:
        pos.append("acquirer is existing partner: ROFR/consent waived")
    elif rc.rofr_impact == "none":
        pos.append("no ROFR blocking")
    if rc.rofr_impact == "blocking":
        neg.append("ROFR blocks this acquirer")
    if rc.manufacturing_mismatch_flag:
        neg.append(f"manufacturing mismatch ({rc.manufacturing_adjustment_applied})")

    return (
        Layer3RightsControlOutput(
            score=round(score, 4),
            confidence=0.75 if rc is not None else 0.30,
            rofr_impact=rc.rofr_impact,
            regional_rights_fit=rc.regional_rights_fit,
            existing_partner_status=rc.existing_partner_match,
            positive_drivers=pos,
            negative_drivers=neg,
        ),
        caps, fails, remediations,
    )


# ---------------------------------------------------------------------------
# 3D — Integration Capability
# ---------------------------------------------------------------------------

_INTEGRATION_TREATMENT: list[tuple[float, str]] = [
    (0.15, "no_penalty"),
    (0.30, "mild"),
    (0.50, "meaningful"),
    (0.70, "severe"),
]


def _score_integration(
    integ: Optional[PairIntegrationAdjustment],
) -> tuple[Layer3IntegrationOutput, list[Layer3Cap], list[Layer3HardFail], list[Layer3RemediationPath]]:
    caps: list[Layer3Cap] = []
    fails: list[Layer3HardFail] = []
    remediations: list[Layer3RemediationPath] = []

    if integ is None:
        return (
            Layer3IntegrationOutput(
                score=_NEUTRAL, confidence=0.30, treatment="unknown",
                missing_data=["integration_adjustment_not_provided"],
            ),
            caps, fails, remediations,
        )

    capability = integ.buyer_integration_capability
    penalty = integ.adjusted_integration_penalty
    score = _CLAMP(1.0 - penalty)

    # Derive treatment
    treatment = "fatal"
    for upper, label in _INTEGRATION_TREATMENT:
        if penalty <= upper:
            treatment = label
            break

    if integ.pair_level_fail:
        fails.append(Layer3HardFail(
            name="integration_pair_fail",
            reason=f"Integration penalty {penalty:.2f}: buyer capability {capability:.2f} too low",
            triggered_by="3D_integration",
            remediation_possible=True,
            layer4_routing_hint="consider_cdmo_partnership_or_co_development",
        ))
        remediations.append(Layer3RemediationPath(
            issue="Severe integration mismatch",
            remediation="CDMO/CMO partner, co-develop, or license only",
            likely_deal_structure="license_or_partnership",
            feasibility=0.35,
        ))
    elif integ.max_score_cap is not None:
        caps.append(Layer3Cap(
            name="integration_capability_cap",
            cap_value=integ.max_score_cap,
            reason=f"Integration penalty={penalty:.2f}, capability={capability:.2f}",
            triggered_by="3D_integration",
            severity="severe" if integ.max_score_cap <= 0.55 else "meaningful",
        ))
        if treatment in ("severe", "meaningful"):
            remediations.append(Layer3RemediationPath(
                issue=f"Integration complexity high (penalty={penalty:.2f})",
                remediation="Co-promote arrangement or CDMO manufacturing partner",
                likely_deal_structure="co_promote_or_service_agreement",
                feasibility=0.55,
            ))

    pos = []
    neg = []
    if penalty <= 0.15:
        pos.append(f"strong integration fit (penalty={penalty:.2f})")
    if penalty > 0.50:
        neg.append(f"high integration penalty ({penalty:.2f}), capability={capability:.2f}")

    return (
        Layer3IntegrationOutput(
            score=round(score, 4),
            confidence=0.75,
            buyer_integration_capability=round(capability, 4),
            raw_integration_complexity_score=round(integ.raw_integration_complexity_score, 4),
            adjusted_integration_penalty=round(penalty, 4),
            treatment=treatment,
            positive_drivers=pos,
            negative_drivers=neg,
        ),
        caps, fails, remediations,
    )


# ---------------------------------------------------------------------------
# 3E — Antitrust Feasibility
# ---------------------------------------------------------------------------

def _score_antitrust(
    inp: AntitrustInputs,
) -> tuple[Layer3AntitrustOutput, list[Layer3Cap], list[Layer3HardFail], list[Layer3RemediationPath]]:
    caps: list[Layer3Cap] = []
    fails: list[Layer3HardFail] = []
    remediations: list[Layer3RemediationPath] = []

    risk = _w_sum(_ANTITRUST_WEIGHTS, {
        "current_product_overlap":      inp.current_product_overlap,
        "pipeline_overlap":             inp.pipeline_overlap,
        "market_concentration":         inp.market_concentration,
        "innovation_competition_risk":  inp.innovation_competition_risk,
        "divestiture_complexity":       inp.divestiture_complexity,
        "jurisdictional_complexity":    inp.jurisdictional_complexity,
    })
    feasibility = _CLAMP(1.0 - risk)

    if inp.required_divestiture_removes_core_value:
        fails.append(Layer3HardFail(
            name="antitrust_divestiture_destroys_deal",
            reason="Required divestiture removes core deal value: deal is economically not viable",
            triggered_by="3E_antitrust",
            remediation_possible=False,
            layer4_routing_hint="pair_not_executable_antitrust",
        ))
    elif risk > 0.80:
        fails.append(Layer3HardFail(
            name="antitrust_hard_fail",
            reason=f"Antitrust risk {risk:.2f} > 0.80: deal likely to be challenged or blocked",
            triggered_by="3E_antitrust",
            remediation_possible=True,
            layer4_routing_hint="consider_divestiture_or_restructure",
        ))
        remediations.append(Layer3RemediationPath(
            issue=f"Antitrust risk too high ({risk:.2f})",
            remediation="Divest overlapping product or restructure as licensing deal",
            likely_deal_structure="license_or_partial",
            feasibility=0.30,
        ))
    elif risk > 0.60:
        caps.append(Layer3Cap(
            name="antitrust_severe_cap",
            cap_value=0.45,
            reason=f"Antitrust risk {risk:.2f} > 0.60: material regulatory challenge",
            triggered_by="3E_antitrust",
            severity="severe",
        ))
        remediations.append(Layer3RemediationPath(
            issue="Material antitrust risk",
            remediation="Pre-clear with DOJ/FTC; consider asset divestitures",
            feasibility=0.50,
        ))
    elif risk > 0.40:
        caps.append(Layer3Cap(
            name="antitrust_meaningful_cap",
            cap_value=0.65,
            reason=f"Antitrust risk {risk:.2f}: material diligence issue",
            triggered_by="3E_antitrust",
            severity="meaningful",
        ))
    elif risk > 0.20:
        caps.append(Layer3Cap(
            name="antitrust_manageable_cap",
            cap_value=0.80,
            reason=f"Antitrust risk {risk:.2f}: manageable but warrants diligence",
            triggered_by="3E_antitrust",
            severity="mild",
        ))

    pos = []
    neg = []
    if risk <= 0.20:
        pos.append(f"low antitrust risk ({risk:.2f})")
    if risk > 0.40:
        neg.append(f"elevated antitrust risk ({risk:.2f}): overlap={inp.current_product_overlap:.2f}")

    return (
        Layer3AntitrustOutput(
            score=round(feasibility, 4),
            confidence=inp.data_confidence,
            antitrust_risk=round(risk, 4),
            current_product_overlap=inp.current_product_overlap,
            pipeline_overlap=inp.pipeline_overlap,
            jurisdiction_risk=inp.jurisdictional_complexity,
            positive_drivers=pos,
            negative_drivers=neg,
        ),
        caps, fails, remediations,
    )


# ---------------------------------------------------------------------------
# 3F — Strategic Conflict
# ---------------------------------------------------------------------------

def _score_strategic_conflict(
    inp: StrategicConflictInputs,
) -> tuple[Layer3StrategicConflictOutput, list[Layer3Cap], list[Layer3HardFail], list[Layer3RemediationPath]]:
    caps: list[Layer3Cap] = []
    fails: list[Layer3HardFail] = []
    remediations: list[Layer3RemediationPath] = []

    risk = _w_sum(_CONFLICT_WEIGHTS, {
        "product_cannibalization":       inp.product_cannibalization,
        "pipeline_cannibalization":      inp.pipeline_cannibalization,
        "channel_conflict":              inp.channel_conflict,
        "partner_conflict":              inp.partner_conflict,
        "pricing_contracting_conflict":  inp.pricing_contracting_conflict,
        "organizational_conflict":       inp.organizational_conflict,
    })
    feasibility = _CLAMP(1.0 - risk)

    # Boolean cap triggers
    if inp.directly_cannibalizes_core_franchise:
        caps.append(Layer3Cap(
            name="strategic_conflict_cannibalization_cap",
            cap_value=0.55,
            reason="Target directly cannibalizes buyer core franchise without replacement logic",
            triggered_by="3F_strategic_conflict",
            severity="severe",
        ))
        remediations.append(Layer3RemediationPath(
            issue="Core franchise cannibalization",
            remediation="Define replacement product plan or franchise transition rationale",
            feasibility=0.40,
        ))
    if inp.has_exclusive_partnership_conflict:
        caps.append(Layer3Cap(
            name="strategic_conflict_exclusive_partnership_cap",
            cap_value=0.50,
            reason="Buyer has exclusive partnership that conflicts with this acquisition",
            triggered_by="3F_strategic_conflict",
            severity="severe",
        ))
    if inp.requires_killing_high_priority_internal_program:
        caps.append(Layer3Cap(
            name="strategic_conflict_internal_program_cap",
            cap_value=0.60,
            reason="Deal requires killing buyer's high-priority internal program",
            triggered_by="3F_strategic_conflict",
            severity="meaningful",
        ))

    # Continuous risk caps
    if not inp.directly_cannibalizes_core_franchise and risk > 0.50:
        caps.append(Layer3Cap(
            name="strategic_conflict_risk_cap",
            cap_value=0.65,
            reason=f"High strategic conflict risk ({risk:.2f})",
            triggered_by="3F_strategic_conflict",
            severity="meaningful",
        ))

    pos = []
    neg = []
    if risk <= 0.15:
        pos.append("low strategic conflict risk")
    if inp.directly_cannibalizes_core_franchise:
        neg.append("directly cannibalizes core franchise")
    if inp.has_exclusive_partnership_conflict:
        neg.append("exclusive partnership conflict")
    if risk > 0.40:
        neg.append(f"elevated conflict risk ({risk:.2f})")

    return (
        Layer3StrategicConflictOutput(
            score=round(feasibility, 4),
            confidence=inp.data_confidence,
            conflict_risk=round(risk, 4),
            cannibalization_risk=round(
                inp.product_cannibalization * 0.30 + inp.pipeline_cannibalization * 0.20, 4
            ),
            partner_conflict=inp.partner_conflict,
            positive_drivers=pos,
            negative_drivers=neg,
        ),
        caps, fails, remediations,
    )


# ---------------------------------------------------------------------------
# 3G — Process / Closing Feasibility
# ---------------------------------------------------------------------------

def _score_process_closing(
    inp: ProcessClosingInputs,
) -> tuple[Layer3ProcessClosingOutput, list[Layer3Cap], list[Layer3HardFail], list[Layer3RemediationPath]]:
    caps: list[Layer3Cap] = []
    fails: list[Layer3HardFail] = []
    remediations: list[Layer3RemediationPath] = []

    raw = _w_sum(_PROCESS_WEIGHTS, {
        "target_board_alignment":              inp.target_board_alignment,
        "shareholder_approval_likelihood":     inp.shareholder_approval_likelihood,
        "management_retention_feasibility":    inp.management_retention_feasibility,
        "financing_process_readiness":         inp.financing_process_readiness,
        "diligence_package_readiness":         inp.diligence_package_readiness,
        "cross_border_execution_feasibility":  inp.cross_border_execution_feasibility,
        "timeline_feasibility":                inp.timeline_feasibility,
        "litigation_risk_inverse":             1.0 - inp.litigation_risk,
    })

    # Boolean cap triggers
    if inp.shareholder_approval_unlikely:
        caps.append(Layer3Cap(
            name="process_shareholder_approval_cap",
            cap_value=0.55,
            reason="Shareholder approval considered unlikely",
            triggered_by="3G_process_closing",
            severity="severe",
        ))
    if inp.founder_controlled_and_unwilling:
        caps.append(Layer3Cap(
            name="process_founder_control_cap",
            cap_value=0.50,
            reason="Founder-controlled company; founder not willing to sell",
            triggered_by="3G_process_closing",
            severity="severe",
        ))
    if inp.unresolved_litigation_blocks_close:
        caps.append(Layer3Cap(
            name="process_litigation_cap",
            cap_value=0.45,
            reason="Unresolved litigation would block deal close",
            triggered_by="3G_process_closing",
            severity="severe",
        ))
        remediations.append(Layer3RemediationPath(
            issue="Unresolved litigation blocks close",
            remediation="Litigation resolution milestone, escrow, or indemnification",
            likely_deal_structure="cvr_or_escrow",
            feasibility=0.45,
        ))
    if inp.management_retention_required_and_unlikely:
        caps.append(Layer3Cap(
            name="process_management_retention_cap",
            cap_value=0.65,
            reason="Key management retention required but unlikely",
            triggered_by="3G_process_closing",
            severity="meaningful",
        ))

    pos = []
    neg = []
    if inp.target_board_alignment >= 0.70:
        pos.append("strong board alignment")
    if inp.shareholder_approval_unlikely:
        neg.append("shareholder approval unlikely")
    if inp.founder_controlled_and_unwilling:
        neg.append("founder control / unwilling seller")
    if inp.unresolved_litigation_blocks_close:
        neg.append("unresolved litigation blocks close")

    return (
        Layer3ProcessClosingOutput(
            score=round(raw, 4),
            confidence=inp.data_confidence,
            governance_risk=round(1.0 - inp.target_board_alignment, 4),
            shareholder_approval_risk=round(1.0 - inp.shareholder_approval_likelihood, 4),
            closing_timeline_risk=round(1.0 - inp.timeline_feasibility, 4),
            positive_drivers=pos,
            negative_drivers=neg,
        ),
        caps, fails, remediations,
    )


# ---------------------------------------------------------------------------
# 3H — Diligence Blockers
# ---------------------------------------------------------------------------

# (flag_name, severity, cap_value_or_None, remediation)
_DILIGENCE_BLOCKER_RULES: list[tuple[str, str, Optional[float], str]] = [
    ("ip_ownership_uncertainty",    "major",    0.50, "independent IP chain-of-title review"),
    ("undisclosed_royalty_stack",   "major",    0.50, "full royalty stack disclosure and legal review"),
    ("unfavorable_coc_clause",      "major",    0.55, "CoC clause renegotiation or waiver"),
    ("trial_data_integrity_issue",  "fatal",    None, "independent data audit before proceeding"),
    ("cmc_package_incomplete",      "moderate", 0.65, "CMC package completion milestone in deal"),
    ("gmp_inspection_issue",        "moderate", 0.65, "GMP remediation plan with timeline"),
    ("supply_dependency_severe",    "major",    0.55, "CDM0 backup supplier agreement"),
    ("material_litigation",         "major",    0.55, "litigation outcome assessment and escrow"),
    ("compliance_fcpa_issue",       "fatal",    None, "full FCPA compliance review; do not proceed until resolved"),
    ("sanctions_export_control",    "fatal",    None, "sanctions/export counsel review required"),
    ("key_employee_retention_risk", "moderate", 0.70, "retention package and stay agreements"),
]


def _evaluate_diligence_blockers(
    flags: DiligenceFlagInputs,
) -> tuple[list[Layer3Blocker], list[Layer3Cap], list[Layer3HardFail], list[Layer3RemediationPath]]:
    blockers: list[Layer3Blocker] = []
    caps: list[Layer3Cap] = []
    fails: list[Layer3HardFail] = []
    remediations: list[Layer3RemediationPath] = []

    for flag_name, severity, cap_val, remediation in _DILIGENCE_BLOCKER_RULES:
        if not getattr(flags, flag_name, False):
            continue

        cap_or_fail = None
        if severity == "fatal":
            fails.append(Layer3HardFail(
                name=f"diligence_{flag_name}",
                reason=f"Fatal diligence blocker: {flag_name.replace('_', ' ')}",
                triggered_by="3H_diligence",
                remediation_possible=True,
                layer4_routing_hint="halt_diligence_until_resolved",
            ))
            cap_or_fail = "hard_fail"
        elif severity == "major" and cap_val is not None:
            caps.append(Layer3Cap(
                name=f"diligence_{flag_name}_cap",
                cap_value=cap_val,
                reason=f"Major diligence blocker: {flag_name.replace('_', ' ')}",
                triggered_by="3H_diligence",
                severity="severe",
            ))
            cap_or_fail = f"cap_{cap_val}"
        elif severity == "moderate" and cap_val is not None:
            caps.append(Layer3Cap(
                name=f"diligence_{flag_name}_cap",
                cap_value=cap_val,
                reason=f"Moderate diligence blocker: {flag_name.replace('_', ' ')}",
                triggered_by="3H_diligence",
                severity="meaningful",
            ))
            cap_or_fail = f"cap_{cap_val}"

        blockers.append(Layer3Blocker(
            blocker_name=flag_name,
            severity=severity,
            confidence=0.70,
            source="diligence_flags",
            owning_layer="Layer 3",
            remediation_path=remediation,
            cap_or_fail=cap_or_fail,
        ))
        if severity in ("fatal", "major"):
            remediations.append(Layer3RemediationPath(
                issue=flag_name.replace("_", " ").capitalize(),
                remediation=remediation,
                feasibility=0.30 if severity == "fatal" else 0.50,
            ))

    return blockers, caps, fails, remediations


# ---------------------------------------------------------------------------
# Confidence system
# ---------------------------------------------------------------------------

def _confidence_label(score: float) -> str:
    if score >= 0.80:
        return "High"
    if score >= 0.60:
        return "Medium"
    if score >= 0.40:
        return "Low"
    return "Very Low"


def _compute_overall_confidence(components: dict[str, float]) -> float:
    return round(_CLAMP(
        sum(_CONFIDENCE_WEIGHTS[k] * components.get(k, 0.50) for k in _CONFIDENCE_WEIGHTS)
    ), 4)


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------

def _build_summary(
    target_id: str,
    acquirer_id: str,
    upstream: float,
    hard_fail: bool,
    fails: list[Layer3HardFail],
    adjusted: float,
    pair_cap: float,
    multiplier: float,
    pair_score: float,
    caps: list[Layer3Cap],
) -> str:
    if hard_fail:
        reasons = "; ".join(f.reason for f in fails[:2])
        return (
            f"HARD FAIL — Pair {acquirer_id}↔{target_id} is not executable. "
            f"Adjusted score: 0.0 (was L2={upstream:.2f}). Reason(s): {reasons}."
        )
    parts = [
        f"Layer 2 score: {upstream:.2f}",
        f"L3 multiplier: {multiplier:.2f}",
    ]
    if pair_cap < 1.0:
        parts.append(f"pair cap: {pair_cap:.2f}")
    parts.append(f"adjusted BD score: {adjusted:.2f}")
    if caps:
        binding = min(caps, key=lambda c: c.cap_value)
        parts.append(f"binding constraint: {binding.name} ({binding.cap_value:.2f})")
    if adjusted >= 0.70:
        verdict = "Pair looks executable. Proceed to Layer 4 routing."
    elif adjusted >= 0.50:
        verdict = "Pair has meaningful constraints. Address blockers before outreach."
    else:
        verdict = "Pair has severe constraints. Layer 4 should review deal structure alternatives."
    return f"{' | '.join(parts)}. {verdict}"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_layer3_pair_realism(inputs: PairRealismInputs) -> PairRealismOutput:
    """Layer 3 Pair-Specific Deal Realism Engine.

    Evaluates a single acquirer-target pair across 7 execution dimensions,
    applies caps and hard fails, and returns an adjusted BD score.

    This module consumes the Layer 2 BD Action Score and pair-specific inputs;
    it does NOT re-score target attractiveness (Layer 1) or strategic fit
    (Layer 2).

    Args:
        inputs: PairRealismInputs with upstream L2 score + all pair signals.

    Returns:
        PairRealismOutput with adjusted_bd_score and full diagnostics.
    """
    all_caps: list[Layer3Cap] = []
    all_fails: list[Layer3HardFail] = []
    all_remediations: list[Layer3RemediationPath] = []
    all_missing: list[str] = []

    # ── Score each component ───────────────────────────────────────────────
    aff_out, c, f, r = _score_affordability(
        inputs.affordability,
        acquirer_credit_stress_high=inputs.acquirer_credit_stress_high,
        deal_requires_large_debt=inputs.deal_requires_large_debt,
        target_requires_cash_deal=inputs.target_requires_cash_deal,
        buyer_cash_insufficient=inputs.buyer_cash_insufficient,
    )
    all_caps += c
    all_fails += f
    all_remediations += r

    con_out, c, f, r = _score_consideration(inputs.consideration)
    all_caps += c
    all_fails += f
    all_remediations += r

    rc_out, c, f, r = _score_rights_control(inputs.rights_control)
    all_caps += c
    all_fails += f
    all_remediations += r

    int_out, c, f, r = _score_integration(inputs.integration)
    all_caps += c
    all_fails += f
    all_remediations += r

    ant_out, c, f, r = _score_antitrust(inputs.antitrust)
    all_caps += c
    all_fails += f
    all_remediations += r

    sc_out, c, f, r = _score_strategic_conflict(inputs.strategic_conflict)
    all_caps += c
    all_fails += f
    all_remediations += r

    pc_out, c, f, r = _score_process_closing(inputs.process_closing)
    all_caps += c
    all_fails += f
    all_remediations += r

    # ── Diligence blockers ─────────────────────────────────────────────────
    blockers, c, f, r = _evaluate_diligence_blockers(inputs.diligence_flags)
    all_caps += c
    all_fails += f
    all_remediations += r

    # ── Pair feasibility score (diagnostic weighted sum) ──────────────────
    pair_score = _CLAMP(
        L3_WEIGHTS["affordability"]          * aff_out.score
        + L3_WEIGHTS["consideration_realism"]  * con_out.score
        + L3_WEIGHTS["rights_control_fit"]     * rc_out.score
        + L3_WEIGHTS["integration_capability"] * int_out.score
        + L3_WEIGHTS["antitrust_feasibility"]  * ant_out.score
        + L3_WEIGHTS["strategic_conflict"]     * sc_out.score
        + L3_WEIGHTS["process_closing"]        * pc_out.score
    )

    # ── Hard fail check ────────────────────────────────────────────────────
    hard_fail = bool(all_fails)

    # ── Pair level cap (most restrictive) ─────────────────────────────────
    cap_values = [c.cap_value for c in all_caps]
    pair_level_cap = round(min(cap_values), 4) if cap_values else 1.0

    # ── Pair feasibility multiplier — derived from pair_feasibility_score tier table ──
    # Spec: ≥0.85 → ×1.00, 0.70–0.84 → ×0.90, 0.55–0.69 → ×0.75,
    #        0.40–0.54 → ×0.55, <0.40 → ×0.40; hard fail → ×0.00
    if hard_fail:
        pair_feasibility_multiplier = 0.0
    elif pair_score >= 0.85:
        pair_feasibility_multiplier = 1.00
    elif pair_score >= 0.70:
        pair_feasibility_multiplier = 0.90
    elif pair_score >= 0.55:
        pair_feasibility_multiplier = 0.75
    elif pair_score >= 0.40:
        pair_feasibility_multiplier = 0.55
    else:
        pair_feasibility_multiplier = 0.40

    # ── Adjusted BD score ─────────────────────────────────────────────────
    if hard_fail:
        adjusted_bd_score = 0.0
    else:
        adjusted_bd_score = round(
            _CLAMP(min(
                inputs.upstream_layer2_score * pair_feasibility_multiplier,
                pair_level_cap,
            )),
            4,
        )

    # ── Confidence ────────────────────────────────────────────────────────
    confidence = _compute_overall_confidence({
        "affordability":          aff_out.confidence,
        "consideration_realism":  con_out.confidence,
        "rights_control_fit":     rc_out.confidence,
        "integration_capability": int_out.confidence,
        "antitrust_feasibility":  ant_out.confidence,
        "strategic_conflict":     sc_out.confidence,
        "process_closing":        pc_out.confidence,
    })

    # ── Missing data ───────────────────────────────────────────────────────
    all_missing += [d for out in (aff_out, con_out, rc_out, int_out, ant_out, sc_out, pc_out)
                    for d in out.missing_data]

    # ── Layer 4 routing hints ──────────────────────────────────────────────
    routing_hints: list[str] = []
    for fail in all_fails:
        if fail.layer4_routing_hint:
            routing_hints.append(fail.layer4_routing_hint)
    if adjusted_bd_score >= 0.65 and not hard_fail:
        routing_hints.append("proceed_to_layer4_deal_structure_routing")
    elif adjusted_bd_score >= 0.40 and not hard_fail:
        routing_hints.append("layer4_review_alternative_structures")

    # ── Summary ───────────────────────────────────────────────────────────
    summary = _build_summary(
        target_id=inputs.target_id,
        acquirer_id=inputs.acquirer_id,
        upstream=inputs.upstream_layer2_score,
        hard_fail=hard_fail,
        fails=all_fails,
        adjusted=adjusted_bd_score,
        pair_cap=pair_level_cap,
        multiplier=pair_feasibility_multiplier,
        pair_score=pair_score,
        caps=all_caps,
    )

    return PairRealismOutput(
        target_id=inputs.target_id,
        acquirer_id=inputs.acquirer_id,
        upstream_layer2_score=inputs.upstream_layer2_score,
        affordability=aff_out,
        consideration_realism=con_out,
        rights_control_fit=rc_out,
        integration_capability=int_out,
        antitrust_feasibility=ant_out,
        strategic_conflict=sc_out,
        process_closing_feasibility=pc_out,
        diligence_blockers=blockers,
        pair_feasibility_score=round(pair_score, 4),
        pair_feasibility_multiplier=pair_feasibility_multiplier,
        pair_level_cap=pair_level_cap,
        hard_fail=hard_fail,
        adjusted_bd_score=adjusted_bd_score,
        active_caps=all_caps,
        hard_fail_reasons=all_fails,
        remediation_paths=all_remediations,
        layer4_routing_hints=list(dict.fromkeys(routing_hints)),  # dedup
        confidence=confidence,
        confidence_label=_confidence_label(confidence),
        missing_data=list(dict.fromkeys(all_missing)),
        plain_english_summary=summary,
    )
