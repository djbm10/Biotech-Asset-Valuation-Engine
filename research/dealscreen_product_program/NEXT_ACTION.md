# Next action (restart checkpoint)

**State at checkpoint (2026-11-01):**
- Branch `dealscreen-mvp`. Cycles 1-5, analyst-simulation cycles A1-A5, comparison cycle C1 and rights cycle R1 revision 7 are committed (see `ITERATION_LOG.md`). R1 revisions 2-4 were never committed separately; they are in the revision 5 commit. Revisions 6 and 7 are one commit.
- Uncommitted user files: `AGENTS.md`, `research/universe/biotech_tickers.yaml`, `.claude/`, `.serena/`, `research/dealscreen_product_program/cycle4/equivalence_result.json`. Never stage them.
- `research/dealscreen_unknown_actions_v1/ACCEPTANCE.md` holds the U1 acceptance criteria, frozen before U1 code on 2026-10-30 and committed on their own, separately from R1.
- Never pop shared stashes.

## On restart

1. Read `PRODUCT_GOAL.md`, `SCORECARD.md` (latest sections at the bottom) and this file.
2. Confirm the branch and that `git status` shows only the user files above.
3. Run the DealScreen tests (expect 816 passed):
   `TMPDIR=$HOME/.cache/dealscreen_suite python -m pytest tests/dealscreen -q -p no:cacheprovider`
   `/tmp` is a small tmpfs; keep test temp files on the home disk.
4. For any cycle that changes screening, re-run
   `python research/dealscreen_product_program/cycle4/equivalence.py $HOME/.cache/cycle4_ws`
   (needs the ontology, ~5 min). Expect byte-identical results on all four workspaces.

## Comparison cycle C1 (2026-10-29)

See `research/dealscreen_comparison_v1/REPORT.md`. Verdict: no demonstrated advantage over general Claude. Next: (1) resolve the critic's transaction-view false OPENs (IBI343, SHR-A1904) by importing vendor rights/deal fields; (2) give each tool-UNKNOWN a concrete next action to reduce anchoring; (3) review X1 isoform reading for landscape tuning; (4) Gate H human session.

## Rights cycle R1 (2026-10-30)

See `research/dealscreen_rights_v1/` (ACCEPTANCE, REVIEW/REREVIEW/REREVIEW2 and the responses). A deals/rights export
is imported through a mapping profile; each program gets a cited rights position for the buyer territory; the `OPEN`
tier is gone. A program reaches a top tier only when its rights evidence is complete, specific, current and
uncontested (`top_tier_blockers` names each failed check). Since revision 5 one gate (`rights_gate`) checks this on
every path; since revision 6 it passes a rights text only as a plain form (`rights_allow`), so anything else blocks.
Revision 6 answers `REREVIEW4.md`; revision 7 answers `REREVIEW5.md` (`REREVIEW5_RESPONSE.md`): the plain forms read places as written, in the buyer territory, and never accept what the reader cannot read. Revision 7 has not been reviewed. CLDN18.2: third-party-held programs shown as unobstructed 4 (+ zanidatamab) -> 0; 0 of 62 scientific
fields changed; usefulness against general Claude unchanged (10/4/1 vs 14/1/0 on 15 deal programs, so no advantage).
Gaps: SKB315's and LM-302's returns are not in the frozen library; a real vendor deals export is untested.

**Next: cycle U1, give each tool-UNKNOWN a concrete next action** (`research/dealscreen_unknown_actions_v1/ACCEPTANCE.md`;
C1 critic section 2). Baseline: 38 UNKNOWN requirement decisions on CLDN18.2 (indication 24, modality 8, target 4,
phase 2). Then: X1 isoform reading review; Gate H human session.

## Analyst-simulation loop

See `analyst_simulation/`. Cycles A1-A5 done (A5: market status vs Phase 4 and approval-statement proposals; A4: valuation transparency on DealScreen paths; engine findings P1-P7 proposed for Lane 1 in `docs/change_requests/proposed/valuation_transparency_from_analyst_simulation.md`). Next: the deferred backlog in `analyst_simulation/PRIORITIZED_FIXES.md` (approval-statement stage extraction, CT.gov research noise, partnerability as a buyer-declared preference).

## Gate H session package: PREPARED (not run). See `gate_h_session/SESSION_PROTOCOL.md`. Running it needs a real BD professional.

## (historical) Gate H preparation plan

**Why this ranks first.** Gates C and D are now technically demonstrated or partial, and the
remaining claims about usefulness, time and accuracy cannot be made without a person. The
cheapest unblocking work is a ready-to-run session package. This is preparation only: no claims
until a human runs it.

**Contents:**
- a task script on the real FcRn / gMG landscape: import, screen, resolve 3 named unknowns with cited assertions, review rights, list candidates, approve up to N, request one valuation readiness check, export;
- a timing and correction log template;
- a baseline task: the same questions answered with a spreadsheet and the public sources only;
- a feedback form;
- a one-page "what is synthetic or hypothetical" disclosure.

## Engineering candidates after that (re-rank before choosing)

- **Stage semantics (backlog 5).** Phase 4 study, ex-U.S. approval and U.S. marketing are conflated at stage order 6. This affects the commercial-stage block (telitacicept would be blocked as commercial on an ex-U.S. Phase 4).
- **Agent approval-statement extraction (backlog 7).** Rozanolixizumab's U.S. approval is in UCB's release, but nothing extracts it.
- **Buyer-spec modality scope.** Fc-fragment FcRn blockers (efgartigimod) cannot be included by a buyer, because no modality term exists. This is a buyer-spec vocabulary question touching the S&E modality ontology, so it needs S&E governance.
- **Identity merges cannot be applied.** Flags are review-only and records stay separate. Needed before a deduplicated shortlist.

## Needs a person or an approval (see BLOCKERS.md)

- Gate H (an analyst);
- Gate B (an independent curator and a held-out landscape);
- Lane 1 sign-offs (the deal-terms prototype, the RLAY patch);
- engineering sign-off to merge;
- licensed data and a security review (Gate I).
