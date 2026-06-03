"""Tests for deal_seed_loader module."""
from __future__ import annotations

import csv
import tempfile
from datetime import date
from pathlib import Path

import pytest

from bve.backtest_research.deal_seed_loader import DealRecord, DealSeedLoader


SAMPLE_CSV = """\
acquirer_ticker,acquirer_name,target_ticker,target_name,deal_type,announced_date,deal_value_usd_millions,deal_value_type,upfront_usd_millions,cvr_max_usd_millions,therapeutic_area,lead_asset,lead_asset_modality,lead_asset_stage_at_deal,indication,verified,verification_source,verification_url,notes
VRTX,Vertex,SEMMA,Semma Therapeutics,full_acquisition,2019-09-03,950.0,cash,950.0,,diabetes_endocrine,VX-880,cell_therapy,preclinical,type_1_diabetes,TRUE,vertex_press_release,https://investors.vrtx.com/news-releases/...,Official PR
VRTX,Vertex,ALPN,Alpine Immune Sciences,full_acquisition,2024-04-10,4900.0,cash,4900.0,,immunology_nephrology,povetacicept,biologic_fusion_protein,phase2,IgA_nephropathy,TRUE,vertex_press_release,https://investors.vrtx.com/news-releases/...,Official PR
REGN,Regeneron,DBTX,Decibel Therapeutics,full_acquisition,2023-08-09,109.0,cash_plus_cvr,109.0,213.0,rare_disease_hearing,DB-OTO,aav_gene_therapy,phase1_2,otoferlin_related_hearing_loss,TRUE,regeneron_press_release,https://investor.regeneron.com/...,Official PR
VRTX,Vertex,VCYT,ViaCyte,full_acquisition,2022-07-18,,,,,diabetes_endocrine,PEC-01,cell_therapy,clinical,type_1_diabetes,FALSE,research_gap,,Unverified
"""


@pytest.fixture
def sample_csv(tmp_path):
    p = tmp_path / "deals.csv"
    p.write_text(SAMPLE_CSV, encoding="utf-8")
    return p


class TestDealSeedLoader:
    def test_load_all_deals(self, sample_csv):
        loader = DealSeedLoader.from_csv(sample_csv)
        assert len(loader.all_deals()) == 4

    def test_verified_deals(self, sample_csv):
        loader = DealSeedLoader.from_csv(sample_csv)
        verified = loader.verified_deals()
        assert len(verified) == 3
        tickers = {d.target_ticker for d in verified}
        assert "SEMMA" in tickers
        assert "ALPN" in tickers
        assert "DBTX" in tickers

    def test_unverified_deals(self, sample_csv):
        loader = DealSeedLoader.from_csv(sample_csv)
        unverified = loader.unverified_deals()
        assert len(unverified) == 1
        assert unverified[0].target_ticker == "VCYT"

    def test_scoring_eligible_excludes_unverified_by_default(self, sample_csv):
        loader = DealSeedLoader.from_csv(sample_csv)
        eligible = loader.scoring_eligible()
        assert len(eligible) == 3   # verified full_acquisitions only
        assert all(d.verified for d in eligible)

    def test_scoring_eligible_includes_unverified_when_flagged(self, sample_csv):
        loader = DealSeedLoader.from_csv(sample_csv)
        eligible = loader.scoring_eligible(include_unverified=True)
        assert len(eligible) == 4

    def test_for_acquirer(self, sample_csv):
        loader = DealSeedLoader.from_csv(sample_csv)
        vrtx = loader.for_acquirer("VRTX")
        assert all(d.acquirer_ticker == "VRTX" for d in vrtx)
        assert len(vrtx) == 2   # SEMMA + ALPN (verified only)

    def test_research_gaps(self, sample_csv):
        loader = DealSeedLoader.from_csv(sample_csv)
        gaps = loader.research_gaps()
        assert len(gaps) == 1
        assert gaps[0].target_ticker == "VCYT"

    def test_deal_id_format(self, sample_csv):
        loader = DealSeedLoader.from_csv(sample_csv)
        deals = loader.all_deals()
        for d in deals:
            assert "_" in d.deal_id
            assert d.acquirer_ticker in d.deal_id
            assert d.target_ticker in d.deal_id

    def test_deal_value_parsed(self, sample_csv):
        loader = DealSeedLoader.from_csv(sample_csv)
        semma = next(d for d in loader.all_deals() if d.target_ticker == "SEMMA")
        assert semma.deal_value_usd_millions == 950.0
        dbtx = next(d for d in loader.all_deals() if d.target_ticker == "DBTX")
        assert dbtx.cvr_max_usd_millions == 213.0

    def test_announced_date_parsed(self, sample_csv):
        loader = DealSeedLoader.from_csv(sample_csv)
        alpn = next(d for d in loader.all_deals() if d.target_ticker == "ALPN")
        assert alpn.announced_date == date(2024, 4, 10)

    def test_is_scoring_eligible(self, sample_csv):
        loader = DealSeedLoader.from_csv(sample_csv)
        for d in loader.verified_deals():
            assert d.is_scoring_eligible  # all are full_acquisition

    def test_default_loader_finds_seed_file(self):
        """Default loader should find the bundled seed CSV."""
        try:
            loader = DealSeedLoader.default()
            assert len(loader.all_deals()) >= 3
        except FileNotFoundError:
            pytest.skip("Seed file not found (expected in repo context)")

    def test_empty_csv(self, tmp_path):
        p = tmp_path / "empty.csv"
        p.write_text("acquirer_ticker,target_ticker,announced_date\n")
        loader = DealSeedLoader.from_csv(p)
        assert loader.all_deals() == []

    def test_invalid_date_skipped(self, tmp_path):
        p = tmp_path / "bad.csv"
        p.write_text(
            "acquirer_ticker,target_ticker,announced_date,deal_type,lead_asset,"
            "therapeutic_area,lead_asset_modality,lead_asset_stage_at_deal,"
            "indication,verified,verification_source,verification_url,"
            "acquirer_name,target_name,deal_value_usd_millions,deal_value_type,"
            "upfront_usd_millions,cvr_max_usd_millions,notes\n"
            "VRTX,FAKE,not-a-date,full_acquisition,drug,ta,mod,stage,ind,TRUE,src,url,Vertex,Fake,,,,,\n"
        )
        loader = DealSeedLoader.from_csv(p)
        assert loader.all_deals() == []
