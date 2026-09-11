"""The acquisition custody boundary: seal the corpus before anything interprets it.

Discovery ends with bytes on disk and a record of how each one got there. Everything
after it — identity, attribution, extraction, gating, scoring — is interpretation, and
interpretation of an unsealed corpus cannot be replayed: B7 produced 3,321 hits from a
corpus whose query partition was never written down, and no later boundary could be
proven identical to what it actually did.

So the boundary is structural. :func:`seal_acquisition` runs between DISCOVERY and
IDENTITY, writes the custody files atomically, and validates the committed bytes. It
raises :class:`~bve.se.discovery.custody.CustodyError` rather than returning a status,
because a caller that is allowed to continue past a failed seal is a caller that will
eventually continue past a failed seal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from bve.se.discovery.custody import (
    AcquisitionCustody,
    CorpusSeal,
    CustodyError,
    LedgerEntry,
)
from bve.se.schemas.contracts import RunManifest

#: Schema tags, so a reader can tell what it is looking at without inferring from shape.
SOURCE_HEALTH_SCHEMA = "se_discovery_source_health_v1"
CORPUS_MANIFEST_SCHEMA = "se_discovery_corpus_manifest_v1"


def build_source_health(
    custody: AcquisitionCustody,
    manifest: RunManifest,
    *,
    mandatory_sources: Sequence[str] = (),
) -> dict[str, object]:
    """One health record per configured source, derived only from what was persisted.

    Deliberately a discovery-native schema rather than the 5-stage
    :class:`~bve.se.acquisition.source_health.SourceHealth`: that model describes the
    separate ``bve-se-acquire`` corpus path, and its stages (``documents_indexed`` and
    friends) have no counterpart here. Reporting stages this path never ran would be
    fabricated provenance.
    """

    mandatory = set(mandatory_sources)
    per_source: dict[str, dict[str, object]] = {}
    for attempt in custody.attempts:
        entry = per_source.setdefault(
            attempt.source,
            {
                "source": attempt.source,
                "mandatory": attempt.source in mandatory,
                "attempts": 0,
                "failed_attempts": 0,
                "retried_queries": 0,
                "semantic_queries": 0,
                "records": 0,
                "snapshots": 0,
            },
        )
        entry["attempts"] = int(entry["attempts"]) + 1
        if attempt.error is not None:
            entry["failed_attempts"] = int(entry["failed_attempts"]) + 1

    accepted_records: dict[str, set[str]] = {}
    accepted_snapshots: dict[str, set[str]] = {}
    queries: dict[str, set[str]] = {}
    retried: dict[str, set[str]] = {}
    for mapping in custody.build_mappings():
        queries.setdefault(mapping.source, set()).add(mapping.semantic_query_id)
        if mapping.total_attempts > 1:
            retried.setdefault(mapping.source, set()).add(mapping.semantic_query_id)
        accepted_records.setdefault(mapping.source, set()).update(mapping.record_ids)
        accepted_snapshots.setdefault(mapping.source, set()).update(mapping.snapshot_ids)

    for source, entry in per_source.items():
        entry["semantic_queries"] = len(queries.get(source, ()))
        entry["retried_queries"] = len(retried.get(source, ()))
        entry["records"] = len(accepted_records.get(source, ()))
        entry["snapshots"] = len(accepted_snapshots.get(source, ()))

    # Sources that were asked and reported a status but never produced an attempt record
    # (an unconfigured connector, for instance) still have to appear: a source missing
    # from the health record is indistinguishable from a source that was never declared.
    for source, status in manifest.source_status.items():
        entry = per_source.setdefault(
            source,
            {
                "source": source,
                "mandatory": source in mandatory,
                "attempts": 0,
                "failed_attempts": 0,
                "retried_queries": 0,
                "semantic_queries": 0,
                "records": 0,
                "snapshots": 0,
            },
        )
        entry["status"] = getattr(status, "value", status)

    return {
        "schema_version": SOURCE_HEALTH_SCHEMA,
        "run_id": manifest.run_id,
        "sources": [per_source[name] for name in sorted(per_source)],
        "known_blind_spots": list(manifest.known_blind_spots),
        "incomplete_reasons": list(manifest.incomplete_reasons),
        "fatal_reasons": list(manifest.fatal_reasons),
        "run_status": manifest.status.value,
    }


def build_corpus_manifest(
    ledger: Sequence[LedgerEntry],
    manifest: RunManifest,
    *,
    pins: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """What this corpus is and under which frozen inputs it was acquired."""

    records_by_source: dict[str, int] = {}
    orphans_by_source: dict[str, int] = {}
    for entry in ledger:
        records_by_source[entry.source] = records_by_source.get(entry.source, 0) + 1
        if entry.is_orphan:
            orphans_by_source[entry.source] = orphans_by_source.get(entry.source, 0) + 1

    return {
        "schema_version": CORPUS_MANIFEST_SCHEMA,
        "run_id": manifest.run_id,
        "problem_id": manifest.problem_id,
        "problem_version": manifest.problem_version,
        "as_of_date": manifest.as_of_date.isoformat(),
        "code_version": manifest.code_version,
        "normalization_version": manifest.normalization_version,
        "ontology_version": manifest.ontology_version,
        "extractor_versions": dict(manifest.extractor_versions),
        "trial_universe": (
            manifest.trial_universe.model_dump(mode="json")
            if manifest.trial_universe is not None
            else None
        ),
        "records_by_source": records_by_source,
        "orphan_records_by_source": orphans_by_source,
        "record_count": len(ledger),
        "pins": dict(pins or {}),
    }


def seal_acquisition(
    custody: AcquisitionCustody | None,
    manifest: RunManifest,
    custody_root: Path,
    *,
    mandatory_sources: Sequence[str] = (),
    pins: Mapping[str, object] | None = None,
) -> CorpusSeal:
    """Commit and validate the custody boundary. Raises rather than degrading."""

    if custody is None:
        raise CustodyError(
            "discovery produced no custody record; the acquisition cannot be sealed and "
            "no downstream stage may run against it"
        )
    ledger = custody.build_ledger()
    return custody.seal(
        Path(custody_root),
        source_health=build_source_health(
            custody, manifest, mandatory_sources=mandatory_sources
        ),
        corpus_manifest=build_corpus_manifest(ledger, manifest, pins=pins),
    )
