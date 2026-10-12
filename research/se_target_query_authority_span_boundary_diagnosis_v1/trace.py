"""Read-only parser trace over the frozen 96 authority-name pairs."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch
from bve.se.intent import parser
from bve.se.ontology.targets import resolve_target

ROOT = Path('/home/djmann/projects/bve-b8')
REF = ROOT / 'research/se_target_query_greek_orthography_v2/query_reference.json'
BASE = ROOT / 'research/se_target_query_alias_coverage_v1/survey_baseline.json'
refs = json.loads(REF.read_text())['rows']
base = {r['id']: r for r in json.loads(BASE.read_text())['rows']}
rows = []
for ref in refs:
    observations = []
    for spelling in ('original_authority_name', 'query_name'):
        name = ref[spelling]
        whole = resolve_target(name)
        for frame in base[ref['id']]['frames']:
            query = frame['query'].replace(ref['query_name'], name)
            calls = []
            def trace(text):
                result = resolve_target(text)
                calls.append({'text': text, 'status': result.status.value if result else None,
                              'entity_id': result.canonical_id if result else None})
                return result
            with patch.object(parser, 'resolve_target', side_effect=trace):
                intent = parser.parse_query(query)
            targets = [t.target_reference.entity_id if t.target_reference else t.canonical_id
                       for t in intent.targets]
            expected = ref['query_reference_entity']
            observations.append({
                'spelling': spelling, 'name': name, 'frame': frame['frame'], 'query': query,
                'whole_resolution': {'status': whole.status.value if whole else None,
                                     'entity_id': whole.canonical_id if whole else None},
                'token_count': len(parser._tokenize(name)),
                'whole_name_offered': any(c['text'].casefold() == name.casefold() for c in calls),
                'resolver_calls': calls, 'targets': targets,
                'outside_frozen_reference': [t for t in targets if expected and t != expected],
                'intent': intent.model_dump(mode='json')})
    rows.append({'reference': ref, 'observations': observations})
summary = {}
for spelling in ('original_authority_name', 'query_name'):
    obs = [o for r in rows for o in r['observations'] if o['spelling'] == spelling]
    summary[spelling] = {
        'frames': len(obs), 'whole_name_offered': sum(o['whole_name_offered'] for o in obs),
        'frames_with_targets_outside_certified_reference': sum(bool(o['outside_frozen_reference']) for o in obs),
        'names_with_targets_outside_certified_reference': sorted({o['name'] for o in obs if o['outside_frozen_reference']}),
        'bare_name_token_counts': dict(sorted(Counter(o['token_count'] for o in obs if o['frame'] == '{}').items()))}
result = {'baseline': '2ff9604', 'input_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (REF, BASE)}, 'summary': summary, 'rows': rows}
Path('/tmp/authority_span_trace_v1.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
print(json.dumps(summary, indent=2, ensure_ascii=False))
