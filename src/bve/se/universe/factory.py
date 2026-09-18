"""Backend selection for the trial universe.

The only place in the codebase that names a concrete backend. Callers pass a string that
came from a CLI flag or config and get a :class:`TrialUniverseProvider`; nothing
downstream imports a backend module directly.
"""

from __future__ import annotations

import os
from pathlib import Path

from bve.se.universe.aact import AACTProvider
from bve.se.universe.ctgov import ClinicalTrialsGovProvider
from bve.se.universe.frozen import FrozenTrialProvider
from bve.se.universe.hybrid import HybridTrialProvider
from bve.se.universe.provider import TrialUniverseProvider

DEFAULT_BACKEND = "rest"
#: ``rest`` is the CLI-facing name for ``ctgov``; both select the REST v2 backend.
KNOWN_BACKENDS = ("rest", "ctgov", "aact", "hybrid", "frozen")

#: Environment variable holding the AACT connection string.
AACT_DSN_ENV = "BVE_AACT_DSN"


class TrialBackendNotConfigured(RuntimeError):
    """A known backend was requested but this machine cannot serve it.

    Raised instead of quietly substituting REST. A run that believed it queried a bulk
    mirror and actually hit a paged API has a different universe than its manifest claims,
    and nothing downstream would reveal the difference.
    """


def build_trial_provider(
    backend: str = DEFAULT_BACKEND,
    *,
    snapshot_root: Path | None = None,
    aact_dsn: str | None = None,
    aact_release: str | None = None,
    fixture_path: Path | None = None,
) -> TrialUniverseProvider:
    """Construct the named backend, or refuse.

    ``rest`` is the default because it requires no local infrastructure. ``aact`` and
    ``hybrid`` raise :class:`TrialBackendNotConfigured` unless a mirror is actually
    reachable; ``hybrid``'s AACT-then-REST preference applies only once it is. An
    unrecognized name is a configuration error, never a default.
    """

    normalized = backend.strip().casefold()
    if normalized in {"rest", "ctgov"}:
        return ClinicalTrialsGovProvider(snapshot_root=snapshot_root)
    if normalized in {"aact", "hybrid"}:
        dsn = aact_dsn or os.environ.get(AACT_DSN_ENV)
        if not dsn:
            raise TrialBackendNotConfigured(
                f"trial backend {normalized!r} needs an AACT mirror: set {AACT_DSN_ENV} or "
                "pass aact_dsn. Not falling back to the REST API, which would query a "
                "different universe than the manifest would record."
            )
        aact = AACTProvider(
            dsn=dsn, snapshot_root=snapshot_root, snapshot_release=aact_release
        )
        if normalized == "aact":
            return aact
        return HybridTrialProvider([aact, ClinicalTrialsGovProvider(snapshot_root=snapshot_root)])
    if normalized == "frozen":
        if fixture_path is None:
            raise ValueError("the frozen backend requires fixture_path")
        return FrozenTrialProvider.from_jsonl(fixture_path)
    raise ValueError(f"unknown trial backend {backend!r}; expected one of {KNOWN_BACKENDS}")
