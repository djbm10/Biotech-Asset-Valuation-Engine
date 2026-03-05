"""
Hard-coded priors and industry benchmarks.

Sources
-------
- Phase transition rates: Biomedtracker/IQVIA 2021, Thomas et al. 2016 (Clinical Pharmacology)
- Phase durations: ClinicalTrials.gov aggregate analysis, DiMasi et al.
- WACC: Damodaran biotech sector, BVP Emerging Pharma dataset
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Phase success rates
# Format: {therapeutic_area: {trial_phase: probability}}
# These are phase-to-NEXT-PHASE transition probabilities.
# ---------------------------------------------------------------------------

PHASE_SUCCESS_RATES: dict[str, dict[str, float]] = {
    "all": {
        "phase_1": 0.64,
        "phase_2": 0.37,
        "phase_3": 0.60,
        "nda_bla": 0.87,
    },
    "oncology": {
        "phase_1": 0.54,
        "phase_2": 0.32,
        "phase_3": 0.55,
        "nda_bla": 0.83,
    },
    "rare_disease": {
        "phase_1": 0.67,
        "phase_2": 0.45,
        "phase_3": 0.62,
        "nda_bla": 0.89,
    },
    "cns": {
        "phase_1": 0.52,
        "phase_2": 0.27,
        "phase_3": 0.49,
        "nda_bla": 0.83,
    },
    "cardiovascular": {
        "phase_1": 0.62,
        "phase_2": 0.45,
        "phase_3": 0.59,
        "nda_bla": 0.85,
    },
    "immunology": {
        "phase_1": 0.66,
        "phase_2": 0.44,
        "phase_3": 0.63,
        "nda_bla": 0.86,
    },
    "infectious_disease": {
        "phase_1": 0.66,
        "phase_2": 0.46,
        "phase_3": 0.72,
        "nda_bla": 0.86,
    },
    "other": {
        "phase_1": 0.64,
        "phase_2": 0.37,
        "phase_3": 0.60,
        "nda_bla": 0.87,
    },
}

# Overall probability of approval from start of each phase (compounded)
PROB_APPROVAL_FROM_PHASE: dict[str, dict[str, float]] = {
    ta: {
        "phase_1": rates["phase_1"] * rates["phase_2"] * rates["phase_3"] * rates["nda_bla"],
        "phase_2": rates["phase_2"] * rates["phase_3"] * rates["nda_bla"],
        "phase_3": rates["phase_3"] * rates["nda_bla"],
        "nda_bla": rates["nda_bla"],
    }
    for ta, rates in PHASE_SUCCESS_RATES.items()
}

# ---------------------------------------------------------------------------
# Phase durations (years) — median from ClinicalTrials.gov analysis
# ---------------------------------------------------------------------------

PHASE_DURATIONS_YEARS: dict[str, float] = {
    "phase_1": 1.5,
    "phase_2": 2.5,
    "phase_3": 3.5,
    "nda_bla": 1.5,
}

# ---------------------------------------------------------------------------
# Phase costs (USD millions) — industry medians, DiMasi 2016 + Tufts CSDD
# ---------------------------------------------------------------------------

PHASE_COSTS_MILLIONS: dict[str, float] = {
    "phase_1": 25.0,
    "phase_2": 75.0,
    "phase_3": 225.0,
    "nda_bla": 35.0,
}

# ---------------------------------------------------------------------------
# Gross-to-net discounts by product type
# (gross_price × (1 - GTN) = net price)
# ---------------------------------------------------------------------------

GROSS_TO_NET_DISCOUNT: dict[str, float] = {
    "small_molecule": 0.45,   # heavy rebates in primary care
    "biologic": 0.30,
    "gene_therapy": 0.10,     # small population, limited rebate leverage
    "cell_therapy": 0.10,
    "adc": 0.25,
    "rna_therapy": 0.20,
    "other": 0.35,
}

# ---------------------------------------------------------------------------
# COGS as % of net revenue by modality
# ---------------------------------------------------------------------------

COGS_RATE: dict[str, float] = {
    "small_molecule": 0.12,
    "biologic": 0.20,
    "gene_therapy": 0.30,     # COGS-intensive manufacturing
    "cell_therapy": 0.40,
    "adc": 0.22,
    "rna_therapy": 0.18,
    "other": 0.18,
}

# ---------------------------------------------------------------------------
# SG&A as % of net revenue — ramps down as product matures
# ---------------------------------------------------------------------------

SGNA_RATE_LAUNCH: float = 0.40   # first 2 years post-launch
SGNA_RATE_MATURE: float = 0.20   # 5+ years post-launch
SGNA_RAMP_YEARS: int = 5         # years to reach mature rate

# ---------------------------------------------------------------------------
# Discount rates / WACC
# ---------------------------------------------------------------------------

DEFAULT_WACC: float = 0.10       # 10% standard biotech WACC
WACC_SMALL_CAP: float = 0.12     # < $500M market cap
WACC_LARGE_CAP: float = 0.09     # > $5B market cap
WACC_RISK_FREE: float = 0.04     # current risk-free proxy

# ---------------------------------------------------------------------------
# Monte Carlo defaults
# ---------------------------------------------------------------------------

MC_N_SIMULATIONS: int = 10_000
MC_RANDOM_SEED: int | None = None

# Beta distribution equivalent sample sizes for phase success rates
# Higher = tighter prior (less uncertainty in the MC draw)
MC_PHASE_ESS: dict[str, int] = {
    "phase_1": 30,
    "phase_2": 25,
    "phase_3": 20,
    "nda_bla": 40,
}

# Coefficient of variation for peak sales (log-normal)
MC_PEAK_SALES_CV: float = 0.35

# Std dev on discount rate
MC_DISCOUNT_RATE_STD: float = 0.02

# ---------------------------------------------------------------------------
# Event study windows (trading days)
# ---------------------------------------------------------------------------

EVENT_PRE_WINDOW: int = 20        # days before event
EVENT_POST_SHORT_WINDOW: int = 1  # same-day + next-day reaction
EVENT_POST_DRIFT_WINDOW: int = 20 # post-event drift

# ---------------------------------------------------------------------------
# Ordering: trial phases
# ---------------------------------------------------------------------------

PHASE_ORDER: dict[str, int] = {
    "phase_1": 1,
    "phase_2": 2,
    "phase_3": 3,
    "nda_bla": 4,
}

# ---------------------------------------------------------------------------
# Memo defaults
# ---------------------------------------------------------------------------

MEMO_AUTHOR: str = "BVE Analytics"
MEMO_DISCLAIMER: str = (
    "This analysis is for informational purposes only and does not constitute "
    "investment advice. All projections are model estimates subject to material uncertainty."
)
