"""Blinded pilot scorer. All references here are SYNTHETIC: they test the scorer only."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from bve.cli.se_pilot import main as cli
from bve.se.evaluation.blinded_pilot import export_candidates, score, seal
from bve.se.pipeline import SESearchResult
from bve.se.schemas.contracts import (
    CanonicalAsset,
    ExtractedClaim,
    NormalizedFact,
    RunManifest,
    RunStatus,
)

SPEC = {
    "spec_id": "s1",
    "therapeutic_area": "autoimmune",
    "targets": ["CD19"],
    "as_of_date": "2026-10-01",
    "query_text": "CD19 T-cell engagers in autoimmune disease",
}
CRITERIA = {
    "criteria_id": "c1",
    "spec_id": "s1",
    "thresholds": {"min_precision": 0.5, "min_recall": 0.5, "max_identity_errors": 0},
}
CANDIDATES = {
    "spec_id": "s1",
    "engine_commit": "abc",
    "candidates": [
        {
            "candidate_id": "c:a",
            "names": ["cizutamig", "CND-106"],
            "target_ids": ["CD19"],
            "modality": "bispecific antibody",
            "trial_ids": ["NCT1"],
            "claims": [
                {"kind": "commercial", "field": "owner", "value": "UCB", "citations": ["d1"]},
                {"kind": "scientific", "field": "stage", "value": "phase 3", "citations": []},
            ],
        },
        {"candidate_id": "c:b", "names": ["EMB06"], "target_ids": ["CD19"]},
        {"candidate_id": "c:c", "names": ["frontline"]},
        {"candidate_id": "c:d", "names": ["trapmab"]},
    ],
}


def _reference(**prov: object) -> dict:
    provenance = {
        "prepared_by": "synthetic fixture",
        "prepared_on": "2026-10-01",
        "method": "hand-written test data",
        "independent_of_engine": False,
        "synthetic": True,
    } | prov
    return {
        "reference_id": "r1",
        "spec_id": "s1",
        "provenance": provenance,
        "assets": [
            {
                "reference_id": "R-A",
                "names": ["cizutamig", "CND106", "EMB-06"],
                "target_ids": ["CD19"],
                "modality": "Bispecific Antibody",
                "trial_ids": ["NCT1", "NCT2"],
                "facts": [
                    {"field": "owner", "value": "UCB"},
                    {"field": "stage", "value": "phase 1"},
                ],
            },
            {"reference_id": "R-B", "names": ["missedmab"]},
            {"reference_id": "R-T", "names": ["trapmab"], "in_scope": False},
        ],
    }


def _write(tmp: Path, reference: dict) -> dict[str, Path]:
    paths = {}
    for name, body in [
        ("spec", SPEC),
        ("criteria", CRITERIA),
        ("candidates", CANDIDATES),
        ("reference", reference),
    ]:
        paths[name] = tmp / f"{name}.json"
        paths[name].write_text(json.dumps(body))
    return paths


def _score(paths: dict[str, Path], repo_root: Path | None = None):
    receipt = seal(paths["spec"], paths["criteria"], paths["candidates"])
    return score(
        receipt,
        spec_path=paths["spec"],
        criteria_path=paths["criteria"],
        candidates_path=paths["candidates"],
        reference_path=paths["reference"],
        repo_root=repo_root,
    )


def test_metrics_and_identity_errors(tmp_path: Path) -> None:
    report = _score(_write(tmp_path, _reference()))
    assert report.status == "SYNTHETIC_SELF_TEST"
    assert report.true_positives == ["R-A"]
    assert report.false_negatives == ["R-B"]
    assert report.negative_control_hits == ["R-T"]
    assert report.unadjudicated_candidates == ["c:c"]
    assert report.split_errors == ["R-A"]  # c:a and c:b are the same drug, not merged
    assert report.recall == 0.5
    assert report.precision_strict == 0.5  # c:a, c:b match in-scope R-A; 4 candidates
    assert report.precision_adjudicated == pytest.approx(2 / 3)
    assert report.target_accuracy == 1.0
    assert report.modality_accuracy == 1.0 and report.modality_unknown == 1
    assert report.trial_coverage == 0.5  # NCT1+NCT2 per hit, NCT1 found once
    assert report.claims_supported == 1 and report.claims_cited == 1
    assert report.misleading_claims == ["c:a:scientific:stage=phase 3"]
    assert report.passes_thresholds is False


def test_merge_error_when_one_candidate_spans_two_references(tmp_path: Path) -> None:
    ref = _reference()
    ref["assets"][1]["names"] = ["missedmab", "frontline"]
    ref["assets"][0]["names"] = ["cizutamig", "CND106", "EMB-06", "trapmab"]
    report = _score(_write(tmp_path, ref))
    assert "c:d" in report.merge_errors


def test_non_independent_reference_stays_unvalidated(tmp_path: Path) -> None:
    report = _score(_write(tmp_path, _reference(synthetic=False, independent_of_engine=False)))
    assert report.status == "UNVALIDATED"
    assert report.passes_thresholds is None


def test_independent_reference_is_scored_but_not_called_validated(tmp_path: Path) -> None:
    report = _score(_write(tmp_path, _reference(synthetic=False, independent_of_engine=True)))
    assert report.status == "SCORED_AGAINST_SUPPLIED_REFERENCE"
    assert "does not verify" in report.status_note


def test_candidates_changed_after_seal_are_refused(tmp_path: Path) -> None:
    paths = _write(tmp_path, _reference())
    receipt = seal(paths["spec"], paths["criteria"], paths["candidates"])
    paths["candidates"].write_text(
        paths["candidates"].read_text().replace("frontline", "missedmab")
    )
    with pytest.raises(ValueError, match="candidates changed"):
        score(
            receipt,
            spec_path=paths["spec"],
            criteria_path=paths["criteria"],
            candidates_path=paths["candidates"],
            reference_path=paths["reference"],
            repo_root=None,
        )


def test_criteria_changed_after_seal_are_refused(tmp_path: Path) -> None:
    paths = _write(tmp_path, _reference())
    receipt = seal(paths["spec"], paths["criteria"], paths["candidates"])
    paths["criteria"].write_text(paths["criteria"].read_text().replace("0.5", "0.1"))
    with pytest.raises(ValueError, match="criteria changed"):
        score(
            receipt,
            spec_path=paths["spec"],
            criteria_path=paths["criteria"],
            candidates_path=paths["candidates"],
            reference_path=paths["reference"],
            repo_root=None,
        )


def test_reference_inside_repo_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="inside the engine repository"):
        _score(_write(tmp_path, _reference()), repo_root=tmp_path)


def test_mismatched_spec_ids_refused(tmp_path: Path) -> None:
    paths = _write(tmp_path, _reference())
    paths["criteria"].write_text(json.dumps(CRITERIA | {"spec_id": "other"}))
    with pytest.raises(ValueError, match="share one spec_id"):
        seal(paths["spec"], paths["criteria"], paths["candidates"])


def test_seal_and_export_commands_accept_no_reference() -> None:
    for cmd in ("seal", "export"):
        with pytest.raises(SystemExit):
            cli([cmd, "--reference", "x"])


def test_only_the_scorer_reads_reference_types() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "bve"
    allowed = {root / "se" / "evaluation" / "blinded_pilot.py", root / "cli" / "se_pilot.py"}
    offenders = [
        str(p)
        for p in root.rglob("*.py")
        if p not in allowed
        and ("ReferenceDataset" in p.read_text() or "blinded_pilot" in p.read_text())
    ]
    assert offenders == []


def test_cli_end_to_end(tmp_path: Path) -> None:
    paths = _write(tmp_path, _reference())
    receipt = tmp_path / "receipt.json"
    out = tmp_path / "report.json"
    assert (
        cli(
            [
                "seal",
                "--spec",
                str(paths["spec"]),
                "--criteria",
                str(paths["criteria"]),
                "--candidates",
                str(paths["candidates"]),
                "--out",
                str(receipt),
            ]
        )
        == 0
    )
    assert (
        cli(
            [
                "score",
                "--receipt",
                str(receipt),
                "--spec",
                str(paths["spec"]),
                "--criteria",
                str(paths["criteria"]),
                "--candidates",
                str(paths["candidates"]),
                "--reference",
                str(paths["reference"]),
                "--out",
                str(out),
                "--allow-reference-in-repo",
            ]
        )
        == 0
    )
    assert json.loads(out.read_text())["status"] == "SYNTHETIC_SELF_TEST"


def test_export_from_engine_result() -> None:
    result = SESearchResult(
        problem_id="p",
        run_manifest=RunManifest(
            run_id="r",
            problem_id="p",
            problem_version="1",
            as_of_date=date(2026, 10, 1),
            started_at=datetime.now(UTC),
            code_version="t",
            normalization_version="t",
            ontology_version="t",
            status=RunStatus.CONVERGED,
        ),
        candidates=[
            CanonicalAsset(
                asset_id="a1",
                canonical_name="X-1",
                aliases=["X1"],
                target_ids=["CD19"],
                trial_ids=["NCT9"],
            )
        ],
        claims=[
            ExtractedClaim(
                claim_id="cl1",
                subject_id="a1",
                predicate="owner",
                normalized_value="Co",
                source_document_id="doc1",
                supporting_passage="p",
                extractor_version="t",
                extraction_method="t",
                extraction_confidence=0.9,
                applicable_as_of_date=date(2026, 10, 1),
            )
        ],
        facts=[
            NormalizedFact(
                fact_id="f1",
                subject_id="a1",
                fact_type="owner",
                value="Co",
                supporting_claim_ids=["cl1"],
                confidence=0.9,
            )
        ],
    )
    export = export_candidates(result, spec_id="s1", engine_commit="abc")
    cand = export.candidates[0]
    assert cand.names == ["X-1", "X1"] and cand.trial_ids == ["NCT9"]
    assert cand.claims[0].kind == "commercial" and cand.claims[0].citations == ["doc1"]
