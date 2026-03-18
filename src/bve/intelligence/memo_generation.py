"""
Weekly memo generation for intelligence workflows.

This module is deterministic and grounded in provided records only.
It provides:
  - prompt construction (for optional LLM summarization workflows)
  - deterministic markdown memo generation with record citations
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field

from bve.intelligence.knowledge_layer import (
    DossierRecord,
    MemoRecord,
    SourceTrace,
    StoredValuationDiff,
)
from bve.intelligence.schemas.runs import ReviewDecision
from bve.intelligence.schemas.signals import StructuredSignal


_CITATION_PATTERN = re.compile(r"\[[a-z_]+:[^\]]+\]")

_SYSTEM_PROMPT = """\
You are a biotech valuation memo writer.

Rules:
1. Use only supplied records. Do not invent claims.
2. Every factual bullet must include at least one record citation.
3. If evidence is ambiguous or unresolved, state it explicitly.
4. Keep memo concise and structured.
5. If evidence is missing for a section, say that directly.
"""


class WeeklyMemoInput(BaseModel):
    """Structured input context for one weekly memo."""

    dossier: DossierRecord
    structured_events: list[StructuredSignal] = Field(default_factory=list)
    valuation_diffs: list[StoredValuationDiff] = Field(default_factory=list)
    review_decisions: list[ReviewDecision] = Field(default_factory=list)
    ambiguous_signal_ids: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WeeklyMemoOutput(BaseModel):
    """Generated weekly memo with explicit citation metadata."""

    id: str
    title: str
    asset_id: Optional[str] = None
    company_id: Optional[str] = None
    generated_at: datetime
    period_start: date
    period_end: date
    week_ending: date
    content_markdown: str
    cited_signal_ids: list[str] = Field(default_factory=list)
    cited_run_ids: list[str] = Field(default_factory=list)
    cited_review_ids: list[str] = Field(default_factory=list)
    cited_event_ids: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    def to_memo_record(self, source_trace: SourceTrace) -> MemoRecord:
        """Convert output into a knowledge-layer memo record."""
        return MemoRecord(
            id=self.id,
            company_id=self.company_id,
            asset_id=self.asset_id,
            title=self.title,
            memo_type="weekly_asset_memo",
            content_markdown=self.content_markdown,
            created_at=self.generated_at,
            period_start=self.period_start,
            period_end=self.period_end,
            source_signal_ids=self.cited_signal_ids,
            source_run_ids=self.cited_run_ids,
            referenced_event_ids=self.cited_event_ids,
            referenced_diff_ids=self.cited_run_ids,
            referenced_review_ids=self.cited_review_ids,
            open_questions=self.open_questions,
            source_trace=source_trace,
        )


class WeeklyMemoPromptBuilder:
    """Builds a strict grounding prompt for optional memo LLM workflows."""

    CURRENT_VERSION = "v1.0"

    def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_user_prompt(self, memo_input: WeeklyMemoInput) -> str:
        compact = {
            "dossier": {
                "id": memo_input.dossier.id,
                "company_id": memo_input.dossier.company_id,
                "asset_id": memo_input.dossier.asset_id,
                "generated_at": memo_input.dossier.generated_at.isoformat(),
                "open_questions": memo_input.dossier.open_questions,
            },
            "structured_events": [
                {
                    "id": s.id,
                    "event_id": s.event_id,
                    "event_type": s.event_type.value,
                    "signal_date": s.signal_date.isoformat(),
                    "trial_phase": s.trial_phase.value if s.trial_phase is not None else None,
                    "primary_endpoint_met": s.primary_endpoint_met,
                    "extraction_confidence": s.extraction_confidence,
                }
                for s in _sorted_events(memo_input.structured_events)
            ],
            "valuation_diffs": [
                {
                    "run_id": d.run_id,
                    "event_id": d.event_id,
                    "asset_id": d.asset_id,
                    "delta_npv": d.delta_npv,
                    "assumptions_changed": d.assumptions_changed,
                }
                for d in _sorted_diffs(memo_input.valuation_diffs)
            ],
            "review_decisions": [
                {
                    "id": r.id,
                    "run_id": r.run_id,
                    "decision": r.decision,
                    "reviewed_at": r.reviewed_at.isoformat(),
                    "rationale": r.rationale,
                }
                for r in _sorted_reviews(memo_input.review_decisions)
            ],
            "ambiguous_signal_ids": sorted(set(memo_input.ambiguous_signal_ids)),
        }

        return (
            "Write a short weekly memo with the following sections exactly:\n"
            "## Key Events\n"
            "## Valuation Changes\n"
            "## Why It Changed\n"
            "## Uncertainties\n"
            "## Needs Review Next\n"
            "## Sources\n\n"
            "Constraint: every factual bullet must include citations like "
            "[signal:<id>] [event:<id>] [diff:<run_id>] [review:<id>].\n"
            "Constraint: no invented claims.\n\n"
            f"INPUT_JSON:\n{json.dumps(compact, ensure_ascii=True, indent=2)}"
        )


class WeeklyMemoGenerator:
    """Deterministic weekly memo generator grounded in structured records."""

    def __init__(
        self,
        *,
        max_events: int = 5,
        max_diffs: int = 5,
        low_confidence_threshold: float = 0.80,
    ) -> None:
        self.max_events = max_events
        self.max_diffs = max_diffs
        self.low_confidence_threshold = low_confidence_threshold

    def generate(
        self,
        memo_input: WeeklyMemoInput,
        *,
        memo_id: Optional[str] = None,
        week_ending: Optional[date] = None,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
    ) -> WeeklyMemoOutput:
        week_ending = week_ending or memo_input.generated_at.date()
        period_end = period_end or week_ending
        period_start = period_start or (period_end - timedelta(days=6))
        memo_id = memo_id or str(uuid.uuid4())

        cited_signals: set[str] = set()
        cited_runs: set[str] = set()
        cited_reviews: set[str] = set()
        cited_events: set[str] = set()
        open_questions: list[str] = []

        key_events = self._key_events_section(
            memo_input,
            cited_signals,
            cited_events,
        )
        valuation_changes = self._valuation_changes_section(
            memo_input,
            cited_runs,
            cited_events,
        )
        self._assert_valuation_section_has_diff_refs(
            memo_input=memo_input,
            valuation_section=valuation_changes,
            cited_runs=cited_runs,
        )
        why_changed = self._why_changed_section(memo_input, cited_runs)
        uncertainties, unresolved = self._uncertainties_section(
            memo_input,
            cited_signals,
            cited_reviews,
            cited_events,
            cited_runs,
        )
        open_questions.extend(unresolved)
        needs_review = self._needs_review_section(
            memo_input,
            cited_reviews,
            cited_runs,
            cited_signals,
        )

        sources = self._sources_section(
            dossier_id=memo_input.dossier.id,
            signal_ids=sorted(cited_signals),
            event_ids=sorted(cited_events),
            run_ids=sorted(cited_runs),
            review_ids=sorted(cited_reviews),
        )

        title = (
            f"Weekly Memo — {memo_input.dossier.asset_id or 'asset'} — "
            f"week ending {week_ending.isoformat()}"
        )
        body = "\n\n".join([
            f"# {title}",
            key_events,
            valuation_changes,
            why_changed,
            uncertainties,
            needs_review,
            sources,
        ])

        self._assert_all_bullets_cited(body)

        return WeeklyMemoOutput(
            id=memo_id,
            title=title,
            asset_id=memo_input.dossier.asset_id,
            company_id=memo_input.dossier.company_id,
            generated_at=memo_input.generated_at,
            period_start=period_start,
            period_end=period_end,
            week_ending=week_ending,
            content_markdown=body,
            cited_signal_ids=sorted(cited_signals),
            cited_run_ids=sorted(cited_runs),
            cited_review_ids=sorted(cited_reviews),
            cited_event_ids=sorted(cited_events),
            open_questions=open_questions,
        )

    def _key_events_section(
        self,
        memo_input: WeeklyMemoInput,
        cited_signals: set[str],
        cited_events: set[str],
    ) -> str:
        lines = ["## Key Events"]
        events = _sorted_events(memo_input.structured_events)[: self.max_events]
        if not events:
            lines.append(f"- No structured events recorded this week. [dossier:{memo_input.dossier.id}]")
            return "\n".join(lines)

        ambiguous_ids = set(memo_input.ambiguous_signal_ids)
        for signal in events:
            cited_signals.add(signal.id)
            cited_events.add(signal.event_id)
            details: list[str] = [f"event_type={signal.event_type.value}"]
            if signal.trial_phase is not None:
                details.append(f"trial_phase={signal.trial_phase.value}")
            if signal.primary_endpoint_met is not None:
                details.append(f"primary_endpoint_met={signal.primary_endpoint_met}")
            details.append(f"confidence={signal.extraction_confidence:.2f}")
            if signal.id in ambiguous_ids:
                details.append("ambiguity=flagged")

            lines.append(
                "- "
                f"{signal.signal_date.isoformat()}: {', '.join(details)} "
                f"[signal:{signal.id}] [event:{signal.event_id}]"
            )
        return "\n".join(lines)

    def _valuation_changes_section(
        self,
        memo_input: WeeklyMemoInput,
        cited_runs: set[str],
        cited_events: set[str],
    ) -> str:
        lines = ["## Valuation Changes"]
        diffs = _sorted_diffs(memo_input.valuation_diffs)[: self.max_diffs]
        if not diffs:
            lines.append(f"- No valuation diff records for the week. [dossier:{memo_input.dossier.id}]")
            return "\n".join(lines)

        for diff in diffs:
            cited_runs.add(diff.run_id)
            cited_events.add(diff.event_id)
            lines.append(
                f"- run={diff.run_id}: delta_npv={diff.delta_npv:+.2f}. "
                f"[diff:{diff.run_id}] [event:{diff.event_id}]"
            )
        return "\n".join(lines)

    def _why_changed_section(
        self,
        memo_input: WeeklyMemoInput,
        cited_runs: set[str],
    ) -> str:
        lines = ["## Why It Changed"]
        diffs = _sorted_diffs(memo_input.valuation_diffs)[: self.max_diffs]
        if not diffs:
            lines.append(f"- No assumption-level drivers were recorded. [dossier:{memo_input.dossier.id}]")
            return "\n".join(lines)

        for diff in diffs:
            cited_runs.add(diff.run_id)
            changes = diff.assumptions_changed or []
            if not changes:
                lines.append(
                    f"- run={diff.run_id}: valuation changed without assumption detail in record. "
                    f"[diff:{diff.run_id}]"
                )
                continue
            top = changes[:3]
            drivers: list[str] = []
            for change in top:
                field = change.get("field", "unknown_field")
                old_value = change.get("old_value")
                new_value = change.get("new_value")
                drivers.append(f"{field}: {old_value} -> {new_value}")
            lines.append(
                f"- run={diff.run_id}: key drivers: {'; '.join(drivers)}. [diff:{diff.run_id}]"
            )
        return "\n".join(lines)

    def _uncertainties_section(
        self,
        memo_input: WeeklyMemoInput,
        cited_signals: set[str],
        cited_reviews: set[str],
        cited_events: set[str],
        cited_runs: set[str],
    ) -> tuple[str, list[str]]:
        lines = ["## Uncertainties"]
        unresolved: list[str] = []

        ambiguous_ids = set(memo_input.ambiguous_signal_ids)
        for signal in _sorted_events(memo_input.structured_events):
            is_ambiguous = signal.id in ambiguous_ids
            low_conf = signal.extraction_confidence < self.low_confidence_threshold
            if not is_ambiguous and not low_conf:
                continue
            cited_signals.add(signal.id)
            cited_events.add(signal.event_id)
            note_parts = []
            if is_ambiguous:
                note_parts.append("ambiguity flagged")
            if low_conf:
                note_parts.append(
                    f"low extraction confidence ({signal.extraction_confidence:.2f})"
                )
            note = ", ".join(note_parts)
            lines.append(
                f"- signal={signal.id}: {note}. [signal:{signal.id}] [event:{signal.event_id}]"
            )
            unresolved.append(f"Clarify signal {signal.id}: {note}")

        for decision in _sorted_reviews(memo_input.review_decisions):
            if decision.decision != "deferred":
                continue
            cited_reviews.add(decision.id)
            if decision.run_id:
                cited_runs.add(decision.run_id)
            lines.append(
                f"- deferred review {decision.id}: {decision.rationale}. "
                f"[review:{decision.id}]"
                + (f" [diff:{decision.run_id}]" if decision.run_id else "")
            )
            unresolved.append(f"Resolve deferred review {decision.id}")

        for q in memo_input.dossier.open_questions:
            lines.append(f"- open question: {q}. [dossier:{memo_input.dossier.id}]")
            unresolved.append(q)

        if len(lines) == 1:
            lines.append(f"- No explicit unresolved issues captured. [dossier:{memo_input.dossier.id}]")

        return "\n".join(lines), _dedupe_keep_order(unresolved)

    def _needs_review_section(
        self,
        memo_input: WeeklyMemoInput,
        cited_reviews: set[str],
        cited_runs: set[str],
        cited_signals: set[str],
    ) -> str:
        lines = ["## Needs Review Next"]

        deferred = [d for d in _sorted_reviews(memo_input.review_decisions) if d.decision == "deferred"]
        for decision in deferred:
            cited_reviews.add(decision.id)
            if decision.run_id:
                cited_runs.add(decision.run_id)
            lines.append(
                f"- Complete deferred decision {decision.id}. [review:{decision.id}]"
                + (f" [diff:{decision.run_id}]" if decision.run_id else "")
            )

        low_conf = [
            s for s in _sorted_events(memo_input.structured_events)
            if s.extraction_confidence < self.low_confidence_threshold
        ]
        for signal in low_conf:
            cited_signals.add(signal.id)
            lines.append(
                f"- Validate low-confidence signal {signal.id}. [signal:{signal.id}]"
            )

        if len(lines) == 1:
            lines.append(f"- No pending review actions identified. [dossier:{memo_input.dossier.id}]")
        return "\n".join(lines)

    @staticmethod
    def _sources_section(
        *,
        dossier_id: str,
        signal_ids: list[str],
        event_ids: list[str],
        run_ids: list[str],
        review_ids: list[str],
    ) -> str:
        lines = ["## Sources"]
        lines.append(f"- dossier: {dossier_id} [dossier:{dossier_id}]")
        for event_id in event_ids:
            lines.append(f"- event: {event_id} [event:{event_id}]")
        for signal_id in signal_ids:
            lines.append(f"- signal: {signal_id} [signal:{signal_id}]")
        for run_id in run_ids:
            lines.append(f"- valuation_diff: {run_id} [diff:{run_id}]")
        for review_id in review_ids:
            lines.append(f"- review_decision: {review_id} [review:{review_id}]")
        return "\n".join(lines)

    @staticmethod
    def _assert_all_bullets_cited(content_markdown: str) -> None:
        lines = content_markdown.splitlines()
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith("- "):
                continue
            if _CITATION_PATTERN.search(stripped) is None:
                raise ValueError(f"Bullet line missing citation: {line}")

    @staticmethod
    def _assert_valuation_section_has_diff_refs(
        *,
        memo_input: WeeklyMemoInput,
        valuation_section: str,
        cited_runs: set[str],
    ) -> None:
        if not memo_input.valuation_diffs:
            return

        provided_ids = {d.run_id for d in memo_input.valuation_diffs}
        cited_in_section = set(re.findall(r"\[diff:([^\]]+)\]", valuation_section))
        if not cited_in_section.intersection(provided_ids):
            raise ValueError(
                "valuation_diffs were provided but no diff ID citation appeared in "
                "the valuation section"
            )
        if not cited_runs.intersection(provided_ids):
            raise ValueError(
                "valuation_diffs were provided but no run ID was structurally captured"
            )



def _sorted_events(events: list[StructuredSignal]) -> list[StructuredSignal]:
    return sorted(
        events,
        key=lambda x: (
            x.signal_date,
            x.created_at,
            x.id,
        ),
        reverse=True,
    )



def _sorted_diffs(diffs: list[StoredValuationDiff]) -> list[StoredValuationDiff]:
    return sorted(
        diffs,
        key=lambda x: (
            x.created_at,
            x.run_id,
        ),
        reverse=True,
    )



def _sorted_reviews(decisions: list[ReviewDecision]) -> list[ReviewDecision]:
    return sorted(
        decisions,
        key=lambda x: (
            x.reviewed_at,
            x.id,
        ),
        reverse=True,
    )



def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output
