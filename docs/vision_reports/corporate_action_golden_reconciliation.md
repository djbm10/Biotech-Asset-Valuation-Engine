# Corporate-Action Ledger — Golden Reconciliation Report

**Scope:** the 6-name pilot (AKAO, GNCA, CNAT, CEMP, ARRY, TBRA) that exposed the
inadequacy of a single scalar `share_conversion_ratio` column and motivated the
`CorporateActionLedger` / `ReconciliationResult` rewrite.

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

## Summary table

| Security | Entry cost | Terminal security | Still trading | Unresolved | Total proceeds | Realized return |
|---|---:|---|:---:|:---:|---:|---:|
| AKAO | $5,000.00 | SEC-AKAO (extinguished) | No | none | $0.00 | **-100.00%** |
| GNCA | $1,000.00 | SEC-GNCA (extinguished) | No | none | $0.00 | **-100.00%** |
| CNAT | $2,000.00 | SEC-HSTO (100 sh) | **Yes** | none | $0.00 | **NULL** (still trading) |
| CEMP | $3,000.00 | SEC-MLNT (extinguished) | No | none | $0.00 | **-100.00%** |
| ARRY | $2,950.00 | cash-out | No | none | $4,800.00 | **+62.71%** |
| TBRA | $474.00 | cash + unresolved CVR | No | **CVR** | $2,835.00 (cash only) | **NULL** (CVR unresolved) |

Three of six names resolve to a real terminal number (AKAO, GNCA, CEMP all
-100%; ARRY +62.71%). Two of six correctly resolve to `NULL` rather than a
fabricated number — CNAT because the successor is still trading with no
terminal $ figure, TBRA because the CVR has not resolved. This is the intended
behavior of the terminal-completeness invariant: a green test suite proves the
resolver is internally consistent, not that every pilot name has a known
historical return yet.

## Verification status

- Full test suite: green (18/18 in `test_corporate_action_ledger.py`; full
  `tests/` suite passing)
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
