"""Durable artifacts for replayable science evidence extraction."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from bve.intelligence.science_evidence import ScienceEvidenceBundle

SCIENCE_EVIDENCE_ARTIFACT_SCHEMA_VERSION = "science_evidence_artifact.v1"
DEFAULT_EXTRACTOR_VERSION = "science_evidence_llm_extractor.v1"
DEFAULT_PROMPT_VERSION = "science_evidence_prompt.v1"


class ScienceEvidenceArtifact(BaseModel):
    """JSON-safe persisted evidence bundle with replay identity metadata."""

    schema_version: str = SCIENCE_EVIDENCE_ARTIFACT_SCHEMA_VERSION
    extractor_version: str = DEFAULT_EXTRACTOR_VERSION
    prompt_version: str = DEFAULT_PROMPT_VERSION
    model_id: str = "unknown"
    document_hash: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_document_id: str
    asset_id: str
    bundle: ScienceEvidenceBundle
    artifact_warnings: list[str] = Field(default_factory=list)


def compute_document_hash(document_text: str) -> str:
    """Return stable SHA-256 hash for source document text."""
    return hashlib.sha256(document_text.encode("utf-8")).hexdigest()


def build_science_evidence_artifact(
    bundle: ScienceEvidenceBundle,
    *,
    document_text: str,
    source_document_id: str,
    asset_id: str | None = None,
    model_id: str | None = None,
    extractor_version: str = DEFAULT_EXTRACTOR_VERSION,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> ScienceEvidenceArtifact:
    """Create an auditable artifact from a validated evidence bundle."""
    return ScienceEvidenceArtifact(
        extractor_version=extractor_version,
        prompt_version=prompt_version,
        model_id=model_id or "unknown",
        document_hash=compute_document_hash(document_text),
        source_document_id=source_document_id,
        asset_id=asset_id or bundle.asset_id,
        bundle=bundle,
    )


def artifact_path_for_document(output_dir: str | Path, *, asset_id: str, document_id: str) -> Path:
    """Return default artifact path for one asset/document pair."""
    safe_asset = asset_id.replace("/", "_")
    safe_doc = document_id.replace("/", "_")
    return Path(output_dir) / safe_asset / f"{safe_doc}.science_evidence.json"


def save_science_evidence_artifact(artifact: ScienceEvidenceArtifact, path: str | Path) -> Path:
    """Write artifact JSON and return written path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
    return out


def load_science_evidence_artifact(
    path: str | Path,
    *,
    current_document_text: str | None = None,
    mismatch_policy: str = "warn",
) -> ScienceEvidenceArtifact:
    """Load artifact and optionally validate it still matches current document text.

    mismatch_policy: "warn" appends an artifact warning, "fail" raises ValueError.
    "ignore" skips the hash check.
    """
    artifact = ScienceEvidenceArtifact.model_validate(json.loads(Path(path).read_text()))
    if current_document_text is None or mismatch_policy == "ignore":
        return artifact
    current_hash = compute_document_hash(current_document_text)
    if current_hash == artifact.document_hash:
        return artifact
    message = "science_evidence_artifact_document_hash_mismatch"
    if mismatch_policy == "fail":
        raise ValueError(message)
    return artifact.model_copy(update={"artifact_warnings": [*artifact.artifact_warnings, message]})
