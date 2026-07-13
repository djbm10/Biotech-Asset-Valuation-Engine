"""
Score-change audit report.

Renders the per-feature audit trail from
``EvidenceLedger.compute_score_state_with_trail`` into markdown so you can show
someone exactly why a company's M&A feature scores moved: which sourced
headline applied which delta, with what confidence, and why.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bve.ingestion.evidence_ledger import ScoreChangeEntry


def _fmt_delta(x: float) -> str:
    return f"{x:+.3f}"


def render_score_audit(
    ticker: str,
    scores: dict[str, float],
    trail: list["ScoreChangeEntry"],
    as_of: str | None = None,
) -> str:
    """
    Render a score-change audit as markdown.

    Final scores are shown first, then a chronological table per feature with
    full provenance (date, event, Δ requested/applied, before→after,
    confidence, source, snippet, URL).
    """
    lines: list[str] = []
    title = f"# Score Audit — {ticker}"
    if as_of:
        title += f" (as of {as_of})"
    lines.append(title)
    lines.append("")

    # Final scores.
    lines.append("## Final scores")
    lines.append("")
    if scores:
        lines.append("| Feature | Score |")
        lines.append("| --- | --- |")
        for feature in sorted(scores):
            lines.append(f"| {feature} | {scores[feature]:.3f} |")
    else:
        lines.append("_(no scores)_")
    lines.append("")

    if not trail:
        lines.append("## Changes")
        lines.append("")
        lines.append("_No score changes — no resolved events for this ticker._")
        lines.append("")
        return "\n".join(lines)

    # Group changes by feature.
    by_feature: dict[str, list["ScoreChangeEntry"]] = {}
    for e in trail:
        by_feature.setdefault(e.feature, []).append(e)

    lines.append("## Changes by feature")
    for feature in sorted(by_feature):
        entries = by_feature[feature]
        lines.append("")
        lines.append(f"### {feature}")
        lines.append("")
        lines.append(
            "| Date | Event | Δ req | Δ applied | Before→After | Conf | Source | Why | Snippet |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for e in entries:
            flags = " (clamped)" if e.clamped else ""
            if e.decay_weight < 1.0:
                flags += f" (decay {e.decay_weight:.2f})"
            reasons = ", ".join(e.reasons) if e.reasons else "—"
            url = e.source_url or "—"
            snippet = (e.snippet or "").replace("|", "\\|").replace("\n", " ")
            source = f"{e.source_type}<br>{url}" if url != "—" else e.source_type
            lines.append(
                f"| {e.event_date} "
                f"| {e.event_type} "
                f"| {_fmt_delta(e.delta_requested)} "
                f"| {_fmt_delta(e.delta_applied)}{flags} "
                f"| {e.score_before:.3f}→{e.score_after:.3f} "
                f"| {e.confidence:.2f} "
                f"| {source} "
                f"| {reasons} "
                f"| {snippet} |"
            )

    lines.append("")
    return "\n".join(lines)
