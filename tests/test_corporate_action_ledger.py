"""Corporate-action ledger reconciliation tests — the 6-name pilot.

These tests exist because a single scalar `share_conversion_ratio` per security
was found (during the 6-name pilot) to conflate distinct events: a reverse split
of the *original* security is not the same number as a merger exchange ratio
applied to the *other* side of a deal, and a name's true terminal outcome can
require chaining through a second corporate event (CEMP -> reverse split ->
renamed/continued as MLNT -> MLNT's own later bankruptcy -> $0 recovery).

Each test below manually recomputes the expected arithmetic
(entry_shares * entry_price, then apply every action in sequence, then compare
to the resolver's output) rather than just asserting against the resolver's own
numbers, per the required reconciliation invariant:

    entry_shares * entry_price  +/- every corporate action + cash/CVR/distributions
        == terminal proceeds  =>  realized return

AKAO and GNCA use synthetic entry prices (a real bankruptcy wipeout is $0
recovery regardless of entry price) -- these are explicitly plumbing tests for
the resolver mechanics, not sourced performance statistics. ARRY and TBRA use
the pilot's back-calculated (not-to-the-cent) entry prices for the same reason:
they exercise the mechanism, and must not be read as final backtest numbers
until the exact historical closes are hand-verified.
"""
from datetime import date
from pathlib import Path

import pytest

from bve.analysis.corporate_action_ledger import CorporateActionLedger, PriceBasis
from bve.models.corporate_action import CorporateAction, CorporateActionType

LEDGER_CSV = Path(__file__).resolve().parents[1] / "research" / "universe" / "corporate_action_ledger.csv"


@pytest.fixture(scope="module")
def ledger() -> CorporateActionLedger:
    return CorporateActionLedger.load_csv(LEDGER_CSV)


def test_ledger_csv_loads_all_six_pilot_chains(ledger: CorporateActionLedger):
    for sid in ("SEC-AKAO", "SEC-GNCA", "SEC-CNAT", "SEC-CEMP", "SEC-ARRY", "SEC-TBRA"):
        assert ledger.chain_for(sid), f"no actions found for {sid}"


def test_ledger_csv_loads_batch2_bankruptcy_wipeout_names(ledger: CorporateActionLedger):
    for sid in ("SEC-AKRX", "SEC-ACET", "SEC-NOVN", "SEC-BIND", "SEC-ARLZ", "SEC-OREX", "SEC-SRNE", "SEC-PZRX"):
        assert ledger.chain_for(sid), f"no actions found for {sid}"


def test_akao_bankruptcy_wipeout_is_plumbing_only(ledger: CorporateActionLedger):
    """AKAO: single bankruptcy_recovery action, distribution_per_share=0 (confirmed).
    Entry price ($5.00) is synthetic -- this asserts the wipeout mechanism, not a
    sourced performance number."""
    entry_shares, entry_price = 1000.0, 5.00
    result = ledger.resolve("SEC-AKAO", entry_shares, entry_price)

    entry_cost = entry_shares * entry_price
    expected_proceeds = entry_shares * 0.0  # distribution_per_share confirmed 0
    assert result.entry_cost == entry_cost
    assert result.total_proceeds == pytest.approx(expected_proceeds)
    assert result.still_trading is False
    assert result.unresolved_components == []
    assert result.realized_return_pct == pytest.approx(-100.0)


def test_gnca_bankruptcy_wipeout(ledger: CorporateActionLedger):
    entry_shares, entry_price = 500.0, 2.00
    result = ledger.resolve("SEC-GNCA", entry_shares, entry_price)

    assert result.total_proceeds == pytest.approx(0.0)
    assert result.still_trading is False
    assert result.realized_return_pct == pytest.approx(-100.0)


@pytest.mark.parametrize("sid", ["SEC-AKRX", "SEC-ACET", "SEC-NOVN"])
def test_batch2_confirmed_zero_recovery_bankruptcies(ledger: CorporateActionLedger, sid: str):
    """AKRX (Akorn), ACET (Aceto), NOVN (Novan): each has a confirmed plan-
    confirmation record stating common equity was cancelled with no
    distribution -- same confirmed-wipeout shape as AKAO/GNCA."""
    entry_shares, entry_price = 100.0, 3.00
    result = ledger.resolve(sid, entry_shares, entry_price)

    assert result.total_proceeds == pytest.approx(0.0)
    assert result.still_trading is False
    assert result.unresolved_components == []
    assert result.realized_return_pct == pytest.approx(-100.0)


def test_bind_bankruptcy_pays_confirmed_nonzero_liquidation_trust_distribution(ledger: CorporateActionLedger):
    """BIND Therapeutics is the one bankruptcy in the pilot where common
    holders received a confirmed non-zero recovery (~$0.89/share aggregate
    liquidation-trust distribution) -- must NOT be defaulted to -100% just
    because the outcome_type bucket is 'bankrupt'."""
    entry_shares, entry_price = 100.0, 3.00
    result = ledger.resolve("SEC-BIND", entry_shares, entry_price)

    expected_distribution = entry_shares * 0.89
    expected_return = (expected_distribution - entry_shares * entry_price) / (entry_shares * entry_price) * 100.0

    assert result.distribution_proceeds == pytest.approx(expected_distribution)
    assert result.still_trading is False
    assert result.unresolved_components == []
    assert result.realized_return_pct == pytest.approx(expected_return)


@pytest.mark.parametrize("sid", ["SEC-ARLZ", "SEC-OREX", "SEC-SRNE", "SEC-PZRX"])
def test_batch2_unresolved_recovery_bankruptcies_are_not_defaulted_to_zero(ledger: CorporateActionLedger, sid: str):
    """ARLZ, OREX, SRNE, PZRX: bankruptcy is confirmed but the amount (if
    any) recovered by common equity is not confirmed in primary sources.
    The resolver must refuse to guess -- neither -100% nor any other
    number -- distinct from AKRX/ACET/NOVN where $0 IS the confirmed fact."""
    entry_shares, entry_price = 100.0, 3.00
    result = ledger.resolve(sid, entry_shares, entry_price)

    assert result.still_trading is False
    assert result.unresolved_components != []
    assert result.realized_return_pct is None


def test_cnat_reverse_split_then_still_trading_as_hsto(ledger: CorporateActionLedger):
    """CNAT: 1-for-10 reverse split (ratio 0.10, confirmed via primary 8-K), then
    continues as HSTO with no further action recorded in this pilot -> still
    trading, no terminal $ figure, no fabricated realized_return."""
    entry_shares, entry_price = 1000.0, 2.00
    result = ledger.resolve("SEC-CNAT", entry_shares, entry_price)

    expected_shares_after_split = entry_shares * 0.10
    assert result.terminal_security_id == "SEC-HSTO"
    assert result.terminal_shares == pytest.approx(expected_shares_after_split)
    assert result.still_trading is True
    assert result.total_proceeds == pytest.approx(0.0)
    assert result.realized_return_pct is None  # must not guess a return while still trading


def test_cemp_chains_through_split_rename_and_mlnt_bankruptcy(ledger: CorporateActionLedger):
    """CEMP: 1-for-5 reverse split (ratio 0.20, confirmed) -> renamed/continued as
    MLNT -> MLNT's own Chapter 11 -> $0 recovery. The 2017 merger close price is
    NOT the true exit; recovery_value=0 only appears after the full chain."""
    entry_shares, entry_price = 1000.0, 3.00
    result = ledger.resolve("SEC-CEMP", entry_shares, entry_price)

    shares_after_split = entry_shares * 0.20
    expected_proceeds = shares_after_split * 0.0  # MLNT bankruptcy, confirmed $0 to common
    assert result.terminal_security_id == "SEC-MLNT"
    assert result.total_proceeds == pytest.approx(expected_proceeds)
    assert result.still_trading is False
    assert result.realized_return_pct == pytest.approx(-100.0)
    # the chain must show both the split AND the transition through MLNT, not a single hop
    action_types = [a.split("@")[0] for a in result.actions_applied]
    assert action_types == ["reverse_split", "ticker_change", "bankruptcy_recovery"]


def test_arry_cash_merger_reconciles_to_confirmed_deal_price(ledger: CorporateActionLedger):
    """ARRY: all-cash merger at a confirmed $48.00/share (Pfizer deal term).
    Entry price ($29.50) is the pilot's back-calculated, not-to-the-cent estimate
    of the pre-announcement close -- treat the resulting return as illustrative
    of the mechanism, not a locked backtest number."""
    entry_shares, entry_price = 100.0, 29.50
    result = ledger.resolve("SEC-ARRY", entry_shares, entry_price)

    entry_cost = entry_shares * entry_price
    expected_cash = entry_shares * 48.00
    expected_return_pct = (expected_cash - entry_cost) / entry_cost * 100.0

    assert result.cash_proceeds == pytest.approx(expected_cash)
    assert result.still_trading is False
    assert result.unresolved_components == []
    assert result.realized_return_pct == pytest.approx(expected_return_pct)
    assert result.realized_return_pct == pytest.approx(62.71186, rel=1e-4)


def test_tbra_cash_plus_unresolved_cvr_must_not_be_treated_as_zero(ledger: CorporateActionLedger):
    """TBRA: $28.35/share cash is a confirmed deal term, but the CVR (up to $49.84,
    milestone-contingent) has an unresolved realized value in this pilot. The
    resolver must flag this and refuse to compute a realized_return_pct rather
    than silently assuming the CVR paid $0 (which would understate the true
    return) or its max value (which would overstate it)."""
    entry_shares, entry_price = 100.0, 4.74
    result = ledger.resolve("SEC-TBRA", entry_shares, entry_price)

    expected_cash = entry_shares * 28.35
    assert result.cash_proceeds == pytest.approx(expected_cash)
    assert result.cvr_proceeds == 0.0
    assert result.unresolved_components != []
    assert result.realized_return_pct is None  # would be wrong to compute this with CVR unresolved


def test_stock_merger_action_requires_merger_exchange_ratio():
    with pytest.raises(ValueError):
        CorporateAction(
            security_id="SEC-TEST",
            action_sequence=1,
            action_type=CorporateActionType.STOCK_MERGER,
            from_security_id="SEC-TEST",
            to_security_id="SEC-OTHER",
        )


def test_bankruptcy_recovery_with_unconfirmed_distribution_is_unresolved_not_zero():
    """distribution_per_share=None on a bankruptcy_recovery action is a distinct,
    explicit fact ("recovery amount not yet confirmed") from distribution_per_share=0.0
    ("confirmed wipeout") -- it must never be silently coerced to either. The resolver
    must flag it in unresolved_components and refuse to compute realized_return_pct,
    the same terminal-completeness treatment as an unresolved CVR."""
    action = CorporateAction(
        security_id="SEC-UNRESOLVED-BK",
        action_sequence=1,
        action_type=CorporateActionType.BANKRUPTCY_RECOVERY,
        effective_date=date(2023, 4, 10),
        from_security_id="SEC-UNRESOLVED-BK",
        to_security_id="SEC-UNRESOLVED-BK",
    )
    ledger = CorporateActionLedger([action])
    result = ledger.resolve("SEC-UNRESOLVED-BK", 100.0, 5.0)

    assert result.distribution_proceeds == 0.0
    assert result.still_trading is False
    assert result.unresolved_components != []
    assert result.realized_return_pct is None  # must not guess $0 or any other value


# --- Edge-case tests added for the resolver rewrite: point-in-time filtering,
# entry-timing warnings, cash-and-stock mergers, fractional cash-in-lieu, and
# raw-vs-adjusted price basis enforcement. All use synthetic single-purpose
# chains built directly from CorporateAction, not the 6-name pilot CSV, since
# none of the pilot rows happen to exercise these mechanics together.


def test_resolve_rejects_split_adjusted_price_basis():
    """The resolver must refuse SPLIT_ADJUSTED input outright -- there is no
    supported reconciliation path for a pre-adjusted price series, since
    applying this ledger's own split actions on top would double-adjust."""
    ledger = CorporateActionLedger([])
    with pytest.raises(ValueError):
        ledger.resolve(
            "SEC-NONE", 100.0, 10.0, price_basis=PriceBasis.SPLIT_ADJUSTED
        )


def test_cash_and_stock_merger_pays_cash_and_continues_chain():
    """CASH_AND_STOCK_MERGER must realize the cash leg immediately (added to
    proceeds) while the stock leg continues the chain under to_security_id --
    unlike CASH_MERGER, this must not terminate the position."""
    actions = [
        CorporateAction(
            security_id="SEC-MIXED",
            action_sequence=1,
            action_type=CorporateActionType.CASH_AND_STOCK_MERGER,
            effective_date=date(2022, 1, 1),
            known_at=date(2022, 1, 1),
            from_security_id="SEC-MIXED",
            to_security_id="SEC-ACQUIRER",
            merger_exchange_ratio=0.5,
            cash_per_share=10.0,
        ),
    ]
    ledger = CorporateActionLedger(actions)
    result = ledger.resolve("SEC-MIXED", 100.0, 20.0)

    assert result.cash_proceeds == pytest.approx(1000.0)  # 100 shares * $10
    assert result.terminal_security_id == "SEC-ACQUIRER"
    assert result.terminal_shares == pytest.approx(50.0)  # 100 shares * 0.5 ratio
    assert result.still_trading is True
    assert result.realized_return_pct is None  # still trading -- no terminal $ figure


def test_fractional_shares_cashed_out_at_cash_in_lieu_price():
    """When cash_in_lieu_price_per_share is set on a stock-conversion action,
    the resulting share count must be floored and the fractional remainder
    cashed out at that price -- not silently dropped or rounded up."""
    actions = [
        CorporateAction(
            security_id="SEC-FRAC",
            action_sequence=1,
            action_type=CorporateActionType.STOCK_MERGER,
            effective_date=date(2021, 6, 1),
            known_at=date(2021, 6, 1),
            from_security_id="SEC-FRAC",
            to_security_id="SEC-NEWCO",
            merger_exchange_ratio=0.3333,
            cash_in_lieu_price_per_share=15.0,
        ),
    ]
    ledger = CorporateActionLedger(actions)
    result = ledger.resolve("SEC-FRAC", 100.0, 5.0)

    exact = 100.0 * 0.3333  # 33.33
    whole = 33.0
    remainder = exact - whole
    assert result.terminal_shares == pytest.approx(whole)
    assert result.cash_in_lieu_proceeds == pytest.approx(remainder * 15.0)
    assert result.still_trading is True


def test_multiple_same_day_actions_apply_in_sequence_order():
    """A same-day split then rename (action_sequence 1, 2) must apply in
    recorded sequence order, not be collapsed or reordered."""
    actions = [
        CorporateAction(
            security_id="SEC-SAMEDAY",
            action_sequence=1,
            action_type=CorporateActionType.REVERSE_SPLIT,
            effective_date=date(2020, 3, 1),
            known_at=date(2020, 3, 1),
            from_security_id="SEC-SAMEDAY",
            to_security_id="SEC-SAMEDAY",
            reverse_split_ratio=0.25,
        ),
        CorporateAction(
            security_id="SEC-SAMEDAY",
            action_sequence=2,
            action_type=CorporateActionType.TICKER_CHANGE,
            effective_date=date(2020, 3, 1),
            known_at=date(2020, 3, 1),
            from_security_id="SEC-SAMEDAY",
            to_security_id="SEC-RENAMED",
        ),
    ]
    ledger = CorporateActionLedger(actions)
    result = ledger.resolve("SEC-SAMEDAY", 400.0, 1.0)

    assert result.terminal_security_id == "SEC-RENAMED"
    assert result.terminal_shares == pytest.approx(100.0)  # 400 * 0.25
    assert [a.split("@")[0] for a in result.actions_applied] == ["reverse_split", "ticker_change"]


def test_exchange_delisting_continued_otc_is_not_an_economic_exit():
    """A venue change (exchange delisting, continued OTC) must not zero out
    shares or be treated as a terminal event -- it's a relabeling, like
    ticker_change."""
    actions = [
        CorporateAction(
            security_id="SEC-OTC",
            action_sequence=1,
            action_type=CorporateActionType.EXCHANGE_DELISTING_CONTINUED_OTC,
            effective_date=date(2023, 2, 1),
            known_at=date(2023, 2, 1),
            from_security_id="SEC-OTC",
            to_security_id="SEC-OTC-PINK",
        ),
    ]
    ledger = CorporateActionLedger(actions)
    result = ledger.resolve("SEC-OTC", 250.0, 3.0)

    assert result.terminal_security_id == "SEC-OTC-PINK"
    assert result.terminal_shares == pytest.approx(250.0)
    assert result.still_trading is True
    assert result.realized_return_pct is None


def test_cvr_realized_years_later_is_hidden_before_known_at_and_visible_after():
    """A CVR paid years after deal close: as_of_date before its known_at must
    truncate the chain (point_in_time_truncated=True, no return); as_of_date
    on/after known_at must resolve it fully."""
    actions = [
        CorporateAction(
            security_id="SEC-CVR",
            action_sequence=1,
            action_type=CorporateActionType.CASH_PLUS_CVR_MERGER,
            announcement_date=date(2018, 1, 10),
            effective_date=date(2018, 3, 1),
            known_at=date(2021, 6, 15),  # milestone outcome disclosed years after close
            from_security_id="SEC-CVR",
            to_security_id="SEC-CVR",
            cash_per_share=10.0,
            cvr_terms="milestone-contingent",
            cvr_value_realized=4.0,
        ),
    ]
    ledger = CorporateActionLedger(actions)

    before = ledger.resolve("SEC-CVR", 100.0, 8.0, as_of_date=date(2020, 1, 1))
    assert before.point_in_time_truncated is True
    assert before.realized_return_pct is None
    assert before.cash_proceeds == 0.0

    after = ledger.resolve("SEC-CVR", 100.0, 8.0, as_of_date=date(2021, 6, 15))
    assert after.point_in_time_truncated is False
    assert after.cash_proceeds == pytest.approx(1000.0)
    assert after.cvr_proceeds == pytest.approx(400.0)
    assert after.realized_return_pct == pytest.approx((1400.0 - 800.0) / 800.0 * 100.0)


def test_acquisition_before_fixed_hold_exit_date_resolves_fully():
    """A hypothetical fixed-hold exit date that falls after the acquisition's
    known_at must see the full cash-merger resolution, not a truncated chain."""
    actions = [
        CorporateAction(
            security_id="SEC-EARLYDEAL",
            action_sequence=1,
            action_type=CorporateActionType.CASH_MERGER,
            announcement_date=date(2019, 5, 1),
            effective_date=date(2019, 7, 1),
            known_at=date(2019, 5, 1),
            from_security_id="SEC-EARLYDEAL",
            to_security_id="SEC-EARLYDEAL",
            cash_per_share=20.0,
        ),
    ]
    ledger = CorporateActionLedger(actions)
    result = ledger.resolve(
        "SEC-EARLYDEAL", 50.0, 12.0, as_of_date=date(2019, 12, 31)
    )

    assert result.point_in_time_truncated is False
    assert result.cash_proceeds == pytest.approx(1000.0)
    assert result.still_trading is False
    assert result.realized_return_pct == pytest.approx((1000.0 - 600.0) / 600.0 * 100.0)


def test_successor_still_trading_past_test_horizon_yields_no_return():
    """A successor security still trading past the as_of_date horizon must
    yield still_trading=True and no fabricated realized_return_pct, whether
    or not an as_of_date is supplied."""
    actions = [
        CorporateAction(
            security_id="SEC-ONGOING",
            action_sequence=1,
            action_type=CorporateActionType.TICKER_CHANGE,
            effective_date=date(2022, 4, 1),
            known_at=date(2022, 4, 1),
            from_security_id="SEC-ONGOING",
            to_security_id="SEC-ONGOING2",
        ),
    ]
    ledger = CorporateActionLedger(actions)
    result = ledger.resolve(
        "SEC-ONGOING", 10.0, 7.0, as_of_date=date(2026, 1, 1)
    )

    assert result.terminal_security_id == "SEC-ONGOING2"
    assert result.still_trading is True
    assert result.point_in_time_truncated is False
    assert result.realized_return_pct is None


def test_entry_between_announcement_and_effective_date_is_flagged():
    """Entry occurring after an action's announcement_date but before its
    effective_date must be surfaced via entry_timing_warnings, not silently
    resolved as a clean pre-announcement entry -- per the validation plan's
    convention this timing should likely be excluded from a clean backtest."""
    actions = [
        CorporateAction(
            security_id="SEC-MERGERARB",
            action_sequence=1,
            action_type=CorporateActionType.CASH_MERGER,
            announcement_date=date(2020, 2, 1),
            effective_date=date(2020, 5, 1),
            known_at=date(2020, 2, 1),
            from_security_id="SEC-MERGERARB",
            to_security_id="SEC-MERGERARB",
            cash_per_share=15.0,
        ),
    ]
    ledger = CorporateActionLedger(actions)

    flagged = ledger.resolve(
        "SEC-MERGERARB", 20.0, 14.0, entry_date=date(2020, 3, 1)
    )
    assert flagged.entry_timing_warnings != []

    clean = ledger.resolve(
        "SEC-MERGERARB", 20.0, 14.0, entry_date=date(2020, 1, 1)
    )
    assert clean.entry_timing_warnings == []
