"""
Block 33 — Indication-Subtype Base Rates
TDD tests written BEFORE implementation.

Tests for:
  1. 8 subtypes loaded from industry_assumptions.yaml
  2. Specific subtype phase rates
  3. Each subtype has required metadata fields (source, n_programs, confidence, ta_fallback)
  4. POSAdjusters.indication_subtype field (Optional[str], default None)
  5. Subtype rate overrides TA base rate when set
  6. Unknown subtype falls back to TA rate with UserWarning
  7. Output audit fields: subtype_base_rate_used, subtype_key_used,
     subtype_confidence, subtype_ta_fallback
  8. Backward compat: indication_subtype=None → unchanged behavior
"""
from __future__ import annotations

import warnings

import pytest

from bve.config.assumptions_loader import AssumptionsLoader
from bve.models.pos_model import (
    POSAdjusters,
    POSComputeResult,
    compute_pos,
    compute_pos_detailed,
    TherapeuticArea,
)
from bve.entities.trial import TrialPhase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _loader() -> AssumptionsLoader:
    return AssumptionsLoader.get()


# ---------------------------------------------------------------------------
# Block 33-A: 8 subtypes in YAML
# ---------------------------------------------------------------------------

class TestIndicationSubtypeYAML:

    def test_eight_subtypes_loaded(self):
        loader = _loader()
        subtypes = loader.indication_subtype_rates
        assert len(subtypes) >= 8

    def test_gbm_present(self):
        loader = _loader()
        assert "gbm" in loader.indication_subtype_rates

    def test_alzheimers_present(self):
        loader = _loader()
        assert "alzheimers" in loader.indication_subtype_rates

    def test_ultra_rare_monogenic_present(self):
        loader = _loader()
        assert "ultra_rare_monogenic" in loader.indication_subtype_rates

    def test_nsclc_targeted_present(self):
        loader = _loader()
        assert "nsclc_targeted" in loader.indication_subtype_rates

    def test_gbm_phase_2_rate(self):
        loader = _loader()
        rate = loader.get_indication_subtype_rate("gbm", "phase_2")
        assert rate == pytest.approx(0.120, abs=1e-3)

    def test_alzheimers_phase_2_rate(self):
        loader = _loader()
        rate = loader.get_indication_subtype_rate("alzheimers", "phase_2")
        assert rate == pytest.approx(0.180, abs=1e-3)

    def test_ultra_rare_monogenic_phase_2_rate(self):
        loader = _loader()
        rate = loader.get_indication_subtype_rate("ultra_rare_monogenic", "phase_2")
        assert rate == pytest.approx(0.580, abs=1e-3)

    def test_nsclc_targeted_phase_3_rate(self):
        loader = _loader()
        rate = loader.get_indication_subtype_rate("nsclc_targeted", "phase_3")
        assert rate == pytest.approx(0.510, abs=1e-3)

    def test_unknown_key_returns_none(self):
        loader = _loader()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            rate = loader.get_indication_subtype_rate("nonexistent_subtype", "phase_2")
        assert rate is None

    def test_each_subtype_has_metadata_fields(self):
        loader = _loader()
        required = {"source", "n_programs", "date_range", "confidence", "ta_fallback"}
        for key, data in loader.indication_subtype_rates.items():
            missing = required - set(data.keys())
            assert not missing, f"Subtype {key!r} missing metadata fields: {missing}"

    def test_get_indication_subtype_metadata_returns_dict(self):
        loader = _loader()
        meta = loader.get_indication_subtype_metadata("gbm")
        assert isinstance(meta, dict)
        assert "source" in meta
        assert "confidence" in meta
        assert "ta_fallback" in meta

    def test_get_indication_subtype_metadata_unknown_returns_none(self):
        loader = _loader()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            meta = loader.get_indication_subtype_metadata("nonexistent")
        assert meta is None


# ---------------------------------------------------------------------------
# Block 33-B: POSAdjusters new field
# ---------------------------------------------------------------------------

class TestPOSAdjustersSubtypeField:

    def test_indication_subtype_field_exists(self):
        adj = POSAdjusters()
        assert hasattr(adj, "indication_subtype")

    def test_indication_subtype_default_none(self):
        adj = POSAdjusters()
        assert adj.indication_subtype is None

    def test_indication_subtype_accepts_string(self):
        adj = POSAdjusters(indication_subtype="gbm")
        assert adj.indication_subtype == "gbm"

    def test_indication_subtype_accepts_any_string(self):
        adj = POSAdjusters(indication_subtype="nsclc_targeted")
        assert adj.indication_subtype == "nsclc_targeted"


# ---------------------------------------------------------------------------
# Block 33-C: Subtype base rate overrides TA base rate in compute_pos
# ---------------------------------------------------------------------------

class TestSubtypeBaseRateInComputePos:

    def test_gbm_pos_lower_than_oncology_solid_for_same_adjusters(self):
        """GBM phase 2 rate 0.12 < oncology_solid phase 2 rate (typically ~0.23)."""
        pos_ta = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_gbm = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(indication_subtype="gbm"),
        )
        assert pos_gbm < pos_ta

    def test_ultra_rare_higher_than_rare_disease_for_same_adjusters(self):
        """Ultra-rare monogenic 0.58 > rare_disease TA rate (typically ~0.48)."""
        pos_ta = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE, POSAdjusters()
        )
        pos_ultra = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(indication_subtype="ultra_rare_monogenic"),
        )
        assert pos_ultra > pos_ta

    def test_unknown_subtype_falls_back_to_ta_with_warning(self):
        """Unknown subtype key: UserWarning emitted, TA rate used."""
        pos_ta = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            pos_unknown = compute_pos(
                TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
                POSAdjusters(indication_subtype="nonexistent_subtype_xyz"),
            )
        assert pos_unknown == pytest.approx(pos_ta, abs=1e-6)
        assert any("nonexistent_subtype_xyz" in str(warning.message) for warning in w)

    def test_none_indication_subtype_uses_ta_rate_unchanged(self):
        pos_none = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_explicit_none = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(indication_subtype=None),
        )
        assert pos_none == pytest.approx(pos_explicit_none, abs=1e-6)


# ---------------------------------------------------------------------------
# Block 33-D: Output audit fields on POSComputeResult
# ---------------------------------------------------------------------------

class TestSubtypeOutputFields:

    def test_subtype_base_rate_used_field_exists(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        assert hasattr(result, "subtype_base_rate_used")

    def test_subtype_key_used_field_exists(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        assert hasattr(result, "subtype_key_used")

    def test_subtype_confidence_field_exists(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        assert hasattr(result, "subtype_confidence")

    def test_subtype_ta_fallback_field_exists(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        assert hasattr(result, "subtype_ta_fallback")

    def test_no_subtype_fields_are_none(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        assert result.subtype_base_rate_used is None
        assert result.subtype_key_used is None
        assert result.subtype_confidence is None
        assert result.subtype_ta_fallback is None

    def test_gbm_subtype_base_rate_used(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(indication_subtype="gbm"),
        )
        assert result.subtype_base_rate_used == pytest.approx(0.120, abs=1e-3)

    def test_gbm_subtype_key_used(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(indication_subtype="gbm"),
        )
        assert result.subtype_key_used == "gbm"

    def test_gbm_subtype_confidence(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(indication_subtype="gbm"),
        )
        assert result.subtype_confidence == "medium"

    def test_gbm_subtype_ta_fallback(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(indication_subtype="gbm"),
        )
        assert result.subtype_ta_fallback == "oncology_solid"


# ---------------------------------------------------------------------------
# Block 33-E: backward compatibility
# ---------------------------------------------------------------------------

class TestSubtypeBackwardCompat:

    def test_no_subtype_same_as_before(self):
        """Existing compute_pos() calls unchanged when indication_subtype=None."""
        pos_old = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_new = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(indication_subtype=None),
        )
        assert pos_old == pytest.approx(pos_new, abs=1e-6)

    def test_existing_ta_rates_unaffected(self):
        """TA base rates in PHASE_SUCCESS_RATES are unchanged."""
        for ta in [TherapeuticArea.ONCOLOGY_SOLID, TherapeuticArea.RARE_DISEASE]:
            pos = compute_pos(TrialPhase.PHASE_2, ta, POSAdjusters())
            assert 0.0 < pos < 1.0

    def test_compute_pos_detailed_backward_compat(self):
        """compute_pos_detailed() returns all existing fields unchanged."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        assert hasattr(result, "pos")
        assert hasattr(result, "confidence_flags")
        assert hasattr(result, "phase_realism_applied")
        assert hasattr(result, "btd_timeline_acceleration_flag")
        assert hasattr(result, "btd_overlap_warning")
