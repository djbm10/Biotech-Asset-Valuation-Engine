"""
ValuationRun and ReviewDecision schemas.

``ValuationRun`` captures the audit trail of one intelligence-triggered
valuation cycle: what parameter overrides were applied, who triggered it,
and what the rNPV delta was.

``ReviewDecision`` records a human reviewer's verdict on a single
``AssumptionChangeProposal``.  A proposal must be reviewed (accepted,
rejected, or deferred) before a ``ValuationRun`` is created.

Design notes
------------
- ``ValuationRun.parameter_overrides`` is a flat ``dict[str, float]``.  By
  the time a run is created, proposals have been reviewed and resolved to
  specific numeric values.  Storing them as a flat dict allows a future
  service to call ``model.model_copy(update=...)`` without re-interpreting
  proposal logic.
- ``ValuationRun.valuation_output_json_path`` stores the path to the
  serialized ``ValuationOutput`` JSON on disk.  The full object is not
  embedded here to keep this schema lightweight.
- ``ReviewDecision.run_id`` is ``None`` for rejected decisions (no run is
  produced when all proposals are rejected).

Examples
--------
>>> from datetime import datetime, timezone
>>> from bve.intelligence.schemas.runs import ValuationRun, ReviewDecision
>>>
>>> run = ValuationRun(
...     id="run-001",
...     engine_asset_id="dupilumab-ad",
...     triggered_by_signal_id="sig-001",
...     triggered_by_proposal_ids=["prop-001"],
...     parameter_overrides={"trials[nda_bla].success_probability": 0.60},
...     rnpv_millions_before=3200.0,
...     rnpv_millions_after=3731.0,
...     run_at=datetime.now(timezone.utc),
...     status="completed",
... )
>>> run.delta_rnpv_millions
531.0

>>> decision = ReviewDecision(
...     id="dec-001",
...     proposal_id="prop-001",
...     decision="accepted",
...     reviewer_id="analyst-dj",
...     reviewed_at=datetime.now(timezone.utc),
...     rationale="Ph3 topline clear; IGA 0/1 and EASI-75 both met. POS step-up justified.",
... )
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field


class ValuationRun(BaseModel):
    """
    Audit record for one intelligence-triggered valuation run.

    Attributes
    ----------
    id:
        Unique run identifier (UUIDv4).
    engine_asset_id:
        Foreign key → ``bve.entities.asset.Asset.id`` (the engine asset being
        re-valued).
    triggered_by_signal_id:
        Foreign key → ``StructuredSignal.id`` that initiated the run.
        None when the run is manually triggered by an analyst.
    triggered_by_proposal_ids:
        Foreign keys → ``AssumptionChangeProposal.id`` — the accepted proposals
        whose overrides are applied in this run.
    parameter_overrides:
        Flat map of engine parameter path → accepted new value.  Derived from
        accepted ``AssumptionChangeProposal`` records after review.
        Example: ``{"trials[nda_bla].success_probability": 0.60}``.
    valuation_output_json_path:
        File path of the serialized ``ValuationOutput`` JSON produced by this
        run.  None while the run is pending or if the run failed.
    rnpv_millions_before:
        rNPV from the previous run (baseline for delta calculation).
    rnpv_millions_after:
        rNPV produced by this run.
    delta_rnpv_millions:
        Computed: ``rnpv_millions_after - rnpv_millions_before``.  None when
        either input is missing.
    run_at:
        UTC timestamp of run execution.
    analyst_id:
        Identifier of the analyst who triggered or confirmed the run.
    notes:
        Free-text notes attached to this run.
    status:
        Lifecycle state of the run.
    """

    id:                         str
    engine_asset_id:            str
    triggered_by_signal_id:     Optional[str]        = None
    triggered_by_proposal_ids:  list[str]            = Field(default_factory=list)
    parameter_overrides:        dict[str, float]     = Field(default_factory=dict)
    valuation_output_json_path: Optional[str]        = None
    rnpv_millions_before:       Optional[float]      = None
    rnpv_millions_after:        Optional[float]      = None
    run_at:                     datetime
    analyst_id:                 Optional[str]        = None
    notes:                      Optional[str]        = None
    status:                     Literal[
        "pending", "running", "completed", "failed"
    ]                                                = "pending"

    @computed_field  # type: ignore[misc]
    @property
    def delta_rnpv_millions(self) -> Optional[float]:
        """rNPV change produced by this run, or None if either value is missing."""
        if self.rnpv_millions_before is not None and self.rnpv_millions_after is not None:
            return round(self.rnpv_millions_after - self.rnpv_millions_before, 2)
        return None

    model_config = {"frozen": True}


class ReviewDecision(BaseModel):
    """
    Human reviewer verdict on a single ``AssumptionChangeProposal``.

    Attributes
    ----------
    id:
        Unique decision identifier (UUIDv4).
    proposal_id:
        Foreign key → ``AssumptionChangeProposal.id`` being reviewed.
    run_id:
        Foreign key → ``ValuationRun.id`` produced by this decision.
        None when the decision is ``"rejected"`` or ``"deferred"``
        (no run is created).
    decision:
        Reviewer verdict:
        - ``"accepted"`` — proposal applied as-is (or with ``override_value``).
        - ``"rejected"`` — proposal dismissed; no change to model.
        - ``"deferred"`` — review postponed pending additional information.
    reviewer_id:
        Identifier of the human reviewer.
    reviewed_at:
        UTC timestamp of the decision.
    override_value:
        Reviewer-specified value that overrides ``proposal.proposed_value``.
        None when the reviewer accepts the proposal as-is or rejects it.
    rationale:
        Mandatory human-readable explanation of the decision.
    notes:
        Optional supplementary notes (e.g. questions to follow up on).
    reviewer_confidence:
        Reviewer's self-reported confidence in their decision (0.0–1.0).
        Used to weight ``"accepted"`` decisions in calibration scoring:
        high-confidence approvals are weighted more heavily.  None when the
        reviewer does not provide a confidence estimate.
    analyst_tags:
        Free-form classification tags applied by the analyst (e.g.
        ``["interim_only", "high_quality_data", "small_sample"]``).
        Used for downstream filtering and cohort analysis.
    supporting_quote:
        Verbatim excerpt from the source document that informed the decision.
        Supports reproducibility and future audit queries.
    """

    id:                   str
    proposal_id:          str
    run_id:               Optional[str]              = None
    decision:             Literal["accepted", "rejected", "deferred"]
    reviewer_id:          str
    reviewed_at:          datetime
    override_value:       Optional[float]            = None
    rationale:            str
    notes:                Optional[str]              = None
    reviewer_confidence:  Optional[float]            = Field(default=None, ge=0.0, le=1.0)
    analyst_tags:         list[str]                  = Field(default_factory=list)
    supporting_quote:     Optional[str]              = None

    model_config = {"frozen": True}
