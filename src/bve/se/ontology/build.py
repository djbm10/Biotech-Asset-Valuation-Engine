"""Build a versioned ontology snapshot from bulk upstream data.

Two ingest paths, both producing the same source-fidelity records:

* ``--open-targets-dir`` parses a downloaded Open Targets ``target`` dataset export
  (JSON lines, one target per line). This is the target-agnostic production path.
* ``--chembl-api`` pages the ChEMBL REST service for human single-protein targets.
  ChEMBL has no comparably small bulk export for this slice, and the paged pull is
  bounded and deterministic given a fixed release.

Neither path takes a list of targets of interest: the snapshot is built over the
whole upstream slice so that resolution does not depend on what was asked for.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import urllib.parse
import urllib.request
from collections.abc import Iterator
from datetime import date, timezone, datetime
from pathlib import Path
from typing import Any, Callable

from bve.se.ontology.records import SourceEntityRecord, SourceProvenance
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.ontology.sources.chembl import SOURCE_NAME as CHEMBL_SOURCE
from bve.se.ontology.sources.chembl import parse_chembl_target
from bve.se.ontology.sources.open_targets import SOURCE_NAME as OPEN_TARGETS_SOURCE
from bve.se.ontology.sources.open_targets import parse_open_targets_target

CHEMBL_BASE_URL = "https://www.ebi.ac.uk/chembl/api/data/target.json"
_USER_AGENT = "bve-se-ontology-builder"


def _digest(values: list[str]) -> str:
    hasher = hashlib.sha256()
    for value in values:
        hasher.update(value.encode("utf-8"))
    return hasher.hexdigest()[:32]


def _iter_json_lines(path: Path) -> Iterator[dict[str, Any]]:
    opener: Callable[..., Any] = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                yield json.loads(stripped)


def build_open_targets_records(directory: Path) -> tuple[list[SourceEntityRecord], str]:
    """Parse every ``*.json``/``*.jsonl`` shard in an Open Targets target export."""

    paths = sorted(
        path
        for pattern in ("*.json", "*.jsonl", "*.json.gz", "*.jsonl.gz")
        for path in directory.glob(pattern)
    )
    if not paths:
        raise FileNotFoundError(f"no Open Targets target shards found under {directory}")

    records: list[SourceEntityRecord] = []
    for path in paths:
        for row in _iter_json_lines(path):
            record = parse_open_targets_target(row)
            if record is not None:
                records.append(record)
    return records, _digest([record.source_id for record in records])


def fetch_chembl_records(
    *,
    limit: int = 1000,
    max_records: int | None = None,
    opener: Callable[[str], Any] = urllib.request.urlopen,
) -> tuple[list[SourceEntityRecord], str]:
    """Page ChEMBL for human single-protein targets.

    ``opener`` is injected so tests exercise paging without network access.
    """

    records: list[SourceEntityRecord] = []
    offset = 0
    while True:
        query = urllib.parse.urlencode(
            {
                "limit": limit,
                "offset": offset,
                "target_type": "SINGLE PROTEIN",
                "organism": "Homo sapiens",
            }
        )
        request = urllib.request.Request(
            f"{CHEMBL_BASE_URL}?{query}", headers={"User-Agent": _USER_AGENT}
        )
        with opener(request) as response:  # type: ignore[arg-type]
            payload = json.loads(response.read().decode("utf-8"))

        page = payload.get("targets") or []
        for row in page:
            record = parse_chembl_target(row)
            if record is not None:
                records.append(record)

        if max_records is not None and len(records) >= max_records:
            records = records[:max_records]
            break
        next_page = (payload.get("page_meta") or {}).get("next")
        if not next_page or not page:
            break
        offset += limit

    return records, _digest([record.source_id for record in records])


def build_snapshot(
    *,
    open_targets_dir: Path | None = None,
    open_targets_release: str | None = None,
    chembl_release: str | None = None,
    chembl_limit: int = 1000,
    chembl_max_records: int | None = None,
    opener: Callable[[str], Any] = urllib.request.urlopen,
    retrieved_at: date | None = None,
) -> OntologySnapshot:
    """Assemble a snapshot from whichever sources the caller enabled."""

    retrieved = retrieved_at or datetime.now(timezone.utc).date()
    sources: list[SourceProvenance] = []
    records: list[SourceEntityRecord] = []

    if open_targets_dir is not None:
        if not open_targets_release:
            raise ValueError("open_targets_release is required to pin the snapshot version")
        parsed, digest = build_open_targets_records(open_targets_dir)
        records.extend(parsed)
        sources.append(
            SourceProvenance(
                source=OPEN_TARGETS_SOURCE,
                release=open_targets_release,
                retrieved_at=retrieved,
                locator=str(open_targets_dir),
                digest=digest,
                record_count=len(parsed),
            )
        )

    if chembl_release:
        parsed, digest = fetch_chembl_records(
            limit=chembl_limit, max_records=chembl_max_records, opener=opener
        )
        records.extend(parsed)
        sources.append(
            SourceProvenance(
                source=CHEMBL_SOURCE,
                release=chembl_release,
                retrieved_at=retrieved,
                locator=CHEMBL_BASE_URL,
                digest=digest,
                record_count=len(parsed),
            )
        )

    if not sources:
        raise ValueError("enable at least one source: --open-targets-dir and/or --chembl-release")
    return OntologySnapshot(sources=sources, records=records)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="bve-se-ontology-build",
        description="Build a versioned biomedical entity snapshot from bulk upstream data.",
    )
    parser.add_argument("--output", required=True, type=Path, help="Snapshot output directory")
    parser.add_argument("--open-targets-dir", type=Path, help="Downloaded Open Targets target export")
    parser.add_argument("--open-targets-release", help="Open Targets release, e.g. 26.06")
    parser.add_argument("--chembl-release", help="ChEMBL release to record, e.g. 36; enables the API pull")
    parser.add_argument("--chembl-limit", type=int, default=1000, help="ChEMBL page size")
    parser.add_argument("--chembl-max-records", type=int, help="Stop after this many ChEMBL records")
    args = parser.parse_args(argv)

    snapshot = build_snapshot(
        open_targets_dir=args.open_targets_dir,
        open_targets_release=args.open_targets_release,
        chembl_release=args.chembl_release,
        chembl_limit=args.chembl_limit,
        chembl_max_records=args.chembl_max_records,
    )
    snapshot.write(args.output)
    print(f"ontology_version={snapshot.ontology_version}")
    for source in snapshot.sources:
        print(f"  {source.source} {source.release}: {source.record_count} records")
    print(f"written to {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
