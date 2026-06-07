"""
Tests for Block 2F CLI commands.

All external fetchers are mocked. No network. No live YAML files required —
fixture YAML files are written to tmp_path.

Covers:
  1. bve-weekly-run --dry-run returns 0 and writes no files
  2. bve-weekly-run writes all expected output files
  3. Missing targets file returns exit code 1
  4. Invalid score mode raises argparse error
  5. bve-build-profiles --dry-run writes no files
  6. bve-run-ma-screen writes screen_result.json
  7. bve-write-report writes CSV/MD files from fixture screen result
  8. Output is deterministic
  9. screen_result.json is valid JSON and reloadable
  10. CLI prints top target in summary
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from bve.cli.build_profiles_cli import main as build_profiles_main
from bve.cli.run_ma_screen_cli import main as run_ma_screen_main
from bve.cli.weekly_run_cli import main as weekly_run_main
from bve.cli.write_report_cli import main as write_report_main


# ---------------------------------------------------------------------------
# Mock fetchers (no network)
# ---------------------------------------------------------------------------


def _null_sec(ticker: str) -> dict:
    return {}


def _null_ledger(ticker: str) -> dict:
    return {}


# ---------------------------------------------------------------------------
# Fixture universe YAML writers
# ---------------------------------------------------------------------------


def _write_targets_yaml(path: Path) -> None:
    data = {
        "RVMD": {
            "name": "Revolution Medicines",
            "exchange": "NASDAQ",
            "company_type": "drug_developer",
            "therapeutic_areas": ["oncology"],
            "lead_asset": "daraxonrasib",
            "lead_asset_phase": "phase3",
            "lead_modality": "small_molecule",
            "lead_indication": "RAS-mutant solid tumors",
            "is_single_asset_company": False,
            "include_in_screen": True,
            "market_cap_bucket": "micro",
        },
        "MDGL": {
            "name": "Madrigal Pharmaceuticals",
            "exchange": "NASDAQ",
            "company_type": "commercial",
            "therapeutic_areas": ["metabolic"],
            "lead_asset": "resmetirom",
            "lead_asset_phase": "commercial",
            "lead_modality": "small_molecule",
            "lead_indication": "MASH",
            "is_single_asset_company": True,
            "include_in_screen": True,
            "market_cap_bucket": "small",
        },
    }
    with path.open("w") as fh:
        yaml.dump(data, fh)


def _write_acquirers_yaml(path: Path) -> None:
    data = {
        "PFE": {
            "name": "Pfizer",
            "therapeutic_areas": ["oncology", "metabolic"],
            "modalities": ["small_molecule", "biologic"],
            "deal_size_range_millions": [1000, 60000],
            "preferred_stages": ["phase2", "phase3", "commercial"],
            "include_as_acquirer": True,
        },
        "LLY": {
            "name": "Eli Lilly",
            "therapeutic_areas": ["metabolic", "oncology"],
            "modalities": ["biologic", "small_molecule"],
            "deal_size_range_millions": [2000, 50000],
            "preferred_stages": ["phase3", "commercial"],
            "include_as_acquirer": True,
        },
    }
    with path.open("w") as fh:
        yaml.dump(data, fh)


def _write_overrides_yaml(path: Path) -> None:
    data = {
        "RVMD": {
            "lead_asset": "daraxonrasib",
            "lead_asset_phase": "phase3",
        }
    }
    with path.open("w") as fh:
        yaml.dump(data, fh)


def _setup_universe(tmp_path: Path) -> dict[str, Path]:
    targets = tmp_path / "targets.yaml"
    acquirers = tmp_path / "acquirers.yaml"
    overrides = tmp_path / "overrides.yaml"
    _write_targets_yaml(targets)
    _write_acquirers_yaml(acquirers)
    _write_overrides_yaml(overrides)
    return {"targets": targets, "acquirers": acquirers, "overrides": overrides}


def _build_profiles(tmp_path: Path, universe: dict[str, Path], profiles_dir: Path) -> None:
    """Run bve-build-profiles to produce profile JSON files."""
    build_profiles_main(
        argv=[
            "--targets", str(universe["targets"]),
            "--acquirers", str(universe["acquirers"]),
            "--overrides", str(universe["overrides"]),
            "--output", str(profiles_dir),
        ],
        _sec_fetcher=_null_sec,
        _ledger_score_fetcher=_null_ledger,
    )


def _write_fixture_screen_result(tmp_path: Path) -> Path:
    """Write a minimal screen_result.json for write_report tests."""
    from bve.cli._serde import screen_result_to_json
    from bve.intelligence.weekly_ma_screen import (
        AcquirerPairResult,
        TargetScreenResult,
        WeeklyMAScreenResult,
    )

    t = TargetScreenResult(
        rank=1, ticker="RVMD", name="Revolution Medicines",
        ma_probability=0.42, probability_low=0.28, probability_high=0.56,
        confidence_label="medium",
        asset_quality=0.65, seller_willingness=0.48, financing_risk=0.10,
        catalyst_timing=0.35,
        ma_attractiveness=0.60, evidence_coverage_overall=0.60,
        profile_quality_score=0.80,
        top_acquirer="PFE", top_acquirer_pair_score=0.68,
        main_drivers=["phase3 asset", "oncology TA"],
        key_risks=["low evidence coverage"],
        suppressed=False, suppression_reason=None,
    )
    p = AcquirerPairResult(
        target_ticker="RVMD", acquirer_ticker="PFE",
        pair_score=0.68, ta_overlap=0.5, modality_fit=1.0,
        stage_fit=1.0, deal_size_fit=0.9, pipeline_gap_fill=0.3,
        integration_complexity=0.2,
    )
    result = WeeklyMAScreenResult(
        as_of_date=date(2026, 6, 1),
        score_mode="provisional",
        ranked_targets=[t],
        suppressed_targets=[],
        top_acquirer_pairs=[p],
        diagnostics={
            "n_targets_input": 1, "n_acquirers_input": 1,
            "n_ranked_targets": 1, "n_suppressed_targets": 0,
            "n_pair_scores": 1, "score_mode": "provisional",
            "as_of_date": "2026-06-01",
        },
    )
    out = tmp_path / "screen_result.json"
    out.write_text(screen_result_to_json(result), encoding="utf-8")
    return out


# ===========================================================================
# bve-weekly-run
# ===========================================================================


class TestWeeklyRunDryRun:
    def test_dry_run_returns_0(self, tmp_path):
        u = _setup_universe(tmp_path)
        out = tmp_path / "weekly_out"
        rc = weekly_run_main(
            argv=[
                "--targets", str(u["targets"]),
                "--acquirers", str(u["acquirers"]),
                "--overrides", str(u["overrides"]),
                "--as-of", "2026-06-01",
                "--output", str(out),
                "--dry-run",
                "--min-coverage", "0.0",
            ],
            _sec_fetcher=_null_sec,
            _ledger_score_fetcher=_null_ledger,
        )
        assert rc == 0

    def test_dry_run_writes_no_files(self, tmp_path):
        u = _setup_universe(tmp_path)
        out = tmp_path / "weekly_out"
        weekly_run_main(
            argv=[
                "--targets", str(u["targets"]),
                "--acquirers", str(u["acquirers"]),
                "--overrides", str(u["overrides"]),
                "--as-of", "2026-06-01",
                "--output", str(out),
                "--dry-run",
                "--min-coverage", "0.0",
            ],
            _sec_fetcher=_null_sec,
            _ledger_score_fetcher=_null_ledger,
        )
        assert not out.exists()


class TestWeeklyRunWritesFiles:
    _EXPECTED = {
        "screen_result.json",
        "ranked_targets.csv",
        "top_acquirer_pairs.csv",
        "suppressed_targets.csv",
        "score_changes.csv",
        "audit_report.md",
        "validation_snapshot.json",
    }

    def _run(self, tmp_path: Path) -> Path:
        u = _setup_universe(tmp_path)
        out = tmp_path / "weekly_out"
        rc = weekly_run_main(
            argv=[
                "--targets", str(u["targets"]),
                "--acquirers", str(u["acquirers"]),
                "--overrides", str(u["overrides"]),
                "--as-of", "2026-06-01",
                "--output", str(out),
                "--min-coverage", "0.0",
            ],
            _sec_fetcher=_null_sec,
            _ledger_score_fetcher=_null_ledger,
        )
        assert rc == 0
        return out

    def test_returns_0(self, tmp_path):
        self._run(tmp_path)

    def test_all_expected_files_exist(self, tmp_path):
        out = self._run(tmp_path)
        written = {p.name for p in out.iterdir()}
        for name in self._EXPECTED:
            assert name in written, f"Missing: {name}"

    def test_screen_result_json_is_valid_json(self, tmp_path):
        out = self._run(tmp_path)
        data = json.loads((out / "screen_result.json").read_text())
        assert "ranked_targets" in data
        assert "as_of_date" in data

    def test_screen_result_reloadable(self, tmp_path):
        out = self._run(tmp_path)
        from bve.cli._serde import screen_result_from_json
        result = screen_result_from_json((out / "screen_result.json").read_text())
        assert result.as_of_date == date(2026, 6, 1)

    def test_audit_report_has_content(self, tmp_path):
        out = self._run(tmp_path)
        content = (out / "audit_report.md").read_text()
        assert "## Run Summary" in content

    def test_validation_snapshot_has_schema_version(self, tmp_path):
        out = self._run(tmp_path)
        snap = json.loads((out / "validation_snapshot.json").read_text())
        assert "schema_version" in snap

    def test_deterministic_across_two_runs(self, tmp_path):
        u = _setup_universe(tmp_path)
        argv = [
            "--targets", str(u["targets"]),
            "--acquirers", str(u["acquirers"]),
            "--overrides", str(u["overrides"]),
            "--as-of", "2026-06-01",
            "--min-coverage", "0.0",
        ]
        out1 = tmp_path / "run1"
        out2 = tmp_path / "run2"
        weekly_run_main(argv + ["--output", str(out1)],
                        _sec_fetcher=_null_sec, _ledger_score_fetcher=_null_ledger)
        weekly_run_main(argv + ["--output", str(out2)],
                        _sec_fetcher=_null_sec, _ledger_score_fetcher=_null_ledger)
        c1 = (out1 / "ranked_targets.csv").read_text()
        c2 = (out2 / "ranked_targets.csv").read_text()
        assert c1 == c2


class TestWeeklyRunErrors:
    def test_missing_targets_returns_1(self, tmp_path):
        rc = weekly_run_main(
            argv=[
                "--targets", str(tmp_path / "nonexistent.yaml"),
                "--acquirers", str(tmp_path / "a.yaml"),
                "--output", str(tmp_path / "out"),
            ],
            _sec_fetcher=_null_sec,
            _ledger_score_fetcher=_null_ledger,
        )
        assert rc == 1

    def test_missing_acquirers_returns_1(self, tmp_path):
        u = _setup_universe(tmp_path)
        rc = weekly_run_main(
            argv=[
                "--targets", str(u["targets"]),
                "--acquirers", str(tmp_path / "nonexistent.yaml"),
                "--output", str(tmp_path / "out"),
            ],
            _sec_fetcher=_null_sec,
            _ledger_score_fetcher=_null_ledger,
        )
        assert rc == 1

    def test_invalid_score_mode_raises(self, tmp_path):
        u = _setup_universe(tmp_path)
        with pytest.raises(SystemExit):
            weekly_run_main(
                argv=[
                    "--targets", str(u["targets"]),
                    "--acquirers", str(u["acquirers"]),
                    "--score-mode", "not_a_mode",
                    "--output", str(tmp_path / "out"),
                ],
                _sec_fetcher=_null_sec,
                _ledger_score_fetcher=_null_ledger,
            )


# ===========================================================================
# bve-build-profiles
# ===========================================================================


class TestBuildProfiles:
    def test_dry_run_returns_0(self, tmp_path):
        u = _setup_universe(tmp_path)
        rc = build_profiles_main(
            argv=[
                "--targets", str(u["targets"]),
                "--acquirers", str(u["acquirers"]),
                "--overrides", str(u["overrides"]),
                "--output", str(tmp_path / "profiles"),
                "--dry-run",
            ],
            _sec_fetcher=_null_sec,
            _ledger_score_fetcher=_null_ledger,
        )
        assert rc == 0

    def test_dry_run_writes_no_files(self, tmp_path):
        u = _setup_universe(tmp_path)
        profiles_dir = tmp_path / "profiles"
        build_profiles_main(
            argv=[
                "--targets", str(u["targets"]),
                "--acquirers", str(u["acquirers"]),
                "--overrides", str(u["overrides"]),
                "--output", str(profiles_dir),
                "--dry-run",
            ],
            _sec_fetcher=_null_sec,
            _ledger_score_fetcher=_null_ledger,
        )
        assert not profiles_dir.exists()

    def test_writes_profile_files(self, tmp_path):
        u = _setup_universe(tmp_path)
        profiles_dir = tmp_path / "profiles"
        rc = build_profiles_main(
            argv=[
                "--targets", str(u["targets"]),
                "--acquirers", str(u["acquirers"]),
                "--overrides", str(u["overrides"]),
                "--output", str(profiles_dir),
            ],
            _sec_fetcher=_null_sec,
            _ledger_score_fetcher=_null_ledger,
        )
        assert rc == 0
        assert (profiles_dir / "target_profiles.json").exists()
        assert (profiles_dir / "acquirer_profiles.json").exists()
        assert (profiles_dir / "profile_quality_report.json").exists()

    def test_target_profiles_json_is_valid(self, tmp_path):
        u = _setup_universe(tmp_path)
        profiles_dir = tmp_path / "profiles"
        build_profiles_main(
            argv=[
                "--targets", str(u["targets"]),
                "--acquirers", str(u["acquirers"]),
                "--output", str(profiles_dir),
            ],
            _sec_fetcher=_null_sec,
            _ledger_score_fetcher=_null_ledger,
        )
        data = json.loads((profiles_dir / "target_profiles.json").read_text())
        assert "RVMD" in data

    def test_missing_targets_returns_1(self, tmp_path):
        rc = build_profiles_main(
            argv=[
                "--targets", str(tmp_path / "missing.yaml"),
                "--acquirers", str(tmp_path / "a.yaml"),
                "--output", str(tmp_path / "profiles"),
            ],
            _sec_fetcher=_null_sec,
            _ledger_score_fetcher=_null_ledger,
        )
        assert rc == 1


# ===========================================================================
# bve-run-ma-screen
# ===========================================================================


class TestRunMAScreen:
    def _setup_profiles(self, tmp_path: Path) -> dict[str, Path]:
        u = _setup_universe(tmp_path)
        profiles_dir = tmp_path / "profiles"
        build_profiles_main(
            argv=[
                "--targets", str(u["targets"]),
                "--acquirers", str(u["acquirers"]),
                "--output", str(profiles_dir),
            ],
            _sec_fetcher=_null_sec,
            _ledger_score_fetcher=_null_ledger,
        )
        return {
            "targets": profiles_dir / "target_profiles.json",
            "acquirers": profiles_dir / "acquirer_profiles.json",
        }

    def test_writes_screen_result_json(self, tmp_path):
        p = self._setup_profiles(tmp_path)
        out = tmp_path / "screen_result.json"
        rc = run_ma_screen_main(argv=[
            "--target-profiles", str(p["targets"]),
            "--acquirer-profiles", str(p["acquirers"]),
            "--as-of", "2026-06-01",
            "--output", str(out),
            "--min-coverage", "0.0",
        ])
        assert rc == 0
        assert out.exists()

    def test_screen_result_is_valid_json(self, tmp_path):
        p = self._setup_profiles(tmp_path)
        out = tmp_path / "screen_result.json"
        run_ma_screen_main(argv=[
            "--target-profiles", str(p["targets"]),
            "--acquirer-profiles", str(p["acquirers"]),
            "--as-of", "2026-06-01",
            "--output", str(out),
            "--min-coverage", "0.0",
        ])
        data = json.loads(out.read_text())
        assert "ranked_targets" in data
        assert data["as_of_date"] == "2026-06-01"

    def test_screen_result_roundtrip(self, tmp_path):
        p = self._setup_profiles(tmp_path)
        out = tmp_path / "screen_result.json"
        run_ma_screen_main(argv=[
            "--target-profiles", str(p["targets"]),
            "--acquirer-profiles", str(p["acquirers"]),
            "--as-of", "2026-06-01",
            "--output", str(out),
            "--min-coverage", "0.0",
        ])
        from bve.cli._serde import screen_result_from_json
        result = screen_result_from_json(out.read_text())
        assert result.as_of_date == date(2026, 6, 1)
        assert result.score_mode == "provisional"

    def test_dry_run_writes_nothing(self, tmp_path):
        p = self._setup_profiles(tmp_path)
        out = tmp_path / "screen_result.json"
        rc = run_ma_screen_main(argv=[
            "--target-profiles", str(p["targets"]),
            "--acquirer-profiles", str(p["acquirers"]),
            "--output", str(out),
            "--dry-run",
        ])
        assert rc == 0
        assert not out.exists()

    def test_missing_target_profiles_returns_1(self, tmp_path):
        rc = run_ma_screen_main(argv=[
            "--target-profiles", str(tmp_path / "missing.json"),
            "--acquirer-profiles", str(tmp_path / "a.json"),
        ])
        assert rc == 1


# ===========================================================================
# bve-write-report
# ===========================================================================


class TestWriteReport:
    def test_writes_six_files(self, tmp_path):
        sr = _write_fixture_screen_result(tmp_path)
        out = tmp_path / "report"
        rc = write_report_main(argv=[
            "--screen-result", str(sr),
            "--output", str(out),
        ])
        assert rc == 0
        written = {p.name for p in out.iterdir()}
        for name in ["ranked_targets.csv", "top_acquirer_pairs.csv",
                     "suppressed_targets.csv", "score_changes.csv",
                     "audit_report.md", "validation_snapshot.json"]:
            assert name in written

    def test_dry_run_writes_nothing(self, tmp_path):
        sr = _write_fixture_screen_result(tmp_path)
        out = tmp_path / "report"
        rc = write_report_main(argv=[
            "--screen-result", str(sr),
            "--output", str(out),
            "--dry-run",
        ])
        assert rc == 0
        assert not out.exists()

    def test_missing_screen_result_returns_1(self, tmp_path):
        rc = write_report_main(argv=[
            "--screen-result", str(tmp_path / "nonexistent.json"),
            "--output", str(tmp_path / "out"),
        ])
        assert rc == 1

    def test_audit_report_contains_sections(self, tmp_path):
        sr = _write_fixture_screen_result(tmp_path)
        out = tmp_path / "report"
        write_report_main(argv=[
            "--screen-result", str(sr),
            "--output", str(out),
        ])
        md = (out / "audit_report.md").read_text()
        assert "## Run Summary" in md
        assert "## Top 25 Targets" in md
        assert "RVMD" in md

    def test_prev_result_nonexistent_does_not_crash(self, tmp_path):
        sr = _write_fixture_screen_result(tmp_path)
        out = tmp_path / "report"
        rc = write_report_main(argv=[
            "--screen-result", str(sr),
            "--output", str(out),
            "--prev-result", str(tmp_path / "nonexistent.json"),
        ])
        assert rc == 0


# ===========================================================================
# serde round-trip
# ===========================================================================


class TestSerdeRoundTrip:
    def test_screen_result_json_roundtrip(self, tmp_path):
        from bve.cli._serde import screen_result_from_json, screen_result_to_json
        from bve.intelligence.weekly_ma_screen import (
            TargetScreenResult, WeeklyMAScreenResult
        )
        t = TargetScreenResult(
            rank=1, ticker="TST", name="Test",
        ma_probability=0.40, probability_low=0.25, probability_high=0.55,
        confidence_label="medium",
        asset_quality=0.60, seller_willingness=0.45, financing_risk=0.10,
        catalyst_timing=0.30,
            ma_attractiveness=0.55, evidence_coverage_overall=0.50,
            profile_quality_score=0.75,
            top_acquirer="PFE", top_acquirer_pair_score=0.65,
            main_drivers=["driver1"], key_risks=["risk1"],
            suppressed=False, suppression_reason=None,
        )
        result = WeeklyMAScreenResult(
            as_of_date=date(2026, 6, 1), score_mode="provisional",
            ranked_targets=[t], suppressed_targets=[],
            top_acquirer_pairs=[], diagnostics={},
        )
        json_str = screen_result_to_json(result)
        restored = screen_result_from_json(json_str)
        assert restored.as_of_date == date(2026, 6, 1)
        assert restored.ranked_targets[0].ticker == "TST"
        assert restored.ranked_targets[0].ma_probability == pytest.approx(0.40)
        assert restored.ranked_targets[0].main_drivers == ["driver1"]

    def test_acquirer_profile_deal_range_tuple_preserved(self, tmp_path):
        from bve.cli._serde import acquirer_profile_from_dict
        from bve.ingestion.profile_enricher import AcquirerProfileEnriched
        import dataclasses
        prof = AcquirerProfileEnriched(
            ticker="PFE", name="Pfizer", cik=None,
            therapeutic_areas=["oncology"],
            modalities=["biologic"],
            deal_size_range_millions=(1000.0, 60000.0),
            preferred_stages=["phase3"],
            include_as_acquirer=True,
            bd_appetite=0.65, urgency=0.55, integration_capacity=0.70,
            quality_score=0.90, data_quality_flags=[],
            source_map={}, enriched_at="2026-06-01T00:00:00+00:00",
        )
        import json
        raw = json.loads(json.dumps(dataclasses.asdict(prof)))
        restored = acquirer_profile_from_dict(raw)
        assert isinstance(restored.deal_size_range_millions, tuple)
        assert restored.deal_size_range_millions == (1000.0, 60000.0)
