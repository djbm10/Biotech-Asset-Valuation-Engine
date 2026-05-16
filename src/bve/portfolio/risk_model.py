"""Risk model for portfolio sizing calculations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PositionInput:
    """All inputs required to size a position."""

    ticker: str
    expected_return: float          # e.g. 0.30 = 30% expected upside
    downside_case: float            # e.g. -0.50 = 50% downside
    liquidity_usd: float            # average daily volume
    nav_usd: float                  # fund NAV in USD
    event_date_days: int | None     # days until catalyst (None = no catalyst)
    correlation_cluster: str | None # e.g. "oncology_io", "cns"
    confidence_score: float         # 0.0–1.0 model confidence
    max_loss_pct_nav: float         # hard stop as % NAV
    phase: str                      # phase_1 / phase_2 / phase_3 / preclinical
    modality: str                   # e.g. "small_molecule", "antibody"
    catalyst_month: str | None      # YYYY-MM of catalyst


class RiskModel:
    """Computes base position size and liquidity multiplier."""

    def base_size_pct_nav(self, inp: PositionInput) -> float:
        """Kelly-inspired fraction: expected_return / |downside|."""
        if inp.downside_case >= 0:
            return 0.0
        return inp.expected_return / abs(inp.downside_case) * 100.0

    def confidence_multiplier(self, confidence: float) -> float:
        """Scale down size for low-confidence signals."""
        return max(0.25, min(1.0, confidence))

    def liquidity_multiplier(self, liquidity_usd: float, nav_usd: float) -> float:
        """
        Penalty if position would take > min_liquidity_days_to_exit days to exit.
        Assumes 20% ADV is the max we can trade in a day without market impact.
        """
        tradeable_per_day = liquidity_usd * 0.20
        if tradeable_per_day <= 0:
            return 0.0
        # If we can exit in 1 day: multiplier=1.0; 5+ days: multiplier=0.5
        days_to_exit_at_1pct = (nav_usd * 0.01) / tradeable_per_day
        return max(0.5, min(1.0, 1.0 / max(1.0, days_to_exit_at_1pct)))

    def compute_raw_size_pct(self, inp: PositionInput) -> float:
        base = self.base_size_pct_nav(inp)
        adj = base * self.confidence_multiplier(inp.confidence_score)
        liq_mult = self.liquidity_multiplier(inp.liquidity_usd, inp.nav_usd)
        return adj * liq_mult

    def max_loss_contribution_pct(self, size_pct: float, downside_case: float) -> float:
        return size_pct * abs(downside_case) / 100.0
