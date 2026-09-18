"""One command, one directory: what a user gets without knowing the pipeline's stages.

Before ``--output-dir``, producing a readable, auditable, reproducible run meant passing
``--emit-problem``, ``--output``, ``--format`` twice, ``--acquisition-ledger``,
``--custody-root`` and ``--snapshot-dir`` -- six flags whose names are internal stage
vocabulary. These tests pin the wiring: the layout is deterministic, the artifacts survive
a run that ends UNSCOREABLE, the summary says what the run actually was, and nothing in it
promotes a status the engine did not report.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from unittest import mock

import pytest
import yaml

from bve.cli import se_search
from bve.se.pipeline import SESearchResult
from bve.se.schemas.contracts import BuyerProblemV2, RunManifest, RunStatus


def _problem() -> BuyerProblemV2:
    return BuyerProblemV2.model_validate(
        {
            "schema_version": "se_buyer_problem_v2",
            "problem_id": "test_run_directory",
            "version": "1.0.0",
            "buyer": {"buyer_id": "b", "name": "B", "as_of_date": "2026-08-20"},
            "strategic_gap": {
                "therapeutic_areas": ["oncology"],
                "indications": [],
                "target_expression": {
                    "operator": "ANY",
                    "targets": [{"canonical_id": "PDCD1", "label": "PDCD1", "aliases": []}],
                },
                "modalities": ["MONOCLONAL_ANTIBODY"],
                "required_biology": [],
                "capability_constraints": {},
                "evidence_floor": {
                    "minimum_stage": "PHASE_1",
                    "human_poc_required": True,
                    "required_evidence_types": ["HUMAN_CLINICAL_RESULT"],
                },
                "clinical_effect_bar": {},
                "acceptable_deal_routes": ["LICENSE"],
                "geographic_rights_requirements": [],
                "missing_evidence_policy": "REVIEW",
            },
            "output": {"landscape_mode": "SEPARATE", "group_by": "COHORT"},
            "ranking_cohort_required": True,
        }
    )


def _result(*, status: RunStatus, fatal: list[str], incomplete: list[str]) -> SESearchResult:
    if status is not RunStatus.CONVERGED and not incomplete:
        # The manifest refuses to record an unexplained incomplete run, which is the point.
        incomplete = ["clinicaltrials_gov: acquisition did not converge"]
    return SESearchResult(
        problem_id="test_run_directory",
        run_manifest=RunManifest(
            run_id="run:test",
            problem_id="test_run_directory",
            problem_version="1.0.0",
            as_of_date=date(2026, 8, 20),
            started_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
            completed_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
            code_version="test",
            normalization_version="test",
            status=status,
            incomplete_reasons=incomplete,
            fatal_reasons=fatal,
            known_blind_spots=["conference_asco: no licence"],
        ),
    )


def _run(tmp_path, *extra, status=RunStatus.CONVERGED, fatal=(), incomplete=()):
    problem = tmp_path / "p.yaml"
    problem.write_text(yaml.safe_dump(_problem().model_dump(mode="json")))
    out_dir = tmp_path / "runs" / "one"
    result = _result(status=status, fatal=list(fatal), incomplete=list(incomplete))
    with mock.patch.object(se_search, "run_landscape_search", lambda *a, **k: result):
        code = se_search.main(
            ["--problem", str(problem), "--output-dir", str(out_dir), *extra]
        )
    return code, out_dir


class TestOneCommandLeavesAWholeRun:
    def test_every_declared_artifact_is_written(self, tmp_path) -> None:
        code, out_dir = _run(tmp_path)

        assert code == 0
        for name in (
            "result.json",
            "shortlist.txt",
            "shortlist.json",
            "memo.md",
            "run_manifest.json",
            "acquisition_ledger.jsonl",
            "summary.txt",
            "summary.json",
            "reproduce.sh",
            "logs/run.log",
        ):
            assert (out_dir / name).exists(), f"{name} missing from the run directory"

    def test_the_two_shortlist_views_are_the_same_object(self, tmp_path) -> None:
        _, out_dir = _run(tmp_path)

        payload = json.loads((out_dir / "shortlist.json").read_text())
        assert payload["run_id"] == "run:test"
        assert payload["run_status"] == RunStatus.CONVERGED.value
        assert RunStatus.CONVERGED.value in (out_dir / "shortlist.txt").read_text()

    def test_the_reproduce_command_is_the_command_that_ran(self, tmp_path) -> None:
        _, out_dir = _run(tmp_path, "--top", "3")

        script = (out_dir / "reproduce.sh").read_text()
        assert "bve-se-search" in script
        assert "--output-dir" in script
        assert "--top 3" in script

    def test_an_explicit_flag_still_wins_over_the_directory_default(self, tmp_path) -> None:
        chosen = tmp_path / "elsewhere.json"
        _, out_dir = _run(tmp_path, "--output", str(chosen))

        assert chosen.exists(), "--output must not be overridden by --output-dir"
        # ...and the directory is still whole, so the choice costs nothing.
        assert (out_dir / "result.json").exists()


class TestAFailedRunIsStillReadable:
    """The run someone most needs the artifacts of is the one that did not finish."""

    def test_an_unscoreable_run_leaves_its_artifacts(self, tmp_path) -> None:
        code, out_dir = _run(
            tmp_path,
            status=RunStatus.INCOMPLETE,
            fatal=["mandatory source failures: clinicaltrials_gov (1 queries failed)"],
        )

        assert code == 3
        assert (out_dir / "result.json").exists()
        assert (out_dir / "shortlist.txt").exists()
        summary = json.loads((out_dir / "summary.json").read_text())
        assert summary["exit_code"] == 3
        assert summary["fatal_reasons"]
        assert "UNSCOREABLE" in (out_dir / "summary.txt").read_text()

    def test_an_incomplete_run_says_so_rather_than_claiming_convergence(self, tmp_path) -> None:
        code, out_dir = _run(
            tmp_path,
            status=RunStatus.INCOMPLETE,
            incomplete=["sec_edgar: not configured"],
        )

        assert code == 2
        summary = json.loads((out_dir / "summary.json").read_text())
        assert summary["run_status"] == RunStatus.INCOMPLETE.value
        assert summary["incomplete_reasons"] == ["sec_edgar: not configured"]

    def test_the_log_survives_the_run(self, tmp_path) -> None:
        _, out_dir = _run(
            tmp_path,
            "--allow-incomplete",
            status=RunStatus.INCOMPLETE,
            fatal=["mandatory source failures: clinicaltrials_gov (1 queries failed)"],
        )

        assert "UNSCOREABLE" in (out_dir / "logs" / "run.log").read_text(), (
            "the stderr explanation of a failed run must outlive the terminal"
        )


class TestTheSummaryClaimsNothingExtra:
    def test_convergence_is_labelled_live_and_not_merely_converged(self, tmp_path) -> None:
        _, out_dir = _run(tmp_path)

        summary = json.loads((out_dir / "summary.json").read_text())
        assert summary["convergence_mode"] == "LIVE"
        assert "re-issued to the live sources" in summary["convergence_meaning"]
        assert "must not be scored as live convergence" in summary["convergence_meaning"]

    def test_the_summary_carries_the_counts_and_blind_spots(self, tmp_path) -> None:
        _, out_dir = _run(tmp_path)

        summary = json.loads((out_dir / "summary.json").read_text())
        assert set(summary["counts"]) >= {"eligible", "review", "excluded", "low_support"}
        assert summary["blind_spots"] == ["conference_asco: no licence"]
        assert summary["artifacts"]["shortlist"] == "shortlist.txt"

    def test_no_entry_carries_a_score(self, tmp_path) -> None:
        """Nothing in this workflow may invent a ranking number to fill a column."""

        _, out_dir = _run(tmp_path)

        summary = json.loads((out_dir / "summary.json").read_text())
        assert all("score" not in entry for entry in summary["top"])

    def test_the_summary_is_printed_not_only_filed(self, tmp_path, capsys) -> None:
        _run(tmp_path)

        out = capsys.readouterr().out
        assert "=== S&E run run:test ===" in out
        assert "artifacts in" in out
        assert "elapsed:" in out


class TestNothingElseMoved:
    def test_without_the_flag_stdout_is_still_the_rendered_result(self, tmp_path, capsys) -> None:
        problem = tmp_path / "p.yaml"
        problem.write_text(yaml.safe_dump(_problem().model_dump(mode="json")))
        result = _result(status=RunStatus.CONVERGED, fatal=[], incomplete=[])

        with mock.patch.object(se_search, "run_landscape_search", lambda *a, **k: result):
            code = se_search.main(["--problem", str(problem)])

        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["problem_id"] == "test_run_directory"


@pytest.mark.parametrize("status", [RunStatus.CONVERGED, RunStatus.INCOMPLETE])
def test_the_directory_layout_does_not_depend_on_the_outcome(tmp_path, status) -> None:
    _, out_dir = _run(tmp_path, "--allow-incomplete", status=status)

    names = {path.name for path in out_dir.iterdir()}
    assert {"result.json", "shortlist.txt", "summary.json", "reproduce.sh"} <= names
