"""Fail-closed, one-command live public-data acquisition-to-asset orchestration."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import uuid
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from bve.se.acquisition.corpus_store import (
    CorpusValidationReport,
    CorpusStore,
    IndexStatus,
    ParserStatus,
)
from bve.se.acquisition.policy import LiveSourcePolicy
from bve.se.acquisition.http import configured_user_agent
from bve.se.acquisition.runner import Connector, connectors_for_policy, run_acquisition
from bve.se.acquisition.source_health import (
    SourceHealth,
    SourceHealthReport,
    SourceVerdict,
)
from bve.se.discovery.corpus import adapters_from_corpus
from bve.se.operations import SEAuditEvent, append_audit_event
from bve.se.pipeline import SESearchResult, run_landscape_search
from bve.se.release import (
    LiveReleaseManifest,
    sha256_file,
    verify_release_manifest,
)
from bve.se.reporting.memo import render_search_memo
from bve.se.schemas.contracts import BuyerProblemV2, RunStatus


class LiveRunMode(str, Enum):
    LIVE = "live"
    REPLAY = "replay"
    DRY_RUN = "dry_run"


class SELivePipelineError(RuntimeError):
    """A classified production stop with a stable CLI exit code."""

    def __init__(self, message: str, *, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _validate_run_id(value: str) -> str:
    if not _RUN_ID_RE.fullmatch(value):
        raise ValueError(
            "run_id must be 1-128 characters beginning with an alphanumeric and "
            "containing only letters, digits, '.', '_', or '-'"
        )
    return value


def _validate_artifact_path(value: str) -> str:
    if not value or value != value.strip() or "\\" in value or "\x00" in value:
        raise ValueError("artifact path must be a canonical relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("artifact path must not be absolute or contain unsafe segments")
    if path.as_posix() != value:
        raise ValueError("artifact path must use canonical POSIX form")
    return value


class ArtifactDigest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str = Field(pattern=_SHA256_PATTERN)
    size_bytes: int = Field(ge=0)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_artifact_path(value)


class ArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["se_run_artifacts_v1"] = "se_run_artifacts_v1"
    run_id: str
    created_at: datetime
    artifacts: tuple[ArtifactDigest, ...]

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        return _validate_run_id(value)

    @model_validator(mode="after")
    def validate_unique_paths(self) -> "ArtifactManifest":
        paths = [artifact.path for artifact in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("artifact manifest contains duplicate paths")
        return self


class SELiveMonitoringSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    observed_at: datetime
    source_verdicts: dict[str, str]
    documents: int = Field(ge=0)
    identity_mentions: int = Field(ge=0)
    canonical_assets: int = Field(ge=0)
    claims: int = Field(ge=0)
    facts: int = Field(ge=0)
    gate_evaluations: int = Field(ge=0)
    eligible: int = Field(ge=0)
    unresolved: int = Field(ge=0)
    excluded: int = Field(ge=0)
    ranked: int = Field(ge=0)
    unknown_rate: float = Field(ge=0.0, le=1.0)
    citation_failure_rate: float = Field(ge=0.0, le=1.0)
    route_leakage_count: int = Field(ge=0)
    alerts: tuple[str, ...] = ()
    stop_reasons: tuple[str, ...] = ()


class SealedCorpusMetadata(BaseModel):
    """Portable custody record required to replay live acquisition semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["se_corpus_seal_v1"] = "se_corpus_seal_v1"
    manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    source_health_sha256: str = Field(pattern=_SHA256_PATTERN)
    policy_hash: str = Field(pattern=_SHA256_PATTERN)
    as_of_date: date
    source_counts: dict[str, int]
    validation: dict[str, object]

    @field_validator("source_counts")
    @classmethod
    def validate_source_counts(cls, values: dict[str, int]) -> dict[str, int]:
        if any(not family or count < 0 for family, count in values.items()):
            raise ValueError("source_counts must contain nonempty families and nonnegative counts")
        return values


class SELiveRunReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["se_live_run_receipt_v1"] = "se_live_run_receipt_v1"
    run_id: str
    execution_key: str = Field(min_length=64, max_length=64)
    mode: LiveRunMode
    status: Literal["SEALED", "VERIFIED_REPLAY", "DRY_RUN"]
    problem_id: str
    problem_hash: str = Field(pattern=_SHA256_PATTERN)
    as_of_date: date
    code_version: str
    policy_version: str
    policy_hash: str = Field(pattern=_SHA256_PATTERN)
    release_id: str | None = None
    release_manifest_hash: str | None = None
    corpus_manifest_hash: str = Field(pattern=_SHA256_PATTERN)
    started_at: datetime
    completed_at: datetime
    result_path: str
    artifact_manifest_path: str

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        return _validate_run_id(value)


class CurrentPointer(BaseModel):
    """Externally anchored promotion record for one immutable live run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["se_current_pointer_v1"] = "se_current_pointer_v1"
    run_id: str
    execution_key: str = Field(pattern=_SHA256_PATTERN)
    receipt_sha256: str = Field(pattern=_SHA256_PATTERN)
    artifact_manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    promoted_at: datetime

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        return _validate_run_id(value)


class SELiveRunOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_dir: Path
    receipt: SELiveRunReceipt
    result: SESearchResult | None = None
    reused: bool = False

    @property
    def status(self) -> str:
        return "PROMOTED" if self.receipt.mode is LiveRunMode.LIVE else self.receipt.status


def _canonical_hash(payload: object) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _problem_hash(problem: BuyerProblemV2) -> str:
    return _canonical_hash(problem.model_dump(mode="json"))


def _code_version() -> str:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return f"{head}+dirty" if dirty else head
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _run_directory(output_root: Path, run_id: str) -> Path:
    """Return a safe lexical run path contained beneath ``output_root/runs``."""

    safe_run_id = _validate_run_id(run_id)
    runs_root = (Path(output_root) / "runs").resolve()
    candidate = runs_root / safe_run_id
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(runs_root):
        raise SELivePipelineError(
            f"run_id resolves outside output root: {safe_run_id!r}",
            exit_code=5,
        )
    if candidate.is_symlink():
        raise SELivePipelineError(
            f"run directory must not be a symbolic link: {candidate}",
            exit_code=5,
        )
    return candidate


def _write_json(path: Path, payload: object) -> None:
    serializable: object
    if isinstance(payload, BaseModel):
        serializable = payload.model_dump(mode="json")
    else:
        serializable = payload
    _atomic_write(path, json.dumps(serializable, indent=2, sort_keys=True) + "\n")


@contextmanager
def _output_lock(output_root: Path):
    output_root.mkdir(parents=True, exist_ok=True)
    lock_path = output_root / ".run.lock"
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _health_from_corpus(store: CorpusStore) -> SourceHealthReport:
    sources: list[SourceHealth] = []
    for family, documents in sorted(store.by_family().items()):
        parse_failures = sum(
            document.parser_status is not ParserStatus.OK for document in documents
        )
        parsed = sum(document.parser_status is ParserStatus.OK for document in documents)
        indexed = sum(document.index_status is IndexStatus.INDEXED for document in documents)
        sources.append(
            SourceHealth(
                source_family=family,
                connector_succeeded=True,
                query_returned_results=bool(documents),
                raw_record_count=len(documents),
                documents_parsed=parsed,
                documents_indexed=indexed,
                parse_failures=parse_failures,
            )
        )
    return SourceHealthReport(sources=sources)


def _source_health_payload(health: SourceHealthReport) -> dict[str, object]:
    return {
        "stage_summary": health.stage_summary(),
        "sources": [
            {
                **source.model_dump(mode="json"),
                "verdict": source.verdict.value,
            }
            for source in health.sources
        ],
    }


def _portable_corpus_validation(
    validation: CorpusValidationReport,
) -> dict[str, object]:
    payload = validation.model_dump(mode="json")
    payload.pop("manifest_path", None)
    return payload


def _parse_source_health_payload(payload: object) -> SourceHealthReport:
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError("sealed source health must contain a sources list")
    sources: list[SourceHealth] = []
    for entry in payload["sources"]:
        if not isinstance(entry, dict):
            raise ValueError("sealed source-health entry must be an object")
        health_fields = {key: value for key, value in entry.items() if key != "verdict"}
        source = SourceHealth.model_validate(health_fields)
        if entry.get("verdict") != source.verdict.value:
            raise ValueError(
                f"sealed source-health verdict mismatch for {source.source_family}"
            )
        sources.append(source)
    report = SourceHealthReport(sources=sources)
    report.by_family()
    return report


def _corpus_health_reconciliation_failures(
    health: SourceHealthReport,
    store: CorpusStore,
) -> list[str]:
    """Cross-check connector claims against the sealed documents they actually wrote."""

    by_health = health.by_family()
    grouped = store.by_family()
    failures = [
        f"corpus contains unreported source family: {family}"
        for family in sorted(set(grouped) - set(by_health))
    ]
    for family, source in sorted(by_health.items()):
        documents = grouped.get(family, [])
        parsed = sum(document.parser_status is ParserStatus.OK for document in documents)
        indexed = sum(document.index_status is IndexStatus.INDEXED for document in documents)
        parse_failures = len(documents) - parsed
        if source.verdict is SourceVerdict.NO_DATA:
            if documents:
                failures.append(
                    f"source {family} reports NO_DATA but wrote {len(documents)} documents"
                )
            continue
        if source.raw_record_count > 0 and not documents:
            failures.append(
                f"source {family} reports {source.raw_record_count} raw records but wrote none"
            )
            continue
        if indexed > source.documents_indexed:
            failures.append(
                f"source {family} corpus indexed count {indexed} exceeds reported "
                f"{source.documents_indexed}"
            )
        if parsed > source.documents_parsed:
            failures.append(
                f"source {family} corpus parsed count {parsed} exceeds reported "
                f"{source.documents_parsed}"
            )
        if parse_failures > source.parse_failures:
            failures.append(
                f"source {family} corpus parse failures {parse_failures} exceed reported "
                f"{source.parse_failures}"
            )
        if source.documents_indexed > 0 and indexed == 0:
            failures.append(
                f"source {family} reports indexed documents but corpus has none"
            )
    return failures


def _load_sealed_corpus(
    corpus_dir: Path,
    *,
    policy_hash: str,
    as_of_date: date,
) -> tuple[CorpusStore, SourceHealthReport, SealedCorpusMetadata]:
    store = CorpusStore(corpus_dir)
    health_path = corpus_dir / "source_health.json"
    seal_path = corpus_dir / "seal.json"
    if health_path.is_symlink() or seal_path.is_symlink():
        raise ValueError("corpus health and seal must not be symbolic links")
    seal = SealedCorpusMetadata.model_validate_json(seal_path.read_text())
    if seal.policy_hash != policy_hash:
        raise ValueError("corpus seal policy hash does not match current policy")
    if seal.as_of_date != as_of_date:
        raise ValueError("corpus seal as-of date does not match the replay problem")
    if sha256_file(store.manifest_path) != seal.manifest_sha256:
        raise ValueError("corpus manifest hash does not match portable seal")
    if sha256_file(health_path) != seal.source_health_sha256:
        raise ValueError("corpus source-health hash does not match portable seal")
    health = _parse_source_health_payload(json.loads(health_path.read_text()))
    validation = store.validate()
    counts = {
        family: len(documents) for family, documents in sorted(store.by_family().items())
    }
    if counts != seal.source_counts:
        raise ValueError("corpus source counts do not match portable seal")
    if _portable_corpus_validation(validation) != seal.validation:
        raise ValueError("corpus validation report does not match portable seal")
    return store, health, seal


def _route_errors(result: SESearchResult) -> list[str]:
    candidate_ids = [asset.asset_id for asset in result.candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        return ["canonical candidate IDs are not unique"]
    eligible = set(result.eligible_asset_ids)
    excluded = set(result.excluded_asset_ids)
    unresolved = set(result.unresolved_asset_ids)
    errors: list[str] = []
    if eligible & excluded or eligible & unresolved or excluded & unresolved:
        errors.append("candidate route sets overlap")
    routed = eligible | excluded | unresolved
    candidate_set = set(candidate_ids)
    if routed != candidate_set:
        missing = sorted(candidate_set - routed)
        extra = sorted(routed - candidate_set)
        errors.append(f"candidate route partition mismatch missing={missing} extra={extra}")
    ranked_ids = {entry.asset_id for entry in result.ranking.ranked}
    if not ranked_ids.issubset(eligible):
        errors.append("non-eligible assets entered ranking")
    if result.processing_errors:
        errors.append(f"evidence processing failures: {len(result.processing_errors)}")
    return errors


def _monitoring_snapshot(
    *,
    run_id: str,
    result: SESearchResult,
    health: SourceHealthReport,
) -> SELiveMonitoringSnapshot:
    route_errors = _route_errors(result)
    candidate_count = len(result.candidates)
    unresolved_count = len(set(result.unresolved_asset_ids))
    claim_ids = {claim.claim_id for claim in result.claims}
    cited_ranked = {
        claim_id
        for profile in result.ranking.ranked
        for claim_id in next(
            (
                candidate.supporting_claim_ids
                for candidate in result.candidates
                if candidate.asset_id == profile.asset_id
            ),
            [],
        )
        if claim_id in claim_ids
    }
    ranked_count = len(result.ranking.ranked)
    citation_failure_rate = (
        max(0, ranked_count - len(cited_ranked)) / ranked_count
        if ranked_count
        else 0.0
    )
    alerts: list[str] = []
    if candidate_count and unresolved_count == candidate_count:
        alerts.append("all discovered assets require diligence; ranking abstained")
    if citation_failure_rate:
        alerts.append("one or more ranked assets lacks a persisted supporting citation")
    if not result.gate_evaluations:
        route_errors.append("no candidate reached evidence-backed gate evaluation")
    if not result.candidates:
        route_errors.append("no canonical assets were discovered")
    return SELiveMonitoringSnapshot(
        run_id=run_id,
        observed_at=datetime.now(timezone.utc),
        source_verdicts={
            source.source_family: source.verdict.value for source in health.sources
        },
        documents=len(result.source_documents),
        identity_mentions=len(result.identity_mentions),
        canonical_assets=candidate_count,
        claims=len(result.claims),
        facts=len(result.facts),
        gate_evaluations=len(result.gate_evaluations),
        eligible=len(set(result.eligible_asset_ids)),
        unresolved=unresolved_count,
        excluded=len(set(result.excluded_asset_ids)),
        ranked=ranked_count,
        unknown_rate=unresolved_count / candidate_count if candidate_count else 1.0,
        citation_failure_rate=citation_failure_rate,
        route_leakage_count=len(route_errors),
        alerts=tuple(alerts),
        stop_reasons=tuple(route_errors),
    )


def _artifact_manifest(run_dir: Path, run_id: str) -> ArtifactManifest:
    manifest_path = run_dir / "artifact_manifest.json"
    artifacts: list[ArtifactDigest] = []
    for path in sorted(run_dir.rglob("*")):
        if path == manifest_path:
            continue
        if path.is_symlink():
            raise SELivePipelineError(
                f"run artifact must not be a symbolic link: {path.relative_to(run_dir)}",
                exit_code=5,
            )
        if not path.is_file():
            continue
        relative = path.relative_to(run_dir).as_posix()
        artifacts.append(
            ArtifactDigest(
                path=relative,
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
            )
        )
    return ArtifactManifest(
        run_id=run_id,
        created_at=datetime.now(timezone.utc),
        artifacts=tuple(artifacts),
    )


def verify_artifact_manifest(run_dir: Path, manifest: ArtifactManifest) -> None:
    failures: list[str] = []
    root = run_dir.resolve()
    manifest_path = run_dir / "artifact_manifest.json"
    if manifest_path.is_symlink():
        failures.append("artifact_manifest.json must not be a symbolic link")
    if manifest.run_id != run_dir.name:
        failures.append(
            f"artifact manifest run_id mismatch: {manifest.run_id!r} != {run_dir.name!r}"
        )
    expected_paths = {artifact.path for artifact in manifest.artifacts}
    actual_paths: set[str] = set()
    for path in sorted(run_dir.rglob("*")):
        if path.name == "artifact_manifest.json" and path.parent == run_dir:
            continue
        if path.is_symlink():
            failures.append(
                f"symbolic links are forbidden in immutable runs: "
                f"{path.relative_to(run_dir).as_posix()}"
            )
            continue
        if path.is_file():
            actual_paths.add(path.relative_to(run_dir).as_posix())
    missing_from_manifest = sorted(actual_paths - expected_paths)
    missing_from_run = sorted(expected_paths - actual_paths)
    if missing_from_manifest:
        failures.append(
            "unlisted files are present: " + ", ".join(missing_from_manifest)
        )
    if missing_from_run:
        failures.append(
            "listed artifacts are missing: " + ", ".join(missing_from_run)
        )
    for artifact in manifest.artifacts:
        lexical_path = run_dir / artifact.path
        if lexical_path.is_symlink():
            failures.append(f"artifact is a symbolic link: {artifact.path}")
            continue
        path = lexical_path.resolve()
        if not path.is_relative_to(root):
            failures.append(f"artifact path escapes run directory: {artifact.path}")
            continue
        if not path.is_file():
            failures.append(f"artifact missing: {artifact.path}")
            continue
        if path.stat().st_size != artifact.size_bytes:
            failures.append(f"artifact size changed: {artifact.path}")
            continue
        actual = sha256_file(path)
        if actual != artifact.sha256:
            failures.append(f"artifact hash changed: {artifact.path}")
    if failures:
        raise SELivePipelineError(
            "run artifact verification failed: " + "; ".join(failures),
            exit_code=5,
        )


def _load_reusable_run(
    output_root: Path,
    execution_key: str,
) -> SELiveRunOutcome | None:
    current_path = output_root / "CURRENT.json"
    if not current_path.exists():
        return None
    try:
        if current_path.is_symlink():
            raise ValueError("CURRENT.json must not be a symbolic link")
        current = CurrentPointer.model_validate_json(current_path.read_text())
        run_dir = _run_directory(output_root, current.run_id)
        if not run_dir.is_dir():
            raise ValueError(f"promoted run directory is missing: {run_dir}")
        receipt_path = run_dir / "run_receipt.json"
        manifest_path = run_dir / "artifact_manifest.json"
        if sha256_file(receipt_path) != current.receipt_sha256:
            raise ValueError("CURRENT receipt hash does not match run_receipt.json")
        if sha256_file(manifest_path) != current.artifact_manifest_sha256:
            raise ValueError(
                "CURRENT artifact-manifest hash does not match artifact_manifest.json"
            )
        receipt = SELiveRunReceipt.model_validate_json(
            receipt_path.read_text()
        )
        manifest = ArtifactManifest.model_validate_json(
            manifest_path.read_text()
        )
        verify_artifact_manifest(run_dir, manifest)
        result = SESearchResult.model_validate_json((run_dir / "result.json").read_text())
        if receipt.run_id != current.run_id or manifest.run_id != current.run_id:
            raise ValueError("CURRENT, receipt, and artifact manifest run IDs do not match")
        if receipt.execution_key != current.execution_key:
            raise ValueError("CURRENT and receipt execution keys do not match")
        if receipt.mode is not LiveRunMode.LIVE or receipt.status != "SEALED":
            raise ValueError("CURRENT must point to a SEALED live run receipt")
        if receipt.result_path != "result.json":
            raise ValueError("live run receipt has an unexpected result path")
        if receipt.artifact_manifest_path != "artifact_manifest.json":
            raise ValueError("live run receipt has an unexpected artifact-manifest path")
        if result.run_manifest.run_id != current.run_id:
            raise ValueError("CURRENT run ID does not match the search result")
        if current.execution_key != execution_key:
            return None
    except (OSError, ValueError, json.JSONDecodeError, SELivePipelineError) as exc:
        raise SELivePipelineError(
            f"CURRENT points to an invalid prior run: {exc}",
            exit_code=5,
        ) from exc
    return SELiveRunOutcome(
        run_dir=run_dir,
        receipt=receipt,
        result=result,
        reused=True,
    )


def verify_current_run(output_root: Path) -> SELiveRunOutcome:
    """Verify and return the externally promoted immutable run at ``CURRENT.json``."""

    current_path = Path(output_root) / "CURRENT.json"
    try:
        current = CurrentPointer.model_validate_json(current_path.read_text())
    except (OSError, ValueError) as exc:
        raise SELivePipelineError(f"invalid CURRENT pointer: {exc}", exit_code=5) from exc
    outcome = _load_reusable_run(Path(output_root), current.execution_key)
    if outcome is None:  # defensive: the same validated key was passed above
        raise SELivePipelineError("CURRENT verification produced no run", exit_code=5)
    return outcome


def _audit_event(
    *,
    run_id: str,
    event_type: str,
    code_version: str,
    policy_hash: str,
    release: LiveReleaseManifest | None,
    details: dict[str, object],
) -> SEAuditEvent:
    occurred_at = datetime.now(timezone.utc)
    event_key = _canonical_hash(
        [run_id, event_type, occurred_at.isoformat(), details]
    )
    return SEAuditEvent(
        event_id=f"se-event:{event_key[:24]}",
        run_id=run_id,
        event_type=event_type,
        occurred_at=occurred_at,
        code_version=code_version,
        evaluator_version=(release.evaluator_version if release else "unvalidated-replay"),
        specification_hash=(release.specification_hash if release else "0" * 64),
        source_configuration_hash=policy_hash,
        details=details,
    )


def run_live_pipeline(
    problem: BuyerProblemV2,
    policy: LiveSourcePolicy,
    *,
    mode: LiveRunMode,
    output_root: Path,
    repo_root: Path,
    release: LiveReleaseManifest | None = None,
    replay_corpus: Path | None = None,
    connectors: Sequence[Connector] | None = None,
    as_of_date: date | None = None,
    run_id: str | None = None,
) -> SELiveRunOutcome:
    """Acquire, seal, discover, resolve, gate, monitor, and atomically promote one run."""

    if mode is LiveRunMode.REPLAY and replay_corpus is None:
        raise SELivePipelineError("replay mode requires a corpus directory", exit_code=2)
    if mode is not LiveRunMode.REPLAY and replay_corpus is not None:
        raise SELivePipelineError("replay corpus is valid only in replay mode", exit_code=2)
    if mode is LiveRunMode.REPLAY and as_of_date is not None:
        raise SELivePipelineError(
            "as-of override is not allowed in replay mode",
            exit_code=2,
        )
    if mode is not LiveRunMode.LIVE and connectors is not None:
        raise SELivePipelineError(
            "connector injection is allowed only in live mode",
            exit_code=2,
        )
    if mode is LiveRunMode.REPLAY and release is not None:
        raise SELivePipelineError(
            "release manifest is not allowed in replay mode",
            exit_code=2,
        )

    effective_as_of = as_of_date or problem.buyer.as_of_date
    if mode is LiveRunMode.LIVE and as_of_date is None:
        effective_as_of = datetime.now(timezone.utc).date()
    if mode is LiveRunMode.REPLAY:
        assert replay_corpus is not None
        try:
            seal_path = Path(replay_corpus) / "seal.json"
            if seal_path.is_symlink():
                raise ValueError("corpus seal must not be a symbolic link")
            effective_as_of = SealedCorpusMetadata.model_validate_json(
                seal_path.read_text()
            ).as_of_date
        except (OSError, ValueError) as exc:
            raise SELivePipelineError(
                f"replay corpus has no valid portable seal: {exc}",
                exit_code=5,
            ) from exc
    effective_problem = problem.model_copy(
        update={
            "buyer": problem.buyer.model_copy(
                update={"as_of_date": effective_as_of}
            )
        }
    )
    policy.validate_problem(effective_problem)
    if mode in {LiveRunMode.LIVE, LiveRunMode.DRY_RUN}:
        if not policy.live_enabled:
            raise SELivePipelineError(
                f"source policy {policy.policy_version!r} is replay-only",
                exit_code=2,
            )
        if release is None:
            raise SELivePipelineError(
                f"{mode.value} mode requires a verified release manifest",
                exit_code=2,
            )
        verify_release_manifest(release, repo_root, policy.configuration_hash, effective_as_of)
        if connectors is None:
            try:
                planned = connectors_for_policy(policy)
                configured_user_agent()
            except (ValueError, RuntimeError) as exc:
                raise SELivePipelineError(
                    f"live acquisition preflight failed: {exc}",
                    exit_code=2,
                ) from exc
            planned_families = {connector.source_family for connector in planned}
            missing = sorted(set(policy.required_source_families) - planned_families)
            if missing:
                raise SELivePipelineError(
                    "live acquisition preflight has no connector for: " + ", ".join(missing),
                    exit_code=2,
                )
    code_version = _code_version()
    problem_digest = _problem_hash(effective_problem)
    corpus_input_hash = (
        sha256_file(Path(replay_corpus) / "manifest.jsonl")
        if replay_corpus is not None
        else "live"
    )
    execution_key = _canonical_hash(
        {
            "mode": mode.value,
            "problem_hash": problem_digest,
            "policy_hash": policy.configuration_hash,
            "release_hash": release.manifest_hash if release else None,
            "code_version": code_version,
            "corpus_input_hash": corpus_input_hash,
        }
    )
    output_root = Path(output_root)
    with _output_lock(output_root):
        if mode is LiveRunMode.LIVE:
            reusable = _load_reusable_run(output_root, execution_key)
            if reusable is not None:
                return reusable
        if mode is LiveRunMode.DRY_RUN:
            now = datetime.now(timezone.utc)
            receipt = SELiveRunReceipt(
                run_id=_validate_run_id(run_id or f"se-dry-{execution_key[:16]}"),
                execution_key=execution_key,
                mode=mode,
                status="DRY_RUN",
                problem_id=effective_problem.problem_id,
                problem_hash=problem_digest,
                as_of_date=effective_as_of,
                code_version=code_version,
                policy_version=policy.policy_version,
                policy_hash=policy.configuration_hash,
                release_id=release.release_id if release else None,
                release_manifest_hash=release.manifest_hash if release else None,
                corpus_manifest_hash="0" * 64,
                started_at=now,
                completed_at=now,
                result_path="",
                artifact_manifest_path="",
            )
            return SELiveRunOutcome(run_dir=output_root, receipt=receipt)

        started_at = datetime.now(timezone.utc)
        effective_run_id = run_id or (
            f"se-{effective_as_of.isoformat()}-{started_at.strftime('%H%M%S')}-"
            f"{execution_key[:10]}"
        )
        try:
            effective_run_id = _validate_run_id(effective_run_id)
        except ValueError as exc:
            raise SELivePipelineError(str(exc), exit_code=2) from exc
        run_dir = _run_directory(output_root, effective_run_id)
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise SELivePipelineError(
                f"refusing to overwrite existing immutable run: {run_dir}",
                exit_code=5,
            ) from exc
        audit_path = run_dir / "audit.jsonl"
        append_audit_event(
            audit_path,
            _audit_event(
                run_id=effective_run_id,
                event_type="run_started",
                code_version=code_version,
                policy_hash=policy.configuration_hash,
                release=release,
                details={"mode": mode.value, "problem_id": effective_problem.problem_id},
            ),
        )
        try:
            if mode is LiveRunMode.LIVE:
                corpus_dir = run_dir / "corpus"
                if connectors is None:
                    health = run_acquisition(
                        effective_problem,
                        corpus_dir,
                        policy=policy,
                    )
                else:
                    health = run_acquisition(
                        effective_problem,
                        corpus_dir,
                        connectors=connectors,
                    )
                store = CorpusStore(corpus_dir)
                if not store.manifest_path.exists():
                    # An empty manifest is the canonical representation when every
                    # successful connector truthfully returns NO_DATA.
                    _atomic_write(store.manifest_path, "")
                validation = store.validate()
            else:
                assert replay_corpus is not None
                corpus_dir = Path(replay_corpus)
                store, health, portable_seal = _load_sealed_corpus(
                    corpus_dir,
                    policy_hash=policy.configuration_hash,
                    as_of_date=effective_as_of,
                )
                validation = store.validate()

            health_failures = health.production_failures(
                set(policy.required_source_families)
            )
            health_failures.extend(
                _corpus_health_reconciliation_failures(health, store)
            )
            health_payload = {
                **_source_health_payload(health),
                "production_failures": health_failures,
            }
            _write_json(
                run_dir / "source_health.json",
                health_payload,
            )
            if health_failures:
                raise SELivePipelineError(
                    "required source health failed: " + "; ".join(health_failures),
                    exit_code=3,
                )

            source_counts = {
                family: len(documents)
                for family, documents in sorted(store.by_family().items())
            }
            if mode is LiveRunMode.LIVE:
                corpus_health_path = corpus_dir / "source_health.json"
                _write_json(corpus_health_path, _source_health_payload(health))
                corpus_manifest_hash = sha256_file(store.manifest_path)
                portable_seal = SealedCorpusMetadata(
                    manifest_sha256=corpus_manifest_hash,
                    source_health_sha256=sha256_file(corpus_health_path),
                    policy_hash=policy.configuration_hash,
                    as_of_date=effective_as_of,
                    source_counts=source_counts,
                    validation=_portable_corpus_validation(validation),
                )
                _write_json(corpus_dir / "seal.json", portable_seal)
            else:
                corpus_manifest_hash = portable_seal.manifest_sha256
            _write_json(run_dir / "corpus_seal.json", portable_seal)
            no_data_families = [
                source.source_family
                for source in health.sources
                if source.verdict is SourceVerdict.NO_DATA
            ]
            adapters = adapters_from_corpus(
                store,
                policy.required_source_families,
                proven_no_data_source_families=no_data_families,
            )
            result = run_landscape_search(
                effective_problem,
                adapters,
                run_id=effective_run_id,
                code_version=code_version,
                normalization_version=policy.policy_version,
                declared_mandatory_sources=policy.required_source_families,
            )
            monitoring = _monitoring_snapshot(
                run_id=effective_run_id,
                result=result,
                health=health,
            )
            _write_json(run_dir / "monitoring.json", monitoring)
            _write_json(run_dir / "result.json", result)
            _atomic_write(run_dir / "memo.md", render_search_memo(result) + "\n")
            if result.run_manifest.status is not RunStatus.CONVERGED:
                raise SELivePipelineError(
                    "discovery did not converge: "
                    + "; ".join(result.run_manifest.incomplete_reasons),
                    exit_code=4,
                )
            if monitoring.stop_reasons:
                raise SELivePipelineError(
                    "semantic production checks failed: "
                    + "; ".join(monitoring.stop_reasons),
                    exit_code=4,
                )

            completed_at = datetime.now(timezone.utc)
            receipt = SELiveRunReceipt(
                run_id=effective_run_id,
                execution_key=execution_key,
                mode=mode,
                status=("SEALED" if mode is LiveRunMode.LIVE else "VERIFIED_REPLAY"),
                problem_id=effective_problem.problem_id,
                problem_hash=problem_digest,
                as_of_date=effective_as_of,
                code_version=code_version,
                policy_version=policy.policy_version,
                policy_hash=policy.configuration_hash,
                release_id=release.release_id if release else None,
                release_manifest_hash=release.manifest_hash if release else None,
                corpus_manifest_hash=corpus_manifest_hash,
                started_at=started_at,
                completed_at=completed_at,
                result_path="result.json",
                artifact_manifest_path="artifact_manifest.json",
            )
            _write_json(run_dir / "run_receipt.json", receipt)
            append_audit_event(
                audit_path,
                _audit_event(
                    run_id=effective_run_id,
                    event_type=(
                        "run_sealed"
                        if mode is LiveRunMode.LIVE
                        else "replay_verified"
                    ),
                    code_version=code_version,
                    policy_hash=policy.configuration_hash,
                    release=release,
                    details={
                        "candidate_count": len(result.candidates),
                        "manifest_status": result.run_manifest.status.value,
                    },
                ),
            )
            artifact_manifest = _artifact_manifest(run_dir, effective_run_id)
            _write_json(run_dir / "artifact_manifest.json", artifact_manifest)
            verify_artifact_manifest(run_dir, artifact_manifest)
            if mode is LiveRunMode.LIVE:
                _write_json(
                    output_root / "CURRENT.json",
                    CurrentPointer(
                        run_id=effective_run_id,
                        execution_key=execution_key,
                        receipt_sha256=sha256_file(run_dir / "run_receipt.json"),
                        artifact_manifest_sha256=sha256_file(
                            run_dir / "artifact_manifest.json"
                        ),
                        promoted_at=datetime.now(timezone.utc),
                    ),
                )
            return SELiveRunOutcome(
                run_dir=run_dir,
                receipt=receipt,
                result=result,
            )
        except Exception as exc:
            try:
                failure_payload = {
                    "run_id": effective_run_id,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                if (run_dir / "artifact_manifest.json").exists():
                    # Once sealed, the run directory is immutable even if external
                    # CURRENT promotion fails. Diagnostics live outside the bundle.
                    _write_json(
                        output_root / "failures" / f"{effective_run_id}.json",
                        failure_payload,
                    )
                else:
                    append_audit_event(
                        audit_path,
                        _audit_event(
                            run_id=effective_run_id,
                            event_type="run_failed",
                            code_version=code_version,
                            policy_hash=policy.configuration_hash,
                            release=release,
                            details={"error_type": type(exc).__name__, "error": str(exc)},
                        ),
                    )
                    _write_json(run_dir / "failure.json", failure_payload)
            except Exception:
                pass
            if isinstance(exc, SELivePipelineError):
                raise
            raise SELivePipelineError(
                f"live S&E run failed at an integrity boundary: {type(exc).__name__}: {exc}",
                exit_code=5,
            ) from exc


__all__ = [
    "ArtifactManifest",
    "CurrentPointer",
    "LiveRunMode",
    "SELiveMonitoringSnapshot",
    "SELivePipelineError",
    "SELiveRunOutcome",
    "SELiveRunReceipt",
    "run_live_pipeline",
    "verify_artifact_manifest",
    "verify_current_run",
]
