# TARGET_ALIAS_AUTHORITY_SOURCE v2 — bounded design study (preregistration)

The last target-alias design iteration before switching workstreams. No production change; no implementation authorized here. v1 (`d4ac958`) is unchanged and exposed. H17 stays a known refusal (no Greek transform). The 2-token parser cap is unchanged. H21–H25 are not read; heldout symbols (CFD, DLL3, ERBB2, IL1RL2, IL23A, KLKB1, LRRK2, MSTN, PCSK9, TSLP) are excluded from every population.

## Sources (frozen hashes in `research/se_target_alias_authority_source_v2/freeze_hashes.txt`)

HGNC complete 2026-10-13; NCIt 26.09d identifier records; runtime ontology ChEMBL_37 + OT 26.06 (TARGET and DRUG entities); NCIt 26.08e non-product names.

## Candidate universe (computed for all 78,378 runtime targets, before any policy filter)

For each runtime TARGET with an Ensembl link to an HGNC record:
- **A-source:** P90 synonyms of NCIt protein-typed concepts linked by HGNC id (via encoded-by gene) or by UniProt accession;
- **B-current:** HGNC `name`, `alias_symbol` and `alias_name`;
- **B-hist:** HGNC `prev_symbol` and `prev_name`.

Only strings whose `normalize_lookup_key` is not already a runtime key for that target are kept.

## Policies (evaluated, not implemented)

Common checks:
1. No other runtime TARGET claims the key.
2. No other HGNC gene claims it in any field.
3. No NCIt protein concept mapping to a different gene claims it.
4. Not an EC identifier (`^EC\s*\d`).
5. ≤ 2 parser tokens.
6. **Name shape:** a single all-lowercase alphabetic token is refused (ordinary-word shape; structural, not a word list).

- **Policy A:** A-source strings from a concept with exactly one encoded-by HGNC gene, whose Swiss-Prot accessions (if any) are within that HGNC record's `uniprot_ids`, plus the common checks.
- **Policy B:** B-current strings plus the common checks. **B-hist** is evaluated under the same checks as a separate high-risk subgroup and is never part of a passing policy.

The policies deliberately do **not** consult the DRUG ontology or NCIt non-product names. Those are held out as independent negative tests.

## Independent negatives (labels follow from the source; no hand curation)

- **N-drug:** a candidate-universe key that is also any runtime DRUG alias (drug names, drug classes, trade names).
- **N-ncit:** a candidate-universe key that is an NCIt non-product name (measurements, procedures, findings, general terms).
- **Overlap requirement:** the union must contain ≥ 20 distinct candidate-universe keys, otherwise STOP (population too easy).
- **Regression controls** (exposed, not counted as independent): `statin`, `statin-like`, all v1 EC strings, and the v1/alias-coverage survey controls. H20 `factor XI` must remain admitted through the F11 chain.

## Independent positives

A disjoint sample of **400 runtime targets**: hash-ordered by `sha256(canonical_id)`, excluding v1's 192 entities and heldout symbols, and requiring an HGNC link. Each policy-admitted reachable alias on these 400 is labelled **SAFE_TARGET_NAME / UNSAFE** by an independent reviewer: a separate agent context that is not shown the policies, results or this document's thresholds. Its labels are frozen before verdicts are computed. Disagreements with my own spot labels are recorded, never overwritten.

## Acceptance (per policy; computed by `audit.py`, self-tested)

- S1: 0 admitted keys in N-drug ∪ N-ncit (universe-wide).
- S2: 0 reviewer-UNSAFE admissions in the 400-sample.
- S3: 0 EC strings admitted.
- S4: regression controls hold; `statin`/`statin-like` are not admitted; existing runtime behaviour is unchanged (admission only adds keys absent from runtime).
- S5: H20 `factor XI` is admitted to F11, and its injected chain compiles with TARGET:F11. Bare `F11` stays ambiguous.
- S6: the overlap requirement is met.
- S7: two builds byte-identical.
- C coverage: ≥ 10% of the 400 entities gain ≥ 1 reviewer-SAFE admitted alias.

Verdict per policy:
- **JUSTIFIED:** S1–S7 and C pass;
- **LIMITED:** S1–S7 pass but C fails;
- **STOP:** otherwise.

Overall verdict = the best policy. Only JUSTIFIED permits drafting a separate implementation contract. If neither policy passes, alias work is parked and the CT.gov posted-results availability survey is next.
