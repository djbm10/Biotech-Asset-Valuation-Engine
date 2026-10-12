"""Freeze current outputs of existing public development controls, offline."""
import hashlib
import json
import socket
from pathlib import Path
from unittest.mock import patch

ROOT = Path('/home/djmann/projects/bve-b8')
OUT = Path('/tmp/target_reference_identity_surface_diagnosis_v1')


def run():
    from bve.se.intent import compile_intent, intent_to_trial_query, parse_query
    from bve.se.intent.compiler import residual_indications
    from bve.se.schemas.contracts import BuyerIdentity
    population = json.loads((ROOT / 'research/se_indication_compilation_v3/population.json').read_text())
    rows = []
    for case in population['cases']:
        assert case['id'] not in {f'H{i}' for i in [6, 7, 8, 9, 10, 21, 22, 23, 24, 25]}
        intent = parse_query(case['query'])
        row = {'id': case['id'], 'query': case['query'],
               'intent': intent.model_dump(mode='json'),
               'blockers': intent.blockers(indication_supplied=True),
               'indications': residual_indications(intent),
               'trial_query': intent_to_trial_query(intent).model_dump(mode='json'),
               'problem': None}
        before = case.get('baseline_problem')
        if intent.is_compilable and before is not None:
            problem = compile_intent(intent, buyer=BuyerIdentity.model_validate(before['buyer']),
                                     therapeutic_areas=before['strategic_gap']['therapeutic_areas'])
            row['problem'] = problem.model_dump(mode='json')
        assert row['indications'] == case['expected'], case['id']
        rows.append(row)
    path = OUT / 'current_scientific_baseline.json'
    path.write_text(json.dumps({'baseline': 'dea4fdb', 'rows': rows,
                                'live_calls': 0, 'holdout_probes': 0}, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'rows': len(rows), 'expected_indications_match': len(rows),
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('network prohibited')) as guard:
        run()
        assert guard.call_count == 0
