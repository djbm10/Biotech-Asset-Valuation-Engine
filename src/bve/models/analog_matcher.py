"""Analog matcher — winning and failing historical analogues for POS and sales calibration."""

from __future__ import annotations

import statistics
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Analog(BaseModel):
    """A historical drug program used as a comparison point."""

    analog_id: str
    name: str
    indication: str
    target: Optional[str] = None
    mechanism: Optional[str] = None
    modality: Optional[str] = None
    phase_at_comparison: str
    outcome: str  # "approved" | "failed" | "ongoing"
    peak_sales_millions: Optional[float] = None
    pos_at_phase: Optional[float] = None


class AnalogMatch(BaseModel):
    """A matched analogue with similarity scoring and lessons."""

    focal_asset_id: str
    analog: Analog
    similarity_score: float = Field(ge=0.0, le=1.0)
    is_winner: bool
    key_similarities: list[str] = Field(default_factory=list)
    key_differences: list[str] = Field(default_factory=list)
    lesson: str


class AnalogMatcher(BaseModel):
    """Aggregated analogue matching result for a focal asset."""

    asset_id: str
    matched_at: datetime
    winning_analogs: list[AnalogMatch] = Field(default_factory=list)
    failing_analogs: list[AnalogMatch] = Field(default_factory=list)
    pos_implied_by_analogs: Optional[float] = None
    analog_confidence: float = Field(ge=0.0, le=1.0)
    summary: str


# ---------------------------------------------------------------------------
# Step 6: Structured analog database and matching types
# ---------------------------------------------------------------------------


class AnalogOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class DrugAnalog(BaseModel):
    """A historical drug program in the Step 6 analog database."""

    model_config = {"frozen": True}

    drug_name: str
    company: str
    mechanism: str
    indication: str
    phase_at_comparison: str
    outcome: AnalogOutcome
    key_finding: str
    approval_year: int | None = None
    peak_sales_millions: float | None = None
    endpoint_used: str | None = None


class AnalogMatchResult(BaseModel):
    """Result of find_analogs() — deterministic, no LLM."""

    model_config = {"frozen": True}

    query_mechanism: str
    query_indication: str
    matched_analogs: list[DrugAnalog]
    success_rate: float
    failure_rate: float
    analog_score: float
    median_peak_sales_millions: float | None
    summary: str


# ---------------------------------------------------------------------------
# Analog database — at least 20 well-known biotech drug classes
# ---------------------------------------------------------------------------

ANALOG_DATABASE: list[DrugAnalog] = [
    # GLP-1 agonists
    DrugAnalog(
        drug_name="Semaglutide (Ozempic/Wegovy)",
        company="Novo Nordisk",
        mechanism="GLP-1 agonist",
        indication="type 2 diabetes obesity",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Semaglutide achieved >15% weight loss in SURMOUNT-1 and dominant GLP-1 market share.",
        approval_year=2017,
        peak_sales_millions=21000.0,
        endpoint_used="HbA1c reduction, body weight",
    ),
    DrugAnalog(
        drug_name="Tirzepatide (Mounjaro/Zepbound)",
        company="Eli Lilly",
        mechanism="GLP-1 GIP dual agonist",
        indication="type 2 diabetes obesity",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Tirzepatide showed superior weight loss vs semaglutide, rapidly captured market share.",
        approval_year=2022,
        peak_sales_millions=18000.0,
        endpoint_used="HbA1c reduction, body weight",
    ),
    DrugAnalog(
        drug_name="Liraglutide (Victoza/Saxenda)",
        company="Novo Nordisk",
        mechanism="GLP-1 agonist",
        indication="type 2 diabetes obesity",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Liraglutide pioneered GLP-1 class and demonstrated cardiovascular benefit.",
        approval_year=2010,
        peak_sales_millions=3800.0,
        endpoint_used="HbA1c reduction",
    ),
    # PCSK9 inhibitors
    DrugAnalog(
        drug_name="Evolocumab (Repatha)",
        company="Amgen",
        mechanism="PCSK9 inhibitor",
        indication="hypercholesterolemia cardiovascular",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Evolocumab reduced LDL >60% but commercial uptake limited by payer access and cost.",
        approval_year=2015,
        peak_sales_millions=1200.0,
        endpoint_used="LDL-C reduction",
    ),
    DrugAnalog(
        drug_name="Alirocumab (Praluent)",
        company="Sanofi/Regeneron",
        mechanism="PCSK9 inhibitor",
        indication="hypercholesterolemia cardiovascular",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Alirocumab effective but commercial underperformance vs statin standard of care.",
        approval_year=2015,
        peak_sales_millions=600.0,
        endpoint_used="LDL-C reduction",
    ),
    # PD-1/PD-L1 inhibitors
    DrugAnalog(
        drug_name="Pembrolizumab (Keytruda)",
        company="Merck",
        mechanism="PD-1 inhibitor",
        indication="oncology solid tumor",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Pembrolizumab became backbone of oncology; >$25B revenue across 40+ indications.",
        approval_year=2014,
        peak_sales_millions=25000.0,
        endpoint_used="ORR, OS, PFS",
    ),
    DrugAnalog(
        drug_name="Nivolumab (Opdivo)",
        company="Bristol Myers Squibb",
        mechanism="PD-1 inhibitor",
        indication="oncology solid tumor hematology",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Nivolumab co-developed PD-1 class with strong survival data across multiple tumor types.",
        approval_year=2014,
        peak_sales_millions=8500.0,
        endpoint_used="OS, ORR, PFS",
    ),
    DrugAnalog(
        drug_name="Atezolizumab (Tecentriq)",
        company="Roche/Genentech",
        mechanism="PD-L1 inhibitor",
        indication="oncology solid tumor",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Atezolizumab validated PD-L1 inhibition; commercial performance below PD-1 agents.",
        approval_year=2016,
        peak_sales_millions=1800.0,
        endpoint_used="OS, PFS",
    ),
    # KRAS G12C inhibitors
    DrugAnalog(
        drug_name="Sotorasib (Lumakras)",
        company="Amgen",
        mechanism="KRAS G12C inhibitor",
        indication="NSCLC oncology",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.MIXED,
        key_finding="Sotorasib proved KRAS druggability but durability limited; resistance develops rapidly.",
        approval_year=2021,
        peak_sales_millions=400.0,
        endpoint_used="ORR, PFS",
    ),
    DrugAnalog(
        drug_name="Adagrasib (Krazati)",
        company="Mirati",
        mechanism="KRAS G12C inhibitor",
        indication="NSCLC oncology",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.MIXED,
        key_finding="Adagrasib showed similar efficacy to sotorasib; class durability remains an open question.",
        approval_year=2022,
        peak_sales_millions=250.0,
        endpoint_used="ORR, PFS",
    ),
    # CAR-T therapies
    DrugAnalog(
        drug_name="Axicabtagene Ciloleucel (Yescarta)",
        company="Kite/Gilead",
        mechanism="CAR-T cell therapy",
        indication="DLBCL hematology lymphoma",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Axicabtagene demonstrated 40% CR rate in refractory DLBCL; curative intent validated.",
        approval_year=2017,
        peak_sales_millions=870.0,
        endpoint_used="ORR, CR",
    ),
    DrugAnalog(
        drug_name="Tisagenlecleucel (Kymriah)",
        company="Novartis",
        mechanism="CAR-T cell therapy",
        indication="ALL hematology pediatric",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Tisagenlecleucel achieved 81% CR in pediatric ALL; first CAR-T approval.",
        approval_year=2017,
        peak_sales_millions=500.0,
        endpoint_used="CR, EFS",
    ),
    # Gene therapy
    DrugAnalog(
        drug_name="Onasemnogene Abeparvovec (Zolgensma)",
        company="AveXis/Novartis",
        mechanism="gene therapy AAV9",
        indication="spinal muscular atrophy SMA",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Single-dose gene therapy cured SMA Type 1; demonstrated transformative gene therapy utility.",
        approval_year=2019,
        peak_sales_millions=1500.0,
        endpoint_used="EFS, motor milestones",
    ),
    DrugAnalog(
        drug_name="Hemophilia Gene Therapy (fitusiran/marstacimab)",
        company="Multiple",
        mechanism="gene therapy hemophilia",
        indication="hemophilia",
        phase_at_comparison="phase3",
        outcome=AnalogOutcome.MIXED,
        key_finding="Hemophilia gene therapy showing efficacy but durability and immune responses remain concerns.",
        approval_year=None,
        peak_sales_millions=None,
        endpoint_used="ABR reduction",
    ),
    # BTK inhibitors
    DrugAnalog(
        drug_name="Ibrutinib (Imbruvica)",
        company="AbbVie/J&J",
        mechanism="BTK inhibitor",
        indication="CLL MCL hematology",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Ibrutinib transformed CLL treatment landscape; $9B peak sales.",
        approval_year=2013,
        peak_sales_millions=9000.0,
        endpoint_used="PFS, OS",
    ),
    DrugAnalog(
        drug_name="Acalabrutinib (Calquence)",
        company="AstraZeneca",
        mechanism="BTK inhibitor",
        indication="CLL hematology",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Acalabrutinib demonstrated superior tolerability vs ibrutinib in CLL.",
        approval_year=2019,
        peak_sales_millions=2000.0,
        endpoint_used="PFS",
    ),
    # CDK4/6 inhibitors
    DrugAnalog(
        drug_name="Palbociclib (Ibrance)",
        company="Pfizer",
        mechanism="CDK4/6 inhibitor",
        indication="HR+ HER2- breast cancer",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Palbociclib pioneered CDK4/6 class in breast cancer; $4.6B peak sales.",
        approval_year=2015,
        peak_sales_millions=4600.0,
        endpoint_used="PFS",
    ),
    DrugAnalog(
        drug_name="Ribociclib (Kisqali)",
        company="Novartis",
        mechanism="CDK4/6 inhibitor",
        indication="HR+ HER2- breast cancer",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Ribociclib demonstrated overall survival benefit — the first OS data in CDK4/6 class.",
        approval_year=2017,
        peak_sales_millions=2100.0,
        endpoint_used="PFS, OS",
    ),
    DrugAnalog(
        drug_name="Abemaciclib (Verzenio)",
        company="Eli Lilly",
        mechanism="CDK4/6 inhibitor",
        indication="HR+ HER2- breast cancer adjuvant",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Abemaciclib first CDK4/6 approved in adjuvant setting with IDFS benefit.",
        approval_year=2017,
        peak_sales_millions=3200.0,
        endpoint_used="IDFS, PFS",
    ),
    # PARP inhibitors
    DrugAnalog(
        drug_name="Olaparib (Lynparza)",
        company="AstraZeneca/MSD",
        mechanism="PARP inhibitor",
        indication="BRCA ovarian breast cancer",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Olaparib pioneered synthetic lethality in BRCA-mutated cancers.",
        approval_year=2014,
        peak_sales_millions=2700.0,
        endpoint_used="PFS, OS",
    ),
    DrugAnalog(
        drug_name="Niraparib (Zejula)",
        company="GSK",
        mechanism="PARP inhibitor",
        indication="ovarian cancer",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Niraparib extends PARP utility beyond BRCA mutation — broader biomarker strategy.",
        approval_year=2017,
        peak_sales_millions=600.0,
        endpoint_used="PFS",
    ),
    # EGFR inhibitors
    DrugAnalog(
        drug_name="Osimertinib (Tagrisso)",
        company="AstraZeneca",
        mechanism="EGFR inhibitor 3rd generation",
        indication="NSCLC EGFR-mutated",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Osimertinib overcame T790M resistance; adjuvant survival benefit established.",
        approval_year=2017,
        peak_sales_millions=5900.0,
        endpoint_used="PFS, OS, DFS",
    ),
    DrugAnalog(
        drug_name="Erlotinib (Tarceva)",
        company="Roche/OSI",
        mechanism="EGFR inhibitor 1st generation",
        indication="NSCLC",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.MIXED,
        key_finding="Erlotinib approved but limited by acquired resistance; superseded by 3rd-gen agents.",
        approval_year=2004,
        peak_sales_millions=1600.0,
        endpoint_used="OS, PFS",
    ),
    # Anti-IL-17/23
    DrugAnalog(
        drug_name="Secukinumab (Cosentyx)",
        company="Novartis",
        mechanism="IL-17A inhibitor",
        indication="psoriasis ankylosing spondylitis",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Secukinumab demonstrated superior PASI 90 vs ustekinumab in psoriasis.",
        approval_year=2015,
        peak_sales_millions=4700.0,
        endpoint_used="PASI 90, IGA",
    ),
    DrugAnalog(
        drug_name="Guselkumab (Tremfya)",
        company="J&J",
        mechanism="IL-23 inhibitor",
        indication="psoriasis dermatology",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Guselkumab showed durable PASI 90 with IL-23 selective inhibition.",
        approval_year=2017,
        peak_sales_millions=2300.0,
        endpoint_used="IGA, PASI 90",
    ),
    # SGLT2 inhibitors
    DrugAnalog(
        drug_name="Empagliflozin (Jardiance)",
        company="Boehringer Ingelheim/Lilly",
        mechanism="SGLT2 inhibitor",
        indication="type 2 diabetes heart failure",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Empagliflozin demonstrated 38% CV death reduction in EMPA-REG OUTCOME.",
        approval_year=2014,
        peak_sales_millions=5900.0,
        endpoint_used="MACE, HF hospitalization",
    ),
    DrugAnalog(
        drug_name="Dapagliflozin (Farxiga)",
        company="AstraZeneca",
        mechanism="SGLT2 inhibitor",
        indication="type 2 diabetes heart failure CKD",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Dapagliflozin expanded SGLT2 utility to HFrEF and CKD, broadening class impact.",
        approval_year=2014,
        peak_sales_millions=4100.0,
        endpoint_used="CV death, worsening HF",
    ),
    # Factor XI inhibitor failure
    DrugAnalog(
        drug_name="Asundexian",
        company="Bayer",
        mechanism="factor XI inhibitor",
        indication="stroke prevention atrial fibrillation",
        phase_at_comparison="phase3",
        outcome=AnalogOutcome.FAILURE,
        key_finding="Asundexian failed Phase 3 (OCEANIC-AF) — inferior to apixaban on stroke/embolism.",
        approval_year=None,
        peak_sales_millions=None,
        endpoint_used="Stroke/systemic embolism",
    ),
    # RNAi therapeutics
    DrugAnalog(
        drug_name="Inclisiran (Leqvio)",
        company="Novartis",
        mechanism="RNAi PCSK9",
        indication="hypercholesterolemia cardiovascular",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Inclisiran validated twice-yearly RNAi dosing for LDL lowering.",
        approval_year=2021,
        peak_sales_millions=600.0,
        endpoint_used="LDL-C reduction",
    ),
    DrugAnalog(
        drug_name="Givosiran (Givlaari)",
        company="Alnylam",
        mechanism="RNAi ALAS1",
        indication="acute hepatic porphyria",
        phase_at_comparison="approved",
        outcome=AnalogOutcome.SUCCESS,
        key_finding="Givosiran demonstrated 74% reduction in porphyria attacks — rare disease RNAi success.",
        approval_year=2019,
        peak_sales_millions=250.0,
        endpoint_used="Annualized attack rate",
    ),
]


def find_analogs(
    mechanism: str,
    indication: str,
    max_results: int = 5,
) -> AnalogMatchResult:
    """Find historical analogs matching mechanism and indication via deterministic scoring."""
    mech_norm = mechanism.lower().strip()
    ind_norm = indication.lower().strip()

    # Tokenise query — words longer than 3 chars
    mech_words = [w for w in mech_norm.split() if len(w) > 3]
    ind_words = [w for w in ind_norm.split() if len(w) > 3]

    scored: list[tuple[float, DrugAnalog]] = []
    for analog in ANALOG_DATABASE:
        a_mech = analog.mechanism.lower()
        a_ind = analog.indication.lower()

        mech_match = 1.0 if any(w in a_mech for w in mech_words) else 0.0
        ind_match = 1.0 if any(w in a_ind for w in ind_words) else 0.0
        combined = mech_match * 0.70 + ind_match * 0.30

        if combined >= 0.1:
            scored.append((combined, analog))

    # Sort by score descending, take top max_results
    scored.sort(key=lambda x: x[0], reverse=True)
    matched = [analog for _, analog in scored[:max_results]]

    if not matched:
        return AnalogMatchResult(
            query_mechanism=mechanism,
            query_indication=indication,
            matched_analogs=[],
            success_rate=0.0,
            failure_rate=0.0,
            analog_score=0.5,
            median_peak_sales_millions=None,
            summary="No matching analogs found; neutral score assigned.",
        )

    success_count = sum(1 for a in matched if a.outcome == AnalogOutcome.SUCCESS)
    failure_count = sum(1 for a in matched if a.outcome == AnalogOutcome.FAILURE)
    total = len(matched)

    success_rate = success_count / total
    failure_rate = failure_count / total

    if success_rate >= 0.6:
        analog_score = success_rate
    elif failure_rate >= 0.6:
        analog_score = 1.0 - failure_rate
    else:
        analog_score = 0.5

    sales_values = [a.peak_sales_millions for a in matched if a.peak_sales_millions is not None]
    median_peak = statistics.median(sales_values) if sales_values else None

    summary = (
        f"Found {total} analog(s) for mechanism='{mechanism}', indication='{indication}'. "
        f"Success rate: {success_rate:.0%}, Failure rate: {failure_rate:.0%}. "
        f"Analog score: {analog_score:.2f}."
    )

    return AnalogMatchResult(
        query_mechanism=mechanism,
        query_indication=indication,
        matched_analogs=matched,
        success_rate=round(success_rate, 4),
        failure_rate=round(failure_rate, 4),
        analog_score=round(analog_score, 4),
        median_peak_sales_millions=median_peak,
        summary=summary,
    )
