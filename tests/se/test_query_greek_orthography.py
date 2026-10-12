"""Frozen target-query orthography controls; original target resolver stays unchanged."""
import json
from datetime import date
from pathlib import Path

import pytest

from bve.se.acquisition.runner import target_queries_for
from bve.se.discovery.query import compile_problem_queries
from bve.se.intent import build_buyer_identity, compile_intent, parse_query
from bve.se.ontology.query_targets import resolve_query_target
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.ontology.targets import get_resolver, reset_resolver_cache, resolve_target

ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / 'research/se_target_query_greek_orthography_v1'
CONTROLS = json.loads((PACKET / 'synthetic_controls.json').read_text())


def decision(result):
    return {'status': result.status.value, 'entity': result.canonical_id,
            'candidates': sorted(c.canonical_id for c in result.candidates)}


@pytest.fixture()
def authority(tmp_path, monkeypatch):
    path = tmp_path / 'authority'
    OntologySnapshot.model_validate_json((PACKET / 'synthetic_authority.json').read_text()).write(path)
    monkeypatch.setenv('BVE_SE_ONTOLOGY_SNAPSHOT', str(path))
    reset_resolver_cache()
    yield get_resolver().ontology_version
    reset_resolver_cache()


@pytest.mark.parametrize('case', CONTROLS['raw_cases'], ids=lambda r: r['query'])
def test_frozen_spelling_decisions(authority, case):
    before = resolve_target(case['query']).model_dump(mode='json')
    result = resolve_query_target(case['query'])
    assert decision(result) == {k: case[k] for k in ['status', 'entity', 'candidates']}
    assert resolve_target(case['query']).model_dump(mode='json') == before
    if result.status.value == 'RESOLVED':
        assert result.ontology_version == authority
        assert result.basis.observed_query == case['query']
        assert result.basis.asserting_record_keys
        assert result.basis.asserted_by
        assert resolve_target(result.basis.matched_alias).canonical_id == result.canonical_id


@pytest.mark.parametrize('case', CONTROLS['queries'], ids=lambda r: r['query'])
def test_frozen_parser_boundaries(authority, case):
    original = parse_query(case['baseline_query'])
    intent = parse_query(case['query'])
    assert [t.canonical_id for t in intent.targets] == case['expected_targets']
    assert [t.canonical_id for t in intent.targets] == [t.canonical_id for t in original.targets]
    assert intent.target_operator == original.target_operator
    assert intent.modalities == original.modalities
    if case['expected_targets']:
        problem = compile_intent(intent, buyer=build_buyer_identity(
            'Greek fixture', as_of_date=date(2026, 10, 12)))
        assert compile_problem_queries(problem)
        assert all('TARGET:' not in plan.query for plan in compile_problem_queries(problem))
        assert all('TARGET:' not in value for q in target_queries_for(problem)
                   for value in [q.canonical_id, *q.aliases])
        assert all(t.target_reference.ontology_version == authority for t in intent.targets)
    else:
        assert not intent.is_compilable


def test_original_exact_lookup_is_not_reinterpreted(authority):
    for name in ['GQ01', 'Anchorase alpha', 'Sharing alpha', 'Composite beta', 'Missing delta']:
        expected = resolve_target(name)
        assert resolve_query_target(name).model_dump(mode='json') == expected.model_dump(mode='json')


def test_missing_snapshot_keeps_existing_behavior(tmp_path, monkeypatch):
    monkeypatch.setenv('BVE_SE_ONTOLOGY_SNAPSHOT', str(tmp_path / 'absent'))
    reset_resolver_cache()
    try:
        assert resolve_query_target('Anchoraseα') is None
    finally:
        reset_resolver_cache()
