"""
Sprint 13 tests — Acquirer pipeline gap analysis.

Tests strategic_fit.py scoring logic (deterministic, no network calls),
acquirer_profiles.yaml structure, and CLI --mna integration.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bve.intelligence.strategic_fit.strategic_fit import (
    _acquirer_key,
    _score_avoid,
    _score_commercial,
    _score_mechanism,
    _score_stage,
    _score_ta,
    _tokens,
    best_fit,
    load_acquirer_profiles,
    score_all_acquirers,
    score_fit,
)

PROFILES_PATH = (
    Path(__file__).parents[1]
    / "src" / "bve" / "intelligence" / "strategic_fit" / "acquirer_profiles.yaml"
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def profiles():
    return load_acquirer_profiles(PROFILES_PATH)


@pytest.fixture()
def pfizer(profiles):
    return profiles["pfizer"]


@pytest.fixture()
def lilly(profiles):
    return profiles["lilly"]


@pytest.fixture()
def novo(profiles):
    return profiles["novo_nordisk"]


def _asset(
    ticker="VKTX",
    ta="other",
    phase="phase_3",
    label="VK2735 — obesity oral small molecule GLP-1",
    peak_sales=4500,
    modality="small_molecule",
):
    return {
        "ticker": ticker,
        "ta": ta,
        "phase": phase,
        "program_label": label,
        "peak_sales_millions": peak_sales,
        "modality": modality,
    }


# ===========================================================================
# TestProfileLoad — YAML structure validation
# ===========================================================================

class TestProfileLoad:
    def test_three_acquirers_present(self, profiles):
        assert set(profiles.keys()) >= {"pfizer", "lilly", "novo_nordisk"}

    def test_pfizer_has_required_fields(self, pfizer):
        assert "name" in pfizer
        assert "ta_priorities" in pfizer
        assert "stage_preference" in pfizer
        assert "mechanism_gaps" in pfizer
        assert "deal_size_range_m" in pfizer

    def test_lilly_has_required_fields(self, lilly):
        assert "ta_priorities" in lilly
        assert "mechanism_gaps" in lilly

    def test_novo_has_required_fields(self, novo):
        assert "ta_priorities" in novo
        assert "deal_size_range_m" in novo

    def test_ta_priorities_are_floats(self, pfizer):
        for k, v in pfizer["ta_priorities"].items():
            assert isinstance(v, float), f"ta_priority[{k}]={v} should be float"

    def test_stage_weights_between_0_and_1(self, pfizer):
        weights = pfizer["stage_preference"]["weight_by_stage"]
        for k, v in weights.items():
            assert 0.0 <= v <= 1.0, f"stage_weight[{k}]={v} out of range"

    def test_deal_size_range_two_elements(self, pfizer):
        r = pfizer["deal_size_range_m"]
        assert len(r) == 2
        assert r[0] < r[1]

    def test_avoid_list_is_list(self, pfizer):
        avoid = pfizer.get("avoid", [])
        assert isinstance(avoid, list)

    def test_mechanism_gaps_nonempty(self, pfizer):
        assert len(pfizer["mechanism_gaps"]) >= 3


# ===========================================================================
# TestTokens — helper
# ===========================================================================

class TestTokens:
    def test_basic_tokenization(self):
        assert _tokens("KRAS G12D") == {"kras", "g12d"}

    def test_punctuation_stripped(self):
        assert "antibody" in _tokens("antibody-drug conjugate")

    def test_empty_string(self):
        assert _tokens("") == set()


# ===========================================================================
# TestScoreFitComponents — individual scorer functions
# ===========================================================================

class TestScoreTa:
    def test_oncology_matches_pfizer_oncology(self, pfizer):
        asset = _asset(ta="oncology", label="solid tumor KRAS")
        rationale: list = []
        score = _score_ta(asset, pfizer, rationale)
        assert score >= 0.85, f"Expected high oncology score, got {score}"
        assert any("oncol" in r.lower() for r in rationale)

    def test_metabolic_matches_lilly(self, lilly):
        asset = _asset(ta="metabolic", label="obesity oral GLP-1")
        rationale: list = []
        score = _score_ta(asset, lilly, rationale)
        assert score >= 0.85

    def test_unrelated_ta_returns_zero(self, pfizer):
        asset = _asset(ta="other", label="unknown niche veterinary product")
        rationale: list = []
        score = _score_ta(asset, pfizer, rationale)
        assert score == 0.0

    def test_rare_disease_matches_pfizer(self, pfizer):
        asset = _asset(ta="rare_disease", label="gene editing rare lysosomal storage disease")
        rationale: list = []
        score = _score_ta(asset, pfizer, rationale)
        assert score > 0.0


class TestScoreStage:
    def test_phase_3_preferred_by_pfizer(self, pfizer):
        asset = _asset(phase="phase_3")
        rationale: list = []
        score = _score_stage(asset, pfizer, rationale)
        assert score == 1.00

    def test_phase_2_gets_partial_credit(self, pfizer):
        asset = _asset(phase="phase_2")
        rationale: list = []
        score = _score_stage(asset, pfizer, rationale)
        assert 0.50 <= score < 1.00

    def test_phase_1_below_min_returns_zero(self, pfizer):
        asset = _asset(phase="phase_1")
        rationale: list = []
        score = _score_stage(asset, pfizer, rationale)
        assert score == 0.0

    def test_nda_gets_discount(self, pfizer):
        asset = _asset(phase="nda_bla")
        rationale: list = []
        score = _score_stage(asset, pfizer, rationale)
        assert score < 1.00
        assert score > 0.0


class TestScoreMechanism:
    def test_kras_g12d_matches_pfizer_gap(self, pfizer):
        asset = _asset(label="RMC-6236 pan-RAS KRAS G12D PDAC", ta="oncology")
        rationale: list = []
        score = _score_mechanism(asset, pfizer, rationale)
        assert score >= 0.60

    def test_adc_matches_pfizer_gap(self, pfizer):
        asset = _asset(label="antibody-drug conjugate ADC HER2", modality="biologic")
        rationale: list = []
        score = _score_mechanism(asset, pfizer, rationale)
        assert score >= 0.60

    def test_no_gap_match_returns_zero(self, pfizer):
        asset = _asset(label="ACE inhibitor hypertension generic", ta="cardiovascular")
        rationale: list = []
        score = _score_mechanism(asset, pfizer, rationale)
        assert score == 0.0

    def test_oral_glp1_matches_lilly(self, lilly):
        asset = _asset(label="oral GLP-1 small molecule obesity", ta="metabolic")
        rationale: list = []
        score = _score_mechanism(asset, lilly, rationale)
        assert score >= 0.60

    def test_no_gaps_defined_returns_neutral(self):
        profile = {"name": "Acme Corp", "mechanism_gaps": []}
        asset = _asset()
        rationale: list = []
        score = _score_mechanism(asset, profile, rationale)
        assert score == 0.50


class TestScoreCommercial:
    def test_large_asset_in_pfizer_range(self, pfizer):
        asset = _asset(peak_sales=4000)  # implied deal $8B–$20B; Pfizer range $3–50B
        rationale: list = []
        score = _score_commercial(asset, pfizer, rationale)
        assert score >= 0.20

    def test_tiny_asset_below_pfizer_range(self, pfizer):
        asset = _asset(peak_sales=200)  # implied $400M–$1B; Pfizer min $3B
        rationale: list = []
        score = _score_commercial(asset, pfizer, rationale)
        assert score <= 0.15

    def test_huge_asset_above_novo_range(self, novo):
        asset = _asset(peak_sales=20000)  # implied $40B–$100B; Novo max $20B
        rationale: list = []
        score = _score_commercial(asset, novo, rationale)
        assert score <= 0.15

    def test_missing_deal_range_returns_neutral(self):
        profile = {"name": "X"}
        asset = _asset(peak_sales=3000)
        rationale: list = []
        score = _score_commercial(asset, profile, rationale)
        assert score == 0.50


class TestScoreAvoid:
    def test_gene_therapy_triggers_pfizer_avoid(self, pfizer):
        asset = _asset(label="SRP-9003 LGMD2E gene therapy", modality="gene_therapy")
        rationale: list = []
        penalty = _score_avoid(asset, pfizer, rationale)
        assert penalty == 0.40
        assert any("AVOID" in r for r in rationale)

    def test_no_avoid_match_returns_zero(self, pfizer):
        asset = _asset(label="KRAS G12D ADC solid tumor", ta="oncology")
        rationale: list = []
        penalty = _score_avoid(asset, pfizer, rationale)
        assert penalty == 0.0

    def test_oncology_triggers_novo_avoid(self, novo):
        asset = _asset(ta="oncology", label="KRAS G12D solid tumor oncology")
        rationale: list = []
        penalty = _score_avoid(asset, novo, rationale)
        assert penalty == 0.40


# ===========================================================================
# TestScoreFit — full scoring integration
# ===========================================================================

class TestScoreFit:
    def test_returns_strategic_fit_score(self, pfizer):
        result = score_fit(_asset(), pfizer)
        assert result.ticker == "VKTX"
        assert result.acquirer_name == "Pfizer"
        assert 0.0 <= result.total <= 1.0

    def test_total_formula_weights(self, pfizer):
        """total = ta×0.35 + stage×0.20 + mech×0.30 + commercial×0.15 - penalty."""
        result = score_fit(_asset(), pfizer)
        expected_pre_penalty = (
            result.ta_match_score * 0.35
            + result.stage_score * 0.20
            + result.mechanism_novelty_score * 0.30
            + result.commercial_fit_score * 0.15
        )
        assert abs(result.total - max(0.0, expected_pre_penalty - result.avoid_penalty)) < 1e-4

    def test_rationale_is_nonempty(self, pfizer):
        result = score_fit(_asset(), pfizer)
        assert len(result.rationale) >= 3

    def test_gene_therapy_penalized_for_pfizer(self, pfizer):
        gene_asset = _asset(
            ticker="SRPT",
            ta="rare_disease",
            label="SRP-9003 LGMD2E gene therapy AAV",
            modality="gene_therapy",
        )
        result = score_fit(gene_asset, pfizer)
        assert result.avoid_penalty == 0.40

    def test_deterministic_same_inputs(self, lilly):
        a1 = _asset(ta="metabolic", label="oral GLP-1 small molecule obesity", phase="phase_3")
        r1 = score_fit(a1, lilly)
        r2 = score_fit(a1, lilly)
        assert r1.total == r2.total

    def test_oncology_not_fit_for_novo(self, novo):
        asset = _asset(ta="oncology", label="KRAS G12D solid tumor pancreatic cancer")
        result = score_fit(asset, novo)
        assert result.total < 0.35  # avoid penalty + TA mismatch

    def test_metabolic_high_fit_for_lilly(self, lilly):
        asset = _asset(
            ticker="VKTX",
            ta="metabolic",
            phase="phase_3",
            label="VK2735 oral GLP-1 obesity small molecule",
            peak_sales=4500,
        )
        result = score_fit(asset, lilly)
        assert result.total >= 0.55


# ===========================================================================
# TestScoreAllAcquirers
# ===========================================================================

class TestScoreAllAcquirers:
    def test_returns_three_results(self, profiles):
        scores = score_all_acquirers(_asset(), profiles)
        assert len(scores) == 3

    def test_sorted_descending(self, profiles):
        scores = score_all_acquirers(_asset(), profiles)
        for i in range(len(scores) - 1):
            assert scores[i].total >= scores[i + 1].total

    def test_best_fit_returns_top(self, profiles):
        top = best_fit(_asset(), profiles)
        all_scores = score_all_acquirers(_asset(), profiles)
        assert top.total == all_scores[0].total


# ===========================================================================
# TestAcquirerKeyHelper
# ===========================================================================

class TestAcquirerKey:
    def test_pfizer_key(self, pfizer):
        assert _acquirer_key(pfizer) == "pfizer"

    def test_lilly_key(self, lilly):
        assert _acquirer_key(lilly) == "eli_lilly"

    def test_novo_key(self, novo):
        assert _acquirer_key(novo) == "novo_nordisk"
