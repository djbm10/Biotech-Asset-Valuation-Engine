"""Assumption provenance objects for key POS and valuation inputs.

Each ProvenanceItem records where a number came from, how fresh it is,
and how confident we are in it. Items are rendered as a Markdown table
for inclusion in decision reports.

Design notes
------------
- ProvenanceItem is a pure data container; it carries no business logic.
- ``build_pos_provenance`` and ``build_valuation_provenance`` are light
  adapters that extract the most decision-relevant fields from existing
  objects. They never raise — missing data is silently represented as
  source="not_available".
- ``render_provenance_table`` returns a Markdown string. The table is
  always emitted; rows with no data show "Not available".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class ProvenanceItem:
    """Provenance record for one assumption or data point.

    Parameters
    ----------
    field:
        Human-readable name (e.g. "Phase 2 base POS", "Net cash").
    value:
        Current value used in the model (any type; rendered via str()).
    source:
        Where the value came from:
        ``"yaml_config"``        — user-supplied YAML
        ``"industry_assumption"``— loaded from industry_assumptions.yaml
        ``"market_data"``        — real-time/near-real-time price/fundamental data
        ``"computed"``           — derived from other inputs
        ``"manual"``             — entered by an analyst; no automated refresh
        ``"not_available"``      — could not be determined
    as_of:
        Date the data was last verified or refreshed. ``None`` = unknown.
    staleness_warning:
        Non-None string when data exceeds its freshness threshold.
    confidence:
        ``"high"`` | ``"medium"`` | ``"low"`` | ``"assumed"``
    notes:
        Optional free-text annotation.
    """

    field: str
    value: Any
    source: str = "not_available"
    as_of: Optional[date] = None
    staleness_warning: Optional[str] = None
    confidence: str = "medium"
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_pos_provenance(
    asset: Any,
    trials: list,
    *,
    as_of_date: Optional[date] = None,
) -> list[ProvenanceItem]:
    """Extract POS-relevant provenance from an Asset and its trials.

    All attributes are read defensively; missing attributes yield a
    ``"not_available"`` item rather than raising.

    Parameters
    ----------
    asset:
        bve.entities.asset.Asset (or duck-typed equivalent).
    trials:
        List of ClinicalTrial objects.
    as_of_date:
        Reference date for staleness checks; defaults to today.

    Returns
    -------
    list[ProvenanceItem]
        One item per key POS input.
    """
    items: list[ProvenanceItem] = []

    # Clinical stage
    stage_val = getattr(asset, "stage", None)
    items.append(ProvenanceItem(
        field="Development stage",
        value=stage_val.value if hasattr(stage_val, "value") else str(stage_val) if stage_val else "Not available",
        source="yaml_config",
        confidence="high",
        notes="Determines which phase-transition base rate applies",
    ))

    # Therapeutic area
    ta_val = getattr(asset, "therapeutic_area", None)
    items.append(ProvenanceItem(
        field="Therapeutic area",
        value=ta_val.value if hasattr(ta_val, "value") else str(ta_val) if ta_val else "Not available",
        source="yaml_config",
        confidence="high",
        notes="Selects TA-specific base rates from industry_assumptions.yaml",
    ))

    # Per-phase POS from trials
    for trial in trials:
        phase_val = getattr(trial, "phase", None)
        success_p = getattr(trial, "success_probability", None)
        if phase_val is None:
            continue
        phase_str = phase_val.value if hasattr(phase_val, "value") else str(phase_val)
        items.append(ProvenanceItem(
            field=f"Success P ({phase_str})",
            value=f"{success_p:.2f}" if success_p is not None else "Not available",
            source="yaml_config",
            confidence="medium",
            notes="Combination of industry base rate + log-odds adjusters",
        ))

    # Breakthrough designation
    bt = getattr(asset, "breakthrough_designation", None)
    if bt is not None:
        items.append(ProvenanceItem(
            field="Breakthrough designation",
            value=str(bt),
            source="yaml_config",
            confidence="high",
            notes="+0.20 log-odds if True",
        ))

    # Biomarker selection
    bm = getattr(asset, "biomarker_selected", None)
    if bm is not None:
        items.append(ProvenanceItem(
            field="Biomarker selection",
            value=str(bm),
            source="yaml_config",
            confidence="high",
            notes="+0.40 log-odds if True",
        ))

    return items


def build_valuation_provenance(
    output: Any,
    *,
    as_of_date: Optional[date] = None,
) -> list[ProvenanceItem]:
    """Extract valuation-relevant provenance from a ValuationOutput.

    Parameters
    ----------
    output:
        bve.valuation.outputs.ValuationOutput (or duck-typed equivalent).
    as_of_date:
        Reference date; defaults to today.

    Returns
    -------
    list[ProvenanceItem]
        One item per key valuation input/output.
    """
    ref = as_of_date or date.today()
    items: list[ProvenanceItem] = []

    company = getattr(output, "company", None)
    rnpv = getattr(output, "rnpv", None)
    market_model = getattr(output, "market_model", None)

    # Peak sales
    peak = getattr(rnpv, "peak_sales_millions", None) if rnpv else None
    items.append(ProvenanceItem(
        field="Peak sales ($M)",
        value=f"{peak:.0f}" if peak is not None else "Not available",
        source="yaml_config",
        confidence="medium" if peak is not None else "not_available",
        notes="Primary revenue driver; see market_model in config",
    ))

    # Discount rate
    dr = getattr(rnpv, "discount_rate", None) if rnpv else None
    items.append(ProvenanceItem(
        field="Discount rate",
        value=f"{dr:.0%}" if dr is not None else "Not available",
        source="yaml_config",
        confidence="high" if dr is not None else "not_available",
    ))

    # Net ownership
    net_own = getattr(rnpv, "net_ownership", None) if rnpv else None
    items.append(ProvenanceItem(
        field="Net ownership",
        value=f"{net_own:.0%}" if net_own is not None else "Not available",
        source="yaml_config",
        confidence="high" if net_own is not None else "not_available",
        notes="1 − royalty_rate; determines shareholder economics",
    ))

    # Current stock price
    price = getattr(company, "current_price", None) if company else None
    stale_warn: Optional[str] = None
    price_as_of: Optional[date] = None
    if price and price > 0:
        price_as_of_raw = getattr(company, "price_as_of", None)
        if price_as_of_raw is not None:
            try:
                price_as_of = (
                    date.fromisoformat(str(price_as_of_raw))
                    if not isinstance(price_as_of_raw, date)
                    else price_as_of_raw
                )
                age = (ref - price_as_of).days
                if age > 30:
                    stale_warn = f"Price is {age} days old (>30d threshold)"
            except (ValueError, TypeError):
                pass
    items.append(ProvenanceItem(
        field="Current price ($)",
        value=f"{price:.2f}" if price and price > 0 else "Not available",
        source="market_data" if price and price > 0 else "not_available",
        as_of=price_as_of,
        staleness_warning=stale_warn,
        confidence="high" if price and price > 0 else "not_available",
        notes="Used to compute implied POS and NAV upside",
    ))

    # Net cash
    net_cash = getattr(company, "net_cash_millions", None) if company else None
    items.append(ProvenanceItem(
        field="Net cash ($M)",
        value=f"{net_cash:.0f}" if net_cash is not None else "Not available",
        source="market_data" if net_cash is not None else "not_available",
        confidence="medium",
        notes="From balance sheet; subtracted from market cap for implied POS",
    ))

    # TAM / peak penetration
    peak_pen = getattr(market_model, "peak_penetration", None) if market_model else None
    if peak_pen is not None:
        items.append(ProvenanceItem(
            field="Peak market penetration",
            value=f"{peak_pen:.0%}",
            source="yaml_config",
            confidence="low",
            notes="Analyst assumption; high sensitivity driver",
        ))

    # Patent life
    pat = getattr(market_model, "patent_life_years", None) if market_model else None
    if pat is not None:
        items.append(ProvenanceItem(
            field="Patent life (years)",
            value=str(pat),
            source="yaml_config",
            confidence="medium",
        ))

    return items


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render_provenance_table(
    items: list[ProvenanceItem],
    *,
    section_title: str = "Assumption Provenance",
) -> str:
    """Render a list of ProvenanceItems as a Markdown table.

    Parameters
    ----------
    items:
        Items to render.
    section_title:
        H2 heading for the section.

    Returns
    -------
    str
        Markdown string with heading and table.
    """
    lines: list[str] = [f"## {section_title}", ""]

    if not items:
        lines.append("_No provenance data available._")
        lines.append("")
        return "\n".join(lines)

    lines.append(
        "| Field | Value | Source | As Of | Confidence | Staleness | Notes |"
    )
    lines.append("|---|---|---|---|---|---|---|")

    for item in items:
        as_of_str = item.as_of.isoformat() if item.as_of else "—"
        stale = f"⚠ {item.staleness_warning}" if item.staleness_warning else "—"
        notes = item.notes or "—"
        value_str = str(item.value) if item.value is not None else "Not available"
        lines.append(
            f"| {item.field} | {value_str} | {item.source} | "
            f"{as_of_str} | {item.confidence} | {stale} | {notes} |"
        )

    lines.append("")
    return "\n".join(lines)
