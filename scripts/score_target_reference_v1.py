"""Formal offline parser preservation and reference-interface evaluation."""
import hashlib
import importlib.util
import json
import socket
from datetime import date
from pathlib import Path
from unittest.mock import patch

from bve.se.acquisition.runner import target_queries_for
from bve.se.discovery.query import compile_problem_queries
from bve.se.intent import build_buyer_identity, compile_intent, parse_query
from bve.se.ontology.target_reference import lookup_id
from bve.se.ontology.targets import resolve_target

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'research/se_target_query_alias_coverage_v1'
SPEC = importlib.util.spec_from_file_location('reference_compatibility',
                                             ROOT / 'scripts/evaluate_target_reference_v1.py')
EVALUATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATION)


def score():
    baseline = json.loads((PACKET / 'survey_baseline.json').read_text())
    errors = []
    count = 0
    for row in baseline['rows']:
        for frozen in row['frames']:
            intent = parse_query(frozen['query'])
            EVALUATION.validate_intent(intent)
            actual = {'targets': [t.canonical_id for t in intent.targets],
                      'operator': intent.target_operator.value,
                      'ambiguous_terms': intent.ambiguous_terms,
                      'blockers': intent.blockers(indication_supplied=True),
                      'spans': EVALUATION.project_metadata(
                          [s.model_dump(mode='json') for s in intent.spans])}
            for key, value in actual.items():
                if value != frozen[key]:
                    errors.append({'id': row['id'], 'frame': frozen['frame'], 'field': key,
                                   'actual': value, 'expected': frozen[key]})
            count += 1
        if count % 700 == 0:
            print(f'Compared {count} parses', flush=True)
    controls = []
    for row in baseline['controls']:
        result = resolve_target(row['text'])
        intent = parse_query(row['intent']['original_query'])
        EVALUATION.validate_intent(intent)
        controls.append({'text': row['text'],
                         'raw_unchanged': [result.status.value, result.canonical_id,
                                          [e.canonical_id for e in result.candidates]] ==
                         [row['raw_status'], row['raw_entity'], row['raw_candidates']],
                         'intent_unchanged': EVALUATION.project_metadata(
                             intent.model_dump(mode='json')) == row['intent']})
    intent = parse_query('Find clinical-stage FXI inhibitors for prevention of thrombosis.')
    problem = compile_intent(intent, buyer=build_buyer_identity(
        'Offline reference audit', as_of_date=date(2026, 10, 12)))
    plans = compile_problem_queries(problem)
    diagnostic = {'reference_ids': [lookup_id(t) for t in intent.targets],
                  'legacy_symbols': [t.canonical_id for t in intent.targets],
                  'plan_count': len(plans),
                  'plan_target_ids': sorted({t for p in plans for t in p.target_ids}),
                  'namespace_literal': any('TARGET:' in p.query for p in plans),
                  'source_targets': [t.canonical_id for t in target_queries_for(problem)],
                  'bare_F11_status': resolve_target('F11').status.value}
    return {'comparisons': count, 'differences': errors, 'controls': controls,
            'diagnostic': diagnostic, 'live_runs': 0, 'holdout_probes': 0,
            'baseline_sha256': hashlib.sha256((PACKET / 'survey_baseline.json').read_bytes()).hexdigest()}


if __name__ == '__main__':
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('network prohibited')) as guard:
        result = score()
        assert guard.call_count == 0
    Path('/tmp/target_reference_formal.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'controls'}, indent=2))
