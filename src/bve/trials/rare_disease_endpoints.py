"""Rare disease endpoint library with 15+ endpoints across neuromuscular, metabolic, pulmonary, hematologic, and ophthalmic indication areas."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class RareDiseaseEndpoint(BaseModel):
    name: str
    abbreviation: str
    indication_area: str  # "neuromuscular" | "metabolic" | "pulmonary" | "hematologic" | "ophthalmic"
    endpoint_type: str  # "primary" | "secondary" | "biomarker"
    fda_path: str  # "standard" | "accelerated_approval" | "breakthrough"
    validated: bool  # FDA-validated endpoint
    notes: str = ""


RARE_DISEASE_ENDPOINTS: list[RareDiseaseEndpoint] = [
    # --- Neuromuscular ---
    RareDiseaseEndpoint(
        name="Six-Minute Walk Distance",
        abbreviation="6MWD",
        indication_area="neuromuscular",
        endpoint_type="primary",
        fda_path="standard",
        validated=True,
        notes=(
            "FDA-validated for Duchenne muscular dystrophy (DMD) and spinal muscular atrophy (SMA); "
            "minimal clinically important difference ~20–30 m. Ceiling effect in ambulatory patients."
        ),
    ),
    RareDiseaseEndpoint(
        name="Forced Vital Capacity",
        abbreviation="FVC",
        indication_area="neuromuscular",
        endpoint_type="primary",
        fda_path="standard",
        validated=True,
        notes=(
            "Pulmonary function primary in DMD and SMA. "
            "Slope of FVC decline vs placebo used in nusinersen and onasemnogene pivotals."
        ),
    ),
    RareDiseaseEndpoint(
        name="Hammersmith Functional Motor Scale Expanded",
        abbreviation="HFMSE",
        indication_area="neuromuscular",
        endpoint_type="primary",
        fda_path="breakthrough",
        validated=True,
        notes=(
            "32-item motor function scale validated in type 2/3 SMA; "
            "used in nusinersen (CHERISH) and risdiplam (SUNFISH) trials."
        ),
    ),
    RareDiseaseEndpoint(
        name="Motor Function Measure 32",
        abbreviation="MFM-32",
        indication_area="neuromuscular",
        endpoint_type="primary",
        fda_path="standard",
        validated=True,
        notes=(
            "32-item scale covering standing/transfers, axial/proximal, distal motor function; "
            "used in DMD and non-ambulant SMA trials."
        ),
    ),
    RareDiseaseEndpoint(
        name="Revised Upper Limb Module",
        abbreviation="RULM",
        indication_area="neuromuscular",
        endpoint_type="secondary",
        fda_path="breakthrough",
        validated=True,
        notes=(
            "Upper limb function in non-ambulant SMA patients; "
            "20-item scale, validated for type 2 SMA; supported nusinersen label in non-sitters."
        ),
    ),
    # --- Metabolic ---
    RareDiseaseEndpoint(
        name="Serum Phenylalanine",
        abbreviation="Phe",
        indication_area="metabolic",
        endpoint_type="biomarker",
        fda_path="accelerated_approval",
        validated=True,
        notes=(
            "FDA-accepted surrogate for PKU (phenylketonuria); "
            "sapropterin and pegvaliase approvals used Phe reduction as primary. "
            "Target <360 micromol/L."
        ),
    ),
    RareDiseaseEndpoint(
        name="Acid Alpha-Glucosidase Enzyme Activity",
        abbreviation="GAA",
        indication_area="metabolic",
        endpoint_type="biomarker",
        fda_path="standard",
        validated=True,
        notes=(
            "Pharmacodynamic biomarker for Pompe disease; "
            "GAA activity in dried blood spots or muscle biopsy. "
            "Clinically anchored to 6MWD and FVC outcomes."
        ),
    ),
    RareDiseaseEndpoint(
        name="Low-Density Lipoprotein Cholesterol",
        abbreviation="LDL-C",
        indication_area="metabolic",
        endpoint_type="biomarker",
        fda_path="standard",
        validated=True,
        notes=(
            "Established surrogate for homozygous familial hypercholesterolemia (HoFH) and PCSK9 inhibitor approvals; "
            "LDL-C reduction >= 50% considered meaningful."
        ),
    ),
    # --- Pulmonary ---
    RareDiseaseEndpoint(
        name="Forced Expiratory Volume in 1 Second",
        abbreviation="FEV1",
        indication_area="pulmonary",
        endpoint_type="primary",
        fda_path="standard",
        validated=True,
        notes=(
            "Standard spirometry endpoint for CF (ivacaftor, lumacaftor/ivacaftor, elexacaftor/tezacaftor/ivacaftor). "
            "Absolute change in ppFEV1 >= 5 percentage points considered clinically meaningful."
        ),
    ),
    RareDiseaseEndpoint(
        name="Percent Predicted Forced Expiratory Volume in 1 Second",
        abbreviation="ppFEV1",
        indication_area="pulmonary",
        endpoint_type="primary",
        fda_path="breakthrough",
        validated=True,
        notes=(
            "Age/sex/height-adjusted FEV1 used as primary in CF modulator trials; "
            "elexacaftor/tezacaftor/ivacaftor achieved +14.3 pp improvement vs placebo."
        ),
    ),
    RareDiseaseEndpoint(
        name="Sweat Chloride",
        abbreviation="SwCl",
        indication_area="pulmonary",
        endpoint_type="biomarker",
        fda_path="breakthrough",
        validated=True,
        notes=(
            "CFTR function biomarker; reduction to <60 mmol/L indicates restored CFTR activity. "
            "Supported ivacaftor (KALYDECO) accelerated approval; clinically anchored to ppFEV1."
        ),
    ),
    RareDiseaseEndpoint(
        name="Lung Clearance Index",
        abbreviation="LCI",
        indication_area="pulmonary",
        endpoint_type="secondary",
        fda_path="accelerated_approval",
        validated=False,
        notes=(
            "Multiple breath washout measure of ventilation inhomogeneity; "
            "sensitive in early CF lung disease; not yet FDA-validated as standalone primary."
        ),
    ),
    # --- Hematologic ---
    RareDiseaseEndpoint(
        name="Hemoglobin",
        abbreviation="Hgb",
        indication_area="hematologic",
        endpoint_type="primary",
        fda_path="standard",
        validated=True,
        notes=(
            "Primary for thalassemia (luspatercept) and sickle cell disease (voxelotor). "
            "Clinically meaningful threshold: >=1 g/dL increase from baseline."
        ),
    ),
    RareDiseaseEndpoint(
        name="Transfusion Independence",
        abbreviation="TI",
        indication_area="hematologic",
        endpoint_type="primary",
        fda_path="standard",
        validated=True,
        notes=(
            "FDA-established endpoint for MDS (luspatercept MEDALIST) and beta-thalassemia. "
            "Definition: >= 8 weeks without RBC transfusion."
        ),
    ),
    RareDiseaseEndpoint(
        name="Lactate Dehydrogenase Normalization",
        abbreviation="LDH",
        indication_area="hematologic",
        endpoint_type="biomarker",
        fda_path="accelerated_approval",
        validated=True,
        notes=(
            "Hemolysis biomarker for paroxysmal nocturnal hemoglobinuria (PNH) and atypical HUS; "
            "eculizumab approval anchored on LDH normalization."
        ),
    ),
    # --- Ophthalmic ---
    RareDiseaseEndpoint(
        name="Best-Corrected Visual Acuity",
        abbreviation="BCVA",
        indication_area="ophthalmic",
        endpoint_type="primary",
        fda_path="standard",
        validated=True,
        notes=(
            "ETDRS letter score; standard primary in retinal dystrophies and macular degeneration. "
            "Voretigene neparvovec (LUXTURNA) used full-field stimulus testing (FST) as primary; "
            "BCVA used as secondary."
        ),
    ),
    RareDiseaseEndpoint(
        name="Visual Function Questionnaire-25",
        abbreviation="VFQ-25",
        indication_area="ophthalmic",
        endpoint_type="secondary",
        fda_path="standard",
        validated=True,
        notes=(
            "NEI VFQ-25 is the standard PRO for visual function impairment; "
            "used as key secondary in inherited retinal dystrophy and age-related macular degeneration trials."
        ),
    ),
]


class RareDiseaseEndpointLibrary:
    """Query interface for the rare disease endpoint corpus."""

    def __init__(self) -> None:
        self._index: dict[str, RareDiseaseEndpoint] = {ep.abbreviation: ep for ep in RARE_DISEASE_ENDPOINTS}

    def get(self, abbreviation: str) -> Optional[RareDiseaseEndpoint]:
        """Return endpoint by abbreviation, or None if not found."""
        return self._index.get(abbreviation)

    def by_indication_area(self, area: str) -> list[RareDiseaseEndpoint]:
        """Return all endpoints for a given indication area."""
        return [ep for ep in RARE_DISEASE_ENDPOINTS if ep.indication_area == area]

    def validated_endpoints(self) -> list[RareDiseaseEndpoint]:
        """Return only FDA-validated endpoints."""
        return [ep for ep in RARE_DISEASE_ENDPOINTS if ep.validated]

    def all_endpoints(self) -> list[RareDiseaseEndpoint]:
        """Return all endpoints in the library."""
        return list(RARE_DISEASE_ENDPOINTS)
