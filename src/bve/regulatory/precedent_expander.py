"""Expanded FDA precedent corpus with richer querying over 15+ drug approval/CRL records."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ApprovalPathway(str, Enum):
    STANDARD = "standard"
    ACCELERATED = "accelerated_approval"
    BREAKTHROUGH = "breakthrough_therapy"
    FAST_TRACK = "fast_track"
    PRIORITY_REVIEW = "priority_review"
    ORPHAN = "orphan_drug"


class ExpandedPrecedentRecord(BaseModel):
    drug_name: str
    brand_name: Optional[str] = None
    company: str
    approval_year: Optional[int] = None
    therapeutic_area: str
    indication: str
    modality: str  # "small_molecule" | "biologic" | "cell_therapy" | "gene_therapy" | "rna"
    primary_endpoint: str
    approval_pathway: list[ApprovalPathway]
    approved: bool
    crl_issued: bool = False
    adcom_vote: Optional[str] = None  # e.g. "12-1 favorable"
    key_lesson: str = ""


EXPANDED_PRECEDENTS: list[ExpandedPrecedentRecord] = [
    # --- Oncology: small molecules ---
    ExpandedPrecedentRecord(
        drug_name="venetoclax",
        brand_name="Venclexta",
        company="AbbVie/Roche",
        approval_year=2016,
        therapeutic_area="oncology",
        indication="CLL with 17p deletion, relapsed/refractory",
        modality="small_molecule",
        primary_endpoint="ORR",
        approval_pathway=[ApprovalPathway.ACCELERATED, ApprovalPathway.BREAKTHROUGH, ApprovalPathway.PRIORITY_REVIEW, ApprovalPathway.ORPHAN],
        approved=True,
        adcom_vote=None,
        key_lesson=(
            "BCL-2 inhibitor with tumor lysis syndrome risk required REMS; "
            "accelerated approval on ORR in heavily biomarker-selected (17p del) population is viable path."
        ),
    ),
    ExpandedPrecedentRecord(
        drug_name="sotorasib",
        brand_name="Lumakras",
        company="Amgen",
        approval_year=2021,
        therapeutic_area="oncology",
        indication="NSCLC KRAS G12C mutation, second-line",
        modality="small_molecule",
        primary_endpoint="ORR",
        approval_pathway=[ApprovalPathway.ACCELERATED, ApprovalPathway.BREAKTHROUGH, ApprovalPathway.PRIORITY_REVIEW],
        approved=True,
        adcom_vote=None,
        key_lesson=(
            "First approved KRAS inhibitor; ORR 36% in CodeBreaK 100 single-arm; "
            "confirms oncogene-specific biomarker selection supports accelerated approval. "
            "Confirmatory CodeBreaK 200 RCT required."
        ),
    ),
    ExpandedPrecedentRecord(
        drug_name="enasidenib",
        brand_name="Idhifa",
        company="Celgene/BMS",
        approval_year=2017,
        therapeutic_area="oncology",
        indication="R/R AML with IDH2 mutation",
        modality="small_molecule",
        primary_endpoint="CR+CRh rate",
        approval_pathway=[ApprovalPathway.ACCELERATED, ApprovalPathway.BREAKTHROUGH, ApprovalPathway.PRIORITY_REVIEW, ApprovalPathway.ORPHAN],
        approved=True,
        adcom_vote=None,
        key_lesson=(
            "IDH2-mutant AML approval on composite CR endpoint in single-arm study; "
            "companion diagnostic (Abbott RealTime IDH2) co-developed. Differentiation syndrome warning required."
        ),
    ),
    ExpandedPrecedentRecord(
        drug_name="ivosidenib",
        brand_name="Tibsovo",
        company="Servier/Agios",
        approval_year=2018,
        therapeutic_area="oncology",
        indication="R/R AML with IDH1 mutation",
        modality="small_molecule",
        primary_endpoint="CR+CRh rate",
        approval_pathway=[ApprovalPathway.ACCELERATED, ApprovalPathway.BREAKTHROUGH, ApprovalPathway.PRIORITY_REVIEW, ApprovalPathway.ORPHAN],
        approved=True,
        adcom_vote=None,
        key_lesson=(
            "IDH1-mutant AML precedent mirrors enasidenib path; "
            "QT prolongation signal managed via labeling. "
            "Later expanded to cholangiocarcinoma based on OS in CLARION trial."
        ),
    ),
    # --- Oncology: biologic ---
    ExpandedPrecedentRecord(
        drug_name="pembrolizumab",
        brand_name="Keytruda",
        company="Merck",
        approval_year=2014,
        therapeutic_area="oncology",
        indication="Advanced melanoma, second-line",
        modality="biologic",
        primary_endpoint="ORR",
        approval_pathway=[ApprovalPathway.ACCELERATED, ApprovalPathway.BREAKTHROUGH, ApprovalPathway.PRIORITY_REVIEW],
        approved=True,
        adcom_vote=None,
        key_lesson=(
            "First PD-1 checkpoint inhibitor approval via accelerated approval on ORR; "
            "established biomarker-unselected IO precedent. "
            "Subsequent PD-L1 stratified approvals in NSCLC refined biomarker use."
        ),
    ),
    # --- Oncology: CRL example ---
    ExpandedPrecedentRecord(
        drug_name="aducanumab",
        brand_name="Aduhelm",
        company="Biogen",
        approval_year=2021,
        therapeutic_area="neurology",
        indication="Alzheimer's disease, early symptomatic",
        modality="biologic",
        primary_endpoint="Amyloid PET reduction (surrogate)",
        approval_pathway=[ApprovalPathway.ACCELERATED],
        approved=True,
        crl_issued=True,
        adcom_vote="10-0-1 against (advisory committee rejected; FDA overrode)",
        key_lesson=(
            "Controversial accelerated approval on amyloid surrogate despite failed Phase 3 trials; "
            "FDA overrode adcom 10-0 rejection. "
            "CMS refused reimbursement; withdrawn from market 2024. "
            "Illustrates regulatory risk when clinical benefit is unproven and adcom is opposed."
        ),
    ),
    # --- Oncology: cell therapy ---
    ExpandedPrecedentRecord(
        drug_name="tisagenlecleucel",
        brand_name="Kymriah",
        company="Novartis",
        approval_year=2017,
        therapeutic_area="oncology",
        indication="R/R B-cell ALL, pediatric and young adult",
        modality="cell_therapy",
        primary_endpoint="Overall remission rate",
        approval_pathway=[ApprovalPathway.ACCELERATED, ApprovalPathway.BREAKTHROUGH, ApprovalPathway.PRIORITY_REVIEW, ApprovalPathway.ORPHAN],
        approved=True,
        adcom_vote="10-0 favorable",
        key_lesson=(
            "First CAR-T approval; 81% overall remission rate in single-arm ELIANA trial. "
            "CRS and neurotoxicity required REMS. Manufacturing vein-to-vein time was a key regulatory discussion point."
        ),
    ),
    # --- Rare disease: small molecules ---
    ExpandedPrecedentRecord(
        drug_name="ivacaftor",
        brand_name="Kalydeco",
        company="Vertex Pharmaceuticals",
        approval_year=2012,
        therapeutic_area="rare_disease",
        indication="CF with G551D-CFTR mutation (gating mutation)",
        modality="small_molecule",
        primary_endpoint="ppFEV1 change",
        approval_pathway=[ApprovalPathway.BREAKTHROUGH, ApprovalPathway.PRIORITY_REVIEW, ApprovalPathway.ORPHAN],
        approved=True,
        adcom_vote=None,
        key_lesson=(
            "First mutation-class specific CF therapy; ppFEV1 +10.6 pp in STRIVE. "
            "Biomarker (sweat chloride) corroborated mechanism; companion diagnostic co-developed. "
            "Template for precision rare disease approvals."
        ),
    ),
    ExpandedPrecedentRecord(
        drug_name="voxelotor",
        brand_name="Oxbryta",
        company="Global Blood Therapeutics",
        approval_year=2019,
        therapeutic_area="rare_disease",
        indication="Sickle cell disease",
        modality="small_molecule",
        primary_endpoint="Hemoglobin response (>=1 g/dL increase)",
        approval_pathway=[ApprovalPathway.ACCELERATED, ApprovalPathway.BREAKTHROUGH, ApprovalPathway.PRIORITY_REVIEW, ApprovalPathway.ORPHAN],
        approved=True,
        adcom_vote=None,
        key_lesson=(
            "Accelerated approval on Hgb surrogate; confirmatory trial required to show VOC reduction or OS benefit. "
            "Withdrawn 2024 after confirmatory HOPE-KIDS 2 failed to show VOC reduction — cautionary tale for surrogate-endpoint approvals."
        ),
    ),
    # --- Rare disease: CRL example ---
    ExpandedPrecedentRecord(
        drug_name="ataluren",
        brand_name="Translarna",
        company="PTC Therapeutics",
        approval_year=None,
        therapeutic_area="rare_disease",
        indication="Duchenne muscular dystrophy, nonsense mutation",
        modality="small_molecule",
        primary_endpoint="6MWD change from baseline",
        approval_pathway=[ApprovalPathway.ACCELERATED, ApprovalPathway.ORPHAN],
        approved=False,
        crl_issued=True,
        adcom_vote="7-6 against (2023 adcom)",
        key_lesson=(
            "FDA issued CRL citing lack of substantial evidence of effectiveness; "
            "6MWD failed to reach significance in confirmatory ACT DMD trial. "
            "Conditional approval in EU does not predict US outcome. "
            "Narrow adcom split (7-6) illustrates high uncertainty in functional endpoint trials."
        ),
    ),
    # --- Rare disease: RNA/gene therapy ---
    ExpandedPrecedentRecord(
        drug_name="nusinersen",
        brand_name="Spinraza",
        company="Biogen/Ionis",
        approval_year=2016,
        therapeutic_area="rare_disease",
        indication="Spinal muscular atrophy (all types)",
        modality="rna",
        primary_endpoint="HFMSE / motor milestone achievement",
        approval_pathway=[ApprovalPathway.ACCELERATED, ApprovalPathway.BREAKTHROUGH, ApprovalPathway.PRIORITY_REVIEW, ApprovalPathway.ORPHAN],
        approved=True,
        adcom_vote=None,
        key_lesson=(
            "First approved therapy for SMA; antisense oligonucleotide modifying SMN2 splicing. "
            "Intrathecal delivery required; NURTURE data in presymptomatic patients supported expanded use. "
            "Validated HFMSE and motor milestones as regulatory endpoints in SMA."
        ),
    ),
    ExpandedPrecedentRecord(
        drug_name="onasemnogene abeparvovec",
        brand_name="Zolgensma",
        company="AveXis/Novartis",
        approval_year=2019,
        therapeutic_area="rare_disease",
        indication="SMA type 1, children <2 years",
        modality="gene_therapy",
        primary_endpoint="Event-free survival / motor milestone achievement",
        approval_pathway=[ApprovalPathway.ACCELERATED, ApprovalPathway.BREAKTHROUGH, ApprovalPathway.PRIORITY_REVIEW, ApprovalPathway.ORPHAN],
        approved=True,
        adcom_vote=None,
        key_lesson=(
            "First gene therapy for SMA; single IV infusion. "
            "Approved on functional motor milestone endpoint in START trial (n=15). "
            "Highest-priced drug at approval ($2.1M). "
            "Post-marketing data manipulation controversy did not reverse approval."
        ),
    ),
    ExpandedPrecedentRecord(
        drug_name="luspatercept",
        brand_name="Reblozyl",
        company="Bristol-Myers Squibb/Acceleron",
        approval_year=2019,
        therapeutic_area="rare_disease",
        indication="Beta-thalassemia and MDS with ring sideroblasts",
        modality="biologic",
        primary_endpoint="Transfusion independence",
        approval_pathway=[ApprovalPathway.PRIORITY_REVIEW, ApprovalPathway.ORPHAN, ApprovalPathway.BREAKTHROUGH],
        approved=True,
        adcom_vote=None,
        key_lesson=(
            "Erythroid maturation agent approved on transfusion independence endpoint; "
            "MEDALIST (MDS) and BELIEVE (beta-thal) Phase 3 trials. "
            "Demonstrates TI as robust FDA endpoint for transfusion-dependent anemias."
        ),
    ),
    # --- Neurology ---
    ExpandedPrecedentRecord(
        drug_name="lecanemab",
        brand_name="Leqembi",
        company="Eisai/Biogen",
        approval_year=2023,
        therapeutic_area="neurology",
        indication="Early Alzheimer's disease (MCI/mild dementia)",
        modality="biologic",
        primary_endpoint="CDR-SB (Clinical Dementia Rating Sum of Boxes)",
        approval_pathway=[ApprovalPathway.ACCELERATED, ApprovalPathway.BREAKTHROUGH, ApprovalPathway.PRIORITY_REVIEW],
        approved=True,
        adcom_vote="6-0 favorable (traditional approval)",
        key_lesson=(
            "First anti-amyloid antibody with traditional approval on clinical endpoint (CDR-SB -0.45 pts). "
            "ARIA (amyloid-related imaging abnormalities) safety managed via MRI monitoring protocol. "
            "Contrasts with aducanumab controversy; reinforces need for clinical benefit on cognitive endpoint."
        ),
    ),
    # --- Immunology / respiratory ---
    ExpandedPrecedentRecord(
        drug_name="dupilumab",
        brand_name="Dupixent",
        company="Sanofi/Regeneron",
        approval_year=2017,
        therapeutic_area="immunology",
        indication="Moderate-to-severe atopic dermatitis",
        modality="biologic",
        primary_endpoint="IGA 0/1 and EASI-75",
        approval_pathway=[ApprovalPathway.BREAKTHROUGH, ApprovalPathway.PRIORITY_REVIEW],
        approved=True,
        adcom_vote=None,
        key_lesson=(
            "First biologic targeting IL-4Rα (dual IL-4/IL-13 blockade); "
            "SOLO 1/2 Phase 3 with robust composite skin endpoint. "
            "Expanded to asthma, CRSwNP, EoE, PNU — validates platform IL-4/IL-13 biology across type 2 inflammation."
        ),
    ),
    ExpandedPrecedentRecord(
        drug_name="tezepelumab",
        brand_name="Tezspire",
        company="AstraZeneca/Amgen",
        approval_year=2021,
        therapeutic_area="immunology",
        indication="Severe asthma (unselected by biomarker)",
        modality="biologic",
        primary_endpoint="Annualized asthma exacerbation rate (AAER)",
        approval_pathway=[ApprovalPathway.BREAKTHROUGH, ApprovalPathway.PRIORITY_REVIEW],
        approved=True,
        adcom_vote=None,
        key_lesson=(
            "Anti-TSLP approved without biomarker enrichment (eosinophil/IgE) in severe asthma — "
            "NAVIGATOR Phase 3 showed AAER reduction across all biomarker subgroups. "
            "Contrasts with mepolizumab/benralizumab which require eosinophil >=150-300."
        ),
    ),
]


class PrecedentExpander:
    """Provides richer query surface over the expanded FDA precedent corpus."""

    def __init__(self) -> None:
        self._records: list[ExpandedPrecedentRecord] = EXPANDED_PRECEDENTS

    def by_modality(self, modality: str) -> list[ExpandedPrecedentRecord]:
        """Return records matching the given modality."""
        return [r for r in self._records if r.modality == modality]

    def by_pathway(self, pathway: ApprovalPathway) -> list[ExpandedPrecedentRecord]:
        """Return records that include the given pathway."""
        return [r for r in self._records if pathway in r.approval_pathway]

    def by_ta(self, therapeutic_area: str) -> list[ExpandedPrecedentRecord]:
        """Return records for a given therapeutic area."""
        return [r for r in self._records if r.therapeutic_area == therapeutic_area]

    def crls(self) -> list[ExpandedPrecedentRecord]:
        """Return records where a CRL was issued."""
        return [r for r in self._records if r.crl_issued]

    def approvals(self) -> list[ExpandedPrecedentRecord]:
        """Return records where the drug was approved."""
        return [r for r in self._records if r.approved]

    def lessons_for_modality(self, modality: str) -> list[str]:
        """Return key_lesson strings for all records matching the given modality."""
        return [r.key_lesson for r in self.by_modality(modality) if r.key_lesson]

    def all_records(self) -> list[ExpandedPrecedentRecord]:
        """Return all records in the corpus."""
        return list(self._records)
