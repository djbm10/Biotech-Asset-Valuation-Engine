# AI-SIMULATED / INTERNAL DEVELOPMENT — baseline comparison critique, frozen before any DealScreen change

Critic: an AI agent in the same environment as the workflows and the reference. This is not independent human validation, and Gates H and B stay open. Date: 2026-10-29. I did not read `src/` or `tests/`. I used about 7 web calls.

Paths below are relative to `research/dealscreen_comparison_v1/`. `X.csv:CL-nn` means the row with that `program_id`.

---

## 0. Verdict (pre-registered rule, PROTOCOL.md "Pre-registered decision rule")

| | Critical errors (rescored, §1) | Reference-IN found | Shortlist evidence more checkable? | Result |
|---|---|---|---|---|
| **C vs B** | C 0, B 0. **Tie on (i).** | C 30/30, B 30/30 | No. Neither is clearly better (§3). | **No demonstrated advantage** |
| **C vs A** | C 0 < A 1 (SOT102) | C 30 ≥ A 29 − 1 | No. A's row-level citations are a URL plus a verbatim quote; C's are source names without URLs (§3). | **No demonstrated advantage.** (i) and (ii) pass; (iii) fails. |

Outside the rule's metrics, C made the single most costly commercial error of the three runs:

- C marked **SKB315 as rights held by Merck & Co.** (`runs/C_dealscreen/calls.csv:CL-27`, "Merck & Co (MK-1200) ex-China per alias", HELD_BY_OTHERS).
- In fact Merck **returned** the global rights in August 2024. I confirmed this at <https://synapse.patsnap.com/article/merck-co-invests-in-kelun-bispecific-adc-exits-cldn182-program>: "Merck has returned global rights to Kelun's CLDN18.2-directed ADC candidate, SKB315."
- As a result, C dropped the reference's #1 transaction candidate, which A ranked #2 and B ranked #5.
- The protocol's critical-error definition does not count a holder error on a non-shortlisted row. That is why the rule above is a tie, and the gap in the definition matters.

---

## 1. Mechanical scores: verified, then rescored

I re-ran the logic of `score.py` by hand against `scores.json`. The counts reproduce. These are the corrections:

1. **Identity contradiction on CL-20/CL-21 (flagged for A and C) is a reference artifact, not a workflow error.**
   - The reference itself calls CL-20 IN and CL-21 UNRESOLVED (`reference/reference_calls.csv:CL-20, CL-21`).
   - It also labels the grouping "(possible)… unverified" (`reference/REFERENCE.md`, Identity groups).
   - A and C made exactly the reference's calls and kept the link as a "?" group.
   - **Rescore: A 0, C 0.**
   - B merged the two into one identity group and called CL-21 IN, while writing "identity NOT confirmed" (`runs/B_general/calls.csv:CL-21`). That asserts more than the evidence supports. It is not critical, because the reference row is UNRESOLVED rather than OUT.
2. **The "tool disposition only" score for C (0/30 IN) is a scorer bug.**
   - The tool's vocabulary is ELIGIBLE / EXCLUDED, and `score.py` compares the column to the string "IN".
   - Rescored with ELIGIBLE→IN and EXCLUDED→OUT, see §2.
3. **`score.py` does not test holder or licensee errors.** Protocol metric 3 requires them. I added them by hand in §4. That added C: SKB315; A and B: none material.
4. **`score.py`'s printed "critical" figure omits wrong inclusions and unreproducible valuations.**
   - It makes no difference here: there are no wrong inclusions on any shortlist, and see §6 for valuations.
5. **The reference is correct on CL-33 (SOT102).**
   - The trial NCT05525286 is titled "…Patients With Gastric and Pancreatic Adenocarcinoma" (`sources/ctgov_cldn18_snapshot.json`).
   - A's exclusion ("pancreatic-only… no gastric data", `runs/A_spreadsheet/calls.csv:CL-33`) is therefore wrong. It is a real critical error, though of low commercial impact because the program is terminated.
6. **Reference fallibility.**
   - SHR-A1904: all three workflows put HELD_BY_OTHERS, while the reference puts NOT_EVIDENCED. An unexercised option is not "held", so the reference is more correct. This is an identical minor conflation in all three runs.
   - The reference's ATG-022 originator is "memory, unverified". It does not affect the scoring.

**Rescored critical errors (protocol definition):**

| Run | Errors |
|---|---|
| A | 1 (wrong exclusion CL-33) |
| B | 0 |
| C | 0 |

Shortlist overlap with the reference's top 15: 10/10 for every run.

---

## 2. What the TOOL contributed vs the C analyst

These come from `runs/C_dealscreen/calls.csv` (tool columns) and `runs/C_dealscreen/LOG.md`.

**Out of the box (`tool_disposition_without_target_map`):**
- **0 eligible**, 39 unresolved, 23 excluded (LOG.md:14).
- The cause: "Claudin 18.2" did not resolve to a target.
- Of the 30 reference-IN rows, 29 are UNRESOLVED and 1 is wrongly EXCLUDED (LCB02A, CL-38).

**Two workarounds were needed first:**
- the analyst wrote a synonym map, `target_map.yaml` (LOG.md:21);
- the analyst made a date-fixed copy of the evidence library, because the offline research step crashed with `ValueError: Invalid isoformat string: '2016-10'` (LOG.md:18).

**After the workarounds** (`tool_disposition`): 8 ELIGIBLE, 28 UNRESOLVED, 26 EXCLUDED.

| Reference \ Tool | ELIGIBLE | UNRESOLVED | EXCLUDED |
|---|---|---|---|
| IN (30) | 8 | 21 | 1 (LCB02A: tool trusted the wrong "Monoclonal antibody" cell) |
| OUT (28) | 0 | 4 (imaging CL-61/62, TAC01, LB4330: blank modality) | 24 |
| UNRESOLVED (4) | 0 | 3 | 1 |

Problems in the tool's 8 ELIGIBLE rows:
- **3 are held by large pharma:** CL-03 and CL-05 (AZ) and CL-10 (Astellas).
- **The sonesitatug molecule is split:**
  - CL-03 and CL-05 are ELIGIBLE, but CL-04 (CMG901) is UNRESOLVED;
  - this is a contradictory call within one molecule, although the tool raised an identity flag for the group.
- The tool's rank 1 was **QLS31905**, a non-ADC TCE. The buyer prefers ADCs.

**Contribution of the C analyst:**
- All 30 IN calls. 22 of them override the tool, with "AI evidence supports call" in `differs_from_tool_why`.
- Every rights and holder entry.
- The EO-3021=SYSA1801 identity (the tool missed it, LOG.md:83).
- IBI343 and LCB02A modality fixes (entered via `propose`).
- The shortlist order: the analyst moved LM-302 to #1 and put ATG-022 in, both tool-UNRESOLVED.

**Net:**
- Scientific screening quality is analyst-made.
- The tool's own value was the gate structure, the audit trail, the refusals, and the scope exclusions of naked mAbs, CAR-T and non-CLDN18.2 drugs once targets resolved.

---

## 3. Evidence quality: 8 shortlist claims per run

Legend: ✓ the citation supports the claim; ◐ the citation supports the identity or phase but not the rights/status claim it accompanies; ✗ the citation is miscited, unverifiable at the URL, or wrong; S = sourced from a search snippet (self-declared).

### Run A (`runs/A_spreadsheet/calls.csv`)

| Row | Claim | Verdict |
|---|---|---|
| CL-07 | BMS returned rights | ✓ pharmaphorum quote, verbatim in `sources/public_evidence.json` |
| CL-27 | Kelun "exploring… international markets" | ✓ S. Verified at patsnap (2024-08-23). |
| CL-16 | "global rights assets — ATG-022" | ✗ S. Fetched <https://www.1stoncology.com/blog/2024/page/503>: no Antengene or ATG-022 text there. Unverifiable as cited. |
| CL-24 | Holder Junshi, "no ex-China licence found" | ◐ evidence is "landscape cell" |
| CL-29 | Baili/SystImmune, no licence | ◐ BioSpace ASCO-2026 PR supports the target only (confirmed via search) |
| CL-31 | Merck is supply only | ✓ S. Clinicaltrialsarena confirms a "clinical collaboration", with Merck supplying KEYTRUDA. |
| CL-13 | I-Mab/ABL share rights | ✓ natlawreview, verbatim in curator file |
| CL-20 | Qilu Ph3 n=602 | ✓ pharmcube (phase; rights absence uncited) |

**A totals:** 5 ✓, 2 ◐, 1 ✗. Four snippet-sourced quotes, declared in A LOG.md:117.

### Run B (`runs/B_general/calls.csv`)

| Row | Claim | Verdict |
|---|---|---|
| CL-16 | Antengene "global rights assets" | ✗ same 1stoncology page/503, unverifiable; B labels it a paraphrase (LOG.md:104) |
| CL-07 | rights handed back | ✓ |
| CL-27 | Merck gave back rights | ✓ S. Labelled "paraphrase via search", and verified. |
| CL-24 | no ex-China licence | ◐ NCT/NCIt support the phase only |
| CL-29 | no outside licensee | ◐ NCT title only |
| CL-13 | shared rights | ◐ quote is correct, but the **URL is truncated** ("…clinical-cance"), so the link is broken |
| CL-25 | "self-developed" | ◐ quote is correct, but the **URL is truncated** ("…gastric-and-pan") |
| CL-46 | bispecific ADC | ◐ S. "WebSearch summary" plus NCT id. |

**B totals:** 2 ✓, 5 ◐, 1 ✗. B is the most candid about snippets, but it has 2 broken links.

### Run C (`runs/C_dealscreen/calls.csv`)

Most citations are source names and dates with no URL.

| Row | Claim | Verdict |
|---|---|---|
| CL-07 | BMS handed back | ✓ "pharmaphorum 2025-07" (resolvable via curator file) |
| CL-20 | Qilu; "BD listing of an unnamed CLDN18.2/CD3 TCE" | ✓ fetched drugtimes.cn 2026-07-11: no developer named, "Clinical stage". C correctly did **not** claim it is QLS31905 or claim availability. |
| CL-16 | interim lists global rights | ◐ an Antengene interim (2026-08-23) exists, but the excerpts I retrieved call ATG-022 an in-house late-stage asset without the words "global rights". No URL. |
| CL-24 | no licence found | ◐ NCIt / NCT only |
| CL-29 | no licence found | ◐ NCIt only |
| CL-25 | self-developed | ✓ "RemeGen 2022-12-12" = the BioSpace ODD PR |
| CL-13 | shared rights | ✓ natlawreview |
| CL-27 (shortlist-relevant, excluded) | Merck holds rights | ✗ "NCIt alias MK-1200" is a drug synonym, not a rights document, and it is stale. This is a **miscitation that drove an exclusion.** |

**C totals:** 4 ✓, 3 ◐, 1 ✗. C's calls.csv citations are the least directly checkable, because they have no URLs. C's workbook `Diligence` and `Audit Trail` sheets do carry provenance for tool-surfaced facts, which is a real auditability plus, but it covers only what the tool researched.

**Summary:**
- Unsupported or miscited claims: A 1, B 1 (+2 broken links), C 1.
- Partial-support claims: A 2, B 5, C 3.
- **No run's shortlist evidence is clearly more checkable than B's, and A's is the most quote-verbatim.**

---

## 4. Commercial handling

| Issue | A | B | C |
|---|---|---|---|
| Availability asserted | none (0 EVIDENCED_AVAILABLE) | none | none. The tool kept U.S. rights UNKNOWN and said a labeler is not an owner (`bd_memo_C.md:62`). |
| LM-302 returned rights | ✓ NOT_EVIDENCED, returned noted | ✓ | ✓ in calls.csv, but **the tool could not store it** (propose REFUSED: "cannot be read as a us_rights value", LOG.md:33). The tool memo shows LM-302 as "U.S. rights unknown" (`bd_memo_C.md:65`), so the return is lost in the Head-of-BD deliverable. |
| SKB315 returned rights | ✓ (#2) | ✓ (#5) | **✗ held by Merck. Holder error; the top candidate was lost.** |
| SHR-A1904 option | HELD_BY_OTHERS, "exercise unknown" (conflates option with held) | same | same. The tool has no "option" vocabulary (LOG.md:84). |
| Large-pharma-held excluded from shortlist | ✓ | ✓ | ✓ by the analyst. The tool's ELIGIBLE set included AZ/Astellas rows (§2). |
| Collaborator ≠ licensee (MSD on ATG-022/PT886) | ✓ CL-31 | ✓ (assumed) | ✓ |
| Marketed zolbetuximab | ✓ | ✓ | ✓ analyst. Screening `market_status` was null for every row, including zolbetuximab (LOG.md:87). The exported CSV shows US_MARKETED for CL-01 only. |

---

## 5. Identity

- **A:**
  - All reference groups are found; ANO31905 is kept as "possible".
  - No wrong merges.
  - A has no group label for CL-07 and similar rows, which is fine.
- **B:**
  - All groups are found.
  - CL-21 is merged into QLS31905 and called IN despite "NOT confirmed": an over-merge of an unverified link.
  - The memo counts are inconsistent with calls.csv. The memo says 31 IN / 26 OUT / 5 UNRESOLVED (`runs/B_general/memo.md:56`); calls.csv has 31 / 27 / 4.
- **C:**
  - The analyst found all the groups.
  - **The tool missed EO-3021=SYSA1801**, even though the evidence says "EO-3021 (SYSA1801)" (LOG.md:83).
  - The tool flagged the sonesitatug group but still gave contradictory dispositions within it (CL-03/05 ELIGIBLE, CL-04 UNRESOLVED).
- No run has the same molecule twice on its shortlist.

---

## 6. Finance (reproduced)

### A (`runs/A_spreadsheet/valuation.md`), LM-302 base, reproduced exactly

```
PV cost = 60/1.1 + 60/1.1² + 60/1.1³ + 20·0.5/1.1⁴ = 156.04
PV unrisked revenue = Σ_{k=1..12} 135·min(k/5,1)/1.1^(4+k) = 475.18
Acquisition = −156.04 + 475.18·0.45·0.40 − 400 = −470.5 ✓
Licence = −156.04 + 475.18·0.45·0.28 − 500·0.45/1.1⁴ − 100 = −349.8 ✓
Bear licence (PoS 0.288, peak 67.5) = −333.9 ✓
```

- Perspective: buyer ✓. Assumptions labelled HYPOTHETICAL or ANALYST ✓.
- **Misleading scenario ordering:**
  - licence bear −333.9 and bull −319.9 are **both better than base −349.8**;
  - A explains only the bear inversion (valuation.md:50).

### B (`runs/B_general/valuation.md`), ATG-022, reproduced exactly

Dev cost at phase start, sales at mid-year:

```
base licence −378.4 ✓
acquisition −497.8 ✓
bear −357.6 / −547.7 ✓
bull −382.3 / −429.5 ✓
```

- Perspective: buyer ✓. Labels ✓.
- The licence bull is worse than base. B **explains** why: milestones are more likely to be paid (valuation.md:97).

### C (`runs/C_dealscreen/valuation.md`, `valuation_runs/*.json`)

- **The composition identities reproduce:**
  - asset rNPV = prob-adj revenue PV 98 − trial cost PV 163.2 = −65.2 → −65 ✓ (`CL-07_asset.json` outputs.rnpv);
  - acquisition −465 = −65 − 400 ✓;
  - bull −300 = 100 − 400 ✓;
  - licence = 80 − 427.1 = −347 ✓ (`CL-07_license.json`).
- **Not hand-reproducible from the disclosed inputs:**
  - the revenue PV of 218 depends on undisclosed engine conventions;
  - `effective_tax_rate: 0.21` appears in the JSON but not in valuation.md's assumption list;
  - my closest hand variant (no tax, half-year ramp) gives 219.9.
- **The scenario shocks are undisclosed in the deliverable:**
  - bull is peak 162 (1.5×), PoS 0.6435 and launch 1 year sooner;
  - bear is peak 59, PoS 0.2205 and 2 years later.
  - They come from the JSON scenarios. They are reproducible by re-running the config with the seed, but they are not labelled as assumptions.
  - The asset bull of **+$100M** rests entirely on these hidden shocks.
- **Ordering:** C **flags** the out-of-order licence scenarios (LM-302 bear above base; RC118 bull below base), and it notes that the prototype path printed them without warning (valuation.md:49-53). That is honest.
- **Perspective:** the "asset, no deal" row sits under a "buyer perspective" heading. It is in fact a 100%-owner standalone value. This is mislabelled, but the other rows are buyer-correct.
- **Deliverable contradiction:**
  - the tool memo says "No valuation was run" (`bd_memo_C.md:78`);
  - the workbook `Valuation Scenarios` sheet is empty (header only);
  - yet valuation.md reports numbers from the PREVIEW / PROTOTYPE path.
  - A Head of BD gets two inconsistent stories.
- **All three runs reach the same conclusion:** every deal is negative because the placeholder market is about $108–135M peak. The engine added no decision-relevant information over a 20-line spreadsheet.

---

## 7. Deliverable quality for a Head of BD

| | A | B | C |
|---|---|---|---|
| Actionable shortlist with rationale | ✓ memo top-5 with the reason and the key diligence question (`memo.md:10-16`) | ✓ concise | Tool memo: names and "U.S. rights unknown" ×10 (the returned-rights facts are lost). The analyst's LOG has more. |
| Uncertainty disclosure | good | good. Snippet/paraphrase is flagged. | **Strongest labelling.** UNVALIDATED banner, AI_PREPARED, human approval refused, NOT COMPLETED BY HUMAN. |
| Auditability | workbook with live formulas + quotes | build.py reproduces everything | **Strongest audit trail:** import manifest, row hashes, gate-by-gate Screening sheet, Diligence provenance, Audit Trail. Undercut by citations without URLs and an empty valuation sheet. |
| Next steps | specific (contact Sino Biopharm, Kelun, Antengene; Merck exit rationale) | specific | generic ("resolve strategy.indication" ×6) |

---

## 8. Effort (self-reported, AI-simulated; not a human time claim)

| Run | Tool calls | Web searches | Workarounds |
|---|---|---|---|
| A | ~19 (LOG.md:109) | 9 | — |
| B | ~16 (LOG.md:101) | 7 | — |
| C | ~30 (LOG.md:6) | 3 | 2 (synonym map + date-fixed library) |

C spent roughly double the calls on tool operation and did the **least web diligence**. That is the plausible cause of the SKB315 error.

---

## 9. Decision rule

Restated from §0:
- **C vs B: no demonstrated advantage.**
  - (i) is a tie at 0–0;
  - (iii) is not met.
- **C vs A: no demonstrated advantage.**
  - (i) and (ii) pass: 0 vs 1 critical errors, 30 vs 29 reference-IN found.
  - (iii) fails: C's row citations are less checkable than A's URL-plus-verbatim-quote citations.
- On the uncounted commercial dimension, C is **worse** than both: SKB315.

---

## 10. DealScreen failures that could cause costly BD decisions

1. **Zero output on default use.** An unresolved target string ("Claudin 18.2") gives 0 eligible; a manual synonym map is needed (LOG.md:14). A user without the workaround gets nothing, or concludes the landscape is empty.
2. **No vocabulary for returned rights or options** (LOG.md:33, 84).
   - The returned-rights fact for LM-302 is dropped from the memo.
   - Stale aliases (MK-1200) go unchallenged, leading to a wrong large-pharma holder on SKB315. A top candidate is lost.
3. **The offline research step crashes on partial dates** in the protocol-supplied library (LOG.md:18).
4. **It trusts vendor modality cells.**
   - LCB02A is wrongly EXCLUDED.
   - IBI343 is left UNRESOLVED.
   - Imaging agents, TAC-T and the IL-10 fusion are not excluded when the modality is blank (LOG.md:79-81).
5. **The indication gate is UNKNOWN for 28 rows**, including obvious Phase 3 gastric ADCs. There is no agent question for indication (LOG.md:82).
6. **Identity:** it missed EO-3021=SYSA1801, and it gave contradictory dispositions within a flagged group (sonesitatug).
7. **ELIGIBLE does not consider rights.** 3 of 8 ELIGIBLE rows are held by large pharma, and the tool's rank 1 is a non-ADC.
8. **Valuation:**
   - the PREVIEW path emits out-of-order scenarios without warning;
   - the scenario shocks and 21% tax are undisclosed in the narrative;
   - the memo and workbook say "no valuation" while numbers circulate.
9. **`market_status` is null in screening**, even for the marketed zolbetuximab (LOG.md:87).

## Genuine DealScreen advantages (with evidence)

- **Availability discipline:** it never invents availability, keeps U.S. rights UNKNOWN, and distinguishes a labeler from an owner (`bd_memo_C.md:62`). A and B also invented no availability, so this is a tie on outcome. The difference is that the tool enforces it rather than relying on analyst judgment.
- **Governance:** it refused AI approval and selection for valuation, and blocked `value` without a human (LOG.md:34-38). Neither A nor B has an enforced control.
- **Audit trail:** the import manifest, row hashes, per-gate Screening columns and Audit Trail sheet (`dealscreen_C.xlsx`) are more granular than A's or B's workbooks.
- **Scope exclusions:** once the target resolved, it correctly excluded the non-CLDN18.2 noise (6 drugs), naked mAbs and CAR-T, with 24/28 reference-OUT rows EXCLUDED.
- **Identity flags:** it raised them without auto-merging (zolbetuximab, sonesitatug, XNW27011).
- **Self-flagging in valuation:** it disclosed the scenario-ordering anomaly.

## Where B is better

- **Correct rights on SKB315 and LM-302 in the deliverable**, with both returned rights stated in the memo (`runs/B_general/memo.md:62,65`).
- **Fewer calls:** about 16 vs about 30.
- **No workarounds needed.**
- **Fully hand-reproducible valuation**, with the scenario inversion explained rather than just flagged.
- **More web diligence per call**, and candid snippet labelling.
- **Weaknesses:** 2 truncated URLs, an over-merge of ANO31905, and memo count inconsistencies.
