"""Phase L portfolio-aware decision and sizing engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from bve.intelligence.catalyst_payoff_trees import (
    CatalystPayoffTreeAssessment,
    CatalystPayoffTreeValue,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PortfolioDecisionModuleOutput(BaseModel):
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[str] = Field(default_factory=list)
    freshness: datetime
    explainability: str
    downstream_dependencies: list[str] = Field(default_factory=list)


class PortfolioContextSnapshot(BaseModel):
    portfolio_snapshot_id: str
    snapshot_at: datetime
    current_gross_exposure_pct: float = Field(ge=0.0, le=1.5)
    current_net_exposure_pct: float = Field(ge=-1.0, le=1.5)
    therapeutic_area_exposure_pct: float = Field(ge=0.0, le=1.0, default=0.0)
    modality_exposure_pct: float = Field(ge=0.0, le=1.0, default=0.0)
    catalyst_cluster_exposure_pct: float = Field(ge=0.0, le=1.0, default=0.0)
    factor_sensitivity_score: float = Field(ge=0.0, le=1.0, default=0.0)
    liquidity_score: float = Field(ge=0.0, le=1.0, default=1.0)
    outcome_correlation_score: float = Field(ge=0.0, le=1.0, default=0.0)
    crowding_score: float = Field(ge=0.0, le=1.0, default=0.0)
    gross_risk_budget_pct: float = Field(ge=0.0, le=1.5, default=1.0)
    net_risk_budget_pct: float = Field(ge=0.0, le=1.5, default=1.0)
    current_position_pct: float = Field(ge=0.0, le=1.0, default=0.0)


class PortfolioDecisionPolicy(BaseModel):
    policy_version: str = "phase-l-v1"
    max_single_position_pct: float = Field(ge=0.0, le=1.0, default=0.10)
    max_event_position_pct: float = Field(ge=0.0, le=1.0, default=0.07)
    max_loss_budget_pct: float = Field(ge=0.0, le=1.0, default=0.02)
    therapeutic_area_soft_limit_pct: float = Field(ge=0.0, le=1.0, default=0.25)
    modality_soft_limit_pct: float = Field(ge=0.0, le=1.0, default=0.25)
    catalyst_cluster_soft_limit_pct: float = Field(ge=0.0, le=1.0, default=0.20)
    crowding_limit_score: float = Field(ge=0.0, le=1.0, default=0.70)
    correlation_limit_score: float = Field(ge=0.0, le=1.0, default=0.70)
    liquidity_floor_score: float = Field(ge=0.0, le=1.0, default=0.35)


class PortfolioDecisionValue(BaseModel):
    asset_id: str
    ticker: Optional[str] = None
    target_position_pct: float = Field(ge=0.0)
    current_position_pct: float = Field(ge=0.0)
    add_reduce_pct: float
    event_cap_pct: float = Field(ge=0.0)
    max_loss_budget_pct: float = Field(ge=0.0)
    scenario_weighted_exposure_pct: float = Field(ge=0.0)
    watchlist_priority_score: float = Field(ge=0.0, le=1.0)
    recommended_action: str
    concentration_penalty: float = Field(ge=0.0, le=1.0)
    liquidity_penalty: float = Field(ge=0.0, le=1.0)
    correlation_penalty: float = Field(ge=0.0, le=1.0)
    crowding_penalty: float = Field(ge=0.0, le=1.0)
    risk_budget_utilization: float = Field(ge=0.0, le=2.0)
    rationale_flags: list[str] = Field(default_factory=list)


class PortfolioDecisionAssessment(BaseModel):
    asset_id: str
    output: PortfolioDecisionModuleOutput
    plain_english_summary: str


class PortfolioDecisionEngine:
    """Translate payoff trees into portfolio-aware target sizing."""

    def build(
        self,
        *,
        asset_id: str,
        ticker: Optional[str],
        payoff_tree: CatalystPayoffTreeAssessment,
        portfolio_context: PortfolioContextSnapshot,
        policy: Optional[PortfolioDecisionPolicy] = None,
        freshness: Optional[datetime] = None,
    ) -> PortfolioDecisionAssessment:
        policy = policy or PortfolioDecisionPolicy()
        freshness = freshness or portfolio_context.snapshot_at or _utcnow()
        payoff_value = CatalystPayoffTreeValue.model_validate(payoff_tree.output.value)

        event_cap = self._event_cap(policy, portfolio_context)
        concentration_penalty = self._concentration_penalty(policy, portfolio_context)
        liquidity_penalty = self._liquidity_penalty(policy, portfolio_context)
        correlation_penalty = self._bounded_penalty(
            portfolio_context.outcome_correlation_score,
            policy.correlation_limit_score,
        )
        crowding_penalty = self._bounded_penalty(
            portfolio_context.crowding_score,
            policy.crowding_limit_score,
        )
        risk_budget_utilization = self._risk_budget_utilization(portfolio_context)

        base_target = min(
            payoff_value.recommended_pre_event_size_pct,
            policy.max_single_position_pct,
            event_cap,
        )
        adjustment_multiplier = max(
            0.0,
            1.0
            - (0.35 * concentration_penalty)
            - (0.25 * liquidity_penalty)
            - (0.20 * correlation_penalty)
            - (0.20 * crowding_penalty),
        )
        budget_multiplier = max(0.0, min(1.0, 1.15 - risk_budget_utilization))
        target_position = round(base_target * adjustment_multiplier * budget_multiplier, 4)

        downside_tail = self._downside_tail(payoff_value)
        max_loss_budget = round(
            min(policy.max_loss_budget_pct, max(target_position * downside_tail, 0.0)),
            4,
        )
        scenario_weighted_exposure = round(target_position * (1.0 - payoff_value.downside_skew), 4)
        watchlist_priority = round(
            min(
                1.0,
                max(
                    0.0,
                    (payoff_value.sharpe_like_setup_score + 1.0) / 2.0
                    + max(payoff_value.expected_return_pct, 0.0) / 100.0
                    - 0.20 * concentration_penalty
                    - 0.15 * correlation_penalty
                    - 0.15 * crowding_penalty,
                ),
            ),
            4,
        )
        delta = round(target_position - portfolio_context.current_position_pct, 4)
        action = self._action(delta, target_position, portfolio_context.current_position_pct)
        flags = self._flags(
            policy=policy,
            context=portfolio_context,
            event_cap=event_cap,
            concentration_penalty=concentration_penalty,
            liquidity_penalty=liquidity_penalty,
            correlation_penalty=correlation_penalty,
            crowding_penalty=crowding_penalty,
        )

        value = PortfolioDecisionValue(
            asset_id=asset_id,
            ticker=ticker,
            target_position_pct=target_position,
            current_position_pct=portfolio_context.current_position_pct,
            add_reduce_pct=delta,
            event_cap_pct=round(event_cap, 4),
            max_loss_budget_pct=max_loss_budget,
            scenario_weighted_exposure_pct=scenario_weighted_exposure,
            watchlist_priority_score=watchlist_priority,
            recommended_action=action,
            concentration_penalty=round(concentration_penalty, 4),
            liquidity_penalty=round(liquidity_penalty, 4),
            correlation_penalty=round(correlation_penalty, 4),
            crowding_penalty=round(crowding_penalty, 4),
            risk_budget_utilization=round(risk_budget_utilization, 4),
            rationale_flags=flags,
        )
        output = PortfolioDecisionModuleOutput(
            value=value.model_dump(),
            confidence=self._confidence(payoff_tree, portfolio_context, flags),
            provenance=[
                f"portfolio_snapshot:{portfolio_context.portfolio_snapshot_id}",
                f"policy:{policy.policy_version}",
                *payoff_tree.output.provenance,
            ],
            freshness=freshness,
            explainability=(
                "Portfolio decisioning starts from catalyst payoff-tree sizing, then discounts or caps "
                "the target for concentration, liquidity, correlation, crowding, and remaining risk budget."
            ),
            downstream_dependencies=["continuous_monitoring", "calibration_feedback_loop"],
        )
        summary = (
            f"{asset_id} target {target_position:.1%} vs current {portfolio_context.current_position_pct:.1%}; "
            f"action {action}, event cap {event_cap:.1%}, watchlist priority {watchlist_priority:.2f}."
        )
        return PortfolioDecisionAssessment(
            asset_id=asset_id,
            output=output,
            plain_english_summary=summary,
        )

    @staticmethod
    def _bounded_penalty(value: float, threshold: float) -> float:
        if value <= threshold:
            return 0.0
        return min(1.0, (value - threshold) / max(1.0 - threshold, 1e-6))

    def _concentration_penalty(
        self,
        policy: PortfolioDecisionPolicy,
        context: PortfolioContextSnapshot,
    ) -> float:
        ta = self._bounded_penalty(
            context.therapeutic_area_exposure_pct,
            policy.therapeutic_area_soft_limit_pct,
        )
        modality = self._bounded_penalty(
            context.modality_exposure_pct,
            policy.modality_soft_limit_pct,
        )
        catalyst = self._bounded_penalty(
            context.catalyst_cluster_exposure_pct,
            policy.catalyst_cluster_soft_limit_pct,
        )
        return max(ta, modality, catalyst)

    def _liquidity_penalty(
        self,
        policy: PortfolioDecisionPolicy,
        context: PortfolioContextSnapshot,
    ) -> float:
        if context.liquidity_score >= policy.liquidity_floor_score:
            return 0.0
        return min(1.0, (policy.liquidity_floor_score - context.liquidity_score) / max(policy.liquidity_floor_score, 1e-6))

    @staticmethod
    def _risk_budget_utilization(context: PortfolioContextSnapshot) -> float:
        gross = (
            context.current_gross_exposure_pct / max(context.gross_risk_budget_pct, 1e-6)
            if context.gross_risk_budget_pct > 0
            else 1.0
        )
        net = (
            abs(context.current_net_exposure_pct) / max(context.net_risk_budget_pct, 1e-6)
            if context.net_risk_budget_pct > 0
            else 1.0
        )
        return max(gross, net)

    @staticmethod
    def _downside_tail(payoff_value: CatalystPayoffTreeValue) -> float:
        return min(
            1.0,
            sum(
                item.probability * abs(min(item.price_move_pct, 0.0)) / 100.0
                for item in payoff_value.scenarios
            ),
        )

    @staticmethod
    def _event_cap(policy: PortfolioDecisionPolicy, context: PortfolioContextSnapshot) -> float:
        cap = policy.max_event_position_pct
        if context.crowding_score > 0.5:
            cap *= 1.0 - min(0.35, (context.crowding_score - 0.5) * 0.5)
        if context.outcome_correlation_score > 0.5:
            cap *= 1.0 - min(0.30, (context.outcome_correlation_score - 0.5) * 0.4)
        return max(0.0, min(policy.max_single_position_pct, cap))

    @staticmethod
    def _action(delta: float, target: float, current: float) -> str:
        if target <= 0.0 and current > 0.0:
            return "exit"
        if delta >= 0.01:
            return "buy" if current <= 0.0 else "add"
        if delta <= -0.01:
            return "reduce"
        return "hold" if current > 0.0 else "monitor"

    @staticmethod
    def _flags(
        *,
        policy: PortfolioDecisionPolicy,
        context: PortfolioContextSnapshot,
        event_cap: float,
        concentration_penalty: float,
        liquidity_penalty: float,
        correlation_penalty: float,
        crowding_penalty: float,
    ) -> list[str]:
        flags: list[str] = []
        if concentration_penalty > 0:
            flags.append("concentration limit pressure")
        if liquidity_penalty > 0:
            flags.append("liquidity cap applied")
        if correlation_penalty > 0:
            flags.append("outcome correlation penalty")
        if crowding_penalty > 0:
            flags.append("crowding penalty")
        if event_cap < policy.max_event_position_pct:
            flags.append("event cap tightened by portfolio context")
        if context.current_gross_exposure_pct >= context.gross_risk_budget_pct:
            flags.append("gross risk budget full")
        return flags

    @staticmethod
    def _confidence(
        payoff_tree: CatalystPayoffTreeAssessment,
        context: PortfolioContextSnapshot,
        flags: list[str],
    ) -> float:
        confidence = 0.60
        confidence += 0.20 * payoff_tree.output.confidence
        if context.portfolio_snapshot_id:
            confidence += 0.05
        if context.liquidity_score >= 0.5:
            confidence += 0.05
        confidence -= min(0.10, len(flags) * 0.02)
        return round(max(0.45, min(0.95, confidence)), 4)
