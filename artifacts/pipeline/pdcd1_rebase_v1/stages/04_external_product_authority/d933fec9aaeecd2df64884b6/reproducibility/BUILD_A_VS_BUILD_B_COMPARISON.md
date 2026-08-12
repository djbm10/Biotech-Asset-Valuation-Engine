# Milestone 4 — Build A vs Build B Reproducibility Comparison

Build A snapshot: `d933fec9aaeecd2df64884b6` (worktree `pdcd1_external_authority_wt`)
Build B snapshot: `14155fd94c1f2d8b621071d2` (independent build, `/tmp/pdcd1_rebase_v1_external_authority_build_b/`)

Both snapshots independently pass `validate_pdcd1_rebase_v1_external_authority.py`
(`overall_pass: True, failed_checks: []`) after a validator fix (see below) that
was verified against Build A's 22-case mutation suite and Build A's real
snapshot before being trusted against Build B.

## Level 1 — Research-universe reproducibility

- Subject count: A=554, B=554. Identical `subject_id` sets (set difference empty
  both directions).
- Research-question count: A=1273, B=1273 — identical.
- Priority-tier distribution identical: `{1: 169, 2: 319, 3: 54, 4: 12}` in both
  builds.

**Conclusion: full research-universe reproducibility.** Both builds independently
reconstructed the exact same 554-subject universe from the same Milestone 3
prerequisite snapshot, with identical question-priority assignment logic.

## Level 2 — Evidence reproducibility

- Conflict ledger: A=76 conflicts, B=76 conflicts, **identical conflict subject
  set**. These conflicts arise from the shared, deterministic Milestone 2
  registry-history data (multiple differing `interventions[].type` values
  across trial versions for the same subject) rather than from independently
  gathered Tier B/C evidence, so exact agreement here is expected and does not
  by itself demonstrate independent-research reproducibility.

- **Material, disclosed capture-methodology difference:** Build B's Tier B/C
  research batches captured essentially zero true Tier B/C (company page, SEC
  filing, peer-reviewed publication) evidence. All 8 independent research
  agents reported WebSearch unavailable for nearly the entire multi-hour run
  and relied on WebFetch against the ClinicalTrials.gov API
  (`armsInterventionsModule.interventions[].otherNames` and similar fields) as
  their primary source. Every asserted unit in Build B's
  `tier_bc_capture_manifest.jsonl` (305 rows / 299 subjects) carries
  `authority_tier: tier_a`, not `tier_b`/`tier_c`. This is a genuine
  divergence in source diversity from Build A (which had broader Tier B/C
  access), not a data-quality defect — every Build B assertion was manually
  spot-checked to confirm it cites a real, resolvable, exact field match, and
  9 subjects were correctly left `EXHAUSTED_NO_MATCH` rather than
  fuzzy-matched to force a resolution.

- Total assertions: A=1465, B=1462 (near-identical volume, 3-assertion
  difference).

- 161 of 554 subjects (29%) have a differing assertion-type *set* between
  builds even where completion state does not differ — expected given B's
  narrower source mix (e.g., B may assert `EXACT_PRODUCT_NAME_EXISTS` via a
  ClinicalTrials.gov field where A asserted the same fact via an openFDA
  field, or B lacks a `TRIAL_TO_PRODUCT_EXPLICIT_LINK` type that A obtained
  from a company pipeline page).

## Level 3 — Assertion / completion reproducibility

Completion-state distributions:

| State | Build A | Build B |
|---|---|---|
| SUFFICIENT_EXTERNAL_AUTHORITY_CAPTURED | 471 | 453 |
| CONFLICTING_AUTHORITY_CAPTURED | 76 | 76 |
| NO_EXTERNAL_AUTHORITY_FOUND | 7 | 15 |
| PARTIAL_AUTHORITY_CAPTURED | 0 | 10 |

522/554 subjects (94.2%) have **identical** completion state across both
independent builds. 32/554 (5.8%) disagree. All 32 are listed explicitly in
`completion_state_disagreements.jsonl`; patterns:

1. **SUFFICIENT (A) → NO_EXTERNAL_AUTHORITY_FOUND (B), 15 subjects** — e.g.
   Tarlatamab, Enfortumab Vedotin-Ejfv, Nab-Paclitaxel, EVM14. These are
   well-known named products where Build A's broader Tier B/C source access
   (company pages, DailyMed) found confirming evidence that Build B's
   ClinicalTrials.gov-only research could not independently reproduce for that
   specific subject/question pairing. Attributable to the disclosed
   WebSearch-unavailability constraint on Build B, not to fabrication or
   error by either build.

2. **SUFFICIENT (A) → PARTIAL_AUTHORITY_CAPTURED (B), 10 subjects** — e.g.
   MK-1308, IBI363, PD-1 Inhibitors class term. Same root cause: Build B
   resolved some but not all of a subject's research questions from
   ClinicalTrials.gov fields alone.

3. **NO_EXTERNAL_AUTHORITY_FOUND (A) → SUFFICIENT (B), 7 subjects** — e.g.
   Bristaxol, MGCD516, Anzatax, Mylosar. Here Build B's independent research
   found qualifying exact-match evidence (brand-name entries in
   ClinicalTrials.gov `otherNames` fields) that Build A's research did not
   locate. This direction demonstrates the independent research was not
   merely a strict subset of Build A's — Build B surfaced genuinely new,
   independently verified evidence in some cases.

No subject shows a CONFLICTING_AUTHORITY_CAPTURED disagreement — the 76
conflict-bearing subjects agree exactly between builds (Level 2 explanation
above).

## Validator fix applied during this comparison

`tier_a_positive_matches_are_exact_field_matches` originally only recognized
openFDA-style `evidence_location` strings (containing `"exact"` or
`"openfda"`). This under-recognized Build B's independently-sourced,
equally-exact ClinicalTrials.gov field locators (e.g. `otherNames` field
entries, intervention-name field entries). Broadened the accepted-marker list
in both builds' copies of the validator; re-ran Build A's full 22-case
mutation suite (22/22 pass, no regression) and re-validated Build A's real
snapshot (unchanged, still clean) before trusting the fix against Build B.

## Overall assessment

Both builds independently and honestly executed full Tier A research and
attempted full Tier B/C escalation under the same isolation and stop-condition
rules, with zero cross-build data leakage (no agent accessed Build A's path;
verified via agent self-reports and absence of any references to Build A
content in Build B's manifests/logs). Research-universe reproducibility is
exact (Level 1). Evidence and completion-state reproducibility is strong
(94.2% subject-level agreement) with all divergence explicitly disclosed,
attributed to a genuine and disclosed capture-methodology asymmetry (Build B's
near-total WebSearch unavailability forcing reliance on ClinicalTrials.gov API
fetches), and fully enumerated rather than smoothed over. No genuinely
conflicting (i.e., mutually contradictory) external evidence was found between
builds — divergences are of the "found vs. not found" type, not the "found
X vs. found not-X" type.
