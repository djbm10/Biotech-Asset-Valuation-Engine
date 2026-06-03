"""
ScenarioTree — outcome-branch decomposition for BD/M&A and investment memos.

A ScenarioTree decomposes a named scenario (Bull, Base, Bear, or any custom
scenario) into three orthogonal outcome axes, each with named branches:

  Clinical outcome  × Regulatory outcome  × Commercial outcome

Each named branch maps to a specific ScenarioShock composition.  The caller
can either:
  (a) Build a ScenarioTree from pre-defined branches using ``from_named_branches()``.
  (b) Compose branches directly and call ``to_shock()`` on the resulting
      ``OutcomeBranch``.

Design rules
------------
- Branches are immutable (frozen Pydantic).
- Each branch declares its shock via a ``ScenarioShock`` — it does NOT apply
  the shock.  Application happens in ``valuation/scenario.py``.
- ``ScenarioTree.to_shock()`` composes the three branch shocks into a single
  ``ScenarioShock`` by merging non-default fields (last-write-wins per field,
  with explicit documentation).

Named branches
--------------
Clinical: failure, mixed_result, success, strong_success
Regulatory: standard_approval, accelerated_approval, narrow_label, delay_crl,
            confirmatory_required
Commercial: strong_launch, normal_launch, payer_restricted_launch,
            competitor_disrupted_launch
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from bve.models.scenario_shock import (
    ClinicalShock,
    CommercialShock,
    CompetitionShock,
    CostsFCFShock,
    RegulatoryShock,
    ScenarioShock,
)

# ---------------------------------------------------------------------------
# Outcome type literals
# ---------------------------------------------------------------------------

ClinicalOutcome = Literal[
    "failure",
    "mixed_result",
    "success",
    "strong_success",
]

RegulatoryOutcome = Literal[
    "standard_approval",
    "accelerated_approval",
    "narrow_label",
    "delay_crl",
    "confirmatory_required",
]

CommercialOutcome = Literal[
    "strong_launch",
    "normal_launch",
    "payer_restricted_launch",
    "competitor_disrupted_launch",
]


# ---------------------------------------------------------------------------
# OutcomeBranch — one axis of the tree
# ---------------------------------------------------------------------------

class OutcomeBranch(BaseModel):
    """A single named outcome branch with its associated ScenarioShock."""
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    shock: ScenarioShock


# ---------------------------------------------------------------------------
# Branch libraries
# ---------------------------------------------------------------------------

# Clinical outcome branches
CLINICAL_BRANCHES: dict[ClinicalOutcome, OutcomeBranch] = {
    "failure": OutcomeBranch(
        name="Endpoint Miss",
        description="Phase 3 primary endpoint missed; commercial revenue near zero",
        shock=ScenarioShock(
            label="Endpoint Miss",
            clinical=ClinicalShock(pos_mult=0.0),      # forces P(approval) → 0
            costs_fcf=CostsFCFShock(rd_cost_mult=1.0), # sunk costs remain
        ),
    ),
    "mixed_result": OutcomeBranch(
        name="Mixed Result",
        description="Primary endpoint met with modest effect size; subgroup dependence",
        shock=ScenarioShock(
            label="Mixed Result",
            clinical=ClinicalShock(
                pos_mult=0.80,
                safety_profile_override="manageable",
            ),
            regulatory=RegulatoryShock(
                label_breadth_mult=0.75,
                duration_add_years=0.5,
            ),
            commercial=CommercialShock(
                peak_penetration_mult=0.75,
                payer_access_probability_mult=0.85,
            ),
        ),
    ),
    "success": OutcomeBranch(
        name="Clinical Success",
        description="Primary endpoint met with clinically meaningful effect",
        shock=ScenarioShock(
            label="Clinical Success",
            clinical=ClinicalShock(pos_mult=1.0),
        ),
    ),
    "strong_success": OutcomeBranch(
        name="Strong Success",
        description="Exceeds primary endpoint; favorable safety; broad label expected",
        shock=ScenarioShock(
            label="Strong Success",
            clinical=ClinicalShock(
                pos_mult=1.25,
                safety_profile_override="clean",
                breakthrough_designation_override=True,
            ),
            regulatory=RegulatoryShock(
                label_breadth_mult=1.20,
                duration_add_years=-0.5,
            ),
            commercial=CommercialShock(
                peak_penetration_mult=1.25,
                payer_access_probability_mult=0.95,
            ),
        ),
    ),
}

# Regulatory outcome branches
REGULATORY_BRANCHES: dict[RegulatoryOutcome, OutcomeBranch] = {
    "standard_approval": OutcomeBranch(
        name="Standard Approval",
        description="Full approval on standard review timeline",
        shock=ScenarioShock(label="Standard Approval"),
    ),
    "accelerated_approval": OutcomeBranch(
        name="Accelerated Approval",
        description="Accelerated/conditional approval; faster to market",
        shock=ScenarioShock(
            label="Accelerated Approval",
            regulatory=RegulatoryShock(
                approval_pathway_override="accelerated",
                duration_add_years=-1.0,
            ),
        ),
    ),
    "narrow_label": OutcomeBranch(
        name="Narrow Label",
        description="Restricted label; smaller eligible population",
        shock=ScenarioShock(
            label="Narrow Label",
            regulatory=RegulatoryShock(label_breadth_mult=0.60),
            commercial=CommercialShock(peak_penetration_mult=0.80),
        ),
    ),
    "delay_crl": OutcomeBranch(
        name="Delay / CRL",
        description="Complete Response Letter or agency request for additional data",
        shock=ScenarioShock(
            label="Delay / CRL",
            regulatory=RegulatoryShock(
                duration_add_years=1.5,
                crl_delay_add_years=1.0,
            ),
            costs_fcf=CostsFCFShock(rd_cost_mult=1.15),
        ),
    ),
    "confirmatory_required": OutcomeBranch(
        name="Confirmatory Trial Required",
        description="Accelerated approval requires confirmatory Phase 3 post-approval",
        shock=ScenarioShock(
            label="Confirmatory Required",
            regulatory=RegulatoryShock(
                approval_pathway_override="accelerated",
                confirmatory_trial_cost_millions=200.0,
                duration_add_years=-1.0,
            ),
        ),
    ),
}

# Commercial outcome branches
COMMERCIAL_BRANCHES: dict[CommercialOutcome, OutcomeBranch] = {
    "strong_launch": OutcomeBranch(
        name="Strong Launch",
        description="KOL-driven fast uptake; favorable payer access; high penetration",
        shock=ScenarioShock(
            label="Strong Launch",
            commercial=CommercialShock(
                peak_penetration_mult=1.30,
                payer_access_probability_mult=0.95,
                years_to_peak_add=-1.0,
                net_price_mult=1.05,
            ),
        ),
    ),
    "normal_launch": OutcomeBranch(
        name="Normal Launch",
        description="Typical specialty launch; standard payer friction",
        shock=ScenarioShock(label="Normal Launch"),
    ),
    "payer_restricted_launch": OutcomeBranch(
        name="Payer-Restricted Launch",
        description="Significant prior authorization burden; restricted formulary access",
        shock=ScenarioShock(
            label="Payer-Restricted Launch",
            commercial=CommercialShock(
                peak_penetration_mult=0.60,
                payer_access_probability_mult=0.65,
                prior_auth_burden_delta=0.35,
                years_to_peak_add=2.0,
                gross_to_net_rate_delta=0.08,
            ),
        ),
    ),
    "competitor_disrupted_launch": OutcomeBranch(
        name="Competitor-Disrupted Launch",
        description="One or more late-stage competitors approved; market share compressed",
        shock=ScenarioShock(
            label="Competitor-Disrupted Launch",
            commercial=CommercialShock(
                peak_penetration_mult=0.65,
                net_price_mult=0.88,
                annual_price_erosion_delta=0.04,
            ),
            competition=CompetitionShock(
                competitor_approval_prob_mult=1.30,
                competitor_market_share_mult=1.25,
                competition_price_pressure_delta=0.04,
            ),
        ),
    ),
}


# ---------------------------------------------------------------------------
# ScenarioTree — three-axis outcome composition
# ---------------------------------------------------------------------------

class ScenarioTree(BaseModel):
    """
    Three-axis outcome scenario for BD/M&A and investment memos.

    Parameters
    ----------
    clinical_branch
        Named clinical outcome or custom ``OutcomeBranch``.
    regulatory_branch
        Named regulatory outcome or custom ``OutcomeBranch``.
    commercial_branch
        Named commercial outcome or custom ``OutcomeBranch``.
    label
        Override label for the composed scenario.  If not provided, auto-generated
        from branch names.
    description
        Override description.  If not provided, auto-generated.
    """
    model_config = ConfigDict(frozen=True)

    clinical_branch: OutcomeBranch
    regulatory_branch: OutcomeBranch
    commercial_branch: OutcomeBranch
    label: Optional[str] = None
    description: Optional[str] = None

    # -----------------------------------------------------------------------
    # Convenience properties
    # -----------------------------------------------------------------------

    @property
    def effective_label(self) -> str:
        if self.label:
            return self.label
        return (
            f"{self.clinical_branch.name} + "
            f"{self.regulatory_branch.name} + "
            f"{self.commercial_branch.name}"
        )

    @property
    def effective_description(self) -> str:
        if self.description:
            return self.description
        return (
            f"Clinical: {self.clinical_branch.description}. "
            f"Regulatory: {self.regulatory_branch.description}. "
            f"Commercial: {self.commercial_branch.description}."
        )

    def to_shock(self) -> ScenarioShock:
        """
        Compose the three branch shocks into a single ScenarioShock.

        Composition rule: each shock category is merged additively (deltas
        summed, multipliers multiplied, overrides last-write-wins in order
        clinical → regulatory → commercial).

        Returns a ``ScenarioShock`` with label/description from this tree.
        """
        return _compose_shocks(
            label=self.effective_label,
            description=self.effective_description,
            shocks=[
                self.clinical_branch.shock,
                self.regulatory_branch.shock,
                self.commercial_branch.shock,
            ],
        )


def _compose_shocks(
    label: str,
    description: str,
    shocks: list[ScenarioShock],
) -> ScenarioShock:
    """
    Merge multiple ScenarioShocks into one.

    Merging rules (applied in order; later shocks override earlier ones):
    - Multipliers: multiplied together
    - Deltas (additive): summed
    - Overrides (Optional): last non-None wins
    - pos_mult per-phase dicts: merged (later keys override earlier)
    """
    # Start with identity values
    pos_mult = 1.0
    per_phase: dict[str, float] = {}
    safety_override: Optional[str] = None
    biomarker_override: Optional[str] = None
    breakthrough_override: Optional[bool] = None
    logodds_delta = 0.0

    duration_add = 0.0
    pathway_override: Optional[str] = None
    label_breadth_mult = 1.0
    confirmatory_cost = 0.0
    crl_delay = 0.0

    patients_mult = 1.0
    penetration_mult = 1.0
    price_mult = 1.0
    g2n_delta = 0.0
    erosion_delta = 0.0
    years_to_peak_add = 0.0
    archetype_override: Optional[str] = None
    geo_delay = 0.0
    payer_access_mult = 1.0
    pa_burden_delta = 0.0
    reimbursement_mult = 1.0

    comp_approval_mult = 1.0
    comp_timing_add = 0.0
    comp_share_mult = 1.0
    comp_price_delta = 0.0

    rd_mult = 1.0
    cmc_mult = 1.0
    inflation_delta = 0.0
    cogs_delta = 0.0
    sgna_delta = 0.0
    capex_delta = 0.0
    wc_delta = 0.0
    tax_delta = 0.0
    wacc_delta = 0.0

    royalty_override: Optional[float] = None
    ps_override: Optional[float] = None
    cdev_override: Optional[float] = None
    ms_pay_mult = 1.0
    ms_recv_mult = 1.0

    for s in shocks:
        c = s.clinical
        pos_mult *= c.pos_mult
        per_phase.update(c.per_phase_pos_mult)
        if c.safety_profile_override is not None:
            safety_override = c.safety_profile_override
        if c.biomarker_selection_override is not None:
            biomarker_override = c.biomarker_selection_override
        if c.breakthrough_designation_override is not None:
            breakthrough_override = c.breakthrough_designation_override
        logodds_delta += c.prior_phase_data_logodds_delta

        r = s.regulatory
        duration_add += r.duration_add_years
        if r.approval_pathway_override is not None:
            pathway_override = r.approval_pathway_override
        label_breadth_mult *= r.label_breadth_mult
        confirmatory_cost += r.confirmatory_trial_cost_millions
        crl_delay += r.crl_delay_add_years

        cm = s.commercial
        patients_mult *= cm.addressable_patients_mult
        penetration_mult *= cm.peak_penetration_mult
        price_mult *= cm.net_price_mult
        g2n_delta += cm.gross_to_net_rate_delta
        erosion_delta += cm.annual_price_erosion_delta
        years_to_peak_add += cm.years_to_peak_add
        if cm.launch_archetype_override is not None:
            archetype_override = cm.launch_archetype_override
        geo_delay += cm.ex_us_launch_delay_add_years
        payer_access_mult *= cm.payer_access_probability_mult
        pa_burden_delta += cm.prior_auth_burden_delta
        reimbursement_mult *= cm.reimbursement_probability_mult

        co = s.competition
        comp_approval_mult *= co.competitor_approval_prob_mult
        comp_timing_add += co.competitor_launch_timing_add_years
        comp_share_mult *= co.competitor_market_share_mult
        comp_price_delta += co.competition_price_pressure_delta

        cf = s.costs_fcf
        rd_mult *= cf.rd_cost_mult
        cmc_mult *= cf.cmc_cost_mult
        inflation_delta += cf.cost_inflation_delta
        cogs_delta += cf.cogs_rate_delta
        sgna_delta += cf.sgna_rate_delta
        capex_delta += cf.maintenance_capex_rate_delta
        wc_delta += cf.working_capital_rate_delta
        tax_delta += cf.tax_rate_delta
        wacc_delta += cf.discount_rate_delta

        de = s.deal_economics
        if de.royalty_rate_override is not None:
            royalty_override = de.royalty_rate_override
        if de.profit_share_rate_override is not None:
            ps_override = de.profit_share_rate_override
        if de.cdev_cost_share_override is not None:
            cdev_override = de.cdev_cost_share_override
        ms_pay_mult *= de.milestone_payment_mult
        ms_recv_mult *= de.milestone_receipt_mult

    return ScenarioShock(
        label=label,
        description=description,
        clinical=ClinicalShock(
            pos_mult=pos_mult,
            per_phase_pos_mult=per_phase,
            safety_profile_override=safety_override,
            biomarker_selection_override=biomarker_override,
            breakthrough_designation_override=breakthrough_override,
            prior_phase_data_logodds_delta=logodds_delta,
        ),
        regulatory=RegulatoryShock(
            duration_add_years=duration_add,
            approval_pathway_override=pathway_override,
            label_breadth_mult=label_breadth_mult,
            confirmatory_trial_cost_millions=confirmatory_cost,
            crl_delay_add_years=crl_delay,
        ),
        commercial=CommercialShock(
            addressable_patients_mult=patients_mult,
            peak_penetration_mult=max(0.0, min(5.0, penetration_mult)),
            net_price_mult=max(0.0, price_mult),
            gross_to_net_rate_delta=max(-1.0, min(1.0, g2n_delta)),
            annual_price_erosion_delta=max(-1.0, min(1.0, erosion_delta)),
            years_to_peak_add=years_to_peak_add,
            launch_archetype_override=archetype_override,
            ex_us_launch_delay_add_years=max(0.0, geo_delay),
            payer_access_probability_mult=max(0.0, min(1.0, payer_access_mult)),
            prior_auth_burden_delta=max(-1.0, min(1.0, pa_burden_delta)),
            reimbursement_probability_mult=max(0.0, min(1.0, reimbursement_mult)),
        ),
        competition=CompetitionShock(
            competitor_approval_prob_mult=max(0.0, comp_approval_mult),
            competitor_launch_timing_add_years=comp_timing_add,
            competitor_market_share_mult=max(0.0, comp_share_mult),
            competition_price_pressure_delta=max(-1.0, min(1.0, comp_price_delta)),
        ),
        costs_fcf=CostsFCFShock(
            rd_cost_mult=max(0.0, rd_mult),
            cmc_cost_mult=max(0.0, cmc_mult),
            cost_inflation_delta=max(-0.5, min(0.5, inflation_delta)),
            cogs_rate_delta=max(-1.0, min(1.0, cogs_delta)),
            sgna_rate_delta=max(-1.0, min(1.0, sgna_delta)),
            maintenance_capex_rate_delta=max(-1.0, min(1.0, capex_delta)),
            working_capital_rate_delta=max(-1.0, min(1.0, wc_delta)),
            tax_rate_delta=max(-1.0, min(1.0, tax_delta)),
            discount_rate_delta=max(-0.5, min(0.5, wacc_delta)),
        ),
        deal_economics=_build_deal_shock(royalty_override, ps_override, cdev_override, ms_pay_mult, ms_recv_mult),
    )


def _build_deal_shock(
    royalty_override: Optional[float],
    ps_override: Optional[float],
    cdev_override: Optional[float],
    ms_pay_mult: float,
    ms_recv_mult: float,
) -> "ScenarioShock":  # returns DealEconomicsShock but avoids forward-ref F821
    from bve.models.scenario_shock import DealEconomicsShock
    return DealEconomicsShock(
        royalty_rate_override=royalty_override,
        profit_share_rate_override=ps_override,
        cdev_cost_share_override=cdev_override,
        milestone_payment_mult=max(0.0, ms_pay_mult),
        milestone_receipt_mult=max(0.0, ms_recv_mult),
    )


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def from_named_branches(
    clinical: ClinicalOutcome,
    regulatory: RegulatoryOutcome,
    commercial: CommercialOutcome,
    label: Optional[str] = None,
    description: Optional[str] = None,
) -> ScenarioTree:
    """
    Build a ScenarioTree from named branch identifiers.

    Example
    -------
    tree = from_named_branches("strong_success", "broad_label", "strong_launch")
    shock = tree.to_shock()
    """
    # broad_label is an alias for standard_approval with the strong_success branch
    # handling label expansion — use standard_approval if called that way
    _reg: RegulatoryOutcome = regulatory

    return ScenarioTree(
        clinical_branch=CLINICAL_BRANCHES[clinical],
        regulatory_branch=REGULATORY_BRANCHES[_reg],
        commercial_branch=COMMERCIAL_BRANCHES[commercial],
        label=label,
        description=description,
    )


# ---------------------------------------------------------------------------
# Pre-built canonical outcome trees
# ---------------------------------------------------------------------------

# Best-case: strong clinical + accelerated + strong launch
TREE_BEST_CASE = ScenarioTree(
    clinical_branch=CLINICAL_BRANCHES["strong_success"],
    regulatory_branch=REGULATORY_BRANCHES["accelerated_approval"],
    commercial_branch=COMMERCIAL_BRANCHES["strong_launch"],
    label="Best Case",
    description="Strong clinical success + accelerated approval + strong market launch",
)

# Base case: success + standard + normal launch
TREE_BASE_CASE = ScenarioTree(
    clinical_branch=CLINICAL_BRANCHES["success"],
    regulatory_branch=REGULATORY_BRANCHES["standard_approval"],
    commercial_branch=COMMERCIAL_BRANCHES["normal_launch"],
    label="Base Case",
    description="Clinical success + standard approval + normal launch",
)

# Conservative downside: mixed result + narrow label + payer-restricted
TREE_DOWNSIDE = ScenarioTree(
    clinical_branch=CLINICAL_BRANCHES["mixed_result"],
    regulatory_branch=REGULATORY_BRANCHES["narrow_label"],
    commercial_branch=COMMERCIAL_BRANCHES["payer_restricted_launch"],
    label="Conservative Downside",
    description="Mixed clinical result + narrow label + payer-restricted access",
)

# Failure: endpoint miss → near-zero commercial value
TREE_FAILURE = ScenarioTree(
    clinical_branch=CLINICAL_BRANCHES["failure"],
    regulatory_branch=REGULATORY_BRANCHES["standard_approval"],  # irrelevant — no approval
    commercial_branch=COMMERCIAL_BRANCHES["normal_launch"],       # irrelevant — no launch
    label="Endpoint Miss",
    description="Phase 3 primary endpoint missed; no approval; residual pipeline option value only",
)

# Confirmatory liability: accelerated approval but confirmatory required + competitor disruption
TREE_CONFIRMATORY_COMPETITOR = ScenarioTree(
    clinical_branch=CLINICAL_BRANCHES["success"],
    regulatory_branch=REGULATORY_BRANCHES["confirmatory_required"],
    commercial_branch=COMMERCIAL_BRANCHES["competitor_disrupted_launch"],
    label="Confirmatory + Competitive Pressure",
    description="Accelerated approval with confirmatory obligation + competitor-disrupted launch",
)
