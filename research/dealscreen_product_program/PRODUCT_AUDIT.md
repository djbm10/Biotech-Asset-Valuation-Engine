# DealScreen product audit

Grade: INTERNAL DEVELOPMENT. Updated each cycle; history is in `ITERATION_LOG.md`.

## Audit 0 (2026-10-28, branch `dealscreen-mvp` @ 44eb9a5)

Baseline reconfirmed. `tests/dealscreen/test_real_landscape.py` reproduces the real-data
result, 4 ELIGIBLE / 14 UNRESOLVED / 22 EXCLUDED on 40 FcRn / gMG programs. The synthetic
200-row demo still passes. DealScreen tests: 72. Focused valuation suite: 820. S&E: 2188 + 3
xfailed.

### What works (evidence)

- **Import.** Row accounting is exact. Raw rows, row/column provenance and the manifest hash
  are kept. Tests: `test_importer_identity.py`; real run 40/40.
- **Screening.** It reuses the S&E `GateEngine` unchanged. Every PASS/FAIL cites an imported row
  and column (test). On real data there were 0 wrong inclusions or exclusions against a
  pre-committed reference.
- **Reference caveat.** That reference is same-author (AI). It checks dispositions, not field
  values, so "0 wrong" says nothing about whether every cited fact is true.
- **Decision log.** Hash-chained and attributable. AI and synthetic reviewers are labelled, and
  the AI kind cannot approve or confirm (tests).
- **Valuation handoff.** Subprocess through the authorised CLI; reads saved output. Readiness
  checklist; scenario-ordering check explains or blocks out-of-order results; reconciles with
  `compute_rnpv_full` (tests).

### Critical findings (ranked by analyst impact)

1. **Analysts cannot resolve UNKNOWNs inside the tool (Gate C).** On real data, 38 of 39 open
   gate questions on unresolved programs need a fact the analyst must type in. DealScreen
   offers only confirm/reject of existing claims or agent findings, so the analyst must edit
   the landscape file and re-import, losing the link between the fix and the original record.
   All 5 in-scope misses fall in this class. This is the largest workflow obstacle measured.
2. **No commercial intelligence (Gate D).** Every program's U.S. rights are UNKNOWN,
   including three U.S.-marketed FcRn products.
   - The commercial model has one field (rights status) and no notion of rights holder, licensor
     or territorial licensee.
   - The rights reader is a regex over vendor text.
   - "Marketed by X under a U.S. label" is real evidence that X holds U.S. rights (and so the
     asset is not obviously available). It is currently discarded.
3. **No real users or independent reference (Gates B, H).** Every result so far was produced and
   judged by the same AI environment. Nothing measures analyst time or usefulness. This cannot
   be fixed by engineering; it needs a person.
4. **Commercial-stage products are not blocked from pre-approval rNPV (Gate F).**
   `valuation_handoff.check_readiness` never looks at stage. Given inputs, a marketed product
   would be valued with a trial-path model. This is a correctness risk in a financial deliverable.
   - *Self-criticism:* the first build relied on the analyst noticing this. The real-data run
     dodged it only because no inputs were supplied for nipocalimab.
5. **Identity: the same molecule under a different holder is invisible.** HBM9161 (Harbour
   BioMed) and batoclimab (Immunovant) resolve to one authority drug. `identity_flags` drops
   cross-company authority matches entirely, to avoid MB-102-style false merges.
   - The right behaviour is a reviewable flag, never a merge. Territorial licensees of one
     molecule are central to BD (Gate A: "distinguish territorial licensees").
   - *Self-criticism:* the MB-102 rule I wrote solved one failure by hiding a different, equally
     important relationship.
6. **Stage semantics.** The real profile maps any Phase 4 trial to stage order 6, displayed as
   "Phase 4 or marketed". A Phase 4 study (e.g. telitacicept, approved outside the U.S.) is not
   U.S. marketing.
   - The landscape builder separately marks a U.S. label as "Marketed". The two signals are
     conflated into one number.
7. **Vocabulary gaps produce UNRESOLVED on real data:**
   - indication "Generalized Myasthenia Gravis" (the NCIt authority has no such name);
   - modality "Protein" / "antibody fragment";
   - "binding agent" mechanisms.

   These are correct UNKNOWNs. Widening S&E vocabularies would change frozen engine behaviour and
   S&E benchmarks, so per-asset cited analyst facts are the safer path; a reviewed synonym
   layer is a later option.
8. **Agent extraction is narrow.** It does not read approval statements ("has been approved by
   the FDA"). It produced one useful finding on real data (the IMVT-1402 target).
9. **No refresh/diff of a new vendor export (Gate I).** Re-importing creates a new dataset
   version with no comparison to the previous one, and decisions keyed to old claim ids are not
   carried across.
10. **Ranking** is a declared lexicographic preference order with no evidence-strength component
    beyond trial count. It is acceptable for now; it is not the bottleneck.

### Three largest obstacles to usefulness

1. No in-tool resolution of unknowns (finding 1).
2. No commercial rights intelligence (findings 2 and 5).
3. No real analyst or independent evaluation (finding 3, external dependency).

## Audit 1 (2026-10-30, after comparison cycle C1 @ 3d0f98d)

AI-simulated, internal development. Full evidence: `research/dealscreen_comparison_v1/REPORT.md`,
`CRITIC_FINAL.md`, `scores.json`. New frozen challenge: CLDN18.2 (gastric/GEJ), 30 reference-IN programs.

**Verdict: no demonstrated advantage over a general Claude analyst with the same spreadsheet.**

| Workflow | Found / wrongly excluded / unresolved | Wrong inclusions | Tool calls |
|---|---|---|---|
| A spreadsheet SOP | 29 / 1 / 0 | 0 | ~19 |
| B general Claude | 30 / 0 / 0 | 0 | ~16 |
| C3 DealScreen + analyst | 23 / 0 / 7 | 0 | ~30 |

- **Where DealScreen is better:** never asserts wrong eligibility; refuses paraphrased rights quotes;
  never infers availability; separates scientific eligibility from transaction attractiveness;
  cross-code identity flags; human-only, hash-chained approvals.
- **Where it is worse:** recall (tool UNKNOWNs anchor the analyst; RC118 a real miss), evidence
  checkability, valuation reproducibility by hand, and roughly double the effort.
- **Costly risks:** transaction view tiered Takeda-held IBI343 and Merck KGaA-optioned SHR-A1904 as
  OPEN without in-tool rights evidence; tax rate and scenario shocks missing from deliverables
  (protected engine, proposals P8/P9, blocked on Lane 1 sign-off).

### Updated largest obstacles

1. Rights/availability still depends on evidence the tool does not hold (import vendor deal fields).
2. Tool-UNKNOWNs without a concrete next action reduce recall versus an unaided analyst.
3. Valuations a Finance Director cannot rebuild by hand (Lane 1 sign-off needed).
4. No real human session (Gate H) — every result above is AI-simulated.
