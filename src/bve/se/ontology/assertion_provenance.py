"""Additive raw target assertion lineage. Never participates in target decisions.

Capture before parsing: raw identity and matching keys deliberately remain separate.
Artifact row ordinals and field paths are locators within content-addressed bytes.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from bve.se.ontology.records import SourceEntityRecord, normalize_lookup_key

SCHEMA = "authority_assertion_provenance_v1"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def stable_id(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _operation(text: str, operation: dict) -> str:
    name = operation["operation"]
    if name == "slice":
        return text[operation["start"] : operation["end"]]
    if name == "strip":
        return text.strip()
    if name == "whitespace_collapse":
        return " ".join(text.split())
    if name == "casefold":
        return text.casefold()
    if name == "lookup_separators":
        return text.replace("-", " ").replace("_", " ").replace("/", " ")
    raise ValueError(f"unknown provenance operation {name}")


def replay(raw: str, transforms: list[dict]) -> str:
    value = raw
    for step in transforms:
        if step["input"] != value:
            raise ValueError("transformation input mismatch")
        value = _operation(value, step)
        if step["output"] != value:
            raise ValueError("transformation output mismatch")
    return value


def capture_assertions(
    source: str,
    release: str,
    artifact_sha256: str,
    artifact_path: str,
    row_index: int,
    raw: dict,
) -> list[dict]:
    """Capture every nonempty assertion origin, including normalized duplicates.

    Does not resolve a canonical identity or mutate the raw input. The caller must
    bind artifact SHA256 to the bytes it actually reads and verify parsed linkage.
    """
    fields: list[tuple] = []
    if source == "open_targets":
        record_id = raw.get("id") or raw.get("ensemblId")
        for field, kind, role in [
            ("approvedSymbol", "SYMBOL", "canonical_symbol"),
            ("approvedName", "APPROVED_NAME", "label"),
        ]:
            value = raw.get(field)
            if isinstance(value, str) and value.strip():
                fields.append(([field], value, 0, len(value), kind, role, None, False))
        for field, kind in [
            ("synonyms", "SYNONYM"),
            ("symbolSynonyms", "SYMBOL"),
            ("nameSynonyms", "SYNONYM"),
            ("obsoleteSymbols", "SYNONYM"),
        ]:
            values = raw.get(field)
            if not isinstance(values, list):
                continue
            for i, value in enumerate(values):
                path: list[str | int] = [field, i]
                if isinstance(value, dict):
                    selected = "label" if value.get("label") else "name"
                    value = value.get(selected)
                    path.append(selected)
                if isinstance(value, str) and value.strip():
                    fields.append((path, value, 0, len(value), kind, "alias", None, False))
    elif source == "chembl":
        record_id = raw.get("target_chembl_id")
        value = raw.get("pref_name")
        if isinstance(value, str) and value.strip():
            fields.append(
                (["pref_name"], value, 0, len(value), "APPROVED_NAME", "label", None, False)
            )
        symbol_seen = False
        types = {
            "GENE_SYMBOL": "SYMBOL",
            "GENE_SYMBOL_OTHER": "SYNONYM",
            "UNIPROT": "SYNONYM",
            "EC_NUMBER": "XREF",
        }
        for ci, component in enumerate(raw.get("target_components") or []):
            if not isinstance(component, dict):
                continue
            for si, synonym in enumerate(component.get("target_component_synonyms") or []):
                if not isinstance(synonym, dict):
                    continue
                scalar = synonym.get("component_synonym")
                if not isinstance(scalar, str):
                    continue
                kind = types.get(str(synonym.get("syn_type") or ""), "SYNONYM")
                start = scalar.index("=") + 1 if "=" in scalar else 0
                for part in scalar[start:].split(";"):
                    end = start + len(part)
                    if part.strip():
                        role = (
                            "alias_and_symbol" if kind == "SYMBOL" and not symbol_seen else "alias"
                        )
                        if kind == "SYMBOL":
                            symbol_seen = True
                        fields.append(
                            (
                                [
                                    "target_components",
                                    ci,
                                    "target_component_synonyms",
                                    si,
                                    "component_synonym",
                                ],
                                scalar,
                                start,
                                end,
                                kind,
                                role,
                                {"index": ci, "accession": component.get("accession")},
                                True,
                            )
                        )
                    start = end + 1
    else:
        raise ValueError(f"unsupported authority {source}")
    if not isinstance(record_id, str) or not record_id.strip():
        return []
    rows = []
    for path, scalar, start, end, kind, role, component, stripped in fields:
        value = scalar
        transforms = []
        operations = [{"operation": "slice", "start": start, "end": end}]
        if stripped:
            operations.append({"operation": "strip"})
        operations += [
            {"operation": name}
            for name in (
                "whitespace_collapse",
                "casefold",
                "lookup_separators",
                "whitespace_collapse",
            )
        ]
        for operation in operations:
            output = _operation(value, operation)
            transforms.append({**operation, "input": value, "output": output})
            value = output
        identity = {
            "source": source,
            "release": release,
            "artifact_sha256": artifact_sha256,
            "record_id": record_id,
            "row_index": row_index,
            "field_path": path,
            "component_interval": [start, end],
            "raw_component": scalar[start:end],
            "upstream_component": component,
        }
        rows.append(
            {
                **identity,
                "schema": SCHEMA,
                "assertion_id": stable_id(identity),
                "artifact_path": artifact_path,
                "raw_scalar": scalar,
                "assertion_type": kind,
                "snapshot_role": role,
                "transforms": transforms,
                "normalized_key": value,
            }
        )
    return rows


def snapshot_fields(record: SourceEntityRecord) -> list[dict]:
    fields = []
    for field, kind in [("canonical_symbol", "SYMBOL"), ("label", "APPROVED_NAME")]:
        value = getattr(record, field)
        if value:
            fields.append({"field": field, "value": value, "assertion_type": kind})
    for i, alias in enumerate(record.aliases):
        fields.append(
            {
                "field": f"aliases/{i}/value",
                "value": alias.value,
                "assertion_type": alias.alias_type.value,
            }
        )
    return fields


def link_assertions(
    rows: list[dict], parsed: SourceEntityRecord | None, accepted: SourceEntityRecord
) -> list[dict]:
    """Fail closed on drift; absent raw source remains explicit, with no fake origin."""
    if parsed is not None and parsed != accepted:
        raise ValueError(f"raw parser differs from snapshot: {accepted.record_key}")
    links = []
    for field in snapshot_fields(accepted):
        ids = []
        if parsed is not None:
            for row in rows:
                role = row["snapshot_role"]
                if field["field"] == "canonical_symbol":
                    eligible = role in ("canonical_symbol", "alias_and_symbol")
                elif field["field"] == "label":
                    eligible = role == "label"
                else:
                    eligible = role in ("alias", "alias_and_symbol")
                if (
                    eligible
                    and row["assertion_type"] == field["assertion_type"]
                    and row["normalized_key"] == normalize_lookup_key(field["value"])
                ):
                    ids.append(row["assertion_id"])
            if not ids:
                raise ValueError(f"available raw assertion unlinked: {accepted.record_key}:{field}")
        links.append(
            {
                **field,
                "record_key": accepted.record_key,
                "status": "RECOVERABLE" if ids else "UNRECOVERABLE",
                "reason": None if ids else "ORIGINAL_INGESTION_ARTIFACT_UNAVAILABLE",
                "assertion_ids": sorted(ids),
            }
        )
    return links
