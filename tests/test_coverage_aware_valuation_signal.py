from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from bve.analysis.coverage_aware_valuation_signal import (
    DEFAULT_COMPONENT_WEIGHTS,
    ComponentCoverage,
    ComponentType,
    CoverageAwareSignalInput,
    CoverageStatus,
    EvidenceType,
    FullyModeledValuationSignal,
    InsufficientEvidenceSignal,
    PartialModelSignal,
    PriceVerificationStatus,
    RobustnessStatus,
    ScenarioValues,
    SignalOutputClass,
    SolverDiagnostics,
    calculate_weighted_completeness,
    classify_coverage_aware_signal,
)


def _component(
    component_id: str,
    component_type: ComponentType,
    weight: float,
    status: CoverageStatus = CoverageStatus.MODELED_COMPANY_SPECIFIC,
    *,
    critical: bool = False,
    omission_reason: str | None = None,
    nonnegative: bool = False,
) -> ComponentCoverage:
    evidence_type = (
        EvidenceType.COMPANY_FILING
        if status == CoverageStatus.MODELED_COMPANY_SPECIFIC
        else EvidenceType.NONE
    )
    return ComponentCoverage(
        component_id=component_id,
        component_type=component_type,
        estimated_materiality_weight=weight,
        coverage_status=status,
        evidence_type=evidence_type,
        point_in_time_source="pre-cutoff filing" if evidence_type != EvidenceType.NONE else None,
        knowability_date=date(2020, 1, 1) if evidence_type != EvidenceType.NONE else None,
        modeled_value_millions=10.0 if evidence_type != EvidenceType.NONE else None,
        omission_reason=omission_reason,
        critical=critical,
        omitted_value_constrained_nonnegative=nonnegative,
    )


def _complete_components() -> tuple[ComponentCoverage, ...]:
    return tuple(
        _component(component_type.value, component_type, weight)
        for component_type, weight in DEFAULT_COMPONENT_WEIGHTS.items()
    )


def _base_input(**overrides) -> CoverageAwareSignalInput:
    data = CoverageAwareSignalInput(
        ticker="TEST",
        valuation_date=date(2020, 1, 2),
        share_price=10.0,
        shares_outstanding_millions=10.0,
        cash_millions=50.0,
        debt_millions=10.0,
        pipeline_identity_available=True,
        components=_complete_components(),
        price_verification_status=PriceVerificationStatus.VERIFIED,
        expected_burn_millions=20.0,
        expected_dilution_millions=15.0,
        corporate_overhead_pv_millions=5.0,
        other_liabilities_millions=0.0,
        modeled_lead_asset_value_millions=150.0,
        scenarios=ScenarioValues(100.0, 200.0, 300.0),
        scenario_valuation_completed=True,
        robustness_status=RobustnessStatus.PASSED,
        valuation_function_monotonic=True,
        lead_asset_market_value_isolated=True,
        implied_pos_candidate=0.45,
        solver_diagnostics=SolverDiagnostics(solver_status="solvable"),
    )
    return replace(data, **overrides)


def test_complete_company_receives_full_valuation_signal() -> None:
    result = classify_coverage_aware_signal(_base_input())

    assert isinstance(result, FullyModeledValuationSignal)
    assert result.output_class == SignalOutputClass.FULLY_MODELED_VALUATION
    assert result.model_completeness_score == pytest.approx(1.0)
    assert result.implied_pos_if_eligible == pytest.approx(0.45)


def test_weighted_score_gives_standardized_prior_partial_credit() -> None:
    components = (
        _component(
            "lead",
            ComponentType.LEAD_ASSET,
            0.6,
            CoverageStatus.MODELED_STANDARDIZED_PRIOR,
        ),
        _component("cash", ComponentType.CASH_MARKETABLE_SECURITIES, 0.4),
    )

    score = calculate_weighted_completeness(components)

    assert score.score == pytest.approx(0.7)


def test_sixty_nine_percent_does_not_pass_seventy_percent_gate() -> None:
    components = (
        _component("covered", ComponentType.LEAD_ASSET, 0.69),
        _component(
            "unknown",
            ComponentType.OTHER_CLINICAL_ASSETS,
            0.31,
            CoverageStatus.NOT_PUBLICLY_KNOWABLE,
            omission_reason="value was not publicly knowable",
        ),
    )

    result = classify_coverage_aware_signal(_base_input(components=components))

    assert isinstance(result, PartialModelSignal)
    assert result.model_completeness_score == pytest.approx(0.69)


def test_above_threshold_missing_approved_product_is_critically_blocked() -> None:
    components = tuple(
        replace(
            item,
            coverage_status=CoverageStatus.OMITTED_POTENTIALLY_MATERIAL,
            evidence_type=EvidenceType.NONE,
            point_in_time_source=None,
            knowability_date=None,
            modeled_value_millions=None,
            omission_reason="approved product is missing from SOTP",
            critical=True,
        )
        if item.component_type == ComponentType.APPROVED_COMMERCIAL_PRODUCTS
        else item
        for item in _complete_components()
    )

    result = classify_coverage_aware_signal(_base_input(components=components))

    assert isinstance(result, PartialModelSignal)
    assert result.model_completeness_score == pytest.approx(0.88)
    assert "approved product is missing from SOTP" in result.critical_omission_reasons


@pytest.mark.parametrize("score", [0.30, 0.33, 0.38])
def test_thirty_to_thirty_eight_percent_is_partial(score: float) -> None:
    components = (
        _component("covered", ComponentType.LEAD_ASSET, score),
        _component(
            "omitted",
            ComponentType.OTHER_CLINICAL_ASSETS,
            1.0 - score,
            CoverageStatus.OMITTED_POTENTIALLY_MATERIAL,
            omission_reason="material pipeline is omitted",
        ),
    )

    result = classify_coverage_aware_signal(_base_input(components=components))

    assert isinstance(result, PartialModelSignal)
    assert result.model_completeness_score == pytest.approx(score)


def test_partial_model_cannot_emit_investment_label_or_implied_pos() -> None:
    components = (
        _component("covered", ComponentType.LEAD_ASSET, 0.3),
        _component(
            "omitted",
            ComponentType.OTHER_CLINICAL_ASSETS,
            0.7,
            CoverageStatus.OMITTED_POTENTIALLY_MATERIAL,
            omission_reason="pipeline omitted",
        ),
    )

    result = classify_coverage_aware_signal(_base_input(components=components))

    assert isinstance(result, PartialModelSignal)
    assert not hasattr(result, "valuation_classification")
    assert not hasattr(result, "investable_ranking")
    assert not hasattr(result, "implied_pos_if_eligible")
    assert not hasattr(result, "valuation_gap_ratio")


def test_lower_bound_requires_all_negative_terms_and_nonnegative_omissions() -> None:
    components = (
        _component("covered", ComponentType.LEAD_ASSET, 0.5),
        _component(
            "omitted",
            ComponentType.OTHER_CLINICAL_ASSETS,
            0.5,
            CoverageStatus.OMITTED_POTENTIALLY_MATERIAL,
            omission_reason="pipeline omitted",
            nonnegative=True,
        ),
    )
    eligible = _base_input(
        components=components,
        lower_bound_requested=True,
        all_negative_claims_modeled=True,
        all_overhead_modeled=True,
        all_dilution_modeled=True,
        all_liabilities_modeled=True,
    )

    result = classify_coverage_aware_signal(eligible)
    ineligible = classify_coverage_aware_signal(replace(eligible, all_dilution_modeled=False))

    assert isinstance(result, PartialModelSignal)
    assert result.value_label == "modeled_value_lower_bound"
    assert isinstance(ineligible, PartialModelSignal)
    assert ineligible.value_label == "partial_modeled_value"


@pytest.mark.parametrize("field_name", ["share_price", "shares_outstanding_millions"])
def test_missing_price_or_share_count_is_insufficient(field_name: str) -> None:
    result = classify_coverage_aware_signal(_base_input(**{field_name: None}))

    assert isinstance(result, InsufficientEvidenceSignal)
    assert field_name in result.missing_required_inputs
    assert not hasattr(result, "market_value_unexplained")


def test_non_monotonic_valuation_blocks_implied_pos() -> None:
    result = classify_coverage_aware_signal(
        _base_input(
            valuation_function_monotonic=False,
            solver_diagnostics=SolverDiagnostics(solver_status="non_monotonic"),
        )
    )

    assert isinstance(result, FullyModeledValuationSignal)
    assert result.implied_pos_if_eligible is None
    assert result.solver_status == "non_monotonic"


def test_required_pos_above_one_preserves_diagnostics_not_point_ninety_nine() -> None:
    diagnostics = SolverDiagnostics(
        solver_status="required_pos_above_one",
        valuation_gap_millions=75.0,
        required_peak_sales_at_pos_1_millions=900.0,
        required_penetration_at_pos_1=1.2,
        unexplained_residual_millions=80.0,
    )

    result = classify_coverage_aware_signal(
        _base_input(implied_pos_candidate=0.99, solver_diagnostics=diagnostics)
    )

    assert isinstance(result, FullyModeledValuationSignal)
    assert result.implied_pos_if_eligible is None
    assert result.solver_status == "required_pos_above_one"
    assert result.solver_diagnostics == diagnostics


def test_provisional_price_is_carried_into_confidence_reporting() -> None:
    result = classify_coverage_aware_signal(
        _base_input(price_verification_status=PriceVerificationStatus.PROVISIONAL)
    )

    assert result.confidence.provisional_price is True
    assert result.confidence.price_verification_status == PriceVerificationStatus.PROVISIONAL
    assert "provisional" in " ".join(result.confidence.limitations)


def test_dilution_and_burn_are_applied_before_equity_value_spread() -> None:
    result = classify_coverage_aware_signal(_base_input())

    assert isinstance(result, FullyModeledValuationSignal)
    # Weighted operating value = 200. Balance adjustment is
    # cash 50 - debt 10 - burn 20 - dilution 15 - overhead 5 = 0.
    assert result.scenario_weighted_equity_value == pytest.approx(200.0)
    assert result.equity_value_spread == pytest.approx(100.0)
    assert result.dilution_adjusted_spread == pytest.approx(100.0)


@pytest.mark.parametrize(
    ("ticker", "score", "price", "shares", "cash", "debt", "lead_value", "residual"),
    [
        ("BIND", 0.33, 4.52, 20.75, 53.4, 3.8, -35.0, 79.19),
        ("GNCA", 0.33, 2.25, 54.37, 66.0, 9.6, -40.0, 105.9325),
        ("CEMP", 0.38, 7.55, 52.38, 248.9, 0.0, -5.0, 151.569),
        ("OCUL", 0.30, 4.85, 76.754, 164.164, 51.435, 25.0, 234.5279),
        ("ACAD", 0.38, 25.59, 160.047, 631.958, 0.0, 673.0, 2790.64473),
        ("TSRO", 0.33, 85.16, 54.382, 521.265, 140.4, 990.0, 3260.30612),
    ],
)
def test_six_names_preserve_attribution_but_reclassify_partial(
    ticker: str,
    score: float,
    price: float,
    shares: float,
    cash: float,
    debt: float,
    lead_value: float,
    residual: float,
) -> None:
    components = (
        _component("represented", ComponentType.LEAD_ASSET, score),
        _component(
            "known_omissions",
            ComponentType.OTHER_CLINICAL_ASSETS,
            1.0 - score,
            CoverageStatus.OMITTED_POTENTIALLY_MATERIAL,
            omission_reason="known six-name audit omissions",
            critical=True,
        ),
    )
    data = _base_input(
        ticker=ticker,
        share_price=price,
        shares_outstanding_millions=shares,
        cash_millions=cash,
        debt_millions=debt,
        components=components,
        expected_burn_millions=0.0,
        expected_dilution_millions=0.0,
        corporate_overhead_pv_millions=0.0,
        other_liabilities_millions=0.0,
        modeled_lead_asset_value_millions=lead_value,
    )

    result = classify_coverage_aware_signal(data)

    assert isinstance(result, PartialModelSignal)
    assert result.output_class == SignalOutputClass.PARTIAL_MODEL
    assert result.model_completeness_score == pytest.approx(score)
    assert result.market_value_unexplained == pytest.approx(residual, abs=1e-5)
    assert not hasattr(result, "implied_pos_if_eligible")
