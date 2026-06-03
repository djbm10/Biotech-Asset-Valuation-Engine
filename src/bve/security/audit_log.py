"""Audit log — records who viewed, changed, and exported model outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass
class AuditEvent:
    """A single auditable action."""

    event_id: str
    user_id: str
    user_role: str
    action: Literal[
        "view_valuation",
        "edit_assumption",
        "approve_assumption",
        "export_memo",
        "run_calibration",
        "view_trade_recommendation",
        "view_acquirer_profile",
        "login",
        "logout",
    ]
    resource_id: str | None = None
    resource_type: str | None = None
    detail: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    success: bool = True

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "user_id": self.user_id,
            "user_role": self.user_role,
            "action": self.action,
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "detail": self.detail,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
        }


class AuditLog:
    """In-memory audit log. Back with a database in production."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"evt-{self._counter:06d}"

    def record(
        self,
        user_id: str,
        user_role: str,
        action: str,
        resource_id: str | None = None,
        resource_type: str | None = None,
        detail: dict | None = None,
        success: bool = True,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=self._next_id(),
            user_id=user_id,
            user_role=user_role,
            action=action,
            resource_id=resource_id,
            resource_type=resource_type,
            detail=detail,
            success=success,
        )
        self._events.append(event)
        return event

    def query(
        self,
        user_id: str | None = None,
        action: str | None = None,
        resource_id: str | None = None,
        since: datetime | None = None,
    ) -> list[AuditEvent]:
        results = self._events
        if user_id:
            results = [e for e in results if e.user_id == user_id]
        if action:
            results = [e for e in results if e.action == action]
        if resource_id:
            results = [e for e in results if e.resource_id == resource_id]
        if since:
            results = [e for e in results if e.timestamp >= since]
        return results

    def all_events(self) -> list[AuditEvent]:
        return list(self._events)

    def export_jsonl(self) -> str:
        import json
        return "\n".join(json.dumps(e.to_dict()) for e in self._events)
