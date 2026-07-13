"""Frozen/development benchmark evaluator with explicit failure accounting."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

from bve.se.evaluation.metrics import ClassificationMetrics, evaluate_classification
from bve.se.pipeline import SESearchResult


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _contains_reference(expected: str, observed: Iterable[str]) -> bool:
    expected_norm = _norm(expected)
    return any(
        expected_norm == _norm(candidate)
        or expected_norm in _norm(candidate)
        or _norm(candidate) in expected_norm
        for candidate in observed
    )


class ReferenceFailure(BaseModel):
    fixture_id: str
    canonical_asset: str
    category: str


class BenchmarkEvaluationReport(BaseModel):
    benchmark_path: str
    reference_set: str
    candidate_metrics: ClassificationMetrics
    expected_assets: list[str]
    observed_assets: list[str]
    failures: list[ReferenceFailure] = Field(default_factory=list)
    citation_coverage: float = 0.0
    citation_entailment: float = 0.0
    unknown_gate_routing: float = 1.0
    precision_evaluable: bool = False
    release_eligible: bool = False


def evaluate_reference_landscape(
    benchmark_path: Path,
    result: SESearchResult,
    *,
    reference_set: str,
) -> BenchmarkEvaluationReport:
    data = yaml.safe_load(benchmark_path.read_text())
    if data.get("status") in {"sealed_holdout", "sealed", "holdout"}:
        raise ValueError("sealed holdout cannot be opened by milestone evaluation")
    records = data.get("records", [])
    expected = [record["canonical_asset"] for record in records if record.get("expected_candidate")]
    observed = [asset.canonical_name for asset in result.candidates]
    matched_expected = {
        value for value in expected if _contains_reference(value, observed)
    }
    # Candidate recall is reference-oriented; precision still uses exact normalized identities so
    # near-matches and supportive interventions remain visible as false positives.
    expected_norm = {_norm(value): value for value in expected}
    observed_norm: dict[str, str] = {}
    for observed_value in observed:
        matching_expected = next(
            (expected_value for expected_value in expected if _contains_reference(expected_value, [observed_value])),
            None,
        )
        canonical = matching_expected or observed_value
        observed_norm[_norm(canonical)] = canonical
    metrics = evaluate_classification(
        expected_norm,
        observed_norm,
    )
    failures: list[ReferenceFailure] = []
    for record in records:
        if record.get("expected_candidate") and record["canonical_asset"] not in matched_expected:
            failures.append(
                ReferenceFailure(
                    fixture_id=record["fixture_id"],
                    canonical_asset=record["canonical_asset"],
                    category="candidate_not_retrieved",
                )
            )
    citation_results = result.entailment_results
    cited = len(result.claims)
    entailed = sum(item.entailed for item in citation_results)
    unknown_total = sum(
        1
        for evaluation in result.gate_evaluations
        for decision in evaluation.decisions
        if (decision.analyst_override or decision.status).value == "UNKNOWN"
    )
    routed = sum(item.requirement_id is not None for item in result.review_queue)
    return BenchmarkEvaluationReport(
        benchmark_path=str(benchmark_path),
        reference_set=reference_set,
        candidate_metrics=metrics,
        expected_assets=expected,
        observed_assets=observed,
        failures=failures,
        citation_coverage=1.0 if cited else 0.0,
        citation_entailment=entailed / cited if cited else 1.0,
        unknown_gate_routing=routed / unknown_total if unknown_total else 1.0,
        precision_evaluable=bool(data.get("precision_evaluable", False)),
        release_eligible=(
            bool(data.get("precision_evaluable", False))
            and metrics.recall >= 0.95
            and metrics.precision >= 0.95
            and routed >= unknown_total
            and not failures
        ),
    )
