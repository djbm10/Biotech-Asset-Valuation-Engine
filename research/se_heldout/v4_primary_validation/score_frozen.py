"""Artifact-only scoring of committed H16-H20 labels; never runs the engine."""
import hashlib
import json
import re
import subprocess
from pathlib import Path
import yaml

ROOT = Path('/home/djmann/projects/bve-b8')
PACKET = ROOT / 'research/se_heldout/v4_primary_validation'
OUT = Path('/tmp/heldout_v4_primary_validation')
LABEL_COMMIT = 'eed63eb7dd5c3ea4387a2b9789c6d886229bbaf5'
REFS = {
 'H16': [['relatlimab','Opdualag','BMS-986016'], ['fianlimab','REGN3767'],
         ['favezelimab','MK-4280'], ['ieramilimab','LAG525'], ['encelimab','TSR-033'], ['tebotelimab','MGD013']],
 'H17': [['dupilumab','Dupixent','REGN668'],['stapokibart','CM310'],['rademikibart','CBP-201'],['comekibart','QX005N'],['manfidokimab','611']],
 'H18': [['semaglutide','Ozempic','Wegovy','Rybelsus'],['tirzepatide','Mounjaro','Zepbound','LY3298176'],
         ['liraglutide','Saxenda','Victoza'],['orforglipron','LY3502970'],['survodutide','BI 456906'],
         ['retatrutide','LY3437943'],['mazdutide','IBI362','LY3305677'],['danuglipron','PF-06882961']],
 'H19': [['sacituzumab govitecan','Trodelvy','IMMU-132'],['datopotamab deruxtecan','Datroway','Dato-DXd','DS-1062'],
         ['sacituzumab tirumotecan','sac-TMT','MK-2870','SKB264'],['ESG401'],['BL-M02D1']],
 'H20': [['abelacimab','MAA868'],['osocimab','BAY 1213790'],['asundexian','BAY 2433334'],
         ['milvexian','BMS-986177','JNJ-70033093'],['fesomersen','IONIS-FXIRx','BAY 2976217'],['xisomab','AB023']]
}
INTENDED = dict(zip(['H16','H17','H18','H19','H20'],['LAG3','IL4R','GLP1R','TACSTD2','F11']))

def read(path):
    return json.loads(path.read_text())

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

labels = read(PACKET/'labels.json')
audit = read(PACKET/'human_poc_labels.json')
manifest = read(PACKET/'input_manifest.json')
freeze = read(PACKET/'label_freeze_manifest.json')
assert freeze['metrics_calculated'] is False
for rel, expected in freeze['files'].items():
    assert digest(PACKET/rel) == expected, ('frozen packet changed',rel)
for rel in ['labels.json','human_poc_labels.json','blind_top20.json']:
    committed = subprocess.check_output(['git','show',f'{LABEL_COMMIT}:research/se_heldout/v4_primary_validation/{rel}'],cwd=ROOT)
    assert committed == (PACKET/rel).read_bytes(), ('labels not committed',rel)
for q, run in manifest['runs'].items():
    for rel, expected in run['files'].items():
        assert digest(Path(run['directory'])/rel) == expected['sha256'], ('input changed',q,rel)

key = lambda s: re.sub(r'[^a-z0-9]','',s.casefold())
rows = []
for q, labeled in labels['queries'].items():
    if labeled['outcome'] == 'REFUSED':
        rows.append({'query_id':q,'engine_outcome':'REFUSED','target_recognition':{'intended':INTENDED[q],'compiled':[],'exact':False},
                     'refusal_reason':labeled['reason'],'P@20':None,'recall_all':None,'recall_20':None,
                     'NON_ASSET':None,'DUPLICATE':None,'false_human_poc':None,'source_coverage':None,
                     'run_status':'REFUSED','verdict':'FAIL','failed_criteria':['query refused / no target recognition'],
                     'metric_note':'N/A: no shortlist exists. Frozen suite refusal rule sets query-level FAIL; no synthetic zero-valued shortlist.'})
        continue
    p=PACKET/'evidence'/q
    all_entries=read(p/'all_shortlist_names.json')
    top=read(p/'emitted_top20.json')
    assert [x['asset_id'] for x in top] == [x['asset_id'] for x in labeled['rows']]
    assert [x['asset_id'] for x in all_entries[:20]] == [x['asset_id'] for x in top]
    codes=[r['label'] for r in labeled['rows']]
    denominator=sum(c!='UNVERIFIABLE' for c in codes)
    numerator=codes.count('RELEVANT')
    p20=numerator/denominator if denominator else None
    def match(entries):
        keys={key(s) for e in entries for s in [e['canonical_name'],*e['aliases']]}
        return [r[0] for r in REFS[q] if any(key(s) in keys for s in r)]
    found_all=match(all_entries)
    found_top=match(all_entries[:20])
    r_all=len(found_all)/len(REFS[q])
    r_top=len(found_top)/len(REFS[q])
    human=read(p/'human_poc_audit_input.json')
    emitted_fact_ids={f['subject_id'] for f in human['facts'] if f['value'] is True}
    audit_ids={top[a['position']-1]['asset_id'] for a in audit['queries'][q]}
    assert emitted_fact_ids == audit_ids
    false_poc=sum(a['false_human_poc'] for a in audit['queries'][q])
    problem=yaml.safe_load((p/'problem.yaml').read_text())
    compiled=sorted(t['canonical_id'] for t in problem['strategic_gap']['target_expression']['targets'])
    exact=compiled==[INTENDED[q]]
    checks={'target_recognition':exact,'P@20>=0.70':p20 is not None and p20>=.70,
            'recall_all>=0.60':r_all>=.60,'NON_ASSET<=1':codes.count('NON_ASSET')<=1,
            'DUPLICATE<=2':codes.count('DUPLICATE')<=2,'false_human_poc=0':false_poc==0}
    summary=read(p/'summary.json')
    runmanifest=read(p/'run_manifest.json')
    rows.append({'query_id':q,'engine_outcome':'RESULT','target_recognition':{'intended':INTENDED[q],'compiled':compiled,'exact':exact},
                 'P@20':p20,'precision_numerator':numerator,'precision_denominator':denominator,
                 'recall_all':r_all,'recall_20':r_top,'reference_size':len(REFS[q]),'found_all':found_all,'found_top20':found_top,
                 'all_shortlist_size':len(all_entries),'NON_ASSET':codes.count('NON_ASSET'),'DUPLICATE':codes.count('DUPLICATE'),
                 'WRONG_TARGET':codes.count('WRONG_TARGET'),'UNVERIFIABLE':codes.count('UNVERIFIABLE'),
                 'false_human_poc':false_poc,'human_poc_rows':audit['queries'][q],
                 'source_coverage':runmanifest['source_status'],'run_status':runmanifest['status'],
                 'incomplete_reasons':runmanifest['incomplete_reasons'],'exit_code':summary['exit_code'],
                 'engine_commit':runmanifest['code_version'],'thresholds':checks,'failed_criteria':[k for k,v in checks.items() if not v],
                 'verdict':'PASS' if all(checks.values()) else 'FAIL',
                 'completeness_note':'Scored under preregistered --allow-incomplete; source-configuration INCOMPLETE is reported, not an added exclusion criterion.'})
passing=sum(r['verdict']=='PASS' for r in rows)
false_total=sum(r['false_human_poc'] or 0 for r in rows)
decision='PASS' if passing>=4 and false_total==0 else 'PASS_WITH_LIMITATIONS' if passing==3 else 'FAIL'
score={'protocol':'Frozen heldout_validation_suite_v4 (inherited v2 labels, v1 metrics)',
       'labels_commit':LABEL_COMMIT,'primary_validation':True,'queries':rows,'passed_queries':passing,'total_queries':5,
       'false_human_poc_total_defined_runs':false_total,'suite_decision':decision,
       'H6_H10':'UNRUN; not executed or scored','excluded_interrupted_runs':manifest['excluded_interrupted_runs'],
       'verification':'Committed label bytes, all label-freeze hashes, all original artifact hashes, exact top20 identity/order, and complete human-PoC audit coverage verified.'}
(OUT/'score.json').write_text(json.dumps(score,indent=2)+'\n')

def fmt(v):
    return 'N/A' if v is None else f'{v:.3f}'

v4=(PACKET/'frozen_rules/heldout_validation_suite_v4.md').read_text()
v1=(PACKET/'frozen_rules/heldout_validation_suite_v1.md').read_text()
run_rules=v4.split('**Run rules:**',1)[1].split('## 2.',1)[0].strip()
metrics=v4.split('## 4.',1)[1].strip()
report='''# Frozen primary validation: H16–H20 v4

**Overall suite decision: {decision}. {passing}/5 query-level PASS.**

All five observed outcomes are the frozen primary validation. Original interrupted H17/H18 runs are excluded. H6–H10 remain UNRUN. No query was rerun, rephrased, or modified, and no engine changes or diagnosis were made.

**Source coverage limitation:** H16/H18/H19 have `INCOMPLETE` status and exit code 0. ClinicalTrials.gov, PubMed and AACR report SUCCESS. Company pipeline/presentation, company press releases, ASCO, ASH, EHA and SEC EDGAR are NOT_CONFIGURED. All three are scored under the explicitly preregistered `--allow-incomplete`; missing source configuration is not a post hoc invalidation rule. H17/H20 refused at query compilation; source coverage and shortlist metrics are N/A.

## Frozen rules quoted before scoring

From v4, run rules:

> {run_rules}

From v4, metrics and overall-suite rule:

> {metrics}

Inherited v1 false-human-PoC definition: “a top-20 row with `human_poc_present` whose cited sentence is not numerical human efficacy for that product”. v1 §4 defines Recall@all as reference found anywhere on the shortlist and Recall@20 as reference found in the top 20; Recall@20 has no threshold. v2 §4 and the preserved v1 refusal results set query-level FAIL for refusal and show shortlist metrics as undefined, not invented zeros.

## Committed label freeze and extraction

Labels and human-PoC judgments were committed at `{label_commit}` before any metric aggregation or reference matching. `blind_top20.json` preserves every emitted position/name/asset ID for H16/H18/H19. Full emitted entries, all shortlist canonical names/aliases, source manifests, frozen-rule copies, input hashes and refusal logs are preserved in this packet. The frozen engine display helper was used only to expose uncapped shortlist entries from saved result bytes; its top20 was verified to exactly match the emitted shortlist artifact. This was not a search run or replay. Deferred low-support and excluded assets are not promoted into the shortlist for Recall@all, matching the prior frozen scoring procedure.

Label relevance is the frozen target-directed therapeutic-product definition; no additional modality, agonism, or indication constraint was introduced. Avexitide targets GLP1R and thus is RELEVANT under that definition. Later brand rows for the same active product are DUPLICATE. The diagnostic PET tracer is NON_ASSET for therapeutic-product precision; unspecified rescue-medication categories are NON_ASSET. Detailed NK-construct duplicate rationale is frozen in `public_label_sources.md`.

## Results

| Query | Target recognition | P@20 | Recall@all | Recall@20 | NON_ASSET | DUPLICATE | False human-PoC | Source coverage / status | Query verdict |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
'''.format(decision=decision,passing=passing,run_rules=run_rules.replace('\n',' '),metrics=metrics.replace('\n',' '),label_commit=LABEL_COMMIT)
for r in rows:
    recognition=r['target_recognition']
    target=', '.join(recognition['compiled'])+' (correct)' if recognition['exact'] else f"REFUSED; {recognition['intended']} not recognized"
    source='3 SUCCESS / 6 NOT_CONFIGURED; INCOMPLETE' if r['engine_outcome']=='RESULT' else 'N/A; REFUSED'
    report+=f"| {r['query_id']} | {target} | {fmt(r['P@20'])} | {fmt(r['recall_all'])} | {fmt(r['recall_20'])} | {r['NON_ASSET'] if r['NON_ASSET'] is not None else 'N/A'} | {r['DUPLICATE'] if r['DUPLICATE'] is not None else 'N/A'} | {r['false_human_poc'] if r['false_human_poc'] is not None else 'N/A'} | {source} | **{r['verdict']}** |\n"
report+='\n## Threshold application and reference matches\n\n'
for r in rows:
    report+=f"- **{r['query_id']}: FAIL** — "+'; '.join(r['failed_criteria'])+'.\n'
    if r['engine_outcome']=='RESULT':
        report+=f"  P@20 numerator/denominator: {r['precision_numerator']}/{r['precision_denominator']}; Recall@all: {len(r['found_all'])}/{r['reference_size']}; Recall@20: {len(r['found_top20'])}/{r['reference_size']}. All-shortlist reference matches: {', '.join(r['found_all']) or 'none'}. Top20 matches: {', '.join(r['found_top20']) or 'none'}.\n"
    else:
        report+=f"  Preserved observed refusal: `{r['refusal_reason']}`. No shortlist exists and no synthetic shortlist was created.\n"
report+='''
## Human-PoC row audit

- H16 Relatlimab: supported numerical patient response rates in a cited combination-treatment passage; false count 0. Another cited passage is nonnumerical, but the row has a qualifying numerical efficacy citation.
- H18 Tirzepatide: false human-PoC. The cited numerical changes are human-myotube respiration in vitro, not human-patient efficacy. Survodutide has numerical liver-fat response proportions in patients and is supported.
- H19 Sacituzumab Tirumotecan: false human-PoC. Its cited passage describes an economic-model simulation, not numerical observed human efficacy.
- H17/H20: N/A; no emitted rows or human-PoC claims to score.

## Frozen overall decision

The overall decision follows the quoted suite rule and includes both refused queries as query-level FAIL. Source configuration is prominently reported and does not by itself invalidate a scored result. This packet records primary validation only; it does not diagnose failures, propose fixes, change code, or run the secondary H6–H10 suite.
'''
(OUT/'report.md').write_text(report)
print(json.dumps({'suite_decision':decision,'passing':passing,'rows':[{k:r[k] for k in ['query_id','P@20','recall_all','recall_20','NON_ASSET','DUPLICATE','false_human_poc','verdict']} for r in rows]},indent=2))
