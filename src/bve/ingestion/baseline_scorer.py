"""
Structured baseline scores for M&A attractiveness.

Baseline scores represent the prior probability of M&A attractiveness *before*
any news events are observed. They encode structural features of the asset and
company that are unlikely to change on a weekly basis.

Design principles
-----------------
1. Broad priors — start near 0.50 and adjust by observable features.
2. Additive modifiers — each structural feature adds/subtracts a small amount.
3. Clamped to [0.05, 0.95] — never assign certainty from structural data alone.
4. as_of_date support — freeze scores to a historical point in time (no lookahead).
5. Versioned — BASELINE_VERSION stamps the rules used so backtest replays can
   detect when priors changed between runs.

Structural feature keys (all optional; missing → prior used)
------------------------------------------------------------
  phase             : "preclinical" | "phase1" | "phase2" | "phase3" | "approved"
  therapeutic_area  : "oncology" | "rare_disease" | "cns" | "immunology" | "other"
  modality          : "small_molecule" | "biologic" | "cell_gene" | "rna"
  has_orphan        : bool — orphan designation granted
  has_btd           : bool — breakthrough therapy designation
  has_fast_track    : bool — fast track designation
  platform_company  : bool — multiple assets from the same platform (reduces urgency)
  single_asset      : bool — company has only one meaningful program
  cash_runway_months: int  — months of cash remaining (< 12 = distressed)
  market_cap_millions: float — used only for bucket; not a direct modifier
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from bve.ingestion.model_versions import BASELINE_VERSION


# ---------------------------------------------------------------------------
# Baseline priors by feature value
# ---------------------------------------------------------------------------

# Starting prior for all features
_BASE_PRIOR = 0.50

# Phase priors — adjustment from base
_PHASE_ADJUSTMENT: dict[str, float] = {
    "preclinical":  -0.10,
    "phase1":       -0.05,
    "phase2":        0.00,   # neutral
    "phase3":       +0.08,   # late-stage = more attractive
    "approved":     +0.10,   # de-risked asset
}

# Therapeutic area adjustments
_TA_ADJUSTMENT: dict[str, float] = {
    "oncology":       +0.05,  # historically high M&A activity
    "rare_disease":   +0.08,  # orphan economics, pricing power
    "cns":            -0.03,  # high trial failure rate
    "immunology":     +0.04,
    "cardiovascular": +0.02,
    "infectious":     +0.01,
    "other":           0.00,
}

# Modality adjustments
_MODALITY_ADJUSTMENT: dict[str, float] = {
    "small_molecule":  0.00,   # neutral — most common
    "biologic":       +0.03,   # biosimilar moat, harder to replicate
    "cell_gene":      +0.06,   # high strategic value, differentiated
    "rna":            +0.04,   # platform-level strategic interest
    "antibody_drug_conjugate": +0.05,
}

# Designation adjustments
_ORPHAN_ADJUSTMENT         = +0.05
_BTD_ADJUSTMENT            = +0.07
_FAST_TRACK_ADJUSTMENT     = +0.03

# Platform / single-asset
_PLATFORM_ADJUSTMENT       = -0.04  # platform reduces urgency for acquirer
_SINGLE_ASSET_ADJUSTMENT   = +0.06  # single asset = cleaner acquisition target

# Cash runway — tiered thresholds and adjustments.
# Burn is estimated from R&D-only, so actual runway is shorter (SG&A excluded).
# Use conservative tiers to account for that systematic overestimate.
#
# seller_willingness deltas: distress forces deal-seeking → more willing to sell
# financing_risk deltas: near-zero cash → acquirer bears dilution / bridge risk
#
# Tiers (months of runway based on R&D-only burn estimate):
#   CRITICAL  ≤  6 months  — existential; forced sale or shutdown imminent
#   HIGH      ≤ 12 months  — significant pressure; management actively exploring options
#   MODERATE  ≤ 18 months  — moderate concern; deal may be attractive vs. equity raise
#   LOW       >  18 months — well-funded; no distress signal

_RUNWAY_CRITICAL_MONTHS   = 6
_RUNWAY_HIGH_MONTHS       = 12
_RUNWAY_MODERATE_MONTHS   = 18

# seller_willingness adjustments per tier (positive = more willing)
_SELLER_WILLINGNESS_CRITICAL  = +0.20
_SELLER_WILLINGNESS_HIGH      = +0.12
_SELLER_WILLINGNESS_MODERATE  = +0.05

# financing_risk adjustments per tier (positive = more risk to acquirer)
_FINANCING_RISK_CRITICAL  = +0.25
_FINANCING_RISK_HIGH      = +0.15
_FINANCING_RISK_MODERATE  = +0.06


# ---------------------------------------------------------------------------
# BaselineScore output dataclass
# ---------------------------------------------------------------------------


@dataclass
class BaselineScore:
    """
    Structured baseline score for one company/asset.

    Fields
    ------
    scores          : dict of feature_name → baseline value [0,1]
    feature_breakdown: dict explaining which adjustments were applied
    as_of_date      : ISO date string (or None = current)
    version         : BASELINE_VERSION stamp
    """

    scores: dict[str, float]
    feature_breakdown: dict[str, float]
    as_of_date: Optional[str]
    version: str = BASELINE_VERSION


# ---------------------------------------------------------------------------
# BaselineScorer
# ---------------------------------------------------------------------------


class BaselineScorer:
    """
    Compute structured baseline M&A attractiveness scores from structural features.

    Usage::

        scorer = BaselineScorer()
        baseline = scorer.compute(
            features={
                "phase": "phase3",
                "therapeutic_area": "oncology",
                "has_btd": True,
                "single_asset": True,
            },
            as_of_date="2024-06-01",
        )
        # baseline.scores["ma_attractiveness"] ≈ 0.80
    """

    # The features we expose as baseline score dimensions
    _SCORE_KEYS = ("ma_attractiveness", "asset_quality", "seller_willingness")

    def compute(
        self,
        features: dict,
        as_of_date: Optional[str] = None,
    ) -> BaselineScore:
        """
        Compute baseline scores from structural features.

        Parameters
        ----------
        features    : dict of structural feature keys (see module docstring)
        as_of_date  : ISO date string — for audit; does not filter features here
                      (caller is responsible for ensuring features are as-of-date)
        """
        breakdown: dict[str, float] = {"base": _BASE_PRIOR}
        adjustment = 0.0

        # Phase
        phase = features.get("phase")
        if phase and phase in _PHASE_ADJUSTMENT:
            adj = _PHASE_ADJUSTMENT[phase]
            breakdown[f"phase:{phase}"] = adj
            adjustment += adj

        # Therapeutic area
        ta = features.get("therapeutic_area")
        if ta and ta in _TA_ADJUSTMENT:
            adj = _TA_ADJUSTMENT[ta]
            breakdown[f"ta:{ta}"] = adj
            adjustment += adj

        # Modality
        modality = features.get("modality")
        if modality and modality in _MODALITY_ADJUSTMENT:
            adj = _MODALITY_ADJUSTMENT[modality]
            breakdown[f"modality:{modality}"] = adj
            adjustment += adj

        # Designations
        if features.get("has_btd"):
            breakdown["has_btd"] = _BTD_ADJUSTMENT
            adjustment += _BTD_ADJUSTMENT
        if features.get("has_orphan"):
            breakdown["has_orphan"] = _ORPHAN_ADJUSTMENT
            adjustment += _ORPHAN_ADJUSTMENT
        if features.get("has_fast_track"):
            breakdown["has_fast_track"] = _FAST_TRACK_ADJUSTMENT
            adjustment += _FAST_TRACK_ADJUSTMENT

        # Platform vs single-asset
        if features.get("platform_company"):
            breakdown["platform_company"] = _PLATFORM_ADJUSTMENT
            adjustment += _PLATFORM_ADJUSTMENT
        if features.get("single_asset"):
            breakdown["single_asset"] = _SINGLE_ASSET_ADJUSTMENT
            adjustment += _SINGLE_ASSET_ADJUSTMENT

        # Cash runway — tiered distress signal for ma_attractiveness
        runway = features.get("cash_runway_months")
        if runway is not None:
            if runway <= _RUNWAY_CRITICAL_MONTHS:
                cash_adj = _SELLER_WILLINGNESS_CRITICAL * 0.5
            elif runway <= _RUNWAY_HIGH_MONTHS:
                cash_adj = _SELLER_WILLINGNESS_HIGH * 0.5
            elif runway <= _RUNWAY_MODERATE_MONTHS:
                cash_adj = _SELLER_WILLINGNESS_MODERATE * 0.5
            else:
                cash_adj = 0.0
            if cash_adj > 0:
                breakdown["cash_runway_distress"] = cash_adj
                adjustment += cash_adj

        raw_ma = _BASE_PRIOR + adjustment
        ma_score = round(max(0.05, min(0.95, raw_ma)), 4)

        # Derive asset_quality, seller_willingness, and financing_risk
        # (simplified heuristics; event evidence will override later)
        asset_adj = self._asset_quality_adjustment(features)
        asset_score = round(max(0.05, min(0.95, _BASE_PRIOR + asset_adj)), 4)

        seller_adj = self._seller_willingness_adjustment(features)
        seller_score = round(max(0.05, min(0.95, _BASE_PRIOR + seller_adj)), 4)

        financing_adj = self._financing_risk_adjustment(features)
        financing_risk_score = round(max(0.0, min(1.0, financing_adj)), 4)

        scores = {
            "ma_attractiveness": ma_score,
            "asset_quality": asset_score,
            "seller_willingness": seller_score,
            "financing_risk": financing_risk_score,
        }

        return BaselineScore(
            scores=scores,
            feature_breakdown=breakdown,
            as_of_date=as_of_date,
        )

    # ------------------------------------------------------------------
    # Component adjustments
    # ------------------------------------------------------------------

    def _asset_quality_adjustment(self, features: dict) -> float:
        adj = 0.0
        phase = features.get("phase")
        if phase in _PHASE_ADJUSTMENT:
            adj += _PHASE_ADJUSTMENT[phase]
        if features.get("has_btd"):
            adj += _BTD_ADJUSTMENT
        if features.get("has_orphan"):
            adj += _ORPHAN_ADJUSTMENT * 0.5  # orphan is TA designation, partial quality signal
        modality = features.get("modality")
        if modality in _MODALITY_ADJUSTMENT:
            adj += _MODALITY_ADJUSTMENT[modality] * 0.5
        return adj

    def _seller_willingness_adjustment(self, features: dict) -> float:
        adj = 0.0
        runway = features.get("cash_runway_months")
        if runway is not None:
            if runway <= _RUNWAY_CRITICAL_MONTHS:
                adj += _SELLER_WILLINGNESS_CRITICAL
            elif runway <= _RUNWAY_HIGH_MONTHS:
                adj += _SELLER_WILLINGNESS_HIGH
            elif runway <= _RUNWAY_MODERATE_MONTHS:
                adj += _SELLER_WILLINGNESS_MODERATE
        if features.get("single_asset"):
            adj += _SINGLE_ASSET_ADJUSTMENT * 0.5
        if features.get("platform_company"):
            adj += _PLATFORM_ADJUSTMENT  # platform co less willing to sell
        return adj

    def _financing_risk_adjustment(self, features: dict) -> float:
        """Acquirer-side risk from target's cash position: dilution / bridge financing."""
        runway = features.get("cash_runway_months")
        if runway is None:
            # Unknown cash ≠ safe cash.  Apply a moderate penalty so that targets
            # with missing financial data do not appear risk-free to acquirers.
            return _FINANCING_RISK_MODERATE
        if runway <= _RUNWAY_CRITICAL_MONTHS:
            return _FINANCING_RISK_CRITICAL
        if runway <= _RUNWAY_HIGH_MONTHS:
            return _FINANCING_RISK_HIGH
        if runway <= _RUNWAY_MODERATE_MONTHS:
            return _FINANCING_RISK_MODERATE
        return 0.0
