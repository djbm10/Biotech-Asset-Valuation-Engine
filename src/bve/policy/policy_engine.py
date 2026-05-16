"""Policy engine — maps model scores to allowed actions and blocked reasons."""

from __future__ import annotations

from dataclasses import dataclass, field

from .decision_policy import (
    BDPolicy,
    DecisionPolicy,
    HedgeFundPolicy,
    PolicyAction,
    VCPolicy,
)


@dataclass
class DecisionRecommendation:
    """Output of the policy engine for one asset / policy combination."""

    policy_name: str
    allowed_action: PolicyAction
    blocked_reasons: list[str] = field(default_factory=list)
    required_next_steps: list[str] = field(default_factory=list)
    score: float | None = None

    @property
    def is_actionable(self) -> bool:
        return self.allowed_action not in (PolicyAction.MONITOR, PolicyAction.NO_TRADE, PolicyAction.PASS)

    def describe(self) -> str:
        lines = [f"Policy: {self.policy_name}"]
        lines.append(f"  Action: {self.allowed_action.value}")
        if self.blocked_reasons:
            lines.append("  Blocked by:")
            for r in self.blocked_reasons:
                lines.append(f"    - {r}")
        if self.required_next_steps:
            lines.append("  Required next steps:")
            for s in self.required_next_steps:
                lines.append(f"    - {s}")
        return "\n".join(lines)


@dataclass
class ModelScores:
    """Normalised scores passed into the policy engine."""

    composite_score: float = 0.0
    asset_quality_score: float = 0.0
    strategic_fit_score: float = 0.0
    seller_willingness_score: float = 0.0
    expected_return: float = 0.0
    downside_floor_exists: bool = False
    liquidity_usd: float = 0.0
    catalyst_days_away: int | None = None
    biology_score: float = 0.0
    capital_to_poc_usd: float = 0.0
    exit_buyer_count: int = 0
    has_platform_optionality: bool = False


class DecisionPolicyEngine:
    """Evaluates model output against configured policies."""

    def evaluate_bd(self, scores: ModelScores, policy: BDPolicy) -> DecisionRecommendation:
        blocked = []
        next_steps = []

        if scores.asset_quality_score < policy.require_asset_quality_min:
            blocked.append(
                f"asset quality {scores.asset_quality_score:.2f} < min {policy.require_asset_quality_min}"
            )
        if scores.strategic_fit_score < policy.require_strategic_fit_min:
            blocked.append(
                f"strategic fit {scores.strategic_fit_score:.2f} < min {policy.require_strategic_fit_min}"
            )
        if scores.seller_willingness_score < policy.require_seller_willingness_min:
            blocked.append(
                f"seller willingness {scores.seller_willingness_score:.2f} < min {policy.require_seller_willingness_min}"
            )

        if blocked:
            action = PolicyAction.MONITOR
        elif scores.composite_score >= policy.active_pursuit_min_score:
            action = PolicyAction.ACTIVE_PURSUIT
            next_steps.append("Prepare diligence memo")
            next_steps.append("Initiate NDA / CDA conversation")
        elif scores.composite_score >= 0.55:
            action = PolicyAction.RELATIONSHIP_BUILD
            next_steps.append("Schedule management meeting")
        else:
            action = PolicyAction.MONITOR

        return DecisionRecommendation(
            policy_name=policy.name,
            allowed_action=action,
            blocked_reasons=blocked,
            required_next_steps=next_steps,
            score=scores.composite_score,
        )

    def evaluate_hf(self, scores: ModelScores, policy: HedgeFundPolicy) -> DecisionRecommendation:
        blocked = []
        next_steps = []

        if scores.expected_return < policy.require_expected_return_min:
            blocked.append(
                f"expected return {scores.expected_return:.1%} < min {policy.require_expected_return_min:.1%}"
            )
        if scores.liquidity_usd < policy.require_liquidity_min_usd:
            blocked.append(
                f"liquidity ${scores.liquidity_usd:,.0f} < min ${policy.require_liquidity_min_usd:,.0f}"
            )
        if policy.require_downside_floor and not scores.downside_floor_exists:
            blocked.append("no identifiable downside floor")
        if (
            policy.catalyst_horizon_max_days > 0
            and scores.catalyst_days_away is not None
            and scores.catalyst_days_away > policy.catalyst_horizon_max_days
        ):
            blocked.append(
                f"catalyst too far away: {scores.catalyst_days_away}d > max {policy.catalyst_horizon_max_days}d"
            )

        if blocked:
            action = PolicyAction.NO_TRADE
        elif scores.expected_return >= policy.require_expected_return_min * 1.5:
            action = PolicyAction.ADD_TO_POSITION
            next_steps.append(f"Size within {policy.max_position_size_pct_nav:.1f}% NAV limit")
        else:
            action = PolicyAction.INITIATE_POSITION
            next_steps.append(f"Size within {policy.max_position_size_pct_nav:.1f}% NAV limit")

        return DecisionRecommendation(
            policy_name=policy.name,
            allowed_action=action,
            blocked_reasons=blocked,
            required_next_steps=next_steps,
            score=scores.expected_return,
        )

    def evaluate_vc(self, scores: ModelScores, policy: VCPolicy) -> DecisionRecommendation:
        blocked = []
        next_steps = []

        if scores.biology_score < policy.require_biology_score_min:
            blocked.append(
                f"biology score {scores.biology_score:.2f} < min {policy.require_biology_score_min}"
            )
        if scores.capital_to_poc_usd > policy.require_capital_to_poc_under:
            blocked.append(
                f"capital to PoC ${scores.capital_to_poc_usd/1e6:.0f}M > limit ${policy.require_capital_to_poc_under/1e6:.0f}M"
            )
        if scores.exit_buyer_count < policy.require_exit_universe_min_buyers:
            blocked.append(
                f"exit buyer universe {scores.exit_buyer_count} < min {policy.require_exit_universe_min_buyers}"
            )
        if policy.require_platform_optionality and not scores.has_platform_optionality:
            blocked.append("no platform optionality identified")

        if blocked:
            action = PolicyAction.PASS
        else:
            action = PolicyAction.DILIGENCE_REQUIRED
            next_steps.append("Request data room access")
            next_steps.append("Commission independent biology review")

        return DecisionRecommendation(
            policy_name=policy.name,
            allowed_action=action,
            blocked_reasons=blocked,
            required_next_steps=next_steps,
            score=scores.biology_score,
        )

    def evaluate_all(
        self, scores: ModelScores, policy: DecisionPolicy
    ) -> dict[str, DecisionRecommendation]:
        return {
            "bd": self.evaluate_bd(scores, policy.bd),
            "hedge_fund": self.evaluate_hf(scores, policy.hedge_fund),
            "vc": self.evaluate_vc(scores, policy.vc),
        }
