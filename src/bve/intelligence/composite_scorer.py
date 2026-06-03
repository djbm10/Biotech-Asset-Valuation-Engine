"""
Composite score signal extensions for the weekly actionable generator.

Six additive signal layers on top of the base ranking × thesis × opportunity
composite.  All adjustments are purely additive; the base composite is
unchanged when no context is supplied.

Signal registry
---------------
Signal                 Source              Direction
---------------------  ------------------  ---------
catalyst_ev            Wave 1 EV calc      positive: high signal_strength → lift
enrollment             Wave 3 flags        negative: stalling / slow velocity → penalty
phase_correlation      Wave 5 Bayesian     positive: posterior > prior → lift
endpoint_z             Wave 6 z-score      positive: high z → lift
competitor_impact      Wave 2 competitor   negative: high competitor signal_strength → drag
capital_risk           Wave 7 cap struct   negative: HIGH/CRITICAL → discount

Weight configuration
--------------------
All weights live in ``scoring_weights:`` section of ``industry_assumptions.yaml``.
Defaults are used when the section is absent.

Design rules
------------
- Missing signals → adjustment = 0.0 (neutral).  Never blocks scoring.
- All per-signal adjustments are logged in ``signal_adjustments`` for attribution.
- Adjustments are additive to the base composite; clamped to [−0.30, +0.30]
  individually, then summed.  Final composite is clamped to [0.0, 1.0].
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from bve.intelligence.capital_structure import CapitalRiskLevel


# ---------------------------------------------------------------------------
# Defaults  (overridden by scoring_weights section in industry_assumptions.yaml)
# ---------------------------------------------------------------------------

SCORING_WEIGHT_DEFAULTS: dict[str, float] = {
    "catalyst_ev":       0.15,
    "enrollment":        1.00,   # multiplies flag penalty values
    "phase_correlation": 0.25,
    "endpoint_z":        0.05,
    "competitor_impact": 0.05,
    "capital_risk":      1.00,   # multiplies risk discount values
}

# Enrollment penalty per-flag (before weight multiplication)
_ENROLLMENT_PENALTY: dict[str, float] = {
    "site_stalling":  -0.05,
    "velocity_low":   -0.05,
    "slippage_alert": -0.10,
}

# Capital risk discount per level (before weight multiplication)
_CAPITAL_RISK_DISCOUNT: dict[CapitalRiskLevel, float] = {
    CapitalRiskLevel.LOW:      0.00,
    CapitalRiskLevel.MEDIUM:  -0.03,
    CapitalRiskLevel.HIGH:    -0.08,
    CapitalRiskLevel.CRITICAL:-0.15,
}

# Per-signal clamp applied before weight multiplication
_SIGNAL_CLAMP: dict[str, tuple[float, float]] = {
    "catalyst_ev":       (-1.0,  1.0),   # signal_strength is EV/std, clip to ±1
    "endpoint_z":        (-2.0,  2.0),   # z typically ±3; clip at ±2
    "competitor_impact": (-1.0,  1.0),
}


# ---------------------------------------------------------------------------
# Context dataclass
# ---------------------------------------------------------------------------

@dataclass
class CompositeScoreContext:
    """
    Optional signal inputs for the composite scorer.

    All fields are Optional or default False.  Callers populate only the
    fields they have live data for; missing fields are treated as neutral.

    Parameters
    ----------
    catalyst_signal_strength:
        ``CatalystEvent.signal_strength`` from the asset's own nearest catalyst
        (Wave 1 CatalystEVCalculator output).  Typically −3 … +3.
    enrollment_site_stalling:
        ``EnrollmentAlertFlags.site_stalling`` (Wave 3).
    enrollment_velocity_low:
        ``EnrollmentAlertFlags.velocity_low`` (Wave 3).
    enrollment_slippage_alert:
        ``EnrollmentAlertFlags.slippage_alert`` (Wave 3).
    phase_prior_pos:
        ``PhaseCorrelationResult.prior_pos`` before Bayesian update (Wave 5).
    phase_posterior_pos:
        ``PhaseCorrelationResult.posterior_pos`` after Bayesian update (Wave 5).
    endpoint_z_score:
        ``EndpointEvaluation.z_score`` from post-readout benchmarking (Wave 6).
    competitor_signal_strengths:
        List of ``CatalystEvent.signal_strength`` from competitor COMPETITOR_READOUT
        events within the look-ahead window (Wave 2).
    capital_risk:
        ``CapitalStructureAssessment.capital_risk`` level (Wave 7).
    """
    # Wave 1
    catalyst_signal_strength:   Optional[float]       = None

    # Wave 3
    enrollment_site_stalling:   bool                  = False
    enrollment_velocity_low:    bool                  = False
    enrollment_slippage_alert:  bool                  = False

    # Wave 5
    phase_prior_pos:            Optional[float]       = None
    phase_posterior_pos:        Optional[float]       = None

    # Wave 6
    endpoint_z_score:           Optional[float]       = None

    # Wave 2
    competitor_signal_strengths: list[float]          = field(default_factory=list)

    # Wave 7
    capital_risk:               Optional[CapitalRiskLevel] = None


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class CompositeScorer:
    """
    Computes additive score adjustments from six signal sources.

    Parameters
    ----------
    weights:
        Override dict for all six signal weights.  When ``None``, loaded from
        ``industry_assumptions.yaml`` under the ``scoring_weights`` key,
        falling back to ``SCORING_WEIGHT_DEFAULTS``.
    """

    def __init__(self, weights: Optional[dict[str, float]] = None) -> None:
        self._weights = weights if weights is not None else _load_weights()

    def compute_adjustments(
        self,
        ctx: CompositeScoreContext,
    ) -> dict[str, float]:
        """
        Compute per-signal additive adjustments for the composite score.

        Parameters
        ----------
        ctx:
            Signal context for one asset.

        Returns
        -------
        Dict mapping signal name → float adjustment.
        Each value is the contribution of that signal to the composite delta.
        Values sum to the total additive change (before final composite clamp).
        Absent signals contribute exactly 0.0.
        """
        w = self._weights
        adj: dict[str, float] = {}

        # ── Signal 1: Catalyst EV signal_strength ──────────────────────────
        if ctx.catalyst_signal_strength is not None:
            lo, hi = _SIGNAL_CLAMP["catalyst_ev"]
            clipped = max(lo, min(hi, ctx.catalyst_signal_strength))
            adj["catalyst_ev"] = round(clipped * w.get("catalyst_ev", SCORING_WEIGHT_DEFAULTS["catalyst_ev"]), 4)
        else:
            adj["catalyst_ev"] = 0.0

        # ── Signal 2: Enrollment flags ──────────────────────────────────────
        raw_enrollment = 0.0
        if ctx.enrollment_site_stalling:
            raw_enrollment += _ENROLLMENT_PENALTY["site_stalling"]
        if ctx.enrollment_velocity_low:
            raw_enrollment += _ENROLLMENT_PENALTY["velocity_low"]
        if ctx.enrollment_slippage_alert:
            raw_enrollment += _ENROLLMENT_PENALTY["slippage_alert"]
        adj["enrollment"] = round(
            raw_enrollment * w.get("enrollment", SCORING_WEIGHT_DEFAULTS["enrollment"]), 4
        )

        # ── Signal 3: Phase correlation posterior delta ─────────────────────
        if ctx.phase_prior_pos is not None and ctx.phase_posterior_pos is not None:
            # delta in ±0.25 (capped inside PhaseCorrelationUpdater)
            delta = ctx.phase_posterior_pos - ctx.phase_prior_pos
            adj["phase_correlation"] = round(
                delta * w.get("phase_correlation", SCORING_WEIGHT_DEFAULTS["phase_correlation"]), 4
            )
        else:
            adj["phase_correlation"] = 0.0

        # ── Signal 4: Endpoint z-score ──────────────────────────────────────
        if ctx.endpoint_z_score is not None:
            lo, hi = _SIGNAL_CLAMP["endpoint_z"]
            clipped_z = max(lo, min(hi, ctx.endpoint_z_score))
            adj["endpoint_z"] = round(
                clipped_z * w.get("endpoint_z", SCORING_WEIGHT_DEFAULTS["endpoint_z"]), 4
            )
        else:
            adj["endpoint_z"] = 0.0

        # ── Signal 5: Competitor catalyst impact ────────────────────────────
        if ctx.competitor_signal_strengths:
            mean_comp = sum(ctx.competitor_signal_strengths) / len(ctx.competitor_signal_strengths)
            lo, hi = _SIGNAL_CLAMP["competitor_impact"]
            clipped_comp = max(lo, min(hi, mean_comp))
            # Positive competitor signal_strength → drag on our asset
            adj["competitor_impact"] = round(
                -clipped_comp * w.get("competitor_impact", SCORING_WEIGHT_DEFAULTS["competitor_impact"]), 4
            )
        else:
            adj["competitor_impact"] = 0.0

        # ── Signal 6: Capital risk discount ─────────────────────────────────
        if ctx.capital_risk is not None:
            discount = _CAPITAL_RISK_DISCOUNT.get(ctx.capital_risk, 0.0)
            adj["capital_risk"] = round(
                discount * w.get("capital_risk", SCORING_WEIGHT_DEFAULTS["capital_risk"]), 4
            )
        else:
            adj["capital_risk"] = 0.0

        return adj

    @staticmethod
    def total(adjustments: dict[str, float]) -> float:
        """Return the sum of all signal adjustments."""
        return round(sum(adjustments.values()), 4)


# ---------------------------------------------------------------------------
# YAML weight loader
# ---------------------------------------------------------------------------

def _load_weights() -> dict[str, float]:
    """
    Load scoring_weights from industry_assumptions.yaml.

    Falls back to ``SCORING_WEIGHT_DEFAULTS`` for any missing keys, so a
    partial YAML section is safe.
    """
    merged = dict(SCORING_WEIGHT_DEFAULTS)
    try:
        from bve.config.assumptions_loader import AssumptionsLoader
        from bve.intelligence.trial_design_feature_extractor import _unfreeze
        data = AssumptionsLoader.get()._data
        section = data.get("scoring_weights")
        if section:
            raw = _unfreeze(section)
            for k, v in raw.items():
                if k in merged:
                    merged[k] = float(v)
    except Exception:
        pass
    return merged
