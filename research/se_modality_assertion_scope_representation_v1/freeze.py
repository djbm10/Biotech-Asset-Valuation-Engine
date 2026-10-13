import hashlib
import json
from pathlib import Path

ROOT=Path('/home/djmann/projects/bve-b8')
OUT=Path('/tmp/modality_repr_v1')
OLD=ROOT/'research/se_product_vs_component_modality_semantics_v1'
rows=json.loads((OLD/'results/scope_table.json').read_text())
controls=[{'id':r['id'],'text':r['text'],'focus_term':r['focus_term'],'expected_scope':r['scope']} for r in rows]
extra=[
 ('Novel Product is not a peptide therapeutic.','peptide','AMBIGUOUS'),
 ('Novel Product may be a peptide therapeutic.','peptide','AMBIGUOUS'),
 ('Other Product is a peptide therapeutic.','peptide','AMBIGUOUS'),
 ('Novel Product and Other Product are peptide therapeutics.','peptide','AMBIGUOUS'),
 ('Novel Product is an ADC. Other Product has a peptide linker.','peptide','AMBIGUOUS'),
 ('Novel Product is an ADC with a cytotoxic payload.','cytotoxic','COMPONENT_LEVEL'),
 ('Novel Product is a peptide therapeutic with a peptide linker.','peptide','PRODUCT_LEVEL'),
 ('Novel Product is a small-molecule product.','small-molecule','PRODUCT_LEVEL'),
 ('Novel Product is an antibody with a viral vector component.','viral vector','COMPONENT_LEVEL'),
 ('Novel Product is being compared with an antibody.','antibody','AMBIGUOUS'),
 ('Novel Product is an ADC without a peptide linker.','peptide','AMBIGUOUS'),
 ('Novel Product is an ADC; peptide assay results are pending.','peptide','AMBIGUOUS'),
]
controls.extend({'id':f'X{i:02}','text':t,'focus_term':f,'expected_scope':s} for i,(t,f,s) in enumerate(extra,1))
(OUT/'controls.json').write_text(json.dumps(controls,indent=2)+'\n')
paths=[OLD/'population.json',OLD/'results/scope_table.json',OLD/'results/all_mention_scopes.json',OLD/'results/h19_rows.json.gz',OLD/'results/datopotamab_lifecycle.json',Path('/home/djmann/se_runs/heldout_h19_v4/result.json')]
paths.extend(ROOT/p for p in ['src/bve/se/discovery/adapters.py','src/bve/se/evidence/clinicaltrials.py','src/bve/se/schemas/contracts.py','src/bve/se/gates/engine.py','src/bve/se/gates/evaluator.py','src/bve/se/pipeline.py','tests/se/test_authority_modality.py','tests/se/test_ncit_modality.py','tests/se/test_modality_optional_and_dual_targets.py','tests/se/test_gates.py','tests/se/test_asset_qualification.py'])
run=json.loads(paths[5].read_text())
paths.extend(Path(d['snapshot_path']) for d in run['source_documents'] if d.get('snapshot_path'))
(OUT/'inputs.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))},sort_keys=True,indent=2)+'\n')
