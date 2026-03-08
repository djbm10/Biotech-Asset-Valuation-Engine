"""
Event and StructuredSignal schemas for the intelligence ingestion layer.

``Event`` is the raw observed fact — minimal, sourced, timestamped.
``StructuredSignal`` is the parsed, enriched representation produced after
NLP/LLM extraction: typed clinical facts, regulatory metadata, and commercial
data extracted from the raw event text.

The two models have a 1:1 relationship (one Event → one StructuredSignal).
Not every Event produces a StructuredSignal immediately; extraction may be
queued or manual for complex events.

Import direction
----------------
Imports ``EventType`` from the intelligence taxonomy and ``TrialPhase`` from
the frozen engine (``bve.entities.trial``).  Neither frozen model is modified.

Examples
--------
>>> from datetime import date, datetime, timezone
>>> from bve.intelligence.taxonomy import EventType
>>> from bve.intelligence.schemas.signals import Event, StructuredSignal
>>> from bve.entities.trial import TrialPhase
>>>
>>> event = Event(
...     id="evt-001",
...     event_type=EventType.TRIAL_READOUT,
...     asset_id="asset-dupilumab-001",
...     company_id="company-regn-001",
...     observed_at=datetime(2017, 3, 28, 14, 0, tzinfo=timezone.utc),
...     ingested_at=datetime.now(timezone.utc),
...     source_type="press_release",
...     headline="Regeneron/Sanofi DUPIXENT® receives FDA approval for adults with moderate-to-severe atopic dermatitis",
...     confidence=0.99,
... )
>>>
>>> signal = StructuredSignal(
...     id="sig-001",
...     event_id="evt-001",
...     asset_id="asset-dupilumab-001",
...     company_id="company-regn-001",
...     event_type=EventType.TRIAL_READOUT,
...     signal_date=date(2017, 3, 28),
...     trial_phase=TrialPhase.NDA_BLA,
...     primary_endpoint_met=True,
...     fda_action_type="approval",
...     extraction_model="gpt-4o-2024-11-20",
...     extraction_confidence=0.97,
...     created_at=datetime.now(timezone.utc),
... )
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Taxonomy import (intelligence layer — no frozen engine models here except TrialPhase)
from bve.intelligence.taxonomy import EventType

# One-way import from the frozen engine: TrialPhase enum only
from bve.entities.trial import TrialPhase


#: Allowed values for Event.source_type.
SourceType = Literal[
    "press_release",
    "sec_filing",
    "clinicaltrials_gov",
    "conference_abstract",
    "publication",
    "fda_website",
    "news_aggregator",
    "manual",
]


class Event(BaseModel):
    """
    A raw observed fact in the biotech intelligence stream.

    Events are the atomic unit of ingestion.  They are created by data
    connectors (SEC EDGAR, ClinicalTrials.gov, PubMed, news feeds) or by
    human analysts entering a finding manually.

    Attributes
    ----------
    id:
        Unique event identifier (UUIDv4 recommended).
    event_type:
        Canonical event category from the intelligence taxonomy.
    asset_id:
        Foreign key → ``IntelligenceAsset.id``.
    company_id:
        Foreign key → ``IntelligenceCompany.id``.
    indication_id:
        Foreign key → ``IntelligenceIndication.id``.  None when the event
        is company-level (e.g. a financing) rather than indication-specific.
    observed_at:
        UTC timestamp when the event occurred in the real world.
    ingested_at:
        UTC timestamp when the pipeline ingested the event.
    source_url:
        Canonical URL of the primary source document.
    source_type:
        Controlled vocabulary for the source channel.
    headline:
        Single sentence description of the event (≤ 280 characters recommended).
    raw_text:
        Full source text.  May be large; stored separately in practice.
    confidence:
        Ingestion-layer confidence that this event is correctly classified,
        from 0.0 (no confidence) to 1.0 (certain).
    tags:
        Free-form labels for filtering and aggregation.
    """

    id:             str
    event_type:     EventType
    asset_id:       str
    company_id:     str
    indication_id:  Optional[str]    = None
    observed_at:    datetime
    ingested_at:    datetime
    source_url:     Optional[str]    = None
    source_type:    SourceType       = "manual"
    headline:       str
    raw_text:       Optional[str]    = None
    confidence:     float            = Field(default=1.0, ge=0.0, le=1.0)
    tags:           list[str]        = Field(default_factory=list)

    model_config = {"frozen": True}


class StructuredSignal(BaseModel):
    """
    Parsed, enriched representation extracted from a raw :class:`Event`.

    Produced by an NLP/LLM extraction pipeline or by manual analyst entry.
    Contains typed clinical, regulatory, and commercial facts that can be
    used to generate :class:`~bve.intelligence.schemas.proposals.AssumptionChangeProposal`
    records.

    Optional fields are typed per domain: clinical (``trial_*``, ``hazard_ratio``,
    etc.), regulatory (``fda_action_type``, ``designation_type``), and commercial
    (``deal_value_millions``, ``deal_type``, ``payer_name``).  A single signal
    populates only the fields relevant to its event type.

    Attributes
    ----------
    id:
        Unique signal identifier.
    event_id:
        Foreign key → ``Event.id`` (1:1 relationship).
    asset_id, company_id:
        Denormalized foreign keys for efficient querying.
    event_type:
        Copied from the parent Event for fast filtering.
    signal_date:
        Calendar date the signal refers to (may differ from ingestion date).
    trial_phase:
        Clinical trial phase the signal relates to.  Uses the frozen engine enum.
    trial_nct_id:
        ClinicalTrials.gov identifier for the trial referenced.
    primary_endpoint_met:
        True if the trial met its primary endpoint; False if not; None if unknown
        or if the event is not a trial readout.
    interim_flag:
        True when the data are from an interim (not final) analysis.
    hazard_ratio:
        HR for time-to-event endpoints (e.g. PFS HR = 0.72).
    p_value:
        P-value of the primary endpoint test.
    response_rate:
        Overall response rate as a decimal (e.g. 0.42 for 42% ORR).
    safety_grade:
        Maximum CTCAE grade of treatment-emergent adverse events observed.
    fda_action_type:
        Regulatory action: ``"approval"``, ``"crl"``, ``"hold"``, or ``"designation"``.
    designation_type:
        Specific designation granted or removed: ``"BTD"``, ``"FTD"``, ``"ODD"``,
        or ``"RMAT"``.
    deal_value_millions:
        Total deal value in USD millions (for partnership/licensing events).
    deal_type:
        Classification of the deal structure.
    payer_name:
        Name of the payer or PBM for payer coverage events.
    extraction_model:
        Name + version of the model used for extraction, e.g.
        ``"gpt-4o-2024-11-20"``; None for manual entries.
    extraction_confidence:
        Model confidence in the extracted facts (0.0–1.0).
    created_at:
        UTC timestamp of signal creation.
    """

    id:                     str
    event_id:               str
    asset_id:               str
    company_id:             str
    event_type:             EventType
    signal_date:            date

    # --- Clinical facts ---
    trial_phase:            Optional[TrialPhase]  = None
    trial_nct_id:           Optional[str]         = None
    primary_endpoint_met:   Optional[bool]        = None
    interim_flag:           bool                  = False
    hazard_ratio:           Optional[float]       = Field(default=None, gt=0.0)
    p_value:                Optional[float]       = Field(default=None, ge=0.0, le=1.0)
    response_rate:          Optional[float]       = Field(default=None, ge=0.0, le=1.0)
    safety_grade:           Optional[int]         = Field(default=None, ge=1, le=5)

    # --- Regulatory facts ---
    fda_action_type:        Optional[Literal[
        "approval", "crl", "hold", "hold_lifted", "designation"
    ]]                                            = None
    designation_type:       Optional[Literal[
        "BTD", "FTD", "ODD", "RMAT", "priority_review"
    ]]                                            = None

    # --- Commercial facts ---
    deal_value_millions:    Optional[float]       = Field(default=None, ge=0.0)
    deal_type:              Optional[str]         = None
    payer_name:             Optional[str]         = None

    # --- Provenance ---
    extraction_model:       Optional[str]         = None
    extraction_confidence:  float                 = Field(default=0.0, ge=0.0, le=1.0)
    created_at:             datetime

    model_config = {"frozen": True}
