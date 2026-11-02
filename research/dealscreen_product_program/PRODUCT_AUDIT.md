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

**Addendum (2026-11-01, revision 7).** Round 6 (`REREVIEW5.md`) found 6 High errors in revision 6's plain forms:
they read lower-cased text in U.S. terms, so a U.S. grant inside a party span, a pronoun subject, a note inside the
text or a grant in a non-U.S. buyer's own territory passed; ownership words and rights rows' quotes were unread. End
to end, 12 test placements reached tier 0 or 1. Revision 7 reads places as written, against the buyer territory,
and never lets a plain form accept what the reader cannot read. Implementer-measured: the 12 placements → 0; the
round-6 usefulness costs removed; no CLDN18.2 field changed. The verdict above is unchanged: no advantage over
general Claude is demonstrated, and revision 7 has not been reviewed.

**Addendum (2026-11-01, revision 8).** Round 7 (`REREVIEW6.md`) found 5 High errors in revision 7: the "other
places" form took any words as a party; quote prefixes were dropped as speakers; options and "worldwide" in quotes
were unread; offers were not compared with a non-U.S. buyer territory; year- or month-dated endings were judged by the
start of the period. Revision 8 closes each. Implementer-measured: the reviewer's 6 end-to-end top-tier placements
→ 0; no CLDN18.2 field changed. The verdict above is unchanged, and revision 8 has not been reviewed.

### Updated largest obstacles

1. Rights/availability still depends on evidence the tool does not hold (import vendor deal fields).
2. Tool-UNKNOWNs without a concrete next action reduce recall versus an unaided analyst.
3. Valuations a Finance Director cannot rebuild by hand (Lane 1 sign-off needed).
4. No real human session (Gate H) — every result above is AI-simulated.

## Audit 2 (2026-10-31, after cycle R1 revision 4)

AI-simulated, internal development. Evidence: `research/dealscreen_rights_v1/` (acceptance criteria, three
adversarial reviews and the responses, CLDN18.2 outputs before and after). Revision 4 is measured by the
implementer only; it has not been re-reviewed by a separate context.

**Verdict: the transaction view no longer misleads on the C1 failures, but DealScreen still shows no advantage over
a general Claude analyst on commercial rights.**

| Measure (CLDN18.2, frozen reference) | Baseline (0ee7752) | After R1 revision 4 |
|---|---|---|
| Third-party-held programs shown as unobstructed (OPEN or a top tier) | 4 definite + zanidatamab | 0 |
| Programs labelled OPEN with no rights evidence | 50 of 62 | 0 (no OPEN tier; 49 read "no rights evidence") |
| Deal programs right / partial / missed (15) | not measured | 10 / 4 / 1 (general Claude: 14 / 1 / 0) |
| Scientific fields changed | — | 0 of 62; 0 of 312 assets on synthetic, FcRn v1/v2, C5 |
| Reviewers' held-out inputs placed in a top tier that they flagged as errors (end-to-end workspaces) | — | revision 3: 12; revision 4: 0 (implementer-measured) |

- **Better than before:** every rights call cites its row, quote, URL, dates and event id; a program reaches a top
  tier only when its rights evidence is complete, specific, current and uncontested, and each failed check is named
  with a question (revision 4; revision 3's narrower guard was bypassed 11 ways in review); returned rights,
  options, sublicenses and acquisitions are modelled; the buyer territory is validated.
- **Still worse than general Claude:** recall. DealScreen reads rights only from the imported file. It misses
  SKB315's return and LM-302's return to LaNova/Sino Biopharm because the frozen library does not record them.
- **Not demonstrated:** a real vendor deals export, a human analyst using the rights view (Gate H), an independent
  reference (Gate B).

**Addendum (2026-11-01, revision 5).** Round 4 (`REREVIEW3.md`) found that revision 4's checks ran in full only where
a return decided the position: on copies of the CLDN18.2 workspace, test cases reached transaction #1-#3 in tier 0.
Revision 5 replaces the checks with one gate on every path that blocks what it cannot read. Implementer-measured: the
round-4 reviewer's flagged top-tier placements 13 → 0; no CLDN18.2 tier or call changed; one clean held-out case is
now held back with an ownership question (a usefulness cost). The verdict above is unchanged. Round 5
(`REREVIEW4.md`) reviews revision 5.

**Addendum (2026-11-01, revision 6).** Round 5 (`REREVIEW4.md`) found 11 High errors, all paths into tier 0 or 1 that
the revision 5 gate passed because its reader marked a misreading as understood, or because the gate did not read
the input at all (Partnerships, Geographic Notes, notes in names, non-U.S. territories). End to end on copies of the
CLDN18.2 workspace, 18 test placements reached tier 0 or 1. Revision 6 inverts the gate's default: beside a clear
position a rights text passes only as a plain form (`rights_allow.py`). Implementer-measured: the 18 flagged
placements → 0; the reviewer's over-caution costs for Chinese originators ("Ex-China rights available",
company-retains wording, a city inside a legal name) removed; no CLDN18.2 tier or call changed. The verdict above is
unchanged: no advantage over general Claude is demonstrated, and revision 6 has not been reviewed.

**Addendum (2026-11-01, cycle U1 revision 3).** Each tool UNKNOWN on a program that is not excluded now carries a
diagnostic naming what the record holds and the cited fact that would decide the gate (CLDN18.2 38 of 38, held-out
104 of 104, no science change). Two AI reviews found misleading classes; revision 3 answers the second and has not
been reviewed. Whether the actions save an analyst time is untested without a human session. The verdict above is
unchanged.

### Updated largest obstacles

1. Tool-UNKNOWNs now carry a concrete next action (U1), but whether that reduces anchoring is unmeasured without a
   human session, and U1 revision 3 has not been reviewed.
2. Rights recall is capped by the imported evidence; a licensed vendor deals export has not been tested. Parties
   are matched by name only, so differently named subsidiaries create cautious conflicts.
3. Valuations a Finance Director cannot rebuild by hand (Lane 1 sign-off needed).
4. No real human session (Gate H) — every result above is AI-simulated.
