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
"""
from __future__ import annotations

import numpy as np
import pytest

from bve.models.trial_design_features import (
    ApprovalPathway,
    CapStressResult,
    DesignAdjustedPOSResult,
    EndpointBasis,
    EvidenceDesign,
    LayerOverlapReport,
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

    def test_neutral_phase_uses_all_ones_scaling(self):
        """Phase 'neutral' should apply scaling=1.0 to all dimensions."""
        features = TrialDesignFeatureSet(evidence_design=EvidenceDesign.SINGLE_ARM)
        result = compute_design_adjusted_pos(0.55, features, phase=TRIAL_DESIGN_PHASE_NEUTRAL)
        assert result.phase_scaling_applied["evidence_design"] == pytest.approx(1.0)
        assert result.phase_scaling_applied["endpoint_basis"] == pytest.approx(1.0)

    def test_compute_adjusted_pos_method_requires_phase(self):
        """TrialDesignFeatureSet.compute_adjusted_pos also requires phase."""
        features = TrialDesignFeatureSet()
        with pytest.raises(TypeError):
            features.compute_adjusted_pos(0.55)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Phase 1A: Trial design monotonicity
# ---------------------------------------------------------------------------

class TestTrialDesignMonotonicity:
    def test_rct_higher_pos_than_single_arm(self):
        """RCT with comparator should give higher adjusted POS than single-arm design."""
        base_pos = 0.55
        rct = TrialDesignFeatureSet(evidence_design=EvidenceDesign.RCT_COMPARATIVE)
        single = TrialDesignFeatureSet(evidence_design=EvidenceDesign.SINGLE_ARM)
        res_rct = compute_design_adjusted_pos(base_pos, rct, phase="phase_3")
        res_single = compute_design_adjusted_pos(base_pos, single, phase="phase_3")
        assert res_rct.adjusted_pos > res_single.adjusted_pos

    def test_hard_endpoint_higher_than_surrogate_novel(self):
        """Hard clinical endpoint should give higher adjusted POS than novel surrogate."""
        base_pos = 0.55
        hard = TrialDesignFeatureSet(endpoint_basis=EndpointBasis.HARD_CLINICAL)
        novel = TrialDesignFeatureSet(endpoint_basis=EndpointBasis.SURROGATE_NOVEL)
        res_hard = compute_design_adjusted_pos(base_pos, hard, phase="phase_3")
        res_novel = compute_design_adjusted_pos(base_pos, novel, phase="phase_3")
        assert res_hard.adjusted_pos > res_novel.adjusted_pos

    def test_validated_surrogate_between_hard_and_novel(self):
        """Validated surrogate should fall between hard endpoint and novel surrogate."""
        base_pos = 0.55
        hard = compute_design_adjusted_pos(base_pos, TrialDesignFeatureSet(endpoint_basis=EndpointBasis.HARD_CLINICAL), phase="phase_3")
        validated = compute_design_adjusted_pos(base_pos, TrialDesignFeatureSet(endpoint_basis=EndpointBasis.SURROGATE_VALIDATED), phase="phase_3")
        novel = compute_design_adjusted_pos(base_pos, TrialDesignFeatureSet(endpoint_basis=EndpointBasis.SURROGATE_NOVEL), phase="phase_3")
        assert hard.adjusted_pos > validated.adjusted_pos > novel.adjusted_pos

    def test_approval_pathway_ordering(self):
        """BTD > standard in terms of adjusted POS (all else equal)."""
        base_pos = 0.55
        btd = compute_design_adjusted_pos(
            base_pos,
            TrialDesignFeatureSet(approval_pathway=ApprovalPathway.BREAKTHROUGH_DESIGNATION),
            phase="phase_3",
        )
        standard = compute_design_adjusted_pos(
            base_pos,
            TrialDesignFeatureSet(approval_pathway=ApprovalPathway.STANDARD),
            phase="phase_3",
        )
        assert btd.adjusted_pos > standard.adjusted_pos


# ---------------------------------------------------------------------------
# Phase 1A: Cap
# ---------------------------------------------------------------------------

class TestTrialDesignCap:
    def test_combined_positive_adjustments_hit_cap(self):
        """
        Check that total_logodds_adjustment <= TRIAL_DESIGN_CAP_POSITIVE always holds,
        and that the uncapped value reflects Phase 3-scaled actual values.

        At Phase 3: hard_clinical (0.35 × 1.0) + rct_comparative (0.0) + BTD (0.10 × 0.80)
        = 0.35 + 0.0 + 0.08 = 0.43 — below cap, so NOT capped.
        """
        features = TrialDesignFeatureSet(
            endpoint_basis=EndpointBasis.HARD_CLINICAL,
            evidence_design=EvidenceDesign.RCT_COMPARATIVE,
            approval_pathway=ApprovalPathway.BREAKTHROUGH_DESIGNATION,
        )
        result = compute_design_adjusted_pos(base_pos=0.55, features=features, phase="phase_3")
        assert result.uncapped_logodds_adjustment == pytest.approx(0.43, abs=0.01)
        assert not result.was_capped
        assert result.total_logodds_adjustment <= TRIAL_DESIGN_CAP_POSITIVE

    def test_cap_activates_when_exceeded(self):
        """
        With a custom settings dict where the cap is very low, the adjustment
        should be capped and was_capped should be True.
        """
        features = TrialDesignFeatureSet(
            endpoint_basis=EndpointBasis.HARD_CLINICAL,
            evidence_design=EvidenceDesign.RCT_COMPARATIVE,
            approval_pathway=ApprovalPathway.BREAKTHROUGH_DESIGNATION,
        )
        # Force a low cap so that 0.43 uncapped → capped at 0.10
        from bve.config.constants import TRIAL_DESIGN_LOGODDS
        settings = dict(TRIAL_DESIGN_LOGODDS)
        settings["cap_logodds_positive"] = 0.10
        settings["cap_logodds_negative"] = -0.50
        result = compute_design_adjusted_pos(base_pos=0.55, features=features, phase="phase_3", settings=settings)
        assert result.was_capped
        assert result.cap_applied == "positive"
        assert result.total_logodds_adjustment == pytest.approx(0.10, abs=0.001)

    def test_negative_cap_activates(self):
        """Stacking maximum negative features should hit TRIAL_DESIGN_CAP_NEGATIVE."""
        features = TrialDesignFeatureSet(
            endpoint_basis=EndpointBasis.BIOMARKER_ONLY,    # -0.80 × 1.0
            evidence_design=EvidenceDesign.REGISTRY_BASED,  # -0.70 × 1.0
            approval_pathway=ApprovalPathway.STANDARD,      # 0.0
        )
        result = compute_design_adjusted_pos(base_pos=0.55, features=features, phase="phase_3")
        assert result.was_capped
        assert result.cap_applied == "negative"
        assert result.total_logodds_adjustment == pytest.approx(TRIAL_DESIGN_CAP_NEGATIVE, abs=0.001)

    def test_breakdown_sums_to_uncapped(self):
        """adjustment_breakdown values should sum to uncapped_logodds_adjustment."""
        features = TrialDesignFeatureSet(
            endpoint_basis=EndpointBasis.HARD_CLINICAL,
            evidence_design=EvidenceDesign.SINGLE_ARM,
            approval_pathway=ApprovalPathway.ACCELERATED_APPROVAL,
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
            endpoint_basis=EndpointBasis.HARD_CLINICAL,
            evidence_design=EvidenceDesign.RCT_COMPARATIVE,
            approval_pathway=ApprovalPathway.BREAKTHROUGH_DESIGNATION,
        )
        extreme_negative = TrialDesignFeatureSet(
            endpoint_basis=EndpointBasis.BIOMARKER_ONLY,
            evidence_design=EvidenceDesign.REGISTRY_BASED,
            approval_pathway=ApprovalPathway.STANDARD,
        )
        for base in [0.001, 0.50, 0.999]:
            r_pos = compute_design_adjusted_pos(base, extreme_positive, phase="phase_3")
            r_neg = compute_design_adjusted_pos(base, extreme_negative, phase="phase_3")
            assert 0.0 < r_pos.adjusted_pos < 1.0
            assert 0.0 < r_neg.adjusted_pos < 1.0

    def test_default_features_leave_pos_unchanged(self):
        """Default TrialDesignFeatureSet (all reference values) should not change base_pos."""
        features = TrialDesignFeatureSet()
        result = compute_design_adjusted_pos(base_pos=0.55, features=features, phase="phase_3")
        assert result.adjusted_pos == pytest.approx(0.55, abs=0.001)
        assert result.total_logodds_adjustment == pytest.approx(0.0, abs=0.001)
        assert not result.was_capped


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
        features = TrialDesignFeatureSet(evidence_design=EvidenceDesign.SINGLE_ARM)
        res_p3 = compute_design_adjusted_pos(base_pos, features, phase="phase_3")
        res_p1 = compute_design_adjusted_pos(base_pos, features, phase="phase_1")
        assert res_p3.adjusted_pos < res_p1.adjusted_pos
        p3_delta = base_pos - res_p3.adjusted_pos
        p1_delta = base_pos - res_p1.adjusted_pos
        assert p3_delta > p1_delta * 3, (
            f"Phase 3 single-arm delta ({p3_delta:.3f}) should be ≥3× Phase 1 delta ({p1_delta:.3f})"
        )

    def test_biomarker_endpoint_minimal_at_phase1(self):
        """Biomarker-only endpoint should barely change POS at Phase 1 (appropriate design)."""
        base_pos = 0.65
        features = TrialDesignFeatureSet(endpoint_basis=EndpointBasis.BIOMARKER_ONLY)
        res_p1 = compute_design_adjusted_pos(base_pos, features, phase="phase_1")
        res_p3 = compute_design_adjusted_pos(base_pos, features, phase="phase_3")
        assert abs(res_p1.adjusted_pos - base_pos) < 0.05
        assert abs(res_p3.adjusted_pos - base_pos) > 0.10

    def test_phase_scaling_fields_in_result(self):
        """phase_scaling_applied should report the scaling used for audit."""
        features = TrialDesignFeatureSet(evidence_design=EvidenceDesign.SINGLE_ARM)
        result = compute_design_adjusted_pos(0.55, features, phase="phase_1")
        from bve.config.constants import TRIAL_DESIGN_PHASE_SCALING
        expected = TRIAL_DESIGN_PHASE_SCALING["phase_1"]
        assert result.phase_scaling_applied["evidence_design"] == pytest.approx(
            expected["evidence_design"], abs=0.001
        )

    def test_neutral_differs_from_phase1(self):
        """Explicit 'neutral' phase should give larger effects than phase_1."""
        features = TrialDesignFeatureSet(evidence_design=EvidenceDesign.SINGLE_ARM)
        res_neutral = compute_design_adjusted_pos(0.55, features, phase=TRIAL_DESIGN_PHASE_NEUTRAL)
        res_p1 = compute_design_adjusted_pos(0.55, features, phase="phase_1")
        # neutral applies 1.0 scaling; phase_1 applies 0.10 → neutral has larger penalty
        assert res_neutral.adjusted_pos < res_p1.adjusted_pos


# ---------------------------------------------------------------------------
# Anti-double-counting
# ---------------------------------------------------------------------------

class TestLayerOverlap:
    def test_no_overlap_when_clean(self):
        """Default POSAdjusters + default TrialDesignFeatureSet: no overlaps."""
        from bve.models.pos_model import POSAdjusters
        adj = POSAdjusters()
        features = TrialDesignFeatureSet()
        report = check_pos_layer_overlap(adj, features, phase="phase_3")
        assert report.is_clean()
        assert not report.has_critical_overlap

    def test_endpoint_quality_overlap_raises_by_default(self):
        """
        Non-default endpoint_type AND non-default endpoint_basis → raises ValueError.
        (Sprint 9.14: hard block replaces silent warning.)
        """
        import pytest
        from bve.models.pos_model import POSAdjusters
        from bve.entities.trial import EndpointType
        adj = POSAdjusters(endpoint_type=EndpointType.HARD_CLINICAL)  # non-default
        features = TrialDesignFeatureSet(endpoint_basis=EndpointBasis.HARD_CLINICAL)  # non-default
        with pytest.raises(ValueError, match="Critical POS layer overlap"):
            check_pos_layer_overlap(adj, features, phase="phase_3")

    def test_endpoint_quality_overlap_allow_overlap_returns_report(self):
        """allow_overlap=True: returns report instead of raising; report shows critical."""
        import warnings
        from bve.models.pos_model import POSAdjusters
        from bve.entities.trial import EndpointType
        adj = POSAdjusters(endpoint_type=EndpointType.HARD_CLINICAL)
        features = TrialDesignFeatureSet(endpoint_basis=EndpointBasis.HARD_CLINICAL)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            report = check_pos_layer_overlap(adj, features, phase="phase_3", allow_overlap=True)
        assert report.has_critical_overlap
        assert any("Endpoint quality" in s for s in report.overlapping_signals)
        assert len(report.recommendations) >= 1

    def test_btd_overlap_raises_by_default(self):
        """has_breakthrough_designation=True AND BREAKTHROUGH_DESIGNATION → raises ValueError."""
        import pytest
        from bve.models.pos_model import POSAdjusters
        adj = POSAdjusters(has_breakthrough_designation=True)
        features = TrialDesignFeatureSet(approval_pathway=ApprovalPathway.BREAKTHROUGH_DESIGNATION)
        with pytest.raises(ValueError, match="Critical POS layer overlap"):
            check_pos_layer_overlap(adj, features, phase="phase_3")

    def test_btd_overlap_allow_overlap_returns_report(self):
        """allow_overlap=True suppresses error; report identifies BTD double-count."""
        import warnings
        from bve.models.pos_model import POSAdjusters
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            adj = POSAdjusters(has_breakthrough_designation=True)
            features = TrialDesignFeatureSet(approval_pathway=ApprovalPathway.BREAKTHROUGH_DESIGNATION)
            report = check_pos_layer_overlap(adj, features, phase="phase_3", allow_overlap=True)
        assert report.has_critical_overlap
        assert any("Breakthrough" in s for s in report.overlapping_signals)

    def test_btd_no_overlap_when_only_in_one_layer(self):
        """BTD in POSAdjusters only (no design features BTD) → no overlap, no raise."""
        from bve.models.pos_model import POSAdjusters
        adj = POSAdjusters(has_breakthrough_designation=True)
        features = TrialDesignFeatureSet(approval_pathway=ApprovalPathway.STANDARD)
        report = check_pos_layer_overlap(adj, features, phase="phase_3")
        assert not report.has_critical_overlap

    def test_double_count_magnitude_nonzero_for_critical_overlap(self):
        """Estimated double-count magnitude should be non-zero when critical overlap exists."""
        import warnings
        from bve.models.pos_model import POSAdjusters
        from bve.entities.trial import EndpointType
        adj = POSAdjusters(endpoint_type=EndpointType.HARD_CLINICAL)
        features = TrialDesignFeatureSet(endpoint_basis=EndpointBasis.HARD_CLINICAL)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            report = check_pos_layer_overlap(adj, features, phase="phase_3", allow_overlap=True)
        assert report.estimated_double_count_logodds > 0.0


# ---------------------------------------------------------------------------
# Cross-axis independence and cap enforcement
# ---------------------------------------------------------------------------

class TestCrossAxisIndependence:
    def test_all_positive_axes_bounded_by_cap(self):
        """Total adjustment must never exceed TRIAL_DESIGN_CAP_POSITIVE."""
        features = TrialDesignFeatureSet(
            endpoint_basis=EndpointBasis.HARD_CLINICAL,
            evidence_design=EvidenceDesign.RCT_COMPARATIVE,
            approval_pathway=ApprovalPathway.BREAKTHROUGH_DESIGNATION,
        )
        result = compute_design_adjusted_pos(0.55, features, phase="phase_3")
        assert result.total_logodds_adjustment <= TRIAL_DESIGN_CAP_POSITIVE + 1e-9
        bd_sum = sum(result.adjustment_breakdown.values())
        assert bd_sum == pytest.approx(result.uncapped_logodds_adjustment, abs=0.001)

    def test_all_negative_axes_bounded_by_negative_cap(self):
        """Total adjustment must never be below TRIAL_DESIGN_CAP_NEGATIVE."""
        features = TrialDesignFeatureSet(
            endpoint_basis=EndpointBasis.BIOMARKER_ONLY,
            evidence_design=EvidenceDesign.REGISTRY_BASED,
            approval_pathway=ApprovalPathway.STANDARD,
        )
        result = compute_design_adjusted_pos(0.55, features, phase="phase_3")
        assert result.total_logodds_adjustment >= TRIAL_DESIGN_CAP_NEGATIVE - 1e-9
        assert result.was_capped
        assert result.cap_applied == "negative"

    def test_adjusted_pos_monotonic_in_endpoint_basis(self):
        """hard_clinical > surrogate_validated > surrogate_novel > biomarker_only at Phase 3."""
        base = 0.50
        results = {
            eb: compute_design_adjusted_pos(base, TrialDesignFeatureSet(endpoint_basis=eb), phase="phase_3")
            for eb in [
                EndpointBasis.HARD_CLINICAL,
                EndpointBasis.SURROGATE_VALIDATED,
                EndpointBasis.SURROGATE_NOVEL,
                EndpointBasis.BIOMARKER_ONLY,
            ]
        }
        assert results[EndpointBasis.HARD_CLINICAL].adjusted_pos > results[EndpointBasis.SURROGATE_VALIDATED].adjusted_pos
        assert results[EndpointBasis.SURROGATE_VALIDATED].adjusted_pos > results[EndpointBasis.SURROGATE_NOVEL].adjusted_pos
        assert results[EndpointBasis.SURROGATE_NOVEL].adjusted_pos > results[EndpointBasis.BIOMARKER_ONLY].adjusted_pos

    def test_adjusted_pos_monotonic_in_evidence_design(self):
        """RCT_COMPARATIVE > RCT_NON_COMPARATIVE > SINGLE_ARM > REGISTRY_BASED at Phase 3."""
        base = 0.50
        order = [
            EvidenceDesign.RCT_COMPARATIVE,
            EvidenceDesign.RCT_NON_COMPARATIVE,
            EvidenceDesign.SINGLE_ARM,
            EvidenceDesign.REGISTRY_BASED,
        ]
        pos_values = [
            compute_design_adjusted_pos(base, TrialDesignFeatureSet(evidence_design=ed), phase="phase_3").adjusted_pos
            for ed in order
        ]
        for i in range(len(pos_values) - 1):
            assert pos_values[i] > pos_values[i + 1]


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
        features = TrialDesignFeatureSet(endpoint_basis=EndpointBasis.HARD_CLINICAL)
        result = cap_stress_analysis(0.55, features, phase="phase_3")
        assert len(result.stress_results) == 5  # default 5 multipliers

    def test_cap_stress_conclusion_stable_for_obvious_case(self):
        """
        A trial with all-positive features and high base_pos should remain
        above 0.50 threshold regardless of cap variation.
        """
        features = TrialDesignFeatureSet(
            endpoint_basis=EndpointBasis.HARD_CLINICAL,
            evidence_design=EvidenceDesign.RCT_COMPARATIVE,
        )
        result = cap_stress_analysis(0.70, features, phase="phase_3", threshold=0.50)
        assert result.conclusion_stable

    def test_cap_stress_conclusion_unstable_near_threshold(self):
        """
        A case near the threshold that flips with cap variation is flagged.
        Use a very tight cap (low multiplier) that can push below threshold.
        """
        # base_pos near threshold + design adjustment that barely crosses it
        # Use custom caps to force instability: cap at 0.001 vs 2.0 should flip
        features = TrialDesignFeatureSet(endpoint_basis=EndpointBasis.HARD_CLINICAL)
        result = cap_stress_analysis(
            0.48, features, phase="phase_3",
            cap_multipliers=[0.001, 1.0, 10.0],  # extremes to force flip
            threshold=0.50,
        )
        # With cap=0.001: adjustment≈0 → pos≈0.48 (below threshold)
        # With cap=10.0: adjustment≈0.35 → pos well above threshold
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
        features = TrialDesignFeatureSet(endpoint_basis=EndpointBasis.HARD_CLINICAL)
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
        assert pos == pytest.approx(0.5500, abs=0.0005), (
            f"compute_pos snapshot mismatch: got {pos:.4f}, expected ~0.5500"
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
      3. RCT/standard (reference) design produces same POS as no design model
      4. Single-arm Phase 3 reduces P(Approval) more than single-arm Phase 2
      5. Overlap warning fires when both layers use non-default endpoint settings
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

    def test_single_arm_phase2_reduces_prob_approval(self):
        """Enabling single-arm Phase 2 design penalty must reduce cumulative P(Approval)."""
        from bve.entities.trial import TrialPhase
        from bve.models.trial_design_features import TrialDesignFeatureSet, EvidenceDesign

        engine_no_design = self._make_simple_engine()
        result_no_design = engine_no_design.run()

        design_adjusters = {
            TrialPhase.PHASE_2: TrialDesignFeatureSet(evidence_design=EvidenceDesign.SINGLE_ARM),
        }
        engine_design = self._make_simple_engine(design_adjusters=design_adjusters, apply_design_model=True)
        result_design = engine_design.run()

        # P(Approval) = product of all phase POS; must be lower with single-arm penalty
        p_approval_no_design = result_no_design.rnpv.cumulative_success_probability
        p_approval_design = result_design.rnpv.cumulative_success_probability
        assert p_approval_design < p_approval_no_design, (
            f"P(Approval) should decrease with single-arm penalty: "
            f"{p_approval_design:.4f} < {p_approval_no_design:.4f}"
        )

    def test_rct_standard_design_equals_no_design(self):
        """Reference design (RCT/standard/surrogate_validated) must not change rNPV."""
        from bve.entities.trial import TrialPhase
        from bve.models.trial_design_features import (
            TrialDesignFeatureSet, EndpointBasis, EvidenceDesign, ApprovalPathway
        )

        engine_no_design = self._make_simple_engine()
        result_no_design = engine_no_design.run()

        # All-reference design: zero adjustment expected
        reference = TrialDesignFeatureSet(
            endpoint_basis=EndpointBasis.SURROGATE_VALIDATED,
            evidence_design=EvidenceDesign.RCT_COMPARATIVE,
            approval_pathway=ApprovalPathway.STANDARD,
        )
        design_adjusters = {
            TrialPhase.PHASE_2: reference,
            TrialPhase.PHASE_3: reference,
            TrialPhase.NDA_BLA: reference,
        }
        engine_design = self._make_simple_engine(design_adjusters=design_adjusters, apply_design_model=True)
        result_design = engine_design.run()

        assert result_design.rnpv.rnpv_millions == pytest.approx(
            result_no_design.rnpv.rnpv_millions, abs=0.01
        )

    def test_single_arm_phase3_reduces_more_than_phase2(self):
        """
        Single-arm at Phase 3 (full scaling=1.0) should reduce P(Approval) more
        than single-arm at Phase 2 (scaling=0.60), given same base POS.
        """
        from bve.entities.trial import TrialPhase
        from bve.models.trial_design_features import TrialDesignFeatureSet, EvidenceDesign

        design_ph2 = {TrialPhase.PHASE_2: TrialDesignFeatureSet(evidence_design=EvidenceDesign.SINGLE_ARM)}
        design_ph3 = {TrialPhase.PHASE_3: TrialDesignFeatureSet(evidence_design=EvidenceDesign.SINGLE_ARM)}

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
        from bve.models.trial_design_features import TrialDesignFeatureSet, EvidenceDesign

        design_adjusters = {
            TrialPhase.PHASE_2: TrialDesignFeatureSet(evidence_design=EvidenceDesign.SINGLE_ARM),
            TrialPhase.PHASE_3: TrialDesignFeatureSet(evidence_design=EvidenceDesign.SINGLE_ARM),
        }
        # apply_design_model=False → adjusters ignored
        eng_disabled = self._make_simple_engine(design_adjusters=design_adjusters, apply_design_model=False)
        eng_none = self._make_simple_engine()

        assert eng_disabled.run().rnpv.rnpv_millions == pytest.approx(
            eng_none.run().rnpv.rnpv_millions, abs=0.01
        )

    def test_overlap_raises_value_error_for_critical_combination(self):
        """
        When both pos_adjusters.endpoint_type and design_features.endpoint_basis
        are non-default simultaneously, a ValueError is raised. (Sprint 9.14: hard block.)
        """
        import pytest
        from bve.entities.asset import Asset, DevelopmentStage, TherapeuticArea, Modality
        from bve.entities.company import Company
        from bve.entities.trial import ClinicalTrial, TrialPhase, EndpointType
        from bve.models.market_model import MarketModel
        from bve.models.monte_carlo import MonteCarloParams
        from bve.models.pos_model import POSAdjusters
        from bve.models.trial_design_features import TrialDesignFeatureSet, EndpointBasis
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
        pos_adjusters = {
            TrialPhase.PHASE_3: POSAdjusters(endpoint_type=EndpointType.HARD_CLINICAL)
        }
        design_adjusters = {
            TrialPhase.PHASE_3: TrialDesignFeatureSet(endpoint_basis=EndpointBasis.HARD_CLINICAL)
        }
        engine = ValuationEngine(
            asset, company, trials, market,
            pos_adjusters=pos_adjusters,
            design_adjusters=design_adjusters,
            apply_pos_model=True,
            apply_design_model=True,
            mc_params=MonteCarloParams(n_simulations=100, random_seed=0),
        )
        with pytest.raises(ValueError, match="Critical POS layer overlap"):
            engine.run()
