"""Dose-response conviction producer (Batch 2, PR-2).

Replaces the old hardcoded ``+0.10`` dose-adequacy posterior bump with a log-odds
``EvidenceUpdate`` (source DOSE_RESPONSE) through the conviction kernel. Proves:

  * a flagged dose-response trend raises the posterior via a likelihood ratio
    (not a flat +0.10), and emits an auditable ``ConvictionRecord``;
  * flat / no-trend questions are untouched (no update, no record);
  * the raise is directional vs the flat case (old Batch-A behavior preserved);
  * the conviction trail reaches the JSON summary on a normal derive+apply run.

Trigger: ``EvidenceResolutionBasis.HUMAN_DOSE_RESPONSE`` (the ``dose_response_trend``
flag set by the spine). No POS / science-modifier / BD-scoring / route change.
"""
from __future__ import annotations

from bve.intelligence.conviction_update import (
    EvidenceSource,
    UpdateDirection,
    apply_dose_response_conviction,
)
from bve.intelligence.killer_question import KillerArchetype, derive_killer_questions
from bve.intelligence.science_thesis import (
    EvidenceResolution,
    EvidenceResolutionBasis,
    ScienceComponentScore,
    ScienceQuestion,
    ScienceScoredQuestions,
    ScienceThesis,
)
from bve.intelligence.science_thesis_summary import build_science_summary

_RESOLVED = EvidenceResolution.RESOLVED
_UNRESOLVED = EvidenceResolution.UNRESOLVED


def _scored(*, drug_basis):
    return ScienceScoredQuestions(
        right_target=ScienceComponentScore(
            name="T", score=0.7, confidence=0.5, resolution=_RESOLVED,
            resolution_basis=EvidenceResolutionBasis.UNSPECIFIED,
        ),
        enough_drug=ScienceComponentScore(
            name="D", score=0.6, confidence=0.5, resolution=_UNRESOLVED,
            resolution_basis=drug_basis,
        ),
    )


def _set(drug_basis):
    return derive_killer_questions(scored=_scored(drug_basis=drug_basis))


# --------------------------------------------------------------------------
# Producer behavior
# --------------------------------------------------------------------------

def test_trend_raises_posterior_via_lr_and_emits_record() -> None:
    raw = _set(EvidenceResolutionBasis.HUMAN_DOSE_RESPONSE)
    raw_posterior = raw.decisive_question().posterior

    updated, records = apply_dose_response_conviction(raw)
    q = updated.decisive_question()

    assert q.archetype == KillerArchetype.DOSE_ADEQUACY
    assert q.posterior > raw_posterior  # raised
    # ... but NOT the old flat +0.10 (log-odds, so it differs from prior+0.10).
    assert abs(q.posterior - (raw_posterior + 0.10)) > 1e-9

    assert len(records) == 1
    rec = records[0]
    assert rec.prior == raw_posterior
    assert rec.posterior == q.posterior
    assert rec.updates[0].source == EvidenceSource.DOSE_RESPONSE
    assert rec.updates[0].direction == UpdateDirection.CONFIRMING


def test_flat_no_trend_is_untouched() -> None:
    raw = _set(EvidenceResolutionBasis.HUMAN_PKPD)  # in DOSE_ADEQUACY, no trend flag
    raw_posterior = raw.decisive_question().posterior

    updated, records = apply_dose_response_conviction(raw)

    assert records == []
    assert updated.decisive_question().posterior == raw_posterior
    assert updated is raw  # unchanged set returned as-is


def test_trend_raise_is_directional_vs_flat() -> None:
    trend, _ = apply_dose_response_conviction(
        _set(EvidenceResolutionBasis.HUMAN_DOSE_RESPONSE)
    )
    flat, _ = apply_dose_response_conviction(_set(EvidenceResolutionBasis.HUMAN_PKPD))
    assert trend.decisive_question().posterior > flat.decisive_question().posterior


def test_none_set_is_safe() -> None:
    updated, records = apply_dose_response_conviction(None)
    assert updated is None
    assert records == []


# --------------------------------------------------------------------------
# Surfacing on a normal derive + apply run
# --------------------------------------------------------------------------

def test_conviction_trail_reaches_json_summary() -> None:
    updated, records = apply_dose_response_conviction(
        _set(EvidenceResolutionBasis.HUMAN_DOSE_RESPONSE)
    )
    thesis = ScienceThesis(
        asset_id="asset-1",
        binding_science_question=ScienceQuestion.ENOUGH_DRUG,
        core_biological_hypothesis="h",
        killer_question_set=updated,
        conviction_records=records,
    )
    summary = build_science_summary(thesis, modifier_applied=False)
    trail = summary["conviction_trail"]
    assert trail[0]["updates"][0]["source"] == "dose_response"
    assert trail[0]["posterior"] > trail[0]["prior"]
