"""
EvidenceGrade — quality and provenance classification for model inputs and outputs.

CALIBRATED
    Coefficient or rate has been empirically fitted against a labelled historical
    dataset with reported calibration metrics (AUC, Brier score, ECE). Outputs
    built entirely on calibrated inputs may carry the CALIBRATED tag.

EVIDENCE_INFORMED
    Value is grounded in published data or regulatory filings but has not been
    formally fitted via regression. Examples: launch analogs sourced from IQVIA
    10-K filings, CT.gov-verified trial parameters, SEC-sourced cash figures.

JUDGMENT
    Expert prior or analyst estimate with no direct empirical anchor. Examples:
    manually set peak-sales assumptions, qualitative pipeline-gap urgency flags.

UNVALIDATED
    Default for all freshly constructed objects. Indicates that no external
    source has been used to cross-check the value. Must be upgraded before
    outputs are shown to external stakeholders.
"""
from __future__ import annotations

from enum import Enum


class EvidenceGrade(str, Enum):
    CALIBRATED = "calibrated"
    EVIDENCE_INFORMED = "evidence_informed"
    JUDGMENT = "judgment"
    UNVALIDATED = "unvalidated"

    def label(self) -> str:
        """Human-readable label for display in memos and dashboards."""
        return {
            "calibrated": "Calibrated",
            "evidence_informed": "Evidence-informed",
            "judgment": "Judgment",
            "unvalidated": "Unvalidated",
        }[self.value]

    def confidence_level(self) -> str:
        """Confidence level string surfaced in outputs."""
        return {
            "calibrated": "high",
            "evidence_informed": "medium",
            "judgment": "low",
            "unvalidated": "low",
        }[self.value]


def round_to_band(value_millions: float, band: int = 25) -> float:
    """Round a USD-millions figure to the nearest band (default 25M).

    Used for rNPV display to avoid false precision.

    >>> round_to_band(137.4)
    125.0
    >>> round_to_band(150.0)
    150.0
    >>> round_to_band(163.0)
    175.0
    """
    return round(value_millions / band) * band


def rnpv_display_range(
    rnpv_millions: float,
    band: int = 25,
) -> tuple[float, float]:
    """Return a (low, high) display range centred on the nearest band.

    The range is ±1 band from the rounded mid-point, communicating that
    reported precision is intentionally limited.

    >>> rnpv_display_range(137.4)
    (100.0, 150.0)
    """
    mid = round_to_band(rnpv_millions, band)
    return mid - band, mid + band
