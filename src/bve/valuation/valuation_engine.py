"""
ValuationEngine — orchestrates the full valuation pipeline.

Usage
-----
    engine = ValuationEngine(asset, company, trials, market_model)
    output = engine.run()
"""
from __future__ import annotations

from typing import Optional

from bve.entities.asset import Asset
from bve.entities.company import Company
from bve.entities.indication import Indication
from bve.entities.trial import ClinicalTrial
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import MonteCarloParams, run_monte_carlo
from bve.models.pos_model import POSAdjusters, apply_pos_to_trials
from bve.models.rnpv_model import compute_rnpv
from bve.valuation.assumptions import AssumptionLog, build_assumption_log
from bve.valuation.outputs import SensitivityPoint, ValuationOutput
from bve.valuation.scenario import build_scenarios


class ValuationEngine:
    """
    Orchestrates: POS model → rNPV → scenarios → Monte Carlo → sensitivity.

    Parameters
    ----------
    asset:              Asset entity
    company:            Company entity
    trials:             Remaining ClinicalTrial objects for this asset
    market_model:       Commercial model
    indication:         Optional Indication entity (for memo context)
    pos_adjusters:      Per-phase POSAdjusters. If None, trial.success_probability is used as-is.
    mc_params:          Monte Carlo parameters. Defaults used if None.
    apply_pos_model:    If True and pos_adjusters provided, override trial success probabilities.
    analyst_notes:      Optional free-text notes included in memo output.
    """

    def __init__(
        self,
        asset: Asset,
        company: Company,
        trials: list[ClinicalTrial],
        market_model: MarketModel,
        indication: Optional[Indication] = None,
        pos_adjusters: Optional[dict] = None,    # TrialPhase → POSAdjusters
        design_adjusters: Optional[dict] = None, # TrialPhase → TrialDesignFeatureSet
        mc_params: Optional[MonteCarloParams] = None,
        apply_pos_model: bool = False,
        apply_design_model: bool = False,
        analyst_notes: Optional[str] = None,
        config_path: Optional[str] = None,
        limitations: Optional[list[str]] = None,
        thesis_changers: Optional[list[str]] = None,
    ):
        self.asset = asset
        self.company = company
        self.trials = [t for t in trials if t.asset_id == asset.id]
        self.market_model = market_model
        self.indication = indication
        self.pos_adjusters = pos_adjusters or {}
        self.design_adjusters = design_adjusters or {}
        self.mc_params = mc_params or MonteCarloParams()
        self.apply_pos_model = apply_pos_model
        self.apply_design_model = apply_design_model
        self.analyst_notes = analyst_notes
        self.config_path = config_path
        self.limitations = limitations
        self.thesis_changers = thesis_changers
        self.sources: Optional[dict] = None
        self.decision_framing = None

    def run(self) -> ValuationOutput:
        """Execute the full valuation pipeline."""
        trials = self._prepare_trials()

        # --- Base-case rNPV ---
        rnpv = compute_rnpv(self.asset, trials, self.market_model)

        # --- Company NAV ---
        ownership = self.company.ownership_of(self.asset.id)
        nav = rnpv.rnpv_millions * ownership + self.company.net_cash_millions
        nav_ps = nav / self.company.shares_outstanding_millions

        # Tag on NAV
        rnpv = rnpv.model_copy(update={"nav_millions": nav, "nav_per_share": nav_ps})

        # --- Scenarios ---
        scenarios = build_scenarios(
            self.asset, trials, self.market_model,
            net_cash_millions=self.company.net_cash_millions,
            shares_outstanding_millions=self.company.shares_outstanding_millions,
        )

        # --- Monte Carlo ---
        mc = run_monte_carlo(self.asset, trials, self.market_model, self.mc_params)
        mc_nav_per_share = (mc.mean_millions + self.company.net_cash_millions) / self.company.shares_outstanding_millions
        mc = mc.model_copy(update={"mean_nav_per_share": round(mc_nav_per_share, 2)})

        # --- Sensitivity ---
        sensitivities = self._compute_sensitivities(trials)

        # --- Assumption log ---
        assumption_log = build_assumption_log(
            self.asset, trials, self.market_model, rnpv,
            limitations=self.limitations,
            thesis_changers=self.thesis_changers,
            sources=self.sources,
        )

        return ValuationOutput(
            asset=self.asset,
            company=self.company,
            trials=trials,
            market_model=self.market_model,
            indication=self.indication,
            rnpv=rnpv,
            scenarios=scenarios,
            monte_carlo=mc,
            nav_millions=round(nav, 2),
            nav_per_share=round(nav_ps, 2),
            sensitivities=sensitivities,
            assumption_log=assumption_log,
            analyst_notes=self.analyst_notes,
            config_path=self.config_path,
            random_seed=self.mc_params.random_seed,
            n_simulations=self.mc_params.n_simulations,
            decision_framing=self.decision_framing,
        )

    def _prepare_trials(self) -> list[ClinicalTrial]:
        trials = self.trials
        if self.apply_pos_model and self.pos_adjusters:
            trials = apply_pos_to_trials(
                trials, self.asset.therapeutic_area, self.pos_adjusters
            )
        if self.apply_design_model and self.design_adjusters:
            trials = self._apply_design_adjustments(trials)
        return trials

    def _apply_design_adjustments(self, trials: list[ClinicalTrial]) -> list[ClinicalTrial]:
        """Apply trial design feature adjustments as the second POS layer.

        Runs after apply_pos_to_trials (if enabled), so adjusts the model-predicted
        POS rather than the raw YAML point estimate.

        Anti-double-counting: if both pos_adjusters and design_adjusters are enabled
        for the same phase, check_pos_layer_overlap() is called. Overlaps are printed
        as warnings but do not halt execution — the analyst must resolve them explicitly.
        """
        from bve.models.trial_design_features import check_pos_layer_overlap, compute_design_adjusted_pos

        result = []
        for trial in trials:
            features = self.design_adjusters.get(trial.phase)
            if features is None:
                result.append(trial)
                continue

            # Warn if this trial's phase also has pos_adjusters (potential double-count)
            if self.apply_pos_model and trial.phase in self.pos_adjusters:
                report = check_pos_layer_overlap(
                    self.pos_adjusters[trial.phase], features, phase=trial.phase.value
                )
                if not report.is_clean():
                    import warnings
                    warnings.warn(
                        f"[BVE design model] {trial.phase.value}: {report.summary()}",
                        stacklevel=2,
                    )

            dar = compute_design_adjusted_pos(
                trial.success_probability, features, phase=trial.phase.value
            )
            result.append(trial.model_copy(update={"success_probability": dar.adjusted_pos}))
        return result

    def _compute_sensitivities(self, trials: list[ClinicalTrial]) -> list[SensitivityPoint]:
        """Tornado analysis: vary one parameter at a time ±30% / ±1σ."""
        sensitivities = []

        def _rnpv(asset=None, trials_=None, market=None) -> float:
            a = asset or self.asset
            t = trials_ or trials
            m = market or self.market_model
            return compute_rnpv(a, t, m).rnpv_millions

        base = _rnpv()

        # 1. Peak sales ±30%
        if self.market_model.total_addressable_market_millions is not None:
            tam = self.market_model.total_addressable_market_millions
            m_lo = self.market_model.model_copy(update={"total_addressable_market_millions": tam * 0.70, "uptake_curve": None})
            m_hi = self.market_model.model_copy(update={"total_addressable_market_millions": tam * 1.30, "uptake_curve": None})
        else:
            price = self.market_model.net_price_per_patient_usd or 100_000
            m_lo = self.market_model.model_copy(update={"net_price_per_patient_usd": price * 0.70, "uptake_curve": None})
            m_hi = self.market_model.model_copy(update={"net_price_per_patient_usd": price * 1.30, "uptake_curve": None})

        sensitivities.append(SensitivityPoint(
            parameter="Peak Sales (±30%)",
            low_value=self.market_model.peak_sales_millions * 0.70,
            high_value=self.market_model.peak_sales_millions * 1.30,
            low_rnpv=_rnpv(market=m_lo),
            high_rnpv=_rnpv(market=m_hi),
        ))

        # 2. Discount rate ±2pp
        r = self.asset.discount_rate
        a_lo = self.asset.model_copy(update={"discount_rate": max(0.01, r - 0.02)})
        a_hi = self.asset.model_copy(update={"discount_rate": min(0.50, r + 0.02)})
        sensitivities.append(SensitivityPoint(
            parameter="Discount Rate (±2pp)",
            low_value=(r - 0.02) * 100,
            high_value=(r + 0.02) * 100,
            low_rnpv=_rnpv(asset=a_hi),   # lower rate → higher NPV so swap
            high_rnpv=_rnpv(asset=a_lo),
        ))

        # 3. Probability of success ±20% relative
        t_lo = [t.model_copy(update={"success_probability": min(0.99, t.success_probability * 0.80)}) for t in trials]
        t_hi = [t.model_copy(update={"success_probability": min(0.99, t.success_probability * 1.20)}) for t in trials]
        sensitivities.append(SensitivityPoint(
            parameter="Phase POS (±20%)",
            low_value=0.80,
            high_value=1.20,
            low_rnpv=_rnpv(trials_=t_lo),
            high_rnpv=_rnpv(trials_=t_hi),
        ))

        # 4. Patent life ±3 years
        pl = self.market_model.patent_life_years
        m_lo = self.market_model.model_copy(update={"patent_life_years": max(1, pl - 3), "uptake_curve": None})
        m_hi = self.market_model.model_copy(update={"patent_life_years": pl + 3, "uptake_curve": None})
        sensitivities.append(SensitivityPoint(
            parameter="Patent Life (±3 yrs)",
            low_value=pl - 3,
            high_value=pl + 3,
            low_rnpv=_rnpv(market=m_lo),
            high_rnpv=_rnpv(market=m_hi),
        ))

        # 5. Peak penetration ±30%
        pen = self.market_model.peak_penetration
        m_lo = self.market_model.model_copy(update={"peak_penetration": max(0.01, pen * 0.70), "uptake_curve": None})
        m_hi = self.market_model.model_copy(update={"peak_penetration": min(0.99, pen * 1.30), "uptake_curve": None})
        sensitivities.append(SensitivityPoint(
            parameter="Peak Penetration (±30%)",
            low_value=pen * 0.70,
            high_value=pen * 1.30,
            low_rnpv=_rnpv(market=m_lo),
            high_rnpv=_rnpv(market=m_hi),
        ))

        # Sort by |swing| descending (tornado order)
        sensitivities.sort(key=lambda s: abs(s.swing), reverse=True)
        return sensitivities
