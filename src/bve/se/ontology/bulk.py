"""Read bulk upstream exports and hash exactly what was read.

Open Targets ships its datasets as Spark-partitioned Parquet; older releases shipped
JSON lines. Both are handled here, and both yield plain row mappings so the parsers in
:mod:`bve.se.ontology.sources` stay format-agnostic — a parser that knew about Parquet
would have to be rewritten the next time upstream changes its serialization.

Every file read is hashed as it is read. A snapshot that records only the release string
is claiming provenance it cannot demonstrate: releases get re-cut, mirrors get corrupted,
and a partial download looks exactly like a small one. The file digests are what make the
claim checkable.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Callable

#: Extensions recognised as bulk shards, in the order the reader tries them.
JSON_SUFFIXES = (".json", ".jsonl", ".json.gz", ".jsonl.gz")
PARQUET_SUFFIXES = (".parquet",)

_HASH_CHUNK_BYTES = 1 << 20


class RawFileDigest:
    """The identity of one file that contributed rows to a snapshot."""

    __slots__ = ("path", "sha256", "byte_length", "rows")

    def __init__(self, path: Path, sha256: str, byte_length: int, rows: int) -> None:
        self.path = path
        self.sha256 = sha256
        self.byte_length = byte_length
        self.rows = rows

    def as_dict(self, *, relative_to: Path | None = None) -> dict[str, Any]:
        name = self.path.name if relative_to is None else str(self.path.relative_to(relative_to))
        return {
            "file": name,
            "sha256": self.sha256,
            "byte_length": self.byte_length,
            "rows": self.rows,
        }


def file_sha256(path: Path) -> tuple[str, int]:
    """Digest a file without holding it in memory; shards run to tens of megabytes."""

    hasher = hashlib.sha256()
    length = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_BYTES):
            hasher.update(chunk)
            length += len(chunk)
    return hasher.hexdigest(), length


def discover_shards(directory: Path) -> list[Path]:
    """Every bulk shard under a dataset directory, in a stable order.

    Sorted by name so two builds over one download read the rows in the same sequence.
    Spark's ``_SUCCESS`` marker and CRC sidecars are not data and are skipped.
    """

    shards = [
        path
        for path in directory.rglob("*")
        if path.is_file()
        and not path.name.startswith((".", "_"))
        and (path.name.endswith(JSON_SUFFIXES) or path.suffix in PARQUET_SUFFIXES)
    ]
    return sorted(shards)


def _iter_json_rows(path: Path) -> Iterator[Mapping[str, Any]]:
    opener: Callable[..., Any] = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                yield json.loads(stripped)


def _iter_parquet_rows(path: Path) -> Iterator[Mapping[str, Any]]:
    """Yield Parquet rows as plain Python mappings.

    ``pyarrow`` is imported here rather than at module scope so that the ontology package
    imports on a machine that will only ever *read* a published snapshot. Building one
    from bulk Parquet is a maintainer operation; reading one is what everybody else does.
    """

    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - exercised by the error path only
        raise ImportError(
            "reading Parquet bulk exports needs pyarrow: pip install 'bve[ontology]'. "
            "Published snapshots read without it."
        ) from exc

    parquet_file = pq.ParquetFile(path)
    for batch in parquet_file.iter_batches(batch_size=2048):
        yield from batch.to_pylist()


def iter_rows(path: Path) -> Iterator[Mapping[str, Any]]:
    """Yield row mappings from one shard, whichever serialization it uses."""

    if path.suffix in PARQUET_SUFFIXES:
        return _iter_parquet_rows(path)
    return _iter_json_rows(path)


def read_dataset(
    directory: Path,
    parse_row: Callable[[Mapping[str, Any]], Any],
) -> tuple[list[Any], list[RawFileDigest]]:
    """Parse every shard of a bulk dataset, returning records and per-file digests.

    No filter is accepted, deliberately. A snapshot built over the targets someone was
    interested in resolves those targets and quietly fails everything else, which is the
    exact failure mode that makes a discovery system look accurate on its own examples.
    """

    shards = discover_shards(directory)
    if not shards:
        raise FileNotFoundError(f"no bulk shards found under {directory}")

    records: list[Any] = []
    digests: list[RawFileDigest] = []
    for shard in shards:
        sha256, byte_length = file_sha256(shard)
        before = len(records)
        for row in iter_rows(shard):
            record = parse_row(row)
            if record is not None:
                records.append(record)
        digests.append(RawFileDigest(shard, sha256, byte_length, len(records) - before))
    return records, digests


def combined_digest(digests: list[RawFileDigest]) -> str:
    """One digest over a whole dataset, derived from its files rather than its rows.

    Hashing the parsed rows would change whenever the parser changed, conflating "the
    upstream data moved" with "we read it differently" — two failures that need very
    different responses.
    """

    hasher = hashlib.sha256()
    for digest in sorted(digests, key=lambda item: item.path.name):
        hasher.update(digest.path.name.encode("utf-8"))
        hasher.update(digest.sha256.encode("utf-8"))
    return hasher.hexdigest()
