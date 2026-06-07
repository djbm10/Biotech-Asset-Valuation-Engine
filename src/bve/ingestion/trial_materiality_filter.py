"""
Trial discontinuation materiality filter.

Fixes the dangerous default where any regex match on "trial terminated /
discontinued" emits the full lead-asset negative delta regardless of:
  - whether the trial is company-sponsored or investigator-initiated
  - whether it affects the lead asset or a non-core program
  - how old the event is
  - how large the trial was

Usage
-----
    from bve.ingestion.trial_materiality_filter import TrialDiscontinuationFilter

    filtered_record = TrialDiscontinuationFilter.apply(record, context)

The filter returns a new EvidenceRecord (immutable; original is unchanged) with:
  - evidence_state set and schema_version = "evidence_state_v1"
  - score_deltas scaled by the materiality tier
  - signal_state = present_negative (confirmed) or present_neutral (ambiguous)

Context hints
-------------
Pass a dict with any of these keys:

    is_company_sponsored : bool
        True if the trial sponsor is the company itself (not investigator-initiated).
        Default: False (conservative — assume non-sponsored if unknown).

    is_lead_asset : bool
        True if the discontinued trial is for the company's primary program.
        Default: False.

    enrollment_count : int | None
        Number of patients enrolled. None = unknown.
        Threshold for "meaningful": >= 50 patients.

    event_age_days : int
        Age of the event in days. > 730 days (2 years) = stale.
        Default: 0 (current).

    is_core_indication : bool
        True if this is the company's primary indication for the asset.
        Default: False.

    source_confirmed : bool
        True if classification comes from a primary source (ClinicalTrials.gov
        status change or company press release), not a news article regex.
        Default: False.

Materiality tiers
-----------------
THESIS_CHANGING — lead asset + company-sponsored + current + meaningful enrollment
    score_deltas: {"asset_quality": -0.20, "seller_willingness": +0.10}

MATERIAL — company-sponsored + current, but not lead asset
    score_deltas: {"asset_quality": -0.10, "seller_willingness": +0.05}

MINOR — company-sponsored + stale, OR non-core + current
    score_deltas: {"asset_quality": -0.05, "seller_willingness": +0.02}

IMMATERIAL — investigator-sponsored, old, tiny, or ambiguous
    score_deltas: {}  (record kept for audit; no score impact)
"""
from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, Optional

from bve.ingestion.evidence_state import (
    AppliesTo,
    ClassificationConfidence,
    EvidenceState,
    LOW_QUALITY_SCALE,
    MaterialityTier,
    Recency,
    SignalState,
    SourceQuality,
)

if TYPE_CHECKING:
    from bve.ingestion.evidence_ledger import EvidenceRecord

_SCHEMA_VERSION = "evidence_state_v1"

# Base score_deltas keyed by materiality tier
_BASE_DELTAS: dict[MaterialityTier, dict[str, float]] = {
    MaterialityTier.THESIS_CHANGING: {"asset_quality": -0.20, "seller_willingness": +0.10},
    MaterialityTier.MATERIAL:        {"asset_quality": -0.10, "seller_willingness": +0.05},
    MaterialityTier.MINOR:           {"asset_quality": -0.05, "seller_willingness": +0.02},
    MaterialityTier.IMMATERIAL:      {},
}

_MEANINGFUL_ENROLLMENT_THRESHOLD = 50
_STALE_AGE_DAYS = 730  # 24 months


def _classify_materiality(ctx: dict[str, Any]) -> MaterialityTier:
    """Determine materiality tier from context hints."""
    is_company_sponsored = bool(ctx.get("is_company_sponsored", False))
    is_lead_asset        = bool(ctx.get("is_lead_asset", False))
    is_core_indication   = bool(ctx.get("is_core_indication", False))
    event_age_days       = int(ctx.get("event_age_days", 0))
    enrollment_count     = ctx.get("enrollment_count")

    is_stale = event_age_days > _STALE_AGE_DAYS
    enrollment_meaningful = (
        enrollment_count is not None and enrollment_count >= _MEANINGFUL_ENROLLMENT_THRESHOLD
    )

    # Not company-sponsored → at most MINOR regardless of anything else
    if not is_company_sponsored:
        return MaterialityTier.IMMATERIAL

    # Company-sponsored + stale → MINOR at best
    if is_stale:
        return MaterialityTier.MINOR

    # Company-sponsored + current
    if is_lead_asset and (is_core_indication or enrollment_meaningful):
        return MaterialityTier.THESIS_CHANGING

    if is_lead_asset or is_core_indication:
        return MaterialityTier.MATERIAL

    # Company-sponsored + current + non-core non-lead
    return MaterialityTier.MINOR


def _classify_applies_to(ctx: dict[str, Any]) -> AppliesTo:
    if ctx.get("is_lead_asset"):
        return AppliesTo.LEAD_ASSET
    if ctx.get("is_core_indication"):
        return AppliesTo.PIPELINE_ASSET
    if ctx.get("is_company_sponsored"):
        return AppliesTo.PIPELINE_ASSET
    return AppliesTo.NON_CORE


def _classify_source_quality(source_type: str, source_confirmed: bool) -> SourceQuality:
    if source_confirmed or source_type in ("clinicaltrials_gov", "sec_filing", "fda_website"):
        return SourceQuality.HIGH
    if source_type in ("press_release", "pubmed", "manual"):
        return SourceQuality.MEDIUM
    return SourceQuality.LOW


def _classify_confidence(ctx: dict[str, Any], source_quality: SourceQuality) -> ClassificationConfidence:
    """Classification confidence reflects how certain we are this is a real discontinuation."""
    source_confirmed = bool(ctx.get("source_confirmed", False))
    if source_confirmed and source_quality == SourceQuality.HIGH:
        return ClassificationConfidence.HIGH
    if source_quality == SourceQuality.LOW:
        return ClassificationConfidence.LOW
    return ClassificationConfidence.MEDIUM


class TrialDiscontinuationFilter:
    """
    Apply materiality-aware scoring to a trial_discontinuation EvidenceRecord.

    Returns a new record — never mutates the input.
    """

    @staticmethod
    def apply(
        record: "EvidenceRecord",
        context: Optional[dict[str, Any]] = None,
    ) -> "EvidenceRecord":
        """
        Classify the trial discontinuation and return a corrected record.

        Parameters
        ----------
        record:
            Original EvidenceRecord with event_type="trial_discontinuation".
        context:
            Dict of context hints (see module docstring). All keys optional.

        Returns
        -------
        New EvidenceRecord with:
          - evidence_state set
          - schema_version = "evidence_state_v1"
          - score_deltas scaled to the materiality tier
        """
        ctx = context or {}
        event_age_days = int(ctx.get("event_age_days", 0))
        source_confirmed = bool(ctx.get("source_confirmed", False))

        materiality   = _classify_materiality(ctx)
        applies_to    = _classify_applies_to(ctx)
        recency       = Recency.STALE if event_age_days > _STALE_AGE_DAYS else Recency.CURRENT
        source_qual   = _classify_source_quality(record.source_type, source_confirmed)
        confidence    = _classify_confidence(ctx, source_qual)

        # Signal state: confirmed negative if company-sponsored and source is good,
        # otherwise neutral (ambiguous classification)
        if (
            ctx.get("is_company_sponsored")
            and source_qual in (SourceQuality.HIGH, SourceQuality.MEDIUM)
        ):
            signal_state = SignalState.PRESENT_NEGATIVE
        else:
            signal_state = SignalState.PRESENT_NEUTRAL

        evidence_state = EvidenceState(
            signal_state=signal_state,
            materiality=materiality,
            source_quality=source_qual,
            recency=recency,
            applies_to=applies_to,
            classification_confidence=confidence,
        )

        new_deltas = dict(_BASE_DELTAS[materiality])

        # _BASE_DELTAS already encodes the tier-appropriate magnitude.
        # Only further downweight when detection quality is poor (source or confidence is LOW).
        # Do NOT re-apply the materiality tier scale — that is already baked into _BASE_DELTAS.
        if (
            evidence_state.source_quality == SourceQuality.LOW
            or evidence_state.classification_confidence == ClassificationConfidence.LOW
        ):
            new_deltas = {k: round(v * LOW_QUALITY_SCALE, 4) for k, v in new_deltas.items()}

        return dataclasses.replace(
            record,
            score_deltas=new_deltas,
            evidence_state=evidence_state.to_dict(),
            schema_version=_SCHEMA_VERSION,
        )

    @staticmethod
    def is_applicable(record: "EvidenceRecord") -> bool:
        """Return True if this filter applies to the record."""
        return record.event_type == "trial_discontinuation"
