"""Tests for normalization data models."""
import pytest
from bve.normalization.types import (
    CanonicalIndication,
    CanonicalMOA,
    CanonicalTarget,
    NormalizationConfidence,
    NormalizationResult,
)


class TestNormalizationResult:
    def test_high_confidence_is_trustworthy(self):
        r = NormalizationResult(
            raw_input="ulcerative colitis",
            canonical_id="IND_ulcerative_colitis",
            canonical_name="Ulcerative Colitis",
            confidence=NormalizationConfidence.HIGH,
            match_score=100.0,
            method="exact",
        )
        assert r.is_trustworthy is True
        assert r.canonical_id == "IND_ulcerative_colitis"

    def test_medium_confidence_is_trustworthy(self):
        r = NormalizationResult(
            raw_input="ulcerative collitis",
            canonical_id="IND_ulcerative_colitis",
            canonical_name="Ulcerative Colitis",
            confidence=NormalizationConfidence.MEDIUM,
            match_score=88.0,
            method="fuzzy",
        )
        assert r.is_trustworthy is True

    def test_low_confidence_not_trustworthy_but_has_canonical_id(self):
        r = NormalizationResult(
            raw_input="some ambiguous string",
            canonical_id="IND_ulcerative_colitis",
            canonical_name="Ulcerative Colitis",
            confidence=NormalizationConfidence.LOW,
            match_score=75.0,
            method="fuzzy",
        )
        assert r.is_trustworthy is False
        assert r.canonical_id is not None  # populated but flagged

    def test_failed_not_trustworthy_and_no_canonical_id(self):
        r = NormalizationResult(
            raw_input="xyzzy nonsense",
            confidence=NormalizationConfidence.FAILED,
            method="none",
        )
        assert r.is_trustworthy is False
        assert r.canonical_id is None

    def test_alternatives_default_empty(self):
        r = NormalizationResult(
            raw_input="test",
            confidence=NormalizationConfidence.FAILED,
        )
        assert r.alternatives == []

    def test_warnings_default_empty(self):
        r = NormalizationResult(
            raw_input="test",
            confidence=NormalizationConfidence.FAILED,
        )
        assert r.warnings == []


class TestCanonicalModels:
    def test_canonical_indication_schema(self):
        ci = CanonicalIndication(
            id="IND_ulcerative_colitis",
            name="Ulcerative Colitis",
            aliases=["ulcerative colitis", "uc"],
            therapeutic_area="immunology",
        )
        assert ci.id == "IND_ulcerative_colitis"
        assert "uc" in ci.aliases
        assert ci.therapeutic_area == "immunology"

    def test_canonical_target_schema(self):
        ct = CanonicalTarget(
            id="TGT_pd1",
            name="PD-1",
            aliases=["pd-1", "pd1", "programmed death 1"],
        )
        assert ct.id == "TGT_pd1"
        assert ct.name == "PD-1"

    def test_canonical_moa_schema(self):
        cm = CanonicalMOA(
            id="MOA_pd1_checkpoint_inhibitor",
            name="PD-1/PD-L1 Checkpoint Inhibitor",
            aliases=["checkpoint inhibitor", "pd-1 inhibitor"],
        )
        assert cm.id == "MOA_pd1_checkpoint_inhibitor"
