# Scoped witness inventory

Full raw spans, relations, source fields and legacy gates are in witnesses.json. Multiple rows per witness are intentional.

| Witness | Mention | Modality | Scope | Relation | Rule |
|---|---|---|---|---|---|
| H19_DATO | ADC | ANTIBODY_DRUG_CONJUGATE | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| H19_DATO | IgG | MONOCLONAL_ANTIBODY | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| H19_DATO | mAb | MONOCLONAL_ANTIBODY | COMPONENT_LEVEL | PRODUCT_HAS_COMPONENT, COMPONENT_HAS_MODALITY | explicit_component_relation |
| H19_DATO | trap | FUSION_PROTEIN | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| H19_DATO | peptide | PEPTIDE | COMPONENT_LEVEL | PRODUCT_HAS_COMPONENT, COMPONENT_HAS_MODALITY | explicit_component_relation |
| S01 | peptide | PEPTIDE | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| S02 | peptide | PEPTIDE | COMPONENT_LEVEL | PRODUCT_HAS_COMPONENT, COMPONENT_HAS_MODALITY | explicit_component_relation |
| S03 | antibody | MONOCLONAL_ANTIBODY | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| S04 | antibody | MONOCLONAL_ANTIBODY | COMPONENT_LEVEL | PRODUCT_HAS_COMPONENT, COMPONENT_HAS_MODALITY | explicit_component_relation |
| S05 | small molecule | SMALL_MOLECULE | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| S06 | small molecule | SMALL_MOLECULE | COMPONENT_LEVEL | PRODUCT_HAS_COMPONENT, COMPONENT_HAS_MODALITY | explicit_component_relation |
| S07 | cell therapy | CELL_THERAPY | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| S08 | cell therapy | CELL_THERAPY | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| S09 | gene therapy | GENE_THERAPY | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| S10 | gene therapy | GENE_THERAPY | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| S11 | ADC | ANTIBODY_DRUG_CONJUGATE | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| S12 | ADC | ANTIBODY_DRUG_CONJUGATE | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| S13 | ADC | ANTIBODY_DRUG_CONJUGATE | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| S13 | trap | FUSION_PROTEIN | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| S13 | peptide | PEPTIDE | COMPONENT_LEVEL | PRODUCT_HAS_COMPONENT, COMPONENT_HAS_MODALITY | explicit_component_relation |
| S13 | cytotoxic | None | COMPONENT_LEVEL | PRODUCT_HAS_COMPONENT, COMPONENT_HAS_MODALITY | explicit_component_relation |
| S14 | ADC | ANTIBODY_DRUG_CONJUGATE | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| S14 | small molecule | SMALL_MOLECULE | COMPONENT_LEVEL | PRODUCT_HAS_COMPONENT, COMPONENT_HAS_MODALITY | explicit_component_relation |
| S15 | CAR-T | CAR_T | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| S15 | antibody | MONOCLONAL_ANTIBODY | COMPONENT_LEVEL | PRODUCT_HAS_COMPONENT, COMPONENT_HAS_MODALITY | explicit_component_relation |
| S16 | gene therapy | GENE_THERAPY | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| S16 | viral vector | None | COMPONENT_LEVEL | PRODUCT_HAS_COMPONENT, COMPONENT_HAS_MODALITY | explicit_component_relation |
| S17 | antibody | MONOCLONAL_ANTIBODY | RELATIONAL_COMPOSITE | PRODUCT_IS_COMPOSITE | explicit_conjugation |
| S17 | antibody conjugate | ANTIBODY_DRUG_CONJUGATE | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| S17 | radionuclide | None | RELATIONAL_COMPOSITE | PRODUCT_IS_COMPOSITE | explicit_conjugation |
| S18 | radionuclide | None | COMPONENT_LEVEL | PRODUCT_HAS_COMPONENT, COMPONENT_HAS_MODALITY | explicit_component_relation |
| S19 | peptide | PEPTIDE | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| S19 | antibody | MONOCLONAL_ANTIBODY | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| S20 | peptide | PEPTIDE | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| X01 | peptide | PEPTIDE | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| X02 | peptide | PEPTIDE | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| X03 | peptide | PEPTIDE | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| X04 | peptide | PEPTIDE | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| X05 | ADC | ANTIBODY_DRUG_CONJUGATE | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| X05 | peptide | PEPTIDE | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| X06 | ADC | ANTIBODY_DRUG_CONJUGATE | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| X06 | cytotoxic | None | COMPONENT_LEVEL | PRODUCT_HAS_COMPONENT, COMPONENT_HAS_MODALITY | explicit_component_relation |
| X07 | peptide | PEPTIDE | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| X07 | peptide | PEPTIDE | COMPONENT_LEVEL | PRODUCT_HAS_COMPONENT, COMPONENT_HAS_MODALITY | explicit_component_relation |
| X08 | small-molecule | SMALL_MOLECULE | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| X09 | antibody | MONOCLONAL_ANTIBODY | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| X09 | viral vector | None | COMPONENT_LEVEL | PRODUCT_HAS_COMPONENT, COMPONENT_HAS_MODALITY | explicit_component_relation |
| X10 | antibody | MONOCLONAL_ANTIBODY | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| X11 | ADC | ANTIBODY_DRUG_CONJUGATE | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| X11 | peptide | PEPTIDE | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
| X12 | ADC | ANTIBODY_DRUG_CONJUGATE | PRODUCT_LEVEL | PRODUCT_IS_MODALITY | explicit_product_predicate |
| X12 | peptide | PEPTIDE | AMBIGUOUS | UNKNOWN_RELATION | unproven_subject_or_relation |
