# ACR/company discovery v1 — development result

**Narrow source-discovery improvement: PASS (1 primary endpoint success).**
**End-to-end scientific eligibility, licensing availability and independent BD usefulness:
not established.** Read the [concise analyst brief](BRIEF.md).

The previously missing HXN-1031 was nominated from a primary ACR abstract reached via generic
query Q1 at rank 9. The URL did not contain the product name. The page explicitly establishes
an engineered, named CD19/BCMA/CD3 trispecific antibody with autoimmune intent and preclinical
experiments. It establishes neither clinical activity in autoimmune patients nor current
programme status, worldwide non-approval, ownership or availability. It is a research lead.

## Design, timing and scope

- Preregistration commit: `e9a2d0a`, before any new search or acquisition implementation.
- Search specification, reference labels and endpoint rules are covered by `FROZEN.sha256`.
- Base code: `58432ad`; no production files or frozen historical experiments changed.
- Four fixed generic queries; 12 ACR and 12 issuer-page ceilings; no follow-link expansion,
  failed-page replacement, named-asset queries, reference URL seeding or post-hoc query changes.
- The prior reference was already exposed to the implementing agent. This is a development
  source-recovery experiment independent of reference-name seeding, **not blind validation**.
- Existing `DeclaredUrlConnector`, bounded public HTTP, `CorpusStore` and
  `extract_observed_asset_names` are reused unchanged. This harness stops at nomination;
  it does not bypass scientific gates by calling its outputs eligible assets.
- Four search-tool calls and 18 selected page fetches. No paid APIs, cloud instances or
  full-scale replay. Acquisition/nomination: 17.94 s, 77,756 KiB peak RSS, 4 GiB limit, 20-minute timeout;
  search and manual adjudication time are excluded.

## Stage accounting

| Stage | Observed result | What it does NOT establish |
|---|---:|---|
| Search results | 70 | Primary-source evidence |
| Selected/attempted pages | 18 | Successful retrieval |
| Fetched/indexed pages | 17 | Product-specific scientific evidence |
| ACR indexed | 12 | Peer-reviewed or clinically validated findings |
| Company indexed | 5; 1 failed | Relevant content or company ownership of each mentioned product |
| Literal name nominations | 643 | Drug assets |
| Normalized nominated strings | 306 | Entity-resolved, deduplicated products |
| Manually identified investigational programmes | 4 | Complete adjudication of all 306 strings |
| New primary endpoint successes | 1: HXN-1031 | Clinical eligibility or an available deal |
| Scientific eligibility evaluated | 0 | No unchanged full-engine gates were run |
| Confirmed BD opportunities | 0 | Commercial rights and availability remain UNKNOWN |

Manual evidence adjudication is in `evaluation/adjudication.json`; results, including every
frozen reference entry's blockers, are in `evaluation/results.json`. Evidence spans use exact
character offsets and hashes into locally retained parsed primary text, avoiding publication
of full source articles. Raw HTML hashes, source URLs, publication metadata and query/rank
provenance are retained. This is traceable manual interpretation, not automatic fact confirmation.

## What improved and what did not

Three names absent from the historical A_base nominations were recovered: HXN-1031, CDR111,
and cizutamig. Only HXN-1031 satisfies every frozen primary-source requirement on the acquired
pages. For CDR111/cizutamig, explicit antibody format was not established on those pages and
was not inferred from outside knowledge. They retain follow-up value but no endpoint credit.

Company-source retrieval provided KT501's issuer-reported Phase 1a RA first-dosing evidence.
KT501 was already in A_base and lacks the prior fully_verified label, so earns no new-discovery
credit. The existing labels were not upgraded to fit the outcome. **No company-only primary
discovery success was demonstrated.**

The historical A_base had nominated CLN-978/OM336 among the eight fully quoted relevant
reference assets. This bounded supplement is not a rerun of that landscape: it omits those
names and others. No 2/8-to-new-recall improvement is asserted. Old source access, search
rankings and historical page versions were not reconstructed. The HXN-1031 page declares a
2025 publication date, but current bytes do not prove historical availability. The sealed
three-arm experiment remains untouched and unfinished.

Controls: blinatumomab/teclistamab remain approved reference comparators, GC012F is a CAR-T
with myeloma evidence, and IMC-002 is outside the requested target/format. None receives
primary success. No generic constructs are promoted. Other nominations are not all adjudicated;
we do not report a population precision or an absence-of-error rate for them.

Failures/limitations:
- Tempest issuer page failed; no backfill. Antengene returned a broad newsroom and Imviva
  largely a navigation shell. HTTP/parser success is not relevant-evidence success.
- Navigation, author names and ordinary prose dominate many nominations. These are literal
  mentions, not claims that the full engine would admit them as assets. No qualification
  rules were changed or parked experiment reopened.
- QYM1 appears in a fetched abstract but was not nominated by the unchanged extractor.
  This exposed exploratory miss receives no manual recovery credit or retrospective gold label.
- LBL-051, A-319 and gamgertamig remain absent. Syndicated LBL-051 search hits were not
  accepted as issuer-primary evidence or converted into direct issuer URLs.
- Generic discovery used the connected search tool plus the research harness. ACR is not
  activated in the production connector registry; default end-to-end search is unchanged.
- Current official-page evidence does not verify territory-specific rights, availability,
  clinical efficacy, current stage or global approval status.
- ACR pages may describe forthcoming November 2026 presentations; publication metadata is
  distinguished from meeting date. No presentation is described as already delivered.

## Reproduce without network or additional acquisition

Run from the repository root; these commands are documentation, not a request for the user
to execute them. The agent executed the score reproduction and compared its bytes.

```bash
.venv/bin/python research/se_acr_company_discovery_v1/evaluate.py \
  --run research/se_acr_company_discovery_v1/run_live_v1 \
  --output /tmp/bve-acr-company-score-repeat-2.json
```

Use a fresh output filename: overwriting is refused. Deterministic nomination replay uses
`acquire.nominate(CorpusStore(run / 'corpus').documents())`; it reproduces the sealed
`nominations.json` exactly. Rank selection also reproduces from the saved search receipts.
The tests guard reference reads during acquisition and reject unsurfaced names, changed sealed
bytes, prior recoveries, missing format evidence and approved comparators during scoring.

For a deliberately authorized later source refresh, the exact live invocation was:

```bash
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=src \
  /usr/bin/time -v -o /tmp/bve-acr-company-refresh.time \
  timeout --signal=TERM --kill-after=30s 1200s \
  .venv/bin/python research/se_acr_company_discovery_v1/acquire.py \
  --output research/se_acr_company_discovery_v1/run_refresh_v2
```

That command re-fetches the selected URLs and is **document replay/refresh**, not another
independent discovery success. A new discovery evaluation needs a new preregistration and
fresh generic query receipts. The actual live run was `run_live_v1`, not the refresh example.

## Artifact custody and sharing

Local raw search responses: `search_receipts/Q1.json`–`Q4.json`; hashes in
`search_receipts.sha256`. Local raw HTML, parsed corpus, source index and sealed nominations:
`run_live_v1/`. Both directories are intentionally Git-ignored and preserved locally.
They contain public publisher content, not a newly distributable article collection.

Committed `results/` contains source metadata, acquisition health, fetch receipts, nominations,
runtime metrics and a copy of the input seal. `selection.json` records all 70 ranked results,
inclusion/exclusion reasons and the six issuer sources. `publisher_adjudication.json` explains
issuer-domain classification; no inclusion decision depends on a reference label.
A clean Git clone has metadata and results but needs the local raw directories for exact
nomination/score reproduction. Do not pretend that hashes can reconstruct missing source bytes.
The HTTP user-agent contact is never published; only its hash/presence receipt is retained.
The runtime code_head is the preregistration commit; acquisition_code_sha256 pins the exact
then-uncommitted implementation, which is unchanged in the final implementation commit.

## Final output review

Implementing-agent desk audit of the FINAL brief: under 1,200 words; names, target descriptions,
preclinical versus clinical evidence, primary links, uncertainty and next checks are explicit.
No efficacy, approval, ownership or availability claim is strengthened beyond the source.
The preclinical success is not described as meeting the desired Phase 1+ diligence population.
This audit is **not independent**. No independent BD professional evaluated the final brief;
that assessment and analyst time-to-candidate measurement remain **OUTSTANDING**.

Next smallest useful step: confirm one clinical follow-up lead's antibody format, autoimmune
trial-level data, current status and rights from issuer/registry records, then obtain independent
BD review. Source recovery alone does not establish a diligence-ready opportunity.
