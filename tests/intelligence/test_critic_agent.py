"""Tests for Wave H — Critic Agent (advisory only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import pytest

from bve.intelligence.critic_agent import (
    CriticAgent,
    CriticConfig,
    CritiqueFinding,
    CritiqueReport,
    FindingSeverity,
)


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

@dataclass
class _Signal:
    id: str = "sig-1"
    event_id: str = "evt-1"
    asset_id: str = "asset-1"
    event_type: str = "trial_readout"
    signal_date: date = field(default_factory=date.today)
    trial_phase: Optional[str] = "phase_3"
    primary_endpoint_met: Optional[bool] = True
    fda_action_type: Optional[str] = None
    extraction_confidence: float = 0.85


@dataclass
class _Diff:
    run_id: str = "run-1"
    event_id: str = "evt-1"
    delta_npv: float = 30.0
    valuation_before: dict = field(default_factory=lambda: {"rnpv_millions": 100.0})


# ---------------------------------------------------------------------------
# Basic smoke test
# ---------------------------------------------------------------------------

def test_critique_returns_report() -> None:
    agent = CriticAgent()
    report = agent.critique(_Signal(), _Diff())
    assert isinstance(report, CritiqueReport)
    assert report.signal_id == "sig-1"
    assert report.diff_run_id == "run-1"


def test_report_advisory_only_no_block_field() -> None:
    """CritiqueReport must not have any blocking/approval field."""
    report = CritiqueReport(
        signal_id="s",
        diff_run_id="r",
    )
    assert not hasattr(report, "approved")
    assert not hasattr(report, "block")
    assert not hasattr(report, "should_reject")


# ---------------------------------------------------------------------------
# Confidence sanity
# ---------------------------------------------------------------------------

def test_low_confidence_large_delta_fires_caution() -> None:
    signal = _Signal(extraction_confidence=0.50)
    diff = _Diff(delta_npv=80.0)   # > 50M threshold
    report = CriticAgent().critique(signal, diff)
    cautions = [f for f in report.findings if f.dimension == "confidence_sanity"]
    assert len(cautions) == 1
    assert cautions[0].severity == FindingSeverity.CAUTION


def test_high_confidence_large_delta_no_caution() -> None:
    signal = _Signal(extraction_confidence=0.90)
    diff = _Diff(delta_npv=80.0)
    report = CriticAgent().critique(signal, diff)
    cautions = [f for f in report.findings if f.dimension == "confidence_sanity"]
    assert cautions == []


def test_low_confidence_small_delta_no_caution() -> None:
    signal = _Signal(extraction_confidence=0.50)
    diff = _Diff(delta_npv=10.0)   # below threshold
    report = CriticAgent().critique(signal, diff)
    cautions = [f for f in report.findings if f.dimension == "confidence_sanity"]
    assert cautions == []


# ---------------------------------------------------------------------------
# Magnitude sanity
# ---------------------------------------------------------------------------

def test_extreme_delta_fires_warning() -> None:
    diff = _Diff(delta_npv=60.0, valuation_before={"rnpv_millions": 100.0})
    report = CriticAgent().critique(_Signal(), diff)
    warnings = [f for f in report.findings if f.dimension == "magnitude_sanity"]
    assert len(warnings) == 1
    assert warnings[0].severity == FindingSeverity.WARNING


def test_normal_delta_no_magnitude_warning() -> None:
    diff = _Diff(delta_npv=20.0, valuation_before={"rnpv_millions": 100.0})
    report = CriticAgent().critique(_Signal(), diff)
    warnings = [f for f in report.findings if f.dimension == "magnitude_sanity"]
    assert warnings == []


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------

def test_stale_signal_fires_warning() -> None:
    signal = _Signal(signal_date=date.today() - timedelta(days=120))
    report = CriticAgent().critique(signal, _Diff())
    staleness = [f for f in report.findings if f.dimension == "staleness"]
    assert len(staleness) == 1
    assert staleness[0].severity == FindingSeverity.WARNING


def test_fresh_signal_no_staleness_warning() -> None:
    signal = _Signal(signal_date=date.today() - timedelta(days=10))
    report = CriticAgent().critique(signal, _Diff())
    staleness = [f for f in report.findings if f.dimension == "staleness"]
    assert staleness == []


# ---------------------------------------------------------------------------
# Phase mismatch
# ---------------------------------------------------------------------------

def test_early_phase_large_delta_fires_caution() -> None:
    signal = _Signal(trial_phase="phase_1")
    diff = _Diff(delta_npv=50.0)
    report = CriticAgent().critique(signal, diff)
    phase = [f for f in report.findings if f.dimension == "phase_mismatch"]
    assert len(phase) == 1
    assert phase[0].severity == FindingSeverity.CAUTION


def test_late_phase_large_delta_no_mismatch() -> None:
    signal = _Signal(trial_phase="phase_3")
    diff = _Diff(delta_npv=50.0)
    report = CriticAgent().critique(signal, diff)
    phase = [f for f in report.findings if f.dimension == "phase_mismatch"]
    assert phase == []


# ---------------------------------------------------------------------------
# Missing indicators
# ---------------------------------------------------------------------------

def test_trial_readout_no_endpoint_fires_info() -> None:
    signal = _Signal(
        event_type="trial_readout",
        primary_endpoint_met=None,
    )
    report = CriticAgent().critique(signal, _Diff())
    missing = [f for f in report.findings if f.dimension == "missing_indicators"]
    assert any(f.severity == FindingSeverity.INFO for f in missing)


def test_fda_signal_no_action_fires_info() -> None:
    signal = _Signal(
        event_type="fda_approval",
        primary_endpoint_met=None,
        fda_action_type=None,
    )
    report = CriticAgent().critique(signal, _Diff())
    missing = [f for f in report.findings if f.dimension == "missing_indicators"]
    assert any("fda" in f.message.lower() for f in missing)


# ---------------------------------------------------------------------------
# Concentration risk
# ---------------------------------------------------------------------------

def test_at_max_weight_fires_caution() -> None:
    report = CriticAgent().critique(
        _Signal(), _Diff(), current_position_weight=0.20
    )
    conc = [f for f in report.findings if f.dimension == "concentration_risk"]
    assert len(conc) == 1
    assert conc[0].severity == FindingSeverity.CAUTION


def test_below_max_weight_no_caution() -> None:
    report = CriticAgent().critique(
        _Signal(), _Diff(), current_position_weight=0.10
    )
    conc = [f for f in report.findings if f.dimension == "concentration_risk"]
    assert conc == []


# ---------------------------------------------------------------------------
# Competitor pressure
# ---------------------------------------------------------------------------

def test_high_confidence_competitor_fires_warning() -> None:
    comp = _Signal(id="comp-1", extraction_confidence=0.80)
    report = CriticAgent().critique(
        _Signal(), _Diff(), competitor_signals=[comp]
    )
    pressure = [f for f in report.findings if f.dimension == "competitor_pressure"]
    assert len(pressure) == 1
    assert pressure[0].severity == FindingSeverity.WARNING


def test_low_confidence_competitor_no_warning() -> None:
    comp = _Signal(id="comp-1", extraction_confidence=0.50)
    report = CriticAgent().critique(
        _Signal(), _Diff(), competitor_signals=[comp]
    )
    pressure = [f for f in report.findings if f.dimension == "competitor_pressure"]
    assert pressure == []


# ---------------------------------------------------------------------------
# Overall severity + ordering
# ---------------------------------------------------------------------------

def test_findings_ordered_caution_first() -> None:
    """CAUTION findings must appear before WARNING and INFO."""
    signal = _Signal(
        extraction_confidence=0.50,   # triggers confidence_sanity CAUTION
        trial_phase="phase_1",        # triggers phase_mismatch CAUTION
        signal_date=date.today() - timedelta(days=120),  # staleness WARNING
    )
    diff = _Diff(
        delta_npv=80.0,
        valuation_before={"rnpv_millions": 100.0},
    )
    report = CriticAgent().critique(signal, diff)
    severities = [f.severity for f in report.findings]
    caution_idx = max(
        (i for i, s in enumerate(severities) if s == FindingSeverity.CAUTION),
        default=-1,
    )
    warning_idx = min(
        (i for i, s in enumerate(severities) if s == FindingSeverity.WARNING),
        default=len(severities),
    )
    assert caution_idx < warning_idx, "CAUTION must come before WARNING"


def test_overall_severity_reflects_highest() -> None:
    signal = _Signal(extraction_confidence=0.50)
    diff = _Diff(delta_npv=80.0)
    report = CriticAgent().critique(signal, diff)
    assert report.overall_severity == FindingSeverity.CAUTION


def test_no_findings_overall_severity_none() -> None:
    signal = _Signal(
        extraction_confidence=0.95,
        primary_endpoint_met=True,
        signal_date=date.today(),
        trial_phase="phase_3",
    )
    diff = _Diff(delta_npv=10.0, valuation_before={"rnpv_millions": 100.0})
    report = CriticAgent().critique(signal, diff)
    assert report.overall_severity is None


# ---------------------------------------------------------------------------
# Advisory note
# ---------------------------------------------------------------------------

def test_advisory_note_populated_when_findings() -> None:
    signal = _Signal(extraction_confidence=0.50)
    diff = _Diff(delta_npv=80.0)
    report = CriticAgent().critique(signal, diff)
    assert report.advisory_note != "No material concerns identified."
    assert len(report.advisory_note) > 0


def test_advisory_note_clean_when_no_findings() -> None:
    signal = _Signal(
        extraction_confidence=0.95,
        primary_endpoint_met=True,
        signal_date=date.today(),
        trial_phase="phase_3",
    )
    diff = _Diff(delta_npv=10.0, valuation_before={"rnpv_millions": 100.0})
    report = CriticAgent().critique(signal, diff)
    assert report.advisory_note == "No material concerns identified."


# ---------------------------------------------------------------------------
# Custom config
# ---------------------------------------------------------------------------

def test_custom_config_thresholds() -> None:
    cfg = CriticConfig(
        high_delta_threshold_millions=10.0,
        min_confidence_for_high_delta=0.90,
    )
    signal = _Signal(extraction_confidence=0.85)
    diff = _Diff(delta_npv=15.0)
    report = CriticAgent(config=cfg).critique(signal, diff)
    cautions = [f for f in report.findings if f.dimension == "confidence_sanity"]
    assert len(cautions) == 1
