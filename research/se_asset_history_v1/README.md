# Historical-code research follow-up

**UNVALIDATED-grade only. Do not use for trade sizing or acquisition probability.**
Start with [ADDENDUM.md](ADDENDUM.md), then [generated trial history](run_02/HISTORY.md).
The source/pointer/query audit is [run_02/history.json](run_02/history.json).
The prior packages and frozen studies have not been rewritten or rescored.

## Observed result

Starting with only `cizutamig`, the workflow derived CND106 from registry intervention metadata,
then EMB-06 from the already acquired primary company disclosure. Its three literal queries returned
9, 3 and 1 records respectively; deduplication by NCT identifier yields **10 distinct records**.
NCT04735575 is the one addition relative to the previous nine-record set. It is retained despite
being terminated, oncology-only, and under a historical name. No indication/status filter runs.
See [comparison.json](comparison.json). The expected miss was disclosed in AI feedback before
implementation; this is a contaminated development reference, not a blind recall experiment.

There is no new asset discovery, no proof of complete history, and no autonomous identity merge.
Manual inspection supports this specific naming chain. The generated result keeps every trial
attribution provisional; three query hits do not have an exact intervention-name match and remain
unattributed. This is intentionally a review queue, not an automatic addition to qualified assets.
The supplied company document is known, not autonomously found by this workflow.

## Architecture inventory and boundary

| Existing component | Actual behavior | Decision here |
|---|---|---|
| `ClinicalTrialsGovConnector` | Target + modality acquisition, one result page in its live search | Preserve; historical named searches must not filter away oncology/terminated studies |
| Discovery adapters / `AssetRegistry` | Carry related names as candidates and apply frozen identity/corroboration rules | Preserve; no automatic registry or company alias admission |
| `alias_admission` / `alias_probe` | Frozen target-alias retrieval study; different concern from drug-code history | Do not reopen |
| Acquisition HTTP boundary | Public-source safety, bounded responses, retry/pacing | Reuse directly for a bounded named-registry query adapter |
| Prior company corpus / evidence ledger | Already acquired visible text with source URL and hashes | Reuse and check hash before extraction; do not crawl anew |
| New `asset_history` utility | Explicit relationship proposals, bounded expansion, query and trial provenance | Opt-in only; no imports from resolver, registry, rankings or gates |

The separate-session AI review is retained in its original local location, not copied into Git.
Its hash is recorded for traceability. Its scores and timings are not entered as human observations.
The human-review status remains PENDING. The AI review's “acquired, not available” inference is not
adopted: availability is UNKNOWN. Geography does not establish rights.

## Reproduce

From the repository root with the existing environment (each output directory must be new):

```bash
# No network: uses the captured query pages and asserts identical core result.
.venv/bin/python research/se_asset_history_v1/run.py --output /tmp/bve-history-replay-01 --offline-from research/se_asset_history_v1/run_02

# Live named follow-up; public, unpaid API. Does not run the frozen discovery experiment.
.venv/bin/python research/se_asset_history_v1/run.py --output /tmp/bve-history-live-01

.venv/bin/python -m pytest tests/se/test_asset_history.py tests/se/test_acquisition.py tests/se/test_acquisition_http.py tests/se/test_identity_evidence_model.py tests/se/test_registry_alias_index.py -q
.venv/bin/python -m pytest tests/se -q
.venv/bin/ruff check src/bve/se/acquisition/asset_history.py tests/se/test_asset_history.py research/se_asset_history_v1/run.py
```

Raw captures are retained locally and ignored by Git, consistent with the earlier verification
milestone. Offline replay requires `run_02/raw/full_result.json` plus the previous archived company
text. A clean clone has the public report, hashes and links but **not** those raw captures; do not
claim it can replay offline. The live command also requires that company archive; it fails if it
is absent or changed. No implicit refresh or history overwrite occurs. Document retrieval and the
archived text's normalization were completed by the previous acquisition workflow.

Fixed bounds: 10 supplied company documents (2 MiB each), 6 query terms, 3 rounds, at most 2 pages
per term, pageSize 100 and 2 MiB per response. Existing HTTP retries remain bounded independently
of this logical-page limit. Requests are sequential; no ontology loads, large crawls or paid calls.
The measured offline replay consumed 46,204 KiB peak RSS (0.25 s); this is not a full-scale capacity
result or a live latency measurement. Core replay is deterministic; run timestamps intentionally differ.

`run_01/` records the failed network-sandbox attempt (AcquisitionHttpError, unknown count, no trials),
not a scientific zero. `run_02/` records the successful authorized public request. Local replay
folders are retained but ignored. `PLAN.md` was hashed before implementation; it fixes scope and
known-development success criteria, not a new scientific validation threshold.

## Safeguards and remaining limitations

- Explicit code pairs and narrow former-name phrases only; nearby names alone do not create edges.
  Negated/combination contexts require review. Arbitrary prose, punctuation and code variants may be missed.
- Only one related code on one registry intervention can drive expansion. Multiple otherNames are
  quarantined; co-interventions never become aliases. Naming metadata is not identity proof.
- Optional externally supplied competing-root claims block expansion. Without that input, global
  collision detection is unavailable. Even a single explicit pair can be misleading; review is mandatory.
- No fuzzy matching, hyphen normalization, cizutamig name-shape exception or global alias table.
  There is no automatic production integration. Operators still supply the root and primary documents.
- Failed/malformed/count-mismatched/truncated requests remain distinct from complete zero-result queries.
  Conflicting duplicate trials are flagged; original query snapshots remain available for adjudication.
- All supplied source naming leads are preserved, including unrelated/unfollowed ones. Use the issued
  query list and source chain to distinguish terms actually followed from other page mentions.
- Completeness remains UNKNOWN even when every requested page returned. Other registries, exhaustive
  alias coverage, full patent/formulation histories, and an independent human benchmark remain absent.

The next small milestone is human adjudication of these naming links and provisional trial matches,
then a bounded additional-registry lookup under reviewed terms. A human-prepared blind reference
set is still needed before claiming discovery recall or operational BD usefulness. Do not build a
large competitor/commercial layer merely to make this known-case report appear more complete.
