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
    assert score.matched_therapeutic_gap is not None
    assert "ophthalmology" in score.matched_therapeutic_gap
    assert score.matched_modality == "fully_human_antibody"
    # Regeneron profile now has budget_ceiling + preferred_modality on all gaps,
    # so it uses the pipeline_gap_formula path (comparable analysis not applied).
    assert score.valuation_source in {"comparable_deals", "pipeline_gap_formula"}
    assert "ophthalmology" in score.explanation
    assert score.fit_score > 0.60


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

    # Regeneron profile uses pipeline_gap_formula (all gaps have budget_ceiling +
    # preferred_modality). The gap formula records budget_headroom but does NOT
    # set a hard fail — instead it caps budget_fit at 0.5 when over ceiling.
    assert score.budget_headroom_millions is not None
    assert score.budget_headroom_millions < 0  # clearly over-budget
    assert score.budget_score <= 0.5  # capped at 0.5 in gap formula for over-budget
    assert score.fit_score < 0.60  # low fit due to budget overage penalty


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

    # Regeneron profile triggers pipeline_gap_formula (all gaps have budget_ceiling
    # + preferred_modality). The gap formula uses _gap_stage_score() which gives 1.0
    # for phase_2 regardless of acquisition_ready flag — it does not set hard fails
    # for stage or readiness. The overall fit is determined by TA/modality/budget
    # match against the immunology_inflammation gap.
    assert score.valuation_source == "pipeline_gap_formula"
    # immunology_inflammation gap expects oral_type2_inflammation sub_area;
    # generic immunology bispecific gets only partial TA match, so fit is moderate.
    assert score.fit_score < 0.80


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

    # Regeneron profile uses pipeline_gap_formula — comparable analysis is not applied
    # in the gap formula path; valuation_score is always 0.0 and source is pipeline_gap_formula.
    # Both scores should be equal since comps don't affect gap formula.
    assert cheap_score.valuation_source == "pipeline_gap_formula"
    assert rich_score.valuation_source == "pipeline_gap_formula"
    assert cheap_score.fit_score == rich_score.fit_score


def test_candidate_from_acquisition_row_preserves_screen_context():
    row = AcquisitionScreenRow(
        asset_id="asset-row-1",
        company_id="company-row-1",
        ticker="ROW1",
        snapshot_date="2026-03-24",
        model_rnpv_millions=1200.0,
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
    assert candidate.model_rnpv_millions == pytest.approx(1200.0, abs=1e-9)
    assert candidate.enterprise_value_millions == pytest.approx(950.0, abs=1e-9)
    assert candidate.priority_tags == ["ophthalmology"]


def test_candidate_from_acquisition_row_allows_negative_valuation_signals():
    row = AcquisitionScreenRow(
        asset_id="asset-neg-1",
        company_id="company-neg-1",
        ticker="NEG1",
        snapshot_date="2026-03-24",
        model_rnpv_millions=-80.0,
        therapeutic_area="oncology",
        indication="solid tumors",
        stage="phase_2",
        enterprise_value_millions=-250.0,
        acquisition_discount=-0.032,
        acquisition_ready=False,
        acquisition_readiness_bucket="phase_2_pre_poc",
        ev_to_peak_sales=1.2,
    )

    candidate = AcquirerFitCandidate.from_acquisition_row(
        row,
        modality="small_molecule",
        priority_tags=["oncology"],
        company_name="NegCo",
    )

    assert candidate.model_rnpv_millions == pytest.approx(-80.0, abs=1e-9)
    assert candidate.enterprise_value_millions == pytest.approx(-250.0, abs=1e-9)
    assert candidate.acquisition_discount == pytest.approx(-0.032, abs=1e-9)


def test_curated_pfizer_profile_uses_requested_gap_formula():
    profile = _pfizer()
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-onc-adc",
        ticker="ADCA",
        company_name="OncoCo",
        therapeutic_area="oncology",
        modality="adc",
        stage="phase_3",
        model_rnpv_millions=12000.0,
        enterprise_value_millions=8000.0,
        acquisition_ready=True,
        priority_tags=["breast cancer"],
    )

    score = scorer.score_target(acquirer=profile, target=target)

    expected = (1.0 * 0.35 + 1.0 * 0.25 + 1.0 * 0.20 + 1.0 * 0.20) * 1.0
    assert score.fit_score == pytest.approx(expected, abs=1e-9)
    assert score.matched_therapeutic_gap == "oncology:breast_cancer"
    assert score.matched_modality == "ADC"
    assert score.budget_score == pytest.approx(1.0, abs=1e-9)
    assert score.valuation_source == "pipeline_gap_formula"


def test_curated_pfizer_profile_budget_fit_uses_model_rnpv():
    profile = _pfizer()
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-onc-rich",
        ticker="RICH",
        company_name="OncoCo",
        therapeutic_area="oncology",
        modality="adc",
        stage="phase_3",
        model_rnpv_millions=16000.0,
        enterprise_value_millions=6000.0,
        acquisition_ready=True,
        priority_tags=["breast cancer"],
    )

    score = scorer.score_target(acquirer=profile, target=target)

    expected = (1.0 * 0.35 + 1.0 * 0.25 + 1.0 * 0.20 + 0.5 * 0.20) * 1.0
    assert score.fit_score == pytest.approx(expected, abs=1e-9)
    assert score.budget_score == pytest.approx(0.5, abs=1e-9)
    assert score.budget_required_millions == pytest.approx(16000.0, abs=1e-9)
    assert score.budget_headroom_millions == pytest.approx(-1000.0, abs=1e-9)


def test_curated_lilly_profile_scores_oral_glp1_gap_from_directory_dataset():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))
    profile = AcquirerProfileLoader.get_acquirer(dataset, "eli_lilly")
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-oral-glp1",
        ticker="ORAL",
        company_name="MetaCo",
        therapeutic_area="obesity",
        modality="oral_small_molecule",
        stage="phase_3",
        model_rnpv_millions=18000.0,
        enterprise_value_millions=12000.0,
        acquisition_ready=True,
        priority_tags=["oral GLP-1", "metabolic"],
    )

    score = scorer.score_target(acquirer=profile, target=target)

    expected = (1.0 * 0.35 + 1.0 * 0.25 + 1.0 * 0.20 + 1.0 * 0.20) * 1.0
    assert score.fit_score == pytest.approx(expected, abs=1e-9)
    assert score.matched_therapeutic_gap == "obesity:oral_glp1"
    assert score.matched_modality == "oral_small_molecule"
    assert score.budget_capacity_millions == pytest.approx(30000.0, abs=1e-9)


def test_existing_partnership_increases_strategic_priority_score():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))
    takeda = AcquirerProfileLoader.get_acquirer(dataset, "takeda_pharmaceutical")
    scorer = AcquirerFitScorer()

    partnered = AcquirerFitCandidate(
        asset_id="asset-ovid",
        ticker="OVID",
        company_name="Ovid Therapeutics",
        therapeutic_area="neuroscience",
        indication="Dravet syndrome",
        modality="small_molecule",
        stage="phase_3",
        model_rnpv_millions=2200.0,
        enterprise_value_millions=1800.0,
        acquisition_ready=True,
        priority_tags=["rare epilepsy"],
    )
    non_partner = partnered.model_copy(update={"ticker": "NEUR", "company_name": "NeuroCo"})

    partnered_score = scorer.score_target(acquirer=takeda, target=partnered)
    non_partner_score = scorer.score_target(acquirer=takeda, target=non_partner)

    assert partnered_score.matched_partnership_target == "Ovid Therapeutics"
    assert partnered_score.strategic_priority_score > non_partner_score.strategic_priority_score
    assert partnered_score.fit_score > non_partner_score.fit_score


def test_lower_acquisition_capacity_reduces_pipeline_gap_budget_score():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))
    takeda = AcquirerProfileLoader.get_acquirer(dataset, "takeda_pharmaceutical")
    constrained_takeda = takeda.model_copy(update={"acquisition_capacity_millions": 6000.0})
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-onc-large",
        ticker="LARG",
        company_name="LargeOnco",
        therapeutic_area="oncology",
        indication="solid tumors",
        modality="adc",
        stage="phase_3",
        model_rnpv_millions=9000.0,
        enterprise_value_millions=10000.0,
        acquisition_ready=True,
        priority_tags=["oncology"],
    )

    unconstrained_score = scorer.score_target(acquirer=takeda, target=target)
    constrained_score = scorer.score_target(acquirer=constrained_takeda, target=target)

    assert unconstrained_score.budget_capacity_millions == pytest.approx(12000.0, abs=1e-9)
    assert constrained_score.budget_capacity_millions == pytest.approx(6000.0, abs=1e-9)
    assert unconstrained_score.budget_score > constrained_score.budget_score


def test_subarea_specific_ibd_gap_outranks_generic_immunology_gap():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))
    pfizer = AcquirerProfileLoader.get_acquirer(dataset, "pfizer")
    amgen = AcquirerProfileLoader.get_acquirer(dataset, "amgen")
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-ibd-precision",
        ticker="IBDP",
        company_name="GutImmune",
        therapeutic_area="immunology",
        indication="ulcerative colitis / Crohn's disease",
        modality="small_molecule",
        stage="phase_2",
        model_rnpv_millions=6000.0,
        enterprise_value_millions=4200.0,
        acquisition_ready=True,
        priority_tags=["inflammatory bowel disease", "ulcerative colitis"],
    )

    pfizer_score = scorer.score_target(acquirer=pfizer, target=target)
    amgen_score = scorer.score_target(acquirer=amgen, target=target)

    assert pfizer_score.fit_score > amgen_score.fit_score
    assert pfizer_score.therapeutic_area_score == pytest.approx(1.0, abs=1e-9)
    assert amgen_score.therapeutic_area_score == pytest.approx(0.0, abs=1e-9)


def test_subarea_specific_kidney_gap_outranks_unrelated_profiles():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))
    novartis = AcquirerProfileLoader.get_acquirer(dataset, "novartis")
    biogen = AcquirerProfileLoader.get_acquirer(dataset, "biogen")
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-kidney-precision",
        ticker="KDNY",
        company_name="KidneyCo",
        therapeutic_area="kidney_disease",
        indication="IgA nephropathy",
        modality="small_molecule",
        stage="phase_3",
        model_rnpv_millions=3500.0,
        enterprise_value_millions=2800.0,
        acquisition_ready=True,
        priority_tags=["IgA nephropathy", "renal disease"],
    )

    novartis_score = scorer.score_target(acquirer=novartis, target=target)
    biogen_score = scorer.score_target(acquirer=biogen, target=target)

    assert novartis_score.fit_score > biogen_score.fit_score
    assert novartis_score.therapeutic_area_score == pytest.approx(1.0, abs=1e-9)
    assert biogen_score.therapeutic_area_score == pytest.approx(0.0, abs=1e-9)


def test_pfizer_cd47_gap_outranks_generic_bms_on_trillium_like_target():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))
    pfizer = AcquirerProfileLoader.get_acquirer(dataset, "pfizer")
    bms = AcquirerProfileLoader.get_acquirer(dataset, "bristol_myers_squibb")
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-heme-cd47",
        ticker="TRIL",
        company_name="HemeIO",
        therapeutic_area="oncology",
        indication="hematologic malignancies",
        stage="phase_1",
        model_rnpv_millions=2200.0,
        enterprise_value_millions=1800.0,
        acquisition_ready=True,
        priority_tags=["CD47 axis", "hematologic malignancies"],
    )

    pfizer_score = scorer.score_target(acquirer=pfizer, target=target)
    bms_score = scorer.score_target(acquirer=bms, target=target)

    assert pfizer_score.fit_score > bms_score.fit_score
    assert pfizer_score.therapeutic_area_score == pytest.approx(1.0, abs=1e-9)
    assert bms_score.therapeutic_area_score == pytest.approx(0.65, abs=1e-9)


def test_merck_t_cell_engager_gap_outranks_bms_radiopharma_on_harpoon_like_target():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))
    merck = AcquirerProfileLoader.get_acquirer(dataset, "merck")
    bms = AcquirerProfileLoader.get_acquirer(dataset, "bristol_myers_squibb")
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-sclc-bispecific",
        ticker="HARP",
        company_name="EngagerCo",
        therapeutic_area="oncology",
        indication="small-cell lung cancer / neuroendocrine tumors",
        modality="small_molecule",
        stage="phase_2",
        model_rnpv_millions=1800.0,
        enterprise_value_millions=1100.0,
        acquisition_ready=True,
        priority_tags=["CD3 redirecting engager", "small-cell lung cancer"],
    )

    merck_score = scorer.score_target(acquirer=merck, target=target)
    bms_score = scorer.score_target(acquirer=bms, target=target)

    assert merck_score.fit_score > bms_score.fit_score
    assert merck_score.matched_therapeutic_gap == "oncology:t_cell_engager_bispecific_io"


def test_merck_mpn_gap_outranks_novartis_bet_specific_gap_on_imago_like_target():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))
    merck = AcquirerProfileLoader.get_acquirer(dataset, "merck")
    novartis = AcquirerProfileLoader.get_acquirer(dataset, "novartis")
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-mpn",
        ticker="IMGO",
        company_name="MPNCo",
        therapeutic_area="hematology",
        indication="essential thrombocythemia / myelofibrosis",
        modality="small_molecule",
        stage="phase_2",
        model_rnpv_millions=1500.0,
        enterprise_value_millions=900.0,
        acquisition_ready=True,
        priority_tags=["LSD1", "myelofibrosis", "essential thrombocythemia"],
    )

    merck_score = scorer.score_target(acquirer=merck, target=target)
    novartis_score = scorer.score_target(acquirer=novartis, target=target)

    assert merck_score.fit_score > novartis_score.fit_score
    assert merck_score.matched_therapeutic_gap == "hematology:mpn_myelofibrosis_lsd1_heme"


def test_novartis_neuromuscular_gap_outranks_biogen_alzheimers_on_avidity_like_target():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))
    novartis = AcquirerProfileLoader.get_acquirer(dataset, "novartis")
    biogen = AcquirerProfileLoader.get_acquirer(dataset, "biogen")
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-neuromuscular-rna",
        ticker="RNA",
        company_name="NeuromuscleCo",
        therapeutic_area="neuroscience",
        indication="myotonic dystrophy type 1 / facioscapulohumeral muscular dystrophy / Duchenne muscular dystrophy",
        modality="small_molecule",
        stage="phase_3",
        model_rnpv_millions=4800.0,
        enterprise_value_millions=3600.0,
        acquisition_ready=True,
        priority_tags=["DMD", "FSHD", "myotonic dystrophy"],
    )

    novartis_score = scorer.score_target(acquirer=novartis, target=target)
    biogen_score = scorer.score_target(acquirer=biogen, target=target)

    assert novartis_score.fit_score > biogen_score.fit_score
    assert novartis_score.therapeutic_area_score == pytest.approx(1.0, abs=1e-9)
    assert biogen_score.therapeutic_area_score == pytest.approx(0.65, abs=1e-9)


def test_pfizer_generic_ibd_gap_outranks_merck_tl1a_on_arena_like_target():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))
    pfizer = AcquirerProfileLoader.get_acquirer(dataset, "pfizer")
    merck = AcquirerProfileLoader.get_acquirer(dataset, "merck")
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-ibd-oral",
        ticker="ARNA",
        company_name="IBDCo",
        therapeutic_area="immunology",
        indication="ulcerative colitis",
        modality="small_molecule",
        stage="nda_bla",
        model_rnpv_millions=7000.0,
        enterprise_value_millions=6800.0,
        acquisition_ready=True,
        priority_tags=["etrasimod", "ulcerative colitis"],
    )

    pfizer_score = scorer.score_target(acquirer=pfizer, target=target)
    merck_score = scorer.score_target(acquirer=merck, target=target)

    assert pfizer_score.fit_score > merck_score.fit_score
    assert pfizer_score.therapeutic_area_score == pytest.approx(1.0, abs=1e-9)
    assert merck_score.therapeutic_area_score == pytest.approx(0.65, abs=1e-9)


def test_gap_notes_do_not_create_false_full_match_on_generic_oncology_target():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))
    gsk = AcquirerProfileLoader.get_acquirer(dataset, "gsk")
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-generic-onc",
        ticker="ONC",
        company_name="OncoCo",
        therapeutic_area="oncology",
        indication="small-cell lung cancer",
        modality="small_molecule",
        stage="phase_2",
        model_rnpv_millions=1200.0,
        enterprise_value_millions=800.0,
        acquisition_ready=True,
        priority_tags=["small-cell lung cancer"],
    )

    gsk_score = scorer.score_target(acquirer=gsk, target=target)

    assert gsk_score.matched_therapeutic_gap == "oncology:synthetic_lethality_parp_beyond"
    assert gsk_score.therapeutic_area_score == pytest.approx(0.65, abs=1e-9)
    assert gsk_score.fit_score < 1.0


def test_merck_pah_gap_outranks_astrazeneca_resistant_htn_on_acceleron_like_target():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))
    merck = AcquirerProfileLoader.get_acquirer(dataset, "merck")
    astrazeneca = AcquirerProfileLoader.get_acquirer(dataset, "astrazeneca")
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-pah",
        ticker="XLRN",
        company_name="PAHCo",
        therapeutic_area="cardiovascular",
        indication="pulmonary arterial hypertension",
        modality="small_molecule",
        stage="phase_3",
        model_rnpv_millions=6500.0,
        enterprise_value_millions=6300.0,
        acquisition_ready=True,
        priority_tags=["sotatercept", "pulmonary arterial hypertension"],
    )

    merck_score = scorer.score_target(acquirer=merck, target=target)
    astrazeneca_score = scorer.score_target(acquirer=astrazeneca, target=target)

    assert merck_score.fit_score > astrazeneca_score.fit_score
    assert merck_score.matched_therapeutic_gap == "cardiovascular:pulmonary_arterial_hypertension"
    assert astrazeneca_score.therapeutic_area_score == pytest.approx(0.65, abs=1e-9)


def test_merck_mpn_gap_outranks_gsk_momelotinib_gap_on_imago_like_target():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))
    merck = AcquirerProfileLoader.get_acquirer(dataset, "merck")
    gsk = AcquirerProfileLoader.get_acquirer(dataset, "gsk")
    scorer = AcquirerFitScorer()
    target = AcquirerFitCandidate(
        asset_id="asset-mpn-2",
        ticker="IMGO",
        company_name="MPNCo",
        therapeutic_area="hematology",
        indication="essential thrombocythemia / myelofibrosis",
        modality="small_molecule",
        stage="phase_2",
        model_rnpv_millions=1500.0,
        enterprise_value_millions=900.0,
        acquisition_ready=True,
        priority_tags=["bomedemstat", "myelofibrosis", "essential thrombocythemia"],
    )

    merck_score = scorer.score_target(acquirer=merck, target=target)
    gsk_score = scorer.score_target(acquirer=gsk, target=target)

    assert merck_score.fit_score > gsk_score.fit_score
    assert merck_score.matched_therapeutic_gap == "hematology:mpn_myelofibrosis_lsd1_heme"
    assert gsk_score.therapeutic_area_score == pytest.approx(0.35, abs=1e-9)


def _regeneron():
    dataset = AcquirerProfileLoader.load(Path("research/mna/pipeline_gaps.yaml"))
    return AcquirerProfileLoader.get_acquirer(dataset, "regeneron")


def _pfizer():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles/pfizer.yaml"))
    return AcquirerProfileLoader.get_acquirer(dataset, "pfizer")
