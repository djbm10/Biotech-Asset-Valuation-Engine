"""Names NCIt types as something other than a product (candidate_qualification_v6 Q1).

A registry enters "R-mini-CHOP" and "Standard of Care" as interventions, so a structured
arm type cannot tell a regimen from a molecule. NCIt can: it files the first as a
Therapeutic or Preventive Procedure and the second as a Health Care Activity. The sidecar
holds only names *every* one of whose NCIt concepts carries non-product semantic types
alone, so a name that is also a substance anywhere in NCIt is never in it.
Policy: ``docs/se_policies/candidate_qualification_v6.md``.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path

ENTITY_TYPES_VERSION = "ncit_entity_types_v1"
NCIT_ENTITY_TYPES_KEY = "ncit_entity_types"
_DEFAULT_PATH = Path("data/se/ontology/ncit/ncit_26.08e_entity_types.json")

#: UMLS semantic-network types that denote no therapeutic product (§2 Q1, frozen).
NON_PRODUCT_TYPES = frozenset(
    {
        "Therapeutic or Preventive Procedure", "Health Care Activity", "Research Activity",
        "Activity", "Diagnostic Procedure", "Laboratory Procedure", "Intellectual Product",
        "Conceptual Entity", "Qualitative Concept", "Quantitative Concept",
        "Functional Concept", "Temporal Concept", "Idea or Concept", "Classification",
        "Finding", "Disease or Syndrome", "Neoplastic Process", "Event", "Population Group",
        "Spatial Concept",
    }
)


def name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def build_entity_types(flat_txt: Path, *, release_zip_sha256: str) -> dict:
    csv.field_size_limit(1 << 30)
    concepts_by_key: dict[str, set[str]] = {}
    types: dict[str, set[str]] = {}
    with flat_txt.open(encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE):
            code = row[0]
            types[code] = {value for value in row[7].split("|") if value}
            for name in [*row[3].split("|"), row[5]]:
                key = name_key(name) if name else ""
                if key:
                    concepts_by_key.setdefault(key, set()).add(code)
    non_product = {}
    for key, codes in concepts_by_key.items():
        merged = set().union(*(types[code] for code in codes))
        if merged and merged <= NON_PRODUCT_TYPES:
            non_product[key] = sorted(codes)
    return {
        "version": ENTITY_TYPES_VERSION,
        "ncit_release": "26.08e",
        "release_zip_sha256": release_zip_sha256,
        "non_product_names": dict(sorted(non_product.items())),
    }


class NcitEntityTypes:
    def __init__(self, payload: dict, sha256: str) -> None:
        self.payload = payload
        self.sha256 = sha256
        self._names: dict[str, list[str]] = payload["non_product_names"]

    @property
    def version_token(self) -> str:
        return f"{ENTITY_TYPES_VERSION}@ncit_{self.payload['ncit_release']}@{self.sha256[:16]}"

    def non_product_concepts(self, name: str) -> list[str]:
        """NCIt codes that make this name a non-product, or ``[]``."""

        return list(self._names.get(name_key(name), ()))


def default_entity_types_path() -> Path:
    override = os.environ.get("BVE_SE_NCIT_ENTITY_TYPES")
    return Path(override) if override else _DEFAULT_PATH


@lru_cache(maxsize=4)
def _load(path: str) -> NcitEntityTypes | None:
    file = Path(path)
    if not file.exists():
        return None
    raw = file.read_bytes()
    return NcitEntityTypes(json.loads(raw), hashlib.sha256(raw).hexdigest())


def ncit_entity_types() -> NcitEntityTypes | None:
    return _load(str(default_entity_types_path()))


def reset_entity_types_cache() -> None:
    _load.cache_clear()
