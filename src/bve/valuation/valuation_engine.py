"""
ValuationEngine — thin orchestrator for the valuation pipeline.

Target shape (Step 2):
    prob  = ProbabilityModel.compute(asset, trials)
    rev   = RevenueModel.compute(market_model)
    cost  = CostModel.compute(prob, asset.discount_rate)
    rnpv  = RNPVModel.compute(asset, prob, rev, cost)

Sensitivity and scenario analysis still call compute_rnpv() (the backward-compat
wrapper) because they require many cheap re-valuations with perturbed inputs.
That is architectural debt to be cleaned in a later step.
"""
from __future__ import annotations

import warnings
from typing import Optional

from bve.entities.asset import Asset, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.indication import Indication
from bve.entities.trial import ClinicalTrial
from bve.models.cost_model import CostModel
from bve.models.drug_asset_program import CommercialPlan, DrugAssetProgram
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import MonteCarloParams, run_monte_carlo
from bve.models.pos_model import apply_pos_to_trials
from bve.models.probability_model import ProbabilityModel
from bve.models.revenue_model import RevenueModel
from bve.models.rnpv_model import RNPVModel, compute_rnpv_full
from bve.valuation.assumptions import build_assumption_log
from bve.valuation.outputs import SensitivityPoint, ValuationOutput
from bve.valuation.scenario import build_scenarios


class ValuationEngine:
    """
    Orchestrates: POS model → ProbabilityModel → RevenueModel → CostModel →
    RNPVModel → scenarios → Monte Carlo → sensitivity → ValuationOutput.

    Parameters
    ----------
    asset:              Asset entity
    company:            Company entity
    trials:             Remaining ClinicalTrial objects for this asset
    market_model:       Commercial model
    indication:         Optional Indication entity (for memo context)
    pos_adjusters:      Per-phase POSAdjusters. If None, trial.success_probability is used as-is.
    design_adjusters:   Per-phase TrialDesignFeatureSet (second POS layer).
    mc_params:          Monte Carlo parameters. Defaults used if None.
    apply_pos_model:    If True and pos_adjusters provided, override trial success probabilities.
    apply_design_model: If True and design_adjusters provided, apply as second POS layer.
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
        self._commercial_plan: Optional[CommercialPlan] = None  # set by from_program
        self._deal_economics = None  # set by from_program; Optional[DealEconomics]

    # ------------------------------------------------------------------
    # Alternate constructor from DrugAssetProgram
    # ------------------------------------------------------------------

    @classmethod
    def from_program(
        cls,
        program: DrugAssetProgram,
        company: Company,
        indication: Optional[Indication] = None,
        mc_params: Optional[MonteCarloParams] = None,
        apply_pos_model: bool = False,
        apply_design_model: bool = False,
        analyst_notes: Optional[str] = None,
        config_path: Optional[str] = None,
        limitations: Optional[list[str]] = None,
        thesis_changers: Optional[list[str]] = None,
    ) -> "ValuationEngine":
        """
        Build a ValuationEngine from a DrugAssetProgram.

        The engine uses program.commercial_plan.loe_profile directly instead
        of fetching it from AssumptionsLoader at run time, making the LOE
        assumption explicit and inspectable before run() is called.
        """
        engine = cls(
            asset=program.asset,
            company=company,
            trials=program.trials,
            market_model=program.market_model,
            indication=indication,
            pos_adjusters=program.pos_adjusters,
            design_adjusters=program.design_features,
            mc_params=mc_params,
            apply_pos_model=apply_pos_model,
            apply_design_model=apply_design_model,
            analyst_notes=analyst_notes,
            config_path=config_path,
            limitations=limitations,
            thesis_changers=thesis_changers,
        )
        engine._commercial_plan = program.commercial_plan
        engine._deal_economics = program.deal_economics
        return engine

    def run(self) -> ValuationOutput:
        """Execute the full valuation pipeline."""
        trials = self._prepare_trials()

        # --- Auto-select SG&A profile and resolve effective market model ---
        market_model = self._resolve_market_model_with_sgna()

        # --- Compliance warning for gene/cell therapy ---
        self._check_compliance_rate()

        # --- Four-engine base-case rNPV ---
        # CommercialPlan has three states:
        #   "unset"      → no explicit plan; fetch default from AssumptionsLoader
        #   "suppressed" → no_loe() was called; apply no tail
        #   "modality:*" → explicit profile loaded via from_modality()
        plan = self._commercial_plan
        if plan is None or plan.is_unset:
            from bve.config.assumptions_loader import AssumptionsLoader
            loe_profile = AssumptionsLoader.get().loe_erosion_profile(self.asset.modality.value)
        else:
            loe_profile = plan.loe_profile  # None for suppressed, dict for loaded
        deal = self._deal_economics
        prob = ProbabilityModel.compute(self.asset, trials)
        rev = RevenueModel.compute(market_model, loe_profile=loe_profile)
        post_rd = self.asset.post_approval_rd_millions
        cost = CostModel.compute(prob, self.asset.discount_rate, deal=deal,
                                 post_approval_rd_millions=post_rd)
        rnpv = RNPVModel.compute(self.asset, prob, rev, cost, deal=deal)

        # --- Company NAV ---
        ownership = self.company.ownership_of(self.asset.id)
        nav = rnpv.rnpv_millions * ownership + self.company.net_cash_millions
        nav_ps = nav / self.company.shares_outstanding_millions
        rnpv = rnpv.model_copy(update={"nav_millions": nav, "nav_per_share": nav_ps})

        # --- Scenarios ---
        scenarios = build_scenarios(
            self.asset, trials, market_model,
            net_cash_millions=self.company.net_cash_millions,
            shares_outstanding_millions=self.company.shares_outstanding_millions,
            loe_profile=loe_profile,
            deal=deal,
        )

        # --- Monte Carlo ---
        mc = run_monte_carlo(
            self.asset, trials, market_model, self.mc_params,
            loe_profile=loe_profile, deal=deal,
        )
        mc_nav_per_share = (mc.mean_millions + self.company.net_cash_millions) / self.company.shares_outstanding_millions
        mc = mc.model_copy(update={"mean_nav_per_share": round(mc_nav_per_share, 2)})

        # --- Sensitivity ---
        sensitivities = self._compute_sensitivities(trials, loe_profile, deal, market_model)

        # --- Assumption log ---
        assumption_log = build_assumption_log(
            self.asset, trials, self.market_model, rnpv,
            limitations=self.limitations,
            thesis_changers=self.thesis_changers,
            sources=self.sources,
        )

        # --- Lifecycle events summary (for valuation.json and memo rendering) ---
        lifecycle_events_applied = self._build_lifecycle_events_applied()

        return ValuationOutput(
            asset=self.asset,
            company=self.company,
            trials=trials,
            market_model=market_model,
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
            lifecycle_events_applied=lifecycle_events_applied,
        )

    # -----------------------------------------------------------------------
    # Trial preparation (POS + design model layers)
    # -----------------------------------------------------------------------

    def _prepare_trials(self) -> list[ClinicalTrial]:
        trials = self.trials
        if self.apply_pos_model and self.pos_adjusters:
            trials = apply_pos_to_trials(
                trials, self.asset.therapeutic_area, self.pos_adjusters,
                approval_pathway=self.asset.approval_pathway,
            )
        if self.apply_design_model and self.design_adjusters:
            trials = self._apply_design_adjustments(trials)
        return trials

    def _apply_design_adjustments(self, trials: list[ClinicalTrial]) -> list[ClinicalTrial]:
        """Apply trial design feature adjustments as the second POS layer."""
        from bve.models.trial_design_features import check_pos_layer_overlap, compute_design_adjusted_pos

        result = []
        for trial in trials:
            features = self.design_adjusters.get(trial.phase)
            if features is None:
                result.append(trial)
                continue

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

    # -----------------------------------------------------------------------
    # Lifecycle events summary
    # -----------------------------------------------------------------------

    def _build_lifecycle_events_applied(self) -> list[dict]:
        """Serialize lifecycle events from market_model into output dicts."""
        events = getattr(self.market_model, "lifecycle_events", None)
        if not events:
            return []
        result = []
        for e in events:
            if e.event_type == "new_formulation":
                effect = f"LOE +{e.loe_delay_years} yr{'s' if e.loe_delay_years != 1 else ''}"
            elif e.event_type in ("label_expansion", "combination_therapy"):
                parts = []
                if e.tam_expansion_factor != 1.0:
                    parts.append(f"TAM \u00d7{e.tam_expansion_factor:.2f}")
                if e.penetration_boost:
                    parts.append(f"pen +{e.penetration_boost:.0%}")
                effect = ", ".join(parts) if parts else "no effect"
            else:
                effect = e.event_type
            result.append({
                "year": e.trigger_year,
                "type": e.event_type,
                "label": e.label or "",
                "effect": effect,
            })
        return result

    # -----------------------------------------------------------------------
    # Sensitivity (tornado) — still uses compute_rnpv() wrapper
    # This is architectural debt; will be refactored in a later step.
    # -----------------------------------------------------------------------

    def _compute_sensitivities(
        self,
        trials: list[ClinicalTrial],
        loe_profile: Optional[dict],
        deal,
        market_model: Optional[MarketModel] = None,
    ) -> list[SensitivityPoint]:
        """Tornado analysis: vary one parameter at a time ±30% / ±1σ."""
        sensitivities = []
        mm = market_model or self.market_model

        def _rnpv(asset=None, trials_=None, market=None) -> float:
            a = asset or self.asset
            t = trials_ or trials
            m = market or mm
            return compute_rnpv_full(a, t, m, loe_profile=loe_profile, deal=deal).rnpv_millions

        _rnpv()

        # 1. Peak sales ±30%
        if mm.total_addressable_market_millions is not None:
            tam = mm.total_addressable_market_millions
            m_lo = mm.model_copy(update={"total_addressable_market_millions": tam * 0.70, "uptake_curve": None})
            m_hi = mm.model_copy(update={"total_addressable_market_millions": tam * 1.30, "uptake_curve": None})
        else:
            price = mm.net_price_per_patient_usd or 100_000
            m_lo = mm.model_copy(update={"net_price_per_patient_usd": price * 0.70, "uptake_curve": None})
            m_hi = mm.model_copy(update={"net_price_per_patient_usd": price * 1.30, "uptake_curve": None})

        sensitivities.append(SensitivityPoint(
            parameter="Peak Sales (±30%)",
            low_value=mm.peak_sales_millions * 0.70,
            high_value=mm.peak_sales_millions * 1.30,
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
        pl = mm.patent_life_years
        m_lo = mm.model_copy(update={"patent_life_years": max(1, pl - 3), "uptake_curve": None})
        m_hi = mm.model_copy(update={"patent_life_years": pl + 3, "uptake_curve": None})
        sensitivities.append(SensitivityPoint(
            parameter="Patent Life (±3 yrs)",
            low_value=pl - 3,
            high_value=pl + 3,
            low_rnpv=_rnpv(market=m_lo),
            high_rnpv=_rnpv(market=m_hi),
        ))

        # 5. Peak penetration ±30%
        pen = mm.peak_penetration
        m_lo = mm.model_copy(update={"peak_penetration": max(0.01, pen * 0.70), "uptake_curve": None})
        m_hi = mm.model_copy(update={"peak_penetration": min(0.99, pen * 1.30), "uptake_curve": None})
        sensitivities.append(SensitivityPoint(
            parameter="Peak Penetration (±30%)",
            low_value=pen * 0.70,
            high_value=pen * 1.30,
            low_rnpv=_rnpv(market=m_lo),
            high_rnpv=_rnpv(market=m_hi),
        ))

        # 6. Effective tax rate ±5pp (e.g. 16% to 26% around 21% base)
        tax = self.asset.effective_tax_rate
        a_lo_tax = self.asset.model_copy(update={"effective_tax_rate": max(0.0, tax - 0.05)})
        a_hi_tax = self.asset.model_copy(update={"effective_tax_rate": min(0.50, tax + 0.05)})
        sensitivities.append(SensitivityPoint(
            parameter="Eff. Tax Rate (±5pp)",
            low_value=(tax - 0.05) * 100,
            high_value=(tax + 0.05) * 100,
            low_rnpv=_rnpv(asset=a_lo_tax),   # lower tax → higher NPV
            high_rnpv=_rnpv(asset=a_hi_tax),
        ))

        # Sort by |swing| descending (tornado order)
        sensitivities.sort(key=lambda s: abs(s.swing), reverse=True)
        return sensitivities

    # -----------------------------------------------------------------------
    # SG&A profile auto-selection (Sprint 9.7)
    # -----------------------------------------------------------------------

    def _resolve_market_model_with_sgna(self) -> MarketModel:
        """
        Return the market model with an auto-selected SG&A profile when the asset
        modality/TA warrants a non-default profile and the market model is using
        default SG&A rates.

        Gene/cell therapy: launch 0.55, mature 0.28, ramp 7yr.
        Rare disease: launch 0.45, mature 0.22, ramp 4yr.
        All others: specialty_pharma (0.40/0.20/5yr) = same as current default.

        Suppressed when the market model has non-default SG&A rates (explicit override).
        """
        from bve.config.constants import SGNA_RATE_LAUNCH, SGNA_RATE_MATURE

        mm = self.market_model
        # Detect non-default (explicitly overridden) SG&A — skip auto-selection
        if mm.sgna_rate_launch != SGNA_RATE_LAUNCH or mm.sgna_rate_mature != SGNA_RATE_MATURE:
            return mm

        modality = self.asset.modality
        ta = self.asset.therapeutic_area

        if modality in (Modality.GENE_THERAPY, Modality.CELL_THERAPY):
            profile_name: Optional[str] = "gene_cell_therapy"
        elif ta == TherapeuticArea.RARE_DISEASE:
            profile_name = "rare_disease"
        else:
            return mm  # specialty_pharma == current default; no change needed

        from bve.config.assumptions_loader import AssumptionsLoader
        profile = AssumptionsLoader.get().sgna_profile(profile_name)
        warnings.warn(
            f"Asset '{self.asset.id}' ({modality.value}/{ta.value}): "
            f"auto-selected SG&A profile '{profile_name}' "
            f"(launch={float(profile['rate_launch']):.0%}, "
            f"mature={float(profile['rate_mature']):.0%}, "
            f"ramp={int(profile['ramp_years'])}yr). "
            "Set sgna_rate_launch/sgna_rate_mature explicitly to suppress.",
            UserWarning,
            stacklevel=3,
        )
        return mm.model_copy(update={
            "sgna_rate_launch": float(profile["rate_launch"]),
            "sgna_rate_mature": float(profile["rate_mature"]),
            "sgna_ramp_years": int(profile["ramp_years"]),
        })

    # -----------------------------------------------------------------------
    # Compliance rate advisory (Sprint 9.6)
    # -----------------------------------------------------------------------

    def _check_compliance_rate(self) -> None:
        """Warn when gene/cell therapy assets use a compliance_rate < 1.0."""
        if self.asset.modality not in (Modality.GENE_THERAPY, Modality.CELL_THERAPY):
            return
        if self.market_model.lines_of_therapy:
            return  # LOT segments manage compliance individually
        if self.market_model.compliance_rate < 1.0:
            warnings.warn(
                f"Asset '{self.asset.id}' is {self.asset.modality.value} "
                f"(single-administration). compliance_rate="
                f"{self.market_model.compliance_rate} — consider setting to 1.0 "
                "since there is no ongoing adherence for a one-time therapy.",
                UserWarning,
                stacklevel=3,
            )
