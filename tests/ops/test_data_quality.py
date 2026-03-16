from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from bve.connectors.market_prices import MarketPriceRecord
from bve.entities.trial import TrialPhase
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.knowledge_layer import AssetRegistryEntry, KnowledgeStore, SourceTrace
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType
from bve.ops.data_quality import DataQualityMonitor


def _trace(ref: str) -> SourceTrace:
    return SourceTrace(
        source_type="unit_test",
        source_ref=ref,
        ingested_at=datetime.now(timezone.utc),
    )


def test_data_quality_empty_db_returns_full_score() -> None:
    store = KnowledgeStore(":memory:")
    try:
        monitor = DataQualityMonitor(store)
        score = monitor.check_asset("asset-empty")
        assert score.overall_score == 1.0
        assert score.gated is False
        assert len(score.checks) == 6
        assert score.failing_checks == []
    finally:
        store.close()


def test_data_quality_fails_when_inputs_are_stale_and_noisy() -> None:
    store = KnowledgeStore(":memory:")
    try:
        monitor = DataQualityMonitor(store)
        asset_id = "asset-bad"
        now = datetime.now(timezone.utc)
        store.upsert_asset_registry_entry(
            AssetRegistryEntry(
                asset_id=asset_id,
                ticker="BADX",
                source="unit_test",
            )
        )

        # Old docs: fail freshness and 7d-volume checks.
        for i in range(2):
            doc = RawDocument.from_text(
                id=f"doc-{i}",
                source="press_release",
                title=f"Doc {i}",
                raw_text=f"payload {i}",
                source_url=f"https://example.org/{i}",
                retrieved_at=now - timedelta(days=10),
                entity_hints=EntityHints(asset_id=asset_id, company_id="company-1"),
            )
            store.add_raw_document(doc, _trace(f"doc-{i}"))

        # Low-confidence signal with no delta_npv_millions field.
        signal = StructuredSignal(
            id="sig-1",
            event_id="evt-1",
            asset_id=asset_id,
            company_id="company-1",
            event_type=EventType.TRIAL_READOUT,
            signal_date=date.today(),
            trial_phase=TrialPhase.PHASE_2,
            extraction_confidence=0.2,
            created_at=now,
        )
        store.add_structured_signal(
            signal,
            _trace("signal"),
            extraction_result_id="extract-1",
        )

        # 5/20 connector failures => 25% error rate.
        for i in range(20):
            status = "failure" if i < 5 else "success"
            started = now - timedelta(minutes=20 - i)
            store.mark_run_state_finished(
                run_id=f"run-{i}",
                stage="fetch:press_release",
                asset_id=asset_id,
                status=status,  # type: ignore[arg-type]
                started_at=started,
                finished_at=started + timedelta(seconds=1),
                checkpoint_json={},
                error_json={"error": "x"} if status == "failure" else {},
            )

        score = monitor.check_asset(asset_id)
        assert score.gated is True
        assert score.overall_score < 0.50
        assert "doc_freshness" in score.failing_checks
        assert "confidence_trend_30d" in score.failing_checks
        assert "clinical_metadata_completeness" in score.failing_checks
        assert "connector_error_rate" in score.failing_checks
        # Ticker is registered but no price data exists yet — this is a soft warning,
        # not a hard failure (prevents permanent gating before the price fetcher runs).
        assert "market_data_freshness" not in score.failing_checks
    finally:
        store.close()


def test_data_quality_market_freshness_passes_when_no_price_data_yet() -> None:
    """Ticker registered but no prices fetched yet → soft warning, not a gate blocker."""
    store = KnowledgeStore(":memory:")
    try:
        monitor = DataQualityMonitor(store)
        asset_id = "asset-no-prices"
        store.upsert_asset_registry_entry(
            AssetRegistryEntry(asset_id=asset_id, ticker="NEWX", source="unit_test")
        )
        score = monitor.check_asset(asset_id)
        market_check = next(c for c in score.checks if c.check_type == "market_data_freshness")
        assert market_check.passed is True
        assert market_check.reason == "no_market_price_data_yet"
        assert market_check.severity == "warning"
        assert "market_data_freshness" not in score.failing_checks
        assert score.gated is False
    finally:
        store.close()


def test_data_quality_market_freshness_fails_when_prices_are_stale() -> None:
    """Ticker registered and prices exist but are older than 3 days → hard failure."""
    store = KnowledgeStore(":memory:")
    try:
        monitor = DataQualityMonitor(store)
        asset_id = "asset-stale-prices"
        store.upsert_asset_registry_entry(
            AssetRegistryEntry(asset_id=asset_id, ticker="STALX", source="unit_test")
        )
        stale_date = date.today() - timedelta(days=10)
        store.upsert_market_prices(
            [
                MarketPriceRecord(
                    ticker="STALX",
                    price_date=stale_date,
                    close_usd=10.0,
                    adj_close_usd=10.0,
                    volume=1000,
                    market_cap_millions=100.0,
                )
            ]
        )
        score = monitor.check_asset(asset_id)
        market_check = next(c for c in score.checks if c.check_type == "market_data_freshness")
        assert market_check.passed is False
        assert market_check.reason == "stale_market_data"
        assert "market_data_freshness" in score.failing_checks
    finally:
        store.close()


def test_data_quality_log_round_trip() -> None:
    store = KnowledgeStore(":memory:")
    try:
        monitor = DataQualityMonitor(store)
        score = monitor.check_asset("asset-1")
        store.log_data_quality(score, run_id="run-abc")
        latest = store.get_latest_data_quality("asset-1")
        assert latest is not None
        assert latest.asset_id == "asset-1"
        assert latest.overall_score == score.overall_score
        assert len(latest.checks) == 6
        rows = store.list_latest_data_quality()
        assert [row.asset_id for row in rows] == ["asset-1"]
        db_rows = store._conn.execute(
            """
            SELECT run_id, asset_id, check_name, status, severity, reason, checked_at
            FROM data_quality_log
            WHERE asset_id = ?
            """,
            ("asset-1",),
        ).fetchall()
        assert db_rows
        assert all(str(row["run_id"]) == "run-abc" for row in db_rows)
        assert all(row["checked_at"] for row in db_rows)
        assert all(row["check_name"] for row in db_rows)
    finally:
        store.close()


def test_data_quality_log_schema_has_run_id_and_indexes() -> None:
    store = KnowledgeStore(":memory:")
    try:
        cols = {
            row["name"]
            for row in store._conn.execute("PRAGMA table_info(data_quality_log)").fetchall()
        }
        assert {
            "id",
            "run_id",
            "asset_id",
            "check_name",
            "status",
            "severity",
            "reason",
            "checked_at",
        }.issubset(cols)

        indexes = {
            row["name"]
            for row in store._conn.execute("PRAGMA index_list(data_quality_log)").fetchall()
        }
        assert "idx_data_quality_asset_checked" in indexes
        assert "idx_data_quality_checked_at" in indexes
    finally:
        store.close()
