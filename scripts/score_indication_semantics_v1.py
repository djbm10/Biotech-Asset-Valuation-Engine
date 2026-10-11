"""Frozen offline indication-only scorer; never acquires or replays source documents."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from bve.se.gates.engine import _requirement
from bve.se.gates.evaluator import evaluate_indication
from bve.se.intent.compiler import residual_indications, intent_to_trial_query
from bve.se.intent.parser import parse_query
from bve.se.ontology.indications import (
    classify_condition, indication_concepts_in_phrase, resolve_indication_phrase,
)
from bve.se.pipeline import SESearchResult
from bve.se.reporting.shortlist import build_shortlist
from bve.se.schemas.contracts import NormalizedFact, RequirementOperator

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/se_indication_semantics_v1'
IND = 'strategy.indication'


def decide(requested, facts, aid):
    return evaluate_indication(
        _requirement(IND, 'indication', RequirementOperator.IN, requested),
        subject_id=aid, facts=facts, gate_id='strategic_sandbox',
    ).model_dump(mode='json')


def fingerprint(raw):
    excluded = {'gate_evaluations', 'excluded_asset_ids', 'unresolved_asset_ids',
                'eligible_asset_ids', 'review_queue'}
    return {k:hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest()
            for k,v in raw.items() if k not in excluded}


def main():
    manifest = json.loads((OUT/'manifest.json').read_text())
    for name, digest in manifest.items():
        assert hashlib.sha256((OUT/name).read_bytes()).hexdigest() == digest, name
    frozen = json.loads((OUT/'population.json').read_text())
    controls = json.loads((OUT/'controls.json').read_text())
    result = {'controls': [], 'leakage': {}, 'queries': {}, 'criteria': {}}
    for label, requested, observed, expected in controls['cases']:
        fact = NormalizedFact(fact_id='control', subject_id='a', fact_type='indication',
                              value=observed, confidence=0.9, supporting_claim_ids=['c'])
        decision = decide([requested], [fact], 'a')
        result['controls'].append({'id':label, 'requested':requested, 'observed':observed,
            'expected':expected, 'actual':decision['status'], 'rationale':decision['rationale']})
    for term in controls['non_disease_terms']:
        result['leakage'][term] = indication_concepts_in_phrase(term)
    for q, pop in frozen.items():
        path = Path(pop['run'])/'result.json'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == pop['result_sha256'], q
        raw = json.loads(path.read_text())
        before_short = build_shortlist(SESearchResult.model_validate(raw), limit=100000)
        before_top = [e.asset_id for e in before_short.entries[:20]]
        if q.startswith('H'):
            argv = pop['invocation']['argv']
            query = argv[argv.index('--query')+1]
            intent = parse_query(query)
            residuals = list(intent.residual_terms)
            retrieval = intent_to_trial_query(intent).model_dump(mode='json')
            requested = residual_indications(intent)
            assert intent.residual_terms == residuals
            assert intent_to_trial_query(intent).model_dump(mode='json') == retrieval
        else:
            query = None
            requested = pop['problem']['strategic_gap']['indications']
        by_subject = defaultdict(list)
        for fact in raw['facts']:
            if fact['fact_type'] == 'indication':
                by_subject[fact['subject_id']].append(NormalizedFact.model_validate(fact))
        transitions, new_pass = Counter(), {}
        original_non_ind = {}
        original = fingerprint(raw)
        pass_preserved, unknown_preserved, explicit_disjoint_preserved = True, True, True
        after_status = {}
        for g in raw['gate_evaluations']:
            aid = g['subject_id']
            original_non_ind[aid] = [d.copy() for d in g['decisions'] if d['requirement_id'] != IND]
            for i, old in enumerate(g['decisions']):
                if old['requirement_id'] != IND:
                    continue
                if not requested:
                    after_status[aid] = 'NO_REQUIREMENT'
                    transitions[old['status']+'->NO_REQUIREMENT'] += 1
                    continue
                decision = decide(requested, by_subject[aid], aid)
                transitions[old['status']+'->'+decision['status']] += 1
                if old['status']=='PASS' and decision['status']!='PASS':
                    pass_preserved=False
                if old['status']=='UNKNOWN' and decision['status']!='UNKNOWN':
                    unknown_preserved=False
                if old['status']!='PASS' and decision['status']=='PASS':
                    for fact in by_subject[aid]:
                        for condition in fact.value if isinstance(fact.value,list) else [fact.value]:
                            if isinstance(condition,str):
                                new_pass[condition] = {
                                    concept:classify_condition(condition,concept).value for concept in requested}
                g['decisions'][i] = decision
                after_status[aid] = decision['status']
            if not requested:
                g['decisions'] = [d for d in g['decisions'] if d['requirement_id'] != IND]
            statuses = [d['status'] for d in g['decisions']]
            g['disposition'] = 'EXCLUDED' if 'FAIL' in statuses else 'UNRESOLVED' if 'UNKNOWN' in statuses else 'ELIGIBLE'
        for key, disposition in [('excluded_asset_ids','EXCLUDED'),('unresolved_asset_ids','UNRESOLVED'),('eligible_asset_ids','ELIGIBLE')]:
            raw[key] = [g['subject_id'] for g in raw['gate_evaluations'] if g['disposition']==disposition]
        assert all(original_non_ind[g['subject_id']] == [d for d in g['decisions'] if d['requirement_id']!=IND] for g in raw['gate_evaluations'])
        assert original == fingerprint(raw)
        after_short = build_shortlist(SESearchResult.model_validate(raw),limit=100000)
        after_top = [e.asset_id for e in after_short.entries[:20]]
        visible = {e.asset_id for e in after_short.entries}
        references = [{'name':r['name'],'asset_id':r['asset_id'],
            'excluded_before':r['before']['disposition']=='EXCLUDED',
            'after':after_status.get(r['asset_id'],'NO_REQUIREMENT'), 'visible':r['asset_id'] in visible}
            for r in pop['reference_records']]
        result['queries'][q] = {'query':query,'requirements_before':pop['problem']['strategic_gap']['indications'],
            'requirements_after':requested,'transitions':dict(transitions),'references':references,
            'only_indication_excluded_before':len(pop['only_indication_excluded_ids']),
            'only_indication_recovered':sum(a in visible for a in pop['only_indication_excluded_ids']),
            'visible_before':len(before_short.entries),'visible_after':len(after_short.entries),
            'top20_unchanged':before_top==after_top,'before_top20':before_top,'after_top20':after_top,
            'passes_preserved':pass_preserved,'unknowns_preserved':unknown_preserved,
            'new_pass_conditions':new_pass,'isolation':True}
        print(q, requested, dict(transitions), 'top20 unchanged', before_top==after_top, flush=True)
        (OUT/'score_partial.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
        del raw, before_short, after_short
    cases = result['controls']
    crit = result['criteria']
    crit['I1'] = all(r['after'] in ('PASS','UNKNOWN') and r['visible'] for q,v in result['queries'].items() for r in v['references'] if r['excluded_before'])
    crit['I2'] = all(c['actual']=='FAIL' for c in cases if c['expected']=='FAIL')
    crit['I3'] = all(c['actual']=='PASS' for c in cases if c['expected']=='PASS')
    crit['I4'] = all(c['actual']=='UNKNOWN' for c in cases if c['expected']=='UNKNOWN')
    crit['I5'] = not any(result['leakage'].values()) and all(v['requirements_after'] and all(x.startswith('INDICATION:') for x in v['requirements_after']) for q,v in result['queries'].items() if q.startswith('H'))
    crit['I6'] = all(result['queries'][q]['top20_unchanged'] for q in ['TAC01','mint5']) and result['queries']['TAC01']['passes_preserved'] and not result['queries']['mint5']['transitions']
    crit['I7_mechanical'] = all(v['isolation'] for v in result['queries'].values())
    crit['I7_review'] = 'PENDING_INDEPENDENT_CONDITION_REVIEW'
    crit['I8'] = False  # Initial targeted quality gate failed; never patched after results.
    result['status'] = 'FAILED_ACCEPTANCE'
    (OUT/'score.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print(crit, flush=True)


if __name__=='__main__':
    main()
