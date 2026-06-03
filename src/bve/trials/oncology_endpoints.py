"""Extended oncology-specific endpoint library with 20+ endpoints covering solid tumors, heme, biomarker, and PRO endpoints."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class OncologyEndpoint(BaseModel):
    name: str
    abbreviation: str
    endpoint_type: str  # "primary" | "secondary" | "exploratory"
    regulatory_precedent: str  # "established" | "accelerated" | "exploratory"
    tumor_types: list[str]  # applicable tumor types
    surrogate_for: Optional[str] = None  # e.g. "OS" if surrogate for overall survival
    fda_notes: str = ""


ONCOLOGY_ENDPOINTS: list[OncologyEndpoint] = [
    # --- Solid tumor primary / key secondary endpoints ---
    OncologyEndpoint(
        name="Overall Survival",
        abbreviation="OS",
        endpoint_type="primary",
        regulatory_precedent="established",
        tumor_types=["nsclc", "breast", "colorectal", "gastric", "melanoma", "prostate", "bladder", "all_solid"],
        surrogate_for=None,
        fda_notes="Gold standard endpoint; required for full traditional approval when feasible.",
    ),
    OncologyEndpoint(
        name="Progression-Free Survival",
        abbreviation="PFS",
        endpoint_type="primary",
        regulatory_precedent="accelerated",
        tumor_types=["nsclc", "breast", "colorectal", "ovarian", "melanoma", "all_solid"],
        surrogate_for="OS",
        fda_notes=(
            "Accepted as primary under accelerated approval; OS confirmation typically required. "
            "Magnitude of PFS benefit and correlation with OS vary by tumor type."
        ),
    ),
    OncologyEndpoint(
        name="Objective Response Rate",
        abbreviation="ORR",
        endpoint_type="primary",
        regulatory_precedent="accelerated",
        tumor_types=["nsclc", "breast", "colorectal", "melanoma", "bladder", "all_solid"],
        surrogate_for="OS",
        fda_notes=(
            "Accepted for single-arm accelerated approvals in relapsed/refractory settings. "
            "Threshold typically >20–30% in R/R; confirmatory trial required."
        ),
    ),
    OncologyEndpoint(
        name="Duration of Response",
        abbreviation="DOR",
        endpoint_type="secondary",
        regulatory_precedent="established",
        tumor_types=["nsclc", "breast", "melanoma", "bladder", "all_solid"],
        surrogate_for=None,
        fda_notes="Key secondary supporting ORR-based approvals; median DOR > 6 months considered meaningful.",
    ),
    OncologyEndpoint(
        name="Disease Control Rate",
        abbreviation="DCR",
        endpoint_type="secondary",
        regulatory_precedent="exploratory",
        tumor_types=["nsclc", "colorectal", "hepatocellular", "all_solid"],
        surrogate_for=None,
        fda_notes="Includes CR + PR + SD; exploratory in most settings; not accepted as standalone primary.",
    ),
    OncologyEndpoint(
        name="Time to Response",
        abbreviation="TTR",
        endpoint_type="secondary",
        regulatory_precedent="exploratory",
        tumor_types=["nsclc", "breast", "melanoma", "all_solid"],
        surrogate_for=None,
        fda_notes="Descriptive endpoint; informs pace of benefit onset; not an approval endpoint.",
    ),
    OncologyEndpoint(
        name="Event-Free Survival",
        abbreviation="EFS",
        endpoint_type="primary",
        regulatory_precedent="accelerated",
        tumor_types=["breast", "bladder", "nsclc", "all_solid"],
        surrogate_for="OS",
        fda_notes=(
            "Used increasingly in neoadjuvant/adjuvant solid tumor trials as OS surrogate; "
            "FDA has accepted in some early-stage breast cancer programs."
        ),
    ),
    OncologyEndpoint(
        name="Recurrence-Free Survival",
        abbreviation="RFS",
        endpoint_type="primary",
        regulatory_precedent="established",
        tumor_types=["melanoma", "breast", "colorectal", "nsclc"],
        surrogate_for="OS",
        fda_notes="Adjuvant setting primary endpoint; established in melanoma (nivolumab, pembrolizumab).",
    ),
    OncologyEndpoint(
        name="Pathologic Complete Response",
        abbreviation="pCR",
        endpoint_type="primary",
        regulatory_precedent="accelerated",
        tumor_types=["breast", "nsclc", "gastric"],
        surrogate_for="EFS",
        fda_notes=(
            "Accelerated approval endpoint in neoadjuvant breast cancer; "
            "correlation with EFS/OS validated in HER2+ and TNBC subtypes."
        ),
    ),
    OncologyEndpoint(
        name="Minimal Residual Disease",
        abbreviation="MRD",
        endpoint_type="exploratory",
        regulatory_precedent="accelerated",
        tumor_types=["nsclc", "colorectal", "breast"],
        surrogate_for="EFS",
        fda_notes=(
            "Emerging solid tumor endpoint via ctDNA MRD; FDA draft guidance issued 2023; "
            "not yet established as standalone primary in solid tumors."
        ),
    ),
    # --- Hematologic malignancy endpoints ---
    OncologyEndpoint(
        name="Complete Remission",
        abbreviation="CR",
        endpoint_type="primary",
        regulatory_precedent="established",
        tumor_types=["aml", "all", "mds", "cll", "dlbcl"],
        surrogate_for=None,
        fda_notes="Established primary in AML/MDS; venetoclax, enasidenib, ivosidenib precedent.",
    ),
    OncologyEndpoint(
        name="Complete Remission with Incomplete Blood Count Recovery",
        abbreviation="CRi",
        endpoint_type="primary",
        regulatory_precedent="established",
        tumor_types=["aml", "mds"],
        surrogate_for="CR",
        fda_notes="Composite with CR for AML approvals; gilteritinib, midostaurin precedent.",
    ),
    OncologyEndpoint(
        name="MRD-Negative Complete Remission",
        abbreviation="MRD-neg-CR",
        endpoint_type="primary",
        regulatory_precedent="accelerated",
        tumor_types=["cll", "all", "mm"],
        surrogate_for="PFS",
        fda_notes=(
            "Emerging endpoint in CLL (venetoclax + obinutuzumab) and MM; "
            "FDA-Oncology Center of Excellence actively evaluating."
        ),
    ),
    OncologyEndpoint(
        name="Overall Survival (hematologic)",
        abbreviation="OS-HEM",
        endpoint_type="primary",
        regulatory_precedent="established",
        tumor_types=["aml", "all", "cll", "dlbcl", "mm"],
        surrogate_for=None,
        fda_notes="Required for full traditional approval in aggressive hematologic malignancies.",
    ),
    OncologyEndpoint(
        name="Progression-Free Survival (hematologic)",
        abbreviation="PFS-HEM",
        endpoint_type="primary",
        regulatory_precedent="established",
        tumor_types=["cll", "fl", "dlbcl", "mm"],
        surrogate_for="OS",
        fda_notes="Established in indolent hematologic malignancies; ibrutinib, acalabrutinib precedent.",
    ),
    OncologyEndpoint(
        name="Time to Response (hematologic)",
        abbreviation="TTR-HEM",
        endpoint_type="secondary",
        regulatory_precedent="exploratory",
        tumor_types=["aml", "mds", "cll"],
        surrogate_for=None,
        fda_notes="Descriptive secondary; not an approval endpoint.",
    ),
    # --- Biomarker / liquid biopsy endpoints ---
    OncologyEndpoint(
        name="Circulating Tumor DNA Clearance",
        abbreviation="ctDNA-clear",
        endpoint_type="exploratory",
        regulatory_precedent="exploratory",
        tumor_types=["colorectal", "nsclc", "breast", "all_solid"],
        surrogate_for="EFS",
        fda_notes=(
            "FDA draft guidance (2023) positions ctDNA MRD clearance as potential accelerated approval endpoint; "
            "analytical validation requirements stringent."
        ),
    ),
    OncologyEndpoint(
        name="Tumor Mutational Burden",
        abbreviation="TMB",
        endpoint_type="exploratory",
        regulatory_precedent="accelerated",
        tumor_types=["nsclc", "melanoma", "colorectal", "all_solid"],
        surrogate_for="ORR",
        fda_notes=(
            "FDA approved pembrolizumab for TMB-H (>=10 mut/Mb) solid tumors (2020); "
            "predictive for IO benefit in some but not all tumor types."
        ),
    ),
    OncologyEndpoint(
        name="PD-L1 Expression",
        abbreviation="PD-L1",
        endpoint_type="exploratory",
        regulatory_precedent="accelerated",
        tumor_types=["nsclc", "bladder", "gastric", "cervical"],
        surrogate_for="ORR",
        fda_notes=(
            "Used as companion diagnostic to enrich responders; TPS >= 50% for pembrolizumab monotherapy "
            "in first-line NSCLC. Not a standalone approval endpoint."
        ),
    ),
    # --- Patient-reported outcome endpoints ---
    OncologyEndpoint(
        name="Quality of Life (EORTC QLQ-C30)",
        abbreviation="QoL-C30",
        endpoint_type="secondary",
        regulatory_precedent="exploratory",
        tumor_types=["nsclc", "colorectal", "breast", "ovarian", "gastric", "all_solid"],
        surrogate_for=None,
        fda_notes=(
            "EORTC QLQ-C30 is the standard PRO instrument in oncology. "
            "FDA increasingly requires PRO data; standalone approval unlikely but supports labeling claims."
        ),
    ),
    OncologyEndpoint(
        name="Pain Response",
        abbreviation="PR-pain",
        endpoint_type="secondary",
        regulatory_precedent="exploratory",
        tumor_types=["prostate", "bone_metastases", "mm"],
        surrogate_for=None,
        fda_notes=(
            "Pain palliation endpoint using BPI or NRS-11; "
            "used in prostate cancer trials and bone mets palliation studies."
        ),
    ),
]


class OncologyEndpointLibrary:
    """Query interface for the extended oncology endpoint corpus."""

    def __init__(self) -> None:
        self._index: dict[str, OncologyEndpoint] = {ep.abbreviation: ep for ep in ONCOLOGY_ENDPOINTS}

    def get(self, abbreviation: str) -> Optional[OncologyEndpoint]:
        """Return endpoint by abbreviation, or None if not found."""
        return self._index.get(abbreviation)

    def by_tumor_type(self, tumor_type: str) -> list[OncologyEndpoint]:
        """Return all endpoints applicable to the given tumor type (including 'all_solid' entries)."""
        return [ep for ep in ONCOLOGY_ENDPOINTS if tumor_type in ep.tumor_types or "all_solid" in ep.tumor_types]

    def established_primaries(self) -> list[OncologyEndpoint]:
        """Return endpoints with regulatory_precedent=='established' AND endpoint_type=='primary'."""
        return [
            ep for ep in ONCOLOGY_ENDPOINTS
            if ep.regulatory_precedent == "established" and ep.endpoint_type == "primary"
        ]

    def surrogates(self) -> list[OncologyEndpoint]:
        """Return endpoints that are surrogates for another endpoint (surrogate_for is not None)."""
        return [ep for ep in ONCOLOGY_ENDPOINTS if ep.surrogate_for is not None]

    def all_endpoints(self) -> list[OncologyEndpoint]:
        """Return all endpoints in the library."""
        return list(ONCOLOGY_ENDPOINTS)
