"""Emit a gap-fill watchlist for pipeline-generated auto-configs.

The watchlist maps each generated ticker to its config path in the format the
M&A coverage map expects (``bve.ops.weekly_runner._load_valuation_config_map``
reads ``ticker`` + ``valuation_config``). It is merged into the coverage map
AFTER the replay and provisional watchlists (gap-fill only), so it never
overrides a point-in-time or hand-authored config.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml

from bve.pipeline.asset_profile import CompanyProfile

_HEADER = (
    "# Auto-generated coarse provisional configs from the auto-profile pipeline.\n"
    "# Produced by `bve-profile gen-config --all`. Merged into the M&A coverage map\n"
    "# AFTER the replay + provisional watchlists (gap-fill only); never overrides a\n"
    "# point-in-time or hand-authored config. Investment evidence stays \"coarse\".\n"
)


def build_watchlist_entries(
    profiles: Iterable[CompanyProfile], config_dir: str | Path
) -> list[dict]:
    """Build watchlist entries (ticker -> auto-generated config path)."""
    config_dir = Path(config_dir)
    entries: list[dict] = []
    for profile in profiles:
        asset = profile.lead_asset
        entries.append(
            {
                "company_id": profile.company_id,
                "asset_id": asset.asset_id,
                "drug_name": asset.drug_name.value,
                "indication": asset.indication.value,
                "ticker": profile.ticker.upper(),
                "valuation_config": str(config_dir / f"{profile.ticker.lower()}.yaml"),
            }
        )
    return entries


def write_auto_watchlist(
    profiles: Iterable[CompanyProfile],
    config_dir: str | Path,
    out_path: str | Path,
) -> Path:
    """Write the auto-generated watchlist YAML; return the path."""
    entries = build_watchlist_entries(profiles, config_dir)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        _HEADER + yaml.safe_dump({"watchlist": entries}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return out_path
