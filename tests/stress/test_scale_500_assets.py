from __future__ import annotations

import statistics
from datetime import datetime, timezone
from time import perf_counter

from bve.intelligence.opportunity_scanner import OpportunityScanner, OpportunityScannerConfig
from bve.intelligence.ranking import RankingConfig
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.load_generator import LoadGenerator
from bve.pipeline.watchlist_runner import WatchlistAsset, WatchlistRunnerConfig


def _company_id_for_asset(asset_id: str) -> str:
    if asset_id.startswith("stress-asset-"):
        return asset_id.replace("stress-asset-", "stress-company-", 1)
    return f"company-{asset_id}"


def test_stress_scale_500_assets_p95_scan_time(tmp_path):
    db_path = tmp_path / "stress_scale_500_assets.db"
    store = KnowledgeStore(db_path)
    try:
        generator = LoadGenerator(store)
        seed_assets_started = perf_counter()
        asset_ids = generator.seed_assets(500)
        seed_assets_seconds = perf_counter() - seed_assets_started
        assert seed_assets_seconds < 10.0, f"seed_assets too slow: {seed_assets_seconds:.3f}s"

        generator.seed_signals(10_000, asset_ids)
        signal_rows = store._conn.execute(
            "SELECT COUNT(*) AS n FROM structured_signals"
        ).fetchone()["n"]
        assert int(signal_rows) >= 10_000

        watchlist = [
            WatchlistAsset(
                company_id=_company_id_for_asset(asset_id),
                asset_id=asset_id,
                ticker=f"T{idx:04d}",
                market_cap_millions=1_000.0 + float(idx),
            )
            for idx, asset_id in enumerate(asset_ids, start=1)
        ]
        watchlist_config = WatchlistRunnerConfig(
            polling_interval_seconds=60,
            watchlist=watchlist,
            ranking=RankingConfig(use_calibration_file=False, top_n=500),
        )
        scanner = OpportunityScanner(
            knowledge_store=store,
            config=OpportunityScannerConfig(
                min_composite_score=0.0,
                min_abs_mispricing_pct=0.0,
                top_n=500,
            ),
        )
        scanned_at = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)

        total_started = perf_counter()
        scanner.scan_from_watchlist_config(
            watchlist_config,
            run_id="stress-scenario-a-full",
            scanned_at=scanned_at,
        )
        total_runtime_seconds = perf_counter() - total_started

        per_asset_scan_seconds: list[float] = []
        for asset in watchlist:
            single_cfg = watchlist_config.model_copy(update={"watchlist": [asset]})
            t0 = perf_counter()
            scanner.scan_from_watchlist_config(
                single_cfg,
                run_id=f"stress-scenario-a-{asset.asset_id}",
                scanned_at=scanned_at,
            )
            per_asset_scan_seconds.append(perf_counter() - t0)

        p95_seconds = statistics.quantiles(per_asset_scan_seconds, n=100, method="inclusive")[94]
        median_seconds = statistics.median(per_asset_scan_seconds)
        max_seconds = max(per_asset_scan_seconds)
        assert p95_seconds <= 2.0, (
            "Scenario A failed: per-asset p95 scan time exceeded 2s "
            f"(p95={p95_seconds:.3f}s, median={median_seconds:.3f}s, "
            f"max={max_seconds:.3f}s, total_runtime={total_runtime_seconds:.3f}s)"
        )
    finally:
        store.close()
