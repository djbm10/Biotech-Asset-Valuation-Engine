"""Post-failure evidence only; never changes the formal R7 result."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path('/home/djmann/projects/bve-b8')
PACKET = ROOT / 'research/se_treatment_cohort_attribution_representation_v1'
code = '''
import json
from pathlib import Path
from bve.se.evidence.human_poc import efficacy_statements
rows=json.loads(Path("research/se_treatment_cohort_attribution_representation_v1/reader_baseline.json").read_text())
out=[]
for r in rows:
 actual=[s.model_dump(mode="json") for s in efficacy_statements(r["text"],asset_names=r["asset_names"],document_id=r["document_id"])]
 out.append({"id":r["id"],"actual":actual,"baseline":r["outputs"]})
print(json.dumps(out))
'''
reports = []
for seed in ('0', '1', '2'):
    env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH='src')
    rows = json.loads(subprocess.check_output(['python', '-c', code], cwd=ROOT, env=env, text=True))
    differences = []
    for row in rows:
        if row['actual'] != row['baseline']:
            differences.append(row)
    fields = set()
    for row in differences:
        if len(row['actual']) != len(row['baseline']):
            fields.add('statement_count')
        for a, b in zip(row['actual'], row['baseline']):
            fields.update(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    reports.append({
        'pythonhashseed': seed, 'reader_decisions_unchanged': sum(bool(r['actual']) == bool(r['baseline']) for r in rows),
        'exact_output_mismatches': len(differences), 'changed_fields': sorted(fields),
        'all_alias_differences_case_only': all(a['asset_name'].casefold() == b['asset_name'].casefold()
            for r in differences for a,b in zip(r['actual'],r['baseline'])),
        'differences': differences,
    })
def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()
protected = json.loads((PACKET/'protected_files.json').read_text())
runs = json.loads((PACKET/'run_baseline.json').read_text())
report = {
    'formal_R7': 'FAIL; unchanged, not rescored',
    'cause': 'Existing human_poc.py line 389 sorts a set of aliases by length only. Equal-length case variants inherit process-dependent hash iteration order.',
    'probes': reports,
    'protected_file_changes': [p for p,h in protected.items() if digest(ROOT/p)!=h],
    'original_result_changes': [name for name,r in runs.items() if digest(r['path'])!=r['sha256']],
    'original_result_files_verified': len(runs),
    'protected_files_verified': len(protected),
    'replays': 0,
    'interpretation': 'Decision booleans and all seven recorded runs are unchanged. Exact cross-process alias spelling is not deterministic in the pre-existing reader. This diagnosis does not repair the defect, change the frozen baseline, or turn the formal R7 failure into a pass.',
}
Path('/tmp/treatment_representation_result/neutrality_failure_diagnosis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'probes':[{k:v for k,v in r.items() if k!='differences'} for r in reports],
                  'protected_file_changes':report['protected_file_changes'],
                  'original_result_changes':report['original_result_changes']},indent=2))
