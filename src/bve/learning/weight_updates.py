"""Weight update engine — proposes and tracks parameter changes requiring human review."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel


class WeightUpdate(BaseModel):
    """A proposed change to a model parameter, requiring human approval."""

    update_id: str
    module: str
    parameter_name: str
    old_value: float
    new_value: float
    delta: float
    rationale: str
    created_at: datetime
    requires_human_review: bool = True
    approved: bool = False


class WeightUpdateEngine:
    """Tracks proposed parameter changes and manages the approval workflow.

    All updates are held in-memory. Proposed updates start with approved=False
    and require explicit approval via approve().
    """

    def __init__(self) -> None:
        self._updates: list[WeightUpdate] = []

    def propose_update(
        self,
        module: str,
        parameter_name: str,
        old_value: float,
        new_value: float,
        rationale: str,
    ) -> WeightUpdate:
        """Propose a new parameter update and store it pending approval."""
        update = WeightUpdate(
            update_id=str(uuid4()),
            module=module,
            parameter_name=parameter_name,
            old_value=old_value,
            new_value=new_value,
            delta=new_value - old_value,
            rationale=rationale,
            created_at=datetime.now(timezone.utc),
            requires_human_review=True,
            approved=False,
        )
        self._updates.append(update)
        return update

    def pending_updates(self) -> list[WeightUpdate]:
        """Return all updates that have not yet been approved."""
        return [u for u in self._updates if not u.approved]

    def approve(self, update_id: str) -> WeightUpdate:
        """Mark an update as approved.

        Returns the updated record.
        Raises ValueError if the update_id is not found.
        """
        for i, u in enumerate(self._updates):
            if u.update_id == update_id:
                approved = u.model_copy(update={"approved": True})
                self._updates[i] = approved
                return approved
        raise ValueError(f"No update found with update_id='{update_id}'")
