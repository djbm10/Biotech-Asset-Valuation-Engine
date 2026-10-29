# AI-SIMULATED / INTERNAL DEVELOPMENT — frozen analyst re-test, cycle A3

Date: 2026-10-28 (runs executed 2026-10-28/29 local clock). Analyst: AI subagent (reviewer kind AI_PREPARED). Nothing here is human validation; Gate H and Gate B stay open. All human-only steps (finalist approval, finding confirmation, valuation selection) are **NOT COMPLETED BY HUMAN**.

Exposure statement: read only docs/dealscreen/README.md, ANALYST_ASSIGNMENT.md, CLI --help, examples/dealscreen_real/{buyer_*.yaml, valuation_assumptions_hypothetical.yaml, landscape_fcrn_gmg_v2.csv (header+2 rows directly; rest via tool outputs)} and workspace outputs. reference_manual_assessment.csv, src/, tests/, other research/ and git history were NOT opened. The README *mentions* paths under research/ (FINANCIAL_AUDIT.md, dealscreen_real_v1/REPORT.md); not opened. One WebFetch (CT.gov NCT04963270) — returned no target sentence, so no fact was proposed from it.

## Action log (exact commands; TMPDIR=$HOME/.cache/dealscreen_suite; B=.venv/bin/bve-dealscreen; E=examples/dealscreen_real)
1. `$B import --workspace ~/.cache/analyst_sim_A3/fcrn --landscape $E/landscape_fcrn_gmg_v2.csv --profile $E/profile_public_landscape_v2.yaml --buyer $E/buyer_fcrn_gmg.yaml --identity-authority` → 40 read/40 imported/0 rejected; 4 identity flags. 31 s incl. screen.
2. `$B screen --workspace …/fcrn` → **6 eligible / 12 unresolved / 22 excluded** (excluded: target 18, phase 2, modality 2).
3. `$B queue --workspace …/fcrn` (same 12 + 4 flags).
4. `$B research --workspace …/fcrn --provider offline:$E/evidence_library_public.json --unresolved` → 1 finding: IMVT-1402 target=FCGRT, quote "The Company is pursuing a broad anti-FcRn strategy based on its lead asset, IMVT-1402." (Immunovant 10-K). **Confirmation NOT COMPLETED BY HUMAN.**
5. Same import/screen with `$E/buyer_c5_gmg_heldout.yaml` into …/c5 → **4 eligible / 12 unresolved / 24 excluded**.
6. `$B decide … --action APPROVE_FINALIST --new-state APPROVED --reviewer-kind AI_PREPARED` → correctly REFUSED ("approval needs a human analyst"). Then 6× `--new-state CANDIDATE_NOT_APPROVED` (RW-03, 04, 06, 05, 09, 08) → recorded dec:00001–00006.
7. `$B value-config --asset RW-08|RW-05|RW-04|RW-03 --assumptions $E/valuation_assumptions_hypothetical.yaml --out …/val/<id>.yaml` → RW-08 written (PREVIEW); RW-05 REFUSED (missing price, ytp, patent life, trials, royalty); RW-04/RW-03 REFUSED (commercial-stage; pre-approval rNPV not applicable). Also `--deal license` for RW-08.
8. `bve-dealscreen-value --config …/val/RW-08.yaml --output-json …/RW-08.json --n-sims 5000 --seed 42` and the `_lic` variant; 9 sensitivity configs (copied YAML, one field edited) at n-sims 2000 seed 42.
9. `$B export --out …/fcrn/deliverables/dealscreen.xlsx [--replace-own]`, `$B memo --out …/bd_memo.md`.

## Part 1 — S&E regression

### Task A (landscape)
40 public programs, all imported; v2 CSV leaves Target/Mechanism/Modality **blank** for several well-characterised molecules (IMVT-1402, gefurulimab/ALXN1720, claseprubart, empasiprubart, satralizumab, telitacicept, povetacicept, NMD670, SHR-2173, cizutamig, CABA-201). These blanks, not the engine, drive 10/12 UNRESOLVED.

### Task B — FcRn buyer call table (tool output order; Rank = rank within disposition, preference key [≥pref phase, active, stage, n_trials, capability modality])
|#|ID|Program|Target|Mechanism|Modality|Phase|Disp|Rank|Gates (non-PASS)|Rights|
|-|-|-|-|-|-|-|-|-|-|-|
|1|RW-39|Cizutamig|||Antibody|Phase 1|EXCLUDED|None [0, 1, 2, 1, 1]|expression=UNKNOWN; mechanism_direction=UNKNOWN; phase_constraint=FAIL|UNKNOWN|
|2|RW-08|IMVT-1402||||Phase 3|UNRESOLVED|5 [1, 1, 4, 1, 0]|expression=UNKNOWN; required=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|3|RW-28|Iscalimab (CFZ533)|CD40|CD40 inhibitor|Antibody|Phase 2|EXCLUDED|None [0, 0, 3, 1, 1]|expression=FAIL|UNKNOWN|
|4|RW-22|Inebilizumab|CD19|CD19 binding agent|Antibody|Phase 3|EXCLUDED|None [1, 1, 4, 2, 1]|expression=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|5|RW-02|Efgartigimod alfa and hyaluronidase (SC)|FCGRT|FCGRT antagonist|Protein|Marketed|UNRESOLVED|7 [1, 0, 6, 7, 0]|required=UNKNOWN|UNKNOWN|
|6|RW-01|Efgartigimod alfa (IV)|FCGRT|FCGRT antagonist|Protein|Marketed|UNRESOLVED|6 [1, 0, 6, 17, 0]|required=UNKNOWN|UNKNOWN|
|7|RW-30|Satralizumab|||Antibody|Phase 3|UNRESOLVED|8 [1, 0, 4, 1, 1]|expression=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|8|RW-18|Iptacopan|CFB|CFB inhibitor|Small molecule|Phase 3|EXCLUDED|None [1, 1, 4, 1, 0]|expression=FAIL; required=FAIL|UNKNOWN|
|9|RW-05|Batoclimab|FCGRT|FCGRT inhibitor|Antibody|Phase 3|ELIGIBLE|4 [1, 0, 4, 1, 1]||UNKNOWN|
|10|RW-36|CABA-201||||Phase 1/2|EXCLUDED|None [0, 1, 2, 1, 0]|expression=UNKNOWN; required=UNKNOWN; mechanism_direction=UNKNOWN; phase_constraint=FAIL|UNKNOWN|
|11|RW-21|Empasiprubart|||Antibody|Phase 2|UNRESOLVED|9 [0, 1, 3, 2, 1]|expression=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|12|RW-38|SHR-2173||||Phase 2|UNRESOLVED|12 [0, 1, 3, 1, 0]|expression=UNKNOWN; required=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|13|RW-16|ALXN1720|||Antibody|Phase 3|UNRESOLVED|3 [1, 1, 4, 1, 1]|expression=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|14|RW-12|Eculizumab-aagh (EPYSQLI)|C5|C5 inhibitor|Antibody|Marketed|EXCLUDED|None [1, 0, 6, 0, 1]|expression=FAIL|UNKNOWN|
|15|RW-37|Anitocabtagene autoleucel|BCMA||Gene|Phase 1|EXCLUDED|None [0, 1, 2, 1, 0]|expression=FAIL; required=UNKNOWN; mechanism_direction=UNKNOWN; phase_constraint=FAIL|UNKNOWN|
|16|RW-11|Eculizumab-aeeb (BKEMV)|C5|C5 inhibitor|Antibody|Marketed|EXCLUDED|None [1, 0, 6, 0, 1]|expression=FAIL|UNKNOWN|
|17|RW-10|Eculizumab|C5|C5 inhibitor|Antibody|Marketed|EXCLUDED|None [1, 0, 6, 5, 1]|expression=FAIL|UNKNOWN|
|18|RW-23|Rituximab (investigator-sponsored)|MS4A1|MS4A1 binding agent|Antibody|Phase 3|EXCLUDED|None [1, 1, 4, 8, 1]|expression=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|19|RW-19|Vemircopan (ALXN2050)|||Small molecule|Phase 2|EXCLUDED|None [0, 0, 3, 1, 0]|expression=UNKNOWN; required=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|20|RW-27|Povetacicept|||Protein|Phase 2|UNRESOLVED|11 [0, 1, 3, 1, 0]|expression=UNKNOWN; required=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|21|RW-32|Remibrutinib|||Small molecule|Phase 3|EXCLUDED|None [1, 1, 4, 1, 0]|expression=UNKNOWN; required=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|22|RW-40|NMD670||||Phase 2|UNRESOLVED|10 [0, 1, 3, 1, 0]|expression=UNKNOWN; required=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|23|RW-04|Nipocalimab|FCGRT|FCGRT antagonist|Antibody|Marketed|ELIGIBLE|2 [1, 0, 6, 5, 1]||UNKNOWN|
|24|RW-07|RVT-1401|FCGRT|FCGRT inhibitor|Antibody|Phase 2|ELIGIBLE|6 [0, 0, 3, 1, 1]||UNKNOWN|
|25|RW-29|Belimumab|TNFSF13B|TNFSF13B inhibitor|Antibody|Phase 2|EXCLUDED|None [0, 0, 3, 1, 1]|expression=FAIL; therapeutic_area=UNKNOWN; indication=UNKNOWN|UNKNOWN|
|26|RW-26|Telitacicept|||Protein|Phase 4|UNRESOLVED|1 [1, 1, 6, 7, 0]|expression=UNKNOWN; required=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|27|RW-31|Tocilizumab (investigator-sponsored)|IL6R|IL6R inhibitor|Antibody|Phase 2/3|EXCLUDED|None [0, 1, 3, 2, 1]|expression=FAIL|UNKNOWN|
|28|RW-13|Ravulizumab|C5|C5 inhibitor|Antibody|Marketed|EXCLUDED|None [1, 0, 6, 4, 1]|expression=FAIL|UNKNOWN|
|29|RW-25|Mezagitamab (TAK-079)|CD38|CD38 binding agent|Antibody|Phase 2|EXCLUDED|None [0, 0, 3, 1, 1]|expression=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|30|RW-20|Claseprubart||||Phase 3|UNRESOLVED|2 [1, 1, 4, 2, 0]|expression=UNKNOWN; required=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|31|RW-09|Orilanolimab (ALXN1830)|FCGRT|FCGRT antagonist|Antibody|Phase 2|ELIGIBLE|5 [0, 0, 3, 1, 1]||UNKNOWN|
|32|RW-33|Tolebrutinib|BTK|BTK inhibitor|Small molecule|Phase 3|EXCLUDED|None [1, 0, 4, 1, 0]|expression=FAIL; required=FAIL|UNKNOWN|
|33|RW-35|KYV-101|CD19||CAR-T|Phase 2/3|EXCLUDED|None [0, 1, 3, 1, 0]|expression=FAIL; required=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|34|RW-24|Ublituximab|MS4A1|MS4A1 binding agent|Antibody|Phase 2|EXCLUDED|None [0, 1, 3, 1, 1]|expression=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|35|RW-15|Gefurulimab|||Antibody|Phase 3|UNRESOLVED|4 [1, 1, 4, 1, 1]|expression=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|36|RW-03|Rozanolixizumab|FCGRT|FCGRT inhibitor|Antibody|Phase 4|ELIGIBLE|1 [1, 1, 6, 10, 1]||UNKNOWN|
|37|RW-06|HBM9161|FCGRT|FCGRT inhibitor|Antibody|Phase 3|ELIGIBLE|3 [1, 0, 4, 3, 1]||UNKNOWN|
|38|RW-34|Descartes-08|BCMA||CAR-T|Phase 3|EXCLUDED|None [1, 1, 4, 3, 0]|expression=FAIL; required=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|39|RW-14|Zilucoplan|C5|C5 inhibitor|Protein|Marketed|EXCLUDED|None [1, 0, 6, 8, 0]|expression=FAIL; required=UNKNOWN|UNKNOWN|
|40|RW-17|Pozelimab + Cemdisiran|C5|C5 inhibitor|Antibody|Phase 3|EXCLUDED|None [1, 1, 4, 1, 0]|expression=FAIL; required=UNKNOWN|UNKNOWN|

AI scientific check (FcRn buyer):
- All 22 EXCLUDED calls are scientifically correct (C5, CD19, CD20, CD38, CD40, IL6R, BAFF, CFB, BTK, CAR-T, phase-1 programs). **0 false exclusions.**
- 6 ELIGIBLE are all real anti-FcRn antibodies — correct — but only **4 distinct molecules**: Batoclimab (RW-05), RVT-1401 (RW-07) and HBM9161 (RW-06) are one molecule. Flags are raised and the memo warns; funnel/memo headline "6 scientifically eligible" still counts three times.
- RW-07 RVT-1401 is labelled Phase 2 though the molecule is Phase 3 (via RW-05/06) — rank 6 is a record artefact.
- RW-09 orilanolimab: eligible is fine; development discontinued (memo says "verify").
- UNRESOLVED efgartigimod IV/SC (modality "Protein"; molecule is an IgG1 Fc fragment, not mAb/bispecific/fusion): UNKNOWN is defensible, but the market-leading FcRn blocker is not eligible for an "antibody-based FcRn" buyer — needs a reviewed synonym (Fc fragment) decision. Friction.
- UNRESOLVED IMVT-1402 is truly FcRn/Phase 3; target finding proposed, modality and mechanism still blank, so one confirmation will not make it eligible.
- UNRESOLVED satralizumab (IL-6R), claseprubart/empasiprubart (C2), gefurulimab/ALXN1720 (C5), telitacicept/povetacicept (BAFF/APRIL), NMD670 (ClC-1 small molecule): all should be EXCLUDED scientifically; UNRESOLVED is the correct *engine* answer on blank data, but the queue ranks Telitacicept #1 and IMVT-1402 #5 — the work queue is ordered by phase/trial count, not likelihood of fit.
- Rank order among eligible (Rozanolixizumab 1 [10 trials], Nipocalimab 2 [5], HBM9161 3, Batoclimab 4 [inactive], Orilanolimab 5, RVT-1401 6) is fully explainable from the key shown in the workbook Screening sheet.

### Task B — held-out C5 buyer call table
|#|ID|Program|Target|Mechanism|Modality|Phase|Disp|Rank|Gates (non-PASS)|Rights|
|-|-|-|-|-|-|-|-|-|-|-|
|1|RW-39|Cizutamig|||Antibody|Phase 1|EXCLUDED|None [0, 1, 2, 1, 1]|expression=UNKNOWN; mechanism_direction=UNKNOWN; phase_constraint=FAIL|UNKNOWN|
|2|RW-08|IMVT-1402||||Phase 3|UNRESOLVED|5 [1, 1, 4, 1, 0]|expression=UNKNOWN; required=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|3|RW-28|Iscalimab (CFZ533)|CD40|CD40 inhibitor|Antibody|Phase 2|EXCLUDED|None [0, 0, 3, 1, 1]|expression=FAIL|UNKNOWN|
|4|RW-22|Inebilizumab|CD19|CD19 binding agent|Antibody|Phase 3|EXCLUDED|None [1, 1, 4, 2, 1]|expression=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|5|RW-02|Efgartigimod alfa and hyaluronidase (SC)|FCGRT|FCGRT antagonist|Protein|Marketed|EXCLUDED|None [1, 0, 6, 7, 0]|expression=FAIL; required=UNKNOWN|UNKNOWN|
|6|RW-01|Efgartigimod alfa (IV)|FCGRT|FCGRT antagonist|Protein|Marketed|EXCLUDED|None [1, 0, 6, 17, 0]|expression=FAIL; required=UNKNOWN|UNKNOWN|
|7|RW-30|Satralizumab|||Antibody|Phase 3|UNRESOLVED|8 [1, 0, 4, 1, 1]|expression=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|8|RW-18|Iptacopan|CFB|CFB inhibitor|Small molecule|Phase 3|EXCLUDED|None [1, 1, 4, 1, 0]|expression=FAIL; required=FAIL|UNKNOWN|
|9|RW-05|Batoclimab|FCGRT|FCGRT inhibitor|Antibody|Phase 3|EXCLUDED|None [1, 0, 4, 1, 1]|expression=FAIL|UNKNOWN|
|10|RW-36|CABA-201||||Phase 1/2|EXCLUDED|None [0, 1, 2, 1, 0]|expression=UNKNOWN; required=UNKNOWN; mechanism_direction=UNKNOWN; phase_constraint=FAIL|UNKNOWN|
|11|RW-21|Empasiprubart|||Antibody|Phase 2|UNRESOLVED|9 [0, 1, 3, 2, 1]|expression=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|12|RW-38|SHR-2173||||Phase 2|UNRESOLVED|12 [0, 1, 3, 1, 0]|expression=UNKNOWN; required=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|13|RW-16|ALXN1720|||Antibody|Phase 3|UNRESOLVED|3 [1, 1, 4, 1, 1]|expression=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|14|RW-12|Eculizumab-aagh (EPYSQLI)|C5|C5 inhibitor|Antibody|Marketed|ELIGIBLE|3 [1, 0, 6, 0, 1]||UNKNOWN|
|15|RW-37|Anitocabtagene autoleucel|BCMA||Gene|Phase 1|EXCLUDED|None [0, 1, 2, 1, 0]|expression=FAIL; required=UNKNOWN; mechanism_direction=UNKNOWN; phase_constraint=FAIL|UNKNOWN|
|16|RW-11|Eculizumab-aeeb (BKEMV)|C5|C5 inhibitor|Antibody|Marketed|ELIGIBLE|4 [1, 0, 6, 0, 1]||UNKNOWN|
|17|RW-10|Eculizumab|C5|C5 inhibitor|Antibody|Marketed|ELIGIBLE|1 [1, 0, 6, 5, 1]||UNKNOWN|
|18|RW-23|Rituximab (investigator-sponsored)|MS4A1|MS4A1 binding agent|Antibody|Phase 3|EXCLUDED|None [1, 1, 4, 8, 1]|expression=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|19|RW-19|Vemircopan (ALXN2050)|||Small molecule|Phase 2|EXCLUDED|None [0, 0, 3, 1, 0]|expression=UNKNOWN; required=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|20|RW-27|Povetacicept|||Protein|Phase 2|UNRESOLVED|11 [0, 1, 3, 1, 0]|expression=UNKNOWN; required=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|21|RW-32|Remibrutinib|||Small molecule|Phase 3|EXCLUDED|None [1, 1, 4, 1, 0]|expression=UNKNOWN; required=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|22|RW-40|NMD670||||Phase 2|UNRESOLVED|10 [0, 1, 3, 1, 0]|expression=UNKNOWN; required=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|23|RW-04|Nipocalimab|FCGRT|FCGRT antagonist|Antibody|Marketed|EXCLUDED|None [1, 0, 6, 5, 1]|expression=FAIL|UNKNOWN|
|24|RW-07|RVT-1401|FCGRT|FCGRT inhibitor|Antibody|Phase 2|EXCLUDED|None [0, 0, 3, 1, 1]|expression=FAIL|UNKNOWN|
|25|RW-29|Belimumab|TNFSF13B|TNFSF13B inhibitor|Antibody|Phase 2|EXCLUDED|None [0, 0, 3, 1, 1]|expression=FAIL; therapeutic_area=UNKNOWN; indication=UNKNOWN|UNKNOWN|
|26|RW-26|Telitacicept|||Protein|Phase 4|UNRESOLVED|1 [1, 1, 6, 7, 0]|expression=UNKNOWN; required=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|27|RW-31|Tocilizumab (investigator-sponsored)|IL6R|IL6R inhibitor|Antibody|Phase 2/3|EXCLUDED|None [0, 1, 3, 2, 1]|expression=FAIL|UNKNOWN|
|28|RW-13|Ravulizumab|C5|C5 inhibitor|Antibody|Marketed|ELIGIBLE|2 [1, 0, 6, 4, 1]||UNKNOWN|
|29|RW-25|Mezagitamab (TAK-079)|CD38|CD38 binding agent|Antibody|Phase 2|EXCLUDED|None [0, 0, 3, 1, 1]|expression=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|30|RW-20|Claseprubart||||Phase 3|UNRESOLVED|2 [1, 1, 4, 2, 0]|expression=UNKNOWN; required=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|31|RW-09|Orilanolimab (ALXN1830)|FCGRT|FCGRT antagonist|Antibody|Phase 2|EXCLUDED|None [0, 0, 3, 1, 1]|expression=FAIL|UNKNOWN|
|32|RW-33|Tolebrutinib|BTK|BTK inhibitor|Small molecule|Phase 3|EXCLUDED|None [1, 0, 4, 1, 0]|expression=FAIL; required=FAIL|UNKNOWN|
|33|RW-35|KYV-101|CD19||CAR-T|Phase 2/3|EXCLUDED|None [0, 1, 3, 1, 0]|expression=FAIL; required=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|34|RW-24|Ublituximab|MS4A1|MS4A1 binding agent|Antibody|Phase 2|EXCLUDED|None [0, 1, 3, 1, 1]|expression=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|35|RW-15|Gefurulimab|||Antibody|Phase 3|UNRESOLVED|4 [1, 1, 4, 1, 1]|expression=UNKNOWN; mechanism_direction=UNKNOWN|UNKNOWN|
|36|RW-03|Rozanolixizumab|FCGRT|FCGRT inhibitor|Antibody|Phase 4|EXCLUDED|None [1, 1, 6, 10, 1]|expression=FAIL|UNKNOWN|
|37|RW-06|HBM9161|FCGRT|FCGRT inhibitor|Antibody|Phase 3|EXCLUDED|None [1, 0, 4, 3, 1]|expression=FAIL|UNKNOWN|
|38|RW-34|Descartes-08|BCMA||CAR-T|Phase 3|EXCLUDED|None [1, 1, 4, 3, 0]|expression=FAIL; required=FAIL; mechanism_direction=UNKNOWN|UNKNOWN|
|39|RW-14|Zilucoplan|C5|C5 inhibitor|Protein|Marketed|UNRESOLVED|7 [1, 0, 6, 8, 0]|required=UNKNOWN|UNKNOWN|
|40|RW-17|Pozelimab + Cemdisiran|C5|C5 inhibitor|Antibody|Phase 3|UNRESOLVED|6 [1, 1, 4, 1, 0]|required=UNKNOWN|UNKNOWN|

AI scientific check (C5 buyer):
- ELIGIBLE: eculizumab, ravulizumab, eculizumab-aagh (EPYSQLI), eculizumab-aeeb (BKEMV) — correct C5 mAbs. Two are biosimilars with 0 registered trials; scientifically eligible but low BD relevance (rank 3/4 explained by trial count 0).
- **Zilucoplan (RW-14) UNRESOLVED on modality**: it is a marketed macrocyclic **peptide** C5 inhibitor in gMG, and this buyer explicitly allows PEPTIDE. Landscape text "Protein" defeats it. For this buyer the single most relevant non-Alexion asset is missing from the eligible list. Severity: wrong decision (outcome-level), caused by vendor text + no synonym layer; the gate itself did not FAIL it.
- **Gefurulimab / ALXN1720** (C5 bispecific VHH, Phase 3 in gMG) UNRESOLVED because Target is blank — the main pipeline C5 opportunity is not eligible; 2 records for one molecule (flag raised).
- Pozelimab + cemdisiran UNRESOLVED on modality (combination mAb + siRNA): correct to hold for review.
- Iptacopan (CFB), vemircopan (CFD), all FcRn and B-cell programs EXCLUDED: correct. **0 false exclusions, 0 false eligibles.**
- Identity flags for batoclimab now show [EXCLUDED] — correctly buyer-relative.

### Task E — shortlist (AI_PREPARED candidates, NOT APPROVED; human approval NOT COMPLETED BY HUMAN)
FcRn: Rozanolixizumab, Nipocalimab, Batoclimab-family (RW-05/06/07 counted once), IMVT-1402 (pending target/modality/mechanism confirmation), Orilanolimab (inactive), Efgartigimod IV/SC (pending modality decision). Recorded 6 candidates via `CANDIDATE_NOT_APPROVED`; memo renders them correctly as "prepared by an AI assistant, NOT approved".
C5 (not recorded): ravulizumab, eculizumab, zilucoplan (pending modality), gefurulimab (pending target), pozelimab+cemdisiran (pending modality); biosimilars de-prioritised.

## Part 2 — BD Finance (preliminary valuation)

Only **RW-08 IMVT-1402** has a READY input block. RW-05 refused (incomplete inputs — correct). RW-04 nipocalimab and RW-03 rozanolixizumab refused as commercial-stage — correct and well explained, but it means **no marketed FcRn asset (most of the eligible list) can be valued at all**. Valuation through `bve-dealscreen value` impossible without human selection (by design); I used `value-config` preview + `bve-dealscreen-value`.

### RW-08 base and deal (hypothetical inputs, $M, seed 42)
| Run | P(approval) | Peak sales | "Gross revenue PV" | Prob-adj "revenue" PV | Cost PV | rNPV base | Bull | Bear |
|---|---|---|---|---|---|---|---|---|
| Asset-holder (5000 sims) | 0.585 | 320 | 604 | 353 | 189.8 | 163 | 736 | −143 |
| License (upfront 500, 15% royalty, 400 approval milestone payable) | 0.585 | 320 | 457 | 267 | 857.4 | −590 | −256 | −720 |
MC: mean 177, median 148, P(>0)=0.91, p5 −25, p95 470.

### Reproduction checks
| Number | Hand reproduction | Status |
|---|---|---|
| P(approval) 0.585 | 0.65 × 0.90 | ✔ |
| Phase 3 cost PV 177.54 | $200M uniform over 2.5y @10% | ✔ |
| BLA cost PV 18.78 gross / 12.21 weighted | 25 × 1.1^-~3 ; × 0.65 | ✔ |
| Total cost PV 189.8 | 177.54+12.21 | ✔ |
| rNPV 163 | 353 − 189.8 = 163.2 | ✔ arithmetic, but see D2 |
| Peak sales 320 | 20,000 × $200k × 10% = **400** | ✘ unexplained ×0.80. Setting `compliance_rate: 1.0` still gives 320 → the haircut is not the visible compliance field (D1) |
| "Gross revenue PV" 604 | my PV of revenue (12y, 6y linear ramp, launch t=3.5) ≈ 1,100–1,150; after-tax EBIT PV ≈ 507–532 | ✘ neither; label "revenue" appears to be a margin/after-tax cash flow (D2) |
| License cost PV 857.4 | 189.8 + 500 + 400×0.585×1.1^-3.5 (=167.6) | ✔ |
| License value line 353→267 (−86) | 15% royalty on revenue, tax-affected | ~✔ plausible |

### Sensitivities (copied config, one change; base 163)
| Change | rNPV | Bull | Bear | Note |
|---|---|---|---|---|
| discount 8% | 242 | 933 | −133 | |
| discount 12% | 103 | 581 | −149 | |
| penetration 5% | −13 | 278 | −174 | peak 160 |
| penetration 15% | 340 | 1,195 | −112 | peak 480 |
| price $150k | 75 | 507 | −159 | |
| Ph3 PoS 0.50 | 85 | 528 | −156 | P=0.45 |
| patent life 1y | −42 | 186 | −177 | revenue PV still 252 → undisclosed post-LOE tail |
| compliance_rate 1.0 | 163 | 736 | −143 | no effect (D1) |
| price $1 | −190 | −181 | −205 | bear≠base with zero revenue: scenarios shock costs/timing too |

Buyer perspective: the CLI prints "asset-holder rNPV with no deal terms (not a buyer's deal NPV)" and for the license run lists the terms — clear. The buyer license NPV (−590) is coherent: buyer pays $500M upfront for an asset whose standalone rNPV is $163M and carries 100% of development cost (`cdev_cost_share=1.0`). From a buyer's view it shows these hypothetical terms destroy value; break-even upfront ≈ −90 (i.e. none). Note IMVT-1402 is owned by Immunovant (licensed from HanAll) — the assumptions file itself says it is not known to be available; the tool does not surface this in the valuation output.

## Task G — deliverables
Workbook (9 sheets) and memo exported. Memo is honest about UNVALIDATED status, rights UNKNOWN, AI candidates not approved, identity flags. Would a Head of BD accept it? As a screening triage note, yes with caveats. Would a Finance Director? **No**: no valuation is in the deliverables (none can be run without human selection), the only valuable asset's peak sales cannot be reproduced from its inputs, and the assumptions table carries invented provenance.

## Defect list
| # | Severity | Defect | Evidence |
|---|---|---|---|
| D1 | **Blocker** (finance) | Peak sales 320 ≠ patients×price×penetration (400); ×0.8 haircut not traceable to any input; `compliance_rate` in output inputs shows 0.8 but setting it to 1.0 changes nothing | RW-08.json `.outputs.rnpv.peak_sales_millions=320`; s_comp1.json identical |
| D2 | **Wrong decision risk** | `gross_revenue_pv_millions`/`prob_adj_revenue_pv_millions` are not revenue PV (604 vs ~1,100 hand calc); rNPV = "prob-adj revenue PV" − cost PV, so the label implies opex/tax are missing or the field is mislabelled — a reader cannot tell | RW-08.json; 353−189.8=163.2 |
| D3 | **Wrong decision risk** | `assumptions.key_assumptions` attaches authoritative-looking sources to HYPOTHETICAL inputs ("Damodaran…", "SEER, IQVIA, company KOL slides", "See pricing_refs.py comp table", "SSR Health / CMS") and lists "Gross-to-Net Discount 30%" and "POS Methodology=Heuristic log-odds model" although price_basis=net, gross_to_net_rate=None, apply_pos_model=false | RW-08.json `.assumptions` |
| D4 | Friction | Sensitivity tornado: "Peak Sales ±30%" and "Peak Penetration ±30%" identical (57/269) — redundant; "Gross-to-Net ±10pp" varies an input not used in base; "Competition (+1/+2)" both values below base (57/110) — low/high labels misleading | RW-08.json `.outputs.sensitivities` |
| D5 | Friction | Deal terms absent from valuation.json `inputs` (`deal_economics: null`) and `net_ownership=1.0` reported under a 15% royalty; deal only visible on the console perspective line | RW-08_lic.json |
| D6 | Friction | Undisclosed post-patent tail: 1-year patent life still yields revenue PV 252 | s_pat1.json |
| D7 | Wrong decision (outcome) | C5 buyer: zilucoplan (marketed peptide, buyer allows PEPTIDE) not eligible because vendor modality "Protein"; gefurulimab not eligible because target blank | c5 table rows 39, 35, 13 |
| D8 | Friction | Funnel/memo count "6 eligible" includes 3 records of one molecule (batoclimab); flags raised but headline not de-duplicated | memo Funnel line |
| D9 | Friction | Unresolved queue ordered by preference key, so non-target programs (telitacicept #1, claseprubart #2) precede IMVT-1402 (#5) | `queue` output |
| D10 | Blocker (product scope) | Marketed/Phase 4 programs cannot be valued at all; 4 of 6 FcRn and all 4 C5 eligible are commercial-stage | value-config REFUSED RW-03/RW-04 |
| D11 | Cosmetic | Memo with no finalists printed "Finalists: 0 ( reviewers)" | first memo run |
| D12 | Cosmetic | Workbook "Valuation Inputs" header says "for the synthetic demo" on the real landscape | dealscreen.xlsx Valuation Inputs A1 |
| D13 | Cosmetic | Linear-uptake UserWarning (pydantic) printed on every valuation run | console |

Working correctly (regression passes): AI approval refused; CANDIDATE_NOT_APPROVED labelling in memo/workbook; incomplete and commercial-stage inputs refused with reasons; rights never AVAILABLE without statement (all 40 UNKNOWN); identity flags buyer-relative; perspective line explicit; cost PVs and license cost reproduce.

## Verdict
S&E screening: **PASS as regression** (0 false eligible, 0 false excluded for both buyers; rank explainable), limited by landscape blanks that leave the most relevant pipeline assets (IMVT-1402, gefurulimab) and zilucoplan UNRESOLVED. BD Finance: **FAIL for Finance-Director use** — 1 of 3 attempted programs valuable, its peak sales and "revenue PV" cannot be reproduced from disclosed inputs, and the assumptions table presents fabricated-looking provenance for hypothetical numbers.

## Totals
Programs screened 40×2 buyers. FcRn: 6 E / 12 U / 22 X. C5: 4 E / 12 U / 24 X. Agent findings 1 (unconfirmed). AI candidates recorded 6. Valuations attempted 4 (1 run, 3 refused correctly); valuation runs 11 (base, license, 9 sensitivities). Defects 13: wrong-decision 3 (D2, D3, D7), blocker 2 (D1, D10); friction 5 (D4, D5, D6, D8, D9); cosmetic 3 (D11–D13).
