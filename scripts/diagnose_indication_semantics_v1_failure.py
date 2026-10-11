import json
from pathlib import Path
from bve.se.intent.parser import parse_query
from bve.se.intent.compiler import residual_indications
from bve.se.gates.evaluator import evaluate_indication
from bve.se.gates.engine import _requirement
from bve.se.schemas.contracts import NormalizedFact, RequirementOperator
R=Path('/home/djmann/projects/bve-b8')
O=R/'research/se_indication_semantics_v1'
pop=json.loads((O/'population.json').read_text())
out={}
for q in ['H11','H2','H13']:
    argv=pop[q]['invocation']['argv']; query=argv[argv.index('--query')+1]
    intent=parse_query(query)
    out[q]={'query':query,'spans':[s.model_dump(mode='json') for s in intent.spans],
            'residual_terms':intent.residual_terms,'requirements':residual_indications(intent)}
for q in ['H12','TAC01']:
    raw=json.loads((Path(pop[q]['run'])/'result.json').read_text())
    by_subject={}
    for f in raw['facts']:
        if f['fact_type']=='indication':
            by_subject.setdefault(f['subject_id'],[]).append(NormalizedFact.model_validate(f))
    if q=='H12':
        ids={r['asset_id'] for r in pop[q]['reference_records'] if r['name'] in ['Crovalimab','zilucoplan']}
    else:
        ids={g['subject_id'] for g in raw['gate_evaluations'] if any(d['requirement_id']=='strategy.indication' and d['status']=='PASS' for d in g['decisions'])}
    cases=[]
    for a in raw['candidates']:
        if a['asset_id'] not in ids: continue
        fs=by_subject.get(a['asset_id'],[])
        requested=['INDICATION:NCIT:C61233'] if q=='H12' else ['INDICATION:B_CELL_LYMPHOMA']
        after=evaluate_indication(_requirement('strategy.indication','indication',RequirementOperator.IN,requested),subject_id=a['asset_id'],facts=fs,gate_id='strategic_sandbox')
        if q=='H12' or after.status.value!='PASS':
            cases.append({'name':a['canonical_name'],'asset_id':a['asset_id'],
                          'conditions':[f.value for f in fs], 'after':after.model_dump(mode='json')})
    out[q]=cases
    del raw,by_subject
(O/'failure_diagnosis.json').write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
print(json.dumps(out,indent=2))
