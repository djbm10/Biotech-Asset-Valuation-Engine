"""Governed Phase 1 validation contracts.

This module deliberately sits after acquisition.  It does not score a CD19/BCMA run against
another target universe and it does not turn retrieval heuristics into scientific truth.  The
contracts make the human-review and custody boundaries explicit so a release cannot silently
promote an anomaly, an unreviewed merge, or an uncited dossier field.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReviewStatus(str, Enum):
    SUSPECTED = "SUSPECTED"
    CONFIRMED = "CONFIRMED"
    CLEARED = "CLEARED"


class ConflictStatus(str, Enum):
    NONE = "NONE"
    MISSING = "MISSING"
    CONFLICTING = "CONFLICTING"


class FieldVerdict(str, Enum):
    SUPPORTED = "SUPPORTED"
    INCORRECT = "INCORRECT"
    CONFLICTING = "CONFLICTING"
    MISSING = "MISSING"


class Phase1Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_reviewer(value: str | None, field_name: str) -> str | None:
    if value is not None and (not value.strip() or re.search(r"UNASSIGNED|PLACEHOLDER|TODO", value, re.I)):
        raise ValueError(f"{field_name} cannot be a placeholder reviewer")
    return value


class FieldProvenance(Phase1Model):
    """Evidence for one populated dossier field, rather than for an entire asset."""

    asset_id: str
    field_name: str
    value: Any
    supporting_claim_id: str
    exact_source_passage: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    as_of_date: date
    verification_status: ReviewStatus
    verdict: FieldVerdict
    value_key: str | int | None = None
    conflict_status: ConflictStatus = ConflictStatus.NONE
    reviewer: str | None = None
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_review(self) -> "FieldProvenance":
        _validate_reviewer(self.reviewer, "reviewer")
        if self.verification_status in {ReviewStatus.CONFIRMED, ReviewStatus.CLEARED}:
            if not self.reviewer or self.reviewed_at is None:
                raise ValueError("confirmed or cleared field provenance requires reviewer and time")
        if self.conflict_status is ConflictStatus.CONFLICTING and self.verification_status is ReviewStatus.CONFIRMED:
            raise ValueError("conflicting field evidence cannot be confirmed")
        return self


class DossierField(Phase1Model):
    """A field can be absent or conflicting, but never silently unsupported."""

    field_name: str
    value: Any = None
    provenance: FieldProvenance | None = None
    item_provenance: list[FieldProvenance] = Field(default_factory=list)
    conflict_status: ConflictStatus = ConflictStatus.NONE
    verdict: FieldVerdict | None = None

    @model_validator(mode="after")
    def validate_citation(self) -> "DossierField":
        if self.value is not None and self.provenance is None:
            raise ValueError(f"populated field {self.field_name!r} requires field-level provenance")
        if self.value is None and self.conflict_status is ConflictStatus.NONE:
            raise ValueError(f"missing field {self.field_name!r} must be explicitly marked MISSING")
        expected_verdict = FieldVerdict.MISSING if self.value is None else self.verdict
        if expected_verdict is None:
            raise ValueError(f"field {self.field_name!r} requires an explicit verdict")
        if self.value is None and expected_verdict is not FieldVerdict.MISSING:
            raise ValueError("missing fields must have MISSING verdict")
        if self.provenance and self.provenance.field_name != self.field_name:
            raise ValueError("field provenance must name the same dossier field")
        if isinstance(self.value, list) and self.value:
            if len(self.item_provenance) != len(self.value):
                raise ValueError(f"list field {self.field_name!r} requires provenance for every value")
            for index, provenance in enumerate(self.item_provenance):
                if provenance.field_name != self.field_name or provenance.value != self.value[index]:
                    raise ValueError("list item provenance must match field and item value")
                if provenance.value_key not in {index, str(index)}:
                    raise ValueError("list item provenance requires its value index")
        if self.conflict_status is ConflictStatus.CONFLICTING and self.value is not None:
            if not self.provenance or self.provenance.conflict_status is not ConflictStatus.CONFLICTING:
                raise ValueError("conflicting populated fields must preserve conflicting provenance")
        return self


class AssetHardGateReview(Phase1Model):
    """Human adjudication record for the identity and hard-gate fields of one asset."""

    asset_id: str
    canonical_identity: DossierField
    aliases: DossierField
    linked_companies: DossierField
    ownership: DossierField
    target: DossierField
    modality: DossierField
    trials: DossierField
    adjudication_status: ReviewStatus
    reviewer: str
    reviewed_at: datetime
    confirmed_wrong_target: bool = False
    confirmed_wrong_modality: bool = False
    probabilistic_merge_confirmed: bool = False

    @model_validator(mode="after")
    def validate_adjudication(self) -> "AssetHardGateReview":
        _validate_reviewer(self.reviewer, "reviewer")
        fields = (
            self.canonical_identity,
            self.aliases,
            self.linked_companies,
            self.ownership,
            self.target,
            self.modality,
            self.trials,
        )
        if any(field.value is not None and field.provenance is None for field in fields):
            raise ValueError("every populated hard-gate field requires provenance")
        if self.probabilistic_merge_confirmed and self.adjudication_status is not ReviewStatus.CONFIRMED:
            raise ValueError("probabilistic merge confirmation requires a confirmed review")
        return self


class ReviewFlag(Phase1Model):
    """A machine heuristic is a review queue item, never a confirmed defect."""

    flag_id: str
    asset_id: str
    flag_type: str
    status: ReviewStatus = ReviewStatus.SUSPECTED
    rationale: str = Field(min_length=1)
    supporting_claim_ids: list[str] = Field(default_factory=list)
    merge_id: str | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None

    @model_validator(mode="after")
    def validate_resolution(self) -> "ReviewFlag":
        _validate_reviewer(self.resolved_by, "resolved_by")
        if self.flag_type == "probabilistic_merge" and not self.merge_id:
            raise ValueError("probabilistic merge flags require merge_id")
        if self.status in {ReviewStatus.CONFIRMED, ReviewStatus.CLEARED}:
            if not self.resolved_by or self.resolved_at is None:
                raise ValueError("resolved review flags require reviewer and time")
        return self


class BaselineCustody(Phase1Model):
    """Immutable inputs required to reproduce a Phase 1 score."""

    code_commit: str = Field(min_length=7)
    problem_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_hashes: dict[str, str] = Field(min_length=1)
    source_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_json_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    asset_ids: tuple[str, ...] = Field(min_length=1)
    asset_id_set_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    probabilistic_merge_ids: tuple[str, ...] = ()
    as_of_date: date
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_config_hashes(self) -> "BaselineCustody":
        if any(not key or not re.fullmatch(r"[0-9a-f]{64}", value) for key, value in self.config_hashes.items()):
            raise ValueError("config_hashes must contain lowercase SHA-256 values")
        if len(self.asset_ids) != len(set(self.asset_ids)):
            raise ValueError("baseline asset IDs must be unique")
        if canonical_asset_set_hash(self.asset_ids) != self.asset_id_set_hash:
            raise ValueError("asset_id_set_hash does not match baseline asset IDs")
        return self


class ReferenceUniverseSpec(Phase1Model):
    """Pre-pipeline, independently reviewed definition of a target/modality universe."""

    universe_id: str
    target: str
    modality: str
    as_of_date: date
    inclusion_criteria: list[str] = Field(min_length=1)
    exclusion_criteria: list[str] = Field(min_length=1)
    citations: list[str] = Field(min_length=1)
    asset_count: int = Field(ge=1)
    asset_file_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    asset_citations: dict[str, tuple[str, ...]] = Field(min_length=1)
    universe_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewers: tuple[str, str]
    sealed_at: datetime | None = None
    pipeline_exposed_before_sealing: bool = False
    minimum_recall: float = Field(ge=0.0, le=1.0)
    minimum_precision: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_independence(self) -> "ReferenceUniverseSpec":
        if self.reviewers[0] == self.reviewers[1]:
            raise ValueError("reference universe requires two distinct reviewers")
        if self.sealed_at is not None and self.pipeline_exposed_before_sealing:
            raise ValueError("a sealed reference universe cannot have prior pipeline exposure")
        _validate_reviewer(self.reviewers[0], "reviewers[0]")
        _validate_reviewer(self.reviewers[1], "reviewers[1]")
        if self.asset_count != len(self.asset_citations):
            raise ValueError("asset_count must equal the number of cited asset rows")
        if any(not asset_id or not citations for asset_id, citations in self.asset_citations.items()):
            raise ValueError("every reference-universe asset row requires citations")
        return self


class UnseededRunEvaluation(Phase1Model):
    universe_id: str
    run_id: str
    target: str
    modality: str
    unseeded: bool
    universe_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_json_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_report_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    applicable_as_of_date: date
    pipeline_commit: str = Field(min_length=7)
    recall: float = Field(ge=0.0, le=1.0)
    precision: float = Field(ge=0.0, le=1.0)


class Phase1ReleaseGate(Phase1Model):
    expected_asset_count: int = Field(default=75, ge=1)
    hard_gate_reviews: list[AssetHardGateReview]
    field_provenance: list[FieldProvenance]
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    custody: BaselineCustody
    reference_universes: list[ReferenceUniverseSpec]
    unseeded_runs: list[UnseededRunEvaluation]

    @property
    def failures(self) -> list[str]:
        failures: list[str] = []
        if len(self.hard_gate_reviews) != self.expected_asset_count:
            failures.append(f"expected {self.expected_asset_count} hard-gate reviews, got {len(self.hard_gate_reviews)}")
        ids = [review.asset_id for review in self.hard_gate_reviews]
        if len(ids) != len(set(ids)):
            failures.append("duplicate asset hard-gate review IDs")
        if set(ids) != set(self.custody.asset_ids):
            failures.append("hard-gate review IDs do not exactly match the baseline asset-ID set")
        if any(review.adjudication_status is ReviewStatus.SUSPECTED for review in self.hard_gate_reviews):
            failures.append("one or more hard-gate reviews remain SUSPECTED")
        if any(
            field.provenance is not None
            and field.provenance.verification_status is ReviewStatus.SUSPECTED
            for review in self.hard_gate_reviews
            for field in (
                review.canonical_identity,
                review.aliases,
                review.linked_companies,
                review.ownership,
                review.target,
                review.modality,
                review.trials,
            )
        ):
            failures.append("one or more populated hard-gate fields remain SUSPECTED")
        if any(review.confirmed_wrong_target for review in self.hard_gate_reviews):
            failures.append("confirmed wrong-target record present")
        if any(review.confirmed_wrong_modality for review in self.hard_gate_reviews):
            failures.append("confirmed wrong-modality record present")
        for review in self.hard_gate_reviews:
            for field_name, field in ((
                ("target", review.target),
                ("modality", review.modality),
            )):
                if field.verdict is FieldVerdict.INCORRECT:
                    failures.append(f"confirmed incorrect {field_name} for {review.asset_id}")
        merge_reviews = {
            flag.merge_id: flag
            for flag in self.review_flags
            if flag.flag_type == "probabilistic_merge" and flag.merge_id
        }
        for merge_id in self.custody.probabilistic_merge_ids:
            flag = merge_reviews.get(merge_id)
            if flag is None or flag.status is ReviewStatus.SUSPECTED:
                failures.append(f"probabilistic merge {merge_id} lacks completed review")
        required_fields = {
            (review.asset_id, field.field_name, value_key)
            for review in self.hard_gate_reviews
            for field in (
                review.canonical_identity,
                review.aliases,
                review.linked_companies,
                review.ownership,
                review.target,
                review.modality,
                review.trials,
            )
            if field.value is not None
            for value_key in (
                [None]
                if not isinstance(field.value, list)
                else list(range(len(field.value)))
            )
        }
        cited_fields = {
            (item.asset_id, item.field_name, item.value_key)
            for item in self.field_provenance
        }
        failures.extend(
            f"populated field value lacks provenance: {asset_id}.{field_name}[{value_key}]"
            for asset_id, field_name, value_key in sorted(required_fields - cited_fields, key=str)
        )
        by_id = {universe.universe_id: universe for universe in self.reference_universes}
        for universe_id, universe in by_id.items():
            if universe.sealed_at is None:
                failures.append(f"reference universe {universe_id} is not sealed")
            runs = [run for run in self.unseeded_runs if run.universe_id == universe_id]
            if not runs:
                failures.append(f"no unseeded run for reference universe {universe_id}")
                continue
            if any(not run.unseeded for run in runs):
                failures.append(f"run for {universe_id} was seeded")
            if any(run.target != universe.target or run.modality != universe.modality for run in runs):
                failures.append(f"run specification does not match reference universe {universe_id}")
            if any(run.universe_hash != universe.universe_hash for run in runs):
                failures.append(f"run is not bound to the sealed universe {universe_id}")
            if any(run.applicable_as_of_date != universe.as_of_date for run in runs):
                failures.append(f"run date does not match reference universe {universe_id}")
            if max(run.recall for run in runs) < universe.minimum_recall:
                failures.append(f"{universe_id} recall below preregistered threshold")
            if max(run.precision for run in runs) < universe.minimum_precision:
                failures.append(f"{universe_id} precision below preregistered threshold")
        return failures

    def passes(self) -> bool:
        return not self.failures


def sha256_file(path: str | Path) -> str:
    """Hash a custody input without loading large corpora into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_hash(payload: object) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def canonical_asset_set_hash(asset_ids: tuple[str, ...] | list[str]) -> str:
    """Hash the exact sorted baseline asset-ID set, independent of row order."""

    return canonical_json_hash(sorted(set(asset_ids)))


def build_baseline_custody(
    *,
    code_commit: str,
    problem_path: str | Path,
    config_paths: dict[str, str | Path],
    source_manifest_path: str | Path,
    corpus_manifest_path: str | Path,
    result_json_path: str | Path,
    asset_ids: tuple[str, ...] | list[str],
    probabilistic_merge_ids: tuple[str, ...] = (),
    as_of_date: date,
) -> BaselineCustody:
    """Create the custody record from the exact files used by a run."""

    return BaselineCustody(
        code_commit=code_commit,
        problem_hash=sha256_file(problem_path),
        config_hashes={name: sha256_file(path) for name, path in config_paths.items()},
        source_manifest_hash=sha256_file(source_manifest_path),
        corpus_hash=sha256_file(corpus_manifest_path),
        result_json_hash=sha256_file(result_json_path),
        asset_ids=tuple(asset_ids),
        asset_id_set_hash=canonical_asset_set_hash(asset_ids),
        probabilistic_merge_ids=tuple(probabilistic_merge_ids),
        as_of_date=as_of_date,
    )
