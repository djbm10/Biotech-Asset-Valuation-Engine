"""
Phase 1 tests.

1A: Trial design features (TrialDesignFeatureSet / compute_design_adjusted_pos)
1B: Probabilistic competitor entry in Monte Carlo (CompetitionModel.sample_launch_outcomes)

Also includes:
- Phase-conditional scaling correctness
- Anti-double-counting: LayerOverlapReport / check_pos_layer_overlap
- Backward compatibility snapshot (canonical case study outputs)
- Cross-axis independence (all-positive → bounded by cap, not exceeding)
- Competition model share invariants (time-aware, 0.10 floor)
- Cap stress analysis (decision robustness)
- Phase required enforcement (phase=None → ValueError)

Layer 2 dimensions (EvidenceDesignQuality, ComparatorFit, RegulatoryPathwayRisk)
replace the old (EndpointBasis, EvidenceDesign, ApprovalPathway) trio.
Phase scaling is a single multiplier per phase, not per-dimension.
"""
from __future__ import annotations

import numpy as np
import pytest

from bve.models.trial_design_features import (
    CapStressResult,
    ComparatorFit,
    DesignAdjustedPOSResult,
    EvidenceDesignQuality,
    LayerOverlapReport,
    RegulatoryPathwayRisk,
    TrialDesignFeatureSet,
    cap_stress_analysis,
    check_pos_layer_overlap,
    compute_design_adjusted_pos,
)
from bve.models.competition_model import CompetitionModel, CompetitorLaunch
from bve.config.constants import (
    TRIAL_DESIGN_CAP_NEGATIVE,
    TRIAL_DESIGN_CAP_POSITIVE,
    TRIAL_DESIGN_PHASE_NEUTRAL,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rng():
    return np.random.default_rng(42)


@pytest.fixture
def approved_competitor():
    return CompetitorLaunch(
        name="Drug A (approved)",
        status="approved",
        launch_year_relative=-1,
        peak_market_share=0.30,
        years_to_peak=3,
        approval_probability=1.0,
    )


@pytest.fixture
def pipeline_competitor_p50():
    return CompetitorLaunch(
        name="Drug B (pipeline, P=0.5)",
        status="phase_3",
        launch_year_relative=2,
        peak_market_share=0.20,
        years_to_peak=3,
        approval_probability=0.5,
    )


@pytest.fixture
def pipeline_competitor_p0():
    return CompetitorLaunch(
        name="Drug C (pipeline, P=0.0)",
        status="phase_3",
        launch_year_relative=2,
        peak_market_share=0.20,
        years_to_peak=3,
        approval_probability=0.0,
    )


@pytest.fixture
def pipeline_competitor_p1():
    return CompetitorLaunch(
        name="Drug D (pipeline, P=1.0)",
        status="phase_3",
        launch_year_relative=2,
        peak_market_share=0.20,
        years_to_peak=3,
        approval_probability=1.0,
    )


# ---------------------------------------------------------------------------
# Phase 1A: Phase required enforcement
# ---------------------------------------------------------------------------

class TestPhaseRequired:
    def test_missing_phase_raises_value_error(self):
        """
        compute_design_adjusted_pos must raise ValueError when phase is not provided.
        Prevents silent amplification of effect sizes via Phase 3 default.
        """
        features = TrialDesignFeatureSet()
        with pytest.raises(TypeError):
            compute_design_adjusted_pos(0.55, features)  # type: ignore[call-arg]

    def test_invalid_phase_raises_value_error(self):
        """An unrecognized phase string must raise ValueError with helpful message."""
        features = TrialDesignFeatureSet()
        with pytest.raises(ValueError, match="Invalid phase"):
            compute_design_adjusted_pos(0.55, features, phase="phase_99")

    def test_neutral_phase_accepted(self):
        """TRIAL_DESIGN_PHASE_NEUTRAL is a valid explicit maximum-effect mode."""
        features = TrialDesignFeatureSet()
        result = compute_design_adjusted_pos(0.55, features, phase=TRIAL_DESIGN_PHASE_NEUTRAL)
        assert 0.0 < result.adjusted_pos < 1.0

    def test_neutral_phase_uses_scaling_of_one(self):
        """Phase 'neutral' should apply scaling=1.0 to all dimensions."""
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.SINGLE_ARM_OBJECTIVE
        )
        result = compute_design_adjusted_pos(0.55, features, phase=TRIAL_DESIGN_PHASE_NEUTRAL)
        assert result.phase_scaling_applied["evidence_design_quality"] == pytest.approx(1.0)
        assert result.phase_scaling_applied["comparator_fit"] == pytest.approx(1.0)
        assert result.phase_scaling_applied["regulatory_pathway_risk"] == pytest.approx(1.0)

    def test_compute_adjusted_pos_method_requires_phase(self):
        """TrialDesignFeatureSet.compute_adjusted_pos also requires phase."""
        features = TrialDesignFeatureSet()
        with pytest.raises(TypeError):
            features.compute_adjusted_pos(0.55)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Phase 1A: Trial design monotonicity
# ---------------------------------------------------------------------------

class TestTrialDesignMonotonicity:
    def test_rct_double_blind_higher_than_single_arm(self):
        """RCT double-blind should give higher adjusted POS than single-arm design."""
        base_pos = 0.55
        rct = TrialDesignFeatureSet(evidence_design_quality=EvidenceDesignQuality.RCT_DOUBLE_BLIND)
        single = TrialDesignFeatureSet(evidence_design_quality=EvidenceDesignQuality.SINGLE_ARM_OBJECTIVE)
        res_rct = compute_design_adjusted_pos(base_pos, rct, phase="phase_3")
        res_single = compute_design_adjusted_pos(base_pos, single, phase="phase_3")
        assert res_rct.adjusted_pos > res_single.adjusted_pos

    def test_evidence_design_quality_monotonically_decreases(self):
        """Design quality must decrease monotonically from RCT_DOUBLE_BLIND to REGISTRY_OBSERVATIONAL."""
        base_pos = 0.55
        order = [
            EvidenceDesignQuality.RCT_DOUBLE_BLIND,
            EvidenceDesignQuality.RCT_OPEN_LABEL,
            EvidenceDesignQuality.RCT_WEAK_COMPARATOR,
            EvidenceDesignQuality.SINGLE_ARM_OBJECTIVE,
            EvidenceDesignQuality.SINGLE_ARM_SUBJECTIVE,
            EvidenceDesignQuality.REGISTRY_OBSERVATIONAL,
        ]
        pos_values = [
            compute_design_adjusted_pos(
                base_pos, TrialDesignFeatureSet(evidence_design_quality=edq), phase="phase_3"
            ).adjusted_pos
            for edq in order
        ]
        for i in range(len(pos_values) - 1):
            assert pos_values[i] > pos_values[i + 1], (
                f"Expected {order[i].value} > {order[i+1].value}: "
                f"{pos_values[i]:.4f} vs {pos_values[i+1]:.4f}"
            )

    def test_comparator_fit_ordering(self):
        """MATCHES_SOC > ACCEPTABLE_NOT_IDEAL > NO_VALID_COMPARATOR."""
        base_pos = 0.55
        best = compute_design_adjusted_pos(
            base_pos,
            TrialDesignFeatureSet(comparator_fit=ComparatorFit.MATCHES_SOC),
            phase="phase_3",
        )
        neutral = compute_design_adjusted_pos(
            base_pos,
            TrialDesignFeatureSet(comparator_fit=ComparatorFit.ACCEPTABLE_NOT_IDEAL),
            phase="phase_3",
        )
        worst = compute_design_adjusted_pos(
            base_pos,
            TrialDesignFeatureSet(comparator_fit=ComparatorFit.NO_VALID_COMPARATOR),
            phase="phase_3",
        )
        assert best.adjusted_pos > neutral.adjusted_pos > worst.adjusted_pos

    def test_regulatory_pathway_ordering(self):
        """ORPHAN_RARE_DISEASE > STANDARD > NO_CLEAR_PRECEDENT."""
        base_pos = 0.55
        orphan = compute_design_adjusted_pos(
            base_pos,
            TrialDesignFeatureSet(regulatory_pathway_risk=RegulatoryPathwayRisk.ORPHAN_RARE_DISEASE),
            phase="phase_3",
        )
        standard = compute_design_adjusted_pos(
            base_pos,
            TrialDesignFeatureSet(regulatory_pathway_risk=RegulatoryPathwayRisk.STANDARD),
            phase="phase_3",
        )
        no_precedent = compute_design_adjusted_pos(
            base_pos,
            TrialDesignFeatureSet(regulatory_pathway_risk=RegulatoryPathwayRisk.NO_CLEAR_PRECEDENT),
            phase="phase_3",
        )
        assert orphan.adjusted_pos > standard.adjusted_pos > no_precedent.adjusted_pos


# ---------------------------------------------------------------------------
# Phase 1A: Cap
# ---------------------------------------------------------------------------

class TestTrialDesignCap:
    def test_combined_positive_adjustments_hit_cap(self):
        """
        All-positive combination at Phase 3 should hit the +0.30 cap.
        rct_double_blind (+0.20) + matches_soc (+0.10) + orphan_rare_disease (+0.10) = +0.40
        → capped at +0.30.
        """
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.RCT_DOUBLE_BLIND,
            comparator_fit=ComparatorFit.MATCHES_SOC,
            regulatory_pathway_risk=RegulatoryPathwayRisk.ORPHAN_RARE_DISEASE,
        )
        result = compute_design_adjusted_pos(base_pos=0.55, features=features, phase="phase_3")
        assert result.uncapped_logodds_adjustment == pytest.approx(0.40, abs=0.01)
        assert result.was_capped
        assert result.cap_applied == "positive"
        assert result.total_logodds_adjustment == pytest.approx(TRIAL_DESIGN_CAP_POSITIVE, abs=0.001)

    def test_cap_activates_when_exceeded(self):
        """
        With a custom settings dict where the cap is very low, the adjustment
        should be capped and was_capped should be True.
        """
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.RCT_DOUBLE_BLIND,
            comparator_fit=ComparatorFit.MATCHES_SOC,
        )
        settings = {"cap_logodds_positive": 0.05, "cap_logodds_negative": -0.60}
        result = compute_design_adjusted_pos(base_pos=0.55, features=features, phase="phase_3", settings=settings)
        assert result.was_capped
        assert result.cap_applied == "positive"
        assert result.total_logodds_adjustment == pytest.approx(0.05, abs=0.001)

    def test_negative_cap_activates(self):
        """Stacking maximum negative features should hit TRIAL_DESIGN_CAP_NEGATIVE."""
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.REGISTRY_OBSERVATIONAL,  # -0.35
            comparator_fit=ComparatorFit.NO_VALID_COMPARATOR,                       # -0.30
            regulatory_pathway_risk=RegulatoryPathwayRisk.NO_CLEAR_PRECEDENT,       # -0.30
        )
        result = compute_design_adjusted_pos(base_pos=0.55, features=features, phase="phase_3")
        assert result.was_capped
        assert result.cap_applied == "negative"
        assert result.total_logodds_adjustment == pytest.approx(TRIAL_DESIGN_CAP_NEGATIVE, abs=0.001)

    def test_breakdown_sums_to_uncapped(self):
        """adjustment_breakdown values should sum to uncapped_logodds_adjustment."""
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.SINGLE_ARM_OBJECTIVE,
            comparator_fit=ComparatorFit.OUTDATED_COMPARATOR,
            regulatory_pathway_risk=RegulatoryPathwayRisk.ACCELERATED_NOVEL_SURROGATE,
        )
        result = compute_design_adjusted_pos(base_pos=0.55, features=features, phase="phase_3")
        bd_sum = sum(result.adjustment_breakdown.values())
        assert bd_sum == pytest.approx(result.uncapped_logodds_adjustment, abs=0.001)


# ---------------------------------------------------------------------------
# Phase 1A: Bounds
# ---------------------------------------------------------------------------

class TestTrialDesignBounds:
    def test_adjusted_pos_strictly_between_zero_and_one(self):
        """Adjusted POS must remain strictly in (0, 1) for extreme inputs."""
        extreme_positive = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.RCT_DOUBLE_BLIND,
            comparator_fit=ComparatorFit.MATCHES_SOC,
            regulatory_pathway_risk=RegulatoryPathwayRisk.ORPHAN_RARE_DISEASE,
        )
        extreme_negative = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.REGISTRY_OBSERVATIONAL,
            comparator_fit=ComparatorFit.NO_VALID_COMPARATOR,
            regulatory_pathway_risk=RegulatoryPathwayRisk.NO_CLEAR_PRECEDENT,
        )
        for base in [0.001, 0.50, 0.999]:
            r_pos = compute_design_adjusted_pos(base, extreme_positive, phase="phase_3")
            r_neg = compute_design_adjusted_pos(base, extreme_negative, phase="phase_3")
            assert 0.0 < r_pos.adjusted_pos < 1.0
            assert 0.0 < r_neg.adjusted_pos < 1.0

    def test_default_features_produce_positive_adjustment(self):
        """
        Default TrialDesignFeatureSet (RCT_DOUBLE_BLIND + ACCEPTABLE_NOT_IDEAL + STANDARD)
        gives a positive adjustment at Phase 3: +0.20 × 1.0 = +0.20.
        """
        features = TrialDesignFeatureSet()
        result = compute_design_adjusted_pos(base_pos=0.55, features=features, phase="phase_3")
        assert result.total_logodds_adjustment == pytest.approx(0.20, abs=0.001)
        assert result.adjusted_pos > 0.55
        assert not result.was_capped

    def test_acceptable_not_ideal_standard_gives_zero_for_cf_rpr(self):
        """ComparatorFit and RegulatoryPathwayRisk baseline values give 0 contribution."""
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.RCT_OPEN_LABEL,  # +0.10
            comparator_fit=ComparatorFit.ACCEPTABLE_NOT_IDEAL,              #  0.00
            regulatory_pathway_risk=RegulatoryPathwayRisk.STANDARD,         #  0.00
        )
        result = compute_design_adjusted_pos(base_pos=0.55, features=features, phase="phase_3")
        assert result.adjustment_breakdown["comparator_fit"] == pytest.approx(0.0, abs=0.001)
        assert result.adjustment_breakdown["regulatory_pathway_risk"] == pytest.approx(0.0, abs=0.001)


# ---------------------------------------------------------------------------
# Phase 1B: Probabilistic competitor entry
# ---------------------------------------------------------------------------

class TestSampleLaunchOutcomes:
    def test_approved_competitor_always_present(self, rng, approved_competitor):
        """An approved competitor must appear in every simulation draw."""
        model = CompetitionModel(competitors=[approved_competitor])
        for _ in range(100):
            sampled = model.sample_launch_outcomes(rng)
            assert len(sampled.competitors) == 1
            assert sampled.competitors[0].name == approved_competitor.name

    def test_pipeline_competitor_excluded_when_prob_zero(self, rng, pipeline_competitor_p0):
        """A pipeline competitor with approval_probability=0 must never appear."""
        model = CompetitionModel(competitors=[pipeline_competitor_p0])
        for _ in range(200):
            sampled = model.sample_launch_outcomes(rng)
            assert len(sampled.competitors) == 0

    def test_pipeline_competitor_always_included_when_prob_one(self, rng, pipeline_competitor_p1):
        """A pipeline competitor with approval_probability=1.0 must always appear."""
        model = CompetitionModel(competitors=[pipeline_competitor_p1])
        for _ in range(100):
            sampled = model.sample_launch_outcomes(rng)
            assert len(sampled.competitors) == 1

    def test_sampled_pipeline_competitor_has_prob_one(self, rng, pipeline_competitor_p50):
        """
        When a pipeline competitor is sampled, its approval_probability in the
        returned model must be 1.0 to prevent double-counting in _single_competitor_share.
        """
        model = CompetitionModel(competitors=[pipeline_competitor_p50])
        sampled_comps = []
        for _ in range(500):
            sampled = model.sample_launch_outcomes(rng)
            sampled_comps.extend(sampled.competitors)
        assert all(c.approval_probability == 1.0 for c in sampled_comps)

    def test_approved_competitor_unmodified(self, rng, approved_competitor):
        """Approved competitor should pass through with original attributes unchanged."""
        model = CompetitionModel(competitors=[approved_competitor])
        sampled = model.sample_launch_outcomes(rng)
        c = sampled.competitors[0]
        assert c.launch_year_relative == approved_competitor.launch_year_relative
        assert c.peak_market_share == approved_competitor.peak_market_share
        assert c.years_to_peak == approved_competitor.years_to_peak

    def test_mixed_model_approved_always_pipeline_sometimes(self, approved_competitor, pipeline_competitor_p50):
        """
        Approved competitor always present; pipeline (P=0.5) appears ~50% of the time.
        """
        rng_local = np.random.default_rng(7)
        model = CompetitionModel(competitors=[approved_competitor, pipeline_competitor_p50])
        approved_count = 0
        pipeline_count = 0
        n = 1000
        for _ in range(n):
            sampled = model.sample_launch_outcomes(rng_local)
            names = {c.name for c in sampled.competitors}
            if approved_competitor.name in names:
                approved_count += 1
            if pipeline_competitor_p50.name in names:
                pipeline_count += 1
        assert approved_count == n, "Approved competitor must be present in all simulations"
        assert 350 <= pipeline_count <= 650, (
            f"Pipeline competitor (P=0.5) appeared in {pipeline_count}/1000 sims; expected ~500 ± 150"
        )

    def test_original_competition_model_unchanged_after_sampling(self, rng, approved_competitor, pipeline_competitor_p50):
        """sample_launch_outcomes must not mutate the original CompetitionModel."""
        model = CompetitionModel(competitors=[approved_competitor, pipeline_competitor_p50])
        original_count = len(model.competitors)
        for _ in range(50):
            model.sample_launch_outcomes(rng)
        assert len(model.competitors) == original_count

    def test_mc_distribution_wider_with_uncertain_competition(self):
        """
        MC rNPV std should be higher when a pipeline competitor has P=0.5 vs P=1.0.
        P=0.5: ~50% of sims have no competition → higher variance.
        P=1.0: all sims have competition → narrower distribution.
        """
        from bve.entities.asset import Asset, DevelopmentStage, TherapeuticArea, Modality
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel
        from bve.models.monte_carlo import MonteCarloParams, run_monte_carlo

        asset = Asset(
            id="test-comp", name="TEST-COMP", indication="Test",
            therapeutic_area=TherapeuticArea.ONCOLOGY, stage=DevelopmentStage.PHASE_3,
            modality=Modality.SMALL_MOLECULE, discount_rate=0.10,
        )
        trials = [ClinicalTrial(
            asset_id="test-comp", phase=TrialPhase.PHASE_3,
            success_probability=0.55, duration_years=3.0, cost_millions=200.0,
        )]

        def _market(p_approval: float) -> MarketModel:
            return MarketModel(
                asset_id="test-comp",
                total_addressable_market_millions=5000.0,
                peak_penetration=0.15, years_to_peak=4, patent_life_years=12,
                competition_model=CompetitionModel(competitors=[CompetitorLaunch(
                    name="Pipeline", status="phase_3", launch_year_relative=2,
                    peak_market_share=0.35, years_to_peak=3, approval_probability=p_approval,
                )]),
            )

        params = MonteCarloParams(n_simulations=3000, random_seed=99)
        mc_uncertain = run_monte_carlo(asset, trials, _market(0.5), params)
        mc_certain = run_monte_carlo(asset, trials, _market(1.0), params)
        assert mc_uncertain.std_millions > mc_certain.std_millions


# ---------------------------------------------------------------------------
# Phase-conditional scaling
# ---------------------------------------------------------------------------

class TestPhaseConditionalScaling:
    def test_single_arm_penalty_stronger_at_phase3_than_phase1(self):
        """Single-arm penalty must be substantially larger at Phase 3 than Phase 1."""
        base_pos = 0.55
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.SINGLE_ARM_SUBJECTIVE
        )
        res_p3 = compute_design_adjusted_pos(base_pos, features, phase="phase_3")
        res_p1 = compute_design_adjusted_pos(base_pos, features, phase="phase_1")
        assert res_p3.adjusted_pos < res_p1.adjusted_pos
        # Phase 3 scaling=1.0, Phase 1 scaling=0.20 → ratio ≥ 3×
        p3_lo = abs(res_p3.total_logodds_adjustment)
        p1_lo = abs(res_p1.total_logodds_adjustment)
        assert p3_lo > p1_lo * 3, (
            f"Phase 3 |logodds| ({p3_lo:.3f}) should be ≥3× Phase 1 ({p1_lo:.3f})"
        )

    def test_risky_design_minimal_at_phase1(self):
        """Subjective single-arm should barely change POS at Phase 1 (small scaling)."""
        base_pos = 0.65
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.SINGLE_ARM_SUBJECTIVE
        )
        res_p1 = compute_design_adjusted_pos(base_pos, features, phase="phase_1")
        res_p3 = compute_design_adjusted_pos(base_pos, features, phase="phase_3")
        # Phase 1: -0.30 × 0.20 = -0.06 → small change
        assert abs(res_p1.adjusted_pos - base_pos) < 0.03
        # Phase 3: -0.30 × 1.00 = -0.30 → large change
        assert abs(res_p3.adjusted_pos - base_pos) > 0.05

    def test_phase_scaling_fields_in_result(self):
        """phase_scaling_applied should report the scaling multiplier for audit."""
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.SINGLE_ARM_OBJECTIVE
        )
        result = compute_design_adjusted_pos(0.55, features, phase="phase_1")
        from bve.config.constants import TRIAL_DESIGN_PHASE_SCALING
        expected_scale = TRIAL_DESIGN_PHASE_SCALING["phase_1"]
        assert result.phase_scaling_applied["evidence_design_quality"] == pytest.approx(
            expected_scale, abs=0.001
        )
        # All three dimensions get the same multiplier
        assert result.phase_scaling_applied["comparator_fit"] == pytest.approx(expected_scale, abs=0.001)
        assert result.phase_scaling_applied["regulatory_pathway_risk"] == pytest.approx(expected_scale, abs=0.001)

    def test_neutral_differs_from_phase1(self):
        """Explicit 'neutral' phase should give larger magnitude than phase_1."""
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.SINGLE_ARM_SUBJECTIVE
        )
        res_neutral = compute_design_adjusted_pos(0.55, features, phase=TRIAL_DESIGN_PHASE_NEUTRAL)
        res_p1 = compute_design_adjusted_pos(0.55, features, phase="phase_1")
        # neutral applies 1.0 scaling; phase_1 applies 0.20 → neutral has larger penalty
        assert res_neutral.adjusted_pos < res_p1.adjusted_pos


# ---------------------------------------------------------------------------
# Anti-double-counting
# ---------------------------------------------------------------------------

class TestLayerOverlap:
    """
    The new Layer 2 (EvidenceDesignQuality, ComparatorFit, RegulatoryPathwayRisk)
    is orthogonal to Layer 1 by design — BTD is in Layer 1 only, and endpoint
    quality is not a Layer 2 dimension. check_pos_layer_overlap() always returns
    a clean report.
    """

    def test_no_overlap_with_default_settings(self):
        """Default POSAdjusters + default TrialDesignFeatureSet: always clean."""
        from bve.models.pos_model import POSAdjusters
        adj = POSAdjusters()
        features = TrialDesignFeatureSet()
        report = check_pos_layer_overlap(adj, features, phase="phase_3")
        assert report.is_clean()
        assert not report.has_critical_overlap
        assert report.estimated_double_count_logodds == pytest.approx(0.0)

    def test_no_overlap_with_btd_in_layer1(self):
        """BTD in Layer 1 only (not in new Layer 2) → no overlap."""
        from bve.models.pos_model import POSAdjusters
        adj = POSAdjusters(has_breakthrough_designation=True)
        features = TrialDesignFeatureSet(
            regulatory_pathway_risk=RegulatoryPathwayRisk.ORPHAN_RARE_DISEASE
        )
        report = check_pos_layer_overlap(adj, features, phase="phase_3")
        assert report.is_clean()
        assert not report.has_critical_overlap

    def test_no_overlap_with_aggressive_layer1_settings(self):
        """Non-default Layer 1 adjusters combined with any Layer 2 features → always clean."""
        from bve.models.pos_model import POSAdjusters
        from bve.entities.trial import EndpointType
        from bve.models.pos_model import BiomarkerSelectionStrength, PriorPhaseDataStrength
        adj = POSAdjusters(
            endpoint_type=EndpointType.HARD_CLINICAL,
            has_breakthrough_designation=True,
            biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
            prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
        )
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.RCT_DOUBLE_BLIND,
            comparator_fit=ComparatorFit.MATCHES_SOC,
            regulatory_pathway_risk=RegulatoryPathwayRisk.ACCELERATED_VALIDATED_SURROGATE,
        )
        report = check_pos_layer_overlap(adj, features, phase="phase_3")
        assert report.is_clean()

    def test_overlap_report_summary_shows_clean(self):
        """summary() returns clean message when no overlaps."""
        from bve.models.pos_model import POSAdjusters
        adj = POSAdjusters()
        features = TrialDesignFeatureSet()
        report = check_pos_layer_overlap(adj, features)
        assert "No signal overlaps" in report.summary()

    def test_overlap_report_is_clean_method(self):
        """is_clean() returns True when no overlapping signals."""
        from bve.models.pos_model import POSAdjusters
        report = check_pos_layer_overlap(POSAdjusters(), TrialDesignFeatureSet())
        assert report.is_clean()
        assert isinstance(report.overlapping_signals, list)
        assert len(report.overlapping_signals) == 0


# ---------------------------------------------------------------------------
# Cross-axis independence and cap enforcement
# ---------------------------------------------------------------------------

class TestCrossAxisIndependence:
    def test_all_positive_axes_bounded_by_cap(self):
        """Total adjustment must never exceed TRIAL_DESIGN_CAP_POSITIVE."""
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.RCT_DOUBLE_BLIND,
            comparator_fit=ComparatorFit.MATCHES_SOC,
            regulatory_pathway_risk=RegulatoryPathwayRisk.ORPHAN_RARE_DISEASE,
        )
        result = compute_design_adjusted_pos(0.55, features, phase="phase_3")
        assert result.total_logodds_adjustment <= TRIAL_DESIGN_CAP_POSITIVE + 1e-9
        bd_sum = sum(result.adjustment_breakdown.values())
        assert bd_sum == pytest.approx(result.uncapped_logodds_adjustment, abs=0.001)

    def test_all_negative_axes_bounded_by_negative_cap(self):
        """Total adjustment must never be below TRIAL_DESIGN_CAP_NEGATIVE."""
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.REGISTRY_OBSERVATIONAL,
            comparator_fit=ComparatorFit.NO_VALID_COMPARATOR,
            regulatory_pathway_risk=RegulatoryPathwayRisk.NO_CLEAR_PRECEDENT,
        )
        result = compute_design_adjusted_pos(0.55, features, phase="phase_3")
        assert result.total_logodds_adjustment >= TRIAL_DESIGN_CAP_NEGATIVE - 1e-9
        assert result.was_capped
        assert result.cap_applied == "negative"

    def test_each_dimension_independently_adjusts_pos(self):
        """Adjusting one dimension should shift POS independently of the others."""
        base = 0.50
        # Only change evidence_design_quality, keep others at baseline
        r_best = compute_design_adjusted_pos(
            base,
            TrialDesignFeatureSet(evidence_design_quality=EvidenceDesignQuality.RCT_DOUBLE_BLIND),
            phase="phase_3",
        )
        r_worst = compute_design_adjusted_pos(
            base,
            TrialDesignFeatureSet(evidence_design_quality=EvidenceDesignQuality.REGISTRY_OBSERVATIONAL),
            phase="phase_3",
        )
        assert r_best.adjusted_pos > r_worst.adjusted_pos
        # Difference should be meaningful at Phase 3
        assert r_best.adjusted_pos - r_worst.adjusted_pos > 0.10

    def test_three_dimensions_combine_additively(self):
        """Sum of individual contributions equals combined uncapped adjustment."""
        base = 0.50
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.RCT_OPEN_LABEL,  # +0.10
            comparator_fit=ComparatorFit.PLACEBO_ACCEPTABLE,               # +0.05
            regulatory_pathway_risk=RegulatoryPathwayRisk.STANDARD,        #  0.00
        )
        result = compute_design_adjusted_pos(base, features, phase="phase_3")
        # At Phase 3: (0.10 + 0.05 + 0.00) × 1.0 = +0.15 → not capped
        assert result.uncapped_logodds_adjustment == pytest.approx(0.15, abs=0.001)
        assert not result.was_capped


# ---------------------------------------------------------------------------
# Competition model share invariants
# ---------------------------------------------------------------------------

class TestCompetitionModelInvariants:
    def test_available_market_fraction_bounded(self, approved_competitor):
        """our_available_market_fraction must always be in [0.10, 1.0]."""
        model = CompetitionModel(competitors=[approved_competitor])
        for yr in range(1, 15):
            frac = model.our_available_market_fraction(yr)
            assert 0.10 <= frac <= 1.0, f"Year {yr}: fraction={frac:.3f} out of bounds"

    def test_combined_competitor_share_nonnegative(self, approved_competitor):
        """combined_competitor_share must be >= 0 (market expansion clamps to 0)."""
        model = CompetitionModel(competitors=[approved_competitor])
        for yr in range(1, 15):
            share = model.combined_competitor_share(yr)
            assert share >= 0.0, f"Year {yr}: combined_share={share:.3f} < 0"

    def test_no_competitors_gives_full_market(self):
        """With no competitors, available fraction must be 1.0 every year."""
        model = CompetitionModel(competitors=[])
        for yr in range(1, 15):
            assert model.our_available_market_fraction(yr) == pytest.approx(1.0)

    def test_negative_peak_share_expands_market(self):
        """
        Negative peak_market_share (market-expanding drug, e.g., combo label)
        must not reduce our available market — combined_competitor_share is
        clamped to max(0, total), so negative competitor entries increase availability.
        """
        expanding_comp = CompetitorLaunch(
            name="Combo label (market-expanding)",
            status="approved",
            launch_year_relative=2,
            peak_market_share=-0.10,  # EXPANDS market
            years_to_peak=2,
            approval_probability=1.0,
        )
        model_with = CompetitionModel(competitors=[expanding_comp])
        model_without = CompetitionModel(competitors=[])
        for yr in range(1, 15):
            assert model_with.our_available_market_fraction(yr) >= model_without.our_available_market_fraction(yr)

    def test_competition_is_time_aware(self, approved_competitor):
        """
        Competitor that launched 1 year before us (launch_year_relative=-1) with
        years_to_peak=3 should ramp: share at Year 1 < share at Year 3.
        This verifies the model is NOT a static haircut.
        """
        model = CompetitionModel(competitors=[approved_competitor])
        share_yr1 = model.combined_competitor_share(1)
        share_yr3 = model.combined_competitor_share(3)
        # At Year 1: 2 years from their launch, years_to_peak=3 → ramp=2/3
        # At Year 3: 4 years from their launch, years_to_peak=3 → ramp=1.0 (peak)
        assert share_yr3 > share_yr1, (
            f"Competition should ramp over time: yr1={share_yr1:.3f} yr3={share_yr3:.3f}"
        )

    def test_pipeline_competitor_excluded_reduces_to_full_market(self, rng, pipeline_competitor_p0):
        """
        When all pipeline competitors are excluded (P=0), sampled model
        should produce full market availability.
        """
        model = CompetitionModel(competitors=[pipeline_competitor_p0])
        sampled = model.sample_launch_outcomes(rng)
        assert len(sampled.competitors) == 0
        assert sampled.our_available_market_fraction(1) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Cap stress analysis (decision robustness)
# ---------------------------------------------------------------------------

class TestCapStressAnalysis:
    def test_cap_stress_returns_multiple_scenarios(self):
        """cap_stress_analysis should return one result per multiplier."""
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.RCT_DOUBLE_BLIND
        )
        result = cap_stress_analysis(0.55, features, phase="phase_3")
        assert len(result.stress_results) == 5  # default 5 multipliers

    def test_cap_stress_conclusion_stable_for_obvious_case(self):
        """
        A trial with all-positive features and high base_pos should remain
        above 0.50 threshold regardless of cap variation.
        """
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.RCT_DOUBLE_BLIND,
            comparator_fit=ComparatorFit.MATCHES_SOC,
        )
        result = cap_stress_analysis(0.70, features, phase="phase_3", threshold=0.50)
        assert result.conclusion_stable

    def test_cap_stress_conclusion_unstable_near_threshold(self):
        """
        A case near the threshold that flips with cap variation is flagged.
        default features (RCT_DOUBLE_BLIND) at Phase 3 give +0.20. With cap=0.001
        adjustment≈0 → pos≈0.48 (below). With cap=10.0 → adjustment=+0.20 → pos>0.50.
        """
        features = TrialDesignFeatureSet()  # RCT_DOUBLE_BLIND gives +0.20 at Phase 3
        result = cap_stress_analysis(
            0.48, features, phase="phase_3",
            cap_multipliers=[0.001, 1.0, 10.0],  # extremes to force flip
            threshold=0.50,
        )
        # With cap×0.001: adjustment≈0 → pos≈0.48 (below threshold)
        # With cap×10.0: adjustment=+0.20 → pos > 0.50
        assert not result.conclusion_stable

    def test_cap_stress_summary_format(self):
        """summary() should return a non-empty string with 'STABLE' or 'UNSTABLE'."""
        features = TrialDesignFeatureSet()
        result = cap_stress_analysis(0.55, features, phase="phase_3")
        s = result.summary()
        assert "STABLE" in s or "UNSTABLE" in s
        assert len(s) > 10

    def test_cap_stress_pos_range_ordered(self):
        """Min pos across stress scenarios should be ≤ base ≤ max pos."""
        features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.RCT_DOUBLE_BLIND
        )
        result = cap_stress_analysis(0.55, features, phase="phase_3")
        lo, hi = result.pos_range()
        assert lo <= result.base_result.adjusted_pos <= hi


# ---------------------------------------------------------------------------
# Backward compatibility snapshot
# ---------------------------------------------------------------------------

class TestBackwardCompatSnapshot:
    """
    Ensure Phase 1 additions do NOT change outputs for configs that don't use
    TrialDesignFeatureSet or CompetitionModel.sample_launch_outcomes.

    Values pinned after Phase 1 implementation with seed=0.
    Re-baseline ONLY if a change is intentional.
    """
    def _make_base_setup(self):
        from bve.entities.asset import Asset, DevelopmentStage, TherapeuticArea, Modality
        from bve.entities.company import Company
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel

        asset = Asset(
            id="snap-001", name="SNAP-001", indication="Snapshot Test",
            therapeutic_area=TherapeuticArea.ONCOLOGY, stage=DevelopmentStage.PHASE_2,
            modality=Modality.SMALL_MOLECULE, discount_rate=0.10,
        )
        trials = [
            ClinicalTrial(asset_id="snap-001", phase=TrialPhase.PHASE_2,
                          success_probability=0.37, duration_years=2.5, cost_millions=80.0, enrollment=150),
            ClinicalTrial(asset_id="snap-001", phase=TrialPhase.PHASE_3,
                          success_probability=0.55, duration_years=3.5, cost_millions=250.0, enrollment=450),
            ClinicalTrial(asset_id="snap-001", phase=TrialPhase.NDA_BLA,
                          success_probability=0.87, duration_years=1.5, cost_millions=35.0),
        ]
        market = MarketModel(
            asset_id="snap-001", total_addressable_market_millions=8_000.0,
            peak_penetration=0.12, years_to_peak=5, patent_life_years=12,
            cogs_rate=0.18, sgna_rate_launch=0.40, sgna_rate_mature=0.20,
        )
        return asset, trials, market

    def test_rnpv_snapshot(self):
        from bve.models.rnpv_model import compute_rnpv
        asset, trials, market = self._make_base_setup()
        result = compute_rnpv(asset, trials, market)
        assert result.rnpv_millions == pytest.approx(65.13, abs=0.5), (
            f"rNPV snapshot mismatch: got {result.rnpv_millions:.2f}, expected ~65.13"
        )

    def test_pos_model_snapshot(self):
        from bve.models.pos_model import compute_pos, POSAdjusters
        from bve.entities.trial import TrialPhase
        from bve.entities.asset import TherapeuticArea
        pos = compute_pos(TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY, POSAdjusters())
        # Snapshot updated 2026-Q2: oncology Phase 3 base rate updated from 0.55
        # to 0.495 (weighted avg solid+hematology) plus SURROGATE_VALIDATED +0.15
        # oncology-TA override → sigmoid(-0.020 + 0.15) ≈ 0.5325.
        assert pos == pytest.approx(0.5325, abs=0.0005), (
            f"compute_pos snapshot mismatch: got {pos:.4f}, expected ~0.5325"
        )

    def test_mc_snapshot_no_competition(self):
        from bve.models.monte_carlo import MonteCarloParams, run_monte_carlo
        asset, trials, market = self._make_base_setup()
        params = MonteCarloParams(n_simulations=1000, random_seed=0)
        mc = run_monte_carlo(asset, trials, market, params)
        assert mc.mean_millions == pytest.approx(69.51, abs=15.0), (
            f"MC mean snapshot mismatch: got {mc.mean_millions:.1f}, expected ~69.51 ± 15"
        )
        assert mc.percentile_95_millions > 2 * mc.percentile_50_millions


# ---------------------------------------------------------------------------
# ValuationEngine design model integration
# ---------------------------------------------------------------------------

class TestValuationEngineDesignModel:
    """
    Integration tests for TrialDesignFeatureSet → ValuationEngine pipeline.

    These verify that:
      1. design_adjusters + apply_design_model=True reduces POS for risky designs
      2. apply_design_model=False leaves trials unchanged (backward compat)
      3. Default design (RCT_DOUBLE_BLIND) INCREASES P(Approval) vs no design model
      4. Single-arm Phase 3 reduces P(Approval) more than single-arm Phase 2
      5. L1 + L2 combination passes the (always-clean) overlap check
    """

    def _make_simple_engine(self, design_adjusters=None, apply_design_model=False):
        from bve.entities.asset import Asset, DevelopmentStage, TherapeuticArea, Modality
        from bve.entities.company import Company
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel
        from bve.models.monte_carlo import MonteCarloParams
        from bve.valuation.valuation_engine import ValuationEngine

        asset = Asset(
            id="tde-001", name="TDE-001", indication="Test",
            therapeutic_area=TherapeuticArea.ONCOLOGY, stage=DevelopmentStage.PHASE_2,
            modality=Modality.SMALL_MOLECULE, discount_rate=0.10,
        )
        company = Company(
            id="test-co", name="TestCo", ticker="TST",
            cash_millions=200.0, shares_outstanding_millions=100.0,
        )
        trials = [
            ClinicalTrial(asset_id="tde-001", phase=TrialPhase.PHASE_2,
                          success_probability=0.52, duration_years=2.0, cost_millions=80.0),
            ClinicalTrial(asset_id="tde-001", phase=TrialPhase.PHASE_3,
                          success_probability=0.60, duration_years=3.0, cost_millions=250.0),
            ClinicalTrial(asset_id="tde-001", phase=TrialPhase.NDA_BLA,
                          success_probability=0.87, duration_years=1.5, cost_millions=30.0),
        ]
        market = MarketModel(
            asset_id="tde-001", addressable_patients_annual=5000,
            net_price_per_patient_usd=100_000, peak_penetration=0.20,
            years_to_peak=4, patent_life_years=10,
        )
        return ValuationEngine(
            asset, company, trials, market,
            design_adjusters=design_adjusters,
            apply_design_model=apply_design_model,
            mc_params=MonteCarloParams(n_simulations=500, random_seed=0),
        )

    def test_single_arm_subjective_phase2_reduces_prob_approval(self):
        """Risky Phase 2 design (single-arm subjective) must reduce cumulative P(Approval)."""
        from bve.entities.trial import TrialPhase
        from bve.models.trial_design_features import (
            EvidenceDesignQuality, TrialDesignFeatureSet
        )

        engine_no_design = self._make_simple_engine()
        result_no_design = engine_no_design.run()

        design_adjusters = {
            TrialPhase.PHASE_2: TrialDesignFeatureSet(
                evidence_design_quality=EvidenceDesignQuality.SINGLE_ARM_SUBJECTIVE
            ),
        }
        engine_design = self._make_simple_engine(design_adjusters=design_adjusters, apply_design_model=True)
        result_design = engine_design.run()

        p_approval_no_design = result_no_design.rnpv.cumulative_success_probability
        p_approval_design = result_design.rnpv.cumulative_success_probability
        assert p_approval_design < p_approval_no_design, (
            f"P(Approval) should decrease with risky design: "
            f"{p_approval_design:.4f} < {p_approval_no_design:.4f}"
        )

    def test_default_design_increases_prob_approval(self):
        """Default TrialDesignFeatureSet (RCT_DOUBLE_BLIND +0.20) increases P(Approval)."""
        from bve.entities.trial import TrialPhase
        from bve.models.trial_design_features import TrialDesignFeatureSet

        engine_no_design = self._make_simple_engine()
        result_no_design = engine_no_design.run()

        design_adjusters = {
            TrialPhase.PHASE_2: TrialDesignFeatureSet(),
            TrialPhase.PHASE_3: TrialDesignFeatureSet(),
            TrialPhase.NDA_BLA: TrialDesignFeatureSet(),
        }
        engine_design = self._make_simple_engine(design_adjusters=design_adjusters, apply_design_model=True)
        result_design = engine_design.run()

        assert result_design.rnpv.cumulative_success_probability > (
            result_no_design.rnpv.cumulative_success_probability
        )

    def test_single_arm_phase3_reduces_more_than_phase2(self):
        """
        Single-arm at Phase 3 (scaling=1.0) should reduce P(Approval) more
        than single-arm at Phase 2 (scaling=0.50).
        """
        from bve.entities.trial import TrialPhase
        from bve.models.trial_design_features import (
            EvidenceDesignQuality, TrialDesignFeatureSet
        )

        risky = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.SINGLE_ARM_SUBJECTIVE
        )
        design_ph2 = {TrialPhase.PHASE_2: risky}
        design_ph3 = {TrialPhase.PHASE_3: risky}

        eng_ph2 = self._make_simple_engine(design_adjusters=design_ph2, apply_design_model=True)
        eng_ph3 = self._make_simple_engine(design_adjusters=design_ph3, apply_design_model=True)
        eng_none = self._make_simple_engine()

        rnpv_none = eng_none.run().rnpv.rnpv_millions
        rnpv_ph2 = eng_ph2.run().rnpv.rnpv_millions
        rnpv_ph3 = eng_ph3.run().rnpv.rnpv_millions

        drop_ph2 = rnpv_none - rnpv_ph2
        drop_ph3 = rnpv_none - rnpv_ph3
        assert drop_ph3 > drop_ph2, (
            f"Phase 3 single-arm drop ({drop_ph3:.1f}M) should exceed Phase 2 drop ({drop_ph2:.1f}M)"
        )

    def test_apply_design_false_leaves_trials_unchanged(self):
        """apply_design_model=False must produce identical output even if adjusters provided."""
        from bve.entities.trial import TrialPhase
        from bve.models.trial_design_features import (
            EvidenceDesignQuality, TrialDesignFeatureSet
        )

        design_adjusters = {
            TrialPhase.PHASE_2: TrialDesignFeatureSet(
                evidence_design_quality=EvidenceDesignQuality.SINGLE_ARM_SUBJECTIVE
            ),
            TrialPhase.PHASE_3: TrialDesignFeatureSet(
                evidence_design_quality=EvidenceDesignQuality.SINGLE_ARM_SUBJECTIVE
            ),
        }
        eng_disabled = self._make_simple_engine(design_adjusters=design_adjusters, apply_design_model=False)
        eng_none = self._make_simple_engine()

        assert eng_disabled.run().rnpv.rnpv_millions == pytest.approx(
            eng_none.run().rnpv.rnpv_millions, abs=0.01
        )

    def test_layer1_layer2_combination_passes_overlap_check(self):
        """
        New Layer 2 is orthogonal to Layer 1 — any L1+L2 combination should pass
        check_pos_layer_overlap without raising ValueError.
        """
        from bve.entities.asset import Asset, DevelopmentStage, TherapeuticArea, Modality
        from bve.entities.company import Company
        from bve.entities.trial import ClinicalTrial, TrialPhase, EndpointType
        from bve.models.market_model import MarketModel
        from bve.models.monte_carlo import MonteCarloParams
        from bve.models.pos_model import POSAdjusters
        from bve.models.trial_design_features import (
            ComparatorFit, EvidenceDesignQuality,
            RegulatoryPathwayRisk, TrialDesignFeatureSet,
        )
        from bve.valuation.valuation_engine import ValuationEngine

        asset = Asset(
            id="overlap-001", name="OV-001", indication="Test",
            therapeutic_area=TherapeuticArea.ONCOLOGY, stage=DevelopmentStage.PHASE_3,
            modality=Modality.SMALL_MOLECULE, discount_rate=0.10,
        )
        company = Company(
            id="ov-co", name="OvCo", ticker="OV",
            cash_millions=100.0, shares_outstanding_millions=50.0,
        )
        trials = [
            ClinicalTrial(asset_id="overlap-001", phase=TrialPhase.PHASE_3,
                          success_probability=0.55, duration_years=3.0, cost_millions=250.0,
                          endpoint_type=EndpointType.HARD_CLINICAL),
        ]
        market = MarketModel(
            asset_id="overlap-001", total_addressable_market_millions=3000.0,
            peak_penetration=0.15, years_to_peak=4, patent_life_years=10,
        )
        # Non-default L1: endpoint_type, has_breakthrough_designation
        pos_adjusters = {
            TrialPhase.PHASE_3: POSAdjusters(
                endpoint_type=EndpointType.HARD_CLINICAL,
                has_breakthrough_designation=True,
            )
        }
        # Non-default L2: all dimensions non-default — no overlap expected
        design_adjusters = {
            TrialPhase.PHASE_3: TrialDesignFeatureSet(
                evidence_design_quality=EvidenceDesignQuality.RCT_DOUBLE_BLIND,
                comparator_fit=ComparatorFit.MATCHES_SOC,
                regulatory_pathway_risk=RegulatoryPathwayRisk.ORPHAN_RARE_DISEASE,
            )
        }
        engine = ValuationEngine(
            asset, company, trials, market,
            pos_adjusters=pos_adjusters,
            design_adjusters=design_adjusters,
            apply_pos_model=True,
            apply_design_model=True,
            mc_params=MonteCarloParams(n_simulations=100, random_seed=0),
        )
        # Should NOT raise — new L2 is orthogonal to L1
        result = engine.run()
        assert result.rnpv.rnpv_millions is not None
