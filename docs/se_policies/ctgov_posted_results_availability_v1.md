# CTGOV_POSTED_RESULTS_AVAILABILITY v1 — source-availability survey (preregistration)

Research retrieval only. No change to production acquisition, extraction, facts, gates, ranking or validation results. No extractor is built. Target alias, human-PoC precision-first, modality, identity, qualification and ESG401 stay parked. H21–H25 are sealed and H6–H10 unrun.

## Boundary confirmed before collection

`ClinicalTrialsGovConnector._live_search` keeps only `protocolSection` (`connectors.py`). The only `ClinicalResult` emitter hardcodes `incomplete_reporting=True`. The API is reachable: v2 `apiVersion` 2.0.5, `dataTimestamp` 2026-10-14T09:00:05.

## Cohort (frozen in `research/se_ctgov_posted_results_availability_v1/cohort.json`)

- **1,932 unique NCT IDs** from tac01_protoid_v1 and mint5_protoid_v1 CT.gov snapshots (non-holdout development; both runs as-of 2026-09-24).
- Deduplicated by NCT; source pools recorded.
- 3 NCTs also appear in exposed H16/H18/H19 snapshots. They stay in the cohort and are flagged diagnostic-only.
- No exclusion by results or outcomes.

## Phase 2: census (metadata only)

`GET /api/v2/studies?filter.ids=<≤100 ids>&fields=NCTId,Phase,OverallStatus,PrimaryCompletionDate,HasResults,ResultsFirstPostDate,LastUpdatePostDate&pageSize=1000`. That is ≤ 20 requests, 1 request/second; each raw response is saved with SHA-256 and timestamp. Cohort IDs absent from responses are recorded as MISSING, separate from HTTP errors.

## Phase 3: sample (rule frozen now; applied to census output)

Among `hasResults=true` studies, strata by phase group (EARLY = PHASE1/EARLY_PHASE1, PHASE2 incl. PHASE1|PHASE2, LATE = PHASE3/PHASE4/PHASE2|PHASE3, OTHER/NA). Take the first **8 per stratum** ordered by `sha256(nct)`, plus **4 negative controls** with `hasResults=false` (first by the same order). Full records are retrieved with `GET /api/v2/studies/<nct>` (≤ 36 requests). The unit is **each PRIMARY outcome measure** (cap: first 2 per study). Packets contain the outcome, groups, measurements, analyses, arms and interventions, and the dev-run candidate names linked to the trial.

## Phase 4: adjudication

Done by an **independent agent context** that sees the packets and category definitions only. Exactly one class per outcome:

- NO_POSTED_RESULTS
- POSTED_WITHOUT_USABLE_OUTCOME
- NON_EFFICACY_OUTCOME
- NUMERICAL_OUTCOME_WITH_UNRESOLVED_PRODUCT
- NUMERICAL_OUTCOME_WITH_RESOLVED_PRODUCT
- POTENTIAL_HUMAN_EFFICACY_EVIDENCE

Flags: ambiguity, incomplete, mixed population, conflict; plus a design note covering single-product, combination, comparator, crossover, pooled and multi-cohort. **POTENTIAL** requires all of: treated humans, candidate identity, arm attribution, an observed disease-relevant outcome, a magnitude, a benefit direction and exact provenance. A regimen outcome is never assigned to each constituent. Labels are frozen before verdicts. No `human_poc_present` is set.

## Phase 6: point-in-time

`ResultsFirstPostDate > 2026-09-24` means the result was **POST_AS_OF**: present-day availability only, never historical replay. Results posted on or before the as-of date are "posted before as-of", but their numerical content at that date is **unverified** without historical versions. They are not claimed as historically present.

## Readiness (computed by `analyze.py`, self-tested)

- **SOURCE_AVAILABLE:** ≥ 10% of retrievable cohort studies have results **and** ≥ 50 such studies.
- **ATTRIBUTION_FEASIBLE:** ≥ 8 distinct sampled studies with an outcome classed RESOLVED_PRODUCT or POTENTIAL, **and** 0 negative controls classed POTENTIAL.
- **IMPLEMENTATION_DESIGN_JUSTIFIED:** both of the above, plus ≥ 5 distinct studies with POTENTIAL, plus a Wilson 95% lower bound of the POTENTIAL study fraction (among sampled results studies) ≥ 0.15.

Verdict:
- **JUSTIFIED** if all three hold;
- **LIMITED** if SOURCE_AVAILABLE holds but not all;
- **STOP** if SOURCE_AVAILABLE fails.

Only JUSTIFIED permits proposing `CTGOV_POSTED_RESULTS_SOURCE v1`, and not implementing it.

`DATA_SOURCE_POLICY.md` (Biotech Tool Context) is not in this repository. Its CT.gov "partial point-in-time" classification is applied as described by the user.
