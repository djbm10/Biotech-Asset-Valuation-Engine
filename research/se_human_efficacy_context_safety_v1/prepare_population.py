import hashlib
import json
from pathlib import Path
from bve.se.evidence.human_poc import efficacy_statements

OUT=Path('/tmp/human_efficacy_context_safety_v1')
survey=json.loads((OUT/'unique_witness_survey.json').read_text())
reasons={
 4:'Treatment-switching proportions, not a measured efficacy outcome.',
 9:'Enrolled/treated n counts and treatment purpose, not efficacy results.',
 16:'Cohort size in a prior-response correlation, no quantitative attributable efficacy outcome.',
 21:'Maintenance-use percentage, not remission or response.',
 22:'Responder threshold and qualitative increased rates; no numerical observed response proportion.',
 25:'Study objective and formulation concentrations, not an observed clinical outcome.',
 31:'Endpoint definition (30% shrinkage) without a reported numerical outcome.',
 40:'Efficacy-cohort enrollment n, not efficacy outcome.',
 44:'Transplantation-use count in CR patients, not a measured CR outcome.',
 45:'Review/cohort n and treatment purpose, not quantified response or survival.',
 47:'Pre-treatment cell assay and molecular correlate; group n, not clinical efficacy.',
 50:'Future relapse prediction, not observed result.',
 53:'Referral-reason percentages, not efficacy outcome proportions.',
 56:'Dose ratio and study duration beside qualitative efficacy.',
 57:'Enzyme-activity eligibility and safety/haemolysis comparison, not efficacy outcome.',
 63:'Reduced use of the named drug among cured patients, not its quantified therapeutic efficacy.',
 64:'Qualitative single-patient remission; numeric match is receptor nomenclature 4/13.',
 75:'Dose ratio and trial durations describing an evaluation, not reported clinical benefit.',
 82:'Animal-model efficacy extrapolated to humans without treated clinical human cohort.',
 87:'Exposure-response/endpoint grading and safety; ratio in endpoint name, not efficacy value.',
 90:'Qualitative PFS improvement; numeric match is phase 2/3, not outcome.',
 93:'Animal-model/estimated human efficacy without a clinical human cohort.',
 96:'Study aim and anesthetic concentrations, not observed patient efficacy.',
 97:'Human myotube respiratory assay, not human clinical efficacy (primary H18 witness).',
 98:'Methods define response strata using thresholds; no observed outcome proportion.',
 101:'Cream concentration beside qualitative case/treatment description.',
 107:'Qualitative survival improvement; numeric match is target-family CDK4/6.',
 108:'Baseline tumor biomarker percentage beside qualitative partial response.',
 109:'Survival-model methods and discount rate, not clinical efficacy (primary H19 witness).',
}
adjudications=[]
for row in survey:
    adjudications.append({**row,'expected_pass':row['id'] not in reasons,
                          'reason':reasons.get(row['id'],'Observed numerical clinical efficacy content; preserve existing asset/regimen attribution guards without redesign.'),
                          'independently_verified_preexisting_numerical_false_positive':row['id'] in reasons})
(OUT/'witness_adjudications.json').write_text(json.dumps(adjudications,indent=2)+'\n')

controls=[]
def add(category,text,expected,**kw):
    controls.append({'id':f'C{len(controls)+1:03}','category':category,'text':text,
                     'asset_names':kw.get('asset_names',['RX-001']),'expected_pass':expected,
                     'baseline_pass':bool(efficacy_statements(text,asset_names=kw.get('asset_names',['RX-001']),document_id='control'))})

for context in ['human cells','human tissue','patient-derived cells','cells isolated from patients',
                'human organoids','human plasma samples','patient tissue specimens']:
    add('laboratory',f'RX-001 produced a response of 63% in {context}.',False)
for measure in ['respiration','metabolism','receptor occupancy','target engagement','cytokine secretion']:
    add('laboratory',f'In human cells, RX-001 increased {measure} by 63% and improved response.',False)
for phrase in ['biomarker response','pharmacodynamic response','plasma concentration response',
               'receptor occupancy response','target engagement response']:
    add('pharmacodynamic',f'In patients treated with RX-001, the {phrase} was 63%.',False)
for descriptor in ['simulated','virtual','synthetic','computer-generated']:
    add('simulation',f'RX-001 achieved a response rate of 63% in {descriptor} patients.',False)
for method in ['simulation','mathematical model','economic model','decision model']:
    add('model',f'A {method} predicted that RX-001 would achieve a response rate of 63% in patients.',False)
add('economic','A survival model evaluated RX-001 for patients, using an annual discount rate of 7%.',False)
add('economic','In patients receiving RX-001, economic response was a 63% reduction in costs.',False)
add('economic','Cost-effectiveness of RX-001 was evaluated in patients, with a 7% survival-model discount rate.',False)
add('statistical','A study of RX-001 had 90% power to detect a response in patients.',False)
add('statistical','RX-001 response was measured in patients using a 95% confidence interval.',False)
add('sample_size','The RX-001 efficacy cohort included n=36 patients.',False)
add('sample_size','Patients received RX-001 (n=36) for disease control.',False)
add('treatment_use','Among patient responders, 63% received RX-001 maintenance therapy.',False)
add('dose','RX-001 at 0.7% concentration was administered to patients to assess efficacy.',False)
add('definition','The response endpoint in patients treated with RX-001 was defined as a 63% reduction.',False)
add('safety','Patients treated with RX-001 had adverse events in 63% of cases.',False)
add('safety','RX-001 was tolerated in patients with adverse reactions in 4 of 18.',False)
add('pk','RX-001 exposure in patients increased by 63%, with a pharmacokinetic response.',False)
add('pk','The half-life of RX-001 in patients was 14 hours with 63% bioavailability.',False)
add('planned','The response rate for RX-001 in 36 patients will be evaluated.',False)
add('planned','The study will report RX-001 remission in 63% of patients.',False)
add('eligibility','Patients must have had a response to RX-001 in 4 of 18 prior treatments.',False)
add('qualitative','RX-001 improved survival in patients enrolled in phase 2/3.',False)

for population in ['patients','participants','subjects','recipients','volunteers','evaluable pts']:
    add('clinical_response',f'RX-001 produced an overall response rate of 63% in {population}.',True)
add('clinical_remission','RX-001 achieved complete remission in 4 of 18 treated patients.',True)
add('clinical_progression','RX-001 achieved progression-free survival of 63% at one year in patients.',True)
add('clinical_symptom','RX-001 produced symptom improvement in 63% of treated patients.',True)
add('clinical_flare','RX-001 produced a 63% reduction in disease flare risk in treated patients.',True)
add('clinical_alias','Treatment with the active name achieved complete remission in 4 of 18 patients.',True,asset_names=['RX-001','the active name'])
add('regimen','RX-001 plus RX-002 achieved an overall response rate of 63% in patients.',False)
add('regimen','Patients treated with RX-001, RX-002, and RX-003 achieved a response rate of 63%.',False)
add('cross_sentence','Patients received RX-001. The response rate was 63%.',False)
add('mixed_positive','RX-001 achieved a response rate of 63% in treated patients; an economic model used a 7% discount rate.',True)
add('mixed_positive','In patients treated with RX-001, the response rate was 63%, and the analysis used a 95% confidence interval.',True)
add('mixed_positive','RX-001 achieved complete remission in 4 of 18 patients, while a simulation predicted survival of 7%.',True)
add('mixed_positive','Safety was evaluated in 36 patients and the RX-001 overall response rate was 63%.',True)
add('mixed_positive','In patients treated with RX-001, the response rate was 63%, and plasma concentrations increased by 7%.',True)
add('mixed_negative','In patients treated with RX-001, an economic analysis used a 7% discount rate, and clinical response was discussed.',False)
add('mixed_negative','Human-cell assays of RX-001 had a 63% response, and simulated patients had remission.',False)
add('mixed_negative','In patients treated with RX-001, plasma concentrations increased 63%, and response was assessed.',False)
add('mixed_negative','The overall response rate for RX-001 was discussed in patients, and 63% experienced adverse events.',False)
add('model_adjustment','A statistical model adjusted for age; RX-001 had an observed response rate of 63% in treated patients.',True)
add('modeled_outcome','A model predicted RX-001 response in 63% of patients without observed clinical results.',False)
add('material_cohort','A cohort of human cells treated with RX-001 achieved a response rate of 63%.',False)
add('ambiguous_cohort','RX-001 achieved a response rate of 63% in a cohort.',False)
add('clinical_cohort','RX-001 achieved a response rate of 63% in the treated clinical cohort.',True)
(OUT/'semantic_controls.json').write_text(json.dumps(controls,indent=2)+'\n')
print('Frozen survey judgments',len(adjudications),'independent preexisting numerical false witnesses',len(reasons),'semantic controls',len(controls))
