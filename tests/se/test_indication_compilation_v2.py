"""Compilation-only regression contracts, with gate compatibility kept frozen."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def result():
    path = Path(__file__).resolve().parents[2] / "scripts/score_indication_compilation_v2.py"
    spec = importlib.util.spec_from_file_location("compilation_v2_score", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.score()


@pytest.mark.parametrize("criterion", ["C1", "C2", "C3", "C4", "C5", "C6", "C7"])
def test_frozen_compilation_contract(result, criterion):
    assert result["criteria"][criterion], [
        (r["id"], r["after"], r["expected"], r["spans"])
        for r in result["records"] if not r["exact"]
    ]


def test_no_parser_retrieval_or_gate_mutation(result):
    assert result["sealed"]
    assert result["protected_source"]
    assert result["gate_controls_unchanged"]
    assert result["JCAR014"]["status"] == "PASS"
    assert all(r["isolation"] and r["offsets"] for r in result["records"])
