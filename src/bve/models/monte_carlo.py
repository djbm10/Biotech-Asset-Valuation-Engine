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

    # ── Stochastic timing (P2.1) ─────────────────────────────────────────────
    # sample_phase_durations=True: draw a gamma multiplier on each trial's duration_years.
    # Gamma is right-skewed (trials overrun more than they underrun).
    # CV of ~0.30 reproduces the ~30% coefficient of variation observed in published
    # clinical trial duration data (Sertkaya et al., FDA/ASPE 2016).
    sample_phase_durations: bool = Field(
        default=False,
        description=(
            "Draw gamma-distributed duration multipliers (mean=1.0) per phase. "
            "Each trial's duration_years is scaled by its drawn multiplier. "
            "Recommended for BD/IC presentations — shows timing tail risk."
        ),
    )
    phase_duration_cv: float = Field(
        default=0.30, gt=0.0,
        description=(
            "CV for phase duration gamma draws. "
            "0.30 ≈ published industry data (Sertkaya et al. 2016). "
            "Active only when sample_phase_durations=True."
        ),
    )

    # ── Stochastic trial cost (P2.1) ─────────────────────────────────────────
    # sample_trial_costs=True: draw a lognormal multiplier on each trial's cost_millions.
    # Lognormal is appropriate because cost overruns are multiplicative and right-skewed.
    # CV of ~0.35 calibrated to bio/pharmaceutical R&D cost variance in industry data.
    sample_trial_costs: bool = Field(
        default=False,
        description=(
            "Draw lognormal cost multipliers (mean=1.0) per trial. "
            "Each trial's cost_millions is scaled by its drawn multiplier. "
            "Recommended when cost estimates are analyst judgments rather than CRO quotes."
        ),
    )
    trial_cost_cv: float = Field(
        default=0.35, gt=0.0,
        description=(
            "CV for trial cost lognormal draws. "
            "0.35 ≈ typical R&D cost overrun dispersion. "
            "Active only when sample_trial_costs=True."
        ),
    )

    # ── Stochastic financing / dilution (P2.2) ───────────────────────────────
    # sample_financing=True: when the company's cash is insufficient to cover
    # trial costs, model an equity offering at a stochastic discount.  The
    # offering dilutes existing shareholders; dilution_factor = pre / post shares.
    # Requires current_price_per_share and shares_outstanding_millions to be
    # passed to run_monte_carlo() — otherwise has no effect (safe fallback).
    sample_financing: bool = Field(
        default=False,
        description=(
            "Model dilutive equity offerings when cash < trial costs. "
            "Each simulation draws an offering discount from N(0.20, discount_std), "
            "computes new shares issued, and applies a dilution_factor to rNPV. "
            "Requires current_price_per_share and shares_outstanding_millions."
        ),
    )
    financing_discount_cv: float = Field(
        default=0.10, gt=0.0,
        description=(
            "Std of the offering discount draw (normal distribution, mean=0.20). "
            "0.10 → discount ranges ~0%–40% at 2σ. "
            "Active only when sample_financing=True."
        ),
    )

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


class SimulationAuditRecord(BaseModel):
    """
    Compact audit record for one representative simulation (P5, P50, or P95).

    Full per-trial traces are NOT stored by default — only these 3 representative
    records are retained in ``MonteCarloResult.audit_trail``.
    """

    simulation_id: int          # 0-based index in the sorted simulation array
    percentile_label: str       # "P5", "P50", or "P95"
    clinical_draw: float        # sampled cumulative success probability for this trial
    commercial_draw: float      # sampled peak_sales_millions for this trial
    cost_draw: float            # sampled discount_rate (WACC) for this trial
    competition_draw: int       # number of competitors sampled into this trial
    rnpv_millions: float
    nav_per_share: Optional[float]
    main_value_driver: str      # highest-impact factor (heuristic from draw values)
    failure_reason: Optional[str]  # non-None when rNPV < 0


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

    # ── Sprint 32F: enhanced output fields ─────────────────────────────────
    # Expected gain/loss in upside and downside scenarios
    expected_upside: float = 0.0    # E[rNPV | rNPV > 0]; 0 when no positive trials
    expected_downside: float = 0.0  # E[rNPV | rNPV < 0]; 0 when no negative trials

    # Downside risk measure: absolute value of P5 percentile (loss in worst 5%)
    downside_value_at_risk: float = 0.0

    # Key variance drivers: variable names ranked by |Spearman r| with rNPV outcomes
    top_variance_drivers: list[str] = Field(default_factory=list)

    # Event-rate diagnostics across all trials
    clinical_failure_rate: float = 0.0     # fraction where cumulative_pos ≤ 0.10
    competitor_disruption_rate: float = 0.0  # fraction where ≥1 pipeline comp sampled in
    payer_restriction_rate: float = 0.0    # fraction where payer_access draw < 0.5

    # Conditional threshold probabilities (populated when EV/price provided at run time)
    probability_nav_above_ev: Optional[float] = None
    probability_nav_above_price: Optional[float] = None

    # Compact audit trail: exactly 3 records (P5, P50, P95); full traces NOT stored
    audit_trail: list[SimulationAuditRecord] = Field(default_factory=list)

    # Sorted simulation outputs
    simulated_values_millions: list[float]

    # Which CV was actually used (stage-conditional or explicit override)
    peak_sales_cv_used: float = MC_PEAK_SALES_CV

    # Mode that produced this result
    mode_used: MCMode = MCMode.SIMPLE

    # Expected NAV/share (set externally)
    mean_nav_per_share: Optional[float] = None


class SimulationDraws(BaseModel):
    """
    Pre-drawn random values for a single Monte Carlo trial.

    Used as the input to ``_run_single_trial()`` so that each step of the
    simulation path can be tested in isolation.  All draws are already in the
    domain of the target variable (e.g. ``discount_rate`` is a probability-clipped
    float, ``years_to_peak`` is a positive integer).
    """

    # Step 1 — Clinical: per-phase success probability draws
    phase_success_probs: dict[str, float]  # {phase.value → sampled probability}

    # Step 2 — Timing (P2.1): gamma duration multipliers per phase (mean=1.0)
    phase_duration_mults: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "{phase.value → gamma multiplier}. "
            "Empty dict when sample_phase_durations=False (no timing uncertainty). "
            "Each trial's duration_years is multiplied by this factor."
        ),
    )

    # Step 3 — Commercial: peak_sales draw (SIMPLE mode) or per-driver mults (DRIVER_BASED)
    peak_sales_millions: float
    years_to_peak: int = Field(ge=1, le=20)

    # Step 4 — Payer/geo/competition: sampled CompetitionModel (may be None)
    competition_model: Optional[object] = None  # CompetitionModel | None

    # Step 5 — Costs / WACC
    discount_rate: float = Field(ge=0.01, le=0.50)

    # Step 5b — Trial cost multipliers (P2.1): lognormal per trial (mean=1.0)
    trial_cost_mults: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "{trial_index_str → lognormal multiplier}. "
            "Empty dict when sample_trial_costs=False (no cost uncertainty). "
            "Each trial's cost_millions is multiplied by this factor."
        ),
    )

    # Step 6 — Financing dilution (P2.2): fraction of pre-dilution value retained
    # 1.0 = no dilution (either no financing needed or sample_financing=False).
    # < 1.0 = dilutive offering occurred; applied to rNPV as existing-shareholder haircut.
    dilution_factor: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description=(
            "Fraction of rNPV retained after dilutive equity offering. "
            "1.0 when sample_financing=False or cash is sufficient. "
            "< 1.0 = shares_pre / shares_post when an offering is modelled."
        ),
    )


class SimulationOutput(BaseModel):
    """
    Output from a single Monte Carlo trial.

    rNPV comes exclusively from a full engine rerun (``compute_rnpv_full()``).
    The ``engine_rerun`` flag is always True — it exists to make the no-shortcut
    invariant testable.
    """

    # Step 11 — rNPV from full engine rerun
    rnpv_millions: float
    engine_rerun: bool = True  # invariant: always True

    # Step 7 — P(approval) from engine ProbabilityModel
    cumulative_success_probability: float

    # Step 8 — Peak revenue from engine RevenueModel
    peak_sales_millions: float

    # Step 12 — NAV/share
    nav_millions: float
    nav_per_share: Optional[float]  # None when shares_outstanding not provided


def _run_single_trial(
    draws: SimulationDraws,
    asset: Asset,
    trials: list[ClinicalTrial],
    market_model: MarketModel,
    *,
    loe_profile: Optional[dict] = None,
    deal: Optional["DealEconomics"] = None,  # type: ignore[name-defined]
    net_cash_millions: float = 0.0,
    shares_outstanding_millions: Optional[float] = None,
) -> SimulationOutput:
    """
    Run one Monte Carlo simulation trial through the canonical 12-step path.

    Step ordering
    -------------
    1.  Clinical draw   — apply per-phase success probabilities
    2.  Regulatory      — (embedded in ProbabilityModel via trial sequence)
    3.  Commercial      — apply peak_sales / driver draws
    4.  Competition     — apply sampled CompetitionModel
    5.  Costs / WACC    — apply discount_rate draw
    6.  Recompute POS   — ProbabilityModel.compute() from engine
    7.  P(approval)     — cumulative_success_probability from engine
    8.  Revenue         — RevenueModel.compute() from engine
    9.  Costs           — CostModel.compute() from engine
    10. After-tax FCF   — RNPVModel.compute() (tax shield, NOL) from engine
    11. rNPV            — full engine result (never a direct shock to rNPV)
    12. NAV/share       — (rNPV + net_cash) / shares_outstanding

    Hard invariant
    --------------
    ``SimulationOutput.engine_rerun`` is always ``True``.  rNPV is NEVER computed
    by shocking the base rNPV directly — the full engine chain reruns on the
    modified inputs.

    Parameters
    ----------
    draws : SimulationDraws
        Pre-sampled random values for this trial.
    asset, trials, market_model :
        Base-case model objects (immutable — not modified in place).
    loe_profile, deal :
        Fixed economic context passed unchanged to the engine.
    net_cash_millions :
        Net cash added to rNPV for NAV calculation.
    shares_outstanding_millions :
        Denominator for NAV/share; None → nav_per_share is None.
    """
    # ── Step 1: Clinical — apply per-phase success probability draws ──────
    sim_trials = [
        t.model_copy(update={"success_probability": min(0.99, max(0.01, draws.phase_success_probs.get(t.phase.value, t.success_probability)))})
        for t in trials
    ]

    # ── Step 2: Timing — apply gamma duration multipliers (P2.1) ──────────
    if draws.phase_duration_mults:
        sim_trials = [
            t.model_copy(update={
                "duration_years": max(0.25, t.duration_years * draws.phase_duration_mults.get(t.phase.value, 1.0))
            })
            for t in sim_trials
        ]

    # ── Step 5b: Trial cost — apply lognormal cost multipliers (P2.1) ─────
    if draws.trial_cost_mults:
        sim_trials = [
            t.model_copy(update={
                "cost_millions": max(0.1, t.cost_millions * draws.trial_cost_mults.get(str(idx), 1.0))
            })
            for idx, t in enumerate(sim_trials)
        ]

    # ── Step 3: Commercial — apply peak_sales draw ────────────────────────
    new_peak_sales = draws.peak_sales_millions
    if market_model.total_addressable_market_millions is not None:
        sim_market = market_model.model_copy(
            update={"total_addressable_market_millions": new_peak_sales / market_model.peak_penetration,
                    "years_to_peak": draws.years_to_peak, "uptake_curve": None}
        )
    else:
        new_price = new_peak_sales * 1e6 / (
            (market_model.addressable_patients_annual or 1)
            * (market_model.compliance_rate or 1)
            * market_model.peak_penetration
        )
        sim_market = market_model.model_copy(
            update={"net_price_per_patient_usd": new_price,
                    "years_to_peak": draws.years_to_peak, "uptake_curve": None}
        )

    # ── Step 4: Payer/geo/competition — apply sampled CompetitionModel ────
    if draws.competition_model is not None:
        sim_market = sim_market.model_copy(update={"competition_model": draws.competition_model})

    # ── Step 5: Costs/WACC — apply discount_rate draw ────────────────────
    sim_asset = asset.model_copy(update={"discount_rate": draws.discount_rate})

    # ── Steps 6–11: Full engine rerun (POS → P(approval) → Revenue → Costs → FCF → rNPV) ──
    result: RNPVResult = compute_rnpv_full(
        sim_asset, sim_trials, sim_market,
        loe_profile=loe_profile, deal=deal,
    )

    # ── Step 6: Financing dilution (P2.2) — apply existing-shareholder haircut ──
    # dilution_factor == 1.0 when no financing is modelled (safe default).
    effective_rnpv = result.rnpv_millions * draws.dilution_factor

    # ── Step 12: NAV/share ────────────────────────────────────────────────
    nav = effective_rnpv + net_cash_millions
    nav_per_share = (nav / shares_outstanding_millions) if shares_outstanding_millions else None

    return SimulationOutput(
        rnpv_millions=effective_rnpv,
        engine_rerun=True,  # invariant — always True
        cumulative_success_probability=result.cumulative_success_probability,
        peak_sales_millions=result.peak_sales_millions,
        nav_millions=nav,
        nav_per_share=nav_per_share,
    )


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
    enterprise_value_millions: Optional[float] = None,
    current_price_per_share: Optional[float] = None,
    shares_outstanding_millions: Optional[float] = None,
    net_cash_millions: float = 0.0,
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

    # ── P2.1: Stochastic phase duration (gamma draws) ────────────────────
    # Gamma parameterisation: shape = 1/cv², scale = cv²  → mean = 1, std = cv
    phase_duration_samples: dict[str, np.ndarray] = {}
    if params.sample_phase_durations:
        cv_d = params.phase_duration_cv
        shape_d = 1.0 / (cv_d ** 2)
        scale_d = cv_d ** 2
        unique_phases = {t.phase.value for t in trials}
        for phase_val in unique_phases:
            phase_duration_samples[phase_val] = rng.gamma(shape=shape_d, scale=scale_d, size=n)

    # ── P2.1: Stochastic trial cost (lognormal draws) ─────────────────────
    # Lognormal with mean=1: s = sqrt(log(1 + cv²)), mu = -0.5*s²
    trial_cost_samples: dict[int, np.ndarray] = {}
    if params.sample_trial_costs:
        cv_c = params.trial_cost_cv
        s_c = np.sqrt(np.log(1 + cv_c ** 2))
        mu_c = -0.5 * s_c ** 2
        for idx in range(len(trials)):
            trial_cost_samples[idx] = lognorm(s=s_c, scale=np.exp(mu_c)).rvs(n, random_state=rng)

    # ── P2.2: Stochastic financing discount (normal draws) ────────────────
    # When cash < trial costs, model a dilutive equity offering at a discount.
    # Discount ~ N(0.20, financing_discount_cv) clipped to [0.05, 0.50].
    # dilution_factor = shares_pre / (shares_pre + shares_issued) ∈ [0, 1].
    financing_discount_samples: np.ndarray = np.full(n, 0.0)
    base_capital_shortfall: float = 0.0
    _financing_active = (
        params.sample_financing
        and shares_outstanding_millions is not None
        and shares_outstanding_millions > 0
        and current_price_per_share is not None
        and current_price_per_share > 0
    )
    if _financing_active:
        base_trial_costs = sum(t.cost_millions for t in trials)
        base_capital_shortfall = max(0.0, base_trial_costs - net_cash_millions)
        if base_capital_shortfall > 0:
            financing_discount_samples = np.clip(
                rng.normal(loc=0.20, scale=params.financing_discount_cv, size=n),
                0.05, 0.50,
            )

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
    all_outputs: list[SimulationOutput] = []          # temporary — discarded after audit extraction
    all_draws_list: list[SimulationDraws] = []        # temporary — for variance driver computation

    n_clinical_failures = 0
    n_competitor_disruptions = 0
    n_payer_restrictions = 0

    for i in range(n):
        # Build SimulationDraws for this trial
        phase_probs = {
            t.phase.value: float(phase_success_samples[t.phase][i])
            for t in trials
        }

        sampled_comp = None
        n_sampled_competitors = 0
        if market_model.competition_model is not None and market_model.competition_model.competitors:
            sampled_comp = market_model.competition_model.sample_launch_outcomes(rng)
            n_sampled_competitors = len(sampled_comp.competitors)

        # Build duration multipliers for this simulation (P2.1)
        dur_mults = (
            {phase_val: float(phase_duration_samples[phase_val][i])
             for phase_val in phase_duration_samples}
            if phase_duration_samples else {}
        )
        # Build cost multipliers for this simulation (P2.1)
        cost_mults = (
            {str(idx): float(trial_cost_samples[idx][i])
             for idx in trial_cost_samples}
            if trial_cost_samples else {}
        )

        # Compute dilution_factor for this simulation (P2.2)
        dilution_factor = 1.0
        if _financing_active and base_capital_shortfall > 0:
            discount = float(financing_discount_samples[i])
            offering_price = current_price_per_share * (1.0 - discount)
            if offering_price > 0 and shares_outstanding_millions:
                # shares_issued_millions = capital_shortfall($M) / offering_price($/share)
                shares_issued_millions = base_capital_shortfall / offering_price
                total_shares = shares_outstanding_millions + shares_issued_millions
                dilution_factor = shares_outstanding_millions / total_shares

        draws = SimulationDraws(
            phase_success_probs=phase_probs,
            phase_duration_mults=dur_mults,
            peak_sales_millions=float(peak_sales_samples[i]),
            years_to_peak=int(ytp_samples[i]),
            competition_model=sampled_comp,
            discount_rate=float(dr_samples[i]),
            trial_cost_mults=cost_mults,
            dilution_factor=dilution_factor,
        )

        output = _run_single_trial(
            draws, asset, trials, market_model,
            loe_profile=loe_profile, deal=deal,
            net_cash_millions=net_cash_millions,
            shares_outstanding_millions=shares_outstanding_millions,
        )
        simulated.append(output.rnpv_millions)
        all_outputs.append(output)
        all_draws_list.append(draws)

        # Diagnostic counters
        if output.cumulative_success_probability <= 0.10:
            n_clinical_failures += 1
        if n_sampled_competitors > 0:
            n_competitor_disruptions += 1
        if params.sample_payer_access and payer_mults[i] < 0.5:
            n_payer_restrictions += 1

    arr = np.array(simulated)
    sorted_vals = sorted(simulated)

    def _r5(v: float) -> float:
        """Round to nearest $5M — MC precision is entirely determined by ESS priors."""
        return round(v / 5.0) * 5.0

    # ── Sprint 32F: enhanced output computation ───────────────────────────

    # Expected upside / downside
    positive_vals = arr[arr > 0]
    negative_vals = arr[arr < 0]
    expected_upside = float(np.mean(positive_vals)) if len(positive_vals) > 0 else 0.0
    expected_downside = float(np.mean(negative_vals)) if len(negative_vals) > 0 else 0.0

    # Downside VaR = absolute value of P5 (positive number = maximum loss in worst 5%)
    p5_val = float(np.percentile(arr, 5))
    downside_var = max(0.0, -p5_val)

    # Top variance drivers: Spearman |r| between draws and rNPV
    driver_arrays: dict[str, np.ndarray] = {
        "peak_sales": peak_sales_samples,
        "discount_rate": dr_samples,
    }
    # Add per-phase success arrays
    for phase_key, arr_vals in phase_success_samples.items():
        driver_arrays[f"pos_{phase_key.value}"] = arr_vals
    # Add driver mults if active
    if params.sample_eligible_patients:
        driver_arrays["eligible_patients"] = patient_mults
    if params.sample_net_price:
        driver_arrays["net_price"] = price_mults
    if params.sample_peak_penetration:
        driver_arrays["peak_penetration"] = penetration_mults
    if params.sample_payer_access:
        driver_arrays["payer_access"] = payer_mults
    if params.sample_geography:
        driver_arrays["geography"] = geo_mults

    from scipy.stats import spearmanr as _spearmanr
    driver_scores: list[tuple[float, str]] = []
    for dname, darr in driver_arrays.items():
        if np.std(darr) > 0 and np.std(arr) > 0:
            r, _ = _spearmanr(darr, arr)
            driver_scores.append((abs(float(r)), dname))
    driver_scores.sort(reverse=True)
    top_variance_drivers = [name for _, name in driver_scores[:5]]

    # Compact audit trail: P5, P50, P95 representative simulations
    sorted_indices = np.argsort(arr)  # indices that would sort simulated ascending
    p5_idx = int(sorted_indices[max(0, int(n * 0.05))])
    p50_idx = int(sorted_indices[int(n * 0.50)])
    p95_idx = int(sorted_indices[min(n - 1, int(n * 0.95))])

    def _main_driver(output: SimulationOutput, draws: SimulationDraws) -> str:
        if output.cumulative_success_probability <= 0.10:
            return "clinical_failure"
        if draws.peak_sales_millions > market_model.peak_sales_millions * 1.5:
            return "commercial_upside"
        if draws.peak_sales_millions < market_model.peak_sales_millions * 0.6:
            return "commercial_downside"
        if draws.discount_rate > 0.15:
            return "high_wacc"
        return "base_dynamics"

    def _failure_reason(output: SimulationOutput) -> Optional[str]:
        if output.rnpv_millions >= 0:
            return None
        if output.cumulative_success_probability <= 0.10:
            return "clinical_failure"
        return "cost_overrun_or_high_wacc"

    def _build_audit(idx: int, label: str) -> SimulationAuditRecord:
        out = all_outputs[idx]
        drw = all_draws_list[idx]
        n_comp = len(drw.competition_model.competitors) if drw.competition_model is not None else 0
        cum_pos = max(drw.phase_success_probs.values()) if drw.phase_success_probs else 0.0
        return SimulationAuditRecord(
            simulation_id=idx,
            percentile_label=label,
            clinical_draw=cum_pos,
            commercial_draw=drw.peak_sales_millions,
            cost_draw=drw.discount_rate,
            competition_draw=n_comp,
            rnpv_millions=out.rnpv_millions,
            nav_per_share=out.nav_per_share,
            main_value_driver=_main_driver(out, drw),
            failure_reason=_failure_reason(out),
        )

    audit_trail = [
        _build_audit(p5_idx, "P5"),
        _build_audit(p50_idx, "P50"),
        _build_audit(p95_idx, "P95"),
    ]

    # Optional conditional probabilities
    prob_nav_above_ev: Optional[float] = None
    prob_nav_above_price: Optional[float] = None
    nav_arr = arr + net_cash_millions
    if enterprise_value_millions is not None:
        prob_nav_above_ev = float(np.mean(nav_arr > enterprise_value_millions))
    if current_price_per_share is not None and shares_outstanding_millions is not None:
        nav_per_share_arr = nav_arr / shares_outstanding_millions
        prob_nav_above_price = float(np.mean(nav_per_share_arr > current_price_per_share))

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
        expected_upside=round(expected_upside, 2),
        expected_downside=round(expected_downside, 2),
        downside_value_at_risk=round(downside_var, 2),
        top_variance_drivers=top_variance_drivers,
        clinical_failure_rate=round(n_clinical_failures / n, 4),
        competitor_disruption_rate=round(n_competitor_disruptions / n, 4),
        payer_restriction_rate=round(n_payer_restrictions / n, 4),
        probability_nav_above_ev=prob_nav_above_ev,
        probability_nav_above_price=prob_nav_above_price,
        audit_trail=audit_trail,
        simulated_values_millions=sorted_vals,
    )
