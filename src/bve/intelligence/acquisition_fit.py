"""Acquisition fit engine — ranks biotech targets by strategic fit for each acquirer.

Scoring dimensions (all bounded [0, 1]):
  strategic_fit      — TA + modality overlap
  pipeline_gap_fit   — target fills acquirer's documented pipeline gaps
  loe_urgency_fit    — LOE pressure makes acquisition more urgent
  commercial_fit     — phase/stage alignment with acquirer preferences
  affordability      — deal size vs acquirer firepower
  exclusivity        — uniqueness / competitive advantage of target
  target_readiness   — how acquirable the target appears (runway, distress, catalyst proximity)

Composite fit_score = weighted sum (weights are versioned and human-promoted).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from bve.entities.acquirer import AcquirerProfile


# ---------------------------------------------------------------------------
# Target summary (lightweight representation of a biotech target)
# ---------------------------------------------------------------------------

class TargetProfile(BaseModel):
    """Lightweight representation of an acquisition target."""
    company_id: str
    name: str
    ticker: Optional[str] = None

    # Science / pipeline
    primary_ta: str
    modality: Optional[str] = None
    current_phase: str = "Phase 2"   # Phase 1 | Phase 2 | Phase 3 | Approved | Preclinical
    indication: Optional[str] = None
    target_mechanism: Optional[str] = None

    # Commercial
    estimated_peak_sales_millions: Optional[float] = None
    partnered: bool = False

    # Financial
    market_cap_millions: Optional[float] = None
    cash_millions: Optional[float] = None
    burn_rate_monthly_millions: Optional[float] = None

    # Signals
    months_to_next_catalyst: Optional[int] = None  # None = no catalyst
    distress_score: float = Field(default=0.0, ge=0.0, le=1.0)  # 0=healthy, 1=distressed
    science_score: float = Field(default=0.5, ge=0.0, le=1.0)

    # Encumbrances
    has_major_partnership: bool = False  # existing deal that limits deal freedom

    @property
    def runway_months(self) -> Optional[float]:
        if self.cash_millions and self.burn_rate_monthly_millions:
            return self.cash_millions / self.burn_rate_monthly_millions
        return None


# ---------------------------------------------------------------------------
# Fit score result
# ---------------------------------------------------------------------------

class TimingBucket(str, Enum):
    NEAR_TERM = "0-6m"
    SHORT_TERM = "6-12m"
    MEDIUM_TERM = "12-24m"
    LONGER_TERM = "24m+"
    UNLIKELY = "unlikely"


@dataclass
class AcquisitionFitScore:
    target_company_id: str
    acquirer_company_id: str
    target_name: str
    acquirer_name: str

    # Dimension scores [0–1]
    strategic_fit: float = 0.0
    pipeline_gap_fit: float = 0.0
    loe_urgency_fit: float = 0.0
    commercial_fit: float = 0.0
    affordability: float = 0.0
    exclusivity: float = 0.0
    target_readiness: float = 0.0

    # Composite
    fit_score: float = 0.0
    confidence: float = 0.5

    # Timing
    timing_bucket: TimingBucket = TimingBucket.UNLIKELY
    timing_drivers: list[str] = field(default_factory=list)

    # Rationale
    rationale: list[str] = field(default_factory=list)
    disqualifiers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "target_company_id": self.target_company_id,
            "acquirer_company_id": self.acquirer_company_id,
            "target_name": self.target_name,
            "acquirer_name": self.acquirer_name,
            "fit_score": round(self.fit_score, 3),
            "timing_bucket": self.timing_bucket.value,
            "strategic_fit": round(self.strategic_fit, 3),
            "pipeline_gap_fit": round(self.pipeline_gap_fit, 3),
            "loe_urgency_fit": round(self.loe_urgency_fit, 3),
            "commercial_fit": round(self.commercial_fit, 3),
            "affordability": round(self.affordability, 3),
            "exclusivity": round(self.exclusivity, 3),
            "target_readiness": round(self.target_readiness, 3),
            "confidence": round(self.confidence, 3),
            "rationale": self.rationale,
            "disqualifiers": self.disqualifiers,
            "timing_drivers": self.timing_drivers,
        }


# ---------------------------------------------------------------------------
# Default weights (version 1.0 — all changes require human review)
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, float] = {
    "strategic_fit": 0.25,
    "pipeline_gap_fit": 0.20,
    "loe_urgency_fit": 0.10,
    "commercial_fit": 0.10,
    "affordability": 0.15,
    "exclusivity": 0.10,
    "target_readiness": 0.10,
}

# Phase ordering for commercial fit scoring
_PHASE_ORDER = {
    "Preclinical": 0,
    "Phase 1": 1,
    "Phase 1/2": 2,
    "Phase 2": 3,
    "Phase 2/3": 4,
    "Phase 3": 5,
    "NDA/BLA": 6,
    "Approved": 7,
}

_ACQUIRER_PREFERRED_PHASE_ORDER = {
    "Phase 2": 3,
    "Phase 3": 5,
    "Approved": 7,
    "Any": -1,  # no preference
}


# ---------------------------------------------------------------------------
# Fit engine
# ---------------------------------------------------------------------------

class AcquisitionFitEngine:
    """Compute acquisition fit between any set of targets and acquirers."""

    def __init__(self, weights: Optional[dict[str, float]] = None) -> None:
        self._weights = weights or DEFAULT_WEIGHTS
        self._validate_weights()

    def _validate_weights(self) -> None:
        total = sum(self._weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total:.3f}")

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def score(
        self,
        target: TargetProfile,
        acquirer: AcquirerProfile,
    ) -> AcquisitionFitScore:
        """Compute a full fit score between one target and one acquirer."""
        result = AcquisitionFitScore(
            target_company_id=target.company_id,
            acquirer_company_id=acquirer.company_id,
            target_name=target.name,
            acquirer_name=acquirer.name,
        )

        # Hard disqualifiers first
        disqualifiers = self._check_disqualifiers(target, acquirer)
        if disqualifiers:
            result.disqualifiers = disqualifiers
            result.fit_score = 0.0
            result.confidence = 0.3
            result.timing_bucket = TimingBucket.UNLIKELY
            return result

        # Score each dimension
        result.strategic_fit, rationale_strategic = self._strategic_fit(target, acquirer)
        result.pipeline_gap_fit, rationale_gap = self._pipeline_gap_fit(target, acquirer)
        result.loe_urgency_fit = self._loe_urgency_fit(acquirer)
        result.commercial_fit, rationale_commercial = self._commercial_fit(target, acquirer)
        result.affordability, rationale_afford = self._affordability(target, acquirer)
        result.exclusivity = self._exclusivity(target)
        result.target_readiness, rationale_ready = self._target_readiness(target)

        # Composite
        result.fit_score = (
            result.strategic_fit * self._weights["strategic_fit"]
            + result.pipeline_gap_fit * self._weights["pipeline_gap_fit"]
            + result.loe_urgency_fit * self._weights["loe_urgency_fit"]
            + result.commercial_fit * self._weights["commercial_fit"]
            + result.affordability * self._weights["affordability"]
            + result.exclusivity * self._weights["exclusivity"]
            + result.target_readiness * self._weights["target_readiness"]
        )

        # Confidence: higher when more data is available
        result.confidence = self._estimate_confidence(target, result.fit_score)

        # Timing
        result.timing_bucket, result.timing_drivers = self._timing(target, acquirer, result)

        # Rationale assembly
        result.rationale = [r for r in [
            *rationale_strategic, *rationale_gap, *rationale_commercial,
            *rationale_afford, *rationale_ready
        ] if r]

        return result

    def rank_targets(
        self,
        targets: list[TargetProfile],
        acquirer: AcquirerProfile,
        min_fit_score: float = 0.0,
    ) -> list[AcquisitionFitScore]:
        """Rank all targets for a given acquirer, highest fit first."""
        scores = [self.score(t, acquirer) for t in targets]
        filtered = [s for s in scores if s.fit_score >= min_fit_score]
        return sorted(filtered, key=lambda s: s.fit_score, reverse=True)

    def rank_acquirers(
        self,
        target: TargetProfile,
        acquirers: list[AcquirerProfile],
        min_fit_score: float = 0.0,
    ) -> list[AcquisitionFitScore]:
        """Rank all acquirers for a given target, highest fit first."""
        scores = [self.score(target, a) for a in acquirers]
        filtered = [s for s in scores if s.fit_score >= min_fit_score]
        return sorted(filtered, key=lambda s: s.fit_score, reverse=True)

    # ------------------------------------------------------------------
    # Dimension scorers
    # ------------------------------------------------------------------

    def _check_disqualifiers(
        self, target: TargetProfile, acquirer: AcquirerProfile
    ) -> list[str]:
        issues = []
        # Too expensive: >50% of firepower is too aggressive even with synergies
        if (
            target.market_cap_millions
            and target.market_cap_millions > acquirer.cash_firepower_millions * 0.60
        ):
            issues.append(
                f"Target market cap {target.market_cap_millions:.0f}M exceeds 60% of "
                f"acquirer firepower {acquirer.cash_firepower_millions:.0f}M"
            )
        # Already majorly partnered with a third party
        if target.has_major_partnership:
            issues.append("Target has existing major partnership that limits deal freedom")
        return issues

    def _strategic_fit(
        self, target: TargetProfile, acquirer: AcquirerProfile
    ) -> tuple[float, list[str]]:
        rationale = []
        score = 0.0

        # TA match (primary signal)
        ta_match = acquirer.covers_ta(target.primary_ta)
        if ta_match:
            score += 0.60
            rationale.append(f"TA match: {target.primary_ta} in acquirer strategic areas")
        else:
            rationale.append(f"TA miss: {target.primary_ta} not in acquirer strategic areas")

        # Modality match
        if target.modality and acquirer.covers_modality(target.modality):
            score += 0.30
            rationale.append(f"Modality match: {target.modality}")
        elif not target.modality:
            score += 0.15  # partial credit — unknown modality
        else:
            rationale.append(f"Modality miss: {target.modality}")

        # Indication specificity bonus
        if ta_match and target.indication:
            score += 0.10
            rationale.append(f"Specific indication: {target.indication}")

        return min(1.0, score), rationale

    def _pipeline_gap_fit(
        self, target: TargetProfile, acquirer: AcquirerProfile
    ) -> tuple[float, list[str]]:
        if not acquirer.pipeline_gaps:
            return 0.5, ["Acquirer has no documented pipeline gaps (neutral)"]

        rationale = []
        matches = 0
        for gap in acquirer.pipeline_gaps:
            ta_match = gap.therapeutic_area.lower() == target.primary_ta.lower()
            mod_match = (
                not gap.modality  # gap is TA-only
                or (target.modality and gap.modality.lower() == target.modality.lower())
            )
            if ta_match and mod_match:
                weight = {"critical": 1.0, "high": 0.80, "medium": 0.50, "low": 0.25}.get(
                    gap.priority, 0.50
                )
                matches += weight
                rationale.append(f"Fills {gap.priority} gap: {gap.therapeutic_area} / {gap.modality or 'any'}")

        if not rationale:
            rationale.append("Target does not fill documented acquirer pipeline gaps")

        return min(1.0, matches / max(1, len(acquirer.pipeline_gaps))), rationale

    def _loe_urgency_fit(self, acquirer: AcquirerProfile) -> float:
        return acquirer.loe_urgency

    def _commercial_fit(
        self, target: TargetProfile, acquirer: AcquirerProfile
    ) -> tuple[float, list[str]]:
        rationale = []
        target_phase_val = _PHASE_ORDER.get(target.current_phase, 3)

        pref = acquirer.preferred_phase
        if not pref or pref == "Any":
            score = 0.70  # neutral preference
            rationale.append("Acquirer has no phase preference")
        else:
            preferred_val = _ACQUIRER_PREFERRED_PHASE_ORDER.get(pref, 3)
            distance = abs(target_phase_val - preferred_val)
            # Score decays by 0.20 per phase of distance
            score = max(0.0, 1.0 - distance * 0.20)
            rationale.append(
                f"Phase {target.current_phase} vs acquirer preference {pref} (distance={distance})"
            )

        return score, rationale

    def _affordability(
        self, target: TargetProfile, acquirer: AcquirerProfile
    ) -> tuple[float, list[str]]:
        rationale = []
        if not target.market_cap_millions:
            return 0.50, ["No market cap data (neutral affordability)"]

        # Typical acquisition premium: 50% over market cap
        deal_size = target.market_cap_millions * 1.5
        firepower = acquirer.cash_firepower_millions

        if firepower <= 0:
            return 0.0, ["Acquirer has no financial capacity"]

        ratio = deal_size / firepower
        # Affordable if deal_size < 25% of firepower → score=1.0
        # Score declines linearly to 0 at 60% of firepower
        if ratio <= 0.25:
            score = 1.0
        elif ratio <= 0.60:
            score = 1.0 - ((ratio - 0.25) / 0.35)
        else:
            score = 0.0

        rationale.append(
            f"Est. deal size {deal_size:.0f}M vs firepower {firepower:.0f}M "
            f"(ratio {ratio:.1%})"
        )
        return max(0.0, min(1.0, score)), rationale

    def _exclusivity(self, target: TargetProfile) -> float:
        """Approximate competitive exclusivity of the target's mechanism/indication."""
        score = target.science_score  # science quality ≈ barrier to imitation
        # Orphan / rare disease bonus → implied in high science score
        return score

    def _target_readiness(
        self, target: TargetProfile
    ) -> tuple[float, list[str]]:
        rationale = []
        score = 0.50  # base

        # Distress increases willingness to deal (but lowers confidence)
        score += target.distress_score * 0.20
        if target.distress_score > 0.5:
            rationale.append(f"Target in financial distress (score={target.distress_score:.2f})")

        # Short runway increases urgency
        runway = target.runway_months
        if runway is not None:
            if runway < 12:
                score += 0.20
                rationale.append(f"Short runway: {runway:.0f} months")
            elif runway < 24:
                score += 0.10

        # Near-term catalyst = good deal window
        if target.months_to_next_catalyst is not None:
            if target.months_to_next_catalyst <= 6:
                score += 0.10
                rationale.append(f"Catalyst in {target.months_to_next_catalyst}m → deal window")

        return min(1.0, score), rationale

    def _estimate_confidence(self, target: TargetProfile, fit_score: float) -> float:
        """Confidence in the score based on data completeness."""
        data_points = sum([
            target.market_cap_millions is not None,
            target.modality is not None,
            target.cash_millions is not None,
            target.estimated_peak_sales_millions is not None,
            target.months_to_next_catalyst is not None,
        ])
        base = 0.30 + data_points * 0.12  # 0.30 → 0.90
        return min(0.90, base)

    # ------------------------------------------------------------------
    # Timing engine
    # ------------------------------------------------------------------

    def _timing(
        self,
        target: TargetProfile,
        acquirer: AcquirerProfile,
        scores: AcquisitionFitScore,
    ) -> tuple[TimingBucket, list[str]]:
        drivers: list[str] = []
        urgency_points = 0

        # LOE cliff pressure
        if acquirer.loe_urgency > 0.6:
            urgency_points += 2
            drivers.append("High LOE urgency for acquirer")
        elif acquirer.loe_urgency > 0.3:
            urgency_points += 1
            drivers.append("Moderate LOE urgency for acquirer")

        # Target financial distress
        if target.distress_score > 0.6:
            urgency_points += 2
            drivers.append("Target in financial distress")
        elif target.distress_score > 0.3:
            urgency_points += 1

        # Short runway
        runway = target.runway_months
        if runway is not None:
            if runway < 12:
                urgency_points += 2
                drivers.append(f"Target runway < 12m ({runway:.0f}m)")
            elif runway < 18:
                urgency_points += 1
                drivers.append(f"Target runway 12-18m ({runway:.0f}m)")

        # Upcoming catalyst = ideal window
        if target.months_to_next_catalyst is not None and target.months_to_next_catalyst <= 6:
            urgency_points += 1
            drivers.append(f"Catalyst in {target.months_to_next_catalyst}m")

        # Low fit → unlikely regardless
        if scores.fit_score < 0.30:
            return TimingBucket.UNLIKELY, drivers

        # Map urgency to timing bucket
        if urgency_points >= 4:
            return TimingBucket.NEAR_TERM, drivers
        elif urgency_points >= 2:
            return TimingBucket.SHORT_TERM, drivers
        elif urgency_points >= 1:
            return TimingBucket.MEDIUM_TERM, drivers
        else:
            return TimingBucket.LONGER_TERM, drivers
