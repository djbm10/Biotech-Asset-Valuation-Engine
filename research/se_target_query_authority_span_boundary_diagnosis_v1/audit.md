# Frozen 96-name authority-span audit

Restored parser only. `Outside` means different from the certified whole-name identity, not newly introduced by a candidate. Six rows have no certified reference; no alternative identity is inferred for them. Counts below use the bare frame; JSON includes all seven frames and complete resolver calls/spans.

| Original authority name | Reference | Tokens | Whole offered | English targets | Greek targets | First observed boundary |
|---|---|---:|---|---|---|---|
| DNA polymerase beta subunit | TARGET:POLB | 4 | False | none | none | target lookup capped at two tokens |
| Beta-site amyloid precursor protein cleaving enzyme 1 | TARGET:BACE1 | 7 | False | none | none | target lookup capped at two tokens |
| H-IDH alpha | TARGET:IDH3A | 2 | True | TARGET:IDH3A | none | full name offered; inspect authority status and role |
| Alcohol dehydrogenase subunit gamma | TARGET:ADH1C | 4 | False | TARGET:AKR1A1 | TARGET:AKR1A1 | target lookup capped at two tokens |
| CaMK-II subunit gamma | TARGET:CAMK2G | 3 | False | TARGET:CAMK2G | TARGET:CAMK2G | target lookup capped at two tokens |
| thyroid hormone receptor alpha 1 | TARGET:THRA | 5 | False | TARGET:NR4A1, TARGET:PSMA6 | TARGET:NR4A1 | target lookup capped at two tokens |
| nuclear factor of kappa light chain gene enhancer in B-cells | TARGET:NFKBIA | 10 | False | TARGET:TNFSF14 | TARGET:TNFSF14 | target lookup capped at two tokens |
| Alpha-1-fetoprotein | TARGET:AFP | 1 | True | TARGET:AFP | none | full name offered; inspect authority status and role |
| calcium channel, cardic dihydropyridine-sensitive, alpha-1 subunit | TARGET:CACNA1C | 6 | False | TARGET:PSMA6 | none | target lookup capped at two tokens |
| intracellular phospholipase A1 gamma | TARGET:DDHD2 | 4 | False | none | none | target lookup capped at two tokens |
| Catenin alpha-1 | TARGET:CTNNA1 | 2 | True | TARGET:CTNNA1 | none | full name offered; inspect authority status and role |
| immunoglobulin E receptor, high-affinity, of mast cells, alpha polypeptide | TARGET:FCER1A | 9 | False | none | none | target lookup capped at two tokens |
| MHC class I antigen HLA-B alpha chain | TARGET:HLA-B | 7 | False | TARGET:HLA-C, TARGET:HLA-B, TARGET:FCGRT | TARGET:HLA-C, TARGET:HLA-B | target lookup capped at two tokens |
| casein kinase 2, beta polypeptide | TARGET:CSNK2B | 5 | False | TARGET:PDIK1L | TARGET:PDIK1L | target lookup capped at two tokens |
| ER alpha-1,2-mannosidase | TARGET:MAN1B1 | 2 | True | TARGET:MAN1B1 | none | full name offered; inspect authority status and role |
| protein kinase, cGMP-dependent, regulatory, type I, beta | TARGET:PRKG1 | 7 | False | TARGET:WEE1, TARGET:SGCG | TARGET:WEE1, TARGET:SGCG | target lookup capped at two tokens |
| GDP-L-Fuc:N-acetyl-beta-D-glucosaminide alpha1,6-fucosyltransferase | TARGET:FUT8 | 2 | True | TARGET:FUT8 | none | full name offered; inspect authority status and role |
| DAG kinase epsilon | TARGET:DGKE | 3 | False | TARGET:DAG1 | TARGET:DAG1 | target lookup capped at two tokens |
| pro-alpha-1 collagen type 1 | TARGET:COL1A1 | 4 | False | TARGET:SGCG | TARGET:SGCG | target lookup capped at two tokens |
| 5'-AMP-activated protein kinase, catalytic alpha-2 chain | TARGET:PRKAA2 | 6 | False | TARGET:WEE1, TARGET:PSMA2 | TARGET:WEE1 | target lookup capped at two tokens |
| sodium channel protein, brain type 2 alpha subunit | TARGET:SCN2A | 8 | False | TARGET:SGCG | TARGET:SGCG | target lookup capped at two tokens |
| big potassium channel beta subunit 4 | TARGET:KCNMB4 | 6 | False | none | none | target lookup capped at two tokens |
| Sialoglycoprotein alpha | TARGET:GYPA | 2 | True | TARGET:GYPA | none | full name offered; inspect authority status and role |
| Hemoglobin beta chain | TARGET:HBB | 3 | False | none | none | target lookup capped at two tokens |
| Soluble APP-beta | TARGET:APP | 2 | True | TARGET:APP | none | full name offered; inspect authority status and role |
| Beta-type CGRP | TARGET:CALCB | 2 | True | TARGET:CALCB | none | full name offered; inspect authority status and role |
| Detyrosinated tubulin alpha-1B chain | UNCERTIFIED | 4 | False | TARGET:TUBA1B | none | target lookup capped at two tokens; identity/reference uncertified |
| C3 and PZP-like alpha-2-macroglobulin domain-containing protein 4 | TARGET:C5 | 7 | False | TARGET:C3, TARGET:A2MP1, TARGET:A2M | TARGET:C3, TARGET:A2MP1 | target lookup capped at two tokens |
| Alpha-2 type I collagen | TARGET:COL1A2 | 4 | False | TARGET:PSMA2, TARGET:SGCG | TARGET:SGCG | target lookup capped at two tokens |
| Isocitrate dehydrogenase [NAD] subunit alpha, mitochondrial | TARGET:IDH3A | 6 | False | none | none | target lookup capped at two tokens |
| Sodium channel protein brain I subunit alpha | TARGET:SCN1A | 7 | False | none | none | target lookup capped at two tokens |
| (R)-beta-hydroxybutyrate dehydrogenase | TARGET:BDH2 | 2 | False | none | none | token-edge punctuation cleaning alters scientific name |
| thymosin, beta 4, X chromosome | TARGET:TMSB4X | 5 | False | none | none | target lookup capped at two tokens |
| Phosphorylase kinase subunit beta | TARGET:PHKB | 4 | False | none | none | target lookup capped at two tokens |
| GDNF family receptor alpha-3 | TARGET:GFRA3 | 4 | False | TARGET:GDNF, TARGET:PSMA4 | TARGET:GDNF | target lookup capped at two tokens |
| COPI coat complex subunit epsilon | TARGET:COPE | 5 | False | none | none | target lookup capped at two tokens |
| protein kinase, cAMP-dependent, regulatory, type I, beta | TARGET:PRKAR1B | 7 | False | TARGET:WEE1, TARGET:SGCG | TARGET:WEE1, TARGET:SGCG | target lookup capped at two tokens |
| Brain-derived tau kinase | TARGET:TTBK1 | 3 | False | TARGET:MAPT | none | target lookup capped at two tokens |
| transforming growth factor beta receptor I | TARGET:TGFBR1 | 6 | False | none | none | target lookup capped at two tokens |
| DAGL-alpha | TARGET:DAGLA | 1 | True | TARGET:DAGLA | none | full name offered; inspect authority status and role |
| TR-BETA | TARGET:TXNRD2 | 1 | True | TARGET:TXNRD2 | none | full name offered; inspect authority status and role |
| Serine/threonine-protein kinase MRCK beta | TARGET:CDC42BPB | 5 | False | TARGET:CDC42BPB | TARGET:CDC42BPA | target lookup capped at two tokens |
| CTP:phosphocholine cytidylyltransferase-alpha | TARGET:PCYT1A | 2 | True | TARGET:PCYT1A | none | full name offered; inspect authority status and role |
| interleukin 2 receptor, alpha | TARGET:IL2RA | 4 | False | TARGET:IL2 | TARGET:IL2 | target lookup capped at two tokens |
| Lanosterol 14-alpha demethylase | TARGET:CYP51A1 | 3 | False | TARGET:MBD2 | TARGET:MBD2 | target lookup capped at two tokens |
| RAC-PK-gamma | TARGET:AKT3 | 1 | True | TARGET:AKT3 | none | full name offered; inspect authority status and role |
| Glycoprotein-fucosylgalactoside alpha-galactosyltransferase | TARGET:ABO | 2 | True | TARGET:ABO | none | full name offered; inspect authority status and role |
| voltage-gated calcium channel alpha subunit Cav2.3 | TARGET:CACNA1E | 6 | False | TARGET:CACNA1E | TARGET:CACNA1E | target lookup capped at two tokens |
| sodium/potassium-dependent ATPase beta-1 subunit | TARGET:ATP1B1 | 5 | False | TARGET:DNAH8 | TARGET:DNAH8 | target lookup capped at two tokens |
| GDNF receptor alpha 1e | TARGET:GFRA1 | 4 | False | TARGET:GDNF | TARGET:GDNF | target lookup capped at two tokens |
| large conductance Ca2+-activated K+ channel beta 1 subunit | TARGET:KCNMB1 | 8 | False | TARGET:LARGE1 | TARGET:LARGE1 | target lookup capped at two tokens |
| Steroid Delta-isomerase | UNCERTIFIED | 2 | True | none | none | full name offered; inspect authority status and role; identity/reference uncertified |
| acetylcholine receptor, nicotinic, delta (muscle) | TARGET:CHRND | 5 | False | none | none | target lookup capped at two tokens |
| 4-galactosyl-N-acetylglucosaminide 3-alpha-L-fucosyltransferase | UNCERTIFIED | 2 | True | none | none | full name offered; inspect authority status and role; identity/reference uncertified |
| PI3K-delta | TARGET:PIK3CD | 1 | True | TARGET:PIK3CD | none | full name offered; inspect authority status and role |
| pro-interleukin-1-beta | TARGET:IL1B | 1 | True | TARGET:IL1B | none | full name offered; inspect authority status and role |
| Serine/threonine-protein phosphatase 2B catalytic subunit beta isoform | TARGET:PPP3CB | 8 | False | none | none | target lookup capped at two tokens |
| tumor necrosis factor, alpha, converting enzyme | TARGET:ADAM17 | 6 | False | none | none | target lookup capped at two tokens |
| MGSA beta | TARGET:CXCL2 | 2 | True | TARGET:CXCL2 | TARGET:CXCL1 | full name offered; inspect authority status and role |
| polymerase (DNA directed), delta 2, regulatory subunit 50kDa | TARGET:POLD2 | 8 | False | none | none | target lookup capped at two tokens |
| nascent-polypeptide-associated complex beta polypeptide | TARGET:BTF3 | 4 | False | none | none | target lookup capped at two tokens |
| HNF-4-gamma | TARGET:HNF4G | 1 | True | TARGET:HNF4G | none | full name offered; inspect authority status and role |
| tubulin gamma complex associated protein 3 | TARGET:TUBGCP3 | 6 | False | TARGET:HSPB3 | TARGET:HSPB3 | target lookup capped at two tokens |
| CD8 beta opposite | TARGET:SMYD1 | 3 | False | TARGET:CD8A | TARGET:CD8A | target lookup capped at two tokens |
| Na(+)/K(+) ATPase alpha-1 subunit | TARGET:ATP1A1 | 4 | False | TARGET:DNAH8, TARGET:PSMA6 | TARGET:DNAH8 | target lookup capped at two tokens |
| Fc fragment of IgE, high affinity I, receptor for; alpha polypeptide | TARGET:FCER1A | 11 | False | TARGET:IGHE | TARGET:IGHE | target lookup capped at two tokens |
| AchR epsilon subunit | TARGET:CHRNE | 3 | False | none | none | target lookup capped at two tokens |
| Nuclear receptor ROR-gamma | TARGET:RORC | 3 | False | none | none | target lookup capped at two tokens |
| MMI-alpha | TARGET:MYO1B | 1 | True | TARGET:MYO1B | none | full name offered; inspect authority status and role |
| interferon alpha 1b | UNCERTIFIED | 3 | False | none | none | target lookup capped at two tokens; identity/reference uncertified |
| Adaptor protein complex AP-2 subunit mu | TARGET:AP2M1 | 6 | False | TARGET:TFAP2A | TARGET:TFAP2A | target lookup capped at two tokens |
| COPI coat complex subunit gamma 1 | TARGET:COPG1 | 6 | False | none | none | target lookup capped at two tokens |
| p70(S6K)-beta | TARGET:RPS6KB2 | 1 | True | TARGET:RPS6KB2 | none | full name offered; inspect authority status and role |
| IL-5R-alpha | TARGET:IL5RA | 1 | True | TARGET:IL5RA | none | full name offered; inspect authority status and role |
| Gamma-secretase-activating protein 16 kDa C-terminal form | TARGET:GSAP | 6 | False | TARGET:GSAP | none | target lookup capped at two tokens |
| Cholesteryl-beta-glucosidase GBA2 | TARGET:GBA2 | 2 | True | TARGET:GBA2 | TARGET:GBA2 | full name offered; inspect authority status and role |
| Delta and Notch-like epidermal growth factor-related receptor | TARGET:DNER | 7 | False | none | none | target lookup capped at two tokens |
| 3-beta-hydroxy-5-ene steroid dehydrogenase | UNCERTIFIED | 3 | False | none | none | target lookup capped at two tokens; identity/reference uncertified |
| Soluble APP-alpha | TARGET:APP | 2 | True | TARGET:APP | none | full name offered; inspect authority status and role |
| Chondroitin beta-1,4-N-acetylgalactosaminyltransferase 1 | TARGET:CSGALNACT1 | 3 | False | TARGET:B4GALNT1 | none | target lookup capped at two tokens |
| LX receptor beta | TARGET:NR1H2 | 3 | False | none | none | target lookup capped at two tokens |
| ATPase, Na+/K+ transporting, beta 3 polypeptide | TARGET:ATP1B3 | 6 | False | TARGET:DNAH8 | TARGET:DNAH8 | target lookup capped at two tokens |
| 3-galactosyl-N-acetylglucosaminide 4-alpha-L-fucosyltransferase 3 | TARGET:FUT3 | 3 | False | none | none | target lookup capped at two tokens |
| Protein transport protein Sec61 subunit beta | TARGET:SEC61B | 6 | False | TARGET:SEC61A1 | TARGET:SEC61A1 | target lookup capped at two tokens |
| 3 beta-HSD type II | TARGET:HSD3B2 | 4 | False | TARGET:SGCG | TARGET:SGCG | target lookup capped at two tokens |
| CaMK-II subunit alpha | TARGET:CAMK2A | 3 | False | TARGET:CAMK2G | TARGET:CAMK2G | target lookup capped at two tokens |
| phosphorylase kinase, delta subunit | UNCERTIFIED | 4 | False | none | none | target lookup capped at two tokens; identity/reference uncertified |
| CMP-N-acetylneuraminate beta-galactosamide alpha-2,6-sialyltransferase | TARGET:ST6GAL1 | 3 | False | none | none | target lookup capped at two tokens |
| PIAS-gamma | TARGET:PIAS4 | 1 | True | TARGET:PIAS4 | none | full name offered; inspect authority status and role |
| Alpha-galactosidase B | TARGET:NAGA | 2 | True | TARGET:NAGA | none | full name offered; inspect authority status and role |
| Thymopoietin-related peptide isoform alpha | TARGET:TMPO | 4 | False | none | none | target lookup capped at two tokens |
| PP2C-gamma | TARGET:PPM1G | 1 | True | TARGET:PPM1G | none | full name offered; inspect authority status and role |
| Guanine nucleotide-binding protein G(y) subunit alpha | TARGET:GNA11 | 6 | False | none | none | target lookup capped at two tokens |
| Beta-glucocerebrosidase | TARGET:GBA1 | 1 | True | TARGET:GBA1 | none | full name offered; inspect authority status and role |
| collagen, type IV, alpha 3 (Goodpasture antigen) binding protein | TARGET:CERT1 | 9 | False | TARGET:SGCG, TARGET:PSMA4, TARGET:COL4A3 | TARGET:SGCG, TARGET:COL4A3 | target lookup capped at two tokens |
| Proteasome subunit alpha type-6 | TARGET:PSMA6 | 4 | False | none | none | target lookup capped at two tokens |
