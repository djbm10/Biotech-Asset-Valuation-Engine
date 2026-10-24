# S&E development handoff — 2026-10-23

Status: bounded infrastructure/workflow improvement; analyst-assisted pilot remains
UNVALIDATED and only partly useful. No full-scale arm run locally. No new discovery claim,
scientific GO, validation promotion, licensing-availability assertion or independent expert
endorsement. No paid infrastructure was provisioned.

## Implemented

- Read-only migration preparation/verification: allowlisted runtime inputs, complete streamed
  SHA-256 inventory, dereferenced ontology, exact environment pins, original absolute paths.
- Cloud wrapper: explicit authorization flag, available-RAM check, payload and installed-version
  checks, lock, three sequential arms, fail-fast, one 36-hour limit, exact output-path receipts,
  separate A and B comparisons. Original runner/preflight/scientific inputs untouched.
- Brief stage evidence now explicitly warns that indication-specific stage is unverified.
  Hashing no longer loads a 400 MB result file into memory. The brief JSON parser still does;
  this change does NOT claim memory-bounded loading of full engine results.
- A separate offline reference-assisted analyst worklist: 19 existing frozen reference entries,
  exact original categories and ANY/ALL annotations, six fact fields with quotation status,
  original source links/passages and caveats, human efficacy unverified, rights unknown.
  This exposes leads for manual investigation; it is NOT a new discovery connector or engine
  output and must never be used to inflate engine recovery.

Change classification and predeclared workflow acceptance: `CHANGE_REQUEST.md`.

## Open and regenerate

Latest reference-assisted worklist:
- `research/se_pilot_handoff_v1/reports/brief.html`
- `research/se_pilot_handoff_v1/reports/brief.md`
- `research/se_pilot_handoff_v1/reports/worklist.json`

From repo root, using a NEW destination (existing output directories are refused):

```bash
.venv/bin/python research/se_pilot_handoff_v1/pilot.py --output-dir /tmp/bve-analyst-worklist-v1
```

Existing frozen development examples remain unchanged:
- `docs/demos/bd_opportunity_triage_v1/cd19_cell_therapy_bcl/brief.html` and `brief.md`
- `docs/demos/bd_opportunity_triage_v1/cd19_bcma_dual_autoimmune/brief.html` and `brief.md`

Their regeneration requires missing `~/se_runs/tac01_protoid_v1` and
`~/se_runs/mint5_protoid_v1` input directories. These are absent in the restored se_runs
and were not found among project run artifacts. Do not fabricate reconstruction from reports.
When those inputs are restored, use (one at a time, fresh output directories):

```bash
.venv/bin/python -m bve.cli.se_bd_brief --run-dir /home/djmann/se_runs/tac01_protoid_v1 --context examples/se_bd/cd19_cell_therapy_bcl.yaml --fda-labels research/se_bd_opportunity_triage_v1/fda_label_snapshot.json --output-dir /tmp/bve-bcl-restored-v1
.venv/bin/python -m bve.cli.se_bd_brief --run-dir /home/djmann/se_runs/mint5_protoid_v1 --context examples/se_bd/cd19_bcma_dual_autoimmune.yaml --fda-labels research/se_bd_opportunity_triage_v1/fda_label_snapshot.json --output-dir /tmp/bve-autoimmune-restored-v1
```

These commands document reproducibility prerequisites; the current worklist runs now without
those missing files. Its 19 reference IDs are unique; this is not drug-level alias resolution.

## Source inventory and priority

Inspected `src/bve/se/acquisition/connectors.py`, the source-coverage preregistration and
`acquire_report.json`, not just connector names. Frozen counts below describe acquisition,
not proof that the engine used or correctly attributed every document.

| Family | What exists / actual limitation | Frozen acquisition |
|---|---|---|
| CT.gov | Registry API; trial registration is not efficacy/ownership | 800 indexed |
| PubMed | ESearch/EFetch; title/abstract availability limits evidence | 573 indexed |
| FDA | openFDA labels; US scope and name matching, not global approval | 5 indexed |
| SEC | EDGAR full text/filings, bounded selection | 967 hits; 20 indexed; 5 parse failures |
| Press releases | SEC-filed releases only; misses private/non-SEC issuers | 452 hits; 4 indexed |
| ASH | Crossref Blood metadata/available abstracts, not exhaustive meeting search | 200 indexed |
| EHA | Crossref HemaSphere metadata/available abstracts | 176 indexed |
| ASCO | Crossref JCO metadata/available abstracts | 196 indexed |
| AACR | Crossref plus an existing optional bulk-proceedings PDF path | 198 indexed in acquisition |
| Company pipelines | Declared URL pages, optional bounded links; not open-ended discovery | 20 declared; 9 indexed; 11 failures |
| ACR | No built-in conference venue; generic declared-URL connector can fetch known pages | Not searched |

Old TAC01/MINT5 demonstrations queried CT.gov, PubMed and AACR. The frozen A_base live
run used native CT.gov/PubMed plus baseline AACR index. Its replay custody contains 8,553
source documents, so acquisition's initial API counts are NOT equivalent to replay totals.
The full source index adds SEC, SEC-filed releases, ASH/EHA/ASCO, FDA and declared pipelines.
The full-index effect is still unknown because the three arms are unfinished.

Priority: a separately preregistered small ACR/declared-company page acquisition using the
existing connector, not a new crawler. Frozen reference source links show why: KT501,
HXN-1031 and A-319 have ACR evidence; CDR111 has company-pipeline evidence; cizutamig has
company and registry evidence. Company manifests need topical relevance and redirect/failure
repair. Count new candidate recovery only in a new development evaluation, not by inserting
reference names into this frozen study. Reusing exposed reference URLs is targeted follow-up,
not independent recall evidence. Secondary publications/press syndication must remain visibly
weaker than direct product/registry documents for diligence.

## Scientific usefulness: evidence and limits

Historical A_base metrics (unchanged, `results/A_base_metrics.json`):
- 6,029 nominated candidates, 41,082 mentions, 8,553 documents.
- 2 of 8 fully quoted relevant reference assets recovered: CLN-978 and OM336.
- Four relevant reference names recovered counting incompletely supported entries:
  KT501, CLN-978, velinotamig and OM336.
- One eligible candidate: blinatumomab, an approved comparator. This is an unresolved failure.
- Fully quoted relevant assets missing: LBL-051, HXN-1031, CDR111, cizutamig, A-319,
  gamgertamig. These are investigational reference leads, not verified available assets.

Previous triage evaluation remains 36/40 category accuracy, 4 wrong named-product promotions
(three non-US approved products and one academic construct), and independent usefulness
PARTLY. Its reviewer relied largely on memory, so this is limited development evidence.
No new comparison with those results is valid: this worklist is curated from a reference,
not recovered by the engine, and the questions/as-of dates differ.

Final-output desk audit by the implementing agent (NOT independent):
- All 19 IDs/labels/A/B annotations match the frozen reference; controls remain visible.
- KT501 and velinotamig target fields remain UNVERIFIED. CND261 retains the frozen
  UNSUPPORTED_LABEL despite a different raw-reference label. GSK5926371 remains unresolved.
- Some reference phase descriptions are planned/preclinical; MATCH is explicitly not an
  eligibility pass. Quotations may be secondary sources and are not adjudicated clinical PoC.
- Rights are UNKNOWN for every entry, including those with company/partnership descriptions.
- No estimate of analyst time-to-candidate was measured. A ~5,300-word worklist still requires
  expert review; its table helps navigation but does not establish a five-minute success.
- No new independent reviewer evaluated the FINAL worklist. The independent reference is
  input evidence, not an independent evaluation of this output. That deliverable remains open.

## Cloud readiness and verification

See `CLOUD.md` for exact preparation, transfer, pinned setup, sequential execution, retrieval,
checksum verification and teardown. Local payload is `/tmp/bve-cloud-payload-final-v1` (~1.5 GB,
16,599 files). It contains no code working tree or credentials. Final code pin is recorded in
its manifest. Keep this ephemeral path out of Git.

Custody check: all 14,194 snapshots and four frozen input hashes pass. Local RAM is 11.5 GB;
no bypass or full-arm attempt. Before committing, preflight additionally reported the expected
dirty src tree. Original frozen files and old reports have no changes.

The tracked `data` symlink targets `/home/djmann/projects/biotech-asset-valuation-engine/data`;
the runbook creates that original target rather than replacing the symlink.

Exact installed Python is 3.11.17; Pydantic is 2.14.1. Environment versions are checked, not
silently inferred from old notes. The current venv has no pip; preparation uses importlib
metadata instead. Cloud install and full replay have NOT been executed. Python package pins
are version pins, not a tested wheelhouse or supply-chain hash lock. A_base's manifest records
code `905df447c1b9fd7b16a5bce1834c373e2624ce7b` and ontology/extractor versions but no complete
Python dependency lock. The recovered interpreter/Pydantic differ from the older execution
notes. Byte-equivalence tests cover the streaming writer change; they do not prove full
cross-environment replay equivalence. Record this provenance limitation when interpreting
the cloud comparisons, and review any unexpected differences before drawing conclusions.

Tests and lint results are recorded in `VALIDATION.md`. New workflow tests establish software
integrity, not scientific utility. Whole-repo Ruff has existing violations; no broad cleanup.

## Remaining blockers, in priority order

1. Discovery: private-company/ACR coverage, topical pipeline manifests, many failed pages.
2. Evidence: indication-specific stage/results, global approval, academic product identity,
   contradictory target/modality and dated rights evidence. Parked scientific experiments
   remain parked; this milestone does not alter their requirements.
3. Validation: independent expert assessment of final outputs and timed analyst task remain
   outstanding. Frozen old-run inputs also need restoration for reproducible updated demos.
4. Compute: paid 32 GB host authorization and supervised teardown. Budget estimate roughly
   EUR 4–11 compute, EUR 15 proposed all-in ceiling, subject to checkout and runtime uncertainty.

Smallest next milestone: preregister a bounded ACR/declared-company acquisition on an explicit
new development reference; demonstrate one previously missing, correctly identified named
investigational autoimmune engager with primary evidence and a clear unresolved-evidence
checklist. Have a separate BD reviewer evaluate that final lead brief. Do not launch another
large crawler or treat the current manual worklist as that discovery result.
