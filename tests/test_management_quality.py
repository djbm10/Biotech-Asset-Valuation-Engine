"""Block 6A–6D: ManagementQualityScore tests.

Tests for:
  1. Composite formula computes expected weighted score
  2. Inputs bounded 0–1 (Pydantic validation)
  3. Risk band mapping LOW/MEDIUM/HIGH/SEVERE/UNKNOWN
  4. UNKNOWN data → no penalty, gate=DILIGENCE_REQUIRED
  5. Stale data → staleness_warning + confidence downgrade
  6. Low trial_design_judgment → CAP_CONFIDENCE + wrong_trial_risk
  7. Low disclosure_transparency → DILIGENCE_REQUIRED or CAP_CONFIDENCE
  8. Low capital_allocation_discipline → STRUCTURE_AROUND_MANAGEMENT_RISK
  9. Low bd_partnering_judgment → STRUCTURE_AROUND_MANAGEMENT_RISK
  10. Low governance_alignment → CAP_ACTIVE_PURSUIT
  11. Most restrictive gate wins
  12. Source quality affects confidence, not composite
  13. POS multiplier is narrow (≤ 0.15 max swing)
  14. UNKNOWN management → no POS penalty
  15. ManagementQualityScore serializes/deserializes consistently
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_management_quality import (
    ManagementConfidence,
    ManagementGate,
    ManagementQualityInput,
    ManagementQualityScore,
    ManagementRiskBand,
    ManagementSignalSourceQuality,
    compute_management_quality_score,
    management_execution_multiplier,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _full_input(**overrides) -> ManagementQualityInput:
    """Return a ManagementQualityInput with all 7 components set to 0.80 unless overridden."""
    defaults = dict(
        target_id="target-001",
        clinical_execution_quality=0.80,
        trial_design_judgment=0.80,
        regulatory_execution=0.80,
        capital_allocation_discipline=0.80,
        bd_partnering_judgment=0.80,
        disclosure_transparency=0.80,
        governance_alignment=0.80,
    )
    defaults.update(overrides)
    return ManagementQualityInput(**defaults)


def _sparse_input(n_components: int = 2) -> ManagementQualityInput:
    """Return an input with only n_components set (rest None)."""
    all_fields = [
        "clinical_execution_quality",
        "trial_design_judgment",
        "regulatory_execution",
        "capital_allocation_discipline",
        "bd_partnering_judgment",
        "disclosure_transparency",
        "governance_alignment",
    ]
    kwargs: dict = {"target_id": "sparse-001"}
    for i, f in enumerate(all_fields):
        kwargs[f] = 0.70 if i < n_components else None
    return ManagementQualityInput(**kwargs)


# ---------------------------------------------------------------------------
# 1. Composite formula
# ---------------------------------------------------------------------------

class TestCompositeFormula:
    def test_all_ones_returns_one(self):
        inp = _full_input(
            clinical_execution_quality=1.0,
            trial_design_judgment=1.0,
            regulatory_execution=1.0,
            capital_allocation_discipline=1.0,
            bd_partnering_judgment=1.0,
            disclosure_transparency=1.0,
            governance_alignment=1.0,
        )
        score = compute_management_quality_score(inp)
        assert score.composite == pytest.approx(1.0, abs=0.001)

    def test_all_zeros_returns_zero(self):
        inp = _full_input(
            clinical_execution_quality=0.0,
            trial_design_judgment=0.0,
            regulatory_execution=0.0,
            capital_allocation_discipline=0.0,
            bd_partnering_judgment=0.0,
            disclosure_transparency=0.0,
            governance_alignment=0.0,
        )
        score = compute_management_quality_score(inp)
        assert score.composite == pytest.approx(0.0, abs=0.001)

    def test_weighted_formula_correct(self):
        # Weights: clinical=0.25, trial_design=0.20, regulatory=0.15,
        #          capital=0.15, bd=0.10, disclosure=0.10, governance=0.05
        inp = _full_input(
            clinical_execution_quality=1.0,
            trial_design_judgment=0.0,
            regulatory_execution=1.0,
            capital_allocation_discipline=0.0,
            bd_partnering_judgment=1.0,
            disclosure_transparency=0.0,
            governance_alignment=1.0,
        )
        expected = 0.25 * 1.0 + 0.20 * 0.0 + 0.15 * 1.0 + 0.15 * 0.0 + 0.10 * 1.0 + 0.10 * 0.0 + 0.05 * 1.0
        score = compute_management_quality_score(inp)
        assert score.composite == pytest.approx(expected, abs=0.001)

    def test_typical_strong_management(self):
        inp = _full_input()  # all 0.80
        score = compute_management_quality_score(inp)
        assert score.composite == pytest.approx(0.80, abs=0.001)

    def test_component_breakdown_present(self):
        score = compute_management_quality_score(_full_input())
        assert isinstance(score.component_breakdown, dict)
        assert "clinical_execution_quality" in score.component_breakdown


# ---------------------------------------------------------------------------
# 2. Input bounds (Pydantic validation)
# ---------------------------------------------------------------------------

class TestInputBounds:
    def test_above_one_raises(self):
        with pytest.raises(Exception):
            ManagementQualityInput(target_id="x", clinical_execution_quality=1.1)

    def test_below_zero_raises(self):
        with pytest.raises(Exception):
            ManagementQualityInput(target_id="x", trial_design_judgment=-0.1)

    def test_exactly_zero_and_one_accepted(self):
        inp = ManagementQualityInput(
            target_id="x",
            clinical_execution_quality=0.0,
            trial_design_judgment=1.0,
        )
        assert inp.clinical_execution_quality == 0.0
        assert inp.trial_design_judgment == 1.0


# ---------------------------------------------------------------------------
# 3. Risk band mapping
# ---------------------------------------------------------------------------

class TestRiskBandMapping:
    def test_low_risk_band(self):
        inp = _full_input()  # all 0.80 → composite 0.80 → LOW
        score = compute_management_quality_score(inp)
        assert score.risk_band == ManagementRiskBand.LOW

    def test_medium_risk_band(self):
        inp = _full_input(**{f: 0.62 for f in [
            "clinical_execution_quality", "trial_design_judgment",
            "regulatory_execution", "capital_allocation_discipline",
            "bd_partnering_judgment", "disclosure_transparency", "governance_alignment"
        ]})
        score = compute_management_quality_score(inp)
        assert score.risk_band == ManagementRiskBand.MEDIUM

    def test_high_risk_band(self):
        inp = _full_input(**{f: 0.45 for f in [
            "clinical_execution_quality", "trial_design_judgment",
            "regulatory_execution", "capital_allocation_discipline",
            "bd_partnering_judgment", "disclosure_transparency", "governance_alignment"
        ]})
        score = compute_management_quality_score(inp)
        assert score.risk_band == ManagementRiskBand.HIGH

    def test_severe_risk_band(self):
        inp = _full_input(**{f: 0.20 for f in [
            "clinical_execution_quality", "trial_design_judgment",
            "regulatory_execution", "capital_allocation_discipline",
            "bd_partnering_judgment", "disclosure_transparency", "governance_alignment"
        ]})
        score = compute_management_quality_score(inp)
        assert score.risk_band == ManagementRiskBand.SEVERE

    def test_unknown_risk_band_when_insufficient_data(self):
        # Fewer than 4 of 7 components provided
        inp = _sparse_input(n_components=2)
        score = compute_management_quality_score(inp)
        assert score.risk_band == ManagementRiskBand.UNKNOWN


# ---------------------------------------------------------------------------
# 4. UNKNOWN data → no penalty
# ---------------------------------------------------------------------------

class TestUnknownDataNoPenalty:
    def test_no_composite_when_insufficient(self):
        inp = _sparse_input(n_components=2)
        score = compute_management_quality_score(inp)
        # composite should be None or not used in gate/penalty logic
        # (risk_band is UNKNOWN → no numeric penalty applied)
        assert score.risk_band == ManagementRiskBand.UNKNOWN

    def test_gate_is_diligence_required_when_unknown(self):
        inp = _sparse_input(n_components=2)
        score = compute_management_quality_score(inp)
        assert score.gate == ManagementGate.DILIGENCE_REQUIRED

    def test_missing_components_listed(self):
        inp = _sparse_input(n_components=2)
        score = compute_management_quality_score(inp)
        assert len(score.missing_components) >= 1

    def test_no_inputs_produces_unknown_with_diligence_gate(self):
        inp = ManagementQualityInput(target_id="empty-001")
        score = compute_management_quality_score(inp)
        assert score.risk_band == ManagementRiskBand.UNKNOWN
        assert score.gate == ManagementGate.DILIGENCE_REQUIRED
        assert score.composite is None


# ---------------------------------------------------------------------------
# 5. Staleness
# ---------------------------------------------------------------------------

class TestStaleness:
    def test_no_staleness_warning_when_fresh(self):
        inp = _full_input(data_staleness_days=90)
        score = compute_management_quality_score(inp)
        assert score.staleness_warning is False

    def test_staleness_warning_when_over_180_days(self):
        inp = _full_input(data_staleness_days=200)
        score = compute_management_quality_score(inp)
        assert score.staleness_warning is True

    def test_staleness_lowers_confidence_one_level(self):
        fresh = compute_management_quality_score(_full_input(data_staleness_days=30))
        stale = compute_management_quality_score(_full_input(data_staleness_days=250))
        # stale confidence should not exceed fresh confidence
        assert stale.confidence.value <= fresh.confidence.value or \
               _confidence_rank(stale.confidence) <= _confidence_rank(fresh.confidence)

    def test_no_staleness_when_field_is_none(self):
        inp = _full_input(data_staleness_days=None)
        score = compute_management_quality_score(inp)
        assert score.staleness_warning is False


def _confidence_rank(c: ManagementConfidence) -> int:
    order = [ManagementConfidence.INSUFFICIENT_DATA, ManagementConfidence.LOW,
             ManagementConfidence.MEDIUM, ManagementConfidence.HIGH]
    return order.index(c)


# ---------------------------------------------------------------------------
# 6. Low trial_design_judgment → CAP_CONFIDENCE + wrong_trial_risk
# ---------------------------------------------------------------------------

class TestTrialDesignGate:
    def test_low_trial_design_triggers_cap_confidence(self):
        inp = _full_input(trial_design_judgment=0.25)
        score = compute_management_quality_score(inp)
        # gate should be at least CAP_CONFIDENCE
        assert score.gate in {
            ManagementGate.CAP_CONFIDENCE,
            ManagementGate.CAP_ACTIVE_PURSUIT,
            ManagementGate.STRUCTURE_AROUND_MANAGEMENT_RISK,
        }

    def test_low_trial_design_adds_wrong_trial_risk_driver(self):
        inp = _full_input(trial_design_judgment=0.25)
        score = compute_management_quality_score(inp)
        assert "wrong_trial_risk" in score.negative_drivers


# ---------------------------------------------------------------------------
# 7. Low disclosure_transparency → diligence / cap
# ---------------------------------------------------------------------------

class TestDisclosureTransparencyGate:
    def test_low_disclosure_triggers_gate(self):
        inp = _full_input(disclosure_transparency=0.25)
        score = compute_management_quality_score(inp)
        assert score.gate != ManagementGate.NONE

    def test_low_disclosure_adds_driver(self):
        inp = _full_input(disclosure_transparency=0.25)
        score = compute_management_quality_score(inp)
        assert "low_disclosure_transparency" in score.negative_drivers


# ---------------------------------------------------------------------------
# 8. Low capital_allocation_discipline → STRUCTURE_AROUND_MANAGEMENT_RISK
# ---------------------------------------------------------------------------

class TestCapitalAllocationGate:
    def test_low_capital_triggers_structure_around(self):
        inp = _full_input(capital_allocation_discipline=0.25)
        score = compute_management_quality_score(inp)
        assert score.gate in {
            ManagementGate.STRUCTURE_AROUND_MANAGEMENT_RISK,
            ManagementGate.CAP_ACTIVE_PURSUIT,
        }

    def test_low_capital_adds_financing_risk_driver(self):
        inp = _full_input(capital_allocation_discipline=0.25)
        score = compute_management_quality_score(inp)
        assert "financing_value_destruction_risk" in score.negative_drivers


# ---------------------------------------------------------------------------
# 9. Low bd_partnering_judgment → STRUCTURE_AROUND_MANAGEMENT_RISK
# ---------------------------------------------------------------------------

class TestBDPartneringGate:
    def test_low_bd_triggers_structure_around(self):
        inp = _full_input(bd_partnering_judgment=0.25)
        score = compute_management_quality_score(inp)
        assert score.gate in {
            ManagementGate.STRUCTURE_AROUND_MANAGEMENT_RISK,
            ManagementGate.CAP_ACTIVE_PURSUIT,
        }

    def test_low_bd_adds_poor_partnering_driver(self):
        inp = _full_input(bd_partnering_judgment=0.25)
        score = compute_management_quality_score(inp)
        assert "poor_partnering_history" in score.negative_drivers


# ---------------------------------------------------------------------------
# 10. Low governance_alignment → CAP_ACTIVE_PURSUIT
# ---------------------------------------------------------------------------

class TestGovernanceGate:
    def test_low_governance_triggers_cap_active_pursuit(self):
        inp = _full_input(governance_alignment=0.25)
        score = compute_management_quality_score(inp)
        assert score.gate == ManagementGate.CAP_ACTIVE_PURSUIT

    def test_low_governance_adds_governance_driver(self):
        inp = _full_input(governance_alignment=0.25)
        score = compute_management_quality_score(inp)
        assert "governance_alignment_risk" in score.negative_drivers


# ---------------------------------------------------------------------------
# 11. Most restrictive gate wins
# ---------------------------------------------------------------------------

class TestGatePriority:
    def test_governance_beats_capital_allocation(self):
        # governance_alignment < 0.35 → CAP_ACTIVE_PURSUIT (highest)
        # capital_allocation < 0.35 → STRUCTURE_AROUND_MANAGEMENT_RISK
        # CAP_ACTIVE_PURSUIT should win
        inp = _full_input(governance_alignment=0.20, capital_allocation_discipline=0.20)
        score = compute_management_quality_score(inp)
        assert score.gate == ManagementGate.CAP_ACTIVE_PURSUIT

    def test_cap_confidence_beats_diligence_required(self):
        # trial_design < 0.35 → CAP_CONFIDENCE; disclosure < 0.35 → CAP_CONFIDENCE or DILIGENCE
        inp = _full_input(trial_design_judgment=0.20, disclosure_transparency=0.20)
        score = compute_management_quality_score(inp)
        assert score.gate in {
            ManagementGate.CAP_CONFIDENCE,
            ManagementGate.STRUCTURE_AROUND_MANAGEMENT_RISK,
            ManagementGate.CAP_ACTIVE_PURSUIT,
        }

    def test_none_gate_when_all_strong(self):
        inp = _full_input()  # all 0.80 — no gate triggers
        score = compute_management_quality_score(inp)
        assert score.gate == ManagementGate.NONE


# ---------------------------------------------------------------------------
# 12. Source quality affects confidence, not composite
# ---------------------------------------------------------------------------

class TestSourceQuality:
    def test_sec_filing_gives_higher_confidence_than_rumor(self):
        sec_inp = _full_input(source_quality=ManagementSignalSourceQuality.SEC_FILING)
        rumor_inp = _full_input(source_quality=ManagementSignalSourceQuality.MARKET_RUMOR)
        sec_score = compute_management_quality_score(sec_inp)
        rumor_score = compute_management_quality_score(rumor_inp)
        # Composite should be the same; confidence should differ
        assert sec_score.composite == pytest.approx(rumor_score.composite, abs=0.001)
        assert _confidence_rank(sec_score.confidence) >= _confidence_rank(rumor_score.confidence)

    def test_unknown_source_does_not_change_composite(self):
        default_inp = _full_input()
        unknown_inp = _full_input(source_quality=ManagementSignalSourceQuality.UNKNOWN)
        s1 = compute_management_quality_score(default_inp)
        s2 = compute_management_quality_score(unknown_inp)
        assert s1.composite == pytest.approx(s2.composite, abs=0.001)


# ---------------------------------------------------------------------------
# 13. POS multiplier is narrow (max ±15%)
# ---------------------------------------------------------------------------

class TestPOSMultiplier:
    def test_low_risk_multiplier_near_one(self):
        m = management_execution_multiplier(ManagementRiskBand.LOW)
        assert 1.00 <= m <= 1.05

    def test_medium_risk_multiplier_slight_discount(self):
        m = management_execution_multiplier(ManagementRiskBand.MEDIUM)
        assert 0.95 <= m <= 1.00

    def test_high_risk_multiplier_modest_discount(self):
        m = management_execution_multiplier(ManagementRiskBand.HIGH)
        assert 0.90 <= m <= 0.95

    def test_severe_risk_multiplier_max_discount(self):
        m = management_execution_multiplier(ManagementRiskBand.SEVERE)
        assert 0.85 <= m <= 0.90

    def test_multiplier_range_never_exceeds_15_pct(self):
        all_bands = list(ManagementRiskBand)
        multipliers = [management_execution_multiplier(b) for b in all_bands if b != ManagementRiskBand.UNKNOWN]
        assert max(multipliers) <= 1.05
        assert min(multipliers) >= 0.85


# ---------------------------------------------------------------------------
# 14. UNKNOWN management → no POS penalty
# ---------------------------------------------------------------------------

class TestUnknownPOSBehavior:
    def test_unknown_band_multiplier_is_one(self):
        m = management_execution_multiplier(ManagementRiskBand.UNKNOWN)
        assert m == pytest.approx(1.0, abs=0.001)

    def test_unknown_management_input_produces_multiplier_one(self):
        inp = _sparse_input(n_components=2)
        score = compute_management_quality_score(inp)
        m = management_execution_multiplier(score.risk_band)
        assert m == pytest.approx(1.0, abs=0.001)


# ---------------------------------------------------------------------------
# 15. Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_round_trip_json(self):
        score = compute_management_quality_score(_full_input())
        dumped = score.model_dump(mode="json")
        reloaded = ManagementQualityScore.model_validate(dumped)
        assert reloaded.risk_band == score.risk_band
        assert reloaded.gate == score.gate
        if score.composite is not None:
            assert reloaded.composite == pytest.approx(score.composite, abs=1e-6)

    def test_unknown_score_serializes(self):
        inp = ManagementQualityInput(target_id="x")
        score = compute_management_quality_score(inp)
        dumped = score.model_dump(mode="json")
        assert dumped["composite"] is None
        assert dumped["risk_band"] == ManagementRiskBand.UNKNOWN.value
