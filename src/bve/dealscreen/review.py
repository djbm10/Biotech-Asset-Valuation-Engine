"""Analyst decision log: append-only, hash-chained, attributable.

Every analyst action is one JSON line with reviewer, timestamp, the old and new state of
its subject, and a rationale. Each line carries the hash of the previous line, so an edit
or deletion anywhere breaks verification on the next load. Decisions are never rewritten:
a change of mind is a new record whose ``old_state`` is the previous decision.

Machine recommendations (rank, CANDIDATE_FOR_ANALYST_REVIEW) live in the screening output
and are never written here. A finalist exists only because a record here says so.

``reviewer_kind`` separates a person from the labelled synthetic fixture used by the
automated demo, so a demo approval can never be presented as a real analyst approval.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from bve.dealscreen.facts import ReviewInputs
from bve.dealscreen.models import AgentFinding

GENESIS = "0" * 64


class Action(str, Enum):
    CONFIRM_CLAIM = "CONFIRM_CLAIM"
    REJECT_CLAIM = "REJECT_CLAIM"
    CONFIRM_FINDING = "CONFIRM_FINDING"
    REJECT_FINDING = "REJECT_FINDING"
    REQUEST_DILIGENCE = "REQUEST_DILIGENCE"
    RESOLVE_IDENTITY_FLAG = "RESOLVE_IDENTITY_FLAG"
    APPROVE_FINALIST = "APPROVE_FINALIST"
    WITHDRAW_FINALIST = "WITHDRAW_FINALIST"
    SELECT_FOR_VALUATION = "SELECT_FOR_VALUATION"
    DESELECT_FOR_VALUATION = "DESELECT_FOR_VALUATION"


class ReviewerKind(str, Enum):
    HUMAN = "HUMAN"
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"


class DecisionRejected(ValueError):
    """The action is not allowed in the current state; nothing was written."""


class LogTampered(RuntimeError):
    """The decision log no longer verifies against its hash chain."""


@dataclass
class ReviewState:
    claims: dict[str, str] = field(default_factory=dict)  # claim_id -> CONFIRMED/REJECTED
    findings: dict[str, str] = field(default_factory=dict)  # finding_id -> CONFIRMED/REJECTED
    diligence_requests: dict[str, list[str]] = field(default_factory=dict)  # asset -> questions
    identity_flags: dict[str, str] = field(default_factory=dict)  # flag -> resolution
    finalists: dict[str, dict[str, Any]] = field(default_factory=dict)  # asset -> approval record
    valuation_selected: dict[str, dict[str, Any]] = field(default_factory=dict)

    def subject_state(self, action: Action, subject_id: str) -> str:
        if action in (Action.CONFIRM_CLAIM, Action.REJECT_CLAIM):
            return self.claims.get(subject_id, "UNREVIEWED")
        if action in (Action.CONFIRM_FINDING, Action.REJECT_FINDING):
            return self.findings.get(subject_id, "PROPOSED")
        if action is Action.RESOLVE_IDENTITY_FLAG:
            return self.identity_flags.get(subject_id, "OPEN")
        if action is Action.REQUEST_DILIGENCE:
            return f"{len(self.diligence_requests.get(subject_id, []))} open requests"
        if action in (Action.APPROVE_FINALIST, Action.WITHDRAW_FINALIST):
            return self.finalists.get(subject_id, {}).get("state", "NOT_A_FINALIST")
        return "SELECTED" if subject_id in self.valuation_selected else "NOT_SELECTED"

    def review_inputs(self, findings: list[AgentFinding]) -> ReviewInputs:
        confirmed = {f for f, s in self.findings.items() if s == "CONFIRMED"}
        return ReviewInputs(
            rejected_claim_ids=frozenset(c for c, s in self.claims.items() if s == "REJECTED"),
            confirmed_claim_ids=frozenset(c for c, s in self.claims.items() if s == "CONFIRMED"),
            confirmed_findings=tuple(f for f in findings if f.finding_id in confirmed),
        )


def _hash(record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def _apply(state: ReviewState, record: dict[str, Any]) -> None:
    action = Action(record["action"])
    subject = record["subject_id"]
    new = record["new_state"]
    if action in (Action.CONFIRM_CLAIM, Action.REJECT_CLAIM):
        state.claims[subject] = new
    elif action in (Action.CONFIRM_FINDING, Action.REJECT_FINDING):
        state.findings[subject] = new
    elif action is Action.REQUEST_DILIGENCE:
        state.diligence_requests.setdefault(subject, []).append(record["detail"].get("question", ""))
    elif action is Action.RESOLVE_IDENTITY_FLAG:
        state.identity_flags[subject] = new
    elif action is Action.APPROVE_FINALIST:
        state.finalists[subject] = {"state": new, **_who(record)}
    elif action is Action.WITHDRAW_FINALIST:
        state.finalists.pop(subject, None)
        state.valuation_selected.pop(subject, None)
    elif action is Action.SELECT_FOR_VALUATION:
        state.valuation_selected[subject] = {"state": new, **_who(record)}
    elif action is Action.DESELECT_FOR_VALUATION:
        state.valuation_selected.pop(subject, None)


def _who(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision_id": record["decision_id"],
        "reviewer_id": record["reviewer_id"],
        "reviewer_kind": record["reviewer_kind"],
        "timestamp": record["timestamp"],
        "rationale": record["rationale"],
    }


class DecisionLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.records: list[dict[str, Any]] = []
        self.state = ReviewState()
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        previous = GENESIS
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("prev_hash") != previous or _hash(record) != record.get("hash"):
                raise LogTampered(f"{self.path}: decision {line_number} fails hash-chain verification")
            _apply(self.state, record)
            self.records.append(record)
            previous = record["hash"]

    @property
    def head(self) -> str:
        return self.records[-1]["hash"] if self.records else GENESIS

    def record(
        self,
        *,
        action: Action,
        subject_id: str,
        new_state: str,
        reviewer_id: str,
        rationale: str,
        reviewer_kind: ReviewerKind = ReviewerKind.HUMAN,
        detail: dict[str, Any] | None = None,
        context: DecisionContext | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        if not reviewer_id.strip():
            raise DecisionRejected("a decision needs a reviewer identifier")
        if not rationale.strip():
            raise DecisionRejected("a decision needs a rationale")
        if context is not None:
            context.check(action, subject_id, self.state, new_state)
        record = {
            "decision_id": f"dec:{len(self.records) + 1:05d}",
            "seq": len(self.records) + 1,
            "timestamp": timestamp or datetime.now(UTC).isoformat(timespec="seconds"),
            "reviewer_id": reviewer_id,
            "reviewer_kind": reviewer_kind.value,
            "action": action.value,
            "subject_id": subject_id,
            "old_state": self.state.subject_state(action, subject_id),
            "new_state": new_state,
            "rationale": rationale,
            "detail": detail or {},
            "prev_hash": self.head,
        }
        record["hash"] = _hash(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        _apply(self.state, record)
        self.records.append(record)
        return record


@dataclass
class DecisionContext:
    """What a decision is checked against before it is written."""

    dispositions: dict[str, str]  # asset_id -> ELIGIBLE / UNRESOLVED / EXCLUDED
    claim_ids: set[str]
    finding_ids: set[str]
    flag_ids: set[str]
    max_finalists: int = 10
    max_valuations: int = 3

    def check(
        self, action: Action, subject_id: str, state: ReviewState, new_state: str = ""
    ) -> None:
        if action in (Action.CONFIRM_CLAIM, Action.REJECT_CLAIM) and subject_id not in self.claim_ids:
            raise DecisionRejected(f"unknown claim {subject_id!r}")
        if action in (Action.CONFIRM_FINDING, Action.REJECT_FINDING) and subject_id not in self.finding_ids:
            raise DecisionRejected(f"unknown agent finding {subject_id!r}")
        if action is Action.RESOLVE_IDENTITY_FLAG and subject_id not in self.flag_ids:
            raise DecisionRejected(f"unknown identity flag {subject_id!r}")
        if action in (Action.REQUEST_DILIGENCE, Action.APPROVE_FINALIST, Action.SELECT_FOR_VALUATION) \
                and subject_id not in self.dispositions:
            raise DecisionRejected(f"unknown asset {subject_id!r}")
        if action is Action.APPROVE_FINALIST:
            disposition = self.dispositions[subject_id]
            if disposition == "EXCLUDED":
                raise DecisionRejected(
                    "an EXCLUDED asset failed a hard scientific requirement and cannot be a "
                    "finalist; correct the underlying claim first if the exclusion is wrong"
                )
            expected = "APPROVED" if disposition == "ELIGIBLE" else "APPROVED_WITH_OPEN_QUESTIONS"
            if new_state != expected:
                raise DecisionRejected(
                    f"a {disposition} asset is approved with new_state {expected!r}; open "
                    "scientific questions must be acknowledged explicitly"
                )
            if subject_id in state.finalists:
                raise DecisionRejected("already an approved finalist")
            if len(state.finalists) >= self.max_finalists:
                raise DecisionRejected(f"the shortlist is limited to {self.max_finalists} finalists")
        if action is Action.WITHDRAW_FINALIST and subject_id not in state.finalists:
            raise DecisionRejected("not a finalist")
        if action is Action.SELECT_FOR_VALUATION:
            if subject_id not in state.finalists:
                raise DecisionRejected("only an analyst-approved finalist can be selected for valuation")
            if subject_id in state.valuation_selected:
                raise DecisionRejected("already selected for valuation")
            if len(state.valuation_selected) >= self.max_valuations:
                raise DecisionRejected(f"at most {self.max_valuations} assets can be valued")
        if action is Action.DESELECT_FOR_VALUATION and subject_id not in state.valuation_selected:
            raise DecisionRejected("not selected for valuation")
