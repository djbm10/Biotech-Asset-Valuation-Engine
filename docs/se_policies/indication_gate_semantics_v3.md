# INDICATION_GATE_SEMANTICS v3

Status: PREREGISTERED before implementation, 2026-10-11. Baseline ff2a69b; audit ff2a69b.
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

research/se_indication_gate_semantics_v3/manifest.json seals population and authority.
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

- V3-G1: zero indication FAIL across every scored frozen registry-only asset.
- V3-G2: all 33 historically indication-only excluded references become PASS or UNKNOWN.
- V3-G3: every exact/synonym positive control PASS.
- V3-G4: observed descendant/broad request PASS; parent-only/narrow request UNKNOWN.
- V3-G5: both multi-indication permutations PASS; other records cannot override a match.
- V3-G6: every frozen UNKNOWN control UNKNOWN, including unresolved identical strings,
  missing evidence, incomplete Finding typing, different diseases and negated spans.
- V3-G7: manually review first five distinct newly PASS witness conditions per run,
  lexicographically sorted by requested/condition/fact ID, plus all newly PASS reference
  witnesses. Every selected PASS must have cited positive compatibility; zero unsupported.
  Record complete new PASS counts and witness inventory for further inspection.
- V3-G8: all prior TAC01 PASS remain PASS, JCAR014 PASS; mint5 all decisions,
  dispositions and shortlist membership/order unchanged. Unsupported TAC01 FAIL may
  become UNKNOWN and is explicitly reported; membership/order changes reported only.
- V3-G9: all existing source outside engine/evaluator unchanged, all intent source hashes
  frozen, all 103 compilation controls exact, all non-indication data/decisions unchanged.
- V3-G10: targeted tests, full PYTHONPATH=src python3 -m pytest tests/se -q
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

## Authority-aware oracle and implementation lock

Independent preimplementation audit: authority_audit.json proves every positive
control via exact unique NCIt identities, explicit directed parent edges, or the
previously adopted B-cell controlled positive rule. Freeze all 28 controls: 9 PASS,
19 UNKNOWN. Only the prior psoriasis_synonym oracle changes, to UNKNOWN because
the pinned authority has no alias. V2 is permanently failed; no historical result
or population is rewritten. Audit narrative count typo corrected here to match JSON.

Use exactly the v2 production implementation from 148b71e in engine.py, evaluator.py,
and indication_compatibility.py. No special psoriasis handling, added synonyms,
authority expansion, ranking change, threshold change or negative-evidence contract.
Test/scorer names and population references become v3. All evaluation and witness
review is run afresh; no reuse of v2 scores or quality logs as v3 evidence.
V3-G3 also requires every PASS oracle to have the frozen audited authority proof.
V3-G9 additionally checks production byte identity with those three v2 source files,
all historical experiment hashes, all frozen compilation sources and 103 query outputs.

After adoption, project the eight frozen result copies with the unchanged shortlist
builder. Report reference visibility, indication-only exclusions, full membership and
top-20 order transitions. For diagnostic row labels use only existing blinded labels
and reference identity evidence. New rows without frozen labels remain UNLABELED;
do not manufacture point precision. Report counts of unlabelled rows and precision
bounds where needed. This readout is descriptive and cannot alter acceptance or code.
Holdouts remain untouched even after adoption; stop and report readiness only.
