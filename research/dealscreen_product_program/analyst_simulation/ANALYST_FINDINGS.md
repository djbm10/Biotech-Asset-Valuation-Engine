# AI-SIMULATED / INTERNAL DEVELOPMENT — frozen pre-fix analyst assessment, cycle A1

Date: 2026-10-28. Analyst: AI subagent (roles: S&E analyst, then BD Finance). No human performed or approved any step.
Workspace: `~/.cache/analyst_sim_ws1` (outside repo). `TMPDIR=~/.cache/dealscreen_suite`.

**Rule compliance note.** I read only the allowed files. However, (a) `docs/dealscreen/README.md` itself names `research/dealscreen_real_v1/REPORT.md` and `research/dealscreen_hardening_v1/FINANCIAL_AUDIT.md` (I did not open them), and (b) the `value` crash printed a Python traceback that exposed `src/bve/dealscreen/workspace.py` line numbers and two lines of code. I did not open any src file.

## 1. Action log

| # | task | what I tried (exact command, abbreviated `B=.venv/bin/bve-dealscreen`, `W=~/.cache/analyst_sim_ws1`, `E=examples/dealscreen_real`) | allowed? | outcome | approx s |
|---|---|---|---|---|---|
| 1 | setup | `cat docs/dealscreen/README.md; cat .../ANALYST_ASSIGNMENT.md; ls $E` | yes | read | 2 |
| 2 | A | `cat $E/buyer_fcrn_gmg.yaml $E/profile_public_landscape_v2.yaml $E/valuation_assumptions_hypothetical.yaml` | yes | read | 1 |
| 3 | A | python csv dump of `$E/landscape_fcrn_gmg_v2.csv` (all 40 rows) | yes | reviewed manually | 1 |
| 4 | A | `$B --help`, `import/research/decide/assert/show/queue/screen/value/export/memo --help`, `bve-dealscreen-value --help` | yes | read | 3 |
| 5 | A | `$B import --workspace $W --landscape $E/landscape_fcrn_gmg_v2.csv --profile $E/profile_public_landscape_v2.yaml --buyer $E/buyer_fcrn_gmg.yaml --identity-authority` | yes | 40 read/40 imported/0 rejected; **no identity flags in console output** | 28 |
| 6 | A | `cat $W/identity.json` | yes (workspace) | 4 flags: batoclimab x3 records, gefurulimab/ALXN1720 | 1 |
| 7 | B | `$B screen --workspace $W` | yes | 4 eligible / 14 unresolved / 22 excluded | 0.4 |
| 8 | B | `$B queue --workspace $W` | yes | same 14 list | 0.4 |
| 9 | B | python table over `$W/screening.json` | yes | per-gate table (basis of §4) | 1 |
| 10 | B | `$B show --workspace $W --asset RW-06` | yes | HBM9161 ELIGIBLE, full detail | 1 |
| 11 | B | `$B show` for RW-05, RW-29, RW-01, RW-04 (non-PASS gates) | yes | see §3B | 2 |
| 12 | B | python facts dump for 5 assets from screening.json | yes | activity/ranking anomalies | 1 |
| 13 | C | `$B research --workspace $W --provider offline:$E/evidence_library_public.json --unresolved` | yes | 1 finding (IMVT-1402 target, Immunovant 10-K) | 28 |
| 14 | C | `$B research --workspace $W --provider ctgov --unresolved` | yes | 39 findings, ~all are phase; 0 targets; 1 "mechanism" that is a trial title | 8 |
| 15 | C | `curl clinicaltrials.gov/api/v2/studies/{NCT06607627,NCT07647510,NCT07039916}` | yes (public) | registry text names no target for gefurulimab/claseprubart/IMVT-1402 | 3 |
| 16 | C/D | WebFetch Immunovant 10-K `sec.gov/.../imvt-20251231.htm` | yes (public) | verbatim quotes: FcRn inhibitor; HanAll license incl. U.S. assigned to ISG; batoclimab rights may return to HanAll | 20 |
| 17 | C | `$B assert --asset RW-08 --field target --value FCGRT --source-url <10-K> --quote "a potentially best-in-class inhibitor of the neonatal fragment crystallizable receptor" --reviewer-kind AI_PREPARED ...` (+ mechanism, us_rights_holder) | yes | **REFUSED** x3 (AI cannot assert) — correct policy; NOT COMPLETED BY HUMAN | 1 |
| 18 | C | `$B decide --action CONFIRM_FINDING --subject RW-08 --field target --reviewer-kind AI_PREPARED` | yes | REFUSED; NOT COMPLETED BY HUMAN | 1 |
| 19 | E | `$B decide --action APPROVE_FINALIST --new-state APPROVED --reviewer-kind AI_PREPARED` RW-03/04/06/07, `SELECT_FOR_VALUATION RW-08`, APPROVE RW-10 (negative test) | yes | all REFUSED (correct) | 2 |
| 20 | E | `$B decide --action APPROVE_FINALIST --new-state CANDIDATE_NOT_APPROVED --reviewer-kind AI_PREPARED` for RW-03,04,01,02,08,06,05 | yes | recorded dec:00001-7 | 2 |
| 21 | F | `$B value --workspace $W --assumptions $E/valuation_assumptions_hypothetical.yaml --n-sims 2000` | yes | **crash: FileNotFoundError .../valuation/valuations.json** (nothing selected) | 2 |
| 22 | F | workaround: built `$W/manual_val/rw08.yaml` from RW-08 block; `bve-dealscreen-value --config ... --output-json ...` | yes | validation error: needs asset.id/name/indication, company cash/shares | 3 |
| 23 | F | retry with placeholder company (cash 0, shares 1) + `deal_options` at top level | yes (workaround) | rNPV base 103 / bull 581 / bear −149 $M; **discount_rate 0.10 ignored (0.12 used); deal_options silently ignored** | 10 |
| 24 | F | python dump of rw08.json key outputs | yes | P=0.585, peak 320 | 1 |
| 25 | G | `$B screen; $B export --out $W/deliverables/ds.xlsx; $B memo --out $W/deliverables/memo.md`; openpyxl read | yes | see §3G | 6 |

Totals: **25 logged commands (~33 tool invocations)**, **4 manual workarounds** (manual identity reasoning; external web/CT.gov diligence outside the tool; hand-built valuation config; placeholder company block), **14 programs UNRESOLVED by tool (my view: 2 truly open)**, **human steps not completed: 3 assertions + 1 finding confirmation + finalist approval + selection for valuation + valuation sign-off = 7 NOT COMPLETED BY HUMAN**.

## 3. Per task

### A. Import & record quality
Found:
- Import is clean mechanically (40/40), but row quality issues are not surfaced at import:
  - **Same molecule under three rows:** RW-05 Batoclimab (aliases incl. IMVT-1401), RW-07 RVT-1401 (former Roivant code for batoclimab), RW-06 HBM9161 (Harbour BioMed's Greater China code for batoclimab). Identity flags exist in `identity.json` (PROPOSED_MERGE RW-05/RW-07; SAME_MOLECULE_DIFFERENT_HOLDER with RW-06) but `import` prints nothing about them and `queue` doesn't list them.
  - **RW-15 Gefurulimab = RW-16 ALXN1720** (correctly flagged PROPOSED_MERGE).
  - **RW-01 / RW-02** efgartigimod IV vs SC (VYVGART vs VYVGART Hytrulo) — same molecule, distinct products; reasonable to keep separate but one program for BD.
  - RW-10/11/12: eculizumab originator + 2 biosimilars (BKEMV, EPYSQLI) — same molecule, different labelers. Not flagged.
  - RW-17 is a combination (pozelimab + cemdisiran, siRNA) recorded as "Antibody".
  - Typos left verbatim: RW-33 alias "Tolebrutininb", RW-34 alias "Decartes-08", RW-29 "Myasthaenia".
  - RW-03 Rozanolixizumab "Phase 4" though U.S.-marketed (RYSTIGGO) — no U.S. labeler/rights holder row unlike other marketed drugs.
  - RW-26 Telitacicept company = "Vor Biopharma" while trials are RemeGen-sponsored (collaborators listed); company column mixes licensee and sponsor.
  - Company column for marketed products = FDA labeler ("argenx US", "Janssen Biotech, Inc."), not legal owner (argenx SE, J&J).
  - 12 rows have blank target ("Target not stated in the sources used").
- **Distinct assets actually represented: ~33 molecules in 40 rows** (batoclimab ×3, gefurulimab ×2, efgartigimod ×2 products, eculizumab ×3 products). Distinct FcRn molecules: efgartigimod, rozanolixizumab, nipocalimab, batoclimab, IMVT-1402, orilanolimab = **6**.

### B. Screening
- Funnel 4 / 14 / 22. Eligible: Rozanolixizumab, HBM9161, Nipocalimab, RVT-1401.
- **Questionable classifications (misleading):**
  - The same molecule gets three dispositions: RVT-1401 ELIGIBLE, HBM9161 ELIGIBLE, Batoclimab UNRESOLVED (indication UNKNOWN).
  - **Indication gate: "Generalized Myasthenia Gravis" alone → UNKNOWN** (Batoclimab RW-05, Orilanolimab RW-09, Efgartigimod SC RW-02, ALXN1720, Gefurulimab), while "Myasthenia Gravis" → PASS. gMG is a subtype of MG; this is the largest source of avoidable UNRESOLVED (strategy.indication UNKNOWN on 22 assets).
  - **Efgartigimod IV/SC (market-leading FcRn blocker) UNRESOLVED on modality** because vendor modality "Protein" (Fc fragment). Buyer allows FUSION_PROTEIN/antibody-based; an analyst would pass it. Tool can't be corrected by AI.
  - **Activity flag wrong:** `activity=ACTIVE` for rows whose status is "Registry: no recruiting gMG trial (COMPLETED)" with old dates: RVT-1401 (2023-12-20), HBM9161, Belimumab (2017-02-09), Iscalimab (2021), Mezagitamab (2023). Marketed Nipocalimab/efgartigimod = UNKNOWN. This feeds preference rank "active development" — RVT-1401 (dormant code) ranks as an active eligible program.
  - Belimumab RW-29 `strategy.therapeutic_area = FAIL` "conflicts with buyer requirement", though its TA is "Neurology" like every other row which PASS. Unexplained (harmless here because target also FAILs).
  - Unresolved ranking puts Telitacicept (#1), Claseprubart (#2), ALXN1720 (#3) above the FcRn programs: rank driven by phase/trial count, not by fit; these are all non-FcRn.
- **Irrelevant inclusions in the unresolved queue (should be excluded on public knowledge):** Gefurulimab/ALXN1720 (C5), Claseprubart (C1s), Empasiprubart (C2), Telitacicept (TACI-Fc, BLyS/APRIL), Povetacicept (APRIL/BAFF), Satralizumab (IL-6R), NMD670 (ClC-1 small molecule). The tool can't know because target is blank; acceptable as UNKNOWN but it costs analyst time.
- Exclusions all look correct (C5, CD19, CD20, CD38, CD40, BAFF, IL-6R, CFB, BTK, CAR-T, phase-1). Not questionable. Note Zilucoplan (peptide) modality UNKNOWN but excluded on target — correct.

### C. Scientific diligence
- Offline library produced 1 useful finding (IMVT-1402 target, Immunovant 10-K). CT.gov provider produced 39 findings, essentially all `phase`, none resolving the blocking gates (target/modality/indication). One `mechanism` finding for Telitacicept is just a trial title (no direction) — misleading as a "mechanism" finding.
- Verified IMVT-1402 public evidence myself (10-K quote above). Attempts to assert/confirm were REFUSED for AI_PREPARED: **NOT COMPLETED BY HUMAN.** So IMVT-1402 stays UNRESOLVED in the deliverable even though the evidence is in hand.
- Human evidence: tool shows registry IDs and phases but **no efficacy data** (MG-ADL, QMG) anywhere. "Prioritize compelling human evidence" cannot be done in the tool; it ranks by phase/trial count. Known publicly: efgartigimod (ADAPT), rozanolixizumab (MycarinG), nipocalimab (Vivacity-MG3) Phase 3 positive and approved; batoclimab Phase 3 gMG data reported but program deprioritized for IMVT-1402.

### D. Commercial diligence
- U.S. rights status UNKNOWN for all 40 — correctly not assumed available.
- Memo says "A U.S. rights holder is evidenced for 1 of them [eligible]" — that is Nipocalimab's FDA **labeler** (Janssen Biotech) per source text "U.S. labeler per FDA label". Labeler ≠ owner ≠ available rights; the memo sentence invites conflation.
- 10-K (fetched): HanAll licensed batoclimab + IMVT-1402 incl. U.S. to RSG, assigned to Immunovant Sciences GmbH; Immunovant "commenced discussions with HanAll regarding the potential return to HanAll of certain rights for batoclimab". So: batoclimab U.S. rights potentially reverting to HanAll (licensor) — the only plausible *available* asset in the set; HBM9161 = Harbour's Greater-China rights, not U.S.; IMVT-1402 U.S. rights held by Immunovant under HanAll license, not evidently available.
- Marketed FcRn products (argenx, UCB, J&J) — U.S. rights effectively unavailable except via M&A. Tool offers no field to express "marketed by owner; acquisition only".
- Could not enter any of this into the tool (AI assertion refused).

### E. Shortlist — see §4.

### F. Valuation (BD Finance)
- Handoff blocked: no human-approved finalist ⇒ `value` cannot run, and **crashes with a traceback** instead of a "nothing selected" message.
- Workaround via `bve-dealscreen-value` on RW-08 hypothetical inputs: base $103M, bull $581M, bear −$149M; P(approval) 0.585 (=0.65×0.90 ✓); trial cost PV $185M (undiscounted 225 ✓ plausible); peak sales $320M vs my 20,000×$200k×10% = $400M — **20% haircut not explained** in output (likely gross-to-net/other; couldn't reproduce). **Discount rate 0.12 used although I passed 0.10** at top level — silently ignored. **`deal_options` silently ignored** → standalone and "deal" runs identical; the license case ($500M upfront, 15% royalty, $400M milestone) could not be evaluated. Buyer view would obviously be deeply negative (upfront 5× standalone rNPV).
- Methodology applicability: trial-path rNPV is wrong for marketed products (nipocalimab, rozanolixizumab, efgartigimod) — the assumptions file correctly declines RW-04; batoclimab (RW-05) is deliberately incomplete (NOT READY). Only RW-08 is valuable and it's not known available — valuation is academic.
- Required company cash/shares for an asset-level deal valuation is friction; I entered placeholders (0 / 1), flagged.

### G. Deliverables
- Workbook 8 sheets opens fine. **Finalists sheet header says "7 approved finalist(s)"** while every row is `CANDIDATE_NOT_APPROVED / AI_PREPARED` — misleading.
- Valuation sheets empty (expected), but memo has heading "**Preliminary valuations**" followed by nothing — no "none run because no human approval" line.
- Memo candidate list includes batoclimab and HBM9161 as two programs without noting they are the same molecule (identity flag not carried into memo).
- Memo "Investigate next" useful; caveats prominent. Company names are labelers.
- Would I present it to Head of BD? **No** — as a working file only. Funnel numbers (4 eligible) understate the real FcRn set and double-count batoclimab.

## 4. Frozen conclusions

**Distinct FcRn antibody-based assets:** efgartigimod (IV+SC products, argenx), rozanolixizumab (UCB), nipocalimab (J&J), batoclimab (= RVT-1401 = IMVT-1401 = HBM9161; HanAll licensor, Immunovant ex-Asia, Harbour Greater China), IMVT-1402 (HanAll→Immunovant), orilanolimab (Alexion, terminated).

| ID | Name | Tool | My call | Reason |
|---|---|---|---|---|
| RW-01 | Efgartigimod IV | UNRESOLVED (modality) | IN (science) / not available | FcRn Fc-fragment, marketed; modality "Protein" is antibody-based |
| RW-02 | Efgartigimod SC | UNRESOLVED | IN, same program as RW-01 | indication gMG should pass |
| RW-03 | Rozanolixizumab | ELIGIBLE | IN / not available | marketed (RYSTIGGO), UCB |
| RW-04 | Nipocalimab | ELIGIBLE | IN / not available | marketed (IMAAVY), J&J |
| RW-05 | Batoclimab | UNRESOLVED (indication) | IN; most interesting rights story | rights may revert to HanAll (10-K) |
| RW-06 | HBM9161 | ELIGIBLE | same molecule as RW-05 | Greater China licensee; not a U.S. option |
| RW-07 | RVT-1401 | ELIGIBLE | duplicate of RW-05 (old code) | should merge, inactive |
| RW-08 | IMVT-1402 | UNRESOLVED (target) | IN | FcRn per 10-K; Ph3 gMG |
| RW-09 | Orilanolimab | UNRESOLVED (indication) | OUT (terminated) | science fits, development stopped |
| RW-10 | Eculizumab | EXCLUDED | OUT | C5 |
| RW-11 | Eculizumab-aeeb | EXCLUDED | OUT | C5 biosimilar |
| RW-12 | Eculizumab-aagh | EXCLUDED | OUT | C5 biosimilar |
| RW-13 | Ravulizumab | EXCLUDED | OUT | C5 |
| RW-14 | Zilucoplan | EXCLUDED | OUT | C5 peptide |
| RW-15 | Gefurulimab | UNRESOLVED | OUT | C5 (public knowledge; = RW-16) |
| RW-16 | ALXN1720 | UNRESOLVED | OUT | = gefurulimab, C5 |
| RW-17 | Pozelimab+Cemdisiran | EXCLUDED | OUT | C5 |
| RW-18 | Iptacopan | EXCLUDED | OUT | CFB small molecule |
| RW-19 | Vemircopan | EXCLUDED | OUT | factor D small molecule |
| RW-20 | Claseprubart | UNRESOLVED | OUT | C1s |
| RW-21 | Empasiprubart | UNRESOLVED | OUT | C2 |
| RW-22 | Inebilizumab | EXCLUDED | OUT | CD19 |
| RW-23 | Rituximab (IIT) | EXCLUDED | OUT | CD20 |
| RW-24 | Ublituximab | EXCLUDED | OUT | CD20 |
| RW-25 | Mezagitamab | EXCLUDED | OUT | CD38 |
| RW-26 | Telitacicept | UNRESOLVED | OUT | TACI-Fc |
| RW-27 | Povetacicept | UNRESOLVED | OUT | APRIL/BAFF |
| RW-28 | Iscalimab | EXCLUDED | OUT | CD40 |
| RW-29 | Belimumab | EXCLUDED | OUT | BAFF (TA FAIL spurious) |
| RW-30 | Satralizumab | UNRESOLVED | OUT | IL-6R |
| RW-31 | Tocilizumab (IIT) | EXCLUDED | OUT | IL-6R |
| RW-32 | Remibrutinib | EXCLUDED | OUT | BTK SM |
| RW-33 | Tolebrutinib | EXCLUDED | OUT | BTK SM |
| RW-34 | Descartes-08 | EXCLUDED | OUT | CAR-T |
| RW-35 | KYV-101 | EXCLUDED | OUT | CAR-T |
| RW-36 | CABA-201 | EXCLUDED | OUT | CAR-T, Ph1/2 |
| RW-37 | Anito-cel | EXCLUDED | OUT | CAR-T, Ph1 |
| RW-38 | SHR-2173 | UNRESOLVED | UNRESOLVED | target not verified by me |
| RW-39 | Cizutamig | EXCLUDED (phase) | OUT | Ph1 |
| RW-40 | NMD670 | UNRESOLVED | OUT | ClC-1 small molecule (public knowledge, not verified in session) |

Calls not verified with a fetched source in this session (based on prior public knowledge): targets of RW-15/16/20/21/26/27/30/40. Unresolved by me: SHR-2173 (1) plus availability questions for batoclimab.

**Shortlist (AI-prepared, NOT human approved):**
1. Batoclimab (RW-05/06/07 merged) — attractive: Ph3 gMG data, rights possibly reverting to HanAll ⇒ potential U.S. license; risk: Immunovant deprioritized for IMVT-1402, class lipid/albumin effects, crowded class; change: HanAll statement on returned rights.
2. IMVT-1402 — attractive: next-gen, Ph3 gMG; risk: Immunovant holds U.S. rights and is the lead asset — likely unavailable; change: partnering signal.
3. Efgartigimod / 4. Rozanolixizumab / 5. Nipocalimab — science benchmarks; acquisition-only; useful as comparators, not deal targets.
6. SHR-2173 — resolve target first.
Orilanolimab excluded on development status.

**Valuation:** none via the handoff (no human approval; `value` crashed). Workaround RW-08 standalone rNPV $103M base (hypothetical, not reproducible exactly; discount rate and deal block ignored). Batoclimab NOT READY (inputs incomplete by design); marketed programs not methodologically suitable.

## 5. Defect list

| # | Severity | Where | Evidence |
|---|---|---|---|
| 1 | could cause wrong decision | indication gate, RW-05/09/02/15/16 `strategy.indication` | "Generalized Myasthenia Gravis" → UNKNOWN; "Myasthenia Gravis" → PASS |
| 2 | could cause wrong decision | identity not applied/surfaced: RW-05/06/07 | same molecule ELIGIBLE ×2 + UNRESOLVED; memo lists batoclimab and HBM9161 as separate candidates; import prints no flags |
| 3 | could cause wrong decision | `activity` field | RVT-1401, HBM9161, Belimumab, Iscalimab, Mezagitamab = ACTIVE with "no recruiting (COMPLETED)" status; marketed Nipocalimab = UNKNOWN; feeds ranking |
| 4 | could cause wrong decision | `bve-dealscreen-value` config | `discount_rate: 0.10` → output 0.12; `deal_options` silently ignored (identical results) |
| 5 | could cause wrong decision | Workbook Finalists sheet header | "7 approved finalist(s)" while all rows CANDIDATE_NOT_APPROVED |
| 6 | could cause wrong decision | memo rights sentence | "U.S. rights holder is evidenced for 1" = Nipocalimab FDA labeler |
| 7 | workflow blocker | `bve-dealscreen value` with no selection | FileNotFoundError traceback `.../valuation/valuations.json` |
| 8 | workflow blocker (by design) | assert/confirm refused for AI_PREPARED | cited 10-K evidence for IMVT-1402 cannot be recorded even as a proposal |
| 9 | friction | modality "Protein" for efgartigimod RW-01/02 UNKNOWN | market leader stuck UNRESOLVED |
| 10 | friction | ctgov research | 39 findings, ~all phase; none resolve blocking target gates; Telitacicept "mechanism" = trial title |
| 11 | friction | value handoff needs company cash/shares | asset-level deal valuation needs fake company block |
| 12 | friction | no human-efficacy evidence field | "prioritize compelling human evidence" impossible in tool |
| 13 | cosmetic/minor | Belimumab RW-29 `strategy.therapeutic_area` FAIL | TA identical to passing rows |
| 14 | cosmetic | memo "Preliminary valuations" heading empty | no explanation |
| 15 | friction | peak sales 320 vs inputs imply 400 | haircut not explained in output |
| 16 | friction | unresolved ranking | Telitacicept/Claseprubart/ALXN1720 ranked above FcRn programs |

## 6. Verdict
Not yet adequate for a real BD discussion. Strengths: clean provenance, rights never assumed available, AI cannot approve or assert (correct guardrails), excluded set is accurate. Biggest problem: **the funnel misstates the opportunity set** — the indication gate fails on "generalized MG" and identity flags are not applied, so batoclimab appears as two ELIGIBLE programs plus one UNRESOLVED while efgartigimod and IMVT-1402 sit UNRESOLVED; combined with the wrong `activity` flag, the ranked list a Head of BD would see is wrong. Finance side: the deal-terms path silently ignores inputs, so no deal economics are trustworthy.

Totals: commands 25 (≈33 tool calls); workarounds 4; unresolved programs 14 (tool) / 1 (mine, plus rights questions); human steps not completed 7.
