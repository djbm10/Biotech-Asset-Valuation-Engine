from typing import Optional

from pydantic import BaseModel, Field


class Partnership(BaseModel):
    partner_name: str
    asset_id: str
    deal_type: str          # license_in | license_out | co-development | acquisition
    upfront_millions: Optional[float] = None
    milestones_total_millions: Optional[float] = None
    royalty_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    territory: str = "global"
    signed_date: Optional[str] = None
    notes: Optional[str] = None


class Company(BaseModel):
    id: str
    name: str
    ticker: Optional[str] = None

    # Balance sheet
    cash_millions: float = Field(ge=0.0, description="Cash + equivalents + short-term investments")
    debt_millions: float = Field(default=0.0, ge=0.0)
    shares_outstanding_millions: float = Field(gt=0.0, description="Diluted share count")

    # Cash flow
    burn_rate_millions_per_quarter: Optional[float] = Field(
        default=None, gt=0.0,
        description="Average quarterly net cash burn"
    )

    # Pipeline
    asset_ids: list[str] = Field(default_factory=list)
    ownership_stakes: dict[str, float] = Field(
        default_factory=dict,
        description="Fractional economic ownership per asset_id (default 1.0)"
    )
    partnerships: list[Partnership] = Field(default_factory=list)

    # Market data (snapshot)
    current_price: Optional[float] = None
    market_cap_millions: Optional[float] = None

    notes: Optional[str] = None

    @property
    def net_cash_millions(self) -> float:
        return self.cash_millions - self.debt_millions

    @property
    def cash_runway_quarters(self) -> Optional[float]:
        if self.burn_rate_millions_per_quarter and self.burn_rate_millions_per_quarter > 0:
            return self.cash_millions / self.burn_rate_millions_per_quarter
        return None

    def ownership_of(self, asset_id: str) -> float:
        return self.ownership_stakes.get(asset_id, 1.0)
