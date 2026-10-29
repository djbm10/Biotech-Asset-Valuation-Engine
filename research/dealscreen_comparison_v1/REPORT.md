# DealScreen vs general Claude vs spreadsheet: CLDN18.2 comparison (cycle C1)

AI-SIMULATED / INTERNAL DEVELOPMENT. All analysts, the reference and the critics are AI agents.
Sources: CRITIC_BASELINE.md, CRITIC_FINAL.md, scores.json, FIXES_C1.md.

**Verdict (pre-registered rule): no demonstrated DealScreen advantage over general Claude (B), before
or after fixes.** After fixes, the final DealScreen run (C3) ties B at 0 screening/shortlist critical
errors. It loses on recall (23/30 vs 30/30 reference-IN), on evidence checkability (4/8 vs 2/8
unsupported sampled claims), on valuation reproducibility, and on effort (~30 vs ~16 tool calls).

1. **Better than Claude:** no wrong eligibility at any point; refuses paraphrased rights quotes; records
   returned rights and options; never infers availability; transaction view separates science from deal
   attractiveness; identity flags across codes; hash-chained, human-only approvals.
2. **Claude better:** recall (judges pan-tumour baskets itself); fully hand-reproducible valuations;
   half the effort; no tool-specific workarounds.
3. **Costly failures found:** the tool silently lost its ontology outside the repo (fixed, X7); isoform
   names unreadable (fixed, X1); anchoring: analysts left tool-UNKNOWN programs unresolved (RC118 a
   real miss); transaction view tiers Takeda-held IBI343 and Merck KGaA-optioned SHR-A1904 OPEN (rights
   evidence not confirmed in-tool); 21% tax and scenario shocks absent from deliverables (protected
   engine, proposal P8/P9).
4. **Missed / wrong / unresolved (reference-IN = 30):** A 29 found / 1 wrongly excluded; B 30/0/0;
   C baseline tool alone 0 as installed; C3 tool alone 14 eligible, 0 wrong inclusions; C3 analyst
   23 found / 0 wrong / 7 unresolved.
5. **Work:** A ~19, B ~16, C ~30 tool calls; no human approval or valuation completed in any workflow.
6. **Reusable:** working-directory fix, partial-date parsing, rights vocabulary, transaction view,
   indication reading v2 (held-out 75k strings: 5 readings, all correct), partial target witness.
   Critic flags the isoform reading (X1) as shaped by this landscape.
7. **Needs a real analyst / data / sign-off:** confirming facts and approvals (Gate H); rights and
   availability (licensed BD databases); valuation transparency in the protected engine (Lane 1).
8. **To be compelling:** import vendor rights/deal fields so the transaction view runs on real
   evidence; no tool-UNKNOWN without a concrete next action; valuation outputs that a Finance Director
   can rebuild by hand; a measured human session showing time or error reduction versus Excel + AI.
