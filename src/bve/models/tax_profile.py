"""
TaxProfile — BD/M&A-ready tax and free-cash-flow model for RNPVModel.

Upgrades from the simple after-tax EBIT with nol_benefit_years to an auditable,
per-year after-tax FCF calculation suitable for BD/M&A memos.

Backward compatibility
----------------------
When tax_profile=None in RNPVModel.compute(), the old behavior is preserved:
  tax = 0 during asset.nol_benefit_years, then asset.effective_tax_rate thereafter.

When a TaxProfile is provided, this module takes over:
  1. Per-year NOL tracking against an explicit dollar balance
  2. Utilization limit (default 80%, matching post-TCJA US law)
  3. Optional NOL generation from loss years
  4. Jurisdiction-mode blended rate (blended or US/ex-US split)
  5. FCF adjustments: maintenance capex, working capital build, one-time launch capex

What is NOT modeled (add later as explicit M&A overlays):
  - Deferred tax assets / liabilities
  - BEAT / AMT
  - Country-by-country transfer pricing
  - Section 382 ownership-change NOL limitations
  - Purchase accounting amortization or tax step-up mechanics

TaxAudit
--------
TaxAudit records the per-year breakdown for every commercial year.
Populated in RNPVResult.tax_audit when a TaxProfile is provided; None otherwise.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# TaxProfile
# ---------------------------------------------------------------------------

class TaxProfile(BaseModel):
    """
    Tax and FCF configuration for a single rNPV run.

    All fields default to zero-effect — a default TaxProfile() with
    nol_balance_millions=0 produces the same result as the simple 21% flat rate.

    Parameters
    ----------
    effective_tax_rate
        Blended statutory rate applied after NOL offset.
        Default 21% (US federal corporate rate post-TCJA).
    nol_balance_millions
        Dollar value of existing NOL carryforwards available at commercial launch.
        Consumed per year subject to nol_utilization_limit_rate.
        0.0 = no NOL carryforward (full tax from year 1).
    nol_utilization_limit_rate
        Maximum fraction of taxable income that can be offset by NOL in any year.
        Default 0.80 (matches post-TCJA US Section 172(a)(2) 80% limitation).
        Set to 1.0 to allow full immediate NOL use (pre-TCJA behaviour or non-US).
    allow_nol_generation
        When True, years where adjusted_EBIT < 0 increase the NOL balance by the
        loss amount.  Default False (typical for deal models where pre-commercial
        losses are not inherited or are excluded from scope).
    jurisdiction_mode
        "blended"   : use effective_tax_rate as a single blended rate (default).
        "us_ex_us"  : compute a weighted rate from us_tax_rate × us_revenue_fraction
                      + ex_us_tax_rate × (1 − us_revenue_fraction).
                      Requires us_tax_rate and ex_us_tax_rate to be set.
    us_revenue_fraction
        Fraction of annual revenue attributable to the US.
        Only used in "us_ex_us" jurisdiction_mode.  Default 0.60.
    us_tax_rate
        US statutory rate.  Required when jurisdiction_mode="us_ex_us".
    ex_us_tax_rate
        Non-US blended rate.  Required when jurisdiction_mode="us_ex_us".
    transaction_structure
        BD/M&A transaction type.  Stored and surfaced in TaxAudit for deal memos.
        Does not change the math in this sprint — reserved for future scenario overlays.
    annual_maintenance_capex_rate
        Maintenance capex as fraction of annual revenue (e.g. 0.01 = 1% of revenue).
        Deducted from after-tax EBIT to compute after-tax FCF each year.
        Default 0.0 → after-tax FCF = after-tax EBIT (no capex).
    working_capital_rate
        Working capital build as fraction of annual revenue.
        Approximates net AR + inventory investment at each revenue level.
        Default 0.0 → no working capital deduction.
    one_time_launch_capex_millions
        One-time launch capex (manufacturing scale-up, IT, field force) in USD millions.
        Deducted in the single commercial year specified by launch_capex_year_offset.
        Default 0.0 → no launch capex.
    launch_capex_year_offset
        Years from first commercial launch year when the one-time capex is incurred.
        0.0 (default) → deducted in commercial year 1.
        1.0 → deducted in commercial year 2, etc.
        Fractional values are floored (offset=0.5 → commercial year 1).
    """
    model_config = ConfigDict(frozen=True)

    effective_tax_rate: float = Field(default=0.21, ge=0.0, le=1.0)

    # NOL tracking
    nol_balance_millions: float = Field(default=0.0, ge=0.0)
    nol_utilization_limit_rate: float = Field(
        default=0.80, ge=0.0, le=1.0,
        description="Max fraction of taxable income that can be offset by NOL per year",
    )
    allow_nol_generation: bool = False

    # Jurisdiction
    jurisdiction_mode: Literal["blended", "us_ex_us"] = "blended"
    us_revenue_fraction: float = Field(
        default=0.60, ge=0.0, le=1.0,
        description="Fraction of revenue attributable to US (used in us_ex_us mode)",
    )
    us_tax_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ex_us_tax_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # Transaction structure — audit only; does not change math
    transaction_structure: Literal[
        "standalone",
        "license",
        "asset_purchase",
        "stock_purchase",
        "co_development",
        "option_to_acquire",
    ] = "standalone"

    # FCF adjustments (all default 0.0 → no change from EBIT-based calculation)
    annual_maintenance_capex_rate: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Maintenance capex as fraction of annual revenue",
    )
    working_capital_rate: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Working capital build as fraction of annual revenue",
    )
    one_time_launch_capex_millions: float = Field(
        default=0.0, ge=0.0,
        description="One-time launch capex in USD millions (deducted in launch_capex_year)",
    )
    launch_capex_year_offset: float = Field(
        default=0.0, ge=0.0,
        description="Commercial years from launch when the one-time capex is incurred",
    )

    @model_validator(mode="after")
    def _validate_jurisdiction(self) -> "TaxProfile":
        if self.jurisdiction_mode == "us_ex_us":
            if self.us_tax_rate is None or self.ex_us_tax_rate is None:
                raise ValueError(
                    "TaxProfile: us_tax_rate and ex_us_tax_rate must both be set "
                    "when jurisdiction_mode='us_ex_us'."
                )
        return self

    @property
    def blended_tax_rate(self) -> float:
        """Applicable tax rate accounting for jurisdiction mode."""
        if self.jurisdiction_mode == "us_ex_us":
            # us_tax_rate and ex_us_tax_rate are guaranteed non-None by validator
            return (
                self.us_revenue_fraction * self.us_tax_rate  # type: ignore[operator]
                + (1.0 - self.us_revenue_fraction) * self.ex_us_tax_rate  # type: ignore[operator]
            )
        return self.effective_tax_rate


# ---------------------------------------------------------------------------
# Per-year FCF calculation
# ---------------------------------------------------------------------------

def compute_year_fcf(
    adjusted_ebit: float,
    revenue_t: float,
    remaining_nol: float,
    tax_profile: TaxProfile,
    yr: int,
) -> tuple[float, float, float, float, float, float, float, float, float]:
    """
    Compute after-tax FCF for one commercial year.

    Parameters
    ----------
    adjusted_ebit : EBIT after royalty and profit_share deductions.
    revenue_t     : Gross revenue for this year (for capex/WC rates).
    remaining_nol : NOL balance remaining entering this year (USD millions).
    tax_profile   : TaxProfile instance driving all parameters.
    yr            : 1-indexed commercial year (1 = first year post-launch).

    Returns (in order)
    ------------------
    usable_nol        : NOL consumed this year (0 if adjusted_ebit ≤ 0).
    nol_remaining     : NOL balance after this year.
    taxable_income    : max(adjusted_ebit, 0) before NOL offset.
    cash_tax          : tax paid this year.
    after_tax_ebit    : adjusted_ebit − cash_tax.
    maintenance_capex : revenue_t × annual_maintenance_capex_rate.
    working_capital   : revenue_t × working_capital_rate.
    launch_capex      : one_time_launch_capex_millions if yr matches offset year, else 0.
    after_tax_fcf     : after_tax_ebit − maintenance_capex − working_capital − launch_capex.
    """
    # --- Tax ---
    if adjusted_ebit <= 0:
        taxable_income = 0.0
        usable_nol = 0.0
        cash_tax = 0.0
        nol_generated = abs(adjusted_ebit) if tax_profile.allow_nol_generation else 0.0
        nol_remaining = remaining_nol + nol_generated
    else:
        taxable_income = adjusted_ebit
        limit = tax_profile.nol_utilization_limit_rate
        usable_nol = min(remaining_nol, taxable_income * limit)
        taxable_after_nol = taxable_income - usable_nol
        cash_tax = taxable_after_nol * tax_profile.blended_tax_rate
        nol_remaining = remaining_nol - usable_nol

    after_tax_ebit = adjusted_ebit - cash_tax

    # --- FCF adjustments ---
    maintenance_capex = revenue_t * tax_profile.annual_maintenance_capex_rate
    working_capital = revenue_t * tax_profile.working_capital_rate

    # One-time launch capex: commercial year = int(offset) + 1
    # e.g. offset=0 → yr 1; offset=1.5 → yr 2
    launch_capex_yr = int(tax_profile.launch_capex_year_offset) + 1
    launch_capex = (
        tax_profile.one_time_launch_capex_millions if yr == launch_capex_yr else 0.0
    )

    after_tax_fcf = after_tax_ebit - maintenance_capex - working_capital - launch_capex

    return (
        usable_nol, nol_remaining, taxable_income, cash_tax, after_tax_ebit,
        maintenance_capex, working_capital, launch_capex, after_tax_fcf,
    )


# ---------------------------------------------------------------------------
# TaxAudit — per-year audit trail
# ---------------------------------------------------------------------------

class TaxAudit(BaseModel, frozen=True):
    """
    Per-year tax and FCF audit trail produced when a TaxProfile is used.

    Each list has one entry per commercial year (same indexing as ebit_by_year).
    Year 1 = first year post-approval/launch.

    Fields
    ------
    pre_tax_adjusted_ebit_by_year : EBIT after royalty and profit_share, before tax.
    taxable_income_by_year        : max(adjusted_ebit, 0) — loss years show 0.
    nol_used_by_year              : NOL consumed in each year.
    remaining_nol_by_year         : NOL balance after each year.
    cash_tax_by_year              : Cash taxes paid each year.
    after_tax_ebit_by_year        : adjusted_ebit − cash_tax (before capex/WC).
    capex_by_year                 : maintenance_capex + launch_capex per year.
    working_capital_by_year       : working capital build per year.
    after_tax_fcf_by_year         : after_tax_ebit − capex − working_capital per year.
    tax_profile_used              : The TaxProfile that produced this audit.
    """
    pre_tax_adjusted_ebit_by_year: list[float] = Field(default_factory=list)
    taxable_income_by_year: list[float] = Field(default_factory=list)
    nol_used_by_year: list[float] = Field(default_factory=list)
    remaining_nol_by_year: list[float] = Field(default_factory=list)
    cash_tax_by_year: list[float] = Field(default_factory=list)
    after_tax_ebit_by_year: list[float] = Field(default_factory=list)
    capex_by_year: list[float] = Field(default_factory=list)
    working_capital_by_year: list[float] = Field(default_factory=list)
    after_tax_fcf_by_year: list[float] = Field(default_factory=list)
    tax_profile_used: Optional[TaxProfile] = None
