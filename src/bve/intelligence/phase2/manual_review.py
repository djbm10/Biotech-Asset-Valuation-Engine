"""
Manual review workflow for Phase 2 assumption changes.

This module provides a lightweight, auditable review process with:
  - review case persistence (JSON per case)
  - append-only action log (JSONL)
  - explicit status transitions
  - human-readable case rendering for terminal workflows
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from bve.intelligence.extraction.result import ExtractionResult
from bve.intelligence.phase2.valuation_integration import ValuationDiffLog
from bve.intelligence.schemas.proposals import AssumptionChangeProposal

ReviewStatus = Literal["pending", "approved", "rejected", "modified"]
ReviewActionType = Literal["approve", "reject", "modify"]


class SourceDocumentMetadata(BaseModel):
    """Minimal source-document metadata shown during manual review."""

    document_id: str
    source: str
    title: str
    source_url: Optional[str] = None
    published_at: Optional[str] = None
    retrieved_at: Optional[str] = None


class ManualReviewAction(BaseModel):
    """Immutable action record for one reviewer decision."""

    id: str
    case_id: str
    action: ReviewActionType
    reviewer_id: str
    rationale: str
    override_value: Optional[float] = None
    action_at: datetime
    previous_status: ReviewStatus
    next_status: ReviewStatus
    provenance: dict[str, str] = Field(default_factory=dict)


class ManualReviewCase(BaseModel):
    """Single review unit joining extraction, mapping, and valuation diff context."""

    id: str
    created_at: datetime
    source_document: SourceDocumentMetadata
    extraction_result: ExtractionResult
    proposal: AssumptionChangeProposal
    valuation_diff: ValuationDiffLog
    status: ReviewStatus = "pending"
    latest_override_value: Optional[float] = None
    actions: list[ManualReviewAction] = Field(default_factory=list)


class ManualReviewStore:
    """File-backed review store with append-only action logging."""

    def __init__(self, root_dir: str | Path = "outputs/intelligence_phase2/reviews") -> None:
        self.root_dir = Path(root_dir)
        self.cases_dir = self.root_dir / "cases"
        self.actions_log_path = self.root_dir / "actions.jsonl"
        self.cases_dir.mkdir(parents=True, exist_ok=True)
        self.actions_log_path.parent.mkdir(parents=True, exist_ok=True)

    def case_path(self, case_id: str) -> Path:
        return self.cases_dir / f"{case_id}.json"

    def create_case(
        self,
        *,
        case_id: str,
        source_document: SourceDocumentMetadata,
        extraction_result: ExtractionResult,
        proposal: AssumptionChangeProposal,
        valuation_diff: ValuationDiffLog,
        created_at: Optional[datetime] = None,
    ) -> ManualReviewCase:
        created_at = created_at or datetime.now(timezone.utc)
        case = ManualReviewCase(
            id=case_id,
            created_at=created_at,
            source_document=source_document,
            extraction_result=extraction_result,
            proposal=proposal,
            valuation_diff=valuation_diff,
            status="pending",
        )
        self.save_case(case)
        return case

    def save_case(self, case: ManualReviewCase) -> None:
        path = self.case_path(case.id)
        path.write_text(case.model_dump_json(indent=2), encoding="utf-8")

    def load_case(self, case_id: str) -> ManualReviewCase:
        path = self.case_path(case_id)
        if not path.exists():
            raise FileNotFoundError(f"Review case not found: {path}")
        return ManualReviewCase.model_validate_json(path.read_text(encoding="utf-8"))

    def list_cases(self, *, status: Optional[ReviewStatus] = None) -> list[ManualReviewCase]:
        cases: list[ManualReviewCase] = []
        for path in sorted(self.cases_dir.glob("*.json")):
            case = ManualReviewCase.model_validate_json(path.read_text(encoding="utf-8"))
            if status is None or case.status == status:
                cases.append(case)
        return cases

    def record_action(
        self,
        *,
        case_id: str,
        action: ReviewActionType,
        reviewer_id: str,
        rationale: str,
        override_value: Optional[float] = None,
        provenance: Optional[dict[str, str]] = None,
        action_at: Optional[datetime] = None,
    ) -> ManualReviewAction:
        action_at = action_at or datetime.now(timezone.utc)
        case = self.load_case(case_id)
        previous = case.status
        next_status = self._next_status(previous, action)

        if action == "modify" and override_value is None:
            raise ValueError("modify action requires override_value")
        if action in {"approve", "reject"} and override_value is not None:
            # Allow approve with override only if it effectively behaves as modify+approve.
            raise ValueError("override_value is only allowed for modify action")

        record = ManualReviewAction(
            id=str(uuid.uuid4()),
            case_id=case_id,
            action=action,
            reviewer_id=reviewer_id,
            rationale=rationale,
            override_value=override_value,
            action_at=action_at,
            previous_status=previous,
            next_status=next_status,
            provenance=provenance or {},
        )

        updated = case.model_copy(
            update={
                "status": next_status,
                "latest_override_value": (
                    override_value if action == "modify" else case.latest_override_value
                ),
                "actions": [*case.actions, record],
            }
        )
        self.save_case(updated)
        self._append_action_log(record)
        return record

    def _append_action_log(self, action: ManualReviewAction) -> None:
        with self.actions_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(action.model_dump(mode="json"), ensure_ascii=True) + "\n")

    @staticmethod
    def _next_status(current: ReviewStatus, action: ReviewActionType) -> ReviewStatus:
        transitions: dict[ReviewStatus, dict[ReviewActionType, ReviewStatus]] = {
            "pending": {"approve": "approved", "reject": "rejected", "modify": "modified"},
            "modified": {"approve": "approved", "reject": "rejected", "modify": "modified"},
            "approved": {},
            "rejected": {},
        }
        allowed = transitions.get(current, {})
        if action not in allowed:
            raise ValueError(f"Invalid transition: status={current!r}, action={action!r}")
        return allowed[action]


def render_case(case: ManualReviewCase) -> str:
    """Render a review case for terminal inspection."""
    er = case.extraction_result
    proposal = case.proposal
    diff = case.valuation_diff

    extracted_json = er.raw_llm_json or (
        er.signal.model_dump(mode="json") if er.signal is not None else {}
    )

    lines = [
        f"Review Case: {case.id}",
        f"Status: {case.status}",
        "",
        "Source Document Metadata:",
        f"- document_id: {case.source_document.document_id}",
        f"- source: {case.source_document.source}",
        f"- title: {case.source_document.title}",
        f"- source_url: {case.source_document.source_url}",
        f"- published_at: {case.source_document.published_at}",
        f"- retrieved_at: {case.source_document.retrieved_at}",
        "",
        "Extracted Event JSON:",
        json.dumps(extracted_json, indent=2, ensure_ascii=True),
        "",
        "Extraction Quality:",
        f"- confidence_score: {er.extraction_confidence:.4f}",
        f"- ambiguity_flag: {er.ambiguity_flag}",
        f"- rationale: {er.rationale}",
        "",
        "Mapping Proposal:",
        f"- proposal_id: {proposal.id}",
        f"- parameter_path: {proposal.parameter_path}",
        f"- current_value: {proposal.current_value}",
        f"- proposed_value: {proposal.proposed_value}",
        f"- proposed_delta_pct: {proposal.proposed_delta_pct}",
        f"- change_mode: {proposal.change_mode.value}",
        "",
        "Valuation Before/After Diff:",
        f"- event_id: {diff.event_id}",
        f"- asset_id: {diff.asset_id}",
        f"- delta_npv: {diff.delta_npv}",
        f"- valuation_before.rnpv_millions: {diff.valuation_before.rnpv_millions}",
        f"- valuation_after.rnpv_millions: {diff.valuation_after.rnpv_millions}",
        "- assumptions_changed:",
    ]
    for row in diff.assumptions_changed:
        lines.append(
            f"  - {row.field}: {row.old_value} -> {row.new_value} (delta={row.delta}, delta_pct={row.delta_pct})"
        )

    lines += [
        "",
        "Reviewer Actions:",
    ]
    if not case.actions:
        lines.append("- (none)")
    else:
        for act in case.actions:
            lines.append(
                f"- {act.action_at.isoformat()} | {act.reviewer_id} | {act.action} | "
                f"{act.previous_status}->{act.next_status} | override={act.override_value} | "
                f"rationale={act.rationale}"
            )

    return "\n".join(lines)
