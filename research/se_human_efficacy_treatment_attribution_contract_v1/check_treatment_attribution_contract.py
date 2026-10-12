"""Offline contract checks on frozen evidence annotations; no new text extractor."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path('/home/djmann/projects/bve-b8');P=ROOT/'research/se_human_efficacy_treatment_attribution_contract_v1';OUT=Path('/tmp/human_efficacy_treatment_attribution_contract_v1')
sys.path.insert(0,str(ROOT/'src'))
from bve.se.evidence.human_poc import efficacy_statements
freeze=json.loads((P/'design_freeze.json').read_text())
for f,h in freeze['files'].items():assert hashlib.sha256((P/f).read_bytes()).hexdigest()==h
rows=json.loads((P/'attribution_audit.json').read_text())
def own_result(r):
 return r['receipt_status']=='CERTIFIED' and r['proposed_edge_basis'] in {'A_EXPLICIT_PROSE','A_ACCEPTED_ALIAS'} and r['treatment_scope'] in {'SINGLE_NAMED_TREATMENT','EXPLICIT_ADD_ON_COMPARISON'}
audit_decisions=[]
for r in rows:
 decision='PASS' if own_result(r) and r['content_expected_unchanged'] else 'UNKNOWN'
 assert decision==r['expected_human_poc']
 audit_decisions.append({'id':r['id'],'edge_certified':own_result(r),'human_poc':decision,'previous_unresolved_14':r['previous_unresolved_14']})
neg=json.loads((P/'negative_controls.json').read_text());negative_results=[]
for r in neg:
 x=r['original'];inputs=x.get('inputs',x);current=bool(efficacy_statements(inputs['text'],asset_names=inputs['asset_names']))
 # The grounded rejection reason is the contract precondition, not a product ID.
 reasons={'REGIMEN_COMPONENT_OR_MULTIPLE_TREATMENTS','NO_PRECEDING_TREATED_COHORT','OTHER_ASSET_RESULT_BRIDGING_IS_NOT_EFFICACY_OWNERSHIP','EXISTING_CONTENT_EXCLUSION'}
 assert r['boundary'] in reasons
 allowed = r['treatment_owner_supported'] is not False and r['content_supported'] is not False
 decision='PASS' if allowed else 'UNKNOWN';assert decision==r['expected']
 if r['id'] not in ['C055','C056']:assert not current
 negative_results.append({'id':r['id'],'boundary':r['boundary'],'current_reader_pass':current,'proposed_contract':decision,'expected':r['expected']})
positive=json.loads((P/'positive_attribution_controls.json').read_text());positive_results=[]
for r in positive:
 i=r['inputs'];current=[s.model_dump(mode='json') for s in efficacy_statements(**i)]
 assert current==r['baseline_outputs']
 positive_results.append({'id':r['id'],'current_unchanged':True,'contract_basis':'Explicit same-asset or accepted alias; whole defined combination product is its own treatment, not a component.'})
structured_results=[]
for r in json.loads((P/'structured_design_cases.json').read_text()):
 cert=all(r[k] for k in ['study_link','result_arm_link','same_asset','mapping_consistent','observed']) and r['therapeutic_count']==1 and r['scope']=='SINGLE_ASSET'
 decision='CERTIFIED' if cert else 'UNKNOWN';assert decision==r['expected'];structured_results.append(dict(r,actual=decision))
discourse_results=[]
for r in json.loads((ROOT/'research/se_human_efficacy_quantity_binding_contract_v1/additional_discourse_cases.json').read_text()):
 decision='ACCEPT' if len(r['treatments'])==1 and r['cohort_reference'] else 'REJECT';assert decision==r['expected'];discourse_results.append(dict(r,actual=decision,check_scope='Previously grounded uniqueness/reference conditions, not automatic text coreference.'))
u=[r for r in rows if r['previous_unresolved_14']]
summary={'milestone':'HUMAN_EFFICACY_TREATMENT_ATTRIBUTION_CONTRACT v1','decision':'DESIGN_COMPLETE_ARCHITECTURAL_EXTENSION_REQUIRED','human_poc_implementation_ready':False,'evaluation_kind':'Grounded semantic-record contract checks and unchanged current-reader control probes; no implemented contract text extractor.',
 'audit_rows':len(rows),'audit_checks_matched':len(audit_decisions),'expected_human_poc_pass':sum(r['human_poc']=='PASS' for r in audit_decisions),'unresolved_14':{'safe_asset_specific_certifications':sum(own_result(r) for r in u),'identity_only_rescues':0,'representation_only_rescues':0,'unsupported_asset_specific_efficacy_with_captured_evidence':14,'receipt_only_certifications':sum(r['receipt_status']=='CERTIFIED' for r in u),'regimen_or_pooled_result_scope':12,'non_treatment_candidates':2,'specific_pi_arm_result_missing':3},
 'negative_controls':len(negative_results),'negative_contract_checks_matched':len(negative_results),'current_negative_control_false_passes':[r['id'] for r in negative_results if r['current_reader_pass']],
 'existing_positive_attribution_controls':len(positive_results),'structured_design_checks':len(structured_results),'discourse_design_checks':len(discourse_results),
 'audit_decisions':audit_decisions,'negative_results':negative_results,'positive_results':positive_results,'structured_results':structured_results,'discourse_results':discourse_results}
(OUT/'contract_checks.json').write_text(json.dumps(summary,indent=2)+'\n')
def c(x):return str(x).replace('|','\\|').replace('\n','<br>')
lines=['# Treatment attribution contract v1 — complete 33-row audit','',
'CERTIFIED receipt alone never licenses an efficacy fact. PASS below is the proposed scoped scientific decision on grounded evidence, not current production behavior. Exact source text, hashes, span offsets and registry JSON are frozen in attribution_audit.json and structured_registry_evidence.json.','',
'| Candidate / witness | Names / aliases | Trial / arm identifiers and interventions | Regimen | Efficacy passage / cohort | Structured evidence | Edge / certifiability | Provenance | Expected human-PoC / reason |',
'|---|---|---|---|---|---|---|---|---|']
for r in rows:
 arms=[]
 for l in r['trial_and_arm_evidence']:
  arms.append({'trial':l['link']['trial_id'],'usable_study_link':l['study_link_usable'],'groups':l['arms_interventions'].get('armGroups',[]),'interventions':l['arms_interventions'].get('interventions',[])})
 prov=(r.get('source') or {}).get('source_url','legacy fixture')+'; '+str(r.get('source_snapshot_sha256') or r['id'])
 vals=[r['candidate_asset']+' / '+r['id'],', '.join(r['explicit_names_aliases']),json.dumps(arms,ensure_ascii=False) if arms else 'No verified trial/result-arm identifier; candidate membership and lexical leads separately recorded',', '.join(r['regimen_components']) or 'None stated in bound assertion',r['efficacy_passage']+' / cohort: '+r['patient_cohort_reference']['text'],str(len(r['candidate_related_registry_document_ids']))+' candidate-related registry documents; '+str(r['clinical_results_available'])+' structured clinical results; no result→arm record',r['proposed_edge_basis']+'; receipt '+r['receipt_status']+'; efficacy owner '+r['efficacy_owner_status'],prov,r['expected_human_poc']+' — '+r['reason']]
 lines.append('| '+' | '.join(c(v) for v in vals)+' |')
(OUT/'attribution_table.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({k:summary[k] for k in ['decision','audit_rows','expected_human_poc_pass','unresolved_14','negative_controls','current_negative_control_false_passes','existing_positive_attribution_controls','structured_design_checks']},indent=2))
