# Frozen focus-scope table

Scope annotations are diagnosis data, not a production parser. Every lexical match is separately annotated in all_mention_scopes.json. Folded hit coordinates are explicitly distinguished from exact raw focus spans.

| Case | Text | Raw focus span | Scope | Current scalar | Reason |
|---|---|---|---|---|---|
| H19_DATO | Dato-DXd is an ADC comprised of a recombinant humanised anti-TROP2 IgG1 mAb, MAAP-9001a, which is covalently conjugated via a cleavable drug-linker, MAAA1162a (the complex of MAAA-1181a and a maleimide tetrapeptide linker), using thioether bonds to the topoisomerase I inhibitor DXd. | 207:214 `peptide` | COMPONENT_LEVEL | PEPTIDE | tetrapeptide modifies linker; ADC predicates the whole product |
| S01 | Novel Product is a peptide therapeutic. | 19:26 `peptide` | PRODUCT_LEVEL | PEPTIDE | predicate nominal describes named product |
| S02 | Novel Product contains a peptide linker. | 25:32 `peptide` | COMPONENT_LEVEL | PEPTIDE | peptide modifies linker possessed by product |
| S03 | Novel Product is an antibody. | 20:28 `antibody` | PRODUCT_LEVEL | MONOCLONAL_ANTIBODY | predicate nominal describes named product |
| S04 | Novel Product contains an antibody-derived binding domain. | 26:34 `antibody` | COMPONENT_LEVEL | MONOCLONAL_ANTIBODY | antibody-derived modifies binding domain |
| S05 | Novel Product is a small molecule. | 19:33 `small molecule` | PRODUCT_LEVEL | SMALL_MOLECULE | predicate nominal describes named product |
| S06 | Novel Product carries a small molecule payload. | 24:38 `small molecule` | COMPONENT_LEVEL | SMALL_MOLECULE | small molecule modifies payload |
| S07 | Novel Product is a cell therapy. | 19:31 `cell therapy` | PRODUCT_LEVEL | CELL_THERAPY | predicate nominal describes named product |
| S08 | Novel Product is mentioned in a cell therapy assay. | 32:44 `cell therapy` | AMBIGUOUS | CELL_THERAPY | assay context does not assert product modality |
| S09 | Novel Product is a gene therapy. | 19:31 `gene therapy` | PRODUCT_LEVEL | GENE_THERAPY | predicate nominal describes named product |
| S10 | Novel Product is mentioned in a gene therapy manufacturing study. | 32:44 `gene therapy` | AMBIGUOUS | GENE_THERAPY | manufacturing-study context does not assert product modality |
| S11 | Novel Product is an ADC. | 20:23 `ADC` | PRODUCT_LEVEL | ANTIBODY_DRUG_CONJUGATE | explicit whole-product composite class ADC |
| S12 | Novel Product was compared with an ADC. | 35:38 `ADC` | AMBIGUOUS | ANTIBODY_DRUG_CONJUGATE | comparison object is not the named product |
| S13 | Novel Product is an ADC with a tetrapeptide linker and cytotoxic payload. | 36:43 `peptide` | COMPONENT_LEVEL | PEPTIDE | tetrapeptide modifies linker; whole product explicitly ADC |
| S14 | Novel Product is an ADC with a small molecule payload. | 31:45 `small molecule` | COMPONENT_LEVEL | SMALL_MOLECULE | small molecule modifies payload; whole product explicitly ADC |
| S15 | Novel Product is CAR-T containing an antibody-derived binding domain. | 37:45 `antibody` | COMPONENT_LEVEL | MONOCLONAL_ANTIBODY | binding domain is constituent of named CAR-T product |
| S16 | Novel Product is a gene therapy delivered using a viral vector. | 50:62 `viral vector` | COMPONENT_LEVEL | GENE_THERAPY | delivery vehicle belongs to gene-therapy relationship, not new whole-product virus class |
| S17 | Novel Product is an antibody conjugated to a radionuclide. | 20:28 `antibody` | RELATIONAL_COMPOSITE | ANTIBODY_DRUG_CONJUGATE | conjugation relates antibody and radionuclide; no constituent inheritance |
| S18 | Novel Product contains a radionuclide component. | 25:37 `radionuclide` | COMPONENT_LEVEL | None | radionuclide explicitly modifies component; whole modality not stated |
| S19 | Novel Product: peptide; antibody; mechanism under investigation. | 15:22 `peptide` | AMBIGUOUS | MONOCLONAL_ANTIBODY | unbound term list |
| S20 | Novel Product was administered; an unrelated peptide assay was performed. | 45:52 `peptide` | AMBIGUOUS | PEPTIDE | unrelated assay is not product modality |
