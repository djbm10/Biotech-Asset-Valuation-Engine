"""
Evidence ledger manifest generator (Block 2I).

A manifest is a small JSON sidecar that captures:
  - SHA-256 checksum of the ledger file (detects silent corruption or substitution)
  - Record counts (total, by source, by ticker)
  - Date range (oldest_record / newest_record)
  - Run metadata (run_id, generated_at, as_of_date)

The manifest is written alongside the ledger on the data branch so that
any downstream consumer can verify integrity without re-reading the full file.

Usage::

    from bve.ingestion.ledger_manifest import LedgerManifest, generate_manifest

    manifest = generate_manifest(
        ledger_path="outputs/intelligence/evidence_ledger.jsonl",
        run_id="daily-2026-06-02",
        as_of_date="2026-06-02",
    )
    manifest.save("outputs/intelligence/ledger_manifest.json")
    print(manifest.sha256)
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class LedgerManifest:
    """Immutable snapshot of ledger state at a point in time."""

    # Provenance
    run_id: str
    generated_at: str           # ISO datetime
    as_of_date: str             # YYYY-MM-DD

    # File integrity
    ledger_path: str
    sha256: str                 # hex digest of the JSONL file bytes
    file_size_bytes: int

    # Record statistics
    total_records: int
    records_by_source: dict[str, int] = field(default_factory=dict)
    records_by_ticker: dict[str, int] = field(default_factory=dict)
    oldest_record: Optional[str] = None   # YYYY-MM-DD
    newest_record: Optional[str] = None   # YYYY-MM-DD

    # Schema version
    manifest_version: str = "1"

    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        """Write manifest as pretty JSON."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "LedgerManifest":
        """Load manifest from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)


def generate_manifest(
    ledger_path: str | Path,
    run_id: str,
    as_of_date: str,
) -> LedgerManifest:
    """
    Build a LedgerManifest by reading the ledger file.

    Parameters
    ----------
    ledger_path:
        Path to the JSONL file.
    run_id:
        Identifier for the run that produced this manifest (e.g. "daily-2026-06-02").
    as_of_date:
        ISO date string representing the logical as-of date for this run.
    """
    ledger_path = Path(ledger_path)

    if not ledger_path.exists() or ledger_path.stat().st_size == 0:
        return LedgerManifest(
            run_id=run_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            as_of_date=as_of_date,
            ledger_path=str(ledger_path),
            sha256=_sha256_of_empty(),
            file_size_bytes=0,
            total_records=0,
        )

    raw_bytes = ledger_path.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    file_size = len(raw_bytes)

    by_source: Counter[str] = Counter()
    by_ticker: Counter[str] = Counter()
    dates: list[str] = []
    total = 0

    for line in raw_bytes.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        src = rec.get("source_type", "unknown")
        ticker = rec.get("ticker", "unknown")
        evt_date = rec.get("event_date", "")
        by_source[src] += 1
        by_ticker[ticker] += 1
        if evt_date:
            dates.append(evt_date)

    sorted_dates = sorted(dates)
    oldest = sorted_dates[0] if sorted_dates else None
    newest = sorted_dates[-1] if sorted_dates else None

    return LedgerManifest(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        as_of_date=as_of_date,
        ledger_path=str(ledger_path),
        sha256=sha256,
        file_size_bytes=file_size,
        total_records=total,
        records_by_source=dict(by_source.most_common()),
        records_by_ticker=dict(by_ticker.most_common()),
        oldest_record=oldest,
        newest_record=newest,
    )


def verify_manifest(
    ledger_path: str | Path,
    manifest_path: str | Path,
) -> tuple[bool, str]:
    """
    Verify the current ledger file matches a previously saved manifest.

    Returns
    -------
    (ok, message)
        ok=True if SHA-256 matches; False otherwise with a descriptive message.
    """
    stored = LedgerManifest.load(manifest_path)
    current_bytes = Path(ledger_path).read_bytes()
    current_sha256 = hashlib.sha256(current_bytes).hexdigest()

    if current_sha256 == stored.sha256:
        return True, f"ok — SHA-256 matches ({stored.sha256[:12]}…)"
    return False, (
        f"MISMATCH — stored={stored.sha256[:12]}… current={current_sha256[:12]}…\n"
        f"Ledger may have been modified outside the pipeline."
    )


def _sha256_of_empty() -> str:
    return hashlib.sha256(b"").hexdigest()
