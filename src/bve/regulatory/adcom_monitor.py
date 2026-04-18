"""Track FDA advisory committee meetings: upcoming dates, agendas, and outcomes."""
from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class AdcomMeeting(BaseModel):
    meeting_id: str
    committee_name: str         # e.g. "Oncologic Drugs Advisory Committee"
    drug_name: str
    indication: str
    company: Optional[str] = None
    meeting_date: date
    briefing_doc_available: bool = False
    briefing_doc_date: Optional[date] = None
    agenda_published: bool = False
    status: str = "scheduled"   # "scheduled" / "held" / "cancelled" / "postponed"
    vote: Optional[str] = None  # e.g. "11-2 in favor"
    recommendation: Optional[str] = None   # "approve" / "reject" / "split"
    key_concerns: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
    source_url: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AdcomMonitor:
    """Track and query FDA advisory committee meeting calendar."""

    def __init__(self) -> None:
        self._meetings: dict[str, AdcomMeeting] = {}

    def add(self, meeting: AdcomMeeting) -> None:
        self._meetings[meeting.meeting_id] = meeting

    def update(self, meeting_id: str, **kwargs) -> Optional[AdcomMeeting]:
        if meeting_id not in self._meetings:
            return None
        existing = self._meetings[meeting_id]
        updated = existing.model_copy(update={**kwargs, "updated_at": datetime.now(timezone.utc)})
        self._meetings[meeting_id] = updated
        return updated

    def get(self, meeting_id: str) -> Optional[AdcomMeeting]:
        return self._meetings.get(meeting_id)

    def upcoming(self, as_of: Optional[date] = None) -> list[AdcomMeeting]:
        ref = as_of or date.today()
        return sorted(
            [m for m in self._meetings.values() if m.meeting_date >= ref and m.status == "scheduled"],
            key=lambda m: m.meeting_date,
        )

    def held(self) -> list[AdcomMeeting]:
        return sorted(
            [m for m in self._meetings.values() if m.status == "held"],
            key=lambda m: m.meeting_date, reverse=True,
        )

    def for_drug(self, drug_name: str) -> list[AdcomMeeting]:
        return [m for m in self._meetings.values() if drug_name.lower() in m.drug_name.lower()]

    def days_to_next_meeting(self, drug_name: str, as_of: Optional[date] = None) -> Optional[int]:
        ref = as_of or date.today()
        upcoming = [m for m in self.for_drug(drug_name) if m.meeting_date >= ref]
        if not upcoming:
            return None
        next_m = min(upcoming, key=lambda m: m.meeting_date)
        return (next_m.meeting_date - ref).days

    def all_meetings(self) -> list[AdcomMeeting]:
        return list(self._meetings.values())
