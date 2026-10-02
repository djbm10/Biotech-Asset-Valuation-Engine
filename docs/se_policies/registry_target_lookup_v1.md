# Registry target lookup v1 (`REGISTRY_TARGET_LOOKUP`)

Status: **PREREGISTERED** 2026-09-30. This is the first milestone of the target-authority arc,
chosen from `target_authority_coverage_survey.md`. Ranking policy is **frozen**.

Written and committed **before** any code change. The rules in §2 and the acceptance criteria in
§4 are fixed here.

## 1. The gap

TAC01 top-20 rows #8–20 have an UNKNOWN target gate. The sealed corpus holds only abstracts for
them, and ChEMBL/OT have no mechanism rows. The survey found that a live CT.gov lookup by asset
name, passed through the existing `intervention_construct_targets` reader **unchanged**, resolves
5/13 correctly (4× BCMA, 1× CD19) with 0 conflicts.

## 2. The rule

> An asset with no target fact may take one from the CT.gov intervention records that name it,
> fetched by that asset's own authority-backed names and read by the existing intervention reader.

- **L1. Eligibility (fill only).** Lookup runs only for a **qualified** asset (same guard as
  human PoC) that has **no** `construct_target_set` fact after the authority and intervention
  routes. It never runs for, supersedes, or competes with stronger evidence. Eligibility does
  not depend on rank.
- **L2. Query names.** The queries are the asset's canonical name plus its **authority-backed**
  aliases (ChEMBL/OT synonyms of its resolved identity) only.
  - Never CT.gov `otherNames`, co-occurrence, or corpus-minted aliases.
  - An asset without an authority identity (CNCT19) is queried by its canonical name alone.
  - No names are hardcoded.
- **L3. Intervention admission.** An intervention in a returned study is admitted only when one
  of the L2 query names appears as whole tokens in its intervention **name**. A study found by
  a match in another field, or an intervention in that study that names another product (a
  comparator or background regimen), is not admitted.
- **L4. Reader unchanged.** Each admitted intervention goes through
  `intervention_construct_targets` exactly as it stands at the parent commit. No change to its
  cues, window, alias handling or symbol shape.
- **L5. Agreement.** Interventions that yield no target set are ignored. All non-empty sets for
  the asset must be **identical**. Any disagreement means no fact, so the gate stays UNKNOWN.
- **L6. No invented targets.** An asset with no admitted intervention, or with only empty
  readings, stays unresolved. There is no "no human target" or placeholder fact in v1.
- **L7. Bounded and deterministic.**
  - At most 25 studies per query name, taken in ascending NCT-id order.
  - Query failure or timeout means no fact for that asset, recorded as `lookup_failed`. It
    never fails open.
- **L8. Pinning.** Every request and response is sealed into a separate **lookup custody**
  (`<run>/lookup_custody`), keyed by query name. A replay given `--replay-lookup <custody>`
  reads only that custody and never touches the network. The main corpus custody is not
  modified.
- **L9. Provenance.** Each fact uses `extraction_method = "REGISTRY_TARGET_LOOKUP"` and cites the
  NCT id, the intervention name and the query name. The shortlist labels the fact with this
  basis, so it is never shown as corpus, ChEMBL or OT evidence.

## 3. Out of scope

- NCIt (the next, separate milestone).
- Sponsor pipeline acquisition.
- Any change to the intervention reader.
- Non-gene target outcomes (tabelecleucel, lifileucel).
- Adding looked-up records to asset discovery, identity, stage or human-PoC evidence: they feed
  the target fact only.
- Any ranking change.

## 4. Protocol and acceptance

Because lookup is a separate stage over a sealed main corpus, the effect can be isolated.

1. **Live lookup run.** Sealed replay of `tac01_control_a1/custody` with live lookup →
   `tac01_lookup_v1` (writes `lookup_custody`). Then the same for mint5 (`mint5_on/custody`) →
   `mint5_lookup_v1`.
2. **Pinned replay.** Rerun each with `--replay-lookup` into a new directory. The output must be
   byte-identical in shortlist and facts to step 1. This is the determinism check (L0).

Compare against `tac01_fragment_a1` / `mint5_fragment_a1`:

- **L0.** The pinned replay is identical to the live-lookup run.
- **A1. Named resolutions.** ALLO-715, anitocabtagene autoleucel, CT053 and equecabtagene
  autoleucel each gain exactly {TNFRSF17}, and their target gate becomes FAIL for TAC01
  (CD19). CNCT19 gains exactly {CD19}.
  - If a named asset does not resolve, this is reported with its cause; A1 fails only if it
    resolves **wrongly**.
  - Missing ≥3 of these 5 fails A1 as a coverage failure.
- **A2. Precision.** Every newly resolved asset→target pair in both populations is listed with
  its NCT id and intervention, and every one is checked by hand. **Zero false assertions.**
- **A3. Controls.** Every baseline `construct_target_set`, target-gate PASS and
  CONFIRMED_TARGET is unchanged (L1 guarantees this; the check verifies it). No ST6GALNAC4
  carrier reappears.
- **A4. Ranking frozen.**
  - No change to `reporting/shortlist.py` ordering or the scorer.
  - R1–R3 pass.
  - Every top-20 movement is explained by a target-gate change from a lookup fact.
  - No wrong-target programme moves up.
- **A5.** `tests/se` passes.

If L0 and A1–A5 all pass, the rule is adopted. If any fails, it is reverted with a normal revert
commit and the result is recorded here. After adoption, the remaining unresolved rows are
reassessed as input to the NCIt milestone.

## 5. Results

### 5.1 Measurement — 2026-10-01, implementation `12f2d1e`

Runs:
- live lookup: `se_runs/tac01_lookup_v1` and `mint5_lookup_v1`;
- pinned replays: `*_lookup_v1_replay`;
- custodies: `*_lookup_v1_custody`.

Scorer output is `scratchpad/lookup_eval.txt`.

- **L0 (determinism).**
  - Facts (44,934 / 26,393), claims and candidates are byte-identical between the live and
    pinned runs.
  - `shortlist.*` and `gate_evaluations` differ in the run id they embed.
- **A1 (named) — 4/5, none wrong.**
  - ALLO-715, CT053 and equecabtagene autoleucel → {TNFRSF17}. Target gate FAIL; they leave
    the TAC01 top 20.
  - CNCT19 → {CD19}, gate PASS (TAC01 #17).
  - Anitocabtagene autoleucel: no fact. Its only BCMA-stating intervention (NCT06626919) is
    named "anito-cel", which is not an authority name, so L3 refuses it as written. Not
    tuned.
- **A2 (precision) — FAIL.**
  - 86 new facts in TAC01 and 73 in mint5.
  - Most CAR-T rows are plausible: CD19, BCMA, and named dual and triple constructs whose
    intervention names spell the targets out ("CD19/CD22/BCMA CAR-T cells (BZE2204)").
  - But many are plainly false:

  | Asset | Fact | Trial | Cause |
  |---|---|---|---|
  | GB5005 | {CARTPT} | NCT06875063 "GB5005 CART" | `CART` is an alias of CARTPT (cocaine- and amphetamine-regulated transcript) |
  | ICAR19, CTA30X (+ IMPT-514 and others; 4 in TAC01, 5 in mint5) | +CARTPT | NCT03383952, NCT05015972 | same `CART` collision, beside a correct CD19 |
  | dasatinib | {ATM} | NCT01467986, NCT02596828 | description prose; dasatinib is a BCR-ABL/SRC inhibitor |
  | docetaxel | {OR2AG1} | NCT00293085 | alias collision; docetaxel is a tubulin agent |
  | pantoprazole | {EVL} | NCT00863837 | alias collision; it is a proton-pump inhibitor |
  | colchicine | {CYP3A4} | NCT04997551 | a metabolising enzyme named in the description, not the target |
  | `CCL19` (a fragment-minted "asset") | {CCL19, CD19, IL7} | NCT04833504 "CD19 CAR-T IL7 CCL19" | an armouring payload read as a target; also breaks the standing rule that keeps CCL19 out |
  | RS001 | {CD19, NT5C} | NCT06894693 | alias collision |

  Other one-off members (PRB4, SHB, AMACR, NR1H4, KRT8, OR2AG1, NRGN, WDTC1, …) follow the
  same pattern.
- **A3 (controls) — PASS.** No baseline construct set changed and no PASS or CONFIRMED_TARGET
  was lost. No ST6GALNAC4 carrier appeared.
- **A4 (ranking frozen).**
  - R1–R3 hold and the scorer is unchanged.
  - TAC01 top-20 movement: 3 rows left on lookup FAILs (ALLO-715, CT053, eque-cel), each
    correct. CNCT19 moved #20→#17. The rows that backfilled include `Fludarabine-based`
    and `R-mini-CHOP`, which are population junk, not lookup effects.
  - mint5 top-20 movement: CM336 (BCMA/CD3) and CNCT19 left on FAIL, both consistent with
    the trial.
  - Every movement is explained by a gate change, but A4 is moot given A2.
- **A5.** `tests/se` 1535 passed.

**Status: FAILED_ACCEPTANCE (A2).** The implementation is reverted with a normal revert
commit.

**Diagnosis.** The intervention reader was "proven precise" only on the population it had
always seen: CT.gov records retrieved by a target-scoped query, which are overwhelmingly
CAR-T and bispecific interventions written with an explicit attributive phrase. A lookup by
asset name sends it everything a qualified asset is registered as, including small molecules
whose descriptions are pharmacology prose ("inhibitor", "against", "blocking"). On that prose
the reader's alias resolution reproduces the defect class of `IV` and the sentence route: a
symbol-shaped token near a cue resolves to an unrelated gene (`CART`, an excipient, an
enzyme). The retrieval worked: A1 reached 4/5 and every named BCMA/CD19 answer was right. The
reader does not generalise to the wider input, and L4 forbade changing it.

Consequence for the arc: the 4 correct A1 resolutions are real, but they cannot be adopted
without a reader that refuses alias-only gene resolution. That reader is a separate
preregistration, not an amendment tuned to these failures.
