"""
MemoEvidenceBuilder — assembles MemoEvidence from an existing ValuationOutput.

All population is deterministic: the builder reads structured fields on
ValuationOutput (AssumptionLog, ComparableDealAnalysis, Asset, trials,
lifecycle_events, decision_framing, signals, knowledge_artifacts) and
converts them into typed MemoEvidenceRef objects.

No LLM is called. No data is fabricated. Where structured evidence is
absent, an explicit gap string is added to ``unsupported_claims``.

Section coverage:
  biology       — MoA, biological target, POS methodology, StructuredSignal biology events
  trial         — per-phase POS assumptions, upcoming catalysts, StructuredSignal trial events
  competitive   — competitor program names, differentiation notes, KnowledgeArtifact landscapes
  assumptions   — all KeyAssumption entries from AssumptionLog
  comps         — matched comparable deals, data quality, deal source
  falsification — kill criteria, thesis changers, comps-based falsifiers
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from bve.reporting.evidence import (
    MemoEvidence,
    MemoEvidenceRef,
    MemoSectionEvidence,
    SourceType,
)

if TYPE_CHECKING:
    from bve.valuation.outputs import ValuationOutput

# ── Event-type sets for signal routing ───────────────────────────────────────
# These match EventType enum values from bve.intelligence.taxonomy
_BIOLOGY_EVENT_TYPES = {
    "publication",
    "conference_presentation",
    "trial_readout",
}
_TRIAL_EVENT_TYPES = {
    "trial_readout",
    "interim_analysis",
    "enrollment_update",
    "endpoint_change",
    "safety_signal",
}


# ── Signal / artifact helpers ─────────────────────────────────────────────────

def _event_type_val(sig) -> str:
    """Return the string value of sig.event_type regardless of whether it's an enum or str."""
    et = getattr(sig, "event_type", "")
    return et if isinstance(et, str) else et.value


def _signal_label(sig) -> str:
    """Build a human-readable label from a StructuredSignal (duck-typed)."""
    parts = [_event_type_val(sig).replace("_", " ").title()]
    phase = getattr(sig, "trial_phase", None)
    if phase is not None:
        phase_str = phase if isinstance(phase, str) else phase.value
        parts.append(phase_str.replace("_", " ").upper())
    ep_met = getattr(sig, "primary_endpoint_met", None)
    if ep_met is True:
        parts.append("endpoint met")
    elif ep_met is False:
        parts.append("endpoint missed")
    p_val = getattr(sig, "p_value", None)
    if p_val is not None:
        parts.append(f"p={p_val:.3f}")
    hr = getattr(sig, "hazard_ratio", None)
    if hr is not None:
        parts.append(f"HR={hr:.2f}")
    rr = getattr(sig, "response_rate", None)
    if rr is not None:
        parts.append(f"ORR={rr:.0%}")
    enroll = getattr(sig, "enrollment_status", None)
    if enroll:
        parts.append(f"enrollment: {enroll}")
    return " · ".join(parts)


def _signal_as_of(sig) -> Optional[str]:
    """Return ISO date string from signal_date if present."""
    d = getattr(sig, "signal_date", None)
    if d is None:
        return None
    return d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]


def _signal_confidence_label(sig) -> str:
    """Convert extraction_confidence float to High/Medium/Low label."""
    score = getattr(sig, "extraction_confidence", None)
    if score is None:
        return "—"
    if score >= 0.8:
        return "High"
    if score >= 0.5:
        return "Medium"
    return "Low"


def _artifact_as_of(artifact) -> Optional[str]:
    """Return ISO date string from artifact.created_at if present."""
    created = getattr(artifact, "created_at", None)
    if created is None:
        return None
    if hasattr(created, "date"):
        return created.date().isoformat()
    return str(created)[:10]


def _artifact_confidence_label(artifact) -> str:
    """Convert artifact.confidence float to High/Medium/Low label."""
    score = getattr(artifact, "confidence", None)
    if score is None:
        return "—"
    if score >= 0.8:
        return "High"
    if score >= 0.5:
        return "Medium"
    return "Low"


def _conf(label: Optional[str]) -> str:
    """Normalize a KeyAssumption confidence label string."""
    if not label:
        return "—"
    return label.capitalize() if label.lower() in ("high", "medium", "low") else label


# ── Section builders ─────────────────────────────────────────────────────────

def _build_biology(output: "ValuationOutput") -> MemoSectionEvidence:
    refs: list[MemoEvidenceRef] = []
    gaps: list[str] = []

    asset = output.asset

    # Mechanism of action
    if asset.mechanism_of_action:
        refs.append(MemoEvidenceRef(
            source_type=SourceType.ASSUMPTION,
            label=f"Mechanism of action: {asset.mechanism_of_action}",
            confidence_label="—",
            notes="As supplied in asset configuration",
        ))
    else:
        gaps.append("Mechanism of action not specified — MoA characterization is missing.")

    # Biological target
    if getattr(asset, "biological_target", None):
        refs.append(MemoEvidenceRef(
            source_type=SourceType.ASSUMPTION,
            label=f"Biological target: {asset.biological_target}",
            confidence_label="—",
            notes="As supplied in asset configuration",
        ))
    else:
        gaps.append("Biological target not specified — target identification lacks structured evidence.")

    # POS methodology (from assumption_log)
    if output.assumption_log:
        pos_m = output.assumption_log.pos_methodology
        refs.append(MemoEvidenceRef(
            source_type=SourceType.ASSUMPTION,
            label=f"POS model: {pos_m.value}",
            url=pos_m.url,
            confidence_label=_conf(pos_m.confidence),
            notes=pos_m.source,
        ))
    else:
        gaps.append(
            "No structured assumption log — POS methodology source is undocumented; "
            "phase transition probabilities are not auditable."
        )

    # StructuredSignal biology evidence (publications, presentations, readouts)
    bio_signals = [
        s for s in output.signals
        if _event_type_val(s) in _BIOLOGY_EVENT_TYPES
    ]
    for sig in bio_signals:
        refs.append(MemoEvidenceRef(
            source_type=SourceType.SIGNAL,
            source_id=getattr(sig, "id", None),
            label=_signal_label(sig),
            confidence_label=_signal_confidence_label(sig),
            confidence_score=getattr(sig, "extraction_confidence", None),
            as_of_date=_signal_as_of(sig),
            notes=(
                f"Extraction model: {sig.extraction_model}"
                if getattr(sig, "extraction_model", None) else None
            ),
        ))

    if not bio_signals:
        gaps.append(
            "Structural/pharmacology characterization (crystal structure, selectivity panel, "
            "in vitro potency data) has no structured evidence linkage in this run. "
            "Add StructuredSignal records via the extraction pipeline to close this gap."
        )

    return MemoSectionEvidence(section_key="biology", refs=refs, unsupported_claims=gaps)


def _build_trial(output: "ValuationOutput") -> MemoSectionEvidence:
    refs: list[MemoEvidenceRef] = []
    gaps: list[str] = []

    # Per-phase POS assumptions from AssumptionLog
    if output.assumption_log and output.assumption_log.phase_pos_list:
        for ka in output.assumption_log.phase_pos_list:
            refs.append(MemoEvidenceRef(
                source_type=SourceType.ASSUMPTION,
                label=f"{ka.parameter}: {ka.value}",
                url=ka.url,
                confidence_label=_conf(ka.confidence),
                notes=ka.source if ka.source else None,
            ))
    else:
        gaps.append(
            "Phase-level POS estimates have no structured source citation. "
            "Add an AssumptionLog via ValuationEngine to document each phase's probability."
        )

    # Upcoming catalysts
    for cat in output.asset.upcoming_catalysts:
        refs.append(MemoEvidenceRef(
            source_type=SourceType.MANUAL,
            label=(
                f"Catalyst: {cat.description}"
                + (f" ({cat.expected_date})" if cat.expected_date else "")
            ),
            confidence_score=cat.probability_positive,
            confidence_label=(
                f"{cat.probability_positive:.0%}" if cat.probability_positive else "—"
            ),
            notes=f"Type: {cat.catalyst_type}",
        ))

    if not output.asset.upcoming_catalysts:
        gaps.append("No upcoming catalysts registered — trial readout timeline is unverified.")

    # Analyst overrides that affected trial parameters
    trial_overrides = [
        o for o in output.analyst_overrides
        if "phase" in o.lower() or "pos" in o.lower()
    ]
    for override_str in trial_overrides:
        refs.append(MemoEvidenceRef(
            source_type=SourceType.MANUAL,
            label=f"Analyst override: {override_str}",
            confidence_label="High",
            notes="Explicitly overridden from industry default in this run.",
        ))

    # StructuredSignal trial evidence (readouts, enrollment, interim, safety)
    trial_signals = [
        s for s in output.signals
        if _event_type_val(s) in _TRIAL_EVENT_TYPES
    ]
    for sig in trial_signals:
        refs.append(MemoEvidenceRef(
            source_type=SourceType.SIGNAL,
            source_id=getattr(sig, "id", None),
            label=_signal_label(sig),
            confidence_label=_signal_confidence_label(sig),
            confidence_score=getattr(sig, "extraction_confidence", None),
            as_of_date=_signal_as_of(sig),
            notes=(
                f"Extraction model: {sig.extraction_model}"
                if getattr(sig, "extraction_model", None) else None
            ),
        ))

    if not trial_signals:
        gaps.append(
            "Trial-level StructuredSignal evidence (hazard ratio, response rate, p-value, "
            "enrollment status) not linked in this run. Connect the extraction pipeline "
            "to populate signal-backed trial claims."
        )

    return MemoSectionEvidence(section_key="trial", refs=refs, unsupported_claims=gaps)


def _build_competitive(output: "ValuationOutput") -> MemoSectionEvidence:
    refs: list[MemoEvidenceRef] = []
    gaps: list[str] = []

    asset = output.asset
    if asset.competitor_assets:
        for comp_name in asset.competitor_assets:
            refs.append(MemoEvidenceRef(
                source_type=SourceType.MANUAL,
                label=f"Competitor: {comp_name}",
                confidence_label="—",
                notes="Listed in asset configuration; no signal-level monitoring linked.",
            ))
    else:
        gaps.append(
            "No competitor assets listed — competitive landscape lacks structured evidence. "
            "Populate asset.competitor_assets or link KnowledgeArtifact competitor_landscape records."
        )

    if asset.differentiation_notes:
        refs.append(MemoEvidenceRef(
            source_type=SourceType.MANUAL,
            label=(
                f"Differentiation: {asset.differentiation_notes[:120]}"
                f"{'…' if len(asset.differentiation_notes) > 120 else ''}"
            ),
            confidence_label="—",
            notes="Analyst commentary from asset configuration.",
        ))
    else:
        gaps.append(
            "Differentiation narrative is blank — no analyst note distinguishes this asset "
            "from the listed competitors."
        )

    # KnowledgeArtifact competitor_landscape wiring
    landscape_artifacts = [
        a for a in output.knowledge_artifacts
        if getattr(a, "artifact_type", None) == "competitor_landscape"
    ]
    for art in landscape_artifacts:
        title = getattr(art, "title", "Competitor landscape analysis")
        art_id = getattr(art, "id", None)
        signal_count = len(getattr(art, "source_signal_ids", []))
        refs.append(MemoEvidenceRef(
            source_type=SourceType.KNOWLEDGE_ART,
            source_id=art_id,
            label=f"Landscape: {title}",
            confidence_label=_artifact_confidence_label(art),
            confidence_score=getattr(art, "confidence", None),
            as_of_date=_artifact_as_of(art),
            notes=(
                f"Backed by {signal_count} signal(s). "
                f"Author: {art.created_by}"
                if getattr(art, "created_by", None) else
                f"Backed by {signal_count} signal(s)."
            ),
        ))

    if not landscape_artifacts:
        gaps.append(
            "No KnowledgeArtifact competitor_landscape records linked. "
            "Competitor trial readouts (competitor_event signals) and head-to-head data "
            "are unverified. Populate output.knowledge_artifacts to close this gap."
        )

    return MemoSectionEvidence(section_key="competitive", refs=refs, unsupported_claims=gaps)


def _build_assumptions(output: "ValuationOutput") -> MemoSectionEvidence:
    refs: list[MemoEvidenceRef] = []
    gaps: list[str] = []

    if output.assumption_log:
        for ka in output.assumption_log.to_flat_list():
            refs.append(MemoEvidenceRef(
                source_type=SourceType.ASSUMPTION,
                label=f"{ka.parameter}: {ka.value}{' ' + ka.units if ka.units else ''}",
                url=ka.url,
                confidence_label=_conf(ka.confidence),
                notes=ka.source or None,
            ))
    else:
        gaps.append(
            "No AssumptionLog attached to this ValuationOutput. All valuation inputs "
            "are unverified estimates with no documented source or confidence."
        )

    # Analyst overrides (provenance of any manual changes)
    for override_str in output.analyst_overrides:
        refs.append(MemoEvidenceRef(
            source_type=SourceType.MANUAL,
            label=f"Override: {override_str}",
            confidence_label="High",
            notes="Explicitly set by analyst; deviates from industry default.",
        ))

    return MemoSectionEvidence(section_key="assumptions", refs=refs, unsupported_claims=gaps)


def _build_comps(output: "ValuationOutput") -> MemoSectionEvidence:
    refs: list[MemoEvidenceRef] = []
    gaps: list[str] = []

    comps = output.comps_fair_value_band
    if comps is None or comps.match_tier == "no_comps":
        gaps.append(
            "No comparable deal analysis available for this run. "
            "Supply comparable_deals to ValuationEngine or add deals to "
            "research/mna/comparable_deals.yaml."
        )
        return MemoSectionEvidence(section_key="comps", refs=refs, unsupported_claims=gaps)

    # Summary evidence ref for the matched comp set
    refs.append(MemoEvidenceRef(
        source_type=SourceType.DEAL_COMP,
        label=(
            f"Matched {comps.n_comps} comparable deal(s) "
            f"via '{comps.match_tier.replace('_', ' ')}' tier; "
            f"peer median EV/peak-sales: "
            f"{comps.peer_median_ev_to_peak_sales:.2f}x"
            if comps.peer_median_ev_to_peak_sales else
            f"Matched {comps.n_comps} comparable deal(s)"
        ),
        confidence_label=(
            "High" if comps.n_hq_comps >= 5
            else "Medium" if comps.n_hq_comps >= 2
            else "Low"
        ),
        notes=(
            f"Match tier: {comps.match_tier}. "
            f"High-quality comps (SEC/press-release verified): {comps.n_hq_comps}."
        ),
    ))

    # Individual matched deal refs (deal_date not available from ComparableDealAnalysis aggregate)
    for target_name in comps.matched_targets:
        refs.append(MemoEvidenceRef(
            source_type=SourceType.DEAL_COMP,
            label=f"Deal comp: {target_name}",
            confidence_label="—",
            notes="From research/mna/comparable_deals.yaml",
        ))

    if comps.match_tier == "phase_only":
        gaps.append(
            "Comp set matched on phase only (not indication or therapeutic area). "
            "Cross-indication comp multiples may not reflect indication-specific risk. "
            "Add indication-matched deals to improve comp quality."
        )
    if comps.n_hq_comps < 3:
        gaps.append(
            f"Only {comps.n_hq_comps} high-quality (SEC-disclosed) comp(s) available. "
            "Quantile ranges have low statistical power. Add SEC-proxy deals for robustness."
        )

    return MemoSectionEvidence(section_key="comps", refs=refs, unsupported_claims=gaps)


def _build_falsification(output: "ValuationOutput") -> MemoSectionEvidence:
    refs: list[MemoEvidenceRef] = []
    gaps: list[str] = []

    # Kill criteria from DecisionFraming
    if output.decision_framing and output.decision_framing.kill_criteria:
        for i, kc in enumerate(output.decision_framing.kill_criteria, 1):
            refs.append(MemoEvidenceRef(
                source_type=SourceType.MANUAL,
                label=f"Kill criterion {i}: {kc}",
                confidence_label="High",
                notes="Analyst-defined falsification condition from DecisionFraming.",
            ))
    else:
        gaps.append(
            "No analyst-defined kill criteria in DecisionFraming. "
            "Populate decision_framing.kill_criteria to make falsification conditions explicit."
        )

    # Thesis changers from AssumptionLog
    if output.assumption_log and output.assumption_log.thesis_changers:
        for i, tc in enumerate(output.assumption_log.thesis_changers, 1):
            refs.append(MemoEvidenceRef(
                source_type=SourceType.ASSUMPTION,
                label=f"Thesis changer {i}: {tc}",
                confidence_label="Medium",
                notes="From AssumptionLog.thesis_changers.",
            ))

    # Comps-based falsification ref
    comps = output.comps_fair_value_band
    if comps and comps.match_tier != "no_comps" and comps.peer_median_ev_to_peak_sales:
        refs.append(MemoEvidenceRef(
            source_type=SourceType.DEAL_COMP,
            label=(
                f"Comp-based floor: peer median EV/peak-sales = "
                f"{comps.peer_median_ev_to_peak_sales:.2f}x across {comps.n_comps} deals. "
                f"A deal at ≤P25 ({comps.peer_min_ev_to_peak_sales:.2f}x) "
                "would imply significantly below-median terms."
            ),
            confidence_label=(
                "High" if comps.n_hq_comps >= 5
                else "Medium" if comps.n_hq_comps >= 2
                else "Low"
            ),
            notes="Derived from ComparableDealAnalysis.",
        ))
    else:
        gaps.append(
            "No comparable deal data to anchor deal-level falsification conditions. "
            "Qualitative analyst judgment only — add comps for quantitative deal floor anchoring."
        )

    # POS falsification anchor
    if output.assumption_log:
        combined_pos = output.rnpv.cumulative_success_probability
        refs.append(MemoEvidenceRef(
            source_type=SourceType.ASSUMPTION,
            label=(
                f"Approval probability: {combined_pos:.0%} — "
                f"a Phase failure probability of {(1-combined_pos):.0%} would invalidate the base case."
            ),
            confidence_label=_conf(output.assumption_log.pos_methodology.confidence),
            notes="Derived from cumulative phase-level POS in rNPV model.",
        ))

    return MemoSectionEvidence(section_key="falsification", refs=refs, unsupported_claims=gaps)


# ── Public entry point ────────────────────────────────────────────────────────

class MemoEvidenceBuilder:
    """
    Builds a MemoEvidence bundle from a ValuationOutput.

    Call ``MemoEvidenceBuilder.build(output)`` immediately after running
    the valuation engine, before rendering the memo template.

    Signals and knowledge_artifacts fields on ValuationOutput are optional.
    When populated, they enrich biology, trial, and competitive sections with
    source-backed refs including as_of_date from the underlying record timestamps.
    """

    @staticmethod
    def build(output: "ValuationOutput") -> MemoEvidence:
        """
        Construct section evidence from all structured fields on *output*.

        Never raises. Any field access error defaults to a gap annotation.
        """
        sections = {}
        builders = {
            "biology": _build_biology,
            "trial": _build_trial,
            "competitive": _build_competitive,
            "assumptions": _build_assumptions,
            "comps": _build_comps,
            "falsification": _build_falsification,
        }
        for key, fn in builders.items():
            try:
                sections[key] = fn(output)
            except Exception as exc:  # noqa: BLE001
                sections[key] = MemoSectionEvidence(
                    section_key=key,
                    unsupported_claims=[
                        f"Evidence builder error for section '{key}': {exc}. "
                        "Check ValuationOutput completeness."
                    ],
                )

        return MemoEvidence(**sections)
