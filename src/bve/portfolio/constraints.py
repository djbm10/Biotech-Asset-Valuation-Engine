"""Portfolio constraint definitions."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PortfolioConstraints(BaseModel):
    """Hard limits on portfolio construction."""

    max_single_name_pct_nav: float = Field(default=3.0, gt=0.0)
    max_preclinical_pct_nav: float = Field(default=0.0, ge=0.0)
    max_phase2_pct_nav: float = Field(default=8.0, ge=0.0)
    max_same_catalyst_month_pct_nav: float = Field(default=10.0, ge=0.0)
    max_same_modality_pct_nav: float = Field(default=15.0, ge=0.0)
    min_liquidity_days_to_exit: int = Field(default=5, ge=1)
    max_expected_drawdown: float = Field(default=15.0, ge=0.0)

    @classmethod
    def conservative(cls) -> "PortfolioConstraints":
        return cls(
            max_single_name_pct_nav=1.5,
            max_preclinical_pct_nav=0.0,
            max_phase2_pct_nav=5.0,
            max_same_catalyst_month_pct_nav=6.0,
            max_same_modality_pct_nav=10.0,
            min_liquidity_days_to_exit=10,
            max_expected_drawdown=10.0,
        )

    @classmethod
    def aggressive(cls) -> "PortfolioConstraints":
        return cls(
            max_single_name_pct_nav=5.0,
            max_preclinical_pct_nav=2.0,
            max_phase2_pct_nav=15.0,
            max_same_catalyst_month_pct_nav=20.0,
            max_same_modality_pct_nav=25.0,
            min_liquidity_days_to_exit=3,
            max_expected_drawdown=25.0,
        )
