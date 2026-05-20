"""
0D — Asset-Control / Encumbrance Gate (6-bucket scoring system).

Answers: "If this buyer acquired the company, would it actually control the
asset, economics, IP, and operations well enough for the deal to make sense?"

Six scored buckets:
  1. Rights control      (25%) — buyer gets what it thinks it's buying
  2. Economic control    (20%) — royalties / milestones / profit-shares
  3. Partner freedom     (20%) — blocking rights, ROFR, consent requirements (PAIR-SPECIFIC)
  4. IP control          (15%) — patent strength, exclusivity, FTO
  5. Manufacturing       (10%) — process transfer, CDMO, GMP (PAIR-SPECIFIC via acquirer_mfg_fit)
  6. Diligence readiness (10%) — data completeness and provenance

Gate treatment by composite score:
  ≥ 0.85   Clean — no penalty
  0.70–0.85 Mild penalty (×0.95)
  0.50–0.70 Meaningful penalty (×0.80); memo flag
  0.35–0.50 Severe cap (×0.60); max M&A score 0.55
  < 0.35   Route to licensing or fail (×0.40); max M&A score 0.40

Hard blockers (not numeric — override gate):
  no_ownable_rights       → HARD_FAIL
  fatal_ip_dispute        → asset_control_score capped at 0.30
  fully_licensed_away     → ROUTE_TO_LICENSING
  blocking_consent_right  → pair-level cap applied
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
    "rights_control": 0.25,
    "economic_control": 0.20,
    "partner_freedom": 0.20,
    "ip_control": 0.15,
    "manufacturing_control": 0.10,
    "diligence_readiness": 0.10,
}
assert abs(sum(_BUCKET_WEIGHTS.values()) - 1.0) < 1e-9

# (score_lower_inclusive, treatment, penalty_mult, max_mna_score_cap)
_GATE_BANDS: list[tuple[float, AssetControlGateTreatment, float, Optional[float]]] = [
    (0.85, AssetControlGateTreatment.CLEAN,               1.00, None),
    (0.70, AssetControlGateTreatment.MILD_PENALTY,         0.95, None),
    (0.50, AssetControlGateTreatment.MEANINGFUL_PENALTY,   0.80, None),
    (0.35, AssetControlGateTreatment.SEVERE_CAP,           0.60, 0.55),
    (0.00, AssetControlGateTreatment.ROUTE_TO_LICENSING,   0.40, 0.40),
]

_ROYALTY_STACK_HIGH_THRESHOLD = 0.15  # cumulative royalty rate above which stack is "high"

_PARTNER_FREEDOM_PARTNER_BONUS = 0.20  # boost to partner_freedom when acquirer IS partner


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class AssetControlInput(BaseModel):
    """Signal bag for the 6 Asset-Control buckets (0D).

    Sub-score semantics:
      0.90–1.00  Clean — buyer can fully control this dimension
      0.70–0.89  Minor issue, manageable
      0.50–0.69  Meaningful encumbrance
      0.30–0.49  Severe issue / likely cap
      < 0.30     Deal-blocking unless special buyer

    Defaults represent a 'neutral/cautiously positive' prior — appropriate when
    only coarse encumbrance signals are available.
    """
    model_config = ConfigDict(frozen=True)

    # ── 1. Rights Control ────────────────────────────────────────────────────
    global_rights_control: float = Field(default=0.80, ge=0.0, le=1.0,
        description="Target owns global rights (vs only regional / indication-level)")
    key_geography_control: float = Field(default=0.80, ge=0.0, le=1.0,
        description="US and EU rights available to buyer (vs out-licensed to partner)")
    indication_control: float = Field(default=0.85, ge=0.0, le=1.0,
        description="All indication rights owned (vs indication-level splits)")
    change_of_control_freedom: float = Field(default=0.70, ge=0.0, le=1.0,
        description="CoC provisions do not trigger adverse payments/rights reversion")

    # ── 2. Economic Control ──────────────────────────────────────────────────
    royalty_cleanliness: float = Field(default=0.82, ge=0.0, le=1.0,
        description="Royalty obligations are low/absent (1.0 = no royalty burden)")
    milestone_burden: float = Field(default=0.80, ge=0.0, le=1.0,
        description="Remaining milestone obligations are manageable (1.0 = no milestones)")
    profit_share_cleanliness: float = Field(default=0.87, ge=0.0, le=1.0,
        description="No profit-sharing or revenue-split obligations with third parties")
    cost_obligation_cleanliness: float = Field(default=0.85, ge=0.0, le=1.0,
        description="Co-development cost obligations are absent or buyer-favorable")

    # ── 3. Partner / Deal Freedom (PAIR-SPECIFIC) ────────────────────────────
    no_blocking_rights: float = Field(default=0.82, ge=0.0, le=1.0,
        description="No partner blocking rights (consent, standstill, co-promotion veto)")
    no_rofr_or_opt_in: float = Field(default=0.85, ge=0.0, le=1.0,
        description="No ROFR or opt-in rights that limit buyer pool for this acquirer")
    no_consent_requirement: float = Field(default=0.85, ge=0.0, le=1.0,
        description="No third-party consents required for this specific change-of-control")
    clean_governance_control: float = Field(default=0.85, ge=0.0, le=1.0,
        description="No joint steering committee or shared governance rights post-close")
    no_exclusivity_conflict: float = Field(default=0.90, ge=0.0, le=1.0,
        description="No exclusivity clause that would complicate this specific acquirer")

    # ── 4. IP Control ────────────────────────────────────────────────────────
    patent_strength: float = Field(default=0.75, ge=0.0, le=1.0,
        description="Composition-of-matter or strong patent position (vs method-of-use only)")
    exclusivity_runway: float = Field(default=0.75, ge=0.0, le=1.0,
        description="Years of patent exclusivity remaining post-expected-approval")
    freedom_to_operate: float = Field(default=0.85, ge=0.0, le=1.0,
        description="No FTO issues; third-party IP landscape is navigable")
    ownership_cleanliness: float = Field(default=0.90, ge=0.0, le=1.0,
        description="IP ownership uncontested; university license obligations manageable")

    # ── 5. Manufacturing / Operational Control (PAIR-SPECIFIC) ───────────────
    process_transferability: float = Field(default=0.75, ge=0.0, le=1.0,
        description="Manufacturing can be transferred to acquirer or qualified CDMO")
    supply_redundancy: float = Field(default=0.70, ge=0.0, le=1.0,
        description="Multiple suppliers available; not single-CDMO dependent")
    acquirer_manufacturing_fit: float = Field(default=0.70, ge=0.0, le=1.0,
        description="PAIR-SPECIFIC: acquirer has capability for this modality/complexity "
                    "(strong capability → reduced penalty; weak → amplified penalty)")
    gmp_quality_readiness: float = Field(default=0.80, ge=0.0, le=1.0,
        description="No open GMP citations, audit findings, or batch release issues")
    scale_capacity: float = Field(default=0.75, ge=0.0, le=1.0,
        description="Manufacturing capacity sufficient for commercial-scale launch")

    # ── 6. Diligence Readiness ───────────────────────────────────────────────
    clinical_data_completeness: float = Field(default=0.65, ge=0.0, le=1.0,
        description="Clinical trial datasets complete; data provenance is clean")
    cmc_package_completeness: float = Field(default=0.62, ge=0.0, le=1.0,
        description="Full CMC package available; manufacturing process documented")
    regulatory_file_completeness: float = Field(default=0.65, ge=0.0, le=1.0,
        description="IND/CTA/NDA-track regulatory files current and accessible")
    safety_database_quality: float = Field(default=0.65, ge=0.0, le=1.0,
        description="Complete safety database; no integrity gaps or unresolved SAEs")
    data_room_readiness: float = Field(default=0.62, ge=0.0, le=1.0,
        description="Data room organized; contracts, IP, financials accessible for diligence")

    # ── Hard blockers (not scored — override gate treatment) ──────────────────
    no_ownable_rights: bool = Field(default=False,
        description="Buyer cannot acquire ownable rights → hard fail for full acquisition")
    blocking_consent_right: bool = Field(default=False,
        description="Third party can block THIS specific acquirer → pair-level cap applied")
    fatal_ip_dispute: bool = Field(default=False,
        description="IP ownership fatally contested → score capped at 0.30")
    fully_licensed_away: bool = Field(default=False,
        description="Rights fully licensed to a third party → route to licensing model")

    # ── Pair-specific context ─────────────────────────────────────────────────
    acquirer_is_existing_partner: bool = Field(default=False,
        description="Acquirer IS the existing development/commercial partner → "
                    "partner_freedom score boosted; ROFR / consent penalties waived")

    # ── Legacy flags (from coarse TargetEligibilityInput; passed through to output) ──
    asset_rights_scope: str = Field(default="global")
    has_existing_partnership: bool = Field(default=False)
    has_right_of_first_refusal: bool = Field(default=False)
    royalty_stack_high: bool = Field(default=False)
    has_co_development_obligation: bool = Field(default=False)
    has_ip_dispute: bool = Field(default=False)
    has_manufacturing_dependency: bool = Field(default=False)


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class AssetControlResult(BaseModel):
    """Full 0D asset-control assessment.

    Backward-compatible replacement for the old EncumbranceFlags model.
    All legacy properties (penalty_multiplier, encumbrance_codes, has_ip_dispute,
    etc.) are preserved alongside the new bucket scores.
    """
    model_config = ConfigDict(frozen=True)

    # ── Composite ─────────────────────────────────────────────────────────────
    asset_control_score: float = Field(..., ge=0.0, le=1.0)
    gate_treatment: AssetControlGateTreatment
    penalty_multiplier: float = Field(..., ge=0.0, le=1.0,
        description="Score multiplier applied to M&A composite (1.0 = no penalty)")
    max_mna_score_cap: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Hard cap on M&A score; None when treatment is CLEAN/MILD/MEANINGFUL")

    # ── Bucket scores ─────────────────────────────────────────────────────────
    rights_control_score: float = Field(..., ge=0.0, le=1.0)
    economic_control_score: float = Field(..., ge=0.0, le=1.0)
    partner_freedom_score: float = Field(..., ge=0.0, le=1.0)
    ip_control_score: float = Field(..., ge=0.0, le=1.0)
    manufacturing_control_score: float = Field(..., ge=0.0, le=1.0)
    diligence_readiness_score: float = Field(..., ge=0.0, le=1.0)

    # ── Hard blocker / pair-level flags ──────────────────────────────────────
    is_hard_fail: bool = Field(default=False)
    is_pair_level_cap: bool = Field(default=False,
        description="True when blocking_consent_right applies to this specific acquirer")
    hard_blockers: list[str] = Field(default_factory=list)
    pair_specific_caps: list[str] = Field(default_factory=list)

    # ── Valuation adjustment ──────────────────────────────────────────────────
    encumbrance_valuation_multiplier: float = Field(..., ge=0.0, le=1.0,
        description="Product of rights / economic / IP / mfg multipliers; "
                    "multiply base rNPV by this to get encumbrance-adjusted value")

    # ── Output metadata ───────────────────────────────────────────────────────
    asset_control_confidence: str = Field(
        ..., description="'high' / 'medium' / 'low' based on diligence_readiness_score")
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
    def encumbrance_codes(self) -> list[str]:
        """Backward compat alias for triggered_encumbrances."""
        return self.triggered_encumbrances


# ---------------------------------------------------------------------------
# Bucket scoring functions
# ---------------------------------------------------------------------------

def _score_rights_control(inp: AssetControlInput) -> tuple[float, list[str]]:
    """Formula: 0.40×global + 0.25×key_geo + 0.20×indication + 0.15×coc_freedom"""
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


def _score_economic_control(inp: AssetControlInput) -> tuple[float, list[str]]:
    """Formula: 0.35×royalty_clean + 0.25×milestone + 0.20×profit_share + 0.20×cost_oblig"""
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


def _score_partner_freedom(inp: AssetControlInput) -> tuple[float, list[str]]:
    """Formula: 0.30×no_blocking + 0.25×no_rofr + 0.20×no_consent + 0.15×governance + 0.10×no_excl

    Pair-specific: when acquirer_is_existing_partner, apply +0.20 bonus and suppress
    ROFR/consent penalties (partner waives its own rights in a self-acquisition scenario).
    """
    base = (
        0.30 * inp.no_blocking_rights
        + 0.25 * inp.no_rofr_or_opt_in
        + 0.20 * inp.no_consent_requirement
        + 0.15 * inp.clean_governance_control
        + 0.10 * inp.no_exclusivity_conflict
    )
    if inp.acquirer_is_existing_partner:
        base = min(1.0, base + _PARTNER_FREEDOM_PARTNER_BONUS)

    score = min(1.0, max(0.0, base))
    codes: list[str] = []
    if inp.has_right_of_first_refusal:
        codes.append("right_of_first_refusal")
    if inp.has_existing_partnership and not inp.acquirer_is_existing_partner:
        codes.append("existing_partner:non_partner_acquirer_penalized")
    if inp.acquirer_is_existing_partner:
        codes.append("partner_freedom:existing_partner_bonus_applied")
    if inp.no_rofr_or_opt_in < 0.40:
        codes.append("partner_freedom:ROFR_or_opt_in_blocks_this_acquirer")
    if inp.no_consent_requirement < 0.30:
        codes.append("partner_freedom:consent_right_blocking")
    return score, codes


def _score_ip_control(inp: AssetControlInput) -> tuple[float, list[str]]:
    """Formula: 0.35×patent_strength + 0.25×exclusivity_runway + 0.20×fto + 0.20×ownership"""
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


def _score_manufacturing_control(inp: AssetControlInput) -> tuple[float, list[str]]:
    """Formula: 0.30×transferability + 0.25×supply_redundancy + 0.20×acquirer_mfg_fit
                + 0.15×gmp_quality + 0.10×scale_capacity

    acquirer_manufacturing_fit is pair-specific: high capability reduces the
    effective penalty from modality complexity.
    """
    raw = (
        0.30 * inp.process_transferability
        + 0.25 * inp.supply_redundancy
        + 0.20 * inp.acquirer_manufacturing_fit
        + 0.15 * inp.gmp_quality_readiness
        + 0.10 * inp.scale_capacity
    )
    score = min(1.0, max(0.0, raw))
    codes: list[str] = []
    if inp.has_manufacturing_dependency:
        codes.append("manufacturing_dependency")
    if inp.supply_redundancy < 0.40:
        codes.append("manufacturing_control:single_CDMO_dependency")
    if inp.gmp_quality_readiness < 0.40:
        codes.append("manufacturing_control:GMP_issue")
    if inp.acquirer_manufacturing_fit >= 0.85:
        codes.append("manufacturing_control:acquirer_strong_capability")
    elif inp.acquirer_manufacturing_fit < 0.40:
        codes.append("manufacturing_control:acquirer_weak_capability_amplifies_risk")
    return score, codes


def _score_diligence_readiness(inp: AssetControlInput) -> tuple[float, list[str]]:
    """Formula: 0.30×clinical + 0.25×cmc + 0.20×regulatory + 0.15×safety_db + 0.10×data_room"""
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
# Valuation multiplier
# ---------------------------------------------------------------------------

def _encumbrance_valuation_multiplier(
    rights: float, economic: float, ip: float, mfg: float,
) -> float:
    """Encumbrance-adjusted rNPV multiplier (product of 4 dimension multipliers).

    Each dimension multiplier is linearly scaled from [0, 1] bucket score to a
    [floor, 1.0] range that reflects realistic valuation impact:
      rights:    floor 0.50 (completely wrong geography → 50% value)
      economic:  floor 0.55 (heavy royalties → 45% value reduction)
      ip:        floor 0.60 (serious IP dispute → 40% value reduction)
      mfg:       floor 0.70 (hard mfg → 30% reduction; acquirer capability limits this)
    """
    r_mult = 0.50 + 0.50 * rights
    e_mult = 0.55 + 0.45 * economic
    i_mult = 0.60 + 0.40 * ip
    m_mult = 0.70 + 0.30 * mfg
    return round(r_mult * e_mult * i_mult * m_mult, 4)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_asset_control(inp: AssetControlInput) -> AssetControlResult:
    """Score all 6 asset-control buckets and compute the composite 0D result.

    Gate primacy: hard blockers override score-based gate treatment.
    Pair-specific: partner_freedom and manufacturing scores reflect acquirer identity.
    """
    # 1. Score each bucket
    rights_score, rights_codes = _score_rights_control(inp)
    economic_score, economic_codes = _score_economic_control(inp)
    partner_score, partner_codes = _score_partner_freedom(inp)
    ip_score, ip_codes = _score_ip_control(inp)
    mfg_score, mfg_codes = _score_manufacturing_control(inp)
    diligence_score, diligence_codes = _score_diligence_readiness(inp)

    # 2. Weighted composite
    composite = (
        _BUCKET_WEIGHTS["rights_control"]       * rights_score
        + _BUCKET_WEIGHTS["economic_control"]   * economic_score
        + _BUCKET_WEIGHTS["partner_freedom"]    * partner_score
        + _BUCKET_WEIGHTS["ip_control"]         * ip_score
        + _BUCKET_WEIGHTS["manufacturing_control"] * mfg_score
        + _BUCKET_WEIGHTS["diligence_readiness"] * diligence_score
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

    # 4. Gate treatment
    treatment, mult, max_cap = _gate_treatment(composite, hard_blockers)

    # 5. Pair-level cap
    pair_caps: list[str] = []
    is_pair_cap = False
    if inp.blocking_consent_right and not inp.acquirer_is_existing_partner:
        pair_caps.append("blocking_consent_right:pair_level_cap_applied")
        is_pair_cap = True
        max_cap = min(max_cap or 0.55, 0.55)
        mult = min(mult, 0.65)
        hard_blockers.append("blocking_consent_right")

    # 6. Triggered encumbrances
    all_codes = (
        rights_codes + economic_codes + partner_codes
        + ip_codes + mfg_codes + diligence_codes
    )
    triggered = sorted(set(all_codes))

    # 7. Recommended action
    _actions = {
        AssetControlGateTreatment.CLEAN: "Proceed to scoring; no encumbrance notes required",
        AssetControlGateTreatment.MILD_PENALTY: "Apply 0.95 multiplier; note minor encumbrances in memo",
        AssetControlGateTreatment.MEANINGFUL_PENALTY: "Apply 0.80 multiplier; flag encumbrances prominently in memo",
        AssetControlGateTreatment.SEVERE_CAP: "Cap M&A score at 0.55; escalate to deal team before proceeding",
        AssetControlGateTreatment.ROUTE_TO_LICENSING: "Route to licensing model; full acquisition not recommended",
        AssetControlGateTreatment.HARD_FAIL: "Hard fail: buyer cannot acquire clean control of asset",
    }

    # 8. Confidence from diligence readiness
    if diligence_score >= 0.80:
        confidence = "high"
    elif diligence_score >= 0.60:
        confidence = "medium"
    else:
        confidence = "low"

    # 9. Rationale
    rationale: list[str] = [
        f"rights_control={rights_score:.3f}  economic={economic_score:.3f}  "
        f"partner_freedom={partner_score:.3f}",
        f"ip_control={ip_score:.3f}  manufacturing={mfg_score:.3f}  "
        f"diligence={diligence_score:.3f}",
        f"composite={composite:.3f}  treatment={treatment.value}",
    ]
    if hard_blockers:
        rationale.append(f"hard_blockers={hard_blockers}")
    if inp.acquirer_is_existing_partner:
        rationale.append("partner_freedom: existing-partner bonus applied (+0.20)")

    # 10. Data gaps
    data_gaps: list[str] = []
    if diligence_score < 0.65:
        data_gaps.append("diligence_readiness: incomplete data package")
    if not inp.data_has_ip_analysis if hasattr(inp, "data_has_ip_analysis") else False:
        data_gaps.append("ip: no confirmed IP analysis available")

    # 11. Valuation multiplier
    val_mult = _encumbrance_valuation_multiplier(
        rights_score, economic_score, ip_score, mfg_score,
    )

    return AssetControlResult(
        asset_control_score=composite,
        gate_treatment=treatment,
        penalty_multiplier=round(mult, 4),
        max_mna_score_cap=max_cap,
        rights_control_score=round(rights_score, 4),
        economic_control_score=round(economic_score, 4),
        partner_freedom_score=round(partner_score, 4),
        ip_control_score=round(ip_score, 4),
        manufacturing_control_score=round(mfg_score, 4),
        diligence_readiness_score=round(diligence_score, 4),
        is_hard_fail=(treatment == AssetControlGateTreatment.HARD_FAIL),
        is_pair_level_cap=is_pair_cap,
        hard_blockers=hard_blockers,
        pair_specific_caps=pair_caps,
        encumbrance_valuation_multiplier=val_mult,
        asset_control_confidence=confidence,
        triggered_encumbrances=triggered,
        recommended_action=_actions[treatment],
        rationale=rationale,
        data_gaps=data_gaps,
        # Legacy backward-compat flags
        asset_rights_scope=inp.asset_rights_scope,
        has_existing_partnership=inp.has_existing_partnership,
        has_right_of_first_refusal=inp.has_right_of_first_refusal,
        royalty_stack_high=inp.royalty_stack_high,
        has_co_development_obligation=inp.has_co_development_obligation,
        has_ip_dispute=inp.has_ip_dispute,
        has_manufacturing_dependency=inp.has_manufacturing_dependency,
    )


# ---------------------------------------------------------------------------
# Mapping from coarse TargetEligibilityInput to detailed AssetControlInput
# ---------------------------------------------------------------------------

def asset_control_from_target(t: object) -> AssetControlInput:
    """Map a TargetEligibilityInput's coarse signals to AssetControlInput sub-scores.

    Known signals set precise sub-scores; unknown signals use defaults.
    Hard blockers are derived from the most severe coarse signals.
    """
    # Safely read optional attributes
    def _g(attr: str, default):
        return getattr(t, attr, default)

    rights_scope = _g("asset_rights_scope", "global")
    has_rofr = _g("has_right_of_first_refusal", False)
    has_partnership = _g("has_existing_partnership", False)
    royalty_rate = _g("royalty_stack_rate", None) or 0.0
    has_cdev = _g("has_co_development_obligation", False)
    has_ip_disp = _g("has_ip_dispute", False)
    has_mfg_dep = _g("has_manufacturing_dependency", False)

    # ── Rights Control ────────────────────────────────────────────────────────
    if rights_scope == "global":
        global_rights = 0.95
        key_geo = 0.90
        indication_ctrl = 0.88
    elif rights_scope == "regional_split":
        global_rights = 0.50
        key_geo = 0.50  # likely missing either US or EU
        indication_ctrl = 0.75
    elif rights_scope == "licensed_in":
        global_rights = 0.25
        key_geo = 0.45
        indication_ctrl = 0.55
    else:  # unknown
        global_rights = 0.65
        key_geo = 0.65
        indication_ctrl = 0.75

    # ── Economic Control ──────────────────────────────────────────────────────
    royalty_cleanliness = max(0.10, 1.0 - royalty_rate * 2.5)  # 20% stack → 0.50 score
    cost_oblig_clean = 0.45 if has_cdev else 0.87

    # ── Partner Freedom ────────────────────────────────────────────────────────
    rofr_score = 0.20 if has_rofr else 0.90
    blocking_score = 0.50 if has_partnership else 0.85
    consent_score = 0.55 if has_partnership and not has_rofr else (0.20 if has_rofr else 0.88)

    # ── IP Control ────────────────────────────────────────────────────────────
    ownership_clean = 0.15 if has_ip_disp else 0.90
    fto_score = 0.45 if has_ip_disp else 0.85

    # ── Manufacturing ─────────────────────────────────────────────────────────
    mfg_complexity = _g("manufacturing_complexity", "low")
    if has_mfg_dep:
        proc_transfer = 0.40
        supply_redund = 0.45
    elif mfg_complexity == "high":
        proc_transfer = 0.55
        supply_redund = 0.60
    elif mfg_complexity == "medium":
        proc_transfer = 0.72
        supply_redund = 0.70
    else:
        proc_transfer = 0.85
        supply_redund = 0.80

    # ── Diligence Readiness ────────────────────────────────────────────────────
    has_clinical = _g("has_clinical_stage", False) or _g("has_trial_status", False)
    clin_comp = 0.75 if has_clinical else 0.55
    has_pat = _g("has_patent_loe_data", False)
    cmc_comp = 0.70 if has_pat else 0.55  # proxy; patent data suggests regulatory engagement

    # Hard blockers
    fully_licensed = (rights_scope == "licensed_in")
    has_blocking_consent = has_rofr and has_partnership  # ROFR + existing partner = high consent risk

    royalty_stack_high = royalty_rate > _ROYALTY_STACK_HIGH_THRESHOLD

    return AssetControlInput(
        global_rights_control=global_rights,
        key_geography_control=key_geo,
        indication_control=indication_ctrl,
        royalty_cleanliness=round(royalty_cleanliness, 4),
        cost_obligation_cleanliness=cost_oblig_clean,
        no_blocking_rights=blocking_score,
        no_rofr_or_opt_in=rofr_score,
        no_consent_requirement=consent_score,
        ownership_cleanliness=ownership_clean,
        freedom_to_operate=fto_score,
        process_transferability=proc_transfer,
        supply_redundancy=supply_redund,
        gmp_quality_readiness=0.80 if mfg_complexity != "high" else 0.62,
        clinical_data_completeness=clin_comp,
        cmc_package_completeness=cmc_comp,
        fully_licensed_away=fully_licensed,
        has_ip_dispute=has_ip_disp,
        has_right_of_first_refusal=has_rofr,
        has_existing_partnership=has_partnership,
        has_co_development_obligation=has_cdev,
        has_manufacturing_dependency=has_mfg_dep,
        royalty_stack_high=royalty_stack_high,
        blocking_consent_right=has_blocking_consent,
        asset_rights_scope=rights_scope,
    )
