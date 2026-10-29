# AI-SIMULATED / INTERNAL DEVELOPMENT — post-fix comparison critique

Critic: AI process (not independent human validation). Gates H and B stay open. Date 2026-10-29.
Scope: C3 (`runs/C3_dealscreen_final`) vs B (`runs/B_general`) vs A (`runs/A_spreadsheet`) against
`reference/reference_calls.csv`, under the decision rule in `PROTOCOL.md` ("Pre-registered decision rule").
**Web verification was limited.** One fetch returned a 404 (B's RC118 URL as written in `B_general/calls.csv`
row CL-25 is truncated). The session limit then stopped all further fetches. Checks therefore rely on the
frozen `sources/public_evidence.json` and on what each citation itself contains.

## 1. Scores verified (scores.json)

| | A | B | C3 |
|---|---|---|---|
| Reference-IN called IN | 29/30 | **30/30** | 23/30 |
| Wrong exclusions | 1 (CL-33) | 0 | 0 |
| Reference-IN left UNRESOLVED | 0 | 0 | 7 (CL-25, 38, 39, 43, 44, 46, 51) |
| Wrong inclusions | 0 | 0 | 0 |
| Shortlist critical (ref OUT / large-pharma / marketed / duplicate) | 0 | 0 | 0 |
| Availability asserted without evidence | 0 | 0 | 0 |
| Shortlist ∩ reference top (15) | 10 | 10 | 10 |

I recomputed from the `calls.csv` files and the numbers are correct. Rescoring notes:
- **Identity "contradiction" CL-20/CL-21 (charged to A and C3) is a reference artefact.** The reference itself
  calls CL-20 IN and CL-21 UNRESOLVED, and calls the match "unverified" (`REFERENCE.md`, Identity groups; csv
  rows CL-20/21). A and C3 make the same call as the reference. It should not count against them. B merged them
  as "likely" (B calls.csv CL-21), which the reference does not support either. I score it as neutral for all three.
- **C3's 7 unresolved.** For CL-39/43/44/51 (Phase 1 solid-tumour baskets, status UNKNOWN) the reference's IN rests
  on its own "lenient" gastric reading (`REFERENCE.md`, "I applied the gastric criterion leniently"). UNRESOLVED is
  a defensible strict reading for these four, so I do not count them as errors.
  **CL-25 RC118 is a genuine recall miss.** The supplied evidence is titled "RC118 … in Patients with **Gastric** and
  Pancreatic Cancers Granted Two Orphan Drug Designations" (`sources/public_evidence.json`, CL-25 modality item).
  C3 nonetheless wrote "gastric not stated" (C3 calls.csv CL-25).
  **CL-38 LCB02A** was wrongly EXCLUDED by the tool on the vendor's "mAb" cell. The analyst cited the CT.gov ADC
  title and moved it only to UNRESOLVED, although the cited title already settles the modality.
  **CL-46 VBC108** is a reference MEDIUM candidate and B shortlisted it.
  Adjusted C3 recall: 26/30 under the strict reading, still below B's 30.
- **C3 tool-level wrong exclusion: LCB02A** (tool_disposition EXCLUDED; FIXES_C1 "Remaining wrong exclusion").
  The analyst masked it, so it does not count in the protocol metric.

## 2. What the tool decided vs what the analyst decided (C3)

- **Tool dispositions** (C3 calls.csv `tool_disposition`): 14 ELIGIBLE, all of them reference-IN, with no false
  ELIGIBLE. That is a real improvement from 0/30 as installed at baseline (FIXES_C1 X1/X7).
  25 UNRESOLVED, including CMG901, givastomig, AZD5863, EO-3021, SOT102, AMG 910 and DA-3501. Per the C3 LOG
  ("Indication gate UNKNOWN for 40 programs (incl. AZD5863, givastomig, DA-3501, CMG901 with gastric in
  conditions)"), X3 did not cover most real registry strings.
  The tool also left 7 obvious noise rows UNRESOLVED (rilvegostomig, volrustomig, two imaging agents, RC148,
  TAC01, LB4330) instead of OUT. Several of these carry high tool ranks: rilvegostomig is UNRESOLVED rank 2.
- **Anchoring: yes, measurably.** On every one of the 7 reference-IN rows C3 left unresolved, the tool was also
  UNRESOLVED or EXCLUDED. C3 overrode the tool upward only where it had a press-release or Phase 3 anchor
  (givastomig, DA-3501, AZD5863, CMG901, EO-3021, SOT102, AMG 910). The 7 reasons are a single templated string,
  "in-scope modality but solid-tumor basket; gastric not stated", which shows the tool's gate became the analyst's
  reason. B, with no tool, resolved all 7.
  **Verdict:** strictness is defensible for 4 status-UNKNOWN Phase 1 baskets. It is a recall failure for RC118
  (gastric evidence in the supplied sources), LCB02A (the cited source says ADC) and VBC108.
- **The analyst's own reasoning was good on rights:** the LM-302 return, SKB315 exit, SHR-A1904 option, IBI343 to
  Takeda, and the MSD collaborator-not-licensee calls. These mostly came from web or curated evidence, not from the
  tool. The tool refused paraphrased rights quotes (C3 LOG "REFUSED"), which is a genuine safety property. But it
  left U.S. rights UNKNOWN for all 14 eligible (LOG "Tool funnel").

## 3. Transaction view

Tool transaction ranks (C3 calls.csv `tool_transaction_rank`): 1 LM-302, 2 QLS31905, 3 SHR-A1904, 4 ATG-022,
5 JS107, 6 BL-M05D1, 7 SKB315, 8 spevatamig, 9 TORL, then DEPRIORITIZED AZ/Astellas at 10–14.
- Good: every AstraZeneca/Astellas-held eligible record is DEPRIORITIZED, zolbetuximab is EXCLUDED_BY_BUYER_PREFERENCE,
  and no availability is implied (all NOT_EVIDENCED/UNKNOWN).
- **Large-pharma-held asset tiered OPEN: IBI343 (CL-06)**, whose ex-China rights Takeda holds. It is tier OPEN with
  tool rank 1 among unresolved. It went unflagged only because the analyst knew the Takeda deal and the tool cannot
  apply that proposal without a human (C3 LOG, Workarounds).
- **Encumbered asset ranked #3 OPEN: SHR-A1904**, which carries a Merck KGaA ex-China option. Merck KGaA is in the
  declared deprioritized list, but matching is by sponsor only (FIXES_C1 X5). `encumbered_rights: deprioritize` did
  nothing because the option was never recorded.
- **The reference's #1 (SKB315, rights returned) is tool rank 7.** Returned rights are not a positive signal in the
  tier.
- EO-3021/SYSA1801 (discontinued; rights unclear) are tiered OPEN.
- The C3 shortlist order nearly copies the tool order (1, 2, 4→3, 5→7, 7→6). The analyst inserted givastomig but
  did not move SKB315 up. Net: the tier removes the baseline's large-pharma-at-#2–#4 error (CRITIC_BASELINE). It does
  not produce the buyer's best-first order, and it relies on an analyst-typed pharma list
  (`buyer_with_transaction.yaml` tail).

## 4. Evidence checkability (8 shortlist claims each, from calls.csv `evidence`)

| # | C3 claim | OK? | B claim | OK? |
|---|---|---|---|---|
|1|LM-302 rights returned, pharmaphorum quote|✓|same source|✓|
|2|QLS31905 Ph3 n=602, pharmcube quote|✓ (Ph3 only, no rights)|QLS31905 BioSpace "targets Claudin18.2"|✓ (no rights evidence)|
|3|ATG-022 "Antengene" = registry sponsor only|✗ sponsor ≠ rights holder|ATG-022 "global rights assets", blog page/503|weak (paraphrase index page)|
|4|givastomig natlawreview URL truncated "gi..."|✗ unresolvable URL|same quote, full URL|✓|
|5|SHR-A1904 option, BioSpace quote|✓|same|✓|
|6|SKB315 headline "exits CLDN18.2 program"|✓|same URL, flagged "paraphrase via search"|weak (self-disclosed)|
|7|JS107 holder from NCT07284134|✗ sponsor only|JS107 NCT + NCI dictionary|✗ for rights (sponsor only)|
|8|BL-M05D1 holder from NCT07518147|✗ sponsor only|same, with quote|✗ for rights|

Unsupported or miscited rights claims: **C3 4/8, B 2/8 unsupported + 2/8 weak**. B also has a truncated RC118 URL
(404, verified) and a "WebSearch summary" citation for VBC108.
Neither workflow is clearly more checkable. C3 does not meet criterion (iii).

## 5. BD Finance audit

**B** (`B_general/valuation.md`, all figures reproduced by me):
- Peak = 6000×150000×0.15 = $135M ✓.
- Development NPV (Ph3 asset) = −180 − 0.5×20/1.1³ = −187.5.
- Sales NPV = 0.45×Σ_{y=1..12} 135·min(1,y/5)·0.40/1.1^(3.5+y) = 89.7.
- Acquisition = −400 − 187.5 + 89.7 = **−497.8 ✓**.
- License = −100 − 0.45×500/1.1⁴ (153.7) − 187.5 + 89.7×0.28/0.40 = **−378.4 ✓**.
- Perspective is the buyer, payments are risked, and the bull<base license ordering is explained (milestones
  likelier). Every number is reproducible from disclosed inputs.
- Weaknesses: a flat 40% margin with no tax, no LOE tail, and the formula is the analyst's own.

**C3** (`C3_dealscreen_final/valuation.md`):
- Peak = 6000×150000×0.15×**0.80** = $108M ✓. P(approval) 0.45 / 0.1575 ✓. BLA PV 20/1.1^3.5 = 14.33 ✓.
- License cost PV = 163.2 + 100 + 100×0.5/1.1³ (37.57) + 400×0.45/1.1⁴ (122.94) = 423.7 ✓.
- Acquisition −68 − 400 = −468 ✓.
- **Not reproducible:**
  - Ph3 cost PV 156.02. Mid-year discounting gives 156.49, so the engine timing convention is undisclosed.
  - Operating PV 212. A linear ramp with after-**tax 21%** margin (1−.12−.25)×0.79 gives ~198, and with no tax
    ~251. The 21% (`effective_tax_rate: 0.21` in valuation JSON, e.g. C2 `valuation_runs/CL-27.json`) appears
    nowhere in C3's valuation.md or memo (grep "tax": 0 hits). The residual ~14 is the uptake/SG&A ramp and LOE
    tail, which are undisclosed.
  - Bear/bull shocks are undisclosed. C3 itself flags bear>base (license) as an "ANOMALY" it cannot explain.
    It is in fact economically coherent (the same mechanism B explains).
  - The SKB315 standalone trial PV 101.8 is not decomposed.
- These are therefore unreproducible numbers presented as results: the operating PV, rNPV base, and every bear/bull.
- Defect labels:
  - 0.80 compliance invisible: P1, engine.
  - Tax not in summary: P8, engine; the prototype print was added, but the analyst never carried it to the
    deliverable.
  - Shocks not listed: P9, engine.
  - Order warning console-only: P10 → P10b, **DealScreen**, fixed after C3.
  - Revenue-PV label: P3, engine.
  - QLS31905 valued identically to LM-302: an analyst input choice.
- Under the protocol's "unreproducible valuation numbers" clause, **C3 carries critical errors that B does not.**

## 6. Effort (AI-simulated; not a human claim)

| | Tool calls | Workarounds |
|---|---|---|
| A | ~19 (A LOG) | — |
| B | ~16 (B LOG) | 0 tool-workarounds; corrected vendor modality errors by hand |
| C3 | ~30 (C3 LOG) | 3: buyer YAML copied to add `transaction`; `value-config` + prototype CLI because `value` needs human-SELECTED finalists; IBI343 rights proposal inert without a human. 32 agent findings were inert ("funnel unchanged after research") |

C3 used about twice B's effort for lower recall.

## 7. Decision rule

**C3 vs B**
- (i) Fewer critical errors? No. Screening and shortlist are tied at 0. On finance, C3 has unreproducible
  operating PV and scenario figures while B has none, so **B wins (i)**.
- (ii) IN found ≥ B−1 (29)? **No**: 23 (26 even under the strict reading).
- (iii) More checkable? **No** (§4).

**Verdict: no demonstrated advantage over B.**

**C3 vs A**
- (i) A has 1 wrong exclusion (SOT102) and fully reproducible spreadsheet math; C3 has 0 wrong exclusions but
  unreproducible valuation outputs. This is roughly a tie, so not "fewer" for C3.
- (ii) 23 vs 28 (A−1): **fails**.
- (iii) Not demonstrated.

**Verdict: no demonstrated advantage over A.**

## 8. Lists

**(a) DealScreen better than B (evidence)**
- Zero false ELIGIBLE across 62 rows despite vendor noise (tool_disposition column).
- It refuses paraphrased rights quotes (C3 LOG), where B accepted self-declared paraphrases (B calls CL-27, CL-16).
- RETURNED/OPTION rights states exist and the memo shows them (FIXES X4; C3 calls CL-07, CL-27, CL-08).
- The transaction tier is separated from science and demotes the AZ/Astellas records.
- Identity alias flags for code/INN triplets, with row accounting.
- The engine valuation includes tax, LOE tail and Monte Carlo, which B's flat model lacks, if it were disclosed.

**(b) B better**
- Recall (30/30 vs 23/30).
- Resolves vendor errors (LCB02A) from cited text.
- Every valuation number reproduces by hand, and B explains the license scenario ordering.
- Lower effort.
- Ranks SKB315/ATG-022 nearer the reference top, and finds RC118/VBC108.

**(c) Failures that could cause costly BD decisions**
1. The indication gate leaves Phase 3 gastric programs UNRESOLVED (CMG901, AZD5863, givastomig). An analyst
   anchored on it drops real candidates (RC118).
2. The OPEN tier on Takeda-held IBI343 and option-encumbered SHR-A1904 (#3). Sponsor-only holder matching creates a
   false impression of openness.
3. Vendor modality errors propagate to EXCLUDED and need a human to fix (LCB02A).
4. Valuation outputs whose tax, compliance and shocks the deliverable never states.
5. Noise rows (rilvegostomig rank 2) remain UNRESOLVED at high rank, wasting diligence time.
6. Agent findings are inert in an AI-only run.

**(d) Reusability vs tuning**
- Generic: X2 (partial dates), X4 (rights states), X5 (transaction view, buyer-declared), X6 (partial target sets;
  applies to any T-cell engager), X7 (cwd ontology), P10b.
- **X1 (isoform "<name> n.m" → gene) is the most landscape-shaped fix.** It is generic in form, but it was
  motivated only by "Claudin 18.2". It also needed a guard after a wrong-isoform PASS (FIXES review: CLDN18.1). It
  cannot distinguish isoforms, so in any isoform-specific landscape it is a standing PASS risk. I flag it as tuned
  to CLDN18.2 in origin.
- X3's biomarker-prefix rule ("<marker>-positive X") was derived from CLDN18.2 condition strings. It was
  generalised and held-out-checked on 75k strings, but it under-delivered here.
- The `deprioritized_holders` list is analyst-typed per run, not a reusable authority.
