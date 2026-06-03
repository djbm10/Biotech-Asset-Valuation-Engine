"""Size a position given portfolio context, conviction, and risk budget."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PositionSizerInput(BaseModel):
    asset_id: str
    asymmetry_score: float  # composite score
    conviction: float = Field(ge=0.0, le=1.0)  # 0-1 analyst conviction
    portfolio_nav: float  # total NAV in USD
    current_position_pct: float = 0.0  # existing exposure as % of NAV
    max_single_position_pct: float = 0.08  # hard cap, default 8%
    max_sector_pct: float = 0.30  # biotech sector cap
    current_sector_pct: float = 0.0  # existing sector exposure
    liquidity_adtv_millions: Optional[float] = None  # average daily trading volume
    financing_risk_tier: Optional[str] = None  # "low"|"medium"|"high"|"distress"


class PositionSizeResult(BaseModel):
    asset_id: str
    target_position_pct: float  # recommended new total position %
    incremental_position_pct: float  # how much to add/remove from current
    position_dollars: float  # incremental in dollar terms
    sizing_rationale: str
    risk_adjustments: list[str] = Field(default_factory=list)
    capped_by: Optional[str] = None  # which constraint bound the size


class PositionSizer:
    """
    Kelly-inspired fractional position sizer with hard caps.

    Base size formula:
        base_pct = asymmetry_score * conviction * base_scale
        where base_scale = 0.10 (so max uncapped = 10% at score=1.0, conviction=1.0)

    Adjustments (multiplicative):
        - financing_risk_tier == "high"    → multiply by 0.50
        - financing_risk_tier == "distress"→ multiply by 0.10
        - liquidity_adtv < 2M             → multiply by 0.50 (illiquidity haircut)
        - liquidity_adtv < 5M             → multiply by 0.75

    Hard caps (binding):
        - max_single_position_pct (default 8%)
        - sector headroom: max_sector_pct - current_sector_pct
        - minimum: if target < 0.005 (50bps) → set to 0 (not worth the friction)

    Incremental = target - current_position_pct (can be negative = trim)
    position_dollars = incremental * portfolio_nav
    """

    BASE_SCALE: float = 0.10

    def size(self, inp: PositionSizerInput) -> PositionSizeResult:
        """Compute target and incremental position size."""
        risk_adjustments: list[str] = []

        # Base size
        base_pct = inp.asymmetry_score * inp.conviction * self.BASE_SCALE

        # Multiplicative adjustments
        adjustment_multiplier = 1.0

        if inp.financing_risk_tier == "distress":
            adjustment_multiplier *= 0.10
            risk_adjustments.append("financing_risk_tier=distress: 0.10x multiplier applied")
        elif inp.financing_risk_tier == "high":
            adjustment_multiplier *= 0.50
            risk_adjustments.append("financing_risk_tier=high: 0.50x multiplier applied")

        if inp.liquidity_adtv_millions is not None:
            if inp.liquidity_adtv_millions < 2.0:
                adjustment_multiplier *= 0.50
                risk_adjustments.append(f"liquidity_adtv={inp.liquidity_adtv_millions:.1f}M < 2M: 0.50x illiquidity haircut")
            elif inp.liquidity_adtv_millions < 5.0:
                adjustment_multiplier *= 0.75
                risk_adjustments.append(f"liquidity_adtv={inp.liquidity_adtv_millions:.1f}M < 5M: 0.75x liquidity haircut")

        adjusted_pct = base_pct * adjustment_multiplier

        # Hard caps
        capped_by: Optional[str] = None

        # Sector headroom cap
        sector_headroom = inp.max_sector_pct - inp.current_sector_pct
        # Sector headroom applies to incremental addition only; bound the target
        max_allowed_by_sector = inp.current_position_pct + max(sector_headroom, 0.0)

        # Single position cap
        single_cap = inp.max_single_position_pct

        effective_cap = min(single_cap, max_allowed_by_sector)

        if adjusted_pct > effective_cap:
            if effective_cap == single_cap and max_allowed_by_sector >= single_cap:
                capped_by = "max_single_position_pct"
            elif max_allowed_by_sector < single_cap:
                capped_by = "sector_headroom"
            else:
                capped_by = "max_single_position_pct"
            adjusted_pct = effective_cap

        # Allow negative target (trimming) to go as low as 0
        if adjusted_pct < 0:
            adjusted_pct = max(adjusted_pct, 0.0)

        # Minimum threshold — below 50bps is not worth the friction
        if 0 < adjusted_pct < 0.005:
            risk_adjustments.append("target_pct < 50bps: zeroed out (below minimum friction threshold)")
            adjusted_pct = 0.0

        target_position_pct = adjusted_pct
        incremental_position_pct = target_position_pct - inp.current_position_pct
        position_dollars = incremental_position_pct * inp.portfolio_nav

        rationale_parts = [
            f"base={inp.asymmetry_score:.3f} * conviction={inp.conviction:.2f} * scale={self.BASE_SCALE:.2f} = {base_pct:.4f}",
            f"adj_multiplier={adjustment_multiplier:.2f}",
            f"target={target_position_pct:.4f}",
        ]
        if capped_by:
            rationale_parts.append(f"capped_by={capped_by}")

        return PositionSizeResult(
            asset_id=inp.asset_id,
            target_position_pct=round(target_position_pct, 6),
            incremental_position_pct=round(incremental_position_pct, 6),
            position_dollars=round(position_dollars, 2),
            sizing_rationale="; ".join(rationale_parts),
            risk_adjustments=risk_adjustments,
            capped_by=capped_by,
        )
