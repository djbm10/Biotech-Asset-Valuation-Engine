"""Read-only exact-key index of adopted raw assertion provenance, not a resolver."""

from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from pathlib import Path

from bve.se.ontology.records import normalize_lookup_key


def build_index(
    source: Path, destination: Path, *, assertions_sha256: str, snapshot_sha256: str
) -> None:
    """Build once from verified sidecar bytes. Existing destination is never replaced."""
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    if digest.hexdigest() != assertions_sha256:
        raise ValueError("sidecar assertion bytes differ from adopted manifest")
    if destination.exists():
        raise FileExistsError(destination)
    connection = sqlite3.connect(destination)
    try:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO metadata VALUES (?, ?)",
            [("assertions_sha256", assertions_sha256), ("snapshot_sha256", snapshot_sha256)],
        )
        connection.execute(
            "CREATE TABLE assertions (match_key TEXT, entity_id TEXT, "
            "component_id TEXT, record_key TEXT, assertion_id TEXT, alias_type TEXT)"
        )
        with gzip.open(source, "rt") as stream:
            for line in stream:
                row = json.loads(line)
                if row["snapshot_records_sha256"] != snapshot_sha256:
                    raise ValueError("sidecar snapshot binding mismatch")
                connection.executemany(
                    "INSERT INTO assertions VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (
                            row["normalized_key"],
                            c["canonical_id"],
                            c["component_id"],
                            row["source_record_key"],
                            row["assertion_id"],
                            row["assertion_type"],
                        )
                        for c in row["resolver_components"]
                    ],
                )
        connection.execute(
            "CREATE UNIQUE INDEX exact_match ON assertions "
            "(match_key, entity_id, component_id, assertion_id)"
        )
        connection.commit()
    finally:
        connection.close()


class SidecarLookup:
    """Caller supplies expected adopted hashes, never inferred from the index itself."""

    def __init__(self, path: Path, *, assertions_sha256: str, snapshot_sha256: str):
        self.connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        metadata = dict(self.connection.execute("SELECT key, value FROM metadata"))
        if metadata != {"assertions_sha256": assertions_sha256, "snapshot_sha256": snapshot_sha256}:
            self.connection.close()
            raise ValueError("stale sidecar index binding")
        self.assertions_sha256 = assertions_sha256
        self.snapshot_sha256 = snapshot_sha256

    def matches(self, text: str) -> list[dict]:
        columns = ("entity_id", "component_id", "record_key", "assertion_id", "alias_type")
        rows = self.connection.execute(
            "SELECT entity_id, component_id, record_key, assertion_id, alias_type "
            "FROM assertions WHERE match_key=? ORDER BY entity_id, component_id, assertion_id",
            (normalize_lookup_key(text),),
        )
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.connection.close()
