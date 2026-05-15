"""
Tests for CT.gov registry validation (P1.6).

All network calls are mocked — no live API access required.
"""
from __future__ import annotations

import warnings
from unittest.mock import MagicMock, patch

import pytest

from bve.entities.trial import ClinicalTrial, TrialPhase, TrialStatus
from bve.ingestion.clinicaltrials_gov import ValidationResult, validate_against_registry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_trial(
    phase: TrialPhase = TrialPhase.PHASE_3,
    status: TrialStatus = TrialStatus.RECRUITING,
    primary_endpoint: str | None = "Overall survival at 24 months",
    nct_id: str | None = "NCT99999999",
) -> ClinicalTrial:
    return ClinicalTrial(
        asset_id="asset-001",
        phase=phase,
        nct_id=nct_id,
        success_probability=0.60,
        duration_years=3.0,
        cost_millions=80.0,
        primary_endpoint=primary_endpoint,
        status=status,
    )


def _make_registry_proto(
    phase_key: str = "PHASE3",
    status_key: str = "RECRUITING",
    primary_outcome: str = "Overall survival at 24 months",
) -> dict:
    """Minimal protocol section that mimics a CT.gov API response."""
    return {
        "designModule": {"phases": [phase_key]},
        "statusModule": {"overallStatus": status_key},
        "outcomesModule": {
            "primaryOutcomes": [{"measure": primary_outcome}]
        },
    }


# ---------------------------------------------------------------------------
# Basic structure tests
# ---------------------------------------------------------------------------

class TestValidationResultDefaults:
    def test_dataclass_fields(self):
        r = ValidationResult(nct_id="NCT123", registry_found=False)
        assert r.nct_id == "NCT123"
        assert r.registry_found is False
        assert r.phase_match is None
        assert r.status_match is None
        assert r.endpoint_match is None
        assert r.mismatches == []
        assert r.evidence_grade == "unvalidated"

    def test_mismatches_not_shared_across_instances(self):
        r1 = ValidationResult(nct_id="A", registry_found=False)
        r2 = ValidationResult(nct_id="B", registry_found=False)
        r1.mismatches.append("something")
        assert r2.mismatches == []


# ---------------------------------------------------------------------------
# Happy path: all fields match
# ---------------------------------------------------------------------------

class TestAllFieldsMatch:
    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_all_match_returns_calibrated(self, mock_fetch):
        mock_fetch.return_value = _make_registry_proto()
        trial = _make_trial()

        result = validate_against_registry("NCT99999999", trial)

        assert result.registry_found is True
        assert result.phase_match is True
        assert result.status_match is True
        assert result.endpoint_match is True
        assert result.mismatches == []
        assert result.evidence_grade == "calibrated"

    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_no_warnings_when_all_match(self, mock_fetch):
        mock_fetch.return_value = _make_registry_proto()
        trial = _make_trial()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            validate_against_registry("NCT99999999", trial)

        assert len(caught) == 0


# ---------------------------------------------------------------------------
# Phase mismatch
# ---------------------------------------------------------------------------

class TestPhaseMismatch:
    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_phase_mismatch_sets_unvalidated(self, mock_fetch):
        mock_fetch.return_value = _make_registry_proto(phase_key="PHASE2")
        trial = _make_trial(phase=TrialPhase.PHASE_3)

        result = validate_against_registry("NCT99999999", trial)

        assert result.phase_match is False
        assert result.evidence_grade == "unvalidated"
        assert any("phase mismatch" in m for m in result.mismatches)

    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_phase_mismatch_emits_warning(self, mock_fetch):
        mock_fetch.return_value = _make_registry_proto(phase_key="PHASE2")
        trial = _make_trial(phase=TrialPhase.PHASE_3)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            validate_against_registry("NCT99999999", trial)

        assert any("phase mismatch" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# Status mismatch
# ---------------------------------------------------------------------------

class TestStatusMismatch:
    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_status_mismatch_sets_unvalidated(self, mock_fetch):
        mock_fetch.return_value = _make_registry_proto(status_key="COMPLETED")
        trial = _make_trial(status=TrialStatus.RECRUITING)

        result = validate_against_registry("NCT99999999", trial)

        assert result.status_match is False
        assert result.evidence_grade == "unvalidated"
        assert any("status mismatch" in m for m in result.mismatches)

    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_status_mismatch_emits_warning(self, mock_fetch):
        mock_fetch.return_value = _make_registry_proto(status_key="TERMINATED")
        trial = _make_trial(status=TrialStatus.RECRUITING)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            validate_against_registry("NCT99999999", trial)

        assert any("status mismatch" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# Endpoint mismatch
# ---------------------------------------------------------------------------

class TestEndpointComparison:
    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_endpoint_fuzzy_match_passes(self, mock_fetch):
        # Registry uses slightly different phrasing but key words overlap
        mock_fetch.return_value = _make_registry_proto(
            primary_outcome="Overall survival at 24 months (OS-24)"
        )
        trial = _make_trial(primary_endpoint="Overall survival at 24 months")

        result = validate_against_registry("NCT99999999", trial)

        assert result.endpoint_match is True
        assert result.evidence_grade == "calibrated"

    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_endpoint_mismatch_sets_unvalidated(self, mock_fetch):
        mock_fetch.return_value = _make_registry_proto(
            primary_outcome="Progression-free survival at 12 months"
        )
        trial = _make_trial(primary_endpoint="Overall survival")

        result = validate_against_registry("NCT99999999", trial)

        assert result.endpoint_match is False
        assert result.evidence_grade == "unvalidated"

    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_no_endpoint_on_trial_skips_comparison(self, mock_fetch):
        mock_fetch.return_value = _make_registry_proto()
        trial = _make_trial(primary_endpoint=None)

        result = validate_against_registry("NCT99999999", trial)

        assert result.endpoint_match is None
        # Phase and status still match → calibrated
        assert result.evidence_grade == "calibrated"


# ---------------------------------------------------------------------------
# Registry not found
# ---------------------------------------------------------------------------

class TestRegistryNotFound:
    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_empty_proto_returns_unvalidated(self, mock_fetch):
        mock_fetch.return_value = {}
        trial = _make_trial()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = validate_against_registry("NCT99999999", trial)

        assert result.registry_found is False
        assert result.evidence_grade == "unvalidated"
        assert any("no registry record" in str(w.message) for w in caught)

    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_none_proto_returns_unvalidated(self, mock_fetch):
        mock_fetch.return_value = None
        trial = _make_trial()

        result = validate_against_registry("NCT99999999", trial)

        assert result.registry_found is False
        assert result.evidence_grade == "unvalidated"


# ---------------------------------------------------------------------------
# Network / fetch error
# ---------------------------------------------------------------------------

class TestNetworkError:
    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_exception_returns_unvalidated_with_warning(self, mock_fetch):
        mock_fetch.side_effect = ConnectionError("timeout")
        trial = _make_trial()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = validate_against_registry("NCT99999999", trial)

        assert result.registry_found is False
        assert result.evidence_grade == "unvalidated"
        assert any("failed to fetch" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# Evidence grade logic
# ---------------------------------------------------------------------------

class TestEvidenceGrade:
    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_evidence_informed_when_no_comparable_fields(self, mock_fetch):
        # Registry has no phase/status/endpoint data
        mock_fetch.return_value = {"designModule": {}, "statusModule": {}, "outcomesModule": {}}
        trial = _make_trial(primary_endpoint=None)

        result = validate_against_registry("NCT99999999", trial)

        # registry_found=True, but no field was compared → evidence_informed
        assert result.registry_found is True
        assert result.phase_match is None
        assert result.evidence_grade == "evidence_informed"

    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_multiple_mismatches_all_recorded(self, mock_fetch):
        mock_fetch.return_value = _make_registry_proto(
            phase_key="PHASE2",
            status_key="COMPLETED",
            primary_outcome="Progression-free survival",
        )
        trial = _make_trial(
            phase=TrialPhase.PHASE_3,
            status=TrialStatus.RECRUITING,
            primary_endpoint="Overall survival",
        )

        result = validate_against_registry("NCT99999999", trial)

        assert result.phase_match is False
        assert result.status_match is False
        assert result.endpoint_match is False
        assert len(result.mismatches) == 3
        assert result.evidence_grade == "unvalidated"

    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_phase_1_match(self, mock_fetch):
        mock_fetch.return_value = _make_registry_proto(phase_key="PHASE1", status_key="RECRUITING")
        trial = _make_trial(phase=TrialPhase.PHASE_1, primary_endpoint=None)

        result = validate_against_registry("NCT99999999", trial)

        assert result.phase_match is True
        assert result.evidence_grade == "calibrated"

    @patch("bve.ingestion.clinicaltrials_gov.fetch_study")
    def test_nct_id_stripped_and_uppercased(self, mock_fetch):
        mock_fetch.return_value = _make_registry_proto()
        trial = _make_trial()

        validate_against_registry("  nct99999999  ", trial)

        mock_fetch.assert_called_once_with("NCT99999999")
