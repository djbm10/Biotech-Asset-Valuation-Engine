"""Durable acquisition custody: every query attempt, and what each one actually retrieved.

Run B7 acquired a clean 13,483-document PDCD1 corpus and then died during EXTRACTION.
Because the pipeline persisted nothing until it returned, the run left only a log line and
a directory of content-addressed bytes. That corpus turned out to be unscoreable, and not
for want of integrity -- every byte verified. It was unscoreable because *which query
returned which record* was never written down, and that mapping cannot be recovered from
the bytes. Replaying the union of all snapshots against every query is a different
experiment: it produced 3,385 hits and 1,179 assets where the original produced 3,321 and
1,064, diverging at the query plan itself.

The same gap produced a second symptom. ``_search_with_retry`` keeps only a query's final
result, so a query that materialized protocols, failed, and then succeeded on retry left
those protocols on disk referenced by nothing. B7 ended with 2,913 CT.gov snapshots and
only 2,819 of them attributable to any attempt. The 94 were not corruption and not
truncation -- they were orphans of superseded attempts, and no artifact recorded that.

This module is the fix. It records:

* every attempt, including the ones that failed and the ones a retry superseded
* the exact record ids and snapshot ids each attempt materialized, failures included
* an explicit query -> record mapping, so replay reproduces membership rather than
  re-deriving it

and it commits all of that atomically, before any downstream stage may begin. A retry may
supersede an earlier attempt, but it may never make that attempt's bytes unexplained.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path

from pydantic import Field

from bve.se.schemas.contracts import SearchOutcome, StrictModel

#: Bumped when the on-disk custody layout changes in a way a reader must notice.
CUSTODY_SCHEMA_VERSION = "se_acquisition_custody_v1"

#: File names inside the custody directory. The seal hashes each of them by name, so a
#: reader that cannot find one of these has found an incomplete custody boundary.
QUERY_ATTEMPTS_FILE = "query_attempts.jsonl"
QUERY_RECORD_MAP_FILE = "query_record_map.jsonl"
ACQUISITION_LEDGER_FILE = "acquisition_ledger.jsonl"
SOURCE_HEALTH_FILE = "source_health.json"
CORPUS_MANIFEST_FILE = "corpus_manifest.json"
SEAL_FILE = "corpus_seal.json"

#: Everything the seal covers. Order is fixed so the seal's own digest is stable.
SEALED_FILES = (
    QUERY_ATTEMPTS_FILE,
    QUERY_RECORD_MAP_FILE,
    ACQUISITION_LEDGER_FILE,
    SOURCE_HEALTH_FILE,
    CORPUS_MANIFEST_FILE,
)


class CustodyError(RuntimeError):
    """Raised when the custody boundary cannot be created or does not validate."""


def query_hash(query_text: str) -> str:
    """Stable digest of a semantic query's exact text."""

    return hashlib.sha256(query_text.encode("utf-8")).hexdigest()


def semantic_query_id(source: str, query_text: str) -> str:
    """Identity of one semantic question asked of one source.

    Deliberately independent of pass and attempt number: the same question asked again
    after a transient failure is the same question, and replay has to be able to say so.
    """

    keyed = "\x1f".join((source, query_text))
    return f"query:{hashlib.sha256(keyed.encode('utf-8')).hexdigest()[:24]}"


class RecordMaterialization(StrictModel):
    """One upstream record an attempt actually pulled down and wrote to the snapshot store.

    Recorded whether or not the attempt went on to succeed, and whether or not the record
    survived the relevance filters. Both exclusions are how snapshots become orphans.
    """

    record_id: str
    snapshot_id: str
    content_hash: str
    snapshot_path: str | None = None


class QueryAttemptRecord(StrictModel):
    """One attempt at one semantic query, retained even when superseded."""

    source: str
    semantic_query_id: str
    query_text: str
    query_hash: str
    pass_number: int = Field(ge=1)
    attempt_number: int = Field(ge=1)
    started_at: datetime
    completed_at: datetime
    outcome: SearchOutcome
    #: True for the attempt whose result the run actually consumed. Exactly one attempt
    #: per (source, semantic query, pass) is accepted; the rest are superseded evidence.
    accepted: bool
    #: Set on a superseded attempt to the attempt number that replaced it, so the chain
    #: from first failure to accepted result is readable without inference.
    superseded_by_attempt: int | None = None
    error: str | None = None
    error_class: str | None = None
    pages_fetched: int = Field(default=0, ge=0)
    materializations: list[RecordMaterialization] = Field(default_factory=list)

    @property
    def record_ids(self) -> list[str]:
        return [m.record_id for m in self.materializations]

    @property
    def snapshot_ids(self) -> list[str]:
        return list(dict.fromkeys(m.snapshot_id for m in self.materializations))


class QueryRecordMapping(StrictModel):
    """The accepted membership of one semantic query: what replay must reproduce."""

    source: str
    semantic_query_id: str
    query_text: str
    query_hash: str
    pass_number: int = Field(ge=1)
    outcome: SearchOutcome
    accepted_attempt_number: int = Field(ge=1)
    total_attempts: int = Field(ge=1)
    record_ids: list[str] = Field(default_factory=list)
    snapshot_ids: list[str] = Field(default_factory=list)


class LedgerEntry(StrictModel):
    """One distinct record in the sealed corpus, with the bytes that prove it."""

    source: str
    record_id: str
    snapshot_id: str
    content_hash: str
    byte_length: int = Field(ge=0)
    snapshot_path: str
    #: Semantic queries whose ACCEPTED attempt returned this record. Empty means the
    #: record reached disk only through attempts that were superseded or failed -- the
    #: B7 orphan case, now explicitly labelled rather than silently unexplained.
    accepted_by_queries: list[str] = Field(default_factory=list)
    #: Every attempt that materialized it, accepted or not.
    materialized_by_attempts: int = Field(default=0, ge=0)

    @property
    def is_orphan(self) -> bool:
        return not self.accepted_by_queries


class CorpusSeal(StrictModel):
    """Hashes over the persisted custody bytes. Never over anything not written down."""

    schema_version: str = CUSTODY_SCHEMA_VERSION
    run_id: str
    sealed_at: datetime
    #: sha256 of each sealed file, by file name.
    file_hashes: dict[str, str]
    #: sha256 over the sorted content hashes of every snapshot in the corpus. Two runs
    #: that acquired the same bytes share this value regardless of acquisition order.
    universe_hash: str
    record_count: int = Field(ge=0)
    snapshot_count: int = Field(ge=0)
    attempt_count: int = Field(ge=0)
    semantic_query_count: int = Field(ge=0)
    orphan_record_count: int = Field(ge=0)
    source_counts: dict[str, int] = Field(default_factory=dict)

    def digest(self) -> str:
        """Single value naming this seal, over the fields a reader must trust."""

        payload = json.dumps(
            {
                "schema_version": self.schema_version,
                "run_id": self.run_id,
                "file_hashes": self.file_hashes,
                "universe_hash": self.universe_hash,
                "record_count": self.record_count,
                "snapshot_count": self.snapshot_count,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


def _canonical_line(model: StrictModel) -> str:
    return json.dumps(model.model_dump(mode="json"), sort_keys=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class AcquisitionCustody:
    """Collects attempts during acquisition, then commits the custody boundary atomically.

    Nothing is written until :meth:`seal`. The boundary appears complete or not at all,
    because a half-written ledger is exactly the state that made B7 unrecoverable.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._attempts: list[QueryAttemptRecord] = []

    def record_attempt(self, attempt: QueryAttemptRecord) -> None:
        self._attempts.append(attempt)

    def extend(self, attempts: Iterable[QueryAttemptRecord]) -> None:
        self._attempts.extend(attempts)

    @property
    def attempts(self) -> list[QueryAttemptRecord]:
        return list(self._attempts)

    def build_mappings(self) -> list[QueryRecordMapping]:
        """Accepted membership per semantic query, in a stable order."""

        grouped: dict[tuple[str, str, int], list[QueryAttemptRecord]] = {}
        for attempt in self._attempts:
            key = (attempt.source, attempt.semantic_query_id, attempt.pass_number)
            grouped.setdefault(key, []).append(attempt)

        mappings: list[QueryRecordMapping] = []
        for (source, sqid, pass_number), attempts in sorted(grouped.items()):
            accepted = [a for a in attempts if a.accepted]
            if len(accepted) != 1:
                raise CustodyError(
                    f"{source}/{sqid} pass {pass_number}: expected exactly one accepted "
                    f"attempt, found {len(accepted)}"
                )
            final = accepted[0]
            mappings.append(
                QueryRecordMapping(
                    source=source,
                    semantic_query_id=sqid,
                    query_text=final.query_text,
                    query_hash=final.query_hash,
                    pass_number=pass_number,
                    outcome=final.outcome,
                    accepted_attempt_number=final.attempt_number,
                    total_attempts=len(attempts),
                    record_ids=list(dict.fromkeys(final.record_ids)),
                    snapshot_ids=final.snapshot_ids,
                )
            )
        return mappings

    def build_ledger(self) -> list[LedgerEntry]:
        """One entry per distinct record, resolving bytes from the snapshot store.

        Records materialized only by failed or superseded attempts appear here too, with
        an empty ``accepted_by_queries``. That is the whole point: a superseded attempt
        may lose its result, but it may not leave bytes nobody can account for.
        """

        accepted_queries: dict[str, list[str]] = {}
        counts: dict[str, int] = {}
        seen: dict[str, RecordMaterialization] = {}
        sources: dict[str, str] = {}

        for attempt in self._attempts:
            for materialization in attempt.materializations:
                key = f"{attempt.source}\x1f{materialization.record_id}"
                seen.setdefault(key, materialization)
                sources.setdefault(key, attempt.source)
                counts[key] = counts.get(key, 0) + 1
                if attempt.accepted:
                    accepted_queries.setdefault(key, [])
                    if attempt.semantic_query_id not in accepted_queries[key]:
                        accepted_queries[key].append(attempt.semantic_query_id)

        entries: list[LedgerEntry] = []
        for key in sorted(seen):
            materialization = seen[key]
            if not materialization.snapshot_path:
                raise CustodyError(
                    f"{key}: cannot seal a record whose snapshot was never written to disk"
                )
            path = Path(materialization.snapshot_path)
            if not path.is_file():
                raise CustodyError(f"{key}: snapshot missing at {path}")
            raw = path.read_bytes()
            observed = hashlib.sha256(raw).hexdigest()
            if observed != materialization.content_hash:
                raise CustodyError(
                    f"{key}: snapshot at {path} hashes to {observed}, expected "
                    f"{materialization.content_hash}"
                )
            entries.append(
                LedgerEntry(
                    source=sources[key],
                    record_id=materialization.record_id,
                    snapshot_id=materialization.snapshot_id,
                    content_hash=materialization.content_hash,
                    byte_length=len(raw),
                    snapshot_path=str(path),
                    accepted_by_queries=sorted(accepted_queries.get(key, [])),
                    materialized_by_attempts=counts[key],
                )
            )
        return entries

    def seal(
        self,
        custody_root: Path,
        *,
        source_health: dict[str, object],
        corpus_manifest: dict[str, object],
    ) -> CorpusSeal:
        """Write the whole custody boundary, or leave the destination untouched.

        Everything is staged in a sibling temp directory, fsynced, and moved into place
        only once the seal itself validates against the staged bytes.
        """

        custody_root = Path(custody_root)
        if custody_root.exists() and any(custody_root.iterdir()):
            raise CustodyError(
                f"refusing to seal into non-empty custody root {custody_root}; a sealed "
                "acquisition is immutable and must never be patched in place"
            )
        custody_root.parent.mkdir(parents=True, exist_ok=True)

        mappings = self.build_mappings()
        ledger = self.build_ledger()

        staging = Path(tempfile.mkdtemp(prefix=".custody-", dir=custody_root.parent))
        try:
            (staging / QUERY_ATTEMPTS_FILE).write_text(
                "".join(_canonical_line(a) + "\n" for a in self._attempts)
            )
            (staging / QUERY_RECORD_MAP_FILE).write_text(
                "".join(_canonical_line(m) + "\n" for m in mappings)
            )
            (staging / ACQUISITION_LEDGER_FILE).write_text(
                "".join(_canonical_line(e) + "\n" for e in ledger)
            )
            (staging / SOURCE_HEALTH_FILE).write_text(
                json.dumps(source_health, indent=2, sort_keys=True, default=str) + "\n"
            )
            (staging / CORPUS_MANIFEST_FILE).write_text(
                json.dumps(corpus_manifest, indent=2, sort_keys=True, default=str) + "\n"
            )

            universe_hash = hashlib.sha256(
                "\n".join(sorted(entry.content_hash for entry in ledger)).encode()
            ).hexdigest()
            source_counts: dict[str, int] = {}
            for entry in ledger:
                source_counts[entry.source] = source_counts.get(entry.source, 0) + 1

            seal = CorpusSeal(
                run_id=self.run_id,
                sealed_at=datetime.now(timezone.utc),
                file_hashes={
                    name: _sha256_file(staging / name) for name in SEALED_FILES
                },
                universe_hash=universe_hash,
                record_count=len(ledger),
                snapshot_count=len({entry.content_hash for entry in ledger}),
                attempt_count=len(self._attempts),
                semantic_query_count=len({m.semantic_query_id for m in mappings}),
                orphan_record_count=sum(1 for entry in ledger if entry.is_orphan),
                source_counts=source_counts,
            )
            (staging / SEAL_FILE).write_text(
                json.dumps(seal.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
            )

            for name in (*SEALED_FILES, SEAL_FILE):
                handle = os.open(staging / name, os.O_RDONLY)
                try:
                    os.fsync(handle)
                finally:
                    os.close(handle)
            _fsync_dir(staging)

            os.rename(staging, custody_root)
            _fsync_dir(custody_root.parent)
        except BaseException:
            for child in staging.glob("*"):
                child.unlink(missing_ok=True)
            staging.rmdir()
            raise

        # Read back from the committed location: the seal is only meaningful if it
        # validates against the bytes that actually landed.
        validate_seal(custody_root)
        return seal


class SealedAcquisition(StrictModel):
    """A validated, read-only view of one sealed acquisition."""

    custody_root: str
    seal: CorpusSeal
    attempts: list[QueryAttemptRecord]
    mappings: list[QueryRecordMapping]
    ledger: list[LedgerEntry]

    def mapping_by_query(self) -> dict[tuple[str, str, int], QueryRecordMapping]:
        return {
            (m.source, m.semantic_query_id, m.pass_number): m for m in self.mappings
        }

    def ledger_by_record(self) -> dict[tuple[str, str], LedgerEntry]:
        return {(e.source, e.record_id): e for e in self.ledger}


def validate_seal(custody_root: Path, *, verify_snapshots: bool = True) -> SealedAcquisition:
    """Load a sealed acquisition, refusing anything that does not verify.

    Fails on a missing file, a mutated file, a snapshot whose bytes no longer match the
    ledger, or a seal whose recorded hashes disagree with what is on disk.
    """

    custody_root = Path(custody_root)
    seal_path = custody_root / SEAL_FILE
    if not seal_path.is_file():
        raise CustodyError(f"no corpus seal at {seal_path}")
    seal = CorpusSeal.model_validate_json(seal_path.read_text())

    for name in SEALED_FILES:
        path = custody_root / name
        if not path.is_file():
            raise CustodyError(f"sealed file missing: {path}")
        observed = _sha256_file(path)
        expected = seal.file_hashes.get(name)
        if expected is None:
            raise CustodyError(f"seal does not cover {name}")
        if observed != expected:
            raise CustodyError(
                f"sealed file mutated: {name} hashes to {observed}, seal records {expected}"
            )

    unexpected = sorted(
        p.name for p in custody_root.iterdir() if p.name not in {*SEALED_FILES, SEAL_FILE}
    )
    if unexpected:
        raise CustodyError(
            f"unexpected files in sealed custody root {custody_root}: {unexpected}"
        )

    attempts = [
        QueryAttemptRecord.model_validate_json(line)
        for line in (custody_root / QUERY_ATTEMPTS_FILE).read_text().splitlines()
        if line.strip()
    ]
    mappings = [
        QueryRecordMapping.model_validate_json(line)
        for line in (custody_root / QUERY_RECORD_MAP_FILE).read_text().splitlines()
        if line.strip()
    ]
    ledger = [
        LedgerEntry.model_validate_json(line)
        for line in (custody_root / ACQUISITION_LEDGER_FILE).read_text().splitlines()
        if line.strip()
    ]

    if len(attempts) != seal.attempt_count:
        raise CustodyError(
            f"seal records {seal.attempt_count} attempts, file holds {len(attempts)}"
        )
    if len(ledger) != seal.record_count:
        raise CustodyError(
            f"seal records {seal.record_count} records, ledger holds {len(ledger)}"
        )

    universe_hash = hashlib.sha256(
        "\n".join(sorted(entry.content_hash for entry in ledger)).encode()
    ).hexdigest()
    if universe_hash != seal.universe_hash:
        raise CustodyError(
            f"universe hash mismatch: computed {universe_hash}, seal records "
            f"{seal.universe_hash}"
        )

    if verify_snapshots:
        for entry in ledger:
            path = Path(entry.snapshot_path)
            if not path.is_file():
                raise CustodyError(f"sealed snapshot missing: {path}")
            raw = path.read_bytes()
            observed = hashlib.sha256(raw).hexdigest()
            if observed != entry.content_hash:
                raise CustodyError(
                    f"sealed snapshot mutated: {path} hashes to {observed}, ledger "
                    f"records {entry.content_hash}"
                )
            if len(raw) != entry.byte_length:
                raise CustodyError(f"sealed snapshot length changed: {path}")

    return SealedAcquisition(
        custody_root=str(custody_root),
        seal=seal,
        attempts=attempts,
        mappings=mappings,
        ledger=ledger,
    )


def unexplained_snapshots(
    sealed: SealedAcquisition, snapshot_roots: Sequence[Path]
) -> list[str]:
    """Snapshot files on disk that the sealed ledger does not account for.

    A retry is allowed to supersede an attempt. It is not allowed to leave bytes behind
    that no record explains -- that is precisely the B7 orphan condition, and the custody
    boundary exists to make it detectable instead of invisible.
    """

    sealed_hashes = {entry.content_hash for entry in sealed.ledger}
    unexplained: list[str] = []
    for root in snapshot_roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.json")):
            if path.stem not in sealed_hashes:
                unexplained.append(str(path))
    return unexplained
