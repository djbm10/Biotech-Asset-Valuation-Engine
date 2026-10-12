"""Trace the first parser boundary for the three frozen false target additions."""
import json
from pathlib import Path
from unittest.mock import patch

from bve.se.intent import parser
from bve.se.ontology.query_targets import resolve_query_target
from bve.se.ontology.targets import resolve_target

ROOT = Path('/home/djmann/projects/bve-b8')
evaluation = json.loads(Path('/tmp/greek_v2_evaluation.json').read_text())
unsafe = {r['id'] for r in evaluation['greek_query_precision'] if r['unsafe']}
population = json.loads((ROOT / 'research/se_target_query_alias_coverage_v1/survey_population.json').read_text())
baseline = {r['id']: r for r in json.loads((ROOT / 'research/se_target_query_alias_coverage_v1/survey_baseline.json').read_text())['rows']}
rows = []
for case in population:
    if case['id'] not in unsafe:
        continue
    query = baseline[case['id']]['frames'][0]['query']
    calls = []
    def observed(text):
        calls.append(text)
        return resolve_query_target(text)
    with patch.object(parser, 'resolve_target', side_effect=observed):
        intent = parser.parse_query(query)
    whole = resolve_query_target(case['text'])
    original = resolve_target(case['authority_alias'])
    rows.append({'id': case['id'], 'query': query, 'original_authority_name': case['authority_alias'],
                 'whole_greek_name': case['text'], 'authority_record_key': case['authority_record_key'],
                 'full_name_query_resolution': {'status': whole.status.value, 'entity_id': whole.canonical_id,
                                               'basis': whole.basis.model_dump(mode='json') if whole.basis else None},
                 'original_full_name_resolution': {'status': original.status.value, 'entity_id': original.canonical_id},
                 'resolver_calls': calls, 'whole_name_was_offered_to_resolver': case['text'] in calls,
                 'before': baseline[case['id']]['frames'][0], 'after': intent.model_dump(mode='json'),
                 'source_records': [r.model_dump(mode='json') for r in whole.entity.source_records]})
Path('/tmp/greek_v2_first_boundaries.json').write_text(json.dumps(rows, indent=2, ensure_ascii=False) + '\n')
print(json.dumps([{'name': r['whole_greek_name'], 'whole_name_offered': r['whole_name_was_offered_to_resolver'],
                   'correct_whole_identity': r['full_name_query_resolution']['entity_id'],
                   'emitted': [t['canonical_id'] for t in r['after']['targets']]} for r in rows], indent=2, ensure_ascii=False))
