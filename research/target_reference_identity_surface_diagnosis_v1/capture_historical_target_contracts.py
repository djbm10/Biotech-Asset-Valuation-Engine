"""Preserve source hash checks at their original implementation revisions."""
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path('/home/djmann/projects/bve-b8')
OUT = Path('/tmp/target_reference_identity_surface_diagnosis_v1')
rows = []
for folder in ['se_indication_compilation_v3', 'se_indication_gate_semantics_v3']:
    packet = ROOT / 'research' / folder
    acceptance = json.loads((packet / 'acceptance.json').read_text())
    population = json.loads((packet / 'population.json').read_text())
    commit = subprocess.check_output(['git', 'rev-parse', acceptance['implementation']],
                                     cwd=ROOT, text=True).strip()
    raw = subprocess.check_output(['git', 'archive', '--format=tar', commit, 'src'], cwd=ROOT)
    archive_name = folder + '_implementation_src.tar.gz'
    compressed = gzip.compress(raw, mtime=0)
    (OUT / archive_name).write_bytes(compressed)
    checks = []
    allowed = population.get('allowed_source', [])
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for path, expected in population['protected_source'].items():
            if path in allowed:
                continue
            assert path.startswith('src/'), path
            stream = archive.extractfile(path)
            actual = hashlib.sha256(stream.read()).hexdigest()
            checks.append({'path': path, 'expected': expected, 'actual': actual,
                           'matches': actual == expected})
    rows.append({'milestone': folder, 'implementation': commit, 'archive': archive_name,
                 'archive_sha256': hashlib.sha256(compressed).hexdigest(),
                 'frozen_artifacts': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in sorted(packet.rglob('*')) if p.is_file()},
                 'checks': checks})
result = {'status': 'diagnostic historical source verification; no existing scorer or label changed',
          'milestones': rows}
(OUT / 'historical_source_verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps([{'milestone': r['milestone'], 'checks': len(r['checks']),
                   'matches': sum(c['matches'] for c in r['checks'])} for r in rows]))
assert all(c['matches'] for r in rows for c in r['checks'])
