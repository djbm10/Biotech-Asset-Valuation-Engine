"""Freeze manually grounded design relations; not an extraction implementation."""
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/djmann/projects/bve-b8')
OUT = Path('/tmp/human_efficacy_quantity_binding_contract_v1')
OUT.mkdir(exist_ok=True)
FROZEN = ROOT / 'research/se_human_efficacy_boundary_diagnosis_v2/witness_register.json'
rows = json.loads(FROZEN.read_text())

# Span quotes below annotate evidence. They are not classifier patterns or exceptions.
# patient, outcome, outcome value(s), treatment scope, explicit relation form
roles = {
  64: ('this patient', 'complete remission', [], 'COMPONENT', 'QUALITATIVE_CASE'),
  97: ('human myotubes', 'respiration', ['42%', '52%'], 'NAMED_LAB_INTERVENTION', 'LAB_MEASUREMENT'),
  109: ('simulate 3-week patients', 'survival model', [], 'MODELED_COMPARISON', 'MODEL_PARAMETER'),
  11: ('patients with measurable diseases treated with and without bevacizumab', 'objective response rates', ['84.5%'], 'MATCHING_ARM', 'ORDERED_ARM_RATES'),
  26: ('5 patients', 'achieved complete remission', ['3'], 'COMPONENT', 'COUNT_ACHIEVED'),
  42: ('patients with PET30-CR', 'ultimately progressed', ['28.6%'], 'NON_TREATMENT', 'PROPORTION_EVENT'),
  54: ('patients', 'progression-free survival', ['52%', '42%'], 'NON_TREATMENT', 'TIME_SERIES'),
  62: ('patients', 'responder rates', ['87.7%'], 'UNRESOLVED_COMPOUND', 'NAMED_TREATMENT_RATES'),
  69: ('patients with hepatitis C virus', 'sustained virologic response', ['95%'], 'COMPONENT', 'RATE_OF_OUTCOME'),
  78: ('patients with RAS wild-type tumors', 'progression-free survival', ['12.0'], 'COMPONENT', 'ORDERED_ARM_DURATIONS'),
  80: ('for patients with baseline viral load', 'HIV RNA responses', ['70.1%', '80.6%'], 'POOLED_REGIMENS', 'ORDERED_BACKBONE_RATES'),
  92: ('in 31', 'virological efficacy', ['89'], 'COMPONENT', 'OBSERVED_THRESHOLD_ATTAINMENT'),
  99: ('patients were responders', 'responders', ['24%', '23%'], 'MATCHING_ARM', 'ORDERED_DOSE_ARM_RATES'),
  103: ('patients achieving clinical response', 'clinical response', ['65.7%'], 'MATCHING_ARM', 'OBSERVED_THRESHOLD_ATTAINMENT'),
  104: ('survodutide-treated patients', 'reduction in LFC', ['84.2%'], 'MATCHING_ARM', 'OBSERVED_THRESHOLD_ATTAINMENT'),
  0: ('patients', 'flares were reported', ['26.8%'], 'MATCHING_ARM', 'EVENT_COUNT_WITH_RATE'),
  1: ('20 patients treated with infusions of CNCT19 cells', 'reached complete remission', ['90%'], 'MATCHING_ARM', 'PROPORTION_ACHIEVED'),
  2: ('20 patients treated with CNCT19 cells', 'overall survival', ['12.91 months'], 'MATCHING_ARM', 'ORDERED_OUTCOME_DURATIONS'),
  8: ('patients receiving ruxolitinib', 'achieving complete remission', ['1/10'], 'MATCHING_ARM', 'PROPORTION_ACHIEVED'),
  14: ('21 evaluable patients', 'complete response rate', ['14.3%'], 'MATCHING_ARM', 'NAMED_TREATMENT_RATES'),
  15: ('all six patients', 'induced MRD-negative remission', ['all six'], 'MATCHING_ARM', 'COUNT_INDUCED_OUTCOME'),
  24: ('12 patients', 'achieving stringent complete remission', ['10 of 12'], 'MATCHING_ARM', 'COUNT_ACHIEVED'),
  29: ('patients who underwent BCMA-targeted treatment', 'overall response rate', ['30.2%'], 'MATCHING_ARM', 'NAMED_TREATMENT_RATES'),
}

def span(row, quote, *, start_after=None):
    text = row.get('decoded_analysis_passage', row['exact_passage'])
    start = text.find(quote, text.find(start_after)+len(start_after) if start_after else 0)
    field = 'decoded_analysis_passage' if 'decoded_analysis_passage' in row else 'exact_passage'
    if start < 0:
        text = row.get('source_abstract', '')
        start = text.find(quote)
        field = 'source_abstract'
    assert start >= 0, (row['id'], quote)
    return {'field':field, 'start':start, 'end':start+len(quote), 'text':quote}

result=[]
for row in rows:
    sid=row.get('survey_id')
    if sid is not None:
        patient,outcome,values,scope,form=roles[sid]
    else:
        patient,outcome,values,scope,form=(
          ('evaluable pts treated with CTL019','ongoing BM CR',['10/16'],'MATCHING_ARM','PROPORTION_ONGOING')
          if row['name']=='CTL019' else
          ('194 patients','reduction in flare risk',['30%'],'MATCHING_ARM','TREATMENT_PRODUCED_EFFECT'))
    aliases=sorted(set(row['asset_names']),key=len,reverse=True)
    text=row.get('decoded_analysis_passage',row['exact_passage'])
    name=next(n for n in aliases if n.lower() in text.lower())
    position=text.lower().find(name.lower())
    candidate_span={'field':'decoded_analysis_passage' if 'decoded_analysis_passage' in row else 'exact_passage',
                    'start':position,'end':position+len(name),'text':text[position:position+len(name)]}
    treatment_quotes={26:'venetoclax (VEN) plus azacitidine (AZA) combined with IVO',
                      69:'Glecaprevir/pibrentasvir',62:'Relugolix-CT',
                      80:'lopinavir/ritonavir (LPV/r), atazanavir/ritonavir (ATV/r) and fosamprenavir/ritonavir (FAPV/r)',
                      92:'DOR/3TC/TDF',64:'combination therapy of dupilumab'}
    treatment=(None if scope=='NON_TREATMENT' else
               span(row,treatment_quotes[sid]) if sid in treatment_quotes else candidate_span)
    p=span(row,patient);o=span(row,outcome)
    q=[span(row,v,start_after='induction, ' if sid==26 and v=='3' else None) for v in values]
    # Source-grounded semantic roles, explicitly manual; extraction is not proved here.
    world='LAB_MATERIAL' if sid==97 else 'SIMULATED' if sid==109 else 'OBSERVED_CLINICAL'
    observed=sid not in [97,109]
    efficacy=sid not in [97,109]
    quantity=bool(q) and efficacy
    relation_form=form
    asset_binding='SUPPORTED' if scope=='MATCHING_ARM' else 'UNSUPPORTED'
    units={78:'months',92:'percent',26:'patients',15:'patients',2:'months'}
    note=row['semantic_observation']['attribution_scope_caveat']
    if sid==62:note+=' Candidate aliases do not include Relugolix-CT; CT designates combination therapy in the source abstract. Same-product equivalence cannot be invented here.'
    if sid==78:note+=' Source explicitly describes anti-EGFR/bevacizumab combined with first-line chemotherapy; the bevacizumab arm corresponds to the second PFS value, 12.0 months.'
    record={'id':row['id'],'group':row['group'],'run':row['run'],'name':row['name'],
      'survey_id':sid,'frozen_source_row':row['id'],'candidate_mention_span':candidate_span,
      'asset_treatment_span':treatment,'patient_cohort_span':p,'efficacy_outcome_span':o,
      'numerical_spans':q,'quantity_unit':units.get(sid,'percent_or_proportion'),
      'treatment_scope':scope,'evidence_world':world,'outcome_observed':observed,
      'outcome_clinical_efficacy':efficacy,'quantity_is_outcome_measure':quantity,
      'relations':{'treatment_to_cohort':{'status':asset_binding,'form':scope,'reason':note},
                   'cohort_to_outcome':{'status':'SUPPORTED' if efficacy and observed else 'UNSUPPORTED','form':form},
                   'outcome_to_quantity':{'status':'SUPPORTED' if quantity else 'UNSUPPORTED','form':relation_form}},
      'boundaries_crossed':{'surface_fragment_indices':row['signal_fragment_map'],
        'source_continuation':sid in [78,80],
        'adjacent_sentence_anaphora':False,
        'note':'A vs. abbreviation continuation is one grammatical sentence, not permission to inherit arbitrary neighboring findings.'},
      'existing_guard_results':{k:row['current_predicates'][k] for k in ['regimen_veto','regimen_list_veto','eligibility_veto','unreported_veto','safety_non_efficacy_veto','nonhuman_veto']},
      'current_selected_numeric_span':dict(row['current_predicates']['first_numeric_value'],field='exact_passage'),
      'current_all_numeric_spans':row['current_predicates']['all_numeric_regex_matches'],
      'current_extractor_decision':'PASS','frozen_expected_decision':'REJECT' if row['group']=='known_false' else 'ACCEPT',
      'quantity_role_reason':row['semantic_observation']['quantity_roles'],
      'content_binding_form':form,'content_expected':row['group']!='known_false',
      'scope_rule':'SAME_ASSERTION' if sid not in [78,80] else 'ABBREVIATION_CONTINUATION',
      'same_document':True,'unique_treatment_anchor':scope=='MATCHING_ARM',
      'existing_guard_veto':False,'grounding_method':'Manual exact-source annotation; no proposed text parser implemented.'}
    result.append(record)

# Additional cases are necessary because no original row demonstrates real adjacent-
# sentence treatment anaphora; vs. truncation is not such evidence. Freeze before rules.
extra=[
 {'id':'D1','text':'Twenty patients received X. Among these evaluable patients, 12 achieved complete responses.',
  'expected':'ACCEPT','treatments':['X'],'cohort_reference':'these evaluable patients','number':'12',
  'reason':'Single previous-sentence treatment cohort; explicit demonstrative evaluable subset.'},
 {'id':'D2','text':'Twenty patients received X, and twenty patients received Y. Among evaluable patients, 12 achieved complete responses.',
  'expected':'REJECT','treatments':['X','Y'],'cohort_reference':'evaluable patients','number':'12',
  'reason':'Two potential antecedent arms; no response-to-arm assignment.'},
 {'id':'D3','text':'Twenty patients received X. A separate cohort received Y. Twelve patients achieved complete responses.',
  'expected':'REJECT','treatments':['X','Y'],'cohort_reference':None,'number':'Twelve',
  'reason':'X is not in the immediately preceding sentence; no explicit reference establishes the requested X cohort.'},
]
for f,value in [('relation_population.json',result),('additional_discourse_cases.json',extra)]:
    (OUT/f).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
(OUT/'population_freeze.json').write_text(json.dumps({'milestone':'HUMAN_EFFICACY_QUANTITY_BINDING_CONTRACT v1',
  'original_rows':33,'added_discourse_cases':3,'labels_unchanged':True,
  'freeze_precedes_contract_and_offline_decision_checker':True,
  'role_annotations_are_manual_not_text_extraction_results':True,
  'original_register_sha256':hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
  'files':{f:hashlib.sha256((OUT/f).read_bytes()).hexdigest() for f in ['relation_population.json','additional_discourse_cases.json']}},indent=2)+'\n')
print('Frozen 33 original relation records and 3 discourse cases.')
