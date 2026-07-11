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

The store is content-addressed and idempotent: re-adding identical bytes is a no-op.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path

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
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
        }


def _canonical_bytes(raw_payload: dict | list | str) -> bytes:
    if isinstance(raw_payload, str):
        return raw_payload.encode("utf-8")
    return json.dumps(raw_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")


class CorpusStore:
    """Persist acquired documents under a content-addressed layout with a JSONL manifest."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.snapshot_root = self.root / "snapshots"
        self.manifest_path = self.root / "manifest.jsonl"
        self._seen: set[str] = set()
        self._documents: list[CorpusDocument] = []
        self._load_existing()

    def _load_existing(self) -> None:
        if not self.manifest_path.exists():
            return
        for line in self.manifest_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            document = CorpusDocument.model_validate_json(line)
            self._seen.add(document.document_id)
            self._documents.append(document)

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
        document_id = f"corpusdoc:{content_hash[:24]}"

        family_dir = self.snapshot_root / source_family
        family_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = family_dir / f"{content_hash}.json"
        if not snapshot_path.exists():
            if isinstance(raw_payload, str):
                snapshot_path.write_text(json.dumps({"raw": raw_payload}, indent=2) + "\n")
            else:
                snapshot_path.write_text(json.dumps(raw_payload, indent=2, sort_keys=True) + "\n")

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
        if document_id in self._seen:
            return next(d for d in self._documents if d.document_id == document_id)
        self._seen.add(document_id)
        self._documents.append(document)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.manifest_path.open("a") as handle:
            handle.write(document.model_dump_json() + "\n")
        return document

    def documents(self) -> list[CorpusDocument]:
        return list(self._documents)

    def by_family(self) -> dict[str, list[CorpusDocument]]:
        grouped: dict[str, list[CorpusDocument]] = {}
        for document in self._documents:
            grouped.setdefault(document.source_family, []).append(document)
        return grouped

    def export_source_index(self, path: Path, *, exclude_native: bool = True) -> dict[str, list[dict]]:
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
