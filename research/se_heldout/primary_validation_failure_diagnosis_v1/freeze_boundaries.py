import csv
import hashlib
import json
from pathlib import Path

OUT=Path('/tmp/primary_validation_failure_diagnosis_v1')
rows=json.loads((OUT/'row_traces.json').read_text())
records=[]
for q,items in rows.items():
    for x in items:
        boundary='NONE_FOR_FROZEN_ROW_METRICS'
        error=False
        reason='Frozen RELEVANT label; no false human-PoC on this row.'
        downstream=[]
        if (q,x['position']) in [('H18',1),('H19',1)]:
            boundary='HUMAN_POC_SENTENCE_ADMISSIBILITY'
            error=True
            reason='Human-myotube respiration was admitted as human-patient efficacy.' if q=='H18' else 'Economic-model simulation and discount rate were admitted as observed human efficacy.'
            downstream=['human_poc_present fact','evidence-sensitive display order']
        elif x['label']=='DUPLICATE':
            boundary='IDENTITY_CONSOLIDATION_TRADE_NAME_POLICY' if q=='H18' or x['position']==16 else 'IDENTITY_CONSOLIDATION_CONSTRUCT_BRIDGE_ABSENT'
            error=True
            reason=x['rationale']
            downstream=['separate canonical IDs survive','multiple shortlist rows for one product']
        elif x['label']=='NON_ASSET':
            boundary='QUALIFICATION_STRUCTURED_ROLE_OVERPROMOTION'
            error=True
            reason='Diagnostic radiotracer in an experimental arm was treated as a therapeutic product.' if x['position']==17 else 'An unspecified premedication category declared DRUG in an experimental arm was promoted to a distinct therapeutic asset.'
            downstream=['identity_valid PASS','review inclusion']
        elif x['label']=='WRONG_TARGET':
            boundary='TARGET_ATTRIBUTION_UNRESOLVED'
            error=True
            reason='Frozen public label is WRONG_TARGET; artifact target.expression remains UNKNOWN rather than containing a false positive target assertion. Earliest unmet prerequisite is product-target evidence; review display admits that uncertainty.'
            downstream=['UNKNOWN goes to review','modality-first ordering can favor unrelated known-modality products']
        records.append({'query_id':q,'position':x['position'],'asset_id':x['asset_id'],'name':x['name'],
                        'frozen_label':x['label'],'first_failure_boundary':boundary,'row_quality_failure':error,
                        'basis':reason,'downstream_effects':downstream,
                        'observed_gate_disposition':x['gate']['disposition'] if x['gate'] else None,
                        'modality_match':x['candidate']['modality_match']})
for q,phrase,target,reason in [
 ('H17','IL-4Rα','IL4R','Existing anti- affix stripping works; remaining Greek-alpha form has no normalized alias key in pinned target authority.'),
 ('H20','factor XI','F11','Original two-word phrase reaches exact alias lookup but has no normalized key; approved coagulation-factor label is not automatically shortened.')]:
    records.append({'query_id':q,'position':None,'asset_id':None,'name':phrase,'frozen_label':'REFUSED',
                    'first_failure_boundary':'TARGET_ALIAS_LOOKUP_COVERAGE','row_quality_failure':True,'basis':reason,
                    'downstream_effects':['zero TARGET spans','compiler refuses exact original query'],
                    'intended_target':target})
for name,boundary,reason in [
 ('datopotamab deruxtecan','STRUCTURED_MODALITY_EXTRACTION','Named product exists and qualifies. Longest-substring modality heuristic chooses peptide from tetrapeptide linker; PEPTIDE fact drives modality.required FAIL despite authority ADC MATCH.'),
 ('ESG401','CANDIDATE_ENUMERATION_STRUCTURED_NAME_BOUNDARY','Name exists in captured NCT06145308 armGroups[].description, but intervention is named generic TROP2 ADC and no ESG401 candidate or mention is materialized.'),
 ('BL-M02D1','DISCOVERY_CORPUS_COVERAGE','No matching candidate, identity mention, or string in the 779 captured query-source snapshots; the other four source-document records are synthetic ontology provenance without snapshot paths. Cause before capture cannot be resolved from artifacts alone; six mandatory families unconfigured.')]:
    records.append({'query_id':'H19','position':None,'asset_id':None,'name':name,'frozen_label':'MISSING_REFERENCE',
                    'first_failure_boundary':boundary,'row_quality_failure':True,'basis':reason,'downstream_effects':['absent from scored shortlist']})
records.append({'query_id':'H16','position':541,'asset_id':'asset:2132e952ba48d3ce24a6','name':'TSR-033 / encelimab',
                'frozen_label':'REFERENCE_FOUND_OUTSIDE_TOP20','first_failure_boundary':'DISPLAY_ORDER_MODALITY_COVERAGE',
                'row_quality_failure':False,'basis':'Correct reference present in all-shortlist at #541; authority modality UNKNOWN sorts behind all ten top20 WRONG_TARGET rows with modality MATCH. Not a recall failure; only frozen P@20 criterion fails.',
                'downstream_effects':['reference outside top20'], 'modality_match':'UNKNOWN'})
assert len(records)==66
(OUT/'first_failure_boundaries.json').write_text(json.dumps(records,indent=2)+'\n')
fields=['query_id','position','asset_id','name','frozen_label','first_failure_boundary','basis']
with (OUT/'first_failure_boundaries.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(records)
print('Frozen first-boundary register: 60 emitted rows, 2 refusals, 3 missing H19 references, 1 H16 reference outside top20.')
