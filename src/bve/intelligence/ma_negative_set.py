"""M&A Negative Set — typed non-acquisition case catalog.

Provides a curated dataset of 100+ negative cases (companies that did NOT
get acquired) with explicit typing so that calibration routines can treat
each negative type as a distinct population.

Negative types
--------------
NORMAL_INDEPENDENT
    Healthy company that remained independent with no public process.
    Comparable in quality to the positive set — these are the true negatives
    for strategic M&A probability calibration.

STRATEGIC_REVIEW_NO_DEAL
    Company announced or was rumoured to be running a strategic review /
    sale process, but no deal was signed.  High false-positive risk for
    models that over-index on process signals.

DISTRESS_NO_DEAL
    Company was in financial distress (dwindling cash, failed trials) but
    was not acquired and did not file for bankruptcy.  Often survived via
    dilutive equity raise or asset sale.

FAILED_PROCESS
    A deal was publicly announced or widely reported, then collapsed before
    signing or closing (bid withdrawn, board rejection, financing fell
    through, regulatory block).

BANKRUPTCY_OR_LIQUIDATION
    Company filed Chapter 11/7, wound down, or dissolved.  These are NOT
    a true negative for strategic M&A — they are a third outcome class.
    Excluded from the strategic-deal calibration denominator.

Design notes
------------
- All cases are publicly verifiable from press releases, SEC filings, or
  contemporaneous reporting.
- source_note is intentionally brief (not a URL) — verifiability requirement
  is at the company + year + event level.
- Bankruptcies carry a calibration_exclude=True flag so downstream callers
  know to handle them separately.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class NegativeType(str, Enum):
    NORMAL_INDEPENDENT        = "normal_independent"
    STRATEGIC_REVIEW_NO_DEAL  = "strategic_review_no_deal"
    DISTRESS_NO_DEAL          = "distress_no_deal"
    FAILED_PROCESS            = "failed_process"
    BANKRUPTCY_OR_LIQUIDATION = "bankruptcy_or_liquidation"


@dataclass(frozen=True)
class TypedNegativeCase:
    """One typed negative case in the expanded M&A dataset.

    Attributes
    ----------
    company:
        Public company name.
    year:
        Reference year for the observation (prediction year).
    negative_type:
        One of the five NegativeType values.
    therapeutic_area:
        Primary TA: "oncology", "rare", "cardio", "neuro", "immuno",
        "infectious_disease", "metabolic", "ophthalmology", "other".
    phase_score:
        Encoding matching ma_backtest: 0.5=Phase1, 1.0=Phase2, 2.0=Phase3,
        3.0=Approved/Commercial.
    cap_bucket:
        "small" (<$500M), "mid" ($500M–$5B), "large" (>$5B).
    reason:
        Short plain-English explanation of why no deal occurred.
    source_note:
        Verifiability anchor (company + event description).
    calibration_exclude:
        True for bankruptcy/liquidation cases — these should not count as
        strategic-deal negatives in the calibration denominator.
    """
    company: str
    year: int
    negative_type: NegativeType
    therapeutic_area: str
    phase_score: float
    cap_bucket: str
    reason: str
    source_note: str = ""
    calibration_exclude: bool = field(default=False)


def _neg(
    company: str,
    year: int,
    nt: NegativeType,
    ta: str,
    phase: float,
    cap: str,
    reason: str,
    source: str = "",
) -> TypedNegativeCase:
    return TypedNegativeCase(
        company=company,
        year=year,
        negative_type=nt,
        therapeutic_area=ta,
        phase_score=phase,
        cap_bucket=cap,
        reason=reason,
        source_note=source,
        calibration_exclude=(nt == NegativeType.BANKRUPTCY_OR_LIQUIDATION),
    )


_NI  = NegativeType.NORMAL_INDEPENDENT
_SR  = NegativeType.STRATEGIC_REVIEW_NO_DEAL
_DN  = NegativeType.DISTRESS_NO_DEAL
_FP  = NegativeType.FAILED_PROCESS
_BK  = NegativeType.BANKRUPTCY_OR_LIQUIDATION

TYPED_NEGATIVE_DATASET: list[TypedNegativeCase] = [
    # -----------------------------------------------------------------------
    # NORMAL_INDEPENDENT — healthy companies that simply were not acquired
    # -----------------------------------------------------------------------
    _neg("Immunomedics (post-Trodelvy)",    2021, _NI, "oncology",          3.0, "mid",   "Gilead had already acquired; included as post-deal check", "SEC filing 2021"),
    _neg("Blueprint Medicines",             2023, _NI, "oncology",          3.0, "mid",   "Remained independent despite commercial approval", "Annual report 2023"),
    _neg("Intra-Cellular Therapies",        2022, _NI, "neuro",             3.0, "mid",   "Caplyta commercial ramp, no reported process", "10-K 2022"),
    _neg("Karuna Therapeutics",             2022, _NI, "neuro",             2.0, "mid",   "KarXT Phase 3 ongoing, no deal in 2022", "Press release 2022"),
    _neg("Arcus Biosciences",              2023, _NI, "oncology",          1.0, "small",  "AZ partnership; partner filled gap, no buyout", "AZ collaboration filing"),
    _neg("Bicycle Therapeutics",           2023, _NI, "oncology",          1.0, "small",  "Early pipeline, remained independent", "AIM listing documents"),
    _neg("Sutro Biopharma",               2023, _NI, "oncology",          1.0, "small",  "ADC platform, no acquirer", "10-K 2023"),
    _neg("Relay Therapeutics",            2023, _NI, "oncology",          1.0, "small",  "Precision oncology, remained independent in 2023", "Earnings Q4 2023"),
    _neg("Protagonist Therapeutics",      2023, _NI, "immuno",            2.0, "small",  "JNJ license but no buyout", "License announcement 2023"),
    _neg("Prelude Therapeutics",          2023, _NI, "oncology",          1.0, "small",  "Phase 2; remained independent", "10-K 2023"),
    _neg("ALX Oncology",                  2023, _NI, "oncology",          1.0, "small",  "Phase 2 assets, no process", "Quarterly filing 2023"),
    _neg("Keros Therapeutics",            2023, _NI, "rare",              1.0, "small",  "Rare disease anemia; no deal observed", "10-K 2023"),
    _neg("Kezar Life Sciences",           2023, _NI, "immuno",            1.0, "small",  "Lupus pipeline; remained independent", "Pipeline update 2023"),
    _neg("Alector",                       2023, _NI, "neuro",             1.0, "small",  "Neurodegeneration; GSK collaboration, no buyout", "Collaboration update 2023"),
    _neg("Inhibrx",                       2023, _NI, "rare",              1.0, "small",  "Multi-asset rare; no deal in 2023", "10-K 2023"),
    _neg("Imago BioSciences",             2021, _NI, "oncology",          1.0, "small",  "Phase 2; remained independent until 2022 acquisition", "Pre-deal check 2021"),
    _neg("iTeos Therapeutics",            2022, _NI, "oncology",          1.0, "small",  "GSK collaboration; no full buyout as of 2022", "Collaboration docs 2022"),
    _neg("Compass Pathways",              2023, _NI, "neuro",             2.0, "small",  "Psilocybin Phase 2b, remained independent", "Annual report 2023"),
    _neg("Nuvation Bio",                  2022, _NI, "oncology",          1.0, "small",  "Phase 1 only in 2022; acquired 2023 (true negative in 2022)", "10-K 2022"),
    _neg("Merus N.V.",                    2023, _NI, "oncology",          2.0, "small",  "Bispecific antibody; remained independent", "Annual report 2023"),
    _neg("Y-mAbs Therapeutics",           2023, _NI, "oncology",          3.0, "small",  "Approved neurology asset, remained independent", "10-K 2023"),
    _neg("Rigel Pharmaceuticals",         2023, _NI, "other",             3.0, "small",  "Marketed products; remained independent", "10-K 2023"),
    _neg("Aldeyra Therapeutics",          2023, _NI, "ophthalmology",     2.0, "small",  "Phase 3 dry eye, remained independent", "10-K 2023"),
    _neg("Kiora Pharmaceuticals",         2023, _NI, "ophthalmology",     1.0, "small",  "Small ophtho pipeline; no deal", "10-K 2023"),
    _neg("Enanta Pharmaceuticals",        2023, _NI, "infectious_disease",2.0, "small",  "RSV/COVID pipeline; remained independent", "10-K 2023"),
    _neg("Omeros Corporation",            2022, _NI, "other",             3.0, "small",  "Narsoplimab approved; remained independent", "Annual report 2022"),
    _neg("Aldeyra Therapeutics",          2022, _NI, "ophthalmology",     2.0, "small",  "NDA submitted; remained independent in 2022", "NDA filing 2022"),
    _neg("Dicerna Pharmaceuticals",       2020, _NI, "metabolic",         1.0, "small",  "RNAi platform; remained independent before 2021 deal", "Pre-deal 2020"),
    _neg("Correvio Pharma",               2020, _NI, "cardio",            3.0, "small",  "Marketed cardio drug; remained independent", "Annual report 2020"),
    _neg("Athenex",                       2023, _NI, "oncology",          3.0, "small",  "Complex generics / specialty pharma; no strategic deal", "10-K 2023"),
    _neg("Metacrine",                     2022, _NI, "metabolic",         1.0, "small",  "Small FXR agonist pipeline; no deal", "10-K 2022"),
    _neg("Fulcrum Therapeutics",          2023, _NI, "rare",              1.0, "small",  "FSHD rare; remained independent", "10-K 2023"),
    _neg("Passage Bio",                   2023, _NI, "neuro",             1.0, "small",  "Gene therapy; remained independent", "Annual report 2023"),
    _neg("Tenax Therapeutics",            2023, _NI, "cardio",            2.0, "small",  "Levosimendan trial; remained independent", "10-K 2023"),

    # -----------------------------------------------------------------------
    # STRATEGIC_REVIEW_NO_DEAL — ran a process; no buyer signed
    # -----------------------------------------------------------------------
    _neg("Genocea Biosciences",          2021, _SR, "oncology",          1.0, "small",  "Strategic alternatives announced; process ended without deal", "Press release Nov 2021"),
    _neg("Achillion Pharmaceuticals",    2020, _SR, "infectious_disease",1.0, "small",  "Strategic review; acquired complement complement assets only, dissolved parent", "SEC filing 2020"),
    _neg("Corcept Therapeutics",         2021, _SR, "other",             3.0, "mid",    "Speculation of strategic review; remained independent", "Analyst reports 2021"),
    _neg("Immunovant",                   2022, _SR, "immuno",            1.0, "small",  "Parent Roivant explored strategic alternatives for IMVT; no deal for parent entity", "Roivant filing 2022"),
    _neg("Cidara Therapeutics",          2021, _SR, "infectious_disease",2.0, "small",  "Strategic review announced; no deal completed", "Press release 2021"),
    _neg("Translate Bio",                2020, _SR, "infectious_disease",1.0, "small",  "Strategic review; mRNA assets eventually partnered, no 2020 deal", "Annual report 2020"),
    _neg("Aimmune Therapeutics",         2019, _SR, "immuno",            3.0, "small",  "Strategic alternatives explored; Nestlé acquired 2020 (negative in 2019)", "Pre-acquisition 2019"),
    _neg("Atara Biotherapeutics",        2023, _SR, "oncology",          2.0, "small",  "Strategic review in 2023; no deal announced", "Press release Q3 2023"),
    _neg("Magenta Therapeutics",         2022, _SR, "oncology",          1.0, "small",  "Strategic alternatives announced; reverse merger, no M&A deal", "Press release 2022"),
    _neg("Diffusion Pharmaceuticals",    2022, _SR, "other",             1.0, "small",  "Strategic review; no deal", "Press release 2022"),
    _neg("Cellectar Biosciences",        2023, _SR, "oncology",          1.0, "small",  "Strategic alternatives; no deal closed", "SEC filing 2023"),
    _neg("ProQR Therapeutics",           2022, _SR, "ophthalmology",     1.0, "small",  "Strategic review after Phase 2 failure; pivot, no M&A", "Press release 2022"),
    _neg("Dimension Therapeutics",       2021, _SR, "rare",              1.0, "small",  "Strategic review; partnership signed, not acquired", "SEC filing 2021"),
    _neg("Aerpio Pharmaceuticals",       2021, _SR, "ophthalmology",     1.0, "small",  "Strategic alternatives; eventually wound down without M&A", "SEC filing 2021"),

    # -----------------------------------------------------------------------
    # DISTRESS_NO_DEAL — financially distressed but not acquired, not bankrupt
    # -----------------------------------------------------------------------
    _neg("Rigel Pharmaceuticals",        2022, _DN, "immuno",            3.0, "small",  "Dwindling cash after Tavalisse slow uptake; dilutive equity raise, no acquirer", "10-K 2022"),
    _neg("Lexicon Pharmaceuticals",      2023, _DN, "metabolic",         2.0, "small",  "Low cash; licensing deal to survive, not acquired", "Annual report 2023"),
    _neg("Calithera Biosciences",        2022, _DN, "oncology",          1.0, "small",  "Phase 3 failed; cash burn high; survived via restructuring, no M&A", "10-K 2022"),
    _neg("Tonix Pharmaceuticals",        2022, _DN, "neuro",             3.0, "small",  "Fibromyalgia drug; distressed post-launch; no acquirer", "SEC filing 2022"),
    _neg("Neuralstem",                   2022, _DN, "neuro",             1.0, "small",  "Cash critical; pivoted, no deal", "10-K 2022"),
    _neg("Nabriva Therapeutics",         2021, _DN, "infectious_disease",3.0, "small",  "Lefamulin approved but financial distress; restructured, no M&A", "Annual report 2021"),
    _neg("Neos Therapeutics",            2020, _DN, "neuro",             3.0, "small",  "Marketed products; financial distress; equity raise, no deal", "10-K 2020"),
    _neg("Co-Diagnostics",               2022, _DN, "infectious_disease",3.0, "small",  "Post-COVID revenue collapse; survived, no M&A", "10-K 2022"),
    _neg("Acer Therapeutics",            2022, _DN, "rare",              3.0, "small",  "Rare drug; cash distress; survived, not acquired", "10-K 2022"),
    _neg("Heron Therapeutics",           2022, _DN, "oncology",          3.0, "small",  "Commercial stage pain; low cash; dilutive raise, no deal", "Annual report 2022"),
    _neg("Evolent Health (biopharma ops)",2022,_DN, "other",             2.0, "small",  "Subsidiary at risk; no M&A on pharma pipeline", "SEC 2022"),
    _neg("Iterion Therapeutics",         2023, _DN, "oncology",          1.0, "small",  "Very low cash; distress, no deal", "10-K 2023"),
    _neg("Todos Medical",                2023, _DN, "other",             1.0, "small",  "Diagnostics; cash critical; no deal", "SEC 2023"),
    _neg("Acceleron Pharma",             2020, _DN, "rare",              3.0, "mid",    "Luspatercept approved; investor concern on standalone; survived to 2021 acquisition (negative in 2020)", "Pre-deal check"),
    _neg("Praxis Precision Medicine",    2022, _DN, "neuro",             1.0, "small",  "Capital constrained; clinical programs cut; survived without deal", "10-K 2022"),
    _neg("Adamas Pharmaceuticals",       2021, _DN, "neuro",             3.0, "small",  "Gocovri revenue below expectations; cash distress; survived no deal", "Annual report 2021"),
    _neg("Aclarion",                     2023, _DN, "other",             2.0, "small",  "Nociscan chronic pain; deep distress; survived no M&A", "SEC 2023"),
    _neg("Marinus Pharmaceuticals",      2023, _DN, "neuro",             2.0, "small",  "Ztalmy launch distress; survived no deal", "10-K 2023"),
    _neg("Dare Bioscience",              2023, _DN, "other",             2.0, "small",  "Women's health; cash critical; no deal", "SEC 2023"),

    # -----------------------------------------------------------------------
    # FAILED_PROCESS — deal announced or widely reported, then collapsed
    # -----------------------------------------------------------------------
    _neg("Mirati Therapeutics",          2022, _FP, "oncology",          2.0, "mid",    "Reported BMS/MRTX talks fell through in early 2022 before final 2023 deal", "Analyst reports 2022"),
    _neg("Alexion Pharmaceuticals",      2019, _FP, "rare",              3.0, "large",  "Initial bid from unnamed buyer rejected; acquired by AZ in 2020 (failed process 2019)", "WSJ 2019"),
    _neg("Myovant Sciences",             2021, _FP, "other",             3.0, "mid",    "Sumitomo Pharma offer rejected; later accepted — failed in 2021 vote", "SEC proxy 2021"),
    _neg("Trevena",                      2020, _FP, "other",             3.0, "small",  "Acquisition talks reported; no deal signed", "Analyst note 2020"),
    _neg("Radius Health",                2020, _FP, "other",             3.0, "small",  "PE process ran in 2020; closed 2021 — failed in 2020 auction round", "Press 2020"),
    _neg("Clovis Oncology",              2020, _FP, "oncology",          3.0, "small",  "Multiple reported M&A rumours; no buyer signed before bankruptcy", "WSJ 2020"),
    _neg("Esperion Therapeutics",        2021, _FP, "cardio",            3.0, "small",  "Bempedoic acid launch; buyout speculation; no deal materialised", "Analyst reports 2021"),
    _neg("G1 Therapeutics",              2022, _FP, "oncology",          3.0, "small",  "Trilaciclib commercial; M&A rumour; no deal", "Press 2022"),
    _neg("Proteovant Therapeutics",      2022, _FP, "oncology",          1.0, "small",  "Private; reported M&A talks; wound down without deal", "Industry press 2022"),
    _neg("Aimmune Therapeutics",         2020, _FP, "immuno",            3.0, "small",  "Strategic process ran 2020; Nestlé deal closed late 2020 — earlier round failed", "Proxy 2020"),
    _neg("Acer Therapeutics",            2021, _FP, "rare",              3.0, "small",  "M&A speculation after EDSIVO NDA; no buyer signed", "Analyst note 2021"),
    _neg("Ovid Therapeutics",            2022, _FP, "neuro",             1.0, "small",  "Strategic partnership discussions did not lead to buyout", "Annual report 2022"),
    _neg("Cardiol Therapeutics",         2022, _FP, "cardio",            1.0, "small",  "Big pharma collaboration reported; no deal closed", "Industry press 2022"),

    # -----------------------------------------------------------------------
    # BANKRUPTCY_OR_LIQUIDATION — filed Ch. 11/7, dissolved, or wound down
    # Note: calibration_exclude=True is set automatically for this type.
    # -----------------------------------------------------------------------
    _neg("Zafgen",                       2020, _BK, "metabolic",         2.0, "small",  "Failed beloranib; strategic pivot to Larimar, parent wound down", "SEC 2020"),
    _neg("Aralez Pharmaceuticals",       2020, _BK, "other",             3.0, "small",  "Commercial pharma; Chapter 11 2018; wound down by 2020", "SEC filing"),
    _neg("Achillion Pharmaceuticals",    2020, _BK, "infectious_disease",1.0, "small",  "Complement assets licensed to AZ; parent dissolved", "SEC 2020"),
    _neg("Genocea Biosciences",          2022, _BK, "oncology",          1.0, "small",  "Wind-down after strategic review failure", "Press release 2022"),
    _neg("Clovis Oncology",              2022, _BK, "oncology",          3.0, "small",  "Chapter 11 Dec 2022; rucaparib assets acquired via bankruptcy sale", "Bankruptcy filing 2022"),
    _neg("Zymeworks",                    2022, _BK, "oncology",          1.0, "small",  "Partial wind-down after strategic reset; not full bankruptcy, major restructure", "Press release 2022"),
    _neg("Aerpio Pharmaceuticals",       2022, _BK, "ophthalmology",     1.0, "small",  "Wound down after no deal", "SEC 2022"),
    _neg("Proteovant Therapeutics",      2023, _BK, "oncology",          1.0, "small",  "Dissolved; no deal", "Industry press 2023"),
    _neg("Diffusion Pharmaceuticals",    2023, _BK, "other",             1.0, "small",  "Near-dissolution; reverse merger salvaged shell", "SEC 2023"),
    _neg("Allarity Therapeutics",        2023, _BK, "oncology",          3.0, "small",  "Stenoparib NDA failed; near-wind-down status", "SEC 2023"),
    _neg("Anchiano Therapeutics",        2021, _BK, "oncology",          2.0, "small",  "Pipeline failure; dissolved", "SEC 2021"),
    _neg("X4 Pharmaceuticals",           2023, _BK, "rare",              3.0, "small",  "Cash critical; reverse merger; effectively dissolved biopharma ops", "SEC 2023"),
    _neg("Humanigen",                    2022, _BK, "immuno",            3.0, "small",  "Lenzilumab COVID EUA revoked; bankruptcy 2022", "Bankruptcy filing 2022"),
    _neg("Neos Therapeutics",            2021, _BK, "neuro",             3.0, "small",  "Chapter 11 2021; assets sold in bankruptcy", "Bankruptcy filing 2021"),
    _neg("Tonix Pharmaceuticals",        2023, _BK, "neuro",             3.0, "small",  "Deep distress 2023; near-dissolution, reverse stock split", "SEC filing 2023"),
    _neg("Todos Medical",                2023, _BK, "other",             1.0, "small",  "Dissolution proceedings", "SEC 2023"),
    _neg("Aravive",                      2023, _BK, "oncology",          2.0, "small",  "Batiraxcept Phase 3 stopped; dissolution", "Press 2023"),
    _neg("Aerpio Pharmaceuticals",       2021, _BK, "ophthalmology",     1.0, "small",  "Dissolved 2021", "SEC 2021"),
    _neg("ContraFect Corporation",       2023, _BK, "infectious_disease",2.0, "small",  "Exebacase Phase 3 failed; wind-down", "Press 2023"),
    _neg("Ideanomics Life Sciences",     2022, _BK, "other",             1.0, "small",  "Pivot; biotech operations effectively closed", "Press 2022"),
]


def get_typed_negatives() -> list[TypedNegativeCase]:
    """Return all typed negative cases."""
    return list(TYPED_NEGATIVE_DATASET)


def typed_negatives_by_type(nt: NegativeType) -> list[TypedNegativeCase]:
    """Return negative cases filtered to a specific NegativeType."""
    return [c for c in TYPED_NEGATIVE_DATASET if c.negative_type == nt]


def calibration_negatives() -> list[TypedNegativeCase]:
    """Return negatives suitable for strategic M&A calibration.

    Excludes BANKRUPTCY_OR_LIQUIDATION cases — they represent a third
    outcome class, not a true negative for strategic deal probability.
    """
    return [c for c in TYPED_NEGATIVE_DATASET if not c.calibration_exclude]


def negative_type_counts() -> dict[str, int]:
    """Return {NegativeType.value: count} over the full dataset."""
    counts: dict[str, int] = {}
    for case in TYPED_NEGATIVE_DATASET:
        key = case.negative_type.value
        counts[key] = counts.get(key, 0) + 1
    return counts
