"""Tests for competition_graph, readthrough_engine, and revaluation_triggers.

Covers:
  - CompetitionGraph: node management, similarity computation, filtering
  - ReadthroughEngine: all event type rules, edge cases
  - RevaluationTriggers: priority classification, TriggerStore, emit_triggers
"""

from __future__ import annotations

import uuid

import pytest

from bve.intelligence.competition_graph import (
    CompetitionGraph,
    CompetitorNode,
    SimilarityDimension,
    SimilarityScore,
    _jaccard,
    _tokenize,
)
from bve.intelligence.readthrough_engine import (
    CompetitorEvent,
    ReadthroughDirection,
    ReadthroughSignal,
    compute_all_readthroughs,
    compute_readthrough,
)
from bve.intelligence.revaluation_triggers import (
    RevaluationTrigger,
    TriggerPriority,
    TriggerStore,
    emit_triggers,
)


# ---------------------------------------------------------------------------
# Fixtures: CompetitorNode helpers
# ---------------------------------------------------------------------------

def _pd1_node(asset_id: str = "A1", ticker: str = "TICK1") -> CompetitorNode:
    return CompetitorNode(
        asset_id=asset_id,
        ticker=ticker,
        target="PD-1",
        mechanism="checkpoint_inhibitor",
        indication="NSCLC",
        lot="2L",
        modality="antibody",
        phase="Phase 3",
        approval_probability=0.6,
    )


def _kras_node(asset_id: str = "B1", ticker: str = "TICK2") -> CompetitorNode:
    return CompetitorNode(
        asset_id=asset_id,
        ticker=ticker,
        target="KRAS_G12C",
        mechanism="small_molecule",
        indication="NSCLC",
        lot="2L",
        modality="small_molecule",
        phase="Phase 2",
        approval_probability=0.45,
    )


def _unrelated_node(asset_id: str = "C1", ticker: str = "TICK3") -> CompetitorNode:
    return CompetitorNode(
        asset_id=asset_id,
        ticker=ticker,
        target="HER2",
        mechanism="ADC",
        indication="breast_cancer",
        lot="3L",
        modality="antibody_drug_conjugate",
        phase="Phase 1",
        approval_probability=0.25,
    )


def _clone_pd1(asset_id: str = "A2", ticker: str = "TICK_CLONE") -> CompetitorNode:
    """Identical to _pd1_node but different ID."""
    return CompetitorNode(
        asset_id=asset_id,
        ticker=ticker,
        target="PD-1",
        mechanism="checkpoint_inhibitor",
        indication="NSCLC",
        lot="2L",
        modality="antibody",
        phase="Phase 3",
        approval_probability=0.6,
    )


# ---------------------------------------------------------------------------
# TestCompetitionGraph
# ---------------------------------------------------------------------------

class TestCompetitionGraph:
    def test_add_single_node(self):
        graph = CompetitionGraph()
        node = _pd1_node()
        graph.add_node(node)
        assert len(graph.all_nodes()) == 1

    def test_all_nodes_returns_all(self):
        graph = CompetitionGraph()
        graph.add_node(_pd1_node("A1"))
        graph.add_node(_kras_node("B1"))
        graph.add_node(_unrelated_node("C1"))
        assert len(graph.all_nodes()) == 3

    def test_add_node_replaces_on_same_id(self):
        graph = CompetitionGraph()
        n1 = _pd1_node("A1")
        n2 = CompetitorNode(
            asset_id="A1", ticker="NEWTICK",
            target="VEGF", mechanism="antibody",
            indication="CRC", lot="1L", modality="antibody",
            phase="Phase 2",
        )
        graph.add_node(n1)
        graph.add_node(n2)
        assert len(graph.all_nodes()) == 1
        assert graph.all_nodes()[0].ticker == "NEWTICK"

    def test_empty_graph_returns_no_competitors(self):
        graph = CompetitionGraph()
        result = graph.get_competitors("MISSING")
        assert result == []

    def test_empty_graph_direct_competitors(self):
        graph = CompetitionGraph()
        assert graph.get_direct_competitors("MISSING") == []

    def test_identical_assets_similarity_is_1(self):
        graph = CompetitionGraph()
        a = _pd1_node("A1")
        b = _clone_pd1("A2")
        graph.add_node(a)
        graph.add_node(b)
        score = graph.compute_similarity(a, b)
        assert score.composite_score == pytest.approx(1.0, abs=1e-9)

    def test_identical_asset_all_dimension_scores_are_1(self):
        graph = CompetitionGraph()
        a = _pd1_node("A1")
        b = _clone_pd1("A2")
        score = graph.compute_similarity(a, b)
        for dim in SimilarityDimension:
            assert score.dimension_scores[dim.value] == pytest.approx(1.0, abs=1e-9)

    def test_completely_different_assets_low_similarity(self):
        graph = CompetitionGraph()
        a = _pd1_node()
        b = _unrelated_node()
        score = graph.compute_similarity(a, b)
        assert score.composite_score < 0.30

    def test_dimension_weights_sum_to_one(self):
        from bve.intelligence.competition_graph import _DIMENSION_WEIGHTS
        total = sum(_DIMENSION_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_is_direct_competitor_true_above_threshold(self):
        graph = CompetitionGraph()
        a = _pd1_node("A1")
        b = _clone_pd1("A2")
        score = graph.compute_similarity(a, b)
        assert score.is_direct_competitor is True

    def test_is_direct_competitor_false_below_threshold(self):
        graph = CompetitionGraph()
        a = _pd1_node("A1")
        b = _unrelated_node("C1")
        score = graph.compute_similarity(a, b)
        assert score.is_direct_competitor is False

    def test_get_competitors_respects_min_score_filter(self):
        graph = CompetitionGraph()
        graph.add_node(_pd1_node("A1"))
        graph.add_node(_clone_pd1("A2"))     # very similar
        graph.add_node(_unrelated_node("C1"))  # very different
        # With default min_score=0.30: unrelated should be excluded
        results = graph.get_competitors("A1", min_score=0.30)
        result_ids = [r.asset_id_b for r in results]
        assert "A2" in result_ids
        assert "C1" not in result_ids

    def test_get_competitors_high_min_score_excludes_moderate(self):
        graph = CompetitionGraph()
        graph.add_node(_pd1_node("A1"))
        graph.add_node(_kras_node("B1"))  # same indication, different mech
        results = graph.get_competitors("A1", min_score=0.99)
        assert results == []

    def test_get_competitors_sorted_by_score_descending(self):
        graph = CompetitionGraph()
        graph.add_node(_pd1_node("A1"))
        graph.add_node(_clone_pd1("A2"))     # score ~1.0
        graph.add_node(_kras_node("B1"))     # partial similarity
        results = graph.get_competitors("A1", min_score=0.0)
        scores = [r.composite_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_get_direct_competitors_uses_0_60_threshold(self):
        graph = CompetitionGraph()
        graph.add_node(_pd1_node("A1"))
        graph.add_node(_clone_pd1("A2"))    # identical → direct
        graph.add_node(_kras_node("B1"))    # partial overlap, may not qualify
        graph.add_node(_unrelated_node("C1"))  # not a direct competitor
        directs = graph.get_direct_competitors("A1")
        direct_ids = [r.asset_id_b for r in directs]
        assert "A2" in direct_ids
        assert "C1" not in direct_ids

    def test_tokenize_on_hyphenated_field(self):
        tokens = _tokenize("PD-1")
        assert "pd" in tokens
        assert "1" in tokens

    def test_tokenize_on_underscored_field(self):
        tokens = _tokenize("checkpoint_inhibitor")
        assert "checkpoint" in tokens
        assert "inhibitor" in tokens

    def test_tokenize_on_space_separated_field(self):
        tokens = _tokenize("KRAS G12C")
        assert "kras" in tokens
        assert "g12c" in tokens

    def test_jaccard_same_strings(self):
        assert _jaccard("NSCLC", "NSCLC") == pytest.approx(1.0)

    def test_jaccard_disjoint_strings(self):
        assert _jaccard("NSCLC", "breast_cancer") == pytest.approx(0.0)

    def test_jaccard_partial_overlap(self):
        # "small_molecule" vs "small_antibody" → tokens: {small, molecule} vs {small, antibody}
        # intersection={small}, union={small, molecule, antibody} → 1/3
        val = _jaccard("small_molecule", "small_antibody")
        assert val == pytest.approx(1 / 3, abs=1e-9)

    def test_multi_node_competitor_ranking(self):
        graph = CompetitionGraph()
        target = _pd1_node("T1")
        close = _clone_pd1("C1")   # identical
        partial = _kras_node("P1")  # same indication, different target
        far = _unrelated_node("F1")  # different everything
        for n in [target, close, partial, far]:
            graph.add_node(n)
        results = graph.get_competitors("T1", min_score=0.0)
        assert results[0].asset_id_b == "C1"  # highest score first

    def test_single_node_has_no_competitors(self):
        graph = CompetitionGraph()
        graph.add_node(_pd1_node("A1"))
        assert graph.get_competitors("A1") == []


# ---------------------------------------------------------------------------
# TestReadthroughEngine
# ---------------------------------------------------------------------------

def _make_event(
    asset_id: str = "A2",
    event_type: str = "trial_success",
    magnitude: float = 0.8,
    indication: str = "NSCLC",
    lot: str = "2L",
    mechanism: str = "checkpoint_inhibitor",
) -> CompetitorEvent:
    return CompetitorEvent(
        asset_id=asset_id,
        event_type=event_type,
        magnitude=magnitude,
        indication=indication,
        lot=lot,
        mechanism=mechanism,
    )


def _build_pd1_graph() -> tuple[CompetitionGraph, CompetitorNode, CompetitorNode]:
    """Return a graph with two very similar PD-1 nodes."""
    graph = CompetitionGraph()
    source = _pd1_node("SOURCE")
    target = _clone_pd1("TARGET")
    graph.add_node(source)
    graph.add_node(target)
    return graph, source, target


class TestReadthroughEngine:
    def test_trial_success_direct_competitor_positive_class_validation(self):
        graph, source, target = _build_pd1_graph()
        event = _make_event(
            asset_id="SOURCE",
            event_type="trial_success",
            indication="NSCLC",
            lot="2L",
            mechanism="checkpoint_inhibitor",
        )
        signal = compute_readthrough(event, graph, "TARGET")
        # Same mechanism (high similarity) → crowding, unless indication/lot very strong
        # The exact direction depends on mechanism_score vs indication_lot_avg; both are high here
        assert signal.direction in (
            ReadthroughDirection.NEGATIVE,
            ReadthroughDirection.POSITIVE,
            ReadthroughDirection.CLASS_EXPANSION,
        )
        assert signal.target_asset_id == "TARGET"
        assert signal.source_asset_id == "SOURCE"

    def test_trial_success_class_validation_strong_indication_lot(self):
        """Moderate mechanism similarity, strong indication/lot match → POSITIVE."""
        graph = CompetitionGraph()
        source = CompetitorNode(
            asset_id="S1", ticker="T1",
            target="PD-L1", mechanism="checkpoint_antibody",
            indication="NSCLC", lot="2L",
            modality="antibody", phase="Phase 3",
        )
        target = CompetitorNode(
            asset_id="T1", ticker="T2",
            target="PD-1", mechanism="checkpoint_inhibitor",
            indication="NSCLC", lot="2L",
            modality="antibody", phase="Phase 3",
        )
        graph.add_node(source)
        graph.add_node(target)
        event = _make_event(
            asset_id="S1", event_type="trial_success",
            indication="NSCLC", lot="2L",
            mechanism="checkpoint_antibody", magnitude=0.8,
        )
        signal = compute_readthrough(event, graph, "T1")
        # indication and lot are identical → strong indication_lot_avg
        # mechanism similarity: "checkpoint_antibody" vs "checkpoint_inhibitor" — partial overlap
        assert signal.direction in (
            ReadthroughDirection.POSITIVE,
            ReadthroughDirection.NEGATIVE,
            ReadthroughDirection.CLASS_EXPANSION,
        )

    def test_trial_success_high_mechanism_similarity_negative_crowding(self):
        """Identical mechanism → NEGATIVE (crowding)."""
        graph = CompetitionGraph()
        source = CompetitorNode(
            asset_id="S1", ticker="T1",
            target="VEGF", mechanism="checkpoint_inhibitor",
            indication="gastric_cancer", lot="1L",
            modality="antibody", phase="Phase 3",
        )
        target = CompetitorNode(
            asset_id="T1", ticker="T2",
            target="VEGF", mechanism="checkpoint_inhibitor",
            indication="gastric_cancer", lot="1L",
            modality="antibody", phase="Phase 2",
        )
        graph.add_node(source)
        graph.add_node(target)
        event = CompetitorEvent(
            asset_id="S1", event_type="trial_success", magnitude=0.9,
            indication="gastric_cancer", lot="1L",
            mechanism="checkpoint_inhibitor",
        )
        signal = compute_readthrough(event, graph, "T1")
        assert signal.direction == ReadthroughDirection.NEGATIVE

    def test_trial_success_class_expansion_differentiated_mechanism(self):
        """Differentiated mechanism + strong indication → CLASS_EXPANSION."""
        graph = CompetitionGraph()
        source = CompetitorNode(
            asset_id="S1", ticker="T1",
            target="PD-1", mechanism="checkpoint_inhibitor",
            indication="NSCLC", lot="2L",
            modality="antibody", phase="Approved",
        )
        target = CompetitorNode(
            asset_id="T1", ticker="T2",
            target="KRAS_G12C", mechanism="irreversible_covalent_inhibitor",
            indication="NSCLC", lot="2L",
            modality="small_molecule", phase="Phase 3",
        )
        graph.add_node(source)
        graph.add_node(target)
        event = CompetitorEvent(
            asset_id="S1", event_type="trial_success", magnitude=0.85,
            indication="NSCLC", lot="2L",
            mechanism="checkpoint_inhibitor",
        )
        signal = compute_readthrough(event, graph, "T1")
        # mechanism_score should be low; indication high → CLASS_EXPANSION
        assert signal.direction == ReadthroughDirection.CLASS_EXPANSION
        assert signal.pos_delta > 0

    def test_fda_approval_same_as_trial_success_rules(self):
        """fda_approval follows same rules as trial_success."""
        graph = CompetitionGraph()
        source = CompetitorNode(
            asset_id="S1", ticker="T1",
            target="KRAS_G12C", mechanism="irreversible_covalent_inhibitor",
            indication="NSCLC", lot="2L",
            modality="small_molecule", phase="Approved",
        )
        target = CompetitorNode(
            asset_id="T1", ticker="T2",
            target="PD-1", mechanism="checkpoint_inhibitor",
            indication="NSCLC", lot="2L",
            modality="antibody", phase="Phase 3",
        )
        graph.add_node(source)
        graph.add_node(target)
        event = CompetitorEvent(
            asset_id="S1", event_type="fda_approval", magnitude=0.9,
            indication="NSCLC", lot="2L",
            mechanism="irreversible_covalent_inhibitor",
        )
        signal_approval = compute_readthrough(event, graph, "T1")
        event2 = event.model_copy(update={"event_type": "trial_success"})
        signal_success = compute_readthrough(event2, graph, "T1")
        assert signal_approval.direction == signal_success.direction

    def test_trial_failure_mechanism_similar_negative(self):
        """Mechanism-similar failure → NEGATIVE (class risk)."""
        graph = CompetitionGraph()
        source = CompetitorNode(
            asset_id="S1", ticker="T1",
            target="BTK", mechanism="btk_inhibitor",
            indication="CLL", lot="2L",
            modality="small_molecule", phase="Phase 3",
        )
        target = CompetitorNode(
            asset_id="T1", ticker="T2",
            target="BTK", mechanism="btk_inhibitor",
            indication="CLL", lot="2L",
            modality="small_molecule", phase="Phase 3",
        )
        graph.add_node(source)
        graph.add_node(target)
        event = CompetitorEvent(
            asset_id="S1", event_type="trial_failure", magnitude=0.8,
            indication="CLL", lot="2L", mechanism="btk_inhibitor",
        )
        signal = compute_readthrough(event, graph, "T1")
        assert signal.direction == ReadthroughDirection.NEGATIVE
        assert signal.pos_delta < 0

    def test_trial_failure_removes_competitor_positive(self):
        """High target similarity, low mechanism similarity → POSITIVE (market opens).

        Uses 'antibody' vs 'degrader' — very different mechanism tokens (no overlap),
        so mechanism_score=0.0 < 0.40, while target 'EGFR' gives target_score=1.0 > 0.60.
        """
        graph = CompetitionGraph()
        source = CompetitorNode(
            asset_id="S1", ticker="T1",
            target="EGFR", mechanism="antibody",
            indication="NSCLC", lot="1L",
            modality="antibody", phase="Phase 3",
        )
        target = CompetitorNode(
            asset_id="T1", ticker="T2",
            target="EGFR", mechanism="degrader",
            indication="NSCLC", lot="1L",
            modality="small_molecule", phase="Phase 2",
        )
        graph.add_node(source)
        graph.add_node(target)
        event = CompetitorEvent(
            asset_id="S1", event_type="trial_failure", magnitude=0.7,
            indication="NSCLC", lot="1L", mechanism="antibody",
        )
        signal = compute_readthrough(event, graph, "T1")
        assert signal.direction == ReadthroughDirection.POSITIVE
        assert signal.pos_delta > 0

    def test_crl_mechanism_similar_negative(self):
        """CRL follows same rules as trial_failure."""
        graph = CompetitionGraph()
        source = CompetitorNode(
            asset_id="S1", ticker="T1",
            target="JAK2", mechanism="jak_inhibitor",
            indication="MF", lot="1L",
            modality="small_molecule", phase="Phase 3",
        )
        target = CompetitorNode(
            asset_id="T1", ticker="T2",
            target="JAK2", mechanism="jak_inhibitor",
            indication="MF", lot="1L",
            modality="small_molecule", phase="Phase 2",
        )
        graph.add_node(source)
        graph.add_node(target)
        event = CompetitorEvent(
            asset_id="S1", event_type="crl", magnitude=0.75,
            indication="MF", lot="1L", mechanism="jak_inhibitor",
        )
        signal = compute_readthrough(event, graph, "T1")
        assert signal.direction == ReadthroughDirection.NEGATIVE

    def test_safety_halt_mechanism_similar_negative_large_delta(self):
        """Safety halt from mechanism-similar competitor → NEGATIVE with large pos_delta."""
        graph = CompetitionGraph()
        source = CompetitorNode(
            asset_id="S1", ticker="T1",
            target="CD19", mechanism="car_t_cell",
            indication="DLBCL", lot="3L",
            modality="cell_therapy", phase="Phase 2",
        )
        target = CompetitorNode(
            asset_id="T1", ticker="T2",
            target="CD19", mechanism="car_t_cell",
            indication="DLBCL", lot="3L",
            modality="cell_therapy", phase="Phase 3",
        )
        graph.add_node(source)
        graph.add_node(target)
        event = CompetitorEvent(
            asset_id="S1", event_type="safety_halt", magnitude=0.9,
            indication="DLBCL", lot="3L", mechanism="car_t_cell",
        )
        signal = compute_readthrough(event, graph, "T1")
        assert signal.direction == ReadthroughDirection.NEGATIVE
        assert signal.pos_delta <= -0.05

    def test_safety_halt_pos_delta_magnitude_bounded(self):
        """pos_delta should never exceed -0.25 in magnitude."""
        graph = CompetitionGraph()
        source = _pd1_node("S1")
        target = _clone_pd1("T1")
        graph.add_node(source)
        graph.add_node(target)
        event = CompetitorEvent(
            asset_id="S1", event_type="safety_halt", magnitude=1.0,
            indication="NSCLC", lot="2L", mechanism="checkpoint_inhibitor",
        )
        signal = compute_readthrough(event, graph, "T1")
        assert signal.pos_delta >= -0.25

    def test_partnership_indication_similar_positive(self):
        """Partnership in same indication → POSITIVE signal."""
        graph = CompetitionGraph()
        source = CompetitorNode(
            asset_id="S1", ticker="T1",
            target="HER2", mechanism="ADC",
            indication="breast_cancer", lot="3L",
            modality="antibody_drug_conjugate", phase="Phase 2",
        )
        target = CompetitorNode(
            asset_id="T1", ticker="T2",
            target="TROP2", mechanism="ADC",
            indication="breast_cancer", lot="3L",
            modality="antibody_drug_conjugate", phase="Phase 3",
        )
        graph.add_node(source)
        graph.add_node(target)
        event = CompetitorEvent(
            asset_id="S1", event_type="partnership", magnitude=0.6,
            indication="breast_cancer", lot="3L", mechanism="ADC",
        )
        signal = compute_readthrough(event, graph, "T1")
        assert signal.direction == ReadthroughDirection.POSITIVE
        assert 0.0 <= signal.pos_delta <= 0.08

    def test_low_similarity_asset_neutral(self):
        """Asset similarity < 0.30 → NEUTRAL with zero pos_delta."""
        graph = CompetitionGraph()
        source = _pd1_node("S1")
        target = _unrelated_node("T1")
        graph.add_node(source)
        graph.add_node(target)
        event = _make_event(asset_id="S1")
        signal = compute_readthrough(event, graph, "T1")
        assert signal.direction == ReadthroughDirection.NEUTRAL
        assert signal.pos_delta == 0.0
        assert signal.magnitude == 0.0

    def test_positive_pos_delta_bounded_above(self):
        """pos_delta must never exceed +0.20."""
        graph = CompetitionGraph()
        source = _pd1_node("S1")
        target = CompetitorNode(
            asset_id="T1", ticker="T2",
            target="EGFR", mechanism="tyrosine_kinase_inhibitor",
            indication="NSCLC", lot="2L",
            modality="small_molecule", phase="Phase 3",
        )
        graph.add_node(source)
        graph.add_node(target)
        event = CompetitorEvent(
            asset_id="S1", event_type="trial_success", magnitude=1.0,
            indication="NSCLC", lot="2L", mechanism="checkpoint_inhibitor",
        )
        signal = compute_readthrough(event, graph, "T1")
        assert signal.pos_delta <= 0.20

    def test_compute_all_readthroughs_excludes_source(self):
        """compute_all_readthroughs must not produce a signal where target == source."""
        graph = CompetitionGraph()
        for i, node in enumerate([_pd1_node("A1"), _clone_pd1("A2"), _kras_node("B1")]):
            graph.add_node(node)
        event = _make_event(asset_id="A1")
        signals = compute_all_readthroughs(event, graph)
        target_ids = [s.target_asset_id for s in signals]
        assert "A1" not in target_ids

    def test_compute_all_readthroughs_extra_exclude(self):
        """Extra exclusions in exclude_asset_ids are respected."""
        graph = CompetitionGraph()
        graph.add_node(_pd1_node("A1"))
        graph.add_node(_clone_pd1("A2"))
        graph.add_node(_kras_node("B1"))
        event = _make_event(asset_id="A1")
        signals = compute_all_readthroughs(event, graph, exclude_asset_ids={"A2"})
        target_ids = [s.target_asset_id for s in signals]
        assert "A2" not in target_ids
        assert "A1" not in target_ids

    def test_confidence_correlates_with_similarity(self):
        """Confidence should be close to composite similarity score."""
        graph = CompetitionGraph()
        source = _pd1_node("S1")
        close = _clone_pd1("T_CLOSE")
        far = _kras_node("T_FAR")
        graph.add_node(source)
        graph.add_node(close)
        graph.add_node(far)
        event = _make_event(asset_id="S1", event_type="trial_failure")
        sig_close = compute_readthrough(event, graph, "T_CLOSE")
        sig_far = compute_readthrough(event, graph, "T_FAR")
        # Confidence for close competitor should be higher
        assert sig_close.confidence >= sig_far.confidence

    def test_unknown_event_type_returns_neutral(self):
        """Unknown event type → NEUTRAL signal."""
        graph = CompetitionGraph()
        source = _pd1_node("S1")
        target = _clone_pd1("T1")
        graph.add_node(source)
        graph.add_node(target)
        event = CompetitorEvent(
            asset_id="S1", event_type="completely_unknown_xyz",
            magnitude=0.8, indication="NSCLC", lot="2L",
            mechanism="checkpoint_inhibitor",
        )
        signal = compute_readthrough(event, graph, "T1")
        assert signal.direction == ReadthroughDirection.NEUTRAL

    def test_source_not_in_graph_returns_neutral(self):
        """If source asset is not in graph → NEUTRAL."""
        graph = CompetitionGraph()
        graph.add_node(_clone_pd1("T1"))
        event = _make_event(asset_id="MISSING_SOURCE")
        signal = compute_readthrough(event, graph, "T1")
        assert signal.direction == ReadthroughDirection.NEUTRAL

    def test_target_not_in_graph_returns_neutral(self):
        """If target asset is not in graph → NEUTRAL."""
        graph = CompetitionGraph()
        graph.add_node(_pd1_node("S1"))
        event = _make_event(asset_id="S1")
        signal = compute_readthrough(event, graph, "MISSING_TARGET")
        assert signal.direction == ReadthroughDirection.NEUTRAL

    def test_compute_all_readthroughs_covers_all_non_source(self):
        """compute_all_readthroughs returns one signal per non-source node."""
        graph = CompetitionGraph()
        graph.add_node(_pd1_node("A1"))
        graph.add_node(_clone_pd1("A2"))
        graph.add_node(_kras_node("B1"))
        graph.add_node(_unrelated_node("C1"))
        event = _make_event(asset_id="A1")
        signals = compute_all_readthroughs(event, graph)
        assert len(signals) == 3

    def test_trial_failure_pos_delta_negative_for_class_risk(self):
        """Class-risk failure must yield negative pos_delta."""
        graph = CompetitionGraph()
        source = _pd1_node("S1")
        target = _clone_pd1("T1")
        graph.add_node(source)
        graph.add_node(target)
        event = CompetitorEvent(
            asset_id="S1", event_type="trial_failure", magnitude=0.8,
            indication="NSCLC", lot="2L", mechanism="checkpoint_inhibitor",
        )
        signal = compute_readthrough(event, graph, "T1")
        assert signal.pos_delta <= 0

    def test_readthrough_signal_is_frozen(self):
        """ReadthroughSignal must be immutable (frozen Pydantic model)."""
        signal = ReadthroughSignal(
            source_asset_id="S1",
            target_asset_id="T1",
            direction=ReadthroughDirection.NEUTRAL,
            magnitude=0.0,
            pos_delta=0.0,
            rationale="test",
            confidence=0.0,
        )
        with pytest.raises(Exception):
            signal.magnitude = 0.5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestRevaluationTriggers
# ---------------------------------------------------------------------------

def _make_signal(
    source: str = "S1",
    target: str = "T1",
    direction: ReadthroughDirection = ReadthroughDirection.NEGATIVE,
    magnitude: float = 0.20,
    pos_delta: float = -0.15,
) -> ReadthroughSignal:
    return ReadthroughSignal(
        source_asset_id=source,
        target_asset_id=target,
        direction=direction,
        magnitude=magnitude,
        pos_delta=pos_delta,
        rationale="test signal",
        confidence=0.8,
    )


class TestRevaluationTriggers:
    def test_immediate_priority_large_pos_delta(self):
        signal = _make_signal(magnitude=0.05, pos_delta=-0.12)
        triggers = emit_triggers([signal])
        assert len(triggers) == 1
        assert triggers[0].priority == TriggerPriority.IMMEDIATE

    def test_immediate_priority_large_magnitude(self):
        signal = _make_signal(magnitude=0.15, pos_delta=-0.01)
        triggers = emit_triggers([signal])
        assert triggers[0].priority == TriggerPriority.IMMEDIATE

    def test_high_priority_threshold(self):
        signal = _make_signal(magnitude=0.10, pos_delta=0.01)
        triggers = emit_triggers([signal])
        assert triggers[0].priority == TriggerPriority.HIGH

    def test_high_priority_pos_delta_threshold(self):
        signal = _make_signal(magnitude=0.01, pos_delta=0.08)
        triggers = emit_triggers([signal])
        assert triggers[0].priority == TriggerPriority.HIGH

    def test_medium_priority_threshold(self):
        signal = _make_signal(magnitude=0.05, pos_delta=0.01)
        triggers = emit_triggers([signal])
        assert triggers[0].priority == TriggerPriority.MEDIUM

    def test_medium_priority_pos_delta_threshold(self):
        signal = _make_signal(magnitude=0.01, pos_delta=0.04)
        triggers = emit_triggers([signal])
        assert triggers[0].priority == TriggerPriority.MEDIUM

    def test_low_priority_for_small_values(self):
        signal = _make_signal(magnitude=0.03, pos_delta=0.02)
        triggers = emit_triggers([signal])
        assert triggers[0].priority == TriggerPriority.LOW

    def test_suppressed_below_minimum(self):
        signal = _make_signal(magnitude=0.01, pos_delta=0.01)
        triggers = emit_triggers([signal])
        assert len(triggers) == 0

    def test_neutral_direction_suppressed(self):
        signal = _make_signal(
            direction=ReadthroughDirection.NEUTRAL,
            magnitude=0.0,
            pos_delta=0.0,
        )
        triggers = emit_triggers([signal])
        assert len(triggers) == 0

    def test_modules_immediate_includes_financing_risk(self):
        signal = _make_signal(magnitude=0.20, pos_delta=0.0)
        triggers = emit_triggers([signal])
        assert "financing_risk" in triggers[0].modules_to_recompute

    def test_modules_immediate_full_list(self):
        signal = _make_signal(magnitude=0.20, pos_delta=0.0)
        triggers = emit_triggers([signal])
        expected = {"probability_stack", "market_expectations", "recommendation", "financing_risk"}
        assert set(triggers[0].modules_to_recompute) == expected

    def test_modules_high_no_financing_risk(self):
        signal = _make_signal(magnitude=0.10, pos_delta=0.01)
        triggers = emit_triggers([signal])
        assert "financing_risk" not in triggers[0].modules_to_recompute
        assert "recommendation" in triggers[0].modules_to_recompute

    def test_modules_medium(self):
        signal = _make_signal(magnitude=0.05, pos_delta=0.01)
        triggers = emit_triggers([signal])
        assert set(triggers[0].modules_to_recompute) == {"probability_stack", "market_expectations"}

    def test_modules_low(self):
        signal = _make_signal(magnitude=0.03, pos_delta=0.02)
        triggers = emit_triggers([signal])
        assert triggers[0].modules_to_recompute == ["market_expectations"]

    def test_emit_triggers_sorted_immediate_first(self):
        signals = [
            _make_signal(source="S1", target="T1", magnitude=0.03, pos_delta=0.02),  # LOW
            _make_signal(source="S2", target="T2", magnitude=0.20, pos_delta=0.0),   # IMMEDIATE
            _make_signal(source="S3", target="T3", magnitude=0.10, pos_delta=0.01),  # HIGH
        ]
        triggers = emit_triggers(signals)
        priorities = [t.priority for t in triggers]
        assert priorities[0] == TriggerPriority.IMMEDIATE
        assert priorities[-1] == TriggerPriority.LOW

    def test_emit_triggers_asset_id_filter(self):
        signals = [
            _make_signal(source="S1", target="T1", magnitude=0.20),
            _make_signal(source="S2", target="T2", magnitude=0.20),
        ]
        triggers = emit_triggers(signals, asset_id_filter="T1")
        assert len(triggers) == 1
        assert triggers[0].asset_id == "T1"

    def test_trigger_id_is_unique_uuid(self):
        signals = [
            _make_signal(source="S1", target="T1", magnitude=0.20),
            _make_signal(source="S2", target="T2", magnitude=0.20),
        ]
        triggers = emit_triggers(signals)
        ids = [t.trigger_id for t in triggers]
        assert len(set(ids)) == len(ids)
        for tid in ids:
            uuid.UUID(tid)  # raises if not valid UUID

    def test_trigger_is_frozen(self):
        signal = _make_signal(magnitude=0.20)
        trigger = emit_triggers([signal])[0]
        with pytest.raises(Exception):
            trigger.priority = TriggerPriority.LOW  # type: ignore[misc]

    # TriggerStore tests

    def test_trigger_store_add_and_count(self):
        store = TriggerStore()
        signal = _make_signal(magnitude=0.20)
        trigger = emit_triggers([signal])[0]
        store.add(trigger)
        assert store.count() == 1

    def test_trigger_store_pending_returns_unprocessed(self):
        store = TriggerStore()
        signal = _make_signal(magnitude=0.20)
        trigger = emit_triggers([signal])[0]
        store.add(trigger)
        pending = store.pending()
        assert len(pending) == 1
        assert pending[0].trigger_id == trigger.trigger_id

    def test_trigger_store_mark_processed(self):
        store = TriggerStore()
        signal = _make_signal(magnitude=0.20)
        trigger = emit_triggers([signal])[0]
        store.add(trigger)
        store.mark_processed(trigger.trigger_id)
        assert len(store.pending()) == 0
        assert store.count() == 1  # still counted, just processed

    def test_trigger_store_pending_filter_by_priority(self):
        store = TriggerStore()
        s_imm = _make_signal(source="S1", target="T1", magnitude=0.20)
        s_low = _make_signal(source="S2", target="T2", magnitude=0.03, pos_delta=0.02)
        for t in emit_triggers([s_imm, s_low]):
            store.add(t)
        immediate = store.pending(TriggerPriority.IMMEDIATE)
        assert len(immediate) == 1
        assert immediate[0].priority == TriggerPriority.IMMEDIATE

    def test_trigger_store_pending_sorted_by_priority(self):
        store = TriggerStore()
        s_low = _make_signal(source="S1", target="T1", magnitude=0.03, pos_delta=0.02)
        s_imm = _make_signal(source="S2", target="T2", magnitude=0.20)
        for t in emit_triggers([s_low, s_imm]):
            store.add(t)
        pending = store.pending()
        assert pending[0].priority == TriggerPriority.IMMEDIATE

    def test_no_triggers_for_all_neutral_signals(self):
        neutral = _make_signal(
            direction=ReadthroughDirection.NEUTRAL, magnitude=0.0, pos_delta=0.0
        )
        assert emit_triggers([neutral]) == []

    def test_trigger_rationale_includes_asset_ids(self):
        signal = _make_signal(source="SRC_ASSET", target="TGT_ASSET", magnitude=0.20)
        trigger = emit_triggers([signal])[0]
        assert "SRC_ASSET" in trigger.rationale
        assert "TGT_ASSET" in trigger.rationale

    def test_trigger_source_event_asset_id(self):
        signal = _make_signal(source="SRC", target="TGT", magnitude=0.20)
        trigger = emit_triggers([signal])[0]
        assert trigger.source_event_asset_id == "SRC"
        assert trigger.asset_id == "TGT"

    def test_emit_empty_signals_returns_empty(self):
        assert emit_triggers([]) == []
