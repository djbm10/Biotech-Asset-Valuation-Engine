"""Scoring is fail-closed on the entity layer; interactive search is not.

The asymmetry is the point. A run without an ontology snapshot resolves targets from the
aliases someone typed into the buyer problem, so its recall measures the problem author,
not the system. Production search may still run that way and say so. A benchmark number
may not be produced that way at all.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml

from bve.cli.se_evaluate import main as evaluate_main
from bve.se.evaluation.benchmark import evaluate_reference_landscape
from bve.se.evaluation.discovery_coverage import evaluate_discovery_coverage
from bve.se.evaluation.ontology_gate import (
    OntologySnapshotRequired,
    require_scoreable_ontology,
)
from bve.se.pipeline import SESearchResult
from bve.se.schemas.contracts import CanonicalAsset, RunManifest, RunStatus

PINNED = "chembl_36__open_targets_26.06__resolver_v1__modality_v2"


def _manifest(ontology_version: str | None) -> RunManifest:
    return RunManifest(
        run_id="run:1",
        problem_id="p",
        problem_version="1",
        as_of_date=date(2026, 7, 12),
        started_at=datetime.now(timezone.utc),
        code_version="test",
        normalization_version="test",
        ontology_version=ontology_version,
        status=RunStatus.CONVERGED,
    )


def _result(ontology_version: str | None) -> SESearchResult:
    return SESearchResult(
        problem_id="p",
        run_manifest=_manifest(ontology_version),
        candidates=[CanonicalAsset(asset_id="asset:a", canonical_name="Asset A")],
    )


def _benchmark(tmp_path: Path) -> Path:
    path = tmp_path / "benchmark.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "status": "development",
                "records": [{"canonical_asset": "Asset A", "expected_candidate": True}],
            }
        )
    )
    return path


def _reference_universe(tmp_path: Path) -> Path:
    path = tmp_path / "reference.csv"
    path.write_text("canonical_asset,aliases,tier\nAsset A,Asset A,GOLD\n")
    return path


class TestGuard:
    def test_pinned_version_passes_through(self) -> None:
        assert require_scoreable_ontology(_manifest(PINNED), reference_set="dev") == PINNED

    @pytest.mark.parametrize(
        "version", [None, "no_snapshot__modality_v2", "no_snapshot"]
    )
    def test_absent_snapshot_refuses(self, version: str | None) -> None:
        with pytest.raises(OntologySnapshotRequired):
            require_scoreable_ontology(_manifest(version), reference_set="dev")

    def test_the_message_names_the_run_and_the_reference_set(self) -> None:
        with pytest.raises(OntologySnapshotRequired) as raised:
            require_scoreable_ontology(_manifest(None), reference_set="pdcd1_dev")
        assert "run:1" in str(raised.value)
        assert "pdcd1_dev" in str(raised.value)


class TestScoringEntrypoints:
    def test_reference_landscape_refuses_without_a_snapshot(self, tmp_path: Path) -> None:
        with pytest.raises(OntologySnapshotRequired):
            evaluate_reference_landscape(
                _benchmark(tmp_path),
                _result("no_snapshot__modality_v2"),
                reference_set="development",
            )

    def test_discovery_coverage_refuses_without_a_snapshot(self, tmp_path: Path) -> None:
        with pytest.raises(OntologySnapshotRequired):
            evaluate_discovery_coverage(
                _result("no_snapshot__modality_v2"), _reference_universe(tmp_path)
            )

    def test_sealed_holdout_refusal_still_takes_precedence(self, tmp_path: Path) -> None:
        """Never open a sealed file, whatever the ontology says about scoreability."""

        sealed = tmp_path / "sealed.yaml"
        sealed.write_text(yaml.safe_dump({"status": "sealed_holdout", "records": []}))
        with pytest.raises(ValueError, match="sealed holdout"):
            evaluate_reference_landscape(
                sealed, _result("no_snapshot__modality_v2"), reference_set="holdout"
            )


class TestCli:
    def _write_result(self, tmp_path: Path, version: str | None) -> Path:
        path = tmp_path / "result.json"
        path.write_text(_result(version).model_dump_json())
        return path

    def test_cli_exits_3_and_writes_nothing(self, tmp_path: Path, capsys) -> None:
        output = tmp_path / "report.json"
        code = evaluate_main(
            [
                "--benchmark",
                str(_benchmark(tmp_path)),
                "--result",
                str(self._write_result(tmp_path, "no_snapshot__modality_v2")),
                "--output",
                str(output),
            ]
        )

        assert code == 3
        assert "refusing to score" in capsys.readouterr().err
        # An unscoreable run must not leave a report behind that looks like a result.
        assert not output.exists()

    def test_cli_scores_a_pinned_run(self, tmp_path: Path) -> None:
        output = tmp_path / "report.json"
        code = evaluate_main(
            [
                "--benchmark",
                str(_benchmark(tmp_path)),
                "--result",
                str(self._write_result(tmp_path, PINNED)),
                "--output",
                str(output),
            ]
        )

        assert code == 0
        assert json.loads(output.read_text())["reference_set"] == "validation"
