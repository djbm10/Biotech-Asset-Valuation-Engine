"""AssetState — composite per-ticker state container.

Wraps existing refresh snapshots (MarketDataSnapshot, FinancialSnapshot,
InputIntegrityScore) with clinical trial records and valuation inputs into a
single, serialisable object that the DB layer persists.

Design rules
------------
- No scoring logic here; pure data container.
- All numeric fields are ``None`` when unavailable.
- ``AssetState.is_stale()`` is the canonical freshness check for downstream callers.
- ``ProvenanceItem`` is re-exported from ``bve.reporting.provenance`` — no new type.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from bve.refresh.financial_refresh import FinancialSnapshot
from bve.refresh.input_integrity import InputIntegrityScore
from bve.refresh.market_data_refresh import MarketDataSnapshot
from bve.reporting.provenance import ProvenanceItem


# ---------------------------------------------------------------------------
# ClinicalAssetState
# ---------------------------------------------------------------------------

@dataclass
class ClinicalAssetState:
    """One clinical-stage asset / trial record for a ticker."""

    nct_id: str
    asset_name: str
    phase: str
    indication: str
    primary_endpoint: Optional[str] = None
    estimated_completion: Optional[date] = None
    status: str = "unknown"   # active | completed | terminated | unknown
    last_synced: Optional[date] = None

    def to_dict(self) -> dict:
        return {
            "nct_id": self.nct_id,
            "asset_name": self.asset_name,
            "phase": self.phase,
            "indication": self.indication,
            "primary_endpoint": self.primary_endpoint,
            "estimated_completion": (
                self.estimated_completion.isoformat()
                if self.estimated_completion else None
            ),
            "status": self.status,
            "last_synced": (
                self.last_synced.isoformat() if self.last_synced else None
            ),
        }

    @classmethod
    def from_dict(cls, d: dict) -> ClinicalAssetState:
        return cls(
            nct_id=d.get("nct_id", ""),
            asset_name=d.get("asset_name", ""),
            phase=d.get("phase", "unknown"),
            indication=d.get("indication", ""),
            primary_endpoint=d.get("primary_endpoint"),
            estimated_completion=_parse_date(d.get("estimated_completion")),
            status=d.get("status", "unknown"),
            last_synced=_parse_date(d.get("last_synced")),
        )


# ---------------------------------------------------------------------------
# ValuationInputState
# ---------------------------------------------------------------------------

@dataclass
class ValuationInputState:
    """Snapshot of the valuation parameters used for this ticker."""

    peak_sales_millions: Optional[float] = None
    wacc: float = 0.12
    years_to_peak: Optional[int] = None
    patent_life_years: Optional[int] = None
    is_screening_grade: bool = True
    config_path: Optional[str] = None
    last_run: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "peak_sales_millions": self.peak_sales_millions,
            "wacc": self.wacc,
            "years_to_peak": self.years_to_peak,
            "patent_life_years": self.patent_life_years,
            "is_screening_grade": self.is_screening_grade,
            "config_path": self.config_path,
            "last_run": self.last_run.isoformat() if self.last_run else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ValuationInputState:
        lr = d.get("last_run")
        return cls(
            peak_sales_millions=d.get("peak_sales_millions"),
            wacc=d.get("wacc", 0.12),
            years_to_peak=d.get("years_to_peak"),
            patent_life_years=d.get("patent_life_years"),
            is_screening_grade=d.get("is_screening_grade", True),
            config_path=d.get("config_path"),
            last_run=datetime.fromisoformat(lr) if lr else None,
        )


# ---------------------------------------------------------------------------
# AssetState — top-level container
# ---------------------------------------------------------------------------

@dataclass
class AssetState:
    """Unified state for one tracked ticker.

    Parameters
    ----------
    ticker:
        Uppercase stock ticker.
    company_name:
        Full company name.
    market_data:
        Live price / market cap snapshot (from refresh layer).
    financials:
        Cash, debt, burn, runway (from refresh layer).
    clinical_assets:
        Tracked clinical programs for this company.
    valuation_inputs:
        Valuation parameter snapshot used in the last run.
    source_provenance:
        List of provenance items tracking where each key value came from.
    last_refreshed:
        Date the state was last written to the DB.
    integrity_score:
        Aggregated input freshness score across all four refresh surfaces.
    """

    ticker: str
    company_name: str
    market_data: MarketDataSnapshot
    financials: FinancialSnapshot
    clinical_assets: list[ClinicalAssetState] = field(default_factory=list)
    valuation_inputs: ValuationInputState = field(default_factory=ValuationInputState)
    source_provenance: list[ProvenanceItem] = field(default_factory=list)
    last_refreshed: date = field(default_factory=date.today)
    integrity_score: InputIntegrityScore = field(default_factory=InputIntegrityScore)

    # ------------------------------------------------------------------
    # Convenience queries
    # ------------------------------------------------------------------

    def is_stale(self, threshold_days: int = 90) -> bool:
        """Return True when last_refreshed is older than *threshold_days*."""
        age = (date.today() - self.last_refreshed).days
        return age > threshold_days

    def has_valuation(self) -> bool:
        """Return True when at least one valuation run has been recorded."""
        return self.valuation_inputs.last_run is not None

    def screening_grade(self) -> bool:
        """Return True when the valuation inputs are screening-grade."""
        return self.valuation_inputs.is_screening_grade

    def provenance_for(self, field_name: str) -> Optional[ProvenanceItem]:
        """Return the first ProvenanceItem matching *field_name*, or None."""
        for item in self.source_provenance:
            if item.field == field_name:
                return item
        return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _parse_date(v: object) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v).split("T")[0])
    except (ValueError, AttributeError):
        return None
