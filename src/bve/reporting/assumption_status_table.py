"""Render assumption ownership status as a formatted table."""

from __future__ import annotations

from datetime import date
from typing import Sequence

from bve.governance.assumption_owner import AssumptionOwner
from bve.governance.assumption_review import AssumptionReviewer


def render_assumption_status_table(
    owners: Sequence[AssumptionOwner],
    as_of: date | None = None,
    emit_warnings: bool = False,
) -> str:
    """Return a Markdown table of assumption ownership status."""
    check_date = as_of or date.today()
    reviewer = AssumptionReviewer()
    report = reviewer.review(owners, as_of=check_date, emit_warnings=emit_warnings)

    lines = []
    lines.append("## Assumption Ownership")
    lines.append("")
    if report.has_stale_inputs:
        lines.append("> **STALE_INPUT WARNING**: One or more assumptions are expired. "
                     "M&A classification capped at `catalyst_watch`. "
                     "Precise probabilities disabled.")
        lines.append("")

    header = "| Assumption | Owner | Status | Last Reviewed | Expires | Days Left | Source | Confidence |"
    sep = "|---|---|---|---|---|---|---|---|"
    lines.append(header)
    lines.append(sep)

    for o in owners:
        d = o.to_display_dict(check_date)
        days = d["days_remaining"]
        days_str = f"**{days}**" if days < 0 else str(days)
        lines.append(
            f"| {d['field']} | {d['owner']} | {d['status']} | "
            f"{d['last_reviewed']} | {d['expires']} | {days_str} | "
            f"{d['source']} | {d['confidence']} |"
        )

    lines.append("")
    lines.append(f"*Generated {check_date.isoformat()}*")
    return "\n".join(lines)
