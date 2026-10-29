# AI-SIMULATED / INTERNAL DEVELOPMENT — a second AI process is not independent human validation

Adversarial review of `ANALYST_FINDINGS.md` (frozen @6fab6d8), cycle A1. Date 2026-10-28.
Reviewer: AI subagent acting as an investment-committee member. Did not read `src/` or `tests/`.
Evidence base: analyst workspace `~/.cache/analyst_sim_ws1` (read; one copy re-run in scratch),
`bve-dealscreen show` for all 40 programs, `examples/dealscreen_real/{landscape_fcrn_gmg_v2.csv,
reference_manual_assessment.csv, valuation_assumptions_hypothetical.yaml, buyer_fcrn_gmg.yaml}`,
`examples/configs/*.yaml` and `docs/dealscreen/README.md` for the valuation config schema.
No web source was fetched by this reviewer; statements labelled "public knowledge" are unverified here.

## 1. Verified headline defects

| # | Analyst claim | Verdict | Evidence (reproduced) |
|---|---|---|---|
| 1 | Indication gate: "Generalized Myasthenia Gravis" alone → UNKNOWN; "Myasthenia Gravis" → PASS | **CONFIRMED — and worse than stated** | `show RW-05` (Batoclimab, indication "Generalized Myasthenia Gravis"): `strategy.indication UNKNOWN` "Positive compatibility … not established". Same for RW-08 IMVT-1402, RW-09 Orilanolimab, RW-15/16, RW-30, RW-02 (gMG + "New Onset Generalized MG"). Also UNKNOWN: "Myasthenia Gravis, Generalized" (RW-20, RW-27, RW-28, RW-31) and "Myasthaenia Gravis" (RW-29). Yet RW-21 Empasiprubart "AChR-Ab Seropositive Generalized Myasthenia Gravis" → **PASS**. The gate is not merely strict on a subtype — it is inconsistent across spellings. 22/40 UNKNOWN on this gate (funnel). Note: the analyst listed RW-08 as UNRESOLVED on *target*; it is also UNKNOWN on indication, so fixing the target alone would not make it ELIGIBLE. |
| 2 | Identity flags exist but are not applied/surfaced; batoclimab appears as 2 ELIGIBLE + 1 UNRESOLVED | **CONFIRMED** | `identity.json`: PROPOSED_MERGE RW-05/RW-07 (`idflag:cf135d61442e`), SAME_MOLECULE_DIFFERENT_HOLDER RW-05/06 and RW-06/07. Screening: RW-06 HBM9161 ELIGIBLE rank 2, RW-07 RVT-1401 ELIGIBLE rank 4, RW-05 Batoclimab UNRESOLVED rank 8. Memo lines 13 and 18 list HBM9161 and Batoclimab as separate candidates with no cross-reference. Flags are *proposed only* by design, so "not applied" is policy; "not surfaced in memo/import/queue" is the real defect. |
| 3 | `activity` wrong: COMPLETED/old rows = ACTIVE; marketed = UNKNOWN; feeds ranking | **CONFIRMED** | `screening.json`: RW-07 RVT-1401 ACTIVE (status "no recruiting gMG trial (COMPLETED)", 2023-12-20); RW-29 Belimumab ACTIVE (2017-02-09); RW-28 Iscalimab ACTIVE (2021-01-05); RW-25 Mezagitamab ACTIVE (2023-06-02). Marketed RW-04 Nipocalimab, RW-01/02 Efgartigimod = UNKNOWN. Consequence verified: preference key HBM9161 `[1,1,4,3,1]` outranks Nipocalimab `[1,0,6,5,1]` — a completed Greater-China Ph3 code ranks **above a U.S.-marketed product** purely on activity. Rozanolixizumab (also U.S.-approved) is recorded "Phase 4 / Active trial" → ACTIVE → rank 1; the ranking reflects how a row was curated, not development reality. |
| 4 | `bve-dealscreen-value` ignores `discount_rate: 0.10` (uses 0.12) and silently ignores `deal_options` | **OVERSTATED (misconfiguration) — residual defect CONFIRMED** | The analyst put `discount_rate` at the YAML top level (`manual_val/rw08.yaml`); every `examples/configs/*.yaml` places it under `asset:`. Re-run with `asset.discount_rate: 0.10` → output `discount_rate 0.1`, **rNPV $163M (bull 736 / bear −143)**, not $103M. `deal_options` is the *assumptions-file* schema; the prototype CLI takes `deal_economics:` (README line 59). With `deal_economics: {cdev_cost_share: 0.5}` rNPV moves 163 → 258, so the block is honoured. Real residual defect: unknown keys (`discount_rate` at top level, `deal_options`, even `deal_economics: {bogus_key: 1}`) are **accepted silently** with no warning, and the default rate (12%) is applied without notice. The analyst's headline number ($103M) and "upfront 5× rNPV" are therefore wrong (≈3× at the intended 10%). |
| 5 | Finalists sheet says "7 approved finalist(s)" while all are CANDIDATE_NOT_APPROVED | **CONFIRMED** | `ds.xlsx` Finalists A1: "7 approved finalist(s) (maximum 10)…"; every row `CANDIDATE_NOT_APPROVED`, `AI_PREPARED`. Rows are correctly labelled; the header count is the misleading element. |
| 6 | Memo: "U.S. rights holder is evidenced for 1" = Nipocalimab FDA labeler | **CONFIRMED, partially mitigated** | memo.md line 9; the only eligible row with a holder is RW-04, `holder_display` "Janssen Biotech, Inc. (U.S. labeler per FDA label; not a rights statement)". The same sentence adds "knowing the holder says nothing about availability", so availability is not overstated — but the memo upgrades a labeler to a "rights holder", contradicting its own source annotation. |
| 7 | `value` with no selection crashes with a traceback | **CONFIRMED** | Re-run on a copy of the workspace: `FileNotFoundError … valuation/valuations.json`. |
| 8 | AI cannot assert/confirm cited evidence (IMVT-1402 10-K) | **CONFIRMED as behaviour; WRONG as a "defect"** | Refusal is the declared guardrail (human-only assertions). Analyst also mislabels the source: `imvt-20251231.htm` is a quarter ended 31-Dec-2025; Immunovant's fiscal year ends 31 March, so this is a **10-Q**, as `reference_manual_assessment.csv` (RW-05, RW-08) says. The analyst's quotes cite a "10-K" throughout. |

Also checked: #13 RW-29 Belimumab `strategy.therapeutic_area FAIL` with TA "Neurology" like passing rows — **CONFIRMED** (`show RW-29`). #15 peak sales $320M vs 20,000×$200k×10% = $400M — **CONFIRMED unexplained** (bull peak 480 = 1.5×320, so the 0.8 factor is applied before scenarios; no output field names it).

## 2. Issues the analyst missed or got wrong

1. **Analyst's own valuation is wrong** (see #4): $103M at 12% reported as "discount rate ignored"; correct run at 10% is $163M. A 58% swing caused by a silent default is the more dangerous finding, and the analyst attributed it to the tool ignoring input rather than the input being in the wrong place.
2. **Batoclimab ranked #1 on unsupported grounds.** Tool row RW-05: "All registered gMG trials terminated or withdrawn" (NCT05403541, 2026-09-14); assumptions file: "Not valued: registered gMG trials terminated and rights may return to HanAll". The analyst's attractiveness case ("Ph3 gMG data reported") cites no source fetched in the session. "Potential return of *certain* rights" (analyst's own quote) does not establish U.S. rights or availability. Shortlisting a terminated program as #1 rests on an inference about an undisclosed rights negotiation.
3. **Indication gate inconsistency** across spellings (RW-21 PASS vs RW-20/27 UNKNOWN) — analyst saw only the gMG half.
4. **RW-08 IMVT-1402 is blocked on four gates**, not one: target, modality, mechanism and indication are all UNKNOWN (`show RW-08`). The landscape row has blank Target/Mechanism/Modality. The "only one human assertion away" impression in §3C is wrong.
5. **Efgartigimod RW-02 is blocked on two gates** (modality *and* indication); analyst's table says UNRESOLVED with only the indication reason.
6. **Rozanolixizumab RW-03 curated as Phase 4 / non-marketed** with no labeler, although the reference CSV says U.S.-approved June 2023 (Rystiggo). Four U.S.-marketed FcRn products are thus represented three different ways (Marketed+labeler; Marketed+UNKNOWN activity; Phase 4+ACTIVE). Ranks 1–3 are artefacts of curation.
7. **Efgartigimod identity not flagged**: RW-01/RW-02 share INN but `identity.json` has no flag; eculizumab RW-10/11/12 likewise. The identity authority only flagged code↔INN pairs.
8. **Unresolved-queue order** (Telitacicept #1, Claseprubart #2, ALXN1720 #3, Gefurulimab #4 before IMVT-1402 #5) means an analyst working the queue top-down spends the first four slots on non-FcRn programs; ALXN1720/Gefurulimab are the same molecule (flagged) yet occupy two consecutive slots.
9. **Coverage risk not discussed.** The landscape is built from a ClinicalTrials.gov MG snapshot + openFDA. FcRn programs with no CT.gov-registered MG trial (e.g. China-only registrations, early or non-MG-first programs) cannot appear. Neither analyst nor tool states this recall boundary. SHR-2173 (RW-38) and Cizutamig (RW-39) remain target-unknown; the analyst did not attempt to resolve them.
10. **Economic perspective.** The hypothetical license terms (upfront $500M payable, 15% royalty, $400M approval milestone payable) are the *buyer's* outflows, but the CLI output reports a single asset rNPV with no labelled perspective; `cdev_cost_share: 0.5` *raised* rNPV (163 → 258), i.e. the number is the value to the program holder of shedding cost. A reader cannot tell from `valuation.json` whose NPV is shown. Analyst did not raise this.
11. **Placeholder company block** (cash 0, shares 1) — `valuation.json` contains per-share/NAV fields computed on 1M shares; if pasted into a deck these are nonsense. Analyst flagged friction but not this contamination.

## 3. Analyst vs `reference_manual_assessment.csv`

Reference scope is scientific fit (IN/OUT/UNKNOWN); analyst mixed scientific and business calls.

| ID | Program | Reference | Analyst | Who is right |
|---|---|---|---|---|
| RW-09 | Orilanolimab | IN (anti-FcRn; inactive) | OUT (terminated) | **Reference** under the buyer spec: phase gate is MINIMUM Phase 2 and `prefer_active_development` is a preference, not a gate. Analyst's call is a defensible business deprioritisation but was presented as scope. |
| RW-06 | HBM9161 | IN (duplicate of RW-05) | "same molecule", not a U.S. option | Agree on science; analyst adds territory — consistent with reference identity note. Not a real disagreement. |
| RW-07 | RVT-1401 | IN (duplicate) | duplicate, should merge | Agree. |
| RW-39 | Cizutamig | UNKNOWN (target unknown) | OUT (Ph1) | **Analyst** — Phase 1 fails the hard phase gate irrespective of target; tool also EXCLUDED on phase. |
| RW-38 | SHR-2173 | UNKNOWN | UNRESOLVED | Agree. |
| others (31) | — | match | match | Agree. Analyst's out-calls on RW-15/16/20/21/26/27/30/40 rely on unfetched public knowledge, same as the reference (which marks them "public knowledge; not in sources used"); both are unverified to the same degree. |

## 4. Could a senior BD leader be materially misled?

**Yes, on three points if reading tool output alone; on one point if reading the analyst's write-up.**

- **Tool output:** (a) the ELIGIBLE list ranks HBM9161 (#2, Harbour's Greater-China code, trials completed) and RVT-1401 (#4, a retired code) alongside approved drugs and counts batoclimab twice, while IMVT-1402 — the only late-stage FcRn program not yet marketed — sits in UNRESOLVED behind four non-FcRn programs; (b) the Finalists sheet header says "7 approved" when none is approved; (c) a valuation run with a misplaced key silently uses 12% and drops deal terms, so a $163M figure becomes $103M with no warning.
- **Analyst write-up:** it recommends batoclimab as #1 on an unsourced efficacy claim and an inferred rights reversion, while the input row says all registered gMG trials are terminated — a leader could open a licensing conversation on a stalled asset. It also reports a wrong rNPV and blames the tool.
- **Not misleading:** exclusions (all 22 confirmed correct against the reference); rights are never shown as available; AI cannot approve or assert. The safe use today is as a working file with a human re-check of every ELIGIBLE/UNRESOLVED FcRn row and any valuation input placement.

---

## Addendum (engineering, after the review): code review of the A1 fixes

A separate AI code review of the fixes found 3 HIGH issues in the fixes themselves (area-name
comparison, over-broad qualifier reading, missing memo disclosure). All were fixed with
regression tests before commit; see `ITERATION_LOG.md`. The review above is unchanged.
