"""Standardized valuation output container."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from bve.entities.asset import Asset
from bve.entities.company import Company
from bve.entities.indication import Indication
from bve.entities.trial import ClinicalTrial
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import MonteCarloResult
from bve.models.rnpv_model import RNPVResult
from bve.valuation.scenario import ScenarioSet


class SensitivityPoint(BaseModel):
    parameter: str
    low_value: float
    high_value: float
    low_rnpv: float
    high_rnpv: float

    @property
    def swing(self) -> float:
        return self.high_rnpv - self.low_rnpv


class ValuationOutput(BaseModel):
    """Full output from ValuationEngine.run(). This object drives all reporting."""

    # Inputs
    asset: Asset
    company: Company
    trials: list[ClinicalTrial]
    market_model: MarketModel
    indication: Optional[Indication] = None

    # Core outputs
    rnpv: RNPVResult
    scenarios: ScenarioSet
    monte_carlo: MonteCarloResult

    # Company-level NAV
    nav_millions: float
    nav_per_share: float

    # Sensitivity analysis (populated by ValuationEngine)
    sensitivities: list[SensitivityPoint] = Field(default_factory=list)

    # Assumption log (populated by ValuationEngine)
    assumption_log: Optional[object] = Field(default=None, exclude=False)   # AssumptionLog

    # Metadata
    analysis_date: str = Field(default_factory=lambda: date.today().isoformat())
    analyst_notes: Optional[str] = None
    config_path: Optional[str] = None    # source YAML, for reproducibility

    # Memo text (populated by reporting layer)
    memo_markdown: Optional[str] = None

    model_config = {"arbitrary_types_allowed": True}

    @property
    def implied_upside_pct(self) -> Optional[float]:
        price = self.company.current_price
        if price and price > 0:
            return round((self.nav_per_share / price - 1) * 100, 1)
        return None

    @property
    def summary_dict(self) -> dict:
        """Flat dict suitable for reporting and templates."""
        return {
            "asset_name": self.asset.name,
            "indication": self.asset.indication,
            "stage": self.asset.stage.value,
            "therapeutic_area": self.asset.therapeutic_area.value,
            "modality": self.asset.modality.value,
            "company": self.company.name,
            "ticker": self.company.ticker,
            "analysis_date": self.analysis_date,
            # rNPV
            "rnpv_millions": self.rnpv.rnpv_millions,
            "peak_sales_millions": self.rnpv.peak_sales_millions,
            "prob_approval_pct": f"{self.rnpv.cumulative_success_probability:.1%}",
            "years_to_launch": self.rnpv.years_to_launch,
            "discount_rate_pct": f"{self.rnpv.discount_rate:.0%}",
            "net_ownership_pct": f"{self.rnpv.net_ownership:.0%}",
            # Scenarios
            "bull_rnpv": self.scenarios.bull.rnpv_millions,
            "base_rnpv": self.scenarios.base.rnpv_millions,
            "bear_rnpv": self.scenarios.bear.rnpv_millions,
            "bull_nav_ps": self.scenarios.bull.nav_per_share,
            "base_nav_ps": self.scenarios.base.nav_per_share,
            "bear_nav_ps": self.scenarios.bear.nav_per_share,
            # MC
            "mc_mean": self.monte_carlo.mean_millions,
            "mc_p5": self.monte_carlo.percentile_5_millions,
            "mc_p10": self.monte_carlo.percentile_10_millions,
            "mc_p25": self.monte_carlo.percentile_25_millions,
            "mc_p50": self.monte_carlo.percentile_50_millions,
            "mc_p75": self.monte_carlo.percentile_75_millions,
            "mc_p90": self.monte_carlo.percentile_90_millions,
            "mc_p95": self.monte_carlo.percentile_95_millions,
            "mc_n_simulations": self.monte_carlo.n_simulations,
            "mc_prob_positive": f"{self.monte_carlo.probability_positive:.1%}",
            "mc_prob_above_500m": f"{self.monte_carlo.probability_above_500m:.1%}",
            # NAV
            "nav_millions": self.nav_millions,
            "nav_per_share": self.nav_per_share,
            "current_price": self.company.current_price,
            "shares_outstanding_millions": self.company.shares_outstanding_millions,
            "implied_upside_pct": self.implied_upside_pct,
            "net_cash_millions": self.company.net_cash_millions,
            "cash_runway_quarters": self.company.cash_runway_quarters,
        }

    def to_json_dict(self) -> dict:
        """
        Machine-readable JSON representation — omits raw MC simulation vector
        (10k floats) but preserves all inputs, outputs, and assumptions.
        """
        d: dict = {
            "meta": {
                "analysis_date": self.analysis_date,
                "config_path": self.config_path,
                "analyst_notes": self.analyst_notes,
                "bve_version": "0.2.0",
            },
            "inputs": {
                "asset": self.asset.model_dump(),
                "company": {
                    k: v for k, v in self.company.model_dump().items()
                    if k != "partnerships"
                },
                "trials": [
                    {k: v for k, v in t.model_dump().items() if k != "arms"}
                    for t in self.trials
                ],
                "market_model": {
                    k: v for k, v in self.market_model.model_dump().items()
                    if k != "uptake_curve"
                },
            },
            "outputs": {
                "rnpv": {
                    "rnpv_millions": self.rnpv.rnpv_millions,
                    "peak_sales_millions": self.rnpv.peak_sales_millions,
                    "gross_revenue_pv_millions": self.rnpv.gross_revenue_pv_millions,
                    "prob_adj_revenue_pv_millions": self.rnpv.probability_adjusted_revenue_pv_millions,
                    "trial_costs_pv_millions": self.rnpv.trial_costs_pv_millions,
                    "cumulative_success_probability": self.rnpv.cumulative_success_probability,
                    "years_to_launch": self.rnpv.years_to_launch,
                    "discount_rate": self.rnpv.discount_rate,
                    "net_ownership": self.rnpv.net_ownership,
                    "phase_breakdown": [pb.model_dump() for pb in self.rnpv.phase_breakdown],
                },
                "nav": {
                    "asset_rnpv_millions": self.rnpv.rnpv_millions,
                    "net_cash_millions": self.company.net_cash_millions,
                    "nav_millions": self.nav_millions,
                    "shares_outstanding_millions": self.company.shares_outstanding_millions,
                    "nav_per_share": self.nav_per_share,
                    "current_price": self.company.current_price,
                    "implied_upside_pct": self.implied_upside_pct,
                },
                "scenarios": {
                    "bull": self.scenarios.bull.model_dump(),
                    "base": self.scenarios.base.model_dump(),
                    "bear": self.scenarios.bear.model_dump(),
                    "upside_downside_ratio": self.scenarios.upside_downside_ratio,
                },
                "monte_carlo": {
                    "n_simulations": self.monte_carlo.n_simulations,
                    "mean_millions": self.monte_carlo.mean_millions,
                    "median_millions": self.monte_carlo.median_millions,
                    "std_millions": self.monte_carlo.std_millions,
                    "percentiles": {
                        "p5": self.monte_carlo.percentile_5_millions,
                        "p10": self.monte_carlo.percentile_10_millions,
                        "p25": self.monte_carlo.percentile_25_millions,
                        "p50": self.monte_carlo.percentile_50_millions,
                        "p75": self.monte_carlo.percentile_75_millions,
                        "p90": self.monte_carlo.percentile_90_millions,
                        "p95": self.monte_carlo.percentile_95_millions,
                    },
                    "probability_positive": self.monte_carlo.probability_positive,
                    "probability_above_500m": self.monte_carlo.probability_above_500m,
                    "probability_above_1b": self.monte_carlo.probability_above_1b,
                },
                "sensitivities": [
                    {
                        "parameter": s.parameter,
                        "low_rnpv": s.low_rnpv,
                        "high_rnpv": s.high_rnpv,
                        "swing": s.swing,
                    }
                    for s in self.sensitivities
                ],
            },
        }

        # Add assumption log if present
        if self.assumption_log is not None:
            try:
                al = self.assumption_log
                d["assumptions"] = {
                    "key_assumptions": [a.model_dump() for a in al.to_flat_list()],
                    "limitations": al.limitations,
                    "what_would_change_thesis": al.thesis_changers,
                }
            except Exception:
                pass

        return d

    def save_json(self, path: str | Path) -> Path:
        """Serialize to a clean JSON file. Excludes raw MC simulation vector."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_json_dict(), f, indent=2, default=str)
        return path
