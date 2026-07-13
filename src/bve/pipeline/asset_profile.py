"""Canonical per-ticker profile models for the auto-profile pipeline.

A ``CompanyProfile`` is the single structured profile per ticker that the
auto-config generator consumes. Every value-bearing fact is wrapped in a
``ProvenancedField`` so the field carries where it came from, when it was last
checked, and how confident we are in it.

Design notes
------------
- Lead-asset-first, multi-asset-ready: ``CompanyProfile.assets`` is a list; the
  MVP populates only ``assets[0]`` (the lead program) but the shape already
  supports the full pipeline.
- Public vs confidential: this model holds ONLY public facts. Confidential
  analyst inputs never live here — they are merged at runtime from a separate
  override file (see ``pipeline/config_resolver.py``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Confidence = Literal["low", "medium", "high"]
EvidenceLevel = Literal["coarse", "full", "not_assessed"]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProvenancedField(BaseModel):
    """A single profile value plus its provenance and freshness metadata."""

    value: Any = None
    source: str = "unset"
    source_url: Optional[str] = None
    source_date: Optional[str] = None  # ISO date the underlying fact is dated
    last_checked: str = Field(default_factory=_utcnow_iso)
    confidence: Confidence = "medium"
    stale: bool = False


def pf(
    value: Any,
    source: str,
    *,
    confidence: Confidence = "medium",
    source_url: Optional[str] = None,
    source_date: Optional[str] = None,
    stale: bool = False,
) -> ProvenancedField:
    """Convenience constructor for a populated ``ProvenancedField``."""
    return ProvenancedField(
        value=value,
        source=source,
        confidence=confidence,
        source_url=source_url,
        source_date=source_date,
        stale=stale,
    )


def _empty() -> ProvenancedField:
    """Default for an unpopulated field — value None, low confidence."""
    return ProvenancedField(value=None, source="unset", confidence="low")


class AssetProfile(BaseModel):
    """One drug program: identity, trial facts, and commercial economics.

    Every ``ProvenancedField`` defaults to an empty/low-confidence placeholder so
    callers can build a profile incrementally and only set what they actually have.
    """

    asset_id: str
    nct_id: Optional[str] = None

    # Identity facts
    drug_name: ProvenancedField = Field(default_factory=_empty)
    indication: ProvenancedField = Field(default_factory=_empty)
    therapeutic_area: ProvenancedField = Field(default_factory=_empty)
    stage: ProvenancedField = Field(default_factory=_empty)
    modality: ProvenancedField = Field(default_factory=_empty)
    discount_rate: ProvenancedField = Field(default_factory=_empty)

    # Trial facts
    success_probability: ProvenancedField = Field(default_factory=_empty)
    duration_years: ProvenancedField = Field(default_factory=_empty)
    cost_millions: ProvenancedField = Field(default_factory=_empty)
    enrollment: ProvenancedField = Field(default_factory=_empty)
    primary_endpoint: ProvenancedField = Field(default_factory=_empty)
    endpoint_type: ProvenancedField = Field(default_factory=_empty)
    estimated_completion_date: ProvenancedField = Field(default_factory=_empty)

    # Commercial economics
    total_addressable_market_millions: ProvenancedField = Field(default_factory=_empty)
    addressable_patients_annual: ProvenancedField = Field(default_factory=_empty)
    net_price_per_patient_usd: ProvenancedField = Field(default_factory=_empty)
    peak_penetration: ProvenancedField = Field(default_factory=_empty)
    years_to_peak: ProvenancedField = Field(default_factory=_empty)
    patent_life_years: ProvenancedField = Field(default_factory=_empty)
    cogs_rate: ProvenancedField = Field(default_factory=_empty)
    sgna_rate_launch: ProvenancedField = Field(default_factory=_empty)
    sgna_rate_mature: ProvenancedField = Field(default_factory=_empty)

    def provenanced_items(self) -> dict[str, ProvenancedField]:
        """Return ``{field_name: ProvenancedField}`` for every provenanced field."""
        return {
            name: getattr(self, name)
            for name in type(self).model_fields
            if isinstance(getattr(self, name), ProvenancedField)
        }

    def low_confidence_fields(self) -> list[str]:
        """Field names whose value is a low-confidence estimate (review targets)."""
        return [
            name
            for name, field in self.provenanced_items().items()
            if field.confidence == "low"
        ]


class CompanyProfile(BaseModel):
    """Canonical public profile for one ticker: company facts + its assets."""

    ticker: str
    name: str
    company_id: str

    # Company-level financial facts
    cash_millions: ProvenancedField = Field(default_factory=_empty)
    shares_outstanding_millions: ProvenancedField = Field(default_factory=_empty)
    debt_millions: ProvenancedField = Field(default_factory=_empty)
    burn_rate_millions_per_quarter: ProvenancedField = Field(default_factory=_empty)
    current_price: ProvenancedField = Field(default_factory=_empty)
    market_cap_millions: ProvenancedField = Field(default_factory=_empty)

    assets: list[AssetProfile] = Field(default_factory=list)
    evidence_level: EvidenceLevel = "coarse"
    generated_at: str = Field(default_factory=_utcnow_iso)
    source: str = "auto_profile"

    @property
    def lead_asset(self) -> AssetProfile:
        if not self.assets:
            raise ValueError(f"CompanyProfile {self.ticker} has no assets")
        return self.assets[0]

    def company_provenanced_items(self) -> dict[str, ProvenancedField]:
        """Company-level (non-asset) provenanced fields."""
        return {
            name: getattr(self, name)
            for name in type(self).model_fields
            if isinstance(getattr(self, name), ProvenancedField)
        }
