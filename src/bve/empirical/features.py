"""
Overlay feature engineering — deterministic binary feature extraction from
POSOutcomeRecord or POSAdjusters inputs.

Feature set (11 binary indicators):
    moa_validated, moa_novel
        MoA tier; "partial" is the baseline/omitted category.
    biomarker_selected
        Biomarker-enriched population; False is baseline.
    endpoint_hard_clinical, endpoint_surrogate_novel, endpoint_biomarker_only
        Endpoint type; "surrogate_validated" is baseline.
    safety_clean, safety_concerning, safety_serious
        Safety profile; "minor" is baseline.
    competition_low, competition_high
        Competitive pressure; "moderate" is baseline.

Missing values (None) map to all-zero indicators — equivalent to the baseline
category for that dimension. This prevents feature sparsity from blocking
inference on records with incomplete annotations.

Usage
-----
from bve.empirical.features import (
    FEATURE_NAMES,
    build_feature_vector,
    build_feature_vector_from_adjusters,
    record_to_adjusters,
    feature_coverage,
)
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from bve.empirical.pos_outcome import POSOutcomeRecord

# ---------------------------------------------------------------------------
# Feature definition
# ---------------------------------------------------------------------------

FEATURE_NAMES: list[str] = [
    "moa_validated",
    "moa_novel",
    "biomarker_selected",
    "endpoint_hard_clinical",
    "endpoint_surrogate_novel",
    "endpoint_biomarker_only",
    "safety_clean",
    "safety_concerning",
    "safety_serious",
    "competition_low",
    "competition_high",
]

# Baseline categories (omitted to avoid perfect multicollinearity):
#   moa_precedent:       "partial"
#   endpoint_type:       "surrogate_validated"
#   safety_profile:      "minor"
#   competitive_pressure: "moderate"

N_FEATURES: int = len(FEATURE_NAMES)

# Expected coefficient signs based on domain knowledge.
# +1  = feature should increase POS (positive log-odds)
# -1  = feature should decrease POS (negative log-odds)
#  0  = no constraint; direction is fully data-determined
# Used by fit_overlay() to zero out economically/clinically nonsensical signs.
EXPECTED_SIGNS: dict[str, int] = {
    "moa_validated":           +1,   # validated MoA → more credible → should help
    "moa_novel":               -1,   # unproven mechanism → riskier
    "biomarker_selected":      +1,   # enriched population → more responsive
    "endpoint_hard_clinical":   0,   # directionally ambiguous; leave data-determined
    "endpoint_surrogate_novel": -1,  # unvalidated surrogate → regulatory risk
    "endpoint_biomarker_only":  -1,  # weakest endpoint class → must be negative
    "safety_clean":            +1,   # clean profile → fewer terminations
    "safety_concerning":       -1,   # AE signals → failure risk
    "safety_serious":          -1,   # CRITICAL: serious AEs must penalise — never positive
    "competition_low":         +1,   # less competition → better enrollment/survival
    "competition_high":        -1,   # crowded market → enrollment pressure
}

# Minimum training records required to attempt fitting the overlay.
MIN_OVERLAY_RECORDS: int = 10


# ---------------------------------------------------------------------------
# Feature extraction from POSOutcomeRecord
# ---------------------------------------------------------------------------

def build_feature_vector(record: "POSOutcomeRecord") -> list[float]:
    """
    Extract the 11-dimensional binary feature vector from a POSOutcomeRecord.

    Missing values (None fields) produce all-zero indicators for that
    dimension, which is equivalent to the baseline category.

    Parameters
    ----------
    record:
        A validated POSOutcomeRecord (censored rows excluded).

    Returns
    -------
    list[float] of length N_FEATURES (11), each element 0.0 or 1.0.
    In the same order as FEATURE_NAMES.
    """
    moa = record.moa_precedent        # "validated" | "partial" | "novel" | None
    ep  = record.endpoint_type         # "hard_clinical" | "surrogate_validated" | ...
    sf  = record.safety_profile        # "clean" | "minor" | "concerning" | "serious"
    cp  = record.competitive_pressure  # "low" | "moderate" | "high"
    bio = bool(record.biomarker_selected)

    return [
        1.0 if moa == "validated" else 0.0,          # moa_validated
        1.0 if moa == "novel" else 0.0,               # moa_novel
        1.0 if bio else 0.0,                          # biomarker_selected
        1.0 if ep == "hard_clinical" else 0.0,        # endpoint_hard_clinical
        1.0 if ep == "surrogate_novel" else 0.0,      # endpoint_surrogate_novel
        1.0 if ep == "biomarker_only" else 0.0,       # endpoint_biomarker_only
        1.0 if sf == "clean" else 0.0,                # safety_clean
        1.0 if sf == "concerning" else 0.0,           # safety_concerning
        1.0 if sf == "serious" else 0.0,              # safety_serious
        1.0 if cp == "low" else 0.0,                  # competition_low
        1.0 if cp == "high" else 0.0,                 # competition_high
    ]


def build_feature_vector_from_adjusters(adjusters) -> list[float]:
    """
    Extract the 11-dimensional binary feature vector from a POSAdjusters object.

    Used at valuation time when a POSOutcomeRecord is not available. The
    POSAdjusters enum values are converted to the same string representations
    used in POSOutcomeRecord so that feature vectors are identical.

    Parameters
    ----------
    adjusters:
        POSAdjusters from bve.models.pos_model. If None, returns zero vector.

    Returns
    -------
    list[float] of length N_FEATURES (11).
    """
    if adjusters is None:
        return [0.0] * N_FEATURES

    def _val(obj) -> Optional[str]:
        """Extract .value string from enum or return str(obj)."""
        if obj is None:
            return None
        return obj.value if hasattr(obj, "value") else str(obj)

    moa = _val(getattr(adjusters, "moa_precedent", None))
    ep  = _val(getattr(adjusters, "endpoint_type", None))
    sf  = _val(getattr(adjusters, "safety_profile", None))
    cp  = _val(getattr(adjusters, "competitive_pressure", None))
    bio = bool(getattr(adjusters, "biomarker_selected_population", False))

    return [
        1.0 if moa == "validated" else 0.0,
        1.0 if moa == "novel" else 0.0,
        1.0 if bio else 0.0,
        1.0 if ep == "hard_clinical" else 0.0,
        1.0 if ep == "surrogate_novel" else 0.0,
        1.0 if ep == "biomarker_only" else 0.0,
        1.0 if sf == "clean" else 0.0,
        1.0 if sf == "concerning" else 0.0,
        1.0 if sf == "serious" else 0.0,
        1.0 if cp == "low" else 0.0,
        1.0 if cp == "high" else 0.0,
    ]


# ---------------------------------------------------------------------------
# Record ↔ POSAdjusters conversion
# ---------------------------------------------------------------------------

def record_to_adjusters(record: "POSOutcomeRecord"):
    """
    Convert a POSOutcomeRecord to a POSAdjusters object.

    Used for computing heuristic POS predictions on outcome records so that
    all modes can be compared on the same dataset.  Missing categorical fields
    map to the baseline enum value for that dimension.

    Parameters
    ----------
    record:
        A validated POSOutcomeRecord.

    Returns
    -------
    POSAdjusters
    """
    from bve.models.pos_model import (
        POSAdjusters,
        MoAPrecedent,
        SafetyProfile,
        CompetitivePressure,
    )
    from bve.entities.trial import EndpointType

    _moa_map: dict[str, MoAPrecedent] = {
        "validated": MoAPrecedent.VALIDATED,
        "partial": MoAPrecedent.PARTIAL,
        "novel": MoAPrecedent.NOVEL,
    }
    _ep_map: dict[str, EndpointType] = {
        "hard_clinical": EndpointType.HARD_CLINICAL,
        "surrogate_validated": EndpointType.SURROGATE_VALIDATED,
        "surrogate_novel": EndpointType.SURROGATE_NOVEL,
        "biomarker_only": EndpointType.BIOMARKER_ONLY,
    }
    _sf_map: dict[str, SafetyProfile] = {
        "clean": SafetyProfile.CLEAN,
        "minor": SafetyProfile.MINOR,
        "concerning": SafetyProfile.CONCERNING,
        "serious": SafetyProfile.SERIOUS,
    }
    _cp_map: dict[str, CompetitivePressure] = {
        "low": CompetitivePressure.LOW,
        "moderate": CompetitivePressure.MODERATE,
        "high": CompetitivePressure.HIGH,
    }

    return POSAdjusters(
        endpoint_type=_ep_map.get(
            record.endpoint_type or "", EndpointType.SURROGATE_VALIDATED
        ),
        moa_precedent=_moa_map.get(
            record.moa_precedent or "", MoAPrecedent.PARTIAL
        ),
        safety_profile=_sf_map.get(
            record.safety_profile or "", SafetyProfile.MINOR
        ),
        competitive_pressure=_cp_map.get(
            record.competitive_pressure or "", CompetitivePressure.MODERATE
        ),
        biomarker_selected_population=bool(record.biomarker_selected),
    )


# ---------------------------------------------------------------------------
# Dataset inspection helpers
# ---------------------------------------------------------------------------

def feature_coverage(records: list["POSOutcomeRecord"]) -> dict[str, float]:
    """
    Fraction of records with a non-zero value for each feature.

    A value near 0.0 means the feature is almost always at its baseline
    (e.g., almost nobody has safety_serious).  Very low coverage features
    will have high-variance, poorly-identified coefficients.

    Parameters
    ----------
    records:
        List of outcome records (censored excluded).

    Returns
    -------
    dict mapping feature_name → fraction in [0.0, 1.0].
    """
    if not records:
        return {name: 0.0 for name in FEATURE_NAMES}
    n = len(records)
    totals = [0.0] * N_FEATURES
    for rec in records:
        fv = build_feature_vector(rec)
        for i, v in enumerate(fv):
            totals[i] += v
    return {FEATURE_NAMES[i]: round(totals[i] / n, 4) for i in range(N_FEATURES)}


def sparsity_report(
    records: list["POSOutcomeRecord"],
    sparse_threshold: float = 0.05,
) -> dict:
    """
    Summary of feature coverage and thin-feature warnings.

    Parameters
    ----------
    records:
        List of outcome records.
    sparse_threshold:
        Features with coverage < threshold are flagged as sparse.

    Returns
    -------
    dict with keys: coverage (dict), sparse_features (list[str]),
    n_records (int), n_features (int).
    """
    cov = feature_coverage(records)
    sparse = [name for name, frac in cov.items() if frac < sparse_threshold]
    return {
        "n_records": len(records),
        "n_features": N_FEATURES,
        "coverage": cov,
        "sparse_features": sparse,
        "sparse_threshold": sparse_threshold,
    }
