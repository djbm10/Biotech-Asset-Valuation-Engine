"""Tests for the portfolio synergy graph (Block 4A)."""
from __future__ import annotations

import pytest

from bve.analysis.synergy_graph import (
    PortfolioSynergyResult,
    SynergyAssetProfile,
    SynergyEdge,
    SynergyGraph,
    SynergyType,
    score_acquirer_portfolio_fit,
    score_portfolio_synergy,
)


# ── Helper fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def glp1_asset() -> SynergyAssetProfile:
    return SynergyAssetProfile(
        asset_id="glp1",
        indication="obesity type-2 diabetes",
        therapeutic_area="metabolic",
        mechanism_of_action="GLP-1 receptor agonist",
        signals=["glp-1", "semaglutide", "obesity", "weight_loss"],
    )


@pytest.fixture
def muscle_asset() -> SynergyAssetProfile:
    return SynergyAssetProfile(
        asset_id="bimagrumab",
        indication="sarcopenia muscle atrophy",
        therapeutic_area="rare_disease",
        signals=["sarcopenia", "muscle_loss", "myostatin", "activin"],
    )


@pytest.fixture
def pd1_asset() -> SynergyAssetProfile:
    return SynergyAssetProfile(
        asset_id="pd1",
        indication="non-small cell lung cancer",
        therapeutic_area="oncology",
        target="pd-1",
        signals=["pd1", "checkpoint", "pdl1"],
    )


@pytest.fixture
def ctla4_asset() -> SynergyAssetProfile:
    return SynergyAssetProfile(
        asset_id="ctla4",
        indication="melanoma",
        therapeutic_area="oncology",
        target="ctla-4",
        signals=["ctla4", "ipilimumab"],
    )


@pytest.fixture
def kras_asset() -> SynergyAssetProfile:
    return SynergyAssetProfile(
        asset_id="kras_g12c",
        indication="KRAS G12C NSCLC",
        therapeutic_area="oncology",
        target="KRAS G12C",
        signals=["kras", "kras_g12c", "kras_beyond_g12c"],
    )


@pytest.fixture
def sos1_asset() -> SynergyAssetProfile:
    return SynergyAssetProfile(
        asset_id="sos1",
        indication="KRAS-driven cancers",
        therapeutic_area="oncology",
        target="SOS1",
        signals=["sos1", "ras_pathway", "mek"],
    )


# ── SynergyGraph.find_synergies ──────────────────────────────────────────────

def test_glp1_muscle_synergy_detected(glp1_asset, muscle_asset) -> None:
    """GLP-1 + muscle loss prevention is a canonical synergy the user mentioned."""
    graph = SynergyGraph.from_rules()
    edges = graph.find_synergies([glp1_asset, muscle_asset])
    assert len(edges) >= 1
    types = {e.synergy_type for e in edges}
    assert SynergyType.MARKET_CREATION in types


def test_pd1_ctla4_synergy_detected(pd1_asset, ctla4_asset) -> None:
    """PD-1 + CTLA-4 combination is the canonical validated oncology combo."""
    graph = SynergyGraph.from_rules()
    edges = graph.find_synergies([pd1_asset, ctla4_asset])
    assert len(edges) >= 1
    assert any(e.synergy_type == SynergyType.COMBINATION_THERAPY for e in edges)
    # Score should be reasonably high for a validated combo
    assert max(e.score for e in edges) >= 0.5


def test_kras_sos1_synergy_detected(kras_asset, sos1_asset) -> None:
    """KRAS + SOS1 vertical pathway combination."""
    graph = SynergyGraph.from_rules()
    edges = graph.find_synergies([kras_asset, sos1_asset])
    assert len(edges) >= 1
    assert any(e.synergy_type == SynergyType.COMBINATION_THERAPY for e in edges)


def test_unrelated_assets_no_synergy() -> None:
    """Two completely unrelated assets should produce no synergy edges."""
    asset_a = SynergyAssetProfile(
        asset_id="arbitrary_antifungal",
        indication="candida infection",
        therapeutic_area="infectious disease",
        signals=["antifungal", "candida", "azole"],
    )
    asset_b = SynergyAssetProfile(
        asset_id="nav18_pain",
        indication="acute pain",
        therapeutic_area="rare_disease",
        signals=["nav1.8", "suzetrigine", "pain"],
    )
    graph = SynergyGraph.from_rules()
    edges = graph.find_synergies([asset_a, asset_b])
    assert len(edges) == 0


def test_find_synergies_sorted_descending(glp1_asset, muscle_asset, pd1_asset, ctla4_asset) -> None:
    """Edges should be sorted by score descending."""
    graph = SynergyGraph.from_rules()
    edges = graph.find_synergies([glp1_asset, muscle_asset, pd1_asset, ctla4_asset])
    scores = [e.score for e in edges]
    assert scores == sorted(scores, reverse=True)


def test_no_self_synergy(pd1_asset) -> None:
    """An asset does not generate a synergy edge with itself."""
    graph = SynergyGraph.from_rules()
    edges = graph.find_synergies([pd1_asset])
    assert len(edges) == 0


def test_find_synergies_no_duplicates(pd1_asset, ctla4_asset) -> None:
    """Each asset pair should appear at most once."""
    graph = SynergyGraph.from_rules()
    edges = graph.find_synergies([pd1_asset, ctla4_asset, pd1_asset])
    pair_keys = [frozenset({e.asset_id_a, e.asset_id_b}) for e in edges]
    assert len(pair_keys) == len(set(pair_keys))


# ── score_pair ───────────────────────────────────────────────────────────────

def test_score_pair_returns_positive(pd1_asset, ctla4_asset) -> None:
    graph = SynergyGraph.from_rules()
    score = graph.score_pair(pd1_asset, ctla4_asset)
    assert score > 0.0


def test_score_pair_unrelated_is_zero() -> None:
    graph = SynergyGraph.from_rules()
    a = SynergyAssetProfile(asset_id="x", signals=["antifungal"])
    b = SynergyAssetProfile(asset_id="y", signals=["suzetrigine"])
    assert graph.score_pair(a, b) == 0.0


def test_score_pair_bounded_0_1(glp1_asset, muscle_asset, pd1_asset, ctla4_asset) -> None:
    graph = SynergyGraph.from_rules()
    for a, b in [(glp1_asset, muscle_asset), (pd1_asset, ctla4_asset)]:
        score = graph.score_pair(a, b)
        assert 0.0 <= score <= 1.0


# ── score_portfolio_synergy ──────────────────────────────────────────────────

def test_portfolio_score_higher_with_synergistic_assets(
    glp1_asset, muscle_asset, pd1_asset, ctla4_asset
) -> None:
    """A portfolio with synergistic assets should score higher than one without."""
    synergistic = score_portfolio_synergy([glp1_asset, muscle_asset])
    unrelated = score_portfolio_synergy([
        SynergyAssetProfile(asset_id="anti_fungal", signals=["antifungal"]),
        SynergyAssetProfile(asset_id="nav_pain", signals=["suzetrigine"]),
    ])
    assert synergistic.total_synergy_score > unrelated.total_synergy_score


def test_portfolio_result_structure(glp1_asset, muscle_asset, pd1_asset, ctla4_asset) -> None:
    result = score_portfolio_synergy([glp1_asset, muscle_asset, pd1_asset, ctla4_asset])
    assert isinstance(result, PortfolioSynergyResult)
    assert result.n_synergy_pairs == len(result.edges)
    assert len(result.top_pairs) <= 5
    assert result.total_synergy_score >= 0.0


# ── score_acquirer_portfolio_fit ─────────────────────────────────────────────

def test_acquirer_fit_synergy_pd1_portfolio(ctla4_asset, kras_asset, sos1_asset) -> None:
    """A PD-1 candidate should score synergy against an oncology portfolio."""
    candidate = SynergyAssetProfile(
        asset_id="pd1_candidate",
        indication="NSCLC",
        therapeutic_area="oncology",
        signals=["pd1", "checkpoint"],
    )
    portfolio = [ctla4_asset, kras_asset, sos1_asset]
    total_score, edges = score_acquirer_portfolio_fit(candidate, portfolio)
    assert total_score > 0.0
    assert len(edges) >= 1


def test_acquirer_fit_synergy_empty_portfolio() -> None:
    """Empty portfolio produces zero synergy."""
    candidate = SynergyAssetProfile(asset_id="any", signals=["pd1"])
    total_score, edges = score_acquirer_portfolio_fit(candidate, [])
    assert total_score == 0.0
    assert edges == []


def test_acquirer_fit_synergy_capped_at_3(
    glp1_asset, muscle_asset, pd1_asset, ctla4_asset, kras_asset, sos1_asset
) -> None:
    """Total portfolio fit score is capped at 3.0."""
    candidate = SynergyAssetProfile(
        asset_id="pd1_candidate",
        signals=["pd1", "checkpoint", "pdl1", "ctla4", "kras", "sos1"],
    )
    portfolio = [glp1_asset, muscle_asset, pd1_asset, ctla4_asset, kras_asset, sos1_asset]
    total_score, _ = score_acquirer_portfolio_fit(candidate, portfolio)
    assert total_score <= 3.0


# ── SynergyEdge data integrity ───────────────────────────────────────────────

def test_synergy_edge_has_evidence(pd1_asset, ctla4_asset) -> None:
    """Rules with known clinical evidence should populate the evidence field."""
    graph = SynergyGraph.from_rules()
    edges = graph.find_synergies([pd1_asset, ctla4_asset])
    assert any(e.evidence for e in edges)


def test_synergy_edge_matched_signals_populated(glp1_asset, muscle_asset) -> None:
    """Matched signals should be populated for debugging traceability."""
    graph = SynergyGraph.from_rules()
    edges = graph.find_synergies([glp1_asset, muscle_asset])
    assert any(e.asset_a_matched_signals or e.asset_b_matched_signals for e in edges)
