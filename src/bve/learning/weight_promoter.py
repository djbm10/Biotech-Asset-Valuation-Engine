"""Suggests rule/weight changes based on calibration, always requiring human review."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from bve.learning.calibration import CalibrationReport
from bve.learning.postmortem import PostmortemStore, ErrorCategory


class PromotionStatus(str, Enum):
    PENDING_REVIEW = "pending_review"   # awaiting human decision
    APPROVED = "approved"               # human approved
    VETOED = "vetoed"                   # human rejected
    EXPIRED = "expired"                 # not reviewed within expiry window


class SuggestionType(str, Enum):
    INCREASE_DOMAIN_WEIGHT = "increase_domain_weight"
    DECREASE_DOMAIN_WEIGHT = "decrease_domain_weight"
    RECALIBRATE_POS_PRIOR = "recalibrate_pos_prior"
    FLAG_FOR_REVIEW = "flag_for_review"


@dataclass
class WeightSuggestion:
    suggestion_id: str         # UUID
    suggestion_type: SuggestionType
    domain: str                # which domain/module is affected
    current_value: float
    suggested_value: float
    rationale: str
    supporting_evidence: str   # e.g. "competition_error in 60% of INCORRECT outcomes"
    requires_human_review: bool = True   # ALWAYS True — never auto-promote
    status: PromotionStatus = PromotionStatus.PENDING_REVIEW
    created_at: datetime = None   # set to UTC now on creation
    reviewed_at: datetime | None = None
    reviewer_note: str | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now(timezone.utc))


class WeightPromoter:
    """
    Analyzes calibration report + postmortem store to generate weight suggestions.
    Suggestions always require human review — never auto-applied.
    """

    def __init__(self) -> None:
        self._suggestions: dict[str, WeightSuggestion] = {}

    def generate_suggestions(
        self,
        calibration: CalibrationReport,
        postmortem_store: PostmortemStore,
        current_weights: dict[str, float],
    ) -> list[WeightSuggestion]:
        """
        Rules:
        1. If brier_score > 0.25 AND overall_bias > 0.10 → suggest RECALIBRATE_POS_PRIOR
        2. For each ErrorCategory with count > 3 and fraction > 0.30 of total errors:
           - COMPETITION_ERROR → suggest INCREASE_DOMAIN_WEIGHT for "competition" (+0.05, capped at 0.20)
           - SCIENCE_ERROR → suggest INCREASE_DOMAIN_WEIGHT for "science" (+0.05, capped at 0.25)
           - FINANCING_ERROR → suggest INCREASE_DOMAIN_WEIGHT for "financing" (+0.05, capped at 0.20)
           - MARKET_DRIFT → suggest FLAG_FOR_REVIEW (no weight change)
        3. If any domain weight > 0.40 → suggest DECREASE_DOMAIN_WEIGHT (-0.05)
        All suggestions: requires_human_review=True.
        """
        new_suggestions: list[WeightSuggestion] = []

        # Rule 1: recalibrate POS prior
        if calibration.brier_score > 0.25 and calibration.overall_bias > 0.10:
            current_val = current_weights.get("pos_prior", 0.5)
            suggestion = WeightSuggestion(
                suggestion_id=str(uuid.uuid4()),
                suggestion_type=SuggestionType.RECALIBRATE_POS_PRIOR,
                domain="pos_prior",
                current_value=current_val,
                suggested_value=current_val - 0.05,
                rationale=(
                    f"Brier score {calibration.brier_score:.3f} > 0.25 and "
                    f"overall bias {calibration.overall_bias:.3f} > 0.10 indicates "
                    "model is overconfident."
                ),
                supporting_evidence=(
                    f"brier_score={calibration.brier_score:.3f}, "
                    f"overall_bias={calibration.overall_bias:.3f}"
                ),
                requires_human_review=True,
                status=PromotionStatus.PENDING_REVIEW,
                created_at=datetime.now(timezone.utc),
            )
            new_suggestions.append(suggestion)
            self._suggestions[suggestion.suggestion_id] = suggestion

        # Rule 2: domain weight adjustments based on error distribution
        dist = postmortem_store.error_distribution()
        total_errors = sum(dist.values())

        # Domain caps
        domain_caps = {
            "competition": 0.20,
            "science": 0.25,
            "financing": 0.20,
        }
        domain_category_map = {
            ErrorCategory.COMPETITION_ERROR: "competition",
            ErrorCategory.SCIENCE_ERROR: "science",
            ErrorCategory.FINANCING_ERROR: "financing",
        }

        for error_category, domain in domain_category_map.items():
            count = dist.get(error_category.value, 0)
            if total_errors > 0 and count > 3 and (count / total_errors) > 0.30:
                current_val = current_weights.get(domain, 0.10)
                cap = domain_caps[domain]
                suggested_val = min(current_val + 0.05, cap)

                suggestion = WeightSuggestion(
                    suggestion_id=str(uuid.uuid4()),
                    suggestion_type=SuggestionType.INCREASE_DOMAIN_WEIGHT,
                    domain=domain,
                    current_value=current_val,
                    suggested_value=suggested_val,
                    rationale=(
                        f"{error_category.value} in {count}/{total_errors} errors "
                        f"({count/total_errors:.0%}). Increase {domain} domain weight."
                    ),
                    supporting_evidence=(
                        f"{error_category.value} in {count/total_errors:.0%} of "
                        "INCORRECT outcomes"
                    ),
                    requires_human_review=True,
                    status=PromotionStatus.PENDING_REVIEW,
                    created_at=datetime.now(timezone.utc),
                )
                new_suggestions.append(suggestion)
                self._suggestions[suggestion.suggestion_id] = suggestion

        # MARKET_DRIFT → FLAG_FOR_REVIEW
        drift_count = dist.get(ErrorCategory.MARKET_DRIFT.value, 0)
        if total_errors > 0 and drift_count > 3 and (drift_count / total_errors) > 0.30:
            current_val = current_weights.get("market_drift", 0.0)
            suggestion = WeightSuggestion(
                suggestion_id=str(uuid.uuid4()),
                suggestion_type=SuggestionType.FLAG_FOR_REVIEW,
                domain="market_drift",
                current_value=current_val,
                suggested_value=current_val,
                rationale=(
                    f"market_drift in {drift_count}/{total_errors} errors "
                    f"({drift_count/total_errors:.0%}). Review macro/sentiment factors."
                ),
                supporting_evidence=(
                    f"market_drift in {drift_count/total_errors:.0%} of outcomes"
                ),
                requires_human_review=True,
                status=PromotionStatus.PENDING_REVIEW,
                created_at=datetime.now(timezone.utc),
            )
            new_suggestions.append(suggestion)
            self._suggestions[suggestion.suggestion_id] = suggestion

        # Rule 3: decrease any domain weight > 0.40
        for domain, weight in current_weights.items():
            if weight > 0.40:
                suggested_val = weight - 0.05
                suggestion = WeightSuggestion(
                    suggestion_id=str(uuid.uuid4()),
                    suggestion_type=SuggestionType.DECREASE_DOMAIN_WEIGHT,
                    domain=domain,
                    current_value=weight,
                    suggested_value=suggested_val,
                    rationale=(
                        f"Domain '{domain}' weight {weight:.2f} > 0.40. "
                        "Reduce to prevent over-reliance on single signal."
                    ),
                    supporting_evidence=f"current weight={weight:.2f} exceeds 0.40 threshold",
                    requires_human_review=True,
                    status=PromotionStatus.PENDING_REVIEW,
                    created_at=datetime.now(timezone.utc),
                )
                new_suggestions.append(suggestion)
                self._suggestions[suggestion.suggestion_id] = suggestion

        return new_suggestions

    def pending(self) -> list[WeightSuggestion]:
        """Return all suggestions with PENDING_REVIEW status."""
        return [
            s for s in self._suggestions.values()
            if s.status == PromotionStatus.PENDING_REVIEW
        ]

    def approve(self, suggestion_id: str, reviewer_note: str = "") -> None:
        """Approve a suggestion."""
        suggestion = self._suggestions.get(suggestion_id)
        if suggestion is None:
            raise ValueError(f"No suggestion found with id='{suggestion_id}'")
        suggestion.status = PromotionStatus.APPROVED
        suggestion.reviewed_at = datetime.now(timezone.utc)
        suggestion.reviewer_note = reviewer_note

    def veto(self, suggestion_id: str, reviewer_note: str = "") -> None:
        """Veto a suggestion."""
        suggestion = self._suggestions.get(suggestion_id)
        if suggestion is None:
            raise ValueError(f"No suggestion found with id='{suggestion_id}'")
        suggestion.status = PromotionStatus.VETOED
        suggestion.reviewed_at = datetime.now(timezone.utc)
        suggestion.reviewer_note = reviewer_note

    def expire(self, suggestion_id: str) -> None:
        """Mark a suggestion as expired."""
        suggestion = self._suggestions.get(suggestion_id)
        if suggestion is None:
            raise ValueError(f"No suggestion found with id='{suggestion_id}'")
        suggestion.status = PromotionStatus.EXPIRED

    def all_suggestions(self) -> list[WeightSuggestion]:
        """Return all suggestions."""
        return list(self._suggestions.values())
