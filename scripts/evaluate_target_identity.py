"""Offline frozen parser comparison; never execute a search or inspect holdouts."""
import hashlib
import json
from datetime import date
from pathlib import Path

from bve.se.discovery.query import compile_problem_queries
from bve.se.intent import build_buyer_identity, compile_intent, parse_query
from bve.se.ontology.targets import resolve_target

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'research/se_target_query_alias_coverage_v1'
OUTPUT = Path('/tmp/target_identity_result.json')
baseline = json.loads((PACKET / 'survey_baseline.json').read_text())
errors = []
comparisons = 0


def biological_id(value):
    return value.removeprefix('TARGET:') if value else value


for row in baseline['rows']:
    for frozen in row['frames']:
        intent = parse_query(frozen['query'])
        checks = {
            'targets': ([biological_id(t.canonical_id) for t in intent.targets], frozen['targets']),
            'operator': (intent.target_operator.value, frozen['operator']),
            'ambiguous_terms': (intent.ambiguous_terms, frozen['ambiguous_terms']),
        }
        # Every span retains its classification, offsets and explanation; only
        # the target reference serialization has a declared allowed difference.
        spans = [s.model_dump(mode='json') for s in intent.spans]
        for span in spans:
            if span['kind'] == 'TARGET':
                span['resolved_to'] = biological_id(span['resolved_to'])
        checks['spans'] = (spans, frozen['spans'])
        for name, (actual, expected) in checks.items():
            if actual != expected:
                errors.append({'id': row['id'], 'frame': frozen['frame'], 'field': name,
                               'actual': actual, 'expected': expected})
        comparisons += 1

controls = []
for row in baseline['controls']:
    result = resolve_target(row['text'])
    actual = [result.status.value, result.canonical_id,
              [e.canonical_id for e in result.candidates]]
    expected = [row['raw_status'], row['raw_entity'], row['raw_candidates']]
    controls.append({'text': row['text'], 'unchanged': actual == expected})

query = 'Find clinical-stage FXI inhibitors for prevention of thrombosis.'
intent = parse_query(query)
problem = compile_intent(intent, buyer=build_buyer_identity(
    'Offline identity audit', as_of_date=date(2026, 10, 12)))
plans = compile_problem_queries(problem)
diagnostic = {
    'query': query,
    'target_ids': [t.canonical_id for t in intent.targets],
    'labels': [t.label for t in intent.targets],
    'plans': len(plans),
    'plan_target_ids': sorted({t for p in plans for t in p.target_ids}),
    'namespace_search_literal': any('"TARGET:' in p.query for p in plans),
    'bare_F11_status': resolve_target('F11').status.value,
}
result = {'comparisons': comparisons, 'differences': errors, 'controls': controls,
          'diagnostic': diagnostic,
          'baseline_sha256': hashlib.sha256((PACKET/'survey_baseline.json').read_bytes()).hexdigest(),
          'live_runs': 0, 'holdout_probes': 0}
OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
print(json.dumps({'comparisons': comparisons, 'differences': len(errors),
                  'controls_unchanged': sum(r['unchanged'] for r in controls),
                  'diagnostic': diagnostic}))
