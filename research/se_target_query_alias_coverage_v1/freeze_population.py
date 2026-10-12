"""Freeze an authority-derived development population without querying the resolver."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path('/home/djmann/projects/bve-b8')
OUT = Path('/tmp/target_query_alias_coverage_v1')
SOURCE = ROOT / 'data/se/ontology/current/records.jsonl'
# Do not inspect or exercise primary/secondary heldout authority rows.
EXCLUDED = {'TSLP', 'KLKB1', 'IL1RL2', 'MSTN', 'CFD',
            'ERBB2', 'PCSK9', 'IL23A', 'DLL3', 'LRRK2'}
def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()
records = []
for line in SOURCE.open():
    row = json.loads(line)
    if row.get('entity_type') != 'TARGET' or row.get('canonical_symbol') in EXCLUDED:
        continue
    records.append(row)
chembl_uniprot = {u for r in records if r['source'] == 'chembl'
                 for u in r.get('xrefs', {}).get('uniprot', [])}
eligible = [r for r in records if r['source'] == 'open_targets'
            and r.get('canonical_symbol') and r.get('label')
            and chembl_uniprot.intersection(r.get('xrefs', {}).get('uniprot', []))]
eligible.sort(key=lambda r: digest(r['source'] + ':' + r['source_id']))
selected = eligible[:192]
greek = {'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ',
         'epsilon': 'ε', 'kappa': 'κ', 'lambda': 'λ', 'mu': 'μ',
         'sigma': 'σ', 'tau': 'τ', 'omega': 'ω'}
pattern = re.compile(r'(?<![A-Za-z])(' + '|'.join(greek) + r')(?![A-Za-z])', re.I)
greek_candidates = []
for record in eligible:
    for alias in record['aliases']:
        if pattern.search(alias['value']):
            greek_candidates.append((record, alias))
greek_candidates.sort(key=lambda pair: digest(pair[0]['source_id'] + ':' + pair[1]['value']))
seen_variants = set()
variants = []
for record, alias in greek_candidates:
    token = pattern.search(alias['value'])
    start, end = token.span()
    # Orthographic proposal only: no interpretation as a gene until an authority
    # alias and unique identifier chain certify it. Keep subunit choice intact.
    if start and alias['value'][start-1] == '-':
        start -= 1
    text = alias['value'][:start] + greek[token.group().lower()] + alias['value'][end:]
    key = (record['source_id'], text)
    if key in seen_variants:
        continue
    seen_variants.add(key)
    variants.append((record, alias, text))
    if len(variants) == 96:
        break
population = []
def add(record, kind, text, authority_alias, alias_type):
    key = digest(record['source_id'] + '\0' + kind + '\0' + text)
    population.append({'id': key, 'kind': kind, 'text': text,
                       'authority_target_symbol': record['canonical_symbol'],
                       'authority_record_key': record['source'] + ':' + record['source_id'],
                       'authority_alias': authority_alias, 'alias_type': alias_type,
                       'identifier_links': record['xrefs'],
                       'expected_scope': 'Authority entity; ambiguity/conflicting identifiers must remain unresolved.',
                       'query_frame': 'Find clinical-stage ' + text + ' therapies.'})
for record in selected:
    add(record, 'approved_symbol', record['canonical_symbol'], record['canonical_symbol'], 'SYMBOL')
    add(record, 'approved_protein_name', record['label'], record['label'], 'APPROVED_NAME')
    aliases = sorted((a for a in record['aliases'] if a['alias_type'] in {'SYMBOL','SYNONYM'}
                      and a['value'] != record['canonical_symbol'] and len(a['value']) >= 3),
                     key=lambda a: digest(a['value']))
    if aliases:
        a = aliases[0]
        add(record, 'authority_alias', a['value'], a['value'], a['alias_type'])
for record, alias, text in variants:
    add(record, 'greek_orthography_proposal', text, alias['value'], alias['alias_type'])
selected_ids = {r['authority_record_key'] for r in population}
captured_records = [r for r in records if r['source'] + ':' + r['source_id'] in selected_ids]
for name, data in [('survey_population.json', population), ('survey_authority_records.json', captured_records)]:
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
controls = [
    {'text': 'IL-4Rα', 'kind': 'H17_diagnostic', 'expected_entity': 'TARGET:IL4R'},
    {'text': 'factor XI', 'kind': 'H20_diagnostic', 'expected_entity': 'TARGET:F11'},
    {'text': 'F11', 'kind': 'existing_homonym', 'expected': 'AMBIGUOUS; do not override ZNF160 claimant'},
    {'text': 'PD-1', 'kind': 'existing_homonym', 'expected': 'preserve existing ambiguity'},
    {'text': 'CD20', 'kind': 'existing_homonym', 'expected': 'preserve existing ambiguity'},
    {'text': 'IL-4Rβ', 'kind': 'different_subunit', 'expected': 'no IL4R equivalence'},
    {'text': 'IL-4Rа', 'kind': 'Cyrillic_confusable', 'expected': 'no IL4R equivalence'},
    {'text': 'factor XIa', 'kind': 'activation_state', 'expected': 'no unqualified new F11 equivalence'},
    {'text': 'factor X', 'kind': 'different_factor', 'expected': 'no F11 equivalence'},
    {'text': 'factor XII', 'kind': 'different_factor', 'expected': 'no F11 equivalence'},
    {'text': 'factor XI deficiency', 'kind': 'disease_not_protein', 'expected': 'no whole-phrase protein equivalence'},
    {'text': 'Factor XI Measurement', 'kind': 'measurement_not_protein', 'expected': 'no whole-phrase protein equivalence'},
    {'text': 'interleukin receptor', 'kind': 'family', 'expected': 'no specific IL4R equivalence'},
    {'text': 'CLDN18.2', 'kind': 'isoform', 'expected': 'no new parent-gene collapse'},
    {'text': 'IL4R/IL13RA1', 'kind': 'separator', 'expected': 'preserve dual-target semantics'},
    {'text': 'AK/ATPase', 'kind': 'separator_negative', 'expected': 'preserve existing semantics'},
]
(OUT/'survey_controls.json').write_text(json.dumps(controls,indent=2,ensure_ascii=False)+'\n')
with SOURCE.open('rb') as f:
    source_hash=hashlib.file_digest(f,'sha256').hexdigest()
freeze = {'baseline_commit': '1e1705c', 'selection': 'First 192 Open Targets records with ChEMBL-linked UniProt identifiers ordered by SHA256 of source:source_id; plus first 96 distinct authority-backed Greek spelling proposals ordered by SHA256 of source_id:alias. No resolver outputs used for selection.',
          'authority_scope': 'Existing pinned source records, not invented phrase-to-symbol labels.',
          'source_path':str(SOURCE), 'source_sha256':source_hash,
          'heldout_concepts_excluded_before_selection':sorted(EXCLUDED),
          'population_rows':len(population),'selected_entities':len(captured_records),
          'frames_for_offline_survey':['bare phrase','anti-X','X-directed','X-targeting','X-blocking','X-binding','X-specific'],
          'files':{n:hashlib.sha256((OUT/n).read_bytes()).hexdigest() for n in ['survey_population.json','survey_authority_records.json','survey_controls.json']}}
(OUT/'survey_freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
print({'population_rows':len(population),'selected_entities':len(captured_records),'control_rows':len(controls)})
