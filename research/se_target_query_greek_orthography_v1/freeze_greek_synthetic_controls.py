"""Freeze synthetic scientific boundaries without invoking a candidate resolver."""
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/djmann/projects/bve-b8')
OUT = Path('/tmp/se_target_query_greek_orthography_v1')
NAMES = 'alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega'.split()
LETTERS = 'αβγδεζηθικλμνξοπρστυφχψω'
records = []
cases = []


def record(index, symbol, aliases, *, accession=None, source='open_targets', gene=None):
    gene = gene or f'ENSG{index:011d}'
    return {'source': source, 'source_id': gene if source == 'open_targets' else f'CHEMBL{index}',
            'entity_type': 'TARGET', 'canonical_symbol': symbol, 'label': symbol,
            'aliases': [{'value': a, 'alias_type': 'SYNONYM'} for a in aliases],
            'xrefs': {'uniprot': [accession or f'Q{index:05d}'], 'ensembl': [gene]}}


for index, (name, letter) in enumerate(zip(NAMES, LETTERS, strict=True), 1):
    symbol = f'GQ{index:02d}'
    records.append(record(index, symbol, ['Anchorase ' + name]))
    for form in ['Anchorase' + letter, 'Anchorase-' + letter.upper(), 'Anchorase ' + letter]:
        cases.append({'query': form, 'status': 'RESOLVED', 'entity': 'TARGET:' + symbol,
                      'candidates': [], 'boundary': 'authority_spelling_equivalence'})
records[0]['aliases'] += [{'value': a, 'alias_type': 'SYNONYM'} for a in ['alpha', 'Sharing alpha', 'Contested alpha', 'Alphabetasealpha']]
records[1]['aliases'].append({'value': 'Sharing alpha', 'alias_type': 'SYNONYM'})
records.extend([record(31, 'GQ31', ['Composite beta', 'Contested alpha'], accession='Q90001'),
                record(32, 'GQ32', ['Composite beta', 'Contested alpha'], accession='Q90001')])
records.extend([record(33, 'GQ33', ['Disagreement gamma'], accession='Q90002'),
                record(34, 'GQ34', ['Disagreement gamma'], accession='Q90002', source='chembl', gene='ENSG00000000033')])
missing = record(35, 'GQ35', ['Missing delta'], source='chembl')
missing['xrefs'].pop('ensembl')
records.append(missing)
records.append(record(36, 'GQ36', ['AΑ B', 'AΑ', 'B']))
for text, boundary in [('α', 'no_biological_anchor'), ('α2', 'no_biological_anchor'),
                       ('Anchoraseα2', 'number_preserved'), ('Anchoraseа', 'cyrillic_confusable'),
                       ('AnchoraseA', 'latin_confusable'), ('Anchoraseµ', 'micro_sign'),
                       ('Anchoraseϕ', 'variant_glyph'), ('Alphabetaseα', 'embedded_english_substring'),
                       ('Anchorase/α', 'separator_boundary'), ('Anchoraseα×unknown', 'separator_boundary'),
                       ('Compositeβ', 'multiple_genes'), ('Disagreementγ', 'multiple_symbols'),
                       ('Missingδ', 'missing_gene_identity'), ('Aα', 'existing_fragment_veto')]:
    cases.append({'query': text, 'status': 'UNRESOLVED', 'entity': None,
                  'candidates': [], 'boundary': boundary})
# Existing source election deterministically uses the last Open Targets record,
# but this fixture's merged component remains ineligible for new alias admission.
for text, ids, boundary in [('Sharingα', ['TARGET:GQ01', 'TARGET:GQ02'], 'multiple_eligible_claimants'),
                            ('Contestedα', ['TARGET:GQ01', 'TARGET:GQ32'], 'ineligible_competitor_is_not_removed')]:
    cases.append({'query': text, 'status': 'AMBIGUOUS', 'entity': None,
                  'candidates': ids, 'boundary': boundary})
queries = []
for frame in ['{}', 'anti-{}', '{}-directed', '{}-targeting', '{}-blocking', '{}-binding', '{}-specific']:
    queries.append({'query': 'Find clinical-stage ' + frame.format('Anchoraseα') + ' antibodies for lung cancer.',
                    'baseline_query': 'Find clinical-stage ' + frame.format('GQ01') + ' antibodies for lung cancer.',
                    'expected_targets': ['GQ01']})
queries += [
    {'query': 'Find clinical-stage Anchorase alpha or Anchoraseα antibodies for lung cancer.',
     'baseline_query': 'Find clinical-stage GQ01 or GQ01 antibodies for lung cancer.', 'expected_targets': ['GQ01']},
    {'query': 'Find clinical-stage Anchoraseα/Anchoraseβ antibodies for lung cancer.',
     'baseline_query': 'Find clinical-stage GQ01/GQ02 antibodies for lung cancer.', 'expected_targets': ['GQ01', 'GQ02']},
    {'query': 'Find clinical-stage Anchoraseα×Anchoraseβ antibodies for lung cancer.',
     'baseline_query': 'Find clinical-stage GQ01×GQ02 antibodies for lung cancer.', 'expected_targets': ['GQ01', 'GQ02']},
    {'query': 'Find clinical-stage Anchoraseα/NotATarget antibodies for lung cancer.',
     'baseline_query': 'Find clinical-stage GQ01/NotATarget antibodies for lung cancer.', 'expected_targets': []},
]
snapshot = {'sources': [{'source': source, 'release': 'greek-fixture-v1', 'retrieved_at': '2026-10-12',
                         'locator': 'fixture:greek-orthography:' + source} for source in ['open_targets', 'chembl']],
            'records': records, 'edges': []}
OUT.mkdir(exist_ok=True)
(OUT / 'synthetic_authority.json').write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + '\n')
(OUT / 'synthetic_controls.json').write_text(json.dumps({'raw_cases': cases, 'queries': queries,
    'additional_state_controls': ['missing snapshot returns existing None', 'existing raw results unchanged',
        'new provenance names original asserted alias and source records', 'seeds 0, 1, 42 identical']}, indent=2, ensure_ascii=False) + '\n')
manifest = {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest()
            for name in ['synthetic_authority.json', 'synthetic_controls.json']}
(OUT / 'synthetic_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'raw_cases': len(cases), 'query_cases': len(queries), 'records': len(records)}))
