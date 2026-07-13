"""Content-addressed corpus store with explicit per-document acquisition health.

Every acquired document carries a full provenance and health envelope so that "source health"
can be decomposed into distinct stages rather than a single opaque pass/fail:

    connector -> query -> retrieval -> raw snapshot -> parse -> index

``parser_status`` and ``index_status`` record the last two stages per document. Whether the
*required* evidence for a benchmark asset is present is a corpus-level question answered separately
by ``bve.se.evaluation.corpus_coverage`` -- it is intentionally not stored on the document.

Storage layout under ``root``::

    root/
      snapshots/<source_family>/<content_hash>.json   # immutable raw snapshot
      manifest.jsonl                                   # one CorpusDocument per line

Snapshots are content-addressed by payload hash. Document identity additionally includes the
source family and URL so identical public bytes acquired through distinct provenance are retained.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
import threading
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import BinaryIO

from pydantic import BaseModel, ConfigDict

from bve.se.schemas.contracts import SourceTier


class ParserStatus(str, Enum):
    """Did we extract usable searchable text from the raw snapshot?"""

    OK = "OK"
    EMPTY = "EMPTY"
    FAILED = "FAILED"


class IndexStatus(str, Enum):
    """Is the extracted evidence available to downstream search?"""

    INDEXED = "INDEXED"
    UNINDEXED = "UNINDEXED"
    FAILED = "FAILED"


class CorpusDocument(BaseModel):
    """One acquired public document with its full acquisition-health envelope."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    source_family: str
    source_url: str
    publisher: str
    document_type: str
    source_tier: SourceTier
    content_hash: str
    snapshot_path: str
    retrieval_date: datetime
    as_of_date: date
    publication_date: date | None = None
    title: str = ""
    text: str = ""
    parser_status: ParserStatus = ParserStatus.OK
    index_status: IndexStatus = IndexStatus.INDEXED
    # Native-format flag: CT.gov / PubMed snapshots replay through their own adapters; other
    # families are exposed to discovery through the generated source index.
    native_snapshot: bool = False

    def indexable_record(self) -> dict[str, object]:
        """Render the ``IndexedDocumentAdapter`` document shape for discovery consumption."""

        return {
            "url": self.source_url,
            "title": self.title,
            "text": self.text,
            "publisher": self.publisher,
            "document_type": self.document_type,
            "publication_date": self.publication_date.isoformat()
            if self.publication_date
            else None,
        }


class CorpusValidationReport(BaseModel):
    """Result of a complete on-disk corpus integrity check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    valid: bool
    manifest_path: str
    document_count: int
    snapshot_count: int
    errors: tuple[str, ...] = ()


class CorpusIntegrityError(RuntimeError):
    """Raised when a corpus manifest or referenced snapshot fails validation."""

    def __init__(self, report: CorpusValidationReport) -> None:
        self.report = report
        detail = "; ".join(report.errors) or "unknown corpus integrity error"
        super().__init__(f"Corpus integrity validation failed: {detail}")


def _canonical_bytes(raw_payload: dict | list | str) -> bytes:
    if isinstance(raw_payload, str):
        return raw_payload.encode("utf-8")
    return json.dumps(raw_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _snapshot_bytes(raw_payload: dict | list | str) -> bytes:
    if isinstance(raw_payload, str):
        serialized = json.dumps({"raw": raw_payload}, indent=2, ensure_ascii=False)
    else:
        serialized = json.dumps(raw_payload, indent=2, sort_keys=True, ensure_ascii=False)
    return (serialized + "\n").encode("utf-8")


def _identity_key(
    *, source_family: str, source_url: str, content_hash: str
) -> tuple[str, str, str]:
    return source_family, source_url, content_hash


def _document_id(*, source_family: str, source_url: str, content_hash: str) -> str:
    identity = json.dumps(
        {
            "content_hash": content_hash,
            "source_family": source_family,
            "source_url": source_url,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"corpusdoc:{hashlib.sha256(identity).hexdigest()[:24]}"


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ManifestSignature = tuple[int, int, int, int]


class CorpusStore:
    """Persist acquired documents under a content-addressed layout with a JSONL manifest."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.snapshot_root = self.root / "snapshots"
        self.manifest_path = self.root / "manifest.jsonl"
        self._seen: set[str] = set()
        self._documents: list[CorpusDocument] = []
        self._by_identity: dict[tuple[str, str, str], CorpusDocument] = {}
        self._manifest_signature: _ManifestSignature | None = None
        self._mutex = threading.RLock()
        self._load_existing()

    def _load_existing(self) -> None:
        if not self.manifest_path.exists():
            return
        self.validate()

    @staticmethod
    def _signature(handle: BinaryIO) -> _ManifestSignature:
        stat = os.fstat(handle.fileno())
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

    def _set_documents(self, documents: list[CorpusDocument]) -> None:
        self._documents = list(documents)
        self._seen = {document.document_id for document in documents}
        self._by_identity = {
            _identity_key(
                source_family=document.source_family,
                source_url=document.source_url,
                content_hash=document.content_hash,
            ): document
            for document in documents
        }

    def _resolve_snapshot_path(self, value: str) -> tuple[Path | None, str | None]:
        configured = Path(value).expanduser()
        root = self.root.resolve()
        if configured.is_absolute():
            candidates = [configured.resolve(strict=False)]
        else:
            # Historical manifests stored paths relative to the process working directory,
            # while root-relative paths are more portable. Accept either when it resolves
            # beneath this store, preferring an existing path.
            candidates = [
                configured.resolve(strict=False),
                (self.root / configured).resolve(strict=False),
            ]
            # Older repo-relative manifests may be opened from a different working directory.
            # Their stable suffix starts at ``snapshots/`` and can be safely rebased to root.
            snapshot_indexes = [
                index for index, part in enumerate(configured.parts) if part == "snapshots"
            ]
            if snapshot_indexes:
                suffix = Path(*configured.parts[snapshot_indexes[-1] :])
                candidates.append((self.root / suffix).resolve(strict=False))

        contained = [candidate for candidate in candidates if candidate.is_relative_to(root)]
        if not contained:
            return None, f"snapshot path escapes store root: {value!r}"
        existing = next((candidate for candidate in contained if candidate.exists()), None)
        return existing or contained[0], None

    @staticmethod
    def _snapshot_payload_hashes(snapshot: bytes) -> set[str]:
        parsed = json.loads(snapshot.decode("utf-8"))
        payloads: list[dict | list | str] = [parsed]
        # String payloads were historically stored as {"raw": "..."}. Include both
        # interpretations because a genuine mapping with that shape is also valid.
        if isinstance(parsed, dict) and set(parsed) == {"raw"} and isinstance(parsed["raw"], str):
            payloads.append(parsed["raw"])
        return {hashlib.sha256(_canonical_bytes(payload)).hexdigest() for payload in payloads}

    def _snapshot_errors(self, document: CorpusDocument, *, line_number: int) -> list[str]:
        prefix = f"manifest line {line_number} ({document.document_id})"
        resolved, path_error = self._resolve_snapshot_path(document.snapshot_path)
        if path_error:
            return [f"{prefix}: {path_error}"]
        assert resolved is not None
        if not resolved.exists():
            return [f"{prefix}: snapshot does not exist: {document.snapshot_path!r}"]
        if not resolved.is_file():
            return [f"{prefix}: snapshot is not a regular file: {document.snapshot_path!r}"]
        if resolved.name != f"{document.content_hash}.json":
            return [
                f"{prefix}: snapshot filename does not match content SHA-256: {resolved.name!r}"
            ]
        try:
            hashes = self._snapshot_payload_hashes(resolved.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            return [f"{prefix}: unreadable snapshot {document.snapshot_path!r}: {exc}"]
        if document.content_hash not in hashes:
            actual = ", ".join(sorted(hashes)) or "unavailable"
            return [
                f"{prefix}: snapshot SHA-256 mismatch; expected {document.content_hash}, "
                f"computed {actual}"
            ]
        return []

    def _inspect_manifest(
        self,
        raw_manifest: bytes,
    ) -> tuple[CorpusValidationReport, list[CorpusDocument]]:
        errors: list[str] = []
        documents: list[CorpusDocument] = []
        snapshot_paths: set[str] = set()
        first_line_by_id: dict[str, int] = {}
        first_line_by_identity: dict[tuple[str, str, str], int] = {}

        try:
            text = raw_manifest.decode("utf-8")
        except UnicodeDecodeError as exc:
            report = CorpusValidationReport(
                valid=False,
                manifest_path=str(self.manifest_path),
                document_count=0,
                snapshot_count=0,
                errors=(f"manifest is not valid UTF-8: {exc}",),
            )
            return report, []

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                document = CorpusDocument.model_validate_json(line)
            except Exception as exc:
                detail = " ".join(str(exc).splitlines())
                errors.append(f"manifest line {line_number}: invalid CorpusDocument: {detail}")
                continue

            documents.append(document)
            snapshot_paths.add(document.snapshot_path)
            if not _SHA256_RE.fullmatch(document.content_hash):
                errors.append(
                    f"manifest line {line_number} ({document.document_id}): "
                    f"invalid content SHA-256 {document.content_hash!r}"
                )

            prior_id_line = first_line_by_id.setdefault(document.document_id, line_number)
            if prior_id_line != line_number:
                errors.append(
                    f"manifest line {line_number}: duplicate document_id "
                    f"{document.document_id!r} (first seen on line {prior_id_line})"
                )

            identity = _identity_key(
                source_family=document.source_family,
                source_url=document.source_url,
                content_hash=document.content_hash,
            )
            prior_identity_line = first_line_by_identity.setdefault(identity, line_number)
            if prior_identity_line != line_number:
                errors.append(
                    f"manifest line {line_number}: duplicate document provenance identity "
                    f"(first seen on line {prior_identity_line})"
                )

            errors.extend(self._snapshot_errors(document, line_number=line_number))

        report = CorpusValidationReport(
            valid=not errors,
            manifest_path=str(self.manifest_path),
            document_count=len(documents),
            snapshot_count=len(snapshot_paths),
            errors=tuple(errors),
        )
        return report, documents

    @staticmethod
    def _raise_if_invalid(report: CorpusValidationReport) -> None:
        if not report.valid:
            raise CorpusIntegrityError(report)

    def validate(self, *, raise_on_error: bool = True) -> CorpusValidationReport:
        """Validate manifest rows, provenance uniqueness, paths, and snapshot payload hashes.

        A valid report refreshes this instance's in-memory view. Invalid corpora raise
        :class:`CorpusIntegrityError` by default; callers performing diagnostics can pass
        ``raise_on_error=False`` to inspect all collected errors.
        """

        with self._mutex:
            if not self.manifest_path.exists():
                self._set_documents([])
                self._manifest_signature = None
                return CorpusValidationReport(
                    valid=True,
                    manifest_path=str(self.manifest_path),
                    document_count=0,
                    snapshot_count=0,
                )
            try:
                with self.manifest_path.open("rb") as handle:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
                    try:
                        raw_manifest = handle.read()
                        signature = self._signature(handle)
                    finally:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError as exc:
                report = CorpusValidationReport(
                    valid=False,
                    manifest_path=str(self.manifest_path),
                    document_count=0,
                    snapshot_count=0,
                    errors=(f"unable to read manifest: {exc}",),
                )
                if raise_on_error:
                    raise CorpusIntegrityError(report) from exc
                return report

            report, documents = self._inspect_manifest(raw_manifest)
            if report.valid:
                self._set_documents(documents)
                self._manifest_signature = signature
            elif raise_on_error:
                raise CorpusIntegrityError(report)
            return report

    def _snapshot_target(self, *, source_family: str, content_hash: str) -> Path:
        target = self.snapshot_root / source_family / f"{content_hash}.json"
        resolved = target.resolve(strict=False)
        if not resolved.is_relative_to(self.root.resolve()):
            report = CorpusValidationReport(
                valid=False,
                manifest_path=str(self.manifest_path),
                document_count=len(self._documents),
                snapshot_count=0,
                errors=(f"snapshot path escapes store root for source family {source_family!r}",),
            )
            raise CorpusIntegrityError(report)
        # Keep the lexical target so a final-component symlink remains detectable before
        # ``os.replace``; ``resolved`` above is used only for the containment check.
        return target.absolute()

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _write_snapshot_atomic(
        self,
        *,
        snapshot_path: Path,
        raw_payload: dict | list | str,
        content_hash: str,
    ) -> None:
        if snapshot_path.is_symlink():
            report = CorpusValidationReport(
                valid=False,
                manifest_path=str(self.manifest_path),
                document_count=len(self._documents),
                snapshot_count=0,
                errors=(f"snapshot target must not be a symbolic link: {snapshot_path}",),
            )
            raise CorpusIntegrityError(report)
        if snapshot_path.exists():
            if not snapshot_path.is_file():
                report = CorpusValidationReport(
                    valid=False,
                    manifest_path=str(self.manifest_path),
                    document_count=len(self._documents),
                    snapshot_count=1,
                    errors=(f"existing snapshot is not a regular file: {snapshot_path}",),
                )
                raise CorpusIntegrityError(report)
            try:
                hashes = self._snapshot_payload_hashes(snapshot_path.read_bytes())
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
                report = CorpusValidationReport(
                    valid=False,
                    manifest_path=str(self.manifest_path),
                    document_count=len(self._documents),
                    snapshot_count=1,
                    errors=(f"existing snapshot is unreadable at {snapshot_path}: {exc}",),
                )
                raise CorpusIntegrityError(report) from exc
            if content_hash not in hashes:
                report = CorpusValidationReport(
                    valid=False,
                    manifest_path=str(self.manifest_path),
                    document_count=len(self._documents),
                    snapshot_count=1,
                    errors=(
                        f"existing snapshot SHA-256 mismatch at {snapshot_path}; "
                        f"expected {content_hash}",
                    ),
                )
                raise CorpusIntegrityError(report)
            return

        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=snapshot_path.parent,
            prefix=f".{snapshot_path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(_snapshot_bytes(raw_payload))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, snapshot_path)
            self._fsync_directory(snapshot_path.parent)
        finally:
            temporary_path.unlink(missing_ok=True)

    def add(
        self,
        *,
        source_family: str,
        source_url: str,
        publisher: str,
        document_type: str,
        source_tier: SourceTier,
        raw_payload: dict | list | str,
        text: str,
        as_of_date: date,
        title: str = "",
        publication_date: date | None = None,
        parser_status: ParserStatus | None = None,
        native_snapshot: bool = False,
        retrieval_date: datetime | None = None,
    ) -> CorpusDocument:
        """Add one document. Returns the stored (possibly pre-existing) ``CorpusDocument``."""

        payload_bytes = _canonical_bytes(raw_payload)
        content_hash = hashlib.sha256(payload_bytes).hexdigest()
        document_id = _document_id(
            source_family=source_family,
            source_url=source_url,
            content_hash=content_hash,
        )
        snapshot_path = self._snapshot_target(
            source_family=source_family,
            content_hash=content_hash,
        )

        if parser_status is None:
            parser_status = ParserStatus.OK if text.strip() else ParserStatus.EMPTY
        index_status = (
            IndexStatus.INDEXED if parser_status is ParserStatus.OK else IndexStatus.UNINDEXED
        )

        document = CorpusDocument(
            document_id=document_id,
            source_family=source_family,
            source_url=source_url,
            publisher=publisher,
            document_type=document_type,
            source_tier=source_tier,
            content_hash=content_hash,
            snapshot_path=str(snapshot_path),
            retrieval_date=retrieval_date or datetime.now(timezone.utc),
            as_of_date=as_of_date,
            publication_date=publication_date,
            title=title,
            text=text,
            parser_status=parser_status,
            index_status=index_status,
            native_snapshot=native_snapshot,
        )
        identity = _identity_key(
            source_family=source_family,
            source_url=source_url,
            content_hash=content_hash,
        )

        with self._mutex:
            self.root.mkdir(parents=True, exist_ok=True)
            manifest_preexisting = self.manifest_path.exists()
            with self.manifest_path.open("a+b") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    current_signature = self._signature(handle)
                    if current_signature != self._manifest_signature:
                        handle.seek(0)
                        report, documents = self._inspect_manifest(handle.read())
                        self._raise_if_invalid(report)
                        self._set_documents(documents)
                        self._manifest_signature = current_signature

                    existing = self._by_identity.get(identity)
                    if existing is not None:
                        snapshot_errors = self._snapshot_errors(existing, line_number=0)
                        if snapshot_errors:
                            report = CorpusValidationReport(
                                valid=False,
                                manifest_path=str(self.manifest_path),
                                document_count=len(self._documents),
                                snapshot_count=1,
                                errors=tuple(snapshot_errors),
                            )
                            raise CorpusIntegrityError(report)
                        return existing
                    if document_id in self._seen:
                        report = CorpusValidationReport(
                            valid=False,
                            manifest_path=str(self.manifest_path),
                            document_count=len(self._documents),
                            snapshot_count=0,
                            errors=(f"provenance-derived document_id collision: {document_id!r}",),
                        )
                        raise CorpusIntegrityError(report)

                    self._write_snapshot_atomic(
                        snapshot_path=snapshot_path,
                        raw_payload=raw_payload,
                        content_hash=content_hash,
                    )
                    handle.seek(0, os.SEEK_END)
                    prefix = b""
                    if handle.tell() > 0:
                        handle.seek(-1, os.SEEK_END)
                        if handle.read(1) != b"\n":
                            prefix = b"\n"
                    handle.seek(0, os.SEEK_END)
                    handle.write(prefix + document.model_dump_json().encode("utf-8") + b"\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                    if not manifest_preexisting:
                        self._fsync_directory(self.root)
                    self._documents.append(document)
                    self._seen.add(document_id)
                    self._by_identity[identity] = document
                    self._manifest_signature = self._signature(handle)
                    return document
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def documents(self) -> list[CorpusDocument]:
        return list(self._documents)

    def by_family(self) -> dict[str, list[CorpusDocument]]:
        grouped: dict[str, list[CorpusDocument]] = {}
        for document in self._documents:
            grouped.setdefault(document.source_family, []).append(document)
        return grouped

    def export_source_index(
        self, path: Path, *, exclude_native: bool = True
    ) -> dict[str, list[dict]]:
        """Write a discovery ``--source-index`` YAML for non-native families.

        CT.gov and PubMed replay through their own snapshot directories, so their native records
        are excluded here by default. Every other family is emitted as indexable document records.
        """

        import yaml  # type: ignore[import-untyped]

        index: dict[str, list[dict]] = {}
        for document in self._documents:
            if exclude_native and document.native_snapshot:
                continue
            if document.index_status is not IndexStatus.INDEXED:
                continue
            index.setdefault(document.source_family, []).append(document.indexable_record())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(index, sort_keys=True))
        return index
