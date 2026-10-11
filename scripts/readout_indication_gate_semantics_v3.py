"""Post-adoption projection of frozen results; no acquisition or ranking change."""
from pathlib import Path
from collections import defaultdict,Counter
import json,hashlib,gc
from bve.se.pipeline import SESearchResult
from bve.se.reporting.shortlist import build_shortlist
from bve.se.gates.engine import _requirement
from bve.se.gates.evaluator import evaluate_indication
from bve.se.schemas.contracts import NormalizedFact,RequirementOperator

R=Path('/home/djmann/projects/bve-b8');O=R/'research/se_indication_gate_semantics_v3';P=json.loads((O/'population.json').read_text());I='strategy.indication'
assert json.loads((O/'acceptance.json').read_text())['status']=='ADOPTED'
oldlabels=json.loads((R/'research/se_shortlist_diag/classified_v1.json').read_text())
rows={q:{x['name'].casefold():x for x in d['rows']} for q,d in oldlabels.items()}
labels={**json.loads((R/'research/se_heldout/labels_v1.json').read_text()),**json.loads((R/'research/se_heldout/labels_v3.json').read_text())}
output={'scope':'Post-adoption development readout only; no generalization evidence','runs':{}}
for q,run in P['runs'].items():
 raw=json.loads(Path(run['result']).read_text());assert hashlib.sha256(Path(run['result']).read_bytes()).hexdigest()==run['sha256']
 before=build_shortlist(SESearchResult.model_validate(raw),limit=20);before_ids=[e.asset_id for e in before.entries]
 cands={a['asset_id']:a for a in raw['candidates']};low=set(raw['low_support_asset_ids']);before_members=set(cands)-set(raw['excluded_asset_ids'])-low
 facts=defaultdict(list)
 for f in raw['facts']:
  if f['fact_type']=='indication':facts[f['subject_id']].append(NormalizedFact.model_validate(f))
 requested=next(c['requested'] for c in P['cases'] if c['query']==q);baseline_nonind={g['subject_id']:[d.copy() for d in g['decisions'] if d['requirement_id']!=I] for g in raw['gate_evaluations']}
 for gate in raw['gate_evaluations']:
  for n,d in enumerate(gate['decisions']):
   if d['requirement_id']==I:
    gate['decisions'][n]=evaluate_indication(_requirement(I,'indication',RequirementOperator.IN,requested),subject_id=gate['subject_id'],facts=facts[gate['subject_id']],gate_id='strategic_sandbox').model_dump(mode='json')
  statuses=[d['status'] for d in gate['decisions']];gate['disposition']='EXCLUDED' if 'FAIL' in statuses else 'UNRESOLVED' if 'UNKNOWN' in statuses else 'ELIGIBLE'
  assert baseline_nonind[gate['subject_id']]==[d for d in gate['decisions'] if d['requirement_id']!=I]
 for key,disposition in [('excluded_asset_ids','EXCLUDED'),('unresolved_asset_ids','UNRESOLVED'),('eligible_asset_ids','ELIGIBLE')]:raw[key]=[g['subject_id'] for g in raw['gate_evaluations'] if g['disposition']==disposition]
 after=build_shortlist(SESearchResult.model_validate(raw),limit=20);after_ids=[e.asset_id for e in after.entries];after_members=set(cands)-set(raw['excluded_asset_ids'])-low
 gates={g['subject_id']:g for g in raw['gate_evaluations']};refs={c['asset_id']:c for c in P['cases'] if c['query']==q and c['reference']};labelmap={name.casefold():lab for name,lab in labels.get(q,{}).items()} if q.startswith('H') else {}
 top=[];seen=set()
 for entry in after.entries:
  a=cands[entry.asset_id];known=rows.get(q,{}).get(entry.name.casefold());lab=labelmap.get(entry.name.casefold(),'UNLABELED');category=known.get('class') if known else None
  if entry.asset_id in refs and lab=='UNLABELED':lab='RELEVANT'
  target=next((d['status'] for d in gates.get(entry.asset_id,{}).get('decisions',[]) if d['requirement_id']=='target.expression'),'UNKNOWN')
  identity=frozenset(a['identity_keys'])
  duplicate=bool(identity and identity in seen);seen.add(identity)
  top.append({'position':entry.position,'name':entry.name,'asset_id':entry.asset_id,'label':lab,'historical_class':category,'target':target,'duplicate_identity_key_set':duplicate})
 counts=Counter(x['label'] for x in top);unknown=counts['UNLABELED'];relevant=counts['RELEVANT']
 references=[{'name':c['name'],'asset_id':aid,'visible_before':aid in before_members,'visible_after':aid in after_members,'historical_only_indication_excluded':c['historical_only_indication_exclusion']} for aid,c in refs.items()]
 output['runs'][q]={'shortlist_counts_before':before.counts,'shortlist_counts_after':after.counts,'membership_added':len(after_members-before_members),'membership_removed':len(before_members-after_members),'top20_before':[e.name for e in before.entries],'top20_after':top,'top20_order_unchanged':before_ids==after_ids,'references':references,'reference_recovery':sum(x['visible_after'] and x['historical_only_indication_excluded'] for x in references),'known_label_counts':dict(counts),'known_TARGET_UNKNOWN_FILL':sum(x['historical_class']=='D' for x in top),'all_target_unknown_rows':sum(x['target']=='UNKNOWN' for x in top),'known_NON_PRODUCT':counts['NON_ASSET'],'known_duplicates':counts['DUPLICATE'],'identity_key_duplicates':sum(x['duplicate_identity_key_set'] for x in top),'unlabeled_rows':unknown,'precision_at20':relevant/20 if not unknown else None,'precision_bounds':{'lower':relevant/20,'upper':(relevant+unknown)/20},'limitation':'New rows without frozen labels remain UNLABELED; pollution counts are confirmed counts, not invented complete labels.'}
 print(q,'membership',len(before_members),'->',len(after_members),'top unchanged',before_ids==after_ids,'labels',dict(counts),flush=True)
 (O/'diagnostic_readout.json').write_text(json.dumps(output,sort_keys=True,indent=2)+'\n')
 del raw,facts,cands,before,after;gc.collect()
