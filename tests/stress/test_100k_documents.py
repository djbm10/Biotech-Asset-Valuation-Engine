from __future__ import annotations

from time import perf_counter

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.load_generator import LoadGenerator


def test_stress_100k_documents_dedup_lookup_latency(tmp_path):
    db_path = tmp_path / "stress_100k_documents.db"
    store = KnowledgeStore(db_path)
    try:
        generator = LoadGenerator(store)
        asset_ids = generator.seed_assets(100)
        generator.seed_documents(100_000, asset_ids)

        row = store._conn.execute("SELECT COUNT(*) AS n FROM raw_documents").fetchone()
        assert int(row["n"]) == 100_000

        doc_ids = [
            r["id"]
            for r in store._conn.execute("SELECT id FROM raw_documents ORDER BY id").fetchall()
        ]
        started = perf_counter()
        for doc_id in doc_ids:
            assert store.raw_document_exists(str(doc_id))
        elapsed = perf_counter() - started
        avg_ms_per_doc = (elapsed * 1000.0) / len(doc_ids)
        assert avg_ms_per_doc <= 10.0, (
            "Scenario B failed: dedup check slower than 10ms/doc "
            f"(avg={avg_ms_per_doc:.4f}ms over {len(doc_ids)} docs)"
        )
    finally:
        store.close()
