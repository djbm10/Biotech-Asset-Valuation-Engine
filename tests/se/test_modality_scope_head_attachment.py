import json
from pathlib import Path

import pytest

from bve.se.evidence.modality_scope import ScopeSource, scoped_modality_assertions

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_modality_scope_head_attachment_v1"
CONTROLS = json.loads((STUDY / "controls.json").read_text())


def source(control):
    return ScopeSource(
        artifact="fixture",
        artifact_sha256="fixture",
        record_id=control["id"],
        field="text",
        product_names=tuple(control["product_names"]),
        product_locator="fixture",
    )


def predicate_start(text):
    for copula in ("Novel Product is a ", "Novel Product is an ", "Novel Product is "):
        if text.startswith(copula):
            return len(copula)
    return None


@pytest.mark.parametrize("control", CONTROLS, ids=lambda c: c["id"])
def test_frozen_head_attachment(control):
    text = control["text"]
    rows = scoped_modality_assertions("candidate", text, source(control))
    have = sorted((r.mention.start, r.mention.end, r.modality, r.scope, r.rule) for r in rows)
    want = sorted(
        (m["start"], m["end"], m["modality"], m["scope"], m["rule"]) for m in control["mentions"]
    )
    assert have == want
    for r in rows:
        if r.rule == "explicit_product_predicate":
            # The relation span runs from the product name to the head designation, so any
            # admitted premodifier stays visible in provenance.
            assert r.relation_span.start == r.product_span.end
            assert r.relation_span.end == r.mention.start
        if r.rule in {"product_phrase_not_head", "product_phrase_coordination"}:
            assert r.relation_span is None and r.component_span is None and not r.relations


@pytest.mark.parametrize(
    "control", [c for c in CONTROLS if c["phrase"] is not None], ids=lambda c: c["id"]
)
def test_product_phrase_structure(control):
    from bve.se.evidence.modality_scope import product_phrase

    text = control["text"]
    start = predicate_start(text)
    right = min([p for ch in ".;\n" if (p := text.find(ch, start)) >= 0] or [len(text)])
    phrase = product_phrase(text, start, right)
    assert phrase.phrase.text == control["phrase"]
    assert phrase.head.text == control["head"]
    assert phrase.coordinated is control["coordinated"]
    assert text[phrase.head.start : phrase.head.end] == phrase.head.text
    assert phrase.phrase.start <= phrase.head.start < phrase.head.end == phrase.phrase.end


@pytest.mark.parametrize(
    ("text", "modifier"),
    [
        ("Novel Product is a peptide-linked antibody-drug conjugate.", "peptide"),
        ("Novel Product is an antibody-derived cell therapy.", "antibody"),
        ("Novel Product is a small-molecule-loaded nanoparticle.", "small-molecule"),
        ("Novel Product is a peptide-drug conjugate.", "peptide"),
        ("Novel Product is a peptide or antibody.", "peptide"),
    ],
)
def test_modifier_is_never_product_level(text, modifier):
    control = {"id": "x", "product_names": ["Novel Product"]}
    rows = scoped_modality_assertions("candidate", text, source(control))
    start = text.index(modifier)
    focus = [r for r in rows if (r.mention.start, r.mention.text) == (start, modifier)]
    assert focus and all(r.scope != "PRODUCT_LEVEL" for r in focus)


def test_unrecognized_head_invents_no_modality():
    text = "Novel Product is a small-molecule-loaded nanoparticle."
    control = {"id": "x", "product_names": ["Novel Product"]}
    rows = scoped_modality_assertions("candidate", text, source(control))
    assert [r for r in rows if r.scope == "PRODUCT_LEVEL"] == []
    assert all(r.modality is not None for r in rows)
