# Two-asset source verification and analyst handoff

Start with [BRIEF.md](BRIEF.md), then [TRIALS.md](TRIALS.md) for record-level context.
This is user-authorized named follow-up to discovery v1, **not another discovery experiment**.
No prior source-acquisition result was rerun, rescored or given retrospective credit.

## What changed

- UCB's June 17, 2026 completion announcement establishes cizutamig's BCMA×CD3 bispecific
  antibody format and placement in UCB's pipeline after acquiring Candid. The wording refers
  to the announcement date, not an independently established legal closing date. Its September
  29 disclosure corroborates continued clinical development. Complete current rights remain unverified. A subsequent bounded check of an SEC-filed Candid
  presentation and EpimAb disclosure verifies the historical ex-Greater-China license; the brief
  retains that carve-out and requests current amendments.
- Registry protocols explicitly connect cizutamig/CND106 and autoimmune indications to Phase 1
  studies (SLE/gMG titles specify 1b). Nine returned records are not nine active autoimmune
  trials: withdrawn, healthy-volunteer and not-yet-recruiting records remain visible.
- HXN-1031 retains its preclinical CD19/BCMA/CD3 classification. The ACR abstract was reacquired
  into this new follow-up directory; Earendil's publisher-linked JavaScript contains the exact
  named program row. This supports program attribution, not legal ownership. Zero CT.gov
  spelling matches do not prove no clinical entry. Current IND/clinical status and rights are unknown.
- Reusable research-only handoff code reuses existing Assessed/Source types, requires sourced
  supported assertions, separates commercial context from maturity/rights, verifies archived
  evidence pointers, and renders a concise brief deterministically. No production rule changed.

[ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) records where existing acquisition, name-shape
triage, identity contracts and reporting can/cannot support these distinctions. These two manual
dossiers are more accurate and actionable; general qualification accuracy is unmeasured.

## Evidence and limits

PLAN.md was written before new searches and implementation; PLAN.sha256 records it.
The two subjects were supplied by the user. Nine named follow-up web queries found primary
sources; secondary summaries were navigation leads only. No new gold dataset or recall score.
Primary acquisition: seven HTML pages, two CT.gov query responses, one linked Earendil JavaScript
bundle. A sandbox-denied attempt is retained in raw/run_01; the authorized public-network
attempt is raw/run_02; the two additional rights disclosures are in raw/run_03. No paid API, cloud job, full discovery replay or new dependency.

acquisition_receipts.json records URLs, timestamps, decoded-payload hashes and connector health.
evidence.json records exact character spans or JSON paths and their hashes; no full publisher
articles are published. raw/ retains fetched data and parsed passages locally and is ignored by Git.
The bundle row is direct publisher-hosted data; no JavaScript was executed. Its pipeline stage
array is not promoted to a clinical-entry claim. UCB dates were read from body text because the
existing publication parser returned None; observations were not backdated.
The archived run's corpus as_of_date is the local date, 2026-10-23; its retrieval timestamps
and this handoff use 2026-10-24 UTC. No historical replay is evaluated. The acquisition utility
now uses UTC for future runs; the original captured metadata is preserved unchanged.

The ACR safety abstract reports heterogeneous uncontrolled observations, not established efficacy.
Registry planned enrollment is not treated-patient count. No trial returned posted results.
No scientific gate, alias authority, candidate-qualification rule, human-PoC standard, frozen
threshold, holdout or old artifact was modified. No availability or comprehensive current-rights claim. Historical license exclusions are reported
from primary disclosures, without assuming that acquisition superseded them.

## Reproduce locally, without new acquisition

From the repository root, with the retained local raw/ directory:

```bash
.venv/bin/python research/se_lead_verification_v1/handoff.py \
  --output /tmp/bve-lead-followup-repeat.md
```

The output filename must be fresh. The renderer verifies archived evidence before writing.
Compare the output to BRIEF.md; no web calls or engine run occur. A Git clone includes the brief,
structured facts and provenance but cannot reconstruct raw evidence from hashes alone.
The focused tests use synthetic custody checks plus committed facts; they do not require raw data.

For intentional future refreshing, acquire.py accepts a fresh --output directory and sources.json;
it is named verification, not new discovery. The Earendil bundle URL came from the saved pipeline
HTML and was fetched once through existing bounded get_text, not an inferred asset endpoint.
Source refreshes require fresh interpretation: never silently replace the archived evidence or brief.

## Review and next milestone

Implementer desk audit only: each material claim in the two cards links to primary evidence or
is explicit UNKNOWN/UNVERIFIED; the cards separate investigational maturity, acquired status,
rights and availability. Negative trial status and serious safety events remain visible.
Independent BD final-output assessment and analyst time-to-action are **OUTSTANDING**.
This is a usable research handoff for expert review, not demonstrated independent BD usefulness.

Next smallest operational step: have a BD professional assess these two finished briefs, then
carry the source-linked verification record into the existing candidate cards and test one additional
independently discovered clinical lead. Target the known date/shell acquisition failures in separately
scoped engineering work rather than building another crawler.

Engineering validation: [VALIDATION.md](VALIDATION.md) and [REGRESSION.md](REGRESSION.md).
Final full scientific suite: 2,000 passed, 3 xfailed. The timing test now isolates cyclic GC
using standard timeit; its sizes/threshold and all scientific requirements are unchanged.
