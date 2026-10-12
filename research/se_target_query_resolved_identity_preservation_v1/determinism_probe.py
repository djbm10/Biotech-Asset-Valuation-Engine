import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

code = '''
import json, runpy, tempfile
from datetime import date
from pathlib import Path
import pytest
from bve.se.intent import parse_query, compile_intent, build_buyer_identity
from bve.se.discovery.query import compile_problem_queries
f=runpy.run_path("tests/se/test_resolved_target_identity.py")["authority"]
with tempfile.TemporaryDirectory() as directory:
 m=pytest.MonkeyPatch(); g=f.__wrapped__(Path(directory),m); next(g)
 i=parse_query("Find clinical-stage AXONE or AXTWO antibodies.")
 p=compile_intent(i,buyer=build_buyer_identity("Determinism",as_of_date=date(2026,10,12)))
 q=compile_problem_queries(p)
 print(json.dumps([i.model_dump(mode="json"),p.model_dump(mode="json"),[x.model_dump(mode="json") for x in q]],sort_keys=True))
 try: next(g)
 except StopIteration: pass
 m.undo()
'''
results=[]
for seed in ['0','1','42']:
 env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':'src'}
 r=subprocess.run([sys.executable,'-c',code],env=env,text=True,capture_output=True,check=True)
 results.append({'seed':seed,'sha256':hashlib.sha256(r.stdout.encode()).hexdigest()})
p=Path('/tmp/target_identity_determinism.json')
p.write_text(json.dumps({'results':results,'identical':len({r['sha256'] for r in results})==1},indent=2)+'\n')
print(p.read_text())
