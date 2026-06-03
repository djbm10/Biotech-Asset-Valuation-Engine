"""
ThesisClaimsBackfiller — seeds historical thesis claims into the replay KB.

Reads ``research/replay/thesis_claims_history.yaml`` and inserts claim records
with accurate ``created_at`` and ``resolved_at`` timestamps so
``ThesisTracker.snapshot(as_of_date=...)`` correctly reflects conviction state
at each replay week (no-lookahead).

Each YAML entry becomes one ``thesis_claims`` row.  The operation is
idempotent: rows with an existing ``claim_id`` (derived from
``ticker:YYYY-MM-DD:N``) are skipped.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import sqlite3

import yaml

from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker


class _MinimalStore:
    """
    Minimal KnowledgeStore shim that exposes only ``_conn``.

    ThesisTracker requires a store object with a ``_conn`` attribute.
    This shim opens the SQLite file directly (bypassing KnowledgeStore's
    full schema migration) and row_factory for dict-like access.
    """

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()


_DEFAULT_YAML = (
    Path(__file__).parents[3] / "research" / "replay" / "thesis_claims_history.yaml"
)


class ThesisClaimsBackfiller:
    """
    Seeds historical thesis claim rows into a KnowledgeStore path.

    Parameters
    ----------
    ks_path:
        Path to the target SQLite database (typically replay_store.sqlite).
    yaml_path:
        Path to the claims YAML.  Defaults to
        ``research/replay/thesis_claims_history.yaml``.
    dry_run:
        When True, validate the YAML and print what would be inserted but
        make no DB changes.
    """

    def __init__(
        self,
        ks_path: str,
        *,
        yaml_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> None:
        self._ks_path = ks_path
        self._yaml_path = yaml_path or _DEFAULT_YAML
        self._dry_run = dry_run

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> list[dict]:
        """Parse and validate the YAML file.  Returns raw claim dicts."""
        with open(self._yaml_path) as fh:
            data = yaml.safe_load(fh)
        claims = data.get("claims", [])
        for i, c in enumerate(claims):
            for field in ("ticker", "asset_id", "company_id", "claim_type",
                          "assertion", "created_at", "resolved_at", "status"):
                if field not in c:
                    raise ValueError(f"Claim[{i}] missing field '{field}'")
            if c["status"] not in ("confirmed", "refuted", "expired"):
                raise ValueError(
                    f"Claim[{i}] ({c['ticker']}): invalid status '{c['status']}'; "
                    "must be confirmed | refuted | expired"
                )
            # Parse dates early to catch malformed values
            datetime.fromisoformat(c["created_at"])
            datetime.fromisoformat(c["resolved_at"])
        return claims

    def seed(self) -> dict[str, int]:
        """
        Insert claims into the KnowledgeStore.

        Returns a summary dict with ``inserted``, ``skipped`` counts.
        """
        claims = self.load()

        if self._dry_run:
            print(f"[dry-run] Would insert up to {len(claims)} claims from "
                  f"{self._yaml_path}")
            for c in claims:
                print(f"  {c['ticker']:6s}  {c['status']:10s}  "
                      f"{c['created_at']} → {c['resolved_at']}  "
                      f"{c['assertion'][:60]}...")
            return {"inserted": 0, "skipped": len(claims)}

        ks = _MinimalStore(self._ks_path)
        tt = ThesisTracker(ks)

        # Build set of (asset_id, assertion_digest) already seeded for idempotency
        existing_keys: set[str] = set()
        rows = ks._conn.execute(
            "SELECT asset_id, assertion FROM thesis_claims"
        ).fetchall()
        for row in rows:
            r = dict(row)
            existing_keys.add(_entry_key(r["asset_id"], r["assertion"]))

        inserted = 0
        skipped = 0

        for entry in claims:
            key = _entry_key(entry["asset_id"], entry["assertion"].strip())
            if key in existing_keys:
                skipped += 1
                continue

            created_dt = datetime.fromisoformat(entry["created_at"]).replace(
                tzinfo=timezone.utc
            )
            resolved_dt = datetime.fromisoformat(entry["resolved_at"]).replace(
                tzinfo=timezone.utc
            )

            claim_type_val = entry["claim_type"]
            try:
                ct = ClaimType(claim_type_val)
            except ValueError:
                # Accept snake_case names as fallback
                ct = ClaimType[claim_type_val.upper()]

            evidence = entry.get("evidence", "").strip()

            # 1. Add claim as "open" with correct created_at; returns ThesisClaim
            claim = tt.add_claim(
                asset_id=entry["asset_id"],
                company_id=entry["company_id"],
                claim_type=ct,
                assertion=entry["assertion"].strip(),
                created_at=created_dt,
            )

            # 2. Resolve with the correct resolved_at date
            tt.resolve_claim(
                claim_id=claim.claim_id,
                status=entry["status"],
                evidence=evidence,
                resolved_at=resolved_dt,
            )

            inserted += 1
            existing_keys.add(key)

        ks.close()
        return {"inserted": inserted, "skipped": skipped}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry_key(asset_id: str, assertion: str) -> str:
    """Stable dedup key: SHA-1 of asset_id + assertion text."""
    raw = f"{asset_id}|{assertion}"
    return hashlib.sha1(raw.encode()).hexdigest()[:20]
