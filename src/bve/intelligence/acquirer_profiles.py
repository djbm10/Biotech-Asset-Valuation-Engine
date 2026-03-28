"""Typed loader for acquirer-side pipeline-gap research profiles."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


class SourceReference(BaseModel):
    """One dated source supporting a curated acquirer-profile statement."""

    source_date: date
    source_type: str
    source_title: str
    source_url: str
    note: str | None = None


class TherapeuticGap(BaseModel):
    """Therapeutic area where the acquirer has a pipeline or franchise need."""

    therapeutic_area: str
    exposure_type: str
    exposure_level: str
    rationale: str
    source_refs: list[SourceReference] = Field(default_factory=list, min_length=1)


class PreferredModality(BaseModel):
    """Modality bias inferred from historical platform choices and public strategy."""

    modality: str
    preference_strength: str
    rationale: str
    source_refs: list[SourceReference] = Field(default_factory=list, min_length=1)


class StrategicPriority(BaseModel):
    """Acquirer-level strategic priority backed by dated management commentary."""

    priority: str
    priority_strength: str
    source_refs: list[SourceReference] = Field(default_factory=list, min_length=1)


class RecentDeal(BaseModel):
    """One recent deal or attempted deal relevant to fit and valuation framing."""

    deal_name: str
    status: str
    announcement_date: date
    deal_type: str
    therapeutic_area: str
    modality: str
    stage_context: str
    upfront_millions: float | None = Field(default=None, ge=0.0)
    milestone_potential_millions: float | None = Field(default=None, ge=0.0)
    royalty_terms: str | None = None
    implied_value_band_millions_low: float | None = Field(default=None, ge=0.0)
    implied_value_band_millions_high: float | None = Field(default=None, ge=0.0)
    source_url: str
    notes: str | None = None

    @model_validator(mode="after")
    def _validate_value_band(self) -> "RecentDeal":
        low = self.implied_value_band_millions_low
        high = self.implied_value_band_millions_high
        if low is not None and high is not None and high < low:
            raise ValueError("implied_value_band_millions_high must be >= low")
        if low is None and high is not None:
            raise ValueError("implied_value_band_millions_low is required when high is provided")
        return self


class BudgetSnapshot(BaseModel):
    """Balance-sheet snapshot used to frame acquisition affordability."""

    as_of_date: date
    cash_and_marketable_securities_millions: float = Field(ge=0.0)
    long_term_debt_millions: float = Field(ge=0.0)
    net_cash_millions: float | None = Field(default=None)
    capacity_notes: str
    source_refs: list[SourceReference] = Field(default_factory=list, min_length=1)

    @model_validator(mode="after")
    def _validate_net_cash(self) -> "BudgetSnapshot":
        computed_net_cash = round(
            float(self.cash_and_marketable_securities_millions)
            - float(self.long_term_debt_millions),
            4,
        )
        if self.net_cash_millions is None:
            self.net_cash_millions = computed_net_cash
            return self
        if abs(float(self.net_cash_millions) - computed_net_cash) > 0.01:
            raise ValueError(
                "net_cash_millions must equal cash_and_marketable_securities_millions "
                "- long_term_debt_millions within 0.01"
            )
        return self


class AcquirerProfile(BaseModel):
    """Full manually curated profile for one acquirer."""

    acquirer_id: str
    company_name: str
    ticker: str | None = None
    profile_as_of: date
    source_notes: str | None = None
    therapeutic_area_gaps: list[TherapeuticGap] = Field(default_factory=list, min_length=1)
    preferred_modalities: list[PreferredModality] = Field(default_factory=list, min_length=1)
    strategic_priorities: list[StrategicPriority] = Field(default_factory=list, min_length=1)
    recent_deal_history: list[RecentDeal] = Field(default_factory=list)
    budget: BudgetSnapshot


class AcquirerProfileDataset(BaseModel):
    """Typed representation of `research/mna/pipeline_gaps.yaml`."""

    as_of_date: date
    acquirers: list[AcquirerProfile] = Field(default_factory=list, min_length=1)

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> "AcquirerProfileDataset":
        seen: set[str] = set()
        for acquirer in self.acquirers:
            key = acquirer.acquirer_id.strip().lower()
            if key in seen:
                raise ValueError(f"Duplicate acquirer_id: {acquirer.acquirer_id}")
            seen.add(key)
        return self


class AcquirerProfileLoader:
    """Load and query acquirer-profile YAML."""

    @staticmethod
    def load(path: Path | str) -> AcquirerProfileDataset:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("Acquirer profile YAML must be a mapping with 'as_of_date' and 'acquirers'")
        return AcquirerProfileDataset.model_validate(raw)

    @staticmethod
    def get_acquirer(
        dataset_or_path: AcquirerProfileDataset | Path | str,
        acquirer_id: str,
    ) -> AcquirerProfile:
        dataset = (
            dataset_or_path
            if isinstance(dataset_or_path, AcquirerProfileDataset)
            else AcquirerProfileLoader.load(dataset_or_path)
        )
        lookup = acquirer_id.strip().lower()
        for acquirer in dataset.acquirers:
            if acquirer.acquirer_id.strip().lower() == lookup:
                return acquirer
        raise KeyError(f"Unknown acquirer_id: {acquirer_id}")
