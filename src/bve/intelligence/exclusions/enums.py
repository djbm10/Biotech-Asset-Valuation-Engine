"""Enumerations for the M&A hard exclusion / routing layer (Gate 0A).

Each gate in the system produces a GateStatus.  The final ExclusionAssessment
derives an overall_status by taking the most-severe status across all gates.

Severity order (most → least restrictive):
  HARD_FAIL > HISTORICAL_ONLY > ROUTE_TO_OTHER_MODEL > SEVERE_CAP
  > DILIGENCE_QUEUE > REFRESH_REQUIRED
  > PAIR_LEVEL_FAIL > PAIR_LEVEL_CAP > PASS

Company-level vs pair-level:
  - HARD_FAIL / HISTORICAL_ONLY / ROUTE_TO_OTHER_MODEL / SEVERE_CAP /
    DILIGENCE_QUEUE / REFRESH_REQUIRED apply to the company regardless of
    which acquirer is paired with it.
  - PAIR_LEVEL_FAIL / PAIR_LEVEL_CAP only invalidate or cap *one specific*
    acquirer-target combination; the company may still appear in rankings
    against other acquirers.
"""
from __future__ import annotations

from enum import Enum


class ExclusionStatus(str, Enum):
    """Output status from a single gate or the final ExclusionAssessment."""

    # Company fully passes — eligible for live M&A scoring.
    PASS = "PASS"

    # Company should not appear in any live ranking output.
    # Historical training / backtest use is still permitted.
    HARD_FAIL = "HARD_FAIL"

    # Already acquired / merged / delisted after takeout.
    # Excluded from live ranking but preserved for historical M&A training.
    HISTORICAL_ONLY = "HISTORICAL_ONLY"

    # Wrong model for this company — route to a specialist model.
    # The company is not bad; it belongs in a different pipeline.
    ROUTE_TO_OTHER_MODEL = "ROUTE_TO_OTHER_MODEL"

    # Company can be scored, but final score is capped at max_score_cap.
    # Used when there is a material but not disqualifying concern.
    SEVERE_CAP = "SEVERE_CAP"

    # Data missing or ambiguous; exclude from ranked output by default.
    # Include in diligence export so analysts can fill the gap.
    DILIGENCE_QUEUE = "DILIGENCE_QUEUE"

    # Stale or unreliable data — must be refreshed before scoring.
    REFRESH_REQUIRED = "REFRESH_REQUIRED"

    # Only this specific acquirer-target pair is invalid.
    # The target company may still rank against other acquirers.
    PAIR_LEVEL_FAIL = "PAIR_LEVEL_FAIL"

    # Only this specific acquirer-target pair score is capped.
    PAIR_LEVEL_CAP = "PAIR_LEVEL_CAP"


# Severity order for collapsing multiple gate results into one overall_status.
# Lower index = more severe.
_SEVERITY_ORDER: list[ExclusionStatus] = [
    ExclusionStatus.HARD_FAIL,
    ExclusionStatus.HISTORICAL_ONLY,
    ExclusionStatus.ROUTE_TO_OTHER_MODEL,
    ExclusionStatus.SEVERE_CAP,
    ExclusionStatus.DILIGENCE_QUEUE,
    ExclusionStatus.REFRESH_REQUIRED,
    ExclusionStatus.PAIR_LEVEL_FAIL,
    ExclusionStatus.PAIR_LEVEL_CAP,
    ExclusionStatus.PASS,
]

_SEVERITY_RANK: dict[ExclusionStatus, int] = {
    s: i for i, s in enumerate(_SEVERITY_ORDER)
}


def most_severe(statuses: list[ExclusionStatus]) -> ExclusionStatus:
    """Return the most restrictive status from a list.

    >>> most_severe([ExclusionStatus.PASS, ExclusionStatus.SEVERE_CAP])
    <ExclusionStatus.SEVERE_CAP: 'SEVERE_CAP'>
    """
    if not statuses:
        return ExclusionStatus.PASS
    return min(statuses, key=lambda s: _SEVERITY_RANK[s])


class GateName(str, Enum):
    """Identifier for each gate in the exclusion pipeline."""

    GATE_0_ENTITY_VALIDITY = "gate_0_entity_validity"
    GATE_1_CORPORATE_STATUS = "gate_1_corporate_status"
    GATE_2_BUYER_TARGET_VALIDITY = "gate_2_buyer_target_validity"
    GATE_3_ASSET_VISIBILITY = "gate_3_asset_visibility"
    GATE_4_ASSET_VIABILITY = "gate_4_asset_viability"
    GATE_5_RIGHTS_IP_OWNERSHIP = "gate_5_rights_ip_ownership"
    GATE_6_FINANCIAL_GOING_CONCERN = "gate_6_financial_going_concern"
    GATE_7_MARKET_DATA_QUALITY = "gate_7_market_data_quality"
    GATE_8_LEGAL_INTEGRITY = "gate_8_legal_integrity"
    GATE_9_COMMERCIAL_RELEVANCE = "gate_9_commercial_relevance"
    GATE_10_MODEL_ROUTING = "gate_10_model_routing"


class RoutingModel(str, Enum):
    """Specialist model that a company should be routed to instead."""

    LICENSING_MODEL = "licensing_model"
    DISTRESSED_OPTIONALITY_MODEL = "distressed_optionality_model"
    COMMERCIAL_FRANCHISE_MODEL = "commercial_franchise_model"
    PLATFORM_ACQUISITION_MODEL = "platform_acquisition_model"
    ROYALTY_MODEL = "royalty_model"
    SERVICES_MA_MODEL = "services_ma_model"
    MERGER_OF_EQUALS_MODEL = "merger_of_equals_model"
