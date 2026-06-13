"""Persistence for canonical company profiles (hybrid: SQLite truth + YAML export).

SQLite is the source of truth. A YAML snapshot per ticker is exported for
diff/review. ``ProfileStore`` manages its own additive ``asset_profiles`` table
(``CREATE TABLE IF NOT EXISTS``) inside the shared intelligence DB, so it adds
zero risk to the existing ``KnowledgeStore`` class. It can be folded into
``KnowledgeStore`` later without changing the on-disk schema.

The profile model holds only public facts, so the YAML export is inherently
shareable — confidential analyst inputs live in a separate override file and
never reach this store.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from bve.pipeline.asset_profile import CompanyProfile

_DEFAULT_DB = "outputs/intelligence/ops.db"
_DEFAULT_EXPORT_DIR = "profiles"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS asset_profiles (
    ticker          TEXT PRIMARY KEY,
    company_id      TEXT,
    name            TEXT,
    lead_asset_id   TEXT,
    evidence_level  TEXT,
    profile_json    TEXT NOT NULL,
    source          TEXT,
    updated_at      TEXT NOT NULL
);
"""


class ProfileStore:
    """Upsert / get / export canonical :class:`CompanyProfile` records."""

    def __init__(self, db_path: str | Path = _DEFAULT_DB) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ProfileStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── persistence ───────────────────────────────────────────────────────

    def upsert(self, profile: CompanyProfile) -> None:
        """Insert or replace the profile keyed by (uppercased) ticker."""
        lead_asset_id = profile.assets[0].asset_id if profile.assets else None
        self._conn.execute(
            """
            INSERT OR REPLACE INTO asset_profiles(
                ticker, company_id, name, lead_asset_id,
                evidence_level, profile_json, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile.ticker.upper(),
                profile.company_id,
                profile.name,
                lead_asset_id,
                profile.evidence_level,
                json.dumps(profile.model_dump(), ensure_ascii=False),
                profile.source,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def get(self, ticker: str) -> Optional[CompanyProfile]:
        row = self._conn.execute(
            "SELECT profile_json FROM asset_profiles WHERE ticker = ? LIMIT 1",
            (ticker.upper(),),
        ).fetchone()
        if row is None:
            return None
        return CompanyProfile.model_validate(json.loads(row["profile_json"]))

    def list_tickers(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT ticker FROM asset_profiles ORDER BY ticker"
        ).fetchall()
        return [r["ticker"] for r in rows]

    # ── YAML export (public snapshot for review/diff) ─────────────────────

    def export_yaml(
        self,
        ticker: str,
        out_dir: str | Path = _DEFAULT_EXPORT_DIR,
    ) -> Path:
        """Write ``<out_dir>/<TICKER>.yaml`` from the stored profile; return path."""
        profile = self.get(ticker)
        if profile is None:
            raise KeyError(f"No stored profile for ticker {ticker!r}")
        out_path = Path(out_dir) / f"{ticker.upper()}.yaml"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            yaml.safe_dump(profile.model_dump(), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return out_path
