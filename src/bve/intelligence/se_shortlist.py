"""Search & Evaluation shortlist driver (Idea 13): one buyer problem over many assets.

Chris's actual deliverable is a ranked, gated shortlist for a *single* buyer
problem (e.g. "every CD19xBCMA T-cell engager we'd consider"), not a per-asset
verdict in isolation. This module is the pure driver that joins the pieces that
already exist — ``ScienceThesisBuilder`` -> ``Layer15BuyerMatcher`` ->
``build_buyer_problem_shortlist`` — into that one surface.

It does no scoring of its own and touches neither POS nor ``compute_science_modifier``
nor ``recommend_bd_route`` logic; it only orchestrates and joins. Gate failures
are recorded as ``ExcludedEntry`` (Idea 14) by the underlying builder.
"""
from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, Field

from bve.intelligence.layer15_buyer_match import (
    Layer15BuyerMatchInput,
    Layer15BuyerMatcher,
)
from bve.intelligence.science_thesis import (
    BDActionabilityResult,
    BuyerProblem,
    BuyerProblemShortlist,
    EvidenceGrade,
    build_buyer_problem_shortlist,
)
from bve.intelligence.science_thesis_builder import (
    ScienceThesisBuilder,
    ScienceThesisBuilderInput,
)


class ShortlistAssetInput(BaseModel):
    """Minimal per-asset spec the driver needs to score one asset against a problem.

    The science-evidence booleans are forwarded to ``ScienceThesisBuilder`` so a
    caller with richer knowledge produces a richer thesis; all default to the
    screening-grade "unknown" so a bare spec still scores.
    """

    asset_id: str
    asset_name: str = ""
    indication: str = ""
    phase: str = "phase2"
    therapeutic_area: str
    target: str = ""
    modality: str = ""
    mechanism: str = ""
    solves_buyer_problem: bool = True
    problem_solution_fit: float = Field(default=0.5, ge=0.0, le=1.0)
    platform_upside: float = Field(default=0.0, ge=0.0, le=1.0)
    internal_overlap_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_grade: EvidenceGrade = EvidenceGrade.SCREENING_PUBLIC
    # Forwarded to the thesis builder (optional enrichment).
    has_target_rationale: bool = False
    has_human_pkpd_evidence: bool = False
    has_biomarker_validation: bool = False
    has_human_poc: bool = False
    has_clinically_meaningful_effect: bool = False
    has_safety_signal: bool = False


def build_se_shortlist(
    buyer_problem: BuyerProblem,
    assets: Iterable[ShortlistAssetInput],
    *,
    buyer_problem_id: str | None = None,
    limit: int | None = None,
) -> BuyerProblemShortlist:
    """Score every asset against one buyer problem and return a ranked shortlist.

    Pure and side-effect-free. Builds a science thesis per asset, runs the Stage-1
    hard gates + Stage-2 scoring via ``Layer15BuyerMatcher``, then joins the
    results with ``build_buyer_problem_shortlist`` (gate-failers become
    ``ExcludedEntry`` records carrying the gate they tripped).
    """
    matcher = Layer15BuyerMatcher()
    builder = ScienceThesisBuilder()
    problem_id = buyer_problem_id or buyer_problem.buyer_id
    scored: list[tuple[str, str, BDActionabilityResult]] = []
    for spec in assets:
        thesis = builder.build(
            ScienceThesisBuilderInput(
                asset_id=spec.asset_id,
                asset_name=spec.asset_name,
                indication=spec.indication,
                phase=spec.phase,
                modality=spec.modality,
                target=spec.target,
                mechanism=spec.mechanism,
                has_target_rationale=(
                    spec.has_target_rationale or bool(spec.target or spec.mechanism)
                ),
                has_human_pkpd_evidence=spec.has_human_pkpd_evidence,
                has_biomarker_validation=spec.has_biomarker_validation,
                has_human_poc=spec.has_human_poc,
                has_clinically_meaningful_effect=spec.has_clinically_meaningful_effect,
                has_safety_signal=spec.has_safety_signal,
            )
        )
        result = matcher.match(
            Layer15BuyerMatchInput(
                science_thesis=thesis,
                buyer_problem=buyer_problem,
                therapeutic_area=spec.therapeutic_area,
                target=spec.target,
                modality=spec.modality,
                solves_buyer_problem=spec.solves_buyer_problem,
                problem_solution_fit=spec.problem_solution_fit,
                platform_upside=spec.platform_upside,
                internal_overlap_risk=spec.internal_overlap_risk,
                evidence_grade=spec.evidence_grade,
            )
        )
        scored.append((spec.asset_id, spec.asset_name, result))
    return build_buyer_problem_shortlist(problem_id, scored, limit=limit)
