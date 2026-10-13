"""Freeze case selection and independent expected labels before certificate code."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/djmann/projects/bve-b8')
OLD = ROOT / 'research/se_target_component_identity_certificate_v1/results'
EVIDENCE = Path('/home/djmann/se_runs/target_component_identity_authority_evidence_v1/seed0')
OUT = Path(__file__).parent


def load(path):
    return json.loads(gzip.open(path).read() if str(path).endswith('.gz') else path.read_bytes())


components = load(OLD / 'component_audit.json.gz')
assertions = load(OLD / 'assertions.json.gz')
records = [json.loads(line) for line in gzip.open(EVIDENCE / 'records.jsonl.gz', 'rt')]
hgnc = {r['raw'].get('ensembl_gene_id'): r['raw'] for r in records
        if r['source']['source'] == 'hgnc'}
cases = []
for c in components:
    cases.append({'id': 'group:' + c['component_id'], 'scope': 'RESOLVER_GROUP',
                  'component_id': c['component_id'], 'canonical_id': c['canonical_id'],
                  'expected': 'AMBIGUOUS',
                  'oracle_reason': 'No authority types this ingestion union and every alias as one entity.'})
for p in load(OLD / 'blocked_86_audit.json'):
    cases.append({'id': p['id'], 'scope': 'PROPOSAL', 'canonical_id': p['canonical_id'],
                  'assertion_ids': sorted(e['assertion_id'] for e in p['evidence']),
                  'expected': p['diagnostic_status'],
                  'oracle_reason': 'Frozen v1 primary-ID conflict or unresolved merged-component identity.'})
for c in components:
    if len(c['source_genes']) != 1:
        continue
    g = c['source_genes'][0]
    h = hgnc.get(g['entity_id'])
    clean = bool(h and h.get('status') == 'Approved'
                 and h.get('symbol') == g['approvedSymbol']
                 and c['canonical_id'] == 'TARGET:' + h['symbol']
                 and len(c['canonical_id_components']) == 1)
    for m in c['members']:
        for a in m.get('primary_assertions', []):
            if a['record_id'] != g['entity_id']:
                continue
            cases.append({'id': 'primary:' + c['component_id'] + ':' + a['assertion_id'],
                          'scope': 'PRIMARY_ASSERTION', 'component_id': c['component_id'],
                          'canonical_id': c['canonical_id'], 'assertion_ids': [a['assertion_id']],
                          'expected': 'CERTIFIED_SINGLE_ENTITY' if clean else 'AMBIGUOUS',
                          'oracle_reason': 'Exact gene ID and approved symbol converge; collisions/missing gene evidence abstain.'})
selection = load(ROOT / 'research/se_target_component_identity_authority_evidence_v1/chembl_selection.json')
for kind, controls in selection['controls'].items():
    for c in controls:
        expected = ('AMBIGUOUS' if kind == 'SINGLE PROTEIN' else
                    'CERTIFIED_MULTI_ENTITY' if kind == 'SELECTIVITY GROUP' else
                    'CERTIFIED_RELATIONAL_ENTITY')
        cases.append({'id': 'structure:' + c['chembl_id'], 'scope': 'STRUCTURED_TARGET',
                      'chembl_id': c['chembl_id'], 'canonical_id': 'CHEMBL:' + c['chembl_id'],
                      'expected': expected,
                      'oracle_reason': 'Authority-typed target structure; no automatic protein-to-gene equivalence.'})
# Positive native-protein controls: frozen structural single-protein records have
# typed membership and are evaluated against their actual reviewed accession.
tables = {}
for r in records:
    if r['source']['source'] == 'chembl':
        tables.setdefault(r['source']['locator']['table'], []).append(r['raw'])
uni = {r['raw'].get('primaryAccession'): r['raw'] for r in records if r['source']['source']=='uniprot'}
for c in selection['controls']['SINGLE PROTEIN']:
    mids = [m['component_id'] for m in tables['target_components'] if m['tid']==c['tid']]
    comp = next(x for x in tables['component_sequences'] if x['component_id']==mids[0])
    accession = comp['accession']; u = uni.get(accession, {})
    gids = {x['id'] for x in u.get('uniProtKBCrossReferences', []) if x['database']=='HGNC'}
    hs = [h for h in hgnc.values() if accession in h.get('uniprot_ids', [])]
    clean = (len(mids)==1 and len(hs)==1 and gids=={hs[0]['hgnc_id']}
             and u.get('entryType')=='UniProtKB reviewed (Swiss-Prot)'
             and u.get('organism', {}).get('taxonId')==9606)
    cases.append({'id': 'protein:' + c['chembl_id'], 'scope': 'PROTEIN_COMPONENT',
                  'chembl_id': c['chembl_id'], 'canonical_id': 'UNIPROT:' + accession,
                  'expected': 'CERTIFIED_SINGLE_ENTITY' if clean else 'AMBIGUOUS',
                  'oracle_reason': 'Typed single protein, exact reviewed accession and reciprocal unique HGNC encoding relation.'})
files = [OLD / n for n in ['component_audit.json.gz','assertions.json.gz','blocked_86_audit.json']]
files += [EVIDENCE / n for n in ['records.jsonl.gz','assertions.jsonl.gz','hashes.json']]
files += [ROOT / 'research/se_target_component_identity_authority_evidence_v1/chembl_selection.json']
manifest = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
for name, data in [('population.json', cases), ('inputs.json', manifest)]:
    (OUT/name).write_text(json.dumps(data, sort_keys=True, indent=2)+'\n')
from collections import Counter
print(len(cases), Counter(c['expected'] for c in cases))
