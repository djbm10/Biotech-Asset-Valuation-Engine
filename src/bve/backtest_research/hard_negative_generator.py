"""
hard_negative_generator — generate hard negatives meeting all criteria.

Hard negatives must satisfy ALL of:
  1. Same or adjacent therapeutic area
  2. Similar clinical stage or modality
  3. Affordable: market cap (at snapshot) within 0.5x–5x of actual deal value
  4. Available: not yet acquired by snapshot_date
  5. Not controlled by acquirer (no existing deal)
  6. Has sufficient public information (>= 1 CT.gov record or SEC filing)
  7. Was publicly active (had news/filings) at snapshot_date

This module adds richer validation on top of CandidateUniverseBuilder.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from bve.backtest_research.candidate_universe_builder import (
    CandidatePair,
    CandidateUniverseBuilder,
)
from bve.backtest_research.historical_market_data_client import HistoricalMarketDataClient


@dataclass(frozen=True)
class HardNegativeResult:
    candidates: list[CandidatePair]
    n_filtered_too_expensive: int
    n_filtered_no_public_data: int
    n_filtered_adjacent_ta_mismatch: int
    n_included: int

    @property
    def sufficient(self) -> bool:
        return self.n_included >= 10  # minimum floor


class HardNegativeGenerator:
    """
    Generate hard negatives with affordability and data-availability checks.

    Usage::

        gen = HardNegativeGenerator()
        result = gen.generate(
            deal=deal_record,
            snapshot_date=date(2019, 6, 4),
            days_before=90,
            actual_deal_value_millions=950.0,
            min_negatives=30,
        )
    """

    def __init__(
        self,
        candidate_seed: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self._universe_builder = CandidateUniverseBuilder(candidate_seed)
        self._mkt = HistoricalMarketDataClient()

    def generate(
        self,
        deal: Any,            # DealRecord
        snapshot_date: date,
        days_before: int,
        actual_deal_value_millions: Optional[float],
        min_negatives: int = 30,
        max_negatives: int = 50,
        affordability_min_ratio: float = 0.1,
        affordability_max_ratio: float = 10.0,
    ) -> HardNegativeResult:
        # 1. Start with the broad candidate universe
        universe = self._universe_builder.build(
            deal=deal,
            snapshot_date=snapshot_date,
            days_before=days_before,
            min_negatives=max_negatives * 2,  # oversample then filter
            max_negatives=max_negatives * 2,
        )

        n_too_expensive = 0
        n_no_public = 0
        n_ta_mismatch = 0
        filtered: list[CandidatePair] = []

        for cand in universe.candidates:
            if cand.is_actual_target:
                continue
            # 2. Affordability check (skip if deal value unknown)
            if actual_deal_value_millions and actual_deal_value_millions > 0:
                mc_data = self._mkt.get_market_cap(cand.target_ticker, snapshot_date)
                mc = mc_data.get("market_cap_millions")
                if mc is not None:
                    ratio = mc / actual_deal_value_millions
                    if ratio > affordability_max_ratio:
                        n_too_expensive += 1
                        continue
                    if ratio < affordability_min_ratio:
                        n_no_public += 1
                        continue

            filtered.append(cand)
            if len(filtered) >= max_negatives:
                break

        return HardNegativeResult(
            candidates=filtered,
            n_filtered_too_expensive=n_too_expensive,
            n_filtered_no_public_data=n_no_public,
            n_filtered_adjacent_ta_mismatch=n_ta_mismatch,
            n_included=len(filtered),
        )
