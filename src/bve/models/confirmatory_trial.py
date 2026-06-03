"""
ConfirmatoryTrialObligation — post-approval study commitment model.

Represents a confirmatory trial required as a condition of accelerated
approval (FDA Accelerated Approval Pathway) or conditional marketing
authorization (EMA).

Design
------
This is a tracking/audit model with NO direct effect on cost or revenue
computation.  Its purpose is to:
  1. Make the obligation visible on DrugAssetProgram (inspectable before run()).
  2. Emit a UserWarning when status is WITHDRAWN_FAILED, signalling that the
     program has a material regulatory risk event that the analyst should
     explicitly model (e.g. by lowering success_probability or adjusting POS).
  3. Enable downstream intelligence and memo layers to surface the obligation
     status in BD / VC memos.

Status semantics
----------------
PENDING          Obligation exists; confirmatory trial not yet started.
ACTIVE           Trial ongoing; FDA/EMA monitoring progress.
MET              Trial succeeded; obligation fulfilled; no further risk.
WITHDRAWN_FAILED Trial failed or sponsor withdrew; major regulatory risk.
                 ValuationEngine emits UserWarning when this status is set.

Attachment
----------
ConfirmatoryTrialObligation is an optional field on DrugAssetProgram.
When None (default), the program has no known confirmatory obligation.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ConfirmatoryTrialStatus(str, Enum):
    """Status of a post-approval confirmatory trial obligation."""
    PENDING = "pending"                  # Obligation exists; trial not yet started
    ACTIVE = "active"                    # Trial ongoing
    MET = "met"                          # Obligation fulfilled; trial succeeded
    WITHDRAWN_FAILED = "withdrawn_failed"  # Trial withdrawn or failed — high risk


class ConfirmatoryTrialObligation(BaseModel):
    """
    Post-approval confirmatory study commitment.

    Frozen — use model_copy(update=...) to derive updated instances.

    Parameters
    ----------
    status          : Current status of the obligation (required).
    description     : Human-readable description of the required study.
    required_by_date: ISO date string (YYYY-MM-DD) by which FDA/EMA requires
                      the trial to be complete. None if not yet specified.
    nct_id          : ClinicalTrials.gov identifier of the confirmatory trial,
                      if it has been registered.
    notes           : Analyst notes on regulatory context or risk.
    """
    model_config = ConfigDict(frozen=True)

    status: ConfirmatoryTrialStatus = Field(
        description="Current status of the confirmatory trial obligation.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Human-readable description of the required confirmatory study.",
    )
    required_by_date: Optional[str] = Field(
        default=None,
        description="ISO date (YYYY-MM-DD) by which the obligation must be met.",
    )
    nct_id: Optional[str] = Field(
        default=None,
        description="ClinicalTrials.gov identifier of the confirmatory trial.",
    )
    notes: Optional[str] = None

    # -- Convenience properties -----------------------------------------------

    @property
    def is_resolved(self) -> bool:
        """True when the obligation has reached a terminal state (MET or WITHDRAWN_FAILED)."""
        return self.status in (ConfirmatoryTrialStatus.MET,
                               ConfirmatoryTrialStatus.WITHDRAWN_FAILED)

    @property
    def is_at_risk(self) -> bool:
        """True when the obligation represents an active regulatory risk (WITHDRAWN_FAILED)."""
        return self.status == ConfirmatoryTrialStatus.WITHDRAWN_FAILED
