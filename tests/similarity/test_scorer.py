"""Tests for SimilarityScorer — five-dimension asset similarity."""
import pytest
from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.similarity.scorer import SimilarityScorer
from bve.similarity.types import AssetSimilarityScore


def _make_asset(**kwargs) -> Asset:
    defaults = dict(
        id="test-asset",
        name="Test Asset",
        indication="ulcerative colitis",
        therapeutic_area=TherapeuticArea.IMMUNOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.BIOLOGIC,
        mechanism_of_action="checkpoint inhibitor",
        biological_target="PD-1",
    )
    defaults.update(kwargs)
    return Asset(**defaults)


@pytest.fixture(scope="module")
def scorer():
    return SimilarityScorer()


class TestScorerIdentical:
    def test_identical_assets_score_1(self, scorer):
        a = _make_asset(id="a")
        b = _make_asset(id="b")
        result = scorer.score(a, b)
        assert result.composite_score == pytest.approx(1.0, abs=0.01)

    def test_identical_indication_full_score(self, scorer):
        a = _make_asset(id="a")
        b = _make_asset(id="b")
        result = scorer.score(a, b)
        assert result.indication_overlap.score == pytest.approx(1.0)

    def test_identical_target_full_score(self, scorer):
        a = _make_asset(id="a")
        b = _make_asset(id="b")
        result = scorer.score(a, b)
        assert result.target_overlap.score == pytest.approx(1.0)

    def test_identical_moa_full_score(self, scorer):
        a = _make_asset(id="a")
        b = _make_asset(id="b")
        result = scorer.score(a, b)
        assert result.moa_overlap.score == pytest.approx(1.0)

    def test_identical_modality_full_score(self, scorer):
        a = _make_asset(id="a")
        b = _make_asset(id="b")
        result = scorer.score(a, b)
        assert result.modality_overlap.score == pytest.approx(1.0)

    def test_identical_stage_full_score(self, scorer):
        a = _make_asset(id="a")
        b = _make_asset(id="b")
        result = scorer.score(a, b)
        assert result.stage_proximity.score == pytest.approx(1.0)


class TestScorerDifferent:
    def test_different_indication_different_ta_zero(self, scorer):
        a = _make_asset(id="a", indication="ulcerative colitis", therapeutic_area=TherapeuticArea.IMMUNOLOGY)
        b = _make_asset(id="b", indication="glioblastoma multiforme", therapeutic_area=TherapeuticArea.ONCOLOGY)
        result = scorer.score(a, b)
        assert result.indication_overlap.score == pytest.approx(0.0)

    def test_same_therapeutic_area_different_indication(self, scorer):
        a = _make_asset(id="a", indication="ulcerative colitis", therapeutic_area=TherapeuticArea.IMMUNOLOGY)
        b = _make_asset(
            id="b",
            indication="plaque psoriasis",
            therapeutic_area=TherapeuticArea.IMMUNOLOGY,
            biological_target="IL-17",
            mechanism_of_action="il-17 inhibitor",
        )
        result = scorer.score(a, b)
        # Same TA → partial overlap, not 0
        assert result.indication_overlap.score > 0.0

    def test_completely_different_assets_low_composite(self, scorer):
        a = _make_asset(
            id="a",
            indication="ulcerative colitis",
            therapeutic_area=TherapeuticArea.IMMUNOLOGY,
            stage=DevelopmentStage.PRECLINICAL,
            modality=Modality.SMALL_MOLECULE,
            mechanism_of_action="jak inhibitor",
            biological_target="JAK",
        )
        b = _make_asset(
            id="b",
            indication="glioblastoma multiforme",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            stage=DevelopmentStage.APPROVED,
            modality=Modality.GENE_THERAPY,
            mechanism_of_action="gene therapy",
            biological_target="RPE65",
        )
        result = scorer.score(a, b)
        assert result.composite_score < 0.3

    def test_different_stage_reduces_stage_score(self, scorer):
        a = _make_asset(id="a", stage=DevelopmentStage.PRECLINICAL)
        b = _make_asset(id="b", stage=DevelopmentStage.APPROVED)
        result = scorer.score(a, b)
        assert result.stage_proximity.score == pytest.approx(0.0)

    def test_adjacent_stage_partial_score(self, scorer):
        a = _make_asset(id="a", stage=DevelopmentStage.PHASE_1)
        b = _make_asset(id="b", stage=DevelopmentStage.PHASE_2)
        result = scorer.score(a, b)
        assert result.stage_proximity.score == pytest.approx(0.8)


class TestScorerModality:
    def test_same_modality_full_score(self, scorer):
        a = _make_asset(id="a", modality=Modality.SMALL_MOLECULE)
        b = _make_asset(id="b", modality=Modality.SMALL_MOLECULE)
        result = scorer.score(a, b)
        assert result.modality_overlap.score == pytest.approx(1.0)

    def test_biologic_adjacent_partial_score(self, scorer):
        a = _make_asset(id="a", modality=Modality.BIOLOGIC)
        b = _make_asset(id="b", modality=Modality.ADC)
        result = scorer.score(a, b)
        assert result.modality_overlap.score == pytest.approx(0.3)

    def test_small_molecule_vs_biologic_zero(self, scorer):
        a = _make_asset(id="a", modality=Modality.SMALL_MOLECULE)
        b = _make_asset(id="b", modality=Modality.BIOLOGIC)
        result = scorer.score(a, b)
        assert result.modality_overlap.score == pytest.approx(0.0)


class TestScorerMissingFields:
    def test_no_biological_target_zero_target_score(self, scorer):
        a = _make_asset(id="a", biological_target=None)
        b = _make_asset(id="b", biological_target=None)
        result = scorer.score(a, b)
        assert result.target_overlap.score == pytest.approx(0.0)

    def test_no_moa_zero_moa_score(self, scorer):
        a = _make_asset(id="a", mechanism_of_action=None)
        b = _make_asset(id="b", mechanism_of_action=None)
        result = scorer.score(a, b)
        assert result.moa_overlap.score == pytest.approx(0.0)

    def test_low_confidence_normalization_adds_flag(self, scorer):
        # Give an unrecognized indication that will have low/failed confidence
        a = _make_asset(id="a", indication="xyzzy super rare unknown condition 9999", therapeutic_area=TherapeuticArea.OTHER)
        b = _make_asset(id="b", indication="completely different gibberish 12345", therapeutic_area=TherapeuticArea.ONCOLOGY)
        result = scorer.score(a, b)
        # At least one low-confidence flag expected
        assert len(result.confidence_flags) >= 1


class TestScorerSymmetry:
    def test_score_is_symmetric(self, scorer):
        a = _make_asset(
            id="a",
            indication="ulcerative colitis",
            therapeutic_area=TherapeuticArea.IMMUNOLOGY,
            stage=DevelopmentStage.PHASE_2,
            modality=Modality.BIOLOGIC,
        )
        b = _make_asset(
            id="b",
            indication="plaque psoriasis",
            therapeutic_area=TherapeuticArea.IMMUNOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
        )
        result_ab = scorer.score(a, b)
        result_ba = scorer.score(b, a)
        assert result_ab.composite_score == pytest.approx(result_ba.composite_score, abs=0.001)


class TestScorerCustomWeights:
    def test_custom_weights_change_composite(self):
        # Heavy indication weight
        scorer_ind = SimilarityScorer(weights={"indication": 0.8, "target": 0.05, "moa": 0.05, "modality": 0.05, "stage": 0.05})
        # Heavy stage weight
        scorer_stg = SimilarityScorer(weights={"indication": 0.05, "target": 0.05, "moa": 0.05, "modality": 0.05, "stage": 0.8})

        a = _make_asset(id="a", indication="ulcerative colitis", stage=DevelopmentStage.PRECLINICAL)
        b = _make_asset(id="b", indication="ulcerative colitis", stage=DevelopmentStage.APPROVED)
        # Same indication, max-distance stage
        r_ind = scorer_ind.score(a, b)
        r_stg = scorer_stg.score(a, b)
        # Indication-heavy scorer sees higher composite (same indication)
        assert r_ind.composite_score > r_stg.composite_score

    def test_result_is_asset_similarity_score_type(self):
        scorer = SimilarityScorer()
        a = _make_asset(id="a")
        b = _make_asset(id="b")
        result = scorer.score(a, b)
        assert isinstance(result, AssetSimilarityScore)


class TestScorerCanonicalFields:
    def test_pre_populated_canonical_indication_used(self, scorer):
        """When canonical_indication is set on the asset, it bypasses normalization."""
        a = _make_asset(id="a", indication="UC", canonical_indication="IND_ulcerative_colitis")
        b = _make_asset(id="b", indication="ulcerative colitis", canonical_indication="IND_ulcerative_colitis")
        result = scorer.score(a, b)
        assert result.indication_overlap.score == pytest.approx(1.0)
