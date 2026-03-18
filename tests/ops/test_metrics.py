from __future__ import annotations

from bve.ops.metrics import RunMetrics, RunMetricsStore


def test_metrics_store_append_and_latest(tmp_path):
    store = RunMetricsStore(tmp_path / "run_metrics.json")
    m1 = RunMetrics(run_id="run-1", ingestion_docs=10, signals_extracted=3)
    m2 = RunMetrics(run_id="run-2", ingestion_docs=5, signals_extracted=2)
    store.append(m1)
    store.append(m2)

    all_rows = store.load_all()
    assert len(all_rows) == 2
    assert all_rows[0].run_id == "run-1"
    assert all_rows[1].run_id == "run-2"
    assert store.latest().run_id == "run-2"  # type: ignore[union-attr]
