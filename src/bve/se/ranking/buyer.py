"""Evidence-backed buyer-advantage and public route hypotheses."""

from __future__ import annotations

from collections.abc import Iterable

from bve.se.schemas.contracts import (
    AttractivenessTier,
    BuyerAdvantageHypothesis,
    BuyerCapabilityProfile,
    GateStatus,
    NormalizedFact,
    ScreeningRouteHypothesis,
)


def build_buyer_advantage_hypothesis(
    profile: BuyerCapabilityProfile,
    *,
    asset_id: str,
    relevant_capability_ids: Iterable[str],
) -> BuyerAdvantageHypothesis:
    requested = set(relevant_capability_ids)
    capabilities = [
        capability
        for group in [
            profile.scientific_translational,
            profile.clinical_development,
            profile.manufacturing_delivery,
            profile.commercial_presence,
            profile.portfolio_combinations,
            profile.integration_constraints,
            profile.risk_transaction_preferences,
        ]
        for capability in group
        if capability.capability_id in requested
    ]
    if not requested or not capabilities:
        return BuyerAdvantageHypothesis(
            buyer_id=profile.buyer_id,
            asset_id=asset_id,
            tier=AttractivenessTier.UNRANKED,
            rationale="No evidence-backed relevant buyer capabilities were identified.",
        )
    matched = {capability.capability_id for capability in capabilities}
    coverage = len(matched) / len(requested)
    confidence = min(capability.confidence for capability in capabilities)
    if coverage == 1.0 and confidence >= 0.75:
        tier = AttractivenessTier.HIGH
    elif coverage >= 0.5 and confidence >= 0.5:
        tier = AttractivenessTier.MODERATE
    else:
        tier = AttractivenessTier.LOW
    return BuyerAdvantageHypothesis(
        buyer_id=profile.buyer_id,
        asset_id=asset_id,
        tier=tier,
        rationale=(
            f"Matched {len(matched)} of {len(requested)} configured relevant capabilities; "
            f"weakest evidence confidence {confidence:.2f}."
        ),
        matched_capability_ids=sorted(matched),
        supporting_claim_ids=list(
            dict.fromkeys(
                claim_id for capability in capabilities for claim_id in capability.evidence_claim_ids
            )
        ),
    )


def build_screening_route_hypothesis(
    *,
    asset_id: str,
    acceptable_routes: list[str],
    facts: Iterable[NormalizedFact],
) -> ScreeningRouteHypothesis:
    facts_list = list(facts)
    route_facts = [fact for fact in facts_list if fact.fact_type == "available_deal_routes"]
    if not route_facts:
        return ScreeningRouteHypothesis(
            asset_id=asset_id,
            status=GateStatus.UNKNOWN,
            rationale="No public fact establishes an available path to access or control.",
            decisive_unknown="Confirm rights, encumbrances, and counterparty willingness.",
        )
    if any(fact.contradicting_claim_ids for fact in route_facts):
        return ScreeningRouteHypothesis(
            asset_id=asset_id,
            status=GateStatus.UNKNOWN,
            rationale="Public route evidence is conflicting.",
            supporting_fact_ids=[fact.fact_id for fact in route_facts],
            supporting_claim_ids=list(
                dict.fromkeys(
                    claim_id
                    for fact in route_facts
                    for claim_id in [*fact.supporting_claim_ids, *fact.contradicting_claim_ids]
                )
            ),
            decisive_unknown="Reconcile ownership, rights, and transaction-path evidence.",
        )
    available = [
        route
        for route in acceptable_routes
        if any(route in set(fact.value) for fact in route_facts)
    ]
    claims = list(
        dict.fromkeys(claim_id for fact in route_facts for claim_id in fact.supporting_claim_ids)
    )
    if not available:
        return ScreeningRouteHypothesis(
            asset_id=asset_id,
            status=GateStatus.FAIL,
            rationale="Affirmative public facts show no configured acceptable route is available.",
            supporting_fact_ids=[fact.fact_id for fact in route_facts],
            supporting_claim_ids=claims,
        )
    return ScreeningRouteHypothesis(
        asset_id=asset_id,
        route=available[0],
        status=GateStatus.PASS,
        rationale="This is a publicly supported screening route hypothesis, not a transaction recommendation.",
        supporting_fact_ids=[fact.fact_id for fact in route_facts],
        supporting_claim_ids=claims,
        decisive_unknown="Confirm willingness, price, legal encumbrances, and undisclosed restrictions.",
    )
