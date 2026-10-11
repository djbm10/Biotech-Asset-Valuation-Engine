from pathlib import Path
from collections import Counter,defaultdict
import hashlib,json
from bve.se.gates.engine import _requirement
from bve.se.gates.evaluator import evaluate_indication
from bve.se.ontology.indication_compatibility import compatibility
from bve.se.schemas.contracts import NormalizedFact,RequirementOperator

R=Path('/home/djmann/projects/bve-b8');O=R/'research/se_indication_gate_semantics_v3';P=json.loads((O/'population.json').read_text());I='strategy.indication'
def decide(requested,facts,aid):
 return evaluate_indication(_requirement(I,'indication',RequirementOperator.IN,requested),subject_id=aid,facts=facts,gate_id='strategic_sandbox').model_dump(mode='json')
result={'controls':[],'runs':{},'references':[],'review_sample':[],'criteria':{}}
for c in P['controls']:
 fs=[NormalizedFact(fact_id=f'f:{n}',subject_id='a',fact_type='indication',value=v,confidence=.95,supporting_claim_ids=[f'c:{n}']) for n,v in enumerate(c['observed'])]
 result['controls'].append({**c,'actual':decide(c['requested'],fs,'a')['status']})
for q,run in P['runs'].items():
 path=Path(run['result']);assert hashlib.sha256(path.read_bytes()).hexdigest()==run['sha256']
 raw=json.loads(path.read_text());facts=defaultdict(list)
 for f in raw['facts']:
  if f['fact_type']=='indication':facts[f['subject_id']].append(NormalizedFact.model_validate(f))
 req=next(c['requested'] for c in P['cases'] if c['query']==q);refs={c['asset_id']:c for c in P['cases'] if c['query']==q and c['reference']}
 transitions=Counter();newpasses=[];statuses=Counter();preserved=True;onlybefore=onlyafter=0;gatecount=0
 for gate in raw['gate_evaluations']:
  aid=gate['subject_id'];old=next((d for d in gate['decisions'] if d['requirement_id']==I),None)
  if old is None:continue
  gatecount+=1;decision=decide(req,facts[aid],aid);statuses[decision['status']]+=1;transitions[old['status']+'->'+decision['status']]+=1
  if old['status']=='PASS' and decision['status']!='PASS':preserved=False
  otherfails=[d for d in gate['decisions'] if d['requirement_id']!=I and d['status']=='FAIL']
  onlybefore+=old['status']=='FAIL' and not otherfails;onlyafter+=decision['status']=='FAIL' and not otherfails
  if aid in refs:
   result['references'].append({'query':q,'name':refs[aid]['name'],'asset_id':aid,'old':old['status'],'actual':decision['status'],'historical_only_excluded':refs[aid]['historical_only_indication_exclusion'],'gate_rankable':not otherfails})
  if decision['status']=='PASS' and old['status']!='PASS':
   witnesses=[]
   for f in facts[aid]:
    for v in f.value if isinstance(f.value,list) else [f.value]:
     for requested in req:
      witness=compatibility(requested,v)
      if witness:witnesses.append({**witness,'fact_id':f.fact_id,'claims':f.supporting_claim_ids})
   assert witnesses
   newpasses.append({'asset_id':aid,'reference':aid in refs,'witnesses':witnesses})
 selected={}
 for a in newpasses:
  for w in a['witnesses']:
   key=(str(w['requested']),str(w['observed']),w['fact_id']);selected.setdefault(key,{'query':q,'asset_id':a['asset_id'],'witness':w})
 unique={}
 for key,row in sorted(selected.items()):unique.setdefault((key[0],key[1]),row)
 result['review_sample'].extend(list(unique.values())[:5])
 for a in newpasses:
  if a['reference']:result['review_sample'].extend({'query':q,'asset_id':a['asset_id'],'witness':w} for w in a['witnesses'])
 result['runs'][q]={'statuses':dict(statuses),'transitions':dict(transitions),'old_pass_preserved':preserved,'indication_only_before':onlybefore,'indication_only_after':onlyafter,'new_pass_assets':len(newpasses),'new_pass_witnesses':newpasses,'gate_count':gatecount}
 print(q,dict(transitions),flush=True)
 del raw,facts
C=result['criteria'];controls=result['controls'];passed=lambda names:all(c['actual']==c['expected'] for c in controls if c['id'] in names)
C['V3-G1']=all(v['statuses'].get('FAIL',0)==0 for v in result['runs'].values())
C['V3-G2']=sum(r['historical_only_excluded'] for r in result['references'])==33 and all(r['actual'] in ('PASS','UNKNOWN') for r in result['references'] if r['historical_only_excluded'])
C['V3-G3']=all(c['actual']=='PASS' for c in controls if c['expected']=='PASS')
C['V3-G4']=passed({'subtype','subtype_exact','parent_direction','broader'})
C['V3-G5']=passed({'multi_match','multi_reverse'})
C['V3-G6']=all(c['actual']=='UNKNOWN' for c in controls if c['expected']=='UNKNOWN')
C['V3-G7']='PENDING_MANUAL_REVIEW'
C['V3-G8']=result['runs']['TAC01']['old_pass_preserved'] and passed({'jcar'}) and result['runs']['mint5']['gate_count']==0
manifest=json.loads((O/'manifest.json').read_text())
C['V3-G9']=all(hashlib.sha256((R/p).read_bytes()).hexdigest()==h for p,h in manifest.items()) and all(hashlib.sha256((R/p).read_bytes()).hexdigest()==h for p,h in P['protected_source'].items() if p not in P['allowed_source'])
C['V3-G10']='PENDING_QUALITY'

# Fresh live compilation population; historical compilation artifacts are read-only.
from bve.se.intent.parser import parse_query
from bve.se.intent.compiler import residual_indications
compilation=json.loads((R/'research/se_indication_compilation_v3/population.json').read_text())
compiled=[{'id':case['id'],'expected':case['expected'],'actual':residual_indications(parse_query(case['query']))} for case in compilation['cases']]
result['compilation_controls']=compiled
C['V3-G9']=C['V3-G9'] and all(x['actual']==x['expected'] for x in compiled)
C['V3-G9']=C['V3-G9'] and all(hashlib.sha256((R/path).read_bytes()).hexdigest()==h for path,h in P['preserved_experiments'].items())
import subprocess
C['V3-G9']=C['V3-G9'] and all((R/path).read_bytes()==subprocess.check_output(['git','show',f'148b71e:{path}'],cwd=R) for path in P['allowed_source'])
audit=json.loads((O/'authority_audit.json').read_text())
oracle={c['id']:c for c in audit['controls']}
C['V3-G3']=C['V3-G3'] and all(oracle[c['id']]['authority_expected']=='PASS' and any(w['supported'] for w in oracle[c['id']]['proofs']) for c in controls if c['expected']=='PASS')

(O/'score.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
print(json.dumps(C),flush=True)
