"""
Ingestion source-health report.

Turns an ``IngestionRunResult`` into a human-readable markdown table and a
machine-readable JSON snapshot that answer, per run:

    sources attempted | records fetched | classified | appended |
    duplicates | unclassified | failures | verdict

The point is to make "did news / SEC / FDA actually work, or silently return
nothing?" answerable at a glance, and to make degraded/failed sources loud.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bve.ingestion.live_ingestion_runner import IngestionRunResult

# Verdict → glyph for quick visual scanning in a terminal/markdown view.
_VERDICT_GLYPH = {
    "OK": "✅ OK",
    "NO_DATA": "➖ NO_DATA",
    "DEGRADED": "⚠️ DEGRADED",
    "FAILED": "❌ FAILED",
}

_COLUMNS = [
    ("source", "Source"),
    ("attempted", "Attempted"),
    ("fetched", "Fetched"),
    ("classified", "Classified"),
    ("appended", "Appended"),
    ("dupes", "Dupes"),
    ("unclassified", "Unclass."),
    ("failures", "Failures"),
    ("verdict", "Verdict"),
]


def render_health_report(result: "IngestionRunResult") -> str:
    """Render the per-source health table as markdown."""
    lines: list[str] = []
    lines.append(f"# Ingestion Health — {result.as_of_date.isoformat()}")
    lines.append("")
    lines.append(
        f"Lookback: {result.lookback_days}d · "
        f"items seen: {result.items_seen} · "
        f"classified: {result.items_classified} · "
        f"appended: {result.records_appended} · "
        f"duplicates: {result.duplicates_skipped} · "
        f"unclassified: {result.unclassified_count}"
    )
    lines.append("")

    header = "| " + " | ".join(label for _, label in _COLUMNS) + " |"
    divider = "| " + " | ".join("---" for _ in _COLUMNS) + " |"
    lines.append(header)
    lines.append(divider)

    if not result.source_health:
        lines.append("| _(no sources run)_ |" + " |" * (len(_COLUMNS) - 1))

    for src_key in sorted(result.source_health):
        h = result.source_health[src_key]
        verdict = _VERDICT_GLYPH.get(h.verdict, h.verdict)
        row = [
            src_key,
            str(h.tickers_attempted),
            str(h.records_fetched),
            str(h.records_classified),
            str(h.records_appended),
            str(h.duplicates_skipped),
            str(h.unclassified),
            str(h.fetch_failures),
            verdict,
        ]
        lines.append("| " + " | ".join(row) + " |")

    # Failure and diagnostic detail — include quiet-window evidence and
    # classifier rejection counts so NO_DATA is distinguishable from silence.
    failed = [
        (k, result.source_health[k])
        for k in sorted(result.source_health)
        if result.source_health[k].failure_samples
    ]
    if failed:
        lines.append("")
        lines.append("## Failure samples")
        for src_key, h in failed:
            lines.append("")
            lines.append(f"**{src_key}** ({h.fetch_failures} failure(s)):")
            for sample in h.failure_samples:
                lines.append(f"- {sample}")

    for src_key in sorted(result.source_health):
        h = result.source_health[src_key]
        lines.append("")
        lines.append(f"### {src_key} diagnostic reason")
        lines.append(f"- Verdict reason: {h.verdict_reason}")
        if h.rejection_reasons:
            lines.append(f"- Rejection reasons: {dict(h.rejection_reasons)}")
        if h.expected_unclassified:
            lines.append(f"- Expected non-event records: {h.expected_unclassified}")
        if h.request_diagnostics:
            statuses = [str(d.get("status", "unknown")) for d in h.request_diagnostics]
            lines.append(f"- Request statuses: {', '.join(statuses)}")

    lines.append("")
    return "\n".join(lines)


def health_report_to_dict(result: "IngestionRunResult") -> dict:
    """Machine-readable health snapshot (for trending across runs)."""
    return {
        "as_of_date": result.as_of_date.isoformat(),
        "lookback_days": result.lookback_days,
        "items_seen": result.items_seen,
        "items_classified": result.items_classified,
        "records_appended": result.records_appended,
        "duplicates_skipped": result.duplicates_skipped,
        "unclassified_count": result.unclassified_count,
        "sources": {k: v.to_dict() for k, v in result.source_health.items()},
    }


def write_health_report(result: "IngestionRunResult", output_dir: Path) -> list[Path]:
    """Write ``ingestion_health.md`` and ``ingestion_health.json`` into output_dir."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    md_path = output_dir / "ingestion_health.md"
    json_path = output_dir / "ingestion_health.json"

    md_path.write_text(render_health_report(result), encoding="utf-8")
    json_path.write_text(
        json.dumps(health_report_to_dict(result), indent=2), encoding="utf-8"
    )
    return [md_path, json_path]


def has_degraded_or_failed(result: "IngestionRunResult") -> bool:
    """True if any source's verdict is DEGRADED or FAILED (for --fail-on-degraded)."""
    return any(
        h.verdict in ("DEGRADED", "FAILED") for h in result.source_health.values()
    )
