from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from bve.analysis.implied_pos_batch import ScreenRow
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.company_sotp_backfiller import CompanySOTPBackfiller
from bve.ops.historical_replay import ReplayStore


def _write_asset_config(
    path: Path,
    *,
    asset_id: str,
    asset_name: str,
    ticker: str,
) -> Path:
    payload = {
        "asset": {
            "id": asset_id,
            "name": asset_name,
            "indication": f"{asset_name} indication",
            "therapeutic_area": "oncology",
            "stage": "phase_2",
            "modality": "small_molecule",
            "discount_rate": 0.1,
        },
        "company": {
            "id": "co-test",
            "name": "Test Company",
            "ticker": ticker,
            "cash_millions": 40.0,
            "debt_millions": 0.0,
            "shares_outstanding_millions": 50.0,
            "burn_rate_millions_per_quarter": 5.0,
            "current_price": 10.0,
        },
        "trials": [
            {
                "phase": "phase_2",
                "success_probability": 0.55,
                "duration_years": 2.0,
                "cost_millions": 20.0,
                "endpoint_type": "surrogate_validated",
            },
            {
                "phase": "phase_3",
                "success_probability": 0.65,
                "duration_years": 3.0,
                "cost_millions": 60.0,
                "endpoint_type": "surrogate_validated",
            },
            {
                "phase": "nda_bla",
                "success_probability": 0.85,
                "duration_years": 1.0,
                "cost_millions": 10.0,
                "endpoint_type": "surrogate_validated",
            },
        ],
        "market_model": {
            "total_addressable_market_millions": 2000.0,
            "peak_penetration": 0.15,
            "years_to_peak": 4,
            "patent_life_years": 10,
            "cogs_rate": 0.15,
            "sgna_rate_launch": 0.4,
            "sgna_rate_mature": 0.2,
        },
        "_meta": {"config_quality": "curated"},
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _write_watchlist(path: Path, entries: list[dict]) -> Path:
    path.write_text(yaml.safe_dump({"watchlist": entries}, sort_keys=False), encoding="utf-8")
    return path


def _screen_row(snapshot_date: date) -> ScreenRow:
    return ScreenRow(
        ticker="TEST",
        asset_id="asset-1",
        program_label="Asset One",
        stage="phase_2",
        ta="oncology",
        model_pos=0.3,
        implied_pos=0.2,
        spread_pp=10.0,
        rnpv_millions=120.0,
        ev_millions=80.0,
        acquisition_discount_pct=50.0,
        next_catalyst="readout",
        catalyst_date=None,
        days_to_catalyst=None,
        single_asset=True,
        approximation_warning=None,
        data_date=snapshot_date,
        config_quality="curated",
    )


def test_company_sotp_backfiller_persists_multiple_snapshot_dates(tmp_path: Path) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            },
            {
                "company_id": "co-other",
                "asset_id": "asset-2",
                "ticker": "MISS",
                "valuation_config": str(cfg),
            }
        ],
    )
    knowledge_path = tmp_path / "knowledge.db"
    replay_path = tmp_path / "replay.sqlite"

    store = KnowledgeStore(knowledge_path)
    try:
        store.write_screen_snapshots([_screen_row(date(2024, 2, 1))], snapshot_date=date(2024, 2, 1))
        store.write_screen_snapshots([_screen_row(date(2024, 3, 1))], snapshot_date=date(2024, 3, 1))
    finally:
        store.close()

    replay = ReplayStore(str(replay_path))
    try:
        replay.insert_prices("TEST", [(date(2024, 2, 1), 9.0), (date(2024, 3, 1), 10.0)])
        replay.upsert_balance_sheet_snapshot(
            ticker="TEST",
            snapshot_date=date(2024, 1, 15),
            period_end_date=date(2023, 12, 31),
            form_type="10-K",
            cash_millions=60.0,
            debt_millions=5.0,
            shares_outstanding_millions=50.0,
            burn_rate_millions_per_quarter=6.0,
            source_type="sec_edgar_company_facts",
            source_ref="0000000000:10-K:2024-01-15",
        )
    finally:
        replay.close()

    summary = CompanySOTPBackfiller(
        knowledge_db_path=knowledge_path,
        replay_db_path=replay_path,
        output_dir=tmp_path / "analysis",
        reporter=None,
    ).backfill_watchlist(watchlist)

    assert summary.n_snapshot_dates == 2
    assert summary.snapshot_start == date(2024, 2, 1)
    assert summary.snapshot_end == date(2024, 3, 1)
    assert summary.total_company_rows == 2
    assert summary.total_pass_recency_gate == 2
    assert summary.summary_csv_path.exists()

    store = KnowledgeStore(knowledge_path)
    try:
        dates = store.list_company_sotp_snapshot_dates()
        feb = store.get_company_sotp_snapshot_for_ticker_on_or_before(
            ticker="TEST",
            as_of=date(2024, 2, 1),
        )
        mar = store.get_company_sotp_snapshot_for_ticker_on_or_before(
            ticker="TEST",
            as_of=date(2024, 3, 1),
        )
    finally:
        store.close()

    assert dates == [date(2024, 3, 1), date(2024, 2, 1)]
    assert feb is not None
    assert feb["snapshot_date"] == date(2024, 2, 1)
    assert feb["balance_sheet_passes_recency_gate"] is True
    assert mar is not None
    assert mar["snapshot_date"] == date(2024, 3, 1)
    assert mar["market_cap_millions"] == 500.0
