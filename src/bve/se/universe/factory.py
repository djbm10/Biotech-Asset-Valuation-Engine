"""Backend selection for the trial universe.

The only place in the codebase that names a concrete backend. Callers pass a string that
came from a CLI flag or config and get a :class:`TrialUniverseProvider`; nothing
downstream imports a backend module directly.
"""

from __future__ import annotations

from pathlib import Path

from bve.se.universe.aact import AACTProvider
from bve.se.universe.ctgov import ClinicalTrialsGovProvider
from bve.se.universe.frozen import FrozenTrialProvider
from bve.se.universe.hybrid import HybridTrialProvider
from bve.se.universe.provider import TrialUniverseProvider

DEFAULT_BACKEND = "ctgov"
KNOWN_BACKENDS = ("ctgov", "aact", "hybrid", "frozen")


def build_trial_provider(
    backend: str = DEFAULT_BACKEND,
    *,
    snapshot_root: Path | None = None,
    aact_dsn: str | None = None,
    aact_release: str | None = None,
    fixture_path: Path | None = None,
) -> TrialUniverseProvider:
    """Construct the named backend.

    ``ctgov`` is the default because it requires no local infrastructure. ``hybrid``
    prefers AACT and falls back to the API, which is the production configuration once a
    mirror exists.
    """

    normalized = backend.strip().casefold()
    if normalized == "ctgov":
        return ClinicalTrialsGovProvider(snapshot_root=snapshot_root)
    if normalized == "aact":
        return AACTProvider(
            dsn=aact_dsn, snapshot_root=snapshot_root, snapshot_release=aact_release
        )
    if normalized == "hybrid":
        return HybridTrialProvider(
            [
                AACTProvider(
                    dsn=aact_dsn, snapshot_root=snapshot_root, snapshot_release=aact_release
                ),
                ClinicalTrialsGovProvider(snapshot_root=snapshot_root),
            ]
        )
    if normalized == "frozen":
        if fixture_path is None:
            raise ValueError("the frozen backend requires fixture_path")
        return FrozenTrialProvider.from_jsonl(fixture_path)
    raise ValueError(f"unknown trial backend {backend!r}; expected one of {KNOWN_BACKENDS}")
