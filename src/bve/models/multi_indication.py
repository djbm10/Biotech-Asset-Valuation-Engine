"""
Multi-indication modeling: aggregate rNPV across a primary indication and one or more
label-expansion indications for the same drug asset.

Architecture
------------
No second valuation engine is introduced.  The existing ValuationEngine is called once
per indication (primary + each secondary).  This module provides:

  1. SecondaryIndication  — config for a single label-expansion program
  2. MultiIndicationProgram — container: primary DrugAssetProgram + list of secondaries
  3. run_multi_indication_valuation() — orchestration function that calls ValuationEngine
     on each indication, applies cascade-PoS adjustment, and returns a combined result

Cascade PoS
-----------
When cascade_pos=True for a secondary indication, its rNPV is multiplied by the primary
program's cumulative P(approval).  This reflects the reality that a label expansion
approval is conditional on the primary indication being approved first.

    secondary_rnpv_adjusted = secondary_rnpv × P(primary approval)

The secondary DrugAssetProgram's own trial success probabilities are NOT modified.
They represent the additional clinical risk of the expansion trial, conditional on
the primary mechanism having worked.  The cascade multiplier is applied after the
secondary rNPV is computed — there is no double-counting.

When cascade_pos=False, the secondary rNPV is included as-is (independent programs).

conditional_pos_override
------------------------
By default the cascade multiplier is primary_output.rnpv.cumulative_success_probability.
Set conditional_pos_override on SecondaryIndication to substitute a different value,
e.g. when the secondary indication has a different regulatory/clinical dependency
than the full primary PoS.

Example
-------
    primary   = DrugAssetProgram.build(asset_a, trials_a, market_a)
    secondary = DrugAssetProgram.build(asset_b, trials_b, market_b)

    program = MultiIndicationProgram(
        primary_program=primary,
        secondary_programs=[
            SecondaryIndication(
                label="Indication B — Phase 3",
                drug_asset_program=secondary,
                launch_year_offset=3,
                cascade_pos=True,
            )
        ],
    )

    result = run_multi_indication_valuation(program, company)
    print(f"Combined rNPV: ${result.total_rnpv_millions:.1f}M")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from bve.models.drug_asset_program import DrugAssetProgram


# ---------------------------------------------------------------------------
# Config: franchise cost sharing
# ---------------------------------------------------------------------------

class FranchiseCostSharing(BaseModel):
    """
    Franchise-level cost sharing for a secondary indication.

    When a secondary indication shares infrastructure, manufacturing, or development
    costs with the primary franchise, modelling it as fully independent overstates
    the incremental cost burden.  This config captures three sharing levers:

    sga_share : float
        Fraction of this secondary's SG&A absorbed by the primary franchise.
        0.70 = 70% of SG&A is shared; secondary bears only 30%.
        Applied to both sgna_rate_launch and sgna_rate_mature.
    manufacturing_share : float
        Fraction of COGS reduction from shared manufacturing infrastructure.
        Reduces cogs_rate by this fraction.
        0.20 = secondary cogs_rate × (1 - 0.20) = 80% of base COGS rate.
    development_share : float
        Fraction of secondary trial costs already counted in the primary program.
        Reduces the secondary's cdev_cost_share by (1 - development_share).
        0.30 = secondary bears 70% of its trial costs (30% shared with primary).

    Scope guard: cost sharing only applies to secondary programs.
    The primary program's DealEconomics is never modified by this config.
    """
    sga_share: float = Field(default=0.0, ge=0.0, le=1.0)
    manufacturing_share: float = Field(default=0.0, ge=0.0, le=1.0)
    development_share: float = Field(default=0.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Config: one secondary indication
# ---------------------------------------------------------------------------

class SecondaryIndication(BaseModel):
    """
    Configuration for a single label-expansion or additional-indication program.

    Parameters
    ----------
    label : str
        Human-readable label, e.g. "Indication B — mBC Phase 3".
    drug_asset_program : DrugAssetProgram
        Fully configured program for this indication.  Must have its own Asset,
        trials, and MarketModel.  The Asset.id may differ from the primary Asset.id
        (e.g. same molecule, different asset record for the new indication).
    launch_year_offset : int
        Expected years after primary approval when this indication launches.
        Informational for now; does not shift discount timing in v1.
    cascade_pos : bool
        If True (default), multiply this indication's rNPV by primary P(approval).
        If False, treat as an independent program (full rNPV included regardless).
    conditional_pos_override : float, optional
        Override the cascade multiplier.  When None, uses the primary program's
        cumulative_success_probability from ValuationEngine output.
    """
    model_config = ConfigDict(frozen=True)

    label: str
    drug_asset_program: DrugAssetProgram
    launch_year_offset: int = Field(default=0, ge=0)
    cascade_pos: bool = True
    conditional_pos_override: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    cost_sharing: Optional[FranchiseCostSharing] = None


# ---------------------------------------------------------------------------
# Container: primary + secondaries
# ---------------------------------------------------------------------------

class MultiIndicationProgram(BaseModel):
    """
    Container for a multi-indication asset: one primary DrugAssetProgram plus
    any number of secondary label-expansion programs.

    Evaluation pattern (caller's responsibility):
        result = run_multi_indication_valuation(program, company)

    The primary program is always valued at full rNPV.
    Secondary programs are optionally cascade-adjusted by primary P(approval).
    """
    model_config = ConfigDict(frozen=True)

    primary_program: DrugAssetProgram
    secondary_programs: list[SecondaryIndication] = Field(default_factory=list)
    default_cost_sharing: FranchiseCostSharing = Field(default_factory=FranchiseCostSharing)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class IndicationResult:
    """rNPV result for a single indication (primary or secondary)."""
    label: str
    rnpv_millions: float               # rNPV as computed by ValuationEngine
    cascade_multiplier: float          # 1.0 for primary or cascade_pos=False
    adjusted_rnpv_millions: float      # rnpv_millions × cascade_multiplier
    cumulative_pos: float              # P(approval) from this indication's engine
    peak_sales_millions: float
    output: object                     # ValuationOutput — preserved for memo/reporting
    cost_sharing_benefit_millions: float = 0.0  # rNPV uplift from shared costs (0 for primary)


@dataclass
class MultiIndicationResult:
    """Combined rNPV and per-indication breakdown for a multi-indication asset."""
    primary: IndicationResult
    secondaries: list[IndicationResult] = field(default_factory=list)

    @property
    def total_rnpv_millions(self) -> float:
        return round(
            self.primary.adjusted_rnpv_millions
            + sum(s.adjusted_rnpv_millions for s in self.secondaries),
            2,
        )

    @property
    def all_indications(self) -> list[IndicationResult]:
        return [self.primary] + self.secondaries

    def summary(self) -> str:
        lines = [
            "",
            "=" * 65,
            "  Multi-Indication rNPV Summary",
            "=" * 65,
        ]
        for ind in self.all_indications:
            cascade_str = (
                "" if ind.cascade_multiplier == 1.0
                else f"  × {ind.cascade_multiplier:.2f} cascade"
            )
            lines.append(
                f"  {ind.label:<35}  ${ind.rnpv_millions:>8,.1f}M{cascade_str}"
                f"  → ${ind.adjusted_rnpv_millions:>8,.1f}M"
            )
        lines += [
            "─" * 65,
            f"  {'Combined rNPV':<35}  {'':>9}   ${self.total_rnpv_millions:>8,.1f}M",
            "=" * 65,
            "",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_multi_indication_valuation(
    program: MultiIndicationProgram,
    company,                          # bve.entities.company.Company
    mc_params=None,                   # bve.models.monte_carlo.MonteCarloParams | None
    apply_pos_model: bool = False,
    apply_design_model: bool = False,
) -> MultiIndicationResult:
    """
    Run ValuationEngine on the primary indication and each secondary, then combine.

    Parameters
    ----------
    program : MultiIndicationProgram
        Container holding primary + secondary DrugAssetPrograms.
    company : Company
        Company entity (provides cash, shares, ownership).
    mc_params : MonteCarloParams, optional
        Monte Carlo parameters.  Defaults applied per-indication if None.
    apply_pos_model : bool
        Passed through to each ValuationEngine instance.
    apply_design_model : bool
        Passed through to each ValuationEngine instance.

    Returns
    -------
    MultiIndicationResult with per-indication breakdown and combined rNPV.

    Notes
    -----
    - Cascade adjustment is applied AFTER each secondary ValuationEngine.run().
      The secondary program's own trial probabilities are never modified.
    - Each ValuationEngine call is independent; there is no shared state between
      primary and secondary engines.
    """
    from bve.valuation.valuation_engine import ValuationEngine

    # --- Primary ---
    primary_engine = ValuationEngine.from_program(
        program.primary_program,
        company,
        mc_params=mc_params,
        apply_pos_model=apply_pos_model,
        apply_design_model=apply_design_model,
    )
    primary_output = primary_engine.run()
    primary_pos = primary_output.rnpv.cumulative_success_probability

    primary_result = IndicationResult(
        label=f"{program.primary_program.asset.name} — {program.primary_program.asset.indication}",
        rnpv_millions=primary_output.rnpv.rnpv_millions,
        cascade_multiplier=1.0,
        adjusted_rnpv_millions=primary_output.rnpv.rnpv_millions,
        cumulative_pos=primary_pos,
        peak_sales_millions=primary_output.rnpv.peak_sales_millions,
        output=primary_output,
    )

    # --- Secondaries ---
    secondary_results = []
    for sec in program.secondary_programs:
        # Resolve effective cost sharing: per-secondary override or program default
        sharing = sec.cost_sharing if sec.cost_sharing is not None else program.default_cost_sharing
        has_sharing = (
            sharing.sga_share > 0.0
            or sharing.manufacturing_share > 0.0
            or sharing.development_share > 0.0
        )

        if has_sharing:
            # Build adjusted program reflecting franchise cost sharing
            mm = sec.drug_asset_program.market_model
            base_cogs_rate = mm.cogs_rate
            if mm.modality is None and "cogs_rate" not in mm.model_fields_set:
                from bve.config.assumptions_loader import AssumptionsLoader

                base_cogs_rate = AssumptionsLoader.get().cogs_rate(
                    sec.drug_asset_program.asset.modality.value
                )
            adjusted_market = mm.model_copy(update={
                "sgna_rate_launch": mm.sgna_rate_launch * (1.0 - sharing.sga_share),
                "sgna_rate_mature": mm.sgna_rate_mature * (1.0 - sharing.sga_share),
                "cogs_rate": base_cogs_rate * (1.0 - sharing.manufacturing_share),
            })
            de = sec.drug_asset_program.deal_economics
            adjusted_deal = de.model_copy(update={
                "cdev_cost_share": de.cdev_cost_share * (1.0 - sharing.development_share),
            })
            adjusted_program = sec.drug_asset_program.model_copy(update={
                "market_model": adjusted_market,
                "deal_economics": adjusted_deal,
            })

            # Run with sharing applied
            sec_engine = ValuationEngine.from_program(
                adjusted_program,
                company,
                mc_params=mc_params,
                apply_pos_model=apply_pos_model,
                apply_design_model=apply_design_model,
            )
            sec_output = sec_engine.run()
            shared_rnpv = sec_output.rnpv.rnpv_millions

            # Run baseline (no sharing) to compute benefit
            base_engine = ValuationEngine.from_program(
                sec.drug_asset_program,
                company,
                mc_params=mc_params,
                apply_pos_model=apply_pos_model,
                apply_design_model=apply_design_model,
            )
            base_output = base_engine.run()
            cost_sharing_benefit = round(shared_rnpv - base_output.rnpv.rnpv_millions, 2)
            sec_rnpv = shared_rnpv
        else:
            sec_engine = ValuationEngine.from_program(
                sec.drug_asset_program,
                company,
                mc_params=mc_params,
                apply_pos_model=apply_pos_model,
                apply_design_model=apply_design_model,
            )
            sec_output = sec_engine.run()
            sec_rnpv = sec_output.rnpv.rnpv_millions
            cost_sharing_benefit = 0.0

        if sec.cascade_pos:
            multiplier = sec.conditional_pos_override if sec.conditional_pos_override is not None else primary_pos
        else:
            multiplier = 1.0

        secondary_results.append(IndicationResult(
            label=sec.label,
            rnpv_millions=sec_rnpv,
            cascade_multiplier=multiplier,
            adjusted_rnpv_millions=round(sec_rnpv * multiplier, 2),
            cumulative_pos=sec_output.rnpv.cumulative_success_probability,
            peak_sales_millions=sec_output.rnpv.peak_sales_millions,
            output=sec_output,
            cost_sharing_benefit_millions=cost_sharing_benefit,
        ))

    return MultiIndicationResult(primary=primary_result, secondaries=secondary_results)
