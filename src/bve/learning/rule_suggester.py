"""Analyze postmortems and prediction accuracy to suggest model rule adjustments."""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from bve.learning.postmortem import ErrorCategory, PostmortemStore
from bve.learning.prediction_log import PredictionLog


class RuleSuggestionType(str, Enum):
    """Types of model rule adjustments that can be suggested."""

    LOWER_BASE_POS = "lower_base_pos"  # model consistently over-optimistic
    RAISE_BASE_POS = "raise_base_pos"
    TIGHTEN_IV_THRESHOLD = "tighten_iv_threshold"
    WIDEN_EV_GAP_THRESHOLD = "widen_ev_gap_threshold"
    ADD_FINANCING_GATE = "add_financing_gate"
    ADD_COMPETITION_DISCOUNT = "add_competition_discount"
    REDUCE_POSITION_CAP = "reduce_position_cap"
    REVIEW_TA_ASSUMPTIONS = "review_ta_assumptions"


class RuleSuggestion(BaseModel):
    """A single rule adjustment suggestion with supporting evidence."""

    suggestion_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    suggestion_type: RuleSuggestionType
    description: str
    evidence_count: int  # number of postmortems / predictions supporting this
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_review: bool = True  # always True for rule changes
    auto_applicable: bool = False


# ---------------------------------------------------------------------------
# Thresholds (named constants — no magic numbers inline)
# ---------------------------------------------------------------------------

_MIN_ERROR_COUNT = 3
_MIN_ERROR_FRACTION = 0.40
_MIN_FINANCING_SURPRISES = 2
_MIN_COMPETITION_SURPRISES = 2
_BRIER_POOR_THRESHOLD = 0.25


class RuleSuggester:
    """Analyze PostmortemStore and PredictionLog to surface rule suggestions.

    Decision logic:
    - pos_overestimate > 3 AND > 40 % of errors  → LOWER_BASE_POS (conf 0.80)
    - pos_underestimate > 3 AND > 40 %            → RAISE_BASE_POS (conf 0.80)
    - financing_surprise >= 2                      → ADD_FINANCING_GATE (conf 0.70)
    - competition_surprise >= 2                    → ADD_COMPETITION_DISCOUNT (conf 0.70)
    - brier_score > 0.25                           → LOWER_BASE_POS (conf 0.60, lower priority)

    All suggestions always carry requires_human_review=True, auto_applicable=False.
    """

    def analyze(
        self,
        postmortem_store: PostmortemStore,
        prediction_log: PredictionLog,
    ) -> list[RuleSuggestion]:
        """Return all applicable rule suggestions, ordered by confidence descending."""
        suggestions: list[RuleSuggestion] = []
        dist = postmortem_store.error_distribution()
        total_errors = sum(dist.values())

        # --- POS overestimate check ----------------------------------------
        over_count = dist.get(ErrorCategory.POS_OVERESTIMATE.value, 0)
        if total_errors > 0 and over_count > _MIN_ERROR_COUNT:
            fraction = over_count / total_errors
            if fraction > _MIN_ERROR_FRACTION:
                suggestions.append(
                    RuleSuggestion(
                        suggestion_type=RuleSuggestionType.LOWER_BASE_POS,
                        description=(
                            f"Model has {over_count} pos_overestimate errors "
                            f"({fraction:.0%} of all errors). "
                            "Consider lowering base PoS assumptions."
                        ),
                        evidence_count=over_count,
                        confidence=0.80,
                    )
                )

        # --- POS underestimate check ----------------------------------------
        under_count = dist.get(ErrorCategory.POS_UNDERESTIMATE.value, 0)
        if total_errors > 0 and under_count > _MIN_ERROR_COUNT:
            fraction = under_count / total_errors
            if fraction > _MIN_ERROR_FRACTION:
                suggestions.append(
                    RuleSuggestion(
                        suggestion_type=RuleSuggestionType.RAISE_BASE_POS,
                        description=(
                            f"Model has {under_count} pos_underestimate errors "
                            f"({fraction:.0%} of all errors). "
                            "Consider raising base PoS assumptions."
                        ),
                        evidence_count=under_count,
                        confidence=0.80,
                    )
                )

        # --- Financing surprise check ----------------------------------------
        financing_count = dist.get(ErrorCategory.FINANCING_SURPRISE.value, 0)
        if financing_count >= _MIN_FINANCING_SURPRISES:
            suggestions.append(
                RuleSuggestion(
                    suggestion_type=RuleSuggestionType.ADD_FINANCING_GATE,
                    description=(
                        f"Model encountered {financing_count} financing surprises. "
                        "Consider adding a financing risk gate to the entry criteria."
                    ),
                    evidence_count=financing_count,
                    confidence=0.70,
                )
            )

        # --- Competition surprise check --------------------------------------
        competition_count = dist.get(ErrorCategory.COMPETITION_SURPRISE.value, 0)
        if competition_count >= _MIN_COMPETITION_SURPRISES:
            suggestions.append(
                RuleSuggestion(
                    suggestion_type=RuleSuggestionType.ADD_COMPETITION_DISCOUNT,
                    description=(
                        f"Model encountered {competition_count} competition surprises. "
                        "Consider applying a systematic competition discount."
                    ),
                    evidence_count=competition_count,
                    confidence=0.70,
                )
            )

        # --- Brier score check (from PredictionLog) -------------------------
        accuracy = prediction_log.compute_accuracy()
        if (
            accuracy.brier_score is not None
            and accuracy.brier_score > _BRIER_POOR_THRESHOLD
        ):
            # Only add if not already covered by the postmortem-based LOWER_BASE_POS
            already_suggested = any(
                s.suggestion_type == RuleSuggestionType.LOWER_BASE_POS
                for s in suggestions
            )
            if not already_suggested:
                suggestions.append(
                    RuleSuggestion(
                        suggestion_type=RuleSuggestionType.LOWER_BASE_POS,
                        description=(
                            f"PredictionLog Brier score = {accuracy.brier_score:.3f} "
                            f"(threshold {_BRIER_POOR_THRESHOLD}). "
                            "Model shows poor probabilistic calibration; "
                            "consider lowering base PoS."
                        ),
                        evidence_count=accuracy.n_predictions,
                        confidence=0.60,
                    )
                )

        # Sort by confidence descending so top_suggestion() is trivial
        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        return suggestions

    def top_suggestion(
        self,
        postmortem_store: PostmortemStore,
        prediction_log: PredictionLog,
    ) -> Optional[RuleSuggestion]:
        """Return the highest-confidence suggestion, or None if none apply."""
        suggestions = self.analyze(postmortem_store, prediction_log)
        return suggestions[0] if suggestions else None
