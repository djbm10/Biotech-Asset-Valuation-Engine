from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path

from bve.analysis.coverage_audit import CoverageAuditor, render_coverage_audit_report
from bve.intelligence.thesis_tracker import ClaimType
from bve.ops.historical_replay import ReplayStore, load_replay_universe
from bve.ops.weekly_runner import UNIVERSE


def _write_universe_file(path: Path, payload: list[dict]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _price_fetcher(price_map: dict[str, dict[date, float]]):
    def _fetch(ticker: str, _start: date, _end: date) -> dict[date, float]:
        return price_map.get(ticker, {})

    return _fetch


def test_universe_file_loads_correctly_with_all_fields(tmp_path: Path) -> None:
    universe_path = _write_universe_file(
        tmp_path / "universe.json",
        [{
            "ticker": "alny",
            "company_id": "alny-auto",
            "asset_id": "a-alny",
            "ranking_score": 0.72,
            "opportunity_score": 0.65,
            "claim_type": "efficacy",
            "claim_assertion": "vutrisiran will show superiority in HELIOS-B",
            "conviction": 0.7,
            "catalyst": "HELIOS-B Phase 3 readout",
        }],
    )

    universe = load_replay_universe(str(universe_path))

    assert len(universe) == 1
    assert universe[0]["ticker"] == "ALNY"
    assert universe[0]["company_id"] == "alny-auto"
    assert universe[0]["asset_id"] == "a-alny"
    assert universe[0]["ranking_score"] == 0.72
    assert universe[0]["opportunity_score"] == 0.65
    assert universe[0]["claim_type"] == ClaimType.ENDPOINT_MET
    assert universe[0]["claim_assertion"] == "vutrisiran will show superiority in HELIOS-B"
    assert universe[0]["conviction"] == 0.7
    assert universe[0]["catalyst"] == "HELIOS-B Phase 3 readout"


def test_universe_file_loads_with_minimal_fields(tmp_path: Path) -> None:
    universe_path = _write_universe_file(
        tmp_path / "universe_minimal.json",
        [{
            "ticker": "vkxt",
            "asset_id": "a-vktx",
        }],
    )

    universe = load_replay_universe(str(universe_path))

    assert len(universe) == 1
    assert universe[0]["ticker"] == "VKXT"
    assert universe[0]["company_id"] == "vkxt-auto"
    assert universe[0]["ranking_score"] == 0.5
    assert universe[0]["opportunity_score"] == 0.5
    assert universe[0]["conviction"] == 0.5
    assert universe[0]["claim_type"] == ClaimType.ENDPOINT_MET
    assert universe[0]["claim_assertion"] == ""
    assert universe[0]["catalyst"] == ""


def test_fallback_to_weekly_runner_universe_works() -> None:
    universe = load_replay_universe(None)

    assert len(universe) == len(UNIVERSE)
    assert universe[0]["ticker"] == UNIVERSE[0]["ticker"]
    assert universe[0]["asset_id"] == UNIVERSE[0]["asset_id"]
    assert isinstance(universe[0]["claim_type"], ClaimType)


def test_coverage_audit_handles_missing_tickers_gracefully(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    ReplayStore(str(db_path)).close()
    universe_path = _write_universe_file(
        tmp_path / "missing.json",
        [{
            "ticker": "MISS",
            "asset_id": "a-miss",
        }],
    )
    auditor = CoverageAuditor(
        replay_db_path=str(db_path),
        output_dir=tmp_path / "analysis",
        price_fetcher=_price_fetcher({}),
    )

    report = auditor.audit(
        universe_path,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )
    rendered = render_coverage_audit_report(report)

    assert len(report.rows) == 1
    assert report.rows[0].price_trading_days == 0
    assert report.rows[0].n_events == 0
    assert report.needing_price_backfill_count == 1
    assert report.needing_event_seeding_count == 1
    assert "(no data)" in rendered


def test_coverage_audit_csv_output_correct(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    store = ReplayStore(str(db_path))
    store.insert_prices("ALNY", [
        (date(2025, 1, 2), 100.0),
        (date(2025, 1, 6), 101.0),
        (date(2025, 1, 7), 102.0),
        (date(2025, 1, 8), 103.0),
        (date(2025, 1, 9), 104.0),
        (date(2025, 1, 10), 105.0),
        (date(2025, 1, 13), 106.0),
        (date(2025, 1, 14), 107.0),
        (date(2025, 1, 15), 108.0),
    ])
    store.insert_event(
        asset_id="a-alny",
        ticker="ALNY",
        event_type="readout",
        announced_at=date(2025, 1, 8),
        effective_date=date(2025, 1, 8),
        outcome_label="positive",
        headline="ALNY readout",
    )
    store._conn.execute(
        "INSERT INTO catalyst_events "
        "(event_id, asset_id, ticker, event_type, event_date, signal_strength, snapshot_date) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), "a-alny", "ALNY", "readout", "2025-01-08", 0.8, "2025-01-08"),
    )
    store._conn.execute(
        "INSERT INTO enrollment_snapshots "
        "(snapshot_id, asset_id, snapshot_date, site_stalling, velocity_low, slippage_alert) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), "a-alny", "2025-01-09", 0, 0, 0),
    )
    store._conn.execute(
        "INSERT INTO structured_signals "
        "(signal_id, asset_id, signal_date, signal_type, z_score, phase_prior_pos, phase_posterior_pos) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), "a-alny", "2025-01-10", "phase_correlation", 1.2, 0.3, 0.5),
    )
    store._conn.execute(
        "INSERT INTO capital_snapshots "
        "(snapshot_id, asset_id, snapshot_date, cash_runway_quarters, capital_risk_level) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), "a-alny", "2025-01-14", 6.0, "low"),
    )
    store._conn.commit()
    store.close()

    universe_path = _write_universe_file(
        tmp_path / "alny.json",
        [{
            "ticker": "ALNY",
            "asset_id": "a-alny",
        }],
    )
    auditor = CoverageAuditor(
        replay_db_path=str(db_path),
        output_dir=tmp_path / "analysis",
        price_fetcher=_price_fetcher({"ALNY": {}}),
    )

    report = auditor.audit(
        universe_path,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 15),
    )

    assert report.csv_path.exists()
    assert report.full_price_coverage_count == 1
    assert report.event_coverage_count == 1
    assert report.ready_for_replay_count == 1
    header = report.csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert header == (
        "ticker,asset_id,price_first_date,price_last_date,price_trading_days,"
        "price_gaps_gt_5,yfinance_first_date,yfinance_last_date,yfinance_trading_days,"
        "replay_price_full_coverage,yfinance_price_full_coverage,n_events,"
        "first_event_date,last_event_date,event_types,catalyst_rows,enrollment_rows,"
        "signal_rows,capital_rows"
    )
