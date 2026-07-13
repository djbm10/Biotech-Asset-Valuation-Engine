"""Eight-gate buyer-specific eligibility engine with mandatory UNKNOWN review routing."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from pydantic import BaseModel, Field

from bve.se.gates.evaluator import evaluate_requirement, evaluate_target_expression
from bve.se.schemas.contracts import (
    AnalystReviewItem,
    BuyerProblemV2,
    BuyerRequirement,
    GateDecision,
    GateStatus,
    NormalizedFact,
    OverallDisposition,
    RequirementDomain,
    RequirementOperator,
)

_STAGE_ORDER = {
    "DISCOVERY": 0,
    "PRECLINICAL": 1,
    "PHASE_1": 2,
    "PHASE_2": 3,
    "PHASE_3": 4,
    "REGISTRATION": 5,
    "APPROVED": 6,
}


class GateEvaluation(BaseModel):
    subject_id: str
    decisions: list[GateDecision]
    disposition: OverallDisposition
    review_items: list[AnalystReviewItem] = Field(default_factory=list)


def _review_id(subject_id: str, gate_id: str, requirement_id: str) -> str:
    digest = hashlib.sha256(f"{subject_id}|{gate_id}|{requirement_id}".encode()).hexdigest()[:20]
    return f"review:{digest}"


def _requirement(
    requirement_id: str,
    fact_type: str,
    operator: RequirementOperator,
    expected_value,
    *,
    domain: RequirementDomain = RequirementDomain.ELIGIBILITY,
) -> BuyerRequirement:
    return BuyerRequirement(
        requirement_id=requirement_id,
        domain=domain,
        fact_type=fact_type,
        operator=operator,
        expected_value=expected_value,
        pass_condition=f"Observed {fact_type} satisfies buyer requirement {requirement_id}.",
        fail_condition=f"Observed {fact_type} conflicts with buyer requirement {requirement_id}.",
        unknown_condition=f"Observed {fact_type} is missing, stale, ambiguous, or conflicting.",
    )


def _stage_requirement(minimum_stage: str) -> BuyerRequirement:
    minimum = _STAGE_ORDER.get(minimum_stage.upper())
    if minimum is None:
        raise ValueError(f"unknown minimum stage {minimum_stage!r}")
    return _requirement(
        "evidence.minimum_stage",
        "development_stage_order",
        RequirementOperator.GTE,
        minimum,
        domain=RequirementDomain.EVIDENCE_SUFFICIENCY,
    )


class GateEngine:
    """Evaluate identity, target, modality, biology, strategy, capability, evidence, and access."""

    def evaluate(
        self,
        problem: BuyerProblemV2,
        *,
        subject_id: str,
        facts: Iterable[NormalizedFact],
    ) -> GateEvaluation:
        facts_list = list(facts)
        by_type: dict[str, list[NormalizedFact]] = {}
        for fact in facts_list:
            by_type.setdefault(fact.fact_type, []).append(fact)
        decisions: list[GateDecision] = []

        # 1. Distinct identity supported by a source-backed canonical/provisional record.
        decisions.append(
            evaluate_requirement(
                _requirement(
                    "identity.distinct_asset",
                    "identity_valid",
                    RequirementOperator.EQ,
                    True,
                ),
                subject_id=subject_id,
                facts=facts_list,
                gate_id="identity_validity",
            )
        )

        # 2. Explicit target expression over a construct-level target set.
        target_facts = by_type.get("construct_target_set", [])
        decisions.append(
            evaluate_target_expression(
                problem.strategic_gap.target_expression,
                subject_id=subject_id,
                target_fact=target_facts[0] if len(target_facts) == 1 else None,
            )
        )

        # 3. Required modality ontology.
        decisions.append(
            evaluate_requirement(
                _requirement(
                    "modality.required",
                    "modality_id",
                    RequirementOperator.IN,
                    problem.strategic_gap.modalities,
                ),
                subject_id=subject_id,
                facts=facts_list,
                gate_id="modality_technology",
            )
        )

        # 4. Buyer-authored biological requirements.
        for requirement in problem.strategic_gap.required_biology:
            decisions.append(
                evaluate_requirement(
                    requirement,
                    subject_id=subject_id,
                    facts=facts_list,
                    gate_id="required_biology",
                )
            )

        # 5. Strategic sandbox. Empty indications mean landscape-wide discovery.
        decisions.append(
            evaluate_requirement(
                _requirement(
                    "strategy.therapeutic_area",
                    "therapeutic_area",
                    RequirementOperator.IN,
                    problem.strategic_gap.therapeutic_areas,
                ),
                subject_id=subject_id,
                facts=facts_list,
                gate_id="strategic_sandbox",
            )
        )
        if problem.strategic_gap.indications:
            decisions.append(
                evaluate_requirement(
                    _requirement(
                        "strategy.indication",
                        "indication",
                        RequirementOperator.IN,
                        problem.strategic_gap.indications,
                    ),
                    subject_id=subject_id,
                    facts=facts_list,
                    gate_id="strategic_sandbox",
                )
            )

        # 6. All configured capability constraints are prerequisites.
        constraints = problem.strategic_gap.capability_constraints
        for requirement in [
            *constraints.manufacturing,
            *constraints.delivery,
            *constraints.clinical_operations,
            *constraints.commercial,
            *constraints.integration,
        ]:
            decisions.append(
                evaluate_requirement(
                    requirement,
                    subject_id=subject_id,
                    facts=facts_list,
                    gate_id="buyer_capability_fit",
                )
            )

        # 7. Evidence floor.
        floor = problem.strategic_gap.evidence_floor
        if floor.minimum_stage:
            decisions.append(
                evaluate_requirement(
                    _stage_requirement(floor.minimum_stage),
                    subject_id=subject_id,
                    facts=facts_list,
                    gate_id="evidence_floor",
                )
            )
        if floor.human_poc_required:
            decisions.append(
                evaluate_requirement(
                    _requirement(
                        "evidence.human_poc",
                        "human_poc_present",
                        RequirementOperator.EQ,
                        True,
                        domain=RequirementDomain.EVIDENCE_SUFFICIENCY,
                    ),
                    subject_id=subject_id,
                    facts=facts_list,
                    gate_id="evidence_floor",
                )
            )
        if floor.evaluable_patients_minimum:
            decisions.append(
                evaluate_requirement(
                    _requirement(
                        "evidence.evaluable_patients",
                        "evaluable_patients",
                        RequirementOperator.GTE,
                        floor.evaluable_patients_minimum,
                        domain=RequirementDomain.EVIDENCE_SUFFICIENCY,
                    ),
                    subject_id=subject_id,
                    facts=facts_list,
                    gate_id="evidence_floor",
                )
            )

        # 8. Access path fails only when all configured routes are affirmatively unavailable.
        if problem.strategic_gap.acceptable_deal_routes:
            decisions.append(
                evaluate_requirement(
                    _requirement(
                        "access.acceptable_route_exists",
                        "available_deal_routes",
                        RequirementOperator.CONTAINS_ANY,
                        problem.strategic_gap.acceptable_deal_routes,
                    ),
                    subject_id=subject_id,
                    facts=facts_list,
                    gate_id="access_path_feasibility",
                )
            )

        statuses = [decision.analyst_override or decision.status for decision in decisions]
        if GateStatus.FAIL in statuses:
            disposition = OverallDisposition.EXCLUDED
        elif GateStatus.UNKNOWN in statuses:
            disposition = OverallDisposition.UNRESOLVED
        else:
            disposition = OverallDisposition.ELIGIBLE
        review_items = [
            AnalystReviewItem(
                review_id=_review_id(subject_id, decision.gate_id, decision.requirement_id),
                subject_id=subject_id,
                gate_id=decision.gate_id,
                requirement_id=decision.requirement_id,
                reason=decision.rationale,
                priority="high",
                claim_ids=decision.supporting_or_contradictory_claim_ids,
            )
            for decision in decisions
            if (decision.analyst_override or decision.status) == GateStatus.UNKNOWN
        ]
        return GateEvaluation(
            subject_id=subject_id,
            decisions=decisions,
            disposition=disposition,
            review_items=review_items,
        )
