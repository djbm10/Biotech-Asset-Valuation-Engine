import hashlib
import json
import shutil
from pathlib import Path

out = Path('/tmp/heldout_v4_primary_validation')
root = Path('/home/djmann/projects/bve-b8')
blind = json.loads((out / 'blind_top20.json').read_text())
R = 'RELEVANT'
W = 'WRONG_TARGET'
D = 'DUPLICATE'
N = 'NON_ASSET'
annotations = {
 'H16': [
  (R,'LAG3 antibody relatlimab.'), (R,'Fianlimab development code; LAG3 antibody.'),
  (R,'PD1/LAG3 bispecific tebotelimab.'), (R,'LAG3 antibody ieramilimab.'),
  (R,'INCAGN02385; LAG3 antibody.'), (R,'LBL-007; LAG3 antibody.'),
  (R,'LAG3 antibody favezelimab.'), (R,'PD1/LAG3 bispecific tobemstomig.'),
  (R,'CTLA4/LAG3 bispecific pavunalimab.'), (W,'CD19/CD3 bispecific.'),
  (W,'PD-L1 antibody.'), (W,'TNF antibody fragment.'), (W,'SARS-CoV-2 spike antibody.'),
  (R,'EMB-02; PD1/LAG3 bispecific.'), (W,'MEDI3902; Pseudomonas PcrV/Psl antibody.'),
  (W,'PD1/VEGF bispecific.'), (W,'BCMA/CD3 bispecific.'), (W,'IL17A antibody.'),
  (W,'RSV F-protein antibody.'), (W,'PD1 agonist antibody.')],
 'H18': [
  (R,'GIP/GLP1R agonist.'), (R,'Glucagon/GLP1R agonist.'), (R,'GLP1R agonist.'),
  (R,'GLP1R antagonist: frozen rubric labels target-directed therapeutic products, not agonism or indication.'),
  (R,'GLP1R agonist.'), (R,'GLP1R agonist.'), (R,'GLP1R agonist liraglutide.'),
  (R,'Distinct GLP1R agonist lixisenatide.'), (D,'Saxenda is liraglutide; duplicates position 7.'),
  (R,'GLP1R agonist semaglutide.'), (D,'Victoza is liraglutide; duplicates position 7.'),
  (D,'Ozempic is semaglutide; duplicates position 10.'), (R,'GIP/glucagon/GLP1R agonist.'),
  (D,'Wegovy is semaglutide; duplicates position 10.'), (R,'Oral small-molecule GLP1R agonist.'),
  (R,'Oral nonpeptide GLP1R agonist.'), (R,'Glucagon/GLP1R agonist.'),
  (R,'Distinct long-acting GLP1R agonist.'), (R,'PEGylated exendin-4 GLP1R agonist; distinct from exenatide formulation.'),
  (D,'Rybelsus is semaglutide; duplicates position 10.')],
 'H19': [
  (R,'TROP2 ADC sacituzumab tirumotecan.'), (R,'TROP2 ADC sacituzumab govitecan.'),
  (W,'EGFR/HER3 ADC BL-B01D1.'), (W,'EGFR ADC MRG003.'), (W,'Mesothelin ADC.'),
  (W,'Folate receptor alpha ADC MORAb-202.'), (W,'B7H3 ADC DS-7300.'), (W,'HER2 ADC SHR-A1811.'),
  (R,'TROP2 ADC LCB84.'), (R,'TROP2 ADC SHR-A1921.'),
  (R,'TROP2 CAR-transduced PD1-positive T cells T60c; target-based frozen labels do not impose an ADC-only gate.'),
  (R,'Multiplex therapeutic T cells with TROP2 among their declared targets; target-based frozen labels.'),
  (R,'Subcutaneous JSKN016 TROP2/HER3 bispecific ADC.'),
  (R,'CB-derived TROP2 CAR/IL15 TGFBR2KO NK therapeutic product. Detailed objectives and intervention identify TROP2 despite conflicting CD70 wording in brief summary.'),
  (D,'Abbreviated same MD Anderson CB-derived TROP2 CAR/IL15 TGFBR2KO NK construct as position 14, in another indication; not a distinct named product.'),
  (D,'Trodelvy is sacituzumab govitecan; duplicates position 2.'),
  (N,'Diagnostic PET tracer, not a therapeutic product; registry explicitly describes imaging, not treatment.'),
  (N,'Unspecified supportive-care category, not a named product.'),
  (N,'Unspecified supportive-care category, not a named product.'), (W,'Nectin4 ADC, not TROP2.')]
}
labels = {'protocol': 'heldout_validation_suite_v4.md sections 1-4; inherited v2 section 3 and v1 section 4',
 'engine_commit': '5feee853c8a15d8c92ef632f82a07c32e1d0e038',
 'method': 'Manual public-product-knowledge labels of exact emitted top20, before metrics. No reference matching or metric aggregation before label commit. Labels apply the frozen target-based definition; no new modality, indication, approval-status, or source-completeness scoring requirement. Later rows of the same product are DUPLICATE.',
 'excluded_interrupted_runs': ['heldout_h17_v4','heldout_h18_v4'], 'queries': {}}
for q, packet in blind.items():
 if packet['outcome'] == 'REFUSED':
  labels['queries'][q] = packet
  continue
 assert len(packet['rows']) == len(annotations[q]) == 20
 labels['queries'][q] = {'outcome': 'RESULT', 'rows': [{**row, 'label': lab, 'rationale': reason}
         for row, (lab, reason) in zip(packet['rows'], annotations[q])]}
(out / 'labels.json').write_text(json.dumps(labels, indent=2) + '\n')
audit = {'method': 'Frozen v1 row-level numerical human efficacy definition. A row with at least one qualifying cited patient-efficacy passage is supported; model simulations and human cells in vitro do not qualify.',
 'queries': {
  'H16': [{'position':1,'name':'Relatlimab','false_human_poc':False,'rationale':'One cited passage reports numerical pathological and radiographic response rates in patients receiving nivolumab plus relatlimab. The additional nonnumerical PFS passage alone would not qualify.'}],
  'H18': [{'position':1,'name':'Tirzepatide','false_human_poc':True,'rationale':'Cited passage reports respiration changes in human myotubes in vitro, not efficacy in human patients.'},
          {'position':2,'name':'survodutide','false_human_poc':False,'rationale':'Cited passage reports the numerical proportion of treated patients with a liver-fat-content reduction versus placebo.'}],
  'H19': [{'position':1,'name':'Sacituzumab Tirumotecan','false_human_poc':True,'rationale':'Cited passage describes a partitioned-survival cost-effectiveness simulation, not numerical observed human efficacy.'}],
  'H17': None, 'H20': None}}
(out / 'human_poc_labels.json').write_text(json.dumps(audit, indent=2) + '\n')
rules = out / 'frozen_rules'
rules.mkdir(exist_ok=True)
for v in [1,2,3,4]:
 p=root/'docs/se_policies'/f'heldout_validation_suite_v{v}.md'
 shutil.copyfile(p, rules/p.name)
(out/'public_label_sources.md').write_text('''# Public sources consulted before label freeze

Labels follow the frozen target-directed therapeutic-product rubric. These sources support unfamiliar identities; ordinary established product identities and trade-name equivalence use public product knowledge. No sources were acquired by rerunning the engine.

- LAG3 class and alcestobart: https://evsexplore.semantics.cancer.gov/evsexplore/concept/ncit/C134305
- Tobemstomig PD1/LAG3 trial protocol: https://cdn.clinicaltrials.gov/large-docs/89/NCT05775289/Prot_SAP_000.pdf
- XmAb22841/pavunalimab: https://www.cancer.gov/publications/dictionaries/cancer-drug/def/pavunalimab
- Fanastomig: https://drugs.ncats.io/drug/1GCR6YY9NI and https://pmc.ncbi.nlm.nih.gov/articles/PMC12072225/
- Benmelstobart PD-L1: https://pmc.ncbi.nlm.nih.gov/articles/PMC11485241/
- Gremubamab PcrV/Psl: https://openaccess.acibadem.edu.tr/server/api/core/bitstreams/8d74bb6f-2124-41d0-9ab3-65a43141a5c3/content
- DA-302168S GLP1R: https://clinicaltrials.gov/study/NCT07629544
- VCT220 GLP1R: https://pmc.ncbi.nlm.nih.gov/articles/PMC13473623/
- Avexitide GLP1R antagonist: https://pubmed.ncbi.nlm.nih.gov/42744082/
- T60c TROP2 therapeutic cells: https://www.cancer.gov/publications/dictionaries/cancer-drug/def/autologous-trop2-car-transduced-pd-1-positive-t-cells-t60c
- Izalontamab brengitecan EGFR/HER3: https://www.cancer.gov/publications/dictionaries/cancer-drug/def/izalontamab-brengitecan
- Becotatug vedotin EGFR: https://www.hkexnews.hk/listedco/listconews/sehk/2025/1030/2025103001194.pdf
- BMS-986148 mesothelin: https://pmc.ncbi.nlm.nih.gov/articles/PMC9401510/
- Farletuzumab ecteribulin FOLR1: https://www.cancer.gov/publications/dictionaries/cancer-drug/def/farletuzumab-ecteribulin
- LCB84 TROP2: https://www.cancer.gov/research/participate/clinical-trials/intervention/anti-trop-2-mmae-antibody-drug-conjugate-lcb84?pn=1
- JSKN016HC/JSKN016 TROP2/HER3: https://www.hkexnews.hk/listedco/listconews/sehk/2026/0602/2026060200035.pdf
- 9MW2821 nectin4: https://www.cancer.gov/publications/dictionaries/cancer-drug/def/bulumtatug-fuvedotin
- TROP2-targeted therapeutic cells and diagnostic PET tracer: original run registry snapshots preserved under evidence/H19 for NCT06902389, NCT07553390, NCT07631013 and NCT06715020; URLs are https://clinicaltrials.gov/study/<NCT-ID>.

NK duplicate judgment: positions 14 and 15 describe the same sponsor's cord-blood-derived TROP2 CAR/IL15 TGFBR2KO NK construct. The iC9 mention in one name and indication-specific trials do not establish distinct products in these records. Both target identity and product-level duplicate decision are frozen here before metric calculation.
''')
hashes={str(p.relative_to(out)):hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
        for p in sorted(out.rglob('*')) if p.is_file() and p.suffix != '.py' and p.name != 'label_freeze_manifest.json'}
(out/'label_freeze_manifest.json').write_text(json.dumps({'files':hashes,'metrics_calculated':False},indent=2)+'\n')
print('Label artifacts frozen; no metrics calculated.')
