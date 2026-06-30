"""Tests for the Killer-Question engine (Batch A).

Regression anchors per docs/killer_question_build_plan.md §4. Most tests drive
the engine with the science objects directly and ``branch_valuator=None``
(openness-only VOI) so they need no full rNPV plumbing; a stub valuator covers
VOI ordering, and one anchor proves the ownership boundary (POS isolation).
"""
from __future__ import annotations

import pytest

from bve.intelligence.killer_question import (
    KillerArchetype,
    derive_killer_questions,
)
from bve.intelligence.science_thesis import (
    ClinicalMeaningfulnessContext,
    EvidenceResolution,
    EvidenceResolutionBasis,
    ScienceComponentScore,
    ScienceContext,
    ScienceGuardrail,
    ScienceQuestion,
    ScienceScoredQuestions,
    compute_science_modifier,
)


def _comp(
    name: str,
    *,
    score: float = 0.5,
    resolution: EvidenceResolution = EvidenceResolution.UNRESOLVED,
    basis: EvidenceResolutionBasis = EvidenceResolutionBasis.UNSPECIFIED,
    confidence: float = 0.5,
) -> ScienceComponentScore:
    return ScienceComponentScore(
        name=name,
        score=score,
        confidence=confidence,
        resolution=resolution,
        resolution_basis=basis,
    )


_RESOLVED = EvidenceResolution.RESOLVED
_UNRESOLVED = EvidenceResolution.UNRESOLVED


def _scored(*, target=_UNRESOLVED, drug=_RESOLVED, drug_basis=EvidenceResolutionBasis.UNSPECIFIED):
    return ScienceScoredQuestions(
        right_target=_comp("T", resolution=target),
        enough_drug=_comp("D", resolution=drug, basis=drug_basis),
    )


# --------------------------------------------------------------------------
# Target validity
# --------------------------------------------------------------------------

def test_validated_target_not_decisive():
    """PCSK9-like: validated target => TARGET_VALIDITY is never decisive."""
    out = derive_killer_questions(
        scored=_scored(
            target=_UNRESOLVED,
            drug=_UNRESOLVED,
            drug_basis=EvidenceResolutionBasis.PRECLINICAL,
        ),
        target_has_precedent=True,
    )
    archetypes = {q.archetype for q in out.decisive}
    assert KillerArchetype.TARGET_VALIDITY not in archetypes
    assert KillerArchetype.DELIVERY_EXPOSURE in archetypes


def test_novel_first_in_class_target_is_decisive():
    out = derive_killer_questions(
        scored=_scored(target=_UNRESOLVED, drug=_RESOLVED),
        target_has_precedent=False,
    )
    assert not out.abstained
    assert out.decisive_question().archetype == KillerArchetype.TARGET_VALIDITY


# --------------------------------------------------------------------------
# Delivery vs dose
# --------------------------------------------------------------------------

def test_cns_delivery_surfaces():
    out = derive_killer_questions(
        scored=_scored(
            target=_RESOLVED,
            drug=_UNRESOLVED,
            drug_basis=EvidenceResolutionBasis.PRECLINICAL,
        ),
    )
    assert out.decisive_question().archetype == KillerArchetype.DELIVERY_EXPOSURE


def test_dose_response_trend_raises_posterior():
    """A human dose-response trend lifts the ENOUGH_DRUG posterior vs a flat readout."""
    flat = derive_killer_questions(
        scored=_scored(
            target=_RESOLVED,
            drug=_UNRESOLVED,
            drug_basis=EvidenceResolutionBasis.HUMAN_PKPD,
        ),
    )
    trend = derive_killer_questions(
        scored=_scored(
            target=_RESOLVED,
            drug=_UNRESOLVED,
            drug_basis=EvidenceResolutionBasis.HUMAN_DOSE_RESPONSE,
        ),
    )
    assert flat.decisive_question().archetype == KillerArchetype.DOSE_ADEQUACY
    assert trend.decisive_question().archetype == KillerArchetype.DOSE_ADEQUACY
    assert trend.decisive_question().posterior > flat.decisive_question().posterior


# --------------------------------------------------------------------------
# Differentiation vs the clinical-meaningfulness bar
# --------------------------------------------------------------------------

def test_below_bar_differentiation_is_decisive():
    out = derive_killer_questions(
        scored=_scored(target=_RESOLVED, drug=_RESOLVED),
        indication="sickle_cell_disease",  # bar = 15% HbF
        claimed_effect=12.0,
    )
    d = out.decisive_question()
    assert d.archetype == KillerArchetype.DIFFERENTIATION
    assert "below_bar" in d.flags


def test_effect_within_noise_clears_bar_not_live():
    """19.9 vs a 20 bar is noise — DIFFERENTIATION must not surface."""
    out = derive_killer_questions(
        scored=_scored(target=_UNRESOLVED, drug=_RESOLVED),
        indication="obesity",  # bar = 20
        claimed_effect=19.9,
    )
    archetypes = {q.archetype for q in out.candidates}
    assert KillerArchetype.DIFFERENTIATION not in archetypes


def test_differentiation_silent_without_claimed_effect():
    out = derive_killer_questions(
        scored=_scored(target=_RESOLVED, drug=_RESOLVED),
        indication="obesity",
    )
    assert out.abstained  # nothing live


# --------------------------------------------------------------------------
# Abstention, escape hatch, company cross-check
# --------------------------------------------------------------------------

def test_flat_voi_field_abstains():
    """Two equally-open questions => no dominant pick => abstain."""
    out = derive_killer_questions(
        scored=_scored(target=_UNRESOLVED, drug=_RESOLVED),
        novel_question="Will the conjugation chemistry scale under GMP?",
    )
    assert out.abstained
    assert "flat" in out.abstain_reason.lower()


def test_novel_escape_hatch_surfaces():
    out = derive_killer_questions(
        scored=_scored(target=_RESOLVED, drug=_RESOLVED),
        novel_question="Does the degrader achieve sustained degradation vs transient binding?",
    )
    assert out.decisive_question().archetype == KillerArchetype.NOVEL_OR_UNMODELED_RISK


def test_company_focus_mismatch_flagged():
    out = derive_killer_questions(
        scored=_scored(target=_UNRESOLVED, drug=_RESOLVED),
        company_focus=KillerArchetype.DOSE_ADEQUACY,
    )
    assert out.decisive_question().archetype == KillerArchetype.TARGET_VALIDITY
    assert out.company_focus_mismatch is not None
    assert "dose_adequacy" in out.company_focus_mismatch


def test_no_live_questions_abstains():
    out = derive_killer_questions(scored=_scored(target=_RESOLVED, drug=_RESOLVED))
    assert out.abstained
    assert not out.decisive


# --------------------------------------------------------------------------
# VOI ordering with a stub branch valuator
# --------------------------------------------------------------------------

class _StubValuator:
    """Returns canned (confirmed, refuted) rNPV per archetype."""

    def __init__(self, table: dict[KillerArchetype, tuple[float, float]]):
        self._table = table

    def value(self, archetype: KillerArchetype) -> tuple[float, float]:
        return self._table.get(archetype, (0.0, 0.0))


def test_voi_ordering_pinned_by_swing():
    """With equal openness, the larger rNPV swing wins the decisive slot."""
    scored = ScienceScoredQuestions(
        right_target=_comp("T", resolution=_UNRESOLVED),
        enough_drug=_comp("D", resolution=_UNRESOLVED, basis=EvidenceResolutionBasis.PRECLINICAL),
    )
    valuator = _StubValuator(
        {
            KillerArchetype.TARGET_VALIDITY: (1500.0, 100.0),   # swing 1400 (large)
            KillerArchetype.DELIVERY_EXPOSURE: (400.0, 350.0),  # swing 50 (small)
        }
    )
    out = derive_killer_questions(scored=scored, branch_valuator=valuator)
    assert out.decisive_question().archetype == KillerArchetype.TARGET_VALIDITY
    # swing recorded for audit
    assert out.decisive_question().swing_m == pytest.approx(1400.0, abs=1.0)


# --------------------------------------------------------------------------
# Ownership boundary — POS / science modifier isolation
# --------------------------------------------------------------------------

def test_ownership_boundary_science_modifier_unchanged():
    """Running the killer engine must not change compute_science_modifier output."""
    components = {
        "T": _comp("T", score=0.6),
        "D": _comp("D", score=0.4),
        "B": _comp("B", score=0.5),
    }
    kwargs = dict(
        phase="phase_2",
        binding_science_question=ScienceQuestion.RIGHT_TARGET,
        components=components,
    )
    before = compute_science_modifier(**kwargs)

    derive_killer_questions(
        scored=ScienceScoredQuestions(
            right_target=_comp("T", score=0.6, resolution=_UNRESOLVED),
            enough_drug=_comp("D", score=0.4, resolution=_UNRESOLVED,
                              basis=EvidenceResolutionBasis.PRECLINICAL),
        ),
        context=ScienceContext(
            clinical_meaningfulness=ClinicalMeaningfulnessContext(clinically_meaningful_delta=15.0)
        ),
        guardrail=ScienceGuardrail(manageable_safety_concern=True),
        indication="sickle_cell_disease",
        claimed_effect=12.0,
    )

    after = compute_science_modifier(**kwargs)
    assert before.model_dump() == after.model_dump()
