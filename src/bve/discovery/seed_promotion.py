"""Promote an analyst-approved proposed_seed into the staging registry.

Conservative consumption path for discovered leads:

    analyst approves a proposed_seed
      -> the seed is appended to a SEPARATE seeds_auto.yaml (never the curated
         universe_registry.yaml)
      -> bve-profile build --missing merges seeds_auto.yaml and builds the profile
      -> the name enters the screen

Guards: approval is required (this is only ever called from an explicit approve
command); a name already in the curated registry, already in seeds_auto, or on the
exclusion ledger is refused (no duplicates, no resurrecting rejected names); and
the originating provenance from proposed_seeds.yaml is carried into the staged seed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from bve.discovery.exclusion_ledger import ExclusionLedger
from bve.pipeline.universe_registry import UniverseRegistryEntry, load_universe_registry

# Registry-entry fields carried from a proposed seed into seeds_auto.yaml.
_SEED_FIELDS = (
    "ticker", "company_name", "asset_id", "drug_name", "indication",
    "therapeutic_area", "stage", "modality", "nct_id",
)

# Promotion outcomes.
STATUS_PROMOTED = "promoted"
STATUS_NOT_FOUND = "not_found"
STATUS_DUPLICATE = "duplicate"
STATUS_EXCLUDED = "excluded"


@dataclass(frozen=True)
class PromotionResult:
    status: str
    ticker: str
    detail: str
    seed: Optional[dict] = None
    seeds_auto_path: Optional[Path] = None


def load_proposed_entries(path: str | Path) -> dict[str, dict]:
    """Flatten a proposed_seeds.yaml doc to ``{TICKER: entry}`` across all sections."""
    p = Path(path)
    if not p.exists():
        return {}
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out: dict[str, dict] = {}
    for section in ("proposals", "review", "auto_added"):
        for entry in doc.get(section) or []:
            tkr = str(entry.get("ticker", "")).upper()
            if tkr and tkr not in out:
                out[tkr] = entry
    return out


def _existing_tickers(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        return {e.ticker.upper() for e in load_universe_registry(path)}
    except Exception:
        return set()


def _seed_from_proposed(entry: dict, *, reviewer: Optional[str], rationale: Optional[str],
                        now: datetime) -> dict:
    """Build a registry-shaped seed dict + provenance from a proposed entry."""
    seed = {k: entry.get(k) for k in _SEED_FIELDS}
    meta = entry.get("_meta", {}) or {}
    seed["provenance"] = {
        "source": "bve-discover",
        "disposition": meta.get("disposition"),
        "tier": meta.get("tier"),
        "score": meta.get("score"),
        "proposed_at": meta.get("generated_at"),
        "approved_by": reviewer,
        "approved_at": now.isoformat(),
        "rationale": rationale,
    }
    return seed


def promote_seed(
    ticker: str,
    *,
    proposals_path: str | Path,
    seeds_auto_path: str | Path,
    registry_path: str | Path,
    exclusion_path: Optional[str | Path] = None,
    reviewer: Optional[str] = None,
    rationale: Optional[str] = None,
    now: Optional[datetime] = None,
) -> PromotionResult:
    """Append an approved proposed_seed to seeds_auto.yaml (idempotent, guarded)."""
    tkr = ticker.upper()
    now = now or datetime.now(timezone.utc)
    seeds_auto_path = Path(seeds_auto_path)

    proposed = load_proposed_entries(proposals_path)
    if tkr not in proposed:
        return PromotionResult(STATUS_NOT_FOUND, tkr,
                               f"{tkr} not found in {proposals_path}")

    ledger = ExclusionLedger(exclusion_path) if exclusion_path else ExclusionLedger()
    if ledger.is_excluded(tkr):
        rec = ledger.get(tkr)
        return PromotionResult(STATUS_EXCLUDED, tkr,
                               f"{tkr} is on the exclusion ledger ({rec.reason})")

    if tkr in _existing_tickers(Path(registry_path)):
        return PromotionResult(STATUS_DUPLICATE, tkr,
                               f"{tkr} already in curated registry")
    if tkr in _existing_tickers(seeds_auto_path):
        return PromotionResult(STATUS_DUPLICATE, tkr,
                               f"{tkr} already in seeds_auto.yaml")

    seed = _seed_from_proposed(proposed[tkr], reviewer=reviewer, rationale=rationale, now=now)

    # Validate the registry-shaped fields before writing (fail loud on bad seed).
    UniverseRegistryEntry.model_validate({k: seed[k] for k in _SEED_FIELDS})

    doc = {}
    if seeds_auto_path.exists():
        doc = yaml.safe_load(seeds_auto_path.read_text(encoding="utf-8")) or {}
    assets = doc.get("assets") or []
    assets.append(seed)
    doc["assets"] = assets
    doc["generated_at"] = now.isoformat()

    seeds_auto_path.parent.mkdir(parents=True, exist_ok=True)
    seeds_auto_path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    return PromotionResult(STATUS_PROMOTED, tkr,
                           f"{tkr} ({seed['drug_name']}) staged to {seeds_auto_path}",
                           seed=seed, seeds_auto_path=seeds_auto_path)
