"""
Wave 6 — Endpoint Benchmarking with z-scores and shrinkage.

Positions a trial's primary endpoint result within the distribution of
approved drugs for the same indication and endpoint type.  Produces a
quantitative ``EndpointEvaluation`` that includes:

  - z_score          — standardised position within the approval reference class
  - category         — EXCELLENT / ABOVE_THRESHOLD / ABOVE_SOC / BELOW_SOC
  - pos_modifier     — additive log-odds term for PoS adjustment (bounded ±0.20)
  - shrinkage_applied — True when prior inflates std_dev to guard against small N

Normalization
-------------
Hazard-ratio endpoints (pfs_hr, os_hr, ttp_hr, dfs_hr, efs_hr) are mapped to a
"higher = better" scale via ``-log(HR)``.  All other endpoints (ORR, CR rate,
PASI90, ACR50 …) pass through unchanged.

Shrinkage
---------
When the reference class is small (few approved drugs), the sample standard
deviation is unreliable.  We add a per-endpoint prior std in quadrature:

    std_adj = sqrt(std_sample² + prior_std²)

The prior_std values live in ``industry_assumptions.yaml`` under
``endpoint_benchmarking.prior_std``.  Hard-coded defaults are used as fallback.

No new network calls
--------------------
All data comes from ``endpoint_benchmarks.yaml`` (static YAML) and the
pre-loaded ``AssumptionsLoader`` singleton.
"""
from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Endpoint normalization
# ---------------------------------------------------------------------------

_HAZARD_RATIO_ENDPOINTS = frozenset({"pfs_hr", "os_hr", "ttp_hr", "dfs_hr", "efs_hr"})


def normalize_endpoint(value: float, endpoint_type: str) -> float:
    """
    Map an endpoint value to a "higher = better" normalized scale.

    Hazard-ratio endpoints: ``-log(value)``  (HR < 1 is good → positive)
    All other endpoints:    pass-through     (ORR, CR, PASI90 etc.)

    Parameters
    ----------
    value:
        Raw observed or reference value.
    endpoint_type:
        Endpoint key string (e.g. ``"pfs_hr"``, ``"orr"``).
    """
    if endpoint_type in _HAZARD_RATIO_ENDPOINTS:
        return -math.log(max(value, 1e-6))
    return value


# ---------------------------------------------------------------------------
# Prior std defaults (fallback when YAML section absent)
# ---------------------------------------------------------------------------

_PRIOR_STD_DEFAULTS: dict[str, float] = {
    "orr":     0.13,
    "pfs_hr":  0.10,
    "os_hr":   0.08,
    "cr_rate": 0.11,
    "pasi90":  0.12,
    "acr50":   0.10,
    "efs_hr":  0.09,
    "default": 0.12,
}


# ---------------------------------------------------------------------------
# EndpointEvaluation model
# ---------------------------------------------------------------------------

class EndpointEvaluation(BaseModel, frozen=True):
    """
    Result of positioning a trial result within the approval reference class.

    Attributes
    ----------
    observed_value:
        Raw endpoint value as reported (e.g. 0.45 for 45% ORR).
    normalized_observed:
        Value after normalization (−log for HR types; passthrough otherwise).
    soc_baseline:
        Standard-of-care comparator value from the benchmark database, if present.
    z_score:
        Distance from the mean of approved drugs in units of ``std_adjusted``.
    n_reference_drugs:
        Number of approved drugs in the reference class.
    std_sample:
        Sample std of the approved-drug normalized values.
    std_adjusted:
        Std after adding prior in quadrature (shrinkage-corrected).
    shrinkage_applied:
        True when ``std_adjusted > std_sample`` (prior inflated the estimate).
    category:
        ``"EXCELLENT"`` (z ≥ 1.5), ``"ABOVE_THRESHOLD"`` (z ≥ 0.5),
        ``"ABOVE_SOC"`` (z ≥ −0.5), ``"BELOW_SOC"`` (z < −0.5).
    pos_modifier:
        Additive log-odds term for PoS adjustment; bounded in [−0.20, 0.20].
        Formula: ``clip(0.10 × z, −0.20, 0.20)``.
    comparable_approvals:
        List of reference dicts from the benchmark database for this class.
    """
    observed_value:      float
    normalized_observed: float
    soc_baseline:        Optional[float]
    z_score:             float
    n_reference_drugs:   int
    std_sample:          float
    std_adjusted:        float
    shrinkage_applied:   bool
    category:            str
    pos_modifier:        float
    comparable_approvals: list[dict]


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class EndpointBenchmarkEvaluator:
    """
    Evaluate a trial endpoint result against the approval reference class.

    Parameters
    ----------
    benchmarks_path:
        Path to ``endpoint_benchmarks.yaml``.  Resolved relative to the
        project root when a relative path is given.
    """

    def __init__(
        self,
        benchmarks_path: str = "src/bve/config/endpoint_benchmarks.yaml",
    ) -> None:
        self._path = Path(benchmarks_path)
        self._data: Optional[dict] = None
        self._prior_std: dict[str, float] = self._load_prior_std()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def evaluate(
        self,
        observed_value: float,
        endpoint_type: str,
        indication: str,
        line_of_therapy: str = "first_line",
    ) -> Optional[EndpointEvaluation]:
        """
        Evaluate *observed_value* against the approval reference class.

        Parameters
        ----------
        observed_value:
            Raw observed endpoint value (e.g. 0.45 for 45% ORR, 0.60 for HR).
        endpoint_type:
            Endpoint key (``"orr"``, ``"pfs_hr"``, ``"cr_rate"``, …).
        indication:
            Indication key matching the benchmark YAML structure
            (e.g. ``"nsclc"``, ``"plaque_psoriasis"``, ``"aml_relapsed"``).
        line_of_therapy:
            Line-of-therapy key (e.g. ``"first_line"``, ``"second_line"``).
            Defaults to ``"first_line"``.

        Returns
        -------
        ``EndpointEvaluation`` or ``None`` when the indication/endpoint
        combination is not found in the benchmark database.
        """
        benchmark = self._load_benchmark(indication, line_of_therapy, endpoint_type)
        if benchmark is None:
            return None

        approved_drugs = benchmark.get("approved_drugs", [])
        if not approved_drugs:
            return None

        # Normalize
        normalized_observed = normalize_endpoint(observed_value, endpoint_type)
        approved_normalized = [
            normalize_endpoint(float(d["value"]), endpoint_type)
            for d in approved_drugs
        ]

        n_approved = len(approved_normalized)
        mean_n = statistics.mean(approved_normalized)
        std_n  = statistics.stdev(approved_normalized) if n_approved > 1 else 0.0

        # Shrinkage: add prior std in quadrature
        prior_std = self._prior_std.get(endpoint_type, self._prior_std.get("default", 0.12))
        std_adj   = math.sqrt(std_n ** 2 + prior_std ** 2)

        z_score = (normalized_observed - mean_n) / std_adj

        category     = _categorize(z_score)
        pos_modifier = _pos_modifier(z_score)

        return EndpointEvaluation(
            observed_value      = observed_value,
            normalized_observed = normalized_observed,
            soc_baseline        = benchmark.get("soc_baseline"),
            z_score             = round(z_score, 4),
            n_reference_drugs   = n_approved,
            std_sample          = round(std_n, 6),
            std_adjusted        = round(std_adj, 6),
            shrinkage_applied   = std_adj > std_n,
            category            = category,
            pos_modifier        = round(pos_modifier, 4),
            comparable_approvals= list(approved_drugs),
        )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _load_benchmark(
        self,
        indication: str,
        line_of_therapy: str,
        endpoint_type: str,
    ) -> Optional[dict]:
        """
        Traverse the benchmark YAML tree and return the endpoint dict or None.

        The YAML is structured as:
          <therapeutic_area> → <indication_key> → <line_of_therapy> → <endpoint_type>

        We search all top-level therapeutic_area nodes for the indication key.
        """
        data = self._get_data()
        if not data:
            return None

        ind_lower = indication.lower().replace(" ", "_").replace("-", "_")

        for _ta, ta_dict in data.items():
            if not isinstance(ta_dict, dict):
                continue
            # Try direct match first, then fuzzy
            for ind_key, ind_dict in ta_dict.items():
                if not isinstance(ind_dict, dict):
                    continue
                if ind_key.lower() == ind_lower or ind_lower in ind_key.lower():
                    lot_dict = ind_dict.get(line_of_therapy)
                    if isinstance(lot_dict, dict):
                        ep_dict = lot_dict.get(endpoint_type)
                        if isinstance(ep_dict, dict):
                            return ep_dict
        return None

    def _get_data(self) -> dict:
        if self._data is None:
            self._data = self._read_yaml()
        return self._data or {}

    def _read_yaml(self) -> dict:
        try:
            import yaml  # pyyaml
            path = self._path if self._path.is_absolute() else Path.cwd() / self._path
            if not path.exists():
                # Try relative to this file's package root
                here = Path(__file__).resolve().parent.parent
                path = here / "config" / "endpoint_benchmarks.yaml"
            with open(path, "r") as fh:
                return yaml.safe_load(fh) or {}
        except Exception:
            return {}

    @staticmethod
    def _load_prior_std() -> dict[str, float]:
        try:
            from bve.config.assumptions_loader import AssumptionsLoader
            from bve.intelligence.trial_design_feature_extractor import _unfreeze
            data = AssumptionsLoader.get()._data
            section = data.get("endpoint_benchmarking")
            if section:
                raw = _unfreeze(section)
                prior = raw.get("prior_std", {})
                if prior:
                    return {k: float(v) for k, v in prior.items()}
        except Exception:
            pass
        return dict(_PRIOR_STD_DEFAULTS)


# ---------------------------------------------------------------------------
# Category and pos_modifier helpers
# ---------------------------------------------------------------------------

def _categorize(z: float) -> str:
    if z >= 1.5:
        return "EXCELLENT"
    if z >= 0.5:
        return "ABOVE_THRESHOLD"
    if z >= -0.5:
        return "ABOVE_SOC"
    return "BELOW_SOC"


def _pos_modifier(z: float) -> float:
    """Bounded additive log-odds term: clip(0.10 × z, −0.20, 0.20)."""
    return max(-0.20, min(0.20, 0.10 * z))
