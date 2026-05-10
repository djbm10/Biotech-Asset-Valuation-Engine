"""
ScenarioShock — per-category input shock specification for scenario analysis.

A ScenarioShock describes how a named scenario (Bull, Base, Bear, or any custom
branch) differs from the base-case model inputs.  It is a pure data container:
it declares *what* changes but does not apply them.  Sprint 31B wires shock
application into the engine.

Design rules
------------
- Zero-effect defaults: a ``ScenarioShock()`` with no arguments produces
  identically the same rNPV as the base case.
- Multiplicative fields default to ``1.0`` (no change).
- Additive delta fields default to ``0.0`` (no change).
- Override fields (``Optional``) default to ``None`` (use base value).
- Frozen Pydantic model — immutable after construction.

Six categories
--------------
1. Clinical / POS
2. Regulatory
3. Commercial
4. Competition
5. Costs / FCF
6. Deal economics
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Category 1 — Clinical / POS
# ---------------------------------------------------------------------------

class ClinicalShock(BaseModel):
    """Shocks to probability-of-success and clinical evidence quality."""
    model_config = ConfigDict(frozen=True)

    # Uniform POS multiplier across all phases (1.0 = no change)
    pos_mult: float = Field(default=1.0, ge=0.0, le=5.0,
        description="Uniform multiplier applied to each phase success probability")

    # Per-phase POS multipliers; keys are phase strings e.g. 'phase_1', 'phase_2', 'phase_3'
    # Applied after pos_mult.  Missing phases use pos_mult only.
    per_phase_pos_mult: dict[str, float] = Field(default_factory=dict,
        description="Per-phase POS multipliers (applied after pos_mult)")

    # Safety profile override — string value of SafetyProfile enum or None
    safety_profile_override: Optional[str] = Field(default=None,
        description="Override POSAdjusters.safety_profile (e.g. 'clean', 'manageable', 'serious')")

    # Biomarker selection strength override — string value of BiomarkerSelectionStrength or None
    biomarker_selection_override: Optional[str] = Field(default=None,
        description="Override POSAdjusters.biomarker_selection")

    # Breakthrough designation override
    breakthrough_designation_override: Optional[bool] = Field(default=None,
        description="Override POSAdjusters.has_breakthrough_designation")

    # Prior-phase data strength adjustment (log-odds additive, e.g. +0.2 = stronger prior data)
    prior_phase_data_logodds_delta: float = Field(default=0.0,
        description="Additive log-odds adjustment for prior-phase data strength")

    @property
    def is_zero_effect(self) -> bool:
        return (
            self.pos_mult == 1.0
            and not self.per_phase_pos_mult
            and self.safety_profile_override is None
            and self.biomarker_selection_override is None
            and self.breakthrough_designation_override is None
            and self.prior_phase_data_logodds_delta == 0.0
        )


# ---------------------------------------------------------------------------
# Category 2 — Regulatory
# ---------------------------------------------------------------------------

class RegulatoryShock(BaseModel):
    """Shocks to approval timing, label scope, and regulatory pathway."""
    model_config = ConfigDict(frozen=True)

    # Additive years to each clinical phase duration (positive = delay, negative = faster)
    duration_add_years: float = Field(default=0.0,
        description="Additive years on each clinical phase duration")

    # Approval pathway override — string value of ApprovalPathway enum or None
    approval_pathway_override: Optional[str] = Field(default=None,
        description="Override approval pathway (e.g. 'accelerated', 'standard', 'full_approval')")

    # Label breadth multiplier — applied to addressable_patients_annual or TAM
    # (1.0 = full label, 0.6 = 40% narrower label, 1.2 = expanded indication)
    label_breadth_mult: float = Field(default=1.0, ge=0.0, le=5.0,
        description="Multiplier on eligible patient population (proxy for label breadth)")

    # Confirmatory trial cost — added to development costs (zero = no confirmatory obligation)
    confirmatory_trial_cost_millions: float = Field(default=0.0, ge=0.0,
        description="One-time confirmatory trial cost added to the cost stream (USD millions)")

    # CRL / delay risk — additional probability-weighted delay in years
    crl_delay_add_years: float = Field(default=0.0, ge=0.0,
        description="Expected delay from CRL or FDA response cycle (years, added to approval timing)")

    @property
    def is_zero_effect(self) -> bool:
        return (
            self.duration_add_years == 0.0
            and self.approval_pathway_override is None
            and self.label_breadth_mult == 1.0
            and self.confirmatory_trial_cost_millions == 0.0
            and self.crl_delay_add_years == 0.0
        )


# ---------------------------------------------------------------------------
# Category 3 — Commercial
# ---------------------------------------------------------------------------

class CommercialShock(BaseModel):
    """Shocks to revenue drivers: population, price, penetration, access, geography."""
    model_config = ConfigDict(frozen=True)

    # Patient population / TAM multiplier (label_breadth_mult in RegulatoryShock narrows label;
    # this separately captures epidemiology re-estimation)
    addressable_patients_mult: float = Field(default=1.0, ge=0.0,
        description="Multiplier on addressable_patients_annual or TAM")

    # Peak penetration multiplier
    peak_penetration_mult: float = Field(default=1.0, ge=0.0, le=5.0,
        description="Multiplier on peak_penetration")

    # Net price multiplier (applied to net_price_per_patient_usd)
    net_price_mult: float = Field(default=1.0, ge=0.0,
        description="Multiplier on net_price_per_patient_usd")

    # Gross-to-net additive delta (e.g. +0.05 = 5pp more rebate pressure)
    gross_to_net_rate_delta: float = Field(default=0.0, ge=-1.0, le=1.0,
        description="Additive change to gross_to_net_rate")

    # Annual price erosion delta (additive, e.g. +0.03 = 3pp faster price decay per year)
    annual_price_erosion_delta: float = Field(default=0.0, ge=-1.0, le=1.0,
        description="Additive change to annual price erosion rate")

    # Years to peak adoption — additive (positive = slower uptake ramp)
    years_to_peak_add: float = Field(default=0.0,
        description="Additive years to peak adoption (positive = slower ramp)")

    # Launch archetype override — string name or None
    launch_archetype_override: Optional[str] = Field(default=None,
        description="Override launch_archetype (e.g. 'oncology_specialist', 'primary_care_broad')")

    # Geography launch delay — additive years for ex-US launch
    ex_us_launch_delay_add_years: float = Field(default=0.0, ge=0.0,
        description="Additional ex-US launch delay in years")

    # Payer access probability multiplier
    payer_access_probability_mult: float = Field(default=1.0, ge=0.0, le=1.0,
        description="Multiplier on PayerAccessModel.access_probability (capped at 1.0)")

    # Prior authorization burden delta (additive, 0.0–1.0 scale)
    prior_auth_burden_delta: float = Field(default=0.0, ge=-1.0, le=1.0,
        description="Additive change to PayerAccessModel.prior_auth_burden")

    # Reimbursement probability multiplier (region-specific access risk)
    reimbursement_probability_mult: float = Field(default=1.0, ge=0.0, le=1.0,
        description="Multiplier on reimbursement probability (if modeled per region)")

    @property
    def is_zero_effect(self) -> bool:
        return (
            self.addressable_patients_mult == 1.0
            and self.peak_penetration_mult == 1.0
            and self.net_price_mult == 1.0
            and self.gross_to_net_rate_delta == 0.0
            and self.annual_price_erosion_delta == 0.0
            and self.years_to_peak_add == 0.0
            and self.launch_archetype_override is None
            and self.ex_us_launch_delay_add_years == 0.0
            and self.payer_access_probability_mult == 1.0
            and self.prior_auth_burden_delta == 0.0
            and self.reimbursement_probability_mult == 1.0
        )


# ---------------------------------------------------------------------------
# Category 4 — Competition
# ---------------------------------------------------------------------------

class CompetitionShock(BaseModel):
    """Shocks to competitor landscape: approval odds, timing, share, price pressure."""
    model_config = ConfigDict(frozen=True)

    # Multiplier on each pipeline competitor's approval_probability
    competitor_approval_prob_mult: float = Field(default=1.0, ge=0.0,
        description="Multiplier on each pipeline competitor's approval_probability")

    # Additive years to each competitor's launch_year_relative (positive = delayed entry)
    competitor_launch_timing_add_years: float = Field(default=0.0,
        description="Additive years to each competitor's launch_year_relative")

    # Multiplier on each competitor's peak_market_share
    competitor_market_share_mult: float = Field(default=1.0, ge=0.0,
        description="Multiplier on each competitor's peak_market_share")

    # Competition-driven net price pressure delta (additive annual erosion rate, e.g. +0.03)
    competition_price_pressure_delta: float = Field(default=0.0, ge=-1.0, le=1.0,
        description="Additive price erosion rate from competitive intensity")

    @property
    def is_zero_effect(self) -> bool:
        return (
            self.competitor_approval_prob_mult == 1.0
            and self.competitor_launch_timing_add_years == 0.0
            and self.competitor_market_share_mult == 1.0
            and self.competition_price_pressure_delta == 0.0
        )


# ---------------------------------------------------------------------------
# Category 5 — Costs / FCF
# ---------------------------------------------------------------------------

class CostsFCFShock(BaseModel):
    """Shocks to development costs, manufacturing, and FCF components."""
    model_config = ConfigDict(frozen=True)

    # Trial R&D cost multiplier (applied to all phase cost_millions)
    rd_cost_mult: float = Field(default=1.0, ge=0.0,
        description="Multiplier on all clinical trial R&D costs")

    # CMC / manufacturing cost multiplier
    cmc_cost_mult: float = Field(default=1.0, ge=0.0,
        description="Multiplier on CMC / manufacturing costs")

    # Cost inflation rate delta (additive, e.g. +0.02 = 2pp higher annual inflation)
    cost_inflation_delta: float = Field(default=0.0, ge=-0.5, le=0.5,
        description="Additive change to annual cost inflation rate")

    # COGS rate delta (additive, e.g. +0.03 = 3pp higher COGS)
    cogs_rate_delta: float = Field(default=0.0, ge=-1.0, le=1.0,
        description="Additive change to cogs_rate")

    # SG&A rate delta (additive, applied uniformly to launch and mature rates)
    sgna_rate_delta: float = Field(default=0.0, ge=-1.0, le=1.0,
        description="Additive change to sgna_rate_launch and sgna_rate_mature")

    # Maintenance capex rate delta (TaxProfile.annual_maintenance_capex_rate)
    maintenance_capex_rate_delta: float = Field(default=0.0, ge=-1.0, le=1.0,
        description="Additive change to TaxProfile.annual_maintenance_capex_rate")

    # Working capital rate delta (TaxProfile.working_capital_rate)
    working_capital_rate_delta: float = Field(default=0.0, ge=-1.0, le=1.0,
        description="Additive change to TaxProfile.working_capital_rate")

    # Effective tax rate delta (additive, e.g. +0.03 = bear scenario tax increase)
    tax_rate_delta: float = Field(default=0.0, ge=-1.0, le=1.0,
        description="Additive change to effective_tax_rate")

    # Discount rate (WACC) delta (additive, e.g. +0.01 = 100bps higher WACC)
    discount_rate_delta: float = Field(default=0.0, ge=-0.5, le=0.5,
        description="Additive change to discount_rate (WACC)")

    @property
    def is_zero_effect(self) -> bool:
        return (
            self.rd_cost_mult == 1.0
            and self.cmc_cost_mult == 1.0
            and self.cost_inflation_delta == 0.0
            and self.cogs_rate_delta == 0.0
            and self.sgna_rate_delta == 0.0
            and self.maintenance_capex_rate_delta == 0.0
            and self.working_capital_rate_delta == 0.0
            and self.tax_rate_delta == 0.0
            and self.discount_rate_delta == 0.0
        )


# ---------------------------------------------------------------------------
# Category 6 — Deal economics
# ---------------------------------------------------------------------------

class DealEconomicsShock(BaseModel):
    """Shocks to deal terms: royalties, profit share, cost share, milestones."""
    model_config = ConfigDict(frozen=True)

    # Full override for royalty rate (None = use base DealEconomics.royalty_rate)
    royalty_rate_override: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Override DealEconomics.royalty_rate")

    # Full override for profit-share rate
    profit_share_rate_override: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Override DealEconomics.profit_share_rate")

    # Full override for co-development cost share (1.0 = bear all costs, 0.5 = partner pays 50%)
    cdev_cost_share_override: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Override DealEconomics.cdev_cost_share")

    # Multiplier on payable milestone amounts
    milestone_payment_mult: float = Field(default=1.0, ge=0.0,
        description="Multiplier on all payable milestone amounts")

    # Multiplier on receivable milestone amounts
    milestone_receipt_mult: float = Field(default=1.0, ge=0.0,
        description="Multiplier on all receivable milestone amounts")

    @property
    def is_zero_effect(self) -> bool:
        return (
            self.royalty_rate_override is None
            and self.profit_share_rate_override is None
            and self.cdev_cost_share_override is None
            and self.milestone_payment_mult == 1.0
            and self.milestone_receipt_mult == 1.0
        )


# ---------------------------------------------------------------------------
# ScenarioShock — top-level composite
# ---------------------------------------------------------------------------

class ScenarioShock(BaseModel):
    """
    Complete input shock specification for one named scenario.

    All category sub-models default to zero-effect.  A ``ScenarioShock()``
    with no arguments is identical to the base case and can be used as a
    no-op placeholder.

    Parameters
    ----------
    label
        Human-readable scenario label (e.g. "Bull", "Bear", "Endpoint Miss").
    description
        One-line description of the scenario thesis.
    clinical
        Clinical/POS category shocks.
    regulatory
        Regulatory timing and label scope shocks.
    commercial
        Revenue driver shocks (price, penetration, population, access).
    competition
        Competitor landscape shocks.
    costs_fcf
        Development cost and FCF adjustment shocks.
    deal_economics
        Deal term shocks.
    """
    model_config = ConfigDict(frozen=True)

    label: str = Field(default="Custom", description="Scenario name")
    description: str = Field(default="", description="One-line scenario thesis")

    clinical: ClinicalShock = Field(default_factory=ClinicalShock)
    regulatory: RegulatoryShock = Field(default_factory=RegulatoryShock)
    commercial: CommercialShock = Field(default_factory=CommercialShock)
    competition: CompetitionShock = Field(default_factory=CompetitionShock)
    costs_fcf: CostsFCFShock = Field(default_factory=CostsFCFShock)
    deal_economics: DealEconomicsShock = Field(default_factory=DealEconomicsShock)

    # -----------------------------------------------------------------------
    # Convenience properties
    # -----------------------------------------------------------------------

    @property
    def is_zero_effect(self) -> bool:
        """True when every category is zero-effect (this IS the base case)."""
        return (
            self.clinical.is_zero_effect
            and self.regulatory.is_zero_effect
            and self.commercial.is_zero_effect
            and self.competition.is_zero_effect
            and self.costs_fcf.is_zero_effect
            and self.deal_economics.is_zero_effect
        )

    @property
    def categories_modified(self) -> list[str]:
        """Names of categories with at least one non-default field."""
        modified = []
        if not self.clinical.is_zero_effect:
            modified.append("clinical")
        if not self.regulatory.is_zero_effect:
            modified.append("regulatory")
        if not self.commercial.is_zero_effect:
            modified.append("commercial")
        if not self.competition.is_zero_effect:
            modified.append("competition")
        if not self.costs_fcf.is_zero_effect:
            modified.append("costs_fcf")
        if not self.deal_economics.is_zero_effect:
            modified.append("deal_economics")
        return modified

    @model_validator(mode="after")
    def _validate_per_phase_keys(self) -> "ScenarioShock":
        valid_phases = {"phase_1", "phase_1a", "phase_1b", "phase_2", "phase_2a",
                        "phase_2b", "phase_3", "nda_bla"}
        bad = set(self.clinical.per_phase_pos_mult) - valid_phases
        if bad:
            raise ValueError(
                f"ScenarioShock.clinical.per_phase_pos_mult contains unknown phase keys: {bad}. "
                f"Valid keys: {valid_phases}"
            )
        return self


# ---------------------------------------------------------------------------
# Canonical named shocks
# ---------------------------------------------------------------------------

SHOCK_BULL = ScenarioShock(
    label="Bull",
    description=(
        "Strong clinical data, clean safety, broad label, faster approval, "
        "strong payer access, higher penetration, favorable pricing, delayed competition"
    ),
    clinical=ClinicalShock(
        pos_mult=1.25,
        safety_profile_override="clean",
        breakthrough_designation_override=True,
    ),
    regulatory=RegulatoryShock(
        duration_add_years=-0.5,
        label_breadth_mult=1.20,
    ),
    commercial=CommercialShock(
        peak_penetration_mult=1.30,
        net_price_mult=1.10,
        payer_access_probability_mult=0.95,
        years_to_peak_add=-0.5,
    ),
    competition=CompetitionShock(
        competitor_approval_prob_mult=0.75,
        competitor_launch_timing_add_years=1.0,
    ),
    costs_fcf=CostsFCFShock(
        rd_cost_mult=0.90,
        discount_rate_delta=-0.01,
    ),
)

SHOCK_BASE = ScenarioShock(
    label="Base",
    description="Analyst-entered assumptions as configured",
)

SHOCK_BEAR = ScenarioShock(
    label="Bear",
    description=(
        "Weaker clinical effect, safety concern, narrower label, delayed approval, "
        "payer restrictions, lower penetration, faster competitor uptake, higher costs"
    ),
    clinical=ClinicalShock(
        pos_mult=0.75,
        safety_profile_override="manageable",
    ),
    regulatory=RegulatoryShock(
        duration_add_years=1.0,
        label_breadth_mult=0.70,
        crl_delay_add_years=0.5,
    ),
    commercial=CommercialShock(
        peak_penetration_mult=0.65,
        net_price_mult=0.90,
        gross_to_net_rate_delta=0.05,
        payer_access_probability_mult=0.75,
        prior_auth_burden_delta=0.20,
        years_to_peak_add=1.0,
    ),
    competition=CompetitionShock(
        competitor_approval_prob_mult=1.25,
        competitor_market_share_mult=1.20,
        competition_price_pressure_delta=0.03,
    ),
    costs_fcf=CostsFCFShock(
        rd_cost_mult=1.20,
        cogs_rate_delta=0.03,
        sgna_rate_delta=0.05,
        discount_rate_delta=0.02,
    ),
)
