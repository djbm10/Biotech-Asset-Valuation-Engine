"""Synthetic data seeding helpers for large-scale stress tests."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Sequence

from bve.intelligence.knowledge_layer import KnowledgeStore


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _company_id_for_asset(asset_id: str) -> str:
    if asset_id.startswith("stress-asset-"):
        return asset_id.replace("stress-asset-", "stress-company-", 1)
    return f"company-{asset_id}"


class LoadGenerator:
    """Bulk seed synthetic assets/signals/documents/competitor programs."""

    def __init__(self, store: KnowledgeStore) -> None:
        self._store = store
        self._asset_seq = 0
        self._signal_seq = 0
        self._doc_seq = 0
        self._program_seq = 0

    def seed_assets(self, n: int) -> list[str]:
        if n <= 0:
            return []
        created_at = _utcnow_iso()
        rows: list[tuple[str, str, str, str, str, str, str, str, str, float, str, str, None]] = []
        asset_ids: list[str] = []
        for _ in range(n):
            self._asset_seq += 1
            seq = self._asset_seq
            asset_id = f"stress-asset-{seq:06d}"
            company_id = f"stress-company-{seq:06d}"
            ticker = f"S{seq:05d}"
            asset_ids.append(asset_id)
            rows.append(
                (
                    asset_id,
                    ticker,
                    company_id,
                    f"StressDrug{seq:06d}",
                    f"StressIndication{seq % 20:02d}",
                    "oncology" if seq % 2 == 0 else "immunology",
                    "small_molecule" if seq % 2 == 0 else "biologic",
                    "phase_2" if seq % 3 else "phase_3",
                    f"NCT{seq:08d}",
                    500.0 + float(seq % 250),
                    created_at,
                    "stress_load_generator",
                    None,
                )
            )

        self._store._conn.executemany(
            """
            INSERT OR REPLACE INTO asset_registry(
                asset_id, ticker, company_id, drug_name, indication, therapeutic_area,
                modality, stage, nct_id, tam_millions, created_at, source,
                last_competitor_discovery_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._store._conn.commit()
        return asset_ids

    def seed_signals(self, n: int, asset_ids: Sequence[str]) -> None:
        if n <= 0 or not asset_ids:
            return
        created_at = _utcnow_iso()
        signal_date = date.today().isoformat()
        source_trace = json.dumps(
            {
                "source_type": "stress",
                "source_ref": "load_generator.seed_signals",
                "ingested_at": created_at,
            },
            ensure_ascii=True,
        )
        rows: list[tuple[str, str, str, str, str, str, str, str, str, str]] = []
        for i in range(n):
            self._signal_seq += 1
            seq = self._signal_seq
            asset_id = str(asset_ids[i % len(asset_ids)])
            company_id = _company_id_for_asset(asset_id)
            signal_id = f"stress-signal-{seq:09d}"
            event_id = f"stress-event-{seq:09d}"
            extraction_result_id = f"stress-extract-{seq:09d}"
            payload = json.dumps(
                {
                    "id": signal_id,
                    "event_id": event_id,
                    "company_id": company_id,
                    "asset_id": asset_id,
                    "event_type": "trial_readout",
                    "signal_date": signal_date,
                    "extraction_confidence": 0.75,
                    "trial_phase": "phase_2",
                    "created_at": created_at,
                },
                ensure_ascii=True,
            )
            rows.append(
                (
                    signal_id,
                    extraction_result_id,
                    event_id,
                    company_id,
                    asset_id,
                    "trial_readout",
                    signal_date,
                    created_at,
                    payload,
                    source_trace,
                )
            )

        self._store._conn.executemany(
            """
            INSERT OR REPLACE INTO structured_signals(
                id, extraction_result_id, event_id, company_id, asset_id,
                event_type, signal_date, created_at, payload_json, source_trace_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._store._conn.commit()

    def seed_documents(self, n: int, asset_ids: Sequence[str]) -> None:
        if n <= 0 or not asset_ids:
            return
        created_at = _utcnow_iso()
        source = "stress_feed"
        source_trace = json.dumps(
            {
                "source_type": "stress",
                "source_ref": "load_generator.seed_documents",
                "ingested_at": created_at,
            },
            ensure_ascii=True,
        )
        rows: list[tuple[str, str, str, str, str, str, str]] = []
        for i in range(n):
            self._doc_seq += 1
            seq = self._doc_seq
            asset_id = str(asset_ids[i % len(asset_ids)])
            company_id = _company_id_for_asset(asset_id)
            doc_id = f"stress-doc-{seq:09d}"
            doc_hash = hashlib.sha256(f"stress-doc-{seq}".encode("utf-8")).hexdigest()
            payload = json.dumps(
                {
                    "id": doc_id,
                    "source": source,
                    "title": f"Synthetic Doc {seq}",
                    "raw_text": f"Synthetic payload {seq}",
                    "source_url": f"https://stress.local/doc/{seq}",
                    "retrieved_at": created_at,
                    "document_hash": doc_hash,
                    "entity_hints": {
                        "asset_id": asset_id,
                        "company_id": company_id,
                    },
                },
                ensure_ascii=True,
            )
            rows.append(
                (
                    doc_id,
                    created_at,
                    source,
                    doc_hash,
                    f"https://stress.local/doc/{seq}",
                    payload,
                    source_trace,
                )
            )

        self._store._conn.executemany(
            """
            INSERT OR IGNORE INTO raw_documents(
                id, created_at, source, document_hash, source_url, payload_json, source_trace_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._store._conn.commit()

    def seed_competitor_programs(self, n_per_asset: int, asset_ids: Sequence[str]) -> None:
        if n_per_asset <= 0 or not asset_ids:
            return
        discovered_at = _utcnow_iso()
        rows: list[tuple[str, str, str, str, str, str, str, str, str, str]] = []
        for asset_id in asset_ids:
            for _ in range(n_per_asset):
                self._program_seq += 1
                seq = self._program_seq
                rows.append(
                    (
                        f"stress-program-{seq:09d}",
                        str(asset_id),
                        f"CompetitorCo{seq:05d}",
                        f"CompDrug{seq:06d}",
                        f"NCT{seq + 10_000_000:08d}",
                        "phase_2",
                        "active",
                        "primary",
                        f"StressIndication{seq % 20:02d}",
                        discovered_at,
                    )
                )

        self._store._conn.executemany(
            """
            INSERT OR IGNORE INTO competitor_programs(
                program_id, asset_id, company, drug_name, nct_id, phase,
                status, primary_endpoint_type, indication, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._store._conn.commit()
