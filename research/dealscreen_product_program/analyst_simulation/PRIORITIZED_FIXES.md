# Prioritized fixes (AI-SIMULATED / INTERNAL DEVELOPMENT)

Ranked by: wrong-decision potential, BD importance, assets affected, analyst effort,
recurrence across landscapes, fix risk. Criteria were written before any code.

## Cycle A1 — ranked list (from frozen ANALYST_FINDINGS.md, reproduced by engineering)

| Rank | Id | Problem (finding #) | Root cause class | Decision |
|---|---|---|---|---|
| 1 | F1 | "Registry: no recruiting gMG trial (COMPLETED)" read as ACTIVE; feeds the "active development" rank (#3; 5 rows) | software defect (negation) | FIX |
| 2 | F2 | "Generalized Myasthenia Gravis" → indication UNKNOWN (#1; 5 rows; recurs in any landscape using severity/extent qualifiers) | weak normalization: frozen NCIt 26.08e has no gMG concept | FIX in DealScreen, disclosed; S&E authority unchanged |
| 3 | F3 | `bve-dealscreen-value` silently drops unknown config keys (`discount_rate`, `deal_options` at top level) (#4) | software defect (fail-open input) | FIX: fail closed |
| 4 | F4 | Workbook Finalists note "7 approved finalist(s)" for AI_PREPARED candidates (#5) | software defect (labelling) | FIX |
| 5 | F5 | Memo: "U.S. rights holder is evidenced" counts an FDA labeler (#6); empty "Preliminary valuations" heading (#14) | labelling defect | FIX |
| 6 | F6 | `bve-dealscreen value` crashes with FileNotFoundError when nothing ran (#7) | software defect | FIX |
| 7 | F7 | Identity flags not shown at import or in the memo candidate list (#2, surfacing part) | workflow / UX | FIX (surface only; merges still not applied) |
| — | D1 | Efgartigimod modality "Protein" (Fc fragment) UNRESOLVED (#9) | unclear buyer requirement + S&E modality vocabulary | DEFER: needs buyer/S&E governance; not assumed |
| — | D2 | AI cannot record cited evidence even as a proposal (#8) | workflow | NEXT CYCLE candidate (AI proposal → human confirm) |
| — | D3 | Identity merges cannot be applied (#2, decision part) | workflow | NEXT CYCLE candidate |
| — | D4 | No human-efficacy evidence field (#12) | missing capability | BACKLOG |
| — | D5 | CT.gov research returns phase-only findings; title labelled "mechanism" (#10) | weak extraction | BACKLOG |
| — | D6 | Peak-sales haircut (gross-to-net) not explained (#15) | valuation disclosure; protected engine | PROPOSAL only |
| — | D7 | `bve-asset` (protected) also ignores unknown top-level keys such as `market:` in 10 example configs | protected code | PROPOSAL only (Lane 1) |

## Acceptance criteria (written before code)

- **F1.** `activity_status` never returns ACTIVE when the activity word is negated
  ("no recruiting", "not recruiting", "no active", "not active", "no ongoing"). "Marketed" is its own
  value MARKETED (not counted as active development, so ranks do not change for marketed rows).
  On the real landscape: RW-06, RW-07, RW-25, RW-28, RW-29 are no longer ACTIVE; every
  "Active trial in registry" row stays ACTIVE. Ranking rule unchanged.
- **F2.** An indication string the NCIt authority cannot identify, written as
  `<qualifier> <disease>` with a qualifier from a closed list (generalized, refractory, relapsed,
  relapsing, recurrent, chronic, severe, moderate, mild, moderate to severe, active, adult,
  pediatric) where `<disease>` identifies exactly one NCIt concept, is also read as that concept.
  Every such reading is listed on the asset (observed text, read as, rule) and appears in `show`
  and the workbook. Never applied when the full name already resolves. Adversarial: "non-small
  cell lung cancer", "anti-…", "ocular …", "AChR+ …", "acute …" are not stripped; a buyer asking for a
  subtype is not satisfied by its parent. No S&E file changes. Real landscape: the gMG-only rows
  move only on the indication gate; no row moves to ELIGIBLE unless all other gates PASS.
- **F3.** Unknown top-level keys fail with exit code 2 and a message naming each key and, for
  known misplacements (`discount_rate` → `asset.discount_rate`, `deal_options` → `deal_economics`),
  the correct location. Results with valid configs unchanged (the bve-asset parity test still passes).
- **F4.** The Finalists note counts by reviewer kind; "approved" is said only of HUMAN decisions in
  APPROVED state.
- **F5.** The memo calls the holder "U.S. labeler/holder per cited source (not a rights or
  availability statement)"; when no valuation ran, the memo says why (no human-selected finalist,
  or not ready).
- **F6.** `value` with nothing to run exits 0 with a plain message and writes an empty results file.
- **F7.** `import` prints the identity flags (kind, records); the memo marks candidates that share
  an identity flag.

## Additions after the adversarial review (still before code)

- **F2 extended.** Also read the inverted form `<disease>, <qualifier>` (e.g. "Myasthenia Gravis,
  Generalized") and a trailing parenthetical acronym (e.g. "… (gMG)", letters only, ≤6 chars).
  The same disclosure applies.
- **F3 corrected.** The critic showed finding #4 was overstated: the analyst's keys were misplaced.
  The defect is that misplaced keys are accepted silently and the default 12% is applied without
  notice. F3 stands as written. **F3b:** the prototype prints, with every result, the discount
  rate used and the economic perspective (asset-holder rNPV, not a buyer deal NPV, unless
  `deal_economics` is given, in which case the terms are listed).
- Reviewer notes "IMVT-1402 is blocked on four gates, not one", "rozanolixizumab curated as
  Phase 4" (stage semantics, backlog) and "coverage limited to CT.gov" are recorded; none is
  in this cycle.

Baseline per asset: `measure/baseline_A1.json` (from the analyst's own workspace).

## F8 (found during F2 testing; criteria before code)

**Problem.** A vendor therapeutic-area label is not exclusive: myasthenia gravis is both
neurological and autoimmune. When the indication text is unreadable, the vendor label
"Neurology" alone becomes the whole area fact and the AUTOIMMUNE requirement FAILs, which
EXCLUDES the program. Analyst finding #13 (belimumab RW-29) is this defect. It is masked on the
real landscape only because belimumab also fails on target. A test-only copy with RW-05's
indication written "gMG" reproduces a wrongful exclusion of an in-scope FcRn antibody.

**Rank.** First by severity: it causes wrongful exclusions, which an analyst never sees in the
review queue.

**Criteria.**
- When the only area evidence is a vendor TA label (no indication-derived area), and that label
  does not include a requested area, the area fact is not emitted, so the gate is UNKNOWN, not FAIL.
  The asset lists the reason ("vendor area label alone cannot exclude").
- When an indication-derived area exists, behaviour is unchanged (FAIL is still possible when the
  indication-derived areas and labels exclude all requested areas).
- A vendor label that matches a requested area still PASSes.
- Real landscape: no disposition changes except RW-29 (stays EXCLUDED on target); its TA gate goes
  FAIL → UNKNOWN. Synthetic demo funnel unchanged, or every change explained.
- S&E gate code unchanged.
