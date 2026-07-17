# Ingestion Health Incident — 2026-07-16

## Final CI evidence

- Final commit: `b25b46667438b70d4433af3572569ab2bc81e921`
- Branch: `fix-se-ci-failures`
- Workflow: `Ingestion Source Health Check`
- Workflow run ID: `29546465885`
- Run URL: https://github.com/djbm10/Biotech-Asset-Valuation-Engine/actions/runs/29546465885
- Configuration: as-of `2026-07-16`, lookback `3` days, 125 targets, 33 acquirers
- Run conclusion: `success`
- Health-probe step conclusion: `success` (workflow exit code 0)
- Health artifact ID: `8394196862`
- Artifact URL: https://github.com/djbm10/Biotech-Asset-Valuation-Engine/actions/runs/29546465885/artifacts/8394196862

## Source counts and verdicts

| Source | Attempted | Fetched | Classified | Expected non-event | Rejected | Failures | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| clinicaltrials_gov | 158 | 1,968 | 203 | 0 | 1,765 | 0 | OK |
| fda_website | 158 | 0 | 0 | 0 | 0 | 0 | NO_DATA |
| sec_filing | 158 | 19 | 3 | 1 | 15 | 0 | OK |

SEC reconciliation: `19 fetched = 3 classified + 1 expected non-event + 15 rejected`.
Expected SEC non-events require parsed items exclusively `2.02`/`9.01` and no
explicit acquisition/BD signal in parsed content. The 15 rejected records remain
visible with item-specific rejection reasons; they are not hidden as expected
non-events.

FDA evidence: all requests used `https://api.fda.gov/drug/drugsfda.json`.
There were 125 HTTP 404 `no_match` responses and 33 HTTP 200 responses whose 50
returned/parsed records were all `outside_date_window`; 0 records were selected
for the three-day window. This is legitimate `NO_DATA` and did not fail CI.

Run totals: 1,987 items seen, 206 classified, 206 appended, 1,781 unclassified.

## Durable artifact copy

The downloaded bundle and extracted files are preserved in the repository at:

`outputs/probe/health/2026-07-16/ci-run-29546465885/`

Files:

- `ingestion-health-2026-07-16.zip` — SHA-256 `00d722e45f13d6ff07c10306d309ee55ccc6e55ac9bd94c0e6c11ddc1ed2bd94`
- `ingestion_health.md` — SHA-256 `ce65c11f93e318b36b2a908222d1fe74844ddd2be0274f3d8987f04fcd18664e`
- `ingestion_health.json` — SHA-256 `8fb8a90282dfb6a1a0ea9106f9fd210f37dd84b57379c42f6bc2f71318b0f9b8`
- `new_events.csv` — SHA-256 `c9451a54889be132e6e5dc24b163d89b46644dc7da2967c5ea87a10cd169b4ea`
- `health-check.log` — SHA-256 `6334f0df4e756bed68ec4aee6fa73023a43e1aaf90506e325c592958054016fb`

No failure-diagnostics artifact was generated: its workflow step is conditional on
job failure, and the final job succeeded.
