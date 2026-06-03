"""Typed loader for acquirer-side pipeline-gap research profiles."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import re

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
    sub_area: str | None = None
    preferred_modality: list[str] = Field(default_factory=list)
    budget_ceiling_millions: float | None = Field(default=None, ge=0.0)
    notes: str | None = None
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
    market_cap_billions: float | None = Field(default=None, ge=0.0)
    cash_billions: float | None = Field(default=None, ge=0.0)
    profile_as_of: date
    source_notes: str | None = None
    therapeutic_area_gaps: list[TherapeuticGap] = Field(default_factory=list, min_length=1)
    preferred_modalities: list[PreferredModality] = Field(default_factory=list, min_length=1)
    strategic_priorities: list[StrategicPriority] = Field(default_factory=list, min_length=1)
    recent_deal_history: list[RecentDeal] = Field(default_factory=list)
    budget: BudgetSnapshot
    acquisition_capacity_millions: float | None = Field(default=None, ge=0.0)
    existing_partnerships: list[ExistingPartnership] = Field(default_factory=list)


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


class CuratedPipelineGap(BaseModel):
    """Lightweight pipeline-gap input used by example acquirer-profile YAMLs."""

    therapeutic_area: str
    sub_area: str | None = None
    gap_type: str
    urgency: str
    preferred_modality: list[str] = Field(default_factory=list, min_length=1)
    budget_ceiling_millions: float = Field(ge=0.0)
    notes: str | None = None


class CuratedRecentDeal(BaseModel):
    """Lightweight recent-deal input used by example acquirer-profile YAMLs."""

    target: str
    date: date
    value_billions: float = Field(ge=0.0)
    therapeutic_area: str
    modality: str


class ExistingPartnership(BaseModel):
    """
    Active partnership / co-development agreement between an acquirer and a
    potential target.

    Partnerships are a strong M&A signal: existing co-devs often give the
    acquirer data rights, option clauses, or right-of-first-negotiation that
    accelerate or de-risk outright acquisition.
    """

    target: str = Field(description="Target company ticker or name")
    partnership_type: str = Field(
        description=(
            "e.g., co_development, licensing_in, licensing_out, option_to_acquire, "
            "co_promotion, research_collaboration"
        )
    )
    therapeutic_area: str
    description: str = Field(description="Brief description of the partnership terms and status")
    year_initiated: int | None = Field(default=None, ge=1990, le=2030)
    acquisition_option: bool = Field(
        default=False,
        description="True if the agreement includes an explicit option to acquire the target",
    )


class CuratedAcquirerProfile(BaseModel):
    """Single-company curated acquirer profile used by examples and screening."""

    company: str
    ticker: str | None = None
    market_cap_billions: float | None = Field(default=None, ge=0.0)
    cash_billions: float | None = Field(default=None, ge=0.0)
    acquisition_capacity_millions: float | None = Field(
        default=None, ge=0.0,
        description=(
            "Estimated remaining acquisition capacity in USD millions. "
            "Accounts for existing debt load, leverage appetite, and current "
            "deal pipeline. Higher than cash_billions × 1000 when the acquirer "
            "can service significant incremental debt (investment-grade issuers). "
            "Set to 0 if the acquirer is currently constrained (integration burden, "
            "high leverage, regulatory review)."
        ),
    )
    pipeline_gaps: list[CuratedPipelineGap] = Field(default_factory=list, min_length=1)
    recent_deals: list[CuratedRecentDeal] = Field(default_factory=list)
    existing_partnerships: list[ExistingPartnership] = Field(
        default_factory=list,
        description=(
            "Active co-development, licensing, or option agreements. "
            "Partners with acquisition options or deep data rights are "
            "elevated in acquirer-fit scoring."
        ),
    )
    stated_priorities: list[str] = Field(default_factory=list)
    profile_as_of: date | None = None


_URGENCY_RANK = {"high": 3, "medium": 2, "low": 1}


def _slugify_company(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return slug.strip("_") or "acquirer"


def _make_source_ref(
    *,
    source_path: Path,
    source_date: date,
    title: str,
    note: str | None = None,
) -> SourceReference:
    return SourceReference(
        source_date=source_date,
        source_type="manual_curation",
        source_title=title,
        source_url=str(source_path),
        note=note,
    )


def _convert_curated_profile(
    profile: CuratedAcquirerProfile,
    *,
    source_path: Path,
) -> AcquirerProfile:
    profile_as_of = profile.profile_as_of or date.today()
    profile_ref = _make_source_ref(
        source_path=source_path,
        source_date=profile_as_of,
        title=f"Curated acquirer profile: {profile.company}",
    )

    therapeutic_area_gaps = [
        TherapeuticGap(
            therapeutic_area=gap.therapeutic_area,
            exposure_type=gap.gap_type,
            exposure_level=gap.urgency,
            rationale=gap.notes or gap.gap_type.replace("_", " "),
            sub_area=gap.sub_area,
            preferred_modality=list(gap.preferred_modality),
            budget_ceiling_millions=gap.budget_ceiling_millions,
            notes=gap.notes,
            source_refs=[profile_ref],
        )
        for gap in profile.pipeline_gaps
    ]

    modality_strengths: dict[str, str] = {}
    modality_gap_labels: dict[str, list[str]] = {}
    for gap in profile.pipeline_gaps:
        gap_label = gap.sub_area or gap.therapeutic_area
        urgency = gap.urgency.strip().lower()
        for modality in gap.preferred_modality:
            current = modality_strengths.get(modality)
            if current is None or _URGENCY_RANK.get(urgency, 0) > _URGENCY_RANK.get(current, 0):
                modality_strengths[modality] = urgency
            modality_gap_labels.setdefault(modality, []).append(gap_label)

    preferred_modalities = [
        PreferredModality(
            modality=modality,
            preference_strength=strength,
            rationale=(
                "Derived from curated pipeline gaps: "
                + ", ".join(sorted(dict.fromkeys(modality_gap_labels.get(modality, []))))
            ),
            source_refs=[profile_ref],
        )
        for modality, strength in sorted(modality_strengths.items())
    ]

    strategic_priorities = [
        StrategicPriority(
            priority=priority,
            priority_strength="high",
            source_refs=[profile_ref],
        )
        for priority in (profile.stated_priorities or ["Curated pipeline-gap priorities"])
    ]

    recent_deal_history = [
        RecentDeal(
            deal_name=deal.target,
            status="completed",
            announcement_date=deal.date,
            deal_type="acquisition",
            therapeutic_area=deal.therapeutic_area,
            modality=deal.modality,
            stage_context="unspecified",
            upfront_millions=round(deal.value_billions * 1000.0, 6),
            implied_value_band_millions_low=round(deal.value_billions * 1000.0, 6),
            implied_value_band_millions_high=round(deal.value_billions * 1000.0, 6),
            source_url=str(source_path),
            notes="Imported from curated acquirer profile",
        )
        for deal in profile.recent_deals
    ]

    max_gap_budget = max(
        (float(gap.budget_ceiling_millions) for gap in profile.pipeline_gaps),
        default=0.0,
    )
    if profile.cash_billions is not None:
        budget_cash_millions = round(profile.cash_billions * 1000.0, 6)
        capacity_notes = (
            f"Curated profile for {profile.company}. "
            "Cash snapshot provided directly by the curated profile; "
            "use per-gap budget ceilings where provided."
        )
    else:
        budget_cash_millions = round(max_gap_budget, 6)
        capacity_notes = (
            f"Curated screening-grade profile for {profile.company}. "
            "Balance-sheet snapshot not provided; budget placeholder is derived from "
            "the largest per-gap budget ceiling and should not be treated as actual cash."
        )

    budget = BudgetSnapshot(
        as_of_date=profile_as_of,
        cash_and_marketable_securities_millions=budget_cash_millions,
        long_term_debt_millions=0.0,
        net_cash_millions=budget_cash_millions,
        capacity_notes=capacity_notes,
        source_refs=[profile_ref],
    )

    return AcquirerProfile(
        acquirer_id=_slugify_company(profile.company),
        company_name=profile.company,
        ticker=profile.ticker,
        market_cap_billions=profile.market_cap_billions,
        cash_billions=profile.cash_billions,
        profile_as_of=profile_as_of,
        source_notes=(
            "Converted from lightweight curated profile format for use by the "
            "acquirer-fit and acquisition-memo pipeline."
        ),
        therapeutic_area_gaps=therapeutic_area_gaps,
        preferred_modalities=preferred_modalities,
        strategic_priorities=strategic_priorities,
        recent_deal_history=recent_deal_history,
        budget=budget,
        acquisition_capacity_millions=profile.acquisition_capacity_millions,
        existing_partnerships=list(profile.existing_partnerships),
    )


def _dataset_from_curated_profile(
    profile: CuratedAcquirerProfile,
    *,
    source_path: Path,
) -> AcquirerProfileDataset:
    converted = _convert_curated_profile(profile, source_path=source_path)
    return AcquirerProfileDataset(
        as_of_date=converted.profile_as_of,
        acquirers=[converted],
    )


def _load_from_yaml_mapping(raw: dict, *, source_path: Path) -> AcquirerProfileDataset:
    if "acquirers" in raw:
        return AcquirerProfileDataset.model_validate(raw)
    if "company" in raw and "pipeline_gaps" in raw:
        profile = CuratedAcquirerProfile.model_validate(raw)
        return _dataset_from_curated_profile(profile, source_path=source_path)
    raise ValueError(
        "Acquirer profile YAML must either define a dataset with 'acquirers' or "
        "a curated single-company profile with 'company' and 'pipeline_gaps'"
    )


def _load_from_directory(path: Path) -> AcquirerProfileDataset:
    yaml_paths = sorted([
        child for child in path.iterdir() if child.is_file() and child.suffix.lower() in {".yaml", ".yml"}
    ])
    if not yaml_paths:
        raise ValueError(f"No YAML files found in acquirer profile directory: {path}")

    acquirers: list[AcquirerProfile] = []
    as_of_dates: list[date] = []
    for yaml_path in yaml_paths:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        dataset = _load_from_yaml_mapping(raw, source_path=yaml_path)
        as_of_dates.append(dataset.as_of_date)
        acquirers.extend(dataset.acquirers)

    return AcquirerProfileDataset(
        as_of_date=max(as_of_dates),
        acquirers=acquirers,
    )


class AcquirerProfileLoader:
    """Load and query acquirer-profile YAML."""

    @staticmethod
    def load(path: Path | str) -> AcquirerProfileDataset:
        resolved_path = Path(path)
        if resolved_path.is_dir():
            return _load_from_directory(resolved_path)

        raw = yaml.safe_load(resolved_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("Acquirer profile YAML must be a mapping")
        return _load_from_yaml_mapping(raw, source_path=resolved_path)

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
