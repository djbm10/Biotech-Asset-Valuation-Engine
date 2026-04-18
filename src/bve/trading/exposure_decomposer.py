"""Decompose portfolio exposure across multiple dimensions."""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from pydantic import BaseModel, Field


class HoldingRecord(BaseModel):
    asset_id: str
    ticker: str
    position_pct: float  # % of NAV
    therapeutic_area: str  # "oncology" | "rare" | "immunology" | etc.
    phase: str  # "1" | "2" | "3" | "approved"
    has_binary_catalyst: bool  # PDUFA / Ph3 readout within 90d
    days_to_next_catalyst: Optional[int] = None


class ExposureBreakdown(BaseModel):
    by_ta: dict[str, float] = Field(default_factory=dict)  # TA → total %
    by_phase: dict[str, float] = Field(default_factory=dict)  # phase → total %
    binary_risk_pct: float = 0.0  # sum of positions with has_binary_catalyst=True
    near_term_catalyst_pct: float = 0.0  # catalyst within 30d
    concentration_score: float = 0.0  # HHI-based: Σ(position_pct²)
    largest_position_pct: float = 0.0
    num_holdings: int = 0


class ExposureDecomposer:
    """
    Decomposes a list of HoldingRecords into ExposureBreakdown.

    concentration_score: HHI = Σ(pos_pct²) normalized.
        - < 0.10: well-diversified
        - 0.10-0.25: moderate concentration
        - > 0.25: high concentration
    near_term_catalyst_pct: sum of positions where days_to_next_catalyst is not None and <= 30
    """

    def decompose(self, holdings: list[HoldingRecord]) -> ExposureBreakdown:
        """Decompose holdings into an ExposureBreakdown."""
        if not holdings:
            return ExposureBreakdown()

        by_ta: dict[str, float] = defaultdict(float)
        by_phase: dict[str, float] = defaultdict(float)
        binary_risk_pct = 0.0
        near_term_catalyst_pct = 0.0
        hhi = 0.0
        largest = 0.0

        for h in holdings:
            by_ta[h.therapeutic_area] += h.position_pct
            by_phase[h.phase] += h.position_pct

            if h.has_binary_catalyst:
                binary_risk_pct += h.position_pct

            if h.days_to_next_catalyst is not None and h.days_to_next_catalyst <= 30:
                near_term_catalyst_pct += h.position_pct

            hhi += h.position_pct ** 2

            if h.position_pct > largest:
                largest = h.position_pct

        return ExposureBreakdown(
            by_ta=dict(by_ta),
            by_phase=dict(by_phase),
            binary_risk_pct=round(binary_risk_pct, 6),
            near_term_catalyst_pct=round(near_term_catalyst_pct, 6),
            concentration_score=round(hhi, 6),
            largest_position_pct=round(largest, 6),
            num_holdings=len(holdings),
        )

    def concentration_label(self, breakdown: ExposureBreakdown) -> str:
        """Return a human-readable concentration label based on HHI score."""
        score = breakdown.concentration_score
        if score < 0.10:
            return "well-diversified"
        elif score <= 0.25:
            return "moderate"
        else:
            return "high"
