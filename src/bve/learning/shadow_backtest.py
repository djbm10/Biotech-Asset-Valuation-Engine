"""Shadow-backtest proposed weight changes before promoting them."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from bve.persistence.gap_fill_store import OutcomeRecord

_ERROR_ATTRIBUTIONS = {"thesis_error", "pos_error"}


class ShadowBacktestConfig(BaseModel):
    min_decisions_required: int = 10
    min_positive_return_rate: float = 0.50
    max_attribution_error_rate: float = 0.40  # thesis_error + pos_error fraction


class ShadowBacktestResult(BaseModel):
    passed: bool
    n_decisions: int
    positive_return_rate: float
    attribution_error_rate: float
    mean_return_pct: float
    recommendation: str  # "promote" / "hold" / "reject"
    notes: list[str]


class ShadowBacktest:
    """
    Run shadow validation on a set of outcome records before weight promotion.

    Gate rules (in ShadowBacktestConfig):
    - n_decisions >= min_decisions_required
    - positive_return_rate >= min_positive_return_rate
    - attribution_error_rate <= max_attribution_error_rate

    Recommendation:
    - all gates pass → "promote"
    - n_decisions < min_required → "hold" (not enough data)
    - any gate fails → "reject"
    """

    def __init__(self, config: Optional[ShadowBacktestConfig] = None) -> None:
        self._config = config or ShadowBacktestConfig()

    def run(self, outcomes: list[OutcomeRecord]) -> ShadowBacktestResult:
        n = len(outcomes)
        notes: list[str] = []

        if n == 0:
            return ShadowBacktestResult(
                passed=False,
                n_decisions=0,
                positive_return_rate=0.0,
                attribution_error_rate=0.0,
                mean_return_pct=0.0,
                recommendation="hold",
                notes=["No outcome records provided."],
            )

        if n < self._config.min_decisions_required:
            return ShadowBacktestResult(
                passed=False,
                n_decisions=n,
                positive_return_rate=_positive_rate(outcomes),
                attribution_error_rate=_error_rate(outcomes),
                mean_return_pct=_mean_return(outcomes),
                recommendation="hold",
                notes=[
                    f"Insufficient data: {n} decisions < required {self._config.min_decisions_required}."
                ],
            )

        positive_rate = _positive_rate(outcomes)
        error_rate = _error_rate(outcomes)
        mean_ret = _mean_return(outcomes)

        gate_failures: list[str] = []

        if positive_rate < self._config.min_positive_return_rate:
            gate_failures.append(
                f"Positive return rate {positive_rate:.2%} < required {self._config.min_positive_return_rate:.2%}."
            )

        if error_rate > self._config.max_attribution_error_rate:
            gate_failures.append(
                f"Attribution error rate {error_rate:.2%} > maximum {self._config.max_attribution_error_rate:.2%}."
            )

        if gate_failures:
            notes.extend(gate_failures)
            return ShadowBacktestResult(
                passed=False,
                n_decisions=n,
                positive_return_rate=positive_rate,
                attribution_error_rate=error_rate,
                mean_return_pct=mean_ret,
                recommendation="reject",
                notes=notes,
            )

        notes.append("All gates passed.")
        return ShadowBacktestResult(
            passed=True,
            n_decisions=n,
            positive_return_rate=positive_rate,
            attribution_error_rate=error_rate,
            mean_return_pct=mean_ret,
            recommendation="promote",
            notes=notes,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _positive_rate(outcomes: list[OutcomeRecord]) -> float:
    if not outcomes:
        return 0.0
    return sum(1 for o in outcomes if o.return_realized_pct > 0) / len(outcomes)


def _error_rate(outcomes: list[OutcomeRecord]) -> float:
    if not outcomes:
        return 0.0
    return sum(1 for o in outcomes if o.attribution in _ERROR_ATTRIBUTIONS) / len(outcomes)


def _mean_return(outcomes: list[OutcomeRecord]) -> float:
    if not outcomes:
        return 0.0
    return sum(o.return_realized_pct for o in outcomes) / len(outcomes)
