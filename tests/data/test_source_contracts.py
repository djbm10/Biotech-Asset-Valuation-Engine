"""Tests for DataSourceRegistry and DataQualityChecker."""

import pytest

from bve.data.source_registry import DataSourceRegistry, DataSourceContract
from bve.data.data_quality import DataQualityChecker, DataQualityResult


class TestDataSourceRegistry:
    def setup_method(self):
        self.reg = DataSourceRegistry()

    def test_loads_clinicaltrials_gov(self):
        contract = self.reg.get("clinicaltrials_gov")
        assert contract is not None
        assert contract.license_status == "public"

    def test_loads_sec_edgar(self):
        contract = self.reg.get("sec_edgar")
        assert contract is not None
        assert contract.point_in_time_available == "full"

    def test_loads_yfinance(self):
        contract = self.reg.get("yfinance")
        assert contract is not None
        assert contract.point_in_time_available == "none"

    def test_pit_safe_sources_excludes_yfinance(self):
        pit_safe = {c.source_name for c in self.reg.pit_safe_sources()}
        assert "yfinance" not in pit_safe
        assert "sec_edgar" in pit_safe

    def test_legal_review_required_for_licensed(self):
        legal = {c.source_name for c in self.reg.requires_legal_review()}
        assert "yfinance" in legal
        assert "biomedtracker_base_rates" in legal

    def test_public_sources_not_legal_review(self):
        legal = {c.source_name for c in self.reg.requires_legal_review()}
        assert "clinicaltrials_gov" not in legal
        assert "sec_edgar" not in legal

    def test_validate_known_field(self):
        assert self.reg.validate_field("clinicaltrials_gov", "nct_id")

    def test_validate_unknown_field_returns_false(self):
        assert not self.reg.validate_field("clinicaltrials_gov", "nonexistent_field")

    def test_validate_unknown_source_returns_false(self):
        assert not self.reg.validate_field("nonexistent_source", "nct_id")

    def test_all_returns_multiple_sources(self):
        all_sources = self.reg.all()
        assert len(all_sources) >= 4

    def test_survivorship_bias_risk_iqvia(self):
        c = self.reg.get("iqvia_estimates")
        assert c.requires_bias_mitigation

    def test_confidence_weight_in_range(self):
        for contract in self.reg.all():
            assert 0.0 <= contract.confidence_weight <= 1.0


class TestDataQualityChecker:
    def setup_method(self):
        self.checker = DataQualityChecker()

    def test_passes_complete_record(self):
        record = {"nct_id": "NCT001", "status": "active", "phase": "PHASE2", "created_at": "2026-01-01"}
        result = self.checker.validate(
            "clinicaltrials_gov",
            record,
            required_fields=["nct_id", "status", "phase"],
            timestamp_field="created_at",
            primary_key_field="nct_id",
        )
        assert result.passed
        assert not result.has_errors

    def test_fails_missing_required_field(self):
        record = {"status": "active"}
        result = self.checker.validate(
            "clinicaltrials_gov",
            record,
            required_fields=["nct_id", "status"],
        )
        assert not result.passed
        assert any("nct_id" in e for e in result.errors)

    def test_warns_null_field(self):
        record = {"nct_id": "NCT001", "status": None}
        result = self.checker.validate(
            "clinicaltrials_gov",
            record,
            required_fields=["nct_id", "status"],
        )
        assert result.passed  # null → warning, not error
        assert len(result.warnings) > 0

    def test_fails_missing_timestamp(self):
        record = {"nct_id": "NCT001"}
        result = self.checker.validate(
            "clinicaltrials_gov",
            record,
            required_fields=["nct_id"],
            timestamp_field="created_at",
        )
        assert not result.passed
        assert any("timestamp" in e for e in result.errors)

    def test_fails_empty_primary_key(self):
        record = {"nct_id": ""}
        result = self.checker.validate(
            "clinicaltrials_gov",
            record,
            required_fields=["nct_id"],
            primary_key_field="nct_id",
        )
        assert not result.passed

    def test_batch_validate_summary(self):
        records = [
            {"nct_id": "NCT001", "status": "active"},
            {"nct_id": "", "status": "active"},  # empty PK → fail
        ]
        results = self.checker.validate_batch(
            "clinicaltrials_gov",
            records,
            required_fields=["nct_id", "status"],
            primary_key_field="nct_id",
        )
        summary = self.checker.summary(results)
        assert summary["total"] == 2
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert summary["pass_rate"] == 0.5
