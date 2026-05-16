"""
P3.5 — Sum-of-the-parts (SOTP) valuation and ex-US geographic modelling.

SOTP aggregates multiple asset rNPVs into a single company NAV, applying
geographic haircuts for ex-US revenue uncertainty and corporate-level
adjustments (overhead, debt, minority interests).

Geographic haircut mechanics
-----------------------------
Each ``SOTPComponent`` carries a ``us_fraction`` (share of revenues from the US)
and an ``ex_us_discount`` (additional haircut on the non-US fraction to reflect
higher regulatory risk, pricing pressure, and partnership structures abroad).

    geo_adjusted_value = rnpv × (us_fraction + (1 − us_fraction) × (1 − ex_us_discount))

With ``us_fraction = 1.0``, no ex-US haircut is applied.

SOTP total NAV
--------------
    total_nav = Σ geo_adjusted_values + net_cash − corporate_adjustments

Waterfall output
----------------
``SOTPResult.as_waterfall_bars()`` returns an ordered list of
``{name, value, bar_type}`` dicts ready for matplotlib waterfall charts.

Usage
-----
>>> from bve.analysis.sotp import SOTPComponent, build_sotp
>>> result = build_sotp(
...     components=[
...         SOTPComponent("DrugA", rnpv_millions=300.0, us_fraction=0.65, ex_us_discount=0.10),
...         SOTPComponent("DrugB", rnpv_millions=150.0, us_fraction=1.0),
...     ],
...     net_cash_millions=100.0,
...     shares_outstanding_millions=80.0,
... )
>>> result.total_nav_millions
539.5
>>> result.nav_per_share
6.74
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# GeographySpec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GeographySpec:
    """
    Geographic revenue split for a single asset.

    Attributes
    ----------
    us : float
        Fraction of revenues from the United States.
    eu : float
        Fraction from Europe (EU + UK).
    japan : float
        Fraction from Japan.
    row : float
        Rest of world.

    All four fractions must sum to 1.0 (±0.01 tolerance).
    """
    us: float = 0.65
    eu: float = 0.20
    japan: float = 0.05
    row: float = 0.10

    def __post_init__(self) -> None:
        total = self.us + self.eu + self.japan + self.row
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"GeographySpec fractions must sum to 1.0; got {total:.4f}"
            )


# ---------------------------------------------------------------------------
# SOTPComponent
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SOTPComponent:
    """
    A single asset contribution to an SOTP valuation.

    Parameters
    ----------
    name : str
        Asset or program name for display.
    rnpv_millions : float
        Base rNPV from the valuation model (US + ex-US combined, or US-only;
        the haircut is applied on top regardless).
    us_fraction : float
        Fraction of revenues attributable to the US market (0–1).
        Default 1.0 (US only — no ex-US haircut applied).
    ex_us_discount : float
        Additional haircut applied to the ex-US fraction (0–1).
        0 = no extra discount; 0.20 = 20% haircut on ex-US revenues.
    label : str, optional
        Optional display label (defaults to ``name``).
    """
    name: str
    rnpv_millions: float
    us_fraction: float = 1.0
    ex_us_discount: float = 0.0
    label: Optional[str] = None

    def __post_init__(self) -> None:
        if not (0.0 <= self.us_fraction <= 1.0):
            raise ValueError(
                f"us_fraction must be in [0, 1]; got {self.us_fraction}"
            )
        if not (0.0 <= self.ex_us_discount <= 1.0):
            raise ValueError(
                f"ex_us_discount must be in [0, 1]; got {self.ex_us_discount}"
            )

    @property
    def geo_adjusted_value(self) -> float:
        """
        rNPV after applying the ex-US geographic haircut.

        geo_adjusted = rnpv × (us_fraction + ex_us_fraction × (1 − ex_us_discount))
        """
        ex_us_fraction = 1.0 - self.us_fraction
        multiplier = self.us_fraction + ex_us_fraction * (1.0 - self.ex_us_discount)
        return round(self.rnpv_millions * multiplier, 4)

    @property
    def geo_haircut_pct(self) -> float:
        """Percentage of rNPV haircut from the geographic discount."""
        if self.rnpv_millions == 0:
            return 0.0
        return round((1.0 - self.geo_adjusted_value / self.rnpv_millions) * 100, 2)

    @property
    def display_name(self) -> str:
        return self.label or self.name


# ---------------------------------------------------------------------------
# SOTPResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SOTPResult:
    """
    Sum-of-the-parts valuation result.

    Attributes
    ----------
    components : list[SOTPComponent]
        Ordered list of asset contributions.
    net_cash_millions : float
        Company net cash (cash minus financial debt).
    corporate_adjustments_millions : float
        Deductions for corporate overhead, minority interests, etc.
        Positive value means the deduction is subtracted from NAV.
    total_nav_millions : float
        Σ geo_adjusted_values + net_cash − corporate_adjustments.
    nav_per_share : Optional[float]
        total_nav_millions / shares_outstanding_millions; None if not provided.
    shares_outstanding_millions : Optional[float]
        Share count used for per-share NAV.
    """
    components: tuple  # tuple[SOTPComponent, ...]
    net_cash_millions: float
    corporate_adjustments_millions: float
    total_nav_millions: float
    nav_per_share: Optional[float]
    shares_outstanding_millions: Optional[float]

    # ------------------------------------------------------------------ #
    # Waterfall                                                            #
    # ------------------------------------------------------------------ #

    def as_waterfall_bars(self) -> list[dict]:
        """
        Ordered waterfall bar data for plotting.

        Each bar is ``{"name": str, "value": float, "bar_type": str}``.

        bar_type values:
        - "asset" — geo-adjusted asset contribution
        - "cash" — net cash
        - "adjustment" — corporate deductions (negative)
        - "total" — final NAV total (absolute, not incremental)
        """
        bars: list[dict] = []

        for comp in self.components:
            bars.append({
                "name": comp.display_name,
                "value": round(comp.geo_adjusted_value, 2),
                "bar_type": "asset",
            })

        bars.append({
            "name": "Net Cash",
            "value": round(self.net_cash_millions, 2),
            "bar_type": "cash",
        })

        if self.corporate_adjustments_millions != 0:
            bars.append({
                "name": "Corp. Adjustments",
                "value": round(-self.corporate_adjustments_millions, 2),
                "bar_type": "adjustment",
            })

        bars.append({
            "name": "Total NAV",
            "value": round(self.total_nav_millions, 2),
            "bar_type": "total",
        })

        return bars

    # ------------------------------------------------------------------ #
    # Export helpers                                                       #
    # ------------------------------------------------------------------ #

    def summary_dict(self) -> dict:
        """Flat dict of key SOTP metrics for reporting."""
        return {
            "total_nav_millions": round(self.total_nav_millions, 2),
            "nav_per_share": self.nav_per_share,
            "net_cash_millions": round(self.net_cash_millions, 2),
            "corporate_adjustments_millions": round(self.corporate_adjustments_millions, 2),
            "n_components": len(self.components),
            "component_names": [c.name for c in self.components],
            "component_geo_adjusted_values": [
                round(c.geo_adjusted_value, 2) for c in self.components
            ],
            "component_geo_haircuts_pct": [c.geo_haircut_pct for c in self.components],
        }

    def as_csv_rows(self) -> list[list]:
        """CSV-compatible representation: header row + one row per component + totals."""
        header = ["Component", "rNPV ($M)", "US Fraction", "Ex-US Discount", "Geo-Adjusted ($M)", "Haircut (%)"]
        rows: list[list] = [header]

        for c in self.components:
            rows.append([
                c.display_name,
                round(c.rnpv_millions, 1),
                f"{c.us_fraction:.0%}",
                f"{c.ex_us_discount:.0%}",
                round(c.geo_adjusted_value, 1),
                f"{c.geo_haircut_pct:.1f}%",
            ])

        rows.append(["Net Cash", "", "", "", round(self.net_cash_millions, 1), ""])
        if self.corporate_adjustments_millions:
            rows.append(["Corp. Adjustments", "", "", "", -round(self.corporate_adjustments_millions, 1), ""])
        rows.append(["TOTAL NAV", "", "", "", round(self.total_nav_millions, 1), ""])

        return rows


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_sotp(
    components: list[SOTPComponent],
    net_cash_millions: float = 0.0,
    shares_outstanding_millions: Optional[float] = None,
    corporate_adjustments_millions: float = 0.0,
) -> SOTPResult:
    """
    Build a sum-of-the-parts valuation.

    Parameters
    ----------
    components : list[SOTPComponent]
        Asset contributions. Must be non-empty.
    net_cash_millions : float
        Company net cash. Default 0.
    shares_outstanding_millions : Optional[float]
        For per-share NAV. Pass None to skip.
    corporate_adjustments_millions : float
        Positive = deducted from NAV (overhead, debt). Default 0.

    Returns
    -------
    SOTPResult
    """
    if not components:
        raise ValueError("components list must not be empty")

    geo_sum = sum(c.geo_adjusted_value for c in components)
    total_nav = round(geo_sum + net_cash_millions - corporate_adjustments_millions, 4)

    nav_ps: Optional[float] = None
    if shares_outstanding_millions and shares_outstanding_millions > 0:
        nav_ps = round(total_nav / shares_outstanding_millions, 4)

    return SOTPResult(
        components=tuple(components),
        net_cash_millions=round(net_cash_millions, 4),
        corporate_adjustments_millions=round(corporate_adjustments_millions, 4),
        total_nav_millions=total_nav,
        nav_per_share=nav_ps,
        shares_outstanding_millions=shares_outstanding_millions,
    )
