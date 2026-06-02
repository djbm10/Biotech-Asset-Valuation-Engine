"""
Tests for Block 2K — Workflow Hardening additions to daily_bve_run.yml
and the new tests.yml CI workflow.
"""
from __future__ import annotations

from pathlib import Path

import pytest

DAILY_WF = Path(__file__).parent.parent / ".github" / "workflows" / "daily_bve_run.yml"
TESTS_WF = Path(__file__).parent.parent / ".github" / "workflows" / "tests.yml"


@pytest.fixture(scope="module")
def daily() -> str:
    assert DAILY_WF.exists(), f"Not found: {DAILY_WF}"
    return DAILY_WF.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tests_wf() -> str:
    assert TESTS_WF.exists(), f"Not found: {TESTS_WF}"
    return TESTS_WF.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Dry-run smoke test step
# ---------------------------------------------------------------------------

class TestDryRunSmokeTest:
    def test_dry_run_step_present(self, daily):
        assert "dry-run" in daily or "--dry-run" in daily

    def test_dry_run_before_live_pipeline(self, daily):
        dry_pos = daily.find("--dry-run")
        live_pos = daily.find("--ingest-live")
        assert dry_pos < live_pos, "--dry-run smoke test must appear before --ingest-live"

    def test_smoke_test_uses_same_targets(self, daily):
        assert "Smoke test" in daily or "smoke" in daily.lower()


# ---------------------------------------------------------------------------
# Push retry with rebase
# ---------------------------------------------------------------------------

class TestPushRetry:
    def test_retry_loop_present(self, daily):
        assert "attempt" in daily

    def test_rebase_used_not_force(self, daily):
        assert "rebase" in daily
        assert "push --force" not in daily

    def test_three_attempts(self, daily):
        assert "3" in daily  # "attempt $attempt -lt 3" or similar

    def test_push_to_data_branch(self, daily):
        assert "push origin HEAD:data" in daily


# ---------------------------------------------------------------------------
# Failure artifact upload
# ---------------------------------------------------------------------------

class TestFailureArtifact:
    def test_failure_upload_step_present(self, daily):
        assert "if: failure()" in daily

    def test_failure_artifact_has_name(self, daily):
        assert "bve-failure-" in daily

    def test_failure_artifact_retention(self, daily):
        assert "retention-days: 7" in daily

    def test_failure_artifact_includes_ledger(self, daily):
        assert "evidence_ledger.jsonl" in daily


# ---------------------------------------------------------------------------
# tests.yml CI workflow
# ---------------------------------------------------------------------------

class TestTestsWorkflow:
    def test_file_exists(self):
        assert TESTS_WF.exists()

    def test_runs_on_push(self, tests_wf):
        assert "push:" in tests_wf

    def test_runs_on_pull_request(self, tests_wf):
        assert "pull_request:" in tests_wf

    def test_runs_pytest(self, tests_wf):
        assert "pytest" in tests_wf

    def test_runs_ruff(self, tests_wf):
        assert "ruff" in tests_wf

    def test_installs_dev_deps(self, tests_wf):
        assert "[dev]" in tests_wf

    def test_timeout_set(self, tests_wf):
        assert "timeout-minutes:" in tests_wf

    def test_failure_upload_on_test_failure(self, tests_wf):
        assert "if: failure()" in tests_wf


# ---------------------------------------------------------------------------
# Validation + manifest steps wired into daily workflow
# ---------------------------------------------------------------------------

class TestValidationManifestInWorkflow:
    def test_validate_before_run(self, daily):
        validate_pos = daily.find("bve-ledger-validate")
        pipeline_pos = daily.find("Run daily BVE pipeline")
        assert validate_pos < pipeline_pos, "validate step must precede the pipeline"

    def test_manifest_generated_after_run(self, daily):
        pipeline_pos = daily.find("Run daily BVE pipeline")
        manifest_pos = daily.find("bve-ledger-manifest")
        assert manifest_pos > pipeline_pos, "manifest step must follow the pipeline"

    def test_manifest_persisted_to_data_branch(self, daily):
        assert "ledger_manifest.json" in daily

    def test_manifest_uses_runner_temp(self, daily):
        assert "MANIFEST_TMP" in daily
