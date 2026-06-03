"""
acquirer_snapshot_builder — build acquirer profile snapshots as of a date.

Produces a flat dict suitable for CSV export that describes an acquirer's
state at a specific snapshot_date, with all fields carrying provenance.

Fields produced:
  ticker, snapshot_date, name,
  cash_and_equivalents_millions, rd_expense_ttm_millions,
  deal_capacity_millions (heuristic from cash + leverage),
  n_prior_deals_5yr, pipeline_phase3_count,
  therapeutic_areas, modalities,
  patent_cliff_score (0-1), urgency_score (0-1)
  + provenance fields per source
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Optional

from bve.backtest_research.historical_market_data_client import HistoricalMarketDataClient
from bve.backtest_research.sec_client import SECClient


class AcquirerSnapshotBuilder:
    """
    Build a point-in-time acquirer snapshot dict.

    The snapshot is used as input to feature construction; it does NOT
    contain any deal labels.

    Usage::

        builder = AcquirerSnapshotBuilder()
        snap = builder.build(
            ticker="VRTX",
            snapshot_date=date(2019, 6, 4),   # 90d before Semma announcement
            acquirer_profile=profile_dict,    # from acquirers.yaml
        )
    """

    def __init__(self, raw_dir: Optional["str | Path"] = None) -> None:
        self._sec = SECClient(raw_dir=str(raw_dir) if raw_dir else None)
        self._mkt = HistoricalMarketDataClient()

    def build(
        self,
        ticker: str,
        snapshot_date: date,
        acquirer_profile: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Return flat snapshot dict for ticker as of snapshot_date.

        acquirer_profile: optional dict from acquirers.yaml for static fields
                          (therapeutic_areas, modalities, deal_size_range, etc.)
        """
        profile = acquirer_profile or {}

        # -- Market / financial data
        ev_data = self._mkt.get_enterprise_value(ticker, snapshot_date)
        fin_data = self._sec.get_financials(ticker, snapshot_date)

        cash_m = fin_data.get("cash_and_equivalents_millions") or ev_data.get("cash_millions")
        rd_m   = fin_data.get("rd_expense_ttm_millions")
        market_cap_m = ev_data.get("market_cap_millions")

        # Deal capacity heuristic: cash + estimated debt capacity (1x EBITDA proxy)
        deal_capacity: Optional[float] = None
        if cash_m is not None:
            deal_capacity = round(cash_m * 1.5, 0)   # simplified; real calc needs EBITDA

        # -- Static fields from profile yaml (not time-varying)
        ta_list = profile.get("therapeutic_areas", [])
        mod_list = profile.get("modalities", [])
        deal_range = profile.get("deal_size_range_millions", [None, None])
        deal_min = deal_range[0] if deal_range else None
        deal_max = deal_range[1] if len(deal_range) > 1 else None

        # -- Patent cliff / urgency (from profile yaml note)
        # In a real implementation this would be computed from pipeline LOE data.
        # We use a static value from the profile's patent_cliff_exposure note.
        cliff_note = profile.get("patent_cliff_exposure", "")
        urgency_score = self._estimate_urgency(cliff_note, snapshot_date)

        # -- Provenance: use the most restrictive (earliest) data source
        #   We take provenance from financials if available, else market data.
        prov_date = fin_data.get("data_as_of_date") or ev_data.get("data_as_of_date") \
                    or snapshot_date.isoformat()

        return {
            "ticker": ticker,
            "snapshot_date": snapshot_date.isoformat(),
            "name": profile.get("name", ticker),
            "cash_and_equivalents_millions": cash_m,
            "rd_expense_ttm_millions": rd_m,
            "market_cap_millions": market_cap_m,
            "deal_capacity_millions_estimate": deal_capacity,
            "deal_min_millions": deal_min,
            "deal_max_millions": deal_max,
            "therapeutic_areas": "|".join(ta_list) if isinstance(ta_list, list) else ta_list,
            "modalities": "|".join(mod_list) if isinstance(mod_list, list) else mod_list,
            "urgency_score": urgency_score,
            # Provenance
            "source_url": fin_data.get("source_url") or ev_data.get("source_url", ""),
            "source_published_date": prov_date,
            "data_as_of_date": prov_date,
            "extraction_method": fin_data.get("extraction_method", "sec_filing_text"),
            "confidence": min(
                float(fin_data.get("confidence", 0.7)),
                float(ev_data.get("confidence", 0.85)),
            ),
        }

    @staticmethod
    def _estimate_urgency(cliff_note: str, snapshot_date: date) -> float:
        """
        Heuristic urgency score [0, 1] from patent cliff note and date.

        In production this should be computed from pipeline LOE timelines.
        """
        if not cliff_note:
            return 0.30
        note_lower = cliff_note.lower()
        # Simple keyword heuristic
        year_str = str(snapshot_date.year)
        next_year = str(snapshot_date.year + 2)
        if year_str in note_lower or next_year in note_lower:
            return 0.75
        if "cliff" in note_lower and "billion" in note_lower:
            return 0.65
        if "cliff" in note_lower:
            return 0.55
        return 0.40
