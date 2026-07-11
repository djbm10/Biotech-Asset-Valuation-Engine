# Private Holdout Evaluation — blocked before opening

Status: **NOT RUN**

The acquisition layer was frozen in commit `afe6bc5` (parent `26723aa`) after the visible
development gate reached 21/21. The private holdout was not opened or evaluated because no
externally managed holdout artifact, custodian path, or one-time evaluator was present in the
workspace or runtime environment. The repository contains only `holdout/.gitkeep`.

This is an execution blocker, not a holdout result. No holdout labels were read, copied, or
committed, and no tuning was performed against the holdout.

## Frozen inputs

| Input | SHA-256 |
|---|---|
| `src/bve/se/acquisition/runner.py` | `9b3cdded0a5c668233dd7f1d81dd2c0b44fa02cd13f806257c7b5468332ff455` |
| `src/bve/cli/se_acquire.py` | `2c101cd029c43b67e109c3dab32aff9492643e0aa13c9338e174d1ad96287bac` |
| `examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml` | `1def61b243d9592d931ee0d9be7c2fd7edec4fe632c75776ed4f6915f57d15e3` |
| `development/declared_sources.yaml` | `841ad31490e2c985214ca1dc0403397755f41b181ae180f835f7ce0a888434f3` |
| `development/reference_universe.csv` | `d2f105592508d5108e2cf17585dd73fdfb4eeaaf03b738f7d39f89253fff4e38` |
| `development/miss_matrix.csv` | `899cb8dc40c12495f1ad3b2b8dea7da50c85cddf9e05a5efe848824b9a5a761d` |
| `benchmark_manifest.yaml` | `27b106d1f5a47609dac12f62eba4b2bb755569f49a5918089e9c7de31a484bfe` |
| `development/corpus/manifest.jsonl` | `03aeee7b54674d42ec424852c53792e08eddd315331b0e2c411664aa7c559ec6` |
| `development/corpus/source_index.yaml` | `3e6b57298f92517b8fe622f0a12f9d23bf1771e69b910ebfe0db2848abd9a79c` |

The corpus manifest and source index are ignored runtime snapshots and remain outside Git.

## Development evidence carried into the freeze

- Recall: GOLD 5/5; SILVER 16/16; total 21/21.
- Identity/duplicate/false-exclusion/UNKNOWN metrics: as recorded by the development acquisition
  run; no holdout values are inferred from them.
- Source health: all generic connectors and declared URL connectors completed successfully;
  the five acquisition stages were recorded in the development run report.

## Holdout fields

Recall by GOLD/SILVER, identity-resolution rate, duplicate rate, false exclusions, UNKNOWN routing,
source-health stages, and every miss are **not available** because the one-time evaluation did not
execute. The existing milestone evaluator intentionally rejects sealed holdout inputs and cannot
serve as the private holdout runner.

Acquisition is frozen, but formal acceptance and ranking authorization remain pending delivery of
the externally managed holdout artifact and its authorized one-time evaluation procedure.
