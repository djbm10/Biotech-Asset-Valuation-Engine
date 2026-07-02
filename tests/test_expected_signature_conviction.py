"""PR-3 step 4: expected-signature conviction producer (gated on review_status==approved).

Exercises the real approved JAK-STAT entry (pSTAT -> down, proximal target engagement).
Central proofs: observed match raises the posterior via a likelihood ratio (not a flat
add); a contradiction lowers it; missing required data is *untested*, never refutation;
a draft entry can never fire; and the producer never touches anything but the killer
question's own posterior.
"""
from __future__ import annotations

import math

import pytest

from bve.config.expected_signatures import ExpectedSignatures
from bve.intelligence.conviction_update import (
    _LR_SIGNATURE_CONTRADICTION,
    _LR_SIGNATURE_MATCH,
    EvidenceSource,
    UpdateDirection,
    apply_expected_signature_conviction,
)
from bve.intelligence.killer_question import (
    KillerArchetype,
    KillerQuestion,
    KillerQuestionSet,
)

_PRIOR = 0.6  # deliberately not 0.5, to distinguish a log-odds update from a flat add
_JAK = "oral JAK1 inhibitor"

_DRAFT_JAK_LIB = """
schema_version: expected_signatures_v1
entries:
  jak_stat_pathway:
    mechanism_tags: ["jak", "stat"]
    review_status: draft
    expected_changes:
      - biomarker: "pSTAT"
        direction: "down"
        informativeness: "proximal_target_engagement"
        required: true
"""


@pytest.fixture(autouse=True)
def _reset_singleton():
    ExpectedSignatures.reset()
    yield
    ExpectedSignatures.reset()


def _set_with(archetype: KillerArchetype, posterior: float = _PRIOR) -> KillerQuestionSet:
    q = KillerQuestion(
        archetype=archetype,
        question_text="Is the drug engaging its target in humans?",
        posterior=posterior,
    )
    return KillerQuestionSet(candidates=[q], decisive=[q])


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _expected_posterior(prior: float, lr: float, info: float = 1.0) -> float:
    return _sigmoid(math.log(prior / (1.0 - prior)) + info * math.log(lr))


# --------------------------------------------------------------------------- #
# Match -> confirming (via LR, not a flat add)
# --------------------------------------------------------------------------- #

def test_match_raises_posterior_via_lr_and_emits_record():
    kqs = _set_with(KillerArchetype.DELIVERY_EXPOSURE)
    new_set, records = apply_expected_signature_conviction(
        kqs, mechanism_context=_JAK, observed_changes=[{"biomarker": "pSTAT", "direction": "down"}]
    )
    assert len(records) == 1
    rec = records[0]
    assert rec.posterior > _PRIOR
    # It is a proper log-odds update, not prior + 0.10.
    assert rec.posterior == pytest.approx(_expected_posterior(_PRIOR, _LR_SIGNATURE_MATCH))
    assert abs(rec.posterior - (_PRIOR + 0.10)) > 1e-6
    assert rec.updates[0].source is EvidenceSource.EXPECTED_SIGNATURE
    assert rec.updates[0].direction is UpdateDirection.CONFIRMING
    # New set carries the raised posterior; original set is untouched (frozen copy).
    assert new_set.decisive[0].posterior == pytest.approx(rec.posterior)
    assert kqs.decisive[0].posterior == _PRIOR


def test_direction_synonyms_are_normalized():
    kqs = _set_with(KillerArchetype.DELIVERY_EXPOSURE)
    _, records = apply_expected_signature_conviction(
        kqs, mechanism_context=_JAK,
        observed_changes=[{"biomarker": "pSTAT", "direction": "reduction"}],
    )
    assert records and records[0].posterior > _PRIOR


# --------------------------------------------------------------------------- #
# Contradiction -> refuting
# --------------------------------------------------------------------------- #

def test_contradiction_lowers_posterior():
    kqs = _set_with(KillerArchetype.DELIVERY_EXPOSURE)
    _, records = apply_expected_signature_conviction(
        kqs, mechanism_context=_JAK,
        observed_changes=[{"biomarker": "pSTAT", "direction": "up"}],  # opposite of expected
    )
    assert len(records) == 1
    rec = records[0]
    assert rec.posterior < _PRIOR
    assert rec.posterior == pytest.approx(_expected_posterior(_PRIOR, _LR_SIGNATURE_CONTRADICTION))
    assert rec.updates[0].direction is UpdateDirection.REFUTING


# --------------------------------------------------------------------------- #
# Untested / inert paths
# --------------------------------------------------------------------------- #

def test_missing_required_marker_is_untested_not_refuting():
    # Observed data provided, but not the required pSTAT -> untested, posterior unchanged.
    kqs = _set_with(KillerArchetype.DELIVERY_EXPOSURE)
    new_set, records = apply_expected_signature_conviction(
        kqs, mechanism_context=_JAK,
        observed_changes=[{"biomarker": "ALT", "direction": "up"}],
    )
    assert len(records) == 1
    rec = records[0]
    assert rec.posterior == pytest.approx(_PRIOR)  # no move
    assert rec.updates == []
    assert any(f.startswith("signature_untested") for f in rec.untested_flags)


def test_no_observed_evidence_is_inert():
    kqs = _set_with(KillerArchetype.DELIVERY_EXPOSURE)
    new_set, records = apply_expected_signature_conviction(kqs, mechanism_context=_JAK)
    assert records == []
    assert new_set is kqs


def test_unknown_mechanism_and_biomarker_no_match():
    kqs = _set_with(KillerArchetype.DELIVERY_EXPOSURE)
    new_set, records = apply_expected_signature_conviction(
        kqs, mechanism_context="unrelated mechanism",
        observed_changes=[{"biomarker": "made_up_marker", "direction": "down"}],
    )
    assert records == []
    assert new_set is kqs


def test_no_target_engagement_question_means_no_attachment():
    # Signature matches, but the set has no ENOUGH_DRUG-family question to attach to.
    kqs = _set_with(KillerArchetype.TARGET_VALIDITY)
    new_set, records = apply_expected_signature_conviction(
        kqs, mechanism_context=_JAK,
        observed_changes=[{"biomarker": "pSTAT", "direction": "down"}],
    )
    assert records == []
    assert new_set is kqs


# --------------------------------------------------------------------------- #
# The gate: draft entries can never fire
# --------------------------------------------------------------------------- #

def test_draft_entry_never_fires(tmp_path):
    path = tmp_path / "draft.yaml"
    path.write_text(_DRAFT_JAK_LIB)
    draft_lib = ExpectedSignatures(path)
    kqs = _set_with(KillerArchetype.DELIVERY_EXPOSURE)
    new_set, records = apply_expected_signature_conviction(
        kqs, mechanism_context=_JAK,
        observed_changes=[{"biomarker": "pSTAT", "direction": "down"}],
        library=draft_lib,
    )
    assert records == []  # HARD RULE: unapproved signatures cannot move a posterior
    assert new_set is kqs


# --------------------------------------------------------------------------- #
# Ownership: nothing but the killer question's posterior is touched
# --------------------------------------------------------------------------- #

def test_producer_does_not_mutate_input_or_science_scoring():
    from bve.intelligence.science_thesis import (
        ObservedBiomarkerChange,
        ScienceQuestion,
        ScienceThesis,
    )
    from bve.intelligence.science_thesis_summary import build_science_summary

    kqs = _set_with(KillerArchetype.DELIVERY_EXPOSURE)
    new_set, records = apply_expected_signature_conviction(
        kqs, mechanism_context=_JAK,
        observed_changes=[ObservedBiomarkerChange(biomarker="pSTAT", direction="down")],
    )
    # Input set is frozen and unchanged; a new set was returned.
    assert kqs.decisive[0].posterior == _PRIOR
    assert new_set is not kqs

    # The trail surfaces in the JSON science summary, and the science modifier flag
    # the summary reports is independent of the conviction records we attached.
    thesis = ScienceThesis(
        asset_id="asset-1",
        binding_science_question=ScienceQuestion.ENOUGH_DRUG,
        core_biological_hypothesis=_JAK,
        conviction_records=records,
    )
    summary = build_science_summary(thesis, modifier_applied=False)
    trail = summary.get("conviction_trail")
    assert trail and any(
        u["source"] == "expected_signature" for row in trail for u in row["updates"]
    )
