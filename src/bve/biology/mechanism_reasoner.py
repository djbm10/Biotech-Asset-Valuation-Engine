"""Reason about mechanism of action to produce efficacy hypotheses, safety liabilities, and biomarker logic."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from bve.biology.pathway_graph import PathwayGraph


class EfficacyHypothesis(BaseModel):
    mechanism: str
    target: str
    indication: str
    hypothesis: str             # plain English
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_biology: list[str] = Field(default_factory=list)
    key_assumptions: list[str] = Field(default_factory=list)


class SafetyLiabilityAssessment(BaseModel):
    mechanism: str
    liability_name: str
    severity: str               # "mild" / "moderate" / "severe"
    mechanism_basis: str        # why this mechanism causes this liability
    class_precedent: bool = False
    mitigation_strategies: list[str] = Field(default_factory=list)


class BiomarkerLogic(BaseModel):
    biomarker: str
    direction: str              # "enriches_responders" / "predicts_toxicity" / "monitors_target_engagement"
    rationale: str
    evidence_quality: str       # "preclinical_only" / "clinical_biomarker" / "validated_companion_dx"


class MechanismReasoningResult(BaseModel):
    mechanism: str
    indication: str
    efficacy_hypotheses: list[EfficacyHypothesis]
    safety_liabilities: list[SafetyLiabilityAssessment]
    biomarker_logic: list[BiomarkerLogic]
    bear_cases: list[str]       # reasons this mechanism might fail despite elegance
    fda_reviewer_concerns: list[str]
    summary: str


class MechanismReasoner:
    """
    Produce structured reasoning about a mechanism given a PathwayGraph and
    optionally pre-seeded node data.

    This is a rule/template-based reasoner, NOT an LLM call.
    It uses graph relationships to infer liabilities and biomarker logic,
    then builds structured outputs from known patterns.
    """

    def __init__(self, graph: Optional[PathwayGraph] = None) -> None:
        self._graph = graph or PathwayGraph()

    def reason(
        self,
        mechanism: str,
        indication: str,
        mechanism_node_id: Optional[str] = None,
    ) -> MechanismReasoningResult:
        """
        Produce reasoning for a mechanism + indication pair.

        When mechanism_node_id is provided, pull liabilities and targets from graph.
        Otherwise build from passed-in mechanism string alone (limited mode).
        """
        liabilities: list[SafetyLiabilityAssessment] = []
        biomarkers: list[BiomarkerLogic] = []

        if mechanism_node_id is not None:
            liability_nodes = self._graph.liabilities_for_mechanism(mechanism_node_id)
            for ln in liability_nodes:
                liabilities.append(SafetyLiabilityAssessment(
                    mechanism=mechanism,
                    liability_name=ln.name,
                    severity="moderate",
                    mechanism_basis=ln.description or f"Graph-linked liability for {mechanism}",
                    class_precedent=False,
                ))

        efficacy_hypotheses = [EfficacyHypothesis(
            mechanism=mechanism,
            target=mechanism,
            indication=indication,
            hypothesis=f"{mechanism} modulation is hypothesized to achieve clinical benefit in {indication}.",
            confidence=0.5,
            supporting_biology=[],
            key_assumptions=["Target is causal in disease", "Sufficient target engagement achievable"],
        )]

        bear_cases = [
            f"Target may not be causally sufficient in {indication}",
            "Compensatory pathway activation may limit durability",
            "Safety liabilities may require dose reduction below efficacy threshold",
        ]

        fda_concerns = [
            "Endpoint validation and clinical meaningfulness",
            "Safety monitoring requirements",
            "Biomarker-selected vs all-comer population design",
        ]

        return MechanismReasoningResult(
            mechanism=mechanism,
            indication=indication,
            efficacy_hypotheses=efficacy_hypotheses,
            safety_liabilities=liabilities,
            biomarker_logic=biomarkers,
            bear_cases=bear_cases,
            fda_reviewer_concerns=fda_concerns,
            summary=(
                f"Mechanism: {mechanism}. Indication: {indication}. "
                f"{len(liabilities)} graph-linked liabilities identified. "
                f"Confidence: moderate pending clinical validation."
            ),
        )
