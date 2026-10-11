# SHORTLIST_NONPRODUCT_OFFTARGET_DIAGNOSIS v1 — per-row appendix (generated from rows_v1.json)

Columns: pos, name, frozen label, first-failure class, gate statuses (ID identity, T target, MOD modality, TA area, IND indication, STG stage), qualification reason, entity link (trials/companies/targets), authority drug → direct targets, modality (declared/authority/match), stage, origin publishers, target assertion status + sources.

## H2 (intended KRAS; candidates 12762, excluded 1735, low-support 9949, shortlist 1078, eligible 0)

| # | name | label | cls | ID | T | MOD | TA | IND | STG | qualification | link t/c/tg | authority | modality | stage | origin | target assertion |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Krazati | RELEVANT |  | UNKN | PASS | - | UNKN | UNKN | UNKN | ENTITY_CORROBORATED_SYNONYM | 0/0/1 | DRUG:ADAGRASIB → KRAS | SMALL_MOLECULE/None/None | - | PubMed×1 | KRAS=CONFIRMED_TARGET(chembl,open_targets) |
| 2 | aficamten | WRONG_TARGET | D | UNKN | UNKN | - | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:AFICAMTEN → ∅ | CELL_THERAPY/SMALL_MOLECULE/None | - | PubMed×4 | KRAS=UNRESOLVED |
| 3 | Trimix | NON_ASSET | A | UNKN | UNKN | - | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:TRIMIX → ∅ | CELL_THERAPY/None/None | - | PubMed×3 | KRAS=UNRESOLVED |
| 4 | AFM11 | WRONG_TARGET | D | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:AFM-11 → ∅ | BISPECIFIC_ANTIBODY/None/None | - | AACR×2 | KRAS=UNRESOLVED |
| 5 | bendamustine | WRONG_TARGET | D | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:BENDAMUSTINE → ∅ | MONOCLONAL_ANTIBODY/SMALL_MOLECULE/None | - | AACR×1, PubMed×11 | KRAS=UNRESOLVED |
| 6 | bromide | NON_ASSET | A | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:BROMIDE → ∅ | None/SMALL_MOLECULE/None | - | PubMed×23, AACR×1 | KRAS=UNRESOLVED |
| 7 | butanone | NON_ASSET | A | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:BUTANONE → ∅ | T_CELL_ENGAGER/SMALL_MOLECULE/None | - | AACR×2, PubMed×1 | KRAS=UNRESOLVED |
| 8 | chromium | NON_ASSET | A | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CHROMIUM → ∅ | None/SMALL_MOLECULE/None | - | AACR×2, PubMed×8 | KRAS=UNRESOLVED |
| 9 | creatinine | NON_ASSET | A | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CREATININE → ∅ | None/SMALL_MOLECULE/None | - | AACR×1, PubMed×125 | KRAS=UNRESOLVED |
| 10 | Curcumin | WRONG_TARGET | D | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CURCUMIN → ∅ | MONOCLONAL_ANTIBODY/SMALL_MOLECULE/None | - | AACR×2, PubMed×35 | KRAS=UNRESOLVED |
| 11 | duvortuxizumab | WRONG_TARGET | D | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:DUVORTUXIZUMAB → ∅ | CELL_THERAPY/ANTIBODY/None | - | AACR×4 | KRAS=UNRESOLVED |
| 12 | Emfizatamab | UNVERIFIABLE |  | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:EMFIZATAMAB → ∅ | MONOCLONAL_ANTIBODY/ANTIBODY/None | - | AACR×1 | KRAS=UNRESOLVED |
| 13 | eosin | NON_ASSET | A | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:EOSIN → ∅ | None/SMALL_MOLECULE/None | - | AACR×1, PubMed×21 | KRAS=UNRESOLVED |
| 14 | fluorescein | NON_ASSET | A | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:FLUORESCEIN → ∅ | None/SMALL_MOLECULE/None | - | AACR×1, PubMed×20 | KRAS=UNRESOLVED |
| 15 | hematoxylin | NON_ASSET | A | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:HEMATOXYLIN → ∅ | T_CELL_ENGAGER/SMALL_MOLECULE/None | - | AACR×1, PubMed×21 | KRAS=UNRESOLVED |
| 16 | isothiocyanate | NON_ASSET | A | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:ISOTHIOCYANATE → ∅ | CAR_T/SMALL_MOLECULE/None | - | AACR×1, PubMed×1 | KRAS=UNRESOLVED |
| 17 | Loncastuximab | WRONG_TARGET | D | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:LONCASTUXIMAB → ∅ | ANTIBODY_DRUG_CONJUGATE/ANTIBODY/None | - | AACR×1 | KRAS=UNRESOLVED |
| 18 | Maleimide | NON_ASSET | A | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:MALEIMIDE → ∅ | ANTIBODY_DRUG_CONJUGATE/SMALL_MOLECULE/None | - | AACR×1, PubMed×1 | KRAS=UNRESOLVED |
| 19 | methane | NON_ASSET | B | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:METHANE → ∅ | CELL_THERAPY/SMALL_MOLECULE/None | - | AACR×1, PubMed×7 | KRAS=UNRESOLVED |
| 20 | mitomycin | WRONG_TARGET | D | PASS | UNKN | - | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:MITOMYCIN → ∅ | FUSION_PROTEIN/SMALL_MOLECULE/None | - | AACR×1, PubMed×44 | KRAS=UNRESOLVED |

**Reference products:** sotorasib: excluded (Sotorasib); adagrasib: excluded (Adagrasib); divarasib: excluded (Divarasib); olomorasib: excluded (olomorasib); garsorasib: excluded (Garsorasib); fulzerasib: excluded (fulzerasib); glecirasib: excluded (glecirasib); opnurasib: excluded (opnurasib); elironrasib: shortlist #362 (elironrasib)

## H4 (intended TNFSF15; candidates 517, excluded 81, low-support 396, shortlist 40, eligible 0)

| # | name | label | cls | ID | T | MOD | TA | IND | STG | qualification | link t/c/tg | authority | modality | stage | origin | target assertion |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | afimkibart | RELEVANT |  | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:AFIMKIBART → ∅ | BISPECIFIC_ANTIBODY/ANTIBODY/MATCH | - | PubMed×1 | TNFSF15=UNRESOLVED |
| 2 | duvakitug | RELEVANT |  | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:DUVAKITUG → ∅ | BISPECIFIC_ANTIBODY/ANTIBODY/MATCH | - | PubMed×1 | TNFSF15=UNRESOLVED |
| 3 | tulisokibart | RELEVANT |  | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:TULISOKIBART → ∅ | BISPECIFIC_ANTIBODY/ANTIBODY/MATCH | - | PubMed×1 | TNFSF15=UNRESOLVED |
| 4 | papain | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:PAPAIN → ∅ | None/None/UNKNOWN | - | PubMed×1 | TNFSF15=UNRESOLVED |
| 5 | sesquiterpene | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:SESQUITERPENE → ∅ | T_CELL_ENGAGER/None/UNKNOWN | - | PubMed×4 | TNFSF15=UNRESOLVED |
| 6 | alloxan | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:ALLOXAN → ∅ | T_CELL_ENGAGER/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TNFSF15=UNRESOLVED |
| 7 | Bavachin | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:BAVACHIN → ∅ | None/SMALL_MOLECULE/MISMATCH | - | PubMed×2 | TNFSF15=UNRESOLVED |
| 8 | Berberine | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:BERBERINE → ∅ | T_CELL_ENGAGER/SMALL_MOLECULE/MISMATCH | - | PubMed×3 | TNFSF15=UNRESOLVED |
| 9 | carboplatin | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CARBOPLATIN → ∅ | MONOCLONAL_ANTIBODY/SMALL_MOLECULE/MISMATCH | - | PubMed×3 | TNFSF15=UNRESOLVED |
| 10 | ceftazidime | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CEFTAZIDIME → ∅ | FUSION_PROTEIN/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TNFSF15=UNRESOLVED |
| 11 | ciprofloxacin | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CIPROFLOXACIN → ∅ | None/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TNFSF15=UNRESOLVED |
| 12 | creatinine | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CREATININE → ∅ | None/SMALL_MOLECULE/MISMATCH | - | PubMed×2 | TNFSF15=UNRESOLVED |
| 13 | danegaptide | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:DANEGAPTIDE → ∅ | MONOCLONAL_ANTIBODY/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TNFSF15=UNRESOLVED |
| 14 | digitoxigenin | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:DIGITOXIGENIN → ∅ | T_CELL_ENGAGER/SMALL_MOLECULE/MISMATCH | - | PubMed×2 | TNFSF15=UNRESOLVED |
| 15 | dihydroergocristine mesylate | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:DIHYDROERGOCRISTINE MESYLATE → ∅ | T_CELL_ENGAGER/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TNFSF15=UNRESOLVED |
| 16 | ethylene | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:ETHYLENE → ∅ | None/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TNFSF15=UNRESOLVED |
| 17 | fluoride | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:FLUORIDE → ∅ | None/SMALL_MOLECULE/MISMATCH | - | PubMed×2 | TNFSF15=UNRESOLVED |
| 18 | hydroxyapatite | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:DURAPATITE → ∅ | None/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TNFSF15=UNRESOLVED |
| 19 | Indocyanine green | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:INDOCYANINE GREEN → ∅ | MONOCLONAL_ANTIBODY/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TNFSF15=UNRESOLVED |
| 20 | lomustine | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:LOMUSTINE → ∅ | MONOCLONAL_ANTIBODY/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TNFSF15=UNRESOLVED |

**Reference products:** tulisokibart: shortlist #3 (tulisokibart); duvakitug: shortlist #2 (duvakitug); afimkibart: shortlist #1 (afimkibart)

## H11 (intended TIGIT; candidates 602, excluded 122, low-support 453, shortlist 27, eligible 0)

| # | name | label | cls | ID | T | MOD | TA | IND | STG | qualification | link t/c/tg | authority | modality | stage | origin | target assertion |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | benmelstobart | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:BENMELSTOBART → ∅ | MONOCLONAL_ANTIBODY/ANTIBODY/MATCH | - | PubMed×5 | TIGIT=UNRESOLVED |
| 2 | gremubamab | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:GREMUBAMAB → ∅ | MONOCLONAL_ANTIBODY/ANTIBODY/MATCH | - | PubMed×1 | TIGIT=UNRESOLVED |
| 3 | Nelistotug | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:NELISTOTUG → ∅ | MONOCLONAL_ANTIBODY/ANTIBODY/MATCH | - | PubMed×2 | TIGIT=UNRESOLVED |
| 4 | peresolimab | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:PERESOLIMAB → ∅ | CAR_T/ANTIBODY/MATCH | - | PubMed×1 | TIGIT=UNRESOLVED |
| 5 | tobemstomig | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:TOBEMSTOMIG → ∅ | MONOCLONAL_ANTIBODY/ANTIBODY/MATCH | - | PubMed×3 | TIGIT=UNRESOLVED |
| 6 | Volrustomig | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:VOLRUSTOMIG → ∅ | None/ANTIBODY/MATCH | - | PubMed×2 | TIGIT=UNRESOLVED |
| 7 | DSTA4637S | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:DSTA-4637S → ∅ | MONOCLONAL_ANTIBODY/None/UNKNOWN | - | PubMed×1 | TIGIT=UNRESOLVED |
| 8 | gebasaxturev | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:GEBASAXTUREV → ∅ | None/None/UNKNOWN | - | PubMed×2 | TIGIT=UNRESOLVED |
| 9 | sodium alginate | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:SODIUM ALGINATE → ∅ | None/None/UNKNOWN | - | PubMed×1 | TIGIT=UNRESOLVED |
| 10 | carboplatin | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CARBOPLATIN → ∅ | MONOCLONAL_ANTIBODY/SMALL_MOLECULE/MISMATCH | - | PubMed×4 | TIGIT=UNRESOLVED |
| 11 | cabotegravir | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CABOTEGRAVIR → ∅ | None/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TIGIT=UNRESOLVED |
| 12 | carbon monoxide | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CARBON MONOXIDE → ∅ | None/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TIGIT=UNRESOLVED |
| 13 | deucrictibant | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:DEUCRICTIBANT → ∅ | None/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TIGIT=UNRESOLVED |
| 14 | dolutegravir | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:DOLUTEGRAVIR → ∅ | None/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TIGIT=UNRESOLVED |
| 15 | gadolinium | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:GADOLINIUM → ∅ | CELL_THERAPY/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TIGIT=UNRESOLVED |
| 16 | icosapent ethyl | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:ICOSAPENT ETHYL → ∅ | None/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TIGIT=UNRESOLVED |
| 17 | leucovorin | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:LEUCOVORIN → ∅ | MONOCLONAL_ANTIBODY/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TIGIT=UNRESOLVED |
| 18 | levofloxacin | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:LEVOFLOXACIN → ∅ | RNA_THERAPEUTIC/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TIGIT=UNRESOLVED |
| 19 | methicillin | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:METHICILLIN → ∅ | MONOCLONAL_ANTIBODY/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TIGIT=UNRESOLVED |
| 20 | oxaliplatin | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:OXALIPLATIN → ∅ | MONOCLONAL_ANTIBODY/SMALL_MOLECULE/MISMATCH | - | PubMed×1 | TIGIT=UNRESOLVED |

**Reference products:** tiragolumab: excluded (Tiragolumab); domvanalimab: excluded (Domvanalimab); vibostolimab: excluded (vibostolimab); ociperlimab: excluded (Ociperlimab); belrestotug: excluded (belrestotug); rilvegostomig: excluded (Rilvegostomig)

## H12 (intended C5; candidates 3481, excluded 547, low-support 2650, shortlist 284, eligible 0)

| # | name | label | cls | ID | T | MOD | TA | IND | STG | qualification | link t/c/tg | authority | modality | stage | origin | target assertion |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Alexion | NON_ASSET | A | UNKN | PASS | - | - | UNKN | UNKN | ENTITY_CORROBORATED_SYNONYM | 0/0/1 | DRUG:ECULIZUMAB → C5 | MONOCLONAL_ANTIBODY/None/None | - | PubMed×2 | C5=CONFIRMED_TARGET(chembl,open_targets) |
| 2 | ARC1905 | RELEVANT |  | UNKN | PASS | - | - | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/1 | DRUG:AVACINCAPTAD PEGOL SODIUM → C5 | None/None/None | - | PubMed×2 | C5=CONFIRMED_TARGET(chembl,open_targets) |
| 3 | crovalimab-akkz | RELEVANT |  | UNKN | PASS | - | - | UNKN | UNKN | ENTITY_CORROBORATED_SYNONYM | 0/0/1 | DRUG:CROVALIMAB → C5 | MONOCLONAL_ANTIBODY/None/None | - | PubMed×2 | C5=CONFIRMED_TARGET(chembl,open_targets) |
| 4 | Izervay | DUPLICATE | H | UNKN | PASS | - | - | UNKN | UNKN | ENTITY_CORROBORATED_SYNONYM | 0/0/1 | DRUG:AVACINCAPTAD PEGOL SODIUM → C5 | None/None/None | - | PubMed×13 | C5=CONFIRMED_TARGET(chembl,open_targets) |
| 5 | pexelizumab | RELEVANT |  | UNKN | PASS | - | - | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/1 | DRUG:PEXELIZUMAB → C5 | MONOCLONAL_ANTIBODY/ANTIBODY/None | - | PubMed×53 | C5=CONFIRMED_TARGET(chembl,open_targets) |
| 6 | PiaSky | DUPLICATE | H | UNKN | PASS | - | - | UNKN | UNKN | ENTITY_CORROBORATED_SYNONYM | 0/0/1 | DRUG:CROVALIMAB → C5 | MONOCLONAL_ANTIBODY/None/None | - | PubMed×5 | C5=CONFIRMED_TARGET(chembl,open_targets) |
| 7 | pozelimab-bbfg | RELEVANT |  | UNKN | PASS | - | - | UNKN | UNKN | ENTITY_CORROBORATED_SYNONYM | 0/0/1 | DRUG:POZELIMAB → C5 | MONOCLONAL_ANTIBODY/None/None | - | PubMed×2 | C5=CONFIRMED_TARGET(chembl,open_targets) |
| 8 | Ultomiris | RELEVANT |  | UNKN | PASS | - | - | UNKN | UNKN | ENTITY_CORROBORATED_SYNONYM | 0/0/1 | DRUG:RAVULIZUMAB → C5 | MONOCLONAL_ANTIBODY/None/None | - | PubMed×1 | C5=CONFIRMED_TARGET(chembl,open_targets) |
| 9 | Veopoz | DUPLICATE | H | UNKN | PASS | - | - | UNKN | UNKN | ENTITY_CORROBORATED_SYNONYM | 0/0/1 | DRUG:POZELIMAB → C5 | MONOCLONAL_ANTIBODY/None/None | - | PubMed×3 | C5=CONFIRMED_TARGET(chembl,open_targets) |
| 10 | Tamuzimod | WRONG_TARGET | D | UNKN | UNKN | - | - | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:TAMUZIMOD → ∅ | None/SMALL_MOLECULE/None | - | PubMed×3 | C5=UNRESOLVED |
| 11 | AFM11 | WRONG_TARGET | D | PASS | UNKN | - | - | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:AFM-11 → ∅ | BISPECIFIC_ANTIBODY/None/None | - | AACR×2 | C5=UNRESOLVED |
| 12 | bendamustine | WRONG_TARGET | D | PASS | UNKN | - | - | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:BENDAMUSTINE → ∅ | None/SMALL_MOLECULE/None | - | AACR×1, PubMed×1 | C5=UNRESOLVED |
| 13 | butanone | NON_ASSET | A | PASS | UNKN | - | - | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:BUTANONE → ∅ | None/SMALL_MOLECULE/None | - | AACR×1 | C5=UNRESOLVED |
| 14 | chromium | NON_ASSET | A | PASS | UNKN | - | - | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CHROMIUM → ∅ | None/SMALL_MOLECULE/None | - | PubMed×1, AACR×1 | C5=UNRESOLVED |
| 15 | creatinine | NON_ASSET | A | PASS | UNKN | - | - | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CREATININE → ∅ | MONOCLONAL_ANTIBODY/SMALL_MOLECULE/None | - | PubMed×22, AACR×1 | C5=UNRESOLVED |
| 16 | cyclophosphamide | WRONG_TARGET | D | PASS | UNKN | - | - | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CYCLOPHOSPHAMIDE → ∅ | MONOCLONAL_ANTIBODY/SMALL_MOLECULE/None | - | PubMed×37, AACR×4 | C5=UNRESOLVED |
| 17 | duvortuxizumab | WRONG_TARGET | D | PASS | UNKN | - | - | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:DUVORTUXIZUMAB → ∅ | CELL_THERAPY/ANTIBODY/None | - | AACR×4 | C5=UNRESOLVED |
| 18 | eosin | NON_ASSET | A | PASS | UNKN | - | - | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:EOSIN → ∅ | CELL_THERAPY/SMALL_MOLECULE/None | - | AACR×1 | C5=UNRESOLVED |
| 19 | fludarabine | WRONG_TARGET | D | PASS | UNKN | - | - | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:FLUDARABINE → ∅ | CAR_T/SMALL_MOLECULE/None | - | PubMed×2, AACR×3 | C5=UNRESOLVED |
| 20 | hematoxylin | NON_ASSET | A | PASS | UNKN | - | - | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:HEMATOXYLIN → ∅ | CELL_THERAPY/SMALL_MOLECULE/None | - | AACR×1 | C5=UNRESOLVED |

**Reference products:** eculizumab: excluded (Soliris); ravulizumab: excluded (Ravulizumab); crovalimab: excluded (Crovalimab); pozelimab: excluded (pozelimab); zilucoplan: excluded (zilucoplan); cemdisiran: excluded (Cemdisiran); tesidolumab: excluded (tesidolumab)

## H13 (intended IL17A; candidates 2514, excluded 263, low-support 2018, shortlist 233, eligible 0)

| # | name | label | cls | ID | T | MOD | TA | IND | STG | qualification | link t/c/tg | authority | modality | stage | origin | target assertion |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ABT-122 | RELEVANT |  | UNKN | PASS | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/1 | DRUG:REMTOLUMAB → IL17A,TNF | SMALL_MOLECULE/ANTIBODY/MATCH | - | PubMed×13 | IL17A=CONFIRMED_TARGET(chembl,open_targets) |
| 2 | Afasevikumab | RELEVANT |  | UNKN | PASS | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/1 | DRUG:AFASEVIKUMAB → IL17A | MONOCLONAL_ANTIBODY/ANTIBODY/MATCH | - | PubMed×2 | IL17A=CONFIRMED_TARGET(chembl,open_targets) |
| 3 | afimkibart | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:AFIMKIBART → ∅ | SMALL_MOLECULE/ANTIBODY/MATCH | - | PubMed×1 | IL17A=UNRESOLVED |
| 4 | Avizakimab | UNVERIFIABLE |  | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:AVIZAKIMAB → ∅ | MONOCLONAL_ANTIBODY/ANTIBODY/MATCH | - | PubMed×1 | IL17A=UNRESOLVED |
| 5 | certolizumab | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CERTOLIZUMAB → ∅ | None/ANTIBODY/MATCH | - | PubMed×2 | IL17A=UNRESOLVED |
| 6 | denecimig | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:DENECIMIG → ∅ | ANTIBODY_DRUG_CONJUGATE/ANTIBODY/MATCH | - | PubMed×1 | IL17A=UNRESOLVED |
| 7 | duvakitug | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:DUVAKITUG → ∅ | SMALL_MOLECULE/ANTIBODY/MATCH | - | PubMed×1 | IL17A=UNRESOLVED |
| 8 | gremubamab | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:GREMUBAMAB → ∅ | MONOCLONAL_ANTIBODY/ANTIBODY/MATCH | - | PubMed×1 | IL17A=UNRESOLVED |
| 9 | gumokimab | RELEVANT |  | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:GUMOKIMAB → ∅ | MONOCLONAL_ANTIBODY/ANTIBODY/MATCH | - | PubMed×1 | IL17A=UNRESOLVED |
| 10 | ivonescimab | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:IVONESCIMAB → ∅ | ANTIBODY_DRUG_CONJUGATE/ANTIBODY/MATCH | - | PubMed×1 | IL17A=UNRESOLVED |
| 11 | netakimab | RELEVANT |  | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:NETAKIMAB → ∅ | None/ANTIBODY/MATCH | - | PubMed×5 | IL17A=UNRESOLVED |
| 12 | Stapokibart | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:STAPOKIBART → ∅ | MONOCLONAL_ANTIBODY/ANTIBODY/MATCH | - | PubMed×2 | IL17A=UNRESOLVED |
| 13 | tulisokibart | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:TULISOKIBART → ∅ | SMALL_MOLECULE/ANTIBODY/MATCH | - | PubMed×1 | IL17A=UNRESOLVED |
| 14 | Bimzelx | RELEVANT |  | UNKN | PASS | UNKN | UNKN | UNKN | UNKN | ENTITY_CORROBORATED_SYNONYM | 0/0/1 | DRUG:BIMEKIZUMAB → IL17A,IL17F | MONOCLONAL_ANTIBODY/None/UNKNOWN | - | PubMed×2 | IL17A=CONFIRMED_TARGET(chembl,open_targets) |
| 15 | amino acids | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:AMINO ACIDS → ∅ | CELL_THERAPY/None/UNKNOWN | - | PubMed×6 | IL17A=UNRESOLVED |
| 16 | Carrageenan | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CARRAGEENAN → ∅ | CELL_THERAPY/None/UNKNOWN | - | PubMed×1 | IL17A=UNRESOLVED |
| 17 | colistin | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:COLISTIN → ∅ | None/None/UNKNOWN | - | PubMed×1 | IL17A=UNRESOLVED |
| 18 | ginger | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:GINGER → ∅ | None/None/UNKNOWN | - | PubMed×1 | IL17A=UNRESOLVED |
| 19 | ginkgo | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:GINKGO → ∅ | T_CELL_ENGAGER/None/UNKNOWN | - | PubMed×2 | IL17A=UNRESOLVED |
| 20 | honey | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:HONEY → ∅ | None/None/UNKNOWN | - | PubMed×2 | IL17A=UNRESOLVED |

**Reference products:** secukinumab: excluded (Secukinumab); ixekizumab: excluded (Ixekizumab); bimekizumab: excluded (Bimekizumab); izokibep: excluded (Izokibep); sonelokimab: excluded (Sonelokimab); netakimab: shortlist #11 (netakimab); vunakizumab: excluded (Vunakizumab); xeligekimab: excluded (Xeligekimab)

## H14 (intended CD38; candidates 3469, excluded 458, low-support 2738, shortlist 273, eligible 0)

| # | name | label | cls | ID | T | MOD | TA | IND | STG | qualification | link t/c/tg | authority | modality | stage | origin | target assertion |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Emfizatamab | UNVERIFIABLE |  | PASS | UNKN | UNKN | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:EMFIZATAMAB → ∅ | MONOCLONAL_ANTIBODY/ANTIBODY/MATCH | - | AACR×1 | CD38=UNRESOLVED |
| 2 | afimkibart | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:AFIMKIBART → ∅ | SMALL_MOLECULE/ANTIBODY/MATCH | - | PubMed×1 | CD38=UNRESOLVED |
| 3 | anselamimab | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:ANSELAMIMAB → ∅ | MONOCLONAL_ANTIBODY/ANTIBODY/MATCH | - | PubMed×3 | CD38=UNRESOLVED |
| 4 | belantamab | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:BELANTAMAB → ∅ | MONOCLONAL_ANTIBODY/ANTIBODY/MATCH | - | PubMed×14 | CD38=UNRESOLVED |
| 5 | BIVV020 | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:RILIPRUBART → ∅ | SMALL_MOLECULE/ANTIBODY/MATCH | - | PubMed×1 | CD38=UNRESOLVED |
| 6 | Cevostamab | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CEVOSTAMAB → ∅ | None/ANTIBODY/MATCH | - | PubMed×2 | CD38=UNRESOLVED |
| 7 | duvakitug | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:DUVAKITUG → ∅ | SMALL_MOLECULE/ANTIBODY/MATCH | - | PubMed×1 | CD38=UNRESOLVED |
| 8 | gremubamab | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:GREMUBAMAB → ∅ | MONOCLONAL_ANTIBODY/ANTIBODY/MATCH | - | PubMed×1 | CD38=UNRESOLVED |
| 9 | linvoseltamab | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:LINVOSELTAMAB → ∅ | T_CELL_ENGAGER/ANTIBODY/MATCH | - | PubMed×16 | CD38=UNRESOLVED |
| 10 | loncastuximab | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:LONCASTUXIMAB → ∅ | ANTIBODY_DRUG_CONJUGATE/ANTIBODY/MATCH | - | PubMed×1 | CD38=UNRESOLVED |
| 11 | tulisokibart | WRONG_TARGET | D | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:TULISOKIBART → ∅ | SMALL_MOLECULE/ANTIBODY/MATCH | - | PubMed×1 | CD38=UNRESOLVED |
| 12 | isatuximab-irfc | RELEVANT |  | UNKN | PASS | UNKN | UNKN | UNKN | UNKN | ENTITY_CORROBORATED_SYNONYM | 0/0/1 | DRUG:ISATUXIMAB → CD38 | MONOCLONAL_ANTIBODY/None/UNKNOWN | - | PubMed×1 | CD38=CONFIRMED_TARGET(chembl,open_targets) |
| 13 | SARCLISA | DUPLICATE | H | UNKN | PASS | UNKN | UNKN | UNKN | UNKN | ENTITY_CORROBORATED_SYNONYM | 0/0/1 | DRUG:ISATUXIMAB → CD38 | MONOCLONAL_ANTIBODY/None/UNKNOWN | - | PubMed×1 | CD38=CONFIRMED_TARGET(chembl,open_targets) |
| 14 | AFM11 | WRONG_TARGET | D | PASS | UNKN | UNKN | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:AFM-11 → ∅ | BISPECIFIC_ANTIBODY/None/UNKNOWN | - | AACR×1 | CD38=UNRESOLVED |
| 15 | paraffin | NON_ASSET | A | PASS | UNKN | UNKN | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:PARAFFIN → ∅ | None/None/UNKNOWN | - | AACR×1, PubMed×2 | CD38=UNRESOLVED |
| 16 | vehicle | NON_ASSET | A | PASS | UNKN | UNKN | PASS | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:VEHICLE → ∅ | CELL_THERAPY/None/UNKNOWN | - | PubMed×17, AACR×5 | CD38=UNRESOLVED |
| 17 | amino acids | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:AMINO ACIDS → ∅ | None/None/UNKNOWN | - | PubMed×12 | CD38=UNRESOLVED |
| 18 | avidin | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:AVIDIN → ∅ | MONOCLONAL_ANTIBODY/None/UNKNOWN | - | PubMed×1 | CD38=UNRESOLVED |
| 19 | carboxymethyl cellulose | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CARBOXYMETHYLCELLULOSE CALCIUM → ∅ | T_CELL_ENGAGER/None/UNKNOWN | - | PubMed×1 | CD38=UNRESOLVED |
| 20 | cinnamon | NON_ASSET | A | UNKN | UNKN | UNKN | UNKN | UNKN | UNKN | DIRECT_APPROVED_NAME | 0/0/0 | DRUG:CINNAMON → ∅ | RNA_THERAPEUTIC/None/UNKNOWN | - | PubMed×8 | CD38=UNRESOLVED |

**Reference products:** daratumumab: excluded (Daratumumab); isatuximab: excluded (Isatuximab); felzartamab: excluded (Felzartamab); mezagitamab: excluded (mezagitamab); CID-103: excluded (CID-103)

