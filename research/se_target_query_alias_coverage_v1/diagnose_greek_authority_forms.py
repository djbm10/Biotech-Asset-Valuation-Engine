"""Diagnose frozen orthography proposals against their unchanged authority spellings."""
import json
from collections import Counter
from pathlib import Path
from bve.se.ontology.targets import resolve_target

ROOT = Path('/home/djmann/projects/bve-b8')
PACKET = ROOT / 'research/se_target_query_alias_coverage_v1'
rows = []
for case in json.loads((PACKET / 'survey_population.json').read_text()):
    if case['kind'] != 'greek_orthography_proposal':
        continue
    original = resolve_target(case['authority_alias'])
    proposal = resolve_target(case['text'])
    rows.append({'id': case['id'], 'authority_alias': case['authority_alias'],
                 'proposal': case['text'], 'authority_record_key': case['authority_record_key'],
                 'source_status': original.status.value, 'source_entity': original.canonical_id,
                 'source_candidates': [e.canonical_id for e in original.candidates],
                 'agrees_with_source_symbol': original.canonical_symbol == case['authority_target_symbol'],
                 'source_basis': original.basis.model_dump(mode='json') if original.basis else None,
                 'entity_conflicts': [c.model_dump(mode='json') for c in original.entity.conflicts] if original.entity else [],
                 'entity_record_symbols': sorted({r.canonical_symbol for r in original.entity.source_records if r.canonical_symbol}) if original.entity else [],
                 'proposal_status': proposal.status.value, 'proposal_entity': proposal.canonical_id,
                 'whitespace_tokens': len(case['text'].split())})
result = {'baseline': '7cece53', 'rows': rows,
          'source_status_counts': dict(Counter(r['source_status'] for r in rows)),
          'source_symbol_agreement': sum(r['agrees_with_source_symbol'] for r in rows),
          'resolved_with_conflicts': sum(r['source_status'] == 'RESOLVED' and bool(r['entity_conflicts']) for r in rows),
          'resolved_multiple_record_symbols': sum(r['source_status'] == 'RESOLVED' and len(r['entity_record_symbols']) > 1 for r in rows),
          'resolved_symbol_disagreement_flags': sum(any(c['conflict_type'] == 'CANONICAL_SYMBOL_DISAGREEMENT' for c in r['entity_conflicts']) for r in rows),
          'proposal_status_counts': dict(Counter(r['proposal_status'] for r in rows)),
          'more_than_five_whitespace_tokens': sum(r['whitespace_tokens'] > 5 for r in rows),
          'note': 'Token count is descriptive only; parser uses its own segmentation. No candidate rule implemented or scored.',
          'live_runs': 0, 'holdout_probes': 0}
Path('/tmp/greek_authority_form_diagnosis.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({k:v for k,v in result.items() if k != 'rows'},indent=2))
