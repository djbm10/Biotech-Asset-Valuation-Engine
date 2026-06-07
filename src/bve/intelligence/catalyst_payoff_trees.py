"""Phase K catalyst payoff tree engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from bve.intelligence.financing_engine import FinancingAssessment, FinancingAssessmentValue
from bve.intelligence.market_expectations import (
    MarketExpectationComparison,
    MarketExpectationComparisonValue,
)
from bve.intelligence.variant_view_engine import VariantViewAssessment, VariantViewValue
from bve.models.catalyst_model import CatalystValuation


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CatalystPayoffModuleOutput(BaseModel):
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[str] = Field(default_factory=list)
    freshness: datetime
    explainability: str
    downstream_dependencies: list[str] = Field(default_factory=list)


class CatalystScenario(BaseModel):
    name: str
    probability: float = Field(ge=0.0, le=1.0)
    price_move_pct: float
    post_event_financing_state: str
    post_event_valuation_regime: str
    thesis_status: str
    next_catalyst: Optional[str] = None


class CatalystPayoffTreeValue(BaseModel):
    asset_id: str
    event_type: str
    scenarios: list[CatalystScenario] = Field(default_factory=list)
    expected_return_pct: float
    downside_skew: float = Field(ge=0.0)
    sharpe_like_setup_score: float
    recommended_pre_event_size_pct: float = Field(ge=0.0)
    recommended_post_event_action_logic: str


class CatalystPayoffTreeAssessment(BaseModel):
    asset_id: str
    output: CatalystPayoffModuleOutput
    plain_english_summary: str


class CatalystPayoffTreeEngine:
    """Build event payoff trees from calibrated catalyst priors plus financing and variant context."""

    def build(
        self,
        *,
        asset_id: str,
        catalyst_valuation: CatalystValuation,
        financing_assessment: Optional[FinancingAssessment] = None,
        market_expectation: Optional[MarketExpectationComparison] = None,
        variant_view: Optional[VariantViewAssessment] = None,
        freshness: Optional[datetime] = None,
    ) -> CatalystPayoffTreeAssessment:
        freshness = freshness or _utcnow()
        financing = (
            FinancingAssessmentValue.model_validate(financing_assessment.output.value)
            if financing_assessment is not None
            else None
        )
        market_value = (
            MarketExpectationComparisonValue.model_validate(market_expectation.output.value)
            if market_expectation is not None
            else None
        )
        variant_value = (
            VariantViewValue.model_validate(variant_view.output.value)
            if variant_view is not None
            else None
        )

        scenarios = self._build_scenarios(
            catalyst_valuation=catalyst_valuation,
            financing=financing,
            market_value=market_value,
            variant_value=variant_value,
        )
        expected_return = round(sum(item.probability * item.price_move_pct for item in scenarios), 4)
        negative_tail = sum(
            item.probability * abs(min(0.0, item.price_move_pct))
            for item in scenarios
        )
        positive_tail = sum(
            item.probability * max(0.0, item.price_move_pct)
            for item in scenarios
        )
        downside_skew = round(
            negative_tail / max(positive_tail + negative_tail, 1e-6),
            4,
        )
        expected_abs_move = sum(item.probability * abs(item.price_move_pct) for item in scenarios)
        sharpe_like = round(expected_return / max(expected_abs_move, 1e-6), 4)
        size_pct = round(
            max(
                0.0,
                min(
                    0.12,
                    (max(expected_return, 0.0) / 100.0)
                    * (1.0 - downside_skew)
                    * (1.0 - (financing.financing_risk_score if financing else 0.25)),
                ),
            ),
            4,
        )
        action_logic = self._post_event_action_logic(
            scenarios=scenarios,
            financing=financing,
            variant_value=variant_value,
        )
        value = CatalystPayoffTreeValue(
            asset_id=asset_id,
            event_type=catalyst_valuation.event_type,
            scenarios=scenarios,
            expected_return_pct=expected_return,
            downside_skew=downside_skew,
            sharpe_like_setup_score=sharpe_like,
            recommended_pre_event_size_pct=size_pct,
            recommended_post_event_action_logic=action_logic,
        )
        output = CatalystPayoffModuleOutput(
            value=value.model_dump(),
            confidence=self._confidence(catalyst_valuation, financing, variant_value),
            provenance=self._provenance(catalyst_valuation, financing_assessment, market_expectation, variant_view),
            freshness=freshness,
            explainability=(
                "Catalyst payoff trees expand each event into scenario probabilities, price moves, "
                "post-event financing state, valuation regime, thesis status, and next-step action logic."
            ),
            downstream_dependencies=[
                "portfolio_decision_engine",
                "daily_scanner",
            ],
        )
        summary = (
            f"{asset_id} {catalyst_valuation.event_type} payoff tree: expected return "
            f"{value.expected_return_pct:+.1f}%, downside skew {value.downside_skew:.2f}, "
            f"pre-event size {value.recommended_pre_event_size_pct:.1%}."
        )
        return CatalystPayoffTreeAssessment(
            asset_id=asset_id,
            output=output,
            plain_english_summary=summary,
        )

    def _build_scenarios(
        self,
        *,
        catalyst_valuation: CatalystValuation,
        financing: Optional[FinancingAssessmentValue],
        market_value: Optional[MarketExpectationComparisonValue],
        variant_value: Optional[VariantViewValue],
    ) -> list[CatalystScenario]:
        p_positive = float(catalyst_valuation.design_adjusted_p_positive_outcome)
        pos_gap = market_value.pos_delta if market_value is not None and market_value.pos_delta is not None else 0.0
        financing_risk = financing.financing_risk_score if financing is not None else 0.25
        upside = float(catalyst_valuation.expected_move_magnitude_pct)
        positive_bias = min(1.0, max(0.0, p_positive + max(0.0, pos_gap) * 0.5))
        competitive_overshadow_prob = 0.06 + (0.04 if variant_value and len(variant_value.deltas) >= 3 else 0.0)

        clear_win = 0.45 * positive_bias
        mixed_fundable = 0.20 * p_positive
        delay = 0.12 + (0.10 * financing_risk)
        narrow_label = 0.10 + (0.08 * max(0.0, -pos_gap))
        fail = 0.20 * (1.0 - p_positive)
        crl = 0.08 * (1.0 - p_positive)
        safety_overhang = 0.05 + (0.03 if catalyst_valuation.event_type in {"trial_readout", "pdufa_decision"} else 0.0)
        competitive_overshadow = competitive_overshadow_prob
        raw = [
            ("clear_win", clear_win),
            ("mixed_but_fundable", mixed_fundable),
            ("delay", delay),
            ("narrow_label", narrow_label),
            ("fail", fail),
            ("crl", crl),
            ("safety_overhang", safety_overhang),
            ("competitive_overshadowing", competitive_overshadow),
        ]
        total = sum(prob for _, prob in raw)
        normalized = [(name, prob / total) for name, prob in raw]

        def scenario(name: str, prob: float) -> CatalystScenario:
            mapping = {
                "clear_win": (
                    upside * 1.35,
                    "funded",
                    "premium",
                    "confirmed",
                    "launch prep / label expansion",
                ),
                "mixed_but_fundable": (
                    upside * 0.55,
                    "funded",
                    "base_plus",
                    "partially_confirmed",
                    "follow-up dataset",
                ),
                "delay": (
                    -(upside * 0.35),
                    "needs_bridge" if financing_risk > 0.4 else "watch_runway",
                    "time_shifted",
                    "delayed",
                    "updated catalyst date",
                ),
                "narrow_label": (
                    upside * 0.15,
                    "watch_dilution",
                    "narrow_label",
                    "partially_confirmed",
                    "commercial execution",
                ),
                "fail": (
                    -(upside * 1.10),
                    "distressed",
                    "bear",
                    "broken",
                    "program triage",
                ),
                "crl": (
                    -(upside * 0.75),
                    "bridge_financing_likely",
                    "regulatory_reset",
                    "broken",
                    "resubmission plan",
                ),
                "safety_overhang": (
                    -(upside * 0.50),
                    "higher_cash_burn",
                    "risk_reset",
                    "challenged",
                    "safety follow-up",
                ),
                "competitive_overshadowing": (
                    -(upside * 0.22),
                    "unchanged",
                    "crowded",
                    "unchanged",
                    "relative-positioning update",
                ),
            }
            move, financing_state, regime, thesis_status, next_cat = mapping[name]
            return CatalystScenario(
                name=name,
                probability=round(prob, 4),
                price_move_pct=round(move, 4),
                post_event_financing_state=financing_state,
                post_event_valuation_regime=regime,
                thesis_status=thesis_status,
                next_catalyst=next_cat,
            )

        return [scenario(name, prob) for name, prob in normalized]

    @staticmethod
    def _post_event_action_logic(
        *,
        scenarios: list[CatalystScenario],
        financing: Optional[FinancingAssessmentValue],
        variant_value: Optional[VariantViewValue],
    ) -> str:
        clear_win = next((item for item in scenarios if item.name == "clear_win"), None)
        fail = next((item for item in scenarios if item.name == "fail"), None)
        if clear_win and clear_win.probability >= 0.25 and financing and financing.financing_risk_score < 0.5:
            base = "Add on a clear win if financing risk remains contained."
        else:
            base = "Keep size moderate pre-event and wait for confirmation before adding."
        if fail and fail.price_move_pct <= -20:
            base += " Cut immediately on a fail or CRL outcome."
        if variant_value and variant_value.deltas:
            base += f" Re-underwrite the thesis against the top delta: {variant_value.deltas[0].dimension}."
        return base

    @staticmethod
    def _confidence(
        catalyst_valuation: CatalystValuation,
        financing: Optional[FinancingAssessmentValue],
        variant_value: Optional[VariantViewValue],
    ) -> float:
        confidence = 0.55
        if catalyst_valuation.profile_source == "calibrated":
            confidence += 0.15
        if financing is not None:
            confidence += 0.10
        if variant_value is not None and variant_value.deltas:
            confidence += 0.10
        return round(min(0.95, confidence), 4)

    @staticmethod
    def _provenance(
        catalyst_valuation: CatalystValuation,
        financing_assessment: Optional[FinancingAssessment],
        market_expectation: Optional[MarketExpectationComparison],
        variant_view: Optional[VariantViewAssessment],
    ) -> list[str]:
        provenance = [f"catalyst:{catalyst_valuation.event_key}", "catalyst_model"]
        if financing_assessment is not None:
            provenance.extend(financing_assessment.output.provenance)
        if market_expectation is not None:
            provenance.extend(market_expectation.output.provenance)
        if variant_view is not None:
            provenance.extend(variant_view.output.provenance)
        return provenance
