# S&E Live Public-Data Pipeline Runbook

## Purpose and production boundary

`bve-se-run` is the fail-closed operational entry point for the public-data S&E
acquisition-to-asset path. In one live invocation it validates the buyer problem and
live-enabled source policy, verifies release custody and the complete connector plan before
network access, acquires public records, seals the content-addressed corpus, performs
discovery and identity resolution, extracts claims and facts, applies evidence gates,
produces monitoring and audit records, seals the immutable run, and atomically promotes it
through an external `CURRENT.json` record.

The production output is explicitly:

> Production-validated public-data S&E screen; pre-diligence—not verified truth.

It is a screening and research-prioritization product. It is not diligence-confirmed
truth, a valuation, an investment recommendation, or evidence of transaction willingness,
rights availability, legal freedom to operate, or an undisclosed counterparty position.
Silence in public sources must not be interpreted as a negative fact.

The checked-in production policy currently limits live use to its declared targets and
modalities (CD19 and BCMA T-cell engagers in
`examples/configs/se/live_cd19_bcma_tce_policy.yaml`). A problem outside that scope is a
configuration failure; operators must not generalize the current validation claim to a new
target, modality, source family, or rubric.

## Modes

The three modes are mutually exclusive.

| Mode | Network | Release manifest | Corpus | Promotion |
|---|---:|---|---|---|
| `--live` | Yes | Required and verified before network access | Acquired and portably sealed in the run directory | Seals the receipt, then writes `CURRENT.json` only after all checks pass |
| `--replay CORPUS_DIR` | No | Forbidden | Requires the supplied portable corpus manifest, source-health record, and seal | Produces `VERIFIED_REPLAY`; never writes `CURRENT.json` |
| `--dry-run` | No | Required | None | Verifies release, policy, operator identity, and full connector plan; writes no run artifacts |

A dry run validates the problem, live-enabled policy, supported scope, release manifest and
file hashes, configured public-source operator identity, and a complete connector plan for
the production policy, including a planned connector for every required source family. It
does not test source availability, parsing, discovery, gates, or artifact promotion. Supply
the same UTC `--as-of` date that live mode will use; the live step repeats the same-date
release and preflight verification before network access.

Replay is deterministic with respect to the supplied corpus, current code, problem, and
policy. It rejects release metadata and `--as-of`, reads the effective logical date from
`corpus/seal.json`, and applies that sealed date to the replay problem automatically. The
BuyerProblem's checked-in date therefore does not need to equal the original live acquisition
date. Replay requires the current policy hash to match the portable seal and verifies the
corpus manifest, sealed source-health hash and verdicts, source counts, validation report,
and every stored snapshot before discovery. It does not claim that the corpus is current and
does not copy the replay corpus into the new run directory. Preserve the complete source
corpus—including `manifest.jsonl`, `source_health.json`, `seal.json`, and snapshots—alongside
a replay record.

## Exact commands

Run from the repository root after installing the package. Before dry-run or live mode, set
a single-line HTTP identity that names the operator and provides a monitored contact address:

```bash
export BVE_SE_USER_AGENT="BVE S&E public pipeline (contact: se-ops@your-company.example)"
```

Replace the example address with the real operations contact. Do not print this variable in
workflow logs. Replay performs no HTTP requests and does not require it.

Production configuration and release verification only:

```bash
bve-se-run \
  --dry-run \
  --as-of "$(date -u +%F)" \
  --problem examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml \
  --source-policy examples/configs/se/live_cd19_bcma_tce_policy.yaml \
  --release-manifest research/se_benchmarks/live_pipeline/live_release_manifest.yaml \
  --output-root outputs/se/production
```

Live acquisition using the current UTC date as its logical date:

```bash
bve-se-run \
  --live \
  --as-of "$(date -u +%F)" \
  --problem examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml \
  --source-policy examples/configs/se/live_cd19_bcma_tce_policy.yaml \
  --release-manifest research/se_benchmarks/live_pipeline/live_release_manifest.yaml \
  --output-root outputs/se/production
```

Verified offline replay of a previously promoted live corpus:

```bash
bve-se-run \
  --replay outputs/se/production/runs/RUN_ID/corpus \
  --problem examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml \
  --source-policy examples/configs/se/live_cd19_bcma_tce_policy.yaml \
  --output-root outputs/se/replay \
  --run-id replay-RUN_ID
```

Replace `RUN_ID` with the source run identifier. The corpus must be a portable live seal, not
only a snapshots directory. Do not pass `--as-of` or `--release-manifest` to replay; replay
derives its date from `corpus/seal.json`, and rejects release metadata. Dry-run and live must
receive the same UTC `--as-of` so they verify the release for the same logical date.
`--run-id` is optional, but a supplied ID must be new under that output root. Existing run
directories are never overwritten.

On success the CLI prints JSON containing `run_id`, `status`, `run_dir`, `reused`, and
`execution_key`. Live CLI output reports `PROMOTED`, while the immutable live
`run_receipt.json` deliberately reports only `SEALED`; the external `CURRENT.json` is the sole
promotion record. A repeated live invocation with the same effective problem, date, policy,
release, code version, and fully verified `CURRENT` run returns that run with `reused: true`
and makes no network request. This same-day idempotency is intentional; do not delete
`CURRENT.json` merely to force another acquisition.

## Exit codes and promotion contract

| Code | Classification | Operator meaning |
|---:|---|---|
| `0` | Success | Live CLI `PROMOTED` backed by a `SEALED` receipt and `CURRENT`, `VERIFIED_REPLAY`, `DRY_RUN`, or a verified idempotent reuse |
| `2` | Usage/configuration/preflight | Invalid CLI arguments or schema, unsupported problem scope, replay-only policy, incompatible mode flags, missing dry/live release, release supplied to replay, missing operator identity/contact, incomplete connector plan, policy mismatch, expired/future release, or changed/missing released file |
| `3` | Required-source health | A required source is missing, `DEGRADED`, or `FAILED`, or reported source health does not reconcile to the written corpus |
| `4` | Discovery/semantic safety | Discovery did not converge, no canonical asset or gate evaluation was produced, routes leaked/overlapped, evidence processing failed, or another semantic stop reason was recorded |
| `5` | Integrity boundary | Invalid portable corpus seal, missing/unlisted/tampered artifact, forbidden symlink, invalid reusable `CURRENT` run, immutable run-ID collision, filesystem failure, or an unexpected exception at an integrity boundary |

Errors are written to stderr with an `ERROR:` prefix. A nonzero run must never be treated
as a partial success. Before sealing, codes 3–5 may leave a quarantined run directory with
the evidence available at the failure point, `audit.jsonl`, and `failure.json`; these are
diagnostics, not promoted output. If sealing completed but external `CURRENT` promotion
failed, the sealed bundle remains immutable and diagnostics are written outside it under
`failures/<run_id>.json`. Failures that occur before run creation, including release or
connector-plan preflight, may have no run directory. `CURRENT.json` is unchanged on every
failure.

## Immutable run layout and `CURRENT` promotion

The normal live layout is:

```text
outputs/se/production/
├── .run.lock
├── CURRENT.json
├── failures/<run_id>.json              # only if post-seal promotion fails
└── runs/
    └── <run_id>/
        ├── audit.jsonl
        ├── source_health.json
        ├── corpus/
        │   ├── manifest.jsonl
        │   ├── source_health.json
        │   ├── seal.json
        │   └── snapshots/<source_family>/<content_sha256>.json
        ├── corpus_seal.json
        ├── monitoring.json
        ├── result.json
        ├── memo.md
        ├── run_receipt.json
        └── artifact_manifest.json
```

The output-root lock serializes writers. Corpus snapshots are content-addressed, manifest
appends are locked and synced, and writes of control JSON use a temporary file, `fsync`, and
atomic replacement. A successful all-`NO_DATA` acquisition still receives a canonical empty
`manifest.jsonl`. The runner validates run IDs as safe single path components and creates each
run directory with overwrite disabled. Treat every directory under `runs/` as immutable
after sealing; correction means a new run, never an in-place edit.

`corpus/source_health.json` preserves the acquisition verdicts needed for portable replay.
`corpus/seal.json` binds their hash to the manifest hash, policy hash, logical date, per-family
counts, and a location-independent corpus-validation report. The top-level `corpus_seal.json`
is the run-level copy of that custody record.

`artifact_manifest.json` records the canonical relative path, byte size, and SHA-256 of every
other file in the completed run. Verification requires an exact set match: an extra unlisted
file fails just like a missing, resized, or rehashed listed file. Symbolic links anywhere in
the immutable run are forbidden, as are path escapes, duplicate paths, and a manifest run ID
that differs from the directory. `run_receipt.json` binds the `SEALED` live run to the
effective BuyerProblem, logical date, code version, source-policy version and hash, release
identity and hash, and corpus-manifest hash.

Only live mode writes `CURRENT.json`, and only after the `SEALED` receipt and artifact
manifest have been written and the exact immutable artifact set has verified. `CURRENT.json`
is a strict, externally anchored promotion record containing its schema version, promoted
`run_id`, execution key, receipt hash, artifact-manifest hash, and promotion time. Reuse and
recovery additionally verify that `CURRENT` is a regular non-symlink, both anchor hashes
match, the receipt/result/manifest run IDs and execution keys agree, the receipt is a live
`SEALED` receipt with the expected result paths, and the full artifact set verifies.
Promotion is an atomic pointer update; it does not mutate the sealed run. Neither a sealed
receipt nor a `run_sealed` audit event alone means promoted. Replay and dry-run never promote.

## Release and source-policy custody

The source policy is a strict, versioned allowlist and scope contract. It controls:

- supported canonical targets and modalities;
- whether the policy is explicitly enabled for live use;
- required and optional source families;
- declared generic public publisher index URLs for non-built-in connectors; and
- a deterministic order-independent configuration SHA-256.

Declared URLs must be public HTTPS locations. Credentials, localhost, private/non-public IP
literals, unsafe paths, and source families outside the policy are rejected. Production
review must allow only generic publisher indexes or listing roots, such as a company news
index or public drug-dictionary index. Direct pages for a named reference asset, trial,
transaction, or presentation are not valid declared acquisition configuration. Acquisition
queries are derived from the problem's target and modality vocabulary; neither the connector
plan nor declared indexes may seed discovery with benchmark or holdout asset identities.

The full production connector plan consists of the built-in ClinicalTrials.gov, FDA label,
PubMed, and SEC EDGAR connectors plus the policy-declared company press-release and company
pipeline/presentation index connectors. Dry-run and live construct the requested plan before
acquisition and fail if any required family lacks a connector. Both also require a nonempty,
single-line `BVE_SE_USER_AGENT` containing an operator contact email. This identity is sent as
the HTTP `User-Agent` to public providers and must be monitored and kept out of diagnostic
echo output.

The v2 live release manifest is the custody envelope for the validated production behavior. It
binds the release ID, validation date and interval, exact source-policy hash, specification path
and hash, evaluator version, and SHA-256 of every validated repository file. Construction and
verification independently require the complete internal Python/runtime closure, controlled
problem and policy, production specification, workflow, package metadata, and dependency lock;
the specification hash must equal the validated hash at `specification_path`. Before any network
access, live mode verifies:

1. the current source-policy hash exactly matches the released hash;
2. the logical as-of date is on or after `validated_on` and before the expiry boundary; and
3. every released file still exists inside the repository and has the recorded hash.

Do not hand-edit a release manifest to accommodate drift. Any custody failure requires a
reviewed revalidation, updated hashes, and a new immutable release identity. Keep the source
policy, specification/rubric, evaluated code set, evaluation evidence, and resulting release
manifest together as one controlled release record.

## Source-health semantics

Health is reported independently for connector execution, query results, raw-record count,
parsing, and indexing. Corpus-level required-evidence coverage is intentionally separate and
is not inferred merely because a connector worked.

| Verdict | Meaning | Required-source behavior |
|---|---|---|
| `OK` | Connector succeeded and returned records that parsed and indexed without loss | Continue |
| `NO_DATA` | Connector succeeded and its generic target/modality query truthfully returned zero records | Continue |
| `DEGRADED` | Some records failed parsing or parsed/indexed counts disagree | Stop with code 3 |
| `FAILED` | Connector failed, produced no indexed documents after returning records, or all records failed parsing | Stop with code 3 |

A required family absent from the health report also stops with code 3. Optional-source
degradation is retained in health output but is not, by itself, a required-source production
failure.

`NO_DATA` is not an outage and must not be rewritten as `OK`, `FAILED`, or evidence that no
asset exists. It says only that this source's generic query returned nothing at that time.
The runner persists this verdict into the portable corpus seal. A required source proven
`NO_DATA` receives an explicit empty mandatory discovery adapter, which records
`NO_EVIDENCE_FOUND` without pretending the source was absent or weakening mandatory-source
coverage. A required family that is merely missing from the corpus and lacks sealed
`NO_DATA` proof still fails closed. Corpus-integrity and downstream semantic checks also
remain active: once a valid corpus is sealed, a run with no canonical assets or no
evidence-backed gate evaluation stops with code 4 even though its connectors may have
truthfully reported `NO_DATA` or `OK`.

Before discovery, the health report is reconciled against the actual corpus. The runner
rejects unreported corpus families, documents written by a source claiming `NO_DATA`, a
positive raw-record report with no documents, impossible parsed/indexed/failure counts, and
a claim of indexed output when the corpus has none. The portable replay path recomputes the
same source-health models and verdicts and verifies their sealed hash; replay cannot
reconstruct or improve health from document presence alone.

Review `source_health.json` by family, not only its stage totals. In particular,
`required_evidence_present` is a later corpus-coverage attribution and can remain unset in an
acquisition report; it is not equivalent to connector, parse, or index health.

## Interpreting `UNKNOWN` and empty rankings

Gate uncertainty is a valid safety outcome. An asset with missing, stale, ambiguous, or
conflicting material evidence is routed to `unresolved_asset_ids` and the analyst review
queue; it must not enter ranking. If every discovered asset is unresolved, the run can still
be a converged, internally valid public pre-diligence screen. In that case:

- `monitoring.json` reports `unknown_rate: 1.0` and the alert
  `all discovered assets require diligence; ranking abstained`;
- `ranking.ranked` is empty;
- `memo.md` lists the unresolved assets and prioritized research questions; and
- promotion means the pipeline faithfully abstained, not that it found no opportunities or
  cleared the assets.

Do not turn `UNKNOWN` into an exclusion, eligibility decision, or neutral score. Resolve it
only through cited evidence and the controlled analyst-review/override process. Likewise, an
empty ranking is not a negative investment conclusion.

## Scheduled GitHub operation

`.github/workflows/se_public_pipeline.yml` runs at `07:15 UTC` every Sunday and supports
manual dispatch. It uses concurrency group `bve-se-public-pipeline` with cancellation disabled,
so two public-pipeline jobs do not write the same output concurrently.

Configure the repository variable `BVE_SE_USER_AGENT` before enabling the job. It must be a
single-line operator identity containing a monitored contact email. Workflow preflight fails
with code 2 if it is blank, multiline, or lacks the email, and it never echoes the value.

The workflow uses least-privilege `contents: read` and `actions: read`. All third-party
Actions are pinned to full commit SHAs. Python 3.12 runtime dependencies and their wheel SHA-256s
are locked in `requirements/se-public-pipeline.txt` and installed with `--require-hashes`,
`--no-deps`, and binary-only mode; the job does not upgrade pip or install the editable
development package.

Before the new run, the workflow locates the most recent earlier successful run of this same
workflow and downloads its `se-public-production-*` artifact. It verifies the prior
`CURRENT`, anchors, sealed receipt, exact artifact set, and result before restore; copies only
the promoted run through a staging directory; refuses overwrite; atomically restores
`CURRENT`; and verifies both staged and destination state. If there is no prior successful
artifact, the run starts from an empty output root. A restore failure stops the job rather
than silently bootstrapping over lost custody.

After restore, the workflow resolves one UTC logical date and passes it to both the dry-run
and live commands. Dry-run verifies the release, policy, contact identity, and complete
connector plan; live repeats preflight and performs acquisition. The live step uses the same
problem, policy, release, and output-root paths shown above. Its job summary reports
`CURRENT`, result convergence/candidate count, and monitoring stops and unknown rate when
those artifacts exist.

The workflow performs no Git commit or push. A successful, restorable output root is uploaded
for 90 days. A diagnostics upload runs even on failure and is retained for 14 days; on a
successful job this shorter-lived diagnostic may duplicate the production artifact.
GitHub-hosted runners remain ephemeral, so continuity depends on successful artifact lookup,
verification, and restore. Copy verified artifacts into approved durable storage if retention
beyond 90 days or recovery independent of GitHub Actions is required.

## Routine verification

For every scheduled or manual live run:

1. Confirm the dry run and live step both returned zero.
2. Confirm the CLI status is `PROMOTED` or an expected verified reuse, the receipt is
   `SEALED`, and `CURRENT.json` names that same run.
3. Read `source_health.json`; investigate every non-`OK` verdict, while preserving the
   truthful `NO_DATA` interpretation above.
4. Read `monitoring.json`; `stop_reasons` must be empty. Alerts require interpretation even
   when they are valid abstentions.
5. Confirm `result.json` is `CONVERGED`, every candidate is in exactly one of eligible,
   excluded, or unresolved, and ranking contains eligible assets only.
6. Read `memo.md` and the unresolved research queue before using any output.
7. Verify `CURRENT`, the receipt, and every artifact digest before recovery or downstream
   transfer.

Use the supported verifier for routine checks and recovery. It validates the strict current
pointer, both anchor hashes, live sealed receipt, result identity, forbidden-symlink rules,
and the exact artifact set:

```bash
SE_OUTPUT_ROOT=outputs/se/production python - <<'PY'
import os
from pathlib import Path

from bve.se.live_run import verify_current_run

outcome = verify_current_run(Path(os.environ["SE_OUTPUT_ROOT"]))
print(f"verified {outcome.status} run {outcome.receipt.run_id}")
PY
```

Do not consume an artifact if this check fails. Unlisted files and any symlink inside the run
are integrity failures, not harmless additions.

## Incident response

### Exit 2: configuration or release custody

Stop before acquisition. Check the exact validation error, the logical as-of date, policy
scope and `live_enabled` flag, full connector plan, `BVE_SE_USER_AGENT` contact, policy hash,
release interval, repository root, and every validated file. Confirm replay was not given a
release or date override. Do not bypass preflight, release verification, or extend
`interval_days` in place. Complete revalidation and issue a new release when drift is real.

### Exit 3: required source is unhealthy

Keep the failed run quarantined and inspect `source_health.json` plus request logs. Determine
whether the cause is upstream availability, rate limiting, a changed response schema,
retrieval failure, parse loss, index loss, or a mismatch between reported counts and persisted
documents. For `NO_DATA`, confirm the sealed health record reports zero data and the corpus
contains no documents for that family. Do not remove a required source, relabel `DEGRADED`
as `NO_DATA`, or promote the partial corpus. Re-run after recovery with a new run ID; omitting
`--run-id` is safest.

### Exit 4: convergence or semantic stop

Inspect `result.json`, `monitoring.json`, `memo.md`, `run_manifest.incomplete_reasons`,
`processing_errors`, gate evaluations, route sets, and the audit/failure records. Preserve the
corpus as diagnostic evidence. Fix the acquisition, extraction, identity, gate, or routing
cause and create a new run. Never edit the result or monitoring file to clear a stop reason.

### Exit 5: corpus, artifact, or filesystem integrity

Stop all consumers of the affected output root. Preserve the directory and logs without
modification. Verify filesystem capacity and permissions, then use the verification procedure
above to identify the first missing, extra, resized, rehashed, or symlinked artifact. For
portable-corpus failures, keep `manifest.jsonl`, `source_health.json`, `seal.json`, and
referenced content-addressed snapshots as one unit and verify the seal's policy/date/count and
hash bindings. Do not regenerate a hash to legitimize changed bytes.

If `CURRENT.json` is corrupt or points to a corrupt run, recover the complete output root or
the complete run plus its matching `CURRENT.json` from a known-good uploaded artifact, verify
it offline, and only then place it back into service. Never repoint `CURRENT` to a failed or
partially written run. Keep the corrupt copy and recovery evidence with the incident record.

### Workflow or artifact-upload failure

The job may have completed computation without durable artifact retention. Check the job log
and step summary; do not infer success from an earlier step. Re-run by manual dispatch after
the fault is resolved. Because the workflow does not push Git state, there is no data branch
to repair and no force-push recovery path.

## Recovery principles

- Preserve failed and superseded run directories; never repair or reuse their IDs.
- Restore `CURRENT.json`, `run_receipt.json`, `artifact_manifest.json`, corpus, results, and
  audit records from the same known-good artifact. Do not mix runs.
- Run `verify_current_run` before making a restored run available to downstream users; stage
  and verify before atomically replacing production `CURRENT`.
- Record the workflow URL, run ID, execution key, UTC logical date, failure classification,
  root cause, recovery source, and verification result in the incident record.
- A replay can confirm deterministic processing of a complete portable corpus seal, but it
  does not restore source currency or convert a failed or merely `SEALED` live acquisition
  into a promoted live run.
- A successful rerun creates or promotes a new immutable run. Retain the failed run for the
  14-day diagnostics window or longer if incident policy requires.

## Revalidation cadence and material change

Production validation expires at the manifest boundary:
`validated_on + interval_days`. The current operational cadence is at most 180 days. The
expiry date itself is invalid; revalidation must be completed before that date.

Revalidate earlier whenever a material input changes, including:

- acquisition, parsing, identity resolution, evidence extraction, gate, routing, ranking,
  or monitoring behavior;
- the BuyerProblem/specification or eligibility and ranking rubric;
- required/optional source families, declared generic index URLs, target/modality scope, or
  other source configuration;
- a validated file, evaluator version, specification hash, or source-policy hash; or
- an upstream schema/behavior change that materially alters pipeline performance.

The release verifier automatically enforces interval, policy-hash, and validated-file
custody. Operational review must also detect material code, rubric/specification, and public
source-configuration changes; unchanged hashes are not a substitute for performance review.
Revalidation must exercise live acquisition, sealed-corpus replay, source-health failure
modes, identity and route partitioning, citation entailment, gate `UNKNOWN` behavior, ranking
eligibility, artifact recovery, and the public benchmark/holdout protocol without exposing
holdout identities to acquisition.

## Privacy and publication controls

Only public-source artifacts belong in this pipeline, its workflow artifacts, or any durable
recovery copy. Before a run or upload, confirm that inputs and outputs contain none of the
following:

- person-specific advice, named-person guidance, meeting preparation, handoff notes, or
  analyst-private annotations;
- benchmark holdout identities, labels, expected rankings, hidden reference universes, or
  evaluation answer keys;
- private diligence, confidential company information, credentials, tokens, email content,
  or non-public transaction assumptions; or
- unrelated KnowledgeStore, portfolio, position, or analyst-execution state.

The checked-in public BuyerProblem may define the target/modality screen, but holdout and
benchmark answer data must remain outside acquisition queries and production artifacts.
Never add advice or meeting-prep files to a workflow artifact, commit, or publication bundle.
The production workflow uploads only `outputs/se/production` and has no write permission to
the repository; maintain that narrow boundary.
