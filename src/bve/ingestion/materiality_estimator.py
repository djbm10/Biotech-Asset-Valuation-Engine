"""
Materiality estimator for biotech events.

Separates CONFIDENCE from MATERIALITY:
  confidence  — how sure are we this event is real / correctly classified?
                (driven by source type and hedging language)
  materiality — how important is this event to valuation / M&A attractiveness?
                (driven by event type, context hints, trial design, etc.)

These two dimensions are orthogonal:
  - An FDA orphan designation from the FDA website may be confidence=0.95, materiality=0.15
  - A Phase 3 failure headline on a news article may be confidence=0.70, materiality=0.90

Effective delta = base_delta × confidence × materiality × novelty

Direction-specific modifiers
-----------------------------
Some event types need conditional materiality based on context hints:
  FDA approval with broad clean label  → full materiality
  FDA approval with narrow label       → 75% materiality
  Phase 2 randomised, stat sig         → full materiality
  Phase 2 biomarker-only subset        → 60% materiality
  Phase 2 open-label, small n          → 70% materiality

These are controlled via optional context_hints dict passed to estimate().
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from bve.ingestion.model_versions import MATERIALITY_VERSION


# ---------------------------------------------------------------------------
# Base materiality by event type
# ---------------------------------------------------------------------------

BASE_MATERIALITY: dict[str, float] = {
    # Clinical — phase 3 outcomes most material
    "clinical_negative_ph3":  0.92,
    "clinical_positive_ph3":  0.88,
    "clinical_negative_ph2":  0.65,
    "clinical_positive_ph2":  0.62,
    "clinical_mixed":         0.45,
    "clinical_negative_ph1":  0.35,
    "clinical_positive_ph1":  0.30,
    "clinical_negative":      0.55,
    "clinical_positive":      0.50,
    "trial_discontinuation":  0.80,
    "trial_delay":            0.40,
    "trial_start":            0.18,
    # Regulatory
    "fda_approval":           0.88,
    "crl":                    0.92,
    "adcom_negative":         0.72,
    "adcom_positive":         0.70,
    "nda_accepted":           0.52,
    "pdufa":                  0.30,  # milestone marker only
    "btd":                    0.42,
    "fast_track":             0.20,
    "orphan":                 0.15,  # routine designation — very low
    # Financial / BD
    "strategic_review":       0.75,
    "cash_low":               0.58,
    "restructuring":          0.42,
    "asset_sale":             0.50,
    "licensing_deal":         0.48,
    "partnership":            0.35,
    "equity_raise":           0.25,
    # Acquirer signals
    "patent_cliff":           0.60,
    "acquirer_large_deal":    0.40,
    "acquirer_bd_appetite":   0.28,
    # Unclassified
    "unclassified":           0.0,
}

# Default for unknown event types
_DEFAULT_MATERIALITY = 0.30


# ---------------------------------------------------------------------------
# Novelty priors — how surprising is this event type in isolation?
# Novelty can only be properly estimated with domain context (priced-in vs not)
# but we provide sensible priors here as starting points.
# ---------------------------------------------------------------------------

BASE_NOVELTY: dict[str, float] = {
    "clinical_negative_ph3":  0.70,  # failures are often surprising
    "clinical_positive_ph3":  0.65,
    "crl":                    0.75,
    "fda_approval":           0.55,  # approvals partially priced in
    "adcom_negative":         0.70,
    "adcom_positive":         0.55,
    "strategic_review":       0.80,  # often unexpected
    "cash_low":               0.50,
    "trial_discontinuation":  0.65,
    "btd":                    0.45,
    "orphan":                 0.20,  # routine, expected
    "fast_track":             0.25,
    "pdufa":                  0.10,  # PDUFA dates are announced, not surprising
    "equity_raise":           0.30,
    "trial_start":            0.20,
}
_DEFAULT_NOVELTY = 0.40


# ---------------------------------------------------------------------------
# Evidence strength by source type
# ---------------------------------------------------------------------------

EVIDENCE_STRENGTH_BY_SOURCE: dict[str, float] = {
    "fda_website":        0.95,
    "sec_filing":         0.90,
    "clinicaltrials_gov": 0.85,
    "pubmed":             0.88,
    "press_release":      0.75,
    "news_article":       0.60,
    "manual":             0.70,
}
_DEFAULT_EVIDENCE_STRENGTH = 0.60


# ---------------------------------------------------------------------------
# Materiality output dataclass
# ---------------------------------------------------------------------------


@dataclass
class MaterialityEstimate:
    """
    Full materiality assessment for one classified event.

    materiality      — economic / M&A relevance (0–1)
    novelty          — how surprising / not-yet-priced-in (0–1)
    evidence_strength — quality of the underlying data (0–1)
    version          — MATERIALITY_VERSION stamp for audit
    """
    materiality: float
    novelty: float
    evidence_strength: float
    version: str = MATERIALITY_VERSION


# ---------------------------------------------------------------------------
# MaterialityEstimator
# ---------------------------------------------------------------------------


class MaterialityEstimator:
    """
    Estimate materiality, novelty, and evidence strength for a classified event.

    Parameters to estimate() map to the context_hints dict keys:
      trial_design     : "standard" | "randomized" | "open_label" | "pivotal" | "exploratory"
      endpoint_result  : "standard" | "stat_sig" | "subgroup_only" | "biomarker_only"
      safety_flag      : bool — any safety concern mentioned?
      label_breadth    : "broad" | "standard" | "narrow"
      post_large_runup : bool — stock already +100%+ before this event?
      indication_size  : "small" | "medium" | "large"
      is_lead_asset    : bool — event affects the company's lead/only program?

    Usage::

        estimator = MaterialityEstimator()
        est = estimator.estimate(
            event_type="fda_approval",
            source_type="fda_website",
            context_hints={"label_breadth": "narrow", "post_large_runup": True},
        )
        # est.materiality ≈ 0.49  (reduced from base 0.88)
    """

    def estimate(
        self,
        event_type: str,
        source_type: str = "news_article",
        context_hints: Optional[dict] = None,
    ) -> MaterialityEstimate:
        """
        Estimate materiality, novelty, and evidence strength.

        context_hints keys (all optional):
            trial_design     str    "standard" | "randomized" | "open_label" | "pivotal" | "exploratory"
            endpoint_result  str    "standard" | "stat_sig" | "subgroup_only" | "biomarker_only"
            safety_flag      bool
            label_breadth    str    "broad" | "standard" | "narrow"
            post_large_runup bool
            indication_size  str    "small" | "medium" | "large"
            is_lead_asset    bool
        """
        hints = context_hints or {}
        base_mat = BASE_MATERIALITY.get(event_type, _DEFAULT_MATERIALITY)
        materiality = self._apply_materiality_modifiers(event_type, base_mat, hints)
        novelty = BASE_NOVELTY.get(event_type, _DEFAULT_NOVELTY)
        evidence_strength = EVIDENCE_STRENGTH_BY_SOURCE.get(source_type, _DEFAULT_EVIDENCE_STRENGTH)

        return MaterialityEstimate(
            materiality=round(max(0.0, min(1.0, materiality)), 4),
            novelty=round(max(0.0, min(1.0, novelty)), 4),
            evidence_strength=round(evidence_strength, 4),
        )

    def _apply_materiality_modifiers(
        self,
        event_type: str,
        base: float,
        hints: dict,
    ) -> float:
        m = base

        # ── FDA approval: context-dependent ─────────────────────────────────
        if event_type == "fda_approval":
            label = hints.get("label_breadth", "standard")
            if label == "narrow":
                m *= 0.75
            elif label == "broad":
                m *= 1.00  # no change — default assumption is standard
            if hints.get("post_large_runup", False):
                # Stock already re-rated; M&A attractiveness may actually decrease
                m *= 0.80
            if hints.get("indication_size") == "large":
                m = min(1.0, m * 1.08)

        # ── Clinical phase 2/3: trial design and endpoint result ─────────────
        elif event_type in ("clinical_positive_ph2", "clinical_positive_ph3",
                            "clinical_negative_ph2", "clinical_negative_ph3"):
            design = hints.get("trial_design", "standard")
            endpoint = hints.get("endpoint_result", "standard")

            if design == "randomized":
                m = min(1.0, m * 1.05)
            elif design in ("open_label", "exploratory"):
                m *= 0.70
            elif design == "pivotal":
                m = min(1.0, m * 1.10)

            if endpoint == "biomarker_only":
                # Result only in biomarker-selected subset — narrow generalisability
                m *= 0.60
            elif endpoint == "subgroup_only":
                m *= 0.70
            elif endpoint == "stat_sig":
                m = min(1.0, m * 1.05)

            if hints.get("safety_flag", False) and "negative" in event_type:
                m = min(1.0, m * 1.10)  # safety compound of negative result

        # ── Any event: indication size ────────────────────────────────────────
        ind_size = hints.get("indication_size")
        if ind_size == "small":
            m *= 0.80
        elif ind_size == "large":
            m = min(1.0, m * 1.10)

        # ── Lead asset amplification ──────────────────────────────────────────
        if hints.get("is_lead_asset", False):
            m = min(1.0, m * 1.10)

        return m
