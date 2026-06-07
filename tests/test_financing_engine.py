from __future__ import annotations

from datetime import date

from bve.entities.company import Company
from bve.entities.company_snapshot import DilutionBridge
from bve.intelligence.financing_engine import (
    FinancingAssessmentValue,
    FinancingCatalyst,
    FinancingEngine,
)
from bve.intelligence.science_engine import ScienceAssessment, ScienceSubscore
from bve.models.probability_stack import ProbabilityStackInputs
from bve.models.regulatory_inference import (
    ApprovalPathway,
    RegulatoryInferenceResult,
    RegulatoryProfile,
    RegulatoryScenario,
    RegulatoryScenarioProbability,
)


def _company() -> Company:
    return Company(
        id="company-rly",
        name="Relay",
        ticker="RLAY",
        cash_millions=180.0,
        debt_millions=25.0,
        shares_outstanding_millions=150.0,
        burn_rate_millions_per_quarter=45.0,
        current_price=4.0,
        market_cap_millions=600.0,
    )


def _science_assessment() -> ScienceAssessment:
    return ScienceAssessment(
        asset_id="asset-rly2608",
        asset_name="RLY-2608",
        science_score=0.73,
        design_score=0.71,
        confidence_band="high",
        subscores=[
            ScienceSubscore(name="mechanism_plausibility", value=0.75, confidence=0.8, rationale="ok"),
            ScienceSubscore(name="target_validation", value=0.72, confidence=0.8, rationale="ok"),
            ScienceSubscore(name="modality_specific_risk", value=0.69, confidence=0.75, rationale="ok"),
            ScienceSubscore(name="biomarker_logic_quality", value=0.70, confidence=0.75, rationale="ok"),
            ScienceSubscore(name="translational_evidence_quality", value=0.67, confidence=0.72, rationale="ok"),
            ScienceSubscore(name="analog_winners_failures_similarity", value=0.66, confidence=0.7, rationale="ok"),
            ScienceSubscore(name="safety_signal_seriousness", value=0.76, confidence=0.76, rationale="ok"),
            ScienceSubscore(name="trial_design_quality", value=0.70, confidence=0.74, rationale="ok"),
        ],
        top_positives=["science"],
        top_risks=["financing"],
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


def test_phase_g_short_runway_drives_high_pre_catalyst_financing_probability() -> None:
    engine = FinancingEngine()
    assessment = engine.assess_company(
        asset_id="asset-rly2608",
        company=_company(),
        next_catalyst=FinancingCatalyst(
            catalyst_id="cat-readout",
            label="Phase 3 readout",
            expected_date=date(2027, 8, 1),
        ),
        approval_target_date=date(2027, 9, 1),
        intrinsic_value_millions=900.0,
        market_snapshot_date=date(2026, 4, 17),
    )

    value = FinancingAssessmentValue.model_validate(assessment.output.value)
    assert value.months_of_runway == 12.0
    assert value.probability_of_pre_catalyst_financing > 0.70
    assert value.likely_raise_size_millions > 0.0
    assert value.expected_dilution_pct_base > 0.0
    assert value.financing_risk_tier in {"medium", "high", "critical"}
    assert "probability_stack" in assessment.output.downstream_dependencies


def test_phase_g_bridge_raises_dilution_floor_and_preserves_provenance() -> None:
    engine = FinancingEngine()
    bridge = DilutionBridge(
        current_shares_millions=150.0,
        expected_dilution_pct=0.18,
        financing_runway_quarters=4.0,
        atm_active=True,
        atm_remaining_millions=80.0,
        shelf_registration_millions=250.0,
        source_ref="10-Q:2026Q1",
        as_of_date=date(2026, 3, 31),
    )
    assessment = engine.assess_company(
        asset_id="asset-rly2608",
        company=_company(),
        next_catalyst=FinancingCatalyst(
            catalyst_id="cat-readout",
            label="Phase 3 readout",
            expected_date=date(2026, 10, 15),
        ),
        approval_target_date=date(2027, 6, 30),
        intrinsic_value_millions=850.0,
        market_snapshot_date=date(2026, 4, 17),
        dilution_bridge=bridge,
    )

    value = FinancingAssessmentValue.model_validate(assessment.output.value)
    assert value.expected_dilution_pct_base >= 0.18
    assert value.expected_dilution_pct_high >= value.expected_dilution_pct_base
    assert "10-Q:2026Q1" in assessment.output.provenance
    assert assessment.output.confidence > 0.50


def test_phase_g_long_runway_produces_low_financing_risk() -> None:
    engine = FinancingEngine()
    company = _company().model_copy(
        update={
            "cash_millions": 500.0,
            "burn_rate_millions_per_quarter": 30.0,
            "market_cap_millions": 1200.0,
            "current_price": 8.0,
        }
    )
    assessment = engine.assess_company(
        asset_id="asset-rly2608",
        company=company,
        next_catalyst=FinancingCatalyst(
            catalyst_id="cat-readout",
            label="Readout",
            expected_date=date(2026, 8, 1),
        ),
        approval_target_date=date(2027, 3, 1),
        intrinsic_value_millions=1500.0,
        market_snapshot_date=date(2026, 4, 17),
    )
    value = FinancingAssessmentValue.model_validate(assessment.output.value)

    assert value.months_of_runway > 24.0
    assert value.capital_needed_to_next_catalyst_millions == 0.0
    assert value.probability_of_pre_catalyst_financing <= 0.25
    assert value.financing_risk_tier == "low"
    assert value.financing_adjusted_intrinsic_value_millions > 1000.0


def test_phase_g_can_update_probability_stack_financing_risk() -> None:
    engine = FinancingEngine()
    assessment = engine.assess_company(
        asset_id="asset-rly2608",
        company=_company(),
        next_catalyst=FinancingCatalyst(
            catalyst_id="cat-readout",
            label="Phase 3 readout",
            expected_date=date(2026, 12, 1),
        ),
        approval_target_date=date(2027, 9, 1),
        intrinsic_value_millions=900.0,
        market_snapshot_date=date(2026, 4, 17),
    )
    updated = engine.apply_to_probability_stack_inputs(
        ProbabilityStackInputs(
            asset_id="asset-rly2608",
            asset_name="RLY-2608",
            base_pos=0.48,
            science_assessment=_science_assessment(),
            regulatory_inference=_regulatory_inference(),
            years_to_approval=3.0,
            financing_risk_score=0.20,
            market_access_pressure_score=0.30,
            management_execution_score=0.65,
            competitor_readthrough_score=0.55,
        ),
        assessment,
    )

    value = FinancingAssessmentValue.model_validate(assessment.output.value)
    assert updated.financing_risk_score == value.financing_risk_score
    assert updated.financing_risk_score > 0.20
