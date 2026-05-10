"""
Monte Carlo simulation engine.

Samples from joint distributions of uncertain inputs using a Gaussian copula
for correlations, then runs compute_rnpv() for each draw.

Key uncertain variables and their distributions
-----------------------------------------------
  peak_sales:      log-normal (CV specified as fraction of base case)
  penetration:     beta (derived from base case + CV)
  discount_rate:   normal, clipped to (0.01, 0.50)
  years_to_peak:   normal, rounded + clipped to [1, 20]
  phase_success:   beta per phase (alpha/beta from mean + ESS)
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Optional

import numpy as np
from pydantic import BaseModel, Field, model_validator
from scipy.stats import lognorm, norm

from bve.config.constants import (
    MC_N_SIMULATIONS, MC_PEAK_SALES_CV, MC_PEAK_SALES_CV_BY_STAGE,
    MC_DISCOUNT_RATE_STD, MC_PHASE_ESS,
    MC_YEARS_TO_PEAK_STD, MC_PATENT_LIFE_STD,
)
from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.correlations import CorrelationSpec, DEFAULT_CORRELATION, correlated_uniform_samples
from bve.models.market_model import MarketModel
from bve.models.rnpv_model import RNPVResult, compute_rnpv_full

if TYPE_CHECKING:
    from bve.models.deal_economics import DealEconomics


class MCMode(str, Enum):
    """
    Monte Carlo sampling mode.

    SIMPLE (default)
        Directly sample ``peak_sales`` as a single log-normal draw.  Fast and
        appropriate for portfolio screening.

    DRIVER_BASED
        Decompose peak_sales into its constituent drivers
        (eligible_patients × net_price × peak_penetration × payer_access × geography)
        and sample each independently.  Preferred for BD/M&A analysis because
        individual driver distributions are auditable and correlations are
        structurally explicit.

    Hard constraint: cannot enable ``sample_peak_sales=True`` AND any driver-based
    flag simultaneously — doing so would double-count commercial uncertainty.
    ``_validate_no_double_counting()`` enforces this at construction time.
    """

    SIMPLE = "simple"
    DRIVER_BASED = "driver_based"


class PhaseSuccessDistribution(BaseModel):
    phase: TrialPhase
    mean: float = Field(gt=0.0, lt=1.0)
    equivalent_sample_size: float = Field(
        default=20.0, gt=0.0,
        description="Higher = tighter prior; alpha = mean × ESS, beta = (1-mean) × ESS"
    )

    @property
    def alpha(self) -> float:
        return self.mean * self.equivalent_sample_size

    @property
    def beta_param(self) -> float:
        return (1.0 - self.mean) * self.equivalent_sample_size


class MonteCarloParams(BaseModel):
    n_simulations: int = Field(default=MC_N_SIMULATIONS, gt=0)
    random_seed: Optional[int] = None

    # Sampling mode
    mode: MCMode = MCMode.SIMPLE

    # ── SIMPLE mode parameters ──────────────────────────────────────────────
    # sample_peak_sales=True: draw peak_sales as a single log-normal.
    # Must be False in DRIVER_BASED mode (enforced by validator below).
    sample_peak_sales: bool = True
    peak_sales_cv: float = Field(default=MC_PEAK_SALES_CV, gt=0.0)
    discount_rate_std: float = Field(default=MC_DISCOUNT_RATE_STD, gt=0.0)
    years_to_peak_std: float = Field(default=MC_YEARS_TO_PEAK_STD, gt=0.0)
    patent_life_std: float = Field(default=MC_PATENT_LIFE_STD, gt=0.0)

    # ── DRIVER_BASED mode parameters ────────────────────────────────────────
    # Each flag activates sampling of that driver; its CV controls dispersion.
    # peak_sales = base_peak × ∏(sampled driver multipliers).
    sample_eligible_patients: bool = False
    eligible_patients_cv: float = Field(default=0.30, gt=0.0)

    sample_net_price: bool = False
    net_price_cv: float = Field(default=0.20, gt=0.0)

    sample_peak_penetration: bool = False
    peak_penetration_cv: float = Field(default=0.25, gt=0.0)

    sample_payer_access: bool = False
    payer_access_cv: float = Field(default=0.20, gt=0.0)

    sample_geography: bool = False
    geography_cv: float = Field(default=0.15, gt=0.0)

    # Per-phase success distributions (override trial point estimates)
    phase_distributions: list[PhaseSuccessDistribution] = Field(default_factory=list)

    # Correlation structure
    correlation_spec: Optional[CorrelationSpec] = None
    use_default_correlations: bool = Field(
        default=True,
        description="Apply DEFAULT_CORRELATION if correlation_spec is None"
    )

    @model_validator(mode="after")
    def _validate_no_double_counting(self) -> "MonteCarloParams":
        """
        Raise ValueError when peak_sales is sampled directly AND any underlying
        driver is also being sampled.  That would double-count commercial
        uncertainty (peak_sales is itself the product of those drivers).
        """
        driver_flags = [
            self.sample_eligible_patients,
            self.sample_net_price,
            self.sample_peak_penetration,
            self.sample_payer_access,
            self.sample_geography,
        ]
        if self.sample_peak_sales and any(driver_flags):
            active = [
                name for name, flag in zip(
                    ["eligible_patients", "net_price", "peak_penetration",
                     "payer_access", "geography"],
                    driver_flags,
                )
                if flag
            ]
            raise ValueError(
                f"Double-counting: sample_peak_sales=True cannot be combined with "
                f"driver-based sampling of {active}. "
                f"Set sample_peak_sales=False when using DRIVER_BASED mode."
            )
        return self


class MonteCarloResult(BaseModel):
    asset_id: str
    n_simulations: int

    mean_millions: float
    median_millions: float
    std_millions: float

    percentile_5_millions: float
    percentile_10_millions: float
    percentile_25_millions: float
    percentile_50_millions: float
    percentile_75_millions: float
    percentile_90_millions: float
    percentile_95_millions: float

    probability_positive: float
    probability_above_500m: float
    probability_above_1b: float

    # Sorted simulation outputs
    simulated_values_millions: list[float]

    # Which CV was actually used (stage-conditional or explicit override)
    peak_sales_cv_used: float = MC_PEAK_SALES_CV

    # Mode that produced this result
    mode_used: MCMode = MCMode.SIMPLE

    # Expected NAV/share (set externally)
    mean_nav_per_share: Optional[float] = None


def _resolve_peak_sales_cv(asset: Asset, params: MonteCarloParams) -> float:
    """
    Return the appropriate peak_sales_cv for this asset.

    When params.peak_sales_cv is the module default (MC_PEAK_SALES_CV), look up
    the stage-conditional table from industry_assumptions.yaml instead — earlier
    stages have genuinely wider commercial uncertainty.  An explicitly overridden
    params.peak_sales_cv (different from the module default) is always respected.
    """
    if params.peak_sales_cv != MC_PEAK_SALES_CV:
        # Caller set an explicit override — respect it.
        return params.peak_sales_cv
    stage_key = asset.stage.value if asset.stage is not None else "default"
    return MC_PEAK_SALES_CV_BY_STAGE.get(stage_key, MC_PEAK_SALES_CV)


def run_monte_carlo(
    asset: Asset,
    trials: list[ClinicalTrial],
    market_model: MarketModel,
    params: MonteCarloParams,
    *,
    loe_profile: Optional[dict] = None,
    deal: Optional["DealEconomics"] = None,  # type: ignore[name-defined]
) -> MonteCarloResult:
    """
    Run Monte Carlo simulation. Returns full distribution of rNPV values.

    Each simulation independently samples:
      - Phase success probabilities (beta)
      - Peak sales (log-normal via correlated uniform)
      - Discount rate (normal)
      - Years to peak (normal → integer)
      - Patent life (normal → integer)

    loe_profile and deal are fixed economic context — they do not vary per
    simulation.  Pass them to match the deterministic base case economic stack.
    """
    rng = np.random.default_rng(params.random_seed)
    n = params.n_simulations
    peak_sales_cv = _resolve_peak_sales_cv(asset, params)

    # Build phase success distribution lookup
    phase_dist_map: dict[TrialPhase, PhaseSuccessDistribution] = {
        d.phase: d for d in params.phase_distributions
    }

    # Pre-sample phase success probabilities
    phase_success_samples: dict[TrialPhase, np.ndarray] = {}
    for trial in trials:
        if trial.phase in phase_success_samples:
            continue
        if trial.phase in phase_dist_map:
            d = phase_dist_map[trial.phase]
            phase_success_samples[trial.phase] = rng.beta(d.alpha, d.beta_param, n)
        else:
            ess_key = trial.phase.value
            ess = MC_PHASE_ESS.get(ess_key, 20)
            mu = trial.success_probability
            a = mu * ess
            b = (1 - mu) * ess
            phase_success_samples[trial.phase] = rng.beta(a, b, n)

    # Correlated sampling for market parameters
    spec = params.correlation_spec
    if spec is None and params.use_default_correlations:
        spec = DEFAULT_CORRELATION

    if spec is not None:
        uniform_samples = correlated_uniform_samples(spec, n, rng)
    else:
        uniform_samples = {v: rng.uniform(0, 1, n) for v in ["peak_sales", "penetration", "discount_rate", "years_to_peak"]}

    # Peak sales sampling — SIMPLE mode: single log-normal draw
    base_peak = market_model.peak_sales_millions

    if params.sample_peak_sales:
        sigma_ln = np.sqrt(np.log(1 + peak_sales_cv ** 2))
        mu_ln = np.log(base_peak) - 0.5 * sigma_ln ** 2
        u_sales = uniform_samples.get("peak_sales", rng.uniform(0, 1, n))
        peak_sales_samples: np.ndarray = lognorm(s=sigma_ln, scale=np.exp(mu_ln)).ppf(
            np.clip(u_sales, 1e-6, 1 - 1e-6)
        )
    else:
        # DRIVER_BASED mode: build peak_sales from active driver multipliers.
        # Each driver mult is log-normal with mean=1.0 and the specified CV.
        # Inactive drivers contribute a multiplier of 1.0 (no variation).
        peak_sales_samples = np.full(n, base_peak, dtype=float)

    # Pre-sample driver multipliers for DRIVER_BASED mode
    def _lognormal_mult(cv: float) -> np.ndarray:
        """Log-normal multiplier with mean=1.0 and coefficient of variation cv."""
        s = np.sqrt(np.log(1 + cv ** 2))
        # scale = exp(mu) where mu = -0.5*s^2 ensures median=1 and mean≈1
        return lognorm(s=s, scale=np.exp(-0.5 * s ** 2)).rvs(n, random_state=rng)

    patient_mults = _lognormal_mult(params.eligible_patients_cv) if params.sample_eligible_patients else np.ones(n)
    price_mults = _lognormal_mult(params.net_price_cv) if params.sample_net_price else np.ones(n)
    penetration_mults = _lognormal_mult(params.peak_penetration_cv) if params.sample_peak_penetration else np.ones(n)
    payer_mults = _lognormal_mult(params.payer_access_cv) if params.sample_payer_access else np.ones(n)
    geo_mults = _lognormal_mult(params.geography_cv) if params.sample_geography else np.ones(n)

    if not params.sample_peak_sales:
        # Compose driver multipliers into peak_sales draws
        peak_sales_samples = base_peak * patient_mults * price_mults * penetration_mults * payer_mults * geo_mults

    # Discount rate: normal via inverse CDF
    u_dr = uniform_samples.get("discount_rate", rng.uniform(0, 1, n))
    dr_samples = norm.ppf(np.clip(u_dr, 1e-6, 1 - 1e-6), loc=asset.discount_rate, scale=params.discount_rate_std)
    dr_samples = np.clip(dr_samples, 0.01, 0.50)

    # Years to peak: normal → integer
    u_ytp = uniform_samples.get("years_to_peak", rng.uniform(0, 1, n))
    ytp_samples = norm.ppf(np.clip(u_ytp, 1e-6, 1 - 1e-6), loc=market_model.years_to_peak, scale=params.years_to_peak_std)
    ytp_samples = np.clip(np.round(ytp_samples), 1, 20).astype(int)

    simulated: list[float] = []

    for i in range(n):
        sim_asset = asset.model_copy(update={"discount_rate": float(dr_samples[i])})

        new_peak_sales = float(peak_sales_samples[i])
        if market_model.total_addressable_market_millions is not None:
            new_tam = new_peak_sales / market_model.peak_penetration
            sim_market = market_model.model_copy(
                update={"total_addressable_market_millions": new_tam, "years_to_peak": int(ytp_samples[i]), "uptake_curve": None}
            )
        else:
            # Scale net_price_per_patient to hit new peak sales
            new_price = new_peak_sales * 1e6 / (
                (market_model.addressable_patients_annual or 1)
                * (market_model.compliance_rate or 1)
                * market_model.peak_penetration
            )
            sim_market = market_model.model_copy(
                update={"net_price_per_patient_usd": new_price, "years_to_peak": int(ytp_samples[i]), "uptake_curve": None}
            )

        # Phase 1B: per-simulation probabilistic competitor entry.
        # Approved competitors always present; pipeline competitors included
        # via Bernoulli draw (approval_probability). See CompetitionModel.sample_launch_outcomes.
        if market_model.competition_model is not None and market_model.competition_model.competitors:
            sampled_comp = market_model.competition_model.sample_launch_outcomes(rng)
            sim_market = sim_market.model_copy(update={"competition_model": sampled_comp})

        sim_trials = [
            t.model_copy(update={"success_probability": float(phase_success_samples[t.phase][i])})
            for t in trials
        ]

        result: RNPVResult = compute_rnpv_full(
            sim_asset, sim_trials, sim_market,
            loe_profile=loe_profile, deal=deal,
        )
        simulated.append(result.rnpv_millions)

    arr = np.array(simulated)
    sorted_vals = sorted(simulated)

    def _r5(v: float) -> float:
        """Round to nearest $5M — MC precision is entirely determined by ESS priors."""
        return round(v / 5.0) * 5.0

    return MonteCarloResult(
        asset_id=asset.id,
        n_simulations=n,
        peak_sales_cv_used=peak_sales_cv,
        mode_used=params.mode,
        mean_millions=round(float(np.mean(arr)), 0),
        median_millions=round(float(np.median(arr)), 0),
        std_millions=round(float(np.std(arr)), 0),
        percentile_5_millions=_r5(float(np.percentile(arr, 5))),
        percentile_10_millions=_r5(float(np.percentile(arr, 10))),
        percentile_25_millions=_r5(float(np.percentile(arr, 25))),
        percentile_50_millions=_r5(float(np.percentile(arr, 50))),
        percentile_75_millions=_r5(float(np.percentile(arr, 75))),
        percentile_90_millions=_r5(float(np.percentile(arr, 90))),
        percentile_95_millions=_r5(float(np.percentile(arr, 95))),
        probability_positive=float(np.mean(arr > 0)),
        probability_above_500m=float(np.mean(arr > 500)),
        probability_above_1b=float(np.mean(arr > 1000)),
        simulated_values_millions=sorted_vals,
    )
