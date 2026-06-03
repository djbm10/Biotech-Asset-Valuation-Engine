"""
Market access / reimbursement risk model.

Adjusts the effective commercial forecast based on payer dynamics.
Formulary placement, prior-authorisation burden, cost-effectiveness risk, and
orphan-drug status are the primary drivers.

Score accumulation uses additive adjusters on linear multipliers (not log-odds)
because commercial-access effects compound multiplicatively against the patient
pool, not against a regulatory binary outcome.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class FormularyTier(str, Enum):
    TIER_1 = "tier_1"          # preferred generic
    TIER_2 = "tier_2"          # preferred brand
    TIER_3 = "tier_3"          # non-preferred brand
    SPECIALTY = "specialty"     # specialty formulary
    EXCLUDED = "excluded"       # not covered
    UNKNOWN = "unknown"


class PriorAuthBurden(str, Enum):
    NONE = "none"
    LOW = "low"            # minimal criteria
    MODERATE = "moderate"  # step edits or lab requirements
    HIGH = "high"          # complex multi-step criteria
    UNKNOWN = "unknown"


class CostEffectivenessRisk(str, Enum):
    LOW = "low"            # ICER < $50K/QALY
    MODERATE = "moderate"  # ICER $50K–$150K/QALY
    HIGH = "high"          # ICER > $150K/QALY or unknown
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Input dataclass
# ---------------------------------------------------------------------------

@dataclass
class PayerDynamics:
    """Observable payer and market access signals."""

    formulary_tier: FormularyTier = FormularyTier.UNKNOWN
    prior_auth_burden: PriorAuthBurden = PriorAuthBurden.UNKNOWN
    cost_effectiveness_risk: CostEffectivenessRisk = CostEffectivenessRisk.UNKNOWN
    step_edit_required: bool = False        # must fail prior therapy first
    rwe_requirement: bool = False           # payer requires real-world evidence post-launch
    medicare_heavy_indication: bool = False  # >60% Medicare patients (reimbursement pressure)
    orphan_drug_designation: bool = False   # 7yr exclusivity + reduced payer scrutiny
    list_price_usd_thousands: float = 0.0   # annual WAC in $K (0 = unknown)
    commercial_payer_coverage_pct: float = 0.0  # estimated % of commercially insured covered
    net_price_to_list_ratio: float = 1.0    # estimated net/WAC (1.0 = no rebate)


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MarketAccessResult:
    """Adjusted commercial forecast based on payer dynamics."""

    payer_dynamics: PayerDynamics
    effective_patient_pool_multiplier: float   # [0.30, 1.0] applied to addressable patients
    adoption_speed_modifier: float             # [−0.30, +0.10] modifier on ramp-up rate
    peak_penetration_modifier: float           # [−0.20, +0.05] modifier on peak market share
    net_price_durability_years: float          # estimated years before significant rebate pressure
    access_risk_score: float                   # 0.0 (easiest) to 1.0 (hardest) market access
    access_risk_tier: str                      # "favorable" / "moderate" / "challenging" / "unknown"
    risk_factors: list[str]
    tailwinds: list[str]


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def assess_market_access(dynamics: PayerDynamics) -> MarketAccessResult:
    """
    Score payer dynamics and return an adjusted commercial forecast envelope.

    Parameters
    ----------
    dynamics:
        Populated PayerDynamics snapshot for the asset.

    Returns
    -------
    MarketAccessResult with all output fields populated.
    """
    risk_factors: list[str] = []
    tailwinds: list[str] = []

    # ------------------------------------------------------------------
    # Short-circuit: EXCLUDED formulary tier
    # ------------------------------------------------------------------
    if dynamics.formulary_tier == FormularyTier.EXCLUDED:
        risk_factors.append("Formulary excluded — effectively no commercial access")
        return MarketAccessResult(
            payer_dynamics=dynamics,
            effective_patient_pool_multiplier=0.30,
            adoption_speed_modifier=-0.30,
            peak_penetration_modifier=-0.20,
            net_price_durability_years=1.0,
            access_risk_score=1.0,
            access_risk_tier="unknown",
            risk_factors=risk_factors,
            tailwinds=tailwinds,
        )

    # ------------------------------------------------------------------
    # effective_patient_pool_multiplier
    # ------------------------------------------------------------------
    pool_mult = 1.0

    if dynamics.formulary_tier == FormularyTier.TIER_3:
        pool_mult -= 0.15
        risk_factors.append("Tier 3 placement — cost-sharing friction reduces addressable pool")
    elif dynamics.formulary_tier == FormularyTier.SPECIALTY:
        pool_mult -= 0.10
        risk_factors.append("Specialty formulary — access requires specialty pharmacy channel")

    if dynamics.step_edit_required:
        pool_mult -= 0.10
        risk_factors.append("Step-edit required — patients must fail prior therapy first")

    if dynamics.prior_auth_burden == PriorAuthBurden.HIGH:
        pool_mult -= 0.12
        risk_factors.append("High prior-auth burden — complex multi-step criteria suppress access")
    elif dynamics.prior_auth_burden == PriorAuthBurden.MODERATE:
        pool_mult -= 0.06
        risk_factors.append("Moderate prior-auth burden — step edits or lab requirements")

    if dynamics.medicare_heavy_indication:
        pool_mult -= 0.08
        risk_factors.append("Medicare-heavy indication (>60%) — price negotiation / rebate pressure")

    if dynamics.orphan_drug_designation:
        pool_mult += 0.08
        tailwinds.append("Orphan drug designation — reduced payer scrutiny and 7yr exclusivity")

    if dynamics.commercial_payer_coverage_pct > 0.70:
        pool_mult += 0.05
        tailwinds.append("High commercial payer coverage (>70%) — broad formulary access expected")

    effective_patient_pool_multiplier = max(0.30, min(1.0, pool_mult))

    # ------------------------------------------------------------------
    # adoption_speed_modifier
    # ------------------------------------------------------------------
    adoption = 0.0

    if dynamics.prior_auth_burden == PriorAuthBurden.HIGH:
        adoption -= 0.15
        # risk already logged above
    if dynamics.step_edit_required:
        adoption -= 0.10
        # risk already logged above
    if dynamics.rwe_requirement:
        adoption -= 0.05
        risk_factors.append("RWE requirement — payer demands post-launch evidence before coverage")

    if dynamics.formulary_tier in (FormularyTier.TIER_1, FormularyTier.TIER_2):
        adoption += 0.08
        tailwinds.append(
            f"{dynamics.formulary_tier.value.replace('_', ' ').title()} placement — "
            "preferred formulary accelerates prescriber uptake"
        )
    if dynamics.orphan_drug_designation:
        adoption += 0.05
        # tailwind already logged above

    adoption_speed_modifier = max(-0.30, min(0.10, adoption))

    # ------------------------------------------------------------------
    # peak_penetration_modifier
    # ------------------------------------------------------------------
    peak = 0.0

    if dynamics.cost_effectiveness_risk == CostEffectivenessRisk.HIGH:
        peak -= 0.12
        risk_factors.append("High cost-effectiveness risk (ICER >$150K/QALY) — payer pushback likely")
    elif dynamics.cost_effectiveness_risk == CostEffectivenessRisk.MODERATE:
        peak -= 0.05
        risk_factors.append("Moderate cost-effectiveness risk (ICER $50K–$150K/QALY)")

    if (
        dynamics.medicare_heavy_indication
        and dynamics.cost_effectiveness_risk in (
            CostEffectivenessRisk.HIGH,
            CostEffectivenessRisk.MODERATE,
        )
    ):
        peak -= 0.05
        risk_factors.append(
            "Medicare-heavy + cost-effectiveness pressure — compounded reimbursement headwind"
        )

    if dynamics.orphan_drug_designation:
        peak += 0.03
        # tailwind already logged above

    if dynamics.formulary_tier == FormularyTier.TIER_1:
        peak += 0.04
        # tailwind already logged above if not duplicate

    peak_penetration_modifier = max(-0.20, min(0.05, peak))

    # ------------------------------------------------------------------
    # net_price_durability_years
    # ------------------------------------------------------------------
    list_k = dynamics.list_price_usd_thousands  # $K

    if dynamics.orphan_drug_designation:
        durability = 8.0
    elif list_k > 0 and list_k < 50.0:
        durability = 6.0
    elif list_k > 0 and list_k < 150.0:
        durability = 5.0
    else:
        durability = 3.0

    if dynamics.rwe_requirement:
        durability -= 1.0
    if dynamics.medicare_heavy_indication:
        durability -= 1.0

    net_price_durability_years = max(1.0, durability)

    # ------------------------------------------------------------------
    # access_risk_score
    # ------------------------------------------------------------------
    risk_score = 0.35  # moderate baseline

    # HIGH-burden signals each add +0.15
    _high_burden_signals = [
        dynamics.formulary_tier in (FormularyTier.TIER_3, FormularyTier.EXCLUDED),
        dynamics.prior_auth_burden == PriorAuthBurden.HIGH,
        dynamics.step_edit_required,
    ]
    risk_score += 0.15 * sum(_high_burden_signals)

    # Favorable signals each subtract −0.10
    _favorable_signals = [
        dynamics.orphan_drug_designation,
        dynamics.formulary_tier in (FormularyTier.TIER_1, FormularyTier.TIER_2),
        dynamics.prior_auth_burden in (PriorAuthBurden.NONE, PriorAuthBurden.LOW),
    ]
    risk_score -= 0.10 * sum(_favorable_signals)

    access_risk_score = max(0.0, min(1.0, risk_score))

    # ------------------------------------------------------------------
    # access_risk_tier
    # ------------------------------------------------------------------
    if access_risk_score < 0.30:
        access_risk_tier = "favorable"
    elif access_risk_score < 0.60:
        access_risk_tier = "moderate"
    elif access_risk_score < 0.85:
        access_risk_tier = "challenging"
    else:
        access_risk_tier = "unknown"

    return MarketAccessResult(
        payer_dynamics=dynamics,
        effective_patient_pool_multiplier=effective_patient_pool_multiplier,
        adoption_speed_modifier=adoption_speed_modifier,
        peak_penetration_modifier=peak_penetration_modifier,
        net_price_durability_years=net_price_durability_years,
        access_risk_score=access_risk_score,
        access_risk_tier=access_risk_tier,
        risk_factors=risk_factors,
        tailwinds=tailwinds,
    )
