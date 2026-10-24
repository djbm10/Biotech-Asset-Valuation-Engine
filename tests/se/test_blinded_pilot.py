"""Blinded pilot scorer. Every reference here is SYNTHETIC test data: these tests check the
scorer's arithmetic and refusals, and say nothing about engine performance."""

from __future__ import annotations

import copy
import json
import os
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from bve.cli.se_pilot import main as cli
from bve.se.evaluation.blinded_pilot import (
    SealReceipt,
    export_candidates,
    preregister,
    score,
    seal,
)
from bve.se.pipeline import SESearchResult
from bve.se.schemas.contracts import (
    CanonicalAsset,
    ExtractedClaim,
    NormalizedFact,
    RunManifest,
    RunStatus,
)

PREREG_DATE = "2026-09-01T12:00:00+00:00"
RUN_STARTED = "2026-10-01T12:00:00+00:00"

SPEC = {
    "spec_id": "s1",
    "therapeutic_area": "synthetic",
    "targets": ["T1"],
    "as_of_date": "2026-10-01",
    "query_text": "synthetic test query",
}
CRITERIA = {
    "criteria_id": "c1",
    "spec_id": "s1",
    "thresholds": {
        "min_precision": 0.2,
        "min_recall": 0.2,
        "max_identity_errors": 5,
        "max_misleading_claims": 5,
    },
}
CANDIDATES = {
    "spec_id": "s1",
    "engine_commit": "abc",
    "run_id": "run-1",
    "run_started_at": RUN_STARTED,
    "candidates": [
        {
            "candidate_id": "c:a",
            "names": ["alphamab", "ALP-106"],
            "target_ids": ["T1"],
            "modality": "bispecific antibody",
            "trial_ids": ["NCT1"],
            "claims": [
                {"kind": "commercial", "field": "owner", "value": "Co A", "citations": ["d1"]},
                {"kind": "scientific", "field": "stage", "value": "phase 3", "citations": []},
            ],
        },
        # Same drug as c:a under an old code: a split identity.
        {"candidate_id": "c:b", "names": ["ALP06"], "target_ids": ["T1"]},
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
                "names": ["alphamab", "ALP106", "ALP-06"],
                "target_ids": ["T1"],
                "modality": "Bispecific Antibody",
                "trial_ids": ["NCT1", "NCT2"],
                "facts": [
                    {"field": "owner", "value": "Co A"},
                    {"field": "stage", "value": "phase 1"},
                ],
            },
            # Missed by the engine; its trial must stay in the overall denominator.
            {"reference_id": "R-B", "names": ["missedmab"], "trial_ids": ["NCT3"]},
            {"reference_id": "R-T", "names": ["trapmab"], "in_scope": False},
        ],
    }


def _git(repo: Path, *args: str, date_: str | None = None) -> None:
    env = os.environ | {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    if date_:
        env |= {"GIT_COMMITTER_DATE": date_, "GIT_AUTHOR_DATE": date_}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def _setup(
    tmp: Path,
    reference: dict,
    *,
    candidates: dict | None = None,
    criteria: dict | None = None,
    prereg_date: str = PREREG_DATE,
    push: bool = True,
) -> dict[str, Path]:
    """A throwaway repo holding a committed prereg, and a reference stored outside it."""
    repo, outside = tmp / "repo", tmp / "analyst"
    repo.mkdir()
    outside.mkdir()
    paths = {
        "repo": repo,
        "spec": repo / "spec.json",
        "criteria": repo / "criteria.json",
        "candidates": repo / "candidates.json",
        "prereg": repo / "prereg.json",
        "reference": outside / "reference.json",
    }
    paths["spec"].write_text(json.dumps(SPEC))
    paths["criteria"].write_text(json.dumps(criteria or CRITERIA))
    paths["prereg"].write_text(preregister(paths["spec"], paths["criteria"]).model_dump_json())
    _git(repo, "init", "-q")
    _git(repo, "add", "spec.json", "criteria.json", "prereg.json")
    _git(repo, "commit", "-q", "-m", "prereg", date_=prereg_date)
    if push:
        remote = tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        _git(repo, "remote", "add", "origin", str(remote))
        _git(repo, "push", "-q", "origin", "HEAD:main")
        _git(repo, "fetch", "-q", "origin")
    paths["candidates"].write_text(json.dumps(candidates or CANDIDATES))
    paths["reference"].write_text(json.dumps(reference))
    return paths


def _seal(paths: dict[str, Path]) -> SealReceipt:
    return seal(
        paths["spec"],
        paths["criteria"],
        paths["candidates"],
        prereg_path=paths["prereg"],
        repo_root=paths["repo"],
    )


def _score(
    paths: dict[str, Path], receipt: SealReceipt | None = None, repo_root: Path | None = None
):
    return score(
        receipt or _seal(paths),
        spec_path=paths["spec"],
        criteria_path=paths["criteria"],
        candidates_path=paths["candidates"],
        reference_path=paths["reference"],
        repo_root=repo_root or paths["repo"],
    )


INDEPENDENT = {"synthetic": False, "independent_of_engine": True}


# ------------------------------------------------------------------- metrics
def test_metrics_and_identity_errors(tmp_path: Path) -> None:
    report = _score(_setup(tmp_path, _reference()))
    assert report.true_positives == ["R-A"]
    assert report.false_negatives == ["R-B"]
    assert report.negative_control_hits == ["R-T"]
    assert report.unadjudicated_candidates == ["c:c"]
    assert report.split_errors == ["R-A"]
    assert report.recall == 0.5
    # One credit for R-A however many candidates it was split into.
    assert report.precision_strict == 0.25
    assert report.precision_adjudicated == pytest.approx(1 / 3)
    assert report.target_accuracy == 1.0 and report.modality_accuracy == 1.0
    assert report.claims_supported == 1 and report.claims_cited == 1
    assert report.misleading_claims == ["c:a:scientific:stage=phase 3"]


def test_trial_coverage_overall_keeps_missed_assets_in_denominator(tmp_path: Path) -> None:
    report = _score(_setup(tmp_path, _reference()))
    # Reference trials: R-A {NCT1, NCT2} (recovered), R-B {NCT3} (missed). Found: NCT1.
    assert report.trial_coverage_overall == pytest.approx(1 / 3)
    assert report.trial_coverage_recovered == 0.5


def test_trial_coverage_when_nothing_is_recovered(tmp_path: Path) -> None:
    cands = copy.deepcopy(CANDIDATES)
    cands["candidates"] = [{"candidate_id": "c:z", "names": ["unrelated"], "trial_ids": ["NCT1"]}]
    report = _score(_setup(tmp_path, _reference(), candidates=cands))
    assert report.trial_coverage_overall == 0.0
    assert report.trial_coverage_recovered is None
    assert report.unreferenced_trials == 0  # trials on unmatched candidates are not attributed


def test_split_identity_trials_are_pooled_once(tmp_path: Path) -> None:
    cands = copy.deepcopy(CANDIDATES)
    cands["candidates"][1]["trial_ids"] = ["NCT2"]
    report = _score(_setup(tmp_path, _reference(), candidates=cands))
    assert report.trial_coverage_recovered == 1.0
    assert report.trial_coverage_overall == pytest.approx(2 / 3)


def test_merge_candidate_does_not_recover_either_asset(tmp_path: Path) -> None:
    ref = _reference()
    ref["assets"][1]["names"] = ["missedmab", "trapmab"]  # c:d now spans R-B and R-T
    report = _score(_setup(tmp_path, ref))
    assert report.merge_errors == ["c:d"]
    assert "R-B" in report.false_negatives
    assert report.precision_strict == 0.25


def test_split_with_conflicting_targets_is_wrong_once(tmp_path: Path) -> None:
    cands = copy.deepcopy(CANDIDATES)
    cands["candidates"][1]["target_ids"] = ["T9"]
    report = _score(_setup(tmp_path, _reference(), candidates=cands))
    assert report.target_accuracy == 0.0  # one reference asset, scored once, wrong


def test_reference_without_value_is_unadjudicable_not_wrong(tmp_path: Path) -> None:
    ref = _reference()
    ref["assets"][0]["modality"] = None
    ref["assets"][0]["target_ids"] = []
    report = _score(_setup(tmp_path, ref))
    assert report.modality_accuracy is None and report.modality_unadjudicable == 1
    assert report.target_accuracy is None and report.target_unadjudicable == 1


def test_unknown_is_reported_both_ways(tmp_path: Path) -> None:
    cands = copy.deepcopy(CANDIDATES)
    cands["candidates"][0]["modality"] = None
    report = _score(_setup(tmp_path, _reference(), candidates=cands))
    assert report.modality_unknown == 1
    assert report.modality_accuracy is None
    assert report.modality_accuracy_incl_unknown == 0.0


# ------------------------------------------------------------------- verdicts
def test_synthetic_reference_never_gets_a_verdict(tmp_path: Path) -> None:
    report = _score(_setup(tmp_path, _reference()))
    assert report.status == "SYNTHETIC_SELF_TEST"
    assert report.passes_thresholds is None


def test_synthetic_flag_wins_even_if_marked_independent(tmp_path: Path) -> None:
    report = _score(_setup(tmp_path, _reference(independent_of_engine=True)))
    assert report.status == "SYNTHETIC_SELF_TEST" and report.passes_thresholds is None


def test_non_independent_reference_stays_unvalidated(tmp_path: Path) -> None:
    report = _score(_setup(tmp_path, _reference(synthetic=False)))
    assert report.status == "UNVALIDATED" and report.passes_thresholds is None


def test_unpushed_preregistration_stays_unvalidated(tmp_path: Path) -> None:
    report = _score(_setup(tmp_path, _reference(**INDEPENDENT), push=False))
    assert report.status == "UNVALIDATED" and report.passes_thresholds is None


def test_independent_pushed_reference_gets_a_verdict(tmp_path: Path) -> None:
    report = _score(_setup(tmp_path, _reference(**INDEPENDENT)))
    assert report.status == "SCORED_AGAINST_SUPPLIED_REFERENCE"
    assert "does not verify" in report.status_note
    assert report.passes_thresholds is True


def test_uncomputable_metric_fails_a_positive_threshold(tmp_path: Path) -> None:
    ref = _reference(**INDEPENDENT)
    for asset in ref["assets"]:
        asset["trial_ids"] = []
    crit = copy.deepcopy(CRITERIA)
    crit["thresholds"]["min_trial_coverage"] = 0.1
    report = _score(_setup(tmp_path, ref, criteria=crit))
    assert report.trial_coverage_overall is None
    assert report.passes_thresholds is False


# ------------------------------------------------------------------- preregistration
def test_preregistration_after_run_is_refused(tmp_path: Path) -> None:
    paths = _setup(tmp_path, _reference(), prereg_date="2026-10-02T00:00:00+00:00")
    with pytest.raises(ValueError, match="does not predate"):
        _seal(paths)


def test_uncommitted_preregistration_is_refused(tmp_path: Path) -> None:
    paths = _setup(tmp_path, _reference())
    body = json.loads(paths["prereg"].read_text())
    paths["prereg"].write_text(json.dumps(body | {"created_at": "2025-01-01T00:00:00Z"}))
    with pytest.raises(ValueError, match="not committed"):
        _seal(paths)


def test_spec_edited_after_preregistration_is_refused(tmp_path: Path) -> None:
    paths = _setup(tmp_path, _reference())
    paths["spec"].write_text(json.dumps(SPEC | {"query_text": "changed"}))
    with pytest.raises(ValueError, match="differ from what was preregistered"):
        _seal(paths)


def test_receipt_records_preregistration(tmp_path: Path) -> None:
    receipt = _seal(_setup(tmp_path, _reference()))
    assert receipt.prereg_on_remote is True
    assert receipt.prereg_committed_at < receipt.run_started_at
    assert len(receipt.prereg_commit) == 40


# ------------------------------------------------------------------- tamper / isolation
@pytest.mark.parametrize("name", ["candidates", "criteria", "spec"])
def test_files_changed_after_seal_are_refused(tmp_path: Path, name: str) -> None:
    paths = _setup(tmp_path, _reference())
    receipt = _seal(paths)
    paths[name].write_text(paths[name].read_text() + "\n")
    with pytest.raises(ValueError, match=f"{name} changed"):
        _score(paths, receipt)


def test_reference_inside_repo_is_refused(tmp_path: Path) -> None:
    paths = _setup(tmp_path, _reference())
    with pytest.raises(ValueError, match="inside the engine repository"):
        _score(paths, repo_root=tmp_path)


def test_mismatched_spec_ids_refused(tmp_path: Path) -> None:
    cands = CANDIDATES | {"spec_id": "other"}
    with pytest.raises(ValueError, match="share one spec_id"):
        _seal(_setup(tmp_path, _reference(), candidates=cands))


def test_prereg_seal_and_export_commands_accept_no_reference() -> None:
    for cmd in ("prereg", "seal", "export"):
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


def test_cli_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _setup(tmp_path, _reference())
    monkeypatch.chdir(paths["repo"])
    receipt, out = tmp_path / "receipt.json", tmp_path / "report.json"
    common = [
        "--spec",
        str(paths["spec"]),
        "--criteria",
        str(paths["criteria"]),
        "--candidates",
        str(paths["candidates"]),
    ]
    assert cli(["seal", *common, "--prereg", str(paths["prereg"]), "--out", str(receipt)]) == 0
    assert (
        cli(
            [
                "score",
                "--receipt",
                str(receipt),
                *common,
                "--reference",
                str(paths["reference"]),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    body = json.loads(out.read_text())
    assert body["status"] == "SYNTHETIC_SELF_TEST" and body["passes_thresholds"] is None


def test_cli_prereg_writes_hashes(tmp_path: Path) -> None:
    (tmp_path / "spec.json").write_text(json.dumps(SPEC))
    (tmp_path / "criteria.json").write_text(json.dumps(CRITERIA))
    out = tmp_path / "prereg.json"
    assert (
        cli(
            [
                "prereg",
                "--spec",
                str(tmp_path / "spec.json"),
                "--criteria",
                str(tmp_path / "criteria.json"),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    assert len(json.loads(out.read_text())["spec_sha256"]) == 64


def test_export_from_engine_result() -> None:
    started = datetime(2026, 10, 1, 9, tzinfo=UTC)
    result = SESearchResult(
        problem_id="p",
        run_manifest=RunManifest(
            run_id="r",
            problem_id="p",
            problem_version="1",
            as_of_date=date(2026, 10, 1),
            started_at=started,
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
                target_ids=["T1"],
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
    assert export.run_id == "r" and export.run_started_at == started
    cand = export.candidates[0]
    assert cand.names == ["X-1", "X1"] and cand.trial_ids == ["NCT9"]
    assert cand.claims[0].kind == "commercial" and cand.claims[0].citations == ["doc1"]


def test_export_strips_engine_target_namespace() -> None:
    """The engine writes ``TARGET:GUCY2C``; references use the bare HGNC symbol.

    Found in pilot gucy2c_oncology_v1: unstripped, every correct target scored as wrong.
    """
    result = SESearchResult(
        problem_id="p",
        run_manifest=RunManifest(
            run_id="r",
            problem_id="p",
            problem_version="1",
            as_of_date=date(2026, 10, 1),
            started_at=datetime(2026, 10, 1, 9, tzinfo=UTC),
            code_version="t",
            normalization_version="t",
            ontology_version="t",
            status=RunStatus.CONVERGED,
        ),
        candidates=[
            CanonicalAsset(
                asset_id="a1", canonical_name="X-1", target_ids=["TARGET:GUCY2C", "CD3E"]
            )
        ],
    )
    export = export_candidates(result, spec_id="s1", engine_commit="abc")
    assert export.candidates[0].target_ids == ["GUCY2C", "CD3E"]
