"""
Tests for:
  - EvidenceState schema (evidence_state.py)
  - TrialDiscontinuationFilter (trial_materiality_filter.py)
  - EvidenceRecord backward compat and new fields (evidence_ledger.py)
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from bve.ingestion.evidence_state import (
    AppliesTo,
    ClassificationConfidence,
    EvidenceState,
    MaterialityTier,
    MATERIALITY_DELTA_SCALE,
    Recency,
    SignalState,
    SourceQuality,
)
from bve.ingestion.trial_materiality_filter import TrialDiscontinuationFilter
from bve.ingestion.evidence_ledger import EvidenceRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(**overrides) -> EvidenceRecord:
    defaults = dict(
        ticker="TEST",
        event_date="2025-01-15",
        event_type="trial_discontinuation",
        direction="negative",
        phase_detected="phase_2",
        source_type="news_article",
        source_url="https://example.com",
        raw_text="Trial discontinued due to slow enrollment",
        confidence=0.70,
        match_reasons=["trial discontinued"],
        score_deltas={"asset_quality": -0.20, "seller_willingness": +0.10},
    )
    defaults.update(overrides)
    return EvidenceRecord(**defaults)


# ---------------------------------------------------------------------------
# EvidenceState — enum values
# ---------------------------------------------------------------------------

class TestEvidenceStateEnums:
    def test_signal_state_values(self):
        assert SignalState.MISSING.value == "missing"
        assert SignalState.PRESENT_NEGATIVE.value == "present_negative"
        assert SignalState.PRESENT_POSITIVE.value == "present_positive"
        assert SignalState.PRESENT_NEUTRAL.value == "present_neutral"

    def test_materiality_tier_values(self):
        assert MaterialityTier.IMMATERIAL.value == "immaterial"
        assert MaterialityTier.MINOR.value == "minor"
        assert MaterialityTier.MATERIAL.value == "material"
        assert MaterialityTier.THESIS_CHANGING.value == "thesis_changing"

    def test_materiality_delta_scale_ordering(self):
        assert MATERIALITY_DELTA_SCALE[MaterialityTier.IMMATERIAL] == 0.00
        assert MATERIALITY_DELTA_SCALE[MaterialityTier.MINOR] == 0.25
        assert MATERIALITY_DELTA_SCALE[MaterialityTier.MATERIAL] == 0.60
        assert MATERIALITY_DELTA_SCALE[MaterialityTier.THESIS_CHANGING] == 1.00


# ---------------------------------------------------------------------------
# EvidenceState.effective_delta_scale
# ---------------------------------------------------------------------------

class TestEffectiveDeltaScale:
    def test_missing_signal_returns_zero(self):
        state = EvidenceState(
            signal_state=SignalState.MISSING,
            materiality=MaterialityTier.THESIS_CHANGING,
            source_quality=SourceQuality.HIGH,
            classification_confidence=ClassificationConfidence.HIGH,
        )
        assert state.effective_delta_scale() == 0.0

    def test_thesis_changing_high_quality_returns_one(self):
        state = EvidenceState(
            signal_state=SignalState.PRESENT_NEGATIVE,
            materiality=MaterialityTier.THESIS_CHANGING,
            source_quality=SourceQuality.HIGH,
            classification_confidence=ClassificationConfidence.HIGH,
        )
        assert state.effective_delta_scale() == 1.00

    def test_minor_high_quality_returns_quarter(self):
        state = EvidenceState(
            signal_state=SignalState.PRESENT_NEGATIVE,
            materiality=MaterialityTier.MINOR,
            source_quality=SourceQuality.HIGH,
            classification_confidence=ClassificationConfidence.HIGH,
        )
        assert state.effective_delta_scale() == 0.25

    def test_low_source_quality_downweights_aggressively(self):
        state = EvidenceState(
            signal_state=SignalState.PRESENT_NEGATIVE,
            materiality=MaterialityTier.THESIS_CHANGING,
            source_quality=SourceQuality.LOW,
            classification_confidence=ClassificationConfidence.HIGH,
        )
        # 1.00 * 0.25 = 0.25
        assert state.effective_delta_scale() == pytest.approx(0.25)

    def test_low_confidence_downweights_aggressively(self):
        state = EvidenceState(
            signal_state=SignalState.PRESENT_NEGATIVE,
            materiality=MaterialityTier.MATERIAL,
            source_quality=SourceQuality.HIGH,
            classification_confidence=ClassificationConfidence.LOW,
        )
        # 0.60 * 0.25 = 0.15
        assert state.effective_delta_scale() == pytest.approx(0.15)

    def test_immaterial_returns_zero_regardless_of_quality(self):
        state = EvidenceState(
            signal_state=SignalState.PRESENT_NEGATIVE,
            materiality=MaterialityTier.IMMATERIAL,
            source_quality=SourceQuality.HIGH,
            classification_confidence=ClassificationConfidence.HIGH,
        )
        assert state.effective_delta_scale() == 0.0


# ---------------------------------------------------------------------------
# EvidenceState — serialisation round-trip
# ---------------------------------------------------------------------------

class TestEvidenceStateSerialization:
    def test_to_dict_and_from_dict_roundtrip(self):
        state = EvidenceState(
            signal_state=SignalState.PRESENT_NEGATIVE,
            materiality=MaterialityTier.THESIS_CHANGING,
            source_quality=SourceQuality.HIGH,
            recency=Recency.CURRENT,
            applies_to=AppliesTo.LEAD_ASSET,
            classification_confidence=ClassificationConfidence.HIGH,
        )
        d = state.to_dict()
        restored = EvidenceState.from_dict(d)
        assert restored == state

    def test_from_dict_uses_enum_values(self):
        d = {
            "signal_state": "present_negative",
            "materiality": "material",
            "source_quality": "medium",
            "recency": "stale",
            "applies_to": "pipeline_asset",
            "classification_confidence": "low",
        }
        state = EvidenceState.from_dict(d)
        assert state.signal_state == SignalState.PRESENT_NEGATIVE
        assert state.materiality == MaterialityTier.MATERIAL
        assert state.recency == Recency.STALE

    def test_from_dict_defaults_on_missing_keys(self):
        state = EvidenceState.from_dict({})
        assert state.signal_state == SignalState.PRESENT_NEUTRAL
        assert state.materiality == MaterialityTier.MINOR
        assert state.classification_confidence == ClassificationConfidence.MEDIUM

    def test_legacy_classmethod(self):
        state = EvidenceState.legacy()
        assert state.signal_state == SignalState.PRESENT_NEUTRAL
        assert state.classification_confidence == ClassificationConfidence.LOW


# ---------------------------------------------------------------------------
# TrialDiscontinuationFilter — materiality classification
# ---------------------------------------------------------------------------

class TestTrialDiscontinuationFilterMateriality:
    """Verify that the correct materiality tier is chosen for each context."""

    def test_investigator_sponsored_is_immaterial(self):
        rec = _make_record()
        result = TrialDiscontinuationFilter.apply(rec, {"is_company_sponsored": False})
        state = EvidenceState.from_dict(result.evidence_state)
        assert state.materiality == MaterialityTier.IMMATERIAL
        assert result.score_deltas == {}

    def test_company_sponsored_stale_is_minor(self):
        rec = _make_record()
        result = TrialDiscontinuationFilter.apply(rec, {
            "is_company_sponsored": True,
            "event_age_days": 800,  # > 730 stale threshold
        })
        state = EvidenceState.from_dict(result.evidence_state)
        assert state.materiality == MaterialityTier.MINOR

    def test_thesis_changing_requires_lead_asset_plus_core_or_enrollment(self):
        rec = _make_record()
        result = TrialDiscontinuationFilter.apply(rec, {
            "is_company_sponsored": True,
            "is_lead_asset": True,
            "is_core_indication": True,
            "event_age_days": 30,
        })
        state = EvidenceState.from_dict(result.evidence_state)
        assert state.materiality == MaterialityTier.THESIS_CHANGING

    def test_thesis_changing_via_enrollment_count(self):
        rec = _make_record()
        result = TrialDiscontinuationFilter.apply(rec, {
            "is_company_sponsored": True,
            "is_lead_asset": True,
            "enrollment_count": 120,
            "event_age_days": 10,
        })
        state = EvidenceState.from_dict(result.evidence_state)
        assert state.materiality == MaterialityTier.THESIS_CHANGING

    def test_lead_asset_alone_is_material(self):
        rec = _make_record()
        result = TrialDiscontinuationFilter.apply(rec, {
            "is_company_sponsored": True,
            "is_lead_asset": True,
            "is_core_indication": False,
            "enrollment_count": 10,  # below threshold
            "event_age_days": 30,
        })
        state = EvidenceState.from_dict(result.evidence_state)
        assert state.materiality == MaterialityTier.MATERIAL

    def test_non_core_non_lead_company_sponsored_current_is_minor(self):
        rec = _make_record()
        result = TrialDiscontinuationFilter.apply(rec, {
            "is_company_sponsored": True,
            "is_lead_asset": False,
            "is_core_indication": False,
            "event_age_days": 10,
        })
        state = EvidenceState.from_dict(result.evidence_state)
        assert state.materiality == MaterialityTier.MINOR

    def test_small_enrollment_below_threshold_does_not_trigger_thesis_changing(self):
        rec = _make_record()
        result = TrialDiscontinuationFilter.apply(rec, {
            "is_company_sponsored": True,
            "is_lead_asset": True,
            "enrollment_count": 20,  # < 50 threshold
            "is_core_indication": False,
            "event_age_days": 10,
        })
        state = EvidenceState.from_dict(result.evidence_state)
        # lead asset + not core + enrollment < 50 → MATERIAL not THESIS_CHANGING
        assert state.materiality == MaterialityTier.MATERIAL


# ---------------------------------------------------------------------------
# TrialDiscontinuationFilter — score delta scaling
# ---------------------------------------------------------------------------

class TestTrialDiscontinuationFilterDeltas:
    """Verify score_deltas are scaled correctly by materiality tier."""

    def test_immaterial_returns_empty_deltas(self):
        rec = _make_record()
        result = TrialDiscontinuationFilter.apply(rec, {"is_company_sponsored": False})
        assert result.score_deltas == {}

    def test_thesis_changing_high_quality_applies_full_base_delta(self):
        rec = _make_record(source_type="clinicaltrials_gov")
        result = TrialDiscontinuationFilter.apply(rec, {
            "is_company_sponsored": True,
            "is_lead_asset": True,
            "is_core_indication": True,
            "source_confirmed": True,
            "event_age_days": 10,
        })
        # scale=1.00, base={asset_quality: -0.20, seller_willingness: +0.10}
        assert result.score_deltas["asset_quality"] == pytest.approx(-0.20)
        assert result.score_deltas["seller_willingness"] == pytest.approx(+0.10)

    def test_minor_tier_applies_quarter_of_base_deltas(self):
        rec = _make_record(source_type="clinicaltrials_gov")
        result = TrialDiscontinuationFilter.apply(rec, {
            "is_company_sponsored": True,
            "is_lead_asset": False,
            "is_core_indication": False,
            "source_confirmed": True,
            "event_age_days": 10,
        })
        # MINOR base: {asset_quality: -0.05, seller_willingness: +0.02}
        # scale=0.25 but MINOR already uses 0.25 × base — check base MINOR values
        state = EvidenceState.from_dict(result.evidence_state)
        assert state.materiality == MaterialityTier.MINOR
        # MINOR base deltas: asset_quality=-0.05, seller_willingness=+0.02
        # high quality source → scale stays at MINOR tier scale (1.0 × base)
        assert result.score_deltas["asset_quality"] == pytest.approx(-0.05)

    def test_low_quality_source_further_downweights(self):
        rec = _make_record(source_type="news_article")  # LOW source quality
        result = TrialDiscontinuationFilter.apply(rec, {
            "is_company_sponsored": True,
            "is_lead_asset": True,
            "is_core_indication": True,
            "source_confirmed": False,
            "event_age_days": 10,
        })
        # THESIS_CHANGING base: asset_quality=-0.20
        # news_article → LOW source quality → LOW_QUALITY_SCALE=0.25 → -0.20 * 0.25 = -0.05
        assert result.score_deltas["asset_quality"] == pytest.approx(-0.05, abs=1e-4)

    def test_original_record_not_mutated(self):
        rec = _make_record()
        original_deltas = dict(rec.score_deltas)
        TrialDiscontinuationFilter.apply(rec, {"is_company_sponsored": True})
        assert rec.score_deltas == original_deltas


# ---------------------------------------------------------------------------
# TrialDiscontinuationFilter — schema_version and evidence_state fields
# ---------------------------------------------------------------------------

class TestTrialDiscontinuationFilterSchema:
    def test_schema_version_set_to_evidence_state_v1(self):
        rec = _make_record()
        result = TrialDiscontinuationFilter.apply(rec, {"is_company_sponsored": True})
        assert result.schema_version == "evidence_state_v1"

    def test_evidence_state_is_dict_with_expected_keys(self):
        rec = _make_record()
        result = TrialDiscontinuationFilter.apply(rec, {
            "is_company_sponsored": True,
            "is_lead_asset": True,
            "is_core_indication": True,
        })
        assert isinstance(result.evidence_state, dict)
        for key in ("signal_state", "materiality", "source_quality",
                    "recency", "applies_to", "classification_confidence"):
            assert key in result.evidence_state

    def test_is_applicable_true_for_trial_discontinuation(self):
        rec = _make_record(event_type="trial_discontinuation")
        assert TrialDiscontinuationFilter.is_applicable(rec) is True

    def test_is_applicable_false_for_other_event_types(self):
        rec = _make_record(event_type="fda_approval")
        assert TrialDiscontinuationFilter.is_applicable(rec) is False

    def test_signal_state_is_present_negative_for_sponsored_good_source(self):
        rec = _make_record(source_type="press_release")
        result = TrialDiscontinuationFilter.apply(rec, {
            "is_company_sponsored": True,
            "source_confirmed": False,
        })
        state = EvidenceState.from_dict(result.evidence_state)
        assert state.signal_state == SignalState.PRESENT_NEGATIVE

    def test_signal_state_is_present_neutral_for_unsponsored(self):
        rec = _make_record(source_type="news_article")
        result = TrialDiscontinuationFilter.apply(rec, {
            "is_company_sponsored": False,
        })
        state = EvidenceState.from_dict(result.evidence_state)
        assert state.signal_state == SignalState.PRESENT_NEUTRAL


# ---------------------------------------------------------------------------
# EvidenceRecord — new fields and backward compat
# ---------------------------------------------------------------------------

class TestEvidenceRecordNewFields:
    def test_new_fields_default_to_none(self):
        rec = _make_record()
        assert rec.schema_version is None
        assert rec.evidence_state is None

    def test_from_jsonl_ignores_unknown_fields(self):
        """Records written by a future schema version should not crash the reader."""
        rec = _make_record()
        d = dataclasses.asdict(rec)
        d["future_field_xyz"] = "ignored"
        line = json.dumps(d)
        restored = EvidenceRecord.from_jsonl(line)
        assert restored.ticker == rec.ticker
        assert not hasattr(restored, "future_field_xyz")

    def test_from_jsonl_reads_schema_version_and_evidence_state(self):
        rec = _make_record()
        result = TrialDiscontinuationFilter.apply(rec, {
            "is_company_sponsored": True,
            "is_lead_asset": True,
            "is_core_indication": True,
        })
        line = result.to_jsonl()
        restored = EvidenceRecord.from_jsonl(line)
        assert restored.schema_version == "evidence_state_v1"
        assert isinstance(restored.evidence_state, dict)
        assert restored.evidence_state["materiality"] == "thesis_changing"

    def test_legacy_record_missing_new_fields_loads_cleanly(self):
        """Old JSONL records without schema_version / evidence_state must load."""
        old_dict = {
            "ticker": "LGCY",
            "event_date": "2023-06-01",
            "event_type": "trial_discontinuation",
            "direction": "negative",
            "phase_detected": None,
            "source_type": "news_article",
            "source_url": "https://example.com",
            "raw_text": "Old trial discontinued",
            "confidence": 0.65,
            "match_reasons": ["trial discontinued"],
            "score_deltas": {"asset_quality": -0.20},
            "created_at": "2023-06-01T00:00:00+00:00",
            "ledger_version": "1",
            "published_date": "2023-06-01",
            "event_hash": "abc123",
        }
        line = json.dumps(old_dict)
        rec = EvidenceRecord.from_jsonl(line)
        assert rec.ticker == "LGCY"
        assert rec.schema_version is None
        assert rec.evidence_state is None
