"""
Tests for the company-level SOTP validation harness.

Covers:
- ADV liquidity gate at entry date
- Transaction cost adjustment (tiered by ADV)
- Placebo test (rank permutation)
- Subgroup analysis (time period, SOTP tier)
- ValidationHarnessReport grade assignment
"""
from __future__ import annotations

import sqlite3
import tempfile
from datetime import date

import pytest

from bve.analysis.company_sotp_backtest import CompanySOTPBacktestTrade
from bve.analysis.validation_harness import (
    ValidationHarnessConfig,
    _compute_adv_millions,
    _compute_placebo_distribution,
    _compute_subgroups,
    _resolve_tx_cost_pct,
    run_validation_harness,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trade(
    ticker: str = "VKTX",
    snapshot_date: date = date(2022, 1, 1),
    exit_date: date = date(2023, 1, 1),
    ranked_sotp_discount: float = 2.0,
    action_policy: str = "buy",
    company_return_pct: float = 0.30,
    benchmark_return_pct: float = 0.10,
) -> CompanySOTPBacktestTrade:
    return CompanySOTPBacktestTrade(
        snapshot_date=snapshot_date,
        exit_date=exit_date,
        ticker=ticker,
        company_id=ticker.lower(),
        ranked_sotp_discount=ranked_sotp_discount,
        action_policy=action_policy,
        company_return_pct=company_return_pct,
        benchmark_return_pct=benchmark_return_pct,
        excess_return_pct=company_return_pct - benchmark_return_pct,
    )


def _make_replay_db_with_market_prices(
    *,
    ticker: str,
    price_date: date,
    close_usd: float = 20.0,
    volume: int = 1_000_000,
    n_days: int = 25,
) -> str:
    """Return path to a temp SQLite db with n_days of market_prices rows."""
    tmp = tempfile.mktemp(suffix=".sqlite")
    conn = sqlite3.connect(tmp)
    conn.execute(
        """
        CREATE TABLE market_prices (
            ticker TEXT NOT NULL,
            price_date TEXT NOT NULL,
            close_usd REAL,
            adj_close_usd REAL,
            open_usd REAL,
            high_usd REAL,
            low_usd REAL,
            volume INTEGER,
            PRIMARY KEY (ticker, price_date)
        )
        """
    )
    from datetime import timedelta

    base = price_date
    for i in range(n_days):
        d = base - timedelta(days=i)
        conn.execute(
            "INSERT INTO market_prices VALUES (?,?,?,?,?,?,?,?)",
            (ticker, d.isoformat(), close_usd, close_usd, close_usd, close_usd, close_usd, volume),
        )
    conn.commit()
    conn.close()
    return tmp


# ---------------------------------------------------------------------------
# _compute_adv_millions
# ---------------------------------------------------------------------------

class TestComputeAdvMillions:
    def test_returns_correct_adv_for_known_prices(self) -> None:
        db_path = _make_replay_db_with_market_prices(
            ticker="VKTX",
            price_date=date(2022, 1, 15),
            close_usd=20.0,
            volume=1_000_000,
            n_days=25,
        )
        adv = _compute_adv_millions("VKTX", date(2022, 1, 15), db_path, window_days=20)
        # 20 * 1_000_000 / 1e6 = $20M ADV
        assert adv is not None
        assert abs(adv - 20.0) < 0.5

    def test_returns_none_when_insufficient_data(self) -> None:
        db_path = _make_replay_db_with_market_prices(
            ticker="TINY",
            price_date=date(2022, 1, 15),
            close_usd=5.0,
            volume=100_000,
            n_days=5,  # fewer than 20
        )
        adv = _compute_adv_millions("TINY", date(2022, 1, 15), db_path, window_days=20, min_days=10)
        assert adv is None

    def test_returns_none_for_missing_ticker(self) -> None:
        db_path = _make_replay_db_with_market_prices(
            ticker="VKTX",
            price_date=date(2022, 1, 15),
            close_usd=20.0,
            volume=1_000_000,
            n_days=25,
        )
        adv = _compute_adv_millions("MISSING", date(2022, 1, 15), db_path)
        assert adv is None


# ---------------------------------------------------------------------------
# _resolve_tx_cost_pct
# ---------------------------------------------------------------------------

class TestResolveTxCostPct:
    def test_high_liquidity_uses_base_cost(self) -> None:
        config = ValidationHarnessConfig(base_tx_cost_pct=0.003, illiquid_tx_cost_pct=0.006)
        cost = _resolve_tx_cost_pct(adv_millions=10.0, config=config)
        assert cost == pytest.approx(0.003)

    def test_mid_liquidity_uses_illiquid_cost(self) -> None:
        config = ValidationHarnessConfig(
            base_tx_cost_pct=0.003,
            illiquid_tx_cost_pct=0.006,
            min_adv_millions=1.0,
            illiquid_adv_threshold_millions=5.0,
        )
        cost = _resolve_tx_cost_pct(adv_millions=2.0, config=config)
        assert cost == pytest.approx(0.006)

    def test_none_adv_uses_illiquid_cost(self) -> None:
        config = ValidationHarnessConfig(base_tx_cost_pct=0.003, illiquid_tx_cost_pct=0.006)
        cost = _resolve_tx_cost_pct(adv_millions=None, config=config)
        assert cost == pytest.approx(0.006)


# ---------------------------------------------------------------------------
# _compute_placebo_distribution
# ---------------------------------------------------------------------------

class TestComputePlaceboDistribution:
    def _make_candidate_map(
        self,
        snapshot_dates: list[date],
        tickers_per_date: list[list[str]],
        returns_by_ticker: dict[str, float],
        benchmark_return: float = 0.05,
    ) -> dict[date, list[CompanySOTPBacktestTrade]]:
        """Build a candidates-by-date map for placebo testing."""
        result: dict[date, list[CompanySOTPBacktestTrade]] = {}
        for snap, tickers in zip(snapshot_dates, tickers_per_date):
            exit_d = snap.replace(year=snap.year + 1)
            result[snap] = [
                _make_trade(
                    ticker=t,
                    snapshot_date=snap,
                    exit_date=exit_d,
                    company_return_pct=returns_by_ticker[t],
                    benchmark_return_pct=benchmark_return,
                )
                for t in tickers
            ]
        return result

    def test_placebo_mean_near_zero_for_random_ranks(self) -> None:
        # Build a pool with 0 expected edge (returns centered around benchmark)
        tickers = [f"T{i}" for i in range(10)]
        returns = {t: 0.05 + (i - 5) * 0.01 for i, t in enumerate(tickers)}  # sym around 0 excess
        snap = date(2022, 1, 1)
        candidate_map = self._make_candidate_map(
            snapshot_dates=[snap],
            tickers_per_date=[tickers],
            returns_by_ticker=returns,
        )
        means = _compute_placebo_distribution(
            candidate_map=candidate_map,
            top_n=3,
            n_iterations=200,
            seed=0,
        )
        assert len(means) == 200
        placebo_mean = sum(means) / len(means)
        # With symmetric returns, permuted mean should center near 0 excess
        assert abs(placebo_mean) < 0.015

    def test_real_edge_exceeds_most_placebos_when_signal_strong(self) -> None:
        # Give the top-ranked names much higher returns
        tickers = [f"T{i}" for i in range(10)]
        # ranks 0-2 (top 3) get +30% excess; rest get -5% excess
        returns = {t: (0.35 if i < 3 else 0.00) for i, t in enumerate(tickers)}
        snap = date(2022, 1, 1)
        candidate_map = self._make_candidate_map(
            snapshot_dates=[snap],
            tickers_per_date=[tickers],
            returns_by_ticker=returns,
            benchmark_return=0.05,
        )
        means = _compute_placebo_distribution(
            candidate_map=candidate_map,
            top_n=3,
            n_iterations=500,
            seed=42,
        )
        real_mean = 0.30  # top 3 get +35% return - 5% benchmark
        pct_rank = sum(m < real_mean for m in means) / len(means)
        assert pct_rank > 0.80  # real signal beats ≥80% of placebos


# ---------------------------------------------------------------------------
# _compute_subgroups
# ---------------------------------------------------------------------------

class TestComputeSubgroups:
    def _make_trades(self) -> list[CompanySOTPBacktestTrade]:
        return [
            _make_trade("A", snapshot_date=date(2021, 6, 1), exit_date=date(2022, 6, 1),
                        company_return_pct=0.40, benchmark_return_pct=0.10),
            _make_trade("B", snapshot_date=date(2021, 9, 1), exit_date=date(2022, 9, 1),
                        company_return_pct=0.20, benchmark_return_pct=0.10),
            _make_trade("C", snapshot_date=date(2022, 6, 1), exit_date=date(2023, 6, 1),
                        company_return_pct=-0.10, benchmark_return_pct=0.05),
            _make_trade("D", snapshot_date=date(2022, 9, 1), exit_date=date(2023, 9, 1),
                        company_return_pct=-0.20, benchmark_return_pct=0.00),
        ]

    def test_time_subgroups_split_by_midpoint(self) -> None:
        trades = self._make_trades()
        result = _compute_subgroups(trades, include_time_subgroups=True)
        names = {s.subgroup_name for s in result}
        assert "first_half" in names
        assert "second_half" in names

    def test_first_half_has_correct_trades(self) -> None:
        trades = self._make_trades()
        result = _compute_subgroups(trades, include_time_subgroups=True)
        first = next(s for s in result if s.subgroup_name == "first_half")
        second = next(s for s in result if s.subgroup_name == "second_half")
        assert first.n_trades + second.n_trades == len(trades)

    def test_first_half_positive_second_half_negative(self) -> None:
        trades = self._make_trades()
        result = _compute_subgroups(trades, include_time_subgroups=True)
        first = next(s for s in result if s.subgroup_name == "first_half")
        second = next(s for s in result if s.subgroup_name == "second_half")
        assert first.mean_excess_return is not None
        assert second.mean_excess_return is not None
        assert first.mean_excess_return > 0
        assert second.mean_excess_return < 0


# ---------------------------------------------------------------------------
# run_validation_harness (integration)
# ---------------------------------------------------------------------------

class TestRunValidationHarness:
    def _build_db(
        self,
        trades: list[CompanySOTPBacktestTrade],
        *,
        adv_millions: float = 5.0,
    ) -> str:
        """Build replay DB with market_prices for all tickers in trades."""
        tmp = tempfile.mktemp(suffix=".sqlite")
        conn = sqlite3.connect(tmp)
        conn.execute(
            """
            CREATE TABLE market_prices (
                ticker TEXT NOT NULL,
                price_date TEXT NOT NULL,
                close_usd REAL,
                adj_close_usd REAL,
                open_usd REAL,
                high_usd REAL,
                low_usd REAL,
                volume INTEGER,
                PRIMARY KEY (ticker, price_date)
            )
            """
        )
        from datetime import timedelta

        seen = set()
        for trade in trades:
            key = (trade.ticker, trade.snapshot_date)
            if key in seen:
                continue
            seen.add(key)
            # ADV = close * volume / 1e6 → to get adv_millions: volume = adv_millions * 1e6 / close
            close = 20.0
            volume = int(adv_millions * 1e6 / close)
            for i in range(25):
                d = trade.snapshot_date - timedelta(days=i)
                conn.execute(
                    "INSERT OR REPLACE INTO market_prices VALUES (?,?,?,?,?,?,?,?)",
                    (trade.ticker, d.isoformat(), close, close, close, close, close, volume),
                )
        conn.commit()
        conn.close()
        return tmp

    def test_all_trades_pass_when_adv_above_threshold(self) -> None:
        trades = [_make_trade("A"), _make_trade("B", snapshot_date=date(2022, 6, 1))]
        db_path = self._build_db(trades, adv_millions=10.0)
        config = ValidationHarnessConfig(min_adv_millions=1.0, n_placebo_iterations=50)
        report = run_validation_harness(
            trades, replay_db_path=db_path, config=config
        )
        assert report.n_input_trades == 2
        assert report.n_liquid_trades == 2
        assert report.n_excluded_low_adv == 0

    def test_low_adv_trades_excluded(self) -> None:
        trades = [_make_trade("A")]
        db_path = self._build_db(trades, adv_millions=0.5)  # below 1M gate
        config = ValidationHarnessConfig(min_adv_millions=1.0, n_placebo_iterations=50)
        report = run_validation_harness(
            trades, replay_db_path=db_path, config=config
        )
        assert report.n_excluded_low_adv == 1
        assert report.n_liquid_trades == 0

    def test_cost_adjusted_return_below_gross_return(self) -> None:
        trades = [
            _make_trade("A", company_return_pct=0.30, benchmark_return_pct=0.10),
        ]
        db_path = self._build_db(trades, adv_millions=5.0)
        config = ValidationHarnessConfig(
            min_adv_millions=1.0,
            base_tx_cost_pct=0.003,
            n_placebo_iterations=20,
        )
        report = run_validation_harness(trades, replay_db_path=db_path, config=config)
        if report.n_liquid_trades > 0:
            assert report.cost_adjusted_stats.mean_excess_return is not None
            assert report.gross_stats.mean_excess_return is not None
            assert (
                report.cost_adjusted_stats.mean_excess_return
                <= report.gross_stats.mean_excess_return
            )

    def test_report_has_placebo_result(self) -> None:
        trades = [_make_trade("A"), _make_trade("B", snapshot_date=date(2022, 6, 1))]
        db_path = self._build_db(trades, adv_millions=5.0)
        config = ValidationHarnessConfig(min_adv_millions=1.0, n_placebo_iterations=20)
        report = run_validation_harness(trades, replay_db_path=db_path, config=config)
        assert report.placebo is not None
        assert report.placebo.n_placebo == 20

    def test_report_has_subgroup_results(self) -> None:
        # Need at least 4 trades spanning two time periods for time subgroups
        trades = [
            _make_trade("A", snapshot_date=date(2021, 3, 1), exit_date=date(2022, 3, 1)),
            _make_trade("B", snapshot_date=date(2021, 9, 1), exit_date=date(2022, 9, 1)),
            _make_trade("C", snapshot_date=date(2022, 3, 1), exit_date=date(2023, 3, 1)),
            _make_trade("D", snapshot_date=date(2022, 9, 1), exit_date=date(2023, 9, 1)),
        ]
        db_path = self._build_db(trades, adv_millions=5.0)
        config = ValidationHarnessConfig(min_adv_millions=1.0, n_placebo_iterations=20)
        report = run_validation_harness(trades, replay_db_path=db_path, config=config)
        names = {s.subgroup_name for s in report.subgroups}
        assert "first_half" in names or "second_half" in names

    def test_validation_grade_insufficient_for_empty(self) -> None:
        config = ValidationHarnessConfig(min_adv_millions=1.0, n_placebo_iterations=10)
        report = run_validation_harness(
            [], replay_db_path=":memory:", config=config
        )
        assert report.validation_grade == "insufficient"

    def test_validation_grade_strong_for_significant_result(self) -> None:
        # Generate 30 trades with consistent +20% excess to create significant result
        from datetime import timedelta

        trades = []
        base = date(2021, 1, 1)
        for i in range(30):
            snap = base + timedelta(days=i * 14)
            trades.append(
                _make_trade(
                    f"T{i}",
                    snapshot_date=snap,
                    exit_date=snap + timedelta(days=365),
                    company_return_pct=0.25,
                    benchmark_return_pct=0.05,
                )
            )
        db_path = self._build_db(trades, adv_millions=5.0)
        config = ValidationHarnessConfig(
            min_adv_millions=1.0,
            n_placebo_iterations=100,
        )
        report = run_validation_harness(trades, replay_db_path=db_path, config=config)
        assert report.n_liquid_trades == 30
        assert report.validation_grade in ("strong", "moderate")
