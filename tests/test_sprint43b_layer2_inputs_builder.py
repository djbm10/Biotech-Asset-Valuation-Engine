"""
Sprint 43B — Layer 2 Inputs Builder test suite.

Tests that each adapter function correctly converts real engine outputs to
Layer2Inputs scores.  All dependencies are faked with minimal dataclasses
so the suite has no I/O and stays fast.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

import pytest

from bve.intelligence.ma_layer2_inputs_builder import (
    acquirer_profile_freshness_score,
    acquirer_pull_row_from_profile,
    build_layer2_inputs,
    catalyst_timing_from_events,
    financing_pressure_from_assessment,
    loe_revenue_cliff_urgency_from_profiles,
    pipeline_gap_urgency_from_profiles,
    rights_encumbrance_clarity_from_layer0,
    valuation_data_freshness_from_assessment,
    valuation_distress_from_assessment,
)


# ===========================================================================
# Fake data models (minimal stand-ins for real Pydantic classes)
# ===========================================================================

@dataclass(frozen=True)
class FakeFinancingAssessmentValue:
    financing_risk_score: float = 0.50
    balance_sheet_stress_score: float = 0.50
    months_of_runway: float = 12.0
    probability_of_pre_catalyst_financing: float = 0.40


@dataclass(frozen=True)
class FakeFinancingModuleOutput:
    value: FakeFinancingAssessmentValue = field(
        default_factory=FakeFinancingAssessmentValue
    )
    freshness: datetime = field(
        default_factory=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    confidence: float = 0.80


@dataclass(frozen=True)
class FakeFinancingAssessment:
    output: FakeFinancingModuleOutput = field(
        default_factory=FakeFinancingModuleOutput
    )


def make_assessment(
    *,
    financing_risk_score: float = 0.50,
    balance_sheet_stress_score: float = 0.50,
    freshness_date: date = date(2026, 1, 1),
) -> FakeFinancingAssessment:
    fav = FakeFinancingAssessmentValue(
        financing_risk_score=financing_risk_score,
        balance_sheet_stress_score=balance_sheet_stress_score,
    )
    dt = datetime(freshness_date.year, freshness_date.month, freshness_date.day,
                  tzinfo=timezone.utc)
    return FakeFinancingAssessment(output=FakeFinancingModuleOutput(value=fav, freshness=dt))


@dataclass(frozen=True)
class FakeCatalystEvent:
    expected_date: date = date(2026, 6, 1)
    date_confidence: str = "quarter"
    is_active: bool = True
    resolved: bool = False


@dataclass(frozen=True)
class FakeTherapeuticGap:
    therapeutic_area: str = "oncology"
    exposure_level: str = "high"
    rationale: str = ""
    notes: Optional[str] = None


@dataclass(frozen=True)
class FakePreferredModality:
    modality: str = "small_molecule"
    preference_strength: str = "high"


@dataclass(frozen=True)
class FakeStrategicPriority:
    priority: str = "oncology pipeline build"
    priority_strength: str = "high"


@dataclass(frozen=True)
class FakeRecentDeal:
    announcement_date: date = date(2025, 6, 1)
    therapeutic_area: str = "oncology"
    modality: str = "small_molecule"
    deal_name: str = "test_deal"
    status: str = "completed"


@dataclass(frozen=True)
class FakeExistingPartnership:
    target: str = "TARG"
    partnership_type: str = "co_development"
    acquisition_option: bool = False


@dataclass
class FakeAcquirerProfile:
    acquirer_id: str = "pfizer"
    company_name: str = "Pfizer Inc."
    profile_as_of: date = date(2026, 1, 1)
    therapeutic_area_gaps: list = field(default_factory=lambda: [FakeTherapeuticGap()])
    preferred_modalities: list = field(default_factory=lambda: [FakePreferredModality()])
    strategic_priorities: list = field(default_factory=lambda: [FakeStrategicPriority()])
    recent_deal_history: list = field(default_factory=lambda: [FakeRecentDeal()])
    existing_partnerships: list = field(default_factory=list)


@dataclass(frozen=True)
class FakeEncumbrance:
    asset_control_score: float = 0.80
    rights_control_score: float = 0.75


@dataclass(frozen=True)
class FakeLayer0Result:
    encumbrance: FakeEncumbrance = field(default_factory=FakeEncumbrance)


@dataclass(frozen=True)
class FakeLayer1Output:
    confidence_adjusted_score: float = 0.75
    overall_confidence: float = 0.80
    capped_score: float = 0.75
    raw_score: float = 0.78

    class _ScarcityStub:
        score: float = 0.70

    class _AssetQualityStub:
        score: float = 0.72

    strategic_scarcity = _ScarcityStub()
    asset_quality = _AssetQualityStub()


# ===========================================================================
# TestFinancingPressureAdapter
# ===========================================================================

class TestFinancingPressureAdapter:
    def test_high_risk_maps_to_high_pressure(self):
        a = make_assessment(financing_risk_score=0.90)
        assert financing_pressure_from_assessment(a) == pytest.approx(0.90)

    def test_low_risk_maps_to_low_pressure(self):
        a = make_assessment(financing_risk_score=0.15)
        assert financing_pressure_from_assessment(a) == pytest.approx(0.15)

    def test_neutral_by_default(self):
        a = make_assessment(financing_risk_score=0.50)
        assert financing_pressure_from_assessment(a) == pytest.approx(0.50)

    def test_missing_assessment_returns_neutral(self):
        assert financing_pressure_from_assessment(None) == pytest.approx(0.50)

    def test_assessment_without_output_attr_returns_neutral(self):
        class _Empty:
            pass
        assert financing_pressure_from_assessment(_Empty()) == pytest.approx(0.50)

    def test_dict_value_is_supported(self):
        """FinancingModuleOutput.value stored as dict when loaded from DB."""
        class _AssessmentWithDictValue:
            class output:
                value = {"financing_risk_score": 0.75, "balance_sheet_stress_score": 0.60}
                freshness = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert financing_pressure_from_assessment(_AssessmentWithDictValue()) == pytest.approx(0.75)


# ===========================================================================
# TestValuationDistressAdapter
# ===========================================================================

class TestValuationDistressAdapter:
    def test_high_stress_maps_to_high_distress(self):
        a = make_assessment(balance_sheet_stress_score=0.85)
        assert valuation_distress_from_assessment(a) == pytest.approx(0.85)

    def test_low_stress_maps_to_low_distress(self):
        a = make_assessment(balance_sheet_stress_score=0.20)
        assert valuation_distress_from_assessment(a) == pytest.approx(0.20)

    def test_missing_returns_neutral(self):
        assert valuation_distress_from_assessment(None) == pytest.approx(0.50)


# ===========================================================================
# TestValuationDataFreshnessAdapter
# ===========================================================================

class TestValuationDataFreshnessAdapter:
    def test_fresh_data_gives_high_score(self):
        # 10 days old → ≤30 bin → 1.0
        a = make_assessment(freshness_date=date(2026, 5, 14))
        score = valuation_data_freshness_from_assessment(a, as_of=date(2026, 5, 24))
        assert score == pytest.approx(1.0)

    def test_45_day_old_data(self):
        a = make_assessment(freshness_date=date(2026, 4, 9))
        score = valuation_data_freshness_from_assessment(a, as_of=date(2026, 5, 24))
        assert score == pytest.approx(0.85)  # 45 days → ≤60 bin

    def test_stale_data_gives_low_score(self):
        a = make_assessment(freshness_date=date(2024, 5, 1))
        score = valuation_data_freshness_from_assessment(a, as_of=date(2026, 5, 24))
        assert score == pytest.approx(0.15)  # >365 days stale

    def test_missing_assessment_returns_neutral(self):
        score = valuation_data_freshness_from_assessment(None, as_of=date(2026, 5, 24))
        assert score == pytest.approx(0.50)


# ===========================================================================
# TestCatalystTimingAdapter
# ===========================================================================

class TestCatalystTimingAdapter:
    AS_OF = date(2026, 5, 24)

    def test_catalyst_within_30_days_gives_max_timing(self):
        event = FakeCatalystEvent(expected_date=date(2026, 6, 5), date_confidence="exact")
        timing, conf = catalyst_timing_from_events([event], self.AS_OF)
        assert timing == pytest.approx(1.0)
        assert conf == pytest.approx(1.0)

    def test_catalyst_within_60_days(self):
        event = FakeCatalystEvent(expected_date=date(2026, 7, 5), date_confidence="quarter")
        timing, conf = catalyst_timing_from_events([event], self.AS_OF)
        assert timing == pytest.approx(0.85)
        assert conf == pytest.approx(0.75)

    def test_catalyst_within_90_days(self):
        event = FakeCatalystEvent(expected_date=date(2026, 8, 15), date_confidence="half_year")
        timing, conf = catalyst_timing_from_events([event], self.AS_OF)
        assert timing == pytest.approx(0.70)
        assert conf == pytest.approx(0.50)

    def test_catalyst_beyond_180_days(self):
        event = FakeCatalystEvent(expected_date=date(2027, 2, 1), date_confidence="estimate")
        timing, conf = catalyst_timing_from_events([event], self.AS_OF)
        assert timing == pytest.approx(0.20)
        assert conf == pytest.approx(0.30)

    def test_no_events_returns_low_timing(self):
        timing, conf = catalyst_timing_from_events([], self.AS_OF)
        assert timing == pytest.approx(0.10)
        assert conf == pytest.approx(0.30)

    def test_resolved_event_is_excluded(self):
        resolved = FakeCatalystEvent(
            expected_date=date(2026, 6, 1), resolved=True
        )
        timing, conf = catalyst_timing_from_events([resolved], self.AS_OF)
        assert timing == pytest.approx(0.10)  # no valid upcoming events

    def test_inactive_event_is_excluded(self):
        inactive = FakeCatalystEvent(
            expected_date=date(2026, 6, 1), is_active=False
        )
        timing, conf = catalyst_timing_from_events([inactive], self.AS_OF)
        assert timing == pytest.approx(0.10)

    def test_past_event_is_excluded(self):
        past = FakeCatalystEvent(expected_date=date(2025, 1, 1))
        timing, _ = catalyst_timing_from_events([past], self.AS_OF)
        assert timing == pytest.approx(0.10)

    def test_nearest_of_multiple_catalysts_selected(self):
        near = FakeCatalystEvent(expected_date=date(2026, 6, 3), date_confidence="exact")
        far = FakeCatalystEvent(expected_date=date(2027, 1, 1), date_confidence="estimate")
        timing, conf = catalyst_timing_from_events([far, near], self.AS_OF)
        assert timing == pytest.approx(1.0)   # nearest (10d)
        assert conf == pytest.approx(1.0)


# ===========================================================================
# TestAcquirerPullRowBuilder
# ===========================================================================

class TestAcquirerPullRowBuilder:
    AS_OF = date(2026, 5, 24)

    def test_perfect_ta_match_gives_high_score(self):
        profile = FakeAcquirerProfile(
            therapeutic_area_gaps=[FakeTherapeuticGap(therapeutic_area="oncology", exposure_level="high")]
        )
        row = acquirer_pull_row_from_profile(
            profile,
            target_ta="oncology",
            target_modality="small_molecule",
            target_ticker="TARG",
            as_of=self.AS_OF,
        )
        assert row.ta_fit == pytest.approx(0.90)
        assert row.pipeline_gap_urgency == pytest.approx(0.90)

    def test_medium_exposure_gives_medium_score(self):
        profile = FakeAcquirerProfile(
            therapeutic_area_gaps=[FakeTherapeuticGap(therapeutic_area="oncology", exposure_level="medium")]
        )
        row = acquirer_pull_row_from_profile(
            profile,
            target_ta="oncology",
            target_modality="small_molecule",
            target_ticker="TARG",
            as_of=self.AS_OF,
        )
        assert row.ta_fit == pytest.approx(0.65)

    def test_no_ta_match_gives_low_score(self):
        profile = FakeAcquirerProfile(
            therapeutic_area_gaps=[FakeTherapeuticGap(therapeutic_area="cns", exposure_level="high")]
        )
        row = acquirer_pull_row_from_profile(
            profile,
            target_ta="oncology",
            target_modality="small_molecule",
            target_ticker="TARG",
            as_of=self.AS_OF,
        )
        assert row.ta_fit == pytest.approx(0.15)

    def test_high_modality_preference_gives_high_fit(self):
        profile = FakeAcquirerProfile(
            preferred_modalities=[FakePreferredModality(modality="small_molecule", preference_strength="high")]
        )
        row = acquirer_pull_row_from_profile(
            profile,
            target_ta="oncology",
            target_modality="small_molecule",
            target_ticker="TARG",
            as_of=self.AS_OF,
        )
        assert row.modality_fit == pytest.approx(0.90)

    def test_no_modality_match_gives_low_fit(self):
        profile = FakeAcquirerProfile(
            preferred_modalities=[FakePreferredModality(modality="biologic", preference_strength="high")]
        )
        row = acquirer_pull_row_from_profile(
            profile,
            target_ta="oncology",
            target_modality="small_molecule",
            target_ticker="TARG",
            as_of=self.AS_OF,
        )
        assert row.modality_fit == pytest.approx(0.25)

    def test_existing_partnership_boosts_relationship(self):
        p = FakeExistingPartnership(target="targ", acquisition_option=False)
        profile = FakeAcquirerProfile(existing_partnerships=[p])
        row = acquirer_pull_row_from_profile(
            profile,
            target_ta="oncology",
            target_modality="small_molecule",
            target_ticker="TARG",
            as_of=self.AS_OF,
        )
        assert row.existing_relationship == pytest.approx(0.85)

    def test_acquisition_option_gives_highest_relationship_score(self):
        p = FakeExistingPartnership(target="TARG", acquisition_option=True)
        profile = FakeAcquirerProfile(existing_partnerships=[p])
        row = acquirer_pull_row_from_profile(
            profile,
            target_ta="oncology",
            target_modality="small_molecule",
            target_ticker="TARG",
            as_of=self.AS_OF,
        )
        assert row.existing_relationship == pytest.approx(0.95)

    def test_no_partnership_gives_low_relationship(self):
        profile = FakeAcquirerProfile(existing_partnerships=[])
        row = acquirer_pull_row_from_profile(
            profile,
            target_ta="oncology",
            target_modality="small_molecule",
            target_ticker="TARG",
            as_of=self.AS_OF,
        )
        assert row.existing_relationship == pytest.approx(0.10)

    def test_recent_deals_give_higher_appetite(self):
        recent = [
            FakeRecentDeal(announcement_date=date(2025, 1, 1)),
            FakeRecentDeal(announcement_date=date(2025, 6, 1)),
            FakeRecentDeal(announcement_date=date(2025, 11, 1)),
        ]
        profile = FakeAcquirerProfile(recent_deal_history=recent)
        row = acquirer_pull_row_from_profile(
            profile,
            target_ta="oncology",
            target_modality="small_molecule",
            target_ticker="TARG",
            as_of=self.AS_OF,
        )
        assert row.buyer_deal_appetite == pytest.approx(0.75)  # 3 × 0.25

    def test_no_recent_deals_gives_low_appetite(self):
        old_deal = FakeRecentDeal(announcement_date=date(2020, 1, 1))
        profile = FakeAcquirerProfile(recent_deal_history=[old_deal])
        row = acquirer_pull_row_from_profile(
            profile,
            target_ta="oncology",
            target_modality="small_molecule",
            target_ticker="TARG",
            as_of=self.AS_OF,
        )
        assert row.buyer_deal_appetite == pytest.approx(0.25)

    def test_freshness_days_computed_correctly(self):
        profile = FakeAcquirerProfile(profile_as_of=date(2026, 2, 24))
        row = acquirer_pull_row_from_profile(
            profile,
            target_ta="oncology",
            target_modality="small_molecule",
            target_ticker="TARG",
            as_of=date(2026, 5, 24),
        )
        assert row.profile_freshness_days == 89

    def test_acquirer_id_and_name_preserved(self):
        profile = FakeAcquirerProfile(acquirer_id="roche-001", company_name="F. Hoffmann-La Roche AG")
        row = acquirer_pull_row_from_profile(
            profile,
            target_ta="oncology",
            target_modality="biologic",
            target_ticker="TARG",
            as_of=self.AS_OF,
        )
        assert row.acquirer_id == "roche-001"
        assert row.acquirer_name == "F. Hoffmann-La Roche AG"


# ===========================================================================
# TestAcquirerProfileFreshness
# ===========================================================================

class TestAcquirerProfileFreshness:
    AS_OF = date(2026, 5, 24)

    def test_fresh_profile_within_90_days_gives_max_score(self):
        p = FakeAcquirerProfile(profile_as_of=date(2026, 3, 1))  # ~84 days old
        score = acquirer_profile_freshness_score([p], self.AS_OF)
        assert score == pytest.approx(1.0)  # 84 days → ≤90 bin

    def test_fresh_profile_within_180_days_gives_085(self):
        p = FakeAcquirerProfile(profile_as_of=date(2025, 12, 15))  # ~160 days old
        score = acquirer_profile_freshness_score([p], self.AS_OF)
        assert score == pytest.approx(0.85)  # 160 days → ≤180 bin

    def test_old_profile_gives_low_score(self):
        p = FakeAcquirerProfile(profile_as_of=date(2023, 1, 1))  # >730 days
        score = acquirer_profile_freshness_score([p], self.AS_OF)
        assert score == pytest.approx(0.20)

    def test_empty_profiles_gives_very_low_score(self):
        score = acquirer_profile_freshness_score([], self.AS_OF)
        assert score == pytest.approx(0.20)

    def test_worst_age_used_across_multiple_profiles(self):
        fresh = FakeAcquirerProfile(profile_as_of=date(2026, 5, 1))   # 23 days
        stale = FakeAcquirerProfile(profile_as_of=date(2023, 1, 1))   # >730 days
        score = acquirer_profile_freshness_score([fresh, stale], self.AS_OF)
        assert score == pytest.approx(0.20)  # worst case governs


# ===========================================================================
# TestPipelineGapUrgency
# ===========================================================================

class TestPipelineGapUrgency:
    def test_high_exposure_gives_high_urgency(self):
        p = FakeAcquirerProfile(
            therapeutic_area_gaps=[FakeTherapeuticGap(therapeutic_area="oncology", exposure_level="high")]
        )
        score = pipeline_gap_urgency_from_profiles([p], "oncology")
        assert score == pytest.approx(0.90)

    def test_no_matching_ta_gives_low_urgency(self):
        p = FakeAcquirerProfile(
            therapeutic_area_gaps=[FakeTherapeuticGap(therapeutic_area="cns", exposure_level="high")]
        )
        score = pipeline_gap_urgency_from_profiles([p], "oncology")
        assert score == pytest.approx(0.30)

    def test_empty_profiles_returns_neutral(self):
        score = pipeline_gap_urgency_from_profiles([], "oncology")
        assert score == pytest.approx(0.50)

    def test_multiple_profiles_returns_max_urgency(self):
        p_low = FakeAcquirerProfile(
            therapeutic_area_gaps=[FakeTherapeuticGap(therapeutic_area="oncology", exposure_level="low")]
        )
        p_high = FakeAcquirerProfile(
            therapeutic_area_gaps=[FakeTherapeuticGap(therapeutic_area="oncology", exposure_level="high")]
        )
        score = pipeline_gap_urgency_from_profiles([p_low, p_high], "oncology")
        assert score == pytest.approx(0.90)


# ===========================================================================
# TestLoeRevenueCliffUrgency
# ===========================================================================

class TestLoeRevenueCliffUrgency:
    def test_loe_priority_detected(self):
        sp = FakeStrategicPriority(
            priority="patent cliff mitigation for key oncology franchise",
            priority_strength="high",
        )
        p = FakeAcquirerProfile(strategic_priorities=[sp])
        score = loe_revenue_cliff_urgency_from_profiles([p], "oncology")
        assert score == pytest.approx(0.90)

    def test_no_loe_signal_returns_neutral(self):
        sp = FakeStrategicPriority(priority="expand rare disease presence", priority_strength="high")
        p = FakeAcquirerProfile(strategic_priorities=[sp])
        score = loe_revenue_cliff_urgency_from_profiles([p], "oncology")
        assert score == pytest.approx(0.50)

    def test_empty_profiles_returns_neutral(self):
        score = loe_revenue_cliff_urgency_from_profiles([], "oncology")
        assert score == pytest.approx(0.50)

    def test_loe_keyword_in_gap_notes(self):
        gap = FakeTherapeuticGap(
            therapeutic_area="oncology",
            exposure_level="high",
            rationale="loss of exclusivity on Keytruda in 2028 creates need",
        )
        p = FakeAcquirerProfile(
            strategic_priorities=[],  # no strategic priority
            therapeutic_area_gaps=[gap],
        )
        score = loe_revenue_cliff_urgency_from_profiles([p], "oncology")
        assert score == pytest.approx(0.90)


# ===========================================================================
# TestRightsEncumbranceClarity
# ===========================================================================

class TestRightsEncumbranceClarity:
    def test_clean_asset_gives_high_clarity(self):
        layer0 = FakeLayer0Result(encumbrance=FakeEncumbrance(asset_control_score=0.90))
        score = rights_encumbrance_clarity_from_layer0(layer0)
        assert score == pytest.approx(0.90)

    def test_encumbered_asset_gives_low_clarity(self):
        layer0 = FakeLayer0Result(encumbrance=FakeEncumbrance(asset_control_score=0.25))
        score = rights_encumbrance_clarity_from_layer0(layer0)
        assert score == pytest.approx(0.25)

    def test_missing_layer0_returns_neutral(self):
        score = rights_encumbrance_clarity_from_layer0(None)
        assert score == pytest.approx(0.50)

    def test_missing_encumbrance_returns_neutral(self):
        class _NoEnc:
            pass
        score = rights_encumbrance_clarity_from_layer0(_NoEnc())
        assert score == pytest.approx(0.50)


# ===========================================================================
# TestBuildLayer2Inputs — integration
# ===========================================================================

class TestBuildLayer2Inputs:
    AS_OF = date(2026, 5, 24)

    def _minimal_build(self, **kwargs):
        defaults = dict(
            target_name="TargetCo",
            as_of_date=self.AS_OF,
        )
        defaults.update(kwargs)
        return build_layer2_inputs(**defaults)

    def test_minimal_build_returns_layer2_inputs(self):
        inputs = self._minimal_build()
        assert inputs.target_name == "TargetCo"

    def test_financing_wiring(self):
        a = make_assessment(financing_risk_score=0.80, balance_sheet_stress_score=0.70)
        inputs = self._minimal_build(financing_assessment=a)
        assert inputs.target_side_pressure.financing_pressure == pytest.approx(0.80)
        assert inputs.target_side_pressure.valuation_distress == pytest.approx(0.70)

    def test_catalyst_wiring(self):
        event = FakeCatalystEvent(expected_date=date(2026, 6, 10), date_confidence="exact")
        inputs = self._minimal_build(catalyst_events=[event])
        assert inputs.target_side_pressure.catalyst_timing == pytest.approx(1.0)
        assert inputs.information_readiness.catalyst_date_confidence == pytest.approx(1.0)

    def test_acquirer_profile_wiring(self):
        profile = FakeAcquirerProfile()
        inputs = self._minimal_build(
            acquirer_profiles=[profile],
            target_ta="oncology",
            target_modality="small_molecule",
            target_ticker="TARG",
        )
        assert len(inputs.acquirer_pull) == 1
        assert inputs.acquirer_pull[0].acquirer_id == "pfizer"
        assert inputs.buyer_side_urgency.pipeline_gap_urgency is not None
        assert inputs.information_readiness.acquirer_profile_freshness is not None

    def test_layer0_wiring(self):
        layer0 = FakeLayer0Result(encumbrance=FakeEncumbrance(asset_control_score=0.88))
        inputs = self._minimal_build(layer0_result=layer0)
        assert inputs.information_readiness.rights_encumbrance_clarity == pytest.approx(0.88)

    def test_layer1_output_wiring(self):
        layer1 = FakeLayer1Output()
        inputs = self._minimal_build(layer1_output=layer1)
        assert inputs.layer1_output is layer1
        assert inputs.information_readiness.layer1_confidence == pytest.approx(0.80)

    def test_no_data_sources_all_nones(self):
        inputs = self._minimal_build()
        assert inputs.target_side_pressure.financing_pressure is None
        assert inputs.target_side_pressure.catalyst_timing is None
        assert inputs.information_readiness.rights_encumbrance_clarity is None
        assert inputs.acquirer_pull == []

    def test_manual_override_passes_through(self):
        inputs = self._minimal_build(
            seller_openness=0.85,
            governance_activist_pressure=0.70,
        )
        assert inputs.target_side_pressure.seller_openness == pytest.approx(0.85)
        assert inputs.target_side_pressure.governance_activist_pressure == pytest.approx(0.70)

    def test_layer3_passthrough_fields_preserved(self):
        inputs = self._minimal_build(
            affordability_override=0.80,
            antitrust_risk=0.30,
            rofr_impact=0.20,
            integration_feasibility=0.75,
        )
        assert inputs.affordability_override == pytest.approx(0.80)
        assert inputs.antitrust_risk == pytest.approx(0.30)
        assert inputs.rofr_impact == pytest.approx(0.20)
        assert inputs.integration_feasibility == pytest.approx(0.75)

    def test_full_wiring_produces_valid_inputs_for_compute(self):
        """End-to-end: wired inputs feed into the Layer 2 engine without error."""
        from bve.intelligence.ma_layer2_bd_priority import compute_layer2_bd_priority

        profile = FakeAcquirerProfile(
            therapeutic_area_gaps=[FakeTherapeuticGap(therapeutic_area="oncology", exposure_level="high")],
            preferred_modalities=[FakePreferredModality(modality="small_molecule", preference_strength="high")],
        )
        a = make_assessment(financing_risk_score=0.75, balance_sheet_stress_score=0.65)
        event = FakeCatalystEvent(expected_date=date(2026, 6, 15), date_confidence="quarter")
        layer0 = FakeLayer0Result(encumbrance=FakeEncumbrance(asset_control_score=0.85))
        layer1 = FakeLayer1Output()

        inputs = build_layer2_inputs(
            target_name="IntegrationTarget",
            layer1_output=layer1,
            financing_assessment=a,
            catalyst_events=[event],
            acquirer_profiles=[profile],
            layer0_result=layer0,
            target_ta="oncology",
            target_modality="small_molecule",
            target_ticker="TARG",
            as_of_date=self.AS_OF,
        )

        result = compute_layer2_bd_priority(inputs)
        assert result is not None
        assert 0.0 <= result.bd_action_score <= 1.0
        assert result.action_classification is not None
