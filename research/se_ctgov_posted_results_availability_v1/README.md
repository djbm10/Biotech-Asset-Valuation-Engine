# CTGOV_POSTED_RESULTS_AVAILABILITY v1 — STOP (source availability below threshold)

Prereg `eefd8a2` (`docs/se_policies/ctgov_posted_results_availability_v1.md`); census/sample/packets `bd08469`; independent adjudication frozen before verdict. Research retrieval only; no production change. API v2.0.5, dataTimestamp 2026-10-14T09:00:05. Raw responses: `~/se_runs/ctgov_posted_results_availability_v1/` (20 census batches and 36 full records, all hashed in `raw_hashes.txt`, all HTTP 200, **0 missing**). Reproduce offline: `python research/se_ctgov_posted_results_availability_v1/analyze.py --output <dir>`; two builds are byte-identical.

## 1. Availability (census, 1,932 unique NCTs)

**164 with posted results = 8.5%** (Wilson 95% 7.3–9.8%). The preregistered SOURCE_AVAILABLE requires ≥ 10% and ≥ 50 studies, so it **FAILS** on the rate (the count passes).

| Phase | Studies | With results |
|---|---|---|
| Phase 1 / early | 908 | 36 (4.0%) |
| Phase 2 | 677 | 98 (14.5%) |
| Phase 3/4 | 92 | 16 (17.4%) |
| Other / NA | 255 | 14 (5.5%) |

By status: completed 92/295 (31%), terminated 46/127, active-not-recruiting 26/196; recruiting, not-yet-recruiting, unknown and withdrawn all 0. The dev cohort is dominated by early, ongoing cell-therapy trials, which structurally have no results.

## 2–4. Sampled outcomes (32 results studies × ≤2 PRIMARY outcomes + 4 negative controls = 50 packets), independently adjudicated

| Class | Packets |
|---|---|
| NON_EFFICACY_OUTCOME (safety, DLT/MTD, PK, feasibility) | 20 |
| POSTED_WITHOUT_USABLE_OUTCOME | 4 |
| NUMERICAL_OUTCOME_WITH_UNRESOLVED_PRODUCT | 1 |
| NUMERICAL_OUTCOME_WITH_RESOLVED_PRODUCT | 13 |
| **POTENTIAL_HUMAN_EFFICACY_EVIDENCE** | **8 (6 distinct studies)** |
| NO_POSTED_RESULTS (negative controls) | 4 |

- **Numerical efficacy outcome studies:** 16 distinct studies have a RESOLVED or POTENTIAL outcome, so ATTRIBUTION_FEASIBLE **PASSES** (≥ 8; 0 negative-control violations).
- **Potentially usable:** 6/32 studies, 18.8%, Wilson 95% 8.9–35.3%. The lower bound is below the preregistered 0.15, so IMPLEMENTATION_DESIGN_JUSTIFIED **FAILS**.
- **The 6:** axi-cel ORR 83% (NCT02348216); blinatumomab ORR by dose (NCT01741792); cilta-cel randomized PFS vs standard care (NCT04181827); Treximet crossover pain-free (NCT00573170); elranatamab ×2 (NCT05932290, NCT05565391). Both elranatamab studies are **external real-world-control comparisons**, not randomized arms, so their benefit inference is weaker.

## 7. Failure classes

- **Primary outcomes are mostly not efficacy:** 20/46 posted primaries are safety, DLT or PK, typical of phase 1.
- **Regimen/combination and multi-cohort designs** (9 + 9 packets): outcomes belong to regimens or cohorts, never to constituents.
- **Incomplete reporting** (12 flags) and dose-level groups.
- **Attribution needs result-group text**, not protocol arm IDs. The adjudicator resolved products from group titles and descriptions. A production extractor would need that mapping, and it isn't guaranteed.

## 8. Point-in-time

161/164 results were first posted on or before as-of 2026-09-24, but their **content at that date is unverified** (current API version only, no historical record version). 3 were posted after the as-of date: present-day availability only. Consistent with CT.gov's partial point-in-time classification, none of this supports historical benchmark replay.

## 9. Disposition

**STOP. A posted-results extractor is not justified on this cohort.** The structured source exists and attribution is often feasible, but in this engine's development cohort only ~8.5% of trials have results, and roughly 1 in 5 of those yields a usable efficacy observation: about 1.6% of trials, ~30 studies (estimate). Human-PoC remains without a structured route. Do not compensate with a free-text classifier.

The engine's query mix (early cell-therapy and bispecific programs) is the worst case for posted results. A cohort weighted toward later-stage or completed programs would score differently, but that would be a different, separately preregistered question, not a re-cut of this one.

## Disclosures

- The self-test's "valid" fixture first reused the real census and so could never pass. Fixed (fixtures get their own census) before the verdict was read; the rules are unchanged.
- The adjudicator's chat summary (NON_EFFICACY 22, RESOLVED 14) disagrees with its own written file (20, 13). The written, frozen file is authoritative.
- `DATA_SOURCE_POLICY.md` is not in this repository; the point-in-time rule follows the user's description.
