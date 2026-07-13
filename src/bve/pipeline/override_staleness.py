"""Override revalidation — detect when public facts have changed materially
enough that an existing analyst override may need to be revisited.

No overrides are deleted. The detector writes a small sidecar JSON record
(``profiles/<TICKER>.stale.json``) when a profile rebuild shows a material
change AND an override file already exists for that ticker. The review queue
reads these sidecars as HIGH-severity ``override_revalidation_needed`` items.

Lifecycle:
- Sidecar written: profile rebuilt, material change detected, override exists.
- Sidecar cleared: profile rebuilt, no material change (or no override present).
- Flag suppressed in queue: analyst resolves via ``bve-profile resolve``
  (existing resolution-suppression rule: ``decided_at >= profile.generated_at``).
- Flag re-surfaces: profile rebuilt again after a stale resolution.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from bve.pipeline.asset_profile import CompanyProfile

_DEFAULT_OVERRIDE_DIR: str = "examples/configs/overrides"
_DEFAULT_PROFILES_DIR: str = "profiles"

# Proportional market-cap change that triggers revalidation of financial overrides.
MCAP_MOVE_THRESHOLD: float = 0.20


def _safe(fn: Callable[[CompanyProfile], object], profile: CompanyProfile) -> object:
    try:
        return fn(profile)
    except Exception:
        return None


def _mcap_moved(old: object, new: object, threshold: float) -> bool:
    if old is None or new is None:
        return False
    try:
        old_f, new_f = float(old), float(new)  # type: ignore[arg-type]
        if old_f == 0.0:
            return False
        return abs(new_f - old_f) / abs(old_f) > threshold
    except (TypeError, ValueError):
        return False


# Each entry: (review_label, extractor).  Order determines the detail string.
_MATERIAL: list[tuple[str, Callable[[CompanyProfile], object]]] = [
    ("lead_asset_name", lambda p: p.lead_asset.drug_name.value),
    ("indication", lambda p: p.lead_asset.indication.value),
    ("stage", lambda p: p.lead_asset.stage.value),
    ("therapeutic_area", lambda p: p.lead_asset.therapeutic_area.value),
    ("nct_id", lambda p: p.lead_asset.nct_id),
    ("market_cap_millions", lambda p: p.market_cap_millions.value),
]


def check_override_staleness(
    old_profile: CompanyProfile,
    new_profile: CompanyProfile,
) -> list[str]:
    """Return field labels that changed materially between two profile snapshots.

    An empty list means nothing material changed — the override is still current.
    """
    changed: list[str] = []
    for label, extractor in _MATERIAL:
        old_val = _safe(extractor, old_profile)
        new_val = _safe(extractor, new_profile)
        if label == "market_cap_millions":
            if _mcap_moved(old_val, new_val, MCAP_MOVE_THRESHOLD):
                changed.append(label)
        else:
            # Any identity/categorical change that produces a non-None new value.
            if old_val != new_val and new_val not in (None, "", "unknown"):
                changed.append(label)
    return changed


# ---------------------------------------------------------------------------
# Sidecar I/O
# ---------------------------------------------------------------------------


def _stale_path(ticker: str, profiles_dir: Path) -> Path:
    return profiles_dir / f"{ticker.upper()}.stale.json"


def write_stale_record(
    ticker: str,
    changed_fields: list[str],
    profiles_dir: Path,
    *,
    details: str = "",
) -> Path:
    """Persist a staleness sidecar for *ticker*."""
    path = _stale_path(ticker, profiles_dir)
    profiles_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "ticker": ticker.upper(),
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "changed_fields": changed_fields,
        "details": details,
    }
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


def clear_stale_record(ticker: str, profiles_dir: Path) -> None:
    """Remove the staleness sidecar for *ticker* (no-op if absent)."""
    path = _stale_path(ticker, profiles_dir)
    if path.exists():
        path.unlink()


def load_all_stale(profiles_dir: Path) -> dict[str, list[str]]:
    """Return ``{TICKER: [changed_field, ...]}`` for all stale-marked tickers."""
    result: dict[str, list[str]] = {}
    if not profiles_dir.exists():
        return result
    for f in profiles_dir.glob("*.stale.json"):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
            ticker = str(doc.get("ticker", "")).upper() or f.stem.split(".")[0].upper()
            fields = [str(x) for x in doc.get("changed_fields", [])]
            if ticker and fields:
                result[ticker] = fields
        except (OSError, ValueError):
            continue
    return result


# ---------------------------------------------------------------------------
# Convenience: update stale state after a profile rebuild
# ---------------------------------------------------------------------------


def update_after_rebuild(
    ticker: str,
    old_profile: Optional[CompanyProfile],
    new_profile: CompanyProfile,
    *,
    override_dir: str | Path = _DEFAULT_OVERRIDE_DIR,
    profiles_dir: str | Path = _DEFAULT_PROFILES_DIR,
) -> list[str]:
    """Compute staleness after a profile rebuild and write / clear the sidecar.

    Returns the list of changed field labels (empty if nothing material changed).
    Writes the sidecar only when both (a) material changes exist and (b) an
    override file already exists for this ticker — no override means nothing to
    revalidate.  Always clears a stale record when there are no changes.
    """
    profiles_dir = Path(profiles_dir)
    override_path = Path(override_dir) / f"{ticker.upper()}.yaml"

    if old_profile is None:
        # First build — nothing to compare against.
        clear_stale_record(ticker, profiles_dir)
        return []

    changed = check_override_staleness(old_profile, new_profile)

    if changed and override_path.exists():
        write_stale_record(
            ticker, changed, profiles_dir,
            details=f"override {override_path.name} may embed stale assumptions",
        )
    else:
        clear_stale_record(ticker, profiles_dir)

    return changed
