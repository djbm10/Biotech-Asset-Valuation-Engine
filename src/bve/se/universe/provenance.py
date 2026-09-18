"""Turn a provider result into the manifest's record of the universe a run queried.

Lives beside the providers rather than in the orchestrator so that adding a backend does
not mean teaching the orchestrator a new provenance shape.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from bve.se.schemas.contracts import TrialUniverseProvenance
from bve.se.universe.provider import TrialQuery, TrialUniverseResult

#: Fields that define *which universe this is*. Timestamps are deliberately absent: two
#: runs over the same records at different times are the same universe, and binding the
#: clock into the digest would make every run trivially unique and the hash worthless.
_IDENTITY_FIELDS = (
    "backend",
    "provider_version",
    "source_release",
    "snapshot_ids",
    "query",
    "records_returned",
    "truncated",
    "extractor",
    "extractor_version",
)


def provenance_hash(provenance: TrialUniverseProvenance) -> str:
    payload = {
        field: getattr(provenance, field) for field in _IDENTITY_FIELDS
    }
    serialized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def describe_universe(
    result: TrialUniverseResult,
    query: TrialQuery,
    *,
    records_considered: int | None = None,
    retrieval_started_at: datetime | None = None,
    retrieval_completed_at: datetime | None = None,
    extractor: str | None = None,
    extractor_version: str | None = None,
) -> TrialUniverseProvenance:
    """Describe one fetch for the run manifest.

    ``records_considered`` defaults to the number returned; a backend that can report how
    much it looked at before filtering should pass the larger figure, because "returned 3"
    means something different after examining 4 rows than after examining 40 000.
    """

    provenance = TrialUniverseProvenance(
        backend=result.backend,
        provider_version=result.backend_version,
        source_release=result.backend_version,
        snapshot_ids=result.snapshot_ids,
        query=query.model_dump(mode="json", exclude_defaults=False),
        retrieval_started_at=retrieval_started_at,
        retrieval_completed_at=retrieval_completed_at,
        records_considered=(
            records_considered if records_considered is not None else len(result.records)
        ),
        records_returned=len(result.records),
        truncated=result.truncated,
        extractor=extractor,
        extractor_version=extractor_version,
    )
    return provenance.model_copy(update={"provenance_hash": provenance_hash(provenance)})
