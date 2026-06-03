# Data Source Policy

**Version:** 1.0 | **Enforced from:** 2026-05-15

Every field that enters any model must have a documented source with the following attributes.
No undocumented field may be used in Lane 1 or Lane 2 model computation.

---

## Required Field Attributes

| Attribute | Description |
|-----------|-------------|
| `source_name` | Name of the data source |
| `license_status` | `public`, `licensed`, `proprietary`, `scraped` |
| `allowed_use` | `commercial`, `research_only`, `internal_only` |
| `refresh_frequency` | How often data is updated |
| `fields_used` | List of fields consumed by models |
| `primary_key` | Unique identifier for records |
| `point_in_time_available` | `full`, `partial`, `none` |
| `survivorship_bias_risk` | `low`, `medium`, `high` |
| `restatement_policy` | How historical data is updated |
| `fallback_source` | What to use if primary source is unavailable |
| `confidence_weight` | 0.0–1.0 weight applied in evidence aggregation |

---

## Registered Sources

See `src/bve/data/source_contracts.yaml` for full specifications.

### Summary Table

| Source | License | PIT | Survivorship | Confidence |
|--------|---------|-----|-------------|-----------|
| ClinicalTrials.gov | public | partial | low | 0.80 |
| SEC EDGAR | public | full | low | 0.90 |
| yfinance / Yahoo Finance | scraped | none | medium | 0.60 |
| FDA drug database | public | partial | low | 0.85 |
| Biomedtracker base rates | licensed | none | medium | 0.75 |
| IQVIA analyst estimates | licensed | partial | high | 0.65 |

---

## Enforcement Rules

1. A field without a `source_contracts.yaml` entry cannot be used in Lane 1/2 models.
2. Fields with `point_in_time_available: none` must not be used in historical replay queries.
3. Fields from sources with `survivorship_bias_risk: high` require documented bias mitigation.
4. Fields with `license_status: scraped` or `license_status: licensed` require legal review before production use.
5. Every ingestion connector must call `DataQualityChecker.validate()` before writing to the store.
