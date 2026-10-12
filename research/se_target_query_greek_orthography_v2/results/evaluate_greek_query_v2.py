"""One frozen evaluation of the unmodified Greek query candidate."""
import importlib.util
import json
import socket
from datetime import date
from pathlib import Path
from unittest.mock import patch

from bve.se.acquisition.runner import target_queries_for
from bve.se.discovery.query import compile_problem_queries
from bve.se.intent import build_buyer_identity, compile_intent, parse_query
from bve.se.ontology.query_targets import RULE, resolve_query_target
from bve.se.ontology.targets import resolve_target

ROOT = Path('/home/djmann/projects/bve-b8')
V1 = ROOT / 'research/se_target_query_greek_orthography_v1'
V2 = ROOT / 'research/se_target_query_greek_orthography_v2'
PARENT = ROOT / 'research/se_target_query_alias_coverage_v1'
SPEC = importlib.util.spec_from_file_location('reference_evaluation', ROOT / 'scripts/evaluate_target_reference_v1.py')
REFERENCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REFERENCE)


def outcome(result):
    return {'status': result.status.value, 'entity_id': result.canonical_id,
            'candidates': sorted(e.canonical_id for e in result.candidates)}


def run():
    oracle = json.loads((V1 / 'authority_oracle.json').read_text())
    raw_rows = []
    for row in oracle['rows']:
        actual = outcome(resolve_query_target(row['text']))
        raw_rows.append({'id': row['id'], 'text': row['text'], 'expected': row['expected'],
                         'actual': actual, 'matches': actual == row['expected'],
                         'global_unchanged': outcome(resolve_target(row['text'])) == row['global_baseline']})
    refs = {r['id']: r for r in json.loads((V2 / 'query_reference.json').read_text())['rows']}
    old = json.loads((PARENT / 'survey_baseline.json').read_text())
    preservation = []
    precision = []
    for row in old['rows']:
        for frame in row['frames']:
            intent = parse_query(frame['query'])
            REFERENCE.validate_intent(intent)
            actual = {'targets': [t.canonical_id for t in intent.targets],
                      'operator': intent.target_operator.value,
                      'ambiguous_terms': intent.ambiguous_terms,
                      'blockers': intent.blockers(indication_supplied=True),
                      'spans': REFERENCE.project_metadata([s.model_dump(mode='json') for s in intent.spans])}
            if row['id'] not in refs:
                preservation.append({'id': row['id'], 'frame': frame['frame'],
                                     'changed_fields': [k for k in actual if actual[k] != frame[k]]})
            else:
                reference = refs[row['id']]['query_reference_entity']
                new_spans = []
                for span in intent.spans:
                    if span.kind.value != 'TARGET':
                        continue
                    resolved = resolve_query_target(span.text)
                    if resolved.rule != RULE:
                        continue
                    new_spans.append({'text': span.text, 'entity': resolved.canonical_id,
                                      'matched_alias': resolved.basis.matched_alias,
                                      'complete_alias_certified': resolve_target(resolved.basis.matched_alias).canonical_id == resolved.canonical_id,
                                      'matches_biological_reference': resolved.canonical_id == reference})
                added = [t.target_reference.entity_id for t in intent.targets if t.canonical_id not in frame['targets']]
                precision.append({'id': row['id'], 'frame': frame['frame'], 'reference': reference,
                                  'new_spans': new_spans, 'added_targets': added,
                                  'unsafe': any(not x['complete_alias_certified'] or not x['matches_biological_reference'] for x in new_spans) or any(x != reference for x in added),
                                  'targets': [t.canonical_id for t in intent.targets]})
    controls = []
    for row in old['controls']:
        intent = parse_query(row['intent']['original_query'])
        projected = REFERENCE.project_metadata(intent.model_dump(mode='json'))
        controls.append({'text': row['text'], 'unchanged': projected == row['intent'],
                         'targets': [t.canonical_id for t in intent.targets]})
    query = oracle['diagnostic_query_baseline'][0]['query']
    intent = parse_query(query)
    problem = compile_intent(intent, buyer=build_buyer_identity('H17 offline diagnostic', as_of_date=date(2026, 10, 12)), therapeutic_areas=['AUTOIMMUNE'])
    plans = compile_problem_queries(problem)
    diagnostic = {'query': query, 'targets': [t.target_reference.entity_id for t in intent.targets],
                  'plan_count': len(plans), 'namespace_literals': any('TARGET:' in p.query for p in plans),
                  'source_targets': [q.canonical_id for q in target_queries_for(problem)],
                  'factor_XI_status': outcome(resolve_query_target('factor XI'))}
    result = {'candidate': 'e3ad3fd', 'preregistration': '8ee443a', 'raw_oracle': raw_rows,
              'non_proposal_preservation': preservation, 'greek_query_precision': precision,
              'controls': controls, 'diagnostic': diagnostic, 'live_asset_runs': 0, 'holdout_probes': 0}
    Path('/tmp/greek_v2_evaluation.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'raw_matches': sum(r['matches'] for r in raw_rows), 'raw_total': len(raw_rows),
                      'global_changes': sum(not r['global_unchanged'] for r in raw_rows),
                      'non_proposal_parses': len(preservation), 'non_proposal_differences': sum(bool(r['changed_fields']) for r in preservation),
                      'greek_parses': len(precision), 'unsafe_greek_parses': sum(r['unsafe'] for r in precision),
                      'changed_controls': [r for r in controls if not r['unchanged']],
                      'diagnostic': diagnostic}, indent=2))


if __name__ == '__main__':
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('network prohibited')):
        run()
