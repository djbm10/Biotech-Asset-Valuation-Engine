# HUMAN_EFFICACY_COVERAGE_DIAGNOSIS v1 — why 0/40 confirmed dual CD19/BCMA assets carry human efficacy

**Status:** FROZEN 2026-10-05. This is diagnosis only: no reader, threshold, source rule,
ranking rule or attribution behaviour was changed.

**Population.** Every asset in `~/se_runs/mint5_armid_v1` whose `target.expression` decision
is PASS: 40 assets, all with `evidence.human_poc` = UNKNOWN.

**Evidence used:**
- `research/se_human_efficacy/corpus_evidence_v1.json`, produced by
  `scripts/diagnose_human_efficacy_coverage.py`. For every document in the sealed corpus that
  mentions each asset, it lists the current strict reader's statements and every looser
  sentence that names the asset next to an efficacy term and a number.
- `research/se_human_efficacy/registry_meta_v1.txt`: status, start date and sponsor of each
  linked CT.gov record.
- A small number of targeted public searches. The search tool began refusing these queries
  partway through, so public verification is incomplete, and every asset I could not verify
  is classified **D**, not A.

**Definitions.**
- Human efficacy is the existing strict definition: observed clinical efficacy attributable to
  the same asset. Regimen and background protections apply. Planned endpoints do not count.
- The as-of date is 2026-09-24.

## Result

| Category | Count |
|---|---|
| **A** — no public human efficacy result can exist yet | **20** |
| **B** — public result exists; the sealed corpus lacks the source | **1** |
| **C** — the corpus holds the evidence; attribution or identity failed | **3** |
| **D** — ambiguous or unverifiable | **16** |

### A (20)

The trial is not yet recruiting, withdrawn, or suspended, or it started on or after
2025-07, and the corpus holds only the registry record:

- Allogeneic CD19/BCMA CAR-γδT (NCT07490275)
- allogenic anti-CD19/BCMA CAR-T (NCT07261345)
- anti-CD19/BCMA U CAR T (NCT07241468)
- anti-CD19/BCMA U CAR T cells (NCT07246096)
- anti-CD19/BCMA-UCAR-T cells (NCT07558850)
- Autologous BCMA/CD19 dual-target CAR-T module (NCT07523555)
- CD19-BCMA dual nanobody CAR-T (NCT07451236)
- CD19/BCMA in vivo CAR-T (NCT07388212)
- CD19/BCMA-targeted CAR-T lentiviral vector drug (NCT07490951)
- CD19/BCMA-Targeted Universal CAR-T (NCT07423572)
- Fast Dual CAR-T (NCT04877080, withdrawn)
- FIT-(BCMA+CD19)-CAR-T (NCT07604792, suspended)
- KSVCBD (NCT0759…/0761…, 2026)
- KT501 (NCT07234773)
- QT-019C (2026)
- QT-219CX (NCT07586267)
- Anti-CD19/BCMA CAR gene vector injection (NCT06973356, NCT07121777)
- umbilical cord blood CD19-BCMA CAR-T (NCT06947473)
- IL-15-armored CAR-T (NCT07509086)
- OriV508 (NCT07101705)

For these, UNKNOWN is the truthful answer.

### B (1)

**Asset:** "Assigned Interventions CD19/BCMA CAR T-cells", from Zhejiang University
NCT05030779 and its sister records.

| Field | Value |
|---|---|
| Public evidence | Feng et al., *Nat Med* 2025;31:3725, epub 2025-09-24: 12/15 (80%) met LLDAS + DORIS remission at week 12 |
| Monotherapy or combination | **Combination.** The trial *co-infuses* two separate products, an anti-CD19 CAR-T and an anti-BCMA CAR-T. The result belongs to the co-infusion, not to one construct. |
| Why the pipeline missed it | The sealed corpus contains only the four registry records and no publication. |

Even if acquired, the result would attach to an unnamed arm label for a two-product regimen.
The adopted regimen protections would refuse to give it to either product, which is correct.

### C (3)

**AZD0120**

| Field | Value |
|---|---|
| Evidence | PMID 41925575, in the corpus: NDMM, age ≥70, 2 cycles of VRD then AZD0120; "All patients achieved a stringent complete response … MRD negativity … 100%", n = 8 |
| Monotherapy or combination | Sequenced after VRD induction; the cell product is given alone after induction |
| Why it was missed | The result sentence does not name the asset ("All patients achieved…"). Sentence-scoped attribution refuses the cross-sentence link by design. |

**GC012F**

| Field | Value |
|---|---|
| Evidence | PMID 39052306, in the corpus: NDMM after 2 induction cycles; "all 19 patients showed stringent complete responses and achieved MRD negativity" |
| Monotherapy or combination | Sequenced after induction |
| Why it was missed | The same cross-sentence pattern. The one sentence that does name GC012F ("GC012F demonstrated a rapid response … median time to first sCR of 84 days") fails the human-population requirement. |

**BCMA-CD19 cCAR T cells (iCell)**

| Field | Value |
|---|---|
| Evidence | The corpus holds human-PoC evidence that the pipeline already accepts, but under the separate asset **ICG318**, which is iCell's BCMA-CD19 compound CAR (public: J Hematol Oncol 2026, 10/12 sCR in SLE). ICG318 is mint5 #1 with target UNKNOWN and human-PoC PASS. The cCAR asset is target PASS and human-PoC UNKNOWN. |
| Why it was missed | **An identity split, not an efficacy-reader failure.** No authority links the development code ICG318 to the descriptive name "BCMA-CD19 cCAR T cells". |

### D (16)

The trial started before 2025-07 and is recruiting or of unknown status. The corpus holds no
efficacy evidence, and public results could not be confirmed or excluded:

- allogeneic cord blood-derived dual-targeting CD19/BCMA (NCT07139509)
- allogeneic UCB-derived CAR-T (NCT07274059)
- "Anti-BCMA and CD19 CART cells will be injected…" (NCT06503224 and others)
- ARI0003 (NCT06097455; the corpus has preclinical only)
- BCMA/CD19 dual-target CAR-T immunotherapy (NCT04412889, 2020, MM)
- CAR-T Autologous T cell injection (NCT05618041)
- CD19-BCMA Targeted CAR-T Dose 1 (NCT06371040, MG; the search was refused)
- CD19/BCMA Lupus Nephritis CAR-T (NCT06785519)
- CD19/CD20/BCMA CAR T cells (NCT06446128)
- CD19/CD20/BCMA CAR-T (NCT06732232)
- FKC289 (NCT06285279; searched, none found)
- KN5601
- PRG-2311 (NCT06497361; searched, none found)
- UCAR T-cell
- UCAR T-cell group
- universal allogeneic anti-CD19/BCMA (NCT06733610)

## Decision (per the operator's frozen rule)

**A dominates (20/40), and only 1 asset is B.**

The C cases do not support loosening the efficacy reader:

- **Two of the three C cases** (AZD0120, GC012F) fail on cross-sentence attribution. That
  refusal is a deliberate, adopted precision rule. One result sentence would also bring in a
  regimen-sequencing question (induction then CAR-T).
- **The third C case is an identity defect.** ICG318 and the iCell BCMA-CD19 cCAR are one
  programme under two unlinked names.

**Therefore:**

1. **No efficacy-reader change is justified.** UNKNOWN is truthful for the A majority. The B
   case would be refused anyway, as a two-product co-infusion.
2. **The material finding is identity, not efficacy.** It is a candidate for a separate
   milestone, but it must not be fixed by a name list. An adopted rule already refuses to
   merge development codes to products without authority; any successor would need a
   structured authority (for example NCIt, which files ICG318-type codes as synonyms of their
   product concept). That milestone is not started here.
3. **Next milestone, per the operator's plan:** NCIt-backed modality coverage. This diagnosis
   leaves the identity question open for a separate decision.

**Limitations.**
- Public verification relied on a few searches before the tool began refusing these queries.
- D is large (16) for that reason.
- A is inferred from registry status and dates. It is not proven absence.
