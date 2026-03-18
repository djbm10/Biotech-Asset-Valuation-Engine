from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.load_generator import LoadGenerator


def _company_id_for_asset(asset_id: str) -> str:
    if asset_id.startswith("stress-asset-"):
        return asset_id.replace("stress-asset-", "stress-company-", 1)
    return f"company-{asset_id}"


@dataclass
class _WriterStats:
    attempts: int = 0
    inserted: int = 0
    lock_retries: int = 0


def _is_locked_error(exc: sqlite3.OperationalError) -> bool:
    return "locked" in str(exc).lower()


def test_stress_concurrent_writes_zero_loss_and_low_retry_rate(tmp_path):
    """Do not parallelize watchlist loop until Postgres migration; this validates sequential safety."""

    duration_seconds = int(os.getenv("BVE_STRESS_CONCURRENT_SECONDS", "60"))
    db_path = tmp_path / "stress_concurrent_writes.db"

    seed_store = KnowledgeStore(db_path)
    try:
        generator = LoadGenerator(seed_store)
        asset_ids = generator.seed_assets(50)
        seed_store._conn.execute("PRAGMA journal_mode=WAL")
        seed_store._conn.commit()
    finally:
        seed_store.close()

    deadline = time.perf_counter() + duration_seconds
    signal_a = _WriterStats()
    signal_b = _WriterStats()
    metrics = _WriterStats()

    def _signal_writer(writer_idx: int, out: _WriterStats) -> None:
        conn = sqlite3.connect(db_path, timeout=10.0)
        try:
            conn.execute("PRAGMA busy_timeout = 10000")
            i = 0
            source_trace = json.dumps(
                {
                    "source_type": "stress",
                    "source_ref": f"concurrent_signal_writer_{writer_idx}",
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=True,
            )
            signal_date = date.today().isoformat()
            while time.perf_counter() < deadline:
                i += 1
                out.attempts += 1
                asset_id = asset_ids[(i + writer_idx) % len(asset_ids)]
                created_at = datetime.now(timezone.utc).isoformat()
                signal_id = f"stress-signal-w{writer_idx}-{i:09d}"
                event_id = f"stress-event-w{writer_idx}-{i:09d}"
                payload = json.dumps(
                    {
                        "id": signal_id,
                        "event_id": event_id,
                        "company_id": _company_id_for_asset(asset_id),
                        "asset_id": asset_id,
                        "event_type": "trial_readout",
                        "signal_date": signal_date,
                        "created_at": created_at,
                        "extraction_confidence": 0.8,
                    },
                    ensure_ascii=True,
                )
                try:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO structured_signals(
                            id, extraction_result_id, event_id, company_id, asset_id,
                            event_type, signal_date, created_at, payload_json, source_trace_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            signal_id,
                            f"stress-extract-w{writer_idx}-{i:09d}",
                            event_id,
                            _company_id_for_asset(asset_id),
                            asset_id,
                            "trial_readout",
                            signal_date,
                            created_at,
                            payload,
                            source_trace,
                        ),
                    )
                    conn.commit()
                    out.inserted += 1
                except sqlite3.OperationalError as exc:
                    if _is_locked_error(exc):
                        out.lock_retries += 1
                        time.sleep(0.002)
                        continue
                    raise
        finally:
            conn.close()

    def _metrics_writer(out: _WriterStats) -> None:
        conn = sqlite3.connect(db_path, timeout=10.0)
        try:
            conn.execute("PRAGMA busy_timeout = 10000")
            i = 0
            while time.perf_counter() < deadline:
                i += 1
                out.attempts += 1
                asset_id = asset_ids[i % len(asset_ids)]
                run_id = f"stress-metrics-{i:09d}"
                started_at = datetime.now(timezone.utc).isoformat()
                try:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO run_state(
                            run_id, stage, asset_id, status, started_at, finished_at,
                            checkpoint_json, error_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            "stress_metrics",
                            asset_id,
                            "success",
                            started_at,
                            started_at,
                            "{}",
                            "{}",
                        ),
                    )
                    conn.commit()
                    out.inserted += 1
                except sqlite3.OperationalError as exc:
                    if _is_locked_error(exc):
                        out.lock_retries += 1
                        time.sleep(0.002)
                        continue
                    raise
        finally:
            conn.close()

    t1 = threading.Thread(target=_signal_writer, args=(1, signal_a), daemon=True)
    t2 = threading.Thread(target=_signal_writer, args=(2, signal_b), daemon=True)
    t3 = threading.Thread(target=_metrics_writer, args=(metrics,), daemon=True)
    t1.start()
    t2.start()
    t3.start()
    t1.join()
    t2.join()
    t3.join()

    verify_store = KnowledgeStore(db_path)
    try:
        signal_rows = verify_store._conn.execute(
            "SELECT COUNT(*) AS n FROM structured_signals WHERE id LIKE 'stress-signal-w%'"
        ).fetchone()
        metric_rows = verify_store._conn.execute(
            "SELECT COUNT(*) AS n FROM run_state WHERE stage = 'stress_metrics'"
        ).fetchone()
        inserted_signals = signal_a.inserted + signal_b.inserted
        inserted_metrics = metrics.inserted
        assert int(signal_rows["n"]) == inserted_signals
        assert int(metric_rows["n"]) == inserted_metrics

        total_attempts = signal_a.attempts + signal_b.attempts + metrics.attempts
        total_retries = signal_a.lock_retries + signal_b.lock_retries + metrics.lock_retries
        retry_rate = total_retries / max(total_attempts, 1)
        assert retry_rate <= 0.01, (
            "Scenario C failed: lock retry rate exceeded 1% "
            f"(retry_rate={retry_rate:.4%}, retries={total_retries}, attempts={total_attempts})"
        )
    finally:
        verify_store.close()
