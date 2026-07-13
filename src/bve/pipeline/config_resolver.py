"""Resolve a valuation config by merging analyst confidential overrides.

The public/auto-generated config is the base. An analyst may add a separate
override file at ``examples/configs/overrides/<TICKER>.yaml`` with two sections::

    meta: { analyst: dmann, reviewed: 2026-06-13, rationale: "..." }
    confidential_overrides:        # mirrors the config tree; deep-merged onto base
      market_model: { peak_penetration: 0.30 }
      trials: [ { success_probability: 0.42 } ]   # merged onto trials[0] by index
      asset: { discount_rate: 0.11 }
    private:                        # confidential signals — NEVER merged into the engine config
      expected_partner_interest: high
      diligence_notes: "..."

Guarantees:
- ``confidential_overrides`` deep-merge onto the base (leaf wins; lists merge by index).
- ``private:`` is returned in the provenance for downstream memos/screens but is
  **never** merged into the engine config and therefore never reaches outputs.
- When any value-driver section is overridden, ``_meta.evidence_level`` elevates to
  ``full`` (the analyst has confirmed the underwriting).
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_OVERRIDE_DIR = "examples/configs/overrides"
_VALUE_DRIVER_SECTIONS = {"asset", "trials", "market_model", "company"}


def _ticker_of(cfg: dict, fallback_path: Path | None) -> str | None:
    ticker = (cfg.get("company") or {}).get("ticker")
    if ticker:
        return str(ticker).upper()
    if fallback_path is not None:
        return fallback_path.stem.upper()
    return None


def _deep_merge(base: Any, override: Any, path: str, applied: list[str]) -> Any:
    """Recursively merge ``override`` onto ``base``; record overridden leaf paths."""
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, ovr_val in override.items():
            sub = f"{path}.{key}" if path else key
            if key in merged:
                merged[key] = _deep_merge(merged[key], ovr_val, sub, applied)
            else:
                merged[key] = copy.deepcopy(ovr_val)
                applied.append(sub)
        return merged
    if isinstance(base, list) and isinstance(override, list):
        merged_list = list(base)
        for i, ovr_item in enumerate(override):
            sub = f"{path}[{i}]"
            if i < len(merged_list):
                merged_list[i] = _deep_merge(merged_list[i], ovr_item, sub, applied)
            else:
                merged_list.append(copy.deepcopy(ovr_item))
                applied.append(sub)
        return merged_list
    # Leaf (or type mismatch): override wins.
    if base != override:
        applied.append(path)
    return copy.deepcopy(override)


def load_resolved_config(
    path: str | Path,
    *,
    override_dir: str | Path | None = None,
) -> tuple[dict, dict]:
    """Load a config and merge its confidential overrides (if any).

    Returns ``(resolved_config, provenance)`` where ``provenance`` holds
    ``overrides_applied`` (list of dotted leaf paths), ``private`` (confidential,
    never in the config), and ``override_file`` (path or None).
    """
    # Late-bound so callers/tests can patch the module default at runtime.
    if override_dir is None:
        override_dir = _DEFAULT_OVERRIDE_DIR
    path = Path(path)
    base = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    provenance: dict[str, Any] = {
        "overrides_applied": [],
        "private": {},
        "override_file": None,
    }

    ticker = _ticker_of(base, path)
    if ticker is None:
        return base, provenance

    override_path = Path(override_dir) / f"{ticker}.yaml"
    if not override_path.exists():
        return base, provenance

    ovr = yaml.safe_load(override_path.read_text(encoding="utf-8")) or {}
    confidential = ovr.get("confidential_overrides") or {}

    applied: list[str] = []
    resolved = _deep_merge(base, confidential, "", applied)

    provenance["overrides_applied"] = applied
    provenance["private"] = ovr.get("private") or {}
    provenance["override_file"] = str(override_path)

    # Elevate evidence level when a value driver was actually overridden.
    if any(p.split(".", 1)[0].split("[", 1)[0] in _VALUE_DRIVER_SECTIONS for p in applied):
        meta = dict(resolved.get("_meta") or {})
        meta["evidence_level"] = "full"
        meta["overrides_applied"] = applied
        resolved["_meta"] = meta

    return resolved, provenance
