"""
Commercial model layer — explicit patient × price × share decomposition (Sprint 14).

Replaces single-point ``peak_sales_millions`` with a structured build-up that:
- explains *how* the peak sales estimate was derived
- propagates uncertainty through each input independently in MC

Three Pydantic models compose into ``CommercialInputs``:

    PatientPool  — epidemiology chain (prevalence → diagnosed → treated → addressable)
    PricingModel — net price with gross-to-net adjustments and erosion
    ShareModel   — peak penetration + ramp + CV for MC

``CommercialInputs.to_peak_sales_millions()`` produces the point estimate used in base-case
valuation; ``sample_peak_sales(rng)`` produces one MC draw.

Backward compatibility
----------------------
This module is purely additive.  ``MarketModel`` grows an optional
``commercial_inputs: Optional[CommercialInputs] = None`` field.  When set:
- ``peak_sales_millions`` is derived from ``commercial_inputs.to_peak_sales_millions()``
- MC sampling uses ``commercial_inputs.sample_peak_sales(rng)``
Existing configs without ``commercial_inputs`` are entirely unaffected.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
from pydantic import BaseModel, Field, model_validator


class PatientPool(BaseModel, frozen=True):
    """
    Epidemiology chain → addressable patient count.

    Chain: prevalence_thousands × 1000 × diagnosed_fraction × treated_fraction
    → addressable_k (override if you have a direct estimate).

    annual_incidence_k is stored for reference / cross-check but not used in
    to_addressable() — set addressable_k directly if you prefer incidence-based sizing.
    """

    indication: str = Field(description="Short indication name for labeling")
    prevalence_thousands: float = Field(
        gt=0,
        description="Diagnosed prevalent population in thousands (US unless noted)",
    )
    diagnosed_fraction: float = Field(
        default=1.0, gt=0.0, le=1.0,
        description="Fraction of prevalent population currently diagnosed",
    )
    treated_fraction: float = Field(
        default=1.0, gt=0.0, le=1.0,
        description="Fraction of diagnosed population currently receiving any treatment",
    )
    addressable_k: Optional[float] = Field(
        default=None, gt=0,
        description=(
            "Override: addressable patient count in thousands. "
            "When set, prevalence chain is bypassed."
        ),
    )
    annual_incidence_k: Optional[float] = Field(
        default=None, gt=0,
        description="Annual new diagnoses in thousands (reference / cross-check only)",
    )
    uncertainty_cv: float = Field(
        default=0.25, ge=0.0, le=1.0,
        description="Coefficient of variation for MC sampling of addressable population",
    )

    def to_addressable(self) -> float:
        """Return addressable patient count (absolute, not thousands)."""
        if self.addressable_k is not None:
            return self.addressable_k * 1_000
        return (
            self.prevalence_thousands
            * 1_000
            * self.diagnosed_fraction
            * self.treated_fraction
        )

    def sample(self, rng: "np.random.Generator") -> float:
        """
        Draw one addressable patient count from a log-normal distribution.

        mu, sigma are derived from to_addressable() and uncertainty_cv so that:
          E[X] ≈ to_addressable()
          CV[X] ≈ uncertainty_cv
        """
        mu = self.to_addressable()
        if self.uncertainty_cv <= 0:
            return mu
        sigma_ln = math.sqrt(math.log(1 + self.uncertainty_cv ** 2))
        mu_ln = math.log(mu) - sigma_ln ** 2 / 2
        return float(rng.lognormal(mean=mu_ln, sigma=sigma_ln))


class PricingModel(BaseModel, frozen=True):
    """Net annual price per patient with gross-to-net adjustments and price erosion."""

    net_price_usd: float = Field(
        gt=0,
        description="Net price per patient per year (after gross-to-net) in USD",
    )
    launch_discount: float = Field(
        default=0.10, ge=0.0, le=1.0,
        description="Additional launch-year rebates/discounts on top of net_price_usd",
    )
    annual_erosion_rate: float = Field(
        default=0.02, ge=0.0, le=1.0,
        description="Annual real price erosion rate post-launch",
    )
    uncertainty_cv: float = Field(
        default=0.15, ge=0.0, le=1.0,
        description="CV for MC sampling of launch-year net price",
    )

    def effective_launch_price(self) -> float:
        """Net price at launch, applying launch_discount."""
        return self.net_price_usd * (1.0 - self.launch_discount)

    def price_in_year(self, year: int) -> float:
        """Net price in post-launch year `year` (1 = launch year)."""
        launch = self.effective_launch_price()
        return launch * (1.0 - self.annual_erosion_rate) ** (year - 1)

    def sample_launch_price(self, rng: "np.random.Generator") -> float:
        """Draw one launch-year net price from a log-normal distribution."""
        mu = self.effective_launch_price()
        if self.uncertainty_cv <= 0:
            return mu
        sigma_ln = math.sqrt(math.log(1 + self.uncertainty_cv ** 2))
        mu_ln = math.log(mu) - sigma_ln ** 2 / 2
        return float(rng.lognormal(mean=mu_ln, sigma=sigma_ln))


class ShareModel(BaseModel, frozen=True):
    """Peak market penetration with ramp and MC uncertainty."""

    peak_share: float = Field(
        gt=0.0, le=1.0,
        description="Peak penetration of addressable market (fraction, not percent)",
    )
    years_to_peak: int = Field(
        default=5, gt=0,
        description="Years from launch to reach peak_share",
    )
    share_cv: float = Field(
        default=0.20, ge=0.0, le=1.0,
        description="CV for MC sampling of peak_share",
    )

    @model_validator(mode="after")
    def _check_share(self) -> "ShareModel":
        if self.peak_share <= 0 or self.peak_share > 1:
            raise ValueError(f"peak_share must be in (0, 1], got {self.peak_share}")
        return self

    def sample_peak_share(self, rng: "np.random.Generator") -> float:
        """Draw one peak_share from a log-normal, clamped to (0, 1]."""
        if self.share_cv <= 0:
            return self.peak_share
        sigma_ln = math.sqrt(math.log(1 + self.share_cv ** 2))
        mu_ln = math.log(self.peak_share) - sigma_ln ** 2 / 2
        sampled = float(rng.lognormal(mean=mu_ln, sigma=sigma_ln))
        return min(1.0, sampled)


class CommercialInputs(BaseModel, frozen=True):
    """
    Explicit commercial build-up: patient × price × share → peak sales.

    All three sub-models are required.  The output of ``to_peak_sales_millions()``
    can be used as ``MarketModel.total_addressable_market_millions`` × penetration
    equivalent — but the decomposition makes the assumption chain auditable.
    """

    patient_pool: PatientPool
    pricing: PricingModel
    share: ShareModel

    def to_peak_sales_millions(self) -> float:
        """
        Point estimate: addressable × peak_share × effective_launch_price / 1e6.

        Does NOT apply price erosion (that is modelled year-by-year in MC).
        """
        addressable = self.patient_pool.to_addressable()
        price = self.pricing.effective_launch_price()
        share = self.share.peak_share
        return round(addressable * price * share / 1e6, 2)

    def sample_peak_sales(self, rng: "np.random.Generator") -> float:
        """
        One MC draw: propagate uncertainty through population × share × price.

        Returns peak annual revenue in USD millions.
        Inputs are sampled independently (no correlation assumed at this level).
        """
        addressable = self.patient_pool.sample(rng)
        price = self.pricing.sample_launch_price(rng)
        share = self.share.sample_peak_share(rng)
        return addressable * price * share / 1e6
