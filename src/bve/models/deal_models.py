"""
Pydantic data models for comparable biotech M&A deals.

Intentionally kept free of any bve.intelligence.* imports so that
bve.valuation.outputs can import ComparableDealAnalysis directly without
triggering the intelligence → phase2 → valuation circular import chain.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ── Type aliases ─────────────────────────────────────────────────────────────

MatchTier = Literal[
    "exact_indication_phase",
    "therapeutic_area_phase",
    "phase_only",
    "no_comps",
]

DataQuality = Literal["high", "medium", "low"]


# ── Text helpers ─────────────────────────────────────────────────────────────

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


# ── Core deal record ──────────────────────────────────────────────────────────

class ComparableDeal(BaseModel):
    """One curated biotech M&A or licensing comparable."""

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

    # ── Deal-structure fields ────────────────────────────────────────────────
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
        description="Upfront + total milestones. Auto-computed when both components are available.",
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
            "'co-promotion', 'royalty_acquisition', 'asset_sale'."
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

    # ── Data quality ─────────────────────────────────────────────────────────
    data_quality: DataQuality = Field(
        default="medium",
        description=(
            "Source reliability tier. "
            "'high' = SEC-disclosed public company acquisition (DEF 14A / merger proxy); "
            "'medium' = press release with stated deal value, industry database; "
            "'low' = analyst estimate, secondary source, undisclosed terms."
        ),
    )

    @model_validator(mode="after")
    def _populate_multiple_and_biobucks(self) -> "ComparableDeal":
        # --- ev_to_peak_sales ---
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

    @property
    def is_high_quality(self) -> bool:
        """True for high- or medium-quality records (excludes low-quality estimates)."""
        return self.data_quality in ("high", "medium")


# ── Quantile container ────────────────────────────────────────────────────────

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


# ── Typed collection ──────────────────────────────────────────────────────────

class ComparableDealSet(BaseModel):
    """Typed collection of curated comparable deals."""

    deals: list[ComparableDeal] = Field(default_factory=list)


# ── Analysis output ───────────────────────────────────────────────────────────

class ComparableDealAnalysis(BaseModel):
    """
    Comparison of one asset versus matched biotech M&A comps.

    Contains EV/peak_sales quantile stats, fair-value bands from all matched
    deals, and a high-quality-only band for more rigorous cross-checks.
    """

    asset_ev_to_peak_sales: Optional[float]
    match_tier: MatchTier
    n_comps: int
    n_hq_comps: int = 0
    peer_min_ev_to_peak_sales: Optional[float] = None
    peer_median_ev_to_peak_sales: Optional[float] = None
    peer_max_ev_to_peak_sales: Optional[float] = None
    percentile_vs_comps: Optional[float] = None
    premium_discount_vs_median: Optional[float] = None
    matched_targets: list[str] = Field(default_factory=list)

    # Quantile bands — all comps vs. high-quality-only comps
    fair_value_band: Optional[FairValueBand] = None
    hq_fair_value_band: Optional[FairValueBand] = None
