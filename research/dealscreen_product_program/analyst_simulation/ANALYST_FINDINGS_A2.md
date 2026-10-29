# AI-SIMULATED / INTERNAL DEVELOPMENT — frozen analyst re-test, cycle A2

Date: 2026-10-28. Analyst: an AI subagent (reviewer id `ai-analyst-sim-A2`, kind AI_PREPARED). Nothing here
is human validation. Every step that needs a human is **NOT COMPLETED BY HUMAN**. Timings are AI wall-clock,
not human time savings.

What I read: `docs/dealscreen/README.md`, `ANALYST_ASSIGNMENT.md`, CLI `--help`, the `examples/dealscreen_real/`
inputs (not `reference_manual_assessment.csv`), my workspace outputs, and public web pages. I did not open
`src/`, `tests/`, git history or any other `research/` file. I did see that the README *names*
`research/dealscreen_real_v1/REPORT.md` and `research/dealscreen_hardening_v1/FINANCIAL_AUDIT.md`. I did not open either.

Workspaces: `~/.cache/analyst_sim_A2/p1` (FcRn buyer) and `~/.cache/analyst_sim_A2/p2` (held-out C5 buyer).
`TMPDIR=$HOME/.cache/dealscreen_suite`.

## Action log

`B=.venv/bin/bve-dealscreen`, `E=examples/dealscreen_real`

| # | Command (abridged paths) | Result | ~s |
|---|---|---|---|
| 1 | `$B import --workspace p1 --landscape $E/landscape_fcrn_gmg_v2.csv --profile $E/profile_public_landscape_v2.yaml --buyer $E/buyer_fcrn_gmg.yaml --identity-authority` | Read 40, imported 40, 0 rejected. Raised 4 identity flags: batoclimab ×3, gefurulimab/ALXN1720 ×1 | 36 |
| 2 | same import into p2 with `--buyer $E/buyer_c5_gmg_heldout.yaml` | Same 40 rows and same 4 flags | 36 |
| 3 | `$B screen --workspace p1` / `p2` | p1: 6 eligible, 12 unresolved, 22 excluded. p2: 5 eligible, 11 unresolved, 24 excluded | 0.6 |
| 4 | `$B queue --workspace p1`; `$B show --asset RW-08` | Worked. The queue is not printed in rank order (#5, #7, #6, …) | 0.2 |
| 5 | `$B research --workspace p1 --provider offline:$E/evidence_library_public.json` | 2 findings: IMVT-1402 target FCGRT (SEC 10-K); rozanolixizumab "mechanism" | 28 |
| 6 | `$B research --workspace p1 --provider ctgov --unresolved` | 36 findings, all of them `phase`. None addresses target or modality, the gates that actually block | 8 |
| 7 | WebSearch/WebFetch: AstraZeneca gefurulimab PR; openFDA labels for zilucoplan and efgartigimod; CT.gov API for NCT06607627 and NCT07039916; search on Regeneron NIMBLE | Quotes obtained (below) | ~60 |
| 8 | `$B propose` ×4 in p1/p2: target=C5 for RW-15 and RW-16 (quote: "Gefurulimab, an investigational complement C5 inhibitor, is a novel dual-binding nanobody", astrazeneca.com 2025-07-25) | Recorded as proposals. They change nothing until a human confirms (NOT COMPLETED BY HUMAN) | 0.2 each |
| 9 | `$B propose --workspace p2 --asset RW-14 --field modality --value PEPTIDE` (openFDA quote: "Zilucoplan, a complement inhibitor, is a 15 amino-acid, synthetic macrocyclic peptide.") | Recorded as a proposal | 0.2 |
| 10 | `$B propose --workspace p1 --asset RW-01/RW-02 --field modality --value FUSION_PROTEIN` (openFDA quote: "…is a human immunoglobulin G1 (IgG1) -derived Fc fragment…") | Recorded. **The tool did not question whether an Fc fragment counts as FUSION_PROTEIN.** My value is debatable | 0.2 |
| 11 | `$B propose … --reviewer jdoe` (a human-looking id on the AI command) | Accepted silently. It returned the same proposal id | 0.2 |
| 12 | `$B decide --action CONFIRM_FINDING … --reviewer-kind AI_PREPARED` (guard test) | REFUSED (correct) | 0.2 |
| 13 | `$B decide --action APPROVE_FINALIST --new-state APPROVED --reviewer-kind AI_PREPARED` ×5 | REFUSED (correct): AI can only list CANDIDATE_NOT_APPROVED | 0.2 |
| 14 | `APPROVE_FINALIST --new-state CANDIDATE_NOT_APPROVED` ×9 (p1), ×8 (p2) | Recorded. Each one prints "Re-run `screen` to apply fact changes", which does not apply to a candidate listing | 0.2 each |
| 15 | `APPROVE_FINALIST` on RW-10 (excluded) | REFUSED (correct) | 0.2 |
| 16 | `SELECT_FOR_VALUATION RW-03` as AI | REFUSED: needs an approved finalist (correct) | 0.2 |
| 17 | `RESOLVE_IDENTITY_FLAG --subject batoclimab` (the README form) | **REFUSED: "no identity flag for 'batoclimab'"**. `DRUG:BATOCLIMAB` was also refused. Only `idflag:…` reaches the human-only refusal | 0.2 |
| 18 | `$B value --workspace p1 --assumptions $E/valuation_assumptions_hypothetical.yaml` | No run: nothing is human-selected. RW-08 is READY (defaults used for COGS/SG&A). Marketed programs are correctly refused | 0.2 |
| 19 | `bve-dealscreen-value --config val/rw08.yaml` (hand-built) | 1) Refused the top-level `market` key with a helpful message, so I renamed it to `market_model`. 2) Refused: missing `asset.id`, `asset.indication`, `company.id/name/cash_millions/shares_outstanding_millions` | 1.3 |
| 20 | `$B export` / `$B memo` (p1, p2) | 9-sheet workbook; 674-word memo plus .docx | 0.5 / 1.9 |

## PART 1 — FcRn antibody buyer (regression)

**A. Landscape.**
- 40 rows and 40 programs.
- 9 FcRn programs, of which batoclimab, RVT-1401 and HBM9161 are one molecule. That leaves 7 distinct FcRn molecules, plus the efgartigimod IV and SC products.
- Also present: complement (8), B-cell/CD19/CD20/BCMA/CD38, BAFF/APRIL, IL-6, BTK, CAR-T and others.
- 13 rows have a blank target; the Notes column says "Target not stated in the sources used".
- Identity flags are correct: RVT-1401 is batoclimab's former code; HBM9161 is Harbour's China licence; ALXN1720 is gefurulimab.

**B. Screen.**
- 6 eligible: rozanolixizumab, nipocalimab, HBM9161, batoclimab, orilanolimab, RVT-1401.
- Excluded correctly overall:
  - C5, CFB, CD19, CD20, CD38, CD40, BAFF, IL6R and BTK fail on target;
  - CAR-T fails on modality;
  - Phase 1 programs fail on phase.
- No false exclusion found.
- **Unresolved items that matter:**
  - IMVT-1402: the row has a blank target, but it is an anti-FcRn mAb;
  - efgartigimod IV and SC: "Protein" does not map to an allowed modality.
- The other 9 unresolved rows are true OUT, but the tool cannot tell, because their targets are blank. That is 9 rows of review work.

**C. Science.**
- The offline library produced the IMVT-1402→FCGRT finding. I could not confirm it, because that needs a human.
- CT.gov research added 36 low-value `phase` findings. Some contradict a Marketed status, e.g. efgartigimod "Phase 2" from NCT02965573.
- The rozanolixizumab "mechanism" finding's value is a full paragraph, not a direction.

**D. Commercial.**
- U.S. rights are UNKNOWN for all 40. That is correct given silent sources.
- **Rozanolixizumab** is FDA-approved (RYSTIGGO, June 2023, per UCB's own release surfaced by the offline library). The landscape says "Phase 4 / Active trial in registry", and the memo prints "Phase 4 or marketed" without "marketed per source".
  - Data gap, not a tool error. But the agent saw an approval sentence and did not raise a STAGE finding.
- Commercial reality:
  - efgartigimod, nipocalimab and rozanolixizumab are big-pharma marketed products, so not licensable;
  - batoclimab gMG is wound down; orilanolimab was terminated.
  - The realistic BD candidates are IMVT-1402 (Immunovant/HanAll; ex-Asia rights are licensed from HanAll) and HBM9161 (Harbour, Greater China rights).
  - The tool cannot express this; every row reads "rights unknown".

**E. Shortlist** (AI_PREPARED, NOT APPROVED BY HUMAN), in the tool's rank order:
1. rozanolixizumab
2. nipocalimab
3. HBM9161
4. batoclimab
5. orilanolimab
6. IMVT-1402
7. RVT-1401
8. efgartigimod IV
9. efgartigimod SC

**My BD order:**
1. IMVT-1402
2. HBM9161 (ex-China question)
3. batoclimab
4. orilanolimab (check whether Alexion would divest)

The marketed products (efgartigimod, nipocalimab, rozanolixizumab) belong only as comparators. RVT-1401 should not be counted separately from batoclimab.

**F. Valuation.**
- Blocked by design: no human approval or selection exists, so the run is NOT COMPLETED BY HUMAN.
- `value` reports RW-08 as READY.
- Hand-built `bve-dealscreen-value` was refused. It needs `company.cash_millions` and `shares_outstanding_millions`, which the hypothetical assumptions file does not provide. I did not invent them.
- **No valuation number exists.**
- The handoff's field names (`market`) also differ from what the CLI accepts (`market_model`), and the assumptions schema cannot be pasted into the CLI config.

**G. Deliverables.**
- Workbook: 9 sheets (README, Landscape, Screening, Diligence, Finalists, Valuation Inputs, Valuation Scenarios, Deal Comparison, Audit Trail). The README says 8.
- The memo is honest about UNVALIDATED status, AI-prepared candidates, identity flags and rights.

### Part 1 — calls for all 40 rows
| id | name | tool | my call | reason |
|---|---|---|---|---|
| RW-01 | Efgartigimod IV | UNRESOLVED (modality) | IN (comparator) | Anti-FcRn IgG1 Fc fragment; marketed argenx, not licensable |
| RW-02 | Efgartigimod SC | UNRESOLVED (modality) | IN (comparator) | Same molecule, SC |
| RW-03 | Rozanolixizumab | ELIGIBLE #1 | IN (comparator) | FDA-approved 2023; row understates stage |
| RW-04 | Nipocalimab | ELIGIBLE #2 | IN (comparator) | Marketed J&J |
| RW-05 | Batoclimab | ELIGIBLE #4 | IN | FcRn mAb; gMG trials terminated |
| RW-06 | HBM9161 | ELIGIBLE #3 | IN | = batoclimab, Harbour China licence |
| RW-07 | RVT-1401 | ELIGIBLE #6 | IN (duplicate) | = batoclimab former code; do not count separately |
| RW-08 | IMVT-1402 | UNRESOLVED | IN | Anti-FcRn mAb (Immunovant 10-K); top BD candidate |
| RW-09 | Orilanolimab | ELIGIBLE #5 | IN | FcRn mAb, terminated |
| RW-10–13 | Eculizumab, 2 biosimilars, ravulizumab | EXCLUDED | OUT | C5 |
| RW-14 | Zilucoplan | EXCLUDED | OUT | C5 peptide |
| RW-15/16 | Gefurulimab / ALXN1720 | UNRESOLVED | OUT | C5 nanobody (AZ PR); same molecule |
| RW-17 | Pozelimab+cemdisiran | EXCLUDED | OUT | C5 |
| RW-18 | Iptacopan | EXCLUDED | OUT | CFB small molecule |
| RW-19 | Vemircopan | EXCLUDED | OUT | Factor D small molecule |
| RW-20 | Claseprubart | UNRESOLVED | OUT | C1s mAb |
| RW-21 | Empasiprubart | UNRESOLVED | OUT | C2 mAb |
| RW-22 | Inebilizumab | EXCLUDED | OUT | CD19 |
| RW-23 | Rituximab | EXCLUDED | OUT | CD20 |
| RW-24 | Ublituximab | EXCLUDED | OUT | CD20 |
| RW-25 | Mezagitamab | EXCLUDED | OUT | CD38 |
| RW-26 | Telitacicept | UNRESOLVED (rank #1 of unresolved) | OUT | TACI-Fc (BLyS/APRIL) |
| RW-27 | Povetacicept | UNRESOLVED | OUT | BAFF/APRIL |
| RW-28 | Iscalimab | EXCLUDED | OUT | CD40 |
| RW-29 | Belimumab | EXCLUDED | OUT | BAFF ("Myasthaenia" spelling left TA and indication UNKNOWN) |
| RW-30 | Satralizumab | UNRESOLVED | OUT | IL-6R |
| RW-31 | Tocilizumab | EXCLUDED | OUT | IL-6R |
| RW-32 | Remibrutinib | EXCLUDED | OUT | BTK small molecule |
| RW-33 | Tolebrutinib | EXCLUDED | OUT | BTK |
| RW-34 | Descartes-08 | EXCLUDED | OUT | BCMA CAR-T (mRNA) |
| RW-35 | KYV-101 | EXCLUDED | OUT | CD19 CAR-T |
| RW-36 | CABA-201 | EXCLUDED | OUT | CAR-T, Ph1/2 |
| RW-37 | Anito-cel | EXCLUDED | OUT | BCMA CAR-T, Ph1 |
| RW-38 | SHR-2173 | UNRESOLVED | UNRESOLVED | Target not found publicly in this session |
| RW-39 | Cizutamig | EXCLUDED (phase) | OUT | Ph1 (BCMAxCD3 T-cell engager) |
| RW-40 | NMD670 | UNRESOLVED | OUT | ClC-1 small molecule |

Agreement with the tool: no wrong ELIGIBLE and no wrong EXCLUDED. 3 true-IN rows are UNRESOLVED (RW-01, RW-02, RW-08), and 9 true-OUT rows are UNRESOLVED.

## PART 2 — held-out C5 buyer (tasks A, B, D, E)

**A. Landscape.**
- C5-relevant rows:
  - eculizumab and 2 biosimilars;
  - ravulizumab;
  - zilucoplan (peptide);
  - gefurulimab = ALXN1720;
  - pozelimab+cemdisiran.
- Nearby but out: iptacopan (CFB), vemircopan (factor D), claseprubart (C1s), empasiprubart (C2).

**B. Screen.**
- 5 eligible: pozelimab+cemdisiran, eculizumab, ravulizumab, Epysqli, Bkemv.
- Zilucoplan is UNRESOLVED: its row says modality "Protein", while the FDA label says "synthetic macrocyclic peptide". I proposed PEPTIDE; human confirmation NOT COMPLETED.
- Gefurulimab and ALXN1720 are UNRESOLVED (blank target); I proposed C5.
- All FcRn rows are correctly excluded on target.
- **No false eligible and no false exclusion by gate.**
- **But:** pozelimab+cemdisiran passes modality as "Antibody" although it contains an siRNA. Regeneron's Aug-2025 NIMBLE topline showed **cemdisiran monotherapy** numerically better than the combination, with cemdisiran alone planned for filing. The tool ranks the combination **#1**, above marketed eculizumab and ravulizumab.

**D. Commercial.**
- Rights are UNKNOWN for all.
- The labelers (Alexion, Amgen, Teva, UCB) are big pharma or biosimilar makers, and none is a plausible licensor. Two of the five eligible rows are eculizumab biosimilars, which are not BD targets.
- The tool's ranking puts "active trial" Phase 3 above Marketed. It appears to treat marketed status as not "active development".

**E. Shortlist** (AI_PREPARED, NOT APPROVED BY HUMAN), in the memo's order:
1. pozelimab+cemdisiran
2. eculizumab
3. ravulizumab
4. ALXN1720
5. gefurulimab
6. Epysqli
7. Bkemv
8. zilucoplan

**My BD order:**
1. gefurulimab (Phase 3 PREVAIL positive; count ALXN1720 once)
2. pozelimab+cemdisiran: flag that the value sits in cemdisiran, which is siRNA and so outside the buyer's modalities
3. zilucoplan, ravulizumab and eculizumab: comparators only
4. biosimilars: exclude as non-targets (a preference the buyer spec cannot express)

### Part 2 — calls for all 40 rows
| id | name | tool | my call | reason |
|---|---|---|---|---|
| RW-01–09 | FcRn programs | EXCLUDED | OUT | FcRn, not C5 |
| RW-10 | Eculizumab | ELIGIBLE #2 | IN (comparator) | Marketed |
| RW-11 | Bkemv | ELIGIBLE #5 | IN, deprioritise | Biosimilar |
| RW-12 | Epysqli | ELIGIBLE #4 | IN, deprioritise | Biosimilar |
| RW-13 | Ravulizumab | ELIGIBLE #3 | IN (comparator) | Marketed |
| RW-14 | Zilucoplan | UNRESOLVED (modality) | IN | FDA label: macrocyclic peptide, binds C5 |
| RW-15 | Gefurulimab | UNRESOLVED | IN | AZ: "complement C5 inhibitor … dual-binding nanobody" |
| RW-16 | ALXN1720 | UNRESOLVED | IN (duplicate) | = gefurulimab |
| RW-17 | Pozelimab+cemdisiran | ELIGIBLE #1 | IN, flagged | Contains siRNA; rank #1 misleading |
| RW-18 | Iptacopan | EXCLUDED | OUT | CFB |
| RW-19 | Vemircopan | EXCLUDED (modality) | OUT | Factor D small molecule |
| RW-20 | Claseprubart | UNRESOLVED | OUT | C1s, not C5 |
| RW-21 | Empasiprubart | UNRESOLVED | OUT | C2 |
| RW-22–25, 28, 29, 31, 33 | B-cell / cytokine / BTK | EXCLUDED | OUT | Not C5 |
| RW-26, 27 | Telitacicept, povetacicept | UNRESOLVED | OUT | TACI-Fc / BAFF-APRIL |
| RW-30 | Satralizumab | UNRESOLVED | OUT | IL-6R |
| RW-32 | Remibrutinib | EXCLUDED | OUT | BTK |
| RW-34–37, 39 | Cell therapies / Ph1 | EXCLUDED | OUT | Modality / phase |
| RW-38 | SHR-2173 | UNRESOLVED | UNRESOLVED | Target unknown |
| RW-40 | NMD670 | UNRESOLVED | OUT | ClC-1 small molecule |

The held-out case generalised in its gates: no wrong ELIGIBLE and no wrong EXCLUDED. 3 true-IN rows are UNRESOLVED (RW-14, 15, 16), and 7 true-OUT rows are UNRESOLVED.

## Defects

| # | Severity | Evidence |
|---|---|---|
| 1 | **Wrong decision (ranking)** | p2 memo ranks `Pozelimab + Cemdisiran` #1 above marketed eculizumab and ravulizumab. In p1, Phase 3 HBM9161 sits close behind marketed products. Marketed status appears to fail "active development". For the combination, the public data put efficacy in the siRNA component, which this buyer would exclude |
| 2 | **Wrong decision (modality)** | RW-17 `modality.required` = PASS on "Antibody" for a combination containing an siRNA (cemdisiran). No combination or component check |
| 3 | **Blocker** | `bve-dealscreen-value` needs `company.cash_millions`, `shares_outstanding_millions`, `asset.id` and `asset.indication`, which the assumptions file lacks. The assumptions schema (`market`) is not the CLI schema (`market_model`). Result: no preliminary valuation without inventing company data |
| 4 | **Blocker (by design)** | Every approval, selection, confirmation and identity resolution is human-only, so the pipeline cannot reach valuation. Correctly enforced; recorded as NOT COMPLETED BY HUMAN |
| 5 | **Friction / doc error** | README example `RESOLVE_IDENTITY_FLAG --subject batoclimab` gives "REFUSED: no identity flag for 'batoclimab'". Only `idflag:<hash>` works, and `queue` never prints flag ids |
| 6 | **Friction** | `research --provider ctgov --unresolved` returns 36 `phase` findings and none on the blocking gates (target, modality). It produces noise such as efgartigimod "Phase 2" for a marketed product |
| 7 | **Friction** | Offline library found the rozanolixizumab FDA approval sentence but raised no STAGE finding. RW-03 stays "Phase 4", and the memo omits "marketed per source" |
| 8 | **Friction** | `propose` records any URL and quote without fetching or checking it. It also accepts `--reviewer jdoe` on the AI command. Integrity rests entirely on the confirming human |
| 9 | **Friction** | `propose --field modality --value FUSION_PROTEIN` for an Fc fragment is accepted without a vocabulary hint. There is no allowed-values list in `--help` |
| 10 | **Friction** | 13 blank-target rows all land UNRESOLVED (9 true OUT for FcRn). No pathway is available to an AI-only workflow to clear them |
| 11 | Cosmetic | `queue` is not in rank order (#5, #7, #6, …) |
| 12 | Cosmetic | A CANDIDATE_NOT_APPROVED decision prints "Re-run `screen` to apply fact changes" |
| 13 | Cosmetic | The workbook has 9 sheets; the README says 8 |
| 14 | Cosmetic | Belimumab's "Myasthaenia Gravis" left therapeutic area and indication UNKNOWN. Its target FAIL still excluded it correctly |
| 15 | Cosmetic | The rozanolixizumab "mechanism" finding's value is a whole paragraph, not a normalized direction |

## Would it survive a Head of BD / Finance Director?

- **Head of BD: partially.** The funnel, exclusions, rights honesty and identity flags hold up, and no gate decision is wrong in either case.
- What a Head of BD would ask:
  - why marketed big-pharma products and biosimilars top a *licensing* shortlist;
  - why the top C5 pick is a combination whose value is in an siRNA;
  - why IMVT-1402, gefurulimab and zilucoplan (true INs) are still "unresolved".
- **Finance Director: no.** No valuation number was produced, and the hand-built config needs company balance-sheet inputs the assumptions do not carry.

**Verdict:** the screening gates are safe and generalised to the held-out buyer. The ranking and shortlist are not BD-ready.

**Single biggest remaining problem:** the shortlist ranking puts marketed, unlicensable products and a modality-mixed combination ahead of the actual BD opportunities. It cannot express "partnerable" or flag combination components. Unresolved true-INs then depend entirely on a human who is absent.

## Totals
- Commands run: about 62 (both parts, including research and guard tests).
- Manual workarounds: 3:
  - renamed `market` to `market_model`;
  - located `idflag:` ids in `identity.json`;
  - web research for 4 proposals.
- Unresolved: 12 (Part 1) and 11 (Part 2).
- Human steps NOT COMPLETED:
  - 7 proposal confirmations;
  - 4 identity resolutions per part;
  - all finalist approvals (17 candidates listed);
  - all valuation selections.
- Wall time: about 4.5 min of tool time; imports dominated (36 s each).
