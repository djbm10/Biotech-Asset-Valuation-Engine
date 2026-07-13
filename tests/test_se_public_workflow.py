"""Structural guardrails for the scheduled public-data S&E production workflow."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import re

import pytest
import yaml

from bve.se.acquisition.policy import LiveSourcePolicy
from bve.se.release import (
    LiveReleaseManifest,
    required_release_files,
    verify_release_manifest,
)


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "se_public_pipeline.yml"
)
PROBLEM = "examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml"
POLICY = "examples/configs/se/live_cd19_bcma_tce_policy.yaml"
RELEASE = "research/se_benchmarks/live_pipeline/live_release_manifest.yaml"
OUTPUT = "outputs/se/production"
RUNTIME_REQUIREMENTS = (
    Path(__file__).resolve().parents[1] / "requirements" / "se-public-pipeline.txt"
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def workflow() -> str:
    assert WORKFLOW.is_file()
    return WORKFLOW.read_text(encoding="utf-8")


def test_weekly_manual_triggers_and_isolated_concurrency(workflow: str) -> None:
    assert "schedule:" in workflow
    assert "cron:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "group: bve-se-public-pipeline" in workflow
    assert "cancel-in-progress: false" in workflow


def test_least_privilege_checkout_and_python_runtime(workflow: str) -> None:
    assert "permissions:\n  contents: read\n  actions: read" in workflow
    assert "contents: write" not in workflow
    assert "actions: write" not in workflow
    assert "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683" in workflow
    assert "fetch-depth: 0" in workflow
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in workflow
    assert 'python-version: "3.12"' in workflow
    assert "MPLCONFIGDIR: /tmp/mpl" in workflow
    assert "PYTHONPATH: src" in workflow
    assert "requirements/se-public-pipeline.txt" in workflow
    assert "--no-deps" in workflow
    assert "--only-binary=:all:" in workflow
    assert "--require-hashes" in workflow
    assert 'python -m pip install -e ".[dev]"' not in workflow
    assert "pip install --upgrade pip" not in workflow


def test_all_third_party_actions_are_pinned_to_full_shas(workflow: str) -> None:
    uses = re.findall(r"^\s*uses:\s*([^\s]+)", workflow, flags=re.MULTILINE)
    assert uses
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in uses)
    assert "# v4.2.2" in workflow
    assert "# v5.6.0" in workflow
    assert "# v4.3.0" in workflow
    assert workflow.count("# v4.6.2") == 2


def test_runtime_requirements_are_minimal_and_exactly_pinned() -> None:
    locked = RUNTIME_REQUIREMENTS.read_text(encoding="utf-8")
    requirements = re.findall(
        r"^([A-Za-z0-9_.-]+)==([^=\s]+) \\\n"
        r"    --hash=sha256:([0-9a-f]{64})$",
        locked,
        flags=re.MULTILINE,
    )
    assert len(requirements) == 11
    assert {name.lower() for name, _version, _digest in requirements} == {
        "annotated-types",
        "certifi",
        "charset-normalizer",
        "idna",
        "pydantic",
        "pydantic-core",
        "pyyaml",
        "requests",
        "typing-extensions",
        "typing-inspection",
        "urllib3",
    }


def test_checked_in_release_exists_and_verifies_current_runtime_closure() -> None:
    release_path = REPOSITORY_ROOT / RELEASE
    policy_path = REPOSITORY_ROOT / POLICY
    assert release_path.is_file()
    release = LiveReleaseManifest.model_validate(
        yaml.safe_load(release_path.read_text(encoding="utf-8"))
    )
    policy = LiveSourcePolicy.model_validate(
        yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    )

    assert release.schema_version == "se_live_release_manifest_v2"
    assert set(required_release_files(REPOSITORY_ROOT, release.specification_path)) <= set(
        release.validated_files
    )
    verify_release_manifest(
        release,
        REPOSITORY_ROOT,
        policy.configuration_hash,
        date.today(),
    )


def test_requires_non_logged_operator_user_agent(workflow: str) -> None:
    assert "BVE_SE_USER_AGENT: ${{ vars.BVE_SE_USER_AGENT }}" in workflow
    preflight = workflow[
        workflow.index("Preflight operator identity") : workflow.index(
            "Install exact S&E runtime dependencies"
        )
    ]
    assert "Repository variable BVE_SE_USER_AGENT is required" in preflight
    assert "operator contact email" in preflight
    assert "set -x" not in workflow
    assert 'echo "$BVE_SE_USER_AGENT"' not in workflow


def test_prior_success_is_verified_before_atomic_restore(workflow: str) -> None:
    locate = workflow.index("Locate most recent successful production run")
    download = workflow.index("Download prior successful production artifact")
    restore = workflow.index("Verify and restore prior promoted state")
    dry_run = workflow.index("Verify release and configuration (dry-run)")
    assert locate < download < restore < dry_run
    assert "status=success" in workflow
    assert "actions/workflows/se_public_pipeline.yml/runs" in workflow
    assert "actions/runs/${candidate_run_id}/artifacts" in workflow
    assert ".expired == false" in workflow
    assert "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093" in workflow
    assert "name: ${{ steps.prior_run.outputs.artifact_name }}" in workflow
    assert "merge-multiple" not in workflow
    assert workflow.count("verify_current_run") == 4
    assert "_load_reusable_run" not in workflow
    assert "os.replace(staging_run, target_run)" in workflow
    assert "refusing to overwrite restored run" in workflow


def test_artifact_names_are_unique_across_workflow_reruns(workflow: str) -> None:
    assert workflow.count("${{ github.run_id }}-${{ github.run_attempt }}") == 2


def test_release_dry_run_precedes_live_run(workflow: str) -> None:
    dry_run = workflow.index("--dry-run")
    live_run = workflow.index("--live", dry_run + 1)
    assert dry_run < live_run
    assert workflow.count("python -m bve.cli.se_run") == 2
    assert workflow.count("set -euo pipefail") >= 4
    assert "continue-on-error" not in workflow
    assert "|| true" not in workflow


def test_commands_use_production_paths_and_utc_as_of(workflow: str) -> None:
    for path in (PROBLEM, POLICY, RELEASE, OUTPUT):
        assert path in workflow
    assert "date -u +%F" in workflow
    live_block = workflow[workflow.index("--live") : workflow.index(
        "Upload successful production artifacts"
    )]
    assert '--as-of "${{ steps.run_date.outputs.as_of }}"' in live_block
    assert '--problem "$PROBLEM_PATH"' in live_block
    assert '--source-policy "$POLICY_PATH"' in live_block
    assert '--release-manifest "$RELEASE_PATH"' in live_block
    assert '--output-root "$OUTPUT_ROOT"' in live_block
    dry_run_block = workflow[workflow.index("--dry-run") : workflow.index("--live")]
    assert '--as-of "${{ steps.run_date.outputs.as_of }}"' in dry_run_block


def test_success_and_failure_artifact_retention(workflow: str) -> None:
    success = workflow[workflow.index("Upload successful production artifacts") :]
    assert "if: success()" in success
    assert "retention-days: 90" in success
    assert "if-no-files-found: error" in success
    diagnostics = workflow[workflow.index("Upload failure diagnostics") :]
    assert "if: always()" in diagnostics
    assert "retention-days: 14" in diagnostics
    assert "if-no-files-found: warn" in diagnostics
    assert workflow.count(
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
    ) == 2


def test_summary_links_current_result_and_monitoring(workflow: str) -> None:
    summary = workflow[workflow.index("Write S&E job summary") :]
    assert "if: always()" in summary
    assert "GITHUB_STEP_SUMMARY" in summary
    assert "CURRENT.json" in summary
    assert "result.json" in summary
    assert "monitoring.json" in summary


@pytest.mark.parametrize(
    "forbidden",
    (
        "git add",
        "git commit",
        "git push",
        "contents: write",
        "docs/advice",
        "Meeting Prep",
        "holdout_labels_private",
        "--no-verify",
    ),
)
def test_never_publishes_git_or_private_material(workflow: str, forbidden: str) -> None:
    assert forbidden not in workflow
