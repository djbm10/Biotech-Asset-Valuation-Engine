"""Outcome taxonomy and retrospective diagnostics for science thesis outputs."""

from __future__ import annotations

from collections import Counter, defaultdict
from enum import Enum

from pydantic import BaseModel, Field


class ScienceOutcomeLabel(str, Enum):
    TARGET_PATHWAY_FAILURE = "target_pathway_failure"
    EXPOSURE_DOSE_FAILURE = "exposure_dose_failure"
    BIOMARKER_TRANSLATION_FAILURE = "biomarker_translation_failure"
    EFFICACY_FAILURE = "efficacy_failure"
    SAFETY_FAILURE = "safety_failure"
    COMMERCIAL_STRATEGIC_FAILURE = "commercial_strategic_failure"
    SUCCESS = "success"
    UNKNOWN = "unknown"


class ScienceOutcomeRecord(BaseModel):
    asset_id: str
    outcome_label: ScienceOutcomeLabel
    science_binding_question: str | None = None
    science_modifier: float | None = Field(default=None, ge=0.0, le=1.1)
    missing_critical_evidence_count: int | None = Field(default=None, ge=0)
    notes: str = ""


class ScienceDiagnosticsReport(BaseModel):
    n_records: int
    n_labeled: int
    outcome_counts: dict[str, int]
    binding_question_by_outcome: dict[str, dict[str, int]]
    average_modifier_by_outcome: dict[str, float | None]
    average_missing_evidence_by_outcome: dict[str, float | None]


def build_science_diagnostics(records: list[ScienceOutcomeRecord]) -> ScienceDiagnosticsReport:
    """Build retrospective diagnostics without changing production weights."""
    outcome_counts = Counter(record.outcome_label.value for record in records)
    by_outcome: dict[str, Counter] = defaultdict(Counter)
    modifiers: dict[str, list[float]] = defaultdict(list)
    gaps: dict[str, list[int]] = defaultdict(list)
    for record in records:
        outcome = record.outcome_label.value
        if record.science_binding_question:
            by_outcome[outcome][record.science_binding_question] += 1
        if record.science_modifier is not None:
            modifiers[outcome].append(record.science_modifier)
        if record.missing_critical_evidence_count is not None:
            gaps[outcome].append(record.missing_critical_evidence_count)
    outcome_keys = sorted(outcome_counts)
    return ScienceDiagnosticsReport(
        n_records=len(records),
        n_labeled=sum(1 for record in records if record.outcome_label != ScienceOutcomeLabel.UNKNOWN),
        outcome_counts=dict(sorted(outcome_counts.items())),
        binding_question_by_outcome={key: dict(by_outcome[key]) for key in outcome_keys},
        average_modifier_by_outcome={key: _avg(modifiers[key]) for key in outcome_keys},
        average_missing_evidence_by_outcome={key: _avg(gaps[key]) for key in outcome_keys},
    )


def _avg(values: list[float] | list[int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)
