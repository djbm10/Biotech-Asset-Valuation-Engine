"""Positive-only indication compatibility under the frozen NCIt authority."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re

from bve.se.ontology.indications import ConditionMatch, classify_condition, is_indication_concept


@lru_cache(maxsize=1)
def _authority() -> dict:
    path = Path(__file__).resolve().parents[4] / "research/se_indication_semantics_v1/ncit_diseases.json"
    return json.loads(path.read_text())


def disease_id(value: object) -> str | None:
    """An ambiguous or incompletely typed name cannot establish disease identity."""
    if not isinstance(value, str):
        return None
    authority = _authority()
    code = value.removeprefix("NCIT:")
    if code in authority["nodes"]:
        return code
    name = " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())
    codes = authority["names"].get(name, [])
    return codes[0] if len(codes) == 1 else None


@lru_cache(maxsize=8192)
def _path(observed: str, requested: str) -> tuple[str, ...]:
    nodes = _authority()["nodes"]
    pending = [(observed, (observed,))]
    visited = set()
    while pending:
        current, path = pending.pop()
        if current == requested:
            return path
        if current in visited:
            continue
        visited.add(current)
        pending.extend((parent, (*path, parent)) for parent in nodes.get(current, {}).get("parents", []))
    return ()


def compatibility(requested: object, observed: object) -> dict | None:
    """A positive witness, never an incompatibility assertion or fuzzy name match."""
    if not isinstance(observed, str) or not isinstance(requested, str):
        return None
    if is_indication_concept(requested):
        from bve.se.intent.grammar import grammatical_negations
        if grammatical_negations(observed):
            return None
        if classify_condition(observed, requested) is ConditionMatch.MATCH:
            return {"requested": requested, "observed": observed, "rule": "accepted_bcell_positive"}
        return None
    query_id, observed_id = disease_id(requested), disease_id(observed)
    if query_id is None or observed_id is None:
        return None
    path = _path(observed_id, query_id)
    if not path:
        return None
    return {"requested": requested, "observed": observed,
            "requested_id": query_id, "observed_id": observed_id,
            "rule": "authority_identity" if len(path) == 1 else "authority_descendant",
            "path": list(path), "authority_release": _authority()["release"]}
