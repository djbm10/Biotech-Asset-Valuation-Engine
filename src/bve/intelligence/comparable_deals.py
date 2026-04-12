"""Comparable biotech M&A deal loader and matcher."""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator


MatchTier = Literal["exact_indication_phase", "therapeutic_area_phase", "phase_only", "no_comps"]


def _normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().lower().split())
    return normalized or None


def _phase_bucket(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = _normalize_text(value)
    mapping = {
        "preclinical": "preclinical",
        "phase_1": "phase_1",
        "phase 1": "phase_1",
        "phase i": "phase_1",
        "phase_2": "phase_2",
        "phase 2": "phase_2",
        "phase ii": "phase_2",
        "phase_3": "phase_3",
        "phase 3": "phase_3",
        "phase iii": "phase_3",
        "nda_bla": "nda_bla",
        "nda/bla": "nda_bla",
        "filing": "nda_bla",
        "approved": "approved",
        "commercial": "approved",
    }
    return mapping.get(normalized, normalized)


class ComparableDeal(BaseModel):
    """One curated biotech M&A comparable."""

    # ── Required / existing fields ──────────────────────────────────────────
    target_name: str
    target_ticker: Optional[str] = None
    drug_name: Optional[str] = None
    indication: str
    therapeutic_area: Optional[str] = None
    phase_at_acquisition: str
    acquirer: str
    deal_date: str
    enterprise_value_millions: Optional[float] = Field(default=None, gt=0.0)
    peak_sales_millions: Optional[float] = Field(default=None, gt=0.0)
    ev_to_peak_sales: Optional[float] = Field(default=None, gt=0.0)
    source: Optional[str] = None
    notes: Optional[str] = None

    # ── New deal-structure fields (all optional for backward compatibility) ──
    upfront_millions: Optional[float] = Field(
        default=None,
        description="Cash paid at signing, net of cash acquired ($M).",
    )
    total_milestones_millions: Optional[float] = Field(
        default=None,
        description="Sum of all regulatory + commercial milestone payments ($M).",
    )
    royalty_rate_low: Optional[float] = Field(
        default=None,
        description="Low end of tiered royalty rate on net sales (0–1 scale, e.g. 0.08).",
    )
    royalty_rate_high: Optional[float] = Field(
        default=None,
        description="High end of tiered royalty rate on net sales (0–1 scale, e.g. 0.14).",
    )
    total_biobucks: Optional[float] = Field(
        default=None,
        description="Upfront + total milestones. If not set, computed when both components are available.",
    )
    equity_component_millions: Optional[float] = Field(
        default=None,
        description="Equity stake or equity consideration component ($M), if any.",
    )
    territory: Optional[str] = Field(
        default=None,
        description=(
            "Geographic scope of the deal. "
            "Values: 'global', 'US', 'ex-US', 'EU', 'Asia', 'US + Canada', etc."
        ),
    )
    deal_structure: Optional[str] = Field(
        default=None,
        description=(
            "Deal type. Values: 'M&A', 'licensing', 'co-development', 'option', "
            "'co-promotion', 'royalty_acquisition'."
        ),
    )
    post_deal_outcome: Optional[str] = Field(
        default=None,
        description=(
            "Outcome of the acquired/licensed asset after deal close. "
            "Values: 'approved', 'failed_ph3', 'failed_ph2', 'discontinued', "
            "'ongoing', 'pending', 'label_expanded'."
        ),
    )

    @model_validator(mode="after")
    def _populate_multiple_and_biobucks(self) -> "ComparableDeal":
        # --- ev_to_peak_sales (existing logic, unchanged) ---
        if self.ev_to_peak_sales is None:
            if (
                self.enterprise_value_millions is not None
                and self.peak_sales_millions is not None
                and self.peak_sales_millions > 0
            ):
                self.ev_to_peak_sales = round(
                    float(self.enterprise_value_millions) / float(self.peak_sales_millions),
                    6,
                )
            else:
                raise ValueError(
                    "Comparable deal requires ev_to_peak_sales or both "
                    "enterprise_value_millions and peak_sales_millions"
                )

        # --- total_biobucks: auto-compute when both components are present ---
        if (
            self.total_biobucks is None
            and self.upfront_millions is not None
            and self.total_milestones_millions is not None
        ):
            self.total_biobucks = round(
                self.upfront_millions + self.total_milestones_millions, 2
            )

        return self

    @property
    def normalized_indication(self) -> Optional[str]:
        return _normalize_text(self.indication)

    @property
    def normalized_therapeutic_area(self) -> Optional[str]:
        return _normalize_text(self.therapeutic_area)

    @property
    def phase_bucket(self) -> Optional[str]:
        return _phase_bucket(self.phase_at_acquisition)


class FairValueBand(BaseModel):
    """
    P25 / P50 / P75 quantile ranges for key deal economics metrics,
    computed from a matched comparable deal set.

    Fields are ``None`` when fewer than 2 deals have data for that metric
    (a single data point does not constitute a meaningful band).
    """

    n_comps_with_ev: int = 0
    n_comps_with_upfront: int = 0
    n_comps_with_biobucks: int = 0

    ev_p25: Optional[float] = None
    ev_p50: Optional[float] = None
    ev_p75: Optional[float] = None

    upfront_p25: Optional[float] = None
    upfront_p50: Optional[float] = None
    upfront_p75: Optional[float] = None

    biobucks_p25: Optional[float] = None
    biobucks_p50: Optional[float] = None
    biobucks_p75: Optional[float] = None


class DealCompsAnalytics:
    """
    Quantile analytics over a matched ``ComparableDeal`` list.

    All methods are static and pure — no side effects, no I/O.
    """

    @staticmethod
    def fair_value_band(deals: list[ComparableDeal]) -> FairValueBand:
        """Compute P25/P50/P75 for EV, upfront, and total_biobucks across matched deals."""
        ev_vals = sorted(
            float(d.enterprise_value_millions)
            for d in deals
            if d.enterprise_value_millions is not None
        )
        upfront_vals = sorted(
            float(d.upfront_millions) for d in deals if d.upfront_millions is not None
        )
        biobucks_vals = sorted(
            float(d.total_biobucks) for d in deals if d.total_biobucks is not None
        )

        return FairValueBand(
            n_comps_with_ev=len(ev_vals),
            n_comps_with_upfront=len(upfront_vals),
            n_comps_with_biobucks=len(biobucks_vals),
            ev_p25=DealCompsAnalytics._quantile(ev_vals, 0.25),
            ev_p50=DealCompsAnalytics._quantile(ev_vals, 0.50),
            ev_p75=DealCompsAnalytics._quantile(ev_vals, 0.75),
            upfront_p25=DealCompsAnalytics._quantile(upfront_vals, 0.25),
            upfront_p50=DealCompsAnalytics._quantile(upfront_vals, 0.50),
            upfront_p75=DealCompsAnalytics._quantile(upfront_vals, 0.75),
            biobucks_p25=DealCompsAnalytics._quantile(biobucks_vals, 0.25),
            biobucks_p50=DealCompsAnalytics._quantile(biobucks_vals, 0.50),
            biobucks_p75=DealCompsAnalytics._quantile(biobucks_vals, 0.75),
        )

    @staticmethod
    def _quantile(sorted_values: list[float], q: float) -> Optional[float]:
        """
        Linear-interpolation quantile (equivalent to numpy default / method='linear').

        Returns ``None`` when the list is empty; returns the single value when n=1.
        """
        if not sorted_values:
            return None
        n = len(sorted_values)
        if n == 1:
            return round(sorted_values[0], 2)
        idx = q * (n - 1)
        lo = int(idx)
        hi = lo + 1
        if hi >= n:
            return round(sorted_values[-1], 2)
        frac = idx - lo
        return round(sorted_values[lo] + frac * (sorted_values[hi] - sorted_values[lo]), 2)


class ComparableDealSet(BaseModel):
    """Typed collection of curated comparable deals."""

    deals: list[ComparableDeal] = Field(default_factory=list)


class ComparableDealAnalysis(BaseModel):
    """
    Comparison of one asset versus matched biotech M&A comps.

    Extends the original EV/peak_sales analysis with a ``FairValueBand``
    containing quantile ranges for EV, upfront, and total_biobucks from
    the matched deal set.
    """

    asset_ev_to_peak_sales: Optional[float]
    match_tier: MatchTier
    n_comps: int
    peer_min_ev_to_peak_sales: Optional[float] = None
    peer_median_ev_to_peak_sales: Optional[float] = None
    peer_max_ev_to_peak_sales: Optional[float] = None
    percentile_vs_comps: Optional[float] = None
    premium_discount_vs_median: Optional[float] = None
    matched_targets: list[str] = Field(default_factory=list)

    # New: quantile bands for deal structure economics
    fair_value_band: Optional[FairValueBand] = None


class ComparableDealLoader:
    """Load and validate comparable biotech M&A deals from YAML."""

    @staticmethod
    def load(path: Path | str) -> ComparableDealSet:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict):
            deals = raw.get("deals", [])
        else:
            deals = raw
        if not isinstance(deals, list):
            raise ValueError("Comparable deals YAML must be a list or contain a 'deals' list")
        return ComparableDealSet(deals=[ComparableDeal.model_validate(item) for item in deals])


class ComparableDealMatcher:
    """Match one asset to curated biotech M&A comparables."""

    @staticmethod
    def analyze(
        *,
        asset_indication: Optional[str],
        asset_therapeutic_area: Optional[str],
        asset_stage: Optional[str],
        asset_ev_to_peak_sales: Optional[float],
        deals: list[ComparableDeal],
    ) -> ComparableDealAnalysis:
        if asset_ev_to_peak_sales is None or asset_ev_to_peak_sales <= 0:
            return ComparableDealAnalysis(
                asset_ev_to_peak_sales=asset_ev_to_peak_sales,
                match_tier="no_comps",
                n_comps=0,
            )

        indication = _normalize_text(asset_indication)
        therapeutic_area = _normalize_text(asset_therapeutic_area)
        phase_bucket = _phase_bucket(asset_stage)

        exact = [
            deal
            for deal in deals
            if deal.ev_to_peak_sales is not None
            and deal.phase_bucket == phase_bucket
            and deal.normalized_indication == indication
        ]
        if exact:
            return ComparableDealMatcher._summarize(
                asset_ev_to_peak_sales=asset_ev_to_peak_sales,
                deals=exact,
                match_tier="exact_indication_phase",
            )

        ta_phase = [
            deal
            for deal in deals
            if deal.ev_to_peak_sales is not None
            and deal.phase_bucket == phase_bucket
            and deal.normalized_therapeutic_area == therapeutic_area
        ]
        if ta_phase:
            return ComparableDealMatcher._summarize(
                asset_ev_to_peak_sales=asset_ev_to_peak_sales,
                deals=ta_phase,
                match_tier="therapeutic_area_phase",
            )

        phase_only = [
            deal
            for deal in deals
            if deal.ev_to_peak_sales is not None and deal.phase_bucket == phase_bucket
        ]
        if phase_only:
            return ComparableDealMatcher._summarize(
                asset_ev_to_peak_sales=asset_ev_to_peak_sales,
                deals=phase_only,
                match_tier="phase_only",
            )

        return ComparableDealAnalysis(
            asset_ev_to_peak_sales=asset_ev_to_peak_sales,
            match_tier="no_comps",
            n_comps=0,
        )

    @staticmethod
    def _summarize(
        *,
        asset_ev_to_peak_sales: float,
        deals: list[ComparableDeal],
        match_tier: MatchTier,
    ) -> ComparableDealAnalysis:
        multiples = sorted(float(deal.ev_to_peak_sales) for deal in deals if deal.ev_to_peak_sales is not None)
        if not multiples:
            return ComparableDealAnalysis(
                asset_ev_to_peak_sales=asset_ev_to_peak_sales,
                match_tier="no_comps",
                n_comps=0,
            )

        median = ComparableDealMatcher._median(multiples)
        percentile = ComparableDealMatcher._percentile(asset_ev_to_peak_sales, multiples)
        premium_discount = None
        if median and median > 0:
            premium_discount = round((asset_ev_to_peak_sales / median) - 1.0, 6)

        fair_band = DealCompsAnalytics.fair_value_band(deals)

        return ComparableDealAnalysis(
            asset_ev_to_peak_sales=round(asset_ev_to_peak_sales, 6),
            match_tier=match_tier,
            n_comps=len(multiples),
            peer_min_ev_to_peak_sales=round(multiples[0], 6),
            peer_median_ev_to_peak_sales=round(median, 6),
            peer_max_ev_to_peak_sales=round(multiples[-1], 6),
            percentile_vs_comps=round(percentile, 6),
            premium_discount_vs_median=premium_discount,
            matched_targets=[deal.target_name for deal in deals],
            fair_value_band=fair_band,
        )

    @staticmethod
    def _median(values: list[float]) -> float:
        n = len(values)
        mid = n // 2
        if n % 2 == 1:
            return values[mid]
        return (values[mid - 1] + values[mid]) / 2.0

    @staticmethod
    def _percentile(value: float, sorted_values: list[float]) -> float:
        if not sorted_values:
            return 0.0
        n_less = sum(1 for item in sorted_values if item < value)
        n_equal = sum(1 for item in sorted_values if item == value)
        return (n_less + 0.5 * n_equal) / len(sorted_values)
