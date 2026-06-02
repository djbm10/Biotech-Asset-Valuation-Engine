"""
Smoke tests for .github/workflows/daily_bve_run.yml.
"""
from __future__ import annotations

from pathlib import Path

import pytest

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "daily_bve_run.yml"


@pytest.fixture(scope="module")
def wf() -> str:
    assert WORKFLOW_PATH.exists(), f"Workflow file not found: {WORKFLOW_PATH}"
    return WORKFLOW_PATH.read_text(encoding="utf-8")


class TestWorkflowFileExists:
    def test_file_exists(self):
        assert WORKFLOW_PATH.exists()

    def test_is_yaml(self):
        assert WORKFLOW_PATH.suffix == ".yml"


class TestTriggers:
    def test_has_schedule(self, wf):
        assert "schedule:" in wf

    def test_has_cron(self, wf):
        assert "cron:" in wf

    def test_has_workflow_dispatch(self, wf):
        assert "workflow_dispatch:" in wf

    def test_has_as_of_date_input(self, wf):
        assert "as_of_date" in wf

    def test_has_score_mode_input(self, wf):
        assert "score_mode" in wf

    def test_has_lookback_days_input(self, wf):
        assert "lookback_days" in wf


class TestPermissionsAndConcurrency:
    def test_has_contents_write_permission(self, wf):
        assert "contents: write" in wf

    def test_has_concurrency_group(self, wf):
        assert "concurrency:" in wf
        assert "group: bve-ledger" in wf

    def test_cancel_in_progress_false(self, wf):
        assert "cancel-in-progress: false" in wf


class TestLedgerRestore:
    def test_restores_from_data_branch(self, wf):
        assert "origin data" in wf

    def test_creates_empty_ledger_if_missing(self, wf):
        assert "touch outputs/intelligence/evidence_ledger.jsonl" in wf

    def test_checks_ledger_before_run(self, wf):
        assert "Ledger records before run" in wf


class TestPipeline:
    def test_calls_bve_weekly_run(self, wf):
        assert "bve-weekly-run" in wf

    def test_passes_ingest_live(self, wf):
        assert "--ingest-live" in wf

    def test_passes_lookback_days(self, wf):
        assert "--lookback-days" in wf

    def test_output_goes_to_daily_dir(self, wf):
        assert "outputs/daily" in wf

    def test_calls_ledger_stats(self, wf):
        assert "bve-ledger-stats" in wf


class TestArtifactUpload:
    def test_uploads_daily_artifact(self, wf):
        assert "upload-artifact" in wf

    def test_artifact_name_has_date(self, wf):
        assert "bve-daily-" in wf

    def test_artifact_retention_30_days(self, wf):
        assert "retention-days: 30" in wf

    def test_artifact_path_is_daily_dir(self, wf):
        assert "outputs/daily/" in wf


class TestLedgerPersist:
    def test_persists_to_data_branch(self, wf):
        assert "git push origin HEAD:data" in wf

    def test_uses_temp_copy_not_stash(self, wf):
        assert "RUNNER_TEMP" in wf
        assert "git stash" not in wf

    def test_configures_git_user(self, wf):
        assert "bve-bot" in wf

    def test_only_commits_ledger(self, wf):
        assert "evidence_ledger.jsonl" in wf

    def test_skips_commit_if_no_changes(self, wf):
        assert "No ledger changes to commit" in wf

    def test_handles_orphan_branch_creation(self, wf):
        assert "--orphan data" in wf

    def test_uses_switch_not_stash(self, wf):
        assert "git switch" in wf


class TestNoDestructiveOperations:
    def test_no_force_push(self, wf):
        assert "push --force" not in wf

    def test_no_git_reset_hard(self, wf):
        assert "reset --hard" not in wf

    def test_no_delete_branch(self, wf):
        assert "branch -D" not in wf

    def test_does_not_commit_report_files(self, wf):
        # Only ledger should be git-added, not report CSVs
        assert "ranked_targets.csv" not in wf
        assert "screen_result.json" not in wf
