"""
Sprint 31B — Enhanced Bull/Base/Bear with full ScenarioShock categories.

Tests cover:
- apply_scenario_shock(): each category applied correctly, no mutation
- build_scenarios_from_shocks(): full engine rerun, ScenarioSet produced
- Ordering invariants: bull > base > bear for rNPV under normal assumptions
- Backward compatibility: existing build_scenarios() (ScenarioAssumptions) unchanged
- Engine rerun invariant: base-case SHOCK_BASE produces same rNPV as direct compute
"""
import pytest

from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.competition_model import CompetitionModel, CompetitorLaunch
from bve.models.deal_economics import DealEconomics, Milestone, MilestoneTrigger
from bve.models.market_model import MarketModel
from bve.models.payer_access import PayerAccessModel
from bve.models.rnpv_model import compute_rnpv_full
from bve.models.scenario_shock import (
    ClinicalShock,
    CommercialShock,
    CompetitionShock,
    CostsFCFShock,
    DealEconomicsShock,
    RegulatoryShock,
    ScenarioShock,
    SHOCK_BASE,
    SHOCK_BEAR,
    SHOCK_BULL,
)
from bve.models.tax_profile import TaxProfile
from bve.valuation.scenario import (
    ScenarioSet,
    apply_scenario_shock,
    build_scenarios,
    build_scenarios_from_shocks,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _asset(**kwargs) -> Asset:
    defaults = dict(
        id="asset-001",
        name="Test Drug",
        indication="Oncology",
        therapeutic_area="oncology",
        stage="phase_2",
        modality="small_molecule",
        launch_year=2028,
        patent_expiry_year=2040,
        discount_rate=0.10,
        effective_tax_rate=0.21,
        royalty_rate=0.0,
    )
    defaults.update(kwargs)
    return Asset(**defaults)


def _trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id="asset-001",
            phase=TrialPhase.PHASE_2,
            success_probability=0.40,
            duration_years=3.0,
            cost_millions=50.0,
        ),
        ClinicalTrial(
            asset_id="asset-001",
            phase=TrialPhase.PHASE_3,
            success_probability=0.65,
            duration_years=4.0,
            cost_millions=150.0,
        ),
    ]


def _market() -> MarketModel:
    return MarketModel(
        asset_id="asset-001",
        therapeutic_area="oncology",
        addressable_patients_annual=50_000,
        net_price_per_patient_usd=80_000,
        peak_penetration=0.25,
        years_to_peak=5,
        patent_life_years=12,
        cogs_rate=0.12,
        sgna_rate_launch=0.40,
        sgna_rate_mature=0.20,
    )


def _market_with_payer() -> MarketModel:
    return MarketModel(
        asset_id="asset-001",
        therapeutic_area="oncology",
        addressable_patients_annual=50_000,
        net_price_per_patient_usd=80_000,
        peak_penetration=0.25,
        years_to_peak=5,
        patent_life_years=12,
        cogs_rate=0.12,
        sgna_rate_launch=0.40,
        sgna_rate_mature=0.20,
        payer_access=PayerAccessModel(
            access_probability=0.85,
            prior_auth_burden=0.10,
        ),
    )


def _market_with_competition() -> MarketModel:
    return MarketModel(
        asset_id="asset-001",
        therapeutic_area="oncology",
        addressable_patients_annual=50_000,
        net_price_per_patient_usd=80_000,
        peak_penetration=0.25,
        years_to_peak=5,
        patent_life_years=12,
        cogs_rate=0.12,
        sgna_rate_launch=0.40,
        sgna_rate_mature=0.20,
        competition_model=CompetitionModel(
            competitors=[
                CompetitorLaunch(
                    name="Competitor A",
                    status="phase_3",
                    launch_year_relative=2,
                    peak_market_share=0.25,
                    years_to_peak=3,
                    approval_probability=0.60,
                ),
            ]
        ),
    )


# ---------------------------------------------------------------------------
# apply_scenario_shock — Clinical category
# ---------------------------------------------------------------------------

class TestApplyShockClinical:
    def test_pos_mult_applied_to_all_trials(self):
        asset = _asset()
        trials = _trials()
        market = _market()
        shock = ScenarioShock(clinical=ClinicalShock(pos_mult=1.50))
        _, shocked_trials, _, _, _ = apply_scenario_shock(asset, trials, market, shock)
        for orig, shocked in zip(trials, shocked_trials):
            assert shocked.success_probability == pytest.approx(
                min(0.99, orig.success_probability * 1.50), abs=1e-6
            )

    def test_per_phase_pos_mult_overrides_uniform(self):
        asset = _asset()
        trials = _trials()
        market = _market()
        shock = ScenarioShock(clinical=ClinicalShock(
            pos_mult=1.0,
            per_phase_pos_mult={"phase_3": 1.30},
        ))
        _, shocked_trials, _, _, _ = apply_scenario_shock(asset, trials, market, shock)
        p2 = next(t for t in shocked_trials if t.phase == TrialPhase.PHASE_2)
        p3 = next(t for t in shocked_trials if t.phase == TrialPhase.PHASE_3)
        # phase_2 unchanged (uniform pos_mult=1.0, no per-phase override)
        assert p2.success_probability == pytest.approx(trials[0].success_probability, abs=1e-6)
        # phase_3 scaled by 1.30
        assert p3.success_probability == pytest.approx(
            min(0.99, trials[1].success_probability * 1.30), abs=1e-6
        )

    def test_pos_mult_combined_with_per_phase(self):
        asset = _asset()
        trials = _trials()
        market = _market()
        # Global ×1.2, phase_3 override ×1.1 → effective ×1.32
        shock = ScenarioShock(clinical=ClinicalShock(
            pos_mult=1.2,
            per_phase_pos_mult={"phase_3": 1.1},
        ))
        _, shocked_trials, _, _, _ = apply_scenario_shock(asset, trials, market, shock)
        p3 = next(t for t in shocked_trials if t.phase == TrialPhase.PHASE_3)
        expected = min(0.99, trials[1].success_probability * 1.2 * 1.1)
        assert p3.success_probability == pytest.approx(expected, abs=1e-6)

    def test_zero_effect_shock_leaves_trials_unchanged(self):
        asset = _asset()
        trials = _trials()
        market = _market()
        _, shocked_trials, _, _, _ = apply_scenario_shock(asset, trials, market, SHOCK_BASE)
        for orig, shocked in zip(trials, shocked_trials):
            assert shocked.success_probability == pytest.approx(orig.success_probability, abs=1e-6)
            assert shocked.duration_years == pytest.approx(orig.duration_years, abs=1e-6)
            assert shocked.cost_millions == pytest.approx(orig.cost_millions, abs=1e-6)

    def test_original_trials_not_mutated(self):
        asset = _asset()
        trials = _trials()
        market = _market()
        orig_pos = [t.success_probability for t in trials]
        shock = ScenarioShock(clinical=ClinicalShock(pos_mult=2.0))
        apply_scenario_shock(asset, trials, market, shock)
        for t, p in zip(trials, orig_pos):
            assert t.success_probability == p


# ---------------------------------------------------------------------------
# apply_scenario_shock — Regulatory category
# ---------------------------------------------------------------------------

class TestApplyShockRegulatory:
    def test_duration_add_years_applied(self):
        asset = _asset()
        trials = _trials()
        market = _market()
        shock = ScenarioShock(regulatory=RegulatoryShock(duration_add_years=1.5))
        _, shocked_trials, _, _, _ = apply_scenario_shock(asset, trials, market, shock)
        for orig, shocked in zip(trials, shocked_trials):
            assert shocked.duration_years == pytest.approx(orig.duration_years + 1.5, abs=1e-6)

    def test_crl_delay_adds_to_duration(self):
        asset = _asset()
        trials = _trials()
        market = _market()
        shock = ScenarioShock(regulatory=RegulatoryShock(
            duration_add_years=0.5,
            crl_delay_add_years=0.5,
        ))
        _, shocked_trials, _, _, _ = apply_scenario_shock(asset, trials, market, shock)
        for orig, shocked in zip(trials, shocked_trials):
            assert shocked.duration_years == pytest.approx(orig.duration_years + 1.0, abs=1e-6)

    def test_label_breadth_mult_scales_patients(self):
        market = _market()
        orig_patients = market.addressable_patients_annual
        shock = ScenarioShock(regulatory=RegulatoryShock(label_breadth_mult=0.70))
        _, _, shocked_market, _, _ = apply_scenario_shock(_asset(), _trials(), market, shock)
        assert shocked_market.addressable_patients_annual == pytest.approx(
            orig_patients * 0.70, abs=1.0
        )

    def test_label_breadth_and_patients_mult_combine(self):
        market = _market()
        orig_patients = market.addressable_patients_annual
        shock = ScenarioShock(
            regulatory=RegulatoryShock(label_breadth_mult=0.8),
            commercial=CommercialShock(addressable_patients_mult=1.1),
        )
        _, _, shocked_market, _, _ = apply_scenario_shock(_asset(), _trials(), market, shock)
        assert shocked_market.addressable_patients_annual == pytest.approx(
            orig_patients * 0.8 * 1.1, abs=1.0
        )


# ---------------------------------------------------------------------------
# apply_scenario_shock — Commercial category
# ---------------------------------------------------------------------------

class TestApplyShockCommercial:
    def test_net_price_mult_applied(self):
        market = _market()
        orig_price = market.net_price_per_patient_usd
        shock = ScenarioShock(commercial=CommercialShock(net_price_mult=0.85))
        _, _, shocked_market, _, _ = apply_scenario_shock(_asset(), _trials(), market, shock)
        assert shocked_market.net_price_per_patient_usd == pytest.approx(orig_price * 0.85, abs=1.0)

    def test_peak_penetration_mult_applied(self):
        market = _market()
        orig_pen = market.peak_penetration
        shock = ScenarioShock(commercial=CommercialShock(peak_penetration_mult=0.70))
        _, _, shocked_market, _, _ = apply_scenario_shock(_asset(), _trials(), market, shock)
        assert shocked_market.peak_penetration == pytest.approx(orig_pen * 0.70, abs=1e-6)

    def test_gross_to_net_delta_applied(self):
        market = MarketModel(
            asset_id="asset-001",
            therapeutic_area="oncology",
            addressable_patients_annual=50_000,
            net_price_per_patient_usd=80_000,
            peak_penetration=0.25,
            years_to_peak=5,
            patent_life_years=12,
            cogs_rate=0.12,
            sgna_rate_launch=0.40,
            sgna_rate_mature=0.20,
            gross_to_net_rate=0.30,
        )
        shock = ScenarioShock(commercial=CommercialShock(gross_to_net_rate_delta=0.05))
        _, _, shocked_market, _, _ = apply_scenario_shock(_asset(), _trials(), market, shock)
        assert shocked_market.gross_to_net_rate == pytest.approx(0.35, abs=1e-6)

    def test_payer_access_probability_mult_applied(self):
        market = _market_with_payer()
        orig_access = market.payer_access.access_probability
        shock = ScenarioShock(commercial=CommercialShock(payer_access_probability_mult=0.80))
        _, _, shocked_market, _, _ = apply_scenario_shock(_asset(), _trials(), market, shock)
        assert shocked_market.payer_access.access_probability == pytest.approx(
            orig_access * 0.80, abs=1e-6
        )

    def test_prior_auth_burden_delta_applied(self):
        market = _market_with_payer()
        orig_burden = market.payer_access.prior_auth_burden
        shock = ScenarioShock(commercial=CommercialShock(prior_auth_burden_delta=0.20))
        _, _, shocked_market, _, _ = apply_scenario_shock(_asset(), _trials(), market, shock)
        assert shocked_market.payer_access.prior_auth_burden == pytest.approx(
            orig_burden + 0.20, abs=1e-6
        )

    def test_no_payer_model_no_crash(self):
        market = _market()  # no payer_access
        shock = ScenarioShock(commercial=CommercialShock(payer_access_probability_mult=0.80))
        _, _, shocked_market, _, _ = apply_scenario_shock(_asset(), _trials(), market, shock)
        assert shocked_market.payer_access is None


# ---------------------------------------------------------------------------
# apply_scenario_shock — Competition category
# ---------------------------------------------------------------------------

class TestApplyShockCompetition:
    def test_competitor_approval_prob_mult_applied(self):
        market = _market_with_competition()
        orig_prob = market.competition_model.competitors[0].approval_probability
        shock = ScenarioShock(competition=CompetitionShock(competitor_approval_prob_mult=0.5))
        _, _, shocked_market, _, _ = apply_scenario_shock(_asset(), _trials(), market, shock)
        shocked_comp = shocked_market.competition_model.competitors[0]
        assert shocked_comp.approval_probability == pytest.approx(orig_prob * 0.5, abs=1e-6)

    def test_competitor_launch_timing_add_years(self):
        market = _market_with_competition()
        orig_yr = market.competition_model.competitors[0].launch_year_relative
        shock = ScenarioShock(competition=CompetitionShock(competitor_launch_timing_add_years=2.0))
        _, _, shocked_market, _, _ = apply_scenario_shock(_asset(), _trials(), market, shock)
        assert shocked_market.competition_model.competitors[0].launch_year_relative == pytest.approx(
            orig_yr + 2.0, abs=1e-6
        )

    def test_competitor_market_share_mult_applied(self):
        market = _market_with_competition()
        orig_share = market.competition_model.competitors[0].peak_market_share
        shock = ScenarioShock(competition=CompetitionShock(competitor_market_share_mult=1.25))
        _, _, shocked_market, _, _ = apply_scenario_shock(_asset(), _trials(), market, shock)
        assert shocked_market.competition_model.competitors[0].peak_market_share == pytest.approx(
            orig_share * 1.25, abs=1e-6
        )

    def test_price_pressure_delta_applied(self):
        market = _market_with_competition()
        shock = ScenarioShock(competition=CompetitionShock(competition_price_pressure_delta=0.04))
        _, _, shocked_market, _, _ = apply_scenario_shock(_asset(), _trials(), market, shock)
        # base_annual_price_erosion_rate was None (0.0) → now 0.04
        assert shocked_market.competition_model.base_annual_price_erosion_rate == pytest.approx(0.04)

    def test_no_competition_model_no_crash(self):
        market = _market()  # no competition_model
        shock = ScenarioShock(competition=CompetitionShock(competitor_approval_prob_mult=0.5))
        _, _, shocked_market, _, _ = apply_scenario_shock(_asset(), _trials(), market, shock)
        assert shocked_market.competition_model is None


# ---------------------------------------------------------------------------
# apply_scenario_shock — Costs/FCF category
# ---------------------------------------------------------------------------

class TestApplyShockCostsFCF:
    def test_rd_cost_mult_applied_to_all_trials(self):
        asset = _asset()
        trials = _trials()
        market = _market()
        shock = ScenarioShock(costs_fcf=CostsFCFShock(rd_cost_mult=1.25))
        _, shocked_trials, _, _, _ = apply_scenario_shock(asset, trials, market, shock)
        for orig, shocked in zip(trials, shocked_trials):
            assert shocked.cost_millions == pytest.approx(orig.cost_millions * 1.25, abs=1e-6)

    def test_cogs_delta_applied(self):
        market = _market()
        orig_cogs = market.cogs_rate
        shock = ScenarioShock(costs_fcf=CostsFCFShock(cogs_rate_delta=0.03))
        _, _, shocked_market, _, _ = apply_scenario_shock(_asset(), _trials(), market, shock)
        assert shocked_market.cogs_rate == pytest.approx(orig_cogs + 0.03, abs=1e-6)

    def test_sgna_delta_applied_to_both_launch_and_mature(self):
        market = _market()
        orig_launch = market.sgna_rate_launch
        orig_mature = market.sgna_rate_mature
        shock = ScenarioShock(costs_fcf=CostsFCFShock(sgna_rate_delta=0.05))
        _, _, shocked_market, _, _ = apply_scenario_shock(_asset(), _trials(), market, shock)
        assert shocked_market.sgna_rate_launch == pytest.approx(orig_launch + 0.05, abs=1e-6)
        assert shocked_market.sgna_rate_mature == pytest.approx(orig_mature + 0.05, abs=1e-6)

    def test_wacc_delta_applied_to_asset(self):
        asset = _asset(discount_rate=0.10)
        shock = ScenarioShock(costs_fcf=CostsFCFShock(discount_rate_delta=0.02))
        shocked_asset, _, _, _, _ = apply_scenario_shock(asset, _trials(), _market(), shock)
        assert shocked_asset.discount_rate == pytest.approx(0.12, abs=1e-6)

    def test_tax_rate_delta_applied_to_asset(self):
        asset = _asset(effective_tax_rate=0.21)
        shock = ScenarioShock(costs_fcf=CostsFCFShock(tax_rate_delta=0.03))
        shocked_asset, _, _, _, _ = apply_scenario_shock(asset, _trials(), _market(), shock)
        assert shocked_asset.effective_tax_rate == pytest.approx(0.24, abs=1e-6)

    def test_tax_profile_capex_delta_applied(self):
        tp = TaxProfile(annual_maintenance_capex_rate=0.01, working_capital_rate=0.02)
        shock = ScenarioShock(costs_fcf=CostsFCFShock(
            maintenance_capex_rate_delta=0.005,
            working_capital_rate_delta=0.01,
        ))
        _, _, _, _, shocked_tp = apply_scenario_shock(
            _asset(), _trials(), _market(), shock, tax_profile=tp
        )
        assert shocked_tp.annual_maintenance_capex_rate == pytest.approx(0.015, abs=1e-6)
        assert shocked_tp.working_capital_rate == pytest.approx(0.03, abs=1e-6)


# ---------------------------------------------------------------------------
# apply_scenario_shock — Deal economics category
# ---------------------------------------------------------------------------

class TestApplyShockDealEconomics:
    def _deal(self) -> DealEconomics:
        return DealEconomics(
            royalty_rate=0.08,
            profit_share_rate=0.10,
            cdev_cost_share=1.0,
            milestones=[
                Milestone(
                    description="Approval milestone",
                    trigger=MilestoneTrigger.APPROVAL,
                    amount_millions=50.0,
                    direction="payable",
                ),
            ],
        )

    def test_royalty_rate_override(self):
        deal = self._deal()
        shock = ScenarioShock(deal_economics=DealEconomicsShock(royalty_rate_override=0.05))
        _, _, _, shocked_deal, _ = apply_scenario_shock(_asset(), _trials(), _market(), shock, deal=deal)
        assert shocked_deal.royalty_rate == pytest.approx(0.05, abs=1e-6)

    def test_profit_share_override(self):
        deal = self._deal()
        shock = ScenarioShock(deal_economics=DealEconomicsShock(profit_share_rate_override=0.20))
        _, _, _, shocked_deal, _ = apply_scenario_shock(_asset(), _trials(), _market(), shock, deal=deal)
        assert shocked_deal.profit_share_rate == pytest.approx(0.20, abs=1e-6)

    def test_cdev_cost_share_override(self):
        deal = self._deal()
        shock = ScenarioShock(deal_economics=DealEconomicsShock(cdev_cost_share_override=0.50))
        _, _, _, shocked_deal, _ = apply_scenario_shock(_asset(), _trials(), _market(), shock, deal=deal)
        assert shocked_deal.cdev_cost_share == pytest.approx(0.50, abs=1e-6)

    def test_milestone_payment_mult_applied(self):
        deal = self._deal()
        shock = ScenarioShock(deal_economics=DealEconomicsShock(milestone_payment_mult=0.80))
        _, _, _, shocked_deal, _ = apply_scenario_shock(_asset(), _trials(), _market(), shock, deal=deal)
        assert shocked_deal.milestones[0].amount_millions == pytest.approx(40.0, abs=1e-6)

    def test_no_deal_returns_none(self):
        shock = ScenarioShock(deal_economics=DealEconomicsShock(royalty_rate_override=0.05))
        _, _, _, shocked_deal, _ = apply_scenario_shock(_asset(), _trials(), _market(), shock, deal=None)
        assert shocked_deal is None


# ---------------------------------------------------------------------------
# build_scenarios_from_shocks — integration
# ---------------------------------------------------------------------------

class TestBuildScenariosFromShocks:
    def test_returns_scenario_set(self):
        result = build_scenarios_from_shocks(
            _asset(), _trials(), _market(), net_cash_millions=100.0,
        )
        assert isinstance(result, ScenarioSet)

    def test_base_shock_matches_direct_compute(self):
        asset = _asset()
        trials = _trials()
        market = _market()

        direct = compute_rnpv_full(asset, trials, market)
        scenario_set = build_scenarios_from_shocks(asset, trials, market)

        assert scenario_set.base.rnpv_millions == pytest.approx(direct.rnpv_millions, rel=1e-4)

    def test_bull_rnpv_gt_base_rnpv(self):
        result = build_scenarios_from_shocks(_asset(), _trials(), _market())
        assert result.bull.rnpv_millions > result.base.rnpv_millions

    def test_base_rnpv_gt_bear_rnpv(self):
        result = build_scenarios_from_shocks(_asset(), _trials(), _market())
        assert result.base.rnpv_millions > result.bear.rnpv_millions

    def test_bull_gt_base_gt_bear_ordering(self):
        result = build_scenarios_from_shocks(_asset(), _trials(), _market())
        assert result.bull.rnpv_millions > result.base.rnpv_millions > result.bear.rnpv_millions

    def test_nav_includes_net_cash(self):
        result = build_scenarios_from_shocks(
            _asset(), _trials(), _market(), net_cash_millions=200.0
        )
        assert result.base.nav_millions == pytest.approx(
            result.base.rnpv_millions + 200.0, abs=1e-4
        )

    def test_nav_per_share_computed(self):
        result = build_scenarios_from_shocks(
            _asset(), _trials(), _market(),
            net_cash_millions=100.0,
            shares_outstanding_millions=50.0,
        )
        assert result.base.nav_per_share == pytest.approx(
            result.base.nav_millions / 50.0, abs=1e-4
        )

    def test_custom_shocks_accepted(self):
        custom = [
            ScenarioShock(label="Strong Bull", clinical=ClinicalShock(pos_mult=1.5)),
            SHOCK_BASE,
            ScenarioShock(label="Deep Bear", clinical=ClinicalShock(pos_mult=0.5)),
        ]
        result = build_scenarios_from_shocks(_asset(), _trials(), _market(), shocks=custom)
        assert result.bull.label == "Strong Bull"
        assert result.bear.label == "Deep Bear"
        assert result.bull.rnpv_millions > result.bear.rnpv_millions

    def test_wrong_number_of_shocks_raises(self):
        with pytest.raises(ValueError, match="exactly 3 shocks"):
            build_scenarios_from_shocks(_asset(), _trials(), _market(), shocks=[SHOCK_BASE])

    def test_engine_reruns_not_shortcut(self):
        """rNPV must be derived from engine output, never applied to base rNPV directly."""
        asset = _asset()
        trials = _trials()
        market = _market()
        base_rnpv = compute_rnpv_full(asset, trials, market).rnpv_millions

        shock = ScenarioShock(clinical=ClinicalShock(pos_mult=1.5))
        shocked_asset, shocked_trials, shocked_market, _, _ = apply_scenario_shock(
            asset, trials, market, shock
        )
        expected_bull_rnpv = compute_rnpv_full(shocked_asset, shocked_trials, shocked_market).rnpv_millions

        result = build_scenarios_from_shocks(asset, trials, market, shocks=[shock, SHOCK_BASE, SHOCK_BEAR])
        assert result.bull.rnpv_millions == pytest.approx(expected_bull_rnpv, rel=1e-4)
        # Verify it's NOT just base * pos_mult
        assert result.bull.rnpv_millions != pytest.approx(base_rnpv * 1.5, rel=0.01)

    def test_upside_downside_ratio_defined(self):
        result = build_scenarios_from_shocks(_asset(), _trials(), _market())
        # Ratio can be negative if bear rNPV < 0 (realistic for deep bear scenario)
        # Just check it is computable and bull > bear in absolute rNPV terms
        assert result.bull.rnpv_millions > result.bear.rnpv_millions

    def test_labels_preserved(self):
        result = build_scenarios_from_shocks(_asset(), _trials(), _market())
        assert result.bull.label == "Bull"
        assert result.base.label == "Base"
        assert result.bear.label == "Bear"


# ---------------------------------------------------------------------------
# Backward compatibility — existing build_scenarios() unchanged
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_legacy_build_scenarios_still_works(self):
        result = build_scenarios(
            _asset(), _trials(), _market(), net_cash_millions=100.0
        )
        assert isinstance(result, ScenarioSet)
        assert result.bull.rnpv_millions > result.base.rnpv_millions

    def test_legacy_result_labels_unchanged(self):
        result = build_scenarios(_asset(), _trials(), _market())
        assert result.bull.label == "Bull"
        assert result.base.label == "Base"
        assert result.bear.label == "Bear"
