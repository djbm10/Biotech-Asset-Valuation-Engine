from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from pydantic import ValidationError

from bve.analysis.company_sotp import (
    CompanySOTPBuilder,
    CompanySOTPStructuredInput,
    classify_sotp_tier,
    summarize_sotp_tiers,
)
from bve.connectors.market_prices import MarketPriceRecord
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.historical_replay import ReplayStore


def _write_asset_config(
    path: Path,
    *,
    asset_id: str,
    asset_name: str,
    ticker: str,
    company_id: str = "co-test",
    company_name: str = "Test Company",
    cash_millions: float = 40.0,
    debt_millions: float = 0.0,
    shares_outstanding_millions: float = 50.0,
    burn_rate_millions_per_quarter: float = 5.0,
    current_price: float = 10.0,
    config_quality: str | None = None,
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
            "id": company_id,
            "name": company_name,
            "ticker": ticker,
            "cash_millions": cash_millions,
            "debt_millions": debt_millions,
            "shares_outstanding_millions": shares_outstanding_millions,
            "burn_rate_millions_per_quarter": burn_rate_millions_per_quarter,
            "current_price": current_price,
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
    }
    if config_quality is not None:
        payload["_meta"] = {"config_quality": config_quality}
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _write_watchlist(path: Path, entries: list[dict]) -> Path:
    path.write_text(yaml.safe_dump({"watchlist": entries}, sort_keys=False), encoding="utf-8")
    return path


def _price_record(
    *,
    ticker: str = "TEST",
    price_date: date,
    close: float,
    market_cap: float,
) -> MarketPriceRecord:
    return MarketPriceRecord(
        ticker=ticker,
        price_date=price_date,
        close_usd=close,
        adj_close_usd=close,
        volume=500_000,
        market_cap_millions=market_cap,
        ingested_at=datetime.now(timezone.utc),
    )


def test_classify_sotp_tier_avoid_above_15x() -> None:
    tier = classify_sotp_tier(16.0, 5.0, 0.8)
    assert tier.tier == "avoid"
    assert tier.action == "exclude"
    assert tier.confidence_tier == "very_low"
    assert tier.reason == "extreme_ratio:16.0x"


def test_classify_sotp_tier_needs_manual_review_above_8x() -> None:
    tier = classify_sotp_tier(9.2, 0.0, 0.8)
    assert tier.tier == "needs_manual_review"
    assert tier.action == "flag"
    assert tier.confidence_tier == "low"
    assert tier.reason == "high_ratio:9.2x"


def test_classify_sotp_tier_crashing_mcap_flags_manual_review() -> None:
    tier = classify_sotp_tier(6.4, -42.0, 0.8)
    assert tier.tier == "needs_manual_review"
    assert tier.action == "flag"
    assert tier.confidence_tier == "low"
    assert tier.reason == "crashing_mcap:-42%"


def test_classify_sotp_tier_stable_mcap_surfaces_watch() -> None:
    tier = classify_sotp_tier(6.4, -5.0, 0.8)
    assert tier.tier == "watch"
    assert tier.action == "surface"
    assert tier.confidence_tier == "medium_flagged"
    assert tier.reason == "possible_mispricing:6.4x"


def test_classify_sotp_tier_missing_mcap_data_surfaces_watch() -> None:
    tier = classify_sotp_tier(5.5, None, 0.8)
    assert tier.tier == "watch"
    assert tier.action == "surface"
    assert tier.confidence_tier == "medium_flagged"
    assert tier.reason == "possible_mispricing:5.5x"


def test_classify_sotp_tier_normal_below_5x() -> None:
    tier = classify_sotp_tier(4.9, -50.0, 0.8)
    assert tier.tier == "normal"
    assert tier.action == "surface"
    assert tier.confidence_tier == "high"
    assert tier.reason == "within_range"


def test_summarize_sotp_tiers_counts_all_buckets() -> None:
    rows = [
        SimpleNamespace(sotp_tier="normal", sotp_tier_reason="within_range"),
        SimpleNamespace(sotp_tier="watch", sotp_tier_reason="possible_mispricing:6.0x"),
        SimpleNamespace(sotp_tier="watch", sotp_tier_reason="declining_mcap:-20%"),
        SimpleNamespace(sotp_tier="needs_manual_review", sotp_tier_reason="high_ratio:9.0x"),
        SimpleNamespace(sotp_tier="avoid", sotp_tier_reason="extreme_ratio:20.0x"),
    ]
    summary = summarize_sotp_tiers(rows)
    assert summary["normal"] == 1
    assert summary["watch_mispricing"] == 1
    assert summary["watch_declining"] == 1
    assert summary["needs_manual_review"] == 1
    assert summary["avoid"] == 1


def test_company_sotp_aggregates_multiple_assets_per_ticker(tmp_path: Path) -> None:
    cfg1 = _write_asset_config(
        tmp_path / "asset1.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
    )
    cfg2 = _write_asset_config(
        tmp_path / "asset2.yaml",
        asset_id="asset-2",
        asset_name="Asset Two",
        ticker="TEST",
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg1),
            },
            {
                "company_id": "co-test",
                "asset_id": "asset-2",
                "ticker": "TEST",
                "valuation_config": str(cfg2),
            },
        ],
    )

    builder = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 500.0},
    )
    rows = builder.build(str(watchlist), price_source="yfinance")

    assert len(rows) == 1
    row = rows[0]
    assert row.asset_count_modeled == 2
    assert set(row.modeled_asset_ids) == {"asset-1", "asset-2"}
    assert row.market_cap_millions == 500.0
    assert row.modeled_asset_value_millions > 0
    assert builder.last_csv_path is not None
    assert builder.last_csv_path.exists()


def test_company_sotp_uses_replay_price_times_shares(tmp_path: Path) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        shares_outstanding_millions=50.0,
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    replay_path = tmp_path / "replay.sqlite"
    replay = ReplayStore(str(replay_path))
    try:
        replay.insert_prices("TEST", [(date(2024, 3, 1), 10.0)])
    finally:
        replay.close()

    builder = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        replay_store_path=replay_path,
        overrides_path=None,
    )
    rows = builder.build(str(watchlist), price_source="replay_store")

    assert len(rows) == 1
    row = rows[0]
    assert row.market_cap_millions == 500.0
    assert row.market_cap_source == "replay_store_price_x_shares"


def test_company_sotp_applies_override_buckets(tmp_path: Path) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        cash_millions=30.0,
        burn_rate_millions_per_quarter=5.0,
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    overrides_path = tmp_path / "company_sotp_overrides.yaml"
    overrides_path.write_text(
        yaml.safe_dump(
            {
                "defaults": {"dilution_reserve_quarters": 0.0},
                "companies": {
                    "TEST": {
                        "platform_value_millions": 20.0,
                        "unmodeled_pipeline_value_millions": 10.0,
                        "royalty_value_millions": 5.0,
                        "dilution_reserve_millions": 7.0,
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    builder = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        overrides_path=overrides_path,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 200.0},
    )
    rows = builder.build(str(watchlist), price_source="yfinance")

    row = rows[0]
    expected = (
        row.modeled_asset_value_millions
        + row.net_cash_millions
        + 20.0
        + 10.0
        + 5.0
        - 7.0
    )
    assert row.platform_value_millions == 20.0
    assert row.unmodeled_pipeline_value_millions == 10.0
    assert row.royalty_value_millions == 5.0
    assert row.dilution_reserve_millions == 7.0
    assert row.sotp_equity_value_millions == expected


def test_company_sotp_supports_structured_dated_inputs_with_bucket_provenance(tmp_path: Path) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        config_quality="curated",
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    overrides_path = tmp_path / "company_sotp_overrides.yaml"
    overrides_path.write_text(
        yaml.safe_dump(
            {
                "companies": {
                    "TEST": {
                        "inputs": [
                            {
                                "bucket_id": "platform_core",
                                "bucket_type": "platform",
                                "label": "Platform core",
                                "value_millions": 25.0,
                                "as_of_date": "2024-01-15",
                                "confidence": 0.8,
                                "source": "analyst_manual",
                                "source_ref": "memo-1",
                                "source_kind": "analyst_bridge",
                            },
                            {
                                "bucket_id": "platform_core",
                                "bucket_type": "platform",
                                "label": "Platform core",
                                "value_millions": 30.0,
                                "as_of_date": "2024-03-01",
                                "confidence": 0.9,
                                "source": "analyst_manual",
                                "source_ref": "memo-2",
                                "source_kind": "analyst_bridge",
                            },
                            {
                                "bucket_id": "royalty_stream",
                                "bucket_type": "royalty",
                                "label": "Royalty stream",
                                "value_millions": 12.0,
                                "as_of_date": "2024-02-01",
                                "confidence": 0.7,
                                "source": "partner_econ_model",
                                "source_ref": "royalty-model",
                                "source_kind": "inferred",
                            },
                        ]
                    }
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    builder = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        overrides_path=overrides_path,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
    )
    rows = builder.build(str(watchlist), price_source="yfinance")

    row = rows[0]
    platform_bucket = next(bucket for bucket in row.buckets if bucket.bucket_id == "platform_core")
    royalty_bucket = next(bucket for bucket in row.buckets if bucket.bucket_id == "royalty_stream")
    modeled_bucket = next(bucket for bucket in row.buckets if bucket.bucket_type == "modeled_asset")

    assert platform_bucket.value_millions == 30.0
    assert platform_bucket.source_kind == "analyst_bridge"
    assert platform_bucket.source_confidence == 0.9
    assert platform_bucket.source_as_of == date(2024, 3, 1)
    assert platform_bucket.source_ref == "memo-2"
    assert royalty_bucket.source_kind == "inferred"
    assert modeled_bucket.source_kind == "modeled"
    assert modeled_bucket.source_confidence > 0.0
    assert row.modeled_asset_confidence_min > 0.0
    assert row.modeled_asset_confidence_avg >= row.modeled_asset_confidence_min
    assert row.structured_input_count == 2
    assert row.actionable_coverage_pct >= row.modeled_asset_coverage_pct
    assert row.actionable_confidence_pct > 0.0


def test_company_sotp_structured_input_normalizes_legacy_manual_source_kind() -> None:
    item = CompanySOTPStructuredInput.model_validate(
        {
            "bucket_id": "platform_core",
            "bucket_type": "platform",
            "label": "Platform core",
            "value_millions": 20.0,
            "as_of_date": "2024-03-01",
            "confidence": 0.70,
            "source": "analyst_manual",
            "source_ref": "memo-1",
            "source_kind": "manual",
        }
    )

    assert item.source_kind == "analyst_bridge"


def test_company_sotp_structured_input_enforces_source_kind_confidence_floor() -> None:
    with pytest.raises(ValidationError, match="below minimum 0.80 for source_kind=company_disclosure"):
        CompanySOTPStructuredInput.model_validate(
            {
                "bucket_id": "platform_core",
                "bucket_type": "platform",
                "label": "Platform core",
                "value_millions": 20.0,
                "as_of_date": "2024-03-01",
                "confidence": 0.75,
                "source": "company_disclosure_deck",
                "source_ref": "deck-1",
                "source_kind": "company_disclosure",
            }
        )


def test_company_sotp_supports_snapshot_bundles_for_point_in_time_company_inputs(
    tmp_path: Path,
) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        config_quality="curated",
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    overrides_path = tmp_path / "company_sotp_overrides.yaml"
    overrides_path.write_text(
        yaml.safe_dump(
            {
                "companies": {
                    "TEST": {
                        "snapshots": [
                            {
                                "as_of_date": "2024-01-15",
                                "inputs": [
                                    {
                                        "bucket_id": "pipeline_family_a",
                                        "bucket_type": "unmodeled_pipeline",
                                        "label": "Pipeline family A",
                                        "value_millions": 50.0,
                                        "as_of_date": "2024-01-15",
                                        "confidence": 0.7,
                                        "source": "analyst_manual",
                                        "source_ref": "snap-1",
                                        "source_kind": "analyst_bridge",
                                    }
                                ],
                            },
                            {
                                "as_of_date": "2024-03-01",
                                "inputs": [
                                    {
                                        "bucket_id": "pipeline_family_a",
                                        "bucket_type": "unmodeled_pipeline",
                                        "label": "Pipeline family A",
                                        "value_millions": 35.0,
                                        "as_of_date": "2024-03-01",
                                        "confidence": 0.8,
                                        "source": "analyst_manual",
                                        "source_ref": "snap-2",
                                        "source_kind": "analyst_bridge",
                                    },
                                    {
                                        "bucket_id": "royalty_stream",
                                        "bucket_type": "royalty",
                                        "label": "Royalty stream",
                                        "value_millions": 10.0,
                                        "as_of_date": "2024-03-01",
                                        "confidence": 0.65,
                                        "source": "partner_model",
                                        "source_ref": "snap-2-royalty",
                                        "source_kind": "inferred",
                                    },
                                ],
                            },
                        ]
                    }
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    rows_early = CompanySOTPBuilder(
        as_of_date=date(2024, 2, 1),
        output_dir=tmp_path / "out-early",
        overrides_path=overrides_path,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
    ).build(str(watchlist), price_source="yfinance")
    rows_late = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 20),
        output_dir=tmp_path / "out-late",
        overrides_path=overrides_path,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
    ).build(str(watchlist), price_source="yfinance")

    early_row = rows_early[0]
    late_row = rows_late[0]

    early_pipeline = next(
        bucket for bucket in early_row.buckets if bucket.bucket_id == "pipeline_family_a"
    )
    late_pipeline = next(
        bucket for bucket in late_row.buckets if bucket.bucket_id == "pipeline_family_a"
    )

    assert early_pipeline.value_millions == 50.0
    assert early_pipeline.source_ref == "snap-1"
    assert late_pipeline.value_millions == 35.0
    assert late_pipeline.source_ref == "snap-2"
    assert not any(bucket.bucket_id == "royalty_stream" for bucket in early_row.buckets)
    assert any(bucket.bucket_id == "royalty_stream" for bucket in late_row.buckets)
    assert late_row.structured_input_count == 2


def test_company_sotp_forces_manual_review_for_low_confidence_high_manual_share_pack(
    tmp_path: Path,
) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        cash_millions=0.0,
        shares_outstanding_millions=10.0,
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    knowledge_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(knowledge_path)
    try:
        store._conn.execute(
            """
            INSERT INTO screen_snapshots(
                snapshot_id, ticker, asset_id, snapshot_date, program_label, stage, ta,
                model_pos, implied_pos, spread_pp, rnpv_millions, ev_millions,
                acquisition_discount_pct, next_catalyst, catalyst_date,
                days_to_catalyst, single_asset, approximation_warning,
                thesis_strength, market_exceeds_model, config_quality, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                "TEST",
                "asset-1",
                "2024-03-01",
                "Asset One",
                "phase_2",
                "oncology",
                0.4,
                0.2,
                0.2,
                120.0,
                60.0,
                1.33,
                None,
                None,
                None,
                1,
                None,
                None,
                0,
                "gold",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        store._conn.commit()
    finally:
        store.close()

    replay_path = tmp_path / "replay.sqlite"
    replay = ReplayStore(str(replay_path))
    try:
        replay.upsert_balance_sheet_snapshot(
            ticker="TEST",
            snapshot_date=date(2024, 2, 20),
            period_end_date=date(2023, 12, 31),
            form_type="10-K",
            cash_millions=0.0,
            debt_millions=0.0,
            shares_outstanding_millions=10.0,
            burn_rate_millions_per_quarter=5.0,
            source_type="sec_edgar_company_facts",
            source_ref="unit-test-bs",
        )
    finally:
        replay.close()

    overrides_path = tmp_path / "company_sotp_overrides.yaml"
    overrides_path.write_text(
        yaml.safe_dump(
            {
                "companies": {
                    "TEST": {
                        "snapshots": [
                            {
                                "as_of_date": "2024-03-01",
                                "inputs": [
                                    {
                                        "bucket_id": "platform_core",
                                        "bucket_type": "platform",
                                        "label": "Platform core",
                                        "value_millions": 180.0,
                                        "as_of_date": "2024-03-01",
                                        "confidence": 0.65,
                                        "source": "analyst_manual",
                                        "source_ref": "memo-platform|deck-platform",
                                        "source_kind": "analyst_bridge",
                                    },
                                    {
                                        "bucket_id": "royalty_stream",
                                        "bucket_type": "royalty",
                                        "label": "Royalty stream",
                                        "value_millions": 20.0,
                                        "as_of_date": "2024-03-01",
                                        "confidence": 0.65,
                                        "source": "partner_model",
                                        "source_ref": "royalty-model",
                                        "source_kind": "inferred",
                                    },
                                ],
                            }
                        ]
                    }
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    rows = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        knowledge_db_path=knowledge_path,
        replay_store_path=replay_path,
        overrides_path=overrides_path,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
    ).build(str(watchlist), price_source="yfinance")

    row = rows[0]
    assert row.manual_bucket_share_pct > 0.35
    assert row.manual_bucket_confidence_avg is not None
    assert row.manual_bucket_confidence_avg < 0.80
    assert row.n_bucket_sources == 3
    assert row.action_policy == "needs_manual_review"
    assert row.action_reason.startswith("manual_bucket_quality_below_threshold:")


def test_company_sotp_forces_manual_review_for_concentrated_single_source_manual_pack(
    tmp_path: Path,
) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        cash_millions=0.0,
        shares_outstanding_millions=10.0,
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    knowledge_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(knowledge_path)
    try:
        store._conn.execute(
            """
            INSERT INTO screen_snapshots(
                snapshot_id, ticker, asset_id, snapshot_date, program_label, stage, ta,
                model_pos, implied_pos, spread_pp, rnpv_millions, ev_millions,
                acquisition_discount_pct, next_catalyst, catalyst_date,
                days_to_catalyst, single_asset, approximation_warning,
                thesis_strength, market_exceeds_model, config_quality, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                "TEST",
                "asset-1",
                "2024-03-01",
                "Asset One",
                "phase_2",
                "oncology",
                0.4,
                0.2,
                0.2,
                120.0,
                60.0,
                1.33,
                None,
                None,
                None,
                1,
                None,
                None,
                0,
                "gold",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        store._conn.commit()
    finally:
        store.close()

    replay_path = tmp_path / "replay.sqlite"
    replay = ReplayStore(str(replay_path))
    try:
        replay.upsert_balance_sheet_snapshot(
            ticker="TEST",
            snapshot_date=date(2024, 2, 20),
            period_end_date=date(2023, 12, 31),
            form_type="10-K",
            cash_millions=0.0,
            debt_millions=0.0,
            shares_outstanding_millions=10.0,
            burn_rate_millions_per_quarter=5.0,
            source_type="sec_edgar_company_facts",
            source_ref="unit-test-bs",
        )
    finally:
        replay.close()

    overrides_path = tmp_path / "company_sotp_overrides.yaml"
    overrides_path.write_text(
        yaml.safe_dump(
            {
                "companies": {
                    "TEST": {
                        "snapshots": [
                            {
                                "as_of_date": "2024-03-01",
                                "inputs": [
                                    {
                                        "bucket_id": "platform_core",
                                        "bucket_type": "platform",
                                        "label": "Platform core",
                                        "value_millions": 180.0,
                                        "as_of_date": "2024-03-01",
                                        "confidence": 0.80,
                                        "source": "analyst_manual",
                                        "source_ref": "memo-platform",
                                        "source_kind": "analyst_bridge",
                                    }
                                ],
                            }
                        ]
                    }
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    rows = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        knowledge_db_path=knowledge_path,
        replay_store_path=replay_path,
        overrides_path=overrides_path,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
    ).build(str(watchlist), price_source="yfinance")

    row = rows[0]
    assert row.manual_bucket_share_pct >= 0.25
    assert row.n_bucket_sources == 1
    assert row.action_policy == "needs_manual_review"
    assert row.action_reason.startswith("manual_bucket_source_concentration:")


def test_company_sotp_allows_strong_multi_source_manual_pack_for_auto_action(
    tmp_path: Path,
) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        cash_millions=0.0,
        shares_outstanding_millions=10.0,
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    knowledge_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(knowledge_path)
    try:
        store._conn.execute(
            """
            INSERT INTO screen_snapshots(
                snapshot_id, ticker, asset_id, snapshot_date, program_label, stage, ta,
                model_pos, implied_pos, spread_pp, rnpv_millions, ev_millions,
                acquisition_discount_pct, next_catalyst, catalyst_date,
                days_to_catalyst, single_asset, approximation_warning,
                thesis_strength, market_exceeds_model, config_quality, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                "TEST",
                "asset-1",
                "2024-03-01",
                "Asset One",
                "phase_2",
                "oncology",
                0.4,
                0.2,
                0.2,
                220.0,
                60.0,
                1.67,
                None,
                None,
                None,
                1,
                None,
                None,
                0,
                "gold",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        store._conn.commit()
    finally:
        store.close()

    replay_path = tmp_path / "replay.sqlite"
    replay = ReplayStore(str(replay_path))
    try:
        replay.upsert_balance_sheet_snapshot(
            ticker="TEST",
            snapshot_date=date(2024, 2, 20),
            period_end_date=date(2023, 12, 31),
            form_type="10-K",
            cash_millions=0.0,
            debt_millions=0.0,
            shares_outstanding_millions=10.0,
            burn_rate_millions_per_quarter=5.0,
            source_type="sec_edgar_company_facts",
            source_ref="unit-test-bs",
        )
    finally:
        replay.close()

    overrides_path = tmp_path / "company_sotp_overrides.yaml"
    overrides_path.write_text(
        yaml.safe_dump(
            {
                "companies": {
                    "TEST": {
                        "snapshots": [
                            {
                                "as_of_date": "2024-03-01",
                                "inputs": [
                                    {
                                        "bucket_id": "platform_core",
                                        "bucket_type": "platform",
                                        "label": "Platform core",
                                        "value_millions": 90.0,
                                        "as_of_date": "2024-03-01",
                                        "confidence": 0.80,
                                        "source": "analyst_manual",
                                        "source_ref": "memo-platform|deck-platform",
                                        "source_kind": "analyst_bridge",
                                    },
                                    {
                                        "bucket_id": "pipeline_family",
                                        "bucket_type": "unmodeled_pipeline",
                                        "label": "Pipeline family",
                                        "value_millions": 10.0,
                                        "as_of_date": "2024-03-01",
                                        "confidence": 0.80,
                                        "source": "analyst_pipeline_map",
                                        "source_ref": "pipeline-map",
                                        "source_kind": "analyst_bridge",
                                    },
                                ],
                            }
                        ]
                    }
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    rows = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        knowledge_db_path=knowledge_path,
        replay_store_path=replay_path,
        overrides_path=overrides_path,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
    ).build(str(watchlist), price_source="yfinance")

    row = rows[0]
    assert row.manual_bucket_share_pct >= 0.25
    assert row.manual_bucket_confidence_avg is not None
    assert row.manual_bucket_confidence_avg >= 0.65
    assert row.n_bucket_sources >= 3
    assert row.action_reason != "manual_bucket_source_concentration:"
    assert row.action_policy in {"watch", "buy"}


def test_company_sotp_counts_net_cash_toward_actionable_coverage(tmp_path: Path) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        cash_millions=120.0,
        shares_outstanding_millions=20.0,
        config_quality="curated",
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    knowledge_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(knowledge_path)
    try:
        store._conn.execute(
            """
            INSERT INTO screen_snapshots(
                snapshot_id, ticker, asset_id, snapshot_date, program_label, stage, ta,
                model_pos, implied_pos, spread_pp, rnpv_millions, ev_millions,
                acquisition_discount_pct, next_catalyst, catalyst_date,
                days_to_catalyst, single_asset, approximation_warning,
                thesis_strength, market_exceeds_model, config_quality, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                "TEST",
                "asset-1",
                "2024-03-01",
                "Asset One",
                "phase_2",
                "oncology",
                0.4,
                0.2,
                0.2,
                80.0,
                100.0,
                0.8,
                None,
                None,
                None,
                1,
                None,
                None,
                0,
                "curated",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        store._conn.commit()
    finally:
        store.close()

    replay_path = tmp_path / "replay.sqlite"
    replay = ReplayStore(str(replay_path))
    try:
        replay.upsert_balance_sheet_snapshot(
            ticker="TEST",
            snapshot_date=date(2024, 3, 1),
            period_end_date=date(2023, 12, 31),
            form_type="10-K",
            cash_millions=120.0,
            debt_millions=0.0,
            shares_outstanding_millions=20.0,
            burn_rate_millions_per_quarter=5.0,
            source_type="sec_edgar_company_facts",
            source_ref="unit-test-bs",
        )
    finally:
        replay.close()

    builder = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        knowledge_db_path=knowledge_path,
        replay_store_path=replay_path,
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
    )
    rows = builder.build(str(watchlist), price_source="yfinance")

    row = rows[0]
    assert row.modeled_asset_coverage_pct < 0.70
    assert row.actionable_coverage_pct > row.modeled_asset_coverage_pct
    assert row.action_policy == "avoid"
    assert row.action_reason.startswith("ranked_discount_below_watch_threshold")


def test_company_sotp_large_cap_single_asset_requires_structured_inputs_for_auto_action(
    tmp_path: Path,
) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        cash_millions=1200.0,
        shares_outstanding_millions=100.0,
        config_quality="curated",
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    knowledge_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(knowledge_path)
    try:
        store._conn.execute(
            """
            INSERT INTO screen_snapshots(
                snapshot_id, ticker, asset_id, snapshot_date, program_label, stage, ta,
                model_pos, implied_pos, spread_pp, rnpv_millions, ev_millions,
                acquisition_discount_pct, next_catalyst, catalyst_date,
                days_to_catalyst, single_asset, approximation_warning,
                thesis_strength, market_exceeds_model, config_quality, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                "TEST",
                "asset-1",
                "2024-03-01",
                "Asset One",
                "phase_2",
                "oncology",
                0.4,
                0.2,
                0.2,
                900.0,
                1500.0,
                1.4,
                None,
                None,
                None,
                1,
                None,
                None,
                0,
                "curated",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        store._conn.commit()
    finally:
        store.close()

    replay_path = tmp_path / "replay.sqlite"
    replay = ReplayStore(str(replay_path))
    try:
        replay.upsert_balance_sheet_snapshot(
            ticker="TEST",
            snapshot_date=date(2024, 3, 1),
            period_end_date=date(2023, 12, 31),
            form_type="10-K",
            cash_millions=1200.0,
            debt_millions=0.0,
            shares_outstanding_millions=100.0,
            burn_rate_millions_per_quarter=25.0,
            source_type="sec_edgar_company_facts",
            source_ref="unit-test-bs",
        )
    finally:
        replay.close()

    builder = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        knowledge_db_path=knowledge_path,
        replay_store_path=replay_path,
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 1500.0},
    )
    rows = builder.build(str(watchlist), price_source="yfinance")
    assert rows[0].action_policy == "needs_manual_review"
    assert rows[0].action_reason == "missing_structured_company_inputs_for_large_cap_single_asset"


def test_company_sotp_prefers_stored_screen_snapshot_for_single_asset(tmp_path: Path) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        config_quality="curated",
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    knowledge_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(knowledge_path)
    try:
        store._conn.execute(
            """
            INSERT INTO screen_snapshots(
                snapshot_id, ticker, asset_id, snapshot_date, program_label, stage, ta,
                model_pos, implied_pos, spread_pp, rnpv_millions, ev_millions,
                acquisition_discount_pct, next_catalyst, catalyst_date,
                days_to_catalyst, single_asset, approximation_warning,
                thesis_strength, market_exceeds_model, config_quality, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                "TEST",
                "asset-1",
                "2024-03-01",
                "Asset One",
                "phase_2",
                "oncology",
                0.4,
                0.2,
                0.2,
                123.0,
                100.0,
                1.23,
                None,
                None,
                None,
                1,
                None,
                None,
                0,
                "gold",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        store._conn.commit()
    finally:
        store.close()

    builder = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        knowledge_db_path=knowledge_path,
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 200.0},
    )
    rows = builder.build(str(watchlist), price_source="yfinance")

    row = rows[0]
    assert row.modeled_asset_value_millions == 123.0
    assert row.buckets[0].source == "stored_screen_snapshot"
    assert row.buckets[0].source_kind == "modeled"
    assert row.buckets[0].source_as_of == date(2024, 3, 1)


def test_company_sotp_uses_point_in_time_balance_sheet_and_asset_level_snapshots(
    tmp_path: Path,
) -> None:
    cfg1 = _write_asset_config(
        tmp_path / "asset1.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        cash_millions=10.0,
        shares_outstanding_millions=50.0,
    )
    cfg2 = _write_asset_config(
        tmp_path / "asset2.yaml",
        asset_id="asset-2",
        asset_name="Asset Two",
        ticker="TEST",
        cash_millions=10.0,
        shares_outstanding_millions=50.0,
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg1),
            },
            {
                "company_id": "co-test",
                "asset_id": "asset-2",
                "ticker": "TEST",
                "valuation_config": str(cfg2),
            },
        ],
    )
    knowledge_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(knowledge_path)
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        store._conn.executemany(
            """
            INSERT INTO screen_snapshots(
                snapshot_id, ticker, asset_id, snapshot_date, program_label, stage, ta,
                model_pos, implied_pos, spread_pp, rnpv_millions, ev_millions,
                acquisition_discount_pct, next_catalyst, catalyst_date,
                days_to_catalyst, single_asset, approximation_warning,
                thesis_strength, market_exceeds_model, config_quality, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(uuid.uuid4()),
                    "TEST",
                    "asset-1",
                    "2024-03-01",
                    "Asset One",
                    "phase_2",
                    "oncology",
                    0.4,
                    0.2,
                    20.0,
                    80.0,
                    60.0,
                    33.3,
                    None,
                    None,
                    None,
                    0,
                    "multi_asset",
                    None,
                    0,
                    "screening_grade",
                    created_at,
                ),
                (
                    str(uuid.uuid4()),
                    "TEST",
                    "asset-2",
                    "2024-03-01",
                    "Asset Two",
                    "phase_3",
                    "oncology",
                    0.6,
                    0.3,
                    30.0,
                    120.0,
                    75.0,
                    60.0,
                    None,
                    None,
                    None,
                    0,
                    "multi_asset",
                    None,
                    0,
                    "screening_grade",
                    created_at,
                ),
            ],
        )
        store._conn.commit()
    finally:
        store.close()

    replay_path = tmp_path / "replay.sqlite"
    replay = ReplayStore(str(replay_path))
    try:
        replay.insert_prices("TEST", [(date(2024, 3, 1), 5.0)])
        replay.upsert_balance_sheet_snapshot(
            ticker="TEST",
            snapshot_date=date(2024, 2, 20),
            period_end_date=date(2023, 12, 31),
            form_type="10-K",
            cash_millions=100.0,
            debt_millions=15.0,
            shares_outstanding_millions=40.0,
            burn_rate_millions_per_quarter=7.5,
            source_type="sec_edgar_company_facts",
            source_ref="0000000000:10-K:2024-02-20",
        )
    finally:
        replay.close()

    builder = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        knowledge_db_path=knowledge_path,
        replay_store_path=replay_path,
        overrides_path=None,
    )
    rows = builder.build(str(watchlist), price_source="replay_store")

    row = rows[0]
    assert row.modeled_asset_ids == ["asset-1", "asset-2"]
    assert row.modeled_asset_value_millions == 200.0
    assert row.balance_sheet_is_point_in_time is True
    assert row.balance_sheet_source == "sec_edgar_company_facts"
    assert row.balance_sheet_source_ref == "0000000000:10-K:2024-02-20"
    assert row.balance_sheet_snapshot_date == date(2024, 2, 20)
    assert row.balance_sheet_period_end_date == date(2023, 12, 31)
    assert row.balance_sheet_form_type == "10-K"
    assert row.balance_sheet_age_days == 10
    assert row.balance_sheet_passes_recency_gate is True
    assert row.balance_sheet_recency_penalty == 1.0
    assert row.net_cash_millions == 85.0
    assert row.shares_outstanding_millions == 40.0
    assert row.market_cap_millions == 200.0
    assert row.action_policy in {"watch", "buy"}
    assert "multi_asset_company_uses_config_valuations_not_per_asset_historical_snapshots" not in row.limitations
    assert "balance_sheet_latest_config_snapshot_not_point_in_time" not in row.limitations


def test_company_sotp_flags_static_balance_sheet_for_historical_date(tmp_path: Path) -> None:
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
            }
        ],
    )

    builder = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 200.0},
    )
    rows = builder.build(str(watchlist), price_source="yfinance")

    assert (
        "balance_sheet_latest_config_snapshot_not_point_in_time"
        in rows[0].limitations
    )
    assert "balance_sheet_recency_gate_not_met" in rows[0].limitations
    assert rows[0].balance_sheet_passes_recency_gate is False
    assert rows[0].balance_sheet_recency_penalty == 0.5
    assert rows[0].ranked_sotp_discount == round(rows[0].sotp_discount * 0.5, 6)
    assert rows[0].action_policy == "needs_manual_review"
    assert rows[0].action_reason == "balance_sheet_recency_gate_failed"


def test_company_sotp_prefers_current_config_quality_over_stale_snapshot_quality(
    tmp_path: Path,
) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        cash_millions=100.0,
        shares_outstanding_millions=20.0,
        config_quality="curated",
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    knowledge_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(knowledge_path)
    try:
        store._conn.execute(
            """
            INSERT INTO screen_snapshots(
                snapshot_id, ticker, asset_id, snapshot_date, program_label, stage, ta,
                model_pos, implied_pos, spread_pp, rnpv_millions, ev_millions,
                acquisition_discount_pct, next_catalyst, catalyst_date,
                days_to_catalyst, single_asset, approximation_warning,
                thesis_strength, market_exceeds_model, config_quality, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                "TEST",
                "asset-1",
                "2024-03-01",
                "Asset One",
                "phase_3",
                "oncology",
                0.6,
                0.3,
                0.3,
                140.0,
                170.0,
                40.0,
                None,
                None,
                None,
                1,
                None,
                None,
                0,
                "screening_grade",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        store._conn.commit()
    finally:
        store.close()

    replay_path = tmp_path / "replay.sqlite"
    replay = ReplayStore(str(replay_path))
    try:
        replay.upsert_balance_sheet_snapshot(
            ticker="TEST",
            snapshot_date=date(2024, 3, 1),
            period_end_date=date(2023, 12, 31),
            form_type="10-K",
            cash_millions=100.0,
            debt_millions=0.0,
            shares_outstanding_millions=20.0,
            burn_rate_millions_per_quarter=5.0,
            source_type="sec_edgar_company_facts",
            source_ref="unit-test-bs",
        )
    finally:
        replay.close()

    builder = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        knowledge_db_path=knowledge_path,
        replay_store_path=replay_path,
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 80.0},
    )
    rows = builder.build(str(watchlist), price_source="yfinance")

    row = rows[0]
    assert row.config_quality_summary == "curated"
    assert row.modeled_asset_confidence_min == pytest.approx(0.85)
    assert row.action_policy != "needs_manual_review"
    assert row.action_reason != "modeled_asset_confidence_below_threshold:0.50"


def test_company_sotp_applies_stale_balance_sheet_penalty(tmp_path: Path) -> None:
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
            }
        ],
    )
    replay_path = tmp_path / "replay.sqlite"
    replay = ReplayStore(str(replay_path))
    try:
        replay.insert_prices("TEST", [(date(2024, 3, 1), 10.0)])
        replay.upsert_balance_sheet_snapshot(
            ticker="TEST",
            snapshot_date=date(2022, 1, 15),
            period_end_date=date(2021, 12, 31),
            form_type="10-K",
            cash_millions=60.0,
            debt_millions=5.0,
            shares_outstanding_millions=50.0,
            burn_rate_millions_per_quarter=6.0,
            source_type="sec_edgar_company_facts",
            source_ref="0000000000:10-K:2022-01-15",
        )
    finally:
        replay.close()

    builder = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        replay_store_path=replay_path,
        overrides_path=None,
    )
    rows = builder.build(str(watchlist), price_source="replay_store")

    row = rows[0]
    assert row.balance_sheet_is_point_in_time is True
    assert row.balance_sheet_age_days == (date(2024, 3, 1) - date(2022, 1, 15)).days
    assert row.balance_sheet_passes_recency_gate is False
    assert row.balance_sheet_recency_penalty == 0.25
    assert row.ranked_sotp_discount == round(row.sotp_discount * 0.25, 6)
    assert row.action_policy == "needs_manual_review"
    assert any(
        item.startswith("balance_sheet_recency_gate_exceeded:")
        for item in row.limitations
    )


def test_company_sotp_surfaces_high_ratio_without_mcap_history_as_watch(
    tmp_path: Path,
) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        cash_millions=0.0,
        shares_outstanding_millions=10.0,
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    knowledge_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(knowledge_path)
    try:
        store._conn.execute(
            """
            INSERT INTO screen_snapshots(
                snapshot_id, ticker, asset_id, snapshot_date, program_label, stage, ta,
                model_pos, implied_pos, spread_pp, rnpv_millions, ev_millions,
                acquisition_discount_pct, next_catalyst, catalyst_date,
                days_to_catalyst, single_asset, approximation_warning,
                thesis_strength, market_exceeds_model, config_quality, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                "TEST",
                "asset-1",
                "2024-03-01",
                "Asset One",
                "phase_2",
                "oncology",
                0.4,
                0.2,
                0.2,
                1500.0,
                60.0,
                25.0,
                None,
                None,
                None,
                1,
                None,
                None,
                0,
                "gold",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        store._conn.commit()
    finally:
        store.close()

    replay_path = tmp_path / "replay.sqlite"
    replay = ReplayStore(str(replay_path))
    try:
        replay.upsert_balance_sheet_snapshot(
            ticker="TEST",
            snapshot_date=date(2024, 2, 20),
            period_end_date=date(2023, 12, 31),
            form_type="10-K",
            cash_millions=0.0,
            debt_millions=0.0,
            shares_outstanding_millions=10.0,
            burn_rate_millions_per_quarter=5.0,
            source_type="sec_edgar_company_facts",
            source_ref="unit-test-bs",
        )
    finally:
        replay.close()

    rows = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        knowledge_db_path=knowledge_path,
        replay_store_path=replay_path,
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
    ).build(str(watchlist), price_source="yfinance")

    row = rows[0]
    assert row.sotp_discount > 5.0
    assert row.reconciliation_status == "extreme_discount"
    assert row.reconciliation_passes_gate is True
    assert row.sotp_tier == "watch"
    assert row.sotp_action == "surface"
    assert row.sotp_confidence_tier == "medium_flagged"
    assert row.action_policy == "watch"
    assert row.action_reason.startswith("possible_mispricing:")
    assert row.extreme_discount is False
    assert any(item.startswith("reconciliation_extreme_discount:") for item in row.limitations)


def test_company_sotp_flags_crashing_high_ratio_as_needs_manual_review(
    tmp_path: Path,
) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        cash_millions=0.0,
        shares_outstanding_millions=10.0,
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    knowledge_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(knowledge_path)
    try:
        store._conn.execute(
            """
            INSERT INTO screen_snapshots(
                snapshot_id, ticker, asset_id, snapshot_date, program_label, stage, ta,
                model_pos, implied_pos, spread_pp, rnpv_millions, ev_millions,
                acquisition_discount_pct, next_catalyst, catalyst_date,
                days_to_catalyst, single_asset, approximation_warning,
                thesis_strength, market_exceeds_model, config_quality, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                "TEST",
                "asset-1",
                "2024-03-01",
                "Asset One",
                "phase_2",
                "oncology",
                0.4,
                0.2,
                0.2,
                1500.0,
                60.0,
                25.0,
                None,
                None,
                None,
                1,
                None,
                None,
                0,
                "gold",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        store.upsert_market_price(_price_record(price_date=date(2023, 12, 1), close=10.0, market_cap=400.0))
        store.upsert_market_price(_price_record(price_date=date(2024, 3, 1), close=4.0, market_cap=150.0))
        store._conn.commit()
    finally:
        store.close()

    replay_path = tmp_path / "replay.sqlite"
    replay = ReplayStore(str(replay_path))
    try:
        replay.upsert_balance_sheet_snapshot(
            ticker="TEST",
            snapshot_date=date(2024, 2, 20),
            period_end_date=date(2023, 12, 31),
            form_type="10-K",
            cash_millions=0.0,
            debt_millions=0.0,
            shares_outstanding_millions=10.0,
            burn_rate_millions_per_quarter=5.0,
            source_type="sec_edgar_company_facts",
            source_ref="unit-test-bs",
        )
    finally:
        replay.close()

    rows = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        knowledge_db_path=knowledge_path,
        replay_store_path=replay_path,
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
    ).build(str(watchlist), price_source="yfinance")

    row = rows[0]
    assert row.sotp_discount > 5.0
    assert row.mcap_trend_3m_pct is not None and row.mcap_trend_3m_pct < -30.0
    assert row.reconciliation_status == "extreme_discount"
    assert row.reconciliation_passes_gate is False
    assert row.sotp_tier == "needs_manual_review"
    assert row.action_policy == "needs_manual_review"
    assert row.action_reason.startswith("crashing_mcap:")
    assert row.extreme_discount is True



def test_company_sotp_flags_extreme_reconciliation_premium_for_manual_review(
    tmp_path: Path,
) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        cash_millions=0.0,
        shares_outstanding_millions=10.0,
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    knowledge_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(knowledge_path)
    try:
        store._conn.execute(
            """
            INSERT INTO screen_snapshots(
                snapshot_id, ticker, asset_id, snapshot_date, program_label, stage, ta,
                model_pos, implied_pos, spread_pp, rnpv_millions, ev_millions,
                acquisition_discount_pct, next_catalyst, catalyst_date,
                days_to_catalyst, single_asset, approximation_warning,
                thesis_strength, market_exceeds_model, config_quality, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                "TEST",
                "asset-1",
                "2024-03-01",
                "Asset One",
                "phase_2",
                "oncology",
                0.4,
                0.2,
                0.2,
                40.0,
                60.0,
                0.67,
                None,
                None,
                None,
                1,
                None,
                None,
                0,
                "gold",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        store._conn.commit()
    finally:
        store.close()

    replay_path = tmp_path / "replay.sqlite"
    replay = ReplayStore(str(replay_path))
    try:
        replay.upsert_balance_sheet_snapshot(
            ticker="TEST",
            snapshot_date=date(2024, 2, 20),
            period_end_date=date(2023, 12, 31),
            form_type="10-K",
            cash_millions=0.0,
            debt_millions=0.0,
            shares_outstanding_millions=10.0,
            burn_rate_millions_per_quarter=5.0,
            source_type="sec_edgar_company_facts",
            source_ref="unit-test-bs",
        )
    finally:
        replay.close()

    rows = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        knowledge_db_path=knowledge_path,
        replay_store_path=replay_path,
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
    ).build(str(watchlist), price_source="yfinance")

    row = rows[0]
    assert row.sotp_discount < 0.25
    assert row.reconciliation_status == "extreme_premium"
    assert row.reconciliation_passes_gate is True
    assert row.action_policy == "avoid"
    assert row.action_reason.startswith("ranked_discount_below_watch_threshold:")
    assert any(item.startswith("reconciliation_extreme_premium:") for item in row.limitations)


def test_company_sotp_persists_company_snapshots_and_supports_lookup(tmp_path: Path) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        config_quality="curated",
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    knowledge_path = tmp_path / "knowledge.db"

    builder = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out",
        knowledge_db_path=knowledge_path,
        overrides_path=None,
        persist_company_snapshots=True,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
    )
    rows = builder.build(str(watchlist), price_source="yfinance")

    assert len(rows) == 1
    store = KnowledgeStore(knowledge_path)
    try:
        snapshot = store.get_company_sotp_snapshot_for_ticker_on_or_before(
            ticker="TEST",
            as_of=date(2024, 3, 2),
        )
    finally:
        store.close()

    assert snapshot is not None
    assert snapshot["ticker"] == "TEST"
    assert snapshot["snapshot_date"] == date(2024, 3, 1)
    assert snapshot["config_quality_summary"] == "curated"
    assert snapshot["action_policy"] == rows[0].action_policy
    assert snapshot["modeled_asset_ids"] == ["asset-1"]
    assert snapshot["bucket_count"] == len(rows[0].buckets)
    assert snapshot["manual_bucket_share_pct"] == rows[0].manual_bucket_share_pct
    assert snapshot["n_bucket_sources"] == rows[0].n_bucket_sources
    assert snapshot["reconciliation_gap_millions"] == rows[0].reconciliation_gap_millions
    assert snapshot["reconciliation_gap_pct"] == rows[0].reconciliation_gap_pct
    assert snapshot["reconciliation_status"] == rows[0].reconciliation_status
    assert snapshot["reconciliation_passes_gate"] == rows[0].reconciliation_passes_gate
    assert snapshot["mcap_trend_3m_pct"] == rows[0].mcap_trend_3m_pct
    assert snapshot["sotp_tier"] == rows[0].sotp_tier
    assert snapshot["sotp_action"] == rows[0].sotp_action
    assert snapshot["sotp_confidence_tier"] == rows[0].sotp_confidence_tier
    assert snapshot["sotp_tier_reason"] == rows[0].sotp_tier_reason


def test_company_sotp_reuses_shared_asset_rnpv_cache_across_builders(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
            }
        ],
    )
    calls: list[str] = []

    def _fake_compute(*, raw_cfg, config_path, company):
        calls.append(str(config_path))
        return 111.0

    monkeypatch.setattr(
        CompanySOTPBuilder,
        "_compute_asset_rnpv",
        staticmethod(_fake_compute),
    )
    shared_cache: dict[str, float] = {}

    first = CompanySOTPBuilder(
        as_of_date=date(2024, 2, 1),
        output_dir=tmp_path / "out1",
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
        asset_rnpv_cache=shared_cache,
    )
    second = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 1),
        output_dir=tmp_path / "out2",
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
        asset_rnpv_cache=shared_cache,
    )

    first_rows = first.build(str(watchlist), price_source="yfinance")
    second_rows = second.build(str(watchlist), price_source="yfinance")

    assert len(calls) == 1
    assert first_rows[0].modeled_asset_value_millions == 111.0
    assert second_rows[0].modeled_asset_value_millions == 111.0
    assert len(shared_cache) == 1


def test_company_sotp_load_from_store_uses_company_snapshots_on_or_before(tmp_path: Path) -> None:
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="asset-1",
        asset_name="Asset One",
        ticker="TEST",
        config_quality="curated",
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    knowledge_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(knowledge_path)
    try:
        store.write_company_sotp_snapshots(
            [
                CompanySOTPBuilder(
                    as_of_date=date(2024, 3, 1),
                    output_dir=tmp_path / "out",
                    overrides_path=None,
                    fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
                ).build(str(watchlist), price_source="yfinance")[0]
            ],
            snapshot_date=date(2024, 3, 1),
        )
    finally:
        store.close()

    builder = CompanySOTPBuilder(
        as_of_date=date(2024, 3, 20),
        output_dir=tmp_path / "out2",
        knowledge_db_path=knowledge_path,
        overrides_path=None,
    )
    resolved_date, rows = builder.load_from_store(str(watchlist))

    assert resolved_date == date(2024, 3, 1)
    assert len(rows) == 1
    assert rows[0].ticker == "TEST"
    assert rows[0].snapshot_date == date(2024, 3, 1)


# ---------------------------------------------------------------------------
# config_valid_from enforcement
# ---------------------------------------------------------------------------

def _write_asset_config_with_valid_from(
    path: Path,
    *,
    asset_id: str,
    asset_name: str,
    ticker: str,
    config_valid_from: str,
    cash_millions: float = 40.0,
    shares_outstanding_millions: float = 50.0,
) -> Path:
    payload = {
        "asset": {
            "id": asset_id,
            "name": asset_name,
            "indication": f"{asset_name} indication",
            "therapeutic_area": "oncology",
            "stage": "phase_3",
            "modality": "small_molecule",
            "discount_rate": 0.1,
        },
        "company": {
            "id": "co-test",
            "name": "Test Company",
            "ticker": ticker,
            "cash_millions": cash_millions,
            "debt_millions": 0.0,
            "shares_outstanding_millions": shares_outstanding_millions,
            "burn_rate_millions_per_quarter": 5.0,
            "current_price": 10.0,
        },
        "trials": [
            {
                "phase": "phase_3",
                "success_probability": 0.65,
                "duration_years": 3.0,
                "cost_millions": 80.0,
                "endpoint_type": "surrogate_validated",
            },
            {
                "phase": "nda_bla",
                "success_probability": 0.87,
                "duration_years": 1.5,
                "cost_millions": 30.0,
                "endpoint_type": "surrogate_validated",
            },
        ],
        "market_model": {
            "total_addressable_market_millions": 30000.0,
            "peak_penetration": 0.12,
            "years_to_peak": 5,
            "patent_life_years": 12,
            "cogs_rate": 0.15,
            "sgna_rate_launch": 0.4,
            "sgna_rate_mature": 0.2,
        },
        "_meta": {
            "config_valid_from": config_valid_from,
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_config_valid_from_excludes_asset_before_thesis_date(tmp_path: Path) -> None:
    """When as_of_date < config_valid_from for all assets, the company is excluded entirely
    from the results list (returns None).  This prevents the false extreme-discount signal
    from contaminating the backtest for pre-thesis historical periods (e.g. VKTX 2021)."""
    cfg = _write_asset_config_with_valid_from(
        tmp_path / "asset.yaml",
        asset_id="a-test",
        asset_name="Test Asset",
        ticker="TEST",
        config_valid_from="2023-01-01",
        cash_millions=200.0,
        shares_outstanding_millions=50.0,
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "a-test",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    rows = CompanySOTPBuilder(
        as_of_date=date(2021, 6, 1),   # before config_valid_from
        output_dir=tmp_path / "out",
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
    ).build(str(watchlist), price_source="yfinance")

    # Company excluded — no false extreme-discount snapshot generated
    assert rows == [], (
        "Expected company to be excluded when all configs are pre-thesis, "
        f"got {len(rows)} row(s)"
    )


def test_config_valid_from_includes_asset_on_or_after_thesis_date(tmp_path: Path) -> None:
    """When as_of_date >= config_valid_from, the asset is computed normally."""
    cfg = _write_asset_config_with_valid_from(
        tmp_path / "asset.yaml",
        asset_id="a-test",
        asset_name="Test Asset",
        ticker="TEST",
        config_valid_from="2023-01-01",
        cash_millions=50.0,
        shares_outstanding_millions=50.0,
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "a-test",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    rows = CompanySOTPBuilder(
        as_of_date=date(2023, 6, 1),   # on or after config_valid_from
        output_dir=tmp_path / "out",
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 250.0},
    ).build(str(watchlist), price_source="yfinance")

    row = rows[0]
    # Modeled asset was included
    assert row.asset_count_modeled == 1
    assert not any("config_not_applicable_pre_thesis" in lim for lim in row.limitations)


def test_config_valid_from_pre_thesis_vktx_excluded_from_backtest(tmp_path: Path) -> None:
    """Reproduces the VKTX 2021 false-extreme-discount scenario.

    VKTX config has TAM=$30B obesity thesis (Phase 3) but is tagged config_valid_from=2023.
    In 2021, market cap was ~$500M. Without the fix, this produced a false 7x ratio and
    extreme-discount flag. With the fix, the company is excluded entirely for 2021
    snapshots, eliminating the contamination from the backtest.
    """
    cfg = _write_asset_config_with_valid_from(
        tmp_path / "asset.yaml",
        asset_id="a-vktx",
        asset_name="VK2735",
        ticker="VKTX",
        config_valid_from="2023-01-01",
        cash_millions=250.0,
        shares_outstanding_millions=100.0,
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "vktx",
                "asset_id": "a-vktx",
                "ticker": "VKTX",
                "valuation_config": str(cfg),
            }
        ],
    )
    rows_2021 = CompanySOTPBuilder(
        as_of_date=date(2021, 6, 1),
        output_dir=tmp_path / "out",
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 500.0},
    ).build(str(watchlist), price_source="yfinance")

    rows_2023 = CompanySOTPBuilder(
        as_of_date=date(2023, 6, 1),
        output_dir=tmp_path / "out2",
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 2000.0},
    ).build(str(watchlist), price_source="yfinance")

    # 2021: excluded — no false 7x extreme-discount
    assert rows_2021 == [], "Pre-thesis VKTX 2021 must be excluded from backtest"
    # 2023: included — thesis is now valid
    assert len(rows_2023) == 1
    assert rows_2023[0].asset_count_modeled == 1


def test_config_without_valid_from_is_always_included(tmp_path: Path) -> None:
    """Configs without config_valid_from are never skipped (backward-compatible)."""
    cfg = _write_asset_config(
        tmp_path / "asset.yaml",
        asset_id="a-test",
        asset_name="Asset",
        ticker="TEST",
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "a-test",
                "ticker": "TEST",
                "valuation_config": str(cfg),
            }
        ],
    )
    rows = CompanySOTPBuilder(
        as_of_date=date(2015, 1, 1),  # very early date
        output_dir=tmp_path / "out",
        overrides_path=None,
        fundamentals_fetcher=lambda _: {"market_cap_millions": 50.0},
    ).build(str(watchlist), price_source="yfinance")

    row = rows[0]
    assert row.asset_count_modeled == 1
    assert not any("config_not_applicable_pre_thesis" in lim for lim in row.limitations)
