"""
0E — Target-Level Commercial Integration Complexity Flag
     + Pair-Specific Integration Capability Adjustment (for Layer 3 / G8)

Layer 0E identifies how operationally complex this target would be to integrate
after acquisition.  It does NOT apply a score penalty directly and does NOT
reward commercial attractiveness or strategic fit — those are handled elsewhere.

Layer 3 then uses the target's raw complexity + the specific acquirer's capability
profile to compute a pair-level adjusted_integration_penalty that feeds G8.

Key design rules:
  - 0E is target-level only (no acquirer identity required).
  - The pair-specific penalty is computed separately in
    compute_pair_integration_adjustment() and fed to G8.
  - No score cap is applied at Layer 0. Caps belong in Layer 3.
  - No synergy / revenue upside is modeled here.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class IntegrationComplexityLevel(str, Enum):
    LOW = "low"           # < 0.25  — minimal complexity; no special handling
    MODERATE = "moderate" # 0.25–0.45 — flag for buyer capability check
    HIGH = "high"         # 0.45–0.65 — requires buyer capability check
    SEVERE = "severe"     # > 0.65  — requires check; Layer 3 cap depends on buyer


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class TargetIntegrationComplexityFlag(BaseModel):
    """Layer 0E — target-level commercial integration complexity flag.

    Tells downstream (Layer 3 / G8) how hard it would be to integrate
    this target.  No score penalty is applied at Layer 0.
    """
    model_config = ConfigDict(frozen=True)

    raw_integration_complexity_score: float = Field(..., ge=0.0, le=1.0)
    complexity_level: IntegrationComplexityLevel
    component_scores: dict[str, float]
    complexity_flags: list[str]
    integration_risk_drivers: list[str]
    requires_buyer_capability_check: bool
    rationale: list[str]
    data_gaps: list[str] = Field(default_factory=list)


class AcquirerIntegrationProfile(BaseModel):
    """Buyer-side integration capability (pair-specific inputs for Layer 3 / G8).

    All sub-scores are 0–1 where 1.0 = full capability.
    Defaults represent a generic large-cap acquirer with moderate infrastructure.
    """
    model_config = ConfigDict(frozen=True)

    acquirer_id: str

    # ── Capability dimensions ─────────────────────────────────────────────
    commercial_infrastructure_fit: float = Field(default=0.60, ge=0.0, le=1.0,
        description="Existing salesforce / commercial ops that can absorb the target")
    manufacturing_capability_fit: float = Field(default=0.60, ge=0.0, le=1.0,
        description="Can the acquirer operate / scale this modality / manufacturing process")
    payer_access_capability_fit: float = Field(default=0.60, ge=0.0, le=1.0,
        description="Existing payer relationships, market access, and reimbursement expertise")
    geographic_footprint_fit: float = Field(default=0.60, ge=0.0, le=1.0,
        description="Acquirer already operates in the geographies that matter for this asset")
    systems_compliance_capability_fit: float = Field(default=0.60, ge=0.0, le=1.0,
        description="Quality systems, PV, regulatory ops, and compliance infrastructure")
    prior_integration_experience: float = Field(default=0.50, ge=0.0, le=1.0,
        description="Track record integrating similar assets (complexity / modality / size)")


class PairIntegrationAdjustment(BaseModel):
    """Pair-specific integration penalty — output of compute_pair_integration_adjustment().

    Feed adjusted_integration_penalty and multiplier into Layer 3 G8.
    Do NOT also apply a Layer 0 penalty — would double-count.
    """
    model_config = ConfigDict(frozen=True)

    acquirer_id: str
    target_id: str = ""

    raw_integration_complexity_score: float = Field(..., ge=0.0, le=1.0)
    buyer_integration_capability: float = Field(..., ge=0.0, le=1.0)
    adjusted_integration_penalty: float = Field(..., ge=0.0, le=1.0)

    # Score multiplier and cap applied to the Layer 3 composite
    multiplier: float = Field(..., ge=0.0, le=1.0)
    max_score_cap: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    pair_level_fail: bool = False

    capability_scores: dict[str, float]
    rationale: list[str]
    data_gaps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Component scoring helpers
# ---------------------------------------------------------------------------

def _product_complexity(n: int) -> float:
    """Integration burden from the number of distinct commercial products."""
    if n <= 0:
        return 0.00
    if n == 1:
        return 0.10   # minimal — single-product ops
    if n == 2:
        return 0.35   # low — two launch/lifecycle plans
    if n <= 5:
        return 0.55   # moderate
    if n <= 10:
        return 0.75   # high
    return 1.00       # severe — portfolio complexity


def _indication_complexity(n: int) -> float:
    """Integration burden from number of disease areas / patient segments."""
    if n <= 1:
        return 0.10
    if n == 2:
        return 0.40
    return 0.70


def _salesforce_burden(required: bool) -> float:
    """Whether the target requires a specialized or novel salesforce."""
    return 0.65 if required else 0.10


_MFG_TRANSFER: dict[str, float] = {"low": 0.15, "medium": 0.50, "high": 0.85}
_GEO: dict[str, float] = {"local": 0.10, "regional": 0.45, "global": 0.80}
_PAYER: dict[str, float] = {"low": 0.10, "medium": 0.50, "high": 0.85}


def _channel_complexity(salesforce_required: bool, payer_level: str) -> float:
    """Inferred distribution / channel complexity.

    Combines payer access friction with whether a specialty channel/salesforce
    is needed. High payer friction + specialty sales = severe channel burden.
    """
    payer_score = _PAYER.get(payer_level, 0.50)
    # Weighted: payer drives 60%, salesforce presence adds up to 30%
    raw = payer_score * 0.60 + (0.30 if salesforce_required else 0.05)
    return min(1.0, raw)


def _systems_compliance_risk(
    mfg_level: str,
    has_co_development_obligation: bool,
    has_manufacturing_dependency: bool,
) -> float:
    """Risk that post-close systems / compliance transfer will be complex.

    Higher for complex manufacturing processes, co-development partners with
    shared infrastructure, and single-CDMO / single-vendor dependencies.
    """
    base = {"low": 0.10, "medium": 0.35, "high": 0.60}.get(mfg_level, 0.35)
    if has_co_development_obligation:
        base += 0.15   # shared ops with a third party must be untangled
    if has_manufacturing_dependency:
        base += 0.10   # single-CDMO dependency complicates transition
    return min(1.0, base)


# Component weights (must sum to 1.0)
_COMPONENT_WEIGHTS: dict[str, float] = {
    "product_complexity":                  0.15,
    "indication_complexity":               0.10,
    "salesforce_burden":                   0.15,
    "manufacturing_transfer_complexity":   0.15,
    "geographic_complexity":               0.15,
    "payer_access_complexity":             0.15,
    "channel_complexity":                  0.10,
    "systems_compliance_transfer_risk":    0.05,
}
assert abs(sum(_COMPONENT_WEIGHTS.values()) - 1.0) < 1e-9


def _complexity_level(score: float) -> IntegrationComplexityLevel:
    if score < 0.25:
        return IntegrationComplexityLevel.LOW
    if score < 0.45:
        return IntegrationComplexityLevel.MODERATE
    if score < 0.65:
        return IntegrationComplexityLevel.HIGH
    return IntegrationComplexityLevel.SEVERE


# ---------------------------------------------------------------------------
# Layer 0E — Target complexity flag
# ---------------------------------------------------------------------------

def compute_target_integration_complexity(
    target: object,
    context: object = None,
) -> TargetIntegrationComplexityFlag:
    """Compute the 8-component target-level integration complexity flag (Layer 0E).

    Uses only target-level fields — no acquirer identity needed.
    Infers channel_complexity and systems_compliance_transfer_risk from available
    signals. Missing / unknown fields produce conservative estimates + data_gaps.

    Returns TargetIntegrationComplexityFlag with:
      - raw_integration_complexity_score (0–1)
      - complexity_level (LOW / MODERATE / HIGH / SEVERE)
      - component_scores (dict for transparency)
      - complexity_flags (shorthand codes)
      - integration_risk_drivers (human-readable rationale fragments)
      - requires_buyer_capability_check (True when MODERATE or above)
      - data_gaps (fields that were inferred conservatively)
    """
    def _g(attr: str, default):
        return getattr(target, attr, default)

    product_count = _g("product_count", 1)
    indication_count = _g("indication_count", 1)
    salesforce_req = _g("salesforce_required", False)
    mfg_level = _g("manufacturing_complexity", "low")
    geo_level = _g("geographic_complexity", "local")
    payer_level = _g("payer_access_complexity", "low")
    has_cdev = _g("has_co_development_obligation", False)
    has_mfg_dep = _g("has_manufacturing_dependency", False)

    data_gaps: list[str] = []
    # Flag when key complexity signals are absent (defaults used conservatively)
    if not hasattr(target, "product_count"):
        data_gaps.append("product_count: not provided; defaulting to 1")
    if not hasattr(target, "salesforce_required"):
        data_gaps.append("salesforce_required: not provided; assuming not required")

    # Score each component
    comp: dict[str, float] = {
        "product_complexity":                  _product_complexity(product_count),
        "indication_complexity":               _indication_complexity(indication_count),
        "salesforce_burden":                   _salesforce_burden(salesforce_req),
        "manufacturing_transfer_complexity":   _MFG_TRANSFER.get(mfg_level, 0.50),
        "geographic_complexity":               _GEO.get(geo_level, 0.45),
        "payer_access_complexity":             _PAYER.get(payer_level, 0.50),
        "channel_complexity":                  _channel_complexity(salesforce_req, payer_level),
        "systems_compliance_transfer_risk":    _systems_compliance_risk(
                                                   mfg_level, has_cdev, has_mfg_dep),
    }

    raw_score = round(
        min(1.0, sum(comp[k] * _COMPONENT_WEIGHTS[k] for k in _COMPONENT_WEIGHTS)),
        4,
    )

    level = _complexity_level(raw_score)
    requires_check = level != IntegrationComplexityLevel.LOW

    # Build flags and risk driver narrative
    flags: list[str] = []
    drivers: list[str] = []

    if comp["product_complexity"] >= 0.55:
        flags.append("multi_product_integration_burden")
        drivers.append(f"product_count={product_count} → multi-product launch/lifecycle ops")
    if comp["indication_complexity"] >= 0.40:
        flags.append("multi_indication_management")
        drivers.append(f"indication_count={indication_count} → multiple patient populations")
    if comp["salesforce_burden"] >= 0.60:
        flags.append("specialty_salesforce_required")
        drivers.append("target requires specialized salesforce / new call points")
    if comp["manufacturing_transfer_complexity"] >= 0.50:
        flags.append("complex_manufacturing_transfer")
        drivers.append(f"manufacturing_complexity={mfg_level} → process transfer risk")
    if comp["geographic_complexity"] >= 0.45:
        flags.append("multi_geography_commercial")
        drivers.append(f"geographic_complexity={geo_level} → multi-region commercial ops")
    if comp["payer_access_complexity"] >= 0.50:
        flags.append("complex_payer_access")
        drivers.append(f"payer_access_complexity={payer_level} → prior auth / reimbursement friction")
    if comp["channel_complexity"] >= 0.45:
        flags.append("complex_distribution_channel")
        drivers.append("specialty pharmacy / buy-and-bill / REMS channel complexity")
    if comp["systems_compliance_transfer_risk"] >= 0.40:
        flags.append("systems_compliance_transfer_risk")
        drivers.append("quality / PV / regulatory file transfer risk post-close")

    rationale: list[str] = [
        f"raw_complexity={raw_score:.3f}  level={level.value}",
        f"product={comp['product_complexity']:.2f}  indication={comp['indication_complexity']:.2f}  "
        f"salesforce={comp['salesforce_burden']:.2f}  mfg={comp['manufacturing_transfer_complexity']:.2f}",
        f"geography={comp['geographic_complexity']:.2f}  payer={comp['payer_access_complexity']:.2f}  "
        f"channel={comp['channel_complexity']:.2f}  systems={comp['systems_compliance_transfer_risk']:.2f}",
    ]
    if requires_check:
        rationale.append(
            "requires_buyer_capability_check=True — downstream Layer 3 G8 will "
            "apply pair-specific integration penalty"
        )

    return TargetIntegrationComplexityFlag(
        raw_integration_complexity_score=raw_score,
        complexity_level=level,
        component_scores=comp,
        complexity_flags=flags,
        integration_risk_drivers=drivers,
        requires_buyer_capability_check=requires_check,
        rationale=rationale,
        data_gaps=data_gaps,
    )


# ---------------------------------------------------------------------------
# Pair-specific integration capability adjustment (feeds Layer 3 G8)
# ---------------------------------------------------------------------------

# Buyer capability formula weights (must sum to 1.0)
_BUYER_CAP_WEIGHTS: dict[str, float] = {
    "commercial_infrastructure_fit":    0.25,
    "manufacturing_capability_fit":     0.20,
    "payer_access_capability_fit":      0.20,
    "geographic_footprint_fit":         0.15,
    "systems_compliance_capability_fit": 0.10,
    "prior_integration_experience":     0.10,
}
assert abs(sum(_BUYER_CAP_WEIGHTS.values()) - 1.0) < 1e-9

# Treatment table for adjusted_integration_penalty → (multiplier, max_cap, pair_fail)
_PENALTY_TREATMENT: list[tuple[float, float, Optional[float], bool]] = [
    # (upper_bound_inclusive, multiplier, max_score_cap, pair_level_fail)
    (0.15, 1.00, None,  False),
    (0.30, 0.95, None,  False),
    (0.50, 0.85, None,  False),
    (0.70, 0.70, 0.60,  False),
    (1.00, 0.50, 0.50,  False),   # >0.70 → pair_level_fail if capability < 0.25
]


def _penalty_treatment(
    penalty: float,
    buyer_capability: float,
) -> tuple[float, Optional[float], bool]:
    """Return (multiplier, max_score_cap, pair_level_fail) for a given penalty."""
    for upper, mult, cap, _ in _PENALTY_TREATMENT:
        if penalty <= upper:
            # pair_level_fail when penalty is extreme AND buyer has no capability
            fail = (penalty > 0.70 and buyer_capability < 0.25)
            return mult, cap, fail
    return 0.50, 0.50, True


def compute_pair_integration_adjustment(
    target_complexity: TargetIntegrationComplexityFlag,
    acquirer_profile: AcquirerIntegrationProfile,
    context: object = None,
) -> PairIntegrationAdjustment:
    """Compute the pair-specific integration penalty for Layer 3 G8.

    Formula:
        buyer_integration_capability =
            0.25 × commercial_infrastructure_fit
          + 0.20 × manufacturing_capability_fit
          + 0.20 × payer_access_capability_fit
          + 0.15 × geographic_footprint_fit
          + 0.10 × systems_compliance_capability_fit
          + 0.10 × prior_integration_experience

        adjusted_integration_penalty =
            raw_integration_complexity_score × (1 − buyer_integration_capability)

    This result should be fed to GateInputs.adjusted_integration_penalty in Layer 3.
    DO NOT also apply a Layer 0 complexity penalty — that would double-count.
    """
    cap_scores: dict[str, float] = {
        "commercial_infrastructure_fit":    acquirer_profile.commercial_infrastructure_fit,
        "manufacturing_capability_fit":     acquirer_profile.manufacturing_capability_fit,
        "payer_access_capability_fit":      acquirer_profile.payer_access_capability_fit,
        "geographic_footprint_fit":         acquirer_profile.geographic_footprint_fit,
        "systems_compliance_capability_fit": acquirer_profile.systems_compliance_capability_fit,
        "prior_integration_experience":     acquirer_profile.prior_integration_experience,
    }

    buyer_cap = round(
        sum(cap_scores[k] * _BUYER_CAP_WEIGHTS[k] for k in _BUYER_CAP_WEIGHTS),
        4,
    )

    raw = target_complexity.raw_integration_complexity_score
    penalty = round(raw * (1.0 - buyer_cap), 4)

    mult, cap, fail = _penalty_treatment(penalty, buyer_cap)

    rationale: list[str] = [
        f"raw_complexity={raw:.3f}  buyer_capability={buyer_cap:.3f}  "
        f"adjusted_penalty={penalty:.3f}",
        f"multiplier={mult:.2f}  cap={cap}  pair_fail={fail}",
    ]
    if target_complexity.complexity_level != IntegrationComplexityLevel.LOW:
        rationale.append(
            f"target_complexity_level={target_complexity.complexity_level.value}  "
            f"risk_drivers={len(target_complexity.integration_risk_drivers)}"
        )
    if fail:
        rationale.append(
            f"pair_level_fail: penalty={penalty:.2f} > 0.70 AND "
            f"buyer_capability={buyer_cap:.2f} < 0.25 — buyer lacks core integration capability"
        )

    return PairIntegrationAdjustment(
        acquirer_id=acquirer_profile.acquirer_id,
        raw_integration_complexity_score=raw,
        buyer_integration_capability=buyer_cap,
        adjusted_integration_penalty=penalty,
        multiplier=mult,
        max_score_cap=cap,
        pair_level_fail=fail,
        capability_scores=cap_scores,
        rationale=rationale,
    )
