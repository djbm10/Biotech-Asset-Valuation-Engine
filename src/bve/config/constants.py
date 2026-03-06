"""
Structural constants and backward-compatible accessors for industry priors.

This module exports the same names that all existing code imports. The
calibrated values (phase success rates, trial design parameters, etc.) now
come from industry_assumptions.yaml via AssumptionsLoader rather than being
hardcoded here. This module is the re-export shim that preserves all existing
import paths with zero changes required in the rest of the codebase.

What stays here (structural, not calibrated):
    PHASE_ORDER           — ordering sentinel for sorting
    TRIAL_DESIGN_PHASE_NEUTRAL — sentinel string for max-effect mode
    MEMO_AUTHOR / MEMO_DISCLAIMER — operational text
    EVENT_* windows       — event study trading-day windows
    MC_N_SIMULATIONS / MC_RANDOM_SEED — operational defaults (not calibrated)

What moved to industry_assumptions.yaml (calibrated, auditable):
    PHASE_SUCCESS_RATES, PROB_APPROVAL_FROM_PHASE
    PHASE_DURATIONS_YEARS, PHASE_COSTS_MILLIONS
    GROSS_TO_NET_DISCOUNT, COGS_RATE
    SGNA_RATE_LAUNCH, SGNA_RATE_MATURE, SGNA_RAMP_YEARS
    DEFAULT_WACC, WACC_SMALL_CAP, WACC_LARGE_CAP, WACC_RISK_FREE
    MC_PHASE_ESS, MC_PEAK_SALES_CV, MC_DISCOUNT_RATE_STD
    TRIAL_DESIGN_LOGODDS, TRIAL_DESIGN_CAP_POSITIVE, TRIAL_DESIGN_CAP_NEGATIVE
    TRIAL_DESIGN_PHASE_SCALING
"""
from __future__ import annotations

from bve.config.assumptions_loader import AssumptionsLoader as _loader_cls

# Load once at import time. All module-level names below are snapshots of the
# loaded YAML. To reload (e.g., in tests), call AssumptionsLoader.reset() and
# then re-import the specific names you need from the loader directly.
_a = _loader_cls.get()


# ---------------------------------------------------------------------------
# Phase success rates
# ---------------------------------------------------------------------------

PHASE_SUCCESS_RATES: dict[str, dict[str, float]] = _a.phase_success_rates
PROB_APPROVAL_FROM_PHASE: dict[str, dict[str, float]] = _a.prob_approval_from_phase


# ---------------------------------------------------------------------------
# Phase durations and costs
# ---------------------------------------------------------------------------

PHASE_DURATIONS_YEARS: dict[str, float] = _a.phase_durations_years
PHASE_COSTS_MILLIONS: dict[str, float] = _a.phase_costs_millions


# ---------------------------------------------------------------------------
# Commercial defaults
# ---------------------------------------------------------------------------

GROSS_TO_NET_DISCOUNT: dict[str, float] = _a.gross_to_net_by_modality
COGS_RATE: dict[str, float] = _a.cogs_rate_by_modality

_sgna = _a.sgna
SGNA_RATE_LAUNCH: float = float(_sgna["rate_launch"])
SGNA_RATE_MATURE: float = float(_sgna["rate_mature"])
SGNA_RAMP_YEARS: int = int(_sgna["ramp_years"])


# ---------------------------------------------------------------------------
# WACC
# ---------------------------------------------------------------------------

_wacc = _a.wacc
DEFAULT_WACC: float = float(_wacc["default"])
WACC_SMALL_CAP: float = float(_wacc["small_cap"])
WACC_LARGE_CAP: float = float(_wacc["large_cap"])
WACC_RISK_FREE: float = float(_wacc["risk_free"])


# ---------------------------------------------------------------------------
# Monte Carlo defaults
# ---------------------------------------------------------------------------

MC_N_SIMULATIONS: int = 10_000          # operational default; not in assumptions YAML
MC_RANDOM_SEED: int | None = None       # operational default

MC_PHASE_ESS: dict[str, int] = _a.mc_phase_ess
MC_PEAK_SALES_CV: float = _a.mc_peak_sales_cv
MC_DISCOUNT_RATE_STD: float = _a.mc_discount_rate_std


# ---------------------------------------------------------------------------
# Trial design (Phase 1A)
# ---------------------------------------------------------------------------

TRIAL_DESIGN_LOGODDS: dict[str, dict[str, float]] = _a.trial_design_logodds
TRIAL_DESIGN_CAP_POSITIVE: float = _a.trial_design_cap_positive
TRIAL_DESIGN_CAP_NEGATIVE: float = _a.trial_design_cap_negative
TRIAL_DESIGN_PHASE_SCALING: dict[str, dict[str, float]] = _a.trial_design_phase_scaling

# Structural sentinel — not a calibrated value; stays in constants.py
TRIAL_DESIGN_PHASE_NEUTRAL: str = "neutral"


# ---------------------------------------------------------------------------
# Structural constants (ordering, metadata, event windows)
# Not calibrated — these belong here, not in assumptions YAML
# ---------------------------------------------------------------------------

PHASE_ORDER: dict[str, int] = {
    "phase_1": 1,
    "phase_2": 2,
    "phase_3": 3,
    "nda_bla": 4,
}

MEMO_AUTHOR: str = "BVE Analytics"
MEMO_DISCLAIMER: str = (
    "This analysis is for informational purposes only and does not constitute "
    "investment advice. All projections are model estimates subject to material uncertainty."
)

EVENT_PRE_WINDOW: int = 20
EVENT_POST_SHORT_WINDOW: int = 1
EVENT_POST_DRIFT_WINDOW: int = 20
