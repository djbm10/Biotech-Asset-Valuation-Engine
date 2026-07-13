"""CorporateActionLedger integration into HistoricalImpliedPoSValidator.

The exit/return path for a held position is a separate concern from the
signal (model_pos/implied_pos/pos_spread), which is computed from
entry_price and the asset config only -- see
HistoricalImpliedPoSValidator._resolve_exit's docstring. These tests cover
that exit path only: names with no ledger coverage must behave exactly as
before (test 1); names with a resolved terminal event exit early at the
ledger's outcome instead of the fixed horizon (tests 2-3, 5); names that
merge into a still-trading successor are priced through that successor at
the fixed horizon (test 4); an unresolved outcome produces no observation
at all rather than a fabricated return (test 6); a terminal event announced
after the planned exit date does not affect the trade (test 7); and the
pre-existing fixed-horizon test suite keeps passing unchanged (test 8, see
test_historical_implied_pos_validation.py itself).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from bve.analysis.corporate_action_ledger import CorporateActionLedger
from bve.analysis.historical_implied_pos_validation import (
    ExitAttribution,
    HistoricalImpliedPoSValidator,
)
from bve.models.corporate_action import CorporateAction, CorporateActionType
from bve.ops.historical_replay import ReplayStore
from tests.test_historical_implied_pos_validation import (
    _FakeSolver,
    _write_config,
    _write_watchlist,
)


def _seed_prices(replay_db: Path, prices: dict[str, list[tuple[date, float]]]) -> None:
    store = ReplayStore(str(replay_db))
    try:
        for ticker, rows in prices.items():
            store.insert_prices(ticker, rows)
    finally:
        store.close()


def test_ordinary_still_trading_company_uses_fixed_horizon(tmp_path: Path) -> None:
    """Test 1: no ledger coverage -> unchanged fixed-horizon behavior."""
    aaa = tmp_path / "aaa.yaml"
    _write_config(aaa, ticker="AAA", asset_id="asset-aaa")
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [aaa])

    replay_db = tmp_path / "replay.sqlite"
    _seed_prices(
        replay_db,
        {
            "AAA": [(date(2025, 1, 1), 10.0), (date(2025, 1, 31), 14.0)],
            "XBI": [(date(2025, 1, 1), 100.0), (date(2025, 1, 31), 102.0)],
        },
    )

    validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.25}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=1,
        bootstrap_iterations=200,
        corporate_action_ledger=CorporateActionLedger([]),
        security_id_by_ticker={},
    )
    report = validator.validate(
        str(watchlist), start_date=date(2025, 1, 1), end_date=date(2025, 1, 31)
    )

    assert report.n_observations == 1
    obs = report.observations[0]
    assert obs.exit_reason == ExitAttribution.FIXED_HORIZON.value
    assert obs.actual_exit_date == obs.exit_date == date(2025, 1, 31)
    assert obs.unresolved_reason is None
    assert obs.asset_return_pct == pytest.approx(ReplayStore.compute_return_pct(10.0, 14.0))


def test_acquisition_before_horizon_exits_at_announcement_convention(tmp_path: Path) -> None:
    """Test 2: cash acquisition closing before the fixed horizon exits early."""
    aaa = tmp_path / "aaa.yaml"
    _write_config(aaa, ticker="AAA", asset_id="asset-aaa")
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [aaa])

    replay_db = tmp_path / "replay.sqlite"
    _seed_prices(
        replay_db,
        {
            "AAA": [(date(2025, 1, 1), 10.0)],
            "XBI": [(date(2025, 1, 1), 100.0), (date(2025, 1, 31), 102.0)],
        },
    )

    ledger = CorporateActionLedger(
        [
            CorporateAction(
                security_id="SEC-AAA",
                action_sequence=1,
                action_type=CorporateActionType.CASH_MERGER,
                announcement_date=date(2025, 1, 5),
                effective_date=date(2025, 1, 15),
                known_at=date(2025, 1, 15),
                from_security_id="SEC-AAA",
                to_security_id="SEC-AAA",
                cash_per_share=25.0,
                source="test",
            )
        ]
    )

    validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.25}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=1,
        bootstrap_iterations=200,
        corporate_action_ledger=ledger,
        security_id_by_ticker={"AAA": "SEC-AAA"},
    )
    report = validator.validate(
        str(watchlist), start_date=date(2025, 1, 1), end_date=date(2025, 1, 31)
    )

    assert report.n_observations == 1
    obs = report.observations[0]
    assert obs.exit_reason == ExitAttribution.CASH_ACQUISITION.value
    assert obs.exit_date == date(2025, 1, 31)
    assert obs.actual_exit_date == date(2025, 1, 15)
    assert obs.terminal_proceeds_per_share == 25.0
    assert obs.asset_return_pct == (25.0 - 10.0) / 10.0 * 100.0
    assert obs.unresolved_reason is None


def test_bankruptcy_before_horizon_uses_confirmed_recovery(tmp_path: Path) -> None:
    """Test 3: confirmed non-zero bankruptcy recovery, not a guessed wipeout."""
    aaa = tmp_path / "aaa.yaml"
    _write_config(aaa, ticker="AAA", asset_id="asset-aaa")
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [aaa])

    replay_db = tmp_path / "replay.sqlite"
    _seed_prices(
        replay_db,
        {
            "AAA": [(date(2025, 1, 1), 10.0)],
            "XBI": [(date(2025, 1, 1), 100.0), (date(2025, 1, 31), 102.0)],
        },
    )

    ledger = CorporateActionLedger(
        [
            CorporateAction(
                security_id="SEC-AAA",
                action_sequence=1,
                action_type=CorporateActionType.BANKRUPTCY_RECOVERY,
                announcement_date=date(2025, 1, 5),
                effective_date=date(2025, 1, 20),
                known_at=date(2025, 1, 20),
                from_security_id="SEC-AAA",
                to_security_id="SEC-AAA",
                distribution_per_share=0.89,
                source="test",
            )
        ]
    )

    validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.25}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=1,
        bootstrap_iterations=200,
        corporate_action_ledger=ledger,
        security_id_by_ticker={"AAA": "SEC-AAA"},
    )
    report = validator.validate(
        str(watchlist), start_date=date(2025, 1, 1), end_date=date(2025, 1, 31)
    )

    assert report.n_observations == 1
    obs = report.observations[0]
    assert obs.exit_reason == ExitAttribution.BANKRUPTCY_RECOVERY.value
    assert obs.actual_exit_date == date(2025, 1, 20)
    assert obs.terminal_proceeds_per_share == 0.89
    assert obs.asset_return_pct == (0.89 - 10.0) / 10.0 * 100.0


def test_reverse_merger_follows_successor_through_horizon(tmp_path: Path) -> None:
    """Test 4: a still-trading successor is priced under its own ticker."""
    aaa = tmp_path / "aaa.yaml"
    _write_config(aaa, ticker="AAA", asset_id="asset-aaa")
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [aaa])

    replay_db = tmp_path / "replay.sqlite"
    _seed_prices(
        replay_db,
        {
            "AAA": [(date(2025, 1, 1), 10.0)],
            "BBB": [(date(2025, 1, 31), 3.0)],
            "XBI": [(date(2025, 1, 1), 100.0), (date(2025, 1, 31), 102.0)],
        },
    )

    ledger = CorporateActionLedger(
        [
            CorporateAction(
                security_id="SEC-AAA",
                action_sequence=1,
                action_type=CorporateActionType.STOCK_MERGER,
                announcement_date=date(2025, 1, 5),
                effective_date=date(2025, 1, 10),
                known_at=date(2025, 1, 10),
                from_security_id="SEC-AAA",
                to_security_id="SEC-BBB",
                merger_exchange_ratio=0.5,
                source="test",
            )
        ]
    )

    validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.25}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=1,
        bootstrap_iterations=200,
        corporate_action_ledger=ledger,
        security_id_by_ticker={"AAA": "SEC-AAA", "BBB": "SEC-BBB"},
    )
    report = validator.validate(
        str(watchlist), start_date=date(2025, 1, 1), end_date=date(2025, 1, 31)
    )

    assert report.n_observations == 1
    obs = report.observations[0]
    assert obs.exit_reason == ExitAttribution.STOCK_MERGER_SUCCESSOR.value
    assert obs.actual_exit_date == date(2025, 1, 31)
    # 1 entry share * 0.5 exchange ratio = 0.5 successor shares @ $3.00 = $1.50
    assert obs.terminal_proceeds_per_share == 1.5
    assert obs.asset_return_pct == (1.5 - 10.0) / 10.0 * 100.0


def test_chained_reverse_split_then_bankruptcy_resolves_correctly(tmp_path: Path) -> None:
    """Test 5: CEMP -> MLNT -> bankruptcy shape (reverse split, rename, then wipeout)."""
    aaa = tmp_path / "aaa.yaml"
    _write_config(aaa, ticker="AAA", asset_id="asset-aaa")
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [aaa])

    replay_db = tmp_path / "replay.sqlite"
    _seed_prices(
        replay_db,
        {
            "AAA": [(date(2025, 1, 1), 10.0)],
            "XBI": [(date(2025, 1, 1), 100.0), (date(2025, 1, 31), 102.0)],
        },
    )

    ledger = CorporateActionLedger(
        [
            CorporateAction(
                security_id="SEC-AAA",
                action_sequence=1,
                action_type=CorporateActionType.STOCK_MERGER,
                announcement_date=date(2025, 1, 2),
                effective_date=date(2025, 1, 5),
                known_at=date(2025, 1, 5),
                from_security_id="SEC-AAA",
                to_security_id="SEC-BBB",
                merger_exchange_ratio=1.0,
                source="test",
            ),
            CorporateAction(
                security_id="SEC-BBB",
                action_sequence=1,
                action_type=CorporateActionType.BANKRUPTCY_RECOVERY,
                announcement_date=date(2025, 1, 10),
                effective_date=date(2025, 1, 20),
                known_at=date(2025, 1, 20),
                from_security_id="SEC-BBB",
                to_security_id="SEC-BBB",
                distribution_per_share=0.0,
                source="test",
            ),
        ]
    )

    validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.25}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=1,
        bootstrap_iterations=200,
        corporate_action_ledger=ledger,
        security_id_by_ticker={"AAA": "SEC-AAA"},
    )
    report = validator.validate(
        str(watchlist), start_date=date(2025, 1, 1), end_date=date(2025, 1, 31)
    )

    assert report.n_observations == 1
    obs = report.observations[0]
    assert obs.exit_reason == ExitAttribution.BANKRUPTCY_RECOVERY.value
    assert obs.actual_exit_date == date(2025, 1, 20)
    assert obs.terminal_proceeds_per_share == 0.0
    assert obs.asset_return_pct == -100.0


def test_unresolved_recovery_produces_no_fabricated_return(tmp_path: Path) -> None:
    """Test 6: OHRP-shape -- dissolution with no confirmed distribution amount
    must produce zero observations, never a guessed $0 or default value."""
    aaa = tmp_path / "aaa.yaml"
    _write_config(aaa, ticker="AAA", asset_id="asset-aaa")
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [aaa])

    replay_db = tmp_path / "replay.sqlite"
    _seed_prices(
        replay_db,
        {
            "AAA": [(date(2025, 1, 1), 10.0)],
            "XBI": [(date(2025, 1, 1), 100.0), (date(2025, 1, 31), 102.0)],
        },
    )

    ledger = CorporateActionLedger(
        [
            CorporateAction(
                security_id="SEC-AAA",
                action_sequence=1,
                action_type=CorporateActionType.LIQUIDATION_DISTRIBUTION,
                announcement_date=date(2025, 1, 5),
                effective_date=date(2025, 1, 20),
                known_at=date(2025, 1, 20),
                from_security_id="SEC-AAA",
                to_security_id="SEC-AAA",
                distribution_per_share=None,
                source="test",
            )
        ]
    )

    validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.25}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=1,
        bootstrap_iterations=200,
        corporate_action_ledger=ledger,
        security_id_by_ticker={"AAA": "SEC-AAA"},
    )
    report = validator.validate(
        str(watchlist), start_date=date(2025, 1, 1), end_date=date(2025, 1, 31)
    )

    assert report.n_observations == 0
    assert report.n_selected_trades == 0


def test_outcome_announced_after_planned_exit_does_not_affect_trade(tmp_path: Path) -> None:
    """Test 7: a deal only known after the planned exit date must not leak
    into the trade -- it should behave exactly like fixed_horizon."""
    aaa = tmp_path / "aaa.yaml"
    _write_config(aaa, ticker="AAA", asset_id="asset-aaa")
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [aaa])

    replay_db = tmp_path / "replay.sqlite"
    _seed_prices(
        replay_db,
        {
            "AAA": [(date(2025, 1, 1), 10.0), (date(2025, 1, 31), 12.0)],
            "XBI": [(date(2025, 1, 1), 100.0), (date(2025, 1, 31), 102.0)],
        },
    )

    ledger = CorporateActionLedger(
        [
            CorporateAction(
                security_id="SEC-AAA",
                action_sequence=1,
                action_type=CorporateActionType.CASH_MERGER,
                announcement_date=date(2025, 2, 5),
                effective_date=date(2025, 2, 15),
                known_at=date(2025, 2, 15),
                from_security_id="SEC-AAA",
                to_security_id="SEC-AAA",
                cash_per_share=25.0,
                source="test",
            )
        ]
    )

    validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.25}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=1,
        bootstrap_iterations=200,
        corporate_action_ledger=ledger,
        security_id_by_ticker={"AAA": "SEC-AAA"},
    )
    report = validator.validate(
        str(watchlist), start_date=date(2025, 1, 1), end_date=date(2025, 1, 31)
    )

    assert report.n_observations == 1
    obs = report.observations[0]
    assert obs.exit_reason == ExitAttribution.FIXED_HORIZON.value
    assert obs.actual_exit_date == date(2025, 1, 31)
    assert obs.asset_return_pct == pytest.approx(ReplayStore.compute_return_pct(10.0, 12.0))
