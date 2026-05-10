"""
Commercial model layer — explicit patient × price × share decomposition (Sprint 14).

Replaces single-point ``peak_sales_millions`` with a structured build-up that:
- explains *how* the peak sales estimate was derived
- propagates uncertainty through each input independently in MC

Three Pydantic models compose into ``CommercialInputs``:

    PatientPool  — full patient-flow funnel with disease-model awareness:
                   prevalent   : prevalence × diagnosed × eligible × treated → addressable
                   incident_chronic: incidence × funnel × duration → steady-state addressable
                   incident_one_time: Year 1 = backlog + annual incident; Year 2+ = annual only
    PricingModel — WAC + gross-to-net → net price with erosion
    ShareModel   — peak penetration + ramp + CV for MC

``CommercialInputs.to_peak_sales_millions()`` produces the point estimate used in base-case
valuation; ``sample_peak_sales(rng)`` produces one MC draw.

Disease model summary (Sprint B1)
----------------------------------
prevalent (default, unchanged)
    addressable = prevalence_thousands × 1000 × diagnosed_fraction
                  × eligible_rate × treated_fraction
    (or addressable_k override)

incident_chronic
    Addressable patients at steady state = patients currently being treated,
    sized by annual incidence × funnel × duration on therapy.

    addressable = annual_incidence_k × 1000
                  × diagnosed_fraction × eligible_rate × treated_fraction
                  × duration_on_therapy_years
    (or addressable_k override)

    Requires: annual_incidence_k.
    Duration defaults to 1.0 year if not explicitly set.

incident_one_time
    Treatment is curative / one-time (gene therapy, cell therapy, surgery).
    Year 1 includes the backlog of prevalent eligible patients plus annual incident.
    Year 2+ is annual incident eligible only — no duration multiplier.

    Year 1: addressable = (prevalent_eligible × backlog_years) + annual_incident_eligible
    Year 2+: addressable = annual_incident_eligible

    Requires: annual_incidence_k.
    backlog_years defaults to 1.0 (one year of prevalent backlog absorbed at launch).

Backward compatibility
----------------------
This module is purely additive.  ``MarketModel`` grows an optional
``commercial_inputs: Optional[CommercialInputs] = None`` field.  When set:
- ``peak_sales_millions`` is derived from ``commercial_inputs.to_peak_sales_millions()``
- MC sampling uses ``commercial_inputs.sample_peak_sales(rng)``
Existing configs without ``commercial_inputs`` are entirely unaffected.

For existing PatientPool configs (no disease_model set), disease_model defaults to
"prevalent" and all outputs are bit-for-bit identical to Sprint 14 behavior.
"""
from __future__ import annotations

import math
import warnings
from typing import Literal, Optional

import numpy as np
from pydantic import BaseModel, Field, model_validator


class PatientPool(BaseModel, frozen=True):
    """
    Full patient-flow funnel → addressable patient count.

    Three disease modeling modes controlled by ``disease_model``:

    prevalent (default, backward-compatible)
        Funnel: prevalence_thousands × 1000
                × diagnosed_fraction × eligible_rate × treated_fraction
                → addressable_k override available.

    incident_chronic
        Steady-state addressable = annual incidence × funnel × duration on therapy.
        annual_incidence_k is required.  duration_on_therapy_years (or _months) sets
        the average time each patient is on treatment.  Defaults to 1.0 year.

    incident_one_time
        Curative / one-time treatment (gene therapy, cell therapy).
        Year 1 absorbs the backlog of prevalent eligible patients plus the annual
        incident cohort.  Year 2+ is annual incident only (no duration multiplier).
        annual_incidence_k is required.  prevalence_thousands is used for backlog
        (optional — omit if no prevalent backlog is expected at launch).
    """

    indication: str = Field(description="Short indication name for labeling")

    # --- Disease model ---
    disease_model: Literal["prevalent", "incident_chronic", "incident_one_time"] = Field(
        default="prevalent",
        description=(
            "Patient-pool disease modeling mode. "
            "'prevalent': funnel from prevalence (default, backward-compatible). "
            "'incident_chronic': incidence × duration gives steady-state addressable. "
            "'incident_one_time': Year 1 = backlog + annual incident; Year 2+ = annual only."
        ),
    )

    # --- Prevalence (required for disease_model='prevalent'; optional for incident) ---
    prevalence_thousands: Optional[float] = Field(
        default=None, gt=0,
        description=(
            "Diagnosed prevalent population in thousands (US unless noted). "
            "Required for disease_model='prevalent'. "
            "Optional for incident_one_time (used for backlog calculation at launch)."
        ),
    )

    # --- Shared funnel fractions ---
    diagnosed_fraction: float = Field(
        default=1.0, gt=0.0, le=1.0,
        description="Fraction of population currently diagnosed",
    )
    eligible_rate: float = Field(
        default=1.0, gt=0.0, le=1.0,
        description=(
            "Fraction of diagnosed patients who meet label eligibility criteria "
            "(e.g., F2-F4 fibrosis gate, biomarker selection, line-of-therapy filter). "
            "Applied between diagnosed_fraction and treated_fraction in the funnel."
        ),
    )
    treated_fraction: float = Field(
        default=1.0, gt=0.0, le=1.0,
        description="Fraction of eligible patients currently receiving any treatment",
    )

    # --- Addressable override ---
    addressable_k: Optional[float] = Field(
        default=None, gt=0,
        description=(
            "Override: addressable patient count in thousands. "
            "When set for prevalent/incident_chronic, bypasses the prevalence/incidence chain. "
            "When set for incident_one_time, used as the backlog base (addressable_k × backlog_years) "
            "plus annual incident eligible for Year 1."
        ),
    )

    # --- Incidence (required for incident_chronic and incident_one_time) ---
    annual_incidence_k: Optional[float] = Field(
        default=None, gt=0,
        description=(
            "Annual new diagnoses in thousands. "
            "Required for disease_model='incident_chronic' and 'incident_one_time'. "
            "Used as reference/cross-check only for disease_model='prevalent'."
        ),
    )

    # --- Duration (incident_chronic) ---
    duration_on_therapy_months: Optional[float] = Field(
        default=None, gt=0,
        description=(
            "Average duration on therapy in months. Converted to years internally. "
            "Used for disease_model='incident_chronic' only. "
            "Provide either this or duration_on_therapy_years (not both)."
        ),
    )
    duration_on_therapy_years: Optional[float] = Field(
        default=None, gt=0,
        description=(
            "Average duration on therapy in years. "
            "Used for disease_model='incident_chronic' only. "
            "If neither months nor years is set, defaults to 1.0 year."
        ),
    )

    # --- Backlog (incident_one_time) ---
    backlog_years: float = Field(
        default=1.0, gt=0,
        description=(
            "For disease_model='incident_one_time': number of years of prevalent-eligible "
            "backlog absorbed at launch (Year 1). "
            "backlog = prevalent_eligible × backlog_years. "
            "Default 1.0 — one year of accumulated untreated patients absorbed at launch."
        ),
    )

    uncertainty_cv: float = Field(
        default=0.25, ge=0.0, le=1.0,
        description="Coefficient of variation for MC sampling of addressable population",
    )

    @model_validator(mode="after")
    def _validate_disease_model_inputs(self) -> "PatientPool":
        dm = self.disease_model

        if dm == "prevalent":
            if self.prevalence_thousands is None and self.addressable_k is None:
                raise ValueError(
                    "PatientPool: disease_model='prevalent' requires either "
                    "prevalence_thousands or addressable_k."
                )

        elif dm in ("incident_chronic", "incident_one_time"):
            if self.annual_incidence_k is None:
                raise ValueError(
                    f"PatientPool: disease_model={dm!r} requires annual_incidence_k "
                    "(annual new diagnoses in thousands)."
                )
            if dm == "incident_chronic" and self.duration_on_therapy_months is not None and self.duration_on_therapy_years is not None:
                raise ValueError(
                    "PatientPool: specify duration_on_therapy_months OR duration_on_therapy_years, not both."
                )

        return self

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _resolved_duration_years(self) -> float:
        """Therapy duration in years. For incident_chronic; defaults to 1.0 if unset."""
        if self.duration_on_therapy_years is not None:
            return self.duration_on_therapy_years
        if self.duration_on_therapy_months is not None:
            return self.duration_on_therapy_months / 12.0
        return 1.0  # safe default: average 1 year on therapy

    def _annual_incident_eligible(self) -> float:
        """
        Annual incident eligible count (absolute patients).

        annual_incidence_k × 1000 × diagnosed_fraction × eligible_rate × treated_fraction
        """
        return (
            (self.annual_incidence_k or 0.0)
            * 1_000
            * self.diagnosed_fraction
            * self.eligible_rate
            * self.treated_fraction
        )

    def _prevalent_eligible(self) -> float:
        """Eligible prevalent patients (absolute). For incident_one_time backlog."""
        if self.addressable_k is not None:
            return self.addressable_k * 1_000
        if self.prevalence_thousands is None:
            return 0.0
        return (
            self.prevalence_thousands
            * 1_000
            * self.diagnosed_fraction
            * self.eligible_rate
            * self.treated_fraction
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def to_addressable(self) -> float:
        """
        Return addressable patient count (absolute, not thousands).

        For prevalent: prevalent funnel or addressable_k override.
        For incident_chronic: annual_incidence × funnel × duration.
        For incident_one_time: Year 1 (backlog + annual incident) — the peak year.

        Used by to_peak_sales_millions() and MC sampling.
        """
        if self.disease_model == "prevalent":
            if self.addressable_k is not None:
                return self.addressable_k * 1_000
            return (
                (self.prevalence_thousands or 0.0)
                * 1_000
                * self.diagnosed_fraction
                * self.eligible_rate
                * self.treated_fraction
            )

        if self.disease_model == "incident_chronic":
            if self.addressable_k is not None:
                return self.addressable_k * 1_000
            return self._annual_incident_eligible() * self._resolved_duration_years

        # incident_one_time: peak = Year 1 (backlog + annual incident)
        return self._prevalent_eligible() * self.backlog_years + self._annual_incident_eligible()

    def to_addressable_ongoing(self) -> float:
        """
        Year 2+ addressable count for incident_one_time (annual incident only, no backlog).

        For prevalent and incident_chronic, returns the same as to_addressable()
        (those models have a steady-state addressable pool).
        """
        if self.disease_model == "incident_one_time":
            return self._annual_incident_eligible()
        return self.to_addressable()

    def to_addressable_in_year(self, year: int) -> float:
        """
        Year-specific addressable count.

        incident_one_time: Year 1 includes backlog; Year 2+ is annual incident only.
        All other disease models: same as to_addressable() regardless of year.
        """
        if self.disease_model == "incident_one_time":
            if year == 1:
                return self.to_addressable()
            return self.to_addressable_ongoing()
        return self.to_addressable()

    def sample(self, rng: "np.random.Generator") -> float:
        """
        Draw one addressable patient count from a log-normal distribution.

        mu, sigma are derived from to_addressable() and uncertainty_cv so that:
          E[X] ≈ to_addressable()
          CV[X] ≈ uncertainty_cv

        For incident_one_time, samples the Year 1 (peak) addressable count.
        Use to_addressable_ongoing() for Year 2+ sampling.
        """
        mu = self.to_addressable()
        if self.uncertainty_cv <= 0:
            return mu
        sigma_ln = math.sqrt(math.log(1 + self.uncertainty_cv ** 2))
        mu_ln = math.log(mu) - sigma_ln ** 2 / 2
        return float(rng.lognormal(mean=mu_ln, sigma=sigma_ln))


class PricingModel(BaseModel, frozen=True):
    """
    Net annual price per patient with gross-to-net adjustments and price erosion.

    Two construction paths:
    1. Direct: set ``net_price_usd`` explicitly (post-G2N net price).
    2. Derived: set ``wac_per_year_usd`` + ``gross_to_net_rate`` and the model
       derives ``net_price_usd = wac × (1 − gross_to_net_rate)`` automatically.
       This is the preferred path for transparency — the WAC and G2N rate are
       separately auditable.

    Consistency check: if all three (wac, g2n_rate, net_price_usd) are provided,
    a UserWarning is issued when wac × (1 − g2n_rate) deviates >1% from net_price_usd.
    """

    net_price_usd: float = Field(
        gt=0,
        description="Net price per patient per year (after gross-to-net) in USD",
    )
    wac_per_year_usd: Optional[float] = Field(
        default=None, gt=0,
        description=(
            "Wholesale acquisition cost (list price) per patient per year in USD. "
            "Set alongside gross_to_net_rate to document price transparency. "
            "When both are set, net_price_usd should equal wac × (1 − gross_to_net_rate)."
        ),
    )
    gross_to_net_rate: Optional[float] = Field(
        default=None, ge=0.0, lt=1.0,
        description=(
            "Gross-to-net discount rate (e.g., 0.35 for 35% typical specialty pharma G2N). "
            "Used to derive and audit net_price_usd from wac_per_year_usd."
        ),
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

    @model_validator(mode="after")
    def _check_wac_consistency(self) -> "PricingModel":
        """Warn when wac × (1 − g2n_rate) deviates materially from net_price_usd."""
        if self.wac_per_year_usd is not None and self.gross_to_net_rate is not None:
            implied = self.wac_per_year_usd * (1.0 - self.gross_to_net_rate)
            if abs(implied - self.net_price_usd) / self.net_price_usd > 0.01:
                warnings.warn(
                    f"PricingModel: wac_per_year_usd × (1 − gross_to_net_rate) = "
                    f"${implied:,.0f} deviates >1% from net_price_usd = ${self.net_price_usd:,.0f}. "
                    "Check that net_price_usd was derived from wac × (1 − g2n_rate).",
                    UserWarning,
                    stacklevel=2,
                )
        return self

    @classmethod
    def from_wac(
        cls,
        wac_per_year_usd: float,
        gross_to_net_rate: float,
        *,
        launch_discount: float = 0.10,
        annual_erosion_rate: float = 0.02,
        uncertainty_cv: float = 0.15,
    ) -> "PricingModel":
        """
        Construct a PricingModel from WAC + G2N rate (transparency-first path).

        Net price is derived automatically: net_price = wac × (1 − g2n_rate).
        """
        net_price = wac_per_year_usd * (1.0 - gross_to_net_rate)
        return cls(
            net_price_usd=net_price,
            wac_per_year_usd=wac_per_year_usd,
            gross_to_net_rate=gross_to_net_rate,
            launch_discount=launch_discount,
            annual_erosion_rate=annual_erosion_rate,
            uncertainty_cv=uncertainty_cv,
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
    Explicit commercial build-up: patient × price × share × ex-US → peak sales.

    All three sub-models are required.  The optional ``ex_us_revenue_multiple``
    scales US-derived peak sales to a global (US + ex-US) estimate.

    The output of ``to_peak_sales_millions()`` can be used as
    ``MarketModel.total_addressable_market_millions`` × penetration
    equivalent — but the decomposition makes the assumption chain auditable.

    Patient-flow chain (full transparency):
        prevalence/incidence → diagnosed → eligible → treated → addressable
        × peak_share × net_price × ex_us_multiple = peak_sales_millions
    """

    patient_pool: PatientPool
    pricing: PricingModel
    share: ShareModel
    ex_us_revenue_multiple: float = Field(
        default=1.0, ge=1.0,
        description=(
            "Global revenue multiplier applied on top of the US-market estimate. "
            "Set to 1.0 (default) for US-only models. "
            "Typical ranges: 1.3–1.6x for EU5+Japan add-on; 1.5–2.0x for full global. "
            "Derived from ex_us_fraction as: 1 / (1 − ex_us_fraction), e.g., "
            "ex_us_fraction=0.40 → ex_us_revenue_multiple=1.67."
        ),
    )

    def to_peak_sales_millions(self) -> float:
        """
        Point estimate: addressable × peak_share × effective_launch_price
                        × ex_us_revenue_multiple / 1e6.

        For incident_one_time, uses Year 1 (backlog + annual incident) addressable
        — the peak year — as the basis for peak sales.

        Does NOT apply price erosion (that is modelled year-by-year in MC).
        """
        addressable = self.patient_pool.to_addressable()
        price = self.pricing.effective_launch_price()
        share = self.share.peak_share
        return round(addressable * price * share * self.ex_us_revenue_multiple / 1e6, 2)

    def to_ongoing_sales_millions(self) -> float:
        """
        Year 2+ steady-state revenue for incident_one_time models.

        addressable_ongoing × peak_share × effective_launch_price × ex_us_multiple / 1e6.

        For prevalent and incident_chronic, identical to to_peak_sales_millions().
        """
        addressable = self.patient_pool.to_addressable_ongoing()
        price = self.pricing.effective_launch_price()
        share = self.share.peak_share
        return round(addressable * price * share * self.ex_us_revenue_multiple / 1e6, 2)

    def sample_peak_sales(self, rng: "np.random.Generator") -> float:
        """
        One MC draw: propagate uncertainty through population × share × price × ex-US.

        Returns peak annual revenue in USD millions.
        Inputs are sampled independently (no correlation assumed at this level).
        """
        addressable = self.patient_pool.sample(rng)
        price = self.pricing.sample_launch_price(rng)
        share = self.share.sample_peak_share(rng)
        return addressable * price * share * self.ex_us_revenue_multiple / 1e6
