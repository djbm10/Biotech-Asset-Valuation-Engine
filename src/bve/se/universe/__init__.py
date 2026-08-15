"""Source-agnostic trial universe layer (M9B)."""

from bve.se.universe.aact import AACTProvider
from bve.se.universe.ctgov import ClinicalTrialsGovProvider, normalize_study
from bve.se.universe.factory import DEFAULT_BACKEND, KNOWN_BACKENDS, build_trial_provider
from bve.se.universe.frozen import FrozenTrialProvider
from bve.se.universe.hybrid import HybridTrialProvider
from bve.se.universe.provider import (
    CLINICALTRIALS_GOV,
    TrialIntervention,
    TrialQuery,
    TrialRecord,
    TrialSnapshot,
    TrialUniverseProvider,
    TrialUniverseResult,
    parse_registry_date,
)

__all__ = [
    "AACTProvider",
    "CLINICALTRIALS_GOV",
    "ClinicalTrialsGovProvider",
    "DEFAULT_BACKEND",
    "FrozenTrialProvider",
    "HybridTrialProvider",
    "KNOWN_BACKENDS",
    "TrialIntervention",
    "TrialQuery",
    "TrialRecord",
    "TrialSnapshot",
    "TrialUniverseProvider",
    "TrialUniverseResult",
    "build_trial_provider",
    "normalize_study",
    "parse_registry_date",
]
