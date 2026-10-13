import hashlib
import json
from pathlib import Path
R=Path('/home/djmann/projects/bve-b8');O=Path('/tmp/modality_v2_design')
old=R/'research/se_modality_assertion_scope_representation_v1'
inputs=json.loads((old/'inputs.json').read_text())
for p in [R/'docs/se_policies/product_vs_component_modality_semantics_v2.md',R/'src/bve/se/evidence/modality_scope.py',R/'src/bve/se/evidence/generic.py',R/'src/bve/se/evidence/entailment.py',*old.glob('results/*.json'),*R.glob('tests/se/test*evidence*.py'),R/'tests/se/test_modality_scope.py']:
 inputs[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
controls=[
 ('P_PEPTIDE','Novel Product is a peptide therapeutic.','peptide','PRODUCT_LEVEL',True),
 ('P_ADC','Novel Product is an antibody-drug conjugate.','antibody-drug conjugate','PRODUCT_LEVEL',True),
 ('P_CELL','Novel Product is a cell therapy.','cell therapy','PRODUCT_LEVEL',True),
 ('P_GENE','Novel Product is a gene therapy.','gene therapy','PRODUCT_LEVEL',True),
 ('P_ANTIBODY','Novel Product is an antibody.','antibody','PRODUCT_LEVEL',True),
 ('P_SMALL','Novel Product is a small molecule.','small molecule','PRODUCT_LEVEL',True),
 ('MODIFIER_PEPTIDE','Novel Product is a peptide-linked antibody-drug conjugate.','peptide','NON_PRODUCT',False),
 ('MODIFIER_ANTIBODY','Novel Product is an antibody-derived cell therapy.','antibody','NON_PRODUCT',False),
 ('MODIFIER_PAYLOAD','Novel Product is a small-molecule-loaded nanoparticle.','small-molecule','NON_PRODUCT',False),
 ('MISSING_SCOPE','Other Product is a peptide therapeutic.','peptide','AMBIGUOUS',False),
 ('NO_COREFERENCE','Novel Product is an ADC. It is a peptide therapeutic.','peptide','AMBIGUOUS',False),
 ('COMPOSITE','Novel Product is an antibody conjugated to a radionuclide.','antibody','RELATIONAL_COMPOSITE',False),
 ('CONFLICT_A','Novel Product is a peptide therapeutic.','peptide','PRODUCT_LEVEL',False),
 ('CONFLICT_B','Novel Product is an antibody.','antibody','PRODUCT_LEVEL',False),
]
rows=[dict(id=i,text=t,focus=f,expected_scope=s,permits_alone=p,source_relation='equal-authority conflicting product assertions' if i.startswith('CONFLICT') else 'independent fixture') for i,t,f,s,p in controls]
(O/'additional_controls.json').write_text(json.dumps(rows,indent=2)+'\n')
(O/'inputs.json').write_text(json.dumps(inputs,sort_keys=True,indent=2)+'\n')
