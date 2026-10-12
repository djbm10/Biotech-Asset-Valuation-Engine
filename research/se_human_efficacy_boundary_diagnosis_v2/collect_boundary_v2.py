import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path('/home/djmann/projects/bve-b8')
BASE = ROOT / 'research/se_human_efficacy_context_safety_v1'
OUT = Path('/tmp/human_efficacy_boundary_diagnosis_v2')
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / 'src'))
from bve.se.evidence import human_poc as hp
from bve.se.evidence.source_capability import may_establish_human_poc

spec = importlib.util.spec_from_file_location('archived_context_attempt', BASE / 'result/human_poc.py')
attempt = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = attempt
spec.loader.exec_module(attempt)

def load(name):
    return json.loads((BASE / name).read_text())

def dump(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

score = load('result/score.json')
survey = load('unique_witness_survey.json')
population = load('benchmark_population.json')
lookup = {(a['run'], w['claim']['claim_id']): (a, w)
          for a in population for w in a['witnesses']}
false = [r for r in score['witness_failures'] if not r['expected_pass']]
losses = [r for r in score['witness_failures'] if r['expected_pass']]
assert len(false) == 2 and len(losses) == 19
for sid in [97, 109]:
    wanted = 'claim:9954996062248331a551' if sid == 97 else 'claim:6c5b35e2a5871015f940'
    r = next(row for row in survey[sid]['rows'] if row['claim_id'] == wanted)
    false.append(dict(r, survey_id=sid, expected_pass=False))

# Manual source-grounded observations, not an executable admission rule or new labels.
# Axes: evidence world; actual outcome quantity; relationship; attribution caveat.
annotations = {
  64: ('observed patient case / combination', 'No numerical efficacy quantity. 4/13 identifies interleukin targets.',
       'Complete remission is qualitative; 4/13 is inside the antibody-description parenthesis, not a result argument.',
       'Combination therapy explicitly named; current immediate-name regimen guard misses the apposition. Do not infer component-specific efficacy.'),
  97: ('human-derived laboratory material', 'Respiration percentages are cell-assay measurements; p-values and timepoints are ancillary.',
       'Human modifies myotubes; responses refers to respiration. First percent belongs to other agents, later percent to tirzepatide.',
       'Named asset exists but there is no treated clinical cohort. Title also establishes In Vitro; local sentence omits that exact veto phrase.'),
  109: ('simulated patient trajectories / economic model', '5% is an annual discount rate, not patient efficacy.',
       'Survival names a model; patient is the modeled entity. The quantity belongs to discount rate in a later comma clause.',
       'Asset is a modeled comparison, not the recipient of an observed patient outcome in this witness.'),
  11: ('observed treated patients / comparative groups', '84.5% and 73.0% are objective response rates; P is statistical support.',
       'Endpoint and cohort precede asset and rates; treatment-group mapping uses with/without and respectively across phrases.',
       'Group-specific comparison, not free attachment of every number to every named product.'),
  26: ('observed induction patients / regimen', '3 achieved CR, 2 MRD-negative. 5 patients (31.2%) describes subgroup enrollment.',
       'Clinical outcome is a plain count in a later comma clause; the regex percentage is not that outcome.',
       'VEN plus AZA combined with IVO is explicit regimen. Frozen clinical-content positive stands; individual attribution is a separate existing concern.'),
  42: ('observed patients / response stratum', '28.6% ultimately progressed.',
       'Progressed is an observed event; current efficacy term is CR in PET30-CR, not the event verb.',
       'PET30-CR is a response stratum in this passage. Therapeutic asset identity is not established by clinical-content truth.'),
  54: ('observed patients / time-indexed outcomes', '79% alive at 6 months; 60% at 12 months; PFS 52% to 42%.',
       'First clause says alive, later clauses name survival and supply time/comparison ellipsis. Current first quantity and first endpoint are in different clauses.',
       'Candidate name though is a conjunction. Existing accepted claim is clinical-content positive, not proof that this token is an asset.'),
  62: ('observed treated patients', '87.7% responder rate; 70% amenorrhea; 52 weeks is follow-up.',
       'Asset, efficacy and first rate precede the clause naming patients. Cohort language need not be repeated for each coordinated outcome.',
       'Relugolix-CT names a treatment; preserve existing candidate/regimen identity semantics.'),
  69: ('observed treated patients / regimen', '>95% sustained virologic response at posttreatment Week 12.',
       'Rate precedes endpoint; patients appear later with eligibility strata and abbreviations. Slashes also encode a combination.',
       'Glecaprevir/pibrentasvir regimen outcome; do not silently convert it to separately demonstrated component efficacy.'),
  78: ('observed patients / comparative groups', 'Source completes PFS 15.6 vs 12.0 months and OS 38.4 vs 32.0 months. n=17/n=9 are group sizes.',
       'Witness is truncated by vs. sentence split. Quantitative outcome requires bounded continuation; current selected n=17 is not efficacy.',
       'Compare anti-EGFR and bevacizumab treatment groups; source context describes combination with first-line chemotherapy.'),
  80: ('observed clinical trial patients / multiple regimens', '70.1% comparison is truncated at vs.; source continuation resolves response proportions. P=0.0015 is statistical support; viral-load cutoff is baseline.',
       'Treatment list, RNA response, cohort and rate span coordinated phrases. Surface slashes/abbreviations are not outcome quantities.',
       'Multiple regimens and backbones are named. Clinical-content truth does not resolve component-specific strict attribution.'),
  92: ('observed treated patients / comparative regimens', '40 patients (93%) and 31 (89%) achieved virological endpoint at 12 months.',
       'HIV RNA <20 copies/ml is the outcome threshold; percentages are observed attainments, not threshold, PK, or baseline viral load.',
       'BIC/F/TAF and DOR/3TC/TDF are comparison regimens; Lamivudine candidate is a component alias (3TC).'),
  99: ('observed treated patients / placebo comparison', '24%, 23%, 12% responders at 300 microg, 100 microg, placebo respectively.',
       'Responders/cohort first, drug later, rates and arm mapping in parenthesis. Doses and p-values have different roles.',
       'Explicit named drug and placebo arms; retain mapping rather than nearest-number attachment.'),
  103: ('observed treated patients / placebo comparison', '65.7% vs 38.9% achieved clinical response; >=20% reduction defines response.',
       'Endpoint definition and its threshold sit between cohort and observed responder proportions; secondary end points can introduce reported results.',
       'Named drug compared with placebo; PS volume outcome is clinical support requirement, not plasma concentration.'),
  104: ('observed treated patients / placebo comparison', '84.2% vs 24.3% achieved >=30% LFC reduction.',
       'Observed proportions precede threshold. Efficacy estimand names analysis; modeled worlds cannot be rejected merely by an analysis word.',
       'Survodutide-treated and placebo-treated groups explicitly identify comparative attribution.'),
  0: ('observed treated patients / placebo comparison', '26/97 (26.8%) vs 53/97 (54.6%) had flares (denominators in abstract).',
      'Event, counts, patients and treatment arms in one sentence but multiple comparator phrases.', 'Explicit drug versus placebo groups.'),
  1: ('observed treated patients', '90% of 20 achieved CR/CRi within 28 days.',
      'CNCT19 cells are administered therapy; cells does not denote the study population here.', 'Named cell treatment and treated patients in same assertion.'),
  2: ('observed treated patients', 'Median OS 12.91 months and relapse-free survival 6.93 months; 95% marks confidence interval, not efficacy magnitude.',
      'Result durations mapped by respectively after cohort/treatment; multiple commas partition confidence intervals.', 'Named cell treatment; actual outcome magnitude differs from current selected 95%.'),
  8: ('observed treated patients', '1/10 achieved CR with incomplete platelet recovery.',
      'Outcome follows treated cohort; low efficacy is a legitimate unfavorable observed result.', 'Named treatment, no efficacy-success threshold required.'),
  14: ('observed evaluable patients', '47.6% overall response and 14.3% CR; 21 evaluable out of 25 treated.',
       'ORR abbreviation plus later spelled complete response; denominator and drug follow rates.', 'Named treated cohort.'),
  15: ('observed treated patients', 'All six achieved MRD-negative remission; >5% marrow blasts is pretreatment burden.',
       'Word-valued count is outcome; regex first percent refers to prior disease, not response.', 'Named drug induced remission, prior burden separately described.'),
  24: ('observed treated patients', '10 of 12 achieved stringent complete remission.',
       'Cohort/comorbidity before treatment, remission after treatment clause; CAR T cells are intervention, not human-cell assay.', 'Named administered product and treated human cohort.'),
  29: ('observed treated patient groups', '30.2% vs 60.6% overall response; subsequent clause concerns CRS safety.',
       'Independent observed efficacy survives neighboring safety; prior BCMA therapy defines strata.', 'Named product efficacy across two pretreated strata.'),
}

def spans(text, terms, bounded=False):
    out = []
    for term in terms:
        pattern = (r'\b' + re.escape(term) + r'\b') if bounded else re.escape(term)
        out.extend({'text': m.group(), 'start': m.start(), 'end': m.end(), 'term': term}
                   for m in re.finditer(pattern, text, re.I))
    return sorted(out, key=lambda x: (x['start'], x['end'], x['term']))

def decode(text):
    return re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m[1], 16)), text)

def trace(text, names):
    named = next((n for n in sorted(set(names), key=len, reverse=True)
                  if n.casefold() in text.casefold()), None)
    value = hp._VALUE.search(text)
    return {
      'length': len(text), 'within_sentence_limit': len(text) <= hp._MAX_SENTENCE_CHARS,
      'human_context': hp._mentions_humans(text), 'human_matches': spans(text, hp._HUMAN_TERMS) + spans(text, ['pt','pts'], True),
      'efficacy_term': hp._efficacy_term(text), 'efficacy_matches': spans(text, hp._EFFICACY_TERMS) + spans(text, ['CR'], True),
      'first_numeric_value': None if value is None else {'text':value.group(), 'start':value.start(),'end':value.end()},
      'all_numeric_regex_matches':[{'text':m.group(),'start':m.start(),'end':m.end()} for m in hp._VALUE.finditer(text)],
      'asset_named':named, 'asset_mentions':spans(text, names),
      'eligibility_veto':hp._contains(text,hp._ELIGIBILITY_TERMS),
      'safety_non_efficacy_veto':hp._contains(text,hp._NON_EFFICACY_TERMS),
      'safety_clean_clause_exception':hp._reports_efficacy_clear_of_safety(text),
      'unreported_veto':hp._contains(text,hp._UNREPORTED_TERMS),
      'nonhuman_veto':hp._contains(text,hp._NONHUMAN_TERMS),
      'regimen_veto':bool(named and hp._reports_a_regimen(text,named,names)),
      'regimen_list_veto':bool(named and hp._is_regimen_list_item(text,named)),
      'statements':[r.model_dump(mode='json') for r in hp.efficacy_statements(text,asset_names=names)],
      'archived_v1_population':attempt._clinical_population(attempt._analysis_text(text)),
      'archived_v1_outcome_value':attempt._clinical_outcome_value(text),
      'archived_v1_statements':[r.model_dump(mode='json') for r in attempt.efficacy_statements(text,asset_names=names)],
    }

def fragments(text):
    # Observational boundaries only; no claim that every comma creates a semantic clause.
    result=[]; start=0
    for m in hp._CLAUSE.finditer(text):
        result.append({'start':start,'end':m.start(),'text':text[start:m.start()],'delimiter':m.group()});start=m.end()
    result.append({'start':start,'end':len(text),'text':text[start:],'delimiter':None})
    return result

def signal_map(text, names):
    fs=fragments(text); tr=trace(text,names)
    categories={'asset':tr['asset_mentions'],'human':tr['human_matches'],
                'efficacy':tr['efficacy_matches'],'numeric':tr['all_numeric_regex_matches']}
    out={}
    for key, matches in categories.items():
        out[key]=[dict(m, fragment_indices=[i for i,f in enumerate(fs)
                         if m['start'] < f['end'] and m['end'] > f['start']]) for m in matches]
    out['interpretation']='Indices refer to the existing surface clause splitter; same-fragment proximity is observational, not a semantic admission rule. Neighboring source text is separately frozen.'
    return out

records=[]
def add(row, group):
    a,w=lookup[(row['run'],row['claim_id'])]; sid=row['survey_id']; text=w['claim']['supporting_passage']
    abstract=w.get('source_abstract') or ''; decoded=decode(text)
    needle=decoded.removeprefix('"abstract": "'); idx=abstract.find(needle)
    if idx<0:
        # Some raw snapshot witnesses contain escaped quote/field suffixes.
        needle=needle.rstrip('"}, ');idx=abstract.find(needle)
    path=Path(w['document']['snapshot_path']); actual=hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual==w['snapshot_sha256'], (path,actual,w['snapshot_sha256'])
    world,quantity,relationship,attribution=annotations[sid]
    records.append({
      'id':f'{group}:{row["run"]}:{row["claim_id"]}', 'group':group,'run':row['run'],
      'name':a['name'],'asset_names':a['asset_names'],'survey_id':sid,
      'frozen_content_positive':group!='known_false', 'claim':w['claim'],
      'exact_passage':text,'decoded_analysis_passage':decoded,
      'source':w['document'],'source_title':w['source_title'],'source_abstract':abstract,
      'snapshot_sha256':actual,'source_match':{'matched':idx>=0,'start':idx,'end':idx+len(needle) if idx>=0 else None,
        'text':needle if idx>=0 else None,'neighbor_before':abstract[max(0,idx-500):idx] if idx>=0 else None,
        'neighbor_after':abstract[idx+len(needle):idx+len(needle)+600] if idx>=0 else None},
      'current_predicates':trace(text,a['asset_names']),
      'signal_fragment_map':signal_map(text,a['asset_names']),
      'surface_fragments':fragments(text),
      'all_numerical_tokens':[{'text':m.group(),'start':m.start(),'end':m.end()}
                              for m in re.finditer(r'\d+(?:\.\d+)?(?:\s*%|\s*/\s*\d+)?',text)],
      'semantic_observation':{'world':world,'quantity_roles':quantity,'signal_relationship':relationship,
                              'attribution_scope_caveat':attribution},
      'source_type_predicates':{'may_establish_human_poc':may_establish_human_poc(w['document']['document_type']), 'registry_prose_exclusion':w['document']['document_type']=='trial_registry_record', 'clinical_study_world_predicate':None},
      'source_type_handling':'publication_abstract is eligible for prose human-PoC; no study-world check. This trace is the exact supporting passage, not a corpus replay.',
    })

for r in false:add(r,'known_false')
for r in losses:add(r,'v1_removed_clinical')
for sid in [0,1,2,8,14,15,24,29]:
    row=survey[sid]['rows'][0];add(dict(row,survey_id=sid),'accepted_representative')

legacy_ids=['6d78dc914bd1f5210d52ebcd432011ae63c50cd3abe0c0ce11fb89539878b2ea',
            'be39eb3f78e48cd8e18e5a3d8ba3f1e0eea265ec153153d2d2dd47f63d3bd13f']
for r in load('existing_test_population.json'):
    if r['id'] not in legacy_ids:continue
    text=r['inputs']['text'];names=r['inputs']['asset_names']
    records.append({'id':r['id'],'group':'changed_legacy','name':names[0],'run':'existing_tests',
      'exact_passage':text,'asset_names':names,'frozen_content_positive':True,'source_type_handling':'synthetic prose test; no publication metadata',
      'legacy_input':r,'current_predicates':trace(text,names),'signal_fragment_map':signal_map(text,names),'surface_fragments':fragments(text),
      'all_numerical_tokens':[{'text':m.group(),'start':m.start(),'end':m.end()} for m in re.finditer(r'\d+(?:\.\d+)?(?:\s*%|\s*/\s*\d+)?',text)],
      'semantic_observation':{'world':'observed treated/evaluable patients',
        'quantity_roles':'10/16 ongoing BM CR; 3.4 months is follow-up.' if names[0]=='CTL019' else '30% observed flare-risk reduction; 194 is cohort size.',
        'signal_relationship':'pts abbreviation establishes cohort; BM CR abbreviation supplies endpoint.' if names[0]=='CTL019' else 'Outcome in first clause, observed cohort in following comma clause.',
        'attribution_scope_caveat':'Named treated asset; preserve existing strict attribution.'}})

assert len(records)==33
assert all(r['current_predicates']['statements'] for r in records)
assert all(not r['current_predicates']['archived_v1_statements'] for r in records if r['group'] in ['v1_removed_clinical','changed_legacy'])
dump('witness_register.json',records)
dump('selection.json',{'milestone':'HUMAN_EFFICACY_BOUNDARY_DIAGNOSIS v2','diagnosis_only':True,
  'selection':'All four specified false claims, all 19 pre-adjudicated clinical claim/run losses, both changed legacy inputs, plus deterministic survey IDs 0,1,2,8,14,15,24,29 for contrasting accepted structures.',
  'groups':{g:sum(r['group']==g for r in records) for g in sorted({r['group'] for r in records})},
  'false_distinct_passages':len({r['exact_passage'] for r in records if r['group']=='known_false'}),
  'clinical_loss_distinct_passages':len({r['exact_passage'] for r in records if r['group']=='v1_removed_clinical'}),
  'source_matches':sum(r.get('source_match',{}).get('matched',False) for r in records),
  'clinical_content_not_asset_truth':'Existing expected_pass labels concern clinical content under old attribution guards; identity/regimen correctness is separately recorded, not relabeled.',
  'no_new_admission_rule':True,'no_preregistration':True,'no_corpus_replay':True})

lines=['# HUMAN_EFFICACY_BOUNDARY_DIAGNOSIS v2 — side-by-side witnesses','',
 'Exact text, offsets, source context and all predicate results are frozen in `witness_register.json`. Offsets are Unicode character indices in exact_passage, not decoded text. Surface fragments expose the existing splitter, not a proposed semantic parser.','',
 '| Group / asset / witness | Exact witness | Clinical world and quantity roles | Signal relationship / attribution limits | Current v4 vs archived attempt |',
 '|---|---|---|---|---|']
for r in records:
    obs=r['semantic_observation'];tr=r['current_predicates']
    esc=lambda s:str(s).replace('|','\\|').replace('\n','<br>')
    cols=[f'{r["group"]} / {r["run"]} / {r["name"]} / {r.get("survey_id",r["id"])}',r['exact_passage'],
          obs['world']+'. '+obs['quantity_roles'],obs['signal_relationship']+' '+obs['attribution_scope_caveat'],
          f'v4 PASS; human={tr["human_context"]}; endpoint={tr["efficacy_term"]}; first value={tr["first_numeric_value"]["text"]}; v1 '+('PASS' if tr['archived_v1_statements'] else 'UNKNOWN')]
    lines.append('| '+' | '.join(map(esc,cols))+' |')
(OUT/'side_by_side.md').write_text('\n'.join(lines)+'\n')
dump('input_manifest.json',{'baseline_commit':'813b215122b6dfd6b36c2ff4fd2a21ae087325f8',
 'extractor_version':hp.EXTRACTOR_VERSION,'files':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
 for path in [BASE/'benchmark_population.json',BASE/'unique_witness_survey.json',BASE/'existing_test_population.json',BASE/'witness_adjudications.json',BASE/'result/score.json',BASE/'result/human_poc.py',ROOT/'src/bve/se/evidence/human_poc.py',ROOT/'src/bve/se/evidence/source_capability.py',ROOT/'src/bve/se/pipeline.py',ROOT/'docs/se_policies/primary_validation_failure_diagnosis_v1.md']}})
print(json.dumps(json.loads((OUT/'selection.json').read_text()),indent=2))
