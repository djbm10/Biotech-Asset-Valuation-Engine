from __future__ import annotations

from pathlib import Path

import pytest

from bve.intelligence.acquirer_fit import (
    AcquirerFitCandidate,
    AcquirerFitScorer,
)
from bve.intelligence.acquirer_profiles import AcquirerProfileLoader
from bve.intelligence.acquisition_screen import AcquisitionScreenRow
from bve.intelligence.comparable_deals import ComparableDealAnalysis


def test_acquirer_fit_scores_strong_regeneron_match():
    profile = _regeneron()
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-eye-1",
        ticker="EYE1",
        company_name="RetinaCo",
        therapeutic_area="ophthalmology",
        modality="fully_human_antibody",
        stage="phase_3",
        enterprise_value_millions=800.0,
        acquisition_ready=True,
        priority_tags=["retinal disease", "ophthalmology"],
    )
    comps = ComparableDealAnalysis(
        asset_ev_to_peak_sales=1.4,
        match_tier="therapeutic_area_phase",
        n_comps=3,
        peer_median_ev_to_peak_sales=2.0,
        premium_discount_vs_median=-0.30,
    )

    score = scorer.score_target(acquirer=profile, target=target, comparable_analysis=comps)

    assert score.passes_hard_filters is True
    assert score.hard_fail_reasons == []
    assert score.matched_therapeutic_gap == "ophthalmology"
    assert score.matched_modality == "fully_human_antibody"
    assert score.valuation_source == "comparable_deals"
    assert "matches ophthalmology gap" in score.explanation
    assert score.fit_score > 0.85


def test_acquirer_fit_flags_outside_budget():
    profile = _regeneron()
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-big-1",
        ticker="BIG1",
        company_name="MegaGene",
        therapeutic_area="genetic medicines",
        modality="genetic_medicine",
        stage="phase_3",
        enterprise_value_millions=25000.0,
        acquisition_ready=True,
        priority_tags=["genetics", "rare disease"],
    )

    score = scorer.score_target(acquirer=profile, target=target)

    assert score.passes_hard_filters is False
    assert "outside_budget" in score.hard_fail_reasons
    assert score.budget_score == 0.0
    assert score.fit_score < score.raw_fit_score


def test_acquirer_fit_requires_phase_2_target_to_be_acquisition_ready():
    profile = _regeneron()
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-phase2-1",
        ticker="P2A",
        company_name="InflamCo",
        therapeutic_area="immunology",
        modality="bispecific_antibody",
        stage="phase_2",
        enterprise_value_millions=600.0,
        acquisition_ready=False,
        acquisition_readiness_bucket="phase_2_pre_poc",
        priority_tags=["immunology"],
    )

    score = scorer.score_target(acquirer=profile, target=target)

    assert score.passes_hard_filters is False
    assert "not_acquisition_ready" in score.hard_fail_reasons
    assert score.stage_score == pytest.approx(0.35, abs=1e-9)


def test_acquirer_fit_prefers_cheaper_comp_relative_valuation():
    profile = _regeneron()
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-ob-1",
        ticker="OB1",
        company_name="MetaCo",
        therapeutic_area="obesity",
        modality="dual_glp1_gip",
        stage="phase_3",
        enterprise_value_millions=1200.0,
        acquisition_ready=True,
        priority_tags=["obesity", "metabolic"],
    )
    cheap = ComparableDealAnalysis(
        asset_ev_to_peak_sales=1.0,
        match_tier="phase_only",
        n_comps=4,
        peer_median_ev_to_peak_sales=1.8,
        premium_discount_vs_median=-0.25,
    )
    rich = ComparableDealAnalysis(
        asset_ev_to_peak_sales=2.8,
        match_tier="phase_only",
        n_comps=4,
        peer_median_ev_to_peak_sales=1.8,
        premium_discount_vs_median=0.55,
    )

    cheap_score = scorer.score_target(acquirer=profile, target=target, comparable_analysis=cheap)
    rich_score = scorer.score_target(acquirer=profile, target=target, comparable_analysis=rich)

    assert cheap_score.valuation_score > rich_score.valuation_score
    assert cheap_score.fit_score > rich_score.fit_score


def test_candidate_from_acquisition_row_preserves_screen_context():
    row = AcquisitionScreenRow(
        asset_id="asset-row-1",
        company_id="company-row-1",
        ticker="ROW1",
        snapshot_date="2026-03-24",
        therapeutic_area="ophthalmology",
        indication="wet AMD",
        stage="phase_3",
        enterprise_value_millions=950.0,
        acquisition_discount=2.0,
        acquisition_ready=True,
        acquisition_readiness_bucket="phase_3_or_later",
        ev_to_peak_sales=1.5,
    )

    candidate = AcquirerFitCandidate.from_acquisition_row(
        row,
        modality="fully_human_antibody",
        priority_tags=["ophthalmology"],
        company_name="RetinaCo",
    )

    assert candidate.asset_id == "asset-row-1"
    assert candidate.company_id == "company-row-1"
    assert candidate.modality == "fully_human_antibody"
    assert candidate.enterprise_value_millions == pytest.approx(950.0, abs=1e-9)
    assert candidate.priority_tags == ["ophthalmology"]


def _regeneron():
    dataset = AcquirerProfileLoader.load(Path("research/mna/pipeline_gaps.yaml"))
    return AcquirerProfileLoader.get_acquirer(dataset, "regeneron")
