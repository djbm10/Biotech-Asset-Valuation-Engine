from __future__ import annotations

from datetime import date

import pytest

from bve.analysis.killer_question_backtest import (
    SCREENING_BACKTEST_MODE,
    SCREENING_BACKTEST_VOI_MODE,
    ReconstructedScienceSnapshot,
    ReplayEvidenceFact,
    load_ground_truth_labels,
    make_scored_questions_for_archetypes,
    replay_killer_questions_openness_only,
    replay_killer_questions_with_voi,
    run_killer_question_backtest,
    voi_stub_program,
)
from bve.intelligence.killer_question import KillerArchetype, RnpvBranchValuator


def _snapshot(*archetypes: KillerArchetype) -> ReconstructedScienceSnapshot:
    scored, context, guardrail, claimed_effect = make_scored_questions_for_archetypes(
        *archetypes
    )
    return ReconstructedScienceSnapshot(
        program_id="synthetic",
        as_of_date=date(2020, 1, 1),
        scored=scored,
        context=context,
        guardrail=guardrail,
        indication="oncology",
        claimed_effect=claimed_effect,
    )


def test_load_ground_truth_labels_parses_seed_dataset() -> None:
    labels = load_ground_truth_labels()

    assert len(labels) >= 15
    assert any(label.headline_eligible for label in labels)
    assert all(label.label_date >= label.decision_date for label in labels)
    assert all(label.decision_date < label.pivotal_evidence_date for label in labels)


def test_openness_only_replay_returns_screening_backtest_prediction() -> None:
    prediction = replay_killer_questions_openness_only(
        _snapshot(KillerArchetype.TOLERABILITY_CEILING)
    )

    assert prediction.reconstruction_mode == SCREENING_BACKTEST_MODE
    assert prediction.ranked_archetypes[0] == KillerArchetype.TOLERABILITY_CEILING
    assert prediction.decisive_archetypes == (KillerArchetype.TOLERABILITY_CEILING,)
    assert not prediction.abstained


def test_openness_only_replay_is_deterministic() -> None:
    snapshot = _snapshot(
        KillerArchetype.TARGET_VALIDITY,
        KillerArchetype.TOLERABILITY_CEILING,
    )

    first = replay_killer_questions_openness_only(snapshot)
    second = replay_killer_questions_openness_only(snapshot)

    assert first == second


def test_future_evidence_is_rejected_before_picker_runs() -> None:
    scored, context, guardrail, _claimed_effect = make_scored_questions_for_archetypes(
        KillerArchetype.TARGET_VALIDITY
    )
    snapshot = ReconstructedScienceSnapshot(
        program_id="future-leak",
        as_of_date=date(2020, 1, 1),
        scored=scored,
        context=context,
        guardrail=guardrail,
        evidence_facts=(
            ReplayEvidenceFact(
                fact_id="outcome-readout",
                known_at=date(2020, 1, 2),
                summary="post-decision outcome",
            ),
        ),
    )

    with pytest.raises(ValueError, match="post-decision evidence"):
        replay_killer_questions_openness_only(snapshot)


def test_same_day_evidence_is_allowed() -> None:
    scored, context, guardrail, _claimed_effect = make_scored_questions_for_archetypes(
        KillerArchetype.TARGET_VALIDITY
    )
    snapshot = ReconstructedScienceSnapshot(
        program_id="same-day",
        as_of_date=date(2020, 1, 1),
        scored=scored,
        context=context,
        guardrail=guardrail,
        evidence_facts=(
            ReplayEvidenceFact(
                fact_id="same-day-source",
                known_at=date(2020, 1, 1),
                summary="available at decision date",
            ),
        ),
    )

    prediction = replay_killer_questions_openness_only(snapshot)

    assert prediction.ranked_archetypes == (KillerArchetype.TARGET_VALIDITY,)


# --------------------------------------------------------------------------
# Step 1.5 — VOI (rNPV-swing) replay
# --------------------------------------------------------------------------

def test_voi_stub_swings_collapse_nondiff_and_separate_differentiation() -> None:
    """The shared stub gives every next-gate archetype the same swing and a
    distinct (smaller) swing to the pivotal-phase DIFFERENTIATION question.

    This is the mechanism behind VOI reweighting: with one shared economics
    stub the valuator can only separate the pivotal-phase question from the
    next-gate pack, not the next-gate archetypes from each other.
    """
    asset, trials, market = voi_stub_program()
    valuator = RnpvBranchValuator(asset, trials, market)

    def swing(arch: KillerArchetype) -> float:
        c, r = valuator.value(arch)
        return abs(c - r)

    target = swing(KillerArchetype.TARGET_VALIDITY)
    tol = swing(KillerArchetype.TOLERABILITY_CEILING)
    delivery = swing(KillerArchetype.DELIVERY_EXPOSURE)
    diff = swing(KillerArchetype.DIFFERENTIATION)

    assert target == tol == delivery  # same governing (earliest-risk) phase
    assert diff != target             # pivotal phase → distinct swing
    assert diff < target              # pivotal de-risking is worth less here


def test_voi_replay_breaks_target_vs_differentiation_tie_without_abstaining() -> None:
    """Openness-only ties TARGET vs DIFFERENTIATION (both 1.0) and abstains;
    VOI ranks TARGET above DIFFERENTIATION on value and does not abstain."""
    snapshot = _snapshot(
        KillerArchetype.TARGET_VALIDITY,
        KillerArchetype.DIFFERENTIATION,
    )

    openness = replay_killer_questions_openness_only(snapshot)
    assert openness.abstained  # flat openness field → abstain

    voi = replay_killer_questions_with_voi(snapshot)
    assert voi.reconstruction_mode == SCREENING_BACKTEST_VOI_MODE
    assert voi.ranked_archetypes[0] == KillerArchetype.TARGET_VALIDITY
    assert not voi.abstained


def test_voi_replay_enforces_no_lookahead() -> None:
    snapshot = ReconstructedScienceSnapshot(
        program_id="voi-future-leak",
        as_of_date=date(2020, 1, 1),
        scored=make_scored_questions_for_archetypes(
            KillerArchetype.TARGET_VALIDITY
        )[0],
        evidence_facts=(
            ReplayEvidenceFact(fact_id="leak", known_at=date(2020, 1, 2)),
        ),
    )
    with pytest.raises(ValueError, match="post-decision evidence"):
        replay_killer_questions_with_voi(snapshot)


_FIXTURE_HEADER = (
    "program_id,decision_date,outcome,decisive_archetype,label_status,"
    "decisive_confidence,why_this_archetype_decided,label_source,label_date,"
    "pivotal_evidence_event,pivotal_evidence_date,single_question_dominant,"
    "competing_archetypes\n"
)


def _fixture_row(pid: str, decisive: str, competing: str, dominant: str) -> str:
    return (
        f"{pid},2020-01-01,failed,{decisive},clean,high,why,src,2020-06-01,"
        f"evt,2020-12-31,{dominant},{competing}\n"
    )


def test_voi_breaks_target_vs_differentiation_ties_that_openness_abstains(
    tmp_path,
) -> None:
    """Corpus-independent regression anchor for the VOI mechanism.

    Two TARGET-vs-DIFFERENTIATION programs (both dominant=true). Under openness
    the two questions tie (1.0 == 1.0): the ranking still puts TARGET first by
    draft order (so M1 top-1 is an *artifact* hit), but the tie falls inside the
    dominance margin and the picker abstains — wrong on M3. VOI ranks TARGET
    (1.00) above DIFFERENTIATION (0.63), so the same M1 hit is now *earned* and
    the picker no longer abstains (M3 correct). The meaningful delta is M3.
    """
    csv_path = tmp_path / "fixture.csv"
    csv_path.write_text(
        _FIXTURE_HEADER
        + _fixture_row("p_target_1", "TARGET_VALIDITY", "DIFFERENTIATION", "true")
        + _fixture_row("p_target_2", "TARGET_VALIDITY", "DIFFERENTIATION", "true"),
        encoding="utf-8",
    )

    openness = run_killer_question_backtest(csv_path, use_voi=False)
    voi = run_killer_question_backtest(csv_path, use_voi=True)

    assert openness.mode == SCREENING_BACKTEST_MODE
    assert voi.mode == SCREENING_BACKTEST_VOI_MODE

    # M1 identical (TARGET ranked first either way); M3 is where VOI wins.
    assert openness.m1_top1_rate == pytest.approx(1.0)
    assert voi.m1_top1_rate == pytest.approx(1.0)
    assert openness.m3_rate == pytest.approx(0.0)   # abstains on the tie -> wrong
    assert voi.m3_rate == pytest.approx(1.0)         # resolves the tie -> correct


def test_voi_never_ranks_tolerability_top1_openness_ceiling(tmp_path) -> None:
    """Documents the standing blind spot: a non-severe tolerability question
    enters at openness 0.5 and shares the earliest-gate swing, so it can never
    win top-1 against a fully-open competitor. Pinned so a future fix is visible.
    """
    csv_path = tmp_path / "tol.csv"
    csv_path.write_text(
        _FIXTURE_HEADER
        + _fixture_row("p_tol", "TOLERABILITY_CEILING", "TARGET_VALIDITY", "true"),
        encoding="utf-8",
    )
    voi = run_killer_question_backtest(csv_path, use_voi=True)
    assert voi.m1_top1_rate == pytest.approx(0.0)
