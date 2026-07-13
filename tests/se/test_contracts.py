from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from bve.se.ontology.targets import normalize_modality, normalize_target
from bve.se.schemas.contracts import (
    BuyerProblemV2,
    GateDecision,
    GateStatus,
    RunManifest,
    RunStatus,
    TargetExpression,
    TargetOperator,
    TargetTerm,
)


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "filename,operator",
    [
        ("cd19_bcma_dual_target.yaml", TargetOperator.EXACT_COMBINATION),
        ("cd19_or_bcma_tce.yaml", TargetOperator.ANY),
    ],
)
def test_benchmark_problem_validates(filename: str, operator: TargetOperator) -> None:
    path = ROOT / "examples/configs/se/benchmarks" / filename
    problem = BuyerProblemV2.model_validate(yaml.safe_load(path.read_text()))

    assert problem.strategic_gap.target_expression.operator == operator
    assert {target.canonical_id for target in problem.strategic_gap.target_expression.targets} == {
        "CD19",
        "BCMA",
    }


def test_presentation_mode_does_not_change_target_expression() -> None:
    path = ROOT / "examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml"
    raw = yaml.safe_load(path.read_text())
    combined = BuyerProblemV2.model_validate(raw)
    raw["output"]["landscape_mode"] = "COMBINED"
    separate = BuyerProblemV2.model_validate(raw)

    assert combined.strategic_gap.target_expression == separate.strategic_gap.target_expression


def test_exact_combination_requires_multiple_targets() -> None:
    with pytest.raises(ValidationError, match="at least two"):
        TargetExpression(
            operator=TargetOperator.EXACT_COMBINATION,
            targets=[TargetTerm(canonical_id="CD19", label="CD19")],
        )


def test_unknown_ontology_terms_abstain() -> None:
    assert normalize_target("TNFRSF17") == "BCMA"
    assert normalize_target("not-a-target") is None
    assert normalize_modality("BiTE") == "T_CELL_ENGAGER"
    assert normalize_modality("unknown format") is None


def test_pass_and_fail_gate_decisions_require_evidence() -> None:
    with pytest.raises(ValidationError, match="fact and claim evidence"):
        GateDecision(
            gate_id="target_logic",
            requirement_id="target.required",
            subject_id="asset:1",
            status=GateStatus.PASS,
            rationale="Target matches.",
        )


def test_unknown_gate_requires_next_action() -> None:
    with pytest.raises(ValidationError, match="next action"):
        GateDecision(
            gate_id="target_logic",
            requirement_id="target.required",
            subject_id="asset:1",
            status=GateStatus.UNKNOWN,
            rationale="Evidence is missing.",
        )


def test_incomplete_run_requires_reason() -> None:
    with pytest.raises(ValidationError, match="at least one reason"):
        RunManifest(
            run_id="run:1",
            problem_id="problem:1",
            problem_version="1",
            as_of_date=date(2026, 7, 10),
            started_at=datetime.now(timezone.utc),
            code_version="test",
            normalization_version="test",
            status=RunStatus.INCOMPLETE,
        )
