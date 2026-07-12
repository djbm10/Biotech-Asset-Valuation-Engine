# Point-in-Time Valuation Date Contract v1

This document is the single authoritative definition of the five date/timestamp
fields used across historical PIT valuation work. It resolves the
`historical_snapshot_date` (coverage-audit CSV) vs. priced-entry-date
(price-sourcing CSV) conflict flagged but not fixed in
`docs/historical_valuation_config_schema_v1.md` and the three-pilot report.

## The five fields

| Field | Definition | Granularity | Authoritative source |
|---|---|---|---|
| `signal_as_of_date` | The single calendar date the whole exercise treats as "today" — the date the market price is drawn from and the date every assumption must be knowable by. **This is the one date solvers and configs key off.** | date | Always equals `price_trading_date` (see below) — there is only one signal date per config, not two. |
| `price_trading_date` | The actual trading day whose closing price is used as the entry price. May differ from a nominal roster/eligibility label date (e.g. a target date that fell on a weekend or holiday resolves to the prior trading day). | date | `adverse_cohort_price_sourcing.csv:coverage_start` (or `coverage_end` for an exit price) |
| `information_cutoff_timestamp` | The precise point in time beyond which no fact may be used. Defaults to US market close (16:00 ET) on `price_trading_date`, since that is the moment the entry price was actually set. | date + time (ET) | Derived: `price_trading_date` + `16:00:00 ET`, unless a config explicitly documents a tighter cutoff (e.g. a pre-halt intraday cutoff) |
| `balance_sheet_as_of_date` | The fiscal period-end date of the filing supplying company financials (cash, debt, shares, burn). | date | The filing itself (10-Q/10-K cover page / balance sheet date) |
| `balance_sheet_publication_date` | The date the filing was actually made public (SEC EDGAR filing date). **Must be ≤ the date component of `information_cutoff_timestamp`.** This is the field that actually gates no-lookahead compliance for company financials — `balance_sheet_as_of_date` alone is not sufficient, since a filing can cover a pre-cutoff period but be published post-cutoff (this is exactly the BIND Q3-2015-10-Q near-miss documented in the pilot report). | date | SEC EDGAR filing-date atom feed / accession metadata |

## Reconciliation rule

`signal_as_of_date` is always `price_trading_date`. It is **never** the
`historical_snapshot_date` value found in
`research/mna/pit/representative_cohort_coverage_audit.csv`. That column is
hereby redefined, not deleted: it is a **roster/eligibility reference date**
(roughly when the name entered the tracked bankruptcy/delisted/acquired
cohort), not a pricing cutoff. It was never fit for that second purpose and
should not be read as one. Any future column in that CSV that requires a true
pricing cutoff should read `adverse_cohort_price_sourcing.csv:coverage_start`
instead of `historical_snapshot_date`.

This resolves — rather than merely re-flags — the discrepancy noted in the
three-pilot report's section 2: there was never a genuine conflict between
two candidate cutoff dates, only a mislabeled column being read for a purpose
it doesn't serve. The six PIT configs in this repo (BIND, GNCA, CEMP, and the
three diagnostic controls) all key `signal_as_of_date` off
`adverse_cohort_price_sourcing.csv:coverage_start`, which is what they did
correctly already; this document just makes that rule explicit and non-local
so it isn't rediscovered/re-litigated per name.

## Applying `information_cutoff_timestamp` at intraday resolution

For most names, date-level resolution is sufficient — no genuinely disputed
fact sits within the same trading day as the cutoff. CEMP is the one pilot
where this matters: its entry price (2016-11-03) sits one day before a
binary FDA AdCom vote, and one candidate input (an FDA briefing-document
safety disclosure) was reported as becoming public "~Nov 2, 2016" without a
verified timestamp relative to the 2016-11-03 16:00 ET cutoff. Per the
governing instruction, this must be verified at timestamp granularity or the
signal date must move backward / the disputed fact must be excluded — see the
CEMP-specific resolution in `docs/historical_valuation_configs/cemp_assumption_ledger.yaml`
and the diagnostic report for the outcome of that check.

## What this document does not do

It does not retroactively rewrite all 66 rows of
`representative_cohort_coverage_audit.csv` — only the rows actually used to
build valuation configs (BIND, GNCA, CEMP, and the three diagnostic controls
added in this phase) have their `signal_as_of_date` explicitly cross-checked
against `adverse_cohort_price_sourcing.csv` below. Rewriting the full roster
is a separate, larger data-hygiene task, not required to unblock the
six-name diagnostic.

| security_id | `historical_snapshot_date` (roster label, NOT a cutoff) | `signal_as_of_date` (authoritative) |
|---|---|---|
| SEC-BIND | 2015-05-02 | 2015-10-09 |
| SEC-GNCA | 2021-07-05 | 2021-07-02 |
| SEC-CEMP | 2016-08-01 | 2016-11-03 |
| (3 diagnostic controls) | see diagnostic-control section of the six-name report | see same |
