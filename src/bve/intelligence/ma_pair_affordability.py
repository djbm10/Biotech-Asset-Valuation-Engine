"""Layer 3A — Pair-Specific Affordability.

This module holds the affordability logic that was previously embedded in
``ma_eligibility.py`` as Layer 0C.

**Why it moved**:
    Affordability requires knowing both the target's EV *and* the specific
    acquirer's balance sheet.  That makes it inherently pair-level — it cannot
    be evaluated at target-only time.  Layer 0 now holds a *target-size
    pre-screen* (``ma_target_size.py``) that annotates size/bucket with no
    score effect.  The actual per-acquirer affordability penalty lives here
    and is applied in Layer 3A scoring.

**Anti-double-counting contract**:
    ``Layer0Result.score_multiplier`` is never derived from affordability.
    The multiplier returned by ``compute_pair_affordability()`` is applied
    exclusively in Layer 3A.  See ``_DOUBLE_COUNT_GUARD_MAP`` in
    ``ma_eligibility.py`` for the canonical record.

**Migration history**:
    - Defined in ``ma_eligibility.py`` as 0C through Phase 1 (Sprint 36).
    - Moved here in Phase 2 (Sprint 37).  Backward-compat re-exports remain
      in ``ma_eligibility.py`` until Phase 3 removes them.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AffordabilityBand(str, Enum):
    """Affordability bracket for a single acquirer-target pair."""
    NO_PENALTY    = "no_penalty"      # cost/capacity ratio ≤ 0.50
    MILD_PENALTY  = "mild_penalty"    # 0.50 < ratio ≤ 0.85
    SEVERE_PENALTY = "severe_penalty" # 0.85 < ratio ≤ 1.10
    HARD_FAIL     = "hard_fail"       # ratio > 1.10


# ---------------------------------------------------------------------------
# (upper_bound_inclusive, band, score_multiplier)
# ---------------------------------------------------------------------------

_AFFORDABILITY_BANDS: list[tuple[float, AffordabilityBand, float]] = [
    (0.50, AffordabilityBand.NO_PENALTY,     1.00),
    (0.85, AffordabilityBand.MILD_PENALTY,   0.90),
    (1.10, AffordabilityBand.SEVERE_PENALTY, 0.60),
    (float("inf"), AffordabilityBand.HARD_FAIL, 0.00),
]


def _affordability_band(ratio: float) -> tuple[AffordabilityBand, float]:
    for upper, band, mult in _AFFORDABILITY_BANDS:
        if ratio <= upper:
            return band, mult
    return AffordabilityBand.HARD_FAIL, 0.00


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class AcquirerCapacityInput(BaseModel):
    """Financial capacity of one potential acquirer for the affordability check.

    Two paths for the stock component:

    **Formula path** (preferred — set ``acquirer_market_cap_millions``):
        realistic_stock_component =
            acquirer_market_cap_millions
            × max_stock_issuance_pct
            × stock_quality_multiplier

        ``stock_quality_multiplier`` is computed from P/B, volatility, and
        dilution tolerance unless supplied directly.

    **Pre-computed path** (backward compat — leave
    ``acquirer_market_cap_millions`` as None):
        ``realistic_stock_component_millions`` is used as-is.
    """

    acquirer_id: str
    cash_available_millions: float = Field(ge=0.0)
    estimated_debt_capacity_millions: float = Field(ge=0.0, default=0.0)
    minimum_balance_buffer_millions: float = Field(ge=0.0, default=0.0)
    expected_takeout_premium: float = Field(ge=0.0, le=2.0, default=0.35)

    # ── Pre-computed path (backward compat) ──────────────────────────────────
    realistic_stock_component_millions: float = Field(
        ge=0.0,
        default=0.0,
        description=(
            "Pre-computed stock deal capacity; used when "
            "acquirer_market_cap_millions is not provided."
        ),
    )

    # ── Formula path: stock-deal realism ─────────────────────────────────────
    acquirer_market_cap_millions: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=(
            "Acquirer market cap; when set, stock component is computed "
            "via formula."
        ),
    )
    max_stock_issuance_pct: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description=(
            "Maximum fraction of market cap the acquirer can realistically "
            "issue as deal consideration without triggering excessive dilution."
        ),
    )

    # Stock quality sub-signals (used to auto-compute stock_quality_multiplier)
    acquirer_price_to_book: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Acquirer P/B ratio; premium valuation → better stock currency.",
    )
    acquirer_stock_volatility_pct: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=(
            "Annualised stock volatility %; high vol → target demands cash premium."
        ),
    )
    investor_dilution_tolerance: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
        description=(
            "How much dilution acquirer shareholders will accept "
            "(0=intolerant, 1=fully tolerant).  Base of the stock quality multiplier."
        ),
    )

    # Override: skip auto-computation and use this value directly
    stock_quality_multiplier: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Explicit stock quality multiplier in [0, 1]. When provided, "
            "P/B and volatility sub-signals are ignored."
        ),
    )


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class AffordabilityResult(BaseModel):
    """Affordability assessment for one acquirer-target pair.

    IMPORTANT — pair-level scope: a HARD_FAIL here removes only this
    specific acquirer-target pair from consideration.  The target remains
    eligible for all other acquirers with sufficient capacity.
    """
    model_config = ConfigDict(frozen=True)

    acquirer_id: str
    expected_acquisition_cost_millions: float
    deal_capacity_millions: float
    affordability_ratio: float
    band: AffordabilityBand
    score_multiplier: float   # 1.0 → 0.90 → 0.60 → 0.0

    # Stock component breakdown
    stock_component_millions: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "Effective stock deal capacity used in this pair "
            "(computed or pre-supplied)."
        ),
    )
    stock_quality_multiplier_applied: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Stock quality multiplier used when formula path was active; "
            "None when pre-computed realistic_stock_component_millions was used."
        ),
    )

    # Pair-level scope note
    pair_scope_note: str = Field(
        default=(
            "Pair-level result: a hard fail excludes only this "
            "acquirer-target pair, not the target globally."
        ),
        description=(
            "Reminder that affordability results are pair-specific, not global."
        ),
    )

    @property
    def is_hard_fail(self) -> bool:
        return self.band == AffordabilityBand.HARD_FAIL

    @property
    def is_pair_level_only(self) -> bool:
        """Always True — affordability gates never exclude a target globally."""
        return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_stock_quality_multiplier(acq: AcquirerCapacityInput) -> float:
    """Derive how much of the theoretical max stock issuance is usable as currency.

    Returns a value in [0.10, 1.0] based on three signals:
      - investor_dilution_tolerance: base (how tolerant shareholders are)
      - acquirer_price_to_book:      premium valuation = stock is valuable currency
      - acquirer_stock_volatility:   high vol = target demands cash; stock discounted

    If ``acq.stock_quality_multiplier`` is provided directly, that value is
    returned as-is (after clamping).  If sub-signals are unavailable, defaults
    produce a neutral 0.50.
    """
    if acq.stock_quality_multiplier is not None:
        return max(0.10, min(1.0, acq.stock_quality_multiplier))

    base = acq.investor_dilution_tolerance  # default 0.50

    pb_adj = 0.0
    if acq.acquirer_price_to_book is not None:
        if acq.acquirer_price_to_book >= 4.0:
            pb_adj = 0.15
        elif acq.acquirer_price_to_book < 1.5:
            pb_adj = -0.20

    vol_adj = 0.0
    if acq.acquirer_stock_volatility_pct is not None:
        if acq.acquirer_stock_volatility_pct < 20.0:
            vol_adj = 0.10
        elif acq.acquirer_stock_volatility_pct > 40.0:
            vol_adj = -0.25
        else:
            vol_adj = -0.10

    return max(0.10, min(1.0, base + pb_adj + vol_adj))


def _effective_stock_component(
    acq: AcquirerCapacityInput,
) -> tuple[float, Optional[float]]:
    """Return (stock_component_millions, sqm_applied).

    When acquirer_market_cap_millions is set, uses the formula:
        stock = market_cap × max_stock_issuance_pct × stock_quality_multiplier

    Otherwise falls back to the pre-supplied realistic_stock_component_millions
    and returns sqm_applied=None (pre-computed path).
    """
    if acq.acquirer_market_cap_millions is not None:
        sqm = _compute_stock_quality_multiplier(acq)
        stock_m = acq.acquirer_market_cap_millions * acq.max_stock_issuance_pct * sqm
        return max(0.0, stock_m), sqm
    return acq.realistic_stock_component_millions, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_pair_affordability(
    target_ev_millions: Optional[float],
    acquirer: AcquirerCapacityInput,
) -> AffordabilityResult:
    """Compute affordability for a single acquirer-target pair.

    Returns an AffordabilityResult with band=HARD_FAIL and
    score_multiplier=0.0 when EV is unknown (cannot assess capacity).
    """
    if target_ev_millions is None:
        return AffordabilityResult(
            acquirer_id=acquirer.acquirer_id,
            expected_acquisition_cost_millions=0.0,
            deal_capacity_millions=0.0,
            affordability_ratio=float("inf"),
            band=AffordabilityBand.HARD_FAIL,
            score_multiplier=0.00,
            pair_scope_note=(
                "Pair-level result: target EV unknown — cannot assess affordability. "
                "Treat as data gap, not hard exclusion."
            ),
        )

    stock_component, sqm_applied = _effective_stock_component(acquirer)
    deal_capacity = max(
        acquirer.cash_available_millions
        + acquirer.estimated_debt_capacity_millions
        + stock_component
        - acquirer.minimum_balance_buffer_millions,
        0.0,
    )
    expected_cost = target_ev_millions * (1.0 + acquirer.expected_takeout_premium)
    ratio = expected_cost / deal_capacity if deal_capacity > 0.0 else float("inf")
    band, mult = _affordability_band(ratio)

    return AffordabilityResult(
        acquirer_id=acquirer.acquirer_id,
        expected_acquisition_cost_millions=round(expected_cost, 2),
        deal_capacity_millions=round(deal_capacity, 2),
        affordability_ratio=round(ratio, 4),
        band=band,
        score_multiplier=mult,
        stock_component_millions=round(stock_component, 2),
        stock_quality_multiplier_applied=(
            round(sqm_applied, 4) if sqm_applied is not None else None
        ),
    )


def compute_pair_affordability_batch(
    target_ev_millions: Optional[float],
    acquirers: list[AcquirerCapacityInput],
) -> list[AffordabilityResult]:
    """Compute per-acquirer affordability for a target.

    Returns empty list when EV is unknown (matching the legacy behaviour of
    the old ``_evaluate_affordability`` function — EV absence means the check
    cannot be performed, not that every acquirer hard-fails).  Use
    ``required_downstream_checks`` (``"affordability_data_required"``) on
    ``Layer0Result`` to surface this data gap to the caller.

    Returns empty list when acquirers is empty.

    Each result is pair-level only: HARD_FAIL for one acquirer does not
    exclude the target from consideration by any other acquirer.
    """
    if target_ev_millions is None:
        return []
    return [compute_pair_affordability(target_ev_millions, acq) for acq in acquirers]


# ---------------------------------------------------------------------------
# Backward-compatibility alias (used by ma_eligibility.py re-export path)
# ---------------------------------------------------------------------------

#: Deprecated name — use compute_pair_affordability_batch instead.
_evaluate_affordability = compute_pair_affordability_batch
