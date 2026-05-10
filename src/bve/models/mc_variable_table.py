"""
Monte Carlo variable specification table — Sprint 32B.

Defines a typed registry of all 23 uncertain variables used in the MC engine,
each with its named distribution and parameters. Variables are opt-in so Mode 1
(SIMPLE) can activate a subset and Mode 2 (DRIVER_BASED) can activate others.

Variable categories
-------------------
  clinical      — per-phase POS, breakthrough designation
  regulatory    — label breadth, duration delta, approval pathway events
  commercial    — eligible patients, net price, peak penetration, timing, patent life
  payer         — payer access fraction, prior auth burden
  competition   — competitor share, price pressure
  costs         — R&D cost multiplier, COGS, SG&A, discount rate
  tax           — effective tax rate / NOL usage

Distribution conventions
------------------------
  Beta(alpha, beta)         — values in (0, 1); used for probabilities, rates
  LogNormal(mu, sigma)      — always positive; multiplicative factors; mu/sigma are
                              the underlying Normal's mean and std (ln-space)
  Normal(mean, std)         — real-valued; used for WACC, time deltas
  Triangular(low, mode, high) — bounded range; used for timing variables
  Bernoulli(p)              — binary event (0 or 1); used for go/no-go triggers
"""
from __future__ import annotations

import math as _math
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DistributionType(str, Enum):
    """Named distribution families used in the MC variable table."""

    BETA = "beta"
    LOGNORMAL = "lognormal"
    NORMAL = "normal"
    TRIANGULAR = "triangular"
    BERNOULLI = "bernoulli"


class MCVariableSpec(BaseModel):
    """
    Specification for a single Monte Carlo uncertain variable.

    Parameters
    ----------
    name:
        Unique snake_case identifier.
    description:
        Human-readable label for reports and audit trails.
    category:
        One of: clinical, regulatory, commercial, payer, competition, costs, tax.
    distribution_type:
        Sampling distribution family.
    params:
        Distribution parameters keyed by canonical name:
          Beta       → ``alpha``, ``beta``
          LogNormal  → ``mu`` (ln-space mean), ``sigma`` (ln-space std)
          Normal     → ``mean``, ``std``
          Triangular → ``low``, ``mode``, ``high``
          Bernoulli  → ``p``
    active:
        Whether this variable is sampled by default.  Callers can override.
    bernoulli_trigger:
        Name of a Bernoulli variable that must equal 1 for this variable to
        contribute to the draw.  Used for conditional costs (e.g. confirmatory
        trial cost is only realised when confirmatory_trial_required=1).
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    category: str
    distribution_type: DistributionType
    params: dict[str, float]
    active: bool = True
    bernoulli_trigger: Optional[str] = Field(default=None)

    def sample_params_valid(self) -> bool:
        """Return True when the params dict contains the expected keys."""
        required = {
            DistributionType.BETA: {"alpha", "beta"},
            DistributionType.LOGNORMAL: {"mu", "sigma"},
            DistributionType.NORMAL: {"mean", "std"},
            DistributionType.TRIANGULAR: {"low", "mode", "high"},
            DistributionType.BERNOULLI: {"p"},
        }
        return required[self.distribution_type].issubset(self.params.keys())


# ---------------------------------------------------------------------------
# Helpers for building specs concisely
# ---------------------------------------------------------------------------

def _beta(name: str, description: str, category: str,
          alpha: float, beta: float, active: bool = True) -> MCVariableSpec:
    return MCVariableSpec(
        name=name, description=description, category=category,
        distribution_type=DistributionType.BETA,
        params={"alpha": alpha, "beta": beta},
        active=active,
    )


def _lognormal(name: str, description: str, category: str,
               mu: float, sigma: float, active: bool = True,
               bernoulli_trigger: Optional[str] = None) -> MCVariableSpec:
    return MCVariableSpec(
        name=name, description=description, category=category,
        distribution_type=DistributionType.LOGNORMAL,
        params={"mu": mu, "sigma": sigma},
        active=active,
        bernoulli_trigger=bernoulli_trigger,
    )


def _normal(name: str, description: str, category: str,
            mean: float, std: float, active: bool = True) -> MCVariableSpec:
    return MCVariableSpec(
        name=name, description=description, category=category,
        distribution_type=DistributionType.NORMAL,
        params={"mean": mean, "std": std},
        active=active,
    )


def _triangular(name: str, description: str, category: str,
                low: float, mode: float, high: float, active: bool = True) -> MCVariableSpec:
    return MCVariableSpec(
        name=name, description=description, category=category,
        distribution_type=DistributionType.TRIANGULAR,
        params={"low": low, "mode": mode, "high": high},
        active=active,
    )


def _bernoulli(name: str, description: str, category: str,
               p: float, active: bool = True) -> MCVariableSpec:
    return MCVariableSpec(
        name=name, description=description, category=category,
        distribution_type=DistributionType.BERNOULLI,
        params={"p": p},
        active=active,
    )


# ---------------------------------------------------------------------------
# The 23-variable table
# ---------------------------------------------------------------------------
#
# Each entry is keyed by ``name`` for O(1) lookup.
# LogNormal mu/sigma are ln-space parameters.  For a multiplier centred at 1.0
# with coefficient of variation CV:
#   sigma = sqrt(ln(1 + CV^2))
#   mu    = -0.5 * sigma^2   →  E[X] ≈ 1.0
#
# Beta(alpha, beta) parametrised from industry mean μ and ESS (total count):
#   alpha = μ × ESS,  beta = (1-μ) × ESS


def _lognormal_from_cv(name: str, description: str, category: str,
                       cv: float, active: bool = True,
                       bernoulli_trigger: Optional[str] = None) -> MCVariableSpec:
    """Construct a LogNormal multiplier spec centred at 1.0 with the given CV."""
    sigma = _math.sqrt(_math.log(1 + cv ** 2))
    mu = -0.5 * sigma ** 2
    return _lognormal(name, description, category, mu=mu, sigma=sigma,
                      active=active, bernoulli_trigger=bernoulli_trigger)


def _beta_from_mean_ess(name: str, description: str, category: str,
                        mean: float, ess: float, active: bool = True) -> MCVariableSpec:
    """Construct a Beta spec from a mean probability and equivalent sample size."""
    return _beta(name, description, category,
                 alpha=mean * ess, beta=(1.0 - mean) * ess, active=active)


MC_VARIABLE_TABLE: dict[str, MCVariableSpec] = {
    # ── Clinical (4 variables) ────────────────────────────────────────────
    "phase_1_success_prob": _beta_from_mean_ess(
        "phase_1_success_prob",
        "Phase 1 success probability",
        "clinical", mean=0.63, ess=20,
    ),
    "phase_2_success_prob": _beta_from_mean_ess(
        "phase_2_success_prob",
        "Phase 2 success probability",
        "clinical", mean=0.40, ess=25,
    ),
    "phase_3_success_prob": _beta_from_mean_ess(
        "phase_3_success_prob",
        "Phase 3 success probability",
        "clinical", mean=0.60, ess=30,
    ),
    "breakthrough_designation": _bernoulli(
        "breakthrough_designation",
        "FDA Breakthrough Therapy Designation granted",
        "clinical", p=0.10, active=False,
    ),

    # ── Regulatory (5 variables) ──────────────────────────────────────────
    "label_breadth_mult": _lognormal_from_cv(
        "label_breadth_mult",
        "Label breadth multiplier vs. base case (approved population fraction)",
        "regulatory", cv=0.20,
    ),
    "regulatory_duration_delta_years": _normal(
        "regulatory_duration_delta_years",
        "Additive shift in time-to-approval relative to base case (years)",
        "regulatory", mean=0.0, std=0.5,
    ),
    "accelerated_approval": _bernoulli(
        "accelerated_approval",
        "Accelerated approval pathway granted (shortens launch timeline)",
        "regulatory", p=0.15, active=False,
    ),
    "confirmatory_trial_required": _bernoulli(
        "confirmatory_trial_required",
        "Post-approval confirmatory trial required as condition of approval",
        "regulatory", p=0.20, active=False,
    ),
    "confirmatory_trial_cost_millions": _lognormal(
        "confirmatory_trial_cost_millions",
        "Post-approval confirmatory trial cost ($M); conditional on confirmatory_trial_required=1",
        "regulatory",
        mu=_math.log(75.0),   # median $75M
        sigma=0.50,            # ~50% log-space std
        active=False,
        bernoulli_trigger="confirmatory_trial_required",
    ),

    # ── Commercial (5 variables) ──────────────────────────────────────────
    "eligible_patients_mult": _lognormal_from_cv(
        "eligible_patients_mult",
        "Eligible patient population multiplier vs. base case",
        "commercial", cv=0.30, active=False,
    ),
    "net_price_mult": _lognormal_from_cv(
        "net_price_mult",
        "Net price per patient multiplier vs. base case",
        "commercial", cv=0.20, active=False,
    ),
    "peak_penetration_mult": _lognormal_from_cv(
        "peak_penetration_mult",
        "Peak market penetration multiplier vs. base case",
        "commercial", cv=0.25, active=False,
    ),
    "years_to_peak": _triangular(
        "years_to_peak",
        "Years from launch to peak penetration",
        "commercial", low=2, mode=4, high=8,
    ),
    "patent_life_years": _triangular(
        "patent_life_years",
        "Effective marketed patent life (years from launch)",
        "commercial", low=8, mode=12, high=15,
    ),

    # ── Payer (2 variables) ───────────────────────────────────────────────
    "payer_access_fraction": _beta_from_mean_ess(
        "payer_access_fraction",
        "Payer formulary access fraction (covered lives with unrestricted access)",
        "payer", mean=0.70, ess=30, active=False,
    ),
    "prior_auth_burden_delta": _beta_from_mean_ess(
        "prior_auth_burden_delta",
        "Prior authorisation burden above base case (additive fraction of eligible patients excluded)",
        "payer", mean=0.10, ess=20, active=False,
    ),

    # ── Competition (2 variables) ─────────────────────────────────────────
    "competitor_share_mult": _lognormal_from_cv(
        "competitor_share_mult",
        "Competitor combined market share multiplier vs. base case",
        "competition", cv=0.30,
    ),
    "competition_price_pressure_delta": _beta_from_mean_ess(
        "competition_price_pressure_delta",
        "Additive price erosion fraction from competitive pressure",
        "competition", mean=0.05, ess=20,
    ),

    # ── Costs (4 variables) ───────────────────────────────────────────────
    "rd_cost_mult": _lognormal_from_cv(
        "rd_cost_mult",
        "R&D cost multiplier vs. base case (captures overrun risk)",
        "costs", cv=0.25,
    ),
    "cogs_rate": _beta_from_mean_ess(
        "cogs_rate",
        "Cost of goods sold as fraction of net revenue",
        "costs", mean=0.15, ess=40,
    ),
    "sgna_rate_launch": _beta_from_mean_ess(
        "sgna_rate_launch",
        "SG&A rate at launch as fraction of net revenue",
        "costs", mean=0.35, ess=30,
    ),
    "discount_rate": _normal(
        "discount_rate",
        "Risk-adjusted discount rate / WACC",
        "costs", mean=0.10, std=0.02,
    ),

    # ── Tax (1 variable) ──────────────────────────────────────────────────
    "effective_tax_rate": _beta_from_mean_ess(
        "effective_tax_rate",
        "Effective corporate income tax rate (includes NOL shield effects)",
        "tax", mean=0.21, ess=50,
    ),
}

assert len(MC_VARIABLE_TABLE) == 23, (
    f"Expected 23 variables, got {len(MC_VARIABLE_TABLE)}"
)

# Convenience views
MC_VARIABLES_BY_CATEGORY: dict[str, list[MCVariableSpec]] = {}
for _spec in MC_VARIABLE_TABLE.values():
    MC_VARIABLES_BY_CATEGORY.setdefault(_spec.category, []).append(_spec)

ACTIVE_MC_VARIABLES: list[MCVariableSpec] = [
    s for s in MC_VARIABLE_TABLE.values() if s.active
]
