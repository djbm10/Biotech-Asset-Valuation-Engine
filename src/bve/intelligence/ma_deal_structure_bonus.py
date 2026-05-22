"""
Deal-Structure Residual Bonus — Phase 4C experimental additive signal.

Computes a small additive bonus (max +0.08) from deal-structure signals that are
NOT already captured in the existing scoring pipeline:

  Layer 0  — encumbrance multiplier, distress guard cap
  Layer 1  — acquirer TA fit, strategic fit
  Layer 3A — asset quality gates
  Layer 3B — pair asset-control combination

Explicitly excluded signals (these are already priced in upstream):
  × acquirer_ta_fit            → Layer 1 strategic fit
  × financing_pressure_high    → Layer 0 distress guard
  × royalty_stack_rate         → Layer 0 encumbrance multiplier
  × distress_flag              → Layer 0 distress guard
  × asset_quality proxies      → Layer 3A quality gates
  × encumbrance signals        → Layer 0

Allowed residual signals:
  ✓ platform breadth / repeatability of the TARGET platform technology
  ✓ number of meaningful related pipeline assets (product_count, indication_count)
  ✓ approved_revenue_share (ONLY when explicitly supplied; None → no contribution)
  ✓ commercial franchise breadth (distinct commercial lines)
  ✓ pipeline-in-a-product flag (single asset with multiple mechanisms / indications)

Formula
-------
  residual_structure_score = weighted average of available components

  deal_structure_residual_bonus = 0.08 × residual_structure_score

  final_score_with_structure_bonus = min(1.0, final_score + deal_structure_residual_bonus)

Rules
-----
  • Bonus can NEVER reduce final_score (additive-only).
  • Bonus is 0.0 when no residual inputs are provided.
  • Bonus is 0.0 when enable_deal_structure_bonus=False (config-gated).
  • Bonus does NOT override hard fails (PASS, DATA_INSUFFICIENT, HISTORICAL_ONLY, any score cap).
  • blended_deal_type_score (Phase 4B) remains memo-only and is kept separate.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Cap constant
# ---------------------------------------------------------------------------

_MAX_BONUS: float = 0.08


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class DealStructureResidualInputs(BaseModel):
    """Non-overlapping residual deal-structure signals.

    All signal fields are Optional so that "data not available" is
    distinguishable from an explicitly provided zero value.  When a field is
    None it is excluded from the weighted average; the remaining weights are
    renormalized.  This prevents penalising licensing or distressed targets
    for missing commercial-franchise or platform data.

    Key design invariant: none of these fields duplicate signals already
    consumed by Layer 0 encumbrance, Layer 0 distress guard, Layer 1 TA fit,
    or Layer 3A quality gates.
    """
    model_config = ConfigDict(frozen=True)

    # ── Platform residual ──────────────────────────────────────────────────────
    # Breadth and repeatability of the TARGET's platform technology.
    # Not captured by Layer 0 (which scores acquirer fit, not platform width).
    is_platform_company: bool = Field(
        default=False,
        description="True when the target has a platform technology, not just a single asset",
    )
    platform_breadth: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="0–1 breadth and tractability of platform technology. "
                    "None = unknown; excluded from scoring when absent.",
    )
    platform_validated: Optional[bool] = Field(
        default=None,
        description="True when platform has ≥1 clinical PoC dataset. "
                    "None = unknown; treated as False when scoring.",
    )

    # ── Pipeline breadth residual ──────────────────────────────────────────────
    # Number of distinct pipeline products and indications.
    # Not captured in any existing scoring layer.
    product_count: Optional[int] = Field(
        default=None, ge=0,
        description="Number of distinct products in the development pipeline. "
                    "None = unknown; excluded when absent.",
    )
    indication_count: Optional[int] = Field(
        default=None, ge=0,
        description="Number of indications pursued across all products. "
                    "None = unknown; excluded when absent.",
    )

    # ── Approved-revenue residual ──────────────────────────────────────────────
    # Fraction of EV from approved-product revenue.
    # CRITICAL: Optional — None means "data not available" and contributes 0
    # weight.  This prevents falsely penalising a pipeline-only target that
    # has no approved revenue (not the same as a target with approved revenue
    # that happens to be zero).
    approved_revenue_share: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Fraction of enterprise value from approved-product revenue. "
                    "None = unknown; excluded from scoring when absent.",
    )

    # ── Commercial franchise breadth ───────────────────────────────────────────
    # Number of distinct commercial product lines / market segments.
    # Captures franchise diversification not reflected in encumbrance scoring.
    commercial_franchise_breadth: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="0–1 normalised breadth of commercial product lines "
                    "(e.g. 0.25 = 1 product line, 1.0 = 4+ distinct lines). "
                    "None = unknown; excluded when absent.",
    )

    # ── Pipeline-in-a-product flag ─────────────────────────────────────────────
    # A single asset that functions like a platform (e.g. bispecific with multiple
    # indications, combination therapy designed for label expansion).
    # Structural deal-type complexity signal not scored elsewhere.
    pipeline_in_a_product: bool = Field(
        default=False,
        description="True when the lead asset is designed with multiple indications "
                    "or mechanisms and creates option value beyond its primary indication",
    )


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class DealStructureResidualResult(BaseModel):
    """Result of compute_deal_structure_residual_bonus()."""
    model_config = ConfigDict(frozen=True)

    residual_structure_score: float = Field(..., ge=0.0, le=1.0,
        description="Weighted average of residual components; 0.0 when no inputs provided")
    deal_structure_residual_bonus: float = Field(..., ge=0.0, le=_MAX_BONUS,
        description=f"Additive bonus = {_MAX_BONUS} × residual_structure_score; "
                    f"capped at +{_MAX_BONUS}")
    components_scored: dict[str, float] = Field(default_factory=dict,
        description="Components that had data; key=component_name, value=raw_score (0–1)")
    components_missing: list[str] = Field(default_factory=list,
        description="Component names excluded because their input was None")
    bonus_enabled: bool = Field(default=False,
        description="Whether the enable_deal_structure_bonus config flag was set")
    rationale: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Component weights (full formula — renormalized when inputs are absent)
# ---------------------------------------------------------------------------

# Base weights; must sum to 1.0.
_COMPONENT_WEIGHTS: dict[str, float] = {
    "platform_residual": 0.35,
    "breadth_residual":  0.30,
    "revenue_residual":  0.20,
    "franchise_residual": 0.05,
    "pip_flag":          0.10,
}


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def compute_deal_structure_residual_bonus(
    inp: DealStructureResidualInputs,
) -> DealStructureResidualResult:
    """Compute the deal-structure residual bonus from non-overlapping signals.

    Returns a DealStructureResidualResult.  The caller is responsible for:
      1. Checking enable_deal_structure_bonus before adding the bonus to final_score.
      2. Ensuring the bonus is NOT applied to hard-fail classes (PASS,
         DATA_INSUFFICIENT, HISTORICAL_ONLY).
      3. Capping final_score_with_structure_bonus at 1.0.
    """
    scored: dict[str, float] = {}
    missing: list[str] = []
    rationale: list[str] = []

    # ── Platform residual ──────────────────────────────────────────────────────
    if inp.is_platform_company and inp.platform_breadth is not None:
        validation_bonus = 0.40 if (inp.platform_validated is True) else 0.0
        platform_score = 0.60 * inp.platform_breadth + validation_bonus
        platform_score = min(1.0, max(0.0, platform_score))
        scored["platform_residual"] = platform_score
        rationale.append(
            f"platform_residual={platform_score:.3f} "
            f"(breadth={inp.platform_breadth:.2f}, "
            f"validated={inp.platform_validated})"
        )
    elif not inp.is_platform_company:
        # Target is not a platform company — component does not apply
        missing.append("platform_residual")
        rationale.append("platform_residual: skipped (is_platform_company=False)")
    else:
        # is_platform_company=True but platform_breadth not provided
        missing.append("platform_residual")
        rationale.append("platform_residual: skipped (platform_breadth=None)")

    # ── Pipeline breadth residual ──────────────────────────────────────────────
    if inp.product_count is not None and inp.indication_count is not None:
        product_norm = min(1.0, inp.product_count / 5.0)
        indication_norm = min(1.0, inp.indication_count / 4.0)
        breadth_score = 0.50 * product_norm + 0.50 * indication_norm
        # Breadth bonus only starts above a single-asset single-indication baseline
        breadth_score = max(0.0, breadth_score - 0.10)   # subtract single-asset baseline
        breadth_score = min(1.0, breadth_score)
        scored["breadth_residual"] = breadth_score
        rationale.append(
            f"breadth_residual={breadth_score:.3f} "
            f"({inp.product_count} products, {inp.indication_count} indications)"
        )
    else:
        missing.append("breadth_residual")
        rationale.append(
            "breadth_residual: skipped "
            f"(product_count={inp.product_count}, indication_count={inp.indication_count})"
        )

    # ── Approved-revenue residual ──────────────────────────────────────────────
    # Only scored when explicitly provided AND > 0.
    # None = data gap → no contribution and no penalty.
    if inp.approved_revenue_share is not None and inp.approved_revenue_share > 0.0:
        scored["revenue_residual"] = inp.approved_revenue_share
        rationale.append(
            f"revenue_residual={inp.approved_revenue_share:.3f} "
            "(approved_revenue_share explicitly provided)"
        )
    else:
        missing.append("revenue_residual")
        if inp.approved_revenue_share is None:
            rationale.append("revenue_residual: skipped (approved_revenue_share=None, data gap)")
        else:
            rationale.append("revenue_residual: skipped (approved_revenue_share=0.0, pipeline-only)")

    # ── Commercial franchise breadth ───────────────────────────────────────────
    if inp.commercial_franchise_breadth is not None and inp.commercial_franchise_breadth > 0.0:
        scored["franchise_residual"] = inp.commercial_franchise_breadth
        rationale.append(
            f"franchise_residual={inp.commercial_franchise_breadth:.3f} "
            "(commercial_franchise_breadth explicitly provided)"
        )
    else:
        missing.append("franchise_residual")
        rationale.append(
            "franchise_residual: skipped "
            f"(commercial_franchise_breadth={inp.commercial_franchise_breadth})"
        )

    # ── Pipeline-in-a-product flag ─────────────────────────────────────────────
    if inp.pipeline_in_a_product:
        scored["pip_flag"] = 1.0
        rationale.append("pip_flag=1.0 (pipeline_in_a_product=True)")
    else:
        # pip_flag contributes 0 — does not produce a bonus, but also not a penalty
        # Still counted as "scored" at 0.0 so weight is included in denominator
        scored["pip_flag"] = 0.0
        rationale.append("pip_flag=0.0 (pipeline_in_a_product=False)")

    # ── Weighted average of scored components ──────────────────────────────────
    active_weights = {
        k: _COMPONENT_WEIGHTS[k]
        for k in scored
    }
    total_weight = sum(active_weights.values())

    if total_weight == 0.0 or not scored:
        residual_score = 0.0
        rationale.append("residual_structure_score=0.0 (no residual data available)")
    else:
        # Renormalize to the active component weights
        residual_score = sum(
            scored[k] * (w / total_weight)
            for k, w in active_weights.items()
        )
        residual_score = min(1.0, max(0.0, residual_score))
        rationale.append(
            f"residual_structure_score={residual_score:.4f} "
            f"(active_components={list(scored.keys())}, "
            f"renormalized_weight={total_weight:.2f})"
        )

    bonus = min(_MAX_BONUS, _MAX_BONUS * residual_score)
    rationale.append(
        f"deal_structure_residual_bonus={bonus:.4f} "
        f"(= {_MAX_BONUS} × {residual_score:.4f})"
    )

    return DealStructureResidualResult(
        residual_structure_score=residual_score,
        deal_structure_residual_bonus=bonus,
        components_scored=dict(scored),
        components_missing=list(missing),
        bonus_enabled=False,  # caller sets this based on config flag
        rationale=rationale,
    )
