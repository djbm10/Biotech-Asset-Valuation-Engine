"""
Sign-aware context modifiers for scored evidence.

Problem
-------
A raw event delta of +0.08 on asset_quality for a Phase 3 positive result should
be amplified when the trial was pivotal/confirmatory, but dampened when:
  - biomarker-selected subgroup only
  - open-label design
  - safety signals were present

Conversely a negative delta (Phase 3 failure) should be amplified when:
  - safety concerns compound the clinical failure
  - it is the company's lead/only asset

Sign-awareness
--------------
Context modifiers are applied conditionally based on the *direction* of the delta:
  - safety_flag   amplifies NEGATIVE deltas (×1.3), dampens POSITIVE (×0.6)
  - is_lead_asset amplifies BOTH directions (×1.15) — more material regardless
  - biomarker_only dampens POSITIVE clinical deltas (×0.7), unchanged for negative
  - open_label    dampens POSITIVE clinical deltas (×0.75), unchanged for negative
  - pivotal_design amplifies POSITIVE clinical deltas (×1.10), amplifies NEGATIVE (×1.05)
  - post_large_runup  dampens POSITIVE deltas (×0.80) — already priced in
  - late_stage_pipeline  amplifies POSITIVE regulatory/clinical (×1.08)

ContextProfile
--------------
A frozen snapshot of all contextual signals relevant at the time of event ingestion.
Built once per event; passed to ContextModifierEngine.apply().

ContextModifierEngine
---------------------
apply(deltas, event_type, profile) → modified deltas dict

All modifications are multiplicative and capped to [0, 1] on the resulting score.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from bve.ingestion.model_versions import CONTEXT_VERSION

# ---------------------------------------------------------------------------
# Event-type families for conditional modifier application
# ---------------------------------------------------------------------------

_CLINICAL_EVENTS = frozenset({
    "clinical_positive_ph3",
    "clinical_positive_ph2",
    "clinical_positive_ph1",
    "clinical_positive",
    "clinical_negative_ph3",
    "clinical_negative_ph2",
    "clinical_negative_ph1",
    "clinical_negative",
    "clinical_mixed",
    "trial_discontinuation",
    "trial_delay",
})

_POSITIVE_CLINICAL = frozenset({
    "clinical_positive_ph3",
    "clinical_positive_ph2",
    "clinical_positive_ph1",
    "clinical_positive",
})

_NEGATIVE_CLINICAL = frozenset({
    "clinical_negative_ph3",
    "clinical_negative_ph2",
    "clinical_negative_ph1",
    "clinical_negative",
    "trial_discontinuation",
})

_REGULATORY_POSITIVE = frozenset({
    "fda_approval",
    "btd",
    "fast_track",
    "adcom_positive",
    "nda_accepted",
})

_REGULATORY_NEGATIVE = frozenset({
    "crl",
    "adcom_negative",
})


# ---------------------------------------------------------------------------
# ContextProfile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextProfile:
    """
    Immutable snapshot of context signals relevant to one ingested event.

    All fields are optional; missing fields apply no modifier.

    Fields
    ------
    safety_flag         : bool — any safety / toxicity concern present?
    is_lead_asset       : bool — event affects the company's lead / only program?
    biomarker_only      : bool — efficacy only in biomarker-selected subgroup?
    open_label          : bool — trial lacked blinded/randomised design?
    pivotal_design      : bool — trial was confirmatory / pivotal (Phase 3 or equiv)?
    post_large_runup    : bool — stock already up ≥100% before this event?
    late_stage_pipeline : bool — program is Phase 3 or in regulatory review?
    version             : str  — CONTEXT_VERSION stamp for audit
    """

    safety_flag: bool = False
    is_lead_asset: bool = False
    biomarker_only: bool = False
    open_label: bool = False
    pivotal_design: bool = False
    post_large_runup: bool = False
    late_stage_pipeline: bool = False
    version: str = CONTEXT_VERSION

    @classmethod
    def from_dict(cls, d: dict) -> "ContextProfile":
        """Build from a plain dict; unknown keys are ignored."""
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# ContextModifierEngine
# ---------------------------------------------------------------------------


class ContextModifierEngine:
    """
    Apply sign-aware context modifiers to a feature-delta dict.

    Usage::

        engine = ContextModifierEngine()
        profile = ContextProfile(safety_flag=True, is_lead_asset=True)
        raw_deltas = {"asset_quality": -0.10, "seller_willingness": +0.05}
        modified = engine.apply(raw_deltas, "clinical_negative_ph3", profile)
        # asset_quality amplified (negative × 1.3 × 1.15)
        # seller_willingness dampened (positive safety_flag × 0.6, then × 1.15 lead)
    """

    def apply(
        self,
        deltas: dict[str, float],
        event_type: str,
        profile: Optional[ContextProfile] = None,
    ) -> dict[str, float]:
        """
        Return a new dict of modified deltas. Input is never mutated.

        Parameters
        ----------
        deltas      : feature → raw delta (pre-context)
        event_type  : classified event type string
        profile     : ContextProfile (None → no modifications applied)
        """
        if profile is None or not deltas:
            return dict(deltas)

        result = {}
        for feature, delta in deltas.items():
            m = self._compute_multiplier(delta, event_type, profile)
            result[feature] = delta * m
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_multiplier(
        self,
        delta: float,
        event_type: str,
        profile: ContextProfile,
    ) -> float:
        """Compute the combined multiplier for one (feature, delta, context) triple."""
        m = 1.0
        is_positive = delta > 0
        is_negative = delta < 0
        is_clinical = event_type in _CLINICAL_EVENTS
        is_positive_clinical = event_type in _POSITIVE_CLINICAL
        is_negative_clinical = event_type in _NEGATIVE_CLINICAL
        is_reg_positive = event_type in _REGULATORY_POSITIVE
        is_reg_negative = event_type in _REGULATORY_NEGATIVE

        # ── safety_flag ─────────────────────────────────────────────────
        if profile.safety_flag:
            if is_negative:
                m *= 1.30   # bad result with safety concern = worse
            elif is_positive:
                m *= 0.60   # good result shadowed by safety signal = dampened

        # ── is_lead_asset ────────────────────────────────────────────────
        if profile.is_lead_asset:
            # Lead asset makes any result more material in either direction
            m *= 1.15

        # ── biomarker_only ───────────────────────────────────────────────
        if profile.biomarker_only and is_clinical:
            if is_positive:
                m *= 0.70   # narrow generalisability
            # negative result not dampened — failure still material

        # ── open_label ───────────────────────────────────────────────────
        if profile.open_label and is_clinical:
            if is_positive:
                m *= 0.75   # weaker evidence design for positive
            # negative result not dampened

        # ── pivotal_design ───────────────────────────────────────────────
        if profile.pivotal_design:
            if is_positive and (is_positive_clinical or is_reg_positive):
                m *= 1.10   # confirmatory positive is very material
            elif is_negative and (is_negative_clinical or is_reg_negative):
                m *= 1.05   # confirmatory failure is more material

        # ── post_large_runup ─────────────────────────────────────────────
        if profile.post_large_runup:
            if is_positive:
                m *= 0.80   # already priced in

        # ── late_stage_pipeline ──────────────────────────────────────────
        if profile.late_stage_pipeline:
            if is_positive and (is_positive_clinical or is_reg_positive):
                m *= 1.08   # late-stage positive = near-term value unlock

        return m
