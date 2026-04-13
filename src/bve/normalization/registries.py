"""
Singleton registries for canonical indication, target, and MOA lookup.

Loaded from YAML at first import; subsequent calls reuse the in-memory dicts.
Each registry exposes:
    - A full dict[id -> Canonical*] for reverse-lookup by canonical ID.
    - A flat dict[normalized_alias -> canonical_id] for fast exact-match.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from bve.normalization.types import CanonicalIndication, CanonicalMOA, CanonicalTarget

_CONFIG_DIR = Path(__file__).parent / "config"


def _norm(s: str) -> str:
    """Lowercase + collapse whitespace (matches normalizer pre-processing)."""
    return " ".join(s.strip().lower().split())


# ── Indication ────────────────────────────────────────────────────────────────

def _load_indications() -> tuple[dict[str, CanonicalIndication], dict[str, str]]:
    raw = yaml.safe_load((_CONFIG_DIR / "indication_synonyms.yaml").read_text(encoding="utf-8"))
    registry: dict[str, CanonicalIndication] = {}
    alias_map: dict[str, str] = {}
    for entry in raw.get("indications", []):
        ci = CanonicalIndication(**entry)
        registry[ci.id] = ci
        for alias in ci.aliases:
            normalized = _norm(alias)
            # Raise loudly if the same alias string maps to two different canonicals
            if normalized in alias_map and alias_map[normalized] != ci.id:
                raise ValueError(
                    f"Duplicate alias '{normalized}' maps to both "
                    f"'{alias_map[normalized]}' and '{ci.id}' in indication_synonyms.yaml"
                )
            alias_map[normalized] = ci.id
    return registry, alias_map


# ── Target ────────────────────────────────────────────────────────────────────

def _load_targets() -> tuple[dict[str, CanonicalTarget], dict[str, str]]:
    raw = yaml.safe_load((_CONFIG_DIR / "target_synonyms.yaml").read_text(encoding="utf-8"))
    registry: dict[str, CanonicalTarget] = {}
    alias_map: dict[str, str] = {}
    for entry in raw.get("targets", []):
        ct = CanonicalTarget(**entry)
        registry[ct.id] = ct
        for alias in ct.aliases:
            normalized = _norm(alias)
            if normalized in alias_map and alias_map[normalized] != ct.id:
                raise ValueError(
                    f"Duplicate alias '{normalized}' maps to both "
                    f"'{alias_map[normalized]}' and '{ct.id}' in target_synonyms.yaml"
                )
            alias_map[normalized] = ct.id
    return registry, alias_map


# ── MOA ───────────────────────────────────────────────────────────────────────

def _load_moas() -> tuple[dict[str, CanonicalMOA], dict[str, str]]:
    raw = yaml.safe_load((_CONFIG_DIR / "moa_synonyms.yaml").read_text(encoding="utf-8"))
    registry: dict[str, CanonicalMOA] = {}
    alias_map: dict[str, str] = {}
    for entry in raw.get("mechanisms", []):
        cm = CanonicalMOA(**entry)
        registry[cm.id] = cm
        for alias in cm.aliases:
            normalized = _norm(alias)
            if normalized in alias_map and alias_map[normalized] != cm.id:
                raise ValueError(
                    f"Duplicate alias '{normalized}' maps to both "
                    f"'{alias_map[normalized]}' and '{cm.id}' in moa_synonyms.yaml"
                )
            alias_map[normalized] = cm.id
    return registry, alias_map


# ── Module-level singletons (loaded once) ────────────────────────────────────

INDICATION_REGISTRY, INDICATION_ALIAS_MAP = _load_indications()
TARGET_REGISTRY, TARGET_ALIAS_MAP = _load_targets()
MOA_REGISTRY, MOA_ALIAS_MAP = _load_moas()


# ── Public helpers ────────────────────────────────────────────────────────────

def get_indication(canonical_id: str) -> Optional[CanonicalIndication]:
    return INDICATION_REGISTRY.get(canonical_id)


def get_target(canonical_id: str) -> Optional[CanonicalTarget]:
    return TARGET_REGISTRY.get(canonical_id)


def get_moa(canonical_id: str) -> Optional[CanonicalMOA]:
    return MOA_REGISTRY.get(canonical_id)
