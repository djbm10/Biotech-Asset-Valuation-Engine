# TARGET_ALIAS_AUTHORITY_SOURCE v1 — computed JUSTIFIED_EXCLUDING_H17; implementation NOT authorized

Prereg `7d5c7ad` (`docs/se_policies/target_alias_authority_source_v1.md`). Readiness only; no production change. Reproduce: `PYTHONPATH=src python research/se_target_alias_authority_source_v1/audit.py --output <new dir>`. Source hashes are verified and two independent builds are byte-identical (J5 is measured by that comparison). Self-test: a certified unique alias → JUSTIFIED; a false unique with competing claimants, a wrong-subunit control, a protein/measurement error, downstream identity loss and an unregistered population change → STOP; no H17 spelling → JUSTIFIED_EXCLUDING_H17.

## Sources examined

HGNC complete set 2026-10-13 (45,277 records); NCIt 26.09d identifier records (13,032; protein-typed with Swiss-Prot/HGNC chains); NCIt 26.08e non-product names (cross-type check); UniProt 2026_03 (348 accessions, recorded only); runtime ChEMBL_37 + OT 26.06. No new acquisition.

## Independent population (192 survey entities)

233 candidate names not already runtime keys for their entity: **186 CERTIFIED**, 41 AMBIGUOUS_AUTHORITY, 4 CONFLICT_RUNTIME (e.g. `NRG1` on GDF15, `S15` on SIGLEC15, `SMR` on MSLN), 2 CROSS_TYPE (disease names). Of the certified names, only **49 are reachable** under the adopted 2-token target cap; 137 are ≥3 tokens and need the unresolved span-arbitration design. Reachable certified names cover **29/192 entities (15.1%)**. J1 PASS; J2 PASS (no certified name has a competing claimant; all 16 frozen controls hold).

## H17 / H20 offline chains

- **H17 `IL-4Rα`: not repairable from any authority.** No exact spelling in HGNC, NCIt protein records or NCIt non-product names (UniProt has `IL-4R-alpha` / `IL-4RA`; NCIt has `IL-4R-Alpha`). Current chain: zero targets → IntentNotCompilable. Repair would need an orthographic transform, which was rejected in Greek v2. J3 FAIL.
- **H20 `factor XI`: repairable in principle.** NCIt C201572 (protein; Swiss-Prot P03951; encoded by a gene carrying HGNC:3529) is the only protein claimant. The NCIt measurement concept is a different type and is not a target. With the alias injected into an in-process resolver copy (research only), parse → `factor XI` TARGET → compile → **5 plans carrying TARGET:F11**, the same as the existing `FXI` chain. Current chain: refusal. The mapping must use the HGNC/UniProt identifier chain, not the symbol `F11`, which stays ambiguous with ZNF160. J4 PASS.

## Why implementation is NOT authorized despite the computed verdict

Inspecting the certified list after measurement shows hazard classes the frozen rubric never measured:
- **Ordinary-language / drug-class names:** `statin` and `statin-like` are certified to EEF1A2 (genuine HGNC previous names). A query mentioning statins would become an EEF1A2 target query. That is an unsupported target promotion in practice, even though it has a single claimant.
- **Enzyme-class codes:** EC numbers (`EC 3.1.1.7`, `EC 3.9.1.1` …) are reaction classes. They look unique only because the NCIt subset is partial; 31 other EC codes were already ambiguous.
- **Historical previous names** supply 80 of 186 certified names (`Flavin reductase`, `nucleoporin 205kDa`) and are the main source of ordinary-word risk.

Claimant uniqueness is necessary but not sufficient. That is the same lesson as trade names (36% ordinary words with a single claimant). The rubric is not amended after results, so this is a **mechanical pass that is not scientifically safe**.

## Next step (precise)

Preregister `TARGET_ALIAS_AUTHORITY_SOURCE v2` (readiness, then implementation contract). It must freeze, **before** measuring:
1. ordinary-word and drug-class negative controls drawn from an independent vocabulary (e.g. the existing ATC/drug-class lists in the ontology), not from this list;
2. exclusion of reaction-class identifiers (EC) as target names;
3. a decision on previous-name admission with its own controls;
4. the NCIt protein-typed + identifier-chain route as a candidate source class.

H20 is the clearest beneficiary. H17 needs no further alias work: it is not authority-repairable and stays a known refusal. The ≥3-token names wait on the span-arbitration design.
