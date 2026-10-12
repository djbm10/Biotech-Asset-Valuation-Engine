# TREATMENT_COHORT_ATTRIBUTION_REPRESENTATION v1 — FAILED / REVERTED

Preregistered in `bbf52e5`; candidate `56513a2`; scorer and grounding review frozen in `a17d3af`; formal failure recorded in `97a82c0`; normal implementation revert `98ed522`. No adoption and no replacement attempt.

## Formal acceptance result

**R1 FAIL.** I froze two unsupported REGIMEN_RECEIPT labels for the prednisone and prednisolone controls. The source says “prednisone or prednisolone”; neither alternative is individually established as received by the outcome cohort. Preserving an alternative qualifier in a regimen list does not make either candidate receipt CERTIFIED. The frozen labels and emitted failed-candidate records remain unchanged as evidence. This is an error in the new receipt annotation layer, not in the adopted 33-row treatment audit.

**R7 FAIL.** The exact cross-process reader-output comparison differed on `asset_name` capitalization. The existing reader sorts a set of names by length only (`human_poc.py:389`), so equal-length case variants inherit hash-dependent iteration order. Three post-failure diagnostic processes (hash seeds 0/1/2) found 8/6/11 literal differences respectively, only in capitalization; all 98 PASS/UNKNOWN decisions were unchanged in each process. The formal failure is retained, not retrospectively rescored or fixed.

R2, R3, R4, R5, R6, R8 and R9 passed. All 65 negative records remain non-owning, but that does not excuse the two unsupported receipt labels. All 98 grounded annotations serialize and round-trip deterministically. These checks concern representation of manual annotations, not an automatic text classifier or generalization evidence.

## Candidate counts (not adopted)

| Population | RESULT_OWNERSHIP | RECEIPT | REGIMEN_RECEIPT | UNRESOLVED |
|---|---:|---:|---:|---:|
| 33 adopted witnesses | 15 | 0 | 11 | 7 |
| 65 negative controls | 0 | 13 | 15 | 37 |
| Total failed candidate | 15 | 13 | 26 | 44 |

Two of the 26 regimen-receipt labels are unsupported. These totals describe the failed artifact; they are not certified adopted relationships. The 15 ownership records merely represent previously certified manual ownership; no new human-PoC fact was emitted.

## All 14 previously unresolved clinical-content positives

| Frozen witness | Candidate | Relation | Result ownership |
|---|---|---|---|
| v1_removed_clinical:mint5:claim:5ededd17eb739d2e1106 | Venetoclax | REGIMEN_RECEIPT | UNKNOWN |
| v1_removed_clinical:AACR_accepted:claim:2ab7b26095caafbfad9b | PET30 | UNRESOLVED | UNKNOWN |
| v1_removed_clinical:AACR_accepted:claim:5ededd17eb739d2e1106 | Venetoclax | REGIMEN_RECEIPT | UNKNOWN |
| v1_removed_clinical:AACR_accepted:claim:95e146d23911c954540c | though | UNRESOLVED | UNKNOWN |
| v1_removed_clinical:H16:claim:dfa26674a43723ab9e68 | Relugolix | REGIMEN_RECEIPT | UNKNOWN |
| v1_removed_clinical:H16:claim:888e9c2c9ce421d305e4 | Glecaprevir | REGIMEN_RECEIPT | UNKNOWN |
| v1_removed_clinical:H16:claim:f93f85d51368a0574d97 | pibrentasvir | REGIMEN_RECEIPT | UNKNOWN |
| v1_removed_clinical:H16:claim:1672c26a362bce427334 | bevacizumab | REGIMEN_RECEIPT | UNKNOWN |
| v1_removed_clinical:H16:claim:e9f5d18fea7bd5531e0e | atazanavir | UNRESOLVED | UNKNOWN |
| v1_removed_clinical:H16:claim:e02f9edf1a088951bfae | ritonavir | REGIMEN_RECEIPT | UNKNOWN |
| v1_removed_clinical:H16:claim:ad115c2cb6291b6ce2e9 | Lopinavir | UNRESOLVED | UNKNOWN |
| v1_removed_clinical:H16:claim:d6109ffeff6ee4cfadca | Fosamprenavir | UNRESOLVED | UNKNOWN |
| v1_removed_clinical:H16:claim:5104ef3bd86e3a7f4e83 | Lamivudine | REGIMEN_RECEIPT | UNKNOWN |
| v1_removed_clinical:H16:claim:07de85a540078d3b5cec | Lamivudine | REGIMEN_RECEIPT | UNKNOWN |

Nine regimen-receipt records, five unresolved records, zero new certifiable asset-specific efficacy edges. All existing scientific labels remain frozen.

## Neutrality, quality and restoration

- Full candidate `tests/se`: **1,824 passed, 3 existing xfails**, exit 0. All 123 added structural representation tests passed. Ruff was clean, including archived research Python during restoration.
- Restored human-PoC/regimen test group: **87 passed**, exit 0. Baseline full suite also completed with exit 0 before the candidate; all pre-existing source/tests/scripts are restored byte-for-byte.
- **1,707 existing tracked source/test/script files** retain their baseline hashes. `git diff 7103da1 -- src tests scripts` is empty after reversion.
- **Seven original result files** retain their hashes, including their human_poc_present facts, evidence.human_poc gates, shortlist membership and ranking. No live run or replay was performed.
- **C056 remains the documented reader false positive.** Its failed-candidate representation is non-owning regimen receipt. No parser repair was made.
- H6–H10 remain **UNRUN**. H16–H20 remain exposed diagnostic/development data.

## Stop decision

**Human-PoC implementation is not ready. Stop recovery of these 14 until stronger sources or explicit structured result attribution exist.** No alternate attribution rule, identity repair or efficacy change is authorized by this result. The representation candidate itself was not adopted. Reopening it would first require a separately frozen correction of receipt expectations and an explicitly preregistered treatment of pre-existing reader serialization nondeterminism, without changing the frozen result of this attempt.

## Artifact use

`score.json` is the unchanged formal result. `scientific_grounding_review.json` (packet root) documents the two unsupported labels. `neutrality_failure_diagnosis.json` is supplemental post-failure evidence, not a rescore. `records.jsonl` and `relation_table.md` preserve all 98 unadopted records. Candidate schema/test source is archived here.

The root `materialize.py` and `evaluate.py` are historical tools for candidate commit `a17d3af`; their production model import intentionally no longer exists at the restored HEAD. They must not be wired into the engine or interpreted as an adopted resolver.
