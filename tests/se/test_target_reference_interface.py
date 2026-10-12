"""Frozen target identity / retrieval interface controls; no external requests."""
import json
import socket
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from bve.se.acquisition import connectors as c
from bve.se.acquisition.policy import LiveSourcePolicy
from bve.se.acquisition.runner import target_queries_for
from bve.se.discovery.query import AmbiguousTargetError, compile_problem_queries
from bve.se.gates.evaluator import _target_key
from bve.se.intent import build_buyer_identity, compile_intent, parse_query
from bve.se.intent.intent import IntentSpan, SpanKind
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.ontology.target_reference import TargetReferenceError, lookup_id
from bve.se.ontology.targets import get_resolver, reset_resolver_cache
from bve.se.resolution.target_attribution import attribution_for
from bve.se.schemas.contracts import (
    BuyerProblemV2, TargetExpression, TargetOperator, TargetReference, TargetTerm,
)

ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / 'research/target_reference_identity_surface_diagnosis_v1'
CONTROLS = json.loads((PACKET / 'controls.json').read_text())
ORACLE = json.loads((PACKET / 'surface_request_oracle.json').read_text())['rows']
BUYER = build_buyer_identity('Offline interface test', as_of_date=date(2026, 10, 12))


@pytest.fixture()
def authority(tmp_path, monkeypatch):
    path = tmp_path / 'snapshot'
    OntologySnapshot.model_validate_json((PACKET / 'synthetic_authority.json').read_text()).write(path)
    monkeypatch.setenv('BVE_SE_ONTOLOGY_SNAPSHOT', str(path))
    reset_resolver_cache()
    yield get_resolver().ontology_version
    reset_resolver_cache()


@pytest.mark.parametrize('case', CONTROLS['queries'], ids=lambda x: x['id'])
def test_frozen_query_entities(authority, case):
    intent = parse_query(case['query'])
    assert [t.target_reference.entity_id for t in intent.targets] == case['intended_entity_ids']
    for span in intent.spans:
        assert (span.target_reference is not None) == (span.kind is SpanKind.TARGET)
    if not case['intended_entity_ids']:
        assert not intent.is_compilable
        return
    problem = compile_intent(intent, buyer=BUYER)
    assert compile_problem_queries(problem)
    restored = BuyerProblemV2.model_validate_json(problem.model_dump_json())
    assert restored == problem
    assert [lookup_id(t) for t in restored.strategic_gap.target_expression.targets] == (
        case['intended_entity_ids'])


def problem_for(term):
    intent = parse_query('Find clinical-stage GAX2 antibodies.')
    intent = intent.model_copy(update={'targets': [term]})
    return compile_intent(intent, buyer=BUYER)


@pytest.mark.parametrize('expected', ORACLE, ids=lambda x: x['surface'])
@pytest.mark.parametrize('qualified', [False, True])
def test_source_requests_and_attribution(authority, expected, qualified):
    term = TargetTerm(
        canonical_id=expected['entity_id'] if qualified else expected['surface'],
        label=expected['surface'],
        target_reference=None if qualified else TargetReference(
            entity_id=expected['entity_id'], ontology_version=authority),
    )
    problem = problem_for(term)
    targets = target_queries_for(problem)
    assert targets[0].canonical_id == expected['surface']
    assert list(targets[0].aliases) == expected['aliases']
    policy = LiveSourcePolicy(policy_version='fixture-reference-v1',
                             required_source_families=('fda_label',), **CONTROLS['source_policy'])
    assert policy.validate_problem(problem) == problem
    attribution = attribution_for([lookup_id(term)])
    actual = {drug: [a.model_dump(mode='json') for a in attribution.assert_targets(drug, [])]
              for drug in expected['attribution']}
    assert actual == expected['attribution']
    assert _target_key(lookup_id(term)) == expected['surface']
    assert all('"TARGET:' not in p.query for p in compile_problem_queries(problem))
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('network prohibited')) as guard:
        for name, wanted in expected['requests'].items():
            requests = []
            def capture(*args):
                requests.append(list(args))
                return []
            connector = (
                c.CrossrefConferenceConnector(c.ConferenceVenue(
                    source_family='conference_asco', publisher='Fixture',
                    container_titles=['Fixture Journal']), search_fn=capture)
                if name == 'CrossrefConferenceConnector' else getattr(c, name)(search_fn=capture)
            )
            health = connector.acquire(None, targets=targets, modality_terms=['antibody'],
                                       as_of_date=date(2026, 10, 12))
            assert health.connector_succeeded
            assert json.loads(json.dumps(requests, default=str)) == wanted
        assert guard.call_count == 0


@pytest.mark.parametrize('entity,symbol', [('TARGET:GAX2', 'GAX1'), ('TARGET:MISSING', 'GAX1')])
def test_incoherent_reference_fails_before_source_adapter(authority, entity, symbol):
    term = TargetTerm(canonical_id=symbol, label=symbol,
                      target_reference=TargetReference(entity_id=entity, ontology_version=authority))
    with pytest.raises(TargetReferenceError):
        problem_for(term)


def test_version_mismatch_is_not_reinterpreted(authority):
    term = TargetTerm(canonical_id='GAX1', label='GAX1', target_reference=TargetReference(
        entity_id='TARGET:GAX1', ontology_version='other-snapshot'))
    with pytest.raises(TargetReferenceError, match='version'):
        problem_for(term)


def test_missing_snapshot_fails_closed(authority, monkeypatch, tmp_path):
    term = TargetTerm(canonical_id='GAX1', label='GAX1', target_reference=TargetReference(
        entity_id='TARGET:GAX1', ontology_version=authority))
    monkeypatch.setenv('BVE_SE_ONTOLOGY_SNAPSHOT', str(tmp_path / 'missing'))
    reset_resolver_cache()
    with pytest.raises(TargetReferenceError, match='snapshot'):
        lookup_id(term)


def test_non_target_reference_is_not_accepted():
    with pytest.raises(ValidationError):
        TargetReference(entity_id='DRUG:DRUGA', ontology_version='fixture-v1')


def test_unreferenced_homonym_remains_ambiguous(authority):
    problem = problem_for(TargetTerm(canonical_id='GAX1', label='GAX1'))
    with pytest.raises(AmbiguousTargetError):
        compile_problem_queries(problem)


def test_legacy_serialization_is_unchanged():
    data = {'canonical_id': 'ABC', 'label': 'ABC', 'aliases': []}
    term = TargetTerm.model_validate(data)
    assert term.model_dump(mode='json') == data
    assert TargetTerm.model_validate_json(term.model_dump_json()) == term


@pytest.mark.parametrize('term', ['TARGET:GAX1', 'target:GAX1'])
def test_connector_boundary_rejects_internal_ids(term):
    with pytest.raises(ValueError, match='biological'):
        c.TargetQuery(canonical_id=term, aliases=[])
    with pytest.raises(ValueError, match='biological'):
        c.TargetQuery(canonical_id='GAX1', aliases=[term])


def test_duplicate_certified_entities_are_rejected(authority):
    ref = TargetReference(entity_id='TARGET:GAX1', ontology_version=authority)
    with pytest.raises(ValidationError, match='duplicate'):
        TargetExpression(operator=TargetOperator.ANY, targets=[
            TargetTerm(canonical_id='GAX1', label='GAX1', target_reference=ref),
            TargetTerm(canonical_id='TARGET:GAX1', label='GAX1', target_reference=ref),
        ])


def test_residual_span_cannot_carry_identity(authority):
    with pytest.raises(ValidationError, match='resolved target'):
        IntentSpan(text='other', start=0, end=5, kind=SpanKind.RESIDUAL, rule='control',
                   target_reference=TargetReference(entity_id='TARGET:GAX1',
                                                    ontology_version=authority))
