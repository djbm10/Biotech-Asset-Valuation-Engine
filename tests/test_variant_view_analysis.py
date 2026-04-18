"""Tests for variant_view analysis module."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from bve.analysis.variant_view import (
    ConsensusAssumption,
    KillCriterion,
    ModelAssumption,
    ThesisEvidence,
    VariantDelta,
    VariantThesis,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# ThesisEvidence
# ---------------------------------------------------------------------------

def test_thesis_evidence_basic():
    ev = ThesisEvidence(
        evidence_id="E1",
        source="NEJM",
        description="Phase 2 response rate 65%",
        supports_model_view=True,
        confidence=0.85,
        date_observed=date(2025, 1, 15),
    )
    assert ev.supports_model_view is True
    assert ev.confidence == 0.85


def test_thesis_evidence_confidence_bounds():
    with pytest.raises(Exception):
        ThesisEvidence(
            evidence_id="E1",
            source="X",
            description="x",
            supports_model_view=True,
            confidence=1.5,
            date_observed=date(2025, 1, 1),
        )


# ---------------------------------------------------------------------------
# KillCriterion
# ---------------------------------------------------------------------------

def test_kill_criterion_defaults():
    kc = KillCriterion(
        criterion_id="K1",
        description="ORR < 20%",
        dimension="efficacy",
        threshold_description="ORR below threshold",
    )
    assert kc.is_triggered is False
    assert kc.observable_by is None


def test_kill_criterion_triggered():
    kc = KillCriterion(
        criterion_id="K1",
        description="SAE rate > 15%",
        dimension="safety",
        threshold_description="Unacceptable safety",
        observable_by=date(2025, 12, 1),
        is_triggered=True,
    )
    assert kc.is_triggered is True


# ---------------------------------------------------------------------------
# VariantDelta
# ---------------------------------------------------------------------------

def test_variant_delta_basic():
    ca = ConsensusAssumption(dimension="pos", consensus_value="40%", confidence=0.7, source="consensus")
    ma = ModelAssumption(dimension="pos", model_value="55%", confidence=0.8, rationale="Better trial design")
    delta = VariantDelta(
        dimension="pos",
        consensus_assumption=ca,
        model_assumption=ma,
        delta_summary="Model 15pp above consensus",
        magnitude=0.35,
        falsifier="Phase 3 readout",
    )
    assert delta.magnitude == 0.35
    assert delta.supporting_evidence == []
    assert delta.kill_criteria == []


def test_variant_delta_magnitude_bounds():
    ca = ConsensusAssumption(dimension="pos", consensus_value="40%", confidence=0.5, source="x")
    ma = ModelAssumption(dimension="pos", model_value="55%", confidence=0.5, rationale="y")
    with pytest.raises(Exception):
        VariantDelta(
            dimension="pos",
            consensus_assumption=ca,
            model_assumption=ma,
            delta_summary="out of range",
            magnitude=2.0,  # > 1.0
            falsifier="readout",
        )


# ---------------------------------------------------------------------------
# VariantThesis
# ---------------------------------------------------------------------------

def test_variant_thesis_basic():
    now = _now()
    thesis = VariantThesis(
        asset_id="A1",
        ticker="TICK",
        created_at=now,
        updated_at=now,
        what_market_believes="Drug will fail Phase 3",
        what_model_thinks="Drug will succeed due to biomarker selection",
        why_gap_exists="Market not pricing biomarker-selected subgroup",
        confidence_score=0.75,
        overall_conviction="high",
    )
    assert thesis.overall_conviction == "high"
    assert thesis.deltas == []
    assert thesis.catalysts_to_resolve == []


def test_variant_thesis_with_deltas():
    now = _now()
    ca = ConsensusAssumption(dimension="pos", consensus_value="30%", confidence=0.6, source="x")
    ma = ModelAssumption(dimension="pos", model_value="50%", confidence=0.7, rationale="y")
    delta = VariantDelta(
        dimension="pos",
        consensus_assumption=ca,
        model_assumption=ma,
        delta_summary="big gap",
        magnitude=0.5,
        falsifier="readout",
    )
    thesis = VariantThesis(
        asset_id="A1",
        ticker="TICK",
        created_at=now,
        updated_at=now,
        what_market_believes="x",
        what_model_thinks="y",
        why_gap_exists="z",
        confidence_score=0.6,
        overall_conviction="medium",
        deltas=[delta],
        catalysts_to_resolve=["Phase 3 readout Q4 2025"],
    )
    assert len(thesis.deltas) == 1
    assert len(thesis.catalysts_to_resolve) == 1
