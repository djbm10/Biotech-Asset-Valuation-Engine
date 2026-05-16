"""Dumb baseline models — every real model must beat these."""

from __future__ import annotations

import math
from typing import Sequence


# Industry-standard TA/phase base rates (from industry_assumptions.yaml)
_BASE_RATES: dict[str, dict[str, float]] = {
    "oncology": {"phase_1": 0.56, "phase_2": 0.35, "phase_3": 0.60, "nda_bla": 0.85},
    "cns": {"phase_1": 0.46, "phase_2": 0.25, "phase_3": 0.50, "nda_bla": 0.80},
    "cardiovascular": {"phase_1": 0.57, "phase_2": 0.38, "phase_3": 0.62, "nda_bla": 0.87},
    "infectious_disease": {"phase_1": 0.60, "phase_2": 0.45, "phase_3": 0.65, "nda_bla": 0.88},
    "other": {"phase_1": 0.55, "phase_2": 0.35, "phase_3": 0.60, "nda_bla": 0.85},
}


class POSBaseline:
    """Dumb POS baseline: TA/stage base rate only, no adjusters."""

    def predict(
        self,
        therapeutic_area: str,
        phase: str,
    ) -> float:
        ta = therapeutic_area.lower().replace(" ", "_")
        rates = _BASE_RATES.get(ta, _BASE_RATES["other"])
        return rates.get(phase, 0.50)

    def predict_batch(
        self,
        records: Sequence[dict],
    ) -> list[float]:
        return [self.predict(r.get("ta", "other"), r.get("phase", "phase_2")) for r in records]

    def brier_score(self, predictions: Sequence[float], outcomes: Sequence[int]) -> float:
        n = len(predictions)
        if n == 0:
            return float("nan")
        return sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / n

    def no_skill_brier(self, outcomes: Sequence[int]) -> float:
        """Brier score of always predicting the mean — the no-skill baseline."""
        if not outcomes:
            return float("nan")
        mean = sum(outcomes) / len(outcomes)
        return sum((mean - o) ** 2 for o in outcomes) / len(outcomes)

    def skill_improvement_pct(
        self, predictions: Sequence[float], outcomes: Sequence[int]
    ) -> float:
        """Percentage improvement over no-skill baseline (positive = better)."""
        model_brier = self.brier_score(predictions, outcomes)
        no_skill = self.no_skill_brier(outcomes)
        if no_skill == 0:
            return 0.0
        return (no_skill - model_brier) / no_skill * 100


class MNABaseline:
    """
    Dumb M&A baseline: cash runway + market cap + Phase 2/3 stage.
    Ranks candidates by: (1 if Phase2/3 else 0) + normalized_cash_score - normalized_market_cap_score
    A large company with Phase 2 and lots of cash is the baseline "top pick".
    """

    def score(
        self,
        phase: str,
        cash_runway_months: float,
        market_cap_usd: float,
    ) -> float:
        phase_score = 1.0 if phase in ("phase_2", "phase_3") else 0.0
        cash_score = min(cash_runway_months / 36.0, 1.0)  # normalise to 36-month max
        size_penalty = min(math.log10(max(market_cap_usd, 1)) / 10.0, 1.0)  # smaller = more acquirable
        return phase_score * 0.50 + cash_score * 0.30 + (1 - size_penalty) * 0.20

    def rank_batch(self, records: Sequence[dict]) -> list[tuple[str, float]]:
        scored = []
        for r in records:
            s = self.score(
                r.get("phase", "phase_1"),
                r.get("cash_runway_months", 12),
                r.get("market_cap_usd", 1e8),
            )
            scored.append((r.get("ticker", "?"), s))
        return sorted(scored, key=lambda x: x[1], reverse=True)


class ValuationBaseline:
    """
    Dumb valuation baseline: simple rNPV with fixed peak sales and TA base rates.
    No adjusters, no competition, no LOE tail.
    """

    FIXED_PEAK_SALES_BY_TA: dict[str, float] = {
        "oncology": 500.0,
        "cns": 350.0,
        "cardiovascular": 600.0,
        "infectious_disease": 400.0,
        "other": 300.0,
    }
    FIXED_DISCOUNT_RATE = 0.10
    FIXED_EBIT_MARGIN = 0.35
    FIXED_YEARS_TO_APPROVAL = 7

    def compute_rnpv(
        self,
        therapeutic_area: str,
        phase: str,
        net_ownership: float = 1.0,
    ) -> float:
        ta = therapeutic_area.lower().replace(" ", "_")
        peak_sales = self.FIXED_PEAK_SALES_BY_TA.get(ta, self.FIXED_PEAK_SALES_BY_TA["other"])
        pos = _BASE_RATES.get(ta, _BASE_RATES["other"]).get(phase, 0.50)
        # PV of 10 years of EBIT post-approval, annuity formula
        r = self.FIXED_DISCOUNT_RATE
        pv_factor = (1 - (1 + r) ** -10) / r / (1 + r) ** self.FIXED_YEARS_TO_APPROVAL
        pv_ebit = peak_sales * self.FIXED_EBIT_MARGIN * pv_factor * net_ownership
        return pos * pv_ebit


class CatalystBaseline:
    """
    Dumb catalyst baseline: historical average move by event type.
    Predicts direction as 50/50 (random), with magnitude = historical average.
    """

    _HISTORICAL_AVERAGE_MOVES: dict[str, float] = {
        "phase_2_topline": 0.25,
        "phase_3_topline": 0.35,
        "nda_submission": 0.10,
        "fda_approval": 0.15,
        "fda_rejection": -0.25,
        "partnership": 0.20,
        "acquisition": 0.40,
    }

    def predict_magnitude(self, event_type: str) -> float:
        return self._HISTORICAL_AVERAGE_MOVES.get(event_type, 0.15)

    def predict_direction(self) -> float:
        """Baseline direction prediction: always 0.5 (no edge)."""
        return 0.5
