from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from bve.analysis.company_sotp_backtest import (
    CompanySOTPBacktestConfig,
    CompanySOTPBacktester,
)
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.historical_replay import ReplayStore


def _company_snapshot(
    *,
    ticker: str,
    company_id: str,
    snapshot_date: date,
    ranked_sotp_discount: float,
    action_policy: str = "buy",
):
    return SimpleNamespace(
        ticker=ticker,
        company_id=company_id,
        company_name=f"Company {ticker}",
        snapshot_date=snapshot_date,
        rank=1,
        market_cap_millions=250.0,
        enterprise_value_millions=230.0,
        sotp_equity_value_millions=300.0,
        sotp_per_share=30.0,
        sotp_discount=ranked_sotp_discount,
        ranked_sotp_discount=ranked_sotp_discount,
        modeled_asset_coverage_pct=0.8,
        asset_count_modeled=1,
        modeled_asset_ids=[f"asset-{ticker.lower()}"],
        config_quality_summary="curated",
        modeled_asset_confidence_min=0.9,
        modeled_asset_confidence_avg=0.9,
        action_policy=action_policy,
        action_reason="ok",
        market_cap_source="unit_test",
        balance_sheet_source="sec_edgar_company_facts",
        balance_sheet_source_ref="unit-test",
        balance_sheet_snapshot_date=snapshot_date,
        balance_sheet_period_end_date=snapshot_date,
        balance_sheet_form_type="10-Q",
        balance_sheet_is_point_in_time=True,
        balance_sheet_age_days=10,
        balance_sheet_passes_recency_gate=True,
        balance_sheet_recency_penalty=1.0,
        buckets=[],
        limitations=[],
        notes=None,
    )


def test_company_sotp_backtester_uses_company_snapshots_as_signal_dataset(tmp_path: Path) -> None:
    knowledge = KnowledgeStore(tmp_path / "knowledge.db")
    replay = ReplayStore(str(tmp_path / "replay.sqlite"))
    try:
        knowledge.write_company_sotp_snapshots(
            [
                _company_snapshot(
                    ticker="AAA",
                    company_id="co-aaa",
                    snapshot_date=date(2024, 1, 1),
                    ranked_sotp_discount=1.8,
                ),
                _company_snapshot(
                    ticker="BBB",
                    company_id="co-bbb",
                    snapshot_date=date(2024, 1, 1),
                    ranked_sotp_discount=1.2,
                ),
            ],
            snapshot_date=date(2024, 1, 1),
        )
        knowledge.write_company_sotp_snapshots(
            [
                _company_snapshot(
                    ticker="AAA",
                    company_id="co-aaa",
                    snapshot_date=date(2024, 2, 1),
                    ranked_sotp_discount=1.7,
                )
            ],
            snapshot_date=date(2024, 2, 1),
        )
        replay.insert_prices(
            "AAA",
            [
                (date(2024, 1, 1), 10.0),
                (date(2024, 1, 31), 12.0),
                (date(2024, 2, 1), 12.0),
                (date(2024, 3, 2), 13.0),
            ],
        )
        replay.insert_prices(
            "BBB",
            [
                (date(2024, 1, 1), 8.0),
                (date(2024, 1, 31), 8.5),
            ],
        )
        replay.insert_prices(
            "XBI",
            [
                (date(2024, 1, 1), 100.0),
                (date(2024, 1, 31), 105.0),
                (date(2024, 2, 1), 105.0),
                (date(2024, 3, 2), 110.0),
            ],
        )

        report = CompanySOTPBacktester(
            knowledge,
            replay_db_path=tmp_path / "replay.sqlite",
            output_dir=tmp_path / "analysis",
            config=CompanySOTPBacktestConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 15),
                hold_days=30,
                top_n=1,
                min_ranked_sotp_discount=1.0,
            ),
        ).run()
    finally:
        replay.close()
        knowledge.close()

    assert report.n_snapshot_dates == 2
    assert report.n_candidate_rows == 3
    assert report.n_selected_trades == 2
    assert report.n_missing_price_trades == 0
    assert report.stats.n_trades == 2
    assert report.csv_path.exists()
    assert [trade.ticker for trade in report.trades] == ["AAA", "AAA"]
