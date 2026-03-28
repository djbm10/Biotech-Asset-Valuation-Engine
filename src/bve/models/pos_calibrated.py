"""
Calibrated PoS model — Sprint 17.

Hierarchical Bayesian model that blends industry priors (from industry_assumptions.yaml)
with posterior means derived from the calibration database (pos_predictions + pos_outcomes).

Blending rule
-------------
- N < N_PRIOR_ONLY   : use pure industry prior (< 10 outcomes in this (ta, phase) bin)
- N_PRIOR_ONLY ≤ N < N_FULL_POSTERIOR : blend posterior and prior linearly
  blend_weight = (N - N_PRIOR_ONLY) / (N_FULL_POSTERIOR - N_PRIOR_ONLY)
  base_rate = blend_weight × posterior + (1 - blend_weight) × industry_prior
- N ≥ N_FULL_POSTERIOR : use pure posterior (≥ 50 outcomes in bin)

The 95% credible interval uses a Beta posterior: Beta(α, β) where
  α = n_success + 1  (Jeffreys prior)
  β = n_failure + 1

Usage
-----
    from bve.models.pos_calibrated import CalibratedPOSModel

    # Load from live KnowledgeStore
    model = CalibratedPOSModel.from_store("outputs/intelligence/ops.db")
    rate = model.base_rate("oncology", "phase_2")
    lo, hi = model.confidence_interval("oncology", "phase_2")

    # Or build from raw prediction/outcome records
    model = CalibratedPOSModel.from_records(predictions, outcomes)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

N_PRIOR_ONLY = 10         # below this: use pure prior
N_FULL_POSTERIOR = 50     # at or above this: use pure posterior (no shrinkage)

# Jeffreys prior (Beta(0.5, 0.5)) — slightly more conservative than uniform
_JEFFREYS_A = 0.5
_JEFFREYS_B = 0.5

# Fallback base rate when no data and no prior
_FALLBACK_BASE_RATE = 0.40


@dataclass
class BinSummary:
    """Aggregated outcomes for one (ta, phase) bin."""

    ta: str
    phase: str
    n_total: int
    n_success: int
    n_failure: int
    posterior_mean: float          # Beta posterior mean
    industry_prior: float          # from industry_assumptions.yaml
    blended_rate: float            # the rate actually used
    blend_weight: float            # 0.0 = pure prior, 1.0 = pure posterior
    ci_lo: float                   # 95% credible interval lower bound
    ci_hi: float                   # 95% credible interval upper bound


@dataclass
class CalibratedPOSModel:
    """
    Hierarchical Bayesian PoS model blending industry priors with outcome data.

    Built via CalibratedPOSModel.from_records() or CalibratedPOSModel.from_store().
    Not constructed directly.
    """

    _bins: dict[tuple[str, str], BinSummary] = field(default_factory=dict)
    _industry_priors: dict[tuple[str, str], float] = field(default_factory=dict)
    _n_outcomes: int = 0
    _n_bins_calibrated: int = 0

    def base_rate(self, ta: str, phase: str) -> float:
        """
        Return the blended PoS base rate for (ta, phase).

        Falls back to industry prior if the bin has insufficient data,
        then to _FALLBACK_BASE_RATE if no prior is known.
        """
        key = (ta.lower(), phase.lower())
        bin_data = self._bins.get(key)
        if bin_data is not None:
            return bin_data.blended_rate
        # No bin: use industry prior or fallback
        return self._industry_priors.get(key, _FALLBACK_BASE_RATE)

    def confidence_interval(
        self,
        ta: str,
        phase: str,
        ci: float = 0.95,
    ) -> tuple[float, float]:
        """
        Return (lo, hi) credible interval for the (ta, phase) base rate.

        Uses Beta posterior if outcome data exists; otherwise returns a
        nominal ±0.10 interval around the industry prior.
        """
        key = (ta.lower(), phase.lower())
        bin_data = self._bins.get(key)
        if bin_data is not None:
            return (bin_data.ci_lo, bin_data.ci_hi)
        prior = self._industry_priors.get(key, _FALLBACK_BASE_RATE)
        return (max(0.0, prior - 0.10), min(1.0, prior + 0.10))

    def bin_summary(self, ta: str, phase: str) -> Optional[BinSummary]:
        """Return the BinSummary for (ta, phase), or None if no data."""
        return self._bins.get((ta.lower(), phase.lower()))

    def all_bins(self) -> list[BinSummary]:
        """Return all BinSummary objects sorted by (ta, phase)."""
        return sorted(self._bins.values(), key=lambda b: (b.ta, b.phase))

    @property
    def n_outcomes(self) -> int:
        return self._n_outcomes

    @property
    def n_bins_calibrated(self) -> int:
        """Number of (ta, phase) bins with at least some posterior weight."""
        return self._n_bins_calibrated

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_records(
        cls,
        predictions: "list",   # list[PredictionRecord]
        outcomes: "list",       # list[OutcomeRecord]
    ) -> "CalibratedPOSModel":
        """
        Build from in-memory PredictionRecord + OutcomeRecord lists.

        Only uses outcomes with non-None, non-'ongoing' outcome_type.
        """
        from bve.analysis.calibration_metrics import _SUCCESS_OUTCOMES
        from bve.config.assumptions_loader import AssumptionsLoader

        loader = AssumptionsLoader()
        outcome_map = {o.program_id: o for o in outcomes}

        # Aggregate by (ta, phase)
        bins: dict[tuple[str, str], dict] = {}
        for pred in predictions:
            outcome = outcome_map.get(pred.program_id)
            if outcome is None or outcome.outcome_type in (None, "ongoing"):
                continue
            key = (pred.ta.lower(), pred.phase.lower())
            if key not in bins:
                bins[key] = {"n": 0, "s": 0}
            bins[key]["n"] += 1
            if outcome.outcome_type in _SUCCESS_OUTCOMES:
                bins[key]["s"] += 1

        industry_priors = _build_prior_map(loader)
        model_bins: dict[tuple[str, str], BinSummary] = {}
        n_outcomes = sum(b["n"] for b in bins.values())
        n_calibrated = 0

        for (ta, phase), counts in bins.items():
            n = counts["n"]
            s = counts["s"]
            f = n - s
            industry_prior = industry_priors.get((ta, phase), _FALLBACK_BASE_RATE)
            summary = _build_bin_summary(ta, phase, n, s, f, industry_prior)
            model_bins[(ta, phase)] = summary
            if summary.blend_weight > 0:
                n_calibrated += 1

        model = cls(
            _bins=model_bins,
            _industry_priors=industry_priors,
            _n_outcomes=n_outcomes,
            _n_bins_calibrated=n_calibrated,
        )
        return model

    @classmethod
    def from_store(
        cls,
        db_path: Optional[Path] = None,
    ) -> "CalibratedPOSModel":
        """
        Build from the live KnowledgeStore at db_path.

        Loads predictions + outcomes, then delegates to from_records().
        Returns a pure-prior model if no outcomes exist yet.
        """
        from bve.analysis.calibration_metrics import OutcomeRecord, PredictionRecord
        from bve.intelligence.knowledge_layer import KnowledgeStore

        from bve.ops.weekly_runner import DB_PATH
        path = db_path or DB_PATH
        store = KnowledgeStore(path)
        try:
            pred_rows = store.get_pos_predictions(limit=10_000)
            outcome_rows = store.get_pos_outcomes()
        finally:
            store.close()

        predictions = [
            PredictionRecord(
                program_id=r["program_id"],
                ticker=r["ticker"],
                ta=r["ta"] or "other",
                phase=r["phase"] or "phase_2",
                model_pos=r["model_pos"],
                implied_pos=r["implied_pos"],
            )
            for r in pred_rows
        ]
        outcomes = [
            OutcomeRecord(
                program_id=r["program_id"],
                outcome_type=r["outcome_type"],
            )
            for r in outcome_rows
        ]
        return cls.from_records(predictions, outcomes)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_bin_summary(
    ta: str,
    phase: str,
    n: int,
    s: int,
    f: int,
    industry_prior: float,
) -> BinSummary:
    """Compute posterior, blending, and credible interval for one bin."""
    # Beta posterior (Jeffreys prior)
    alpha = s + _JEFFREYS_A
    beta = f + _JEFFREYS_B
    posterior_mean = alpha / (alpha + beta)

    # Blend weight
    if n < N_PRIOR_ONLY:
        blend_weight = 0.0
    elif n >= N_FULL_POSTERIOR:
        blend_weight = 1.0
    else:
        blend_weight = (n - N_PRIOR_ONLY) / (N_FULL_POSTERIOR - N_PRIOR_ONLY)

    blended_rate = blend_weight * posterior_mean + (1 - blend_weight) * industry_prior

    # 95% credible interval from Beta quantiles (Wilson approximation for speed)
    ci_lo, ci_hi = _beta_ci_approx(alpha, beta, 0.95)

    return BinSummary(
        ta=ta,
        phase=phase,
        n_total=n,
        n_success=s,
        n_failure=f,
        posterior_mean=round(posterior_mean, 4),
        industry_prior=round(industry_prior, 4),
        blended_rate=round(blended_rate, 4),
        blend_weight=round(blend_weight, 4),
        ci_lo=round(ci_lo, 4),
        ci_hi=round(ci_hi, 4),
    )


def _beta_ci_approx(alpha: float, beta: float, ci: float = 0.95) -> tuple[float, float]:
    """
    Approximate 95% credible interval for Beta(alpha, beta).

    Uses the normal approximation to the Beta distribution for speed.
    For small N, this is conservative (wider than exact).
    """
    mean = alpha / (alpha + beta)
    var = alpha * beta / ((alpha + beta) ** 2 * (alpha + beta + 1))
    std = math.sqrt(var)
    z = 1.96  # ~95%
    lo = max(0.0, mean - z * std)
    hi = min(1.0, mean + z * std)
    return lo, hi


def _build_prior_map(loader: "AssumptionsLoader") -> dict[tuple[str, str], float]:  # type: ignore[name-defined]  # noqa: F821
    """
    Extract {(ta, phase): base_rate} from AssumptionsLoader.

    Handles the nested PHASE_SUCCESS_RATES structure.
    """
    try:
        data = loader.phase_success_rates()  # returns MappingProxyType
        priors: dict[tuple[str, str], float] = {}
        for ta, phases in data.items():
            if isinstance(phases, dict):
                for phase, rate in phases.items():
                    if isinstance(rate, (int, float)):
                        priors[(ta.lower(), phase.lower())] = float(rate)
        return priors
    except Exception:  # noqa: BLE001
        return {}
