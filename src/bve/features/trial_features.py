"""
Trial feature extraction for POS model inputs.

Derives structured qualitative + quantitative features from a ClinicalTrial
and its ClinicalTrials.gov protocol data that can feed into the POS model
or a downstream ML model.
"""
from __future__ import annotations

from pydantic import BaseModel

from bve.entities.trial import ClinicalTrial, EndpointType
from bve.models.pos_model import (
    CompetitivePressure, MoAPrecedent, POSAdjusters, SampleSizeAdequacy, SafetyProfile
)


class TrialFeatures(BaseModel):
    """Structured features derived from a trial + analyst judgment."""

    nct_id: str | None = None
    phase: str
    enrollment: int | None = None
    is_randomized: bool = True
    is_blinded: bool = True
    endpoint_type: EndpointType = EndpointType.SURROGATE_VALIDATED
    moa_precedent: MoAPrecedent = MoAPrecedent.PARTIAL
    sample_size_adequacy: SampleSizeAdequacy = SampleSizeAdequacy.ADEQUATE
    safety_profile: SafetyProfile = SafetyProfile.MINOR
    competitive_pressure: CompetitivePressure = CompetitivePressure.MODERATE
    biomarker_selected: bool = False
    strong_prior_data: bool = False
    has_breakthrough: bool = False

    def to_pos_adjusters(self) -> POSAdjusters:
        return POSAdjusters(
            endpoint_type=self.endpoint_type,
            moa_precedent=self.moa_precedent,
            sample_size_adequacy=self.sample_size_adequacy,
            safety_profile=self.safety_profile,
            competitive_pressure=self.competitive_pressure,
            biomarker_selected_population=self.biomarker_selected,
            strong_prior_phase_data=self.strong_prior_data,
            has_breakthrough_designation=self.has_breakthrough,
        )


def extract_features(trial: ClinicalTrial) -> TrialFeatures:
    """
    Extract a TrialFeatures object from a ClinicalTrial entity.
    Analyst qualitative inputs (MoA precedent, safety, etc.) default to midpoints
    and should be overridden with expert judgment before running the POS model.
    """
    # Estimate sample size adequacy from enrollment
    sample_adequacy = SampleSizeAdequacy.ADEQUATE
    if trial.enrollment:
        if trial.enrollment < 50:
            sample_adequacy = SampleSizeAdequacy.BORDERLINE
        elif trial.enrollment > 500:
            sample_adequacy = SampleSizeAdequacy.WELL_POWERED

    return TrialFeatures(
        nct_id=trial.nct_id,
        phase=trial.phase.value,
        enrollment=trial.enrollment,
        is_randomized=trial.is_randomized,
        is_blinded=trial.is_blinded,
        endpoint_type=trial.endpoint_type,
        sample_size_adequacy=sample_adequacy,
    )
