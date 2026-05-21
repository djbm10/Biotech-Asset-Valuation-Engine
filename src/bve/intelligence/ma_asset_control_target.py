"""
0D-T — Target-Level Asset-Control / Encumbrance Profile.

Answers: "Is this target's asset clean enough for ANY acquirer to control it?"

Records objective facts about rights, economics, IP, manufacturing readiness,
and diligence completeness.  Does NOT know the buyer identity.

Pair-specific signals that do NOT belong here:
  - acquirer_is_existing_partner  → Layer 3B partner waiver
  - acquirer_manufacturing_fit    → Layer 3B manufacturing mismatch penalty
  - blocking_consent_right        → Layer 3B pair-level cap
  - ROFR/opt-in blocking THIS acquirer → Layer 3B

Compared to the legacy 0D (ma_asset_control.py):
  Bucket 3 renamed: partner_freedom → partner_encumbrance_facts
    Removed pair sub-signals: no_rofr_or_opt_in, no_consent_requirement,
    no_exclusivity_conflict (all move to Layer 3B).
    Kept:  no_blocking_rights, clean_governance_control.
    Added: partner_encumbrance_severity (overall target-level encumbrance weight).
  Bucket 5 renamed: manufacturing_control → manufacturing_readiness
    Removed: acquirer_manufacturing_fit (moves to Layer 3B).
    Weights renormalised over the 4 remaining signals.

Six scored buckets (weights unchanged at top level):
  1. Rights control             (25%)
  2. Economic control           (20%)
  3. Partner encumbrance facts  (20%)
  4. IP control                 (15%)
  5. Manufacturing readiness    (10%)
  6. Diligence readiness        (10%)

Gate treatment by composite score (identical thresholds to legacy 0D):
  ≥ 0.85   Clean — no penalty (×1.00)
  0.70–0.85 Mild penalty (×0.95)
  0.50–0.70 Meaningful penalty (×0.80)
  0.35–0.50 Severe cap (×0.60); max M&A score 0.55
  < 0.35   Route to licensing (×0.40); max M&A score 0.40

Hard blockers (override gate):
  no_ownable_rights   → HARD_FAIL
  fatal_ip_dispute    → composite capped at 0.30
  fully_licensed_away → ROUTE_TO_LICENSING

Output flags forwarded to Layer 3B:
  has_rofr_fact              — ROFR partner exists (buyer impact resolved in 3B)
  has_existing_partner_fact  — active development/commercial partner exists
  manufacturing_complexity_flag — "low"/"medium"/"high" for 3B mismatch logic
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums and constants
# ---------------------------------------------------------------------------

class AssetControlGateTreatment(str, Enum):
    CLEAN = "clean"
    MILD_PENALTY = "mild_penalty"
    MEANINGFUL_PENALTY = "meaningful_penalty"
    SEVERE_CAP = "severe_cap"
    ROUTE_TO_LICENSING = "route_to_licensing_or_fail"
    HARD_FAIL = "hard_fail"


# Bucket weights (must sum to 1.0)
_BUCKET_WEIGHTS: dict[str, float] = {
    "rights_control":            0.25,
    "economic_control":          0.20,
    "partner_encumbrance_facts": 0.20,
    "ip_control":                0.15,
    "manufacturing_readiness":   0.10,
    "diligence_readiness":       0.10,
}
assert abs(sum(_BUCKET_WEIGHTS.values()) - 1.0) < 1e-9

# Gate bands: (score_lower_inclusive, treatment, penalty_mult, max_mna_score_cap)
_GATE_BANDS: list[tuple[float, AssetControlGateTreatment, float, Optional[float]]] = [
    (0.85, AssetControlGateTreatment.CLEAN,             1.00, None),
    (0.70, AssetControlGateTreatment.MILD_PENALTY,       0.95, None),
    (0.50, AssetControlGateTreatment.MEANINGFUL_PENALTY, 0.80, None),
    (0.35, AssetControlGateTreatment.SEVERE_CAP,         0.60, 0.55),
    (0.00, AssetControlGateTreatment.ROUTE_TO_LICENSING, 0.40, 0.40),
]

_ROYALTY_STACK_HIGH_THRESHOLD = 0.15


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class AssetControlTargetInput(BaseModel):
    """Signal bag for 0D-T: target-level asset-control profile.

    All fields are target-level facts — no acquirer identity required.
    Sub-score semantics (same as legacy 0D):
      0.90–1.00  Clean
      0.70–0.89  Minor issue, manageable
      0.50–0.69  Meaningful encumbrance
      0.30–0.49  Severe issue
      < 0.30     Deal-blocking unless special buyer
    """
    model_config = ConfigDict(frozen=True)

    # ── 1. Rights Control ─────────────────────────────────────────────────────
    global_rights_control: float = Field(default=0.80, ge=0.0, le=1.0,
        description="Target owns global rights (vs regional / indication-level)")
    key_geography_control: float = Field(default=0.80, ge=0.0, le=1.0,
        description="US and EU rights available to a buyer (not out-licensed)")
    indication_control: float = Field(default=0.85, ge=0.0, le=1.0,
        description="All indication rights owned (vs indication-level splits)")
    change_of_control_freedom: float = Field(default=0.70, ge=0.0, le=1.0,
        description="CoC provisions do not trigger adverse payments/reversion")

    # ── 2. Economic Control ───────────────────────────────────────────────────
    royalty_cleanliness: float = Field(default=0.82, ge=0.0, le=1.0,
        description="Royalty obligations low/absent (1.0 = no royalty burden)")
    milestone_burden: float = Field(default=0.80, ge=0.0, le=1.0,
        description="Remaining milestone obligations manageable")
    profit_share_cleanliness: float = Field(default=0.87, ge=0.0, le=1.0,
        description="No profit-sharing / revenue-split obligations")
    cost_obligation_cleanliness: float = Field(default=0.85, ge=0.0, le=1.0,
        description="Co-development cost obligations absent or buyer-favorable")

    # ── 3. Partner Encumbrance Facts (target-level only) ──────────────────────
    # Removed: no_rofr_or_opt_in, no_consent_requirement, no_exclusivity_conflict
    # Those are pair-specific and live in Layer 3B.
    no_blocking_rights: float = Field(default=0.82, ge=0.0, le=1.0,
        description="No partner veto / co-promotion blocking (generic, not buyer-specific)")
    clean_governance_control: float = Field(default=0.85, ge=0.0, le=1.0,
        description="No joint steering committee or shared governance rights post-close")
    partner_encumbrance_severity: float = Field(default=0.85, ge=0.0, le=1.0,
        description="Overall severity of partnership encumbrances (few/simple = high score). "
                    "Captures number of partners, complexity of obligations, overlap of rights.")

    # ── 4. IP Control ─────────────────────────────────────────────────────────
    patent_strength: float = Field(default=0.75, ge=0.0, le=1.0,
        description="Composition-of-matter or strong patent position")
    exclusivity_runway: float = Field(default=0.75, ge=0.0, le=1.0,
        description="Years of patent exclusivity remaining post-expected-approval")
    freedom_to_operate: float = Field(default=0.85, ge=0.0, le=1.0,
        description="No FTO issues; third-party IP landscape navigable")
    ownership_cleanliness: float = Field(default=0.90, ge=0.0, le=1.0,
        description="IP ownership uncontested; university license obligations manageable")

    # ── 5. Manufacturing Readiness (target-level; acquirer_mfg_fit removed) ───
    process_transferability: float = Field(default=0.75, ge=0.0, le=1.0,
        description="Manufacturing can be transferred to acquirer or qualified CDMO")
    supply_redundancy: float = Field(default=0.70, ge=0.0, le=1.0,
        description="Multiple suppliers available; not single-CDMO dependent")
    gmp_quality_readiness: float = Field(default=0.80, ge=0.0, le=1.0,
        description="No open GMP citations, audit findings, or batch release issues")
    scale_capacity: float = Field(default=0.75, ge=0.0, le=1.0,
        description="Manufacturing capacity sufficient for commercial-scale launch")
    manufacturing_complexity: str = Field(default="low",
        description="Modality complexity class: 'low'/'medium'/'high'. "
                    "Exported to Layer 3B for acquirer manufacturing-fit scoring. "
                    "Does not directly affect the bucket score — that comes from the "
                    "sub-scores above.")

    # ── 6. Diligence Readiness ────────────────────────────────────────────────
    clinical_data_completeness: float = Field(default=0.65, ge=0.0, le=1.0)
    cmc_package_completeness: float = Field(default=0.62, ge=0.0, le=1.0)
    regulatory_file_completeness: float = Field(default=0.65, ge=0.0, le=1.0)
    safety_database_quality: float = Field(default=0.65, ge=0.0, le=1.0)
    data_room_readiness: float = Field(default=0.62, ge=0.0, le=1.0)

    # ── Hard blockers (not scored — override gate) ────────────────────────────
    no_ownable_rights: bool = Field(default=False,
        description="Buyer cannot acquire ownable rights → HARD_FAIL")
    fatal_ip_dispute: bool = Field(default=False,
        description="IP ownership fatally contested → composite capped at 0.30")
    fully_licensed_away: bool = Field(default=False,
        description="Rights fully out-licensed → ROUTE_TO_LICENSING")

    # ── Target-level ROFR / partner facts (recorded; pair impact resolved in 3B) ──
    has_existing_partnership: bool = Field(default=False)
    has_right_of_first_refusal: bool = Field(default=False)
    royalty_stack_high: bool = Field(default=False)
    has_co_development_obligation: bool = Field(default=False)
    has_ip_dispute: bool = Field(default=False)
    has_manufacturing_dependency: bool = Field(default=False)
    asset_rights_scope: str = Field(default="global")


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class AssetControlTargetResult(BaseModel):
    """0D-T target-level asset-control result.

    Backward-compatible with AssetControlResult field names where overlap exists.
    New fields:
      partner_encumbrance_facts_score  — replaces partner_freedom_score (no pair contamination)
      manufacturing_readiness_score    — replaces manufacturing_control_score (no mfg_fit)
      has_rofr_fact                    — ROFR partner present; buyer impact resolved in 3B
      has_existing_partner_fact        — active development/commercial partner present
      manufacturing_complexity_flag    — "low"/"medium"/"high" for Layer 3B
      route_to_licensing               — True when fully_licensed_away triggers routing
    """
    model_config = ConfigDict(frozen=True)

    # ── Composite ──────────────────────────────────────────────────────────────
    asset_control_score: float = Field(..., ge=0.0, le=1.0)
    gate_treatment: AssetControlGateTreatment
    penalty_multiplier: float = Field(..., ge=0.0, le=1.0,
        description="Score multiplier applied to M&A composite (1.0 = no penalty)")
    max_mna_score_cap: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # ── Bucket scores ──────────────────────────────────────────────────────────
    rights_control_score: float = Field(..., ge=0.0, le=1.0)
    economic_control_score: float = Field(..., ge=0.0, le=1.0)
    partner_encumbrance_facts_score: float = Field(..., ge=0.0, le=1.0,
        description="Target-level partner encumbrance (no acquirer identity)")
    ip_control_score: float = Field(..., ge=0.0, le=1.0)
    manufacturing_readiness_score: float = Field(..., ge=0.0, le=1.0,
        description="Target-level manufacturing readiness (no acquirer fit)")
    diligence_readiness_score: float = Field(..., ge=0.0, le=1.0)

    # ── Hard blocker / routing ────────────────────────────────────────────────
    is_hard_fail: bool = Field(default=False)
    route_to_licensing: bool = Field(default=False)
    hard_blockers: list[str] = Field(default_factory=list)

    # ── Valuation adjustment ──────────────────────────────────────────────────
    encumbrance_valuation_multiplier: float = Field(..., ge=0.0, le=1.0,
        description="Product of rights/economic/IP/mfg multipliers; pure target-level")

    # ── Downstream signal flags for Layer 3B ─────────────────────────────────
    has_rofr_fact: bool = Field(default=False,
        description="ROFR partner exists; buyer-specific impact resolved in Layer 3B")
    has_existing_partner_fact: bool = Field(default=False,
        description="Active development/commercial partner exists")
    manufacturing_complexity_flag: str = Field(default="low",
        description="'low'/'medium'/'high' — passed to Layer 3B mfg mismatch scoring")

    # ── Output metadata ───────────────────────────────────────────────────────
    asset_control_confidence: str
    triggered_encumbrances: list[str]
    recommended_action: str
    rationale: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)

    # ── Backward-compat legacy fields ─────────────────────────────────────────
    asset_rights_scope: str = Field(default="global")
    has_existing_partnership: bool = Field(default=False)
    has_right_of_first_refusal: bool = Field(default=False)
    royalty_stack_high: bool = Field(default=False)
    has_co_development_obligation: bool = Field(default=False)
    has_ip_dispute: bool = Field(default=False)
    has_manufacturing_dependency: bool = Field(default=False)

    @property
    def score_cap(self) -> Optional[float]:
        """Alias for max_mna_score_cap (target-level only; pair caps live in 3B)."""
        return self.max_mna_score_cap

    @property
    def encumbrance_codes(self) -> list[str]:
        """Backward-compat alias for triggered_encumbrances."""
        return self.triggered_encumbrances

    @property
    def partner_freedom_score(self) -> float:
        """Backward-compat alias for partner_encumbrance_facts_score.

        Legacy name from the old ma_asset_control.py partner_freedom bucket.
        Callers should migrate to partner_encumbrance_facts_score.
        """
        return self.partner_encumbrance_facts_score

    @property
    def manufacturing_control_score(self) -> float:
        """Backward-compat alias for manufacturing_readiness_score.

        Legacy name from the old ma_asset_control.py manufacturing_control bucket.
        Callers should migrate to manufacturing_readiness_score.
        """
        return self.manufacturing_readiness_score


# ---------------------------------------------------------------------------
# Bucket scoring functions
# ---------------------------------------------------------------------------

def _score_rights_control(inp: AssetControlTargetInput) -> tuple[float, list[str]]:
    """0.40×global + 0.25×key_geo + 0.20×indication + 0.15×coc_freedom"""
    raw = (
        0.40 * inp.global_rights_control
        + 0.25 * inp.key_geography_control
        + 0.20 * inp.indication_control
        + 0.15 * inp.change_of_control_freedom
    )
    score = min(1.0, max(0.0, raw))
    codes: list[str] = []
    if inp.global_rights_control >= 0.90:
        codes.append("global_rights:positive")
    elif inp.global_rights_control < 0.50:
        codes.append("rights_control:severe_restriction")
    if inp.key_geography_control < 0.55:
        codes.append("key_geography:major_market_unavailable")
    if inp.asset_rights_scope == "regional_split":
        codes.append("regional_rights_split")
    elif inp.asset_rights_scope == "licensed_in":
        codes.append("licensed_in_rights")
    return score, codes


def _score_economic_control(inp: AssetControlTargetInput) -> tuple[float, list[str]]:
    """0.35×royalty + 0.25×milestone + 0.20×profit_share + 0.20×cost_oblig"""
    raw = (
        0.35 * inp.royalty_cleanliness
        + 0.25 * inp.milestone_burden
        + 0.20 * inp.profit_share_cleanliness
        + 0.20 * inp.cost_obligation_cleanliness
    )
    score = min(1.0, max(0.0, raw))
    codes: list[str] = []
    if inp.royalty_stack_high:
        codes.append("royalty_stack_high")
    if inp.royalty_cleanliness < 0.55:
        codes.append("economic_control:heavy_royalty_burden")
    if inp.has_co_development_obligation:
        codes.append("co_development_obligation")
    if inp.milestone_burden < 0.50:
        codes.append("economic_control:large_milestone_burden")
    return score, codes


def _score_partner_encumbrance_facts(inp: AssetControlTargetInput) -> tuple[float, list[str]]:
    """0.50×no_blocking + 0.30×governance + 0.20×severity

    Target-level only.  The pair-specific sub-signals (no_rofr_or_opt_in,
    no_consent_requirement, no_exclusivity_conflict) have been removed.
    Their impact on a specific acquirer is resolved in Layer 3B.
    """
    raw = (
        0.50 * inp.no_blocking_rights
        + 0.30 * inp.clean_governance_control
        + 0.20 * inp.partner_encumbrance_severity
    )
    score = min(1.0, max(0.0, raw))
    codes: list[str] = []
    if inp.has_right_of_first_refusal:
        codes.append("partner_fact:rofr_present")
    if inp.has_existing_partnership:
        codes.append("partner_fact:existing_partner_present")
    if inp.no_blocking_rights < 0.40:
        codes.append("partner_encumbrance:generic_blocking_rights_severe")
    if inp.partner_encumbrance_severity < 0.40:
        codes.append("partner_encumbrance:high_overall_severity")
    return score, codes


def _score_ip_control(inp: AssetControlTargetInput) -> tuple[float, list[str]]:
    """0.35×patent_strength + 0.25×exclusivity + 0.20×fto + 0.20×ownership"""
    raw = (
        0.35 * inp.patent_strength
        + 0.25 * inp.exclusivity_runway
        + 0.20 * inp.freedom_to_operate
        + 0.20 * inp.ownership_cleanliness
    )
    score = min(1.0, max(0.0, raw))
    codes: list[str] = []
    if inp.has_ip_dispute:
        codes.append("ip_dispute")
    if inp.ownership_cleanliness < 0.30:
        codes.append("ip_control:ownership_fatally_contested")
    if inp.freedom_to_operate < 0.40:
        codes.append("ip_control:FTO_issue")
    if inp.patent_strength < 0.50:
        codes.append("ip_control:weak_patent_position")
    return score, codes


def _score_manufacturing_readiness(inp: AssetControlTargetInput) -> tuple[float, list[str]]:
    """0.35×transferability + 0.30×supply + 0.20×gmp + 0.15×scale

    acquirer_manufacturing_fit removed — pair-specific and moved to Layer 3B.
    Weights renormalised over 4 remaining signals (sum = 1.00).
    """
    raw = (
        0.35 * inp.process_transferability
        + 0.30 * inp.supply_redundancy
        + 0.20 * inp.gmp_quality_readiness
        + 0.15 * inp.scale_capacity
    )
    score = min(1.0, max(0.0, raw))
    codes: list[str] = []
    if inp.has_manufacturing_dependency:
        codes.append("manufacturing_dependency")
    if inp.supply_redundancy < 0.40:
        codes.append("manufacturing_readiness:single_CDMO_dependency")
    if inp.gmp_quality_readiness < 0.40:
        codes.append("manufacturing_readiness:GMP_issue")
    if inp.manufacturing_complexity == "high":
        codes.append("manufacturing_readiness:high_complexity_modality")
    return score, codes


def _score_diligence_readiness(inp: AssetControlTargetInput) -> tuple[float, list[str]]:
    """0.30×clinical + 0.25×cmc + 0.20×regulatory + 0.15×safety + 0.10×data_room"""
    raw = (
        0.30 * inp.clinical_data_completeness
        + 0.25 * inp.cmc_package_completeness
        + 0.20 * inp.regulatory_file_completeness
        + 0.15 * inp.safety_database_quality
        + 0.10 * inp.data_room_readiness
    )
    score = min(1.0, max(0.0, raw))
    codes: list[str] = []
    if inp.safety_database_quality < 0.35:
        codes.append("diligence_readiness:incomplete_safety_database")
    if inp.clinical_data_completeness < 0.40:
        codes.append("diligence_readiness:missing_trial_data")
    if inp.cmc_package_completeness < 0.40:
        codes.append("diligence_readiness:missing_CMC_data")
    return score, codes


# ---------------------------------------------------------------------------
# Gate treatment
# ---------------------------------------------------------------------------

def _gate_treatment(
    score: float,
    hard_blockers: list[str],
) -> tuple[AssetControlGateTreatment, float, Optional[float]]:
    """Return (gate_treatment, penalty_multiplier, max_mna_score_cap)."""
    if "no_ownable_rights" in hard_blockers:
        return AssetControlGateTreatment.HARD_FAIL, 0.20, 0.40
    for lower, treatment, mult, cap in _GATE_BANDS:
        if score >= lower:
            return treatment, mult, cap
    return AssetControlGateTreatment.ROUTE_TO_LICENSING, 0.40, 0.40


# ---------------------------------------------------------------------------
# Valuation multiplier (target-level only; no acquirer_mfg_fit contamination)
# ---------------------------------------------------------------------------

def _encumbrance_valuation_multiplier(
    rights: float, economic: float, ip: float, mfg_readiness: float,
) -> float:
    """Target-level encumbrance-adjusted rNPV multiplier.

    Each dimension linearly scaled from [0, 1] score to [floor, 1.0]:
      rights:        floor 0.50
      economic:      floor 0.55
      ip:            floor 0.60
      mfg_readiness: floor 0.70  (pure target complexity; acquirer fit in 3B)
    """
    r_mult = 0.50 + 0.50 * rights
    e_mult = 0.55 + 0.45 * economic
    i_mult = 0.60 + 0.40 * ip
    m_mult = 0.70 + 0.30 * mfg_readiness
    return round(r_mult * e_mult * i_mult * m_mult, 4)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_asset_control_target(inp: AssetControlTargetInput) -> AssetControlTargetResult:
    """Score all 6 target-level asset-control buckets and compute 0D-T result.

    No acquirer identity is used.  Pair-specific adjustments are applied
    downstream in Layer 3B (ma_pair_asset_control.py).
    """
    # 1. Score each bucket
    rights_score, rights_codes = _score_rights_control(inp)
    economic_score, economic_codes = _score_economic_control(inp)
    partner_score, partner_codes = _score_partner_encumbrance_facts(inp)
    ip_score, ip_codes = _score_ip_control(inp)
    mfg_score, mfg_codes = _score_manufacturing_readiness(inp)
    diligence_score, diligence_codes = _score_diligence_readiness(inp)

    # 2. Weighted composite
    composite = (
        _BUCKET_WEIGHTS["rights_control"]            * rights_score
        + _BUCKET_WEIGHTS["economic_control"]        * economic_score
        + _BUCKET_WEIGHTS["partner_encumbrance_facts"] * partner_score
        + _BUCKET_WEIGHTS["ip_control"]              * ip_score
        + _BUCKET_WEIGHTS["manufacturing_readiness"] * mfg_score
        + _BUCKET_WEIGHTS["diligence_readiness"]     * diligence_score
    )

    # 3. Hard blockers
    hard_blockers: list[str] = []
    if inp.no_ownable_rights:
        hard_blockers.append("no_ownable_rights")
    if inp.fatal_ip_dispute:
        hard_blockers.append("fatal_ip_dispute")
        composite = min(composite, 0.30)
    if inp.fully_licensed_away:
        hard_blockers.append("fully_licensed_away")
        composite = min(composite, 0.30)

    composite = round(min(1.0, max(0.0, composite)), 4)

    # 4. Gate treatment (target-level only; no pair-level cap here)
    treatment, mult, max_cap = _gate_treatment(composite, hard_blockers)

    # 5. Triggered encumbrances
    all_codes = (
        rights_codes + economic_codes + partner_codes
        + ip_codes + mfg_codes + diligence_codes
    )
    triggered = sorted(set(all_codes))

    # 6. Recommended action
    _actions = {
        AssetControlGateTreatment.CLEAN:
            "Proceed to scoring; no encumbrance notes required",
        AssetControlGateTreatment.MILD_PENALTY:
            "Apply 0.95 multiplier; note minor encumbrances in memo",
        AssetControlGateTreatment.MEANINGFUL_PENALTY:
            "Apply 0.80 multiplier; flag encumbrances prominently in memo",
        AssetControlGateTreatment.SEVERE_CAP:
            "Cap M&A score at 0.55; escalate to deal team before proceeding",
        AssetControlGateTreatment.ROUTE_TO_LICENSING:
            "Route to licensing model; full acquisition not recommended",
        AssetControlGateTreatment.HARD_FAIL:
            "Hard fail: buyer cannot acquire clean control of asset",
    }

    # 7. Confidence from diligence readiness
    if diligence_score >= 0.80:
        confidence = "high"
    elif diligence_score >= 0.60:
        confidence = "medium"
    else:
        confidence = "low"

    # 8. Rationale
    rationale: list[str] = [
        f"rights_control={rights_score:.3f}  economic={economic_score:.3f}  "
        f"partner_encumbrance_facts={partner_score:.3f}",
        f"ip_control={ip_score:.3f}  manufacturing_readiness={mfg_score:.3f}  "
        f"diligence={diligence_score:.3f}",
        f"composite={composite:.3f}  treatment={treatment.value}",
    ]
    if hard_blockers:
        rationale.append(f"hard_blockers={hard_blockers}")
    if inp.has_right_of_first_refusal or inp.has_existing_partnership:
        rationale.append(
            "pair_note: ROFR/partner impact on specific buyer resolved in Layer 3B"
        )

    # 9. Data gaps
    data_gaps: list[str] = []
    if diligence_score < 0.65:
        data_gaps.append("diligence_readiness: incomplete data package")

    # 10. Valuation multiplier (target-level only)
    val_mult = _encumbrance_valuation_multiplier(
        rights_score, economic_score, ip_score, mfg_score,
    )

    return AssetControlTargetResult(
        asset_control_score=composite,
        gate_treatment=treatment,
        penalty_multiplier=round(mult, 4),
        max_mna_score_cap=max_cap,
        rights_control_score=round(rights_score, 4),
        economic_control_score=round(economic_score, 4),
        partner_encumbrance_facts_score=round(partner_score, 4),
        ip_control_score=round(ip_score, 4),
        manufacturing_readiness_score=round(mfg_score, 4),
        diligence_readiness_score=round(diligence_score, 4),
        is_hard_fail=(treatment == AssetControlGateTreatment.HARD_FAIL),
        route_to_licensing=(
            treatment == AssetControlGateTreatment.ROUTE_TO_LICENSING
            or inp.fully_licensed_away
        ),
        hard_blockers=hard_blockers,
        encumbrance_valuation_multiplier=val_mult,
        has_rofr_fact=inp.has_right_of_first_refusal,
        has_existing_partner_fact=inp.has_existing_partnership,
        manufacturing_complexity_flag=inp.manufacturing_complexity,
        asset_control_confidence=confidence,
        triggered_encumbrances=triggered,
        recommended_action=_actions[treatment],
        rationale=rationale,
        data_gaps=data_gaps,
        # Backward-compat legacy fields
        asset_rights_scope=inp.asset_rights_scope,
        has_existing_partnership=inp.has_existing_partnership,
        has_right_of_first_refusal=inp.has_right_of_first_refusal,
        royalty_stack_high=inp.royalty_stack_high,
        has_co_development_obligation=inp.has_co_development_obligation,
        has_ip_dispute=inp.has_ip_dispute,
        has_manufacturing_dependency=inp.has_manufacturing_dependency,
    )


# ---------------------------------------------------------------------------
# Mapper: TargetEligibilityInput → AssetControlTargetInput
# ---------------------------------------------------------------------------

def asset_control_target_from_target(t: object) -> AssetControlTargetInput:
    """Map a TargetEligibilityInput's coarse signals to AssetControlTargetInput.

    Known signals set precise sub-scores; unknown signals use defaults.
    Hard blockers derived from most severe coarse signals.

    Note: does NOT set acquirer_is_existing_partner, acquirer_manufacturing_fit,
    or blocking_consent_right — those are pair-specific inputs to Layer 3B.
    """
    def _g(attr: str, default):
        return getattr(t, attr, default)

    rights_scope = _g("asset_rights_scope", "global")
    has_rofr = _g("has_right_of_first_refusal", False)
    has_partnership = _g("has_existing_partnership", False)
    royalty_rate = _g("royalty_stack_rate", None) or 0.0
    has_cdev = _g("has_co_development_obligation", False)
    has_ip_disp = _g("has_ip_dispute", False)
    has_mfg_dep = _g("has_manufacturing_dependency", False)
    mfg_complexity = _g("manufacturing_complexity", "low")

    # ── Rights Control ────────────────────────────────────────────────────────
    if rights_scope == "global":
        global_rights, key_geo, indication_ctrl = 0.95, 0.90, 0.88
    elif rights_scope == "regional_split":
        global_rights, key_geo, indication_ctrl = 0.50, 0.50, 0.75
    elif rights_scope == "licensed_in":
        global_rights, key_geo, indication_ctrl = 0.25, 0.45, 0.55
    else:
        global_rights, key_geo, indication_ctrl = 0.65, 0.65, 0.75

    # ── Economic Control ──────────────────────────────────────────────────────
    royalty_cleanliness = max(0.10, 1.0 - royalty_rate * 2.5)
    cost_oblig_clean = 0.45 if has_cdev else 0.87

    # ── Partner Encumbrance Facts ─────────────────────────────────────────────
    # no_blocking_rights: reflects generic partner veto/co-promotion risk
    blocking_score = 0.50 if has_partnership else 0.85
    # partner_encumbrance_severity: overall severity proxy from coarse signals
    if has_partnership and has_rofr:
        partner_severity = 0.30   # multiple encumbrances — complex partner landscape
    elif has_partnership:
        partner_severity = 0.55   # existing partner, no hard ROFR
    elif has_rofr:
        partner_severity = 0.65   # ROFR only (no active partnership)
    else:
        partner_severity = 0.90   # clean

    # ── IP Control ────────────────────────────────────────────────────────────
    ownership_clean = 0.15 if has_ip_disp else 0.90
    fto_score = 0.45 if has_ip_disp else 0.85

    # ── Manufacturing Readiness ────────────────────────────────────────────────
    if has_mfg_dep:
        proc_transfer, supply_redund = 0.40, 0.45
    elif mfg_complexity == "high":
        proc_transfer, supply_redund = 0.55, 0.60
    elif mfg_complexity == "medium":
        proc_transfer, supply_redund = 0.72, 0.70
    else:
        proc_transfer, supply_redund = 0.85, 0.80
    gmp = 0.62 if mfg_complexity == "high" else 0.80

    # ── Diligence Readiness ───────────────────────────────────────────────────
    has_clinical = _g("has_clinical_stage", False) or _g("has_trial_status", False)
    clin_comp = 0.75 if has_clinical else 0.55
    has_pat = _g("has_patent_loe_data", False)
    cmc_comp = 0.70 if has_pat else 0.55

    fully_licensed = (rights_scope == "licensed_in")
    royalty_stack_high = royalty_rate > _ROYALTY_STACK_HIGH_THRESHOLD

    return AssetControlTargetInput(
        global_rights_control=global_rights,
        key_geography_control=key_geo,
        indication_control=indication_ctrl,
        royalty_cleanliness=round(royalty_cleanliness, 4),
        cost_obligation_cleanliness=cost_oblig_clean,
        no_blocking_rights=blocking_score,
        clean_governance_control=0.85,          # default: no JSC insight from coarse data
        partner_encumbrance_severity=partner_severity,
        ownership_cleanliness=ownership_clean,
        freedom_to_operate=fto_score,
        process_transferability=proc_transfer,
        supply_redundancy=supply_redund,
        gmp_quality_readiness=gmp,
        manufacturing_complexity=mfg_complexity,
        clinical_data_completeness=clin_comp,
        cmc_package_completeness=cmc_comp,
        fully_licensed_away=fully_licensed,
        has_ip_dispute=has_ip_disp,
        has_right_of_first_refusal=has_rofr,
        has_existing_partnership=has_partnership,
        has_co_development_obligation=has_cdev,
        has_manufacturing_dependency=has_mfg_dep,
        royalty_stack_high=royalty_stack_high,
        asset_rights_scope=rights_scope,
    )
