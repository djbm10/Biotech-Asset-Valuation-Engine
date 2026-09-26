# Query-parser defects — backlog for a separate parser milestone

Status: **LOGGED, not scheduled.** Opened 2026-09-26. The operator ruled these must not be
bundled into the therapeutic-area gate fix (`docs/se_policies/ta_gate_semantics.md`). Until
they are fixed, ranking benchmarks use only queries whose parser interpretation has already
been checked.

1. **`large` → `LARGE1`.**
   - The word "large" (as in "large B-cell lymphoma") resolves to the target symbol `LARGE1`.
   - This made the original TAC01 preregistered query a QUERY_FAILURE. See
     `tac01_overreach_positive_control_amendment_1.md`.
   - An ordinary English word is being admitted as a target symbol.
2. **`CD19-directed` is unrecognised.**
   - The hyphenated target-plus-suffix form is not resolved to `CD19`.
   - A query naming its target only in that form compiles with no target.
3. **Leftover query words become indication requirements.**
   - Without `--indication`, the intent's residual terms are compiled into
     `strategic_gap.indications` as independent literals: `relapsed`, `refractory`, `B-cell` and
     `lymphoma` in `tac01_control_a1`.
   - `strategy.indication` compares a registry condition string (`"Lymphoma, B-Cell"`) against
     that list with `IN`, so no asset can PASS.
   - Every asset with a condition fact FAILs: 607 in `tac01_control_a1`.

Found while writing the TA declaration, and also out of scope for it:

4. **`tumor` matches `tumor necrosis factor`.** This is an extraction-lexicon defect, not a
   parser defect. It is logged here so it is not lost. A TNF-inhibitor record is classified
   ONCOLOGY.
