"""
Tests for P2.7 — Evidence pack ingestion & YAML validation.

Verifies:
- EvidenceValidator.validate_file loads both canonical evidence packs without errors
- EvidenceValidator.validate_dict validates a minimal in-memory dict
- All required top-level fields are checked
- Confidence level must be High, Medium, or Low
- Ticker format must match 1-6 uppercase letters
- asof_date must be a valid ISO date string
- knowable must be a non-empty dict with required sub-fields
- not_knowable must be a non-empty list with required sub-fields
- error_decomposition is optional but validated when present
- EvidencePack accessors: knowable_by_key, overall_confidence, confidence counts
- batch_validate_dir finds and validates multiple files
- load_evidence_pack raises ValueError on invalid file
- load_all_evidence_packs returns only valid packs
- EvidenceValidationResult.error_messages() returns readable strings
"""
from __future__ import annotations

import pathlib

import pytest

from bve.analysis.evidence_validator import (
    EvidencePack,
    EvidenceValidationResult,
    EvidenceValidator,
    KnowableItem,
    NotKnowableItem,
    ErrorDecomposition,
    ValidationError,
    load_all_evidence_packs,
    load_evidence_pack,
)

# ---------------------------------------------------------------------------
# Paths to canonical evidence packs
# ---------------------------------------------------------------------------

_PROJECT_ROOT = pathlib.Path(__file__).parent.parent
_EVIDENCE_DIR = _PROJECT_ROOT / "research" / "evidence"
_VRTX_YAML = _EVIDENCE_DIR / "vertex_ivacaftor_2010" / "asof.yaml"
_INCY_YAML = _EVIDENCE_DIR / "incyte_ruxolitinib_2010" / "asof.yaml"


# ---------------------------------------------------------------------------
# Minimal valid dict for in-memory tests
# ---------------------------------------------------------------------------

def _minimal_valid_dict() -> dict:
    return {
        "asof_date": "2021-06-01",
        "company": "Test Pharma Inc",
        "ticker": "TPHR",
        "drug": "TP-101",
        "indication": "Non-small cell lung cancer",
        "analysis_phase": "phase_2",
        "knowable": {
            "trial_data": {
                "description": "Phase 1 data shows 30% ORR",
                "source": "ASCO 2020 abstract #1234",
                "confidence": "Medium",
                "notes": "Preliminary data only",
            },
            "competitive_landscape": {
                "description": "No approved PD-L1 inhibitors in 2L",
                "source": "FDA Orange Book 2021",
                "confidence": "High",
            },
        },
        "not_knowable": [
            {
                "item": "Phase 2 primary endpoint result",
                "actual_disclosure": "ASCO 2023",
                "error_if_used": "Lookahead bias — result unknown at analysis date",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Loading canonical files
# ---------------------------------------------------------------------------

class TestLoadCanonicalFiles:
    def test_vertex_file_ok(self):
        result = EvidenceValidator().validate_file(_VRTX_YAML)
        assert result.ok, f"Errors: {result.error_messages()}"

    def test_vertex_returns_pack(self):
        result = EvidenceValidator().validate_file(_VRTX_YAML)
        assert isinstance(result.pack, EvidencePack)

    def test_vertex_company(self):
        result = EvidenceValidator().validate_file(_VRTX_YAML)
        assert result.pack.company == "Vertex Pharmaceuticals"

    def test_vertex_ticker(self):
        result = EvidenceValidator().validate_file(_VRTX_YAML)
        assert result.pack.ticker == "VRTX"

    def test_vertex_asof_date(self):
        from datetime import date
        result = EvidenceValidator().validate_file(_VRTX_YAML)
        assert result.pack.asof_date == date(2010, 1, 1)

    def test_vertex_has_knowable_items(self):
        result = EvidenceValidator().validate_file(_VRTX_YAML)
        assert len(result.pack.knowable_items) >= 4

    def test_vertex_has_not_knowable_items(self):
        result = EvidenceValidator().validate_file(_VRTX_YAML)
        assert len(result.pack.not_knowable_items) >= 3

    def test_vertex_has_error_decomposition(self):
        result = EvidenceValidator().validate_file(_VRTX_YAML)
        assert result.pack.error_decomposition is not None

    def test_incyte_file_ok(self):
        result = EvidenceValidator().validate_file(_INCY_YAML)
        assert result.ok, f"Errors: {result.error_messages()}"

    def test_incyte_ticker(self):
        result = EvidenceValidator().validate_file(_INCY_YAML)
        assert result.pack.ticker == "INCY"

    def test_no_errors_list(self):
        result = EvidenceValidator().validate_file(_VRTX_YAML)
        assert result.errors == []


# ---------------------------------------------------------------------------
# In-memory validation
# ---------------------------------------------------------------------------

class TestValidateDict:
    def setup_method(self):
        self.validator = EvidenceValidator()

    def test_minimal_valid(self):
        result = self.validator.validate_dict(_minimal_valid_dict())
        assert result.ok

    def test_missing_required_field(self):
        d = _minimal_valid_dict()
        del d["ticker"]
        result = self.validator.validate_dict(d)
        assert not result.ok
        assert any("ticker" in e.path for e in result.errors)

    def test_invalid_ticker_lowercase(self):
        d = _minimal_valid_dict()
        d["ticker"] = "tphr"
        result = self.validator.validate_dict(d)
        assert not result.ok
        assert any("ticker" in e.path for e in result.errors)

    def test_invalid_ticker_too_long(self):
        d = _minimal_valid_dict()
        d["ticker"] = "TOOLONG"
        result = self.validator.validate_dict(d)
        assert not result.ok

    def test_valid_ticker_one_char(self):
        d = _minimal_valid_dict()
        d["ticker"] = "A"
        result = self.validator.validate_dict(d)
        assert result.ok

    def test_invalid_date(self):
        d = _minimal_valid_dict()
        d["asof_date"] = "not-a-date"
        result = self.validator.validate_dict(d)
        assert not result.ok
        assert any("asof_date" in e.path for e in result.errors)

    def test_date_as_date_object(self):
        from datetime import date
        d = _minimal_valid_dict()
        d["asof_date"] = date(2021, 6, 1)
        result = self.validator.validate_dict(d)
        assert result.ok

    def test_empty_knowable_rejected(self):
        d = _minimal_valid_dict()
        d["knowable"] = {}
        result = self.validator.validate_dict(d)
        assert not result.ok
        assert any("knowable" in e.path for e in result.errors)

    def test_knowable_not_dict_rejected(self):
        d = _minimal_valid_dict()
        d["knowable"] = ["a", "b"]
        result = self.validator.validate_dict(d)
        assert not result.ok

    def test_knowable_missing_source_rejected(self):
        d = _minimal_valid_dict()
        d["knowable"]["trial_data"].pop("source")
        result = self.validator.validate_dict(d)
        assert not result.ok

    def test_invalid_confidence_rejected(self):
        d = _minimal_valid_dict()
        d["knowable"]["trial_data"]["confidence"] = "Very High"
        result = self.validator.validate_dict(d)
        assert not result.ok
        assert any("confidence" in e.path for e in result.errors)

    def test_valid_confidence_values(self):
        for conf in ("High", "Medium", "Low"):
            d = _minimal_valid_dict()
            d["knowable"]["trial_data"]["confidence"] = conf
            result = self.validator.validate_dict(d)
            assert result.ok, f"Expected ok for confidence={conf}"

    def test_empty_not_knowable_rejected(self):
        d = _minimal_valid_dict()
        d["not_knowable"] = []
        result = self.validator.validate_dict(d)
        assert not result.ok

    def test_not_knowable_missing_field_rejected(self):
        d = _minimal_valid_dict()
        d["not_knowable"][0].pop("error_if_used")
        result = self.validator.validate_dict(d)
        assert not result.ok
        assert any("error_if_used" in e.path for e in result.errors)

    def test_not_knowable_not_list_rejected(self):
        d = _minimal_valid_dict()
        d["not_knowable"] = {"key": "value"}
        result = self.validator.validate_dict(d)
        assert not result.ok

    def test_root_not_mapping_rejected(self):
        result = self.validator.validate_dict(["not", "a", "dict"])
        assert not result.ok

    def test_error_messages_are_strings(self):
        d = _minimal_valid_dict()
        del d["company"]
        result = self.validator.validate_dict(d)
        msgs = result.error_messages()
        assert isinstance(msgs, list)
        assert all(isinstance(m, str) for m in msgs)

    def test_error_messages_contain_path(self):
        d = _minimal_valid_dict()
        del d["company"]
        result = self.validator.validate_dict(d)
        assert any("company" in m for m in result.error_messages())


# ---------------------------------------------------------------------------
# EvidencePack accessors
# ---------------------------------------------------------------------------

class TestEvidencePackAccessors:
    def setup_method(self):
        result = EvidenceValidator().validate_file(_VRTX_YAML)
        self.pack = result.pack

    def test_knowable_by_key_found(self):
        item = self.pack.knowable_by_key("indication_and_target")
        assert item is not None
        assert isinstance(item, KnowableItem)

    def test_knowable_by_key_not_found(self):
        item = self.pack.knowable_by_key("nonexistent_key")
        assert item is None

    def test_high_confidence_count(self):
        assert self.pack.high_confidence_count >= 1

    def test_confidence_counts_sum_to_total(self):
        total = (
            self.pack.high_confidence_count
            + self.pack.medium_confidence_count
            + self.pack.low_confidence_count
        )
        assert total == len(self.pack.knowable_items)

    def test_overall_confidence_is_valid(self):
        assert self.pack.overall_confidence in {"High", "Medium", "Low"}

    def test_overall_confidence_low_when_any_low(self):
        # Build a pack with one Low item
        d = _minimal_valid_dict()
        d["knowable"]["trial_data"]["confidence"] = "Low"
        result = EvidenceValidator().validate_dict(d)
        assert result.pack.overall_confidence == "Low"

    def test_overall_confidence_high_when_all_high(self):
        d = _minimal_valid_dict()
        for item in d["knowable"].values():
            item["confidence"] = "High"
        result = EvidenceValidator().validate_dict(d)
        assert result.pack.overall_confidence == "High"

    def test_source_path_set_from_file(self):
        assert self.pack.source_path is not None
        assert self.pack.source_path.name == "asof.yaml"

    def test_source_path_none_from_dict(self):
        result = EvidenceValidator().validate_dict(_minimal_valid_dict())
        assert result.pack.source_path is None

    def test_error_decomposition_primary_driver(self):
        assert self.pack.error_decomposition.primary_error_driver is not None
        assert len(self.pack.error_decomposition.primary_error_driver) > 0

    def test_error_decomposition_foreseeable_errors_tuple(self):
        assert isinstance(self.pack.error_decomposition.foreseeable_errors, tuple)

    def test_error_decomposition_optional_none(self):
        d = _minimal_valid_dict()  # No error_decomposition key
        result = EvidenceValidator().validate_dict(d)
        assert result.pack.error_decomposition is None


# ---------------------------------------------------------------------------
# Batch validation
# ---------------------------------------------------------------------------

class TestBatchValidation:
    def test_batch_finds_both_canonical_files(self):
        results = EvidenceValidator().batch_validate_dir(_EVIDENCE_DIR)
        assert len(results) >= 2

    def test_batch_all_ok(self):
        results = EvidenceValidator().batch_validate_dir(_EVIDENCE_DIR)
        for r in results:
            assert r.ok, f"Failed: {r.error_messages()}"

    def test_load_all_packs_returns_list(self):
        packs = load_all_evidence_packs(_EVIDENCE_DIR)
        assert isinstance(packs, list)
        assert len(packs) >= 2

    def test_load_all_packs_are_evidence_packs(self):
        packs = load_all_evidence_packs(_EVIDENCE_DIR)
        for p in packs:
            assert isinstance(p, EvidencePack)

    def test_batch_empty_dir(self, tmp_path):
        results = EvidenceValidator().batch_validate_dir(tmp_path)
        assert results == []

    def test_load_evidence_pack_raises_on_missing_file(self, tmp_path):
        missing = tmp_path / "not_there.yaml"
        with pytest.raises(ValueError, match="Evidence validation failed"):
            load_evidence_pack(missing)

    def test_load_evidence_pack_raises_on_invalid_yaml(self, tmp_path):
        bad = tmp_path / "asof.yaml"
        bad.write_text("asof_date: 2021-01-01\n# missing required fields\n")
        with pytest.raises(ValueError):
            load_evidence_pack(bad)

    def test_validate_file_missing_file(self, tmp_path):
        missing = tmp_path / "ghost.yaml"
        result = EvidenceValidator().validate_file(missing)
        assert not result.ok
        assert any("not found" in m.lower() for m in result.error_messages())
