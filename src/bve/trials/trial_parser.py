"""Parse and normalize clinical trial metadata into structured TrialRecord objects."""
from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class TrialEndpoint(BaseModel):
    endpoint_type: str          # "primary" / "secondary" / "exploratory" / "safety"
    name: str
    description: Optional[str] = None
    is_surrogate: bool = False
    measurement_timepoint: Optional[str] = None


class TrialDesignRecord(BaseModel):
    """Structured representation of a parsed clinical trial."""
    nct_id: Optional[str] = None
    asset_id: Optional[str] = None
    phase: str                          # "1" / "1/2" / "2" / "2/3" / "3" / "4"
    design_type: str                    # "randomized_controlled" / "single_arm" / "open_label" / "crossover"
    blinding: str                       # "double_blind" / "single_blind" / "open_label"
    randomized: bool = True
    indication: Optional[str] = None
    condition: Optional[str] = None
    intervention: Optional[str] = None
    comparator: Optional[str] = None    # "placebo" / "active_comparator" / "none"
    enrollment_target: Optional[int] = None
    enrollment_actual: Optional[int] = None
    endpoints: list[TrialEndpoint] = Field(default_factory=list)
    biomarker_stratification: Optional[str] = None
    geography: list[str] = Field(default_factory=list)
    dosing_regimen: Optional[str] = None
    primary_completion_date: Optional[date] = None
    estimated_completion_date: Optional[date] = None
    status: str = "unknown"             # "recruiting" / "active" / "completed" / "terminated" / "withdrawn"
    sponsor: Optional[str] = None
    statistical_power: Optional[float] = None  # e.g. 0.80
    alpha: Optional[float] = None       # e.g. 0.05
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "manual"


class TrialParser:
    """
    Parse raw trial metadata dicts (e.g. from ClinicalTrials.gov API responses)
    into TrialDesignRecord objects.
    """

    def parse(self, raw: dict) -> TrialDesignRecord:
        """
        Parse a flat or nested dict of trial metadata.

        Handles both CT.gov v2 API shape and simplified flat dicts.
        Falls back gracefully when fields are missing.
        """
        # Support CT.gov v2 protocolSection nesting
        proto = raw.get("protocolSection", raw)
        ident = proto.get("identificationModule", proto)
        design = proto.get("designModule", proto)
        outcomes = proto.get("outcomesModule", proto)
        status_mod = proto.get("statusModule", proto)
        eligibility = proto.get("eligibilityModule", proto)

        nct_id = ident.get("nctId") or raw.get("nct_id")
        phase_raw = design.get("phases", [raw.get("phase", "unknown")])
        phase = phase_raw[0].replace("PHASE", "").strip() if isinstance(phase_raw, list) and phase_raw else str(raw.get("phase", "unknown"))

        primary_endpoints = [
            TrialEndpoint(endpoint_type="primary", name=m.get("measure", ""), description=m.get("description"))
            for m in (outcomes.get("primaryOutcomes") or outcomes.get("primary_outcomes") or [])
        ]
        secondary_endpoints = [
            TrialEndpoint(endpoint_type="secondary", name=m.get("measure", ""), description=m.get("description"))
            for m in (outcomes.get("secondaryOutcomes") or outcomes.get("secondary_outcomes") or [])
        ]

        # Design type from allocation field
        allocation = design.get("designInfo", {}).get("allocation") or raw.get("allocation", "")
        randomized = "RANDOMIZED" in str(allocation).upper() or raw.get("randomized", True)
        blinding_raw = design.get("designInfo", {}).get("maskingInfo", {}).get("masking") or raw.get("blinding", "open_label")
        if "DOUBLE" in str(blinding_raw).upper():
            blinding = "double_blind"
        elif "SINGLE" in str(blinding_raw).upper():
            blinding = "single_blind"
        else:
            blinding = "open_label"
        design_type = "randomized_controlled" if randomized and raw.get("comparator") else "single_arm"

        enrollment_raw = status_mod.get("enrollmentInfo", {})
        enrollment_target = enrollment_raw.get("count") or raw.get("enrollment_target")
        if isinstance(enrollment_target, str):
            try:
                enrollment_target = int(enrollment_target)
            except ValueError:
                enrollment_target = None

        completion_raw = status_mod.get("primaryCompletionDateStruct", {}).get("date") or raw.get("primary_completion_date")
        primary_completion = None
        if completion_raw:
            try:
                primary_completion = date.fromisoformat(str(completion_raw)[:10])
            except ValueError:
                pass

        return TrialDesignRecord(
            nct_id=nct_id,
            asset_id=raw.get("asset_id"),
            phase=phase,
            design_type=raw.get("design_type", design_type),
            blinding=blinding,
            randomized=bool(randomized),
            indication=raw.get("indication") or ident.get("officialTitle"),
            condition=raw.get("condition"),
            intervention=raw.get("intervention"),
            comparator=raw.get("comparator"),
            enrollment_target=enrollment_target,
            enrollment_actual=raw.get("enrollment_actual"),
            endpoints=primary_endpoints + secondary_endpoints or raw.get("endpoints", []),
            biomarker_stratification=eligibility.get("biomarker") or raw.get("biomarker_stratification"),
            geography=raw.get("geography", []),
            dosing_regimen=raw.get("dosing_regimen"),
            primary_completion_date=primary_completion,
            status=raw.get("status", "unknown").lower(),
            sponsor=raw.get("sponsor"),
            statistical_power=raw.get("statistical_power"),
            alpha=raw.get("alpha"),
            source=raw.get("source", "manual"),
        )

    def parse_batch(self, raws: list[dict]) -> list[TrialDesignRecord]:
        return [self.parse(r) for r in raws]
