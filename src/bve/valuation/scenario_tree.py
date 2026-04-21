"""Catalyst scenario trees — both the original multi-branch tree and the 6-outcome payoff tree."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ===========================================================================
# Original ScenarioTree (backward-compatible — do NOT remove)
# ===========================================================================

class ScenarioBranch(BaseModel):
    """One branch of a catalyst scenario tree."""
    branch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    label: str                      # "clear_success" / "mixed_efficacy" / "safety_overhang" /
                                    # "narrow_label" / "delay" / "failure" / "crl" / "financing_first"
    probability: float = Field(ge=0.0, le=1.0)
    equity_value_post_event_millions: Optional[float] = None
    expected_price_move_pct: float  # signed: positive = up
    iv_reaction: str = "compress"   # "compress" / "expand" / "neutral"
    post_event_thesis_state: str    # "confirmed" / "partial" / "broken" / "delayed"
    post_event_financing_state: str = "no_change"  # "no_need" / "bridge_needed" / "follow_on" / "distressed"
    likely_management_narrative: str = ""
    next_catalyst: Optional[str] = None
    confidence_interval_low_pct: Optional[float] = None   # 10th pct move
    confidence_interval_high_pct: Optional[float] = None  # 90th pct move


class ScenarioTree(BaseModel):
    """
    Full scenario tree for one catalyst event.

    Probabilities across branches must sum to ~1.0 (validated within 0.01 tolerance).
    """
    tree_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    ticker: str
    catalyst_label: str
    catalyst_date: date
    catalyst_type: str              # "phase3_readout" / "phase2_readout" / "fda_decision" /
                                    # "adcom" / "phase1_data" / "ira_negotiation" / "partnership"
    built_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    branches: list[ScenarioBranch] = Field(default_factory=list)
    # Aggregate metrics (computed)
    expected_return_pct: float = 0.0
    downside_severity_pct: float = 0.0     # probability-weighted downside
    upside_capture_pct: float = 0.0        # probability-weighted upside
    skew_ratio: float = 0.0                # |expected_upside| / |expected_downside|, >1 = favorable skew
    setup_score: float = Field(ge=0.0, le=1.0, default=0.5)
    recommended_pre_event_action: str = "hold"   # "add" / "hold" / "reduce" / "pass"
    model_version: str = "v1"

    def prob_sum(self) -> float:
        return sum(b.probability for b in self.branches)

    def is_valid(self) -> bool:
        return abs(self.prob_sum() - 1.0) <= 0.01

    def success_branches(self) -> list[ScenarioBranch]:
        return [b for b in self.branches if b.expected_price_move_pct > 0]

    def failure_branches(self) -> list[ScenarioBranch]:
        return [b for b in self.branches if b.expected_price_move_pct <= 0]


class ScenarioTreeBuilder:
    """
    Build a ScenarioTree from a catalyst specification.

    Default branches when not overridden:
    - Phase 3 oncology: clear_success 0.35, mixed 0.20, narrow_label 0.15,
                        safety_overhang 0.10, delay 0.10, failure 0.10
    - Phase 2:          clear_success 0.30, mixed 0.25, delay 0.20, failure 0.25
    - FDA decision:     approval 0.65, crl 0.20, delay 0.15
    """

    _DEFAULT_BRANCHES: dict[str, list[dict]] = {
        "phase3_readout": [
            {"label": "clear_success",    "probability": 0.35, "expected_price_move_pct":  0.60, "post_event_thesis_state": "confirmed",  "iv_reaction": "compress"},
            {"label": "mixed_efficacy",   "probability": 0.20, "expected_price_move_pct":  0.10, "post_event_thesis_state": "partial",    "iv_reaction": "expand"},
            {"label": "narrow_label",     "probability": 0.15, "expected_price_move_pct": -0.10, "post_event_thesis_state": "partial",    "iv_reaction": "expand"},
            {"label": "safety_overhang",  "probability": 0.10, "expected_price_move_pct": -0.30, "post_event_thesis_state": "broken",     "iv_reaction": "expand"},
            {"label": "delay",            "probability": 0.10, "expected_price_move_pct": -0.20, "post_event_thesis_state": "delayed",    "iv_reaction": "expand"},
            {"label": "failure",          "probability": 0.10, "expected_price_move_pct": -0.60, "post_event_thesis_state": "broken",     "iv_reaction": "expand"},
        ],
        "phase2_readout": [
            {"label": "clear_success",    "probability": 0.30, "expected_price_move_pct":  0.50, "post_event_thesis_state": "confirmed",  "iv_reaction": "compress"},
            {"label": "mixed_efficacy",   "probability": 0.25, "expected_price_move_pct":  0.05, "post_event_thesis_state": "partial",    "iv_reaction": "expand"},
            {"label": "delay",            "probability": 0.20, "expected_price_move_pct": -0.15, "post_event_thesis_state": "delayed",    "iv_reaction": "expand"},
            {"label": "failure",          "probability": 0.25, "expected_price_move_pct": -0.55, "post_event_thesis_state": "broken",     "iv_reaction": "expand"},
        ],
        "fda_decision": [
            {"label": "approval",         "probability": 0.65, "expected_price_move_pct":  0.25, "post_event_thesis_state": "confirmed",  "iv_reaction": "compress"},
            {"label": "crl",              "probability": 0.20, "expected_price_move_pct": -0.45, "post_event_thesis_state": "broken",     "iv_reaction": "expand"},
            {"label": "delay",            "probability": 0.15, "expected_price_move_pct": -0.15, "post_event_thesis_state": "delayed",    "iv_reaction": "expand"},
        ],
    }

    def build(
        self,
        *,
        asset_id: str,
        ticker: str,
        catalyst_label: str,
        catalyst_date: date,
        catalyst_type: str = "phase3_readout",
        branch_overrides: Optional[list[dict]] = None,
    ) -> ScenarioTree:
        raw_branches = branch_overrides or self._DEFAULT_BRANCHES.get(
            catalyst_type, self._DEFAULT_BRANCHES["phase3_readout"]
        )
        branches = [ScenarioBranch(**b, post_event_financing_state="no_change") for b in raw_branches]

        tree = ScenarioTree(
            asset_id=asset_id, ticker=ticker,
            catalyst_label=catalyst_label, catalyst_date=catalyst_date,
            catalyst_type=catalyst_type, branches=branches,
        )

        # Compute aggregate metrics
        expected_return = sum(b.probability * b.expected_price_move_pct for b in branches)
        downside = sum(b.probability * min(0.0, b.expected_price_move_pct) for b in branches)
        upside = sum(b.probability * max(0.0, b.expected_price_move_pct) for b in branches)
        abs_down = abs(downside)
        skew = round(upside / abs_down, 2) if abs_down > 0 else 0.0

        # Recommended action based on expected return and skew
        if expected_return > 0.10 and skew >= 1.2:
            action = "add"
        elif expected_return > 0.05:
            action = "hold"
        elif expected_return < -0.05:
            action = "reduce"
        else:
            action = "pass"

        # Setup score: normalize expected_return to 0-1 range (-0.5 to +0.5 maps to 0-1)
        setup = min(1.0, max(0.0, (expected_return + 0.5) / 1.0))

        return tree.model_copy(update={
            "expected_return_pct": round(expected_return, 4),
            "downside_severity_pct": round(downside, 4),
            "upside_capture_pct": round(upside, 4),
            "skew_ratio": skew,
            "recommended_pre_event_action": action,
            "setup_score": round(setup, 3),
        })


# ===========================================================================
# Step 9: CatalystPayoffTree — 6-outcome structured payoff tree
# ===========================================================================

class ScenarioOutcome(str, Enum):
    STRONG_POSITIVE = "strong_positive"   # e.g. clean Ph3 data, accelerated approval
    POSITIVE = "positive"                  # meets primary endpoint
    MIXED = "mixed"                        # mixed signals, partial hit
    NEUTRAL = "neutral"                    # inconclusive, no signal
    NEGATIVE = "negative"                  # misses endpoint
    STRONG_NEGATIVE = "strong_negative"    # CRL, safety halt, complete failure


_POSITIVE_OUTCOMES = {ScenarioOutcome.STRONG_POSITIVE, ScenarioOutcome.POSITIVE}
_NEGATIVE_OUTCOMES = {ScenarioOutcome.NEGATIVE, ScenarioOutcome.STRONG_NEGATIVE}


class CatalystScenario(BaseModel, frozen=True):
    outcome: ScenarioOutcome
    probability: float         # 0.0-1.0; all scenarios for a catalyst must sum to 1.0
    expected_return: float     # projected stock return (e.g. +0.60, -0.40)
    pos_revision: float        # how this outcome would shift model PoS (-0.30 to +0.20)
    rationale: str


def _compute_setup_score(skew_ratio: float, expected_return: float) -> float:
    skew_component = min(1.0, skew_ratio / 3.0)
    return_component = min(1.0, max(0.0, (expected_return + 0.20) / 0.60))
    return round(0.60 * skew_component + 0.40 * return_component, 6)


class CatalystPayoffTree(BaseModel, frozen=True):
    """
    6-scenario payoff distribution for a single catalyst event.
    Probabilities must sum to 1.0 (validated).
    """
    catalyst_id: str
    asset_id: str
    catalyst_description: str
    catalyst_date: str         # ISO date string, e.g. "2026-Q3"
    scenarios: list[CatalystScenario]  # must have exactly 6 (one per ScenarioOutcome)

    # Derived (auto-computed via model_validator):
    expected_return: float            # sum(prob × return) across scenarios
    expected_pos_revision: float      # sum(prob × pos_revision) across scenarios
    upside_capture: float             # sum of positive scenario probs × their returns
    downside_risk: float              # abs(sum of negative scenario probs × their returns)
    skew_ratio: float                 # upside_capture / (downside_risk + 1e-9)
    setup_score: float                # 0.0-1.0 composite: skew_ratio normalized + expected_return

    @model_validator(mode="before")
    @classmethod
    def validate_and_compute(cls, data: dict) -> dict:
        scenarios = data.get("scenarios", [])
        if scenarios:
            # Validate probabilities sum to 1.0 within 1e-6 tolerance
            prob_sum = sum(
                s.get("probability", 0) if isinstance(s, dict) else s.probability
                for s in scenarios
            )
            if abs(prob_sum - 1.0) > 1e-6:
                raise ValueError(
                    f"Scenario probabilities must sum to 1.0; got {prob_sum:.8f}"
                )

            # Compute derived fields
            expected_return = sum(
                (s.get("probability", 0) if isinstance(s, dict) else s.probability)
                * (s.get("expected_return", 0) if isinstance(s, dict) else s.expected_return)
                for s in scenarios
            )
            expected_pos_revision = sum(
                (s.get("probability", 0) if isinstance(s, dict) else s.probability)
                * (s.get("pos_revision", 0) if isinstance(s, dict) else s.pos_revision)
                for s in scenarios
            )

            def _get_outcome(s) -> str:
                raw = s.get("outcome") if isinstance(s, dict) else s.outcome
                return raw.value if hasattr(raw, "value") else str(raw)

            positive_values = {o.value for o in _POSITIVE_OUTCOMES}
            negative_values = {o.value for o in _NEGATIVE_OUTCOMES}

            upside_capture = sum(
                (s.get("probability", 0) if isinstance(s, dict) else s.probability)
                * (s.get("expected_return", 0) if isinstance(s, dict) else s.expected_return)
                for s in scenarios
                if _get_outcome(s) in positive_values
                and (s.get("expected_return", 0) if isinstance(s, dict) else s.expected_return) > 0
            )

            downside_raw = sum(
                (s.get("probability", 0) if isinstance(s, dict) else s.probability)
                * (s.get("expected_return", 0) if isinstance(s, dict) else s.expected_return)
                for s in scenarios
                if _get_outcome(s) in negative_values
                and (s.get("expected_return", 0) if isinstance(s, dict) else s.expected_return) < 0
            )
            downside_risk = abs(downside_raw)
            skew_ratio = upside_capture / (downside_risk + 1e-9)
            setup_score = _compute_setup_score(skew_ratio, expected_return)

            data["expected_return"] = expected_return
            data["expected_pos_revision"] = expected_pos_revision
            data["upside_capture"] = upside_capture
            data["downside_risk"] = downside_risk
            data["skew_ratio"] = skew_ratio
            data["setup_score"] = min(1.0, max(0.0, setup_score))

        return data


def build_catalyst_tree(
    catalyst_id: str,
    asset_id: str,
    catalyst_description: str,
    catalyst_date: str,
    scenario_inputs: list[dict],   # list of {outcome, probability, expected_return, pos_revision, rationale}
) -> CatalystPayoffTree:
    """Validate inputs and construct CatalystPayoffTree."""
    scenarios = [CatalystScenario(**s) for s in scenario_inputs]
    return CatalystPayoffTree(
        catalyst_id=catalyst_id,
        asset_id=asset_id,
        catalyst_description=catalyst_description,
        catalyst_date=catalyst_date,
        scenarios=scenarios,
        # derived fields — populated by model_validator
        expected_return=0.0,
        expected_pos_revision=0.0,
        upside_capture=0.0,
        downside_risk=0.0,
        skew_ratio=0.0,
        setup_score=0.0,
    )


def rank_catalysts(trees: list[CatalystPayoffTree]) -> list[CatalystPayoffTree]:
    """Return trees sorted by setup_score descending."""
    return sorted(trees, key=lambda t: t.setup_score, reverse=True)
