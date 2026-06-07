"""Trading friction assumptions for replay validation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrictionModel:
    """Simple round-trip execution cost model for biotech replay trades."""

    entry_timing_delay_days: int = 1
    slippage_bps: float = 12.0
    bid_ask_half_spread_bps: float = 15.0
    commission_bps: float = 1.0
    max_pct_adv: float = 0.05

    @property
    def round_trip_cost_bps(self) -> float:
        """Total round-trip cost in basis points."""
        return 2 * (self.slippage_bps + self.bid_ask_half_spread_bps + self.commission_bps)

    def net_return(self, gross_return_pct: float) -> float:
        """Apply round-trip cost to a gross percent return."""
        return gross_return_pct - self.round_trip_cost_bps / 100.0


INSTITUTIONAL_FRICTIONS = FrictionModel(
    entry_timing_delay_days=1,
    slippage_bps=15.0,
    bid_ask_half_spread_bps=20.0,
    commission_bps=1.0,
)

RETAIL_FRICTIONS = FrictionModel(
    entry_timing_delay_days=0,
    slippage_bps=5.0,
    bid_ask_half_spread_bps=8.0,
    commission_bps=0.5,
)
