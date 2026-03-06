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
    # Ophthalmology: higher-than-average success rates driven by objective, measurable
    # endpoints (BCVA, retinal thickness), well-characterized patient populations, and
    # strong historical precedent for anti-VEGF drugs.
    # Sources: Wong et al. 2019 (Biostatistics); GlobalData ophtho analysis; Biomedtracker
    "ophthalmology": {
        "phase_1": 0.72,
        "phase_2": 0.47,
        "phase_3": 0.65,
        "nda_bla": 0.89,
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

# ---------------------------------------------------------------------------
# Trial design log-odds adjustments (Phase 1A)
#
# IMPORTANT: These are EVIDENCE-INFORMED PRIORS, not statistically estimated
# effects. They are intended for scenario differentiation and sensitivity
# analysis, NOT precise prediction. A reviewer should interpret these as:
#   "Hard endpoints are directionally better than novel surrogates at Phase 3"
# not as:
#   "The log-odds difference is exactly 0.70 per this regression."
#
# Three orthogonal dimensions, applied in log-odds space. Effects are
# phase-conditional via TRIAL_DESIGN_PHASE_SCALING below — most effects
# are attenuated at Phase 1 (where single-arm is universal) and fully
# expressed at Phase 3 (where design choices directly determine FDA outcome).
#
# Provenance (what the cited evidence actually supports + judgment calls):
#
#   EndpointBasis:
#     Direction support: Hwang TJ et al. (2020) "Association between FDA
#       approval based on surrogate endpoints and overall survival" JAMA
#       Internal Medicine — confirms surrogates have higher post-approval
#       failure rates (~2×). Supports DIRECTION of hard_clinical > surrogate.
#     Magnitude: JUDGMENT CALL. +0.35 is a moderate prior. A strict reader
#       of Hwang 2020 might place this lower; an FDA guideline reader higher.
#     Biomarker_only: ICH E15 guidance and DiMasi JA et al. (2021) J Clin
#       Pharmacol support large downward adjustment; -0.80 is conservative
#       (judgment call — rarely sufficient as standalone primary).
#
#   EvidenceDesign:
#     Direction support: FDA Evidentiary Standards for Drug Development,
#       CDER (2019) — confirms RCT > single-arm for approval certainty.
#     Single_arm magnitude: Blumenthal GM et al. (2017) "Oncology drug
#       approvals: evaluating endpoints and evidence" The Oncologist.
#       Single-arm Phase 2→Phase 3 translation ≈ 40% relative reduction in
#       success, translating to roughly -0.40 to -0.55 log-odds at Phase 3.
#       -0.45 is a conservative central estimate. JUDGMENT CALL on exact value.
#     Single-arm is standard for Phase 1 and common in rare oncology Phase 2:
#       Phase-conditional scaling (below) reduces this effect to near-zero at
#       Phase 1, avoiding penalizing trials where single-arm is appropriate.
#     Registry_based: FDA Real-World Evidence guidance (2021); rarely
#       sufficient standalone. -0.70 is a conservative prior. JUDGMENT CALL.
#
#   ApprovalPathway:
#     CAUTION: Pathway designations primarily affect time-to-approval and
#     commercial adoption, not binary approval probability. Positive
#     adjustments here are intentionally small (weak modifiers only).
#     DOUBLE-COUNTING RISK: has_breakthrough_designation in POSAdjusters
#     (pos_model.py) captures the BTD POS signal. If using TrialDesignFeatureSet
#     with breakthrough_designation AND POSAdjusters.has_breakthrough_designation=True,
#     you WILL double-count. Use one or the other, not both.
#     Accelerated_approval/orphan: direction support from Braun MM et al.
#       (2010) NEJM "Emergence of orphan drugs" and FDA AA records, but
#       magnitudes are weak priors (+0.05). JUDGMENT CALL.
#
# Cap implication table (at TRIAL_DESIGN_CAP_POSITIVE=+0.60, TRIAL_DESIGN_CAP_NEGATIVE=-0.50):
#
#   base_pos  │ capped-up (max +0.60)  │ capped-down (max -0.50)
#   ──────────┼────────────────────────┼──────────────────────────
#   0.10      │  0.168  (+6.8pp)       │  0.063  (-3.7pp)
#   0.20      │  0.313  (+11.3pp)      │  0.132  (-6.8pp)
#   0.30      │  0.439  (+13.9pp)      │  0.206  (-9.4pp)
#   0.50      │  0.646  (+14.6pp)      │  0.378  (-12.2pp)
#   0.55      │  0.690  (+14.0pp)      │  0.426  (-12.4pp)
#   0.60      │  0.732  (+13.2pp)      │  0.524  (-7.6pp)
#
#   Interpretation: at typical Phase 3 base rates (~0.50-0.60), the design
#   feature adjustment can move POS by up to ±13pp. This is conservative
#   relative to the real-world difference between an RCT using hard endpoints
#   vs a single-arm trial using a novel surrogate in a competitive indication.
#   These are judgment calls on what constitutes a "reasonable prior effect."
# ---------------------------------------------------------------------------

TRIAL_DESIGN_LOGODDS: dict[str, dict[str, float]] = {
    "endpoint_basis": {
        "hard_clinical": +0.35,          # OS, DFS — most accepted; direction from Hwang 2020
        "surrogate_validated": 0.00,     # Reference: PFS, HbA1c, FEV1, SVR35
        "surrogate_novel": -0.35,        # Uncertain regulatory acceptance; judgment call
        "biomarker_only": -0.80,         # Rarely sufficient; ICH E15 + DiMasi 2021 support direction
    },
    "evidence_design": {
        "rct_comparative": 0.00,         # Reference: gold standard randomized controlled trial
        "rct_non_comparative": -0.15,    # Judgment call; minor penalty vs full RCT
        "single_arm": -0.45,             # Phase 3 prior from Blumenthal 2017; phase-scaled below
        "registry_based": -0.70,         # Observational; FDA RWE guidance supports direction
    },
    "approval_pathway": {
        # WEAK MODIFIERS ONLY — pathway primarily affects timeline, not binary POS
        # Double-counting risk: see CAUTION note in provenance block above
        "standard": 0.00,                # Reference
        "accelerated_approval": +0.05,   # Weak prior; FDA engagement signal only
        "breakthrough_designation": +0.10,  # Weak prior; use POSAdjusters.has_breakthrough_designation instead
        "orphan_drug": +0.05,            # Weak prior; regulatory flexibility for rare disease
    },
}

# Cap on combined trial design log-odds adjustment (all 3 dimensions summed,
# after phase-conditional scaling is applied).
# Separate from existing POSAdjusters (endpoint_type, moa_precedent, etc.).
TRIAL_DESIGN_CAP_POSITIVE: float = +0.60   # Max upward design adjustment (~+14pp at 50% base)
TRIAL_DESIGN_CAP_NEGATIVE: float = -0.50   # Max downward design adjustment (~-12pp at 50% base)

# ---------------------------------------------------------------------------
# Phase-conditional scaling for trial design effects
#
# Trial design features are not equally relevant at every phase:
#   Phase 1: Nearly all trials are single-arm dose-escalation with biomarker/PK
#     endpoints — these are appropriate designs, not regulatory risks. Applying
#     Phase 3 design penalties to Phase 1 would be a category error.
#   Phase 2: Intermediate — RCT vs single-arm matters increasingly, especially
#     for accelerated approval pathways in oncology.
#   Phase 3: Full effect — trial design choices directly determine FDA approval
#     outcome. This is where design quality matters most.
#   NDA/BLA: Evidence already gathered; endpoint and evidence quality are
#     "baked in" from prior phases. The remaining design effect is partial.
#
# Each value is a multiplier applied to the raw log-odds adjustment from
# TRIAL_DESIGN_LOGODDS before summation and capping.
# All values are JUDGMENT CALLS — no published literature directly calibrates
# these phase-specific attenuation factors.
# ---------------------------------------------------------------------------

# Explicit sentinel for "no phase attenuation" mode.
# Used with compute_design_adjusted_pos(phase=TRIAL_DESIGN_PHASE_NEUTRAL) when
# the analyst explicitly wants maximum-effect estimates regardless of actual phase.
# This is the MOST opinionated mode — use only when phase is genuinely unknown
# and you are deliberately overestimating design effects as a stress test.
# Do NOT use as a default or shortcut; always prefer an explicit phase key.
TRIAL_DESIGN_PHASE_NEUTRAL: str = "neutral"

TRIAL_DESIGN_PHASE_SCALING: dict[str, dict[str, float]] = {
    "phase_1": {
        "endpoint_basis": 0.15,     # Biomarker/PK endpoints are expected at Phase 1; near-zero penalty
        "evidence_design": 0.10,    # Single-arm is universal at Phase 1; no meaningful penalty
        "approval_pathway": 0.40,   # Designations obtained here still have some forward signal
    },
    "phase_2": {
        "endpoint_basis": 0.55,     # Moving toward registration endpoints; moderate effect
        "evidence_design": 0.60,    # RCT vs single-arm increasingly important
        "approval_pathway": 0.70,   # More relevant as Phase 2 design shapes registration path
    },
    "phase_3": {
        "endpoint_basis": 1.00,     # Full effect: endpoint type is the primary FDA review question
        "evidence_design": 1.00,    # Full effect: randomized vs single-arm drives approval certainty
        "approval_pathway": 0.80,   # Slightly attenuated: pathway mainly affects review speed at P3
    },
    "nda_bla": {
        "endpoint_basis": 0.60,     # Evidence baked in; quality still affects NDA review outcome
        "evidence_design": 0.60,    # Design quality flows through to NDA; partially already discounted
        "approval_pathway": 0.50,   # By NDA submission, pathway mainly affects review timeline
    },
}
