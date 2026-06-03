from __future__ import annotations

import csv
import sqlite3
from datetime import date
from pathlib import Path

import yaml

from bve.analysis.historical_implied_pos_validation import (
    HistoricalImpliedPoSValidator,
    render_historical_implied_pos_report,
)
from bve.analysis.implied_pos import ImpliedPoSResult
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.historical_replay import ReplayStore


def _insert_market_price_rows(
    db_path: Path,
    *,
    ticker: str,
    rows: list[tuple[date, float, int, float]],
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS market_prices ("
            "ticker TEXT NOT NULL, "
            "price_date TEXT NOT NULL, "
            "close_usd REAL, "
            "adj_close_usd REAL, "
            "volume INTEGER, "
            "market_cap_millions REAL, "
            "is_adjusted INTEGER NOT NULL DEFAULT 1, "
            "source TEXT NOT NULL DEFAULT 'yfinance', "
            "ingested_at TEXT NOT NULL, "
            "PRIMARY KEY (ticker, price_date)"
            ")"
        )
        conn.executemany(
            "INSERT OR REPLACE INTO market_prices "
            "(ticker, price_date, close_usd, volume, market_cap_millions, ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (ticker, d.isoformat(), close, volume, market_cap, f"{d.isoformat()}T00:00:00Z")
                for d, close, volume, market_cap in rows
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _write_config(
    path: Path,
    *,
    ticker: str,
    asset_id: str,
    stage: str = "phase_2",
    shares: float = 10.0,
    cash: float = 20.0,
) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "asset": {
                    "id": asset_id,
                    "name": asset_id,
                    "indication": "test indication",
                    "therapeutic_area": "oncology",
                    "stage": stage,
                    "modality": "small_molecule",
                    "discount_rate": 0.10,
                },
                "company": {
                    "id": f"co-{ticker.lower()}",
                    "name": ticker,
                    "ticker": ticker,
                    "cash_millions": cash,
                    "debt_millions": 0.0,
                    "shares_outstanding_millions": shares,
                    "burn_rate_millions_per_quarter": 10.0,
                    "current_price": 10.0,
                },
                "trials": [
                    {
                        "phase": "phase_2",
                        "success_probability": 0.4,
                        "duration_years": 2.0,
                        "cost_millions": 20.0,
                        "endpoint_type": "surrogate_validated",
                    }
                ],
                "market_model": {
                    "addressable_patients_annual": 10000,
                    "net_price_per_patient_usd": 20000,
                    "peak_penetration": 0.1,
                    "years_to_peak": 5,
                    "patent_life_years": 10,
                    "cogs_rate": 0.15,
                    "sgna_rate_launch": 0.40,
                    "sgna_rate_mature": 0.20,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_watchlist(path: Path, config_paths: list[Path]) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "watchlist": [
                    {
                        "company_id": f"co-{cfg.stem.lower()}",
                        "asset_id": f"asset-{cfg.stem.lower()}",
                        "drug_name": cfg.stem,
                        "indication": "test indication",
                        "ticker": cfg.stem.upper(),
                        "valuation_config": str(cfg),
                    }
                    for cfg in config_paths
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


class _FakeSolver:
    def __init__(self, spreads: dict[str, float]) -> None:
        self.spreads = spreads

    def solve(self, config_path: str, current_ev_millions: float) -> ImpliedPoSResult:
        ticker = Path(config_path).stem.upper()
        model_pos = 0.60
        spread = self.spreads[ticker]
        implied = model_pos - spread
        return ImpliedPoSResult(
            asset_id=f"asset-{ticker.lower()}",
            ticker=ticker,
            current_ev_millions=current_ev_millions,
            implied_pos=implied,
            model_pos=model_pos,
            pos_spread=spread,
            model_rnpv_millions=current_ev_millions * 1.25,
            implied_rnpv_millions=current_ev_millions,
            acquisition_discount=1.25,
            market_exceeds_model=False,
            iterations=3,
        )


def test_validator_selects_highest_spread_name_per_snapshot(tmp_path: Path) -> None:
    aaa = tmp_path / "aaa.yaml"
    bbb = tmp_path / "bbb.yaml"
    _write_config(aaa, ticker="AAA", asset_id="asset-aaa")
    _write_config(bbb, ticker="BBB", asset_id="asset-bbb")
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [aaa, bbb])

    replay_db = tmp_path / "replay.sqlite"
    store = ReplayStore(str(replay_db))
    try:
        store.insert_prices(
            "AAA",
            [
                (date(2025, 1, 1), 10.0),
                (date(2025, 1, 31), 14.0),
            ],
        )
        store.insert_prices(
            "BBB",
            [
                (date(2025, 1, 1), 10.0),
                (date(2025, 1, 31), 9.0),
            ],
        )
        store.insert_prices(
            "XBI",
            [
                (date(2025, 1, 1), 100.0),
                (date(2025, 1, 31), 102.0),
            ],
        )
    finally:
        store.close()

    validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.30, "BBB": 0.10}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        cadence="monthly",
        top_n=1,
        require_phase2_plus=True,
        bootstrap_iterations=200,
    )
    report = validator.validate(
        str(watchlist),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    assert report.n_observations == 2
    assert report.n_selected_trades == 1
    assert report.selected_trades[0].ticker == "AAA"
    assert report.clusters.n_assets == 1


def test_validator_applies_phase_and_market_cap_filters(tmp_path: Path) -> None:
    phase1 = tmp_path / "phase1.yaml"
    phase2 = tmp_path / "phase2.yaml"
    _write_config(phase1, ticker="P1A", asset_id="asset-p1a", stage="phase_1")
    _write_config(phase2, ticker="P2A", asset_id="asset-p2a", stage="phase_2", shares=5.0)
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [phase1, phase2])

    replay_db = tmp_path / "replay.sqlite"
    store = ReplayStore(str(replay_db))
    try:
        store.insert_prices(
            "P1A",
            [(date(2025, 1, 1), 30.0), (date(2025, 1, 31), 31.0)],
        )
        store.insert_prices(
            "P2A",
            [(date(2025, 1, 1), 10.0), (date(2025, 1, 31), 11.0)],
        )
        store.insert_prices(
            "XBI",
            [(date(2025, 1, 1), 100.0), (date(2025, 1, 31), 100.0)],
        )
    finally:
        store.close()

    validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"P1A": 0.20, "P2A": 0.20}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=1,
        require_phase2_plus=True,
        min_market_cap_millions=60.0,
    )
    report = validator.validate(
        str(watchlist),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    assert report.n_observations == 0
    assert report.n_selected_trades == 0


def test_validator_skips_assets_without_exit_price(tmp_path: Path) -> None:
    aaa = tmp_path / "aaa.yaml"
    bbb = tmp_path / "bbb.yaml"
    _write_config(aaa, ticker="AAA", asset_id="asset-aaa")
    _write_config(bbb, ticker="BBB", asset_id="asset-bbb")
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [aaa, bbb])

    replay_db = tmp_path / "replay.sqlite"
    store = ReplayStore(str(replay_db))
    try:
        store.insert_prices("AAA", [(date(2025, 1, 1), 10.0), (date(2025, 1, 31), 11.0)])
        store.insert_prices("BBB", [(date(2025, 1, 1), 10.0)])
        store.insert_prices("XBI", [(date(2025, 1, 1), 100.0), (date(2025, 1, 31), 100.0)])
    finally:
        store.close()

    validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.15, "BBB": 0.05}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=2,
        bootstrap_iterations=200,
    )
    report = validator.validate(
        str(watchlist),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    assert report.n_observations == 1
    assert report.observations[0].ticker == "AAA"


def test_validator_writes_observation_csv(tmp_path: Path) -> None:
    aaa = tmp_path / "aaa.yaml"
    _write_config(aaa, ticker="AAA", asset_id="asset-aaa")
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [aaa])

    replay_db = tmp_path / "replay.sqlite"
    store = ReplayStore(str(replay_db))
    try:
        store.insert_prices("AAA", [(date(2025, 1, 1), 10.0), (date(2025, 1, 31), 12.0)])
        store.insert_prices("XBI", [(date(2025, 1, 1), 100.0), (date(2025, 1, 31), 101.0)])
    finally:
        store.close()

    validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.25}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=1,
        bootstrap_iterations=200,
    )
    report = validator.validate(
        str(watchlist),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    assert report.observations_csv_path.exists()
    with report.observations_csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAA"
    assert rows[0]["selected"] == "True"


def test_validator_output_suffix_includes_stage_scope(tmp_path: Path) -> None:
    aaa = tmp_path / "aaa.yaml"
    _write_config(aaa, ticker="AAA", asset_id="asset-aaa")
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [aaa])

    replay_db = tmp_path / "replay.sqlite"
    store = ReplayStore(str(replay_db))
    try:
        store.insert_prices("AAA", [(date(2025, 1, 1), 10.0), (date(2025, 1, 31), 12.0)])
        store.insert_prices("XBI", [(date(2025, 1, 1), 100.0), (date(2025, 1, 31), 101.0)])
    finally:
        store.close()

    phase2_validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.25}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=1,
        require_phase2_plus=True,
        bootstrap_iterations=200,
    )
    allstage_validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.25}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=1,
        require_phase2_plus=False,
        bootstrap_iterations=200,
    )

    phase2_report = phase2_validator.validate(
        str(watchlist),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )
    allstage_report = allstage_validator.validate(
        str(watchlist),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    assert "phase2plus" in phase2_report.observations_csv_path.name
    assert "allstages" in allstage_report.observations_csv_path.name
    assert phase2_report.observations_csv_path != allstage_report.observations_csv_path


def test_validator_applies_historical_adv_filter_when_market_prices_exist(tmp_path: Path) -> None:
    aaa = tmp_path / "aaa.yaml"
    bbb = tmp_path / "bbb.yaml"
    _write_config(aaa, ticker="AAA", asset_id="asset-aaa")
    _write_config(bbb, ticker="BBB", asset_id="asset-bbb")
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [aaa, bbb])

    replay_db = tmp_path / "replay.sqlite"
    store = ReplayStore(str(replay_db))
    try:
        store.insert_prices("AAA", [(date(2025, 1, 20), 10.0), (date(2025, 2, 19), 12.0)])
        store.insert_prices("BBB", [(date(2025, 1, 20), 10.0), (date(2025, 2, 19), 11.0)])
        store.insert_prices("XBI", [(date(2025, 1, 20), 100.0), (date(2025, 2, 19), 101.0)])
    finally:
        store.close()

    adv_dates = [date(2025, 1, day) for day in range(1, 21)]
    _insert_market_price_rows(
        replay_db,
        ticker="AAA",
        rows=[(d, 10.0, 300_000, 100.0) for d in adv_dates],  # $3.0M ADV
    )
    _insert_market_price_rows(
        replay_db,
        ticker="BBB",
        rows=[(d, 10.0, 50_000, 100.0) for d in adv_dates],  # $0.5M ADV
    )

    validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.20, "BBB": 0.10}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=2,
        min_adv_millions=2.0,
        bootstrap_iterations=200,
    )
    report = validator.validate(
        str(watchlist),
        start_date=date(2025, 1, 20),
        end_date=date(2025, 2, 19),
    )

    assert report.n_observations == 1
    assert report.n_adv_covered_observations == 1
    assert report.observations[0].ticker == "AAA"
    assert report.observations[0].daily_dollar_volume_millions == 3.0
    assert "adv2" in report.observations_csv_path.name


def test_validator_returns_no_observations_when_adv_filter_active_but_no_adv_data(
    tmp_path: Path,
) -> None:
    aaa = tmp_path / "aaa.yaml"
    _write_config(aaa, ticker="AAA", asset_id="asset-aaa")
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [aaa])

    replay_db = tmp_path / "replay.sqlite"
    store = ReplayStore(str(replay_db))
    try:
        store.insert_prices("AAA", [(date(2025, 1, 1), 10.0), (date(2025, 1, 31), 11.0)])
        store.insert_prices("XBI", [(date(2025, 1, 1), 100.0), (date(2025, 1, 31), 100.0)])
    finally:
        store.close()

    validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.15}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=1,
        min_adv_millions=2.0,
        bootstrap_iterations=200,
    )
    report = validator.validate(
        str(watchlist),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    assert report.n_observations == 0
    assert report.n_adv_covered_observations == 0


def test_validator_can_persist_historical_screen_snapshots(tmp_path: Path) -> None:
    aaa = tmp_path / "aaa.yaml"
    bbb = tmp_path / "bbb.yaml"
    _write_config(aaa, ticker="AAA", asset_id="asset-aaa")
    _write_config(bbb, ticker="BBB", asset_id="asset-bbb")
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [aaa, bbb])

    replay_db = tmp_path / "replay.sqlite"
    knowledge_db = tmp_path / "knowledge.db"
    store = ReplayStore(str(replay_db))
    try:
        store.insert_prices("AAA", [(date(2025, 1, 1), 10.0), (date(2025, 1, 31), 12.0)])
        store.insert_prices("BBB", [(date(2025, 1, 1), 10.0), (date(2025, 1, 31), 11.0)])
        store.insert_prices("XBI", [(date(2025, 1, 1), 100.0), (date(2025, 1, 31), 101.0)])
    finally:
        store.close()

    validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.25, "BBB": 0.10}),
        replay_db_path=replay_db,
        knowledge_db_path=knowledge_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=1,
        persist_screen_snapshots=True,
        shuffle_iterations=20,
        bootstrap_iterations=200,
    )
    report = validator.validate(
        str(watchlist),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    assert report.persisted_snapshot_rows == 2
    assert report.knowledge_db_path == str(knowledge_db)

    knowledge = KnowledgeStore(knowledge_db)
    try:
        rows = knowledge.get_screen_snapshots(snapshot_date=date(2025, 1, 1), limit=10)
    finally:
        knowledge.close()

    assert len(rows) == 2
    assert rows[0]["ticker"] == "AAA"
    assert rows[0]["spread_pp"] == 25.0


def test_validator_reports_placebo_leave_one_out_and_stage_robustness(tmp_path: Path) -> None:
    aaa = tmp_path / "aaa.yaml"
    bbb = tmp_path / "bbb.yaml"
    ccc = tmp_path / "ccc.yaml"
    _write_config(aaa, ticker="AAA", asset_id="asset-aaa", stage="phase_3")
    _write_config(bbb, ticker="BBB", asset_id="asset-bbb", stage="phase_2")
    _write_config(ccc, ticker="CCC", asset_id="asset-ccc", stage="phase_2")
    watchlist = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist, [aaa, bbb, ccc])

    replay_db = tmp_path / "replay.sqlite"
    store = ReplayStore(str(replay_db))
    try:
        store.insert_prices("AAA", [(date(2025, 1, 1), 10.0), (date(2025, 1, 31), 15.0)])
        store.insert_prices("BBB", [(date(2025, 1, 1), 10.0), (date(2025, 1, 31), 12.0)])
        store.insert_prices("CCC", [(date(2025, 1, 1), 10.0), (date(2025, 1, 31), 8.0)])
        store.insert_prices("XBI", [(date(2025, 1, 1), 100.0), (date(2025, 1, 31), 101.0)])
    finally:
        store.close()

    validator = HistoricalImpliedPoSValidator(
        solver=_FakeSolver({"AAA": 0.30, "BBB": 0.20, "CCC": -0.10}),
        replay_db_path=replay_db,
        output_dir=tmp_path,
        hold_days=30,
        top_n=2,
        shuffle_iterations=100,
        bootstrap_iterations=200,
    )
    report = validator.validate(
        str(watchlist),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    assert report.placebo.reverse_signal_n_trades == 2
    assert report.placebo.reverse_signal_mean_excess_return_pct is not None
    assert report.placebo.shuffled_mean_excess_return_pct is not None
    assert report.placebo.shuffled_beats_actual_p_value is not None
    assert 0.0 <= report.placebo.shuffled_beats_actual_p_value <= 1.0
    assert report.leave_one_out.n_clusters_evaluated == 2
    assert report.leave_one_out.worst_case_mean_excess_return_pct is not None
    assert report.leave_one_out.best_case_mean_excess_return_pct is not None
    assert report.leave_one_out.min_remaining_clusters == 1
    assert [row.stage for row in report.stage_robustness] == ["phase_3", "phase_2"]

    rendered = render_historical_implied_pos_report(report)
    assert "Reverse placebo:" in rendered
    assert "Shuffle >= actual p:" in rendered
    assert "Leave-one-out worst:" in rendered
