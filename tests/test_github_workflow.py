"""
Smoke tests for .github/workflows/weekly_bve_run.yml.

These tests validate that the workflow file exists and contains the
required structure without needing to run GitHub Actions locally.
"""
from __future__ import annotations

from pathlib import Path

import pytest

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "weekly_bve_run.yml"


@pytest.fixture(scope="module")
def workflow_text() -> str:
    assert WORKFLOW_PATH.exists(), f"Workflow file not found: {WORKFLOW_PATH}"
    return WORKFLOW_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Workflow file exists
# ---------------------------------------------------------------------------

class TestWorkflowFileExists:
    def test_file_exists(self):
        assert WORKFLOW_PATH.exists(), f"Missing: {WORKFLOW_PATH}"

    def test_file_is_yaml(self):
        assert WORKFLOW_PATH.suffix == ".yml"

    def test_file_is_nonempty(self):
        assert WORKFLOW_PATH.stat().st_size > 100


# ---------------------------------------------------------------------------
# 2. Workflow has schedule and workflow_dispatch
# ---------------------------------------------------------------------------

class TestWorkflowTriggers:
    def test_has_schedule(self, workflow_text):
        assert "schedule:" in workflow_text

    def test_has_cron_entry(self, workflow_text):
        assert "cron:" in workflow_text

    def test_has_workflow_dispatch(self, workflow_text):
        assert "workflow_dispatch:" in workflow_text

    def test_workflow_dispatch_has_inputs(self, workflow_text):
        assert "inputs:" in workflow_text

    def test_has_score_mode_input(self, workflow_text):
        assert "score_mode" in workflow_text

    def test_has_lookback_days_input(self, workflow_text):
        assert "lookback_days" in workflow_text

    def test_has_as_of_date_input(self, workflow_text):
        assert "as_of_date" in workflow_text


# ---------------------------------------------------------------------------
# 3. Workflow calls bve-weekly-run
# ---------------------------------------------------------------------------

class TestWorkflowCallsWeeklyRun:
    def test_calls_bve_weekly_run(self, workflow_text):
        assert "bve-weekly-run" in workflow_text

    def test_passes_targets_flag(self, workflow_text):
        assert "--targets" in workflow_text

    def test_passes_acquirers_flag(self, workflow_text):
        assert "--acquirers" in workflow_text

    def test_passes_score_mode_flag(self, workflow_text):
        assert "--score-mode" in workflow_text

    def test_passes_ingest_live_flag(self, workflow_text):
        assert "--ingest-live" in workflow_text

    def test_passes_lookback_days_flag(self, workflow_text):
        assert "--lookback-days" in workflow_text

    def test_passes_output_flag(self, workflow_text):
        assert "--output" in workflow_text


# ---------------------------------------------------------------------------
# 4. Workflow uploads artifacts
# ---------------------------------------------------------------------------

class TestWorkflowArtifacts:
    def test_has_upload_artifact_step(self, workflow_text):
        assert "upload-artifact" in workflow_text

    def test_uses_upload_artifact_v4(self, workflow_text):
        assert "actions/upload-artifact@v4" in workflow_text

    def test_artifact_name_includes_date(self, workflow_text):
        # Artifact name should reference the resolved date
        assert "as_of_date" in workflow_text

    def test_artifact_targets_outputs_dir(self, workflow_text):
        assert "outputs/weekly" in workflow_text

    def test_artifact_has_if_no_files_found_error(self, workflow_text):
        assert "if-no-files-found: error" in workflow_text


# ---------------------------------------------------------------------------
# 5. Workflow does NOT auto-commit or push
# ---------------------------------------------------------------------------

class TestNoAutomaticGitOperations:
    def test_no_git_push(self, workflow_text):
        assert "git push" not in workflow_text

    def test_no_git_commit(self, workflow_text):
        assert "git commit" not in workflow_text

    def test_no_force_push(self, workflow_text):
        assert "push --force" not in workflow_text

    def test_no_git_add(self, workflow_text):
        # git add is a write operation — should not be in the workflow
        assert "git add" not in workflow_text


# ---------------------------------------------------------------------------
# 6. Workflow infrastructure checks
# ---------------------------------------------------------------------------

class TestWorkflowInfrastructure:
    def test_uses_ubuntu_latest(self, workflow_text):
        assert "ubuntu-latest" in workflow_text

    def test_uses_python_311(self, workflow_text):
        assert "3.11" in workflow_text

    def test_uses_checkout_v4(self, workflow_text):
        assert "actions/checkout@v4" in workflow_text

    def test_uses_setup_python_v5(self, workflow_text):
        assert "actions/setup-python@v5" in workflow_text

    def test_has_timeout_minutes(self, workflow_text):
        assert "timeout-minutes" in workflow_text

    def test_installs_package(self, workflow_text):
        assert "pip install" in workflow_text

    def test_resolves_date_with_step_output(self, workflow_text):
        assert "GITHUB_OUTPUT" in workflow_text
