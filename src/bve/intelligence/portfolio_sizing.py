"""
Wave P — Portfolio Sizing Framework.

Converts ranked opportunities into dollar-weighted position allocations via a
rules-based sizing engine.  Designed to complement the PortfolioRankingEngine
(which orders assets) by answering "how much of each position to hold."

Sizing logic
------------
1. Filter the ranked opportunity list to the top-N eligible positions
   (min composite score gate, concentration limits).
2. Compute a raw Kelly weight per position:
   - When mispricing_score is available: half-Kelly = 0.5 × mispricing_score
     (mispricing_score > 0 = undervalued, represents the edge fraction)
   - When mispricing_score is absent: fall back to proportional composite_score
3. Clip each weight to [min_position_pct, max_position_pct].
4. Apply concentration guardrails (same indication, same company).
5. Normalise to sum ≤ 100% (cash buffer = 1 − sum of weights).

The result is a ``PortfolioAllocation`` with a list of ``PositionAllocation``
objects that can be passed directly to a broker or paper-trading system.

No external API calls.  All inputs come from the opportunity ranking layer.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class PositionSizeRules(BaseModel):
    """
    Analyst-configurable sizing guardrails.

    Attributes
    ----------
    kelly_fraction:
        Scaling factor applied to the raw Kelly weight.  0.5 = half-Kelly
        (default).  0.0 disables Kelly and falls back to equal-weight.
    max_position_pct:
        Hard cap on any single position as a fraction of AUM.  Default 0.20.
    min_position_pct:
        Minimum weight for any included position.  Default 0.01.
    max_concentration_pct:
        Maximum combined weight across positions sharing the same indication
        *or* company.  Default 0.40.
    max_n_positions:
        Maximum number of positions to allocate.  Default 20.
    min_composite_score:
        Positions with composite_score below this threshold are excluded.
        Default 0.0 (no filter).
    cash_buffer_pct:
        Minimum fraction of AUM to keep as cash (unallocated).  Default 0.05.
    """

    model_config = {"frozen": True}

    kelly_fraction: float = Field(default=0.5, ge=0.0, le=1.0)
    max_position_pct: float = Field(default=0.20, gt=0.0, le=1.0)
    min_position_pct: float = Field(default=0.01, ge=0.0, lt=1.0)
    max_concentration_pct: float = Field(default=0.40, gt=0.0, le=1.0)
    max_n_positions: int = Field(default=20, ge=1)
    min_composite_score: float = Field(default=0.0)
    cash_buffer_pct: float = Field(default=0.05, ge=0.0, lt=1.0)


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class PositionAllocation(BaseModel):
    """Single position within a portfolio allocation."""

    model_config = {"frozen": True}

    asset_id: str
    ticker: Optional[str]
    rank: int
    weight: float               # fraction of AUM, post-normalisation
    dollar_amount_millions: Optional[float]   # None when portfolio_aum is None
    composite_score: float
    mispricing_score: Optional[float]
    raw_kelly_weight: float     # pre-clip, pre-normalise weight
    sizing_method: str          # "half_kelly" | "proportional" | "equal_weight"


class PortfolioAllocation(BaseModel):
    """Full portfolio allocation from one sizing run."""

    model_config = {"frozen": True}

    rules: PositionSizeRules
    positions: list[PositionAllocation] = Field(default_factory=list)
    portfolio_aum_millions: Optional[float]
    total_weight: float = 0.0       # sum of position weights
    cash_weight: float = 1.0        # 1 - total_weight
    n_positions: int = 0
    n_excluded_score: int = 0       # excluded by min_composite_score
    n_excluded_concentration: int = 0
    n_excluded_max_positions: int = 0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class PortfolioSizingEngine:
    """
    Compute position allocations from a ranked opportunity list.

    Parameters
    ----------
    rules:
        Sizing guardrails.  Defaults to ``PositionSizeRules()``.
    """

    def __init__(self, rules: Optional[PositionSizeRules] = None) -> None:
        self.rules = rules or PositionSizeRules()

    def size(
        self,
        opportunities: list[Any],
        *,
        portfolio_aum_millions: Optional[float] = None,
    ) -> PortfolioAllocation:
        """
        Convert ranked opportunities into position allocations.

        Parameters
        ----------
        opportunities:
            List of ``RankedOpportunity`` (or any object with
            ``asset_id``, ``composite_score``, and optionally
            ``ticker``, ``rank``, ``mispricing_score``).
        portfolio_aum_millions:
            Total AUM in $M.  When provided, ``dollar_amount_millions`` is
            populated on each position.  When None, only weights are computed.

        Returns
        -------
        PortfolioAllocation
        """
        r = self.rules

        # Step 1: filter by composite score
        n_excluded_score = 0
        eligible = []
        for opp in sorted(
            opportunities,
            key=lambda o: getattr(o, "composite_score", 0.0),
            reverse=True,
        ):
            cs = getattr(opp, "composite_score", 0.0)
            if cs < r.min_composite_score:
                n_excluded_score += 1
                continue
            eligible.append(opp)

        # Step 2: concentration guard — track per-indication and per-company weights
        indication_weight: dict[str, float] = {}
        company_weight: dict[str, float] = {}
        positions: list[PositionAllocation] = []
        n_excluded_concentration = 0
        n_excluded_max_positions = 0

        for opp in eligible:
            if len(positions) >= r.max_n_positions:
                n_excluded_max_positions += len(eligible) - len(positions) - n_excluded_concentration
                break

            asset_id = getattr(opp, "asset_id", "")
            company_id = getattr(opp, "company_id", "")
            indication = getattr(opp, "indication", None) or asset_id  # fallback key
            composite_score = float(getattr(opp, "composite_score", 0.0))
            mispricing = getattr(opp, "mispricing_score", None)
            rank = getattr(opp, "rank", len(positions) + 1)

            # Compute raw Kelly weight
            raw_weight, method = self._raw_weight(composite_score, mispricing, r)

            # Clip to [min, max]
            clipped = max(r.min_position_pct, min(r.max_position_pct, raw_weight))

            # Check concentration constraints
            ind_used = indication_weight.get(indication, 0.0)
            cmp_used = company_weight.get(company_id, 0.0)
            if (ind_used + clipped > r.max_concentration_pct or
                    cmp_used + clipped > r.max_concentration_pct):
                # Reduce to headroom
                headroom = min(
                    r.max_concentration_pct - ind_used,
                    r.max_concentration_pct - cmp_used,
                    r.max_position_pct,
                )
                if headroom < r.min_position_pct:
                    n_excluded_concentration += 1
                    continue
                clipped = headroom

            indication_weight[indication] = indication_weight.get(indication, 0.0) + clipped
            company_weight[company_id] = company_weight.get(company_id, 0.0) + clipped

            dollar = None
            if portfolio_aum_millions is not None:
                dollar = round(clipped * portfolio_aum_millions, 4)

            positions.append(
                PositionAllocation(
                    asset_id=asset_id,
                    ticker=getattr(opp, "ticker", None),
                    rank=rank,
                    weight=round(clipped, 6),
                    dollar_amount_millions=dollar,
                    composite_score=composite_score,
                    mispricing_score=(
                        float(mispricing) if mispricing is not None else None
                    ),
                    raw_kelly_weight=round(raw_weight, 6),
                    sizing_method=method,
                )
            )

        # Step 3: normalise to cash buffer constraint
        total_w = sum(p.weight for p in positions)
        max_total = 1.0 - r.cash_buffer_pct
        if total_w > max_total and total_w > 0:
            scale = max_total / total_w
            scaled: list[PositionAllocation] = []
            for p in positions:
                new_w = round(p.weight * scale, 6)
                new_d = (
                    round(new_w * portfolio_aum_millions, 4)
                    if portfolio_aum_millions is not None
                    else None
                )
                scaled.append(p.model_copy(update={"weight": new_w, "dollar_amount_millions": new_d}))
            positions = scaled
            total_w = sum(p.weight for p in positions)

        return PortfolioAllocation(
            rules=r,
            positions=positions,
            portfolio_aum_millions=portfolio_aum_millions,
            total_weight=round(total_w, 6),
            cash_weight=round(1.0 - total_w, 6),
            n_positions=len(positions),
            n_excluded_score=n_excluded_score,
            n_excluded_concentration=n_excluded_concentration,
            n_excluded_max_positions=n_excluded_max_positions,
        )

    @staticmethod
    def _raw_weight(
        composite_score: float,
        mispricing_score: Optional[float],
        rules: PositionSizeRules,
    ) -> tuple[float, str]:
        """
        Compute raw (pre-clip) weight and name the method used.

        Returns (weight, method_name).
        """
        if rules.kelly_fraction > 0 and mispricing_score is not None:
            # Half-Kelly: edge = mispricing_score (fraction of intrinsic value above market)
            # Biotech Kelly: f = kelly_fraction × max(0, mispricing_score)
            raw = rules.kelly_fraction * max(0.0, float(mispricing_score))
            if raw > 0:
                return raw, "half_kelly"

        if composite_score > 0:
            # Proportional to composite score, scaled to max_position_pct
            raw = rules.max_position_pct * (
                composite_score / max(composite_score, 1.0)
            )
            return raw, "proportional"

        # Equal weight fallback
        return rules.min_position_pct, "equal_weight"


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def compute_portfolio_allocation(
    opportunities: list[Any],
    *,
    portfolio_aum_millions: Optional[float] = None,
    rules: Optional[PositionSizeRules] = None,
) -> PortfolioAllocation:
    """
    One-call convenience wrapper around PortfolioSizingEngine.

    Parameters
    ----------
    opportunities:
        Ranked opportunity list (list of ``RankedOpportunity`` or compatible).
    portfolio_aum_millions:
        Total portfolio AUM in $M (optional).
    rules:
        Sizing rules; defaults to ``PositionSizeRules()``.

    Returns
    -------
    PortfolioAllocation
    """
    return PortfolioSizingEngine(rules).size(
        opportunities,
        portfolio_aum_millions=portfolio_aum_millions,
    )
