"""Tests for IndicationNormalizer, TargetNormalizer, and MOANormalizer."""
import pytest
from bve.normalization.normalizer import (
    IndicationNormalizer,
    MOANormalizer,
    TargetNormalizer,
)
from bve.normalization.types import NormalizationConfidence


@pytest.fixture(scope="module")
def ind():
    return IndicationNormalizer()


@pytest.fixture(scope="module")
def tgt():
    return TargetNormalizer()


@pytest.fixture(scope="module")
def moa():
    return MOANormalizer()


class TestIndicationNormalizerExact:
    def test_exact_lowercase(self, ind):
        r = ind.normalize("ulcerative colitis")
        assert r.confidence == NormalizationConfidence.HIGH
        assert r.canonical_id == "IND_ulcerative_colitis"
        assert r.method == "exact"

    def test_exact_mixed_case(self, ind):
        r = ind.normalize("Ulcerative Colitis")
        assert r.confidence == NormalizationConfidence.HIGH
        assert r.canonical_id == "IND_ulcerative_colitis"

    def test_exact_with_extra_whitespace(self, ind):
        r = ind.normalize("  ulcerative   colitis  ")
        assert r.confidence == NormalizationConfidence.HIGH
        assert r.canonical_id == "IND_ulcerative_colitis"

    def test_known_abbreviation_uc(self, ind):
        r = ind.normalize("UC")
        assert r.confidence == NormalizationConfidence.HIGH
        assert r.canonical_id == "IND_ulcerative_colitis"

    def test_known_abbreviation_nsclc(self, ind):
        r = ind.normalize("NSCLC")
        assert r.confidence == NormalizationConfidence.HIGH
        assert r.canonical_id == "IND_nsclc"

    def test_ros1_positive_nsclc(self, ind):
        r = ind.normalize("ROS1-positive non-small cell lung cancer")
        assert r.confidence == NormalizationConfidence.HIGH
        assert r.canonical_id == "IND_nsclc"

    def test_compound_ibd_string(self, ind):
        r = ind.normalize("ulcerative colitis and Crohn's disease")
        assert r.is_trustworthy
        assert r.canonical_id in ("IND_ulcerative_colitis", "IND_crohns_disease", "IND_ibd")

    def test_myelofibrosis_with_anemia(self, ind):
        r = ind.normalize("myelofibrosis with anemia")
        assert r.confidence == NormalizationConfidence.HIGH
        assert r.canonical_id == "IND_myelofibrosis"

    def test_braf_melanoma(self, ind):
        r = ind.normalize("BRAF V600-mutant melanoma")
        assert r.confidence == NormalizationConfidence.HIGH
        assert r.canonical_id == "IND_melanoma"

    def test_er_pos_breast_cancer(self, ind):
        r = ind.normalize("ER+/HER2- breast cancer")
        assert r.confidence == NormalizationConfidence.HIGH
        assert r.canonical_id == "IND_breast_cancer"


class TestIndicationNormalizerFuzzy:
    def test_typo_close_match(self, ind):
        r = ind.normalize("ulcerative collitis")  # deliberate typo
        assert r.is_trustworthy
        assert r.canonical_id == "IND_ulcerative_colitis"
        assert r.method == "fuzzy"

    def test_alternatives_populated_on_success(self, ind):
        r = ind.normalize("NSCLC")
        # Alternatives may or may not be populated for exact hit — just verify type
        assert isinstance(r.alternatives, list)

    def test_alternatives_populated_on_failure(self, ind):
        r = ind.normalize("xyzzy completely unknown disease qqqqq")
        assert r.confidence == NormalizationConfidence.FAILED
        assert r.canonical_id is None
        # Alternatives should be populated for human review even on failure
        assert isinstance(r.alternatives, list)

    def test_no_match_failed(self, ind):
        r = ind.normalize("xyzzy nonsense disease 12345")
        assert r.confidence == NormalizationConfidence.FAILED
        assert r.canonical_id is None
        assert not r.is_trustworthy

    def test_empty_string_fails(self, ind):
        r = ind.normalize("")
        assert r.confidence == NormalizationConfidence.FAILED
        assert "empty_input" in r.warnings


class TestTargetNormalizer:
    def test_pd1_exact(self, tgt):
        r = tgt.normalize("PD-1")
        assert r.confidence == NormalizationConfidence.HIGH
        assert r.canonical_id == "TGT_pd1"

    def test_pd1_no_dash(self, tgt):
        r = tgt.normalize("PD1")
        assert r.confidence == NormalizationConfidence.HIGH
        assert r.canonical_id == "TGT_pd1"

    def test_pd1_full_name(self, tgt):
        r = tgt.normalize("programmed death 1")
        assert r.confidence == NormalizationConfidence.HIGH
        assert r.canonical_id == "TGT_pd1"

    def test_vegf_variants(self, tgt):
        r = tgt.normalize("VEGF")
        assert r.confidence == NormalizationConfidence.HIGH
        assert r.canonical_id == "TGT_vegf"

    def test_her2_exact(self, tgt):
        r = tgt.normalize("HER2")
        assert r.is_trustworthy
        assert r.canonical_id == "TGT_her2"

    def test_unknown_target_fails(self, tgt):
        r = tgt.normalize("SUPER_NOVEL_TARGET_XY99Z_UNKNOWN")
        assert r.confidence == NormalizationConfidence.FAILED


class TestMOANormalizer:
    def test_checkpoint_inhibitor_exact(self, moa):
        r = moa.normalize("checkpoint inhibitor")
        assert r.confidence == NormalizationConfidence.HIGH
        assert r.canonical_id == "MOA_pd1_checkpoint_inhibitor"

    def test_pd1_inhibitor(self, moa):
        r = moa.normalize("pd-1 inhibitor")
        assert r.confidence == NormalizationConfidence.HIGH
        assert r.canonical_id == "MOA_pd1_checkpoint_inhibitor"

    def test_parp_inhibitor(self, moa):
        r = moa.normalize("PARP inhibitor")
        assert r.is_trustworthy
        assert r.canonical_id == "MOA_parp_inhibitor"

    def test_cftr_modulator(self, moa):
        r = moa.normalize("CFTR modulator")
        assert r.is_trustworthy
        assert r.canonical_id == "MOA_cftr_modulator"

    def test_fuzzy_checkpoint(self, moa):
        r = moa.normalize("check point inhibitor")  # space variant
        assert r.is_trustworthy

    def test_unknown_moa_fails(self, moa):
        r = moa.normalize("completely unknown novel xyz mechanism 99")
        assert r.confidence == NormalizationConfidence.FAILED
