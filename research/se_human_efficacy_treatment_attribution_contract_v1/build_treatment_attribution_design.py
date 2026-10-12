import json,hashlib,re,sys
from pathlib import Path
ROOT=Path('/home/djmann/projects/bve-b8');OUT=Path('/tmp/human_efficacy_treatment_attribution_contract_v1')
rows=json.loads((ROOT/'research/se_human_efficacy_boundary_diagnosis_v2/witness_register.json').read_text())
relations={x['id']:x for x in json.loads((ROOT/'research/se_human_efficacy_quantity_binding_contract_v1/relation_population.json').read_text())}
failed={x['id'] for x in json.loads((ROOT/'research/se_human_efficacy_quantity_binding_contract_v1/offline_result.json').read_text())['full_chain_target_failures']}
ce={x['id']:x for x in json.loads((OUT/'candidate_evidence.json').read_text())};registry=json.loads((OUT/'structured_registry_evidence.json').read_text())
# Manual scientific annotations of named captured passages, not admission patterns.
components={64:['dupilumab','ivermectin'],26:['venetoclax','azacitidine','ivosidenib'],62:['relugolix','estradiol','norethindrone acetate'],69:['glecaprevir','pibrentasvir'],78:['bevacizumab','first-line chemotherapy (agents unspecified)'],80:['lopinavir/ritonavir OR atazanavir/ritonavir OR fosamprenavir/ritonavir','TDF/FTC OR ABC/3TC'],92:['doravirine','lamivudine','tenofovir disoproxil fumarate'],11:['bevacizumab add-on','platinum-based chemotherapy background']}
reasons={26:'Exact induction subgroup received VEN/AZA/IVO. The 3 CRs belong to that regimen; no VEN-specific or incremental contrast in this witness. Other IVO-only/subgroup results must not transfer.',42:'PET30 denotes a PET response assessment at day 30, not administered treatment. CAR-T elsewhere in the paper cannot be renamed PET30.',54:'though is a conjunction in a CAR-T meta-analysis, not a therapeutic intervention or accepted treatment alias.',62:'Source defines relugolix-CT as relugolix 40 mg + estradiol 1 mg + norethindrone acetate 0.5 mg. Captured NCT04714554 separately lists Relugolix/E2/NETA FDC (Rel-CT) and Relugolix (MVT-601/TAK-385), and is a PK interaction study, not this efficacy cohort.',69:'Observed SVR is assigned to G/P as a combination. Neither component has a separately attributed outcome here.',78:'The bevacizumab arm received first-line chemotherapy too. Its 12.0-month PFS belongs to the arm/regimen comparison with anti-EGFR plus chemotherapy, not an isolated bevacizumab effect or a with/without-bevacizumab contrast.',80:'Response proportions compare ABC/3TC versus TDF/FTC across pooled boosted-PI regimens. No individual PI-stratified result or same-asset result-group bridge is captured.',92:'89% belongs to DOR/3TC/TDF; 93% belongs to BIC/F/TAF. 3TC identifies a received component, not a separately estimated component outcome.',64:'Combination receipt is explicit; the remission statement has no numerical efficacy result. The token 4/13 is receptor nomenclature.',97:'Human myotubes are laboratory material. No clinical patient receipt/result edge exists.',109:'Simulated patient trajectories and discount rate do not establish observed clinical receipt or efficacy.'}
audit=[]
for r in rows:
 sid=r.get('survey_id');rel=relations[r['id']];ev=ce.get(r['id'],{});unresolved=r['id'] in failed
 receipt='CERTIFIED';owner='CERTIFIED';basis='A_EXPLICIT_PROSE';first='NONE';classes=['A'];scope='SINGLE_NAMED_TREATMENT';reason='Explicit named treatment and outcome cohort in the same assertion; preserve the captured scope.'
 if r['name']=='Lamivudine' and sid==92:basis='A_ACCEPTED_ALIAS'
 if sid in [64,26,62,69,78,80,92]:
  owner='UNKNOWN';basis='D_REGIMEN';first='REGIMEN_RESULT_OWNERSHIP';classes=['D'];scope='REGIMEN_COMPONENT';reason=reasons[sid]
  if sid==80:
   scope='POOLED_REGIMEN';classes=['C','D','G']
   if r['name'].casefold() in ['atazanavir','lopinavir','fosamprenavir']:
    receipt='UNKNOWN';first='RESULT_COHORT_TO_SPECIFIC_PI_ARM'
   else:
    reason+=' Receipt is supported only as common ritonavir boosting or the ABC/3TC backbone component; no component-specific efficacy ownership follows.'
  if sid==62:classes=['D','E'];reason=reasons[sid]
 if sid in [42,54]:receipt=owner='UNKNOWN';basis='G_UNSUPPORTED';first='CANDIDATE_IS_NOT_A_TREATMENT';classes=['E','G'];scope='NON_TREATMENT';reason=reasons[sid]
 if sid in [97,109]:receipt=owner='UNKNOWN';basis='G_UNSUPPORTED';first='NO_ACTUAL_CLINICAL_COHORT';classes=['G'];scope='NONCLINICAL';reason=reasons[sid]
 if sid==11:
  scope='EXPLICIT_ADD_ON_COMPARISON';reason='Source explicitly compares with/without bevacizumab on first-line platinum-based chemotherapy and assigns response rates by group. Certify the named add-on arm only, retaining observational/add-on context; no monotherapy or causal incremental-effect assertion.'
 # Data near an asset is recorded separately from a verified study/result bridge.
 links=[]
 for link in ev.get('direct_registry_links',[]):
  reg=registry[r['run']][link['document_id']]
  valid=link['link_basis']=='publication_nct' or any(v.get('type')=='DERIVED' for v in link['reference_entries'])
  aliases={x.casefold() for x in r['asset_names']}
  matches=[i for i in reg['arms_interventions'].get('interventions',[]) if any(str(n).casefold() in aliases for n in [i.get('name',''),*i.get('otherNames',[])])]
  links.append({'link':link,'study_link_usable':valid,'source_document':reg['document'],'snapshot_sha256':reg['snapshot_sha256'],'identification':reg['identification'],'arms_interventions':reg['arms_interventions'],'accepted_name_interventions':matches,'result_to_arm_record_present':False,'interpretation':('Valid study link; result-group and same-asset intervention proof still required.' if valid else 'BACKGROUND citation only; not a study/result ownership link.')})
 record={'id':r['id'],'run':r['run'],'candidate_asset':r['name'],'asset_id':r.get('claim',{}).get('subject_id'),'explicit_names_aliases':r['asset_names'],'exact_name_spans':r['current_predicates']['asset_mentions'],'previous_unresolved_14':unresolved,'efficacy_passage':r['exact_passage'],'patient_cohort_reference':rel['patient_cohort_span'],'source':r.get('source'),'source_title':r.get('source_title'),'source_abstract':r.get('source_abstract'),'source_snapshot_sha256':r.get('snapshot_sha256'),'source_spans':{k:rel[k] for k in ['candidate_mention_span','asset_treatment_span','patient_cohort_span','efficacy_outcome_span','numerical_spans']},'publication_trial_ids':ev.get('publication_trial_ids',[]),'trial_and_arm_evidence':links,'candidate_related_registry_document_ids':ev.get('candidate_related_registry_documents',[]),'lexical_protocol_id_leads':ev.get('publication_protocol_links',[]),'lexical_leads_accepted_as_study_bridge':False,'clinical_results_available':len(ev.get('clinical_results',[])),'regimen_components':components.get(sid,[]),'categories':classes,'proposed_edge_basis':basis,'receipt_status':receipt,'efficacy_owner_status':owner,'treatment_scope':scope,'first_missing_boundary':first,'content_expected_unchanged':r['frozen_content_positive'],'expected_human_poc':'PASS' if owner=='CERTIFIED' and r['frozen_content_positive'] else 'UNKNOWN','reason':reason,'four_way_recovery_bucket':'UNSUPPORTED_ASSET_SPECIFIC_EFFICACY' if unresolved else None,'other_human_poc_claims_available':len(ev.get('other_human_poc_claims',[])),'other_claims_used_to_replace_witness':False,'annotation_method':'Manual source-grounded evidence audit; proposed runtime text extraction is not implemented.'}
 audit.append(record)
legacy=json.loads((ROOT/'research/se_human_efficacy_context_safety_v1/existing_test_population.json').read_text())
neg=[]
for x in legacy:
 if x['route']!='prose' or x['baseline_outputs']:continue
 tests=' '.join(x['tests']);boundary='EXISTING_CONTENT_EXCLUSION'
 if 'regimen_lists' in tests or any(z in tests for z in ['combination','second_named_asset']):boundary='REGIMEN_COMPONENT_OR_MULTIPLE_TREATMENTS'
 if 'unnamed_asset' in tests:boundary='NO_PRECEDING_TREATED_COHORT'
 if 'co_administered' in tests:boundary='OTHER_ASSET_RESULT_BRIDGING_IS_NOT_EFFICACY_OWNERSHIP'
 neg.append({'id':x['id'],'original':x,'boundary':boundary,'expected':'UNKNOWN','treatment_owner_supported':False if boundary!='EXISTING_CONTENT_EXCLUSION' else None,'content_supported':False if boundary=='EXISTING_CONTENT_EXCLUSION' else None,'source':'research/se_human_efficacy_context_safety_v1/existing_test_population.json'})
for x in json.loads((ROOT/'research/se_human_efficacy_context_safety_v1/semantic_controls.json').read_text()):
 if x['category']=='regimen':neg.append({'id':x['id'],'original':x,'boundary':'REGIMEN_COMPONENT_OR_MULTIPLE_TREATMENTS','expected':'UNKNOWN','treatment_owner_supported':False,'content_supported':True,'source':'research/se_human_efficacy_context_safety_v1/semantic_controls.json'})
# Existing positive attribution controls are included to prevent a reject-everything design.
pos=[x for x in legacy if x['route']=='prose' and x['baseline_outputs'] and any(any(z in t for z in ['regimen_lists','TestEfficacyBelongsToOneAsset']) for t in x['tests'])]
struct=[
 {'id':'S1','case':'Observed single-arm trial, accepted asset name, explicit result-cohort link','study_link':True,'result_arm_link':True,'same_asset':True,'mapping_consistent':True,'therapeutic_count':1,'scope':'SINGLE_ASSET','observed':True,'expected':'CERTIFIED'},
 {'id':'S2','case':'Outcome belongs to other intervention arm','study_link':True,'result_arm_link':True,'same_asset':False,'mapping_consistent':True,'therapeutic_count':1,'scope':'SINGLE_ASSET','observed':True,'expected':'UNKNOWN'},
 {'id':'S3','case':'Multi-arm trial, result group unassigned','study_link':True,'result_arm_link':False,'same_asset':True,'mapping_consistent':True,'therapeutic_count':1,'scope':'SINGLE_ASSET','observed':True,'expected':'UNKNOWN'},
 {'id':'S4','case':'Single intervention protocol planned endpoint','study_link':True,'result_arm_link':True,'same_asset':True,'mapping_consistent':True,'therapeutic_count':1,'scope':'SINGLE_ASSET','observed':False,'expected':'UNKNOWN'},
 {'id':'S5','case':'Known result arm contains combination, requested candidate is component','study_link':True,'result_arm_link':True,'same_asset':True,'mapping_consistent':True,'therapeutic_count':2,'scope':'COMPONENT','observed':True,'expected':'UNKNOWN'},
 {'id':'S6','case':'Generic therapy description lacks accepted same-asset bridge','study_link':True,'result_arm_link':True,'same_asset':False,'mapping_consistent':True,'therapeutic_count':1,'scope':'SINGLE_ASSET','observed':True,'expected':'UNKNOWN'},
 {'id':'S7','case':'Publication is cited only as background','study_link':False,'result_arm_link':True,'same_asset':True,'mapping_consistent':True,'therapeutic_count':1,'scope':'SINGLE_ASSET','observed':True,'expected':'UNKNOWN'},
 {'id':'S8','case':'Forward/reverse/arm-label linkage conflicts','study_link':True,'result_arm_link':True,'same_asset':True,'mapping_consistent':False,'therapeutic_count':1,'scope':'SINGLE_ASSET','observed':True,'expected':'UNKNOWN'},
]
for f,v in [('attribution_audit.json',audit),('negative_controls.json',neg),('positive_attribution_controls.json',pos),('structured_design_cases.json',struct)]:
 (OUT/f).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
files=['attribution_audit.json','negative_controls.json','positive_attribution_controls.json','structured_design_cases.json']
(OUT/'design_freeze.json').write_text(json.dumps({'baseline':'867275c','rows':33,'emphasized_rows':14,'negative_controls':len(neg),'positive_attribution_controls':len(pos),'structured_cases':8,'frozen_before_contract_evaluation':True,'files':{f:hashlib.sha256((OUT/f).read_bytes()).hexdigest() for f in files}},indent=2)+'\n')
print('audit',len(audit),'receipt-only in 14',sum(x['receipt_status']=='CERTIFIED' for x in audit if x['previous_unresolved_14']),'negative controls',len(neg),'positive controls',len(pos))
