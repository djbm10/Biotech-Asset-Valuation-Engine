"""Build a versioned ontology snapshot from bulk upstream data.

Two ingest paths, both producing the same source-fidelity records:

* ``--open-targets-dir`` parses a downloaded Open Targets ``target`` dataset export.
  Recent releases ship Spark-partitioned Parquet and older ones ship JSON lines;
  :mod:`bve.se.ontology.bulk` reads either, so the parser sees only rows.
* ``--chembl-release`` pages the ChEMBL REST service for human single-protein targets.
  ChEMBL has no comparably small bulk export for this slice, and the paged pull is
  bounded and deterministic given a fixed release.

Neither path takes a list of targets of interest: the snapshot is built over the
whole upstream slice so that resolution does not depend on what was asked for.

Release strings are verified, not trusted. ``--chembl-release`` is checked against what
the live service reports it is serving, because a snapshot stamped with a release it did
not come from is worse than one with no release at all: it is confidently wrong, and
every downstream manifest inherits the error.
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from bve.se.ontology.bulk import RawFileDigest, combined_digest, read_dataset
from bve.se.ontology.records import SourceEntityRecord, SourceProvenance
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.ontology.sources.chembl import SOURCE_NAME as CHEMBL_SOURCE
from bve.se.ontology.sources.chembl import parse_chembl_target
from bve.se.ontology.sources.open_targets import SOURCE_NAME as OPEN_TARGETS_SOURCE
from bve.se.ontology.sources.open_targets import parse_open_targets_target

CHEMBL_BASE_URL = "https://www.ebi.ac.uk/chembl/api/data/target.json"
CHEMBL_STATUS_URL = "https://www.ebi.ac.uk/chembl/api/data/status.json"
_USER_AGENT = "bve-se-ontology-builder"


def _digest(values: list[str]) -> str:
    hasher = hashlib.sha256()
    for value in values:
        hasher.update(value.encode("utf-8"))
    return hasher.hexdigest()[:32]


def build_open_targets_records(
    directory: Path,
) -> tuple[list[SourceEntityRecord], str, list[RawFileDigest]]:
    """Parse every shard in an Open Targets target export, Parquet or JSON lines.

    The returned digest is over the *files*, not the parsed rows, so that a changed
    parser and a changed upstream release stay distinguishable in the manifest.
    """

    records, digests = read_dataset(directory, parse_open_targets_target)
    return records, combined_digest(digests), digests


def verify_chembl_release(
    declared: str, *, opener: Callable[[str], Any] = urllib.request.urlopen
) -> str:
    """Confirm the live ChEMBL service is serving the release the caller declared.

    Returns the release as the service spells it (``ChEMBL_37``). Raises when it serves
    something else: pinning a release the data did not come from turns the manifest into
    a claim nobody can check, which is the one thing this layer exists to prevent.
    """

    request = urllib.request.Request(CHEMBL_STATUS_URL, headers={"User-Agent": _USER_AGENT})
    with opener(request) as response:  # type: ignore[arg-type]
        status = json.loads(response.read().decode("utf-8"))

    served = str(status.get("chembl_db_version") or "").strip()
    if not served:
        raise ValueError(f"ChEMBL status endpoint reported no release: {CHEMBL_STATUS_URL}")

    # ``36``, ``ChEMBL_36`` and ``chembl36`` all mean one release; anything else does not.
    def digits(value: str) -> str:
        return "".join(character for character in value if character.isdigit())

    if digits(declared) != digits(served):
        raise ValueError(
            f"ChEMBL is serving {served!r} but the build declared {declared!r}. "
            "Re-run with the served release, or pull from a pinned mirror of the "
            "declared one; do not stamp a release the records did not come from."
        )
    return served


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
    verify_release: bool = True,
) -> tuple[OntologySnapshot, dict[str, list[RawFileDigest]]]:
    """Assemble a snapshot from whichever sources the caller enabled.

    Returns the snapshot together with the per-file digests of the bulk inputs, which the
    artifact manifest records so a published snapshot can be traced back to the exact
    bytes it was built from.
    """

    retrieved = retrieved_at or datetime.now(timezone.utc).date()
    sources: list[SourceProvenance] = []
    records: list[SourceEntityRecord] = []
    raw_files: dict[str, list[RawFileDigest]] = {}

    if open_targets_dir is not None:
        if not open_targets_release:
            raise ValueError("open_targets_release is required to pin the snapshot version")
        parsed, digest, file_digests = build_open_targets_records(open_targets_dir)
        records.extend(parsed)
        raw_files[OPEN_TARGETS_SOURCE] = file_digests
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
        release = (
            verify_chembl_release(chembl_release, opener=opener)
            if verify_release
            else chembl_release
        )
        parsed, digest = fetch_chembl_records(
            limit=chembl_limit, max_records=chembl_max_records, opener=opener
        )
        records.extend(parsed)
        sources.append(
            SourceProvenance(
                source=CHEMBL_SOURCE,
                release=release,
                retrieved_at=retrieved,
                locator=CHEMBL_BASE_URL,
                digest=digest,
                record_count=len(parsed),
            )
        )

    if not sources:
        raise ValueError("enable at least one source: --open-targets-dir and/or --chembl-release")
    return OntologySnapshot(sources=sources, records=records), raw_files


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="bve-se-ontology-build",
        description="Build a versioned biomedical entity snapshot from bulk upstream data.",
    )
    parser.add_argument("--output", required=True, type=Path, help="Snapshot output directory")
    parser.add_argument("--open-targets-dir", type=Path, help="Downloaded Open Targets target export")
    parser.add_argument("--open-targets-release", help="Open Targets release, e.g. 26.06")
    parser.add_argument("--chembl-release", help="ChEMBL release to record, e.g. 37; enables the API pull")
    parser.add_argument("--chembl-limit", type=int, default=1000, help="ChEMBL page size")
    parser.add_argument("--chembl-max-records", type=int, help="Stop after this many ChEMBL records")
    parser.add_argument(
        "--publish",
        action="store_true",
        help=(
            "Write the durable artifact tree (manifest, receipt, normalized snapshot, "
            "archive + checksum) under --output instead of a bare snapshot directory"
        ),
    )
    parser.add_argument(
        "--skip-release-check",
        action="store_true",
        help=(
            "Do not verify --chembl-release against the live service. Only for pinned "
            "mirrors and offline rebuilds; the check exists so a snapshot cannot claim "
            "a release its records did not come from"
        ),
    )
    args = parser.parse_args(argv)

    snapshot, raw_files = build_snapshot(
        open_targets_dir=args.open_targets_dir,
        open_targets_release=args.open_targets_release,
        chembl_release=args.chembl_release,
        chembl_limit=args.chembl_limit,
        chembl_max_records=args.chembl_max_records,
        verify_release=not args.skip_release_check,
    )

    print(f"ontology_version={snapshot.ontology_version}")
    for source in snapshot.sources:
        print(f"  {source.source} {source.release}: {source.record_count} records")

    if not args.publish:
        snapshot.write(args.output)
        print(f"written to {args.output}")
        return 0

    from bve.se.ontology.artifact import publish, revalidate

    artifact_dir = publish(snapshot, raw_files, root=args.output)
    problems = revalidate(artifact_dir)
    for problem in problems:
        print(f"  REVALIDATION: {problem}")
    print(f"published to {artifact_dir}")
    # A freshly built artifact that cannot revalidate is not publishable, and saying so
    # here is cheaper than discovering it after the upload.
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
