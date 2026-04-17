"""Tests for bve.dossier (AssetDossier, DossierBuilder, completeness)."""
import pytest
from datetime import date

from bve.dossier.dossier import AssetDossier, ProvenanceField, TrialSummary, DossierCompletenessReport
from bve.dossier.builder import DossierBuilder


_TODAY = date(2026, 4, 17)


def _builder() -> DossierBuilder:
    return DossierBuilder("PROG-001", "Drug X", "Acme Bio")


class TestProvenanceField:
    def test_stores_value(self):
        pf = ProvenanceField(value="PD-1 inhibitor", source="SEC", extracted_at=_TODAY, confidence=0.9)
        assert pf.value == "PD-1 inhibitor"

    def test_confidence_bounds(self):
        with pytest.raises(ValueError):
            ProvenanceField(value="x", source="y", extracted_at=_TODAY, confidence=1.5)
        with pytest.raises(ValueError):
            ProvenanceField(value="x", source="y", extracted_at=_TODAY, confidence=-0.1)

    def test_last_verified_optional(self):
        pf = ProvenanceField(value=42.0, source="model", extracted_at=_TODAY, confidence=0.8)
        assert pf.last_verified is None


class TestDossierBuilder:
    def test_build_returns_asset_dossier(self):
        dossier = _builder().build()
        assert isinstance(dossier, AssetDossier)

    def test_identity_fields_set(self):
        dossier = _builder().build()
        assert dossier.program_id == "PROG-001"
        assert dossier.asset_name == "Drug X"
        assert dossier.company == "Acme Bio"

    def test_set_field_creates_provenance_field(self):
        dossier = (
            _builder()
            .set_field("mechanism_of_action", "PD-1 inhibitor",
                       source="SEC", confidence=0.95, extracted_at=_TODAY)
            .build()
        )
        pf = dossier.mechanism_of_action
        assert isinstance(pf, ProvenanceField)
        assert pf.value == "PD-1 inhibitor"
        assert pf.source == "SEC"
        assert pf.confidence == 0.95

    def test_chained_set_field(self):
        dossier = (
            _builder()
            .set_field("mechanism_of_action", "PD-1 inhibitor",
                       source="SEC", confidence=0.95, extracted_at=_TODAY)
            .set_field("current_phase", "phase_3",
                       source="ClinicalTrials.gov", confidence=0.99, extracted_at=_TODAY)
            .build()
        )
        assert dossier.mechanism_of_action is not None
        assert dossier.current_phase is not None

    def test_invalid_field_raises(self):
        with pytest.raises(ValueError, match="not a recognised"):
            _builder().set_field("nonexistent_field", "value",
                                 source="x", confidence=0.5, extracted_at=_TODAY)

    def test_add_active_trial(self):
        trial = TrialSummary(
            nct_id="NCT01234567", phase="phase_3", status="recruiting",
            primary_endpoint="OS", enrollment_target=800,
        )
        dossier = _builder().add_active_trial(trial).build()
        assert len(dossier.active_trials) == 1
        assert dossier.active_trials[0].nct_id == "NCT01234567"

    def test_add_prior_trial(self):
        trial = TrialSummary(
            nct_id="NCT09876543", phase="phase_2", status="completed",
            primary_endpoint="ORR", enrollment_target=100,
        )
        dossier = _builder().add_prior_trial(trial).build()
        assert len(dossier.prior_trial_history) == 1

    def test_add_risk(self):
        dossier = _builder().add_risk("CRL risk due to prior class failures").build()
        assert len(dossier.key_risks) == 1

    def test_add_kill_criterion(self):
        dossier = _builder().add_kill_criterion("ORR < 20% in interim").build()
        assert len(dossier.kill_criteria) == 1

    def test_set_analyst(self):
        dossier = _builder().set_analyst("djmann").build()
        assert dossier.analyst == "djmann"


class TestCompletenessReport:
    def test_empty_dossier_zero_completeness(self):
        dossier = _builder().build()
        report = dossier.completeness()
        assert report.completeness_score == 0.0

    def test_completeness_score_in_range(self):
        dossier = (
            _builder()
            .set_field("mechanism_of_action", "PD-1", source="x", confidence=0.9, extracted_at=_TODAY)
            .build()
        )
        report = dossier.completeness()
        assert 0.0 <= report.completeness_score <= 1.0

    def test_filled_fields_contains_set_field(self):
        dossier = (
            _builder()
            .set_field("mechanism_of_action", "PD-1", source="x", confidence=0.9, extracted_at=_TODAY)
            .build()
        )
        report = dossier.completeness()
        assert "mechanism_of_action" in report.filled_fields

    def test_missing_fields_excludes_set_field(self):
        dossier = (
            _builder()
            .set_field("mechanism_of_action", "PD-1", source="x", confidence=0.9, extracted_at=_TODAY)
            .build()
        )
        report = dossier.completeness()
        assert "mechanism_of_action" not in report.missing_fields

    def test_has_thesis_false_when_not_set(self):
        dossier = _builder().build()
        assert dossier.completeness().has_thesis is False

    def test_has_thesis_true_when_set(self):
        dossier = (
            _builder()
            .set_field("thesis_summary", "Strong biomarker-selected PD-1 story",
                       source="analyst", confidence=1.0, extracted_at=_TODAY)
            .build()
        )
        assert dossier.completeness().has_thesis is True

    def test_has_valuation_false_when_not_set(self):
        dossier = _builder().build()
        assert dossier.completeness().has_valuation is False

    def test_n_active_trials_reflects_count(self):
        trial = TrialSummary(nct_id="NCT0001", phase="phase_2", status="recruiting",
                             primary_endpoint="ORR", enrollment_target=150)
        dossier = _builder().add_active_trial(trial).build()
        assert dossier.completeness().n_active_trials == 1

    def test_report_str_contains_program_id(self):
        dossier = _builder().build()
        report = dossier.completeness()
        assert "PROG-001" in str(report)

    def test_report_str_contains_percentage(self):
        dossier = _builder().build()
        report = dossier.completeness()
        assert "%" in str(report)

    def test_returns_dossier_completeness_report(self):
        dossier = _builder().build()
        assert isinstance(dossier.completeness(), DossierCompletenessReport)


class TestGetFieldValue:
    def test_returns_raw_value_not_wrapper(self):
        dossier = (
            _builder()
            .set_field("mechanism_of_action", "KRAS G12C inhibitor",
                       source="SEC", confidence=0.9, extracted_at=_TODAY)
            .build()
        )
        val = dossier.get_field_value("mechanism_of_action")
        assert val == "KRAS G12C inhibitor"
        assert not isinstance(val, ProvenanceField)

    def test_returns_none_for_unset_field(self):
        dossier = _builder().build()
        assert dossier.get_field_value("mechanism_of_action") is None
