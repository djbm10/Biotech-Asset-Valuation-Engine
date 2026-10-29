# Next action (restart checkpoint)

**State at checkpoint (2026-10-28):**
- Branch `dealscreen-mvp`. Cycles 1-5 and analyst-simulation cycle A1 are committed (see `ITERATION_LOG.md` and `analyst_simulation/ITERATION_LOG.md`).
- Uncommitted user files: `AGENTS.md`, `research/universe/biotech_tickers.yaml`, `.claude/`, `.serena/`. Never stage them.
- Never pop shared stashes.

## On restart

1. Read `PRODUCT_GOAL.md`, `SCORECARD.md` (latest sections at the bottom) and this file.
2. Confirm the branch and that `git status` shows only the user files above.
3. Run the DealScreen tests (expect 248 passed):
   `TMPDIR=$HOME/.cache/dealscreen_suite python -m pytest tests/dealscreen -q -p no:cacheprovider`
   `/tmp` is a small tmpfs; keep test temp files on the home disk.
4. For any cycle that changes screening, re-run
   `python research/dealscreen_product_program/cycle4/equivalence.py $HOME/.cache/cycle4_ws`
   (needs the ontology, ~5 min). Expect byte-identical results on all four workspaces.

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
