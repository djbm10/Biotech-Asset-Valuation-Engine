from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
    SourceProvenance,
)
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.ontology.targets import (
    normalize_modality,
    normalize_target,
    reset_resolver_cache,
)
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


def test_unknown_ontology_terms_abstain(tmp_path, monkeypatch) -> None:
    """Target normalization abstains without a snapshot and uses HGNC symbols with one.

    The former stub mapped ``TNFRSF17`` to ``BCMA``; that inverted HGNC convention,
    where ``TNFRSF17`` is the approved symbol and ``BCMA`` the synonym.
    """

    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "absent"))
    reset_resolver_cache()
    assert normalize_target("TNFRSF17") is None

    OntologySnapshot(
        sources=[
            SourceProvenance(
                source="open_targets",
                release="26.06",
                retrieved_at=date(2026, 8, 15),
                locator="ftp://example.invalid/target",
            )
        ],
        records=[
            SourceEntityRecord(
                source="open_targets",
                source_id="ENSG00000048462",
                entity_type=EntityType.TARGET,
                canonical_symbol="TNFRSF17",
                aliases=[SourceAlias(value="BCMA", alias_type=AliasType.SYNONYM)],
                xrefs={"uniprot": ["Q02223"]},
            )
        ],
    ).write(tmp_path / "snap")
    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "snap"))
    reset_resolver_cache()
    try:
        assert normalize_target("BCMA") == "TNFRSF17"
        assert normalize_target("not-a-target") is None
    finally:
        reset_resolver_cache()

    # Modality is an in-repo controlled vocabulary, so it resolves without a snapshot.
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
