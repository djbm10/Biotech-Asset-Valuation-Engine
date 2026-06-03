"""Tests for Block 4C: synergy-aware gap suggester."""
from __future__ import annotations

import pytest

from bve.analysis.synergy_graph import SynergyAssetProfile, SynergyType
from bve.intelligence.synergy_gap_suggester import (
    SynergyGapReport,
    SynergyGapSuggestion,
    suggest_synergy_gaps,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def pd1_asset() -> SynergyAssetProfile:
    return SynergyAssetProfile(
        asset_id="pd1",
        therapeutic_area="oncology",
        signals=["pd1", "checkpoint", "pdl1"],
    )


@pytest.fixture
def ctla4_asset() -> SynergyAssetProfile:
    return SynergyAssetProfile(
        asset_id="ctla4",
        therapeutic_area="oncology",
        signals=["ctla4", "ipilimumab"],
    )


@pytest.fixture
def kras_asset() -> SynergyAssetProfile:
    return SynergyAssetProfile(
        asset_id="kras_g12c",
        therapeutic_area="oncology",
        signals=["kras", "kras_g12c"],
    )


@pytest.fixture
def glp1_asset() -> SynergyAssetProfile:
    return SynergyAssetProfile(
        asset_id="glp1",
        therapeutic_area="metabolic",
        signals=["glp1", "semaglutide", "obesity"],
    )


@pytest.fixture
def muscle_asset() -> SynergyAssetProfile:
    return SynergyAssetProfile(
        asset_id="bimagrumab",
        therapeutic_area="rare_disease",
        signals=["sarcopenia", "muscle_loss", "myostatin", "activin"],
    )


@pytest.fixture
def igan_asset() -> SynergyAssetProfile:
    return SynergyAssetProfile(
        asset_id="povetacicept",
        therapeutic_area="immunology",
        signals=["baff", "april", "igan", "iga_nephropathy"],
    )


# ── Empty / trivial portfolio ─────────────────────────────────────────────────

def test_empty_portfolio_produces_no_gaps() -> None:
    report = suggest_synergy_gaps([])
    assert report.suggestions == []
    assert report.current_synergy_score == 0.0


def test_single_asset_may_produce_gaps(pd1_asset) -> None:
    """A single PD-1 asset should suggest acquiring a CTLA-4 combo partner."""
    report = suggest_synergy_gaps([pd1_asset])
    assert len(report.suggestions) >= 1
    rule_ids = {s.rule_id for s in report.suggestions}
    assert "onc_pd1_ctla4_combo" in rule_ids


# ── Gap detection ─────────────────────────────────────────────────────────────

def test_pd1_portfolio_suggests_ctla4_gap(pd1_asset) -> None:
    report = suggest_synergy_gaps([pd1_asset])
    ctla4_gap = next(s for s in report.suggestions if s.rule_id == "onc_pd1_ctla4_combo")
    # Should flag ctla4-related signals as missing
    assert any("ctla4" in sig or "ipilimumab" in sig for sig in ctla4_gap.missing_signals)
    assert pd1_asset.asset_id in ctla4_gap.present_asset_ids


def test_glp1_portfolio_suggests_sarcopenia_gap(glp1_asset) -> None:
    """GLP-1 portfolio should suggest acquiring a muscle/sarcopenia asset."""
    report = suggest_synergy_gaps([glp1_asset])
    sarcopenia_gap = next(
        (s for s in report.suggestions if s.rule_id == "glp1_muscle_sarcopenia"), None
    )
    assert sarcopenia_gap is not None
    assert sarcopenia_gap.synergy_type == SynergyType.MARKET_CREATION
    assert any("sarcopenia" in sig or "muscle" in sig for sig in sarcopenia_gap.missing_signals)


def test_kras_portfolio_suggests_sos1_gap(kras_asset) -> None:
    report = suggest_synergy_gaps([kras_asset])
    kras_gap = next(
        (s for s in report.suggestions if s.rule_id == "onc_kras_sos1_combo"), None
    )
    assert kras_gap is not None
    assert kras_asset.asset_id in kras_gap.present_asset_ids


# ── No gap when both sides present ───────────────────────────────────────────

def test_no_gap_when_synergy_already_filled(pd1_asset, ctla4_asset) -> None:
    """When both sides of a rule are in the portfolio, no gap is reported."""
    report = suggest_synergy_gaps([pd1_asset, ctla4_asset])
    assert not any(s.rule_id == "onc_pd1_ctla4_combo" for s in report.suggestions)


def test_no_gap_glp1_muscle_when_both_present(glp1_asset, muscle_asset) -> None:
    report = suggest_synergy_gaps([glp1_asset, muscle_asset])
    assert not any(s.rule_id == "glp1_muscle_sarcopenia" for s in report.suggestions)


# ── Report structure ─────────────────────────────────────────────────────────

def test_report_is_sorted_descending(pd1_asset, kras_asset, igan_asset) -> None:
    report = suggest_synergy_gaps([pd1_asset, kras_asset, igan_asset])
    scores = [s.gap_score for s in report.suggestions]
    assert scores == sorted(scores, reverse=True)


def test_report_structure_fields(pd1_asset) -> None:
    report = suggest_synergy_gaps([pd1_asset])
    assert isinstance(report, SynergyGapReport)
    assert report.portfolio_asset_ids == [pd1_asset.asset_id]
    assert isinstance(report.current_synergy_score, (int, float))
    assert isinstance(report.covered_synergy_types, list)
    assert isinstance(report.uncovered_synergy_types, list)
    assert isinstance(report.suggestions, list)


def test_suggestion_structure(pd1_asset) -> None:
    report = suggest_synergy_gaps([pd1_asset])
    assert report.suggestions
    s = report.suggestions[0]
    assert isinstance(s, SynergyGapSuggestion)
    assert 0.0 < s.gap_score <= 1.0
    assert s.present_asset_ids
    assert s.missing_signals
    assert s.description


def test_top_suggestions_at_most_5(pd1_asset, kras_asset, igan_asset, glp1_asset) -> None:
    report = suggest_synergy_gaps([pd1_asset, kras_asset, igan_asset, glp1_asset])
    assert len(report.top_suggestions) <= 5


# ── Coverage summary ─────────────────────────────────────────────────────────

def test_covered_types_populated_when_synergy_exists(pd1_asset, ctla4_asset) -> None:
    report = suggest_synergy_gaps([pd1_asset, ctla4_asset])
    assert SynergyType.COMBINATION_THERAPY.value in report.covered_synergy_types


def test_no_covered_types_for_empty_portfolio() -> None:
    report = suggest_synergy_gaps([])
    assert report.covered_synergy_types == []


# ── Gap score bounds ─────────────────────────────────────────────────────────

def test_gap_scores_bounded_0_1(pd1_asset, kras_asset, glp1_asset, igan_asset) -> None:
    report = suggest_synergy_gaps([pd1_asset, kras_asset, glp1_asset, igan_asset])
    for s in report.suggestions:
        assert 0.0 < s.gap_score <= 1.0


def test_min_gap_score_filter() -> None:
    """High min_gap_score should suppress low-value suggestions."""
    report_all = suggest_synergy_gaps(
        [SynergyAssetProfile(asset_id="pd1", signals=["pd1", "checkpoint"])],
        min_gap_score=0.0,
    )
    report_strict = suggest_synergy_gaps(
        [SynergyAssetProfile(asset_id="pd1", signals=["pd1", "checkpoint"])],
        min_gap_score=0.9,
    )
    assert len(report_strict.suggestions) <= len(report_all.suggestions)
