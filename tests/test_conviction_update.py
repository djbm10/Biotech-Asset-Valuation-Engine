"""Tests for the Conviction Update Layer (Batch 2, PR-1).

Kernel: log-odds composition, refutation is first-class, informativeness gating,
clamping, and a logged human override. Readout interpreter (Idea 7): the four
buckets and — the behavior Harvey most wants proven — near-miss WITH a trend
raises conviction while near-miss WITHOUT a trend lowers it. Plus the ownership
boundary: the layer never changes ``compute_science_modifier``.
"""
from __future__ import annotations

from bve.intelligence.conviction_update import (
    EvidenceSource,
    UpdateDirection,
    interpret_readout,
    update_killer_question_posterior,
)
from bve.intelligence.killer_question import KillerArchetype, KillerQuestion
from bve.intelligence.science_thesis import (
    EvidenceResolution,
    EvidenceResolutionBasis,
    ScienceComponentScore,
    ScienceQuestion,
    compute_science_modifier,
)


def _q(posterior: float = 0.5) -> KillerQuestion:
    return KillerQuestion(
        archetype=KillerArchetype.DIFFERENTIATION,
        question_text="Is the effect above the disease bar?",
        posterior=posterior,
    )


# --------------------------------------------------------------------------
# Kernel
# --------------------------------------------------------------------------

def test_empty_updates_leave_posterior_unchanged() -> None:
    q, record = update_killer_question_posterior(_q(0.4), [])
    assert q.posterior == 0.4
    assert record.prior == 0.4
    assert record.posterior == 0.4


def test_confirming_updates_compound_upward() -> None:
    u = interpret_readout(20.0, bar=20.0)  # clean hit, LR 3.0
    q, record = update_killer_question_posterior(_q(0.5), [u, u])
    assert q.posterior > 0.5
    assert q.posterior < 1.0
    assert all(up.direction == UpdateDirection.CONFIRMING for up in record.updates)


def test_refutation_is_first_class() -> None:
    """A strong refutation pulls the posterior below the prior even after a confirm."""
    confirm = interpret_readout(20.0, bar=20.0)          # LR 3.0
    refute = interpret_readout(5.0, bar=20.0)            # clean miss, LR 0.33
    q_confirm_only, _ = update_killer_question_posterior(_q(0.5), [confirm])
    q, _ = update_killer_question_posterior(_q(0.5), [confirm, refute])
    assert q.posterior < q_confirm_only.posterior
    assert q.posterior < 0.5


def test_zero_informativeness_does_not_move_posterior() -> None:
    u = interpret_readout(20.0, bar=20.0, informativeness=0.0)
    q, _ = update_killer_question_posterior(_q(0.5), [u])
    assert q.posterior == 0.5


def test_extreme_lr_is_clamped_below_one() -> None:
    from bve.intelligence.conviction_update import EvidenceUpdate

    huge = EvidenceUpdate(
        source=EvidenceSource.MANUAL,
        likelihood_ratio=1e9,
        rationale="stress",
        provenance="test",
    )
    q, _ = update_killer_question_posterior(_q(0.5), [huge])
    assert q.posterior < 1.0


def test_human_override_pins_and_is_logged() -> None:
    confirm = interpret_readout(20.0, bar=20.0)
    q, record = update_killer_question_posterior(
        _q(0.5), [confirm], human_override=0.9, override_rationale="SME disagrees"
    )
    assert abs(q.posterior - 0.9) < 1e-6
    assert record.human_override == 0.9
    manual = [u for u in record.updates if u.source == EvidenceSource.MANUAL]
    assert len(manual) == 1
    assert manual[0].rationale == "SME disagrees"


# --------------------------------------------------------------------------
# Idea 7 — readout interpreter buckets + the trend discriminator
# --------------------------------------------------------------------------

def test_clean_hit_raises() -> None:
    u = interpret_readout(21.0, bar=20.0)
    assert u is not None and u.direction == UpdateDirection.CONFIRMING


def test_near_miss_with_trend_raises_but_less_than_clean_hit() -> None:
    hit = interpret_readout(21.0, bar=20.0)
    near = interpret_readout(18.0, bar=20.0, trend_present=True)  # within near band
    assert near.direction == UpdateDirection.CONFIRMING
    assert near.likelihood_ratio < hit.likelihood_ratio


def test_silence_returns_no_update() -> None:
    assert interpret_readout(None, bar=20.0) is None
    assert interpret_readout(18.0, bar=None) is None  # unknown bar => silence


def test_trend_is_the_discriminator() -> None:
    """Near miss + trend -> posterior up; near miss + no trend -> posterior down."""
    with_trend = interpret_readout(18.0, bar=20.0, trend_present=True)
    without_trend = interpret_readout(18.0, bar=20.0, trend_present=False)
    up, _ = update_killer_question_posterior(_q(0.5), [with_trend])
    down, _ = update_killer_question_posterior(_q(0.5), [without_trend])
    assert up.posterior > 0.5
    assert down.posterior < 0.5


def test_bar_resolves_from_indication() -> None:
    # obesity bar = 20 (Batch A); 12 is a clean miss well below the near band.
    u = interpret_readout(12.0, indication="obesity")
    assert u is not None and u.direction == UpdateDirection.REFUTING


# --------------------------------------------------------------------------
# Ownership boundary — POS / science modifier isolation
# --------------------------------------------------------------------------

def test_ownership_boundary_science_modifier_unchanged() -> None:
    components = {
        "T": ScienceComponentScore(name="T", score=0.6, confidence=0.5,
                                   resolution=EvidenceResolution.UNRESOLVED,
                                   resolution_basis=EvidenceResolutionBasis.UNSPECIFIED),
        "D": ScienceComponentScore(name="D", score=0.4, confidence=0.5,
                                   resolution=EvidenceResolution.UNRESOLVED,
                                   resolution_basis=EvidenceResolutionBasis.UNSPECIFIED),
    }
    kwargs = dict(
        phase="phase_2",
        binding_science_question=ScienceQuestion.RIGHT_TARGET,
        components=components,
    )
    before = compute_science_modifier(**kwargs)

    original = _q(0.5)
    update_killer_question_posterior(original, [interpret_readout(21.0, bar=20.0)])

    after = compute_science_modifier(**kwargs)
    assert before.model_dump() == after.model_dump()
    # And the original question is not mutated (immutable copy semantics).
    assert original.posterior == 0.5
