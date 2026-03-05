"""
Explicit assumption logging — every modeled number traces to a source or rationale.

Design goal: every ValuationOutput carries an AssumptionLog so that
anyone reading the memo or JSON can see exactly what was assumed and why.

Philosophy
----------
"Every assumption that materially affects rNPV must be documented."
If you can't explain it in a sentence, you shouldn't be modeling it.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class KeyAssumption(BaseModel):
    parameter: str
    value: str
    source: str
    sensitivity: str     # "High" | "Medium" | "Low" — impact on rNPV
    notes: Optional[str] = None


class AssumptionLog(BaseModel):
    """
    Explicit audit trail of all key modeling assumptions.
    Populated by ValuationEngine and attached to ValuationOutput.
    """

    # --- Valuation mechanics ---
    discount_rate: KeyAssumption
    patent_life: KeyAssumption
    net_ownership: KeyAssumption

    # --- Market model ---
    addressable_patients: Optional[KeyAssumption] = None
    net_price: Optional[KeyAssumption] = None
    gross_to_net: Optional[KeyAssumption] = None
    cogs_rate: KeyAssumption
    peak_penetration: KeyAssumption
    years_to_peak: KeyAssumption
    sgna_structure: KeyAssumption

    # --- Clinical / POS ---
    pos_methodology: KeyAssumption
    phase_pos_list: list[KeyAssumption]     # one per remaining phase

    # --- Limitations ---
    limitations: list[str] = []

    # --- What would change the thesis ---
    thesis_changers: list[str] = []

    def to_flat_list(self) -> list[KeyAssumption]:
        """Return all scalar KeyAssumptions as a flat list for table rendering."""
        items = [
            self.discount_rate,
            self.patent_life,
            self.net_ownership,
        ]
        if self.addressable_patients:
            items.append(self.addressable_patients)
        if self.net_price:
            items.append(self.net_price)
        if self.gross_to_net:
            items.append(self.gross_to_net)
        items += [
            self.cogs_rate,
            self.peak_penetration,
            self.years_to_peak,
            self.sgna_structure,
            self.pos_methodology,
        ]
        items += self.phase_pos_list
        return items


def build_assumption_log(
    asset,
    trials,
    market_model,
    rnpv_result,
    pos_methodology_note: str = "Industry-prior base rates (Biomedtracker/IQVIA 2021) adjusted in log-odds space for endpoint quality, MoA precedent, biomarker selection, safety profile, and competitive dynamics.",
    limitations: Optional[list[str]] = None,
    thesis_changers: Optional[list[str]] = None,
) -> AssumptionLog:
    """
    Auto-generate an AssumptionLog from model inputs and outputs.

    The caller can pass custom limitations and thesis_changers
    (from the YAML config) to override the generic defaults.
    """
    # --- Phase POS entries ---
    phase_entries: list[KeyAssumption] = []
    for pb in rnpv_result.phase_breakdown:
        phase_entries.append(KeyAssumption(
            parameter=f"P(Success | {pb.phase.upper().replace('_', ' ')})",
            value=f"{pb.success_probability:.0%}",
            source="Analyst estimate; adjusted from TA-specific prior via POS model",
            sensitivity="High",
            notes=f"P(reaching this phase) = {pb.prob_reaching:.0%}",
        ))

    # --- GTN ---
    if market_model.total_addressable_market_millions is not None:
        gtn_note = None
        gtn_assum = None
    else:
        from bve.config.constants import GROSS_TO_NET_DISCOUNT
        gtn_rate = GROSS_TO_NET_DISCOUNT.get(asset.modality.value, 0.30)
        gtn_assum = KeyAssumption(
            parameter="Gross-to-Net Discount",
            value=f"{gtn_rate:.0%}",
            source=f"SSR Health / CMS data benchmarks for {asset.modality.value.replace('_',' ')} in {asset.therapeutic_area.value.replace('_',' ')}",
            sensitivity="Medium",
            notes="Applied to WAC to derive net realized price. G2N ranges widely by therapeutic area and payer mix.",
        )

    # --- Default limitations ---
    default_limitations = [
        "US market only; ex-US contribution not modeled (typically adds 30-50% for a global asset).",
        f"Patient population derived from public epidemiology data; actual eligible pool subject to diagnostic rate, testing penetration, and label restrictions.",
        f"Competition modeled as fixed penetration ceiling; does not simulate dynamic market share over time.",
        "Tax effects, R&D tax credits, and operating leverage not modeled at the company level.",
        "Milestone payments to partners are excluded from base-case rNPV.",
        "Post-loss-of-exclusivity revenues are assumed zero; biosimilar/generic erosion not modeled.",
    ]

    # --- Default thesis changers ---
    default_thesis_changers = [
        "Phase 2/3 ORR or PFS data significantly above or below the expected efficacy bar.",
        "FDA grants or revokes Breakthrough Therapy designation (major POS signal).",
        f"Competitor drug achieves superior label (broader population, better efficacy, or lower price).",
        "Unexpected safety findings (Grade 3+ on-target toxicities or SAEs) trigger clinical hold.",
        f"Payer/reimbursement environment shifts materially (Part D restructuring, IRA negotiation).",
        "Company secures a partnership or acquisition offer at a significant premium to NAV.",
        "Cash runway falls below 4 quarters without a clear financing path (increases dilution risk).",
    ]

    net_margin_pct = (1.0 - market_model.cogs_rate - market_model.sgna_rate_mature) * 100

    log = AssumptionLog(
        discount_rate=KeyAssumption(
            parameter="WACC (Discount Rate)",
            value=f"{asset.discount_rate:.0%}",
            source="Damodaran biotech sector WACC; standard industry convention for clinical-stage assets",
            sensitivity="High",
            notes="A ±2pp change in WACC shifts rNPV by ~10-15%. Use company-specific beta for more precision.",
        ),
        patent_life=KeyAssumption(
            parameter="Commercial Horizon",
            value=f"{market_model.patent_life_years} years post-launch",
            source="Estimated based on typical composition-of-matter patent + PTE; NCE status assumed",
            sensitivity="Medium",
            notes="Assumes no material generic/biosimilar entry until year {}. Actual IP position should be verified.".format(market_model.patent_life_years),
        ),
        net_ownership=KeyAssumption(
            parameter="Net Economic Ownership",
            value=f"{asset.net_ownership:.0%}",
            source="Implied by royalty_rate in config; adjust for any licensed-in/out deal terms",
            sensitivity="Medium",
        ),
        addressable_patients=KeyAssumption(
            parameter="Addressable Patients (annual, US)",
            value=f"{market_model.addressable_patients_annual:,}" if market_model.addressable_patients_annual else "N/A (TAM-based model)",
            source="Public epidemiology data (SEER, IQVIA, company KOL slides); analyst adjustment for eligible fraction",
            sensitivity="High",
            notes="Represents diagnosed + treated + biomarker-eligible patients in US per year.",
        ) if market_model.addressable_patients_annual else None,
        net_price=KeyAssumption(
            parameter="Net Price per Patient / Year (US)",
            value=f"${market_model.net_price_per_patient_usd:,.0f}" if market_model.net_price_per_patient_usd else "N/A",
            source="Benchmarked against approved comps; WAC × (1 – GTN). See pricing_refs.py for comp table.",
            sensitivity="High",
            notes="Single biggest swing factor in peak sales. Validate against approved drug pricing in same class.",
        ) if market_model.net_price_per_patient_usd else None,
        gross_to_net=gtn_assum,
        cogs_rate=KeyAssumption(
            parameter="COGS Rate",
            value=f"{market_model.cogs_rate:.0%} of net revenue",
            source=f"Industry benchmark for {asset.modality.value.replace('_',' ')}; DiMasi / company gross margin disclosures",
            sensitivity="Low",
        ),
        peak_penetration=KeyAssumption(
            parameter="Peak Market Penetration",
            value=f"{market_model.peak_penetration:.0%} of addressable patients",
            source="Analyst estimate based on competitive positioning, differentiation, and comparable launch trajectories",
            sensitivity="High",
            notes=f"Reaches peak in year {market_model.years_to_peak} post-launch. Modeled as linear ramp.",
        ),
        years_to_peak=KeyAssumption(
            parameter="Years to Peak Sales",
            value=f"{market_model.years_to_peak} years post-launch",
            source="Comparable product launches in specialty/oncology; faster for biomarker-selected populations",
            sensitivity="Low",
        ),
        sgna_structure=KeyAssumption(
            parameter="SG&A Structure",
            value=f"{market_model.sgna_rate_launch:.0%} (launch) → {market_model.sgna_rate_mature:.0%} (mature) of revenue",
            source="Industry benchmarks; specialty pharma commercial model. Net margin at maturity: {:.0%}".format(net_margin_pct / 100),
            sensitivity="Low",
        ),
        pos_methodology=KeyAssumption(
            parameter="POS Methodology",
            value="Heuristic log-odds model",
            source=pos_methodology_note,
            sensitivity="High",
            notes="Base rates from Biomedtracker/IQVIA 2021. Adjusters calibrated to shift P by ±10-25pp per factor.",
        ),
        phase_pos_list=phase_entries,
        limitations=limitations or default_limitations,
        thesis_changers=thesis_changers or default_thesis_changers,
    )

    return log
