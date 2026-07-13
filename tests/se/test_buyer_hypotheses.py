from __future__ import annotations

from datetime import date

from bve.se.ranking.buyer import (
    build_buyer_advantage_hypothesis,
    build_screening_route_hypothesis,
)
from bve.se.schemas.contracts import (
    AttractivenessTier,
    BuyerCapabilityProfile,
    CapabilityEvidence,
    GateStatus,
    NormalizedFact,
)


def test_buyer_advantage_is_hypothesis_backed_by_versioned_capabilities() -> None:
    profile = BuyerCapabilityProfile(
        profile_id="profile:1",
        buyer_id="buyer:1",
        version="1",
        as_of_date=date(2026, 7, 10),
        scientific_translational=[
            CapabilityEvidence(
                capability_id="cap:b_cell",
                category="science",
                description="B-cell translational expertise",
                evidence_claim_ids=["claim:cap"],
                confidence=0.9,
                effective_from=date(2025, 1, 1),
            )
        ],
    )
    hypothesis = build_buyer_advantage_hypothesis(
        profile, asset_id="asset:1", relevant_capability_ids=["cap:b_cell"]
    )
    assert hypothesis.tier == AttractivenessTier.HIGH
    assert hypothesis.supporting_claim_ids == ["claim:cap"]
    assert hypothesis.public_pre_diligence is True


def test_silent_deal_market_is_unknown_not_available() -> None:
    hypothesis = build_screening_route_hypothesis(
        asset_id="asset:1", acceptable_routes=["LICENSE"], facts=[]
    )
    assert hypothesis.status == GateStatus.UNKNOWN
    assert hypothesis.route is None


def test_route_hypothesis_requires_affirmative_fact() -> None:
    fact = NormalizedFact(
        fact_id="fact:route",
        subject_id="asset:1",
        fact_type="available_deal_routes",
        value=["LICENSE"],
        supporting_claim_ids=["claim:route"],
        confidence=0.7,
    )
    hypothesis = build_screening_route_hypothesis(
        asset_id="asset:1", acceptable_routes=["LICENSE", "OPTION"], facts=[fact]
    )
    assert hypothesis.status == GateStatus.PASS
    assert hypothesis.route == "LICENSE"
    assert hypothesis.supporting_claim_ids == ["claim:route"]
