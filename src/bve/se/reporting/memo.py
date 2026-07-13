"""Render an auditable public pre-diligence landscape memo."""

from __future__ import annotations

from bve.se.pipeline import SESearchResult
from bve.se.schemas.contracts import GateStatus


def _asset_name(result: SESearchResult, asset_id: str) -> str:
    return next(
        (asset.canonical_name for asset in result.candidates if asset.asset_id == asset_id),
        asset_id,
    )


def _group(lines: list[str], title: str, asset_ids: list[str], result: SESearchResult) -> None:
    lines.extend([f"## {title} ({len(asset_ids)})", ""])
    if not asset_ids:
        lines.extend(["_None._", ""])
        return
    lines.extend(["| Company/asset | Asset ID |", "|---|---|"])
    for asset_id in asset_ids:
        lines.append(f"| {_asset_name(result, asset_id)} | `{asset_id}` |")
    lines.append("")


def render_search_memo(result: SESearchResult) -> str:
    manifest = result.run_manifest
    lines = [
        f"# Buyer-Specific S&E Landscape — {result.problem_id}",
        "",
        f"**{result.label}**",
        "",
        f"- Run: `{manifest.run_id}`",
        f"- As of: {manifest.as_of_date.isoformat()}",
        f"- Coverage status: **{manifest.status.value}**",
        "",
    ]
    if manifest.incomplete_reasons:
        lines.extend(["### Incomplete-run reasons", ""])
        lines.extend(f"- {reason}" for reason in manifest.incomplete_reasons)
        lines.append("")

    lines.extend(["## Coverage", "", "| Source | Outcome |", "|---|---|"])
    for source, outcome in sorted(manifest.source_status.items()):
        lines.append(f"| {source} | {outcome.value} |")
    if not manifest.source_status:
        lines.append("| — | No source attempts recorded |")
    lines.append("")
    for attempt in result.search_attempts:
        if attempt.error:
            lines.append(
                f"- Attempt `{attempt.attempt_id}` failed at {attempt.source}: {attempt.error}"
            )
    if any(attempt.error for attempt in result.search_attempts):
        lines.append("")
    for coverage_pass in manifest.coverage_passes:
        lines.append(
            f"- Pass {coverage_pass.pass_number}: {coverage_pass.new_mentions} new mentions; "
            f"{coverage_pass.unresolved_mentions} unresolved; "
            f"{len(coverage_pass.remaining_frontier)} frontier queries"
        )
    lines.append("")

    _group(lines, "Eligible and ranked", result.eligible_asset_ids, result)
    _group(lines, "Confirmed exclusions", result.excluded_asset_ids, result)
    _group(lines, "Unresolved — analyst research required", result.unresolved_asset_ids, result)

    lines.extend(["## Gate audit", ""])
    for evaluation in result.gate_evaluations:
        lines.extend([f"### {_asset_name(result, evaluation.subject_id)}", ""])
        lines.extend(
            [
                "| Gate | Requirement | Status | Rationale | Claims |",
                "|---|---|---|---|---|",
            ]
        )
        for decision in evaluation.decisions:
            claims = ", ".join(f"`{claim}`" for claim in decision.supporting_or_contradictory_claim_ids)
            status = decision.analyst_override or decision.status
            lines.append(
                f"| {decision.gate_id} | `{decision.requirement_id}` | {status.value} | "
                f"{decision.rationale} | {claims or '—'} |"
            )
        lines.append("")

    lines.extend(["## Prioritized research queue", ""])
    if not result.review_queue:
        lines.extend(["_No unresolved review items._", ""])
    else:
        for item in sorted(
            result.review_queue,
            key=lambda value: {"critical": 0, "high": 1, "medium": 2, "low": 3}[value.priority],
        ):
            lines.append(
                f"- **{item.priority.upper()}** — {_asset_name(result, item.subject_id)}: "
                f"{item.reason}"
            )
        lines.append("")

    documents = {document.document_id: document for document in result.source_documents}
    lines.extend(["## Evidence citations", ""])
    if not result.claims:
        lines.extend(["_No extracted claims._", ""])
    else:
        for claim in result.claims:
            document = documents.get(claim.source_document_id)
            source = f"[{document.publisher}]({document.source_url})" if document else claim.source_document_id
            lines.append(
                f"- `{claim.claim_id}` — {source}, {claim.locator or 'locator unavailable'}: "
                f'“{claim.supporting_passage}”'
            )
        lines.append("")

    unknown_count = sum(
        (decision.analyst_override or decision.status) == GateStatus.UNKNOWN
        for evaluation in result.gate_evaluations
        for decision in evaluation.decisions
    )
    lines.extend(
        [
            "## Limitations",
            "",
            f"- {unknown_count} gate decisions remain UNKNOWN.",
            "- Public evidence is screening evidence, not diligence-confirmed truth.",
            "- No transaction willingness or undisclosed rights position is inferred from silence.",
            "",
        ]
    )
    return "\n".join(lines)
