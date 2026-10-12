import gc
import hashlib
import json
from pathlib import Path
from bve.se.evidence import human_poc as hp

ROOT=Path('/home/djmann/projects/bve-b8')
OUT=Path('/tmp/human_efficacy_context_safety_v1')
paths={'TAC01':Path('/home/djmann/se_runs/tac01_protoid_v1'),
       'mint5':Path('/home/djmann/se_runs/mint5_protoid_v1'),
       'AACR_accepted':Path('/home/djmann/se_runs/aacr_design'),
       'TAC01_regimen_accepted':Path('/home/djmann/se_runs/tac01_regimen_offline'),
       'H16':Path('/home/djmann/se_runs/heldout_h16_v4'),
       'H18':Path('/home/djmann/se_runs/heldout_h18_v4_rerun1'),
       'H19':Path('/home/djmann/se_runs/heldout_h19_v4')}
pool=[];unknown=[];manifest={}
for q,run in paths.items():
    file=run/'result.json'
    with file.open('rb') as f:manifest[q]={'path':str(file),'sha256':hashlib.file_digest(f,'sha256').hexdigest()}
    raw=json.loads(file.read_text());candidates={a['asset_id']:a for a in raw['candidates']}
    claims={c['claim_id']:c for c in raw['claims']};docs={d['document_id']:d for d in raw['source_documents']}
    poc={f['subject_id']:f for f in raw['facts'] if f['fact_type']=='human_poc_present' and f['value'] is True}
    for aid,f in poc.items():
        a=candidates[aid];names=[a['canonical_name'],*a['aliases']]
        witnesses=[]
        for cid in f['supporting_claim_ids']:
            c=claims[cid];doc=docs.get(c['source_document_id']);text=c['supporting_passage']
            statements=hp.efficacy_statements(text,asset_names=names,document_id=c['source_document_id']) if c['extraction_method']=='reported_efficacy_sentence' else []
            title='';snapshot_hash=None;source_context=None
            if doc and doc.get('snapshot_path') and Path(doc['snapshot_path']).exists():
                path=Path(doc['snapshot_path'])
                with path.open('rb') as stream:snapshot_hash=hashlib.file_digest(stream,'sha256').hexdigest()
                try:
                    data=json.loads(path.read_text());title=data.get('title','')
                    source_context=data.get('abstract')
                except (ValueError,AttributeError):pass
            witnesses.append({'claim':c,'document':doc,'source_title':title,'source_abstract':source_context,
                              'snapshot_sha256':snapshot_hash,'baseline_accepted':bool(statements),
                              'baseline_statements':[s.model_dump(mode='json') for s in statements]})
        pool.append({'run':q,'asset_id':aid,'name':a['canonical_name'],'asset_names':names,'fact':f,'witnesses':witnesses})
    if q in ['TAC01','mint5']:
        gates={g['subject_id']:g for g in raw['gate_evaluations']}
        # All target-PASS/human-PoC-UNKNOWN assets, not a score-driven subset.
        for aid,g in gates.items():
            status={d['requirement_id']:d['status'] for d in g['decisions']}
            if status.get('target.expression')!='PASS' or status.get('evidence.human_poc')!='UNKNOWN':continue
            a=candidates[aid]
            unknown.append({'run':q,'asset_id':aid,'name':a['canonical_name'],'gate':status,
                            'clinical_results':[r for r in raw['clinical_results'] if r['subject_id']==aid]})
    print(q,'existing facts',len(poc),flush=True)
    del raw,candidates,claims,docs
    gc.collect()
(OUT/'benchmark_population.json').write_text(json.dumps(pool,indent=2)+'\n')
(OUT/'unknown_asset_population.json').write_text(json.dumps(unknown,indent=2)+'\n')
(OUT/'input_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
survey=[]
for a in pool:
    for w in a['witnesses']:
        if w['baseline_accepted']:
            survey.append({'run':a['run'],'name':a['name'],'claim_id':w['claim']['claim_id'],
                           'title':w['source_title'],'passage':w['claim']['supporting_passage']})
(OUT/'accepted_witness_survey.json').write_text(json.dumps(survey,indent=2)+'\n')
print('Accepted claim witnesses to audit',len(survey),'target-PASS/PoC-UNKNOWN assets',len(unknown))
