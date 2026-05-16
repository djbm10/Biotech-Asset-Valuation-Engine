"""Deal structure definitions and economics."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class DealStructureType(str, Enum):
    FULL_ACQUISITION = "full_acquisition"
    ASSET_LICENSE = "asset_license"
    OPTION_TO_ACQUIRE = "option_to_acquire"
    REGIONAL_LICENSE = "regional_license"
    CO_DEVELOPMENT = "co_development"
    EQUITY_PLUS_OPTION = "equity_plus_option"
    ROYALTY_PURCHASE = "royalty_purchase"


class DealStructure(BaseModel):
    """Economics of a specific deal structure."""

    structure_type: DealStructureType
    upfront_cash_usd_m: float = Field(default=0.0, ge=0.0, description="Cash required now")
    option_exercise_price_usd_m: float = Field(
        default=0.0, ge=0.0, description="Option exercise payment (0 if not applicable)"
    )
    milestones_total_usd_m: float = Field(default=0.0, ge=0.0)
    royalty_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Running royalty on net sales")
    buyer_cost_share_pct: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Fraction of R&D costs borne by buyer"
    )
    buyer_rnpv_usd_m: float = Field(default=0.0, description="Buyer's risk-adjusted NPV")
    seller_expected_value_usd_m: float = Field(default=0.0, description="Seller's expected value")
    risk_transfer_to_buyer: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Fraction of development risk shifted to buyer"
    )
    control_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Buyer's operational control (1.0 = full)"
    )
    accounting_complexity: Literal["low", "medium", "high"] = "low"
    probability_seller_accepts: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str | None = None

    @property
    def net_buyer_rnpv_after_upfront(self) -> float:
        return self.buyer_rnpv_usd_m - self.upfront_cash_usd_m

    @property
    def upfront_as_pct_buyer_rnpv(self) -> float:
        if self.buyer_rnpv_usd_m <= 0:
            return 0.0
        return self.upfront_cash_usd_m / self.buyer_rnpv_usd_m * 100

    def summary(self) -> str:
        lines = [f"Structure: {self.structure_type.value}"]
        if self.rationale:
            lines.append(f"  Why: {self.rationale}")
        lines.append(f"  Upfront: ${self.upfront_cash_usd_m:.0f}M")
        if self.option_exercise_price_usd_m > 0:
            lines.append(f"  Option exercise: ${self.option_exercise_price_usd_m:.0f}M")
        lines.append(f"  Milestones: ${self.milestones_total_usd_m:.0f}M")
        if self.royalty_rate > 0:
            lines.append(f"  Royalty: {self.royalty_rate:.1%}")
        lines.append(f"  Buyer rNPV: ${self.buyer_rnpv_usd_m:.0f}M")
        lines.append(f"  Seller expected value: ${self.seller_expected_value_usd_m:.0f}M")
        lines.append(f"  Seller acceptance probability: {self.probability_seller_accepts:.0%}")
        return "\n".join(lines)
