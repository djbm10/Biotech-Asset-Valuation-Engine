"""Sprint 53 — Block 12: Product Workflow & User Packaging tests.

Covers three workflow entry points:
  - evaluate_target  (bve-evaluate-target)
  - morning_screen   (bve-morning-screen)
  - init_asset       (bve-init-asset)
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valuation_json(tmp_path: Path, ticker: str, **overrides) -> Path:
    """Write a minimal valuation.json under tmp_path/outputs/<TICKER>/."""
    d = tmp_path / "outputs" / ticker.upper()
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "base_rnpv": 120.0,
        "nav_per_share": 8.50,
        "implied_upside_pct": 45.0,
        "prob_approval_pct": 35.0,
        "as_of": "2026-05-26",
        "staleness_warnings": [],
    }
    payload.update(overrides)
    (d / "valuation.json").write_text(json.dumps(payload), encoding="utf-8")
    return d / "valuation.json"


# ===========================================================================
# evaluate_target
# ===========================================================================

class TestEvaluateTarget:
    def test_import(self):
        from bve.workflows.evaluate_target import evaluate_target  # noqa: F401

    def test_returns_string(self, tmp_path):
        from bve.workflows.evaluate_target import evaluate_target
        result = evaluate_target(
            "SRPT",
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
            skip_refresh=True,
        )
        assert isinstance(result, str)

    def test_report_contains_ticker_header(self, tmp_path):
        from bve.workflows.evaluate_target import evaluate_target
        result = evaluate_target(
            "VKTX",
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
            skip_refresh=True,
        )
        assert "VKTX" in result

    def test_report_contains_date(self, tmp_path):
        from bve.workflows.evaluate_target import evaluate_target
        result = evaluate_target(
            "SRPT",
            as_of_date=date(2026, 5, 26),
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
            skip_refresh=True,
        )
        assert "2026-05-26" in result

    def test_missing_valuation_degrades_gracefully(self, tmp_path):
        from bve.workflows.evaluate_target import evaluate_target
        # No valuation.json in outputs — should not raise, just show "not available"
        result = evaluate_target(
            "FAKE",
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
            skip_refresh=True,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_valuation_data_appears_in_report(self, tmp_path):
        from bve.workflows.evaluate_target import evaluate_target
        _make_valuation_json(tmp_path, "NVAX")
        result = evaluate_target(
            "NVAX",
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
            skip_refresh=True,
        )
        assert isinstance(result, str)
        # Report should contain the ticker
        assert "NVAX" in result

    def test_notes_appended(self, tmp_path):
        from bve.workflows.evaluate_target import evaluate_target
        result = evaluate_target(
            "SRPT",
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
            skip_refresh=True,
            notes=["Analyst note: check Phase 3 timeline"],
        )
        assert "Analyst note: check Phase 3 timeline" in result

    def test_ticker_normalised_to_uppercase(self, tmp_path):
        from bve.workflows.evaluate_target import evaluate_target
        result = evaluate_target(
            "srpt",  # lowercase
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
            skip_refresh=True,
        )
        assert "SRPT" in result

    def test_cli_main_prints_report(self, tmp_path, capsys):
        from bve.workflows.evaluate_target import main
        rc = main([
            "--ticker", "SRPT",
            "--no-refresh",
            "--outputs-dir", str(tmp_path / "outputs"),
            "--ops-db", str(tmp_path / "nonexistent.db"),
            "--prediction-log", str(tmp_path / "nonexistent_pred.db"),
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "SRPT" in out

    def test_cli_main_writes_output_file(self, tmp_path):
        from bve.workflows.evaluate_target import main
        out_file = tmp_path / "report.md"
        rc = main([
            "--ticker", "SRPT",
            "--no-refresh",
            "--outputs-dir", str(tmp_path / "outputs"),
            "--ops-db", str(tmp_path / "nonexistent.db"),
            "--prediction-log", str(tmp_path / "nonexistent_pred.db"),
            "--output", str(out_file),
        ])
        assert rc == 0
        assert out_file.exists()
        assert "SRPT" in out_file.read_text()

    def test_cli_invalid_as_of_returns_1(self, tmp_path):
        from bve.workflows.evaluate_target import main
        rc = main(["--ticker", "SRPT", "--as-of", "not-a-date"])
        assert rc == 1


# ===========================================================================
# morning_screen
# ===========================================================================

class TestMorningScreen:
    def test_import(self):
        from bve.workflows.morning_screen import morning_screen  # noqa: F401

    def test_returns_string(self, tmp_path):
        from bve.workflows.morning_screen import morning_screen
        result = morning_screen(
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
        )
        assert isinstance(result, str)

    def test_report_has_title(self, tmp_path):
        from bve.workflows.morning_screen import morning_screen
        result = morning_screen(
            as_of_date=date(2026, 5, 26),
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
        )
        assert "BVE Morning Screen" in result
        assert "2026-05-26" in result

    def test_report_has_disclaimer(self, tmp_path):
        from bve.workflows.morning_screen import morning_screen
        result = morning_screen(
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
        )
        assert "Research-grade output only" in result

    def test_all_sections_present(self, tmp_path):
        from bve.workflows.morning_screen import morning_screen
        result = morning_screen(
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
        )
        assert "Top M&A / BD Action Candidates" in result
        assert "Top Valuation Dislocations" in result
        assert "Catalyst / Watchlist Items" in result
        assert "Stale / Low-Integrity Inputs" in result
        assert "Unresolved Prediction Log Items" in result

    def test_trial_diff_section_present_by_default(self, tmp_path):
        from bve.workflows.morning_screen import morning_screen
        result = morning_screen(
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
        )
        assert "ClinicalTrials.gov Changes" in result

    def test_trial_diff_section_excluded_when_disabled(self, tmp_path):
        from bve.workflows.morning_screen import morning_screen
        result = morning_screen(
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
            include_trial_diff=False,
        )
        assert "ClinicalTrials.gov Changes" not in result

    def test_empty_outputs_dir_degrades_gracefully(self, tmp_path):
        from bve.workflows.morning_screen import morning_screen
        # No outputs at all
        result = morning_screen(
            outputs_dir=tmp_path / "no_such_dir",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_valuation_dislocations_populated(self, tmp_path):
        from bve.workflows.morning_screen import morning_screen
        # Write two valuation files with known upside
        _make_valuation_json(tmp_path, "SRPT", implied_upside_pct=80.0)
        _make_valuation_json(tmp_path, "VKTX", implied_upside_pct=-30.0)
        result = morning_screen(
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
            top_n=5,
        )
        # Both tickers should appear in the dislocations table
        assert "SRPT" in result
        assert "VKTX" in result

    def test_stale_inputs_detected(self, tmp_path):
        from bve.workflows.morning_screen import morning_screen
        d = tmp_path / "outputs" / "STALE_CO"
        d.mkdir(parents=True, exist_ok=True)
        payload = {
            "base_rnpv": 10.0,
            "staleness_warnings": ["cash balance older than 90 days"],
        }
        (d / "valuation.json").write_text(json.dumps(payload))
        result = morning_screen(
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "nonexistent.db",
            prediction_log_db=tmp_path / "nonexistent_pred.db",
        )
        assert "STALE_CO" in result
        assert "cash balance older than 90 days" in result

    def test_cli_main_prints_report(self, tmp_path, capsys):
        from bve.workflows.morning_screen import main
        rc = main([
            "--outputs-dir", str(tmp_path / "outputs"),
            "--ops-db", str(tmp_path / "nonexistent.db"),
            "--prediction-log", str(tmp_path / "nonexistent_pred.db"),
            "--no-trial-diff",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "BVE Morning Screen" in out

    def test_cli_main_writes_output_file(self, tmp_path):
        from bve.workflows.morning_screen import main
        out_file = tmp_path / "screen.md"
        rc = main([
            "--output", str(out_file),
            "--outputs-dir", str(tmp_path / "outputs"),
            "--ops-db", str(tmp_path / "nonexistent.db"),
            "--prediction-log", str(tmp_path / "nonexistent_pred.db"),
        ])
        assert rc == 0
        assert out_file.exists()
        assert "BVE Morning Screen" in out_file.read_text()

    def test_cli_top_flag(self, tmp_path, capsys):
        from bve.workflows.morning_screen import main
        rc = main([
            "--top", "5",
            "--outputs-dir", str(tmp_path / "outputs"),
            "--ops-db", str(tmp_path / "nonexistent.db"),
            "--prediction-log", str(tmp_path / "nonexistent_pred.db"),
        ])
        assert rc == 0

    def test_cli_invalid_as_of_returns_1(self):
        from bve.workflows.morning_screen import main
        rc = main(["--as-of", "bad-date"])
        assert rc == 1


# ===========================================================================
# init_asset
# ===========================================================================

class TestInitAsset:
    def test_import(self):
        from bve.workflows.init_asset import init_asset  # noqa: F401

    def test_creates_files(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        created = init_asset(
            "TEST",
            configs_dir=tmp_path / "configs",
            outputs_dir=tmp_path / "outputs",
        )
        assert len(created) == 7  # 5 yaml + 2 json

    def test_created_files_exist(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        created = init_asset(
            "TEST",
            configs_dir=tmp_path / "configs",
            outputs_dir=tmp_path / "outputs",
        )
        for p in created:
            assert Path(p).exists(), f"{p} was not created"

    def test_ticker_uppercased_in_paths(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        created = init_asset(
            "srpt",  # lowercase
            configs_dir=tmp_path / "configs",
            outputs_dir=tmp_path / "outputs",
        )
        for p in created:
            assert "SRPT" in str(p)

    def test_asset_profile_contains_ticker(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        init_asset("MRGN", configs_dir=tmp_path / "configs", outputs_dir=tmp_path / "outputs")
        content = (tmp_path / "configs" / "MRGN" / "asset_profile.yaml").read_text()
        assert "MRGN" in content

    def test_valuation_config_contains_ticker(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        init_asset("MRGN", configs_dir=tmp_path / "configs", outputs_dir=tmp_path / "outputs")
        content = (tmp_path / "configs" / "MRGN" / "valuation_config.yaml").read_text()
        assert "mrgn" in content.lower()

    def test_management_quality_json_valid(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        init_asset("ABC", configs_dir=tmp_path / "configs", outputs_dir=tmp_path / "outputs")
        raw = (tmp_path / "outputs" / "ABC" / "management_quality.json").read_text()
        parsed = json.loads(raw)
        assert "_ticker" in parsed or "ABC" in raw

    def test_financial_snapshot_json_valid(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        init_asset("ABC", configs_dir=tmp_path / "configs", outputs_dir=tmp_path / "outputs")
        raw = (tmp_path / "outputs" / "ABC" / "financial_snapshot.json").read_text()
        parsed = json.loads(raw)
        assert "as_of" in parsed

    def test_trial_records_yaml_present(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        init_asset("XYZ", configs_dir=tmp_path / "configs", outputs_dir=tmp_path / "outputs")
        content = (tmp_path / "configs" / "XYZ" / "trial_records.yaml").read_text()
        assert "trials:" in content

    def test_acquirer_mapping_yaml_present(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        init_asset("XYZ", configs_dir=tmp_path / "configs", outputs_dir=tmp_path / "outputs")
        content = (tmp_path / "configs" / "XYZ" / "acquirer_mapping.yaml").read_text()
        assert "potential_acquirers:" in content

    def test_ma_target_profile_yaml_present(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        init_asset("XYZ", configs_dir=tmp_path / "configs", outputs_dir=tmp_path / "outputs")
        content = (tmp_path / "configs" / "XYZ" / "ma_target_profile.yaml").read_text()
        assert "management_receptivity:" in content

    def test_idempotent_second_run_creates_nothing(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        first = init_asset("IDEM", configs_dir=tmp_path / "configs", outputs_dir=tmp_path / "outputs")
        second = init_asset("IDEM", configs_dir=tmp_path / "configs", outputs_dir=tmp_path / "outputs")
        assert len(first) == 7
        assert len(second) == 0

    def test_returns_list(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        result = init_asset("RET", configs_dir=tmp_path / "configs", outputs_dir=tmp_path / "outputs")
        assert isinstance(result, list)

    def test_cli_main_returns_zero(self, tmp_path):
        from bve.workflows.init_asset import main
        rc = main([
            "--ticker", "CLIA",
            "--configs-dir", str(tmp_path / "configs"),
            "--outputs-dir", str(tmp_path / "outputs"),
        ])
        assert rc == 0

    def test_cli_main_creates_files(self, tmp_path):
        from bve.workflows.init_asset import main
        main([
            "--ticker", "CLIA",
            "--configs-dir", str(tmp_path / "configs"),
            "--outputs-dir", str(tmp_path / "outputs"),
        ])
        assert (tmp_path / "configs" / "CLIA" / "asset_profile.yaml").exists()

    def test_cli_main_idempotent(self, tmp_path):
        from bve.workflows.init_asset import main
        rc1 = main([
            "--ticker", "IDEM2",
            "--configs-dir", str(tmp_path / "configs"),
            "--outputs-dir", str(tmp_path / "outputs"),
        ])
        rc2 = main([
            "--ticker", "IDEM2",
            "--configs-dir", str(tmp_path / "configs"),
            "--outputs-dir", str(tmp_path / "outputs"),
        ])
        assert rc1 == 0
        assert rc2 == 0


# ===========================================================================
# Architecture contract — workflows module registered
# ===========================================================================

class TestArchitectureContractWorkflows:
    def test_workflows_module_registered(self):
        from bve.architecture import load_architecture_contract
        payload = load_architecture_contract()
        mapped = {entry["module"] for entry in payload["top_level_module_map"]}
        assert "workflows" in mapped, (
            "workflows module not found in architecture_contract.yaml top_level_module_map"
        )
