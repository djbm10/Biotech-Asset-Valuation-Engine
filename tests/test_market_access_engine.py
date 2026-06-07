from __future__ import annotations

from bve.intelligence.market_access_engine import (
    MarketAccessAssessmentValue,
    MarketAccessEngine,
)
from bve.intelligence.science_engine import ScienceAssessment, ScienceSubscore
from bve.models.commercial_inputs import CommercialInputs, PatientPool, PricingModel, ShareModel
from bve.models.market_access import (
    CostEffectivenessRisk,
    FormularyTier,
    PayerDynamics,
    PriorAuthBurden,
)
from bve.models.probability_stack import ProbabilityStackInputs
from bve.models.regulatory_inference import (
    ApprovalPathway,
    RegulatoryInferenceResult,
    RegulatoryProfile,
    RegulatoryScenario,
    RegulatoryScenarioProbability,
)


def _commercial_inputs() -> CommercialInputs:
    return CommercialInputs(
        patient_pool=PatientPool(
            indication="mBC",
            prevalence_thousands=120.0,
            diagnosed_fraction=0.80,
            eligible_rate=0.35,
            treated_fraction=0.70,
            uncertainty_cv=0.20,
        ),
        pricing=PricingModel.from_wac(
            wac_per_year_usd=180000.0,
            gross_to_net_rate=0.25,
            launch_discount=0.08,
            annual_erosion_rate=0.03,
        ),
        share=ShareModel(
            peak_share=0.24,
            years_to_peak=5,
            share_cv=0.18,
        ),
        ex_us_revenue_multiple=1.45,
    )


def _science_assessment() -> ScienceAssessment:
    return ScienceAssessment(
        asset_id="asset-rly2608",
        asset_name="RLY-2608",
        science_score=0.74,
        design_score=0.71,
        confidence_band="high",
        subscores=[
            ScienceSubscore(name="mechanism_plausibility", value=0.75, confidence=0.8, rationale="ok"),
            ScienceSubscore(name="target_validation", value=0.72, confidence=0.8, rationale="ok"),
            ScienceSubscore(name="modality_specific_risk", value=0.70, confidence=0.76, rationale="ok"),
            ScienceSubscore(name="biomarker_logic_quality", value=0.71, confidence=0.75, rationale="ok"),
            ScienceSubscore(name="translational_evidence_quality", value=0.68, confidence=0.72, rationale="ok"),
            ScienceSubscore(name="analog_winners_failures_similarity", value=0.67, confidence=0.71, rationale="ok"),
            ScienceSubscore(name="safety_signal_seriousness", value=0.77, confidence=0.76, rationale="ok"),
            ScienceSubscore(name="trial_design_quality", value=0.70, confidence=0.74, rationale="ok"),
        ],
        top_positives=["science"],
        top_risks=["access"],
        nearest_analogs=[],
        kill_criteria=["safety"],
        plain_english_summary="Science package.",
    )


def _regulatory_inference() -> RegulatoryInferenceResult:
    return RegulatoryInferenceResult(
        profile=RegulatoryProfile(
            approval_pathway=ApprovalPathway.PRIORITY,
            endpoint_type="surrogate_validated",
            safety_serious_events=False,
            adcom_precedent="positive",
        ),
        scenarios=[
            RegulatoryScenarioProbability(
                scenario=RegulatoryScenario.CLEAN_APPROVAL,
                probability=0.60,
                pdufa_months=6,
                rationale="clean",
            ),
            RegulatoryScenarioProbability(
                scenario=RegulatoryScenario.NARROW_LABEL,
                probability=0.18,
                pdufa_months=7,
                rationale="narrow",
            ),
            RegulatoryScenarioProbability(
                scenario=RegulatoryScenario.HIGH_POSTMARKET_BURDEN,
                probability=0.09,
                pdufa_months=8,
                rationale="burden",
            ),
            RegulatoryScenarioProbability(
                scenario=RegulatoryScenario.DELAYED_APPROVAL,
                probability=0.08,
                pdufa_months=11,
                rationale="delay",
            ),
            RegulatoryScenarioProbability(
                scenario=RegulatoryScenario.CRL,
                probability=0.05,
                pdufa_months=6,
                rationale="crl",
            ),
        ],
        dominant_scenario=RegulatoryScenario.CLEAN_APPROVAL,
        approval_probability=0.84,
        expected_pdufa_months=6.7,
        risk_flags=[],
        pos_modifier=0.03,
    )


def test_phase_h_builds_patient_funnel_and_adoption_curve() -> None:
    engine = MarketAccessEngine()
    assessment = engine.assess(
        asset_id="asset-rly2608",
        commercial_inputs=_commercial_inputs(),
        payer_dynamics=PayerDynamics(
            formulary_tier=FormularyTier.TIER_2,
            prior_auth_burden=PriorAuthBurden.LOW,
            cost_effectiveness_risk=CostEffectivenessRisk.MODERATE,
            commercial_payer_coverage_pct=0.78,
            net_price_to_list_ratio=0.76,
            list_price_usd_thousands=180.0,
        ),
        years=6,
    )

    value = MarketAccessAssessmentValue.model_validate(assessment.output.value)
    assert value.diagnosed_population > value.accessible_patient_pool
    assert value.eligible_population <= value.diagnosed_population
    assert value.reimbursed_population <= value.reachable_population
    assert len(value.adoption_curve) == 6
    assert value.adoption_curve[0].revenue_millions < value.adoption_curve[-1].revenue_millions
    assert value.net_realized_price_usd > 0
    assert value.commercial_uncertainty_low < value.commercial_uncertainty_base < value.commercial_uncertainty_high
    assert "probability_stack" in assessment.output.downstream_dependencies


def test_phase_h_challenging_access_reduces_pool_and_raises_pressure() -> None:
    engine = MarketAccessEngine()
    favorable = engine.assess(
        asset_id="asset-rly2608",
        commercial_inputs=_commercial_inputs(),
        payer_dynamics=PayerDynamics(
            formulary_tier=FormularyTier.TIER_1,
            prior_auth_burden=PriorAuthBurden.NONE,
            cost_effectiveness_risk=CostEffectivenessRisk.LOW,
            commercial_payer_coverage_pct=0.85,
            net_price_to_list_ratio=0.82,
            orphan_drug_designation=True,
        ),
    )
    challenging = engine.assess(
        asset_id="asset-rly2608",
        commercial_inputs=_commercial_inputs(),
        payer_dynamics=PayerDynamics(
            formulary_tier=FormularyTier.EXCLUDED,
            prior_auth_burden=PriorAuthBurden.HIGH,
            cost_effectiveness_risk=CostEffectivenessRisk.HIGH,
            step_edit_required=True,
            medicare_heavy_indication=True,
            net_price_to_list_ratio=0.55,
            list_price_usd_thousands=180.0,
        ),
    )

    fav = MarketAccessAssessmentValue.model_validate(favorable.output.value)
    hard = MarketAccessAssessmentValue.model_validate(challenging.output.value)
    assert hard.accessible_patient_pool < fav.accessible_patient_pool
    assert hard.net_realized_price_usd < fav.net_realized_price_usd
    assert hard.access_risk_score > fav.access_risk_score
    assert hard.medicare_negotiation_risk_score > fav.medicare_negotiation_risk_score


def test_phase_h_can_update_probability_stack_market_access_pressure() -> None:
    engine = MarketAccessEngine()
    assessment = engine.assess(
        asset_id="asset-rly2608",
        commercial_inputs=_commercial_inputs(),
        payer_dynamics=PayerDynamics(
            formulary_tier=FormularyTier.SPECIALTY,
            prior_auth_burden=PriorAuthBurden.MODERATE,
            cost_effectiveness_risk=CostEffectivenessRisk.MODERATE,
            step_edit_required=True,
            net_price_to_list_ratio=0.68,
        ),
    )
    updated = engine.apply_to_probability_stack_inputs(
        ProbabilityStackInputs(
            asset_id="asset-rly2608",
            asset_name="RLY-2608",
            base_pos=0.48,
            science_assessment=_science_assessment(),
            regulatory_inference=_regulatory_inference(),
            years_to_approval=3.0,
            financing_risk_score=0.30,
            market_access_pressure_score=0.20,
            management_execution_score=0.65,
            competitor_readthrough_score=0.55,
        ),
        assessment,
    )

    value = MarketAccessAssessmentValue.model_validate(assessment.output.value)
    assert updated.market_access_pressure_score == value.access_risk_score
    assert updated.market_access_pressure_score > 0.20
