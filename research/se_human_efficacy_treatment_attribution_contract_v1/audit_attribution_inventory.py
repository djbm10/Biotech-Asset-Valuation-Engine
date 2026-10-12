import json,hashlib,re
from pathlib import Path
ROOT=Path('/home/djmann/projects/bve-b8');OUT=Path('/tmp/human_efficacy_treatment_attribution_contract_v1');OUT.mkdir(exist_ok=True)
rows=json.loads((ROOT/'research/se_human_efficacy_boundary_diagnosis_v2/witness_register.json').read_text())
manifest=json.loads((ROOT/'research/se_human_efficacy_context_safety_v1/input_manifest.json').read_text())
all_rows=[];registries={};run_audit={}
for run,m in manifest.items():
 wanted=[r for r in rows if r['run']==run]
 if not wanted:continue
 path=Path(m['path']);blob=path.read_bytes();assert hashlib.sha256(blob).hexdigest()==m['sha256'];data=json.loads(blob);del blob
 candidates={a['asset_id']:a for a in data['candidates']};docs={d['document_id']:d for d in data['source_documents']}
 pmids={re.search(r'/([0-9]+)/?',r['source']['source_url']).group(1) for r in wanted}
 reg={}
 for doc in data['source_documents']:
  if doc['document_type']!='trial_registry_record' or not doc.get('snapshot_path'):continue
  p=Path(doc['snapshot_path']);raw=p.read_bytes();s=json.loads(raw);proto=s.get('protocolSection',s)
  ident=proto.get('identificationModule',{});arms=proto.get('armsInterventionsModule',{});refs=proto.get('referencesModule',{})
  reg[doc['document_id']]={'document':doc,'snapshot_sha256':hashlib.sha256(raw).hexdigest(),'trial_id':ident.get('nctId'),'identification':ident,'arms_interventions':arms,'references':refs,'snapshot_top_level_keys':list(s),'has_results_section':'resultsSection' in s,'result_section':s.get('resultsSection')}
 registries[run]=reg
 for row in wanted:
  aid=row['claim']['subject_id'];candidate=candidates[aid];pmid=re.search(r'/([0-9]+)/?',row['source']['source_url']).group(1)
  ncts=sorted(set(re.findall(r'\bNCT\d{8}\b',row['source_abstract'],re.I)))
  mentions=[v for v in data['identity_mentions'] if v['mention_id'] in set(candidate['mention_ids'])]
  connected={v['source_document_id'] for v in mentions}|{c['source_document_id'] for c in data['claims'] if c['subject_id']==aid}
  linked=[];related=[];protocol_links=[]
  for did,r in reg.items():
   refs=[ref for ref in r['references'].get('references',[]) if str(ref.get('pmid',''))==pmid]
   ident=r['identification'];ids=[ident.get('orgStudyIdInfo',{}).get('id'),ident.get('acronym')]+[z.get('id') for z in ident.get('secondaryIdInfos',[])]
   matches=[v for v in ids if v and len(v)>=5 and re.search(r'(?<![A-Za-z0-9])'+re.escape(v)+r'(?![A-Za-z0-9])',row['source_title']+' '+row['source_abstract'],re.I)]
   if matches:protocol_links.append({'document_id':did,'trial_id':r['trial_id'],'exact_identifier_matches':matches})
   if r['trial_id'] in ncts or refs:linked.append({'document_id':did,'trial_id':r['trial_id'],'link_basis':'publication_nct' if r['trial_id'] in ncts else 'registry_pubmed_reference','reference_entries':refs})
   if did in connected or r['trial_id'] in candidate['trial_ids']:related.append(did)
  all_rows.append({'id':row['id'],'run':run,'name':row['name'],'candidate':candidate,'publication_pmid':pmid,'publication_trial_ids':ncts,'direct_registry_links':linked,'publication_protocol_links':protocol_links,'other_human_poc_claims':[c for c in data['claims'] if c['subject_id']==aid and c['predicate']=='human_poc_present' and c['claim_id']!=row['claim']['claim_id']],'candidate_related_registry_documents':related,'identity_edges':[e for e in data.get('identity_edges',[]) if e['asset_id']==aid],'clinical_results':[c for c in data.get('clinical_results',[]) if c['subject_id']==aid],'cohort_assignments':[c for c in data.get('cohort_assignments',[]) if c['subject_id']==aid],'trial_reattributions':[x for x in data.get('trial_reattributions',[]) if aid in [x.get('from_asset_id'),x.get('to_asset_id')]]})
 run_audit[run]={'path':str(path),'sha256':m['sha256'],'source_documents':len(docs),'registry_documents_scanned':len(reg),'selected_rows':len(wanted),'registry_with_arm_groups':sum(bool(r['arms_interventions'].get('armGroups')) for r in reg.values()),'registry_with_intervention_arm_labels':sum(any(i.get('armGroupLabels') for i in r['arms_interventions'].get('interventions',[])) for r in reg.values()),'registry_with_results_section':sum(r['has_results_section'] for r in reg.values())}
 print(run,run_audit[run],flush=True)
 del data
# Retain all source inventory metadata, detailed protocols only for candidate connections / exact links.
kept={}
for run,reg in registries.items():
 wanted={d['document_id'] for x in all_rows if x['run']==run for d in x['publication_protocol_links']}|{d for x in all_rows if x['run']==run for d in x['candidate_related_registry_documents']}|{d['document_id'] for x in all_rows if x['run']==run for d in x['direct_registry_links']}
 kept[run]={k:v for k,v in reg.items() if k in wanted}
for name,value in [('candidate_evidence.json',all_rows),('structured_registry_evidence.json',kept),('capture_inventory.json',run_audit)]:
 (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print('DONE',len(all_rows),sum(len(r) for r in kept.values()),flush=True)
