"""One sentence, one asset, an explicit target: ``asset_sentence_target_v1.md``."""

from __future__ import annotations

from datetime import date

import pytest

from bve.se.evidence.construct_targets import attributed_targets_in
from bve.se.evidence.sentence_targets import (
    EXTRACTION_METHOD,
    SentenceTarget,
    asset_sentence_target_evidence,
    name_keys,
    sentence_targets,
)

CD19 = "TARGET:CD19"
BCMA = "TARGET:TNFRSF17"


@pytest.fixture(autouse=True)
def _ontology(se_ontology_snapshot):
    return se_ontology_snapshot


def _read(text: str, name: str = "ALLO-715", others=("lenalidomide", "tisagenlecleucel")):
    return sentence_targets(
        text,
        asset_names=[name],
        other_asset_names=name_keys([name, *others]),
        document_id="doc:1",
    )


def test_an_explicit_target_beside_the_named_asset_is_admitted() -> None:
    [admitted] = _read("ALLO-715, a BCMA-directed allogeneic CAR T, was well tolerated.")
    assert admitted.targets == (BCMA,)


def test_a_dual_construct_keeps_both_arms() -> None:
    [admitted] = _read("ALLO-715 is an anti-CD19/BCMA CAR T cell product.")
    assert admitted.targets == (CD19, BCMA)


def test_a_sentence_not_naming_the_asset_is_ignored() -> None:
    assert _read("BCMA-directed CAR T cells induce deep responses.") == []


def test_a_name_inside_a_longer_word_is_not_the_asset() -> None:
    assert _read("XALLO-715Y, a BCMA-directed CAR T.") == []


def test_a_second_asset_in_the_sentence_leaves_it_unknown() -> None:
    assert _read("ALLO-715, a BCMA-directed CAR T, was given with lenalidomide.") == []


def test_a_target_far_from_the_name_is_general_discussion() -> None:
    text = "ALLO-715 was studied in a cohort of patients whose disease expressed high levels of BCMA-directed antigen."
    assert attributed_targets_in(text)
    assert _read(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "After BCMA-directed CAR T, ALLO-715 was given.",
        "ALLO-715 in patients refractory to BCMA-directed therapy.",
        "ALLO-715 is not a BCMA-directed product.",
        "ALLO-715 versus a BCMA-directed CAR T.",
        "Post-BCMA-directed ALLO-715 cohort enrolled.",
    ],
)
def test_a_frame_pointing_at_another_therapy_refuses(text: str) -> None:
    assert _read(text) == []


def test_an_unresolved_symbol_beside_a_cue_refuses_the_whole_sentence() -> None:
    # A partial set for a dual construct would fail a dual-target question wrongly.
    assert _read("ALLO-715 is a CD19/XYZ9-directed CAR T.") == []


def test_its_own_alias_is_not_another_asset() -> None:
    admitted = sentence_targets(
        "ALLO-715 (cema-cel), a BCMA-directed CAR T.",
        asset_names=["ALLO-715", "cema-cel"],
        other_asset_names=name_keys(["ALLO-715", "cema-cel"]),
        document_id="doc:1",
    )
    assert [a.targets for a in admitted] == [(BCMA,)]


def _obs(*targets: str, sentence: str = "s") -> SentenceTarget:
    return SentenceTarget(document_id="doc:1", sentence=sentence, targets=targets)


def test_agreeing_sentences_make_one_fact_with_distinct_provenance() -> None:
    evidence = asset_sentence_target_evidence(
        "asset:1", [_obs(BCMA, sentence="a"), _obs(BCMA, sentence="b")], as_of_date=date(2026, 9, 24)
    )
    assert evidence is not None
    assert evidence.fact.value == [BCMA]
    assert evidence.fact.fact_type == "construct_target_set"
    assert {claim.extraction_method for claim in evidence.claims} == {EXTRACTION_METHOD}
    assert evidence.fact.confidence < 0.95


def test_disagreeing_sentences_make_no_fact() -> None:
    assert (
        asset_sentence_target_evidence(
            "asset:1", [_obs(BCMA, sentence="a"), _obs(CD19, sentence="b")], as_of_date=date(2026, 9, 24)
        )
        is None
    )


def test_no_sentences_make_no_fact() -> None:
    assert asset_sentence_target_evidence("asset:1", [], as_of_date=date(2026, 9, 24)) is None
