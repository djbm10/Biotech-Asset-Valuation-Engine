"""Offline compatibility and historical certificates for separate target references."""
import hashlib
import json
import socket
import tarfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'research/target_reference_identity_surface_diagnosis_v1'
NEW_VERSIONS = ('intent_v1__target_reference_v1__target_query_greek_v2',
                'intent_v1__target_reference_v1')


def project_metadata(value):
    """Validate each reference before removing only the declared additive metadata."""
    from bve.se.ontology.target_reference import lookup_id
    from bve.se.schemas.contracts import TargetReference, TargetTerm
    if isinstance(value, list):
        return [project_metadata(v) for v in value]
    if not isinstance(value, dict):
        return value
    value = dict(value)
    if 'target_reference' in value:
        reference = TargetReference.model_validate(value.pop('target_reference'))
        if 'canonical_id' in value:
            term = TargetTerm.model_validate({**value, 'target_reference': reference})
        else:
            assert value.get('kind') == 'TARGET'
            term = TargetTerm(canonical_id=value['resolved_to'], label=value['resolved_to'],
                              target_reference=reference)
        assert lookup_id(term) == reference.entity_id
    if value.get('compiler_version') in NEW_VERSIONS:
        value['compiler_version'] = 'intent_v1'
    for version in NEW_VERSIONS:
        if isinstance(value.get('version'), str) and value['version'].startswith(version + '__'):
            value['version'] = 'intent_v1__' + value['version'][len(version + '__'):]
            break
    return {k: project_metadata(v) for k, v in value.items()}


def validate_intent(intent):
    from bve.se.ontology.query_targets import resolve_query_target as resolve_target
    for span in intent.spans:
        if span.kind.value == 'TARGET':
            assert span.target_reference is not None
            assert resolve_target(span.text).entity.canonical_id == span.target_reference.entity_id
        else:
            assert span.target_reference is None
    for term in intent.targets:
        assert term.target_reference is not None
    project_metadata(intent.model_dump(mode='json'))


def current_compatibility():
    from bve.se.intent import compile_intent, intent_to_trial_query, parse_query
    from bve.se.intent.compiler import residual_indications
    from bve.se.schemas.contracts import BuyerIdentity
    rows = []
    baseline = json.loads((PACKET / 'current_scientific_baseline.json').read_text())
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('network prohibited')):
        for before in baseline['rows']:
            intent = parse_query(before['query'])
            validate_intent(intent)
            after = {'id': before['id'], 'query': before['query'],
                     'intent': intent.model_dump(mode='json'),
                     'blockers': intent.blockers(indication_supplied=True),
                     'indications': residual_indications(intent),
                     'trial_query': intent_to_trial_query(intent).model_dump(mode='json'),
                     'problem': None}
            if before['problem'] is not None:
                problem = compile_intent(intent,
                    buyer=BuyerIdentity.model_validate(before['problem']['buyer']),
                    therapeutic_areas=before['problem']['strategic_gap']['therapeutic_areas'])
                after['problem'] = problem.model_dump(mode='json')
            projected = project_metadata(after)
            rows.append({'id': before['id'], 'matches': projected == before,
                         'changed_fields': [k for k in before if before[k] != projected[k]]})
    return rows


def historical_certificates():
    records = json.loads((PACKET / 'historical_source_verification.json').read_text())
    rows = []
    for milestone in records['milestones']:
        archive = PACKET / milestone['archive']
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == milestone['archive_sha256']
        population = json.loads((ROOT / 'research' / milestone['milestone'] / 'population.json').read_text())
        acceptance = json.loads((ROOT / 'research' / milestone['milestone'] / 'acceptance.json').read_text())
        assert milestone['implementation'].startswith(acceptance['implementation'])
        checked = 0
        with tarfile.open(archive) as source:
            for path, expected in population['protected_source'].items():
                if path in population.get('allowed_source', []):
                    continue
                assert hashlib.sha256(source.extractfile(path).read()).hexdigest() == expected
                checked += 1
        for path, expected in milestone['frozen_artifacts'].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
        rows.append({'milestone': milestone['milestone'], 'checks': checked, 'matches': True})
    assert sum(r['checks'] for r in rows) == 1791
    return rows


if __name__ == '__main__':
    print(json.dumps({'compatibility': current_compatibility(),
                      'historical_certificates': historical_certificates()}, indent=2))
