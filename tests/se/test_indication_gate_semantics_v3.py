"""Frozen positive-only indication gate contract, without acquisition."""
import hashlib
import json
from pathlib import Path

import pytest

from bve.se.gates.engine import _requirement
from bve.se.gates.evaluator import evaluate_indication
from bve.se.schemas.contracts import NormalizedFact, RequirementOperator

ROOT = Path(__file__).resolve().parents[2]
POP = json.loads((ROOT / "research/se_indication_gate_semantics_v3/population.json").read_text())


@pytest.mark.parametrize("case", POP["controls"], ids=lambda case: case["id"])
def test_frozen_control(case):
    facts = [NormalizedFact(fact_id=f"f:{i}", subject_id="a", fact_type="indication",
             value=value, confidence=.95, supporting_claim_ids=[f"c:{i}"])
             for i, value in enumerate(case["observed"])]
    decision = evaluate_indication(
        _requirement("strategy.indication", "indication", RequirementOperator.IN, case["requested"]),
        subject_id="a", facts=facts, gate_id="strategic_sandbox",
    )
    assert decision.status.value == case["expected"]


def test_frozen_compilation_and_source_isolation():
    for path, digest in POP["protected_source"].items():
        if path not in POP["allowed_source"]:
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
