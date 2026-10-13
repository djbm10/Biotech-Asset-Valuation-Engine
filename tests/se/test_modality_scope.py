import hashlib
import json
from pathlib import Path

import pytest

from bve.se.evidence.modality_scope import ScopeSource, scoped_modality_assertions

ROOT = Path(__file__).resolve().parents[2]
CONTROLS = json.loads((ROOT / 'research/se_modality_assertion_scope_representation_v1/controls.json').read_text())


def source(text):
    return ScopeSource(artifact='fixture', artifact_sha256=hashlib.sha256(text.encode()).hexdigest(), record_id='fixture', field='description', product_names=('Novel Product', 'Dato-DXd'), product_locator='intervention.name+otherNames')


@pytest.mark.parametrize('control', CONTROLS, ids=lambda x: x['id'])
def test_frozen_scope(control):
    text = control['text']
    records = scoped_modality_assertions('candidate', text, source(text))
    start = text.casefold().index(control['focus_term'].casefold())
    matches = [r for r in records if r.mention.start == start and r.mention.end == start + len(control['focus_term'])]
    assert matches
    assert all(r.scope == control['expected_scope'] for r in matches)
    for r in records:
        assert text[r.mention.start:r.mention.end] == r.mention.text
        assert r.legacy_decision_bearing is False
        assert r.source == source(text)
        if r.scope != 'AMBIGUOUS':
            assert r.product_span is not None
            assert r.relations
    assert records == scoped_modality_assertions('candidate', text, source(text))


def test_multiple_levels_and_no_fact_promotion():
    text = 'Novel Product is a peptide therapeutic with a peptide linker.'
    records = scoped_modality_assertions('candidate', text, source(text))
    peptides = [r for r in records if r.modality == 'PEPTIDE']
    assert [r.scope for r in peptides] == ['PRODUCT_LEVEL', 'COMPONENT_LEVEL']
    assert len({r.assertion_id for r in records}) == len(records)
