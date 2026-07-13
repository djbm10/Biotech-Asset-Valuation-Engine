"""Tests for the science claim ledger + shadow modifier (Phase 1 vertical slice).

These pin the invariants the POS Claim-Ledger Build Plan requires of the shadow
path: the evidence hierarchy is a materiality gate, missing evidence keeps openness
high (not false), refutation is first-class, and nothing touches live POS.
"""
from __future__ import annotations

import pytest

from bve.intelligence.claim_ledger import (
    EXPOSURE_WINDOW_FAMILY,
    ClaimType,
    EvidenceTier,
    MatchStatus,
    ObservationBasis,
    ReviewStatus,
    ScienceClaim,
    build_claim_ledger_summary,
    claim_posterior_to_dict,
    compute_claim_posterior,
    make_claim_atom,
)
from bve.intelligence.killer_question import KillerArchetype, KillerQuestion, KillerQuestionSet
from bve.intelligence.shadow_science_modifier import (
    ConsistencyVerdict,
    audit_system_consistency,
    seed_exposure_window_claims,
    shadow_modifier_to_dict,
    shadow_science_modifier,
)


def _strong_atom(claim_type, lr, source_id="RCT-1"):
    """A HIGH-tier, approved, observed, population-matched (material) atom."""
    return make_claim_atom(
        claim_type,
        likelihood_ratio=lr,
        tier=EvidenceTier.HIGH,
        rationale="randomized human exposure-response",
        source_id=source_id,
        review_status=ReviewStatus.APPROVED,
        observed_vs_inferred=ObservationBasis.OBSERVED,
        population_match=MatchStatus.MATCH,
    )


def _weak_atom(claim_type, lr, source_id="slide-1"):
    """A LOW-tier, unreviewed atom — should raise a question but not move POS."""
    return make_claim_atom(
        claim_type,
        likelihood_ratio=lr,
        tier=EvidenceTier.LOW,
        rationale="company slide claims exposure adequate",
        source_id=source_id,
        review_status=ReviewStatus.DRAFT,
    )


# --- Phase 4: posterior engine --------------------------------------------------


def test_missing_evidence_leaves_posterior_at_prior_and_openness_high():
    claim = ScienceClaim(
        claim_type=ClaimType.EXPOSURE_DELIVERY, question="Enough drug at target?", prior=0.5
    )
    post = compute_claim_posterior(claim)
    assert post.posterior == pytest.approx(0.5, abs=1e-3)
    assert post.openness == pytest.approx(1.0, abs=1e-6)
    assert post.n_material_atoms == 0
    assert post.missing_critical_evidence  # flagged, not treated as false


def test_strong_confirming_evidence_moves_posterior_up_and_closes_openness():
    claim = ScienceClaim(
        claim_type=ClaimType.EXPOSURE_DELIVERY,
        question="Enough drug at target?",
        prior=0.5,
        atoms=[_strong_atom(ClaimType.EXPOSURE_DELIVERY, 4.0)],
    )
    post = compute_claim_posterior(claim)
    assert post.posterior > 0.6
    assert post.openness < 1.0
    assert post.n_material_atoms == 1
    assert post.top_positive


def test_refutation_is_first_class_and_lowers_posterior():
    claim = ScienceClaim(
        claim_type=ClaimType.THERAPEUTIC_WINDOW,
        question="Window wide enough?",
        prior=0.5,
        atoms=[_strong_atom(ClaimType.THERAPEUTIC_WINDOW, 0.2)],
    )
    post = compute_claim_posterior(claim)
    assert post.posterior < 0.4
    assert post.top_negative


def test_strong_refutation_not_drowned_by_weak_confirmations():
    # One strong refute + several weak (non-material) confirms => posterior still falls.
    atoms = [_strong_atom(ClaimType.THERAPEUTIC_WINDOW, 0.2)]
    atoms += [_weak_atom(ClaimType.THERAPEUTIC_WINDOW, 5.0, f"slide-{i}") for i in range(5)]
    claim = ScienceClaim(
        claim_type=ClaimType.THERAPEUTIC_WINDOW, question="Window?", prior=0.5, atoms=atoms
    )
    post = compute_claim_posterior(claim)
    assert post.posterior < 0.4
    assert post.n_raised_questions == 5


# --- Phase 3: materiality gate --------------------------------------------------


def test_weak_evidence_raises_question_but_does_not_move_posterior():
    claim = ScienceClaim(
        claim_type=ClaimType.EXPOSURE_DELIVERY,
        question="Enough drug?",
        prior=0.5,
        atoms=[_weak_atom(ClaimType.EXPOSURE_DELIVERY, 9.0)],
    )
    post = compute_claim_posterior(claim)
    assert post.posterior == pytest.approx(0.5, abs=1e-3)  # LOW tier => no movement
    assert post.openness == pytest.approx(1.0, abs=1e-6)
    assert post.n_material_atoms == 0
    assert post.n_raised_questions == 1
    assert post.raised_questions


def test_unreviewed_high_tier_evidence_is_not_material():
    atom = make_claim_atom(
        ClaimType.EXPOSURE_DELIVERY,
        likelihood_ratio=4.0,
        tier=EvidenceTier.HIGH,
        rationale="strong but not yet reviewed",
        source_id="preprint-1",
        review_status=ReviewStatus.DRAFT,  # not approved
        population_match=MatchStatus.MATCH,
    )
    assert atom.provenance.is_material() is False
    claim = ScienceClaim(
        claim_type=ClaimType.EXPOSURE_DELIVERY, question="q", prior=0.5, atoms=[atom]
    )
    assert compute_claim_posterior(claim).posterior == pytest.approx(0.5, abs=1e-3)


def test_inferred_and_population_mismatch_block_materiality():
    inferred = make_claim_atom(
        ClaimType.EXPOSURE_DELIVERY,
        likelihood_ratio=4.0,
        tier=EvidenceTier.HIGH,
        rationale="inferred from analog",
        source_id="analog-1",
        review_status=ReviewStatus.APPROVED,
        observed_vs_inferred=ObservationBasis.INFERRED,
    )
    mismatch = make_claim_atom(
        ClaimType.EXPOSURE_DELIVERY,
        likelihood_ratio=4.0,
        tier=EvidenceTier.HIGH,
        rationale="wrong population",
        source_id="other-pop-1",
        review_status=ReviewStatus.APPROVED,
        population_match=MatchStatus.MISMATCH,
    )
    assert inferred.provenance.is_material() is False
    assert mismatch.provenance.is_material() is False


def test_medium_tier_moves_posterior_less_than_high_tier():
    def post_for(tier):
        atom = make_claim_atom(
            ClaimType.EXPOSURE_DELIVERY,
            likelihood_ratio=4.0,
            tier=tier,
            rationale="r",
            source_id="s",
            review_status=ReviewStatus.APPROVED,
            population_match=MatchStatus.MATCH,
        )
        claim = ScienceClaim(
            claim_type=ClaimType.EXPOSURE_DELIVERY, question="q", prior=0.5, atoms=[atom]
        )
        return compute_claim_posterior(claim).posterior

    assert post_for(EvidenceTier.HIGH) > post_for(EvidenceTier.MEDIUM) > 0.5


def test_conflicting_material_evidence_is_flagged():
    claim = ScienceClaim(
        claim_type=ClaimType.THERAPEUTIC_WINDOW,
        question="q",
        prior=0.5,
        atoms=[
            _strong_atom(ClaimType.THERAPEUTIC_WINDOW, 4.0, "rct-up"),
            _strong_atom(ClaimType.THERAPEUTIC_WINDOW, 0.25, "rct-down"),
        ],
    )
    post = compute_claim_posterior(claim)
    assert post.conflicting_evidence


# --- Shadow modifier + NO LIVE POS GATE ----------------------------------------


def test_shadow_modifier_never_affects_live_pos():
    claim = ScienceClaim(
        claim_type=ClaimType.EXPOSURE_DELIVERY,
        question="q",
        prior=0.5,
        atoms=[_strong_atom(ClaimType.EXPOSURE_DELIVERY, 4.0)],
    )
    shadow = shadow_science_modifier([compute_claim_posterior(claim)])
    assert shadow.affects_live_pos is False
    assert shadow.calibration_status == "shadow_uncalibrated"
    assert 0.70 <= shadow.shadow_modifier <= 1.10


def test_shadow_modifier_inert_without_family_claims():
    shadow = shadow_science_modifier([])
    assert shadow.n_claims == 0
    assert "no_exposure_window_claims" in shadow.warnings


def test_shadow_binding_constraint_is_weakest_claim():
    strong = ScienceClaim(
        claim_type=ClaimType.EXPOSURE_DELIVERY,
        question="q",
        prior=0.5,
        atoms=[_strong_atom(ClaimType.EXPOSURE_DELIVERY, 6.0)],
    )
    weak = ScienceClaim(
        claim_type=ClaimType.THERAPEUTIC_WINDOW,
        question="q",
        prior=0.5,
        atoms=[_strong_atom(ClaimType.THERAPEUTIC_WINDOW, 0.3, "rct-2")],
    )
    posts = [compute_claim_posterior(strong), compute_claim_posterior(weak)]
    shadow = shadow_science_modifier(posts)
    assert shadow.binding_claim == ClaimType.THERAPEUTIC_WINDOW


# --- Source module has no path into live POS -----------------------------------


def test_no_live_pos_import_in_shadow_modules():
    import bve.intelligence.claim_ledger as cl
    import bve.intelligence.shadow_science_modifier as ssm

    for src in (cl.__file__, ssm.__file__):
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
        assert "compute_science_modifier" not in text.replace(
            "compute_science_modifier``", ""
        ).replace("`compute_science_modifier`", ""), src


# --- System 1 <-> System 2 consistency audit -----------------------------------


def test_audit_consistent_when_modifiers_agree():
    claim = ScienceClaim(
        claim_type=ClaimType.EXPOSURE_DELIVERY,
        question="q",
        prior=0.5,
        atoms=[_strong_atom(ClaimType.EXPOSURE_DELIVERY, 1.05)],
    )
    posts = [compute_claim_posterior(claim)]
    shadow = shadow_science_modifier(posts)
    audit = audit_system_consistency(shadow.shadow_modifier, [], shadow, posts)
    assert audit.verdict == ConsistencyVerdict.CONSISTENT
    assert audit.affects_live_pos is False


def test_audit_flags_conflict_when_live_kills_but_shadow_favorable():
    claim = ScienceClaim(
        claim_type=ClaimType.THERAPEUTIC_WINDOW,
        question="q",
        prior=0.5,
        atoms=[_strong_atom(ClaimType.THERAPEUTIC_WINDOW, 6.0)],
    )
    posts = [compute_claim_posterior(claim)]
    shadow = shadow_science_modifier(posts)
    audit = audit_system_consistency(0.65, ["infeasible_exposure"], shadow, posts)
    assert audit.verdict == ConsistencyVerdict.CONFLICT


def test_audit_divergent_when_modifiers_far_apart():
    claim = ScienceClaim(
        claim_type=ClaimType.EXPOSURE_DELIVERY,
        question="q",
        prior=0.5,
        atoms=[_strong_atom(ClaimType.EXPOSURE_DELIVERY, 8.0)],
    )
    posts = [compute_claim_posterior(claim)]
    shadow = shadow_science_modifier(posts)
    audit = audit_system_consistency(0.70, [], shadow, posts)
    assert audit.verdict == ConsistencyVerdict.DIVERGENT
    assert abs(audit.modifier_delta) > 0.10


# --- Openness wiring from killer questions --------------------------------------


def test_seed_claims_carry_killer_question_openness():
    kq_set = KillerQuestionSet(
        decisive=[
            KillerQuestion(
                archetype=KillerArchetype.DELIVERY_EXPOSURE,
                question_text="Can enough drug reach the target tissue?",
                openness=0.8,
            )
        ],
        candidates=[
            KillerQuestion(
                archetype=KillerArchetype.TOLERABILITY_CEILING,
                question_text="Does tox cap the window?",
                openness=0.4,
            ),
            KillerQuestion(
                archetype=KillerArchetype.DIFFERENTIATION,  # outside slice -> skipped
                question_text="Differentiated?",
                openness=1.0,
            ),
        ],
    )
    claims = seed_exposure_window_claims(kq_set)
    assert {c.claim_type for c in claims} == EXPOSURE_WINDOW_FAMILY
    by_type = {c.claim_type: c for c in claims}
    assert by_type[ClaimType.EXPOSURE_DELIVERY].baseline_openness == pytest.approx(0.8)
    assert by_type[ClaimType.THERAPEUTIC_WINDOW].baseline_openness == pytest.approx(0.4)


def test_seed_claims_none_input():
    assert seed_exposure_window_claims(None) == []


def test_seeded_open_claim_stays_open_without_evidence():
    kq_set = KillerQuestionSet(
        decisive=[
            KillerQuestion(
                archetype=KillerArchetype.DELIVERY_EXPOSURE,
                question_text="q",
                openness=0.9,
            )
        ]
    )
    claim = seed_exposure_window_claims(kq_set)[0]
    post = compute_claim_posterior(claim)
    assert post.openness == pytest.approx(0.9, abs=1e-6)  # inherited, no evidence yet


# --- Surfacing ------------------------------------------------------------------


def test_surfacing_dicts_are_json_safe():
    claim = ScienceClaim(
        claim_type=ClaimType.EXPOSURE_DELIVERY,
        question="q",
        prior=0.5,
        atoms=[_strong_atom(ClaimType.EXPOSURE_DELIVERY, 4.0)],
    )
    post = compute_claim_posterior(claim)
    row = claim_posterior_to_dict(post)
    assert row["claim_type"] == "exposure_delivery"
    assert build_claim_ledger_summary([post])
    assert build_claim_ledger_summary([]) is None
    shadow = shadow_science_modifier([post])
    assert shadow_modifier_to_dict(shadow)["affects_live_pos"] is False
