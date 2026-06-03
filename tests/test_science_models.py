"""Tests for science_score, trial_design_score, endpoint_validity, analog_matcher, safety_context modules."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bve.models.analog_matcher import Analog, AnalogMatch, AnalogMatcher
from bve.models.endpoint_validity import EndpointValidity, EndpointValidityScore
from bve.models.safety_context import SafetyContext, SafetySignal
from bve.models.science_score import ScienceScore, ScienceScoreComponent
from bve.models.trial_design_score import TrialDesignScore, TrialDesignScoreComponent


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# ScienceScoreComponent / ScienceScore
# ---------------------------------------------------------------------------

def test_science_score_component_basic():
    comp = ScienceScoreComponent(
        name="target_validation",
        score=0.85,
        weight=0.30,
        rationale="Well-validated oncology target.",
        confidence=0.80,
    )
    assert comp.name == "target_validation"


def test_science_score_weighted_property():
    c1 = ScienceScoreComponent(name="target", score=0.80, weight=0.60, rationale="x", confidence=0.7)
    c2 = ScienceScoreComponent(name="moa", score=0.60, weight=0.40, rationale="y", confidence=0.6)
    ss = ScienceScore(
        asset_id="A1",
        scored_at=_now(),
        components=[c1, c2],
        composite_score=0.72,
        confidence_band_low=0.60,
        confidence_band_high=0.85,
        top_positives=["strong target validation"],
        top_risks=["no biomarker"],
        plain_english_summary="Solid science.",
    )
    expected = (0.80 * 0.60 + 0.60 * 0.40) / (0.60 + 0.40)
    assert abs(ss.weighted_score - expected) < 1e-9


def test_science_score_weighted_empty_components():
    ss = ScienceScore(
        asset_id="A1",
        scored_at=_now(),
        components=[],
        composite_score=0.0,
        confidence_band_low=0.0,
        confidence_band_high=0.0,
        plain_english_summary="No data.",
    )
    assert ss.weighted_score == 0.0


# ---------------------------------------------------------------------------
# TrialDesignScore
# ---------------------------------------------------------------------------

def test_trial_design_score_basic():
    comp = TrialDesignScoreComponent(name="endpoint", score=0.80, weight=0.40, rationale="Accepted endpoint.")
    tds = TrialDesignScore(
        asset_id="A1",
        trial_id="NCT001",
        scored_at=_now(),
        components=[comp],
        composite_score=0.75,
        endpoint_score=0.80,
        power_score=0.70,
        design_score=0.75,
        biomarker_score=0.60,
        regulatory_alignment_score=0.80,
        plain_english_summary="Good trial design.",
    )
    assert tds.endpoint_score == 0.80
    assert tds.trial_id == "NCT001"


def test_trial_design_score_no_trial_id():
    tds = TrialDesignScore(
        asset_id="A1",
        scored_at=_now(),
        components=[],
        composite_score=0.5,
        endpoint_score=0.5,
        power_score=0.5,
        design_score=0.5,
        biomarker_score=0.5,
        regulatory_alignment_score=0.5,
        plain_english_summary="Average.",
    )
    assert tds.trial_id is None


# ---------------------------------------------------------------------------
# EndpointValidity
# ---------------------------------------------------------------------------

def test_endpoint_validity_score_basic():
    evs = EndpointValidityScore(
        endpoint_name="PFS",
        endpoint_type="primary",
        clinical_meaningfulness=0.75,
        regulatory_acceptability=0.85,
        measurability=0.90,
        precedent_count=12,
        rationale="PFS is regulatory-accepted for oncology.",
    )
    assert evs.precedent_count == 12


def test_endpoint_validity_container():
    evs = EndpointValidityScore(
        endpoint_name="OS",
        endpoint_type="primary",
        clinical_meaningfulness=0.95,
        regulatory_acceptability=0.95,
        measurability=1.0,
        rationale="Gold standard.",
    )
    ev = EndpointValidity(
        asset_id="A1",
        scored_at=_now(),
        primary_endpoint_scores=[evs],
        overall_validity_score=0.90,
        regulatory_risk="low",
        commentary="Strong endpoint selection.",
    )
    assert ev.regulatory_risk == "low"
    assert len(ev.primary_endpoint_scores) == 1


# ---------------------------------------------------------------------------
# AnalogMatcher
# ---------------------------------------------------------------------------

def test_analog_basic():
    analog = Analog(
        analog_id="ANA1",
        name="Venetoclax",
        indication="CLL",
        phase_at_comparison="Phase 2",
        outcome="approved",
        peak_sales_millions=2000.0,
        pos_at_phase=0.55,
    )
    assert analog.outcome == "approved"
    assert analog.target is None


def test_analog_match_basic():
    analog = Analog(
        analog_id="ANA1",
        name="Venetoclax",
        indication="CLL",
        phase_at_comparison="Phase 2",
        outcome="approved",
    )
    match = AnalogMatch(
        focal_asset_id="A1",
        analog=analog,
        similarity_score=0.75,
        is_winner=True,
        key_similarities=["same target class", "same indication"],
        key_differences=["different patient selection"],
        lesson="Venetoclax success suggests high POS for similar BH3 mimetics.",
    )
    assert match.is_winner is True
    assert len(match.key_similarities) == 2


def test_analog_matcher_container():
    analog = Analog(
        analog_id="ANA1",
        name="Venetoclax",
        indication="CLL",
        phase_at_comparison="Phase 2",
        outcome="approved",
    )
    match = AnalogMatch(focal_asset_id="A1", analog=analog, similarity_score=0.75, is_winner=True, lesson="x")
    matcher = AnalogMatcher(
        asset_id="A1",
        matched_at=_now(),
        winning_analogs=[match],
        failing_analogs=[],
        pos_implied_by_analogs=0.55,
        analog_confidence=0.70,
        summary="Strong winning analogue set.",
    )
    assert matcher.pos_implied_by_analogs == 0.55
    assert len(matcher.winning_analogs) == 1


# ---------------------------------------------------------------------------
# SafetyContext
# ---------------------------------------------------------------------------

def test_safety_signal_basic():
    sig = SafetySignal(
        signal_id="SIG1",
        description="Grade 3 neutropenia",
        severity="severe",
        frequency="uncommon",
        mechanism_plausibility="high",
        regulatory_precedent="managed",
        source="Phase 2 data",
    )
    assert sig.severity == "severe"


def test_safety_context_basic():
    sig = SafetySignal(
        signal_id="SIG1",
        description="Grade 3 neutropenia",
        severity="moderate",
        frequency="uncommon",
        mechanism_plausibility="medium",
        regulatory_precedent="managed",
        source="Phase 2",
    )
    ctx = SafetyContext(
        asset_id="A1",
        assessed_at=_now(),
        signals=[sig],
        overall_safety_score=0.75,
        safety_risk_tier="medium",
        class_safety_profile="Known manageable toxicities",
        regulatory_concern=False,
        pos_penalty=0.05,
        commentary="Manageable toxicity profile.",
    )
    assert ctx.safety_risk_tier == "medium"
    assert ctx.regulatory_concern is False


def test_safety_context_pos_penalty_bounds():
    with pytest.raises(Exception):
        SafetyContext(
            asset_id="A1",
            assessed_at=_now(),
            overall_safety_score=0.5,
            safety_risk_tier="high",
            class_safety_profile="x",
            regulatory_concern=True,
            pos_penalty=1.5,  # out of range
            commentary="x",
        )
