from __future__ import annotations

import json
from pathlib import Path

import pytest

from bve.se.evaluation.holdout import HoldoutCase, predict_case, predict_holdout


ROOT = Path(__file__).resolve().parents[2]
V3 = ROOT / "research/se_benchmarks/cd19_bcma/development/v3_failure_analysis"


def _case(
    case_id: str,
    *,
    target: str = "EGFR",
    modality: str = "monoclonal antibody",
    source_text: str,
    required_buyer_capability: str | None = None,
    buyer_capabilities: list[str] | None = None,
) -> HoldoutCase:
    return HoldoutCase(
        case_id=case_id,
        target=target,
        modality=modality,
        source_text=source_text,
        required_buyer_capability=required_buyer_capability,
        buyer_capabilities=buyer_capabilities,
    )


FULL_SUPPORT = (
    "A randomized phase 2 trial of an EGFR monoclonal antibody enrolled 24 patients and "
    "reported confirmed responses, dose cohorts, and treatment-emergent safety events."
)


@pytest.mark.parametrize(
    ("category", "case", "expected", "decisive_gate"),
    [
        ("target", _case("target-pass", source_text=FULL_SUPPORT), "INCLUDE", None),
        (
            "target",
            _case(
                "target-fail",
                source_text=(
                    "The phase 2 monoclonal antibody is confirmed to target HER2 rather than EGFR; "
                    "20 patients had response and safety assessments."
                ),
            ),
            "EXCLUDE",
            "target_match",
        ),
        (
            "target",
            _case(
                "target-unknown",
                source_text=(
                    "A phase 2 monoclonal antibody trial enrolled 20 patients and reported "
                    "responses, but the target is not identified."
                ),
            ),
            "UNKNOWN",
            "target_match",
        ),
        (
            "modality",
            _case(
                "modality-pass",
                target="CD19",
                modality="bispecific T-cell engager",
                source_text=(
                    "A phase 1 CD19 bispecific T-cell engager treated 18 patients and reported "
                    "responses, dose cohorts, and safety events."
                ),
            ),
            "INCLUDE",
            None,
        ),
        (
            "modality",
            _case(
                "modality-fail",
                target="CD19",
                modality="CAR-T",
                source_text=(
                    "A phase 2 CD19 monoclonal antibody treated 22 patients and reported responses; "
                    "the report provides no evidence involving a CAR-T product."
                ),
            ),
            "EXCLUDE",
            "modality_match",
        ),
        (
            "modality",
            _case(
                "modality-unknown",
                target="CD19",
                modality="CAR-T",
                source_text=(
                    "A phase 1 CD19 program treated 17 patients and reported responses, but the "
                    "intervention modality remains unclear."
                ),
            ),
            "UNKNOWN",
            "modality_match",
        ),
        (
            "buyer_capability",
            _case(
                "capability-pass",
                source_text=FULL_SUPPORT,
                required_buyer_capability="antibody manufacturing",
                buyer_capabilities=["antibody manufacturing", "clinical operations"],
            ),
            "INCLUDE",
            None,
        ),
        (
            "buyer_capability",
            _case(
                "capability-fail",
                source_text=FULL_SUPPORT,
                required_buyer_capability="antibody manufacturing",
                buyer_capabilities=["small-molecule chemistry"],
            ),
            "EXCLUDE",
            "buyer_capability",
        ),
        (
            "buyer_capability",
            _case(
                "capability-unknown",
                source_text=FULL_SUPPORT,
                required_buyer_capability="antibody manufacturing",
            ),
            "UNKNOWN",
            "buyer_capability",
        ),
        ("evidence_threshold", _case("evidence-pass", source_text=FULL_SUPPORT), "INCLUDE", None),
        (
            "evidence_threshold",
            _case(
                "evidence-fail",
                source_text=(
                    "An EGFR monoclonal antibody reduced tumor volume in a mouse xenograft. "
                    "No human exposure or regulator-origin evidence is presented."
                ),
            ),
            "EXCLUDE",
            "evidence_provenance",
        ),
        (
            "evidence_threshold",
            _case(
                "evidence-unknown",
                source_text=(
                    "A conference sentence says patients responded to an EGFR monoclonal antibody "
                    "but omits the number, population, dose, and response definition."
                ),
            ),
            "UNKNOWN",
            "evidence_threshold",
        ),
        ("missing_evidence", _case("missing-pass", source_text=FULL_SUPPORT), "INCLUDE", None),
        (
            "missing_evidence",
            _case(
                "missing-fail",
                source_text=(
                    "An EGFR monoclonal antibody was evaluated only in cultured tumor cells in "
                    "vitro, with no human results."
                ),
            ),
            "EXCLUDE",
            "evidence_provenance",
        ),
        (
            "missing_evidence",
            _case(
                "missing-unknown",
                source_text="An EGFR monoclonal antibody was evaluated; outcomes are not present.",
            ),
            "UNKNOWN",
            "evidence_provenance",
        ),
    ],
)
def test_balanced_adversarial_gate_outcomes(
    category: str,
    case: HoldoutCase,
    expected: str,
    decisive_gate: str | None,
) -> None:
    prediction = predict_case(case)
    assert prediction.disposition == expected, category
    assert prediction.gates
    assert all(gate.evidence and gate.reason for gate in prediction.gates)
    assert prediction.reason
    if decisive_gate:
        decisive_status = "FAIL" if expected == "EXCLUDE" else "UNKNOWN"
        assert any(
            gate.gate == decisive_gate and gate.status == decisive_status
            for gate in prediction.gates
        )
    else:
        assert all(gate.status == "PASS" for gate in prediction.gates)


def test_v3_open_failure_analysis_is_a_complete_regression() -> None:
    labels = {
        row["case_id"]: row["disposition"]
        for row in (
            json.loads(line) for line in (V3 / "labels.jsonl").read_text().splitlines()
        )
    }
    predictions = predict_holdout(V3 / "cases.jsonl")

    assert len(predictions) == 36
    assert {prediction.case_id for prediction in predictions} == set(labels)
    assert {
        prediction.case_id: prediction.disposition for prediction in predictions
    } == labels
    assert all(prediction.gates and prediction.reason for prediction in predictions)
