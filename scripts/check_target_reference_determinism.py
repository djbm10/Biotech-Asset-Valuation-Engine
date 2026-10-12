"""Hash-seed comparison of frozen synthetic intent/problem/plan/source requests."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

CODE = '''
import json, runpy, tempfile, socket
from datetime import date
from pathlib import Path
from unittest.mock import patch
import pytest
from bve.se.intent import parse_query, compile_intent, build_buyer_identity
from bve.se.discovery.query import compile_problem_queries
from bve.se.acquisition.runner import target_queries_for
from bve.se.acquisition import connectors as c
module=runpy.run_path("tests/se/test_target_reference_interface.py")
f=module["authority"]
rows=[]
with tempfile.TemporaryDirectory() as directory:
 m=pytest.MonkeyPatch(); g=f.__wrapped__(Path(directory),m); next(g)
 with patch.object(socket.socket,"connect",side_effect=AssertionError("network prohibited")):
  for case in module["CONTROLS"]["queries"]:
   i=parse_query(case["query"])
   if not case["intended_entity_ids"]:
    rows.append(i.model_dump(mode="json")); continue
   p=compile_intent(i,buyer=build_buyer_identity("Determinism",as_of_date=date(2026,10,12)))
   q=compile_problem_queries(p)
   requests={}
   for name in module["ORACLE"][0]["requests"]:
    captured=[]
    def capture(*args):
     captured.append(list(args)); return []
    connector=(c.CrossrefConferenceConnector(c.ConferenceVenue(source_family="conference_asco",publisher="Fixture",container_titles=["Fixture Journal"]),search_fn=capture) if name=="CrossrefConferenceConnector" else getattr(c,name)(search_fn=capture))
    connector.acquire(None,targets=target_queries_for(p),modality_terms=["antibody"],as_of_date=date(2026,10,12))
    requests[name]=captured
   rows.append([i.model_dump(mode="json"),p.model_dump(mode="json"),[x.model_dump(mode="json") for x in q],requests])
 try: next(g)
 except StopIteration: pass
 m.undo()
print(json.dumps(rows,sort_keys=True,default=str))
'''

if __name__ == '__main__':
    results = []
    for seed in ['0', '1', '42']:
        env = {**os.environ, 'PYTHONHASHSEED': seed, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': 'src'}
        run = subprocess.run([sys.executable, '-c', CODE], env=env, text=True,
                             capture_output=True, check=True)
        results.append({'seed': seed, 'sha256': hashlib.sha256(run.stdout.encode()).hexdigest()})
    result = {'results': results, 'identical': len({r['sha256'] for r in results}) == 1}
    Path('/tmp/target_reference_determinism.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
