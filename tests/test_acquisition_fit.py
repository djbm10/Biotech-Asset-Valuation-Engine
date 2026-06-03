"""Tests for acquisition fit + timing engine (Step 8)."""

from __future__ import annotations

import pytest

from bve.entities.acquirer import (
    AcquirerProfile,
    BDStyle,
    LOECliff,
    PipelineGap,
    ACQUIRER_BY_ID,
)
from bve.intelligence.acquisition_fit import (
    AcquisitionFitEngine,
    AcquisitionFitScore,
    TargetProfile,
    TimingBucket,
    DEFAULT_WEIGHTS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    return AcquisitionFitEngine()


@pytest.fixture
def oncology_acquirer():
    return AcquirerProfile(
        company_id="big_pharma",
        name="BigPharma Inc",
        cash_millions=10_000,
        annual_fcf_millions=5_000,
        strategic_areas=["oncology", "immunology"],
        preferred_modalities=["biologic", "antibody_drug_conjugate"],
        preferred_phase="Phase 3",
        pipeline_gaps=[
            PipelineGap(therapeutic_area="oncology", modality="biologic",
                        rationale="No Phase 3 biologic in solid tumors", priority="high"),
        ],
    )


@pytest.fixture
def good_target():
    return TargetProfile(
        company_id="small_bio",
        name="SmallBio",
        ticker="SMBIO",
        primary_ta="oncology",
        modality="biologic",
        current_phase="Phase 3",
        indication="NSCLC",
        market_cap_millions=800,
        cash_millions=200,
        burn_rate_monthly_millions=10,
        months_to_next_catalyst=4,
        distress_score=0.2,
        science_score=0.75,
    )


@pytest.fixture
def poor_fit_target():
    return TargetProfile(
        company_id="neuro_bio",
        name="NeuroBio",
        primary_ta="neuroscience",
        modality="gene_therapy",
        current_phase="Phase 1",
        market_cap_millions=300,
        science_score=0.50,
    )


# ---------------------------------------------------------------------------
# AcquisitionFitEngine — weight validation
# ---------------------------------------------------------------------------

class TestWeightValidation:
    def test_default_weights_sum_to_one(self):
        assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 0.01

    def test_invalid_weights_raise(self):
        bad_weights = {k: v * 2 for k, v in DEFAULT_WEIGHTS.items()}
        with pytest.raises(ValueError, match="sum to 1.0"):
            AcquisitionFitEngine(weights=bad_weights)

    def test_custom_valid_weights(self):
        w = {k: 1 / 7 for k in DEFAULT_WEIGHTS}
        engine = AcquisitionFitEngine(weights=w)
        assert engine is not None


# ---------------------------------------------------------------------------
# Strategic fit dimension
# ---------------------------------------------------------------------------

class TestStrategicFit:
    def test_ta_match_boosts_score(self, engine, oncology_acquirer, good_target):
        result = engine.score(good_target, oncology_acquirer)
        assert result.strategic_fit > 0.5

    def test_ta_mismatch_lowers_score(self, engine, oncology_acquirer, poor_fit_target):
        result = engine.score(poor_fit_target, oncology_acquirer)
        assert result.strategic_fit < 0.5

    def test_modality_match_adds_bonus(self, engine, oncology_acquirer, good_target):
        result = engine.score(good_target, oncology_acquirer)
        assert result.strategic_fit >= 0.80  # TA + modality + indication

    def test_no_modality_data_partial_credit(self, engine, oncology_acquirer):
        target = TargetProfile(
            company_id="x", name="X", primary_ta="oncology",
            modality=None, science_score=0.5
        )
        result = engine.score(target, oncology_acquirer)
        assert result.strategic_fit > 0.0


# ---------------------------------------------------------------------------
# Pipeline gap fit
# ---------------------------------------------------------------------------

class TestPipelineGapFit:
    def test_fills_high_priority_gap(self, engine, oncology_acquirer, good_target):
        result = engine.score(good_target, oncology_acquirer)
        assert result.pipeline_gap_fit > 0.5

    def test_no_gap_filled_returns_low(self, engine, oncology_acquirer, poor_fit_target):
        result = engine.score(poor_fit_target, oncology_acquirer)
        # neuroscience/gene_therapy doesn't fill oncology/biologic gap
        assert result.pipeline_gap_fit < 0.5

    def test_no_documented_gaps_neutral(self, engine, good_target):
        acquirer = AcquirerProfile(
            company_id="x", name="X", cash_millions=5_000,
            strategic_areas=["oncology"], pipeline_gaps=[]
        )
        result = engine.score(good_target, acquirer)
        assert result.pipeline_gap_fit == 0.5

    def test_critical_gap_scores_higher(self):
        engine = AcquisitionFitEngine()
        acquirer_critical = AcquirerProfile(
            company_id="x", name="X", cash_millions=5_000,
            strategic_areas=["oncology"],
            pipeline_gaps=[
                PipelineGap(therapeutic_area="oncology", rationale="critical need", priority="critical"),
            ]
        )
        acquirer_medium = AcquirerProfile(
            company_id="y", name="Y", cash_millions=5_000,
            strategic_areas=["oncology"],
            pipeline_gaps=[
                PipelineGap(therapeutic_area="oncology", rationale="medium need", priority="medium"),
            ]
        )
        target = TargetProfile(company_id="t", name="T", primary_ta="oncology", science_score=0.7)
        score_crit = engine.score(target, acquirer_critical).pipeline_gap_fit
        score_med = engine.score(target, acquirer_medium).pipeline_gap_fit
        assert score_crit > score_med


# ---------------------------------------------------------------------------
# Affordability
# ---------------------------------------------------------------------------

class TestAffordability:
    def test_cheap_target_scores_high(self, engine, oncology_acquirer):
        target = TargetProfile(
            company_id="cheap", name="CheapBio", primary_ta="oncology",
            market_cap_millions=200,  # est. deal size = 300M; firepower = 20_000M
            science_score=0.6,
        )
        result = engine.score(target, oncology_acquirer)
        assert result.affordability == 1.0

    def test_expensive_target_scores_low(self, engine, oncology_acquirer):
        target = TargetProfile(
            company_id="expensive", name="ExpensiveBio", primary_ta="oncology",
            market_cap_millions=15_000,  # deal ~22_500 >> firepower 20_000
            science_score=0.6,
        )
        result = engine.score(target, oncology_acquirer)
        assert result.affordability < 0.30

    def test_no_market_cap_neutral(self, engine, oncology_acquirer):
        target = TargetProfile(
            company_id="t", name="T", primary_ta="oncology",
            market_cap_millions=None, science_score=0.5
        )
        result = engine.score(target, oncology_acquirer)
        assert result.affordability == 0.50


# ---------------------------------------------------------------------------
# Commercial fit (phase alignment)
# ---------------------------------------------------------------------------

class TestCommercialFit:
    def test_phase3_match_preferred_phase3(self, engine, oncology_acquirer, good_target):
        # oncology_acquirer prefers Phase 3, good_target is Phase 3
        result = engine.score(good_target, oncology_acquirer)
        assert result.commercial_fit == 1.0

    def test_phase1_vs_preferred_phase3(self, engine, oncology_acquirer):
        target = TargetProfile(
            company_id="p1", name="P1Bio", primary_ta="oncology",
            current_phase="Phase 1", science_score=0.5
        )
        result = engine.score(target, oncology_acquirer)
        assert result.commercial_fit < 0.80

    def test_no_phase_preference_neutral(self, engine, good_target):
        acquirer = AcquirerProfile(
            company_id="any", name="AnyPharma", cash_millions=5_000,
            strategic_areas=["oncology"], preferred_phase="Any"
        )
        result = engine.score(good_target, acquirer)
        assert result.commercial_fit == 0.70


# ---------------------------------------------------------------------------
# Disqualifiers
# ---------------------------------------------------------------------------

class TestDisqualifiers:
    def test_too_expensive_disqualifies(self, engine):
        poor_acquirer = AcquirerProfile(
            company_id="small_acq", name="SmallAcq", cash_millions=1_000,
            annual_fcf_millions=0, strategic_areas=["oncology"]
        )
        expensive_target = TargetProfile(
            company_id="huge", name="HugeBio", primary_ta="oncology",
            market_cap_millions=5_000, science_score=0.8
        )
        result = engine.score(expensive_target, poor_acquirer)
        assert result.fit_score == 0.0
        assert len(result.disqualifiers) > 0

    def test_major_partnership_disqualifies(self, engine, oncology_acquirer):
        target = TargetProfile(
            company_id="partnered", name="PartneredBio", primary_ta="oncology",
            market_cap_millions=500, has_major_partnership=True, science_score=0.7
        )
        result = engine.score(target, oncology_acquirer)
        assert result.fit_score == 0.0
        assert any("partnership" in d.lower() for d in result.disqualifiers)


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------

class TestCompositeScore:
    def test_good_fit_scores_above_0_5(self, engine, oncology_acquirer, good_target):
        result = engine.score(good_target, oncology_acquirer)
        assert result.fit_score > 0.50

    def test_poor_fit_scores_below_good(self, engine, oncology_acquirer, good_target, poor_fit_target):
        good_score = engine.score(good_target, oncology_acquirer).fit_score
        poor_score = engine.score(poor_fit_target, oncology_acquirer).fit_score
        assert good_score > poor_score

    def test_fit_score_bounded(self, engine, oncology_acquirer, good_target):
        result = engine.score(good_target, oncology_acquirer)
        assert 0.0 <= result.fit_score <= 1.0

    def test_confidence_increases_with_data(self, engine, oncology_acquirer, good_target):
        sparse_target = TargetProfile(
            company_id="sparse", name="SparseBio", primary_ta="oncology", science_score=0.5
        )
        full_result = engine.score(good_target, oncology_acquirer)
        sparse_result = engine.score(sparse_target, oncology_acquirer)
        assert full_result.confidence > sparse_result.confidence


# ---------------------------------------------------------------------------
# Timing engine
# ---------------------------------------------------------------------------

class TestTimingEngine:
    def test_distressed_near_catalyst_is_near_term(self, engine, oncology_acquirer):
        target = TargetProfile(
            company_id="distressed", name="DistressedBio", primary_ta="oncology",
            modality="biologic", current_phase="Phase 3",
            market_cap_millions=400, cash_millions=50,
            burn_rate_monthly_millions=12,  # ~4m runway
            months_to_next_catalyst=3,
            distress_score=0.8, science_score=0.6
        )
        result = engine.score(target, oncology_acquirer)
        assert result.timing_bucket in [TimingBucket.NEAR_TERM, TimingBucket.SHORT_TERM]

    def test_healthy_no_urgency_is_longer_term(self, engine, oncology_acquirer, good_target):
        # good_target has months_to_catalyst=4 but low distress
        # No LOE urgency on acquirer
        acquirer_no_loe = AcquirerProfile(
            company_id="no_loe", name="NoLOEPharma", cash_millions=15_000,
            strategic_areas=["oncology"], loe_cliffs=[],
        )
        target = TargetProfile(
            company_id="healthy", name="HealthyBio", primary_ta="oncology",
            modality="biologic", current_phase="Phase 3",
            market_cap_millions=600, cash_millions=500,
            burn_rate_monthly_millions=10,
            distress_score=0.0, science_score=0.7
        )
        result = engine.score(target, acquirer_no_loe)
        assert result.timing_bucket in [TimingBucket.MEDIUM_TERM, TimingBucket.LONGER_TERM]

    def test_low_fit_score_gives_unlikely(self, engine):
        # Acquirer has very small firepower; target costs more than 60% → disqualified
        poor_acquirer = AcquirerProfile(
            company_id="x", name="X", cash_millions=200,
            annual_fcf_millions=0, strategic_areas=["rare_disease"]
        )
        expensive_target = TargetProfile(
            company_id="wrong_ta", name="WrongTA", primary_ta="oncology",
            market_cap_millions=500,   # deal ~750M >> 60% of 200M firepower
            science_score=0.4
        )
        result = engine.score(expensive_target, poor_acquirer)
        # disqualified by affordability → fit_score = 0 → unlikely
        assert result.timing_bucket == TimingBucket.UNLIKELY

    def test_loe_urgency_drives_earlier_timing(self):
        engine = AcquisitionFitEngine()
        loe_acquirer = AcquirerProfile(
            company_id="loe", name="LOEPharma", cash_millions=15_000,
            annual_fcf_millions=5_000,
            strategic_areas=["oncology"],
            preferred_modalities=["biologic"],
            loe_cliffs=[
                LOECliff(product_name="BigDrug", indication="cancer", peak_sales_millions=10_000,
                         loe_year=2026, revenue_at_risk_millions=9_000),
            ],
        )
        target = TargetProfile(
            company_id="t", name="OncoTarget", primary_ta="oncology",
            modality="biologic", current_phase="Phase 3",
            market_cap_millions=1_000, distress_score=0.4, science_score=0.7,
            cash_millions=100, burn_rate_monthly_millions=15,
        )
        result = engine.score(target, loe_acquirer)
        assert result.timing_bucket in [
            TimingBucket.NEAR_TERM, TimingBucket.SHORT_TERM, TimingBucket.MEDIUM_TERM
        ]

    def test_timing_drivers_populated(self, engine):
        acquirer = AcquirerProfile(
            company_id="x", name="X", cash_millions=15_000, annual_fcf_millions=5_000,
            strategic_areas=["oncology"],
            loe_cliffs=[LOECliff(product_name="D", indication="c", peak_sales_millions=8_000,
                                 loe_year=2026, revenue_at_risk_millions=7_000)]
        )
        target = TargetProfile(
            company_id="t", name="T", primary_ta="oncology",
            market_cap_millions=500, distress_score=0.7,
            science_score=0.6, cash_millions=30, burn_rate_monthly_millions=10
        )
        result = engine.score(target, acquirer)
        assert len(result.timing_drivers) > 0


# ---------------------------------------------------------------------------
# rank_targets / rank_acquirers
# ---------------------------------------------------------------------------

class TestRanking:
    def test_rank_targets_returns_sorted(self, engine, oncology_acquirer, good_target, poor_fit_target):
        ranked = engine.rank_targets([good_target, poor_fit_target], oncology_acquirer)
        assert ranked[0].target_company_id == good_target.company_id

    def test_rank_targets_min_fit_filter(self, engine, oncology_acquirer, good_target, poor_fit_target):
        ranked = engine.rank_targets(
            [good_target, poor_fit_target], oncology_acquirer, min_fit_score=0.70
        )
        for r in ranked:
            assert r.fit_score >= 0.70

    def test_rank_acquirers_returns_sorted(self, engine, good_target):
        good_acquirer = AcquirerProfile(
            company_id="gaq", name="GoodAcq", cash_millions=20_000,
            strategic_areas=["oncology"], preferred_modalities=["biologic"],
            preferred_phase="Phase 3"
        )
        bad_acquirer = AcquirerProfile(
            company_id="baq", name="BadAcq", cash_millions=5_000,
            strategic_areas=["neuroscience"]
        )
        ranked = engine.rank_acquirers(good_target, [good_acquirer, bad_acquirer])
        assert ranked[0].acquirer_company_id == "gaq"

    def test_rank_targets_empty_input(self, engine, oncology_acquirer):
        result = engine.rank_targets([], oncology_acquirer)
        assert result == []


# ---------------------------------------------------------------------------
# as_dict output
# ---------------------------------------------------------------------------

class TestAsDictOutput:
    def test_as_dict_contains_required_keys(self, engine, oncology_acquirer, good_target):
        result = engine.score(good_target, oncology_acquirer)
        d = result.as_dict()
        required = [
            "target_company_id", "acquirer_company_id", "fit_score",
            "timing_bucket", "strategic_fit", "pipeline_gap_fit",
            "affordability", "confidence", "rationale",
        ]
        for key in required:
            assert key in d

    def test_as_dict_scores_rounded(self, engine, oncology_acquirer, good_target):
        d = engine.score(good_target, oncology_acquirer).as_dict()
        assert len(str(d["fit_score"]).split(".")[-1]) <= 3


# ---------------------------------------------------------------------------
# Integration with real ACQUIRER_UNIVERSE
# ---------------------------------------------------------------------------

class TestRealAcquirerUniverse:
    def test_score_against_merck(self, engine, good_target):
        merck = ACQUIRER_BY_ID["merck"]
        result = engine.score(good_target, merck)
        assert 0.0 <= result.fit_score <= 1.0

    def test_pfizer_prefers_phase3(self, engine):
        pfizer = ACQUIRER_BY_ID["pfizer"]
        p3_target = TargetProfile(
            company_id="p3t", name="Phase3Target", primary_ta="oncology",
            modality="biologic", current_phase="Phase 3",
            market_cap_millions=2_000, science_score=0.7
        )
        p2_target = TargetProfile(
            company_id="p2t", name="Phase2Target", primary_ta="oncology",
            modality="biologic", current_phase="Phase 2",
            market_cap_millions=800, science_score=0.7
        )
        r3 = engine.score(p3_target, pfizer)
        r2 = engine.score(p2_target, pfizer)
        assert r3.commercial_fit >= r2.commercial_fit

    def test_rank_multiple_acquirers_for_oncology_target(self, engine):
        from bve.entities.acquirer import ACQUIRER_UNIVERSE
        target = TargetProfile(
            company_id="onco_t", name="OncoTarget", primary_ta="oncology",
            modality="antibody_drug_conjugate", current_phase="Phase 3",
            market_cap_millions=1_500, science_score=0.80,
        )
        ranked = engine.rank_acquirers(target, ACQUIRER_UNIVERSE)
        # Should return non-empty list; best fits should have oncology coverage
        assert len(ranked) > 0
        assert ranked[0].fit_score > 0.0
