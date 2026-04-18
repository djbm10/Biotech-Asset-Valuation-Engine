"""Promote validated weight updates to active parameter versions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

from bve.learning.shadow_backtest import ShadowBacktestResult
from bve.learning.weight_updates import WeightUpdate, WeightUpdateEngine
from bve.persistence.gap_fill_store import ParameterVersion


class PromotionResult(BaseModel):
    update_id: str
    promoted: bool
    reason: str
    new_version_id: Optional[str] = None
    promoted_at: Optional[datetime] = None


class WeightPromoter:
    """
    Promote approved weight updates that have passed shadow backtest.

    Safety rule: requires_human_review=True updates are never auto-promoted.
    Only updates with approved=True and requires_human_review=False are eligible.
    """

    def __init__(self, update_engine: Optional[WeightUpdateEngine] = None) -> None:
        self._update_engine = update_engine or WeightUpdateEngine()

    def promote(
        self,
        update: WeightUpdate,
        backtest_result: ShadowBacktestResult,
    ) -> PromotionResult:
        """
        Promote update to a ParameterVersion if:
        1. update.approved == True
        2. update.requires_human_review == False
        3. backtest_result.passed == True

        Returns a PromotionResult. Does not write to any store (caller's responsibility).
        Returns ParameterVersion as result.new_version_id (a uuid string).
        """
        if not update.approved:
            return PromotionResult(
                update_id=update.update_id,
                promoted=False,
                reason="Update has not been approved.",
            )

        if update.requires_human_review:
            return PromotionResult(
                update_id=update.update_id,
                promoted=False,
                reason="Update requires human review before promotion.",
            )

        if not backtest_result.passed:
            return PromotionResult(
                update_id=update.update_id,
                promoted=False,
                reason=f"Shadow backtest did not pass (recommendation={backtest_result.recommendation}).",
            )

        pv = self.build_parameter_version(update)
        promoted_at = datetime.now(timezone.utc)
        return PromotionResult(
            update_id=update.update_id,
            promoted=True,
            reason="All gates passed; update promoted to active parameter version.",
            new_version_id=pv.version_id,
            promoted_at=promoted_at,
        )

    def build_parameter_version(
        self,
        update: WeightUpdate,
    ) -> ParameterVersion:
        """Build a ParameterVersion from an approved WeightUpdate."""
        return ParameterVersion(
            module=update.module,
            description=f"Promoted from update {update.update_id}: {update.rationale}",
            parameters={update.parameter_name: update.new_value},
            is_active=True,
            promoted_from_backtest=True,
        )
