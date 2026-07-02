"""ExpectedSignatures — curated expected-biomarker-signature library (Idea 4, PR-3 step 1-3).

Loads ``expected_signatures.yaml`` and exposes, per mechanism, the biomarker
changes we would expect IF the drug engages its target as claimed. Mirrors the
``MeaningfulnessBars`` / ``AssumptionsLoader`` conventions: a lazily loaded
singleton with frozen (read-only) data.

SCOPE (PR-3, steps 1-3 only): schema + loader + validation + **no-op surfacing**.
This module deliberately contains **no conviction producer** and never moves a
posterior. ``describe_signature_availability`` returns descriptors with
``scored=False`` for every entry — including ``approved`` ones — because no
producer is wired yet.

HARD RULE (enforced when the producer lands in step 4): only entries with
``review_status == "approved"`` may ever produce a conviction ``EvidenceUpdate``.
``draft`` / ``retired`` entries surface as "signature candidate — not scored". A
wrong curated signature manufactures false falsification, so entries stay draft
until a domain reviewer approves them.

Kept in a small standalone loader (not folded into ``industry_assumptions.yaml``)
so refining a signature never risks the core assumptions validation.
"""
from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Optional

import yaml

from bve.config.assumptions_loader import _freeze

_DEFAULT_PATH = Path(__file__).parent / "expected_signatures.yaml"

_SCHEMA_VERSION = "expected_signatures_v1"
_VALID_REVIEW_STATES = {"draft", "approved", "retired"}
_VALID_DIRECTIONS = {"up", "down", "unchanged"}


def _normalize(text: Optional[str]) -> str:
    return (text or "").strip().lower()


class ExpectedSignatures:
    """Loads, validates, and caches the curated expected-signature library."""

    _instance: Optional["ExpectedSignatures"] = None

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        with open(path) as f:
            raw: dict = yaml.safe_load(f) or {}
        _validate(raw, path)
        self._entries: MappingProxyType = _freeze(raw.get("entries", {}))
        self._meta: MappingProxyType = _freeze(raw.get("meta", {}))
        self._schema_version: str = raw.get("schema_version", "")
        self._path = path

    @classmethod
    def get(cls) -> "ExpectedSignatures":
        if cls._instance is None:
            cls._instance = cls(_DEFAULT_PATH)
        return cls._instance

    @classmethod
    def reset(cls, path: Optional[Path] = None) -> "ExpectedSignatures":
        cls._instance = cls(path or _DEFAULT_PATH)
        return cls._instance

    @property
    def meta(self) -> MappingProxyType:
        return self._meta

    @property
    def schema_version(self) -> str:
        return self._schema_version

    @property
    def entries(self) -> MappingProxyType:
        return self._entries

    def entry(self, key: str) -> Optional[MappingProxyType]:
        """Full entry for a signature key, or None if absent."""
        return self._entries.get(key)

    def approved_entries(self) -> dict:
        """Only entries a future producer would be allowed to score."""
        return {
            key: entry
            for key, entry in self._entries.items()
            if entry.get("review_status") == "approved"
        }


def _validate(raw: dict, path: Path) -> None:
    """Fail fast on a malformed library — validated at the config boundary."""
    version = raw.get("schema_version")
    if version != _SCHEMA_VERSION:
        raise ValueError(
            f"{path.name}: schema_version {version!r} unsupported "
            f"(expected {_SCHEMA_VERSION!r})."
        )
    entries = raw.get("entries", {})
    if not isinstance(entries, dict):
        raise ValueError(f"{path.name}: 'entries' must be a mapping.")

    for key, entry in entries.items():
        if not isinstance(entry, dict):
            raise ValueError(f"{path.name}: entry {key!r} must be a mapping.")

        tags = entry.get("mechanism_tags")
        if not isinstance(tags, list) or not tags or not all(isinstance(t, str) for t in tags):
            raise ValueError(
                f"{path.name}: entry {key!r} needs a non-empty list of string mechanism_tags."
            )

        status = entry.get("review_status")
        if status not in _VALID_REVIEW_STATES:
            raise ValueError(
                f"{path.name}: entry {key!r} review_status {status!r} invalid "
                f"(expected one of {sorted(_VALID_REVIEW_STATES)})."
            )

        changes = entry.get("expected_changes")
        if not isinstance(changes, list) or not changes:
            raise ValueError(
                f"{path.name}: entry {key!r} needs a non-empty expected_changes list."
            )
        for i, change in enumerate(changes):
            if not isinstance(change, dict):
                raise ValueError(f"{path.name}: entry {key!r} change #{i} must be a mapping.")
            if not isinstance(change.get("biomarker"), str) or not change["biomarker"].strip():
                raise ValueError(f"{path.name}: entry {key!r} change #{i} needs a biomarker.")
            direction = change.get("direction")
            if direction not in _VALID_DIRECTIONS:
                raise ValueError(
                    f"{path.name}: entry {key!r} change #{i} direction {direction!r} invalid "
                    f"(expected one of {sorted(_VALID_DIRECTIONS)})."
                )
            if not isinstance(change.get("informativeness"), str) or not change["informativeness"]:
                raise ValueError(
                    f"{path.name}: entry {key!r} change #{i} needs an informativeness label."
                )
            if not isinstance(change.get("required"), bool):
                raise ValueError(
                    f"{path.name}: entry {key!r} change #{i} 'required' must be a boolean."
                )


def _label_for(review_status: str) -> str:
    if review_status == "approved":
        # No producer is wired in this PR, so even approved entries are not scored yet.
        return "approved signature — not yet wired to conviction updates"
    return "signature candidate — not scored"


def _change_summary(change: MappingProxyType) -> dict:
    return {
        "biomarker": change.get("biomarker"),
        "direction": change.get("direction"),
        "informativeness": change.get("informativeness"),
        "required": change.get("required"),
    }


def _entry_matches(
    entry: MappingProxyType,
    *,
    context_text: str,
    biomarker_hints: list[str],
) -> bool:
    """Conservative match: a mechanism tag appears in the context text, or an
    expected biomarker overlaps a hint. Match quality is irrelevant here because
    the result is never scored — it only decides whether to surface a candidate."""
    tags = [_normalize(t) for t in entry.get("mechanism_tags", [])]
    if context_text and any(tag and tag in context_text for tag in tags):
        return True
    hints = [_normalize(h) for h in biomarker_hints]
    if hints:
        for change in entry.get("expected_changes", []):
            bm = _normalize(change.get("biomarker"))
            if bm and any(bm in h or h in bm for h in hints if h):
                return True
    return False


def matching_approved_signatures(
    *,
    context_text: str = "",
    biomarker_hints: Optional[list[str]] = None,
    library: Optional[ExpectedSignatures] = None,
) -> list[tuple[str, MappingProxyType]]:
    """Approved entries relevant to a program — the ONLY entries a producer may score.

    Centralizes the hard gate: draft / retired entries can never be returned here,
    so no downstream conviction producer can act on an unapproved signature.
    """
    lib = library or ExpectedSignatures.get()
    ctx = _normalize(context_text)
    hints = list(biomarker_hints or [])
    out: list[tuple[str, MappingProxyType]] = []
    for key, entry in lib.entries.items():
        if entry.get("review_status") != "approved":
            continue
        if _entry_matches(entry, context_text=ctx, biomarker_hints=hints):
            out.append((key, entry))
    return out


def describe_signature_availability(
    *,
    context_text: str = "",
    biomarker_hints: Optional[list[str]] = None,
    library: Optional[ExpectedSignatures] = None,
) -> list[dict]:
    """No-op surfacing: which curated signatures are *relevant* to this program.

    Returns descriptors only. ``scored`` is **always False** in this PR — nothing
    here moves a posterior. This is the "expected signature available / untested"
    surface; the actual match/mismatch scoring is deferred to step 4 and gated on
    ``review_status == 'approved'``.
    """
    lib = library or ExpectedSignatures.get()
    ctx = _normalize(context_text)
    hints = list(biomarker_hints or [])

    rows: list[dict] = []
    for key, entry in lib.entries.items():
        if not _entry_matches(entry, context_text=ctx, biomarker_hints=hints):
            continue
        review_status = entry.get("review_status", "draft")
        rows.append(
            {
                "signature_key": key,
                "review_status": review_status,
                "scored": False,  # invariant for PR-3 steps 1-3
                "status_label": _label_for(review_status),
                "mechanism_tags": list(entry.get("mechanism_tags", [])),
                "expected_changes": [
                    _change_summary(c) for c in entry.get("expected_changes", [])
                ],
            }
        )
    return rows
