"""Offline validator of frozen manually grounded relations, NOT a text extractor."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path('/home/djmann/projects/bve-b8')
OUT = Path('/tmp/human_efficacy_quantity_binding_contract_v1')
BASE = ROOT / 'research/se_human_efficacy_quantity_binding_contract_v1'
ORIGINAL = ROOT / 'research/se_human_efficacy_boundary_diagnosis_v2/witness_register.json'

freeze = json.loads((BASE / 'population_freeze.json').read_text())
for name,digest in freeze['files'].items():
    assert hashlib.sha256((BASE/name).read_bytes()).hexdigest() == digest
assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == freeze['original_register_sha256']
original={r['id']:r for r in json.loads(ORIGINAL.read_text())}
population=json.loads((BASE/'relation_population.json').read_text())

SCOPE = {'SAME_ASSERTION','ABBREVIATION_CONTINUATION','ADJACENT_EXPLICIT_COHORT'}

def content_chain(r):
    return (r['same_document'] and r['scope_rule'] in SCOPE
            and r['evidence_world']=='OBSERVED_CLINICAL'
            and r['outcome_observed'] and r['outcome_clinical_efficacy']
            and r['quantity_is_outcome_measure'] and bool(r['numerical_spans'])
            and r['relations']['cohort_to_outcome']['status']=='SUPPORTED'
            and r['relations']['outcome_to_quantity']['status']=='SUPPORTED')

def full_chain(r):
    return (content_chain(r) and not r['existing_guard_veto']
            and r['asset_treatment_span'] is not None
            and r['unique_treatment_anchor']
            and r['treatment_scope']=='MATCHING_ARM'
            and r['relations']['treatment_to_cohort']['status']=='SUPPORTED')

decisions=[]
for r in population:
    source=original[r['id']]
    for node in [r['candidate_mention_span'],r['asset_treatment_span'],r['patient_cohort_span'],r['efficacy_outcome_span'],r['current_selected_numeric_span'],*r['numerical_spans']]:
        if node is None:continue
        assert source[node['field']][node['start']:node['end']]==node['text'],(r['id'],node)
    assert r['frozen_expected_decision']==('ACCEPT' if source['frozen_content_positive'] else 'REJECT')
    content='ACCEPT' if content_chain(r) else 'REJECT'
    full='ACCEPT' if full_chain(r) else 'REJECT'
    reasons=[]
    if r['evidence_world']!='OBSERVED_CLINICAL':reasons.append('not an observed clinical population')
    if not r['quantity_is_outcome_measure']:reasons.append('no numerical clinical efficacy measure')
    if r['treatment_scope']!='MATCHING_ARM':reasons.append('treatment edge unproved: '+r['treatment_scope'])
    decisions.append({'id':r['id'],'group':r['group'],'name':r['name'],
      'expected':r['frozen_expected_decision'],'content_only':content,'full_chain':full,
      'matches_full_target':full==r['frozen_expected_decision'],'reasons':reasons})

extra=json.loads((BASE/'additional_discourse_cases.json').read_text())
disc=[]
for r in extra:
    # These synthetic designs explicitly provide the antecedent alternatives. This
    # checks the uniqueness/scope contract only, not arbitrary-language coreference.
    accept=len(r['treatments'])==1 and r['cohort_reference'] is not None
    actual='ACCEPT' if accept else 'REJECT'
    assert actual==r['expected']
    disc.append(dict(r,actual=actual,scope_checked_only=True))

groups={}
for g in sorted({r['group'] for r in decisions}):
    rr=[r for r in decisions if r['group']==g]
    groups[g]={'rows':len(rr),'expected_accept':sum(r['expected']=='ACCEPT' for r in rr),
      'content_only_matches':sum(r['content_only']==r['expected'] for r in rr),
      'full_chain_matches':sum(r['matches_full_target'] for r in rr),
      'full_chain_accept':sum(r['full_chain']=='ACCEPT' for r in rr)}
result={'milestone':'HUMAN_EFFICACY_QUANTITY_BINDING_CONTRACT v1',
  'decision':'NOT_IMPLEMENTATION_READY','acceptance_target_met':all(r['matches_full_target'] for r in decisions),
  'evaluation_kind':'Deterministic contract predicate on frozen manually grounded semantic records; no raw-text extraction or end-to-end fact-generation test.',
  'groups':groups,'content_only_matches':sum(r['content_only']==r['expected'] for r in decisions),
  'full_chain_matches':sum(r['matches_full_target'] for r in decisions),'original_rows':len(decisions),
  'full_chain_target_failures':[r for r in decisions if not r['matches_full_target']],
  'decisions':decisions,'additional_discourse_designs':disc,'labels_changed':False}
(OUT/'offline_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

def cell(s):return str(s).replace('|','\\|').replace('\n','<br>')
def show(n):
    if n is None:return 'NONE'
    return f'`{n["text"]}` ({n["field"]}:{n["start"]}–{n["end"]})'
lines=['# Quantity-binding contract v1 — every frozen witness','',
 'REJECT means no fact / runtime UNKNOWN. Expected labels are unchanged. Content-only acceptance is a diagnostic ablation, never an emission rule. Relations are manually grounded, not automatic extraction outputs.','',
 '| Witness | Treatment / candidate | Patient cohort | Outcome | Numerical measure (current match) | T→C | C→O | O→Q | Boundaries | Current / expected | Content / full contract | Reason |',
 '|---|---|---|---|---|---|---|---|---|---|---|---|']
for r,d in zip(population,decisions):
    cols=[r['id']+' / '+r['name'],show(r['asset_treatment_span'])+'; candidate '+show(r['candidate_mention_span']),
          show(r['patient_cohort_span']),show(r['efficacy_outcome_span']),
          ', '.join(show(n) for n in r['numerical_spans'])+'; current '+show(r['current_selected_numeric_span']),
          r['relations']['treatment_to_cohort']['status']+' / '+r['treatment_scope'],
          r['relations']['cohort_to_outcome']['status']+' / '+r['content_binding_form'],
          r['relations']['outcome_to_quantity']['status']+' / '+r['quantity_role_reason'],
          r['scope_rule']+'; exact clause indices in relation_population.json',
          r['current_extractor_decision']+' / '+d['expected'],
          d['content_only']+' / '+d['full_chain'],
          '; '.join(d['reasons']) if d['reasons'] else 'Complete grounded chain; no existing guard veto']
    lines.append('| '+' | '.join(map(cell,cols))+' |')
(OUT/'relation_table.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({k:result[k] for k in ['decision','acceptance_target_met','groups','content_only_matches','full_chain_matches','original_rows']},indent=2))
