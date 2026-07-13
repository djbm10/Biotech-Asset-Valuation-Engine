"""Tests for the killer-question backtest scorer (P3).

These tests anchor the scoring math and report structure — not specific metric
values, which depend on the label corpus and will evolve as N grows.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from bve.analysis.killer_question_backtest import (
    DEFAULT_KILLER_QUESTION_GROUND_TRUTH_CSV,
    MIN_N_FOR_CALIBRATION,
    KillerQuestionBacktestReport,
    KillerQuestionGroundTruthLabel,
    KillerQuestionReplayPrediction,
    ProgramScore,
    ReconstructedScienceSnapshot,
    SCREENING_BACKTEST_MODE,
    _snapshot_from_label,
    assert_no_lookahead,
    load_ground_truth_labels,
    make_scored_questions_for_archetypes,
    replay_killer_questions_openness_only,
    run_killer_question_backtest,
    score_program,
)
from bve.intelligence.killer_question import KillerArchetype


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_label(
    program_id: str = "test_drug",
    decisive_archetype: KillerArchetype = KillerArchetype.TARGET_VALIDITY,
    label_status: str = "clean",
    single_question_dominant: bool = True,
    decision_date: date = date(2020, 1, 1),
    pivotal_evidence_date: date = date(2020, 6, 1),
) -> KillerQuestionGroundTruthLabel:
    return KillerQuestionGroundTruthLabel(
        program_id=program_id,
        decision_date=decision_date,
        outcome="failed",
        decisive_archetype=decisive_archetype,
        label_status=label_status,  # type: ignore[arg-type]
        decisive_confidence="high",
        why_this_archetype_decided="Test rationale.",
        label_source="Test source",
        label_date=date(2026, 1, 1),
        pivotal_evidence_event="Test event",
        pivotal_evidence_date=pivotal_evidence_date,
        single_question_dominant=single_question_dominant,
    )


def _make_prediction(
    ranked_archetypes: tuple[KillerArchetype, ...] = (KillerArchetype.TARGET_VALIDITY,),
    decisive_archetypes: tuple[KillerArchetype, ...] = (KillerArchetype.TARGET_VALIDITY,),
    abstained: bool = False,
) -> KillerQuestionReplayPrediction:
    return KillerQuestionReplayPrediction(
        program_id="test_drug",
        as_of_date=date(2020, 1, 1),
        reconstruction_mode=SCREENING_BACKTEST_MODE,
        ranked_archetypes=ranked_archetypes,
        decisive_archetypes=decisive_archetypes,
        abstained=abstained,
        abstain_reason="",
    )


# ---------------------------------------------------------------------------
# ProgramScore: M1 gating
# ---------------------------------------------------------------------------

def test_m1_top1_hit_true_when_clean_and_correct() -> None:
    label = _make_label(decisive_archetype=KillerArchetype.TARGET_VALIDITY, label_status="clean")
    pred = _make_prediction(ranked_archetypes=(KillerArchetype.TARGET_VALIDITY,))
    ps = score_program(label, pred)
    assert ps.m1_top1_hit is True


def test_m1_top1_miss_when_clean_and_wrong() -> None:
    label = _make_label(decisive_archetype=KillerArchetype.TARGET_VALIDITY, label_status="clean")
    pred = _make_prediction(ranked_archetypes=(KillerArchetype.DOSE_ADEQUACY,))
    ps = score_program(label, pred)
    assert ps.m1_top1_hit is False


def test_m1_top1_none_for_subjective_rows() -> None:
    label = _make_label(label_status="subjective")
    pred = _make_prediction()
    ps = score_program(label, pred)
    assert ps.m1_top1_hit is None
    assert ps.m1_top2_hit is None


def test_m1_top1_none_for_excluded_rows() -> None:
    label = _make_label(label_status="excluded")
    pred = _make_prediction()
    ps = score_program(label, pred)
    assert ps.m1_top1_hit is None


def test_m1_top2_hit_when_label_in_second_position() -> None:
    label = _make_label(decisive_archetype=KillerArchetype.TARGET_VALIDITY, label_status="clean")
    pred = _make_prediction(
        ranked_archetypes=(KillerArchetype.DOSE_ADEQUACY, KillerArchetype.TARGET_VALIDITY)
    )
    ps = score_program(label, pred)
    assert ps.m1_top1_hit is False   # not top-1
    assert ps.m1_top2_hit is True    # but visible in top-2


def test_m1_top2_miss_when_label_absent() -> None:
    label = _make_label(decisive_archetype=KillerArchetype.TARGET_VALIDITY, label_status="clean")
    pred = _make_prediction(
        ranked_archetypes=(KillerArchetype.DOSE_ADEQUACY, KillerArchetype.DIFFERENTIATION)
    )
    ps = score_program(label, pred)
    assert ps.m1_top2_hit is False


# ---------------------------------------------------------------------------
# ProgramScore: M3
# ---------------------------------------------------------------------------

def test_m3_correct_when_dominant_and_not_abstained() -> None:
    label = _make_label(label_status="clean", single_question_dominant=True)
    pred = _make_prediction(abstained=False)
    ps = score_program(label, pred)
    assert ps.m3_correct is True


def test_m3_correct_when_not_dominant_and_abstained() -> None:
    label = _make_label(label_status="clean", single_question_dominant=False)
    pred = _make_prediction(abstained=True)
    ps = score_program(label, pred)
    assert ps.m3_correct is True


def test_m3_wrong_when_dominant_but_abstained() -> None:
    label = _make_label(label_status="clean", single_question_dominant=True)
    pred = _make_prediction(abstained=True)
    ps = score_program(label, pred)
    assert ps.m3_correct is False


def test_m3_none_for_subjective() -> None:
    label = _make_label(label_status="subjective")
    pred = _make_prediction()
    ps = score_program(label, pred)
    assert ps.m3_correct is None


# ---------------------------------------------------------------------------
# KillerQuestionBacktestReport aggregation
# ---------------------------------------------------------------------------

def test_report_counts_clean_rows_only_in_m1_n() -> None:
    report = KillerQuestionBacktestReport()
    report.program_scores.append(
        score_program(
            _make_label(label_status="clean"),
            _make_prediction(ranked_archetypes=(KillerArchetype.TARGET_VALIDITY,)),
        )
    )
    report.program_scores.append(
        score_program(_make_label(label_status="subjective"), _make_prediction())
    )
    report.program_scores.append(
        score_program(_make_label(label_status="excluded"), _make_prediction())
    )
    assert report.m1_n == 1
    assert report.n_subjective == 1
    assert report.n_excluded == 1


def test_report_insufficient_n_flag_below_threshold() -> None:
    report = KillerQuestionBacktestReport()
    for _ in range(MIN_N_FOR_CALIBRATION - 1):
        report.program_scores.append(
            score_program(
                _make_label(label_status="clean"),
                _make_prediction(ranked_archetypes=(KillerArchetype.TARGET_VALIDITY,)),
            )
        )
    assert report.m1_insufficient_n is True


def test_report_not_insufficient_at_threshold() -> None:
    report = KillerQuestionBacktestReport()
    for _ in range(MIN_N_FOR_CALIBRATION):
        report.program_scores.append(
            score_program(
                _make_label(label_status="clean"),
                _make_prediction(ranked_archetypes=(KillerArchetype.TARGET_VALIDITY,)),
            )
        )
    assert report.m1_insufficient_n is False


def test_report_top1_rate_is_fraction_of_hits() -> None:
    report = KillerQuestionBacktestReport()
    hit_label = _make_label(decisive_archetype=KillerArchetype.TARGET_VALIDITY, label_status="clean")
    miss_label = _make_label(decisive_archetype=KillerArchetype.DOSE_ADEQUACY, label_status="clean")
    hit_pred = _make_prediction(ranked_archetypes=(KillerArchetype.TARGET_VALIDITY,))
    miss_pred = _make_prediction(ranked_archetypes=(KillerArchetype.TARGET_VALIDITY,))
    report.program_scores.append(score_program(hit_label, hit_pred))
    report.program_scores.append(score_program(miss_label, miss_pred))
    assert report.m1_top1_rate == pytest.approx(0.5)


def test_summary_lines_include_mode_stamp() -> None:
    report = KillerQuestionBacktestReport()
    lines = "\n".join(report.summary_lines())
    assert SCREENING_BACKTEST_MODE in lines
    assert "do not overclaim" in lines


def test_summary_lines_include_insufficient_n_warning() -> None:
    report = KillerQuestionBacktestReport()
    lines = "\n".join(report.summary_lines())
    assert "INSUFFICIENT N" in lines


# ---------------------------------------------------------------------------
# Snapshot builder + no-lookahead guard
# ---------------------------------------------------------------------------

def test_snapshot_from_label_has_correct_as_of_date() -> None:
    label = _make_label(
        decisive_archetype=KillerArchetype.DOSE_ADEQUACY,
        decision_date=date(2019, 3, 15),
    )
    snapshot = _snapshot_from_label(label)
    assert snapshot.as_of_date == date(2019, 3, 15)


def test_no_lookahead_assert_passes_clean_snapshot() -> None:
    label = _make_label(decision_date=date(2020, 1, 1))
    snapshot = _snapshot_from_label(label)
    assert_no_lookahead(snapshot)  # must not raise


def test_no_lookahead_assert_raises_on_future_fact() -> None:
    from bve.analysis.killer_question_backtest import ReplayEvidenceFact

    label = _make_label(decision_date=date(2020, 1, 1))
    snapshot = _snapshot_from_label(label)
    future_fact = ReplayEvidenceFact(
        fact_id="future_readout", known_at=date(2021, 6, 1), summary="post-decision"
    )
    dirty_snapshot = ReconstructedScienceSnapshot(
        program_id=snapshot.program_id,
        as_of_date=snapshot.as_of_date,
        scored=snapshot.scored,
        context=snapshot.context,
        guardrail=snapshot.guardrail,
        evidence_facts=(future_fact,),
    )
    with pytest.raises(ValueError, match="future_readout"):
        assert_no_lookahead(dirty_snapshot)


# ---------------------------------------------------------------------------
# End-to-end: run against the real label file
# ---------------------------------------------------------------------------

def test_run_killer_question_backtest_produces_report() -> None:
    report = run_killer_question_backtest(DEFAULT_KILLER_QUESTION_GROUND_TRUTH_CSV)
    assert len(report.program_scores) > 0
    assert report.mode == SCREENING_BACKTEST_MODE


def test_end_to_end_report_has_clean_rows_in_m1() -> None:
    report = run_killer_question_backtest(DEFAULT_KILLER_QUESTION_GROUND_TRUTH_CSV)
    assert report.m1_n >= 15  # plan requires ≥15 clean seed rows


def test_end_to_end_summary_renders_without_error() -> None:
    report = run_killer_question_backtest(DEFAULT_KILLER_QUESTION_GROUND_TRUTH_CSV)
    lines = report.summary_lines()
    assert any("Top-1 hit rate" in line for line in lines)
    assert any("M2" in line for line in lines)
