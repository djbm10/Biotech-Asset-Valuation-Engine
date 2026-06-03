"""Tests for candidate pair schema and CandidateUniverseBuilder."""
from __future__ import annotations

from datetime import date

import pytest

from bve.backtest_research.candidate_universe_builder import (
    CandidatePair,
    CandidateUniverse,
    CandidateUniverseBuilder,
)
from bve.backtest_research.deal_seed_loader import DealSeedLoader


def _make_deal(target_ticker="ALPN", ta="immunology_nephrology"):
    row = {
        "acquirer_ticker": "VRTX",
        "acquirer_name": "Vertex",
        "target_ticker": target_ticker,
        "target_name": "Test",
        "deal_type": "full_acquisition",
        "announced_date": "2024-04-10",
        "deal_value_usd_millions": "4900.0",
        "deal_value_type": "cash",
        "upfront_usd_millions": "4900.0",
        "cvr_max_usd_millions": "",
        "therapeutic_area": ta,
        "lead_asset": "povetacicept",
        "lead_asset_modality": "biologic_fusion_protein",
        "lead_asset_stage_at_deal": "phase2",
        "indication": "IgA_nephropathy",
        "verified": "TRUE",
        "verification_source": "vertex_press_release",
        "verification_url": "https://example.com",
        "notes": "",
    }
    return DealSeedLoader._parse_row(row)


class TestCandidatePairSchema:
    def test_schema_fields_present(self):
        pair = CandidatePair(
            deal_id="VRTX_ALPN_20240410",
            acquirer_ticker="VRTX",
            target_ticker="ALPN",
            target_name="Alpine Immune Sciences",
            snapshot_date="2024-01-10",
            days_before=90,
            is_actual_target=True,
            therapeutic_area="immunology_nephrology",
            modality="biologic_fusion_protein",
            lead_asset_stage="phase2",
            is_hard_negative=False,
        )
        assert pair.deal_id == "VRTX_ALPN_20240410"
        assert pair.is_actual_target is True
        assert pair.days_before == 90

    def test_hard_negative_schema(self):
        pair = CandidatePair(
            deal_id="VRTX_ALPN_20240410",
            acquirer_ticker="VRTX",
            target_ticker="IMVT",
            target_name="Immunovant",
            snapshot_date="2024-01-10",
            days_before=90,
            is_actual_target=False,
            therapeutic_area="immunology",
            modality="biologic_fcrn",
            lead_asset_stage="phase3",
            is_hard_negative=True,
            negative_reason="same_or_adjacent_ta",
        )
        assert pair.is_hard_negative is True
        assert pair.negative_reason == "same_or_adjacent_ta"


class TestCandidateUniverseBuilder:
    def test_universe_contains_actual_target(self):
        builder = CandidateUniverseBuilder()
        deal = _make_deal()
        universe = builder.build(
            deal=deal,
            snapshot_date=date(2024, 1, 10),
            days_before=90,
        )
        actuals = [c for c in universe.candidates if c.is_actual_target]
        assert len(actuals) == 1
        assert actuals[0].target_ticker == "ALPN"

    def test_universe_has_negatives(self):
        builder = CandidateUniverseBuilder()
        deal = _make_deal()
        universe = builder.build(
            deal=deal,
            snapshot_date=date(2024, 1, 10),
            days_before=90,
            min_negatives=5,
        )
        assert universe.n_hard_negatives >= 1

    def test_actual_target_not_in_negatives(self):
        builder = CandidateUniverseBuilder()
        deal = _make_deal(target_ticker="ALPN")
        universe = builder.build(
            deal=deal,
            snapshot_date=date(2024, 1, 10),
            days_before=90,
        )
        negative_tickers = [
            c.target_ticker for c in universe.candidates if not c.is_actual_target
        ]
        assert "ALPN" not in negative_tickers

    def test_n_candidates_property(self):
        builder = CandidateUniverseBuilder()
        deal = _make_deal()
        universe = builder.build(deal=deal, snapshot_date=date(2024, 1, 10), days_before=90)
        assert universe.n_candidates == len(universe.candidates)

    def test_deal_id_propagated(self):
        builder = CandidateUniverseBuilder()
        deal = _make_deal()
        universe = builder.build(deal=deal, snapshot_date=date(2024, 1, 10), days_before=90)
        for c in universe.candidates:
            assert c.deal_id == deal.deal_id

    def test_max_negatives_respected(self):
        builder = CandidateUniverseBuilder()
        deal = _make_deal()
        universe = builder.build(
            deal=deal,
            snapshot_date=date(2024, 1, 10),
            days_before=90,
            max_negatives=5,
        )
        assert universe.n_hard_negatives <= 5
