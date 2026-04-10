from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml

from bve.ops.replay_watchlist_builder import ReplayWatchlistBuilder


def _write_yaml(path: Path, payload: object) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_config(path: Path, *, ticker: str, stage: str) -> None:
    _write_yaml(
        path,
        {
            "asset": {
                "id": f"asset-{ticker.lower()}",
                "name": ticker,
                "indication": f"{ticker} indication",
                "therapeutic_area": "oncology",
                "stage": stage,
                "modality": "small_molecule",
                "discount_rate": 0.11,
            },
            "company": {
                "id": f"co-{ticker.lower()}",
                "name": ticker,
                "ticker": ticker,
                "cash_millions": 100.0,
                "shares_outstanding_millions": 10.0,
                "burn_rate_millions_per_quarter": 10.0,
                "current_price": 10.0,
            },
            "trials": [
                {
                    "phase": stage,
                    "success_probability": 0.5,
                    "duration_years": 2.0,
                    "cost_millions": 50.0,
                    "endpoint_type": "surrogate_validated",
                }
            ],
            "market_model": {
                "total_addressable_market_millions": 2_000.0,
                "peak_penetration": 0.2,
                "years_to_peak": 5,
                "patent_life_years": 10,
                "cogs_rate": 0.15,
                "sgna_rate_launch": 0.40,
                "sgna_rate_mature": 0.20,
            },
        },
    )


def _write_replay_db(path: Path, prices: dict[str, float]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE historical_prices (ticker TEXT NOT NULL, price_date TEXT NOT NULL, close_usd REAL NOT NULL, PRIMARY KEY (ticker, price_date))"
        )
        for ticker, price in prices.items():
            conn.execute(
                "INSERT INTO historical_prices (ticker, price_date, close_usd) VALUES (?, ?, ?)",
                (ticker, "2025-03-31", price),
            )
        conn.commit()
    finally:
        conn.close()


def _write_knowledge_db(path: Path, market_caps: dict[str, float]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE market_prices (ticker TEXT NOT NULL, price_date TEXT NOT NULL, close_usd REAL, adj_close_usd REAL, volume INTEGER, market_cap_millions REAL, is_adjusted INTEGER NOT NULL DEFAULT 1, source TEXT NOT NULL DEFAULT 'yfinance', ingested_at TEXT NOT NULL, PRIMARY KEY (ticker, price_date))"
        )
        for ticker, market_cap in market_caps.items():
            conn.execute(
                "INSERT INTO market_prices (ticker, price_date, close_usd, market_cap_millions, ingested_at) VALUES (?, ?, ?, ?, ?)",
                (ticker, "2025-03-31", 10.0, market_cap, "2025-03-31T00:00:00Z"),
            )
        conn.commit()
    finally:
        conn.close()


def test_builder_reuses_existing_phase2_and_generates_missing_entries(tmp_path: Path) -> None:
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    aaa_config = configs_dir / "aaa.yaml"
    bbb_config = configs_dir / "bbb.yaml"
    _write_config(aaa_config, ticker="AAA", stage="phase_3")
    _write_config(bbb_config, ticker="BBB", stage="phase_1")

    watchlist_path = tmp_path / "watchlist.yaml"
    _write_yaml(
        watchlist_path,
        {
            "watchlist": [
                {
                    "company_id": "co-aaa",
                    "asset_id": "asset-aaa",
                    "drug_name": "AAA",
                    "indication": "AAA indication",
                    "ticker": "AAA",
                    "valuation_config": str(aaa_config),
                },
                {
                    "company_id": "co-bbb",
                    "asset_id": "asset-bbb",
                    "drug_name": "BBB",
                    "indication": "BBB indication",
                    "ticker": "BBB",
                    "valuation_config": str(bbb_config),
                },
            ]
        },
    )

    expanded_universe_path = tmp_path / "expanded.yaml"
    _write_yaml(
        expanded_universe_path,
        {
            "universe": [
                {
                    "ticker": "AAA",
                    "asset_id": "asset-aaa",
                    "company_name": "AAA Corp",
                    "drug_name": "AAA",
                    "indication": "AAA indication",
                    "therapeutic_area": "oncology",
                    "stage": "phase_3",
                },
                {
                    "ticker": "BBB",
                    "asset_id": "asset-bbb",
                    "company_name": "BBB Corp",
                    "drug_name": "BBB",
                    "indication": "BBB indication",
                    "therapeutic_area": "oncology",
                    "stage": "phase_1",
                },
                {
                    "ticker": "CCC",
                    "asset_id": "asset-ccc",
                    "company_name": "CCC Corp",
                    "drug_name": "CCC",
                    "indication": "CCC indication",
                    "therapeutic_area": "immunology",
                    "stage": "phase_2",
                },
                {
                    "ticker": "DDD",
                    "asset_id": "asset-ddd",
                    "company_name": "DDD Corp",
                    "drug_name": "DDD",
                    "indication": "DDD indication",
                    "therapeutic_area": "cns",
                    "stage": "approved",
                },
            ]
        },
    )

    universe_params_path = tmp_path / "params.yaml"
    _write_yaml(
        universe_params_path,
        {
            "universe": {
                "CCC": {
                    "program_label": "CCC - CCC indication",
                    "ta": "immunology",
                    "phase": "phase_2",
                    "modality": "biologic",
                    "peak_sales_millions": 1800.0,
                    "years_to_approval": 4.0,
                    "patent_life_years": 11,
                    "single_asset": True,
                    "peak_penetration": 0.2,
                }
            }
        },
    )

    replay_db = tmp_path / "replay.sqlite"
    _write_replay_db(replay_db, {"CCC": 20.0, "DDD": 40.0})

    knowledge_db = tmp_path / "knowledge.sqlite"
    _write_knowledge_db(knowledge_db, {"AAA": 2_000.0})

    builder = ReplayWatchlistBuilder(
        base_watchlist_path=watchlist_path,
        expanded_universe_path=expanded_universe_path,
        universe_params_path=universe_params_path,
        replay_db_path=replay_db,
        knowledge_db_path=knowledge_db,
        generated_config_dir=tmp_path / "generated",
        output_watchlist_path=tmp_path / "watchlist_out.yaml",
    )

    result = builder.build()

    assert result.reused_count == 1
    assert result.generated_count == 2
    assert result.total_count == 3
    assert [entry["ticker"] for entry in result.watchlist] == ["AAA", "CCC", "DDD"]

    ccc_config = result.generated_configs["CCC"]
    assert ccc_config["asset"]["stage"] == "phase_2"
    assert ccc_config["asset"]["modality"] == "biologic"
    assert ccc_config["market_model"]["total_addressable_market_millions"] == 9000.0

    ddd_config = result.generated_configs["DDD"]
    assert ddd_config["asset"]["stage"] == "nda_bla"
    assert ddd_config["trials"][0]["phase"] == "nda_bla"


def test_builder_write_outputs_watchlist_and_generated_configs(tmp_path: Path) -> None:
    config = tmp_path / "aaa.yaml"
    _write_config(config, ticker="AAA", stage="phase_3")
    watchlist_path = tmp_path / "watchlist.yaml"
    _write_yaml(
        watchlist_path,
        {
            "watchlist": [
                {
                    "company_id": "co-aaa",
                    "asset_id": "asset-aaa",
                    "drug_name": "AAA",
                    "indication": "AAA indication",
                    "ticker": "AAA",
                    "valuation_config": str(config),
                }
            ]
        },
    )
    expanded_universe_path = tmp_path / "expanded.yaml"
    _write_yaml(
        expanded_universe_path,
        {
            "universe": [
                {
                    "ticker": "AAA",
                    "asset_id": "asset-aaa",
                    "company_name": "AAA Corp",
                    "drug_name": "AAA",
                    "indication": "AAA indication",
                    "therapeutic_area": "oncology",
                    "stage": "phase_3",
                },
                {
                    "ticker": "CCC",
                    "asset_id": "asset-ccc",
                    "company_name": "CCC Corp",
                    "drug_name": "CCC",
                    "indication": "CCC indication",
                    "therapeutic_area": "oncology",
                    "stage": "phase_3",
                },
            ]
        },
    )
    universe_params_path = tmp_path / "params.yaml"
    _write_yaml(universe_params_path, {"universe": {}})
    replay_db = tmp_path / "replay.sqlite"
    _write_replay_db(replay_db, {"CCC": 25.0})
    knowledge_db = tmp_path / "knowledge.sqlite"
    _write_knowledge_db(knowledge_db, {"AAA": 2_000.0})

    builder = ReplayWatchlistBuilder(
        base_watchlist_path=watchlist_path,
        expanded_universe_path=expanded_universe_path,
        universe_params_path=universe_params_path,
        replay_db_path=replay_db,
        knowledge_db_path=knowledge_db,
        generated_config_dir=tmp_path / "generated",
        output_watchlist_path=tmp_path / "watchlist_out.yaml",
    )
    result = builder.build()
    watchlist_out, written_configs = builder.write(result)

    assert watchlist_out.exists()
    assert len(written_configs) == 1
    assert written_configs[0].exists()
    written_watchlist = yaml.safe_load(watchlist_out.read_text(encoding="utf-8"))
    assert [entry["ticker"] for entry in written_watchlist["watchlist"]] == ["AAA", "CCC"]


def test_expanded_replay_watchlist_artifact_has_50_plus_assets() -> None:
    watchlist_path = (
        Path(__file__).resolve().parents[2]
        / "examples"
        / "configs"
        / "watchlists"
        / "watchlist_replay_expanded_phase2.yaml"
    )
    assert watchlist_path.exists()

    raw = yaml.safe_load(watchlist_path.read_text(encoding="utf-8"))
    watchlist = raw["watchlist"]
    assert len(watchlist) >= 50
    tickers = [entry["ticker"] for entry in watchlist]
    assert len(tickers) == len(set(tickers))

    for entry in watchlist:
        cfg_path = Path(entry["valuation_config"])
        if not cfg_path.is_absolute():
            cfg_path = (Path(__file__).resolve().parents[2] / cfg_path).resolve()
        assert cfg_path.exists(), f"Missing config: {cfg_path}"
        payload = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        stage = payload["asset"]["stage"]
        assert stage in {"phase_2", "phase_3", "nda_bla"}
