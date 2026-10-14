# TRADE_NAME_ASSET_IDENTITY_DIAGNOSIS v1 — STOP

Prereg `e0b3750` (`docs/se_policies/trade_name_asset_identity_diagnosis_v1.md`). Diagnosis only; `_IDENTIFIER_ALIAS_TYPES` is unchanged. Reproduce: `PYTHONPATH=src python research/se_trade_name_asset_identity_diagnosis_v1/audit.py --output <new dir>`. Run hashes are verified and two builds are byte-identical. Self-test: a valid fixture is JUSTIFIED; a certified ordinary word fails S1; a biosimilar without a product relation fails S2 (and passes once that relation exists); coverage loss fails S3; missing provenance fails S4.

## First boundary (all six exposed H18/H19 rows)

Saxenda, Victoza, Ozempic, Wegovy, Rybelsus and TRODELVY each RESOLVE through TRADE_NAME only, with a single claimant, to the expected canonical drug. `resolve_identifier` returns None because TRADE_NAME is not in `_IDENTIFIER_ALIAS_TYPES`, so `identifies_drug` returns None and `consolidate_by_authority` never groups the brand record with the molecule record. The boundary is the identity policy; authority data and discovery are not the problem.

## Independent population

69 trade-name-only (name, canonical) pairs across the non-holdout dev runs (TRODELVY excluded as exposed). Blind labels:
- 38 equivalent single-molecule brands;
- 2 biosimilars (Herwenda, Tyruko);
- 4 authority-too-coarse (Gardasil and Cervarix share one HPV antigen canonical; Abrysvo; Nuvaxovid);
- 25 not-equivalent (`frontline`, `avert`, `choice`, `search`, `saline`, `roche`, `fresenius` …).

**36% of trade-name-only resolutions in real candidate names are wrong.** Every one of the 25 has a single claimant in the authority, so ambiguity counting cannot catch them.

## Contracts

| | Certified | False certified (S1) | Biosimilar (S2) | Coverage (S3) | First fail |
|---|---|---|---|---|---|
| T0 single-claimant TRADE_NAME | 68 | **29** (25 ordinary/company words + 4 coarse vaccines) | 2 | 97% | **S1** |
| T1 + canonical approved name in the candidate's own source document | 20 | **0** | 2 | **47%** | **S2** (S3 also fails) |

- **T0 is unsafe.** It would merge, for example, the candidate `avert` into a real acyclovir candidate (a would-merge partner exists in the dev run).
- **T1 is safe on molecule identity** (zero ordinary words, zero coarse vaccines) but fails twice. It certifies both biosimilars, whose source documents naturally name the originator molecule, and the schema has no product-level relation (`SAME_MOLECULE_DISTINCT_PRODUCT`) to keep them distinct. It also reaches only 18/38 true brands, because abstracts and registry records often name the brand without the INN.
- **Exposed duplicates under T1:** TRODELVY's own source document does not contain "sacituzumab govitecan" (not corroborated), so even T1 would not fix H19.

## Diagnostic estimate (not a validated improvement)

34 dev trade-name pairs have a would-merge partner (an identifier-resolving candidate for the same canonical). T1 would merge only the corroborated subset, including two biosimilar-into-originator merges that are unsafe without a product relation.

## Verdict and next milestone

**No general trade-name identity contract is justified.** The safe variant (T1) needs two things that don't exist:
1. a product-level relationship (`SAME_MOLECULE_DISTINCT_PRODUCT` / `BIOSIMILAR_OF`) so molecule display groups keep brands and biosimilars as distinct members;
2. a recall source beyond in-document co-mention, e.g. an authority-backed brand→INN record (FDA/EMA product labels) rather than ChEMBL's free-text trade-name list, which carries ordinary words.

Next authorized step, if pursued: a separately preregistered **PRODUCT_LEVEL_IDENTITY_RELATION v1** representation milestone (decision-neutral), then re-run this diagnosis. The H18/H19 duplicates remain, by design. The NK-construct duplicate is untouched.
