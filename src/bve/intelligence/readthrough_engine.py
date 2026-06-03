"""Readthrough engine — propagates competitor events to related assets.

Rules are deterministic (no LLM calls, no external HTTP).

Event type rules:
  trial_success / fda_approval from direct competitor (similarity >= 0.60):
    - POSITIVE (class validation) if indication+lot avg >= 0.60
    - NEGATIVE (crowding) if mechanism_score >= 0.70
    - CLASS_EXPANSION if mechanism_score < 0.30 AND indication match strong

  trial_failure / crl:
    - NEGATIVE if mechanism_similarity >= 0.60 (class risk)
    - POSITIVE if target_similarity >= 0.60 but mechanism_similarity < 0.40

  safety_halt:
    - Always NEGATIVE for mechanism-similar assets (mechanism >= 0.40)

  partnership:
    - POSITIVE for indication-similar assets (indication_score >= 0.40)

  Assets with similarity < 0.30:
    - NEUTRAL (magnitude=0, pos_delta=0)
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from bve.intelligence.competition_graph import (
    CompetitionGraph,
    SimilarityScore,
)


class ReadthroughDirection(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    CLASS_EXPANSION = "class_expansion"


class ReadthroughSignal(BaseModel, frozen=True):
    source_asset_id: str
    target_asset_id: str
    direction: ReadthroughDirection
    magnitude: float          # 0.0-1.0 strength
    pos_delta: float          # suggested PoS adjustment (-0.20 to +0.20)
    rationale: str
    confidence: float         # 0.0-1.0


class CompetitorEvent(BaseModel, frozen=True):
    asset_id: str
    event_type: str           # "trial_success", "trial_failure", "fda_approval", "crl",
    #                           "safety_halt", "partnership"
    magnitude: float          # 0.0-1.0 — how big the event is
    indication: str
    lot: str
    mechanism: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _neutral_signal(
    source_asset_id: str, target_asset_id: str, rationale: str
) -> ReadthroughSignal:
    return ReadthroughSignal(
        source_asset_id=source_asset_id,
        target_asset_id=target_asset_id,
        direction=ReadthroughDirection.NEUTRAL,
        magnitude=0.0,
        pos_delta=0.0,
        rationale=rationale,
        confidence=0.0,
    )


def _handle_success_approval(
    event: CompetitorEvent,
    score: SimilarityScore,
    target_asset_id: str,
) -> ReadthroughSignal:
    """Handle trial_success or fda_approval from a direct competitor."""
    indication_score = score.dimension_scores.get("indication", 0.0)
    lot_score = score.dimension_scores.get("lot", 0.0)
    mechanism_score = score.dimension_scores.get("mechanism", 0.0)
    indication_lot_avg = (indication_score + lot_score) / 2.0

    # CLASS_EXPANSION: differentiated mechanism but same indication space
    if mechanism_score < 0.30 and indication_lot_avg >= 0.60:
        mag = _clamp(event.magnitude * score.composite_score * 0.8, 0.0, 1.0)
        pos_d = _clamp(event.magnitude * score.composite_score * 0.12, 0.0, 0.20)
        return ReadthroughSignal(
            source_asset_id=event.asset_id,
            target_asset_id=target_asset_id,
            direction=ReadthroughDirection.CLASS_EXPANSION,
            magnitude=mag,
            pos_delta=pos_d,
            rationale=(
                "Competitor success validates indication with differentiated mechanism — "
                "class expansion for target asset."
            ),
            confidence=score.composite_score,
        )

    # NEGATIVE: mechanism crowding
    if mechanism_score >= 0.70:
        mag = _clamp(event.magnitude * score.composite_score * 0.8, 0.0, 1.0)
        pos_d = _clamp(event.magnitude * score.composite_score * -0.15, -0.15, 0.0)
        return ReadthroughSignal(
            source_asset_id=event.asset_id,
            target_asset_id=target_asset_id,
            direction=ReadthroughDirection.NEGATIVE,
            magnitude=mag,
            pos_delta=pos_d,
            rationale=(
                "High mechanism similarity — competitor success increases competitive crowding."
            ),
            confidence=score.composite_score,
        )

    # POSITIVE: class validation
    if indication_lot_avg >= 0.60:
        mag = _clamp(event.magnitude * score.composite_score * 0.7, 0.0, 1.0)
        pos_d = _clamp(event.magnitude * score.composite_score * 0.15, 0.0, 0.20)
        return ReadthroughSignal(
            source_asset_id=event.asset_id,
            target_asset_id=target_asset_id,
            direction=ReadthroughDirection.POSITIVE,
            magnitude=mag,
            pos_delta=pos_d,
            rationale=(
                "Competitor success validates indication/LOT class — positive readthrough."
            ),
            confidence=score.composite_score,
        )

    # Default for direct competitor with moderate scores
    mag = _clamp(event.magnitude * score.composite_score * 0.5, 0.0, 1.0)
    pos_d = _clamp(event.magnitude * score.composite_score * 0.08, 0.0, 0.15)
    return ReadthroughSignal(
        source_asset_id=event.asset_id,
        target_asset_id=target_asset_id,
        direction=ReadthroughDirection.POSITIVE,
        magnitude=mag,
        pos_delta=pos_d,
        rationale="Competitor success provides moderate class validation.",
        confidence=score.composite_score,
    )


def _handle_failure_crl(
    event: CompetitorEvent,
    score: SimilarityScore,
    target_asset_id: str,
) -> ReadthroughSignal:
    """Handle trial_failure or crl from a competitor."""
    mechanism_score = score.dimension_scores.get("mechanism", 0.0)
    target_score = score.dimension_scores.get("target", 0.0)

    # POSITIVE: competitor removed from race (high target match, low mechanism match)
    if target_score >= 0.60 and mechanism_score < 0.40:
        mag = _clamp(event.magnitude * score.composite_score * 0.6, 0.0, 1.0)
        pos_d = _clamp(event.magnitude * score.composite_score * 0.10, 0.0, 0.15)
        return ReadthroughSignal(
            source_asset_id=event.asset_id,
            target_asset_id=target_asset_id,
            direction=ReadthroughDirection.POSITIVE,
            magnitude=mag,
            pos_delta=pos_d,
            rationale=(
                "Competitor failure removes rival from same target — "
                "market opportunity improves for target asset."
            ),
            confidence=score.composite_score,
        )

    # NEGATIVE: class risk from mechanism-similar failure
    if mechanism_score >= 0.60:
        mag = _clamp(event.magnitude * score.composite_score * 0.8, 0.0, 1.0)
        pos_d = _clamp(event.magnitude * score.composite_score * -0.20, -0.20, 0.0)
        return ReadthroughSignal(
            source_asset_id=event.asset_id,
            target_asset_id=target_asset_id,
            direction=ReadthroughDirection.NEGATIVE,
            magnitude=mag,
            pos_delta=pos_d,
            rationale=(
                "Mechanism-similar competitor failure suggests class-level risk."
            ),
            confidence=score.composite_score,
        )

    # Moderate negative for other direct competitors
    mag = _clamp(event.magnitude * score.composite_score * 0.5, 0.0, 1.0)
    pos_d = _clamp(event.magnitude * score.composite_score * -0.08, -0.10, 0.0)
    return ReadthroughSignal(
        source_asset_id=event.asset_id,
        target_asset_id=target_asset_id,
        direction=ReadthroughDirection.NEGATIVE,
        magnitude=mag,
        pos_delta=pos_d,
        rationale="Competitor failure raises indirect class-level concern.",
        confidence=score.composite_score,
    )


def _handle_safety_halt(
    event: CompetitorEvent,
    score: SimilarityScore,
    target_asset_id: str,
) -> ReadthroughSignal:
    """Handle safety_halt — always negative for mechanism-similar assets."""
    mechanism_score = score.dimension_scores.get("mechanism", 0.0)

    if mechanism_score >= 0.40:
        mag = _clamp(event.magnitude * score.composite_score * 0.9, 0.0, 1.0)
        pos_d = _clamp(event.magnitude * mechanism_score * -0.25, -0.25, 0.0)
        return ReadthroughSignal(
            source_asset_id=event.asset_id,
            target_asset_id=target_asset_id,
            direction=ReadthroughDirection.NEGATIVE,
            magnitude=mag,
            pos_delta=pos_d,
            rationale=(
                "Safety halt in mechanism-similar competitor — class-level safety signal."
            ),
            confidence=score.composite_score,
        )

    # Low mechanism similarity — smaller negative
    mag = _clamp(event.magnitude * score.composite_score * 0.4, 0.0, 1.0)
    pos_d = _clamp(event.magnitude * score.composite_score * -0.05, -0.10, 0.0)
    return ReadthroughSignal(
        source_asset_id=event.asset_id,
        target_asset_id=target_asset_id,
        direction=ReadthroughDirection.NEGATIVE,
        magnitude=mag,
        pos_delta=pos_d,
        rationale="Safety halt in related competitor — moderate negative readthrough.",
        confidence=score.composite_score,
    )


def _handle_partnership(
    event: CompetitorEvent,
    score: SimilarityScore,
    target_asset_id: str,
) -> ReadthroughSignal:
    """Handle partnership — positive for indication-similar assets."""
    indication_score = score.dimension_scores.get("indication", 0.0)

    if indication_score >= 0.40:
        mag = _clamp(event.magnitude * indication_score * 0.5, 0.0, 1.0)
        pos_d = _clamp(event.magnitude * indication_score * 0.08, 0.0, 0.08)
        return ReadthroughSignal(
            source_asset_id=event.asset_id,
            target_asset_id=target_asset_id,
            direction=ReadthroughDirection.POSITIVE,
            magnitude=mag,
            pos_delta=pos_d,
            rationale=(
                "Partnership in same indication space validates class attractiveness."
            ),
            confidence=score.composite_score,
        )

    # Low indication similarity — neutral
    return _neutral_signal(
        event.asset_id,
        target_asset_id,
        "Partnership in unrelated indication — no readthrough.",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_readthrough(
    event: CompetitorEvent,
    graph: CompetitionGraph,
    target_asset_id: str,
) -> ReadthroughSignal:
    """Compute readthrough from a competitor event to a specific target asset."""
    source_node = None
    target_node = None
    for node in graph.all_nodes():
        if node.asset_id == event.asset_id:
            source_node = node
        if node.asset_id == target_asset_id:
            target_node = node

    if source_node is None or target_node is None:
        return _neutral_signal(
            event.asset_id,
            target_asset_id,
            "Source or target asset not found in competition graph.",
        )

    score = graph.compute_similarity(source_node, target_node)

    # Assets with similarity < 0.30 → NEUTRAL
    if score.composite_score < 0.30:
        return _neutral_signal(
            event.asset_id,
            target_asset_id,
            f"Similarity {score.composite_score:.2f} below 0.30 threshold — no readthrough.",
        )

    etype = event.event_type

    if etype in ("trial_success", "fda_approval"):
        return _handle_success_approval(event, score, target_asset_id)
    elif etype in ("trial_failure", "crl"):
        return _handle_failure_crl(event, score, target_asset_id)
    elif etype == "safety_halt":
        return _handle_safety_halt(event, score, target_asset_id)
    elif etype == "partnership":
        return _handle_partnership(event, score, target_asset_id)
    else:
        return _neutral_signal(
            event.asset_id,
            target_asset_id,
            f"Unknown event type '{etype}' — no readthrough rule defined.",
        )


def compute_all_readthroughs(
    event: CompetitorEvent,
    graph: CompetitionGraph,
    exclude_asset_ids: set[str] | None = None,
) -> list[ReadthroughSignal]:
    """Compute readthrough signals to all assets in the graph except the source."""
    excluded = exclude_asset_ids or set()
    excluded = excluded | {event.asset_id}

    signals: list[ReadthroughSignal] = []
    for node in graph.all_nodes():
        if node.asset_id in excluded:
            continue
        signal = compute_readthrough(event, graph, node.asset_id)
        signals.append(signal)

    return signals
