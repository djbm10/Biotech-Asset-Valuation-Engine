"""Tests for hard_negative_generator module."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from bve.backtest_research.deal_seed_loader import DealSeedLoader
from bve.backtest_research.hard_negative_generator import (
    HardNegativeGenerator,
    HardNegativeResult,
)


def _make_deal(target_ticker="SEMMA", ta="diabetes_endocrine", deal_value=950.0):
    """Create a minimal DealRecord for testing."""
    import csv
    import io
    row = {
        "acquirer_ticker": "VRTX",
        "acquirer_name": "Vertex",
        "target_ticker": target_ticker,
        "target_name": "Test Target",
        "deal_type": "full_acquisition",
        "announced_date": "2019-09-03",
        "deal_value_usd_millions": str(deal_value),
        "deal_value_type": "cash",
        "upfront_usd_millions": str(deal_value),
        "cvr_max_usd_millions": "",
        "therapeutic_area": ta,
        "lead_asset": "VX-880",
        "lead_asset_modality": "cell_therapy",
        "lead_asset_stage_at_deal": "preclinical",
        "indication": "type_1_diabetes",
        "verified": "TRUE",
        "verification_source": "vertex_press_release",
        "verification_url": "https://example.com",
        "notes": "test",
    }
    return DealSeedLoader._parse_row(row)


class TestHardNegativeGenerator:
    def test_generates_negatives(self):
        gen = HardNegativeGenerator()
        deal = _make_deal()
        result = gen.generate(
            deal=deal,
            snapshot_date=date(2019, 6, 4),
            days_before=90,
            actual_deal_value_millions=950.0,
            min_negatives=10,
        )
        assert isinstance(result, HardNegativeResult)
        assert result.n_included >= 1

    def test_actual_target_not_in_negatives(self):
        gen = HardNegativeGenerator()
        deal = _make_deal(target_ticker="SEMMA")
        result = gen.generate(
            deal=deal,
            snapshot_date=date(2019, 6, 4),
            days_before=90,
            actual_deal_value_millions=950.0,
        )
        tickers = [c.target_ticker for c in result.candidates]
        assert "SEMMA" not in tickers

    def test_all_negatives_are_not_actual_target(self):
        gen = HardNegativeGenerator()
        deal = _make_deal()
        result = gen.generate(
            deal=deal,
            snapshot_date=date(2019, 6, 4),
            days_before=90,
            actual_deal_value_millions=950.0,
        )
        assert all(not c.is_actual_target for c in result.candidates)

    def test_hearing_loss_ta(self):
        gen = HardNegativeGenerator()
        deal = _make_deal(target_ticker="DBTX", ta="rare_disease_hearing", deal_value=109.0)
        result = gen.generate(
            deal=deal,
            snapshot_date=date(2023, 5, 10),
            days_before=90,
            actual_deal_value_millions=109.0,
        )
        assert result.n_included >= 1

    def test_sufficient_property(self):
        gen = HardNegativeGenerator()
        deal = _make_deal()
        result = gen.generate(
            deal=deal,
            snapshot_date=date(2019, 6, 4),
            days_before=90,
            actual_deal_value_millions=950.0,
            min_negatives=5,
        )
        # sufficient is True when n_included >= 10
        if result.n_included >= 10:
            assert result.sufficient
        else:
            assert not result.sufficient

    def test_none_deal_value_no_affordability_filter(self):
        """When deal value is unknown, affordability filter is skipped."""
        gen = HardNegativeGenerator()
        deal = _make_deal(deal_value=0.0)
        result = gen.generate(
            deal=deal,
            snapshot_date=date(2019, 6, 4),
            days_before=90,
            actual_deal_value_millions=None,
        )
        # Should still return candidates (filter skipped)
        assert result.n_included >= 1
