"""Disposition write-back for the analyst review queue.

Closes the loop: an analyst resolves a review item and the correction is
preserved.

- approve: writes the corrected value into examples/configs/overrides/<TICKER>.yaml
  (the confidential_overrides that config_resolver already merges) AND logs the
  decision. Future runs use the analyst value and the name's evidence_level
  elevates coarse -> full.
- reject / defer: logs the decision only (no override).

Decisions are logged to a dedicated ``profile_review_decisions`` table in the
shared intelligence DB. (The existing ``review_decisions`` table is coupled to
the M&A *proposal* workflow — its reader strictly parses every row as a proposal
ReviewDecision — so a separate table keeps that workflow safe.)
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

_DEFAULT_DB = "outputs/intelligence/ops.db"
_DEFAULT_OVERRIDE_DIR = "examples/configs/overrides"
_VALID_ACTIONS = ("approve", "reject", "defer")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profile_review_decisions (
    id          TEXT PRIMARY KEY,
    ticker      TEXT NOT NULL,
    asset_id    TEXT,
    reason      TEXT NOT NULL,
    field       TEXT,
    action      TEXT NOT NULL,
    value       TEXT,
    rationale   TEXT,
    reviewer    TEXT,
    decided_at  TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class ReviewDispositionRecord:
    ticker: str
    asset_id: Optional[str]
    reason: str
    field: Optional[str]
    action: str
    value: Optional[str]
    rationale: Optional[str]
    reviewer: Optional[str]
    decided_at: str


class ProfileReviewStore:
    """Persist + query analyst dispositions for profile review items."""

    def __init__(self, db_path: str | Path = _DEFAULT_DB) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def record(self, rec: ReviewDispositionRecord) -> str:
        decision_id = str(uuid.uuid4())
        self._conn.execute(
            """
            INSERT INTO profile_review_decisions(
                id, ticker, asset_id, reason, field, action, value,
                rationale, reviewer, decided_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id, rec.ticker.upper(), rec.asset_id, rec.reason, rec.field,
                rec.action, rec.value, rec.rationale, rec.reviewer, rec.decided_at,
            ),
        )
        self._conn.commit()
        return decision_id

    def resolutions(self) -> dict[tuple[str, str], datetime]:
        """Latest decision time per (ticker, reason) — used to suppress resolved items."""
        rows = self._conn.execute(
            "SELECT ticker, reason, MAX(decided_at) AS decided_at "
            "FROM profile_review_decisions GROUP BY ticker, reason"
        ).fetchall()
        out: dict[tuple[str, str], datetime] = {}
        for r in rows:
            dt = _parse_iso(r["decided_at"])
            if dt is not None:
                out[(r["ticker"].upper(), r["reason"])] = dt
        return out

    def list_for(self, ticker: str) -> list[ReviewDispositionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM profile_review_decisions WHERE ticker = ? ORDER BY decided_at DESC",
            (ticker.upper(),),
        ).fetchall()
        return [
            ReviewDispositionRecord(
                ticker=r["ticker"], asset_id=r["asset_id"], reason=r["reason"], field=r["field"],
                action=r["action"], value=r["value"], rationale=r["rationale"],
                reviewer=r["reviewer"], decided_at=r["decided_at"],
            )
            for r in rows
        ]


def _parse_iso(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        text = iso.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except ValueError:
        return None


def parse_value(raw: str) -> Any:
    """Coerce a CLI string to int / float / bool / str."""
    low = raw.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    for cast in (int, float):
        try:
            return cast(raw)
        except ValueError:
            continue
    return raw


def _deep_set(root: dict, dotted: str, value: Any) -> None:
    """Set a dotted path into nested dicts/lists. Integer segments are list indices."""
    parts = dotted.split(".")
    node: Any = root
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        nxt = parts[i + 1] if not last else None
        if part.isdigit():
            idx = int(part)
            while len(node) <= idx:
                node.append({})
            if last:
                node[idx] = value
            else:
                if not isinstance(node[idx], (dict, list)):
                    node[idx] = [] if nxt.isdigit() else {}
                node = node[idx]
        else:
            if last:
                node[part] = value
            else:
                child = node.get(part)
                if not isinstance(child, (dict, list)):
                    child = [] if nxt.isdigit() else {}
                    node[part] = child
                node = child


def set_override(
    ticker: str,
    field_path: str,
    value: Any,
    *,
    override_dir: str | Path = _DEFAULT_OVERRIDE_DIR,
    rationale: Optional[str] = None,
    reviewer: Optional[str] = None,
) -> Path:
    """Write/merge a confidential override for ``field_path`` into <TICKER>.yaml."""
    out_path = Path(override_dir) / f"{ticker.upper()}.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = yaml.safe_load(out_path.read_text(encoding="utf-8")) if out_path.exists() else None
    if not isinstance(doc, dict):
        doc = {}
    doc.setdefault("confidential_overrides", {})
    _deep_set(doc["confidential_overrides"], field_path, value)
    meta = doc.setdefault("meta", {})
    meta["analyst"] = reviewer or meta.get("analyst", "analyst")
    meta["reviewed"] = datetime.now(timezone.utc).date().isoformat()
    if rationale:
        meta["rationale"] = rationale
    out_path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return out_path


def apply_decision(
    ticker: str,
    reason: str,
    action: str,
    *,
    field: Optional[str] = None,
    value: Any = None,
    rationale: Optional[str] = None,
    reviewer: Optional[str] = None,
    asset_id: Optional[str] = None,
    override_dir: str | Path = _DEFAULT_OVERRIDE_DIR,
    db_path: str | Path = _DEFAULT_DB,
) -> dict:
    """Apply an analyst disposition; returns a summary dict."""
    action = action.lower()
    if action not in _VALID_ACTIONS:
        raise ValueError(f"action must be one of {_VALID_ACTIONS}, got {action!r}")

    override_path: Optional[Path] = None
    if action == "approve":
        if not field or value is None:
            raise ValueError("approve requires --field and --value")
        override_path = set_override(
            ticker, field, value, override_dir=override_dir, rationale=rationale, reviewer=reviewer
        )

    store = ProfileReviewStore(db_path)
    try:
        store.record(
            ReviewDispositionRecord(
                ticker=ticker, asset_id=asset_id, reason=reason, field=field, action=action,
                value=None if value is None else str(value), rationale=rationale,
                reviewer=reviewer, decided_at=datetime.now(timezone.utc).isoformat(),
            )
        )
    finally:
        store.close()

    return {"action": action, "ticker": ticker.upper(), "reason": reason,
            "override_file": str(override_path) if override_path else None}
