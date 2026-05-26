"""Standardized valuation output container."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from bve.entities.asset import Asset
from bve.entities.company import Company
from bve.entities.indication import Indication
from bve.entities.trial import ClinicalTrial
# Import from bve.models.deal_models — avoids triggering bve.intelligence.__init__
# which would create a phase2 → valuation_integration → outputs circular import.
from bve.models.deal_models import ComparableDealAnalysis
from bve.models.market_model import MarketModel
from bve.models.revenue_audit import RevenueAuditTable
from bve.models.monte_carlo import MonteCarloResult
from bve.models.rnpv_model import RNPVResult
from bve.valuation.scenario import ScenarioSet
# Assumption types — assumptions.py does not import from outputs.py.
from bve.valuation.assumptions import AssumptionLog, DecisionFraming
# Market-implied expectation (no circular import — expectations module is standalone)
from bve.expectations.market_implied_pos import ImpliedPoSResult
# Acquirer match (entities module is standalone — no circular import)
from bve.entities.acquirer import AcquirerMatch
# Runway and dilution models (models module is standalone — no circular import)
from bve.models.runway_forecast import RunwayForecastV2
from bve.models.dilution_model import DilutionAnalysis
# Analog match (models module is standalone — no circular import)
from bve.models.analog_matcher import AnalogMatchResult
# Catalyst payoff (models module is standalone — no circular import)
from bve.models.catalyst_payoff import CatalystPayoffResult
# Variant perception back-solve (analysis module; only imports outputs under TYPE_CHECKING — no cycle)
from bve.analysis.variant_perception import VariantPerceptionResult
# NOTE: bve.reporting.evidence and bve.intelligence.schemas cannot be imported here:
#   bve.reporting.__init__ → memo_generator → ValuationOutput (circular)
#   bve.intelligence.__init__ → phase2 → valuation_integration → ValuationOutput (circular)
# Those fields are typed as list/Optional[object] with descriptive docstrings instead.


class SensitivityPoint(BaseModel):
    parameter: str
    low_value: float
    high_value: float
    low_rnpv: float
    high_rnpv: float
    # Sprint 35 additions (backward-compatible defaults)
    base_rnpv: float = 0.0    # rNPV at unshocked base — anchors tornado bars
    shock_pct: float = 0.0    # shock magnitude as a percentage, e.g. 30.0 = ±30%
    rank: int = 0             # 1 = largest |swing| (set after sorting)

    @property
    def swing(self) -> float:
        return self.high_rnpv - self.low_rnpv

    @property
    def abs_swing(self) -> float:
        return abs(self.swing)


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
    assumption_log: Optional[AssumptionLog] = Field(default=None, exclude=False)

    # Decision framing (optional — populated when decision_framing: section present in YAML)
    decision_framing: Optional[DecisionFraming] = Field(default=None)

    # Lifecycle events (populated from market_model.lifecycle_events when present)
    lifecycle_events_applied: list[dict] = Field(
        default_factory=list,
        description=(
            "Serialized summary of LifecycleEvent objects active in this valuation. "
            "Each dict contains: year, type, label, effect (human-readable description). "
            "Empty list when no lifecycle events are configured."
        ),
    )

    # Metadata
    analysis_date: str = Field(default_factory=lambda: date.today().isoformat())
    run_timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    analyst_notes: Optional[str] = None
    config_path: Optional[str] = None    # source YAML, for reproducibility
    random_seed: Optional[int] = None
    n_simulations: Optional[int] = None

    # Provenance — institutional audit trail (Task 9.21)
    assumptions_yaml_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 (first 12 chars) of industry_assumptions.yaml used in this run.",
    )
    config_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 (first 12 chars) of the asset YAML config file, when supplied.",
    )
    wacc_vintage: Optional[str] = Field(
        default=None,
        description="WACC vintage tag from industry_assumptions.yaml (e.g. '2026-Q1').",
    )
    analyst_overrides: list[str] = Field(
        default_factory=list,
        description=(
            "Fields explicitly overridden from industry defaults in this run. "
            "e.g. ['discount_rate: 0.14 (default: 0.12)', 'peak_penetration: 0.25']"
        ),
    )

    # Deal comps analysis (populated by ValuationEngine when comparable_deals provided)
    comps_fair_value_band: Optional[ComparableDealAnalysis] = Field(
        default=None,
        description=(
            "Matched biotech M&A comparable deal analysis, including EV/peak_sales "
            "percentiles and fair-value bands for EV, upfront, and total_biobucks. "
            "None when no comparable_deals list is supplied to ValuationEngine."
        ),
    )

    # Intelligence signals and artifacts (caller-supplied; used by MemoEvidenceBuilder).
    # Typed as plain list to avoid bve.intelligence.__init__ circular import.
    # Items are StructuredSignal objects from bve.intelligence.schemas.signals.
    signals: list = Field(
        default_factory=list,
        description=(
            "StructuredSignal records for this asset, sourced from KnowledgeStore or manual entry. "
            "When populated, MemoEvidenceBuilder wires them into biology and trial evidence sections."
        ),
    )
    # Items are KnowledgeArtifact objects from bve.intelligence.schemas.knowledge.
    knowledge_artifacts: list = Field(
        default_factory=list,
        description=(
            "KnowledgeArtifact records for this asset. competitor_landscape artifacts are wired "
            "into the competitive evidence section by MemoEvidenceBuilder."
        ),
    )

    # Revenue audit table (populated by ValuationEngine.run())
    revenue_audit_table: Optional[RevenueAuditTable] = Field(
        default=None,
        description=(
            "Year-by-year revenue decomposition into gross uptake, competition fraction, "
            "price pressure, payer access, COGS, SG&A, and EBIT. "
            "Rows correspond 1:1 to RevenueStream.revenue_by_year. "
            "None only when the engine is invoked without a full MarketModel."
        ),
    )

    # Market-implied expectation (auto-populated by ValuationEngine when price data is available)
    market_expectation: Optional[ImpliedPoSResult] = Field(
        default=None,
        description=(
            "Back-solved market-implied PoS and peak sales. Populated by ValuationEngine "
            "when company.current_price > 0. Contains pos_gap (model_pos − implied_pos): "
            "positive = model more bullish than market; negative = market more bullish."
        ),
    )

    # Top acquirers (auto-populated by ValuationEngine — top-2 by composite score)
    top_acquirers: list[AcquirerMatch] = Field(
        default_factory=list,
        description=(
            "Top-ranked acquirers from ACQUIRER_UNIVERSE, scored by TA match, LOE urgency, "
            "and budget capacity. Populated by ValuationEngine.run(). Empty list when "
            "rNPV is unavailable or the asset has no clear strategic fit signals."
        ),
    )

    # Runway forecast (auto-populated when Company.burn_rate_millions_per_quarter is set)
    runway_forecast: Optional[RunwayForecastV2] = Field(
        default=None,
        description=(
            "Cash runway forecast computed from company.cash_millions and burn_rate_millions_per_quarter. "
            "None when burn rate is not available. runway_risk: critical|high|medium|low|comfortable."
        ),
    )

    # Dilution analysis (auto-populated when Company.current_price and burn rate are set)
    dilution_analysis: Optional[DilutionAnalysis] = Field(
        default=None,
        description=(
            "Bull/base/bear dilution scenarios for equity raise needed to fund remaining trial costs. "
            "None when current_price is not available. weighted_dilution_pct is the probability-weighted estimate."
        ),
    )

    # Catalyst payoff decomposition (auto-populated by ValuationEngine.run())
    catalyst_payoff: Optional[CatalystPayoffResult] = Field(
        default=None,
        description=(
            "Binary catalyst EV decomposition: success vs failure rNPV scenarios. "
            "upside = value_if_success - current_value; "
            "downside = current_value - value_if_failure; "
            "delta_ev = pos × upside - (1-pos) × downside. "
            "signal_strength > 0 = positive EV catalyst."
        ),
    )

    # Launch analog match (auto-populated by ValuationEngine when mechanism/indication available)
    analog_match: Optional[AnalogMatchResult] = Field(
        default=None,
        description=(
            "Historical launch analogs matched by mechanism_of_action and indication. "
            "Contains median_peak_sales_millions as a sanity-check reference for the model's "
            "commercial assumption. None when no matching analogs are found."
        ),
    )

    # Variant perception back-solve (auto-populated by ValuationEngine when price data is available)
    variant_perception: Optional[VariantPerceptionResult] = Field(
        default=None,
        description=(
            "Back-solved market assumptions from current stock price. "
            "Isolates this asset's implied EV, then inverts the rNPV equation to infer "
            "market-implied POS, peak sales, penetration, price, and eligible patients. "
            "None when company.current_price is not set. "
            "variant_perception_category: clinical | commercial | pricing | mixed | allocation | indeterminate."
        ),
    )

    # Per-metric evidence grade (populated by caller; keyed by metric name)
    confidence_tags: dict = Field(
        default_factory=dict,
        description="Per-metric evidence grade dictionary (EvidenceGrade values by metric name).",
    )

    # Memo text (populated by reporting layer)
    memo_markdown: Optional[str] = None

    # Structured evidence bundle (populated by MemoEvidenceBuilder during generate_memo)
    # Type is MemoEvidence; kept as object to avoid bve.reporting.__init__ circular import.
    memo_evidence: Optional[object] = Field(
        default=None,
        description=(
            "Section-keyed evidence bundle (MemoEvidence) built by MemoEvidenceBuilder. "
            "Contains traceable MemoEvidenceRef objects for each memo section. "
            "None until generate_memo() has been called."
        ),
    )

    model_config = {"arbitrary_types_allowed": True}

    @staticmethod
    def _git_commit() -> Optional[str]:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=3
            )
            return result.stdout.strip() or None
        except Exception:
            return None

    @staticmethod
    def _package_versions() -> dict:
        pkgs = ["pydantic", "numpy", "scipy", "pandas", "matplotlib"]
        versions = {}
        for pkg in pkgs:
            try:
                import importlib.metadata
                versions[pkg] = importlib.metadata.version(pkg)
            except Exception:
                pass
        return versions

    @property
    def implied_upside_pct(self) -> Optional[float]:
        price = self.company.current_price
        if price and price > 0:
            return round((self.nav_per_share / price - 1) * 100, 1)
        return None

    @property
    def implied_pos(self) -> Optional[float]:
        """
        Market-implied probability of approval, back-solved from current stock price.

        Derivation:
          market_cap = price × shares
          market_implied_rnpv = market_cap - net_cash
          rNPV = P × gross_revenue_pv - trial_costs_pv (weighted)
          => P_implied = (market_implied_rnpv + trial_costs_pv) / gross_revenue_pv

        Returns None if price unavailable or gross_revenue_pv <= 0.
        """
        price = self.company.current_price
        if not price or price <= 0:
            return None
        gross_pv = self.rnpv.gross_revenue_pv_millions
        if gross_pv <= 0:
            return None
        mkt_cap = price * self.company.shares_outstanding_millions
        implied_rnpv = mkt_cap - self.company.net_cash_millions
        pos = (implied_rnpv + self.rnpv.trial_costs_pv_millions) / gross_pv
        return round(max(0.0, min(1.0, pos)), 4)

    @property
    def pos_comparison_text(self) -> Optional[str]:
        """Human-readable POS comparison string.

        Returns None when market-implied POS is unavailable (no price data).
        Example: "Model POS: 45.0% | Market-implied: 38.0% | Gap: +7.0pp (underpriced)"
        """
        if self.market_expectation is None:
            return None
        model_pos = self.rnpv.cumulative_success_probability
        implied = self.market_expectation.implied_pos
        gap_pp = self.market_expectation.pos_gap * 100
        direction = self.market_expectation.mispricing_direction or "aligned"
        return (
            f"Model POS: {model_pos:.0%} | "
            f"Market-implied: {implied:.0%} | "
            f"Gap: {gap_pp:+.1f}pp ({direction})"
        )

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
            # Deal comps (None when not computed)
            "comps_match_tier": self.comps_fair_value_band.match_tier if self.comps_fair_value_band else None,
            "comps_n_comps": self.comps_fair_value_band.n_comps if self.comps_fair_value_band else None,
            "comps_peer_median_ev_to_peak_sales": (
                self.comps_fair_value_band.peer_median_ev_to_peak_sales
                if self.comps_fair_value_band else None
            ),
            # Model POS (always available; pos_comparison_text None without price data)
            "model_pos": round(self.rnpv.cumulative_success_probability, 4),
            "pos_comparison_text": self.pos_comparison_text if self.market_expectation is not None else None,
            # Market-implied expectation delta (None when no price data)
            "market_implied_pos": (
                round(self.market_expectation.implied_pos, 3)
                if self.market_expectation else None
            ),
            "market_pos_gap": (
                round(self.market_expectation.pos_gap, 3)
                if self.market_expectation else None
            ),
            "market_pos_gap_pct": (
                f"{self.market_expectation.pos_gap:+.1%}"
                if self.market_expectation else None
            ),
            "market_mispricing_direction": (
                self.market_expectation.mispricing_direction
                if self.market_expectation else None
            ),
            "market_mispricing_magnitude": (
                self.market_expectation.mispricing_magnitude
                if self.market_expectation else None
            ),
            "market_implied_peak_sales_millions": (
                round(self.market_expectation.implied_peak_sales_millions, 0)
                if self.market_expectation else None
            ),
            # Top acquirers (names and scores for memo display)
            "top_acquirer_1": self.top_acquirers[0].name if len(self.top_acquirers) > 0 else None,
            "top_acquirer_1_score": self.top_acquirers[0].composite_score if len(self.top_acquirers) > 0 else None,
            "top_acquirer_1_rationale": self.top_acquirers[0].rationale if len(self.top_acquirers) > 0 else None,
            "top_acquirer_2": self.top_acquirers[1].name if len(self.top_acquirers) > 1 else None,
            "top_acquirer_2_score": self.top_acquirers[1].composite_score if len(self.top_acquirers) > 1 else None,
            "top_acquirer_2_rationale": self.top_acquirers[1].rationale if len(self.top_acquirers) > 1 else None,
            # Runway flags (None when no burn rate data)
            "runway_months": (
                round(self.runway_forecast.runway_months, 1)
                if self.runway_forecast else None
            ),
            "runway_risk": (
                self.runway_forecast.runway_risk
                if self.runway_forecast else None
            ),
            "runway_date": (
                self.runway_forecast.runway_date
                if self.runway_forecast else None
            ),
            # Catalyst payoff (None when not computed)
            "catalyst_upside_millions": (
                self.catalyst_payoff.upside if self.catalyst_payoff else None
            ),
            "catalyst_downside_millions": (
                self.catalyst_payoff.downside if self.catalyst_payoff else None
            ),
            "catalyst_delta_ev_millions": (
                self.catalyst_payoff.delta_ev if self.catalyst_payoff else None
            ),
            "catalyst_signal_strength": (
                self.catalyst_payoff.signal_strength if self.catalyst_payoff else None
            ),
            "catalyst_asymmetry_ratio": (
                self.catalyst_payoff.asymmetry_ratio if self.catalyst_payoff else None
            ),
            "catalyst_ev_label": (
                self.catalyst_payoff.ev_label if self.catalyst_payoff else None
            ),
            # Analog match (None when no matching analogs found)
            "analog_median_peak_sales_millions": (
                self.analog_match.median_peak_sales_millions
                if self.analog_match and self.analog_match.median_peak_sales_millions is not None
                else None
            ),
            "analog_score": (
                round(self.analog_match.analog_score, 2)
                if self.analog_match else None
            ),
            "analog_success_rate": (
                round(self.analog_match.success_rate, 2)
                if self.analog_match else None
            ),
            "analog_n_matched": (
                len(self.analog_match.matched_analogs)
                if self.analog_match else None
            ),
            "analog_peak_sales_gap_pct": (
                round(
                    (self.rnpv.peak_sales_millions / self.analog_match.median_peak_sales_millions - 1) * 100, 1
                )
                if (self.analog_match and self.analog_match.median_peak_sales_millions
                    and self.analog_match.median_peak_sales_millions > 0)
                else None
            ),
            # Variant perception back-solve (None when no price data)
            "vp_category": (
                self.variant_perception.variant_perception_category
                if self.variant_perception else None
            ),
            "vp_implied_pos": (
                self.variant_perception.base.implied_pos
                if self.variant_perception and self.variant_perception.base.implied_pos is not None
                else None
            ),
            "vp_pos_gap_pp": (
                round(
                    (self.rnpv.cumulative_success_probability
                     - self.variant_perception.base.implied_pos) * 100, 1
                )
                if (self.variant_perception
                    and self.variant_perception.base.implied_pos is not None)
                else None
            ),
            "vp_implied_peak_sales_millions": (
                self.variant_perception.base.implied_peak_sales_millions
                if self.variant_perception else None
            ),
            "vp_memo": (
                self.variant_perception.memo_interpretation
                if self.variant_perception else None
            ),
            # Dilution flag (None when no price data)
            "dilution_weighted_pct": (
                round(self.dilution_analysis.weighted_dilution_pct, 1)
                if self.dilution_analysis else None
            ),
            "dilution_flag": (
                "high" if (self.dilution_analysis and self.dilution_analysis.weighted_dilution_pct > 20.0)
                else ("moderate" if (self.dilution_analysis and self.dilution_analysis.weighted_dilution_pct > 10.0)
                      else ("low" if self.dilution_analysis else None))
            ),
        }

    def to_json_dict(self) -> dict:
        """
        Machine-readable JSON representation — omits raw MC simulation vector
        (10k floats) but preserves all inputs, outputs, and assumptions.
        """
        d: dict = {
            "meta": {
                "analysis_date": self.analysis_date,
                "run_timestamp": self.run_timestamp,
                "git_commit": self._git_commit(),
                "random_seed": self.random_seed,
                "n_simulations": self.n_simulations,
                "bve_version": "0.2.0",
                "python_version": sys.version.split()[0],
                "package_versions": self._package_versions(),
                "config_path": self.config_path,
                "analyst_notes": self.analyst_notes,
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

        # Add deal comps analysis if present
        if self.comps_fair_value_band is not None:
            d["outputs"]["deal_comps"] = self.comps_fair_value_band.model_dump()

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
