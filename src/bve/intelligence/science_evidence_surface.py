"""Compact human-facing summaries for science evidence bundles."""

from __future__ import annotations

from collections import Counter

from bve.intelligence.science_evidence import ScienceEvidenceBundle


def build_compact_evidence_surface(
    bundle: ScienceEvidenceBundle | None,
    *,
    max_snippets: int = 5,
) -> dict | None:
    """Return compact evidence surfacing data for replay/memo display.

    Full evidence tables stay in artifacts; this summary intentionally keeps only
    counts, a few source-backed snippets, warnings, and gaps.
    """
    if bundle is None:
        return None
    counts = Counter(item.mapped_component.value for item in bundle.items)
    snippets = []
    for item in bundle.items[:max_snippets]:
        snippets.append(
            {
                "quote": item.quote or item.text_span,
                "component": item.mapped_component.value,
                "mapped_field": item.mapped_field.value,
                "direction": item.direction.value,
                "confidence": item.confidence,
                "source_id": item.source_id,
                "source_uri": item.source_uri,
                "warnings": list(item.warnings),
            }
        )
    warning_count = len(bundle.bundle_warnings) + sum(len(item.warnings) for item in bundle.items)
    return {
        "evidence_counts_by_component": dict(sorted(counts.items())),
        "top_snippets": snippets,
        "rejected_or_ambiguous_warning_count": warning_count,
        "unresolved_gaps": list(bundle.unresolved_gaps),
    }
