"""
Thesis and KnowledgeArtifact schemas — the persistent "memory" of the
intelligence platform.

``Thesis`` encapsulates an analyst's investment thesis for a single asset:
variant perception, probability estimate, kill criteria, and catalyst calendar.
Theses are versioned; when updated, the old version is archived and
``superseded_by_id`` points forward to the new version.

``KnowledgeArtifact`` is the general-purpose container for any processed
intelligence output: competitor landscapes, payer intelligence summaries,
regulatory precedent memos, trial design critiques, etc.  Artifacts carry
full provenance (source signals, valuation runs, and the generating model).

Examples
--------
>>> from datetime import datetime, timezone
>>> from bve.intelligence.schemas.knowledge import Thesis, KnowledgeArtifact
>>>
>>> thesis = Thesis(
...     id="thesis-dupilumab-v1",
...     asset_id="asset-dupilumab-001",
...     company_id="company-regn-001",
...     variant_perception=(
...         "Market prices dupilumab as a single-indication AD drug. "
...         "We model three label expansions (asthma, CRSwNP, EoE) that "
...         "expand TAM by 60% and are not reflected in consensus."
...     ),
...     our_pos_estimate=0.82,
...     consensus_pos_estimate=0.70,
...     peak_sales_estimate_millions=4500.0,
...     kill_criteria=[
...         "SOLO-1 IGA 0/1 < 25% (well below observed 38%)",
...         "FDA issues safety-related clinical hold prior to approval",
...         "Competitor biologic approved in AD with superior efficacy profile",
...     ],
...     created_at=datetime.now(timezone.utc),
...     updated_at=datetime.now(timezone.utc),
...     status="active",
... )
>>>
>>> artifact = KnowledgeArtifact(
...     id="artifact-001",
...     artifact_type="competitor_landscape",
...     asset_id="asset-dupilumab-001",
...     company_id="company-regn-001",
...     title="IL-4/IL-13 Competitor Landscape — Atopic Dermatitis 2016",
...     content_markdown="## Competitive Landscape\\n\\nNo approved biologics for AD...",
...     created_at=datetime.now(timezone.utc),
...     updated_at=datetime.now(timezone.utc),
...     created_by="analyst-dj",
... )
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Thesis(BaseModel):
    """
    An investment thesis for a single drug asset.

    Theses are versioned: when an analyst updates a thesis, they create a new
    ``Thesis`` record, set its ``status="active"``, and update the old record's
    ``superseded_by_id`` to point to the new one.  The version chain is
    traversable forward (``superseded_by_id``) but not backward (no ``parent_id``
    stored — look it up by query).

    Attributes
    ----------
    id:
        Unique thesis identifier (UUIDv4).
    asset_id:
        Foreign key → ``IntelligenceAsset.id``.
    company_id:
        Foreign key → ``IntelligenceCompany.id``.
    variant_perception:
        1–3 sentence statement of where this thesis diverges from market
        consensus and why that divergence is exploitable.
    our_pos_estimate:
        Analyst's probability of approval (0.0–1.0).
    consensus_pos_estimate:
        Market-implied probability of approval, back-solved from current
        price and net cash (cf. ``ValuationOutput.implied_pos``).
    peak_sales_estimate_millions:
        Analyst's peak net sales estimate in USD millions.
    kill_criteria:
        Ordered list of specific data outcomes that would terminate the thesis.
        Each entry should be a falsifiable, measurable statement.
    catalyst_calendar:
        List of upcoming events expected to be material.  Each entry is a dict
        with keys: ``date`` (ISO string), ``description``, ``expected_impact``
        (``"positive"`` | ``"negative"`` | ``"uncertain"``).
    created_at:
        UTC timestamp of thesis creation.
    updated_at:
        UTC timestamp of last modification.
    version:
        Monotonically increasing version counter (starts at 1).
    superseded_by_id:
        Foreign key → the newer ``Thesis.id`` that replaced this one.
        None if this is the current active version.
    status:
        Lifecycle state: ``"draft"``, ``"active"``, or ``"archived"``.
    """

    id:                        str
    asset_id:                  str
    company_id:                str
    variant_perception:        Optional[str]        = None
    our_pos_estimate:          Optional[float]      = Field(default=None, ge=0.0, le=1.0)
    consensus_pos_estimate:    Optional[float]      = Field(default=None, ge=0.0, le=1.0)
    peak_sales_estimate_millions: Optional[float]   = Field(default=None, ge=0.0)
    kill_criteria:             list[str]            = Field(default_factory=list)
    catalyst_calendar:         list[dict[str, Any]] = Field(default_factory=list)
    created_at:                datetime
    updated_at:                datetime
    version:                   int                  = Field(default=1, ge=1)
    superseded_by_id:          Optional[str]        = None
    status:                    Literal[
        "draft", "active", "archived"
    ]                                               = "draft"

    model_config = {"frozen": True}


#: Valid artifact types for :class:`KnowledgeArtifact`.
ArtifactType = Literal[
    "thesis",
    "signal_summary",
    "competitor_landscape",
    "payer_intelligence",
    "regulatory_precedent",
    "trial_design_critique",
]


class KnowledgeArtifact(BaseModel):
    """
    A processed intelligence output with full provenance tracking.

    Knowledge artifacts are the durable outputs produced by analysts or LLMs
    working with the intelligence platform.  They carry explicit provenance
    (which signals, runs, and thesis they derive from) so that every claim
    in the artifact can be traced to a primary source.

    Attributes
    ----------
    id:
        Unique artifact identifier (UUIDv4).
    artifact_type:
        Controlled vocabulary for the artifact category.
    asset_id:
        Foreign key → ``IntelligenceAsset.id``.  None for company-level
        artifacts (e.g. an enterprise risk landscape).
    company_id:
        Foreign key → ``IntelligenceCompany.id``.  None for class-level
        artifacts that span multiple companies.
    title:
        Short, descriptive title for display and search.
    content_markdown:
        Full artifact text in Markdown format.
    source_signal_ids:
        Foreign keys → ``StructuredSignal.id`` — the signals this artifact
        draws from.  Provides the provenance chain back to primary sources.
    source_run_ids:
        Foreign keys → ``ValuationRun.id`` — runs whose outputs informed
        this artifact.
    thesis_id:
        Foreign key → ``Thesis.id`` when the artifact derives from or
        supports a specific thesis.
    created_at:
        UTC timestamp of artifact creation.
    updated_at:
        UTC timestamp of last modification.
    created_by:
        Identifier of the analyst or model that created the artifact.
        LLM entries use the format ``"llm:<model_name>"``, e.g.
        ``"llm:gpt-4o-2024-11-20"``.
    confidence:
        Overall confidence in the artifact's conclusions (0.0–1.0).
        Analyst-assigned for manual artifacts; model-assigned for LLM outputs.
    tags:
        Free-form labels for filtering and aggregation.
    """

    id:                 str
    artifact_type:      ArtifactType
    asset_id:           Optional[str]        = None
    company_id:         Optional[str]        = None
    title:              str
    content_markdown:   str
    source_signal_ids:  list[str]            = Field(default_factory=list)
    source_run_ids:     list[str]            = Field(default_factory=list)
    thesis_id:          Optional[str]        = None
    created_at:         datetime
    updated_at:         datetime
    created_by:         Optional[str]        = None
    confidence:         float                = Field(default=0.5, ge=0.0, le=1.0)
    tags:               list[str]            = Field(default_factory=list)

    model_config = {"frozen": True}
