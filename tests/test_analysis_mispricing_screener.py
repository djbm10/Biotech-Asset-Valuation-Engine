from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import yaml

from bve.analysis.implied_pos_batch import ScreenRow
from bve.analysis.implied_pos import ImpliedPoSSolver
from bve.analysis.mispricing_screener import MispricingScreener
from bve.intelligence.catalyst_calendar import CatalystEvent, CatalystType
from bve.intelligence.knowledge_layer import KnowledgeStore


def _write_asset_config(
    path: Path,
    *,
    asset_id: str,
    ticker: str,
    stage: str = "phase_2",
    success_probability: float = 0.60,
    cash_millions: float = 20.0,
    debt_millions: float = 0.0,
    shares_outstanding_millions: float = 10.0,
    config_quality: str | None = None,
) -> Path:
    cfg = {
        "asset": {
            "id": asset_id,
            "name": asset_id.upper(),
            "indication": "Solid tumors",
            "therapeutic_area": "oncology",
            "stage": stage,
            "modality": "small_molecule",
            "discount_rate": 0.10,
            "royalty_rate": 0.0,
        },
        "company": {
            "id": f"co-{asset_id}",
            "name": f"Company {asset_id}",
            "ticker": ticker,
            "cash_millions": cash_millions,
            "debt_millions": debt_millions,
            "shares_outstanding_millions": shares_outstanding_millions,
            "burn_rate_millions_per_quarter": 10.0,
        },
        "trials": [
            {
                "phase": stage if stage in {"phase_1", "phase_2", "phase_3", "nda_bla"} else "phase_2",
                "success_probability": success_probability,
                "duration_years": 2.0,
                "cost_millions": 40.0,
                "endpoint_type": "surrogate_validated",
            }
        ],
        "market_model": {
            "total_addressable_market_millions": 2000.0,
            "peak_penetration": 0.25,
            "years_to_peak": 4,
            "patent_life_years": 12,
            "cogs_rate": 0.15,
            "sgna_rate_launch": 0.40,
            "sgna_rate_mature": 0.20,
        },
    }
    if config_quality is not None:
        cfg["_meta"] = {"config_quality": config_quality}
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _write_watchlist(
    path: Path,
    *,
    entries: list[dict],
    knowledge_db_path: Path,
) -> Path:
    raw = {
        "knowledge_db_path": str(knowledge_db_path),
        "watchlist": entries,
    }
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def _make_entry(asset_id: str, ticker: str, config_path: Path) -> dict:
    return {
        "company_id": f"co-{asset_id}",
        "asset_id": asset_id,
        "ticker": ticker,
        "valuation_config": str(config_path),
    }


def _screener(
    tmp_path: Path,
    *,
    as_of_date: date,
    fundamentals: dict[str, dict],
    replay_store_path: Path | None = None,
    knowledge_db_path: Path | None = None,
    persist_screen_snapshots: bool = False,
    prefer_stored_snapshots: bool = False,
) -> MispricingScreener:
    return MispricingScreener(
        solver=ImpliedPoSSolver(max_iterations=50, mc_simulations=1, random_seed=42),
        as_of_date=as_of_date,
        output_dir=tmp_path / "outputs",
        replay_store_path=replay_store_path,
        knowledge_db_path=knowledge_db_path,
        persist_screen_snapshots=persist_screen_snapshots,
        prefer_stored_snapshots=prefer_stored_snapshots,
        fundamentals_fetcher=lambda ticker: fundamentals[ticker],
    )


def _write_company_snapshot(
    store: KnowledgeStore,
    *,
    ticker: str,
    snapshot_date: date,
    passes_gate: bool,
    action_policy: str = "watch",
    action_reason: str = "ok",
) -> None:
    store.write_company_sotp_snapshots(
        [
            SimpleNamespace(
                ticker=ticker,
                company_id=f"co-{ticker.lower()}",
                company_name=f"Company {ticker}",
                snapshot_date=snapshot_date,
                rank=1,
                market_cap_millions=250.0,
                enterprise_value_millions=230.0,
                sotp_equity_value_millions=300.0,
                sotp_per_share=30.0,
                sotp_discount=1.2,
                ranked_sotp_discount=1.2,
                modeled_asset_coverage_pct=0.8,
                asset_count_modeled=1,
                modeled_asset_ids=[f"asset-{ticker.lower()}"],
                config_quality_summary="curated",
                modeled_asset_confidence_min=0.9,
                modeled_asset_confidence_avg=0.9,
                action_policy=action_policy,
                action_reason=action_reason,
                market_cap_source="unit_test",
                balance_sheet_source="sec_edgar_company_facts",
                balance_sheet_source_ref="unit-test",
                balance_sheet_snapshot_date=snapshot_date,
                balance_sheet_period_end_date=snapshot_date,
                balance_sheet_form_type="10-Q",
                balance_sheet_is_point_in_time=True,
                balance_sheet_age_days=10,
                balance_sheet_passes_recency_gate=passes_gate,
                balance_sheet_recency_penalty=1.0 if passes_gate else 0.25,
                buckets=[],
                limitations=[],
                notes=None,
            )
        ],
        snapshot_date=snapshot_date,
    )


def test_company_sotp_snapshot_write_replaces_stale_same_date_rows(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db")
    snapshot_date = date(2026, 4, 5)
    try:
        store.write_company_sotp_snapshots(
            [
                SimpleNamespace(
                    ticker="AAA",
                    company_id="co-aaa",
                    company_name="Company AAA",
                    snapshot_date=snapshot_date,
                    rank=1,
                    market_cap_millions=250.0,
                    enterprise_value_millions=230.0,
                    sotp_equity_value_millions=300.0,
                    sotp_per_share=30.0,
                    sotp_discount=1.2,
                    ranked_sotp_discount=1.2,
                    modeled_asset_coverage_pct=0.8,
                    asset_count_modeled=1,
                    modeled_asset_ids=["asset-aaa"],
                    config_quality_summary="curated",
                    modeled_asset_confidence_min=0.9,
                    modeled_asset_confidence_avg=0.9,
                    action_policy="watch",
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
                ),
                SimpleNamespace(
                    ticker="BBB",
                    company_id="co-bbb",
                    company_name="Company BBB",
                    snapshot_date=snapshot_date,
                    rank=2,
                    market_cap_millions=260.0,
                    enterprise_value_millions=240.0,
                    sotp_equity_value_millions=310.0,
                    sotp_per_share=31.0,
                    sotp_discount=1.19,
                    ranked_sotp_discount=1.19,
                    modeled_asset_coverage_pct=0.8,
                    asset_count_modeled=1,
                    modeled_asset_ids=["asset-bbb"],
                    config_quality_summary="curated",
                    modeled_asset_confidence_min=0.9,
                    modeled_asset_confidence_avg=0.9,
                    action_policy="watch",
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
                ),
            ],
            snapshot_date=snapshot_date,
        )
        store.write_company_sotp_snapshots(
            [
                SimpleNamespace(
                    ticker="AAA",
                    company_id="co-aaa",
                    company_name="Company AAA",
                    snapshot_date=snapshot_date,
                    rank=1,
                    market_cap_millions=255.0,
                    enterprise_value_millions=235.0,
                    sotp_equity_value_millions=305.0,
                    sotp_per_share=30.5,
                    sotp_discount=1.196,
                    ranked_sotp_discount=1.196,
                    modeled_asset_coverage_pct=0.8,
                    asset_count_modeled=1,
                    modeled_asset_ids=["asset-aaa"],
                    config_quality_summary="curated",
                    modeled_asset_confidence_min=0.9,
                    modeled_asset_confidence_avg=0.9,
                    action_policy="buy",
                    action_reason="updated",
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
            ],
            snapshot_date=snapshot_date,
        )
        rows = store.get_company_sotp_snapshots(snapshot_date=snapshot_date, limit=10)
    finally:
        store.close()

    assert [row["ticker"] for row in rows] == ["AAA"]
    assert rows[0]["action_policy"] == "buy"


def test_screen_produces_ranked_results_sorted_by_pos_spread(tmp_path: Path) -> None:
    as_of = date(2026, 4, 5)
    cfg_a = _write_asset_config(tmp_path / "a.yaml", asset_id="asset-a", ticker="AAA")
    cfg_b = _write_asset_config(tmp_path / "b.yaml", asset_id="asset-b", ticker="BBB")
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        entries=[
            _make_entry("asset-a", "AAA", cfg_a),
            _make_entry("asset-b", "BBB", cfg_b),
        ],
        knowledge_db_path=tmp_path / "knowledge.db",
    )
    fundamentals = {
        "AAA": {"market_cap_millions": 160.0},
        "BBB": {"market_cap_millions": 260.0},
    }

    rows = _screener(tmp_path, as_of_date=as_of, fundamentals=fundamentals).screen(str(watchlist))

    assert len(rows) == 2
    assert rows[0].pos_spread >= rows[1].pos_spread
    assert [row.rank for row in rows] == [1, 2]
    assert rows[0].ticker == "AAA"


def test_handles_assets_with_missing_price_data_gracefully(tmp_path: Path) -> None:
    as_of = date(2026, 4, 5)
    cfg_a = _write_asset_config(tmp_path / "a.yaml", asset_id="asset-a", ticker="AAA")
    cfg_b = _write_asset_config(tmp_path / "b.yaml", asset_id="asset-b", ticker="BBB")
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        entries=[
            _make_entry("asset-a", "AAA", cfg_a),
            _make_entry("asset-b", "BBB", cfg_b),
        ],
        knowledge_db_path=tmp_path / "knowledge.db",
    )
    fundamentals = {
        "AAA": {"market_cap_millions": 180.0},
        "BBB": {"market_cap_millions": None, "current_price": None},
    }

    rows = _screener(tmp_path, as_of_date=as_of, fundamentals=fundamentals).screen(str(watchlist))

    assert len(rows) == 1
    assert rows[0].ticker == "AAA"


def test_handles_assets_where_ev_exceeds_max_rnpv(tmp_path: Path) -> None:
    as_of = date(2026, 4, 5)
    cfg = _write_asset_config(tmp_path / "huge.yaml", asset_id="asset-huge", ticker="HUGE")
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        entries=[_make_entry("asset-huge", "HUGE", cfg)],
        knowledge_db_path=tmp_path / "knowledge.db",
    )
    fundamentals = {
        "HUGE": {"market_cap_millions": 5000.0},
    }

    rows = _screener(tmp_path, as_of_date=as_of, fundamentals=fundamentals).screen(str(watchlist))

    assert len(rows) == 1
    assert rows[0].implied_pos == 0.99


def test_csv_output_written_correctly(tmp_path: Path) -> None:
    as_of = date(2026, 4, 5)
    cfg = _write_asset_config(tmp_path / "csv.yaml", asset_id="asset-csv", ticker="CSV")
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        entries=[_make_entry("asset-csv", "CSV", cfg)],
        knowledge_db_path=tmp_path / "knowledge.db",
    )
    screener = _screener(
        tmp_path,
        as_of_date=as_of,
        fundamentals={"CSV": {"market_cap_millions": 200.0}},
    )

    rows = screener.screen(str(watchlist))

    assert len(rows) == 1
    assert screener.last_csv_path is not None
    assert screener.last_csv_path.exists()
    with screener.last_csv_path.open("r", encoding="utf-8", newline="") as handle:
        saved_rows = list(csv.DictReader(handle))
    assert len(saved_rows) == 1
    assert saved_rows[0]["ticker"] == "CSV"
    assert saved_rows[0]["asset_id"] == "asset-csv"


def test_clinical_stage_extracted_from_config(tmp_path: Path) -> None:
    as_of = date(2026, 4, 5)
    cfg = _write_asset_config(
        tmp_path / "phase3.yaml",
        asset_id="asset-phase3",
        ticker="PH3",
        stage="phase_3",
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        entries=[_make_entry("asset-phase3", "PH3", cfg)],
        knowledge_db_path=tmp_path / "knowledge.db",
    )

    rows = _screener(
        tmp_path,
        as_of_date=as_of,
        fundamentals={"PH3": {"market_cap_millions": 220.0}},
    ).screen(str(watchlist))

    assert len(rows) == 1
    assert rows[0].clinical_stage == "Phase 3"


def test_next_catalyst_populated_from_catalyst_events_if_available(tmp_path: Path) -> None:
    as_of = date(2026, 4, 5)
    knowledge_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(str(knowledge_path))
    try:
        store.upsert_catalyst_event(
            CatalystEvent(
                asset_id="asset-cat",
                company_id="co-asset-cat",
                catalyst_type=CatalystType.TRIAL_READOUT,
                expected_date=as_of + timedelta(days=45),
                date_confidence="exact",
                source="unit_test",
                description="Phase 3 readout",
            )
        )
    finally:
        store.close()

    cfg = _write_asset_config(tmp_path / "cat.yaml", asset_id="asset-cat", ticker="CAT")
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        entries=[_make_entry("asset-cat", "CAT", cfg)],
        knowledge_db_path=knowledge_path,
    )

    rows = _screener(
        tmp_path,
        as_of_date=as_of,
        fundamentals={"CAT": {"market_cap_millions": 180.0}},
    ).screen(str(watchlist))

    assert len(rows) == 1
    assert rows[0].next_catalyst == "Phase 3 readout"
    assert rows[0].days_to_catalyst == 45


def test_persist_screen_snapshots_writes_rows_to_knowledge_store(tmp_path: Path) -> None:
    as_of = date(2026, 4, 5)
    knowledge_path = tmp_path / "persisted_knowledge.db"
    cfg = _write_asset_config(
        tmp_path / "persist.yaml",
        asset_id="asset-persist",
        ticker="PST",
        config_quality="screening_grade",
    )
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        entries=[_make_entry("asset-persist", "PST", cfg)],
        knowledge_db_path=knowledge_path,
    )
    screener = _screener(
        tmp_path,
        as_of_date=as_of,
        fundamentals={"PST": {"market_cap_millions": 220.0}},
        knowledge_db_path=knowledge_path,
        persist_screen_snapshots=True,
    )

    rows = screener.screen(str(watchlist))

    assert len(rows) == 1
    assert knowledge_path.exists()
    store = KnowledgeStore(str(knowledge_path))
    try:
        persisted = store.get_screen_snapshots(snapshot_date=as_of)
    finally:
        store.close()
    assert len(persisted) == 1
    assert persisted[0]["ticker"] == "PST"
    assert persisted[0]["program_label"] == "asset-persist"
    assert persisted[0]["stage"] == "Phase 2"
    assert persisted[0]["market_exceeds_model"] == 0
    assert persisted[0]["config_quality"] == "screening_grade"


def test_use_stored_snapshots_loads_latest_on_or_before_as_of(tmp_path: Path) -> None:
    as_of = date(2026, 4, 5)
    snapshot_date = date(2026, 4, 3)
    knowledge_path = tmp_path / "snapshots.db"
    store = KnowledgeStore(str(knowledge_path))
    try:
        store.write_screen_snapshots(
            [
                ScreenRow(
                    ticker="STO",
                    program_label="asset-stored",
                    stage="phase_2",
                    ta="oncology",
                    model_pos=0.55,
                    implied_pos=0.33,
                    spread_pp=22.0,
                    rnpv_millions=480.0,
                    ev_millions=290.0,
                    acquisition_discount_pct=65.5,
                    next_catalyst="Phase 2 data",
                    catalyst_date=None,
                    days_to_catalyst=30,
                    single_asset=True,
                    approximation_warning=None,
                    data_date=snapshot_date,
                    thesis_strength=None,
                    market_exceeds_model=True,
                    config_quality="screening_grade",
                )
            ],
            snapshot_date=snapshot_date,
        )
    finally:
        store.close()

    cfg = _write_asset_config(tmp_path / "stored.yaml", asset_id="asset-stored", ticker="STO")
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        entries=[_make_entry("asset-stored", "STO", cfg)],
        knowledge_db_path=knowledge_path,
    )
    screener = _screener(
        tmp_path,
        as_of_date=as_of,
        fundamentals={},
        knowledge_db_path=knowledge_path,
        prefer_stored_snapshots=True,
    )

    rows = screener.screen(str(watchlist))

    assert len(rows) == 1
    assert rows[0].ticker == "STO"
    assert rows[0].asset_id == "asset-stored"
    assert rows[0].clinical_stage == "Phase 2"
    assert rows[0].acquisition_discount == 1.655
    assert rows[0].market_exceeds_model is True
    assert rows[0].config_quality == "screening_grade"
    assert screener.last_resolved_snapshot_date == snapshot_date


def test_company_recency_gate_excludes_asset_from_live_screen(tmp_path: Path) -> None:
    as_of = date(2026, 4, 5)
    knowledge_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(str(knowledge_path))
    try:
        _write_company_snapshot(
            store,
            ticker="AAA",
            snapshot_date=date(2026, 4, 1),
            passes_gate=False,
            action_policy="needs_manual_review",
            action_reason="balance_sheet_recency_gate_failed",
        )
    finally:
        store.close()

    cfg = _write_asset_config(tmp_path / "a.yaml", asset_id="asset-a", ticker="AAA")
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        entries=[_make_entry("asset-a", "AAA", cfg)],
        knowledge_db_path=knowledge_path,
    )

    screener = _screener(
        tmp_path,
        as_of_date=as_of,
        fundamentals={"AAA": {"market_cap_millions": 180.0}},
        knowledge_db_path=knowledge_path,
    )
    rows = screener.screen(str(watchlist))

    assert rows == []
    assert screener.last_company_gate_exclusions == [
        {"ticker": "AAA", "reason": "company_recency_gate_failed"}
    ]


def test_company_snapshot_metadata_is_attached_to_screen_rows(tmp_path: Path) -> None:
    as_of = date(2026, 4, 5)
    knowledge_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(str(knowledge_path))
    try:
        _write_company_snapshot(
            store,
            ticker="AAA",
            snapshot_date=date(2026, 4, 1),
            passes_gate=True,
            action_policy="watch",
            action_reason="ranked_discount_above_watch_threshold:1.20x",
        )
    finally:
        store.close()

    cfg = _write_asset_config(tmp_path / "a.yaml", asset_id="asset-a", ticker="AAA")
    watchlist = _write_watchlist(
        tmp_path / "watchlist.yaml",
        entries=[_make_entry("asset-a", "AAA", cfg)],
        knowledge_db_path=knowledge_path,
    )

    rows = _screener(
        tmp_path,
        as_of_date=as_of,
        fundamentals={"AAA": {"market_cap_millions": 180.0}},
        knowledge_db_path=knowledge_path,
    ).screen(str(watchlist))

    assert len(rows) == 1
    assert rows[0].company_action_policy == "watch"
    assert rows[0].company_action_reason == "ranked_discount_above_watch_threshold:1.20x"
    assert rows[0].company_snapshot_date == date(2026, 4, 1)
    assert rows[0].company_recency_gate_failed is False
