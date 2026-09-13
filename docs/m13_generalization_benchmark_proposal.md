# M13 — a zero-shot generalization benchmark

**Status: proposal. Requires one decision from the operator, and deliberately does not make it.**

## The question M13 exists to answer

Is this a generalized biotech discovery and evaluation engine, or a system that has been fitted
to PDCD1 over eight milestones?

Nothing in M8–M12 can answer that. Every threshold, every identity rule, every query-plan
heuristic was written by someone who could see PDCD1 scores. The M12 combined result — floor
held, identity graph preserved edge for edge, +541 assets — is a real result about *robustness
under source expansion*, and says nothing about transfer to a target the system has never seen.

## The one rule that makes M13 mean anything

**The target must be chosen by a party who does not know how the engine behaves, and it must be
chosen before any code is run against it.**

This is not procedural fussiness. If I propose a target now, I am choosing after seeing that the
engine handles a well-annotated, heavily-published, monoclonal-antibody immuno-oncology target
with hundreds of trials and a dense alias graph. Any target I named would be shaded by that,
consciously or not, and the zero-shot property — the entire point of M13 — would be gone before
the first query. So this document specifies *rules and a procedure*, not a target.

This is the single decision the operator must make. Everything else below is executable without
further input.

## Selection rules

The target/mechanism must satisfy all of the following. The rules are stated so that many
candidates qualify and so that satisfying them can be checked mechanically, by someone who has
not run the engine.

1. **Not PDCD1, and not in PDCD1's pathway.** Excludes PDCD1, CD274/PDCD1LG2, CTLA4, LAG3,
   TIGIT, HAVCR2 — anything that shares the checkpoint-blockade literature and would let
   PDCD1-era tuning transfer through shared vocabulary.
2. **A different modality class.** M8–M12 were dominated by monoclonal antibodies. M13 should
   centre on something structurally different — small molecule, degrader, ADC, cell therapy,
   oligonucleotide, radioligand. Naming rule 2 is not naming a target; many hundreds qualify.
3. **A different therapeutic area if possible.** Oncology-only performance is a weaker claim
   than cross-TA performance.
4. **Enough public evidence to be scoreable.** A rough floor of ≥25 distinct clinical-stage
   assets with a defensible target attribution as of the as-of date. Below that the denominator
   is too small for the misses to mean anything.
5. **Reachable by the already-frozen source families.** No new acquisition work in M13. If a
   target needs a source family M12 could not configure, it is out of scope — otherwise M13
   measures acquisition, not generalization.
6. **No prior contact.** The target must not appear as a worked example, test fixture, seed, or
   tuning case anywhere in the repo or staging. Rule 6 is verified mechanically in step 2 below,
   and a candidate that fails it is discarded, not patched.

## Arms-length selection procedure

1. **The operator picks**, or names a disinterested third party to pick, from targets satisfying
   the rules. Alternatively: the operator supplies a list of ≥5 qualifying targets and a random
   seed, and the target is drawn mechanically from the list. The draw is recorded before any
   run.
2. **I verify the choice mechanically and publicly** — grep the repo, staging, ontology snapshot
   and all frozen benchmark files for the chosen symbol and its aliases, and record the result.
   This checks rule 6 and rule 4 (asset count) without giving me a veto: if the check fails, the
   operator draws again from the same list.
3. **Freeze the benchmark before running anything.** Gold set, denominators, as-of date, trap
   set, scoring script — all sealed and hashed *before* the first query. This is the M8/V2
   discipline, and in M13 it carries much more weight, because the temptation to adjust a
   denominator after seeing a bad score is exactly what a generalization test must exclude.
4. **Run once. Report the first number.** Not the best of several configurations.

## What M13 measures

The same four floor metrics as M11/M12, recomputed against the new target's own denominators:
discovery, identification, false assertions against confirmed negatives, and same-pathway traps
falsely asserted. Plus the identity result, which is the one that transfers least obviously:
does the M11 evidence model hold when the alias landscape is not the one it was written against?

Reported alongside, not instead: the M12 PDCD1 numbers, unchanged and not re-run for
improvement.

## Predicted failure modes, written down in advance

Recording these now is itself part of the method — a prediction made before the run is evidence;
the same claim made after is a rationalization.

- **Ontology coverage.** The snapshot is `chembl_ChEMBL_37__open_targets_26.06`. A target with
  thinner ChEMBL/Open Targets coverage will lose identification recall for reasons that are
  about the snapshot, not the engine. Must be measured and attributed separately, as the B6
  attrition work did.
- **Query-plan shape.** The plan was written watching PDCD1 retrieval. A target whose literature
  is organised differently — by indication rather than mechanism, say — may retrieve worse.
- **Nomenclature density.** PDCD1 assets carry rich code-name/INN/brand alias chains. A target
  with sparser naming gives the identity model less to work with in both directions.
- **Trap-set asymmetry.** PDCD1's traps (PD-L1) are unusually well-defined. Constructing a
  comparably sharp trap set for another target may be harder, and a weak trap set makes the
  false-assertion metric easier to pass. State the trap set's strength explicitly.

**A low M13 score is a valid and publishable result.** It would mean the engine is PDCD1-fitted,
which is worth knowing and is precisely what this milestone is for. The failure mode to guard
against is not a bad number — it is tuning until the number is good and then calling it
zero-shot.

## Explicitly out of scope

- Further PDCD1 optimization. M12 closed it. The five identification misses stay unsolved.
- New source acquisition, paid licences, or credentialed access.
- Any change to M8/V1/V2/M11/M12 frozen rules or artifacts.
- Choosing the target myself.

## Provenance

M12 closure: `docs/pdcd1_m12_source_expansion_report.md`, and
`/home/djmann/staging/pdcd1_baseline/M12_HANDOFF.md` for the operational handoff.
