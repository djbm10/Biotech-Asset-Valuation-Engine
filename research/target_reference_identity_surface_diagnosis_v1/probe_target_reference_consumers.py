"""Capture current interfaces with frozen synthetic authority and no network."""
import json
import os
import socket
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path('/home/djmann/projects/bve-b8')
PACKET = ROOT / 'research/target_reference_identity_surface_diagnosis_v1'
OUTPUT = Path('/tmp/target_reference_consumer_baseline.json')


def run():
    from bve.se.acquisition import connectors as c
    from bve.se.acquisition.policy import LiveSourcePolicy
    from bve.se.acquisition.runner import target_queries_for
    from bve.se.discovery.query import compile_problem_queries
    from bve.se.intent import build_buyer_identity, compile_intent, intent_to_trial_query, parse_query
    from bve.se.ontology.snapshot import OntologySnapshot
    from bve.se.ontology.targets import reset_resolver_cache, resolve_target
    from bve.se.resolution.target_attribution import attribution_for
    from bve.se.schemas.contracts import TargetTerm

    controls = json.loads((PACKET / 'controls.json').read_text())
    fixture = json.loads((PACKET / 'synthetic_authority.json').read_text())
    snapshot = OntologySnapshot.model_validate(fixture)
    buyer = build_buyer_identity('Offline synthetic consumer audit', as_of_date=date(2026, 10, 12))
    policy = LiveSourcePolicy(policy_version='fixture-reference-v1',
                              required_source_families=('fda_label',), **controls['source_policy'])
    output = {'network_calls': 0, 'holdout_probes': 0, 'query_cases': [], 'reference_cases': []}
    with tempfile.TemporaryDirectory(prefix='target-reference-') as directory:
        snapshot.write(Path(directory) / 'snapshot')
        os.environ['BVE_SE_ONTOLOGY_SNAPSHOT'] = str(Path(directory) / 'snapshot')
        reset_resolver_cache()
        for case in controls['queries']:
            intent = parse_query(case['query'])
            row = {'id': case['id'], 'intent': intent.model_dump(mode='json'),
                   'blockers': intent.blockers(indication_supplied=True)}
            try:
                problem = compile_intent(intent, buyer=buyer)
                row['problem'] = problem.model_dump(mode='json')
                row['plans'] = [p.model_dump(mode='json') for p in compile_problem_queries(problem)]
            except Exception as exc:
                row['error'] = {'type': type(exc).__name__, 'message': str(exc)}
            output['query_cases'].append(row)

        base_intent = parse_query('Find clinical-stage GAX2 antibodies.')
        for surface, entity_id in controls['programmatic_reference_pairs']:
            for reference in [surface, entity_id]:
                intent = base_intent.model_copy(update={'targets': [TargetTerm(
                    canonical_id=reference, label=surface)]})
                problem = compile_intent(intent, buyer=buyer)
                targets = target_queries_for(problem)
                result = resolve_target(reference)
                row = {'surface': surface, 'reference': reference,
                       'resolver': {'status': result.status.value, 'entity_id': result.canonical_id},
                       'targets': [{'canonical_id': t.canonical_id, 'aliases': list(t.aliases)}
                                   for t in targets],
                       'trial_query': intent_to_trial_query(intent).model_dump(mode='json')}
                try:
                    row['plans'] = [p.model_dump(mode='json') for p in compile_problem_queries(problem)]
                except Exception as exc:
                    row['plan_error'] = {'type': type(exc).__name__, 'message': str(exc)}
                try:
                    policy.validate_problem(problem)
                    row['policy'] = 'ACCEPT'
                except Exception as exc:
                    row['policy'] = {'type': type(exc).__name__, 'message': str(exc)}
                attribution = attribution_for([reference])
                row['attribution'] = None if attribution is None else {
                    drug: [a.model_dump(mode='json') for a in attribution.assert_targets(drug, [])]
                    for drug in ['DRUGA', 'DRUGB', 'DRUGC']}
                row['connectors'] = {}
                for name in controls['connectors']:
                    requests = []
                    def capture(*args):
                        requests.append(list(args))
                        return []
                    if name == 'CrossrefConferenceConnector':
                        connector = c.CrossrefConferenceConnector(
                            c.ConferenceVenue(source_family='conference_asco', publisher='Fixture',
                                              container_titles=['Fixture Journal']), search_fn=capture)
                    else:
                        connector = getattr(c, name)(search_fn=capture)
                    health = connector.acquire(None, targets=targets, modality_terms=['antibody'],
                                               as_of_date=date(2026, 10, 12))
                    row['connectors'][name] = {'requests': requests,
                                               'health': health.model_dump(mode='json')}
                output['reference_cases'].append(row)
        reset_resolver_cache()
    OUTPUT.write_text(json.dumps(output, indent=2, sort_keys=True, default=str) + '\n')
    print(json.dumps({'queries': len(output['query_cases']),
                      'query_errors': sum('error' in r for r in output['query_cases']),
                      'reference_cases': len(output['reference_cases']),
                      'connector_calls': sum(len(r['connectors']) for r in output['reference_cases'])}))


if __name__ == '__main__':
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('network prohibited')) as guard:
        run()
        assert guard.call_count == 0
