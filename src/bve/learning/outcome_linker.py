"""Link decisions to realized outcomes and classify attribution."""

from __future__ import annotations

from datetime import date
from typing import Optional

from bve.persistence.gap_fill_store import DecisionRecord, OutcomeRecord


class OutcomeLinker:
    """
    Given a decision and its realized return, classify attribution and build OutcomeRecord.

    Attribution taxonomy:
    - "confirmed_thesis"  — catalyst triggered AND return > 0
    - "pos_error"         — negative catalyst event AND return > 0
    - "timing_error"      — positive catalyst event AND return <= 0
    - "thesis_error"      — no catalyst AND return <= 0
    - "market_drift"      — no catalyst AND return > 0
    - "unclassified"      — default
    """

    def link(
        self,
        decision: DecisionRecord,
        outcome_date: date,
        return_realized_pct: float,
        *,
        catalyst_triggered: bool = False,
        catalyst_description: Optional[str] = None,
        thesis_confirmed: Optional[bool] = None,
    ) -> OutcomeRecord:
        """Build and return an OutcomeRecord with computed attribution."""
        attribution = self._classify(
            return_realized_pct=return_realized_pct,
            catalyst_triggered=catalyst_triggered,
            thesis_confirmed=thesis_confirmed,
        )
        decision_date = (
            decision.decision_date.date()
            if hasattr(decision.decision_date, "date")
            else decision.decision_date
        )
        return OutcomeRecord(
            decision_id=decision.decision_id,
            asset_id=decision.asset_id,
            ticker=decision.ticker,
            decision_date=decision_date,
            outcome_date=outcome_date,
            return_realized_pct=return_realized_pct,
            catalyst_triggered=catalyst_triggered,
            catalyst_description=catalyst_description,
            thesis_confirmed=thesis_confirmed,
            attribution=attribution,
        )

    def link_batch(
        self,
        decisions: list[DecisionRecord],
        returns_by_decision_id: dict[str, float],
        outcome_date: date,
    ) -> list[OutcomeRecord]:
        """
        Link a batch. Use returns_by_decision_id[decision.decision_id].
        Skip decisions not in the dict.
        """
        results: list[OutcomeRecord] = []
        for decision in decisions:
            if decision.decision_id not in returns_by_decision_id:
                continue
            return_pct = returns_by_decision_id[decision.decision_id]
            outcome = self.link(
                decision,
                outcome_date,
                return_pct,
            )
            results.append(outcome)
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify(
        return_realized_pct: float,
        catalyst_triggered: bool,
        thesis_confirmed: Optional[bool],
    ) -> str:
        positive_return = return_realized_pct > 0

        if catalyst_triggered:
            # thesis_confirmed=False means the catalyst was a negative/disappointing event
            if thesis_confirmed is False:
                # Negative catalyst event
                if positive_return:
                    return "pos_error"
                else:
                    return "timing_error"
            else:
                # Positive catalyst event (confirmed=True or None)
                if positive_return:
                    return "confirmed_thesis"
                else:
                    return "timing_error"

        # No catalyst triggered
        if positive_return:
            return "market_drift"
        else:
            return "thesis_error"
