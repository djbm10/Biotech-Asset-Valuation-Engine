"""Endpoint validity — regulatory and clinical meaningfulness scoring for endpoints."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EndpointValidityScore(BaseModel):
    """Validity assessment for a single clinical endpoint."""

    endpoint_name: str
    endpoint_type: str  # "primary" | "secondary" | "exploratory"
    clinical_meaningfulness: float = Field(ge=0.0, le=1.0)
    regulatory_acceptability: float = Field(ge=0.0, le=1.0)
    measurability: float = Field(ge=0.0, le=1.0)
    precedent_count: int = 0
    rationale: str


class EndpointValidity(BaseModel):
    """Full endpoint validity assessment for a trial."""

    asset_id: str
    trial_id: Optional[str] = None
    scored_at: datetime
    primary_endpoint_scores: list[EndpointValidityScore] = Field(default_factory=list)
    secondary_endpoint_scores: list[EndpointValidityScore] = Field(default_factory=list)
    overall_validity_score: float = Field(ge=0.0, le=1.0)
    regulatory_risk: str  # "low" | "medium" | "high"
    commentary: str


# ---------------------------------------------------------------------------
# Step 6: Structured endpoint scoring types
# ---------------------------------------------------------------------------


class EndpointCategory(str, Enum):
    OS = "OS"
    PFS = "PFS"
    ORR = "ORR"
    DFS = "DFS"
    EFS = "EFS"
    CR = "CR"
    PRO = "PRO"
    BIOMARKER = "BIOMARKER"
    SURROGATE = "SURROGATE"
    COMPOSITE = "COMPOSITE"
    SAFETY = "SAFETY"
    OTHER = "OTHER"


class RegulatoryWeight(str, Enum):
    GOLD = "GOLD"
    SILVER = "SILVER"
    BRONZE = "BRONZE"
    EXPLORATORY = "EXPLORATORY"


class EndpointProfile(BaseModel):
    """Canonical profile for a known clinical endpoint."""

    model_config = {"frozen": True}

    name: str
    category: EndpointCategory
    regulatory_weight: RegulatoryWeight
    typical_effect_size: str | None = None
    requires_comparator: bool
    notes: str | None = None


class EndpointValidityScoreV2(BaseModel):
    """Step 6 validity score for an endpoint — deterministic rules, no LLM."""

    model_config = {"frozen": True}

    endpoint_name: str
    matched_profile: EndpointProfile | None
    validity_score: float
    regulatory_weight: RegulatoryWeight
    requires_comparator: bool
    is_primary: bool
    rationale: str


# ---------------------------------------------------------------------------
# Endpoint library — keyed by lowercase name / alias
# ---------------------------------------------------------------------------

_OS_PROFILE = EndpointProfile(
    name="Overall Survival",
    category=EndpointCategory.OS,
    regulatory_weight=RegulatoryWeight.GOLD,
    typical_effect_size="HR 0.65-0.80",
    requires_comparator=True,
    notes="Gold standard; FDA strongly prefers OS for oncology approvals.",
)

_PFS_PROFILE = EndpointProfile(
    name="Progression-Free Survival",
    category=EndpointCategory.PFS,
    regulatory_weight=RegulatoryWeight.SILVER,
    typical_effect_size="HR 0.60-0.75",
    requires_comparator=True,
    notes="Widely accepted primary endpoint in oncology.",
)

_ORR_PROFILE = EndpointProfile(
    name="Objective Response Rate",
    category=EndpointCategory.ORR,
    regulatory_weight=RegulatoryWeight.SILVER,
    typical_effect_size="ORR > 30%",
    requires_comparator=False,
    notes="Supports accelerated approval; often single-arm acceptable.",
)

_CR_PROFILE = EndpointProfile(
    name="Complete Response",
    category=EndpointCategory.CR,
    regulatory_weight=RegulatoryWeight.SILVER,
    typical_effect_size="CR > 20%",
    requires_comparator=False,
    notes="Complete disappearance of measurable disease.",
)

_DFS_PROFILE = EndpointProfile(
    name="Disease-Free Survival",
    category=EndpointCategory.DFS,
    regulatory_weight=RegulatoryWeight.SILVER,
    typical_effect_size="HR 0.65-0.80",
    requires_comparator=True,
    notes="Used in adjuvant settings.",
)

_EFS_PROFILE = EndpointProfile(
    name="Event-Free Survival",
    category=EndpointCategory.EFS,
    regulatory_weight=RegulatoryWeight.SILVER,
    typical_effect_size="HR 0.65-0.80",
    requires_comparator=True,
    notes="Common in hematologic malignancies and pediatric oncology.",
)

_DOR_PROFILE = EndpointProfile(
    name="Duration of Response",
    category=EndpointCategory.SURROGATE,
    regulatory_weight=RegulatoryWeight.BRONZE,
    typical_effect_size=None,
    requires_comparator=False,
    notes="Surrogate; often used alongside ORR.",
)

_TTP_PROFILE = EndpointProfile(
    name="Time to Progression",
    category=EndpointCategory.SURROGATE,
    regulatory_weight=RegulatoryWeight.BRONZE,
    typical_effect_size=None,
    requires_comparator=True,
    notes="Older surrogate; largely superseded by PFS.",
)

_MRD_PROFILE = EndpointProfile(
    name="Minimal Residual Disease",
    category=EndpointCategory.BIOMARKER,
    regulatory_weight=RegulatoryWeight.BRONZE,
    typical_effect_size=None,
    requires_comparator=False,
    notes="Biomarker endpoint; FDA increasingly accepts as surrogate in CLL/ALL.",
)

_PCR_PROFILE = EndpointProfile(
    name="Pathologic Complete Response",
    category=EndpointCategory.SURROGATE,
    regulatory_weight=RegulatoryWeight.SILVER,
    typical_effect_size="pCR > 40%",
    requires_comparator=True,
    notes="FDA-accepted accelerated approval endpoint in some breast cancer settings.",
)

_PRO_PROFILE = EndpointProfile(
    name="Patient-Reported Outcomes",
    category=EndpointCategory.PRO,
    regulatory_weight=RegulatoryWeight.BRONZE,
    typical_effect_size=None,
    requires_comparator=False,
    notes="Increasingly valued by FDA; rarely approval-enabling alone.",
)

_HBA1C_PROFILE = EndpointProfile(
    name="HbA1c",
    category=EndpointCategory.SURROGATE,
    regulatory_weight=RegulatoryWeight.SILVER,
    typical_effect_size="Reduction ≥ 0.5%",
    requires_comparator=True,
    notes="FDA-accepted surrogate in endocrinology / T2DM.",
)

_LDL_PROFILE = EndpointProfile(
    name="LDL-C Reduction",
    category=EndpointCategory.SURROGATE,
    regulatory_weight=RegulatoryWeight.SILVER,
    typical_effect_size="LDL-C reduction ≥ 40%",
    requires_comparator=True,
    notes="Accepted surrogate in cardiovascular / dyslipidemia.",
)

_FEV1_PROFILE = EndpointProfile(
    name="FEV1",
    category=EndpointCategory.SURROGATE,
    regulatory_weight=RegulatoryWeight.SILVER,
    typical_effect_size="Absolute change ≥ 100 mL",
    requires_comparator=True,
    notes="Lung function surrogate in COPD/asthma/CF.",
)

_ACR_PROFILE = EndpointProfile(
    name="ACR Response",
    category=EndpointCategory.COMPOSITE,
    regulatory_weight=RegulatoryWeight.SILVER,
    typical_effect_size="ACR20 ≥ 20% improvement",
    requires_comparator=True,
    notes="Composite endpoint in rheumatology.",
)

_EASI_PROFILE = EndpointProfile(
    name="EASI",
    category=EndpointCategory.COMPOSITE,
    regulatory_weight=RegulatoryWeight.SILVER,
    typical_effect_size="EASI-75 in ≥ 30% of patients",
    requires_comparator=True,
    notes="Composite endpoint in atopic dermatitis.",
)

_PSYCH_PRO_PROFILE = EndpointProfile(
    name="Psychiatric PRO Scale",
    category=EndpointCategory.PRO,
    regulatory_weight=RegulatoryWeight.SILVER,
    typical_effect_size=None,
    requires_comparator=True,
    notes="HAM-A, HAM-D, MADRS, PANSS — accepted in psychiatry/neurology.",
)

ENDPOINT_LIBRARY: dict[str, EndpointProfile] = {
    "overall survival": _OS_PROFILE,
    "os": _OS_PROFILE,
    "progression-free survival": _PFS_PROFILE,
    "progression free survival": _PFS_PROFILE,
    "pfs": _PFS_PROFILE,
    "objective response rate": _ORR_PROFILE,
    "overall response rate": _ORR_PROFILE,
    "orr": _ORR_PROFILE,
    "complete response": _CR_PROFILE,
    "cr": _CR_PROFILE,
    "disease-free survival": _DFS_PROFILE,
    "disease free survival": _DFS_PROFILE,
    "dfs": _DFS_PROFILE,
    "event-free survival": _EFS_PROFILE,
    "event free survival": _EFS_PROFILE,
    "efs": _EFS_PROFILE,
    "duration of response": _DOR_PROFILE,
    "dor": _DOR_PROFILE,
    "time to progression": _TTP_PROFILE,
    "ttp": _TTP_PROFILE,
    "minimal residual disease": _MRD_PROFILE,
    "mrd": _MRD_PROFILE,
    "pathologic complete response": _PCR_PROFILE,
    "pathological complete response": _PCR_PROFILE,
    "pcr": _PCR_PROFILE,
    "patient-reported outcomes": _PRO_PROFILE,
    "patient reported outcomes": _PRO_PROFILE,
    "pro": _PRO_PROFILE,
    "quality of life": _PRO_PROFILE,
    "qol": _PRO_PROFILE,
    "hba1c": _HBA1C_PROFILE,
    "hba1c reduction": _HBA1C_PROFILE,
    "ldl": _LDL_PROFILE,
    "ldl-c reduction": _LDL_PROFILE,
    "ldl-c": _LDL_PROFILE,
    "fev1": _FEV1_PROFILE,
    "lung function": _FEV1_PROFILE,
    "acr20": _ACR_PROFILE,
    "acr50": _ACR_PROFILE,
    "acr70": _ACR_PROFILE,
    "easi": _EASI_PROFILE,
    "easi-75": _EASI_PROFILE,
    "iga": _EASI_PROFILE,
    "iga 0/1": _EASI_PROFILE,
    "ham-a": _PSYCH_PRO_PROFILE,
    "ham-d": _PSYCH_PRO_PROFILE,
    "madrs": _PSYCH_PRO_PROFILE,
    "panss": _PSYCH_PRO_PROFILE,
}

_WEIGHT_TO_SCORE: dict[RegulatoryWeight, float] = {
    RegulatoryWeight.GOLD: 1.0,
    RegulatoryWeight.SILVER: 0.85,
    RegulatoryWeight.BRONZE: 0.65,
    RegulatoryWeight.EXPLORATORY: 0.40,
}


def score_endpoint(
    endpoint_name: str,
    is_primary: bool = True,
) -> EndpointValidityScoreV2:
    """Return a deterministic EndpointValidityScoreV2 for the given endpoint name."""
    normalized = endpoint_name.lower().strip()

    # Exact match first
    matched_profile: EndpointProfile | None = ENDPOINT_LIBRARY.get(normalized)

    # Substring match — longest key that is a substring of the normalized name, or vice versa
    if matched_profile is None:
        best_key: str | None = None
        best_len: int = 0
        for key, profile in ENDPOINT_LIBRARY.items():
            if (key in normalized or normalized in key) and len(key) > best_len:
                best_key = key
                best_len = len(key)
        if best_key is not None:
            matched_profile = ENDPOINT_LIBRARY[best_key]

    if matched_profile is not None:
        base_score = _WEIGHT_TO_SCORE[matched_profile.regulatory_weight]
        validity_score = base_score if is_primary else base_score * 0.90
        rationale = (
            f"Matched '{matched_profile.name}' ({matched_profile.category.value}, "
            f"{matched_profile.regulatory_weight.value}). "
            f"{'Primary endpoint.' if is_primary else 'Secondary endpoint (0.90× adjustment).'}"
        )
        return EndpointValidityScoreV2(
            endpoint_name=endpoint_name,
            matched_profile=matched_profile,
            validity_score=round(validity_score, 6),
            regulatory_weight=matched_profile.regulatory_weight,
            requires_comparator=matched_profile.requires_comparator,
            is_primary=is_primary,
            rationale=rationale,
        )

    # No match
    validity_score = 0.50 if is_primary else 0.50 * 0.90
    return EndpointValidityScoreV2(
        endpoint_name=endpoint_name,
        matched_profile=None,
        validity_score=round(validity_score, 6),
        regulatory_weight=RegulatoryWeight.EXPLORATORY,
        requires_comparator=False,
        is_primary=is_primary,
        rationale=(
            f"No library match for '{endpoint_name}'. "
            "Assigned EXPLORATORY weight and neutral score."
        ),
    )
