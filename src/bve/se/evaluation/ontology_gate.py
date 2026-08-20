"""Fail-closed guard: a benchmark claim may not be scored without a pinned ontology.

Production search is allowed to degrade — with no snapshot installed, resolution falls
back to problem-declared aliases, the run is stamped ``no_snapshot__…`` and the blind
spot is recorded. A *scored* run is different: recall measured against a reference set
is only interpretable if the entity layer that produced the candidates is identified and
reproducible. Scoring a snapshot-less run would report the aliases someone happened to
type into the buyer problem as system performance.

So evaluation refuses rather than warns, and refuses on a missing version too: a run
that cannot state its ontology is not more trustworthy than one that states it has none.
"""

from __future__ import annotations

from bve.se.ontology.targets import NO_SNAPSHOT_VERSION
from bve.se.schemas.contracts import RunManifest


class OntologySnapshotRequired(RuntimeError):
    """Raised when a run is scored without a pinned biomedical entity snapshot."""


def require_scoreable_ontology(manifest: RunManifest, *, reference_set: str) -> str:
    """Return the pinned ontology version, or refuse to score the run.

    ``reference_set`` only shapes the message; every reference set is gated the same way.
    """

    version = manifest.ontology_version
    if not version:
        raise OntologySnapshotRequired(
            f"run {manifest.run_id} does not record an ontology version, so its "
            f"candidates cannot be scored against reference set {reference_set!r}; "
            "re-run with a published snapshot installed (BVE_SE_ONTOLOGY_SNAPSHOT)"
        )
    if version.startswith(NO_SNAPSHOT_VERSION):
        raise OntologySnapshotRequired(
            f"run {manifest.run_id} ran with no ontology snapshot ({version}); "
            f"it resolved targets from problem-declared aliases alone and must not be "
            f"scored against reference set {reference_set!r}. Interactive search may "
            "abstain without a snapshot; a benchmark claim may not."
        )
    return version


__all__ = ["OntologySnapshotRequired", "require_scoreable_ontology"]
