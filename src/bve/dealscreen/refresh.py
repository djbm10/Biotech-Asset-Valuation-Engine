"""Compare a refreshed landscape import with the previous one, and check every live decision.

A vendor refresh can add, remove or change programs. Analyst decisions point at claims,
findings, assets and identity flags. This module reports, without changing anything:
- which assets were added or removed;
- which field values were added or removed per asset;
- which active decisions no longer have a subject (ORPHANED).

An orphaned decision stays in the log, so history is never rewritten, but it no longer
affects the screen. A changed value orphans a decision on the old value; nothing is ever
transferred to the new value.
"""

from __future__ import annotations

import re
from typing import Any

from bve.dealscreen.models import AgentFinding, IdentityFlag, ImportResult
from bve.dealscreen.review import ReviewState

_LEGACY_CLAIM_ID = re.compile(r":r\d+:")


def _values(result: ImportResult | None) -> dict[str, dict[str, set[str]]]:
    """Per asset and field: the set of 'value [source | date]' strings, so a source or date
    change counts as a change, not only a value change (review M4)."""
    out: dict[str, dict[str, set[str]]] = {}
    for asset in (result.assets if result else []):
        fields: dict[str, set[str]] = {}
        for claim in asset.claims:
            fields.setdefault(claim.field, set()).add(
                f"{claim.value_as_written} [{claim.source_reference or ''} | {claim.source_date or ''}]")
        out[asset.asset_id] = fields
    return out


def refresh_report(
    previous: ImportResult | None,
    current: ImportResult,
    state: ReviewState,
    findings: list[AgentFinding],
    flags: list[IdentityFlag],
) -> dict[str, Any]:
    old, new = _values(previous), _values(current)
    names = {a.asset_id: f"{a.external_id} {a.program_name}"
             for a in [*(previous.assets if previous else []), *current.assets]}
    changes: dict[str, list[dict[str, Any]]] = {}
    for asset_id in sorted(set(old) & set(new)):
        for field in sorted(set(old[asset_id]) | set(new[asset_id])):
            before, after = old[asset_id].get(field, set()), new[asset_id].get(field, set())
            if before != after:
                changes.setdefault(names[asset_id], []).append(
                    {"field": field, "removed": sorted(before - after), "added": sorted(after - before)})

    current_assets = set(new)
    claim_ids = {c.claim_id for a in current.assets for c in a.claims}
    finding_assets = {f.finding_id: f.asset_id for f in findings}
    flag_ids = {f.flag_id for f in flags}
    orphaned: list[dict[str, str]] = []
    for claim_id, decision in sorted(state.claims.items()):
        if claim_id not in claim_ids:
            reason = ("legacy row-based claim id from before Cycle 5; re-decide against the current claim"
                      if _LEGACY_CLAIM_ID.search(claim_id)
                      else "claim no longer in the landscape (value, source or date changed, or removed)")
            orphaned.append({"subject": claim_id, "decision": f"{decision} claim", "reason": reason})
    for finding_id, decision in sorted(state.findings.items()):
        if finding_assets.get(finding_id) not in current_assets:
            orphaned.append({"subject": finding_id, "decision": f"{decision} finding",
                             "reason": "the finding's asset is no longer in the landscape"})
    for assertion_id, a in sorted(state.assertions.items()):
        if a["asset_id"] not in current_assets:
            orphaned.append({"subject": assertion_id, "decision": f"assertion {a['field']}={a['value']!r}",
                             "reason": "asset no longer in the landscape"})
    for label, subjects in (("finalist", state.finalists), ("valuation selection", state.valuation_selected)):
        for asset_id in sorted(subjects):
            if asset_id not in current_assets:
                orphaned.append({"subject": asset_id, "decision": label,
                                 "reason": "asset no longer in the landscape"})
    for asset_id in sorted(state.diligence_requests):
        if asset_id not in current_assets:
            orphaned.append({"subject": asset_id, "decision": "diligence request",
                             "reason": "asset no longer in the landscape"})
    for flag_id, resolution in sorted(state.identity_flags.items()):
        if flag_id not in flag_ids:
            orphaned.append({"subject": flag_id, "decision": f"identity resolution {resolution}",
                             "reason": "identity flag no longer raised"})
    # Decisions that still apply but whose asset's content changed (review M4): re-review.
    decided = {*state.finalists, *state.valuation_selected, *state.diligence_requests,
               *(a["asset_id"] for a in state.assertions.values()),
               *(finding_assets.get(f) for f in state.findings),
               *(":".join(c.split(":")[:2]) for c in state.claims)}
    changed_ids = {a for a in set(old) & set(new) if names[a] in changes}
    review_needed = sorted(names[a] for a in decided & changed_ids)
    return {
        "previous_dataset": previous.manifest.dataset_version if previous else None,
        "current_dataset": current.manifest.dataset_version,
        "assets_added": sorted(names[a] for a in set(new) - set(old)),
        "assets_removed": sorted(names[a] for a in set(old) - set(new)),
        "field_changes": changes,
        "orphaned_decisions": orphaned,
        "decided_assets_with_changed_content": review_needed,
    }
