# INDICATION_GATE_SEMANTICS v2

Status: PREREGISTERED before implementation, 2026-10-11. Baseline 4cf8485.
The diagnosis remains authoritative. User explicitly defers negative evidence/FAIL.

## Hypothesis and exact rule

Closed-world comparison of partial trial conditions manufactures unsupported asset
negatives. Route every strategy.indication requirement to the indication evaluator.
Under today's contract the only outcomes are PASS and UNKNOWN; no new negative contract.
Preserve missing/conflicting/stale evidence guards and non-indication evaluators.

For literal indications, normalize punctuation/case to whole alphanumeric words, then
resolve exactly one NCIt Disease-or-Syndrome/Neoplastic-Process ID using the frozen
release 26.08e graph from the failed-v1 immutable artifact. Accept unique identity,
authority synonym (same ID), or an explicit parent-chain path from observed ID to
requested ID. No substring, word-overlap, fuzzy matching, or absent-path disjointness.
No positive conclusion from ambiguous aliases, missing disease typing, unsupported
values, or unresolved/negated requests. Observed parent does not satisfy narrow request.
No normalization trimming or query compilation change. Explicit NCIt IDs may resolve
only if their nodes exist in that frozen disease graph.

Preserve the previously adopted controlled B_CELL_LYMPHOMA MATCH vocabulary as a
positive-only compatibility rule, including accepted NOS/JCAR014 evidence. NO and
UNDETERMINED both become UNKNOWN. Existing grammatical-negation role detection may
guard legacy positive evidence; no full negative-query semantics is invented.
Any one compatible record is sufficient after existing conflict/staleness guards.
Attach supporting fact/claim IDs and explain the requested/observed IDs and authority
path or legacy rule. UNKNOWN explains insufficiency; FAIL reserved for a future contract.

## Frozen population and measurement

research/se_indication_gate_semantics_v2/manifest.json seals population and authority.
All eight existing frozen runs are scored offline, with input hashes verified; no
acquisition/replay. Includes 38 references, all 655 historical diagnostic indication-only
exclusions, full TAC01/mint5 gate populations, original 16 controls with unsupported
negative expectations explicitly changed to UNKNOWN, and 12 additional controls.
JCAR014 explicit NOS regression retained. Compilation-v3's 103 controls remain frozen.

Replace only indication decisions in copies of frozen results, derive dispositions
using the unchanged FAIL/UNKNOWN/ELIGIBLE precedence, and project using the unchanged
shortlist builder. All other facts/decisions/source/ranking are checked byte-for-byte.
No top-20 success threshold and no tuning from diagnostic scores.

## Acceptance (all together; zero tolerance)

- V2-G1: zero indication FAIL across every scored frozen registry-only asset.
- V2-G2: all 33 historically indication-only excluded references become PASS or UNKNOWN.
- V2-G3: every exact/synonym positive control PASS.
- V2-G4: observed descendant/broad request PASS; parent-only/narrow request UNKNOWN.
- V2-G5: both multi-indication permutations PASS; other records cannot override a match.
- V2-G6: every frozen UNKNOWN control UNKNOWN, including unresolved identical strings,
  missing evidence, incomplete Finding typing, different diseases and negated spans.
- V2-G7: manually review first five distinct newly PASS witness conditions per run,
  lexicographically sorted by requested/condition/fact ID, plus all newly PASS reference
  witnesses. Every selected PASS must have cited positive compatibility; zero unsupported.
  Record complete new PASS counts and witness inventory for further inspection.
- V2-G8: all prior TAC01 PASS remain PASS, JCAR014 PASS; mint5 all decisions,
  dispositions and shortlist membership/order unchanged. Unsupported TAC01 FAIL may
  become UNKNOWN and is explicitly reported; membership/order changes reported only.
- V2-G9: all existing source outside engine/evaluator unchanged, all intent source hashes
  frozen, all 103 compilation controls exact, all non-indication data/decisions unchanged.
- V2-G10: targeted tests, full PYTHONPATH=src python3 -m pytest tests/se -q
  (all non-xfails pass), and ruff check src/ clean.

Test maintenance: existing gate expectations asserting unrelated conditions FAIL are
superseded by this explicit contract. Compilation-v3's historical gate/source-isolation
assertions are checked against its recorded acceptance artifact (not rewritten), while
live compiler controls and source hashes remain enforced. Historical scorer/artifacts
are never modified. This prevents a later authorized gate change from retroactively
invalidating a compilation-only experiment.

## Stop/revert and deferred scope

Commit preregistration first; implement one gate root cause. Run all criteria together.
Any failure: record, commit, normal git revert of implementation, no post-score patches.
All pass: adopt, record diagnostic readout, handoff and stop before H16–H20.
No compiler, target, identity, qualification, modality, efficacy, ranking/routing or
acquisition changes. H16–H20 untouched and H6–H10 unrun.
Deferred INDICATION_NEGATIVE_EVIDENCE_CONTRACT v1 must define asset identity, indication,
negative relation, claim/source authority, provenance, review/confidence and contradictions
before indication FAIL can be reconsidered. No part of it is implemented here.

## Result — FAILED_ACCEPTANCE (2026-10-11)

Preregistration 43c7cc5; implementation 148b71e. V2-G3 and V2-G10 FAIL;
V2-G1/G2/G4/G5/G6/G7/G8/G9 PASS. Frozen 28 controls: 27 correct, one failed.
The psoriasis_synonym control expected PASS for Psoriasis Vulgaris, but that surface
has no disease alias in the selected NCIt authority; the implementation returns UNKNOWN.
The positive-control authority premise was not verified before freezing. This is a
preregistration/authority-coverage failure, not permission to invent an alias afterward.
No behavior patch or acceptance change was made after results.

Targeted: 85 passed / 1 failed. Full suite failure and collection counts are recorded
in research/se_indication_gate_semantics_v2/acceptance.json and tests_se.log. Ruff clean.
Manual review: 124 witness records, 20 distinct pairs, zero unsupported positive claims.
Failed-attempt references: 18 PASS / 20 UNKNOWN / 0 FAIL; 33 previous exclusions free
of other FAIL gates. Historical diagnostic indication-only exclusions 655 -> 0.
These are failed-development measurements, not adopted behavior or generalization.
TAC01 preserves all 157 baseline PASS; 324 unsupported FAIL become UNKNOWN; no new PASS.
mint5 indication gate absent and unchanged; JCAR014 control PASS. No ranking tuning.

Normal git revert is required and recorded in the handoff. After reversion there is
no durable diagnostic improvement; baseline remains 0 PASS / 5 UNKNOWN / 33 FAIL,
655 indication-only diagnostic exclusions, historical 5/38 visible references,
57 TARGET_UNKNOWN_FILL, 40 NON_PRODUCT_GENERATION plus one QUALIFICATION_MISS, and
four duplicate top-20 rows. No post-adoption readout applies to a failed milestone.
H16-H20 remain untouched; the indication stack is NOT finalized for primary validation.
Next: independently verify authority coverage for every positive control, then NEW
preregistration. Preserve UNKNOWN for unsupported names. Negative evidence contract deferred.
