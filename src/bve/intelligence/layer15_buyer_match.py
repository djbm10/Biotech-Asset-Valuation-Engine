"""Layer 1.5 buyer-problem matching for BD mode."""

from __future__ import annotations

from pydantic import BaseModel, Field

from bve.intelligence.science_thesis import (
    BDActionabilityResult,
    BuyerProblem,
    ScienceThesis,
    compute_bd_actionability,
    evaluate_bd_hard_gates,
    recommend_bd_route,
)


class Layer15BuyerMatchInput(BaseModel):
    science_thesis: ScienceThesis
    buyer_problem: BuyerProblem
    therapeutic_area: str
    target: str
    modality: str
    solves_buyer_problem: bool
    problem_solution_fit: float = Field(default=0.5, ge=0.0, le=1.0)
    platform_upside: float = Field(default=0.0, ge=0.0, le=1.0)
    internal_overlap_risk: float = Field(default=0.0, ge=0.0, le=1.0)


class Layer15BuyerMatcher:
    """Apply Chris-style buyer sandbox gates and BD actionability scoring."""

    def match(self, inputs: Layer15BuyerMatchInput) -> BDActionabilityResult:
        failed_gates = evaluate_bd_hard_gates(
            inputs.buyer_problem,
            therapeutic_area=inputs.therapeutic_area,
            target=inputs.target,
            modality=inputs.modality,
            solves_buyer_problem=inputs.solves_buyer_problem,
        )
        passed = not failed_gates
        if not passed:
            return compute_bd_actionability(
                passed_hard_gates=False,
                failed_gates=failed_gates,
                diligence_questions=inputs.science_thesis.bd_diligence_questions,
            )

        science_fit = self._science_thesis_fit(inputs.science_thesis)
        evidence_quality = self._component_score(inputs.science_thesis, "Q")
        diligence_readiness = self._diligence_readiness(inputs.science_thesis)
        modality_fit = self._modality_fit(inputs.buyer_problem, inputs.modality)
        owner_advantage = self._owner_advantage(inputs.buyer_problem)
        deal_feasibility = max(0.0, 0.75 - (0.25 * inputs.internal_overlap_risk))
        human_poc_strength = self._component_score(inputs.science_thesis, "H")
        route, route_confidence, route_rationale = recommend_bd_route(
            passed_hard_gates=True,
            science_thesis_fit=science_fit,
            human_poc_strength=human_poc_strength,
            strategic_fit=inputs.problem_solution_fit,
            urgency=inputs.buyer_problem.urgency,
            platform_upside=inputs.platform_upside,
            uncertainty=max(0.0, 1.0 - diligence_readiness),
            thesis_refuted=self._thesis_refuted(inputs.science_thesis),
        )
        return compute_bd_actionability(
            passed_hard_gates=True,
            buyer_problem_fit=inputs.problem_solution_fit,
            science_thesis_fit=science_fit,
            evidence_quality=evidence_quality,
            diligence_readiness=diligence_readiness,
            modality_capability_fit=modality_fit,
            buyer_owner_advantage=owner_advantage,
            internal_portfolio_fit=0.65 if inputs.buyer_problem.existing_portfolio_context else 0.5,
            assessed_internal_overlap_risk=inputs.internal_overlap_risk,
            combination_or_lifecycle_fit=0.70 if inputs.buyer_problem.combination_or_lifecycle_fit else 0.5,
            alternative_assets_available=inputs.buyer_problem.alternative_assets_available,
            competitive_intensity=inputs.buyer_problem.competitive_intensity,
            scarcity_value=inputs.buyer_problem.scarcity_value,
            time_sensitivity=inputs.buyer_problem.time_sensitivity,
            deal_feasibility=deal_feasibility,
            confidence_inputs=[inputs.buyer_problem.confidence, evidence_quality, diligence_readiness],
            route=route,
            route_confidence=route_confidence,
            route_rationale=route_rationale,
            diligence_questions=inputs.science_thesis.bd_diligence_questions,
        )

    def _science_thesis_fit(self, thesis: ScienceThesis) -> float:
        if thesis.modifier_result is None:
            return 0.5
        if self._thesis_refuted(thesis):
            return 0.0
        return thesis.modifier_result.science_score

    def _component_score(self, thesis: ScienceThesis, component: str) -> float:
        if component not in thesis.components:
            return 0.5
        return thesis.components[component].score

    def _diligence_readiness(self, thesis: ScienceThesis) -> float:
        missing_count = len(thesis.missing_critical_evidence)
        readiness = max(0.0, 1.0 - (0.12 * missing_count))
        if thesis.modifier_result is not None and thesis.modifier_result.warnings:
            readiness = max(0.0, readiness - 0.10)
        return round(readiness, 4)

    def _modality_fit(self, buyer_problem: BuyerProblem, modality: str) -> float:
        if not buyer_problem.required_modalities:
            return 0.5
        return 0.85 if modality.lower() in {item.lower() for item in buyer_problem.required_modalities} else 0.25

    def _owner_advantage(self, buyer_problem: BuyerProblem) -> float:
        score = 0.5
        if buyer_problem.existing_portfolio_context:
            score += 0.10
        if buyer_problem.combination_or_lifecycle_fit:
            score += 0.10
        if buyer_problem.scarcity_value >= 0.70:
            score += 0.05
        return min(1.0, score)

    def _thesis_refuted(self, thesis: ScienceThesis) -> bool:
        return bool(thesis.modifier_result and thesis.modifier_result.kill_flags)
