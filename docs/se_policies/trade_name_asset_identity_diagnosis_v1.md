# TRADE_NAME_ASSET_IDENTITY_DIAGNOSIS v1 — preregistration

Diagnosis only. No production change. `_IDENTIFIER_ALIAS_TYPES` stays {APPROVED_NAME, DEVELOPMENT_CODE}. The H19 NK-construct duplicate is out of scope (no construct-identity bridge). Modality, qualification, ESG401, target-component and human-PoC work stay parked. H21–H25 are not inspected, H6–H10 are not run, and nothing is acquired live.

## Identity levels

Alias string → authority canonical drug → active ingredient → marketed product/formulation → development program → shortlist display group. The authority (ChEMBL_37 + Open Targets 26.06) files trade names on the **molecule** record: biosimilar brands share the originator's record, and some canonicals are antigen classes spanning distinct vaccines. So an authority TRADE_NAME edge can at most support **molecule-level display grouping that keeps product names as distinct members**. It can never support product or program identity.

## Population (frozen)

- **Exposed development cases** (not used for acceptance): H18 Saxenda, Victoza, Ozempic, Wegovy, Rybelsus; H19 TRODELVY.
- **Independent population:** every candidate name in the non-holdout development runs tac01_protoid_v1, mint5_protoid_v1 and aacr_safety that RESOLVES to a DRUG only through TRADE_NAME (not APPROVED_NAME or DEVELOPMENT_CODE). That yields **70 distinct (name, canonical) pairs** (`population_listing.txt`); `trodelvy` is excluded as exposed, leaving 69 for acceptance.
- `labels.json` (blind, before measurement): 38 independent EQUIVALENT_SINGLE_MOLECULE_BRAND, 2 BIOSIMILAR, 4 AUTHORITY_TOO_COARSE (HPV ×2, RSV, COVID spike), 25 NOT_EQUIVALENT (ordinary words, company names, class words).

## Candidate contracts (evaluated, not implemented)

- **T0:** single-claimant TRADE_NAME (`claimants_of == 1`) → molecule display group.
- **T1:** T0 **and** source corroboration: at least one source document supporting the trade-name candidate contains the canonical drug's authority APPROVED_NAME (word-bounded, case-insensitive) in the same document. This is a source-backed bridge with no target, ranking or text-similarity input.

## Measured per pair

Claimant count; alias sources; whether the canonical's approved name co-occurs in the candidate's own source documents (T1); and whether a **would-merge partner** exists, meaning another candidate in the same run that `resolve_identifier`s to the same canonical.

## Readiness (computed by `audit.py`, self-tested; the first failure is reported)

- S1 safety: the contract certifies **0** NOT_EQUIVALENT or AUTHORITY_TOO_COARSE pairs.
- S2 product distinction: BIOSIMILAR pairs may be grouped only if the contract also emits a product-level relation. No such relation exists in `IdentityRelationship` today, so any certified BIOSIMILAR pair fails S2.
- S3 coverage: the contract certifies ≥ 80% of independent EQUIVALENT pairs.
- S4 provenance: every certification carries canonical id, alias type, alias sources and record keys, plus (T1) the corroborating document id.

JUSTIFIED iff some contract passes S1–S4. Otherwise STOP. The reduction in duplicate shortlist rows is reported as an estimate only (exposed cases and dev would-merge pairs).
