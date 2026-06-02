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

# Cash runway distress signals
_CASH_DISTRESS_MONTHS      = 12
_CASH_DISTRESS_ADJUSTMENT  = +0.08  # distress accelerates deal willingness


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

        # Cash distress
        runway = features.get("cash_runway_months")
        if runway is not None and runway < _CASH_DISTRESS_MONTHS:
            breakdown["cash_distress"] = _CASH_DISTRESS_ADJUSTMENT
            adjustment += _CASH_DISTRESS_ADJUSTMENT

        raw_ma = _BASE_PRIOR + adjustment
        ma_score = round(max(0.05, min(0.95, raw_ma)), 4)

        # Derive asset_quality and seller_willingness from structural features
        # (simplified heuristics; event evidence will override later)
        asset_adj = self._asset_quality_adjustment(features)
        asset_score = round(max(0.05, min(0.95, _BASE_PRIOR + asset_adj)), 4)

        seller_adj = self._seller_willingness_adjustment(features)
        seller_score = round(max(0.05, min(0.95, _BASE_PRIOR + seller_adj)), 4)

        scores = {
            "ma_attractiveness": ma_score,
            "asset_quality": asset_score,
            "seller_willingness": seller_score,
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
        if runway is not None and runway < _CASH_DISTRESS_MONTHS:
            adj += _CASH_DISTRESS_ADJUSTMENT * 1.5  # distress strongly drives willingness
        if features.get("single_asset"):
            adj += _SINGLE_ASSET_ADJUSTMENT * 0.5
        if features.get("platform_company"):
            adj += _PLATFORM_ADJUSTMENT  # platform co less willing to sell
        return adj
