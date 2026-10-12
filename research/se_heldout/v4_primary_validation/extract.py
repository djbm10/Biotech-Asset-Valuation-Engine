import hashlib
import json
import shutil
from pathlib import Path
from bve.se.pipeline import SESearchResult
from bve.se.reporting.shortlist import build_shortlist

OUT = Path('/tmp/heldout_v4_primary_validation')
BASE = Path('/home/djmann/se_runs')
RUNS = {'H16': 'heldout_h16_v4', 'H17': 'heldout_h17_v4_rerun1',
        'H18': 'heldout_h18_v4_rerun1', 'H19': 'heldout_h19_v4', 'H20': 'heldout_h20_v4'}
manifest = {'excluded_interrupted_runs': ['heldout_h17_v4', 'heldout_h18_v4'], 'runs': {}}
blind = {}
for qid, name in RUNS.items():
    root = BASE / name
    evidence = OUT / 'evidence' / qid
    evidence.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for rel in ['result.json', 'shortlist.json', 'summary.json', 'run_manifest.json',
                'problem.yaml', 'invocation.json', 'reproduce.sh', 'logs/run.log',
                'custody/corpus_seal.json', 'custody/corpus_manifest.json', 'custody/source_health.json']:
        p = root / rel
        if not p.exists():
            continue
        hashes[rel] = {'sha256': hashlib.file_digest(p.open('rb'), 'sha256').hexdigest(),
                       'bytes': p.stat().st_size}
        if rel not in ['result.json', 'shortlist.json', 'logs/run.log', 'custody/corpus_manifest.json']:
            dst = evidence / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dst)
    log = (root / 'logs/run.log').read_text()
    manifest['runs'][qid] = {'directory': str(root), 'files': hashes}
    if not (root / 'result.json').exists():
        shutil.copyfile(root / 'logs/run.log', evidence / 'refusal.log')
        blind[qid] = {'outcome': 'REFUSED', 'reason': next(l.strip() for l in log.splitlines() if 'blocked:' in l), 'rows': []}
        continue
    raw = json.loads((root / 'result.json').read_text())
    emitted = json.loads((root / 'shortlist.json').read_text())
    result = SESearchResult.model_validate(raw)
    complete = build_shortlist(result, limit=100_000)
    assert [e.asset_id for e in complete.entries[:20]] == [e['asset_id'] for e in emitted['entries']]
    assert [e.name for e in complete.entries[:20]] == [e['name'] for e in emitted['entries']]
    (evidence / 'emitted_top20.json').write_text(json.dumps(emitted['entries'], indent=2) + '\n')
    blind[qid] = {'outcome': 'RESULT', 'rows': [{'position': e['position'], 'asset_id': e['asset_id'], 'name': e['name']} for e in emitted['entries']]}
    candidates = {a['asset_id']: a for a in raw['candidates']}
    all_rows = [{'asset_id': e.asset_id, 'name': e.name, 'canonical_name': candidates[e.asset_id]['canonical_name'], 'aliases': candidates[e.asset_id]['aliases']} for e in complete.entries]
    (evidence / 'all_shortlist_names.json').write_text(json.dumps(all_rows, indent=2) + '\n')
    top_ids = {e['asset_id'] for e in emitted['entries']}
    hpoc = [f for f in raw['facts'] if f['subject_id'] in top_ids and f['fact_type'] == 'human_poc_present']
    claim_ids = {c for f in hpoc for c in f['supporting_claim_ids']}
    claims = [c for c in raw['claims'] if c['claim_id'] in claim_ids]
    (evidence / 'human_poc_audit_input.json').write_text(json.dumps({'facts': hpoc, 'claims': claims}, indent=2) + '\n')
    print(qid, 'top20 identity/order matches emitted artifact', 'human_poc facts', len(hpoc))
(OUT / 'blind_top20.json').write_text(json.dumps(blind, indent=2) + '\n')
(OUT / 'input_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
