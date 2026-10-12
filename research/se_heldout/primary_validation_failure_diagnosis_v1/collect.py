"""Read-only probes of frozen primary validation; no search, replay or implementation."""
import gc
import hashlib
import json
import re
import shutil
from pathlib import Path
from bve.se.evidence import human_poc as hp
from bve.se.intent.parser import parse_query, _strip_target_affixes, _tokenize
from bve.se.ontology.targets import get_resolver, resolve_target
from bve.se.ontology.drug_modality import modality_authority
from bve.se.ontology.records import EntityType, normalize_lookup_key

ROOT=Path('/home/djmann/projects/bve-b8')
PACKET=ROOT/'research/se_heldout/v4_primary_validation'
OUT=Path('/tmp/primary_validation_failure_diagnosis_v1')
labels=json.loads((PACKET/'labels.json').read_text())
inputs=json.loads((PACKET/'input_manifest.json').read_text())
scores=json.loads((PACKET/'score.json').read_text())
resolver=get_resolver()
authority=modality_authority()
probes={}
for q, phrase, target in [('H17','IL-4Rα','IL4R'),('H20','factor XI','F11')]:
    inv=json.loads((PACKET/'evidence'/q/'invocation.json').read_text())
    print(q,'invocation keys',list(inv))
    argv=inv.get('argv',inv.get('arguments',[]))
    if isinstance(argv,str):
        raise ValueError('need structured argv')
    query=argv[argv.index('--query')+1]
    intent=parse_query(query)
    result=resolve_target(phrase)
    entity=resolver.get('TARGET:'+target)
    probes[q]={'original_query':query,'query_after_existing_affix_normalization':_strip_target_affixes(query),
               'tokens':_tokenize(_strip_target_affixes(query)), 'exact_phrase':phrase,
               'lookup_key':normalize_lookup_key(phrase),'resolution':result.model_dump(mode='json') if result else None,
               'intent':intent.model_dump(mode='json'), 'authority_entity':entity.model_dump(mode='json') if entity else None,
               'scope':'Only exact original query parsed offline, original target phrase resolved, intended entity metadata read. No alternate query or live engine run.'}
(OUT/'target_recognition_probes.json').write_text(json.dumps(probes,indent=2)+'\n')

rows={}; false_audits={}; identity={}; missing={}; doc_scan={}
for q in ['H16','H18','H19']:
    run=Path(inputs['runs'][q]['directory'])
    raw=json.loads((run/'result.json').read_text())
    cands={a['asset_id']:a for a in raw['candidates']}
    gates={g['subject_id']:g for g in raw['gate_evaluations']}
    claims={c['claim_id']:c for c in raw['claims']}
    docs={d['document_id']:d for d in raw['source_documents']}
    facts={}
    for f in raw['facts']:facts.setdefault(f['subject_id'],[]).append(f)
    mentions={m['mention_id']:m for m in raw['identity_mentions']}
    allshort=json.loads((PACKET/'evidence'/q/'all_shortlist_names.json').read_text())
    positions={e['asset_id']:i for i,e in enumerate(allshort,1)}
    def candidate_record(a):
        aid=a['asset_id']
        ff=[f for f in facts.get(aid,[]) if f['fact_type'] in ['modality_id','construct_target_set','human_poc_present','identity_valid']]
        cid={c for f in ff for c in f['supporting_claim_ids']}
        return {'candidate':a,'sets':{k:aid in raw[k] for k in ['eligible_asset_ids','excluded_asset_ids','unresolved_asset_ids','low_support_asset_ids']},
                'gate':gates.get(aid),'all_shortlist_position':positions.get(aid),'diagnostic_facts':ff,
                'supporting_claims':[claims[c] for c in cid if c in claims],
                'identity_mentions':[mentions[m] for m in a['mention_ids'] if m in mentions],
                'identity_edges':[e for e in raw['identity_edges'] if e['asset_id']==aid],
                'identity_merges':[e for e in raw['identity_merges'] if aid in e['source_asset_ids'] or e['target_asset_id']==aid]}
    rows[q]=[{**l,**candidate_record(cands[l['asset_id']])} for l in labels['queries'][q]['rows']]
    false_ids=['asset:8866bafec6e43f4b49da'] if q=='H18' else ['asset:cf362b6bc18a7577433e'] if q=='H19' else []
    false_audits[q]=[]
    for aid in false_ids:
        a=cands[aid]; names=[a['canonical_name'],*a['aliases']]
        for c in raw['claims']:
            if c['subject_id']!=aid or c['predicate']!='human_poc_present':continue
            s=c['supporting_passage'];d=docs[c['source_document_id']]
            snap=json.loads(Path(d['snapshot_path']).read_text())
            accepted=hp.efficacy_statements(s,asset_names=names,document_id=d['document_id'])
            trace={'sentence_length':len(s),'max_sentence_chars':hp._MAX_SENTENCE_CHARS,
                   'endpoint_term':hp._efficacy_term(s),'human_term':hp._contains(s,hp._HUMAN_TERMS),
                   'numeric_token':hp._VALUE.search(s).group(0) if hp._VALUE.search(s) else None,
                   'nonhuman_veto':hp._contains(s,hp._NONHUMAN_TERMS),'unreported_veto':hp._contains(s,hp._UNREPORTED_TERMS),
                   'non_efficacy_veto':hp._contains(s,hp._NON_EFFICACY_TERMS),
                   'accepted_statements':[x.model_dump() for x in accepted]}
            assert accepted, (q,'frozen false citation no longer accepted')
            false_audits[q].append({'asset_id':aid,'name':a['canonical_name'],'claim':c,'document':d,'source_snapshot':snap,'acceptance_trace':trace})
            dest=OUT/'source_evidence'/q
            dest.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(d['snapshot_path'],dest/Path(d['snapshot_path']).name)
    identity[q]=[]
    for l in labels['queries'][q]['rows']:
        if l['label']!='DUPLICATE':continue
        a=cands[l['asset_id']]
        name_resolutions=[]
        for name in [a['canonical_name'],*a['aliases']]:
            rr=resolver.resolve(name,EntityType.DRUG)
            name_resolutions.append({'name':name,'resolution_status':rr.status.value,'canonical_id':rr.canonical_id,
                                    'basis':rr.basis.model_dump(mode='json') if rr.basis else None,
                                    'identifier_resolution':resolver.resolve_identifier(name,EntityType.DRUG),
                                    'authority_identifies_drug':authority.identifies_drug(name)})
        identity[q].append({'position':l['position'],'name':l['name'],'resolutions':name_resolutions,
                            'identity_edges':[e for e in raw['identity_edges'] if e['asset_id']==a['asset_id']]})
    if q=='H19':
        patterns={'datopotamab deruxtecan':r'datopo|dato.?dxd|ds.?1062','ESG401':r'esg[\s-]?401','BL-M02D1':r'bl[\s-]?m02d1'}
        missing[q]={ref:[candidate_record(a) for a in raw['candidates'] if any(re.search(pat,x,re.I) for x in [a['canonical_name'],*a['aliases']])] for ref,pat in patterns.items()}
        scan={ref:[] for ref in patterns}
        for d in raw['source_documents']:
            p=Path(d['snapshot_path']) if d.get('snapshot_path') else None
            if not p or not p.exists():continue
            text=p.read_text()
            for ref,pat in patterns.items():
                hit=re.search(pat,text,re.I)
                if hit:scan[ref].append({'document_id':d['document_id'],'source_url':d['source_url'],'snapshot_path':str(p),'context':text[max(0,hit.start()-120):hit.end()+240]})
        doc_scan[q]=scan
        (OUT/'search_attempts_H19.json').write_text(json.dumps(raw['search_attempts'],indent=2)+'\n')
        # Preserve the source records for the two generic medication strings and modality error.
        selected=[a for a in raw['candidates'] if a['canonical_name'] in ['Rescue Medication','Rescue Medications','Datopotamab deruxtecan']]
        dids={mentions[m]['source_document_id'] for a in selected for m in a['mention_ids'] if m in mentions}
        dids.update(c['source_document_id'] for a in selected for f in facts.get(a['asset_id'],[]) if f['fact_type']=='modality_id' for i in f['supporting_claim_ids'] if (c:=claims.get(i)))
        dest=OUT/'source_evidence'/'H19';dest.mkdir(parents=True,exist_ok=True)
        for did in dids:
            d=docs.get(did)
            if d and d.get('snapshot_path'):shutil.copyfile(d['snapshot_path'],dest/Path(d['snapshot_path']).name)
    print(q,'artifact trace complete')
    del raw,cands,gates,claims,docs,facts,mentions
    gc.collect()
for name,data in [('row_traces.json',rows),('false_human_poc_traces.json',false_audits),('duplicate_identity_traces.json',identity),('missing_reference_traces.json',missing),('sealed_document_reference_scan.json',doc_scan)]:
    (OUT/name).write_text(json.dumps(data,indent=2)+'\n')
print('Diagnosis artifact collection complete; no engine execution.')
