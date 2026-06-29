"""Tests for dual-source buyer-problem intake (spec Part 2.1)."""

from __future__ import annotations

from typing import Sequence

from bve.intelligence.buyer_problem_inferencer import (
    BuyerProblemDraft,
    BuyerProblemInferencer,
    BuyerProblemProvenance,
    EvidenceRef,
    InferenceResult,
    apply_analyst_correction,
)
from bve.intelligence.science_thesis import BuyerProblem


class _FakeExtractor:
    """Deterministic stand-in for the LLM-over-ingestion extractor."""

    def __init__(self, result: InferenceResult) -> None:
        self._result = result

    def extract(self, buyer_id: str, sources: Sequence[EvidenceRef]) -> InferenceResult:
        return self._result


def _inferred_result() -> InferenceResult:
    return InferenceResult(
        buyer_problem=BuyerProblem(
            buyer_id="vertex",
            required_ta=["oncology"],
            required_targets=["KRAS"],
            required_modalities=["small molecule"],
        ),
        confidence=0.62,
        citations=[EvidenceRef(source_type="sec_edgar", citation="0001-23", as_of_date="2026-05-01")],
        model_name="claude-opus-4-8",
    )


def test_analyst_draft_is_trusted_and_full_confidence() -> None:
    problem = BuyerProblem(buyer_id="vertex", required_ta=["autoimmune"])
    draft = BuyerProblemDraft.from_analyst(problem)

    assert draft.provenance == BuyerProblemProvenance.ANALYST
    assert draft.inference_confidence == 1.0
    assert draft.reviewed is True
    assert draft.is_trusted is True


def test_inferencer_produces_unreviewed_inferred_draft() -> None:
    inferencer = BuyerProblemInferencer(_FakeExtractor(_inferred_result()))

    draft = inferencer.infer("vertex", sources=[EvidenceRef(source_type="press")])

    assert draft.provenance == BuyerProblemProvenance.INFERRED
    assert draft.inference_confidence == 0.62
    assert draft.inferred_by_model == "claude-opus-4-8"
    assert draft.reviewed is False
    assert draft.is_trusted is False
    assert draft.evidence_citations[0].source_type == "sec_edgar"


def test_analyst_correction_records_diff_and_persists_to_sink() -> None:
    inferencer = BuyerProblemInferencer(_FakeExtractor(_inferred_result()))
    draft = inferencer.infer("vertex", sources=[])

    logged: list[list[dict]] = []
    corrected = apply_analyst_correction(
        draft,
        {"required_targets": ["KRAS", "G12C"], "required_ta": ["oncology"]},  # second is unchanged
        sink=logged.append,
    )

    assert corrected.provenance == BuyerProblemProvenance.ANALYST_CORRECTED
    assert corrected.reviewed is True
    assert corrected.is_trusted is True
    # Only the genuinely changed field is recorded.
    assert corrected.corrected_fields == ["required_targets"]
    assert corrected.buyer_problem.required_targets == ["KRAS", "G12C"]
    # Original draft is untouched (immutability).
    assert draft.buyer_problem.required_targets == ["KRAS"]
    # Sink received exactly one correction record with before/after values.
    assert len(logged) == 1
    assert logged[0][0]["field"] == "required_targets"
    assert logged[0][0]["inferred_value"] == ["KRAS"]
    assert logged[0][0]["corrected_value"] == ["KRAS", "G12C"]


def test_correction_with_no_changes_logs_nothing() -> None:
    inferencer = BuyerProblemInferencer(_FakeExtractor(_inferred_result()))
    draft = inferencer.infer("vertex", sources=[])

    logged: list[list[dict]] = []
    corrected = apply_analyst_correction(
        draft,
        {"required_targets": ["KRAS"]},  # identical to inferred value
        sink=logged.append,
    )

    assert corrected.corrected_fields == []
    assert logged == []
    assert corrected.provenance == BuyerProblemProvenance.ANALYST_CORRECTED


def test_correction_rejects_unknown_field() -> None:
    inferencer = BuyerProblemInferencer(_FakeExtractor(_inferred_result()))
    draft = inferencer.infer("vertex", sources=[])

    try:
        apply_analyst_correction(draft, {"not_a_field": 1})
    except ValueError as exc:
        assert "not_a_field" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for unknown field")
