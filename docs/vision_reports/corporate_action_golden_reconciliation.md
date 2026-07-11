# Corporate-Action Ledger — Golden Reconciliation Report

**Scope:** the original 6-name pilot (AKAO, GNCA, CNAT, CEMP, ARRY, TBRA) that
exposed the inadequacy of a single scalar `share_conversion_ratio` column and
motivated the `CorporateActionLedger` / `ReconciliationResult` rewrite, plus
Batch 2 — the remaining 9 bankruptcy-wipeout names (MLNT, AKRX, ACET, NOVN,
BIND, ARLZ, OREX, SRNE, PZRX) — extended per the approved outcome-based-batch
sequence (wipeouts first). MLNT is already covered inside the CEMP chain
above and is also independently resolvable as its own entry. **15 of 30**
pilot names now resolve through the ledger; 15 remain (the `acquired` cash-
merger batch and the remaining `delisted_failed` reverse-merger batch).

**Source code:** `src/bve/analysis/corporate_action_ledger.py`, `src/bve/models/corporate_action.py`
**Source data:** `research/universe/corporate_action_ledger.csv`
**Tests:** `tests/test_corporate_action_ledger.py` (18/18 passing; full suite green; `ruff check src/` clean)

**Numbers below are the live `resolve()` output** (regenerated against current
code/CSV at report time), not hand-transcribed. AKAO/GNCA entry prices are
synthetic (a bankruptcy wipeout is -100% at any entry price — these two exist
to prove the wipeout mechanism). ARRY/TBRA entry prices are the pilot's
back-calculated, not-to-the-cent pre-announcement estimates — treat those two
returns as illustrative of the mechanism, not locked backtest numbers, until
exact historical closes are hand-verified.

---

## AKAO — Achaogen (bankruptcy wipeout, single action)

```
Entry: 1,000 sh SEC-AKAO @ $5.00  ->  entry_cost = $5,000.00
  → bankruptcy_recovery @ (effective date pending verification)
      distribution_per_share = $0.00 (confirmed: Chapter 11 filed 2019-04-15,
      liquidation plan directed proceeds to secured/unsecured creditors, no
      distribution to common found)
Resulting security/shares: SEC-AKAO, 0 shares (extinguished)
Unresolved components: none
Terminal proceeds: $0.00
Realized return: -100.00%
```

## GNCA — Genocea Biosciences (bankruptcy wipeout, single action)

```
Entry: 500 sh SEC-GNCA @ $2.00  ->  entry_cost = $1,000.00
  → bankruptcy_recovery @ (effective date pending verification)
      distribution_per_share = $0.00 (confirmed: Chapter 11 filed 2022-07-05,
      Case 1:22-BK-10938, liquidation plan cancelled common equity, no
      distribution to common found)
Resulting security/shares: SEC-GNCA, 0 shares (extinguished)
Unresolved components: none
Terminal proceeds: $0.00
Realized return: -100.00%
```

## CNAT — Conatus Pharmaceuticals (reverse split → still-trading successor)

```
Entry: 1,000 sh SEC-CNAT @ $2.00  ->  entry_cost = $2,000.00
  → reverse_split @ 2020-05-26, ratio=0.10 (1-for-10, confirmed via primary
      8-K accession 0001193125-20-152366) -> 100.0000 shares
  → ticker_change @ 2020-05-27, SEC-CNAT -> SEC-HSTO (same legal entity,
      renamed Histogen Inc.; no share/value change)
Resulting security/shares: SEC-HSTO, 100 shares — STILL TRADING
Unresolved components: none (chain not extended past HSTO in this pilot —
  HSTO's later fate is explicitly out of scope)
Terminal proceeds: $0.00 (no cash leg — position is still held as SEC-HSTO)
Realized return: NULL — still_trading=True, no terminal $ figure exists.
  The resolver refuses to fabricate a return by pricing HSTO's current quote;
  that would require a separate valuation lookup, not ledger resolution.
```

## CEMP — Cempra (reverse split → rename → successor's own bankruptcy)

```
Entry: 1,000 sh SEC-CEMP @ $3.00  ->  entry_cost = $3,000.00
  → reverse_split @ 2017-11-03, ratio=0.20 (1-for-5, confirmed via primary
      8-K accession 0001193125-17-333062 — this is Cempra's OWN split, distinct
      from the separate 0.0229 exchange ratio applied to legacy private-Melinta
      holders, which does NOT apply to CEMP holders) -> 200.0000 shares
  → ticker_change @ 2017-11-03, SEC-CEMP -> SEC-MLNT (same legal entity,
      renamed Melinta Therapeutics Inc.; no share/value change)
  → bankruptcy_recovery @ 2020-04-02 (known_at=2020-03-13, plan confirmation
      date — not the Dec-2019 filing date, since recovery amount only became
      knowable at confirmation)
      distribution_per_share = $0.00 on 200.0000 shares (confirmed: Deerfield
      debt-for-equity swap of ~$140M debt for 100% of new equity; unsecured
      creditors given a $3.5M trust; no distribution to pre-petition common
      found)
Resulting security/shares: SEC-MLNT, 0 shares (extinguished)
Unresolved components: none
Terminal proceeds: $0.00
Realized return: -100.00%

This is the case that broke the old single-scalar schema: the 2017 merger
close price is NOT the true exit. The true terminal outcome (-100%) only
appears after chaining split -> rename -> MLNT's own later Chapter 11.
```

## ARRY — Array BioPharma (all-cash merger)

```
Entry: 100 sh SEC-ARRY @ $29.50  ->  entry_cost = $2,950.00
  → cash_merger @ (effective date pending verification), cash_per_share=$48.00
      on 100.0000 shares (confirmed deal term: Pfizer tender offer announced
      2019-06-17 at $48.00/share cash, ~$11.4B; ~77.0% of shares tendered by
      close of the 2019-07-29 tender period)
Resulting security/shares: none — cash-out
Unresolved components: none
Terminal proceeds: $4,800.00 (cash)
Realized return: +62.71% ((4,800 - 2,950) / 2,950 * 100)

Note: entry price is the pilot's back-calculated estimate, not a hand-verified
historical close — do not cite this return as a locked backtest number.
```

## TBRA — Tobira Therapeutics (cash + unresolved CVR)

```
Entry: 100 sh SEC-TBRA @ $4.74  ->  entry_cost = $474.00
  → cash_plus_cvr_merger @ (effective date pending verification),
      cash_per_share=$28.35 on 100.0000 shares (confirmed deal term: Allergan
      tender offer announced 2016-09-20)
      + 1 non-transferable CVR/share, worth up to $49.84/share in contingent
        milestones (e.g. $13.68/CVR if first patient enrolled in a qualifying
        Phase 3 CVC cenicriviroc fibrosis trial by 2028-12-31)
Resulting security/shares: none — cash + CVR
Unresolved components:
  - cvr_value_realized unresolved for SEC-TBRA (milestone outcome not yet
    known/disclosed as of this pilot's known_at cutoff)
Terminal proceeds: $2,835.00 cash ONLY — CVR is NOT counted as $0, it is
  excluded from total_proceeds entirely pending resolution
Realized return: NULL — the resolver explicitly refuses to compute a return
  with the CVR unresolved (would understate if assumed $0, overstate if
  assumed max value $49.84/share)
```

---

---

## Batch 2 — remaining bankruptcy wipeouts (9 names)

Same reconciliation standard as the original pilot. Three shapes emerged that
the ledger had to represent distinctly: **confirmed $0** (AKRX, ACET, NOVN,
plus MLNT already covered above), **confirmed non-zero** (BIND — the resolver
must not flatten every "bankrupt" outcome_type to -100%), and **confirmed
bankrupt but recovery amount not yet confirmed** (ARLZ, OREX, SRNE, PZRX —
required extending `CorporateAction.distribution_per_share` to allow an
explicit `None` = "unresolved" state, distinct from `0.0` = "confirmed
wipeout", mirroring the existing `cvr_value_realized=None` pattern).

### AKRX — Akorn (confirmed zero recovery)

```
Entry: 100 sh SEC-AKRX @ $3.00  ->  entry_cost = $300.00
  → bankruptcy_recovery @ 2020-10-01 (known_at=2020-09-02, plan/sale
      approval date), distribution_per_share=$0.00 (confirmed: Chapter 11
      filed 2020-05-20, term-loan lenders' 100% credit bid converted debt to
      equity in a new private entity; existing common equity wiped out)
Terminal proceeds: $0.00 | Realized return: -100.00%
```

### ACET — Aceto (confirmed zero recovery)

```
Entry: 100 sh SEC-ACET @ $3.00  ->  entry_cost = $300.00
  → bankruptcy_recovery @ 2019-10-01 (known_at=2019-09-18, plan confirmation
      date), distribution_per_share=$0.00 (confirmed: Second Modified Joint
      Plan of Liquidation confirmed 2019-09-18; "all interests in parent
      cancelled, released, extinguished on the Effective Date")
Terminal proceeds: $0.00 | Realized return: -100.00%
```

### NOVN — Novan (confirmed zero recovery)

```
Entry: 100 sh SEC-NOVN @ $3.00  ->  entry_cost = $300.00
  → bankruptcy_recovery @ 2024-01-25 (known_at=2024-01-25, plan confirmation
      hearing), distribution_per_share=$0.00 (confirmed: plan cancels all
      outstanding equity, no distribution to common)
Terminal proceeds: $0.00 | Realized return: -100.00%
```

### BIND — BIND Therapeutics (confirmed NON-ZERO recovery — the outlier)

```
Entry: 100 sh SEC-BIND @ $3.00  ->  entry_cost = $300.00
  → bankruptcy_recovery @ 2016-10-11 (known_at=2016-10-11, Plan Effective
      Date), distribution_per_share=$0.89 (confirmed: Pfizer won the 363
      auction for assets at $40M; common holders of record 2016-08-30 who
      completed required paperwork received two liquidation-trust
      distributions totaling ~$0.89/share, ~75.05% participation rate)
Resulting security/shares: extinguished, cash distribution only
Terminal proceeds: $89.00 | Realized return: -70.33%

This is the case that would break a naive "bankrupt = -100%" rule. BIND
common holders got a real, confirmed, non-trivial recovery — the ledger's
per-name distribution_per_share field (not an outcome_type-level default)
is what keeps this correct.
```

### ARLZ, OREX, SRNE, PZRX — confirmed bankrupt, recovery amount UNRESOLVED

```
ARLZ (Aralez): entry_cost = $300.00 (100 sh @ $3.00)
  → bankruptcy_recovery @ 2019-05-17 (Plan Effective Date), known_at=None,
      distribution_per_share=UNRESOLVED (TOPROL-XL franchise sold via
      ~$130M credit bid to a secured creditor -- suggests likely $0 to
      common but NOT confirmed to a primary document)
Terminal proceeds: $0.00 (cash-component only; recovery excluded, not
  assumed zero) | Realized return: NULL

OREX (Orexigen): entry_cost = $300.00
  → bankruptcy_recovery @ 2018-03-01 (month-level filing date, day
      unconfirmed), known_at=None, distribution_per_share=UNRESOLVED
      (company's own filings warned recovery may bear "little or no
      relationship" to trading price -- a caution, not a confirmed figure)
Terminal proceeds: $0.00 | Realized return: NULL

SRNE (Sorrento): entry_cost = $300.00
  → bankruptcy_recovery @ 2024-04-10 (Liquidation Plan Effective Date),
      known_at=None, distribution_per_share=UNRESOLVED (equity holders get
      a pro rata share of a Liquidating Trust -- a real, non-zero
      contingent entitlement whose magnitude is unresolved pending ongoing
      2025 clawback litigation)
Terminal proceeds: $0.00 | Realized return: NULL

PZRX (PhaseRx): entry_cost = $300.00
  → bankruptcy_recovery @ None (no plan-confirmation date located),
      known_at=None, distribution_per_share=UNRESOLVED (363 sale proceeds
      of $800K went to secured lender Hercules Capital first; a proposed
      equity distribution record date was filed then withdrawn)
Terminal proceeds: $0.00 | Realized return: NULL
```

All four correctly refuse to report a return rather than guessing —
`unresolved_components` is non-empty and `realized_return_pct` is `None` for
each, exactly like TBRA's unresolved CVR in the original pilot.

---

## Summary table

| Security | Entry cost | Terminal security | Still trading | Unresolved | Total proceeds | Realized return |
|---|---:|---|:---:|:---:|---:|---:|
| AKAO | $5,000.00 | SEC-AKAO (extinguished) | No | none | $0.00 | **-100.00%** |
| GNCA | $1,000.00 | SEC-GNCA (extinguished) | No | none | $0.00 | **-100.00%** |
| CNAT | $2,000.00 | SEC-HSTO (100 sh) | **Yes** | none | $0.00 | **NULL** (still trading) |
| CEMP | $3,000.00 | SEC-MLNT (extinguished) | No | none | $0.00 | **-100.00%** |
| ARRY | $2,950.00 | cash-out | No | none | $4,800.00 | **+62.71%** |
| TBRA | $474.00 | cash + unresolved CVR | No | **CVR** | $2,835.00 (cash only) | **NULL** (CVR unresolved) |
| MLNT | $600.00 | SEC-MLNT (extinguished) | No | none | $0.00 | **-100.00%** |
| AKRX | $300.00 | SEC-AKRX (extinguished) | No | none | $0.00 | **-100.00%** |
| ACET | $300.00 | SEC-ACET (extinguished) | No | none | $0.00 | **-100.00%** |
| NOVN | $300.00 | SEC-NOVN (extinguished) | No | none | $0.00 | **-100.00%** |
| BIND | $300.00 | SEC-BIND (extinguished) | No | none | $89.00 | **-70.33%** |
| ARLZ | $300.00 | SEC-ARLZ (extinguished) | No | **distribution** | $0.00 | **NULL** (recovery unresolved) |
| OREX | $300.00 | SEC-OREX (extinguished) | No | **distribution** | $0.00 | **NULL** (recovery unresolved) |
| SRNE | $300.00 | SEC-SRNE (extinguished) | No | **distribution** | $0.00 | **NULL** (recovery unresolved) |
| PZRX | $300.00 | SEC-PZRX (extinguished) | No | **distribution** | $0.00 | **NULL** (recovery unresolved) |

Three of the original six names resolve to a real terminal number (AKAO,
GNCA, CEMP all -100%; ARRY +62.71%). Two of six correctly resolve to `NULL`
rather than a fabricated number — CNAT because the successor is still trading
with no terminal $ figure, TBRA because the CVR has not resolved. This is the
intended behavior of the terminal-completeness invariant: a green test suite
proves the resolver is internally consistent, not that every pilot name has a
known historical return yet.

Batch 2 (bankruptcy-wipeout names) adds 9 more: 5 resolve to a confirmed
number (MLNT, AKRX, ACET, NOVN all -100%; BIND -70.33% — the confirmed
non-zero outlier), and 4 correctly resolve to `NULL` (ARLZ, OREX, SRNE, PZRX
— confirmed bankrupt, recovery-per-share amount not yet confirmed to a
primary document). **15 of 30 pilot names now resolve through the ledger;
15 remain** (9 `acquired` cash-merger names, 5 remaining `delisted_failed`
names — OHRP stays quarantined).

## Verification status

- Ledger test suite: green (27/27 in `test_corporate_action_ledger.py`,
  up from 18/18 in the original 6-name pilot); `ruff check` clean. This is a
  narrower claim than "full repository suite" — see wording-precision note
  in memory ([[corporate-action-ledger]]).
- `ruff check src/`: clean
- All six chains hand-reconciled against `resolve()` output above; numbers
  match the assertions in `tests/test_corporate_action_ledger.py`

## Next: extending to the remaining 24

Per the four locked invariants (price-basis consistency, point-in-time
separation, terminal completeness, security-vs-ticker lineage) and the edge
cases now covered by tests (cash+stock, fractional/cash-in-lieu, same-day
multi-action, OTC continuation, delayed CVR, early acquisition, still-trading
successor, entry-during-announcement-window), the resolver is ready to scale.
Extend in outcome-based batches (wipeouts, cash mergers, stock/cash-and-stock
mergers, still-trading successors) rather than alphabetically, and build the
representative investable cohort in parallel rather than gating on 100%
completion of the adverse-outcome cohort first.
