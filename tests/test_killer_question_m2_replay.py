from __future__ import annotations

from datetime import date

import pytest

from bve.analysis.killer_question_m2_replay import (
    M2Input,
    load_m2_inputs,
    replay_m2,
    run_m2_replay,
)
from bve.intelligence.killer_question import KillerArchetype


def _input(
    *,
    program_id: str = "p",
    mechanism_context: str = "imatinib bcr-abl kinase inhibitor cml",
    changes: tuple[dict[str, str], ...] = ({"biomarker": "pCRKL", "direction": "down"},),
    prior: float = 0.5,
    outcome: str = "success",
    evidence_date: date = date(2000, 1, 1),
    pivotal_date: date = date(2001, 1, 1),
) -> M2Input:
    return M2Input(
        program_id=program_id,
        mechanism_context=mechanism_context,
        open_archetype=KillerArchetype.DELIVERY_EXPOSURE,
        observed_biomarker_changes=changes,
        prior=prior,
        outcome=outcome,  # type: ignore[arg-type]
        evidence_date=evidence_date,
        pivotal_date=pivotal_date,
    )


# --------------------------------------------------------------------------
# Seed dataset
# --------------------------------------------------------------------------

def test_seed_inputs_load_and_discriminate() -> None:
    """Seed set = 4 canonical confirming-successes + 3 hand-picked
    confirming-but-wrong failures (target engaged yet drug failed). The harness
    must fire on all of them and score the failures WRONG, so the curated rate is
    below 1.0 — proving the metric discriminates, not just rewards agreement."""
    report = run_m2_replay()
    assert report.n_total >= 7
    assert report.n_silent == 0
    # All seeds are confirming-direction; the 3 failure cases are the wrong calls.
    assert all(p.direction == "confirming" for p in report.predictions)
    scored = [p for p in report.predictions if p.scored]
    correct = sum(1 for p in scored if p.correct)
    assert correct == 4  # the four successes
    assert len(scored) - correct == 3  # the three confirming-but-wrong failures
    assert report.direction_accuracy == pytest.approx(4 / 7, abs=0.02)


def test_seed_inputs_respect_no_lookahead() -> None:
    for item in load_m2_inputs():
        assert item.evidence_date < item.pivotal_date


# --------------------------------------------------------------------------
# Scorer discriminates both directions (uses the real approved BCR-ABL entry)
# --------------------------------------------------------------------------

def test_contradiction_with_failure_scores_correct() -> None:
    """Biomarker moved opposite (pCRKL up) and the drug failed -> refuting is the
    right call, so M2 counts it correct. Proves the scorer isn't just rewarding
    'confirming'."""
    pred = replay_m2(
        _input(changes=({"biomarker": "pCRKL", "direction": "up"},), outcome="failure")
    )
    assert pred.direction == "refuting"
    assert pred.correct is True


def test_confirming_but_failure_scores_wrong() -> None:
    """Target engaged (pCRKL down) yet the drug failed -> confirming was the wrong
    direction, so M2 must count it wrong. Proves the metric can fail."""
    pred = replay_m2(_input(changes=({"biomarker": "pCRKL", "direction": "down"},), outcome="failure"))
    assert pred.direction == "confirming"
    assert pred.correct is False


def test_unmatched_evidence_is_silent_and_excluded() -> None:
    """No approved signature is relevant (unrelated mechanism AND an unrelated
    biomarker) -> producer inert -> excluded from the rate (not counted wrong).

    NB the producer matches on biomarker OR mechanism, so silence requires both to
    miss — an observed pCRKL alone would match the BCR-ABL signature by biomarker."""
    pred = replay_m2(
        _input(
            mechanism_context="some unrelated mechanism",
            changes=({"biomarker": "ALT", "direction": "up"},),
        )
    )
    assert pred.direction == "silent"
    assert pred.scored is False
    assert pred.correct is None


def test_lookahead_input_is_rejected() -> None:
    bad = _input(evidence_date=date(2001, 1, 1), pivotal_date=date(2001, 1, 1))
    with pytest.raises(ValueError, match="lookahead"):
        replay_m2(bad)


def test_silent_cases_excluded_from_accuracy() -> None:
    from bve.analysis.killer_question_m2_replay import M2Report

    report = M2Report(
        predictions=[
            replay_m2(_input(outcome="success")),  # confirming/correct
            replay_m2(  # silent: unrelated mechanism AND unrelated biomarker
                _input(
                    mechanism_context="unrelated",
                    changes=({"biomarker": "ALT", "direction": "up"},),
                )
            ),
        ]
    )
    assert report.n_total == 2
    assert report.n_scored == 1
    assert report.direction_accuracy == pytest.approx(1.0)
