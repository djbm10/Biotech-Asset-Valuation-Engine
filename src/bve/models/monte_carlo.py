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

from typing import TYPE_CHECKING, Optional

import numpy as np
from pydantic import BaseModel, Field
from scipy.stats import lognorm, norm

from bve.config.constants import (
    MC_N_SIMULATIONS, MC_PEAK_SALES_CV, MC_DISCOUNT_RATE_STD, MC_PHASE_ESS,
    MC_YEARS_TO_PEAK_STD, MC_PATENT_LIFE_STD,
)
from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.correlations import CorrelationSpec, DEFAULT_CORRELATION, correlated_uniform_samples
from bve.models.market_model import MarketModel
from bve.models.rnpv_model import RNPVResult, compute_rnpv_full

if TYPE_CHECKING:
    from bve.models.deal_economics import DealEconomics


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

    # Marginal distribution parameters
    peak_sales_cv: float = Field(default=MC_PEAK_SALES_CV, gt=0.0)
    discount_rate_std: float = Field(default=MC_DISCOUNT_RATE_STD, gt=0.0)
    years_to_peak_std: float = Field(default=MC_YEARS_TO_PEAK_STD, gt=0.0)
    patent_life_std: float = Field(default=MC_PATENT_LIFE_STD, gt=0.0)

    # Per-phase success distributions (override trial point estimates)
    phase_distributions: list[PhaseSuccessDistribution] = Field(default_factory=list)

    # Correlation structure
    correlation_spec: Optional[CorrelationSpec] = None
    use_default_correlations: bool = Field(
        default=True,
        description="Apply DEFAULT_CORRELATION if correlation_spec is None"
    )


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

    # Expected NAV/share (set externally)
    mean_nav_per_share: Optional[float] = None


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

    # Peak sales: log-normal via inverse CDF of correlated uniform
    base_peak = market_model.peak_sales_millions
    sigma_ln = np.sqrt(np.log(1 + params.peak_sales_cv ** 2))
    mu_ln = np.log(base_peak) - 0.5 * sigma_ln ** 2
    u_sales = uniform_samples.get("peak_sales", rng.uniform(0, 1, n))
    peak_sales_samples = lognorm(s=sigma_ln, scale=np.exp(mu_ln)).ppf(np.clip(u_sales, 1e-6, 1 - 1e-6))

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

    return MonteCarloResult(
        asset_id=asset.id,
        n_simulations=n,
        mean_millions=float(np.mean(arr)),
        median_millions=float(np.median(arr)),
        std_millions=float(np.std(arr)),
        percentile_5_millions=float(np.percentile(arr, 5)),
        percentile_10_millions=float(np.percentile(arr, 10)),
        percentile_25_millions=float(np.percentile(arr, 25)),
        percentile_50_millions=float(np.percentile(arr, 50)),
        percentile_75_millions=float(np.percentile(arr, 75)),
        percentile_90_millions=float(np.percentile(arr, 90)),
        percentile_95_millions=float(np.percentile(arr, 95)),
        probability_positive=float(np.mean(arr > 0)),
        probability_above_500m=float(np.mean(arr > 500)),
        probability_above_1b=float(np.mean(arr > 1000)),
        simulated_values_millions=sorted_vals,
    )
