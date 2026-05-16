"""Decision policy data models — configurable thresholds and allowed actions."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PolicyAction(str, Enum):
    MONITOR = "monitor"
    RELATIONSHIP_BUILD = "relationship_build"
    REQUEST_CDA = "request_cda"
    DILIGENCE_MEMO = "diligence_memo"
    PURSUE_OPTION_DEAL = "pursue_option_deal"
    ACTIVE_PURSUIT = "active_pursuit"
    NO_TRADE = "no_trade"
    INITIATE_POSITION = "initiate_position"
    ADD_TO_POSITION = "add_to_position"
    REDUCE_POSITION = "reduce_position"
    CLOSE_POSITION = "close_position"
    DILIGENCE_REQUIRED = "diligence_required"
    PASS = "pass"


class BDPolicy(BaseModel):
    """BD screening decision policy."""

    name: str = "bd_screening"
    active_pursuit_min_score: float = Field(default=0.75, ge=0.0, le=1.0)
    require_asset_quality_min: float = Field(default=0.60, ge=0.0, le=1.0)
    require_strategic_fit_min: float = Field(default=0.70, ge=0.0, le=1.0)
    require_seller_willingness_min: float = Field(default=0.40, ge=0.0, le=1.0)
    allowed_actions: list[PolicyAction] = Field(
        default_factory=lambda: [
            PolicyAction.MONITOR,
            PolicyAction.RELATIONSHIP_BUILD,
            PolicyAction.REQUEST_CDA,
            PolicyAction.DILIGENCE_MEMO,
            PolicyAction.PURSUE_OPTION_DEAL,
        ]
    )


class HedgeFundPolicy(BaseModel):
    """Hedge fund event-driven policy."""

    name: str = "hedge_fund_event"
    require_expected_return_min: float = Field(default=0.20, ge=0.0)
    require_liquidity_min_usd: float = Field(default=5_000_000.0, ge=0.0)
    max_position_size_pct_nav: float = Field(default=2.0, gt=0.0)
    require_downside_floor: bool = True
    catalyst_horizon_max_days: int = Field(default=180, gt=0)


class VCPolicy(BaseModel):
    """Venture capital underwriting policy."""

    name: str = "vc_underwriting"
    require_biology_score_min: float = Field(default=0.65, ge=0.0, le=1.0)
    require_capital_to_poc_under: float = Field(default=100_000_000.0, gt=0.0)
    require_exit_universe_min_buyers: int = Field(default=3, ge=1)
    require_platform_optionality: bool = False


class DecisionPolicy(BaseModel):
    """Container for all configured decision policies."""

    bd: BDPolicy = Field(default_factory=BDPolicy)
    hedge_fund: HedgeFundPolicy = Field(default_factory=HedgeFundPolicy)
    vc: VCPolicy = Field(default_factory=VCPolicy)

    @classmethod
    def default(cls) -> "DecisionPolicy":
        return cls()
