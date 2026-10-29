"""Human-confirmed identity groups (cycle A2 G2).

An identity flag says two source records may be the same molecule. Only a HUMAN reviewer's
SAME_MOLECULE resolution groups them. Grouping is for counting and display: records are never
merged, their claims stay separate, and no gate or disposition changes.
"""

from __future__ import annotations

from typing import Any

from bve.dealscreen.models import IdentityFlag
from bve.dealscreen.review import DecisionLog


def identity_groups(flags: list[IdentityFlag], log: DecisionLog) -> dict[str, str]:
    """Asset id -> group key ("<label> (group of <root>)") for assets in a human-confirmed
    SAME_MOLECULE flag. The key is unique per group; the label is for display."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            x = parent[x]
        return x

    confirmed: list[IdentityFlag] = []
    for flag in flags:
        resolution: dict[str, Any] = log.state.identity_resolutions.get(flag.flag_id, {})
        if resolution.get("state") != "SAME_MOLECULE" or resolution.get("reviewer_kind") != "HUMAN":
            continue
        confirmed.append(flag)
        first, *rest = flag.asset_ids
        for other in rest:
            parent[find(other)] = find(first)
    labels: dict[str, str] = {}
    for flag in confirmed:  # label each final group after all unions
        labels.setdefault(find(flag.asset_ids[0]), flag.shared_value)
    groups: dict[str, str] = {}
    for asset_id in list(parent):
        root = find(asset_id)
        # Unique per union-find root, so two groups sharing a label never collapse (review A2-5).
        groups[asset_id] = f"{labels.get(root, 'group')} (group of {root})"
    return groups


def distinct_count(asset_ids: list[str], groups: dict[str, str]) -> int:
    """Records counted once per human-confirmed group; ungrouped records count alone."""
    return len({groups.get(a, a) for a in asset_ids})


__all__ = ["distinct_count", "identity_groups"]
