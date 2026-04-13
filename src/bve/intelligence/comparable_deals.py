"""Comparable biotech M&A deal loader, analytics, and matcher.

All Pydantic models live in bve.intelligence.deal_models so that
bve.valuation.outputs can import them without triggering the
intelligence → phase2 → valuation circular dependency.  Everything
is re-exported here for backward compatibility.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

# ── Re-export all models from deal_models (backward-compat) ──────────────────
from bve.models.deal_models import (
    ComparableDeal,
    ComparableDealAnalysis,
    ComparableDealSet,
    DataQuality,
    FairValueBand,
    MatchTier,
    _normalize_text,
    _phase_bucket,
)

__all__ = [
    "ComparableDeal",
    "ComparableDealAnalysis",
    "ComparableDealSet",
    "DataQuality",
    "FairValueBand",
    "MatchTier",
    "DealCompsAnalytics",
    "ComparableDealLoader",
    "ComparableDealMatcher",
]


# ── Analytics ─────────────────────────────────────────────────────────────────

class DealCompsAnalytics:
    """
    Quantile analytics over a matched ``ComparableDeal`` list.

    All methods are static and pure — no side effects, no I/O.
    """

    @staticmethod
    def fair_value_band(deals: list[ComparableDeal]) -> FairValueBand:
        """Compute P25/P50/P75 for EV, upfront, and total_biobucks across *all* deals."""
        return DealCompsAnalytics._band_from_deals(deals)

    @staticmethod
    def fair_value_band_hq(deals: list[ComparableDeal]) -> Optional[FairValueBand]:
        """
        Compute P25/P50/P75 using only high- and medium-quality deals.

        Returns ``None`` when no high/medium-quality deals are available.
        """
        hq = [d for d in deals if d.is_high_quality]
        if not hq:
            return None
        return DealCompsAnalytics._band_from_deals(hq)

    @staticmethod
    def _band_from_deals(deals: list[ComparableDeal]) -> FairValueBand:
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


# ── Loader ────────────────────────────────────────────────────────────────────

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


# ── Matcher ───────────────────────────────────────────────────────────────────

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

        hq_deals = [d for d in deals if d.is_high_quality]

        return ComparableDealAnalysis(
            asset_ev_to_peak_sales=round(asset_ev_to_peak_sales, 6),
            match_tier=match_tier,
            n_comps=len(multiples),
            n_hq_comps=len(hq_deals),
            peer_min_ev_to_peak_sales=round(multiples[0], 6),
            peer_median_ev_to_peak_sales=round(median, 6),
            peer_max_ev_to_peak_sales=round(multiples[-1], 6),
            percentile_vs_comps=round(percentile, 6),
            premium_discount_vs_median=premium_discount,
            matched_targets=[deal.target_name for deal in deals],
            fair_value_band=DealCompsAnalytics.fair_value_band(deals),
            hq_fair_value_band=DealCompsAnalytics.fair_value_band_hq(deals),
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
