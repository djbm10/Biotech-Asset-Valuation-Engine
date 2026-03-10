from __future__ import annotations

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.load_generator import LoadGenerator


def _company_id_for_asset(asset_id: str) -> str:
    if asset_id.startswith("stress-asset-"):
        return asset_id.replace("stress-asset-", "stress-company-", 1)
    return f"company-{asset_id}"


def _query_plan_details(
    store: KnowledgeStore, sql: str, params: tuple[object, ...]
) -> tuple[str, ...]:
    rows = store._conn.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()
    return tuple(str(row["detail"]) for row in rows)


def test_stress_history_replay_365_cycles_query_plan_and_size(tmp_path):
    db_path = tmp_path / "stress_history_replay.db"
    store = KnowledgeStore(db_path)
    try:
        generator = LoadGenerator(store)
        asset_ids = generator.seed_assets(100)

        # Cycle 1 (baseline), then capture initial query plan.
        generator.seed_documents(100, asset_ids)
        generator.seed_signals(100, asset_ids)
        anchor_asset = asset_ids[0]
        anchor_company = _company_id_for_asset(anchor_asset)
        query = """
        SELECT id
        FROM structured_signals
        WHERE company_id = ? AND asset_id = ?
        ORDER BY signal_date DESC
        LIMIT 20
        """
        initial_plan = _query_plan_details(store, query, (anchor_company, anchor_asset))
        assert any("idx_signals_company_asset" in detail for detail in initial_plan)

        # Remaining 364 cycles to reach full 365-day replay.
        for _ in range(364):
            generator.seed_documents(100, asset_ids)
            generator.seed_signals(100, asset_ids)

        final_plan = _query_plan_details(store, query, (anchor_company, anchor_asset))
        assert final_plan == initial_plan, (
            "Scenario D failed: final query plan degraded "
            f"(initial={initial_plan}, final={final_plan})"
        )

        size_mb = db_path.stat().st_size / (1024.0 * 1024.0)
        assert size_mb < 500.0, f"Scenario D failed: DB file exceeded 500MB (size={size_mb:.2f}MB)"
    finally:
        store.close()
