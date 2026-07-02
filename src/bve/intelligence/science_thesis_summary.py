"""Compact JSON-safe summaries for Science Thesis and BD Fit audit output."""

from __future__ import annotations

from typing import Any

from bve.config.expected_signatures import describe_signature_availability
from bve.intelligence.conviction_update import build_conviction_summary


def _value(value: Any) -> Any:
    """Return enum values as strings while preserving JSON primitives."""
    return getattr(value, "value", value)


def _expected_signature_status(science_thesis: object) -> list[dict] | None:
    """No-op surfacing of relevant curated signatures for this program.

    Presentation only — every row is ``scored=False``. Deriving the match hints
    from existing thesis text never moves a posterior (see
    ``expected_signatures.describe_signature_availability``).
    """
    context_parts = [
        str(getattr(science_thesis, "modality", "") or ""),
        str(getattr(science_thesis, "core_biological_hypothesis", "") or ""),
    ]
    biomarker_hints = list(getattr(science_thesis, "expected_biomarker_changes", []) or [])
    context_parts.extend(biomarker_hints)
    rows = describe_signature_availability(
        context_text=" ".join(context_parts),
        biomarker_hints=biomarker_hints,
    )
    return rows or None


def _killer_question_summary(question: object) -> dict:
    return {
        "archetype": _value(getattr(question, "archetype", None)),
        "question_text": getattr(question, "question_text", ""),
        "voi_score": getattr(question, "voi_score", None),
        "posterior": getattr(question, "posterior", None),
        "confidence": getattr(question, "confidence", None),
        "openness": getattr(question, "openness", None),
        "value_if_confirmed_m": getattr(question, "value_if_confirmed_m", None),
        "value_if_refuted_m": getattr(question, "value_if_refuted_m", None),
        "swing_m": getattr(question, "swing_m", None),
        "resolving_readout": getattr(question, "resolving_readout", ""),
        "evidence_touched": _value(getattr(question, "evidence_touched", None)),
        "diligence_question": getattr(question, "diligence_question", ""),
        "why_fired": getattr(question, "why_fired", ""),
        "flags": list(getattr(question, "flags", []) or []),
    }


def build_killer_question_summary(killer_question_set: object | None) -> dict | None:
    """Build compact JSON-safe KillerQuestionSet summary."""
    if killer_question_set is None:
        return None
    return {
        "abstained": bool(getattr(killer_question_set, "abstained", False)),
        "abstain_reason": getattr(killer_question_set, "abstain_reason", ""),
        "company_focus_mismatch": getattr(killer_question_set, "company_focus_mismatch", None),
        "decisive": [
            _killer_question_summary(question)
            for question in (getattr(killer_question_set, "decisive", []) or [])
        ],
        "candidates": [
            _killer_question_summary(question)
            for question in (getattr(killer_question_set, "candidates", []) or [])
        ],
    }


def build_science_summary(science_thesis: object | None, *, modifier_applied: bool) -> dict | None:
    """Build a compact JSON-safe Science Thesis summary.

    The full ScienceThesis remains runtime/memo-facing only. This summary keeps
    stable audit facts that appeared in memo/watchlist output.
    """
    if science_thesis is None:
        return None

    modifier_result = getattr(science_thesis, "modifier_result", None)
    killer_question_summary = build_killer_question_summary(
        getattr(science_thesis, "killer_question_set", None)
    )
    summary = {
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
    if killer_question_summary is not None:
        summary["killer_question_set"] = killer_question_summary
    conviction_summary = build_conviction_summary(
        getattr(science_thesis, "conviction_records", None)
    )
    if conviction_summary is not None:
        summary["conviction_trail"] = conviction_summary
    signature_status = _expected_signature_status(science_thesis)
    if signature_status is not None:
        summary["expected_signature_status"] = signature_status
    return summary


def build_bd_summary(
    bd_actionability: object | None,
    *,
    buyer_problem: object | None = None,
    buyer_problem_id: str | None = None,
) -> dict | None:
    """Build a compact JSON-safe BD actionability summary."""
    if bd_actionability is None:
        return None

    killer_question_summary = build_killer_question_summary(
        getattr(bd_actionability, "killer_question_set", None)
    )
    summary = {
        "bd_route": _value(getattr(bd_actionability, "recommended_bd_route", None)),
        "bd_hard_gate_passed": getattr(bd_actionability, "passed_hard_gates", None),
        "bd_actionability_score": getattr(bd_actionability, "bd_actionability", None),
        "failed_gates": list(getattr(bd_actionability, "failed_gates", []) or []),
        "diligence_questions": list(getattr(bd_actionability, "diligence_questions", []) or []),
        "warnings": list(getattr(bd_actionability, "warnings", []) or []),
        "buyer_problem_id": buyer_problem_id or getattr(buyer_problem, "problem_id", None),
        "buyer_id": getattr(buyer_problem, "buyer_id", None),
    }
    if killer_question_summary is not None:
        summary["killer_question_set"] = killer_question_summary
    conviction_summary = build_conviction_summary(
        getattr(bd_actionability, "conviction_records", None)
    )
    if conviction_summary is not None:
        summary["conviction_trail"] = conviction_summary
    return summary
