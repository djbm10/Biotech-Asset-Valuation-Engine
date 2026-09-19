# S&E engine — handoff state

**As of 2026-09-17, engine tagged `se-v1.0.0` at `8b49000`, merged to `master` (`1f880f4`)
and pushed. Work continues on `m11-identity-graph`.**

This is the "where we left off" document. It records the current state of the search &
evidence engine, what is frozen, what the next work is, and the environment facts that cost
time to rediscover. Milestone detail lives in the per-milestone reports; this file is the
index and the operating manual. **Update it after every run.**

## 0. Current directive (last updated 2026-09-19)

**ACCEPTANCE COMPLETE — the architecture loop is stopped.** The live acceptance query
(`Find clinical-stage dual CD19/BCMA therapies for autoimmune disease with human efficacy.`)
was run against live sources at `ad78e62` and recorded **PASS_WITH_COVERAGE_LIMITATIONS**.
Full entry in `docs/se_acceptance_log.md` (@`0f2c772`); artifacts in
`/home/djmann/se_runs/acceptance_20260919_live/`.

Result: query interpretation correct on all six phrases; 56 dual-target PASS with 615
single-target assets explicitly FAILed; 40 human_poc PASS, all but seven real molecules;
**0 assets clear both gates, 0 eligible**, which is the correct answer under the coverage
actually available. Live behaviour matched the sealed replay on every measured axis.

**The bottleneck is no longer identity or scientific correctness — it is source coverage.**
Seven mandatory families have no configured connector (company pipeline/presentation, company
press release, AACR, ASCO, ASH, EHA, SEC EDGAR), and CAR-T human-efficacy evidence lives in
exactly those. Every run will keep returning INCOMPLETE with 0 eligible until they exist.

Next work, in order:
1. **Source connectors** for the seven missing families. This is the only change that can
   move `eligible` off zero.
2. **Shortlist ordering** — prose words head the user-facing list because nothing is ever
   ELIGIBLE, so the review population *is* the shortlist and order is declared, not ranked.
   Presentation defect, not correctness.
3. **Disjunctive arm labels** — `CD19 or CD19-BCMA CAR-T` is read as conjunctive and passes
   the dual-target gate. The only such residual found.

Known, pre-declared limitation to *not* re-litigate: seven non-assets (`choice`, `though`,
`frontline`, `discase`, `DAS28`, `PET30`, `INDIGO`) still clear human_poc, sitting under the
5% document-frequency ceiling in `asset_qualification.py`. That ceiling was declared before
measurement and must not be fitted to these names.

## 0b. Prior directive (last updated 2026-09-16)

The zero-shot remediation loop is **stopped** — M17 satisfied the architecture stopping
condition. **Do not draw M18.** The engine is judged *scientifically credible as a
generalized v1*, with one caveat to keep beside the success: M17's 100% discovery is partly
authority-seeded and only **33.3% independently corroborated**, so the engine is not yet
fully independent of authority seeding. That is no longer the bottleneck.

The remaining problem is **product quality, not core scientific correctness**: too many junk
mentions are nominated before the downstream gates reject them.

**M18 objective — mention precision.** Reduce false-positive candidate-name extraction
before identity resolution, without reducing true drug recall or weakening any scientific
gate. Detail and acceptance criteria in §2.

**M18 progress (analysis complete, engine unchanged).** See
`docs/m18_mention_precision_findings.md`. Three things a resumer needs:

1. **The predicted failure classes are not the actual ones.** Junk is dominated by ordinary
   prose — English and *non-English* abstract text, place names, taxonomy, chemistry nouns
   — not cell lines/residues/assay constants. The shape model was trained drug-vs-biomedical
   -symbol and never saw an ordinary word, so prose is out of distribution.
2. **Document frequency runs backwards from intuition**: gold is the *most* frequent class
   (median 40), junk the least (median 1). Inverted into a minimum-corpus-support rule it is
   the strongest signal available. The prose classifier I trained only rejects 11% of M17's
   junk and is demoted to a secondary signal.
3. **Selected rule:** keep protected routes (exact ontology drug match, development-code
   shape) always; for everything else require ≥5 supporting documents, or ≥2 if drug-shaped.
   Measured: M17 −35.9%, M16R −32.1%, **zero** gold/known_molecule/trap lost.

**M18 is DONE and shipped** (`6473334` — `fc68a3d` is the pre-amend orphan, unreachable from
the branch; do not cite it). See `docs/m18_mention_precision_report.md`.
Three dispositions at the nomination boundary — `PROTECTED` / `SUPPORTED_UNKNOWN` /
`LOW_SUPPORT_UNKNOWN` — **none of which is deletion**; low support is routed to review with
full provenance via `SESearchResult.low_support_asset_ids`. All seven acceptance criteria
met: default path −43.0% (M17) and −33.8% (M16R), 0 gold demoted, 0 asserted assets demoted,
100% of gold and 100% of surfaced traps `PROTECTED`. Suite 739 passed / 2 xfailed, ruff
clean.

One fact a resumer needs: live sealed-corpus replay **cannot** isolate an engine change
(re-queries uncached gaps; an M16 replay returned 1,965 records vs M16R's 3,623), so
controlled measurement is done by applying logic to frozen result artifacts.

**M18.1 is DONE and shipped.** See `docs/m18_1_structured_drug_typing.md`. It closes M18's
known gap: a source that types an intervention `DRUG` in a structured field is now a third
`PROTECTED` route, alongside exact ontology match and development-code shape. New flag
`CanonicalAsset.structurally_typed_drug`, set in `AssetRegistry.ingest_hit` from
`CandidateHit.intervention_type`, monotonic on update and across merges; read only at the
nomination boundary. It mints no alias, asserts no target, does not bypass identity
resolution, and is never inferred from prose. Only `DRUG` counts — `COMBINATION_PRODUCT` is
excluded because sponsors give it to single agents. Measured on the sealed corpora: M17
promotes **36** candidates (default path 4,603 → 4,639), M16R promotes **6** (3,090 →
3,096), **zero** demotions (structurally impossible — typing adds a route, removes none).
Honest reading: the promoted names are mostly salt/regimen decorations and six placebo arms,
not novel assets, because no benchmark drawn contains a novel asset. Suite 747 passed / 2
xfailed, ruff clean.

**Mention-precision remediation is FROZEN here.**

**Productization step 1 (query UX) is DONE** (`b719541`). Key finding: the whole NL intake
layer — `bve.se.intent` (parser, `SearchIntent`, `compile_intent`) — already existed from M9
and **nothing outside that package imported it**. Step 1 was wiring, not building.
`bve-se-search` now takes `--query "small molecule CHRM1 programs in phase 2"` as a mutually
exclusive alternative to `--problem`, via `problem_from_args`. The interpretation is printed
per span with the rule that fired, always; a non-compilable question exits with its blockers
named and ambiguous targets list their claimants. `--emit-problem` writes the compiled YAML
back out so the run stays replayable from a file (this also serves step 7). `--as-of`,
`--buyer-name`, `--therapeutic-area`, `--indication` are the remaining knobs; TA and
indication stay caller-supplied because neither is inferable from a target. 9 tests in
`tests/se/test_search_cli_query_entry.py`. Suite 756 passed / 2 xfailed, ruff clean.

**Productization steps 1–7 are all DONE.** The build phase is over.

**Active directive (2026-09-17): real-world acceptance testing, not another milestone.**
The engine is a usable generalized v1, frozen as tag `se-v1.0.0` and merged to `master`.
The work now is to *use* it on real BD questions, log the failures users actually hit in
`docs/se_acceptance_log.md`, and reopen architecture only when a real query exposes a
defect. **Do not draw M19.** Do not build more benchmarks. Do not invent a ranking score.

Judge a run the way a BD user would: did it find the right programs, cite them, explain
them, and make its uncertainty obvious?

The known caveats are deliberately *not* being chased proactively. Prioritize one only if
it hurts real usage, in this order: HISTAMINE endogenous-ligand collision (highest
scientific-correctness risk); dose/salt/combination decoration (highest identity
annoyance); `MIN_SUPPORTED_DOCS = 5` rare-vs-contested, which matters for novel assets;
`\bAR\b` / `\bMET\b` regex false positives; §2 retitle (low priority).

First acceptance pass found and fixed two question-layer defects — `phase 1-2` silently
read as `PHASE1` alone, and plural modalities (`bispecifics`) refusing to compile at all.

**The acceptance rule now in force, and it is not negotiable.** A scientifically meaningful
phrase must be (1) compiled into an enforceable constraint, (2) reported unresolved by name,
or (3) refused. It must never fall silently into residual text while the run proceeds as
though the whole question were honoured. Applied in the second pass: `human efficacy` and
its controlled equivalents set `EvidenceFloor.human_poc_required`; `clinical-stage` sets
`EvidenceFloor.minimum_stage = "PHASE_1"` and **never** a `PhaseConstraint`; vague words
(`promising`, `effective`) set nothing on purpose; a disease *class* like `autoimmune
disease` is refused with `NEEDS_CLARIFICATION` naming the phrase, because the indication
gate tests an asset's own indication and the ontology snapshot has zero DISEASE entities.
Also fixed there: `CD19/BCMA` and `CD19xBCMA` resolved *neither* target, and the connector
`x` in `CD19 x BCMA` resolved to PSMB5 — an invented target.

See `docs/se_acceptance_log.md`, which is the live record.

## 1. Where the work stands

The architecture-remediation loop is **complete and should not be continued**. Three
consecutive mechanically drawn targets trace the arc:

| milestone | target | discovery | identification | false target assertions |
|---|---|---|---|---|
| M13 | SLC6A2 | 5/41 | 0/41 | 0 (vacuous) |
| M15 | HRH1 | 49/51 | 6/51 (11.8%) | 0 |
| M16 | HTR2A | 40/41 | 29/41 (70.7%) | 0 |
| **M17** | **CHRM1** | **21/21** | **21/21 (100%)** | **0**, 0/26 traps with 16 surfaced |

M15 exposed identification as the binding constraint; M16 showed the fix generalizing;
M17 closed it against the hardest trap set drawn (CHRM2/3/4 — sibling subtypes one
character from the target). The stopping condition set for this loop is met.

**Next work is productization, not another target draw.** A fourth draw would re-measure
the same architecture at rising cost — M17's discovery stage alone ran 76 minutes over a
15,454-record corpus.

## 2. The one subsystem to fix first

**Mention-layer precision.** It is the dominant remaining failure layer, and it degraded as
recall improved:

| class | M16 | M16R | M17 |
|---|---|---|---|
| known_molecule | 849 (39.1%) | 1,645 (35.3%) | 1,892 (23.4%) |
| development_code | 688 (31.7%) | 684 (14.7%) | 1,071 (13.3%) |
| **unknown_word (false accepts)** | **576 (26.5%)** | **2,270 (48.7%)** | **4,480 (55.5%)** |

More than half of what the engine nominates is an ordinary alphabetic token the frozen
ontology has no drug record for: chemical-class nouns (`phenols`, `quinolines`,
`xanthones`), demonyms and place names (`Afghanistan`, `Jordanian`), hyphen compounds.

It costs **zero** benchmark metrics — the identity and `CandidateTargetAssertion` gates hold,
extraction may nominate but never assert, and false target assertions stayed at 0 across
8,080 candidates. But it is why `SCORING` reports 7,966 unresolved against 114 excluded and
0 eligible, and anything downstream consuming *candidates* rather than *assertions* inherits
the noise directly.

The fix is a filtering layer at the nomination boundary. Unlike everything in the
remediation loop, **it can be evaluated without drawing a new target** — rerun
`mention_precision_audit.py` against the existing sealed results.

### M18 scope

**Prioritize filtering of:** cell lines (`HEK293`), amino-acid residue tokens (`LYS191`,
`ASN198`), assay constants/measurements (`IC50`, `EC50`), gene/protein symbols,
cytokines/receptors, generic biomedical nouns, non-drug abbreviations, malformed fragments.

**Preserve:** exact known drug/alias matches, development codes, legitimate uncommon
small-molecule names, M11 identity rules, `CandidateTargetAssertion` semantics, and all
frozen benchmark results.

**Method constraint:** generic evidence and frozen data only. **Do not tune against CHRM1,
HTR2A, HRH1, SLC6A2 or PDCD1 asset names**, and do not hand-tighten using observed
benchmark misses. Evaluate the filter independently on held-out ontology-derived
positives/negatives first, then replay the frozen M15/M16/M17 corpora where valid.

**Acceptance criteria — all required:**
- materially reduce unknown-word false accepts from M17's 55.5%
- materially reduce unresolved candidate count
- no regression in frozen benchmark discovery
- no regression in frozen benchmark identification
- no increase in false target assertions
- no increase in trap errors
- no target-specific exceptions

**Report before/after:** extracted mention count, true drug-shaped mentions, false accepts,
false rejects, unresolved assets, runtime/memory impact, benchmark invariants.

### After M18 — user-facing productization

In order: query UX; ranked/cited asset results; explanation of why each asset matched;
source provenance; unresolved/review visibility; runtime reduction and caching; packaging a
reproducible one-command search workflow.

**Step 1 (query UX) — done, `b719541`.** `bve-se-search --query "small molecule CHRM1
programs in phase 2"`, mutually exclusive with `--problem`. `bve.se.intent` had existed
unwired since M9; this was wiring, not building. **Check the remaining steps for the same
before writing anything.**

**Steps 2 and 3 (ranked/cited results, why-matched) — done, collapsed into one
implementation.** See `docs/productization_step2_ranked_cited_results.md`.
`src/bve/se/reporting/shortlist.py`; `--format shortlist` / `shortlist-json`, `--top`,
`--detail`. Three things a resumer must not undo:

1. **The display order is not a score and says so.** The real pairwise ranker
   (`rank_profiles`) produces *zero* entries in a discovery run — it needs comparative
   clinical profiles a landscape run never builds. The shortlist defers to it when populated
   and otherwise uses a declared order (section → `TargetAssertionStatus` precedence →
   document count → mention count → name → asset id). Do not replace this with a weighted
   score; that would be a second, unvalidated ranking model wearing the real one's clothes.
2. **No real run has an eligible candidate.** M17: 0 eligible, 114 excluded, 7,966
   unresolved — every candidate has at least one UNKNOWN gate. The shortlist therefore shows
   the review population, labelled, and says why in a note.
3. **Modality, phase and company are not asset properties** and are rendered with their
   origin: `modality_id` comes from the discovery context text, `development_stage` is null
   for ~99% of candidates, `company_ids` is populated for <1%. A fact with no evidence shows
   as `unresolved`, never as a blank.

**Phase intent — fixed as a gate.** See `docs/productization_phase_intent_gate.md`.
`PhaseConstraint` (EXACT / ANY_OF / MINIMUM) on `StrategicGap`, compiled from
`SearchIntent.phases` + `phase_operator`, decided by `GateEngine` as requirement
`evidence.phase_constraint` over `development_stage_order` facts. Four things not to undo:

1. **Bare `phase 2` is EXACT, not `minimum_stage`.** Mapping it onto the evidence floor would
   admit every Phase 3 asset into a Phase 2 search. `minimum_stage` is untouched.
2. **Unknown phase is UNKNOWN, never FAIL** — absent or conflicting stage evidence routes to
   review, like every other gate.
3. **Only asset-specific `development_stage_order` facts reach the gate.** Discovery-context
   text naming a phase cannot satisfy it.
4. **`phase_constraint` defaults to `None`**, so pre-existing BuyerProblems gate identically
   and benchmark runs without phase intent are unchanged.

The parser gained the MINIMUM vocabulary it never had ("at least", "or later", "+", …); the
cue text is consumed with the phase span so it cannot fall through as a free-text indication.
`tests/se/test_phase_intent_gate.py` (18 tests).

**Steps 4 and 5 (source provenance, review visibility) — done.** See
`docs/productization_step4_source_visibility.md`. Step 5 was already carried by the shortlist
(labelled sections, `review_reasons`, a held-back low-support block, whole-run counts); the
real gap was step 4 at the *run* level. `Shortlist` now carries `run_status`, `sources`
(`SourceCoverage` per family), `blind_spots`, `incomplete_reasons`, `fatal_reasons` and
`documents_by_publisher`, and `render_shortlist` states them **before the assets**. Three
things not to undo:

1. **`NOT_CONFIGURED` is never merged into `FAILED`.** A declared blind spot is a scope
   decision; a failed source is a hole in the corpus.
2. **`SourceCoverage.documents` is always `None`.** `SourceDocument` has a `publisher` and no
   source-family field, and no attempt→document mapping is recorded, so documents are counted
   by publisher. Do not invent the mapping to fill the field in.
3. **Fatal reasons render as a loud `!! UNSCOREABLE` line; incomplete reasons do not.** A run
   short of a waived source is not the same claim as a run that lost one it depends on.

`tests/se/test_shortlist_source_visibility.py` (9 tests).

Other open items, unchanged: endogenous-ligand collision (HISTAMINE), dose/salt/combination
decoration, `MIN_SUPPORTED_DOCS = 5` conflating contested with rare, and the rule-6
`\bAR\b`/`\bMET\b` English-word false-positive mode.

## 3. What is frozen and must not be touched

- **M13** stays at 5/41 discovery, 0/41 identification. Never rewrite.
- **M16** stays at the published 29/41 identification. The corrected-harness reading
  (30/41) is reported *alongside*, never substituted.
- **M15** unchanged; **M15L** published 41/51, corrected reading 42/51.
- Benchmark rules are never changed after observing results.
- Sealed corpora are never mutated. The 5 PDCD1 identification misses are not hand-solved;
  Lambrolizumab stays separate from Pembrolizumab.
- The drug-name-shape model, its features and its threshold (0.2498) are frozen. Any future
  recall gap gets a new *mechanically derived* route — never a lowered threshold, never a
  hand-added suffix.
- The ≥40-molecule stem threshold stays at 40.

## 4. Reports and artifacts

Reports in `docs/`: `m13_zero_shot_generalization_report.md`,
`m14_slc6a2_remediation_report.md`, `m15_hrh1_zero_shot_report.md`,
`m15l_hrh1_remediation_report.md`, `m16_htr2a_zero_shot_report.md`,
`m17_chrm1_zero_shot_report.md`, `m18_mention_precision_findings.md`,
`m18_mention_precision_report.md`, `m18_1_structured_drug_typing.md`.

Commit lineage for the identity work: `e0743eb` (M16 report) → `e689936` (canonical identity
contract) → `aeea608` (drug-name-shape route) → `f57f4bc` (M17 report) → `6473334` (M18
dispositions) → `09ef747` (handoff) → `ffeaaa7` (M18.1 structured DRUG typing) → `b719541`
(productization step 1, `--query`) → `e310723` (handoff) → `8e4aeed` (cold-start handoff) → `f98e3a2` (productization steps 2+3, asset shortlist) -> `69712d5` (handoff) -> `bab008d` (phase intent compiled into the gate) -> `157fb52` (handoff) -> `e12de03` (shortlist source provenance) -> `8fdc4c8` (handoff) -> `4d61880` (productization
steps 6+7: snapshot cache, `--output-dir` one-command workflow) -> `8b49000` (handoff,
**tagged `se-v1.0.0`**) -> first acceptance fixes. All pushed to
`origin/m11-identity-graph`; `se-v1.0.0` merged into `origin/master` as `1f880f4`.

M18/M18.1 measurement scripts, in staging: `m18_dump_candidates.py`,
`m18_train_prose_discriminator.py`, `m18_eval_filter.py`, `m18_controlled_eval.py`,
`m181_typed_drug_eval.py` (re-derives the typing flag from sealed CT.gov snapshots,
read-only). Outputs `M18_controlled_M17.json`, `M18_controlled_M16R.json`,
`M181_typed_M17.json`, `M181_typed_M16R.json`.

Run artifacts live in **`/home/djmann/staging/pdcd1_baseline`**, which is outside the repo
and untracked by git. M17 artifacts: `M17_result.json` (419 MB), `M17_score.json`
(sha256 `70a17735…`), `M17_mention_audit.json` (sha256 `3468f12b…`), `M17_custody/`,
`M17_alias_probes.json`, `M17_run.log`, `m17_benchmark_v1.json` (sha256 `03876755…`),
`m17_chrm1_problem.yaml`, `m17_pool_rules.json`, plus `score_m17.sh` and `run_m17.sh`.

## 5. Environment facts that cost time to rediscover

- **Worktree is `/home/djmann/projects/bve-b8`.** The shell's default working directory is
  `/home/djmann/projects/biotech-asset-valuation-engine`, a *different* worktree, and the
  Bash tool resets cwd between calls. Always `cd` or use absolute paths.
- Every command needs `PYTHONPATH=/home/djmann/projects/bve-b8/src` (editable-install
  contamination) and
  `BVE_SE_ONTOLOGY_SNAPSHOT=/home/djmann/projects/bve-b8/data/se/ontology/current` — the
  default is CWD-relative and **fails open** to `no_snapshot` rather than erroring.
- **Exit code 2 = `RunStatus.INCOMPLETE`** and is the expected diagnostic state for a
  discovery-only run. Exit 3 is fatal. A missing output file is the real failure signal.
- `score_zero_shot.score()` arguments must be `pathlib.Path`, not `str`.
- **scikit-learn is not installed.** The shape model is pure-Python naive Bayes by necessity.
- Ontology snapshot `chembl_ChEMBL_37__open_targets_26.06__resolver_v2__modality_v2`:
  84,560 TARGET + 71,506 DRUG entities. TARGET records have no `canonical_id`/`name`;
  `aliases` is a list of `{"alias_type","value"}` dicts.
- Machine has 10 GB RAM. **The system reaps background tasks under memory pressure** — five
  watchers were killed during M17 even one that slept 60s between checks. The primary
  scientific process survived each time and must never be killed for a watcher's
  convenience. Wait in the **foreground** instead (a `for`-loop with `sleep`, 10-minute tool
  timeout, repeated); foreground calls are not reaped.
- `pgrep -f "<string in your own command>"` self-matches.
- Multi-line Bash commands are flattened — use a heredoc or a script file.
- Large JSON dumps printed to the shell get elided/mangled. **Always verify counts
  programmatically**; a list that displayed as 14 items was actually 40.

## 6. Security constraints in force

- Credential at `~/.config/bve/env`, sourced before any live acquisition. Never print or
  persist the value; verify only that `BVE_SE_USER_AGENT` is present and its SHA-256 matches
  `456da4da5c35d281066d62aacc673f13a17a5499de717bbb41fd5149a9dead58`. Record only
  `user_agent_contact_present = true` / `user_agent_sha256 = …`.
- Never commit: operator email, credentials, secrets, or large artifacts that belong in
  staging rather than git.
- The operator's own email identifies the operator only and must never be sent to an
  unrelated service — not in a header, URL, or payload. It is not an acquisition header.
- Not permitted: spoofing browser identity, bypassing anti-bot systems, circumventing
  authentication or paywalls, fabricating headers or provenance, scraping around access
  controls, or initiating paid/account actions without authorization.
- No ASCO/AACR/ASH licences are to be requested or paid.

**HARD STOP conditions** (only these): a required paid purchase/licence/DUA/login/CAPTCHA;
a missing required credential; anything requiring bypass of an access control; anything
requiring fabricated provenance; changing frozen benchmark rules after seeing outcomes;
mutating a sealed artifact; two defensible scientific choices that would materially change
benchmark meaning; a source that changed fundamentally; a destructive system action.

## 7. If picking this up cold

1. Read `docs/m17_chrm1_zero_shot_report.md` — it carries the current result and the
   route-confound and corroboration caveats that belong beside it.
2. **Do not draw another benchmark target.** The remediation loop is stopped, mention
   precision is frozen at M18.1, and the build phase ended at `se-v1.0.0`. The current
   milestone is real-world acceptance testing: use the tool, and log what a real question
   breaks in `docs/se_acceptance_log.md`. That log — not a new benchmark — is what reopens
   architecture.
3. Phase intent is now a real gate (`docs/productization_phase_intent_gate.md`); the query in
   the smoke command below therefore *changes dispositions*, and an asset whose trials span
   more than one phase is UNKNOWN (review), not a match. Drop "in phase 2" if you want the
   unconstrained landscape.
4. **The productization checklist (steps 1–7) is complete.** See
   `docs/productization_step4_source_visibility.md` (steps 4/5) and
   `docs/productization_steps6_7_workflow.md` (steps 6/7). Three things not to undo:
   - **`LIVE_CONVERGED` means the seed queries were re-issued to the live source and
     produced zero growth.** Discovery is 92% of a run and the only within-run repeat work
     (154 of 1,419 attempts, 10.9%) *is* that proof. Do not relax
     `test_orchestrator_converges_after_two_complete_zero_growth_passes` to accept cache
     hits. A fast path may only ever exist as a separately labelled mode (e.g.
     `LOCAL_FIXPOINT`) that reports its own status and is never scored as live convergence.
   - The one optimization taken is `bve/se/evidence/snapshot_cache.py`: extraction parsed
     each sealed snapshot once per *hit* (~3.6 hits per record). Keyed on
     `(path, size, mtime_ns)`, output-equivalence pinned. The returned objects are shared
     and must not be mutated.
   - `--output-dir` defaults every artifact path but **never overrides an explicit flag**,
     and writes the artifacts *before* the fail-closed exits so a failed run is readable.
   Do **not** invent a ranking
   score merely because a user-facing shortlist exists. Before building anything on that list, *check
   whether it already exists unwired*: step 1 was pure wiring because `bve.se.intent` had
   been complete since M9 with zero importers, and `SourceEvidenceClaim` is still a complete
   contract with no producers.
5. Sanity-check the engine runs end to end before changing it:

```bash
cd /home/djmann/projects/bve-b8
PYTHONPATH=src BVE_SE_ONTOLOGY_SNAPSHOT=data/se/ontology/current \
  python -m bve.cli.se_search --query "small molecule CHRM1 programs in phase 2" \
  --as-of 2026-09-16 --emit-problem /tmp/p.yaml --offline --allow-incomplete
```

   For the productized one-command form — every artifact, the summary, and the command to
   reproduce it, in one directory:

```bash
PYTHONPATH=src BVE_SE_ONTOLOGY_SNAPSHOT=data/se/ontology/current \
  python -m bve.cli.se_search --query "small molecule CHRM1 programs in phase 2" \
  --as-of 2026-09-16 --offline --allow-incomplete --output-dir /tmp/run1
```

   It should print the per-span interpretation to stderr, write the compiled problem, and
   exit 0 (or 2 = `INCOMPLETE`, which is diagnostic, not failure). Add
   `--format shortlist --top 5` to see the reader's view; `--detail` expands every citation.

   The shortlist can also be rendered from a sealed artifact without re-running anything:

```python
from bve.se.pipeline import SESearchResult
from bve.se.reporting.shortlist import build_shortlist, render_shortlist
result = SESearchResult.model_validate_json(open("M17_result.json").read())
print(render_shortlist(build_shortlist(result, limit=5)))
```

6. Test/lint commands for this worktree:

```bash
cd /home/djmann/projects/bve-b8
PYTHONPATH=src BVE_SE_ONTOLOGY_SNAPSHOT=data/se/ontology/current python -m pytest tests/se -q
ruff check src/bve/ tests/se/
```

   Current baseline: **856 passed, 2 xfailed**, ruff clean, on
   `m11-identity-graph`, pushed. Worktree clean apart from untracked `data/` (the ontology
   snapshot — large, deliberately not committed).

6. Commit a git message with `-F` and a quoted heredoc, never `-m`: backticks in a message
   trigger shell command substitution and have silently mangled a commit here before.
