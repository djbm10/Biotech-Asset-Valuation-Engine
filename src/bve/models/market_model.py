"""
Market model: patient-based TAM/SAM/SOM → revenue curve.

Two modes:
  1. Patient-based: builds up from epidemiology → addressable patients → revenue
  2. TAM-based: specify market size directly and apply penetration

Both produce an annual revenue curve (USD millions) from launch through patent expiry.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator

from bve.config.constants import GROSS_TO_NET_DISCOUNT, SGNA_RATE_LAUNCH, SGNA_RATE_MATURE, SGNA_RAMP_YEARS
from bve.entities.indication import Indication


class UptakeCurve(BaseModel):
    """Year-by-year penetration ramp as fraction of addressable market."""
    penetrations: list[float] = Field(
        description="Penetration fraction for each year from launch. Last value holds for remaining years."
    )

    @classmethod
    def linear_ramp(cls, years_to_peak: int, peak_penetration: float, patent_life: int) -> "UptakeCurve":
        """Build a simple linear ramp to peak, then flat."""
        percs = []
        for yr in range(1, patent_life + 1):
            if yr <= years_to_peak:
                percs.append(peak_penetration * yr / years_to_peak)
            else:
                percs.append(peak_penetration)
        return cls(penetrations=percs)

    @classmethod
    def s_curve(cls, years_to_peak: int, peak_penetration: float, patent_life: int) -> "UptakeCurve":
        """Logistic S-curve uptake — more realistic for specialty pharma."""
        import math
        percs = []
        k = 8.0 / years_to_peak  # steepness calibrated so ~peak at years_to_peak
        midpoint = years_to_peak / 2.0
        for yr in range(1, patent_life + 1):
            s = peak_penetration / (1.0 + math.exp(-k * (yr - midpoint)))
            percs.append(min(s, peak_penetration))
        return cls(penetrations=percs)

    def penetration_at_year(self, year: int) -> float:
        """1-indexed year from launch."""
        if year <= 0:
            return 0.0
        idx = min(year - 1, len(self.penetrations) - 1)
        return self.penetrations[idx]


class MarketModel(BaseModel):
    asset_id: str

    # --- Mode 1: patient-based ---
    addressable_patients_annual: Optional[int] = Field(
        default=None, gt=0,
        description="Eligible patients per year in target geography"
    )
    net_price_per_patient_usd: Optional[float] = Field(
        default=None, gt=0.0,
        description="Annual net price (after gross-to-net) per patient in USD"
    )
    compliance_rate: float = Field(
        default=0.80, gt=0.0, le=1.0,
        description="Average fraction of year patients remain on therapy"
    )

    # --- Mode 2: TAM-based (fallback) ---
    total_addressable_market_millions: Optional[float] = Field(
        default=None, gt=0.0,
        description="Total market size in USD millions (net of G2N)"
    )

    # --- Shared ---
    uptake_curve: Optional[UptakeCurve] = None
    peak_penetration: float = Field(
        default=0.10, gt=0.0, le=1.0,
        description="Peak market share fraction"
    )
    years_to_peak: int = Field(default=5, gt=0)
    patent_life_years: int = Field(default=12, gt=0)
    use_s_curve: bool = Field(default=False, description="Use S-curve instead of linear ramp")

    # Cost structure
    cogs_rate: float = Field(default=0.18, ge=0.0, le=1.0)
    sgna_rate_launch: float = Field(default=SGNA_RATE_LAUNCH, ge=0.0, le=1.0)
    sgna_rate_mature: float = Field(default=SGNA_RATE_MATURE, ge=0.0, le=1.0)
    sgna_ramp_years: int = Field(default=SGNA_RAMP_YEARS, gt=0)

    @model_validator(mode="after")
    def _check_mode(self) -> "MarketModel":
        patient_mode = self.addressable_patients_annual and self.net_price_per_patient_usd
        tam_mode = self.total_addressable_market_millions is not None
        if not patient_mode and not tam_mode:
            raise ValueError(
                "Provide either (addressable_patients_annual + net_price_per_patient_usd) "
                "or total_addressable_market_millions"
            )
        return self

    @model_validator(mode="after")
    def _build_uptake_curve(self) -> "MarketModel":
        if self.uptake_curve is None:
            if self.use_s_curve:
                self.uptake_curve = UptakeCurve.s_curve(
                    self.years_to_peak, self.peak_penetration, self.patent_life_years
                )
            else:
                self.uptake_curve = UptakeCurve.linear_ramp(
                    self.years_to_peak, self.peak_penetration, self.patent_life_years
                )
        return self

    @property
    def peak_sales_millions(self) -> float:
        if self.addressable_patients_annual and self.net_price_per_patient_usd:
            return (
                self.addressable_patients_annual
                * self.net_price_per_patient_usd
                * self.compliance_rate
                * self.peak_penetration
                / 1e6
            )
        return (self.total_addressable_market_millions or 0) * self.peak_penetration

    def _get_uptake_curve(self) -> UptakeCurve:
        """Return uptake_curve, rebuilding if None (e.g. after model_copy with update)."""
        if self.uptake_curve is not None:
            return self.uptake_curve
        if self.use_s_curve:
            return UptakeCurve.s_curve(self.years_to_peak, self.peak_penetration, self.patent_life_years)
        return UptakeCurve.linear_ramp(self.years_to_peak, self.peak_penetration, self.patent_life_years)

    def revenue_in_year(self, years_from_launch: int) -> float:
        """Gross revenue (net of G2N, pre-COGS) in USD millions, N years from launch."""
        if years_from_launch <= 0 or years_from_launch > self.patent_life_years:
            return 0.0
        pen = self._get_uptake_curve().penetration_at_year(years_from_launch)

        if self.addressable_patients_annual and self.net_price_per_patient_usd:
            return (
                self.addressable_patients_annual
                * self.net_price_per_patient_usd
                * self.compliance_rate
                * pen
                / 1e6
            )
        return (self.total_addressable_market_millions or 0) * pen

    def gross_profit_in_year(self, years_from_launch: int) -> float:
        """Revenue minus COGS."""
        return self.revenue_in_year(years_from_launch) * (1.0 - self.cogs_rate)

    def sgna_in_year(self, years_from_launch: int) -> float:
        """SG&A expense in USD millions — declines from launch rate to mature rate."""
        if years_from_launch <= 0:
            return 0.0
        rev = self.revenue_in_year(years_from_launch)
        if years_from_launch >= self.sgna_ramp_years:
            return rev * self.sgna_rate_mature
        blend = years_from_launch / self.sgna_ramp_years
        rate = self.sgna_rate_launch + blend * (self.sgna_rate_mature - self.sgna_rate_launch)
        return rev * rate

    def ebit_in_year(self, years_from_launch: int) -> float:
        """EBIT = gross profit - SG&A."""
        return self.gross_profit_in_year(years_from_launch) - self.sgna_in_year(years_from_launch)

    def revenue_curve(self) -> list[float]:
        """Full revenue curve from year 1 to patent_life_years."""
        return [self.revenue_in_year(y) for y in range(1, self.patent_life_years + 1)]

    def ebit_curve(self) -> list[float]:
        return [self.ebit_in_year(y) for y in range(1, self.patent_life_years + 1)]

    @classmethod
    def from_indication(
        cls,
        asset_id: str,
        indication: Indication,
        net_price_usd: float,
        peak_penetration: float,
        **kwargs,
    ) -> "MarketModel":
        """Build a MarketModel from an Indication entity."""
        patients = indication.addressable_patients
        if patients is None:
            raise ValueError("Indication.addressable_patients is None; provide epidemiology data")
        return cls(
            asset_id=asset_id,
            addressable_patients_annual=patients,
            net_price_per_patient_usd=net_price_usd,
            peak_penetration=peak_penetration,
            **kwargs,
        )
