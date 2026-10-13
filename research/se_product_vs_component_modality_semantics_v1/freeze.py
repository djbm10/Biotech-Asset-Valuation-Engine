import hashlib
import json
from pathlib import Path

ROOT = Path('/home/djmann/projects/bve-b8')
OUT = Path('/tmp/modality_scope_v1')
rows = []
pairs = [
 ('peptide','Novel Product is a peptide therapeutic.','Novel Product contains a peptide linker.'),
 ('antibody','Novel Product is an antibody.','Novel Product contains an antibody-derived binding domain.'),
 ('small molecule','Novel Product is a small molecule.','Novel Product carries a small molecule payload.'),
 ('cell therapy','Novel Product is a cell therapy.','Novel Product is mentioned in a cell therapy assay.'),
 ('gene therapy','Novel Product is a gene therapy.','Novel Product is mentioned in a gene therapy manufacturing study.'),
 ('ADC','Novel Product is an ADC.','Novel Product was compared with an ADC.'),
]
for term, product, other in pairs:
    for label,text in [('product',product),('other',other)]:
        rows.append({'id':f'S{len(rows)+1:02}', 'origin':'SYNTHETIC_PAIRED_STRUCTURAL_CONTROL', 'text':text,'focus_term':term,'pair_position':label})
for text,term in [
 ('Novel Product is an ADC with a tetrapeptide linker and cytotoxic payload.','peptide'),
 ('Novel Product is an ADC with a small molecule payload.','small molecule'),
 ('Novel Product is CAR-T containing an antibody-derived binding domain.','antibody'),
 ('Novel Product is a gene therapy delivered using a viral vector.','viral vector'),
 ('Novel Product is an antibody conjugated to a radionuclide.','antibody'),
 ('Novel Product contains a radionuclide component.','radionuclide'),
 ('Novel Product: peptide; antibody; mechanism under investigation.','peptide'),
 ('Novel Product was administered; an unrelated peptide assay was performed.','peptide'),
]: rows.append({'id':f'S{len(rows)+1:02}','origin':'SYNTHETIC_STRUCTURAL_CONTROL','text':text,'focus_term':term})
audit=ROOT/'research/se_h19_candidate_qualification_diagnosis_v1/results/datopotamab_exact_field.json'
a=json.loads(audit.read_text())
rows.insert(0,{'id':'H19_DATO','origin':str(audit),'text':a['raw_description'],'focus_term':'peptide','artifact':a})
paths={audit,ROOT/'research/se_h19_candidate_qualification_diagnosis_v1/results/row_audit.json.gz',Path(a['document']['snapshot_path']),Path('/home/djmann/se_runs/heldout_h19_v4/result.json')}
for folder in ['src/bve/se/evidence','src/bve/se/gates','src/bve/se/schemas']:
 paths.update((ROOT/folder).glob('*.py'))
for name in ['src/bve/se/discovery/adapters.py','src/bve/se/discovery/asset_qualification.py','src/bve/se/pipeline.py','src/bve/se/reporting/shortlist.py','src/bve/se/ontology/drug_modality.py']:
 paths.add(ROOT/name)
tests=['test_authority_modality.py','test_ncit_modality.py','test_modality_optional_and_dual_targets.py','test_gates.py','test_asset_qualification.py']
for name in tests:paths.add(ROOT/'tests/se'/name)
manifest={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
(OUT/'population.json').write_text(json.dumps({'text_controls':rows,'existing_controls':[f'tests/se/{x}' for x in tests],'h19_rows':'ALL frozen row_audit.json.gz rows; no relabeling'},indent=2)+'\n')
(OUT/'inputs.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
