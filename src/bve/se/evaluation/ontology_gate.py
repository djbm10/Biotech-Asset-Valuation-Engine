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

import warnings

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


class TruncatedUniverseError(RuntimeError):
    """Raised when discovery recall is scored against a deliberately partial universe."""


def require_untruncated_universe(manifest: RunManifest, *, reference_set: str) -> None:
    """Refuse to score recall when the trial universe was cut short.

    Same fail-closed reasoning as the ontology gate. Recall answers "how much of the
    reference set can the system find"; against a universe that stopped early it
    answers "how much fits under the bound", which is not the same claim and cannot be
    compared across runs. A run that cannot state its universe at all is treated the
    same way: silence is not evidence of completeness.
    """

    universe = manifest.trial_universe
    if universe is None:
        # The offline and legacy search_fn paths acquire their own records and cannot
        # state which universe they saw. That is a weaker claim than a declared complete
        # sweep, so it is said out loud rather than scored as if it were the same thing.
        warnings.warn(
            f"run {manifest.run_id} records no trial universe, so its recall against "
            f"reference set {reference_set!r} cannot be shown to be complete",
            UserWarning,
            stacklevel=2,
        )
        return
    if universe.truncated:
        raise TruncatedUniverseError(
            f"run {manifest.run_id} returned a truncated trial universe "
            f"({universe.records_returned} records), so recall against reference set "
            f"{reference_set!r} would measure the record bound rather than the system; "
            "re-run without a max-records bound"
        )


__all__ = [
    "OntologySnapshotRequired",
    "TruncatedUniverseError",
    "require_scoreable_ontology",
    "require_untruncated_universe",
]
