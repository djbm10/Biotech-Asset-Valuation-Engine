"""Compact JSON-safe summaries for Science Thesis and BD Fit audit output."""

from __future__ import annotations

from typing import Any


def _value(value: Any) -> Any:
    """Return enum values as strings while preserving JSON primitives."""
    return getattr(value, "value", value)


def build_science_summary(science_thesis: object | None, *, modifier_applied: bool) -> dict | None:
    """Build a compact JSON-safe Science Thesis summary.

    The full ScienceThesis remains runtime/memo-facing only. This summary keeps
    stable audit facts that appeared in memo/watchlist output.
    """
    if science_thesis is None:
        return None

    modifier_result = getattr(science_thesis, "modifier_result", None)
    return {
        "science_binding_question": _value(
            getattr(science_thesis, "binding_science_question", None)
        ),
        "science_modifier": (
            getattr(modifier_result, "heuristic_science_modifier", None)
            if modifier_result is not None
            else None
        ),
        "science_score": (
            getattr(modifier_result, "science_score", None) if modifier_result is not None else None
        ),
        "science_modifier_applied": bool(modifier_applied),
        "missing_critical_evidence_count": len(
            getattr(science_thesis, "missing_critical_evidence", []) or []
        ),
        "next_readout_requirement": getattr(science_thesis, "next_readout_requirement", None),
        "warnings": list(getattr(modifier_result, "warnings", []) or []),
        "science_scoring_version": getattr(science_thesis, "scoring_version", None),
        "science_weight_set_version": getattr(science_thesis, "weight_set_version", None),
        "science_calibration_status": _value(
            getattr(science_thesis, "calibration_status", None)
        ),
    }


def build_bd_summary(
    bd_actionability: object | None,
    *,
    buyer_problem: object | None = None,
    buyer_problem_id: str | None = None,
) -> dict | None:
    """Build a compact JSON-safe BD actionability summary."""
    if bd_actionability is None:
        return None

    return {
        "bd_route": _value(getattr(bd_actionability, "recommended_bd_route", None)),
        "bd_hard_gate_passed": getattr(bd_actionability, "passed_hard_gates", None),
        "bd_actionability_score": getattr(bd_actionability, "bd_actionability", None),
        "failed_gates": list(getattr(bd_actionability, "failed_gates", []) or []),
        "warnings": list(getattr(bd_actionability, "warnings", []) or []),
        "buyer_problem_id": buyer_problem_id or getattr(buyer_problem, "problem_id", None),
        "buyer_id": getattr(buyer_problem, "buyer_id", None),
    }
