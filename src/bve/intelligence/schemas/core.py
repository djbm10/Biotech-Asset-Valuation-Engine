"""
Intelligence-layer entity schemas: Company, Asset, Indication.

These are distinct from the frozen engine entities in bve.entities.*  The engine
entities model exactly what the rNPV pipeline needs.  These intelligence schemas
model what an ingestion pipeline, analyst workflow, or LLM reasoning layer needs:
source provenance, monitoring metadata, and loose foreign-key links back to engine
objects (via ``engine_*_id`` string references, resolved at query time — not by
inheritance).

Import direction
----------------
These schemas import from the frozen engine (``bve.entities.asset``) to reuse
enums that are already authoritative there.  The frozen engine never imports from
this module.

Examples
--------
>>> from bve.intelligence.schemas.core import IntelligenceCompany, IntelligenceAsset
>>> from bve.entities.asset import TherapeuticArea, DevelopmentStage, Modality
>>> from datetime import datetime, timezone
>>>
>>> company = IntelligenceCompany(
...     id="company-regn-001",
...     name="Regeneron Pharmaceuticals",
...     ticker="REGN",
...     created_at=datetime.now(timezone.utc),
...     updated_at=datetime.now(timezone.utc),
... )
>>> asset = IntelligenceAsset(
...     id="asset-dupilumab-001",
...     name="dupilumab (DUPIXENT)",
...     company_id="company-regn-001",
...     therapeutic_area=TherapeuticArea.IMMUNOLOGY,
...     stage=DevelopmentStage.APPROVED,
...     modality=Modality.BIOLOGIC,
...     created_at=datetime.now(timezone.utc),
...     updated_at=datetime.now(timezone.utc),
... )
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# One-way import from the frozen engine (read-only — never modify these)
from bve.entities.asset import DevelopmentStage, Modality, TherapeuticArea


class IntelligenceCompany(BaseModel):
    """
    Intelligence-layer view of a biopharmaceutical company.

    Attributes
    ----------
    id:
        Unique identifier within the intelligence platform (UUIDv4 recommended).
    name:
        Full legal name.
    ticker:
        Exchange ticker (None for private companies).
    engine_company_id:
        Foreign key → ``bve.entities.company.Company.id``.  None when the
        company has not yet been linked to an engine model.
    sector:
        Broad sector label.  Defaults to ``"biotech"`` for this platform.
    monitoring_enabled:
        Whether the pipeline actively ingests events for this company.
    data_sources:
        List of source identifiers (e.g. ``["sec_edgar", "clinicaltrials_gov"]``).
    created_at:
        UTC timestamp of record creation.
    updated_at:
        UTC timestamp of last modification.
    notes:
        Free-text analyst notes.
    """

    id:                  str
    name:                str
    ticker:              Optional[str]        = None
    engine_company_id:   Optional[str]        = None
    sector:              str                  = "biotech"
    monitoring_enabled:  bool                 = True
    data_sources:        list[str]            = Field(default_factory=list)
    created_at:          datetime
    updated_at:          datetime
    notes:               Optional[str]        = None

    model_config = {"frozen": True}


class IntelligenceAsset(BaseModel):
    """
    Intelligence-layer view of a drug asset.

    Attributes
    ----------
    id:
        Unique identifier within the intelligence platform.
    name:
        Drug name (INN preferred; brand name in parentheses when approved).
    engine_asset_id:
        Foreign key → ``bve.entities.asset.Asset.id``.  None until linked.
    company_id:
        Foreign key → ``IntelligenceCompany.id``.
    indication_ids:
        Ordered list of foreign keys → ``IntelligenceIndication.id``.
    therapeutic_area:
        Reuses the frozen engine enum so taxonomy is consistent.
    stage:
        Current highest development stage.  Reuses the frozen engine enum.
    modality:
        Drug modality.  Reuses the frozen engine enum.
    monitoring_enabled:
        Whether the pipeline actively ingests events for this asset.
    created_at:
        UTC timestamp of record creation.
    updated_at:
        UTC timestamp of last modification.
    notes:
        Free-text analyst notes.

    Examples
    --------
    >>> asset.engine_asset_id  # may be None before engine linkage
    None
    >>> asset.indication_ids
    []
    """

    id:                 str
    name:               str
    engine_asset_id:    Optional[str]          = None
    company_id:         str
    indication_ids:     list[str]              = Field(default_factory=list)
    therapeutic_area:   TherapeuticArea
    stage:              DevelopmentStage
    modality:           Modality               = Modality.SMALL_MOLECULE
    monitoring_enabled: bool                   = True
    created_at:         datetime
    updated_at:         datetime
    notes:              Optional[str]           = None

    model_config = {"frozen": True}


class IntelligenceIndication(BaseModel):
    """
    Intelligence-layer view of a disease indication being tracked.

    One asset may target multiple indications (e.g. dupilumab: AD, asthma,
    CRSwNP, EoE).  Each indication is tracked separately so that lifecycle
    events (label expansions) can be attributed to the correct indication
    and propagated to the right ``LifecycleEvent`` in the engine model.

    Attributes
    ----------
    id:
        Unique identifier within the intelligence platform.
    name:
        Human-readable indication name, e.g. ``"Moderate-to-Severe Atopic Dermatitis"``.
    engine_indication_id:
        Foreign key → ``bve.entities.indication.Indication.id``.  None until linked.
    asset_id:
        Foreign key → ``IntelligenceAsset.id``.
    icd10_codes:
        One or more ICD-10-CM codes for the indication (for epidemiology data joins).
    line_of_therapy:
        Optional line (``"1L"``, ``"2L+"``, ``"any"``) for oncology indications.
    approval_status:
        ``"approved"``, ``"clinical"``, or ``"preclinical"``.
    created_at:
        UTC timestamp of record creation.
    updated_at:
        UTC timestamp of last modification.
    """

    id:                    str
    name:                  str
    engine_indication_id:  Optional[str]        = None
    asset_id:              str
    icd10_codes:           list[str]            = Field(default_factory=list)
    line_of_therapy:       Optional[str]        = None
    approval_status:       str                  = "clinical"
    created_at:            datetime
    updated_at:            datetime

    model_config = {"frozen": True}
