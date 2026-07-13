from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from bve.se.acquisition.connectors import TargetQuery
from bve.se.acquisition.corpus_store import CorpusStore
from bve.se.acquisition.policy import LiveSourcePolicy
from bve.se.acquisition.source_health import SourceHealth
from bve.se.live_run import LiveRunMode, SELivePipelineError, run_live_pipeline
from bve.se.release import build_release_manifest, required_release_files, sha256_file
from bve.se.schemas.contracts import BuyerProblemV2, SourceTier


AS_OF = date(2026, 7, 12)
SPECIFICATION_PATH = "research/se_benchmarks/live_pipeline/production_validation_spec.yaml"


def _problem() -> BuyerProblemV2:
    return BuyerProblemV2.model_validate(
        {
            "schema_version": "se_buyer_problem_v2",
            "problem_id": "live-pipeline-test",
            "version": "1.0.0",
            "buyer": {"buyer_id": "buyer", "name": "Buyer", "as_of_date": AS_OF},
            "strategic_gap": {
                "therapeutic_areas": ["oncology"],
                "target_expression": {
                    "operator": "ANY",
                    "targets": [{"canonical_id": "CD19", "label": "CD19"}],
                },
                "modalities": ["T_CELL_ENGAGER"],
                "evidence_floor": {
                    "minimum_stage": None,
                    "human_poc_required": False,
                },
                "acceptable_deal_routes": [],
            },
        }
    )


def _policy() -> LiveSourcePolicy:
    return LiveSourcePolicy.model_validate(
        {
            "policy_version": "test-v1",
            "required_source_families": ["clinicaltrials_gov"],
            "supported_targets": ["CD19"],
            "supported_modalities": ["T_CELL_ENGAGER"],
        }
    )


def _release(tmp_path: Path, policy: LiveSourcePolicy):
    repo = tmp_path / "repo"
    repo.mkdir()
    fixture_files = {
        "src/bve/se/__init__.py": "\n",
        "src/bve/cli/se_run.py": "# test entry point\n",
        ".github/workflows/se_public_pipeline.yml": "name: test\n",
        "examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml": "problem: test\n",
        "examples/configs/se/live_cd19_bcma_tce_policy.yaml": "policy: test\n",
        "pyproject.toml": "[project]\nname = 'test'\n",
        "requirements/se-public-pipeline.txt": "pydantic==2.12.5\n",
        SPECIFICATION_PATH: "specification: test\n",
    }
    for relative_path, content in fixture_files.items():
        target = repo / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    (repo / "validated.py").write_text("validated live glue\n")
    files = [*required_release_files(repo, SPECIFICATION_PATH), "validated.py"]
    release = build_release_manifest(
        release_id="test-release",
        validated_on=date(2026, 7, 1),
        interval_days=180,
        policy_hash=policy.configuration_hash,
        specification_path=SPECIFICATION_PATH,
        specification_hash=sha256_file(repo / SPECIFICATION_PATH),
        evaluator_version="test-evaluator-v1",
        repo_root=repo,
        files=files,
    )
    return repo, release


class HealthyClinicalTrialsConnector:
    source_family = "clinicaltrials_gov"

    def acquire(
        self,
        store: CorpusStore,
        *,
        targets: list[TargetQuery],
        modality_terms: list[str],
        as_of_date: date,
    ) -> SourceHealth:
        assert targets and modality_terms
        protocol = {
            "identificationModule": {
                "nctId": "NCT00000001",
                "briefTitle": "CLN-978 CD19 T-cell engager",
            },
            "sponsorCollaboratorsModule": {
                "leadSponsor": {"name": "Example Bio"}
            },
            "statusModule": {
                "overallStatus": "RECRUITING",
                "lastUpdatePostDateStruct": {"date": "2026-07-11"},
            },
            "conditionsModule": {"conditions": ["B-cell lymphoma"]},
            "armsInterventionsModule": {
                "interventions": [
                    {
                        "name": "CLN-978",
                        "description": "CD19-directed CD3 bispecific T-cell engager",
                    }
                ]
            },
        }
        store.add(
            source_family=self.source_family,
            source_url="https://clinicaltrials.gov/study/NCT00000001",
            publisher="ClinicalTrials.gov",
            document_type="trial_registry_record",
            source_tier=SourceTier.REGISTRY,
            raw_payload=protocol,
            text="CLN-978 CD19 CD3 T-cell engager B-cell lymphoma",
            title="CLN-978 study",
            as_of_date=as_of_date,
            native_snapshot=True,
        )
        return SourceHealth(
            source_family=self.source_family,
            connector_succeeded=True,
            query_returned_results=True,
            raw_record_count=1,
            documents_parsed=1,
            documents_indexed=1,
        )


class FailedConnector:
    source_family = "clinicaltrials_gov"

    def acquire(self, store, *, targets, modality_terms, as_of_date):
        return SourceHealth(
            source_family=self.source_family,
            connector_succeeded=False,
            query_returned_results=False,
            error="upstream unavailable",
        )


class NoDataFdaConnector:
    source_family = "fda_label"

    def acquire(self, store, *, targets, modality_terms, as_of_date):
        return SourceHealth(
            source_family=self.source_family,
            connector_succeeded=True,
            query_returned_results=False,
        )


class FalseHealthyConnector:
    source_family = "clinicaltrials_gov"

    def acquire(self, store, *, targets, modality_terms, as_of_date):
        return SourceHealth(
            source_family=self.source_family,
            connector_succeeded=True,
            query_returned_results=True,
            raw_record_count=1,
            documents_parsed=1,
            documents_indexed=1,
        )


def test_live_run_promotes_immutable_artifacts_and_is_idempotent(tmp_path: Path) -> None:
    policy = _policy()
    repo, release = _release(tmp_path, policy)
    output = tmp_path / "output"
    first = run_live_pipeline(
        _problem(),
        policy,
        mode=LiveRunMode.LIVE,
        output_root=output,
        repo_root=repo,
        release=release,
        connectors=[HealthyClinicalTrialsConnector()],
        as_of_date=AS_OF,
        run_id="live-test-run",
    )

    assert first.status == "PROMOTED"
    assert first.receipt.status == "SEALED"
    assert first.result is not None
    assert first.result.run_manifest.status.value == "CONVERGED"
    assert [asset.canonical_name for asset in first.result.candidates] == ["CLN-978"]
    assert first.result.eligible_asset_ids == [first.result.candidates[0].asset_id]
    assert (first.run_dir / "artifact_manifest.json").is_file()
    assert (first.run_dir / "corpus_seal.json").is_file()
    current = json.loads((output / "CURRENT.json").read_text())
    assert current["run_id"] == "live-test-run"

    reused = run_live_pipeline(
        _problem(),
        policy,
        mode=LiveRunMode.LIVE,
        output_root=output,
        repo_root=repo,
        release=release,
        connectors=[HealthyClinicalTrialsConnector()],
        as_of_date=AS_OF,
    )
    assert reused.reused is True
    assert reused.run_dir == first.run_dir


def test_required_source_failure_is_quarantined_and_never_promoted(tmp_path: Path) -> None:
    policy = _policy()
    repo, release = _release(tmp_path, policy)
    output = tmp_path / "output"

    with pytest.raises(SELivePipelineError, match="required source") as raised:
        run_live_pipeline(
            _problem(),
            policy,
            mode=LiveRunMode.LIVE,
            output_root=output,
            repo_root=repo,
            release=release,
            connectors=[FailedConnector()],
            as_of_date=AS_OF,
            run_id="failed-run",
        )

    assert raised.value.exit_code == 3
    assert not (output / "CURRENT.json").exists()
    assert (output / "runs" / "failed-run" / "failure.json").is_file()


def test_required_no_data_is_preserved_and_does_not_block_promotion(tmp_path: Path) -> None:
    policy = _policy().model_copy(
        update={"required_source_families": ("clinicaltrials_gov", "fda_label")}
    )
    repo, release = _release(tmp_path, policy)

    outcome = run_live_pipeline(
        _problem(),
        policy,
        mode=LiveRunMode.LIVE,
        output_root=tmp_path / "output",
        repo_root=repo,
        release=release,
        connectors=[HealthyClinicalTrialsConnector(), NoDataFdaConnector()],
        as_of_date=AS_OF,
        run_id="no-data-run",
    )

    assert outcome.status == "PROMOTED"
    health = json.loads((outcome.run_dir / "source_health.json").read_text())
    assert {source["source_family"]: source["verdict"] for source in health["sources"]} == {
        "clinicaltrials_gov": "OK",
        "fda_label": "NO_DATA",
    }
    assert not health["production_failures"]


def test_connector_cannot_claim_health_without_sealed_documents(tmp_path: Path) -> None:
    policy = _policy()
    repo, release = _release(tmp_path, policy)

    with pytest.raises(SELivePipelineError, match="reports 1 raw records but wrote none") as raised:
        run_live_pipeline(
            _problem(),
            policy,
            mode=LiveRunMode.LIVE,
            output_root=tmp_path / "output",
            repo_root=repo,
            release=release,
            connectors=[FalseHealthyConnector()],
            as_of_date=AS_OF,
            run_id="false-health",
        )

    assert raised.value.exit_code == 3


def test_replay_uses_sealed_corpus_without_network_or_current_promotion(
    tmp_path: Path,
) -> None:
    policy = _policy()
    repo, release = _release(tmp_path, policy)
    live_output = tmp_path / "live"
    live = run_live_pipeline(
        _problem(),
        policy,
        mode=LiveRunMode.LIVE,
        output_root=live_output,
        repo_root=repo,
        release=release,
        connectors=[HealthyClinicalTrialsConnector()],
        as_of_date=AS_OF,
        run_id="source-live-run",
    )
    replay_output = tmp_path / "replay"

    replay_problem = _problem().model_copy(
        update={
            "buyer": _problem().buyer.model_copy(
                update={"as_of_date": date(2026, 7, 10)}
            )
        }
    )
    replay = run_live_pipeline(
        replay_problem,
        policy,
        mode=LiveRunMode.REPLAY,
        output_root=replay_output,
        repo_root=repo,
        replay_corpus=live.run_dir / "corpus",
        run_id="replay-run",
    )

    assert replay.receipt.status == "VERIFIED_REPLAY"
    assert replay.result is not None
    assert replay.result.candidates[0].canonical_name == "CLN-978"
    assert replay.receipt.as_of_date == AS_OF
    assert not (replay_output / "CURRENT.json").exists()


def test_live_release_is_verified_before_connector_runs(tmp_path: Path) -> None:
    policy = _policy()
    repo, release = _release(tmp_path, policy)
    (repo / "validated.py").write_text("changed after validation\n")

    with pytest.raises(Exception, match="validated file changed"):
        run_live_pipeline(
            _problem(),
            policy,
            mode=LiveRunMode.LIVE,
            output_root=tmp_path / "output",
            repo_root=repo,
            release=release,
            connectors=[HealthyClinicalTrialsConnector()],
            as_of_date=AS_OF,
        )

    assert not (tmp_path / "output" / "runs").exists()


def test_replay_only_policy_cannot_be_used_for_live_acquisition(tmp_path: Path) -> None:
    policy = _policy().model_copy(update={"live_enabled": False})
    repo, release = _release(tmp_path, policy)

    with pytest.raises(SELivePipelineError, match="replay-only") as raised:
        run_live_pipeline(
            _problem(),
            policy,
            mode=LiveRunMode.LIVE,
            output_root=tmp_path / "output",
            repo_root=repo,
            release=release,
            connectors=[HealthyClinicalTrialsConnector()],
            as_of_date=AS_OF,
        )

    assert raised.value.exit_code == 2


def test_dry_run_accepts_as_of_used_by_live_release_verification(
    tmp_path: Path,
    monkeypatch,
) -> None:
    policy = _policy()
    repo, release = _release(tmp_path, policy)
    monkeypatch.setenv("BVE_SE_USER_AGENT", "BVE test operator tests@example.com")

    outcome = run_live_pipeline(
        _problem(),
        policy,
        mode=LiveRunMode.DRY_RUN,
        output_root=tmp_path / "output",
        repo_root=repo,
        release=release,
        as_of_date=AS_OF,
    )

    assert outcome.receipt.status == "DRY_RUN"
    assert outcome.receipt.as_of_date == AS_OF


def test_dry_run_requires_release_and_live_http_identity(tmp_path: Path, monkeypatch) -> None:
    policy = _policy()
    with pytest.raises(SELivePipelineError, match="requires a verified release") as missing:
        run_live_pipeline(
            _problem(),
            policy,
            mode=LiveRunMode.DRY_RUN,
            output_root=tmp_path / "output",
            repo_root=tmp_path,
            as_of_date=AS_OF,
        )
    assert missing.value.exit_code == 2

    repo, release = _release(tmp_path, policy)
    monkeypatch.delenv("BVE_SE_USER_AGENT", raising=False)
    with pytest.raises(SELivePipelineError, match="BVE_SE_USER_AGENT") as missing_identity:
        run_live_pipeline(
            _problem(),
            policy,
            mode=LiveRunMode.DRY_RUN,
            output_root=tmp_path / "output",
            repo_root=repo,
            release=release,
            as_of_date=AS_OF,
        )
    assert missing_identity.value.exit_code == 2


def test_replay_rejects_as_of_override(tmp_path: Path) -> None:
    with pytest.raises(SELivePipelineError, match="not allowed in replay mode") as raised:
        run_live_pipeline(
            _problem(),
            _policy(),
            mode=LiveRunMode.REPLAY,
            output_root=tmp_path / "output",
            repo_root=tmp_path,
            replay_corpus=tmp_path / "corpus",
            as_of_date=AS_OF,
        )

    assert raised.value.exit_code == 2


def test_replay_rejects_unverified_release_metadata(tmp_path: Path) -> None:
    policy = _policy()
    repo, release = _release(tmp_path, policy)

    with pytest.raises(SELivePipelineError, match="not allowed in replay mode") as raised:
        run_live_pipeline(
            _problem(),
            policy,
            mode=LiveRunMode.REPLAY,
            output_root=tmp_path / "output",
            repo_root=repo,
            release=release,
            replay_corpus=tmp_path / "corpus",
        )

    assert raised.value.exit_code == 2


@pytest.mark.parametrize("run_id", ["../escape", "/tmp/escape", "nested/run", ".hidden"])
def test_run_id_is_a_safe_single_path_component(tmp_path: Path, run_id: str) -> None:
    policy = _policy()
    repo, release = _release(tmp_path, policy)

    with pytest.raises(SELivePipelineError) as raised:
        run_live_pipeline(
            _problem(),
            policy,
            mode=LiveRunMode.LIVE,
            output_root=tmp_path / "output",
            repo_root=repo,
            release=release,
            connectors=[HealthyClinicalTrialsConnector()],
            as_of_date=AS_OF,
            run_id=run_id,
        )

    assert raised.value.exit_code == 2
    assert not (tmp_path / "escape").exists()


def test_reuse_verifies_current_anchors_and_rejects_unlisted_artifacts(
    tmp_path: Path,
) -> None:
    policy = _policy()
    repo, release = _release(tmp_path, policy)
    output = tmp_path / "output"
    first = run_live_pipeline(
        _problem(),
        policy,
        mode=LiveRunMode.LIVE,
        output_root=output,
        repo_root=repo,
        release=release,
        connectors=[HealthyClinicalTrialsConnector()],
        as_of_date=AS_OF,
        run_id="anchored-run",
    )
    (first.run_dir / "unlisted.txt").write_text("unexpected\n")

    with pytest.raises(SELivePipelineError, match="unlisted files") as raised:
        run_live_pipeline(
            _problem(),
            policy,
            mode=LiveRunMode.LIVE,
            output_root=output,
            repo_root=repo,
            release=release,
            connectors=[HealthyClinicalTrialsConnector()],
            as_of_date=AS_OF,
        )

    assert raised.value.exit_code == 5


def test_reuse_rejects_tampered_current_receipt_anchor(tmp_path: Path) -> None:
    policy = _policy()
    repo, release = _release(tmp_path, policy)
    output = tmp_path / "output"
    run_live_pipeline(
        _problem(),
        policy,
        mode=LiveRunMode.LIVE,
        output_root=output,
        repo_root=repo,
        release=release,
        connectors=[HealthyClinicalTrialsConnector()],
        as_of_date=AS_OF,
        run_id="tamper-test",
    )
    current_path = output / "CURRENT.json"
    current = json.loads(current_path.read_text())
    current["receipt_sha256"] = "0" * 64
    current_path.write_text(json.dumps(current))

    with pytest.raises(SELivePipelineError, match="receipt hash") as raised:
        run_live_pipeline(
            _problem(),
            policy,
            mode=LiveRunMode.LIVE,
            output_root=output,
            repo_root=repo,
            release=release,
            connectors=[HealthyClinicalTrialsConnector()],
            as_of_date=AS_OF,
        )

    assert raised.value.exit_code == 5
