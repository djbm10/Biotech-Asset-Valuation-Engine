"""Derive authority expectations before a query-orthography implementation exists."""
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from bve.se.intent import parse_query
from bve.se.ontology.records import AliasType, EntityType, normalize_lookup_key
from bve.se.ontology.targets import get_resolver, resolve_target

ROOT = Path('/home/djmann/projects/bve-b8')
OUT = Path('/tmp/se_target_query_greek_orthography_v1')
NAMES = 'alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega'.split()
LETTERS = 'αβγδεζηθικλμνξοπρστυφχψω'
WORDS = dict(zip(NAMES, LETTERS, strict=True))
PATTERN = re.compile(r'(?<![a-z])(' + '|'.join(NAMES) + r')(?![a-z])')


def relation_key(value):
    text = normalize_lookup_key(value)
    text = PATTERN.sub(lambda m: WORDS[m.group()], text)
    return ' '.join(''.join(' ' + c + ' ' if c in LETTERS else c for c in text).split())


def identity_records(entity):
    symbols = sorted({r.canonical_symbol.casefold() for r in entity.source_records if r.canonical_symbol})
    genes = sorted({x for r in entity.source_records for x in r.xrefs.get('ensembl', [])})
    coherent = (len(symbols) == len(genes) == 1
                and entity.canonical_symbol is not None
                and symbols == [entity.canonical_symbol.casefold()]
                and any(r.source == 'open_targets' and r.source_id == genes[0]
                        for r in entity.source_records))
    return {'symbols': symbols, 'ensembl_genes': genes, 'coherent': coherent}


def run():
    OUT.mkdir(exist_ok=True)
    resolver = get_resolver()
    claims = defaultdict(list)
    for entity in resolver.entities_of_type(EntityType.TARGET):
        for alias in entity.aliases:
            if alias.alias_type not in {AliasType.SYMBOL, AliasType.APPROVED_NAME, AliasType.SYNONYM}:
                continue
            key = relation_key(alias.value)
            if not any(c in LETTERS for c in key):
                continue
            claims[key].append((entity, alias))
    packet = ROOT / 'research/se_target_query_alias_coverage_v1'
    population = json.loads((packet / 'survey_population.json').read_text())
    controls = json.loads((packet / 'survey_controls.json').read_text())
    examples = [(r['id'], r['text'], 'population') for r in population]
    examples += [(f'original-control-{i}', r['text'], 'original-control')
                 for i, r in enumerate(controls)]
    examples += [(f'new-control-{i}', text, 'new-control') for i, text in enumerate([
        'IL-4Rα', 'IL-4RΑ', 'IL-4Rа', 'IL-4RA', 'IL-4Rβ', 'IL-4Rα2',
        'IL-4Rµ', 'IL-4Rϕ', 'α', 'α2', 'IL4R/α', 'IL-4Rα/unknown',
        'factor XI', 'factor XIa', 'factor XI deficiency', 'Factor XI Measurement'])]
    rows = []
    for case_id, text, kind in examples:
        raw = resolve_target(text)
        key = relation_key(text)
        matches = sorted(claims.get(key, []), key=lambda p: (
            p[0].canonical_id, p[1].alias_type.value, p[1].value.casefold(), p[1].value))
        details = []
        for entity, alias in matches:
            lookup = resolver.resolve(alias.value, EntityType.TARGET)
            details.append({'entity_id': entity.canonical_id, 'authority_alias': alias.value,
                            'alias_type': alias.alias_type.value, 'sources': sorted(alias.sources),
                            'record_keys': sorted(alias.record_keys),
                            'identity': identity_records(entity),
                            'original_status': lookup.status.value,
                            'original_entity': lookup.canonical_id})
        status, entity_id, candidates = raw.status.value, raw.canonical_id, sorted(e.canonical_id for e in raw.candidates)
        reason = 'existing_exact_lookup'
        literal = any(c in LETTERS or c in LETTERS.upper() for c in text)
        if status == 'UNRESOLVED' and literal and '/' not in text and '×' not in text and re.search('[a-z]', key):
            ids = sorted({d['entity_id'] for d in details})
            if len(ids) > 1:
                status, candidates, reason = 'AMBIGUOUS', ids, 'multiple_authority_claimants'
            elif len(ids) == 1:
                if not details[0]['identity']['coherent']:
                    reason = 'uncertified_gene_identity'
                elif not any(d['original_status'] == 'RESOLVED' and d['original_entity'] == ids[0] for d in details):
                    reason = 'original_alias_not_certified'
                else:
                    status, entity_id, reason = 'RESOLVED', ids[0], 'authority_greek_orthography'
            else:
                reason = 'no_authority_claim'
        rows.append({'id': case_id, 'kind': kind, 'text': text, 'key': key,
                     'global_baseline': {'status': raw.status.value, 'entity_id': raw.canonical_id,
                                         'candidates': sorted(e.canonical_id for e in raw.candidates)},
                     'expected': {'status': status, 'entity_id': entity_id, 'candidates': candidates},
                     'reason': reason, 'authority_claims': details})
    queries = ['Find clinical-stage anti-IL-4Rα antibodies for atopic dermatitis.']
    baseline = [{'query': q, 'intent': parse_query(q).model_dump(mode='json')} for q in queries]
    (OUT / 'authority_oracle.json').write_text(json.dumps({'rows': rows, 'diagnostic_query_baseline': baseline}, indent=2, ensure_ascii=False) + '\n')
    files = [packet / 'survey_population.json', packet / 'survey_baseline.json',
             ROOT / 'data/se/ontology/current/records.jsonl', ROOT / 'src/bve/se/ontology/resolver.py',
             ROOT / 'src/bve/se/ontology/records.py']
    manifest = {'baseline': '0fcfa5a', 'inputs': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}, 'oracle_sha256': hashlib.sha256((OUT / 'authority_oracle.json').read_bytes()).hexdigest(), 'holdout_probes': 0, 'live_asset_runs': 0}
    (OUT / 'authority_oracle_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    greek_ids = {r['id'] for r in population if r['kind'] == 'greek_orthography_proposal'}
    subset = [r for r in rows if r['id'] in greek_ids]
    print(json.dumps({'greek_count': len(subset), 'expected_counts': {s: sum(r['expected']['status'] == s for r in subset) for s in ['RESOLVED', 'AMBIGUOUS', 'UNRESOLVED']}, 'rows': len(rows)}, indent=2))


if __name__ == '__main__':
    run()
