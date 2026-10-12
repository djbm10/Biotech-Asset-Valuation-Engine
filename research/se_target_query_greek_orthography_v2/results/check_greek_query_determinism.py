"""Hash-seed check of the unchanged candidate using the frozen synthetic population."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

CODE = '''
import json,runpy,tempfile,socket
from datetime import date
from pathlib import Path
from unittest.mock import patch
import pytest
from bve.se.intent import parse_query,compile_intent,build_buyer_identity
from bve.se.discovery.query import compile_problem_queries
from bve.se.acquisition.runner import target_queries_for
from bve.se.ontology.query_targets import resolve_query_target
m=runpy.run_path("tests/se/test_query_greek_orthography.py")
rows=[]
with tempfile.TemporaryDirectory() as directory:
 p=pytest.MonkeyPatch();g=m["authority"].__wrapped__(Path(directory),p);next(g)
 with patch.object(socket.socket,"connect",side_effect=AssertionError("network prohibited")):
  for case in m["CONTROLS"]["raw_cases"]:
   result=resolve_query_target(case["query"])
   rows.append(result.model_dump(mode="json"))
  for case in m["CONTROLS"]["queries"]:
   intent=parse_query(case["query"])
   row={"intent":intent.model_dump(mode="json")}
   if intent.is_compilable:
    problem=compile_intent(intent,buyer=build_buyer_identity("Determinism",as_of_date=date(2026,10,12)))
    row["problem"]=problem.model_dump(mode="json")
    row["plans"]=[x.model_dump(mode="json") for x in compile_problem_queries(problem)]
    row["source_targets"]=[{"canonical_id":q.canonical_id,"aliases":list(q.aliases)} for q in target_queries_for(problem)]
   rows.append(row)
 try:next(g)
 except StopIteration:pass
 p.undo()
print(json.dumps(rows,sort_keys=True))
'''
results=[]
for seed in ['0','1','42']:
    env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':'src'}
    run=subprocess.run([sys.executable,'-c',CODE],env=env,text=True,capture_output=True,check=True)
    results.append({'seed':seed,'sha256':hashlib.sha256(run.stdout.encode()).hexdigest()})
result={'results':results,'identical':len({r['sha256'] for r in results})==1}
Path('/tmp/greek_v2_determinism.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
