import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path('/home/djmann/projects/bve-b8')
OUT=Path('/tmp/human_efficacy_context_safety_v1_result')
s=json.loads((OUT/'score.json').read_text())
assert s['decision']=='FAILED_ACCEPTANCE'
testroot=ET.parse(OUT/'tests.xml').getroot()
suites=list(testroot) if testroot.tag=='testsuites' else [testroot]
totals={k:sum(int(x.get(k,0)) for x in suites) for k in ['tests','failures','errors','skipped']}
failure_nodes=[{'file':c.get('classname'),'test':c.get('name'),'message':f.get('message')} for c in testroot.iter('testcase') for f in list(c) if f.tag in ['failure','error']]
(OUT/'test_failure_inventory.json').write_text(json.dumps({'totals':totals,'failures':failure_nodes},indent=2)+'\n')
before={}
for f in ['src/bve/se/evidence/human_poc.py','tests/se/test_human_efficacy_context_safety.py','scripts/score_human_efficacy_context_safety_v1.py']:
    data=(ROOT/f).read_bytes();dst=OUT/Path(f).name;dst.write_bytes(data);before[f]=hashlib.sha256(data).hexdigest()
counts={'clinical_expected':sum(w['expected_pass'] for w in s['witnesses']),
        'clinical_preserved':sum(w['expected_pass'] and w['actual_pass'] for w in s['witnesses']),
        'false_expected':sum(not w['expected_pass'] for w in s['witnesses']),
        'false_rejected':sum(not w['expected_pass'] and not w['actual_pass'] for w in s['witnesses']),
        'legacy_calls_preserved':sum(c['expected']==c['actual'] for c in s['existing_controls']),
        'legacy_calls_total':len(s['existing_controls'])}
(OUT/'attempt_manifest.json').write_text(json.dumps({'preregistration_commit':'38ca6c86e8d9479eae874eabb1533be999e0a232','implementation_commit':'755e9c1','preexecution_scorer_fixture_commit':'b1645a3','source_hashes':before,'first_acceptance_decision':'FAILED_ACCEPTANCE','tests':totals,'counts':counts,'no_post_result_behavior_patch':True},indent=2)+'\n')
report='''# HUMAN_EFFICACY_CONTEXT_SAFETY v1 — failed acceptance result

**Decision: FAILED_ACCEPTANCE. Do not adopt. Normal reversion required.**

Preregistration `38ca6c8`; implementation attempt `755e9c1`; scorer-only required-fixture
completion `b1645a3` before the scorer's first execution. No production change, label
change or acceptance-rule amendment followed the failing measurement.

This is diagnostic evidence-only evaluation, not a search replay or top20 rescore.
H6–H10 remain UNRUN. Frozen primary validation remains FAIL 0/5. H16–H20 are exposed
development data and cannot count as future generalization evidence.

## Frozen criteria

| Criterion | Result |
|---|---|
'''
for criterion,value in s['criteria'].items():report+=f'| {criterion} | {"PASS" if value else "FAIL"} |\n'
report+=f'''
Both exact primary false witnesses are rejected by the attempted reader. H18's human-cell
assay and H19's model/discount-rate sentence cannot supply human-PoC under the attempt.
That alone is insufficient for adoption: true-positive preservation and other frozen
requirements must pass simultaneously.

Full tests/se: **{totals['tests']-totals['failures']-totals['errors']-totals['skipped']} passed,
{totals['failures']} failed, {totals['errors']} errors, {totals['skipped']} expected xfails**.
Required Ruff checks are clean. The first Ruff invocation did not inspect code because
the sandbox refused its cache write; an unchanged-code `--no-cache` retry passed. That
infrastructure retry and original log are preserved separately.

Of {counts['clinical_expected']} pre-adjudicated clinical claim witnesses,
{counts['clinical_preserved']} remain admitted. Of {counts['false_expected']} pre-adjudicated
numerical false witnesses, {counts['false_rejected']} reject. Existing reader-call
outcomes preserved: {counts['legacy_calls_preserved']}/{counts['legacy_calls_total']}.
These are per-claim/run witnesses, so repeated source sentences across benchmarks count
separately here; preregistration also records distinct-passage and test-input counts.

## Exact failed semantic controls

'''
for c in s['semantic_failures']:report+=f"- {c['id']} ({c['category']}): expected {c['expected_pass']}, actual {c['actual_pass']}. `{c['text']}`\n"
for c in s['structured_failures']:report+=f"- Structured {c['id']}: expected {c['expected_pass']}, actual {c['actual_pass']}.\n"
report+='\n## Exact failed preserved/adjudicated witnesses\n\n'
for w in s['witness_failures']:report+=f"- {w['run']} / {w['name']} / survey {w['survey_id']} / `{w['claim_id']}`: expected {w['expected_pass']}, actual {w['actual_pass']}.\n"
report+='''
## Reversion and stopping rule

The stricter structural matcher was not adequate for the whole frozen clinical population.
The full failure inventory, first scorer output, attempted source/test/scorer bytes and
preregistered judgments are retained. No individual failure may be rescued by a post-result
patch, new exception, edited positive label, weaker criterion or benchmark/top20 optimization.

Revert the scorer-fixture commit and the implementation commit normally, verify byte-level
restoration against the preregistered clean baseline, update the handoff, and stop. A future
v2 requires new diagnosis/preregistration; this result does not authorize it or any later
target, qualification, identity, modality or ranking milestone.
'''
(OUT/'result.md').write_text(report)
print(json.dumps({'criteria':s['criteria'],'tests':totals,'counts':counts},indent=2))
