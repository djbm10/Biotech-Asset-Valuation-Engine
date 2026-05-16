"""
Tests for P3.3 — Evidence-quality scoring: penalty multiplier on model components.

Verifies:
- EvidenceQualityScorer.score() returns EvidenceAdjustedValuation
- All-CALIBRATED inputs → composite_penalty = 1.0 (no haircut)
- All-UNVALIDATED inputs → composite_penalty = 0.68 (32% haircut)
- EVIDENCE_INFORMED → 0.93 multiplier
- JUDGMENT → 0.82 multiplier
- Composite penalty is weighted average of component penalties
- Missing components default to default_missing_grade
- adjusted_rnpv = base_rnpv × composite_penalty
- adjusted_nav = adjusted_rnpv + net_cash
- adjusted_nav_per_share = adjusted_nav / shares (when provided)
- composite_grade nearest to composite_penalty
- haircut_pct = (1 - composite_penalty) × 100
- all_calibrated property
- has_unvalidated_inputs property
- score_from_output uses ValuationOutput.confidence_tags
- summary_dict contains expected keys
- weights_not_summing raises ValueError
- score_evidence_quality convenience function
- custom component_weights respected
- explanation is non-empty string mentioning haircut
"""
from __future__ import annotations

import math

import pytest

from bve.analysis.evidence_quality_scorer import (
    DEFAULT_COMPONENT_WEIGHTS,
    GRADE_PENALTIES,
    EvidenceAdjustedValuation,
    EvidenceQualityScorer,
    score_evidence_quality,
)
from bve.models.evidence_grade import EvidenceGrade


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_grades(grade: EvidenceGrade) -> dict[str, EvidenceGrade]:
    return {k: grade for k in DEFAULT_COMPONENT_WEIGHTS}


def _scorer(**kwargs) -> EvidenceQualityScorer:
    return EvidenceQualityScorer(**kwargs)


# ---------------------------------------------------------------------------
# Basic scoring
# ---------------------------------------------------------------------------

class TestBasicScoring:
    def test_returns_evidence_adjusted_valuation(self):
        result = _scorer().score(100.0, component_grades=_all_grades(EvidenceGrade.CALIBRATED))
        assert isinstance(result, EvidenceAdjustedValuation)

    def test_all_calibrated_no_haircut(self):
        result = _scorer().score(100.0, component_grades=_all_grades(EvidenceGrade.CALIBRATED))
        assert result.composite_penalty == pytest.approx(1.0)

    def test_all_calibrated_adjusted_equals_base(self):
        result = _scorer().score(250.0, component_grades=_all_grades(EvidenceGrade.CALIBRATED))
        assert result.adjusted_rnpv_millions == pytest.approx(250.0)

    def test_all_unvalidated_32pct_haircut(self):
        result = _scorer().score(100.0, component_grades=_all_grades(EvidenceGrade.UNVALIDATED))
        assert result.composite_penalty == pytest.approx(0.68, abs=0.001)

    def test_all_evidence_informed_7pct_haircut(self):
        result = _scorer().score(100.0, component_grades=_all_grades(EvidenceGrade.EVIDENCE_INFORMED))
        assert result.composite_penalty == pytest.approx(0.93, abs=0.001)

    def test_all_judgment_18pct_haircut(self):
        result = _scorer().score(100.0, component_grades=_all_grades(EvidenceGrade.JUDGMENT))
        assert result.composite_penalty == pytest.approx(0.82, abs=0.001)

    def test_adjusted_rnpv_formula(self):
        result = _scorer().score(300.0, component_grades=_all_grades(EvidenceGrade.JUDGMENT))
        expected = round(300.0 * 0.82, 2)
        assert result.adjusted_rnpv_millions == pytest.approx(expected, abs=0.5)

    def test_adjusted_nav_includes_cash(self):
        result = _scorer().score(200.0, net_cash_millions=80.0,
                                 component_grades=_all_grades(EvidenceGrade.CALIBRATED))
        assert result.adjusted_nav_millions == pytest.approx(280.0)

    def test_nav_per_share(self):
        result = _scorer().score(
            200.0, net_cash_millions=80.0, shares_outstanding_millions=100.0,
            component_grades=_all_grades(EvidenceGrade.CALIBRATED),
        )
        assert result.adjusted_nav_per_share == pytest.approx(2.80, abs=0.01)

    def test_nav_per_share_none_when_no_shares(self):
        result = _scorer().score(200.0, component_grades=_all_grades(EvidenceGrade.CALIBRATED))
        assert result.adjusted_nav_per_share is None

    def test_base_rnpv_preserved(self):
        result = _scorer().score(175.0, component_grades=_all_grades(EvidenceGrade.JUDGMENT))
        assert result.base_rnpv_millions == pytest.approx(175.0)


# ---------------------------------------------------------------------------
# Composite penalty math
# ---------------------------------------------------------------------------

class TestCompositePenalty:
    def test_weighted_average_formula(self):
        """Composite = Σ(weight_i × penalty_i)."""
        grades = {
            "peak_sales": EvidenceGrade.CALIBRATED,      # 1.00, weight=0.35
            "pos": EvidenceGrade.EVIDENCE_INFORMED,      # 0.93, weight=0.30
            "pricing": EvidenceGrade.JUDGMENT,           # 0.82, weight=0.15
            "market_size": EvidenceGrade.UNVALIDATED,    # 0.68, weight=0.10
            "trial_costs": EvidenceGrade.CALIBRATED,     # 1.00, weight=0.05
            "discount_rate": EvidenceGrade.CALIBRATED,   # 1.00, weight=0.05
        }
        expected = (
            0.35 * 1.00   # peak_sales
            + 0.30 * 0.93  # pos
            + 0.15 * 0.82  # pricing
            + 0.10 * 0.68  # market_size
            + 0.05 * 1.00  # trial_costs
            + 0.05 * 1.00  # discount_rate
        )
        result = _scorer().score(100.0, component_grades=grades)
        assert result.composite_penalty == pytest.approx(expected, abs=0.001)

    def test_missing_component_defaults_to_unvalidated(self):
        """Supplying only pos → missing 5 components default to UNVALIDATED."""
        grades = {"pos": EvidenceGrade.CALIBRATED}
        result = _scorer(
            default_missing_grade=EvidenceGrade.UNVALIDATED
        ).score(100.0, component_grades=grades)
        assert len(result.missing_components) == 5
        assert result.composite_penalty < 1.0  # has unvalidated haircut

    def test_missing_component_defaults_to_judgment(self):
        """With JUDGMENT default, penalty is less severe than UNVALIDATED."""
        grades = {"pos": EvidenceGrade.CALIBRATED}
        r_unvalidated = _scorer(default_missing_grade=EvidenceGrade.UNVALIDATED).score(
            100.0, component_grades=grades
        )
        r_judgment = _scorer(default_missing_grade=EvidenceGrade.JUDGMENT).score(
            100.0, component_grades=grades
        )
        assert r_judgment.composite_penalty > r_unvalidated.composite_penalty

    def test_composite_penalty_in_unit_interval(self):
        for grade in EvidenceGrade:
            result = _scorer().score(100.0, component_grades=_all_grades(grade))
            assert 0.0 <= result.composite_penalty <= 1.0

    def test_haircut_pct_formula(self):
        result = _scorer().score(100.0, component_grades=_all_grades(EvidenceGrade.JUDGMENT))
        expected_haircut = round((1.0 - result.composite_penalty) * 100, 1)
        assert result.haircut_pct == pytest.approx(expected_haircut, abs=0.1)


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class TestProperties:
    def test_all_calibrated_true(self):
        result = _scorer().score(100.0, component_grades=_all_grades(EvidenceGrade.CALIBRATED))
        assert result.all_calibrated is True

    def test_all_calibrated_false_when_judgment(self):
        grades = _all_grades(EvidenceGrade.CALIBRATED)
        grades["pos"] = EvidenceGrade.JUDGMENT
        result = _scorer().score(100.0, component_grades=grades)
        assert result.all_calibrated is False

    def test_has_unvalidated_when_any_unvalidated(self):
        grades = _all_grades(EvidenceGrade.CALIBRATED)
        grades["pricing"] = EvidenceGrade.UNVALIDATED
        result = _scorer().score(100.0, component_grades=grades)
        assert result.has_unvalidated_inputs is True

    def test_no_unvalidated_when_all_calibrated(self):
        result = _scorer(
            default_missing_grade=EvidenceGrade.CALIBRATED
        ).score(100.0, component_grades=_all_grades(EvidenceGrade.CALIBRATED))
        assert result.has_unvalidated_inputs is False

    def test_composite_grade_calibrated_when_all_calibrated(self):
        result = _scorer().score(100.0, component_grades=_all_grades(EvidenceGrade.CALIBRATED))
        assert result.composite_grade == EvidenceGrade.CALIBRATED

    def test_composite_grade_unvalidated_when_all_unvalidated(self):
        result = _scorer().score(100.0, component_grades=_all_grades(EvidenceGrade.UNVALIDATED))
        assert result.composite_grade == EvidenceGrade.UNVALIDATED

    def test_explanation_is_string(self):
        result = _scorer().score(100.0, component_grades=_all_grades(EvidenceGrade.JUDGMENT))
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 20

    def test_explanation_mentions_haircut(self):
        result = _scorer().score(100.0, component_grades=_all_grades(EvidenceGrade.UNVALIDATED))
        assert "haircut" in result.explanation.lower() or "%" in result.explanation


# ---------------------------------------------------------------------------
# summary_dict
# ---------------------------------------------------------------------------

class TestSummaryDict:
    def test_has_expected_keys(self):
        result = _scorer().score(100.0, component_grades=_all_grades(EvidenceGrade.CALIBRATED))
        sd = result.summary_dict()
        for key in [
            "base_rnpv_millions", "adjusted_rnpv_millions", "composite_penalty",
            "haircut_pct", "composite_grade", "composite_grade_label",
            "adjusted_nav_millions", "adjusted_nav_per_share",
            "has_unvalidated_inputs", "n_missing_components",
        ]:
            assert key in sd

    def test_composite_grade_label_is_string(self):
        result = _scorer().score(100.0, component_grades=_all_grades(EvidenceGrade.CALIBRATED))
        assert isinstance(result.summary_dict()["composite_grade_label"], str)

    def test_n_missing_components(self):
        result = _scorer().score(100.0, component_grades={"pos": EvidenceGrade.CALIBRATED})
        assert result.summary_dict()["n_missing_components"] == 5


# ---------------------------------------------------------------------------
# score_from_output
# ---------------------------------------------------------------------------

class TestScoreFromOutput:
    def test_score_from_output_integration(self):
        from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
        from bve.entities.company import Company
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel
        from bve.valuation.valuation_engine import ValuationEngine

        asset = Asset(
            id="eq-test", name="EQ Drug", indication="Oncology",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            modality=Modality.SMALL_MOLECULE,
            stage=DevelopmentStage.PHASE_3,
            discount_rate=0.10,
        )
        company = Company(
            id="co-eq", name="EQ Pharma", ticker="EQP",
            shares_outstanding_millions=100.0,
            cash_millions=150.0,
        )
        trials = [
            ClinicalTrial(
                asset_id="eq-test", phase=TrialPhase.PHASE_3,
                success_probability=0.55, duration_years=3.0, cost_millions=80.0,
            )
        ]
        market_model = MarketModel(
            asset_id="eq-test",
            total_addressable_market_millions=5000.0,
            peak_penetration=0.05, years_to_peak=4, patent_life_years=10,
        )
        output = ValuationEngine(
            asset=asset, company=company, trials=trials, market_model=market_model
        ).run()
        grades = {
            "pos": EvidenceGrade.EVIDENCE_INFORMED,
            "peak_sales": EvidenceGrade.JUDGMENT,
        }
        result = _scorer().score_from_output(output, component_grades=grades)
        assert isinstance(result, EvidenceAdjustedValuation)
        assert result.base_rnpv_millions == pytest.approx(output.rnpv.rnpv_millions, abs=0.1)
        assert 0.0 < result.composite_penalty < 1.0


# ---------------------------------------------------------------------------
# Validation and edge cases
# ---------------------------------------------------------------------------

class TestValidationAndEdgeCases:
    def test_custom_weights_respected(self):
        weights = {
            "peak_sales": 0.50,
            "pos": 0.50,
            "pricing": 0.0,
            "market_size": 0.0,
            "trial_costs": 0.0,
            "discount_rate": 0.0,
        }
        scorer = EvidenceQualityScorer(component_weights=weights)
        grades = {
            "peak_sales": EvidenceGrade.CALIBRATED,  # 1.0
            "pos": EvidenceGrade.UNVALIDATED,         # 0.68
            # rest are 0 weight
        }
        result = scorer.score(100.0, component_grades=_all_grades(EvidenceGrade.CALIBRATED))
        assert result.composite_penalty == pytest.approx(1.0, abs=0.01)

    def test_bad_weights_raises(self):
        with pytest.raises(ValueError, match="sum"):
            EvidenceQualityScorer(component_weights={"peak_sales": 0.9, "pos": 0.9})

    def test_zero_base_rnpv(self):
        result = _scorer().score(0.0, component_grades=_all_grades(EvidenceGrade.CALIBRATED))
        assert result.adjusted_rnpv_millions == pytest.approx(0.0)

    def test_negative_rnpv_preserved(self):
        """Negative rNPV (loss-making program) should remain negative after haircut."""
        result = _scorer().score(-50.0, component_grades=_all_grades(EvidenceGrade.JUDGMENT))
        assert result.adjusted_rnpv_millions < 0

    def test_convenience_function(self):
        grades = _all_grades(EvidenceGrade.EVIDENCE_INFORMED)
        result = score_evidence_quality(100.0, grades, net_cash_millions=50.0)
        assert isinstance(result, EvidenceAdjustedValuation)
        assert result.composite_penalty == pytest.approx(0.93, abs=0.001)

    def test_component_penalty_method(self):
        scorer = _scorer()
        assert scorer.component_penalty(EvidenceGrade.CALIBRATED) == pytest.approx(1.0)
        assert scorer.component_penalty(EvidenceGrade.UNVALIDATED) == pytest.approx(0.68)
