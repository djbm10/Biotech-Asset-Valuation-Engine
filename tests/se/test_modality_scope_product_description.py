import json
import sys
from pathlib import Path

import pytest

from bve.se.evidence.modality_scope import ScopeSource, scoped_modality_assertions

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_modality_scope_product_description_v1"
sys.path.insert(0, str(STUDY))
import checker  # noqa: E402

SAMPLE = {u["unit_id"]: u for u in json.loads((STUDY / "sample.json").read_text())["units"]}
LABELS = json.loads((STUDY / "labels.json").read_text())["labels"]


def rows(text, names=("Novel Product",)):
    src = ScopeSource(
        artifact="fixture",
        artifact_sha256="fixture",
        record_id="x",
        field="text",
        product_names=tuple(names),
        product_locator="fixture",
    )
    return scoped_modality_assertions("candidate", text, src)


def product(text, names=("Novel Product",)):
    return {(r.mention.text, r.rule) for r in rows(text, names) if r.scope == "PRODUCT_LEVEL"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Novel Product is a humanized monoclonal antibody targeting PD-1.",
            {("monoclonal antibody", "explicit_product_predicate_premodified")},
        ),
        (
            "Trials of Novel Product, a selective anti-IL-23 antibody, are ongoing.",
            {("antibody", "explicit_product_appositive")},
        ),
        (
            "Novel Product (NP-1) is a second generation, orally administered, tyrosine kinase "
            "inhibitor (TKI) that blocks ALK.",
            {("tyrosine kinase inhibitor", "explicit_product_predicate_premodified")},
        ),
    ],
)
def test_explicit_descriptions_become_product_level(text, expected):
    assert expected <= product(text)


@pytest.mark.parametrize(
    "text",
    [
        "Novel Product is a bispecific T cell engaging antibody.",
        "Novel Product is not a humanized monoclonal antibody.",
        "Novel Product is a peptide and antibody combination.",
        "Other Product, a humanized antibody, was compared with Novel Product.",
        "Novel Product, and an antibody, were given.",
        "Novel Product is a humanized antibody-derived cell product.",
    ],
)
def test_no_unsupported_whole_product_promotion(text):
    assert not {r for r in product(text) if "MONOCLONAL" in r[0].upper() or r[0] == "antibody"}


def test_premodifier_of_another_modality_blocks_the_head():
    found = {r.mention.text: r.scope for r in rows("Novel Product is a bispecific T cell engaging antibody.")}
    assert found["antibody"] != "PRODUCT_LEVEL"


def test_nested_suffix_is_not_promoted():
    found = [
        (r.mention.text, r.scope) for r in rows("Novel Product, an EGFR-MET bispecific antibody, works.")
    ]
    assert ("bispecific antibody", "PRODUCT_LEVEL") in found
    assert ("antibody", "PRODUCT_LEVEL") not in found


def test_provenance_on_new_assertions():
    for r in rows("Novel Product, a selective anti-IL-23 antibody, was given."):
        if r.rule == "explicit_product_appositive":
            assert r.product_span.text == "Novel Product"
            assert r.relation_span.start == r.product_span.end
            assert r.relation_span.end == r.mention.start
            assert r.relations == ("PRODUCT_IS_MODALITY",)


def test_independent_sample_has_no_unsafe_promotion_and_meets_recall():
    measured = {uid: checker.run_unit(u) for uid, u in SAMPLE.items()}
    unsafe, _, by_rule, missing = checker.score_units(measured, LABELS)
    assert unsafe == []
    assert missing == []
    for rule, (hit, total) in by_rule.items():
        assert total >= 5 and hit / total >= 0.8, (rule, hit, total)
