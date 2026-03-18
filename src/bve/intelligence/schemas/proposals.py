"""
AssumptionChangeProposal schema — the bridge between intelligence signals and the
frozen valuation engine.

A proposal is an immutable data record describing a *recommended* change to one
scalar engine parameter.  It is **not** an instruction that executes directly:
applying a proposal to the frozen engine objects (via ``model_copy(update=...)``)
is the responsibility of a future service layer (Phase 1).

Phase 0 invariants
------------------
1. The schema stores ``parameter_path`` as a free string.  Phase 1 will parse
   and resolve it against the actual trial list (wildcard ``[*]`` → specific
   phase discriminator).
2. ``proposed_value`` is always a scalar ``float``.  Non-scalar parameters
   (``market_model.lifecycle_events``, ``market_model.competition_model``) are
   always ``ChangeMode.MANUAL`` and produce proposals only as flag records with
   ``proposed_value=0.0`` and a rationale directing the analyst to the YAML.
3. AUTO and BOUNDED proposals are validated at construction: the absolute
   percentage change must not exceed ``bound_pct``.
4. MANUAL proposals are exempt from bound validation (no bound applies).

Examples
--------
>>> from datetime import datetime, timezone
>>> from bve.intelligence.taxonomy import EventType, ChangeMode
>>> from bve.intelligence.schemas.proposals import AssumptionChangeProposal
>>>
>>> # AUTO proposal within bound — should construct cleanly
>>> prop = AssumptionChangeProposal(
...     id="prop-001",
...     signal_id="sig-001",
...     asset_id="asset-dupilumab-001",
...     engine_asset_id="dupilumab-ad",
...     parameter_path="trials[*].success_probability",
...     current_value=0.50,
...     proposed_value=0.60,
...     change_mode=ChangeMode.AUTO,
...     bound_pct=20.0,
...     event_type=EventType.TRIAL_READOUT,
...     rationale="Positive Ph3 topline; met IGA 0/1 and EASI-75 primary endpoints.",
...     created_at=datetime.now(timezone.utc),
... )
>>> round(prop.proposed_delta_pct, 1)
20.0

>>> # AUTO proposal outside bound — raises ValidationError
>>> import pytest
>>> with pytest.raises(Exception):
...     AssumptionChangeProposal(
...         id="prop-002",
...         signal_id="sig-001",
...         asset_id="asset-001",
...         engine_asset_id="asset-001",
...         parameter_path="trials[*].success_probability",
...         current_value=0.50,
...         proposed_value=0.70,   # +40% — exceeds 20% bound
...         change_mode=ChangeMode.AUTO,
...         bound_pct=20.0,
...         event_type=EventType.TRIAL_READOUT,
...         rationale="Exceeds bound — should be rejected.",
...         created_at=datetime.now(timezone.utc),
...     )
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field, model_validator

from bve.intelligence.taxonomy import ChangeMode, EventType


class AssumptionChangeProposal(BaseModel):
    """
    A proposed change to one scalar valuation engine parameter.

    Attributes
    ----------
    id:
        Unique proposal identifier (UUIDv4).
    signal_id:
        Foreign key → ``StructuredSignal.id`` that triggered this proposal.
    asset_id:
        Foreign key → ``IntelligenceAsset.id``.
    engine_asset_id:
        Foreign key → ``bve.entities.asset.Asset.id`` (the frozen engine asset).
    parameter_path:
        Dot-path of the parameter to modify.  Wildcard ``[*]`` means "any
        matching trial phase"; resolved at apply-time by the service layer.
        Must be a member of ``bve.intelligence.mapping.LEGAL_PARAMETER_PATHS``
        (validated in tests; not at construction to keep Phase 0 simple).
    current_value:
        Current value of the parameter in the active engine model.
    proposed_value:
        Recommended new value.
    proposed_delta_pct:
        Computed: ``(proposed_value - current_value) / |current_value| × 100``.
        Cached as a stored field for convenient bound validation and display.
        Protected from manual override by the model validator.
    change_mode:
        AUTO, BOUNDED, or MANUAL from the intelligence taxonomy.
    bound_pct:
        Maximum allowed absolute ``proposed_delta_pct`` for AUTO/BOUNDED modes.
        Must be None for MANUAL proposals.
    event_type:
        The event category that triggered this proposal.
    rationale:
        Human-readable explanation of why this change is recommended.
    supporting_signal_ids:
        Additional corroborating signal IDs beyond the primary ``signal_id``.
    created_at:
        UTC timestamp of proposal creation.
    expires_at:
        Optional expiry timestamp — stale proposals auto-expire if not reviewed.
    status:
        Lifecycle state of the proposal.
    """

    id:                     str
    signal_id:              str
    asset_id:               str
    engine_asset_id:        str
    parameter_path:         str
    current_value:          float
    proposed_value:         float
    change_mode:            ChangeMode
    bound_pct:              Optional[float]  = Field(default=None, ge=0.0, le=100.0)
    event_type:             EventType
    rationale:              str
    supporting_signal_ids:  list[str]        = Field(default_factory=list)
    created_at:             datetime
    expires_at:             Optional[datetime] = None
    status:                 Literal[
        "pending", "accepted", "rejected", "expired"
    ]                                        = "pending"

    @computed_field  # type: ignore[misc]
    @property
    def proposed_delta_pct(self) -> float:
        """
        Percentage change from current to proposed value.

        Uses absolute value of current_value as denominator to handle the case
        where current_value is negative (discount_rate is always positive in
        practice, but this guard is defensive).
        """
        denom = abs(self.current_value) if self.current_value != 0.0 else 1.0
        return round((self.proposed_value - self.current_value) / denom * 100.0, 4)

    @model_validator(mode="after")
    def _validate_bound_and_mode_consistency(self) -> "AssumptionChangeProposal":
        """
        Enforce two invariants:

        1. AUTO and BOUNDED proposals must have ``bound_pct`` set.
        2. For AUTO and BOUNDED, ``|proposed_delta_pct|`` must not exceed
           ``bound_pct``.
        3. MANUAL proposals must have ``bound_pct=None``.
        """
        mode = self.change_mode

        if mode in (ChangeMode.AUTO, ChangeMode.BOUNDED):
            if self.bound_pct is None:
                raise ValueError(
                    f"AssumptionChangeProposal with change_mode={mode} requires "
                    f"bound_pct to be set."
                )
            if abs(self.proposed_delta_pct) > self.bound_pct + 1e-9:
                raise ValueError(
                    f"proposed_delta_pct={self.proposed_delta_pct:.2f}% exceeds "
                    f"bound_pct={self.bound_pct}% for change_mode={mode} "
                    f"(parameter: {self.parameter_path!r}). "
                    f"Reduce the proposed_value or use MANUAL mode."
                )

        elif mode == ChangeMode.MANUAL:
            if self.bound_pct is not None:
                raise ValueError(
                    f"AssumptionChangeProposal with change_mode=MANUAL must have "
                    f"bound_pct=None (got {self.bound_pct})."
                )

        return self

    model_config = {"frozen": True}
