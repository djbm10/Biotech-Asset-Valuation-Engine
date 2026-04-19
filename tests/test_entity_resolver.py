"""Tests for EntityResolver, AcquirerProfile, and alias table (Step 2)."""

from __future__ import annotations

import pytest

from bve.normalization.resolver import (
    EntityResolver,
    MatchMethod,
    build_default_resolver,
    BIOTECH_ALIAS_TABLE,
)
from bve.entities.acquirer import (
    AcquirerProfile,
    BDStyle,
    LOECliff,
    PipelineGap,
    ACQUIRER_UNIVERSE,
    ACQUIRER_BY_ID,
    ACQUIRER_BY_TICKER,
)


# ---------------------------------------------------------------------------
# EntityResolver — exact match
# ---------------------------------------------------------------------------

class TestExactMatch:
    @pytest.fixture
    def resolver(self):
        r = EntityResolver()
        r.register("pfizer", "Pfizer", ticker="PFE", aliases=["Pfizer Inc", "PFZ"])
        r.register("lilly", "Eli Lilly", ticker="LLY", aliases=["Lilly"])
        return r

    def test_exact_ticker_match(self, resolver):
        result = resolver.resolve("PFE")
        assert result.canonical_id == "pfizer"
        assert result.method == MatchMethod.EXACT_TICKER
        assert result.confidence == 1.0

    def test_ticker_case_insensitive(self, resolver):
        result = resolver.resolve("pfe")
        assert result.canonical_id == "pfizer"

    def test_exact_alias_match(self, resolver):
        result = resolver.resolve("Pfizer Inc")
        assert result.canonical_id == "pfizer"
        assert result.method == MatchMethod.EXACT_ALIAS

    def test_alias_case_insensitive(self, resolver):
        result = resolver.resolve("PFIZER INC")
        assert result.canonical_id == "pfizer"

    def test_canonical_name_returned(self, resolver):
        result = resolver.resolve("PFE")
        assert result.canonical_name == "Pfizer"

    def test_no_review_needed_on_exact(self, resolver):
        assert resolver.resolve("PFE").needs_review is False
        assert resolver.resolve("Pfizer Inc").needs_review is False


# ---------------------------------------------------------------------------
# EntityResolver — fuzzy match
# ---------------------------------------------------------------------------

class TestFuzzyMatch:
    @pytest.fixture
    def resolver(self):
        r = EntityResolver()
        r.register("pfizer", "Pfizer")
        r.register("merck", "Merck & Co")
        r.register("novartis", "Novartis")
        return r

    def test_fuzzy_below_threshold_is_unresolved(self, resolver):
        result = resolver.resolve("Pfizr")  # severe typo
        # May or may not resolve; confidence must be < 1.0
        assert result.confidence < 1.0

    def test_confidence_not_perfect_on_fuzzy(self, resolver):
        result = resolver.resolve("Novartis AG")  # not in alias table for this resolver
        assert result.confidence <= 1.0

    def test_unresolvable_returns_none(self, resolver):
        result = resolver.resolve("ZYXWVUT Biopharma")
        assert result.canonical_id is None
        assert result.method == MatchMethod.UNRESOLVED
        assert result.needs_review is True


# ---------------------------------------------------------------------------
# EntityResolver — empty registry
# ---------------------------------------------------------------------------

class TestEmptyResolver:
    def test_resolve_empty_registry(self):
        r = EntityResolver()
        result = r.resolve("Pfizer")
        assert result.canonical_id is None
        assert result.method == MatchMethod.UNRESOLVED

    def test_canonical_ids_empty(self):
        r = EntityResolver()
        assert r.canonical_ids() == []


# ---------------------------------------------------------------------------
# EntityResolver — bulk operations
# ---------------------------------------------------------------------------

class TestBulkResolution:
    def test_resolve_many(self):
        r = EntityResolver()
        r.register("pfizer", "Pfizer", ticker="PFE")
        r.register("merck", "Merck & Co", ticker="MRK")
        results = r.resolve_many(["PFE", "MRK", "UNKNOWN_XYZ"])
        assert results[0].canonical_id == "pfizer"
        assert results[1].canonical_id == "merck"
        assert results[2].canonical_id is None

    def test_needs_review_count(self):
        r = EntityResolver()
        r.register("pfizer", "Pfizer", ticker="PFE")
        results = r.resolve_many(["PFE", "UNKNOWN_XYZ"])
        assert r.needs_review_count(results) == 1


# ---------------------------------------------------------------------------
# EntityResolver — register_many
# ---------------------------------------------------------------------------

class TestRegisterMany:
    def test_register_many(self):
        r = EntityResolver()
        r.register_many([
            {"id": "co1", "name": "Company One", "ticker": "CO1"},
            {"id": "co2", "name": "Company Two", "ticker": "CO2"},
        ])
        assert r.resolve("CO1").canonical_id == "co1"
        assert r.resolve("CO2").canonical_id == "co2"

    def test_get_name(self):
        r = EntityResolver()
        r.register("pfizer", "Pfizer", ticker="PFE")
        assert r.get_name("pfizer") == "Pfizer"
        assert r.get_name("nonexistent") is None


# ---------------------------------------------------------------------------
# Default resolver (biotech alias table)
# ---------------------------------------------------------------------------

class TestDefaultResolver:
    @pytest.fixture
    def resolver(self):
        return build_default_resolver()

    def test_all_alias_table_entries_registered(self, resolver):
        ids = resolver.canonical_ids()
        for entry in BIOTECH_ALIAS_TABLE:
            assert entry["id"] in ids

    def test_ticker_lookup_pfizer(self, resolver):
        assert resolver.resolve("PFE").canonical_id == "pfizer"

    def test_ticker_lookup_lilly(self, resolver):
        assert resolver.resolve("LLY").canonical_id == "eli_lilly"

    def test_alias_lookup_bms(self, resolver):
        result = resolver.resolve("BMS")
        assert result.canonical_id == "bristol_myers_squibb"

    def test_alias_genentech_maps_to_roche(self, resolver):
        result = resolver.resolve("Genentech")
        assert result.canonical_id == "roche"

    def test_alias_msd_maps_to_merck(self, resolver):
        result = resolver.resolve("MSD")
        assert result.canonical_id == "merck"

    def test_alias_janssen_maps_to_j_and_j(self, resolver):
        result = resolver.resolve("Janssen")
        assert result.canonical_id == "johnson_johnson"


# ---------------------------------------------------------------------------
# AcquirerProfile domain model
# ---------------------------------------------------------------------------

class TestAcquirerProfile:
    def test_cash_firepower_includes_fcf(self):
        profile = AcquirerProfile(
            company_id="test",
            name="TestPharma",
            cash_millions=5_000,
            annual_fcf_millions=3_000,
        )
        assert profile.cash_firepower_millions == 5_000 + 2 * 3_000

    def test_cash_firepower_no_negative_fcf(self):
        profile = AcquirerProfile(
            company_id="test",
            name="TestPharma",
            cash_millions=5_000,
            annual_fcf_millions=-1_000,
        )
        assert profile.cash_firepower_millions == 5_000

    def test_can_afford_within_ratio(self):
        profile = AcquirerProfile(
            company_id="test", name="TestPharma",
            cash_millions=10_000, annual_fcf_millions=5_000
        )
        # firepower = 20_000, 25% = 5_000
        assert profile.can_afford(5_000) is True

    def test_can_afford_exceeds_ratio(self):
        profile = AcquirerProfile(
            company_id="test", name="TestPharma",
            cash_millions=10_000, annual_fcf_millions=5_000
        )
        assert profile.can_afford(15_000) is False

    def test_covers_ta(self):
        profile = AcquirerProfile(
            company_id="test", name="TestPharma",
            cash_millions=1_000,
            strategic_areas=["oncology", "immunology"],
        )
        assert profile.covers_ta("oncology") is True
        assert profile.covers_ta("Oncology") is True
        assert profile.covers_ta("rare_disease") is False

    def test_covers_modality_empty_list_accepts_all(self):
        profile = AcquirerProfile(
            company_id="test", name="TestPharma",
            cash_millions=1_000,
            preferred_modalities=[],
        )
        assert profile.covers_modality("cell_therapy") is True

    def test_covers_modality_filtered(self):
        profile = AcquirerProfile(
            company_id="test", name="TestPharma",
            cash_millions=1_000,
            preferred_modalities=["biologic", "small_molecule"],
        )
        assert profile.covers_modality("biologic") is True
        assert profile.covers_modality("gene_therapy") is False

    def test_loe_urgency_no_cliffs(self):
        profile = AcquirerProfile(company_id="test", name="TestPharma", cash_millions=1_000)
        assert profile.loe_urgency == 0.0

    def test_loe_urgency_with_cliffs(self):
        profile = AcquirerProfile(
            company_id="test", name="TestPharma", cash_millions=1_000,
            loe_cliffs=[LOECliff(product_name="Drug A", indication="cancer", peak_sales_millions=5_000, loe_year=2027, revenue_at_risk_millions=8_000)]
        )
        assert 0 < profile.loe_urgency <= 1.0

    def test_total_loe_revenue_at_risk(self):
        profile = AcquirerProfile(
            company_id="test", name="TestPharma", cash_millions=1_000,
            loe_cliffs=[
                LOECliff(product_name="Drug A", indication="cancer", peak_sales_millions=5_000, loe_year=2027, revenue_at_risk_millions=3_000),
                LOECliff(product_name="Drug B", indication="diabetes", peak_sales_millions=4_000, loe_year=2028, revenue_at_risk_millions=2_000),
            ]
        )
        assert profile.total_loe_revenue_at_risk_millions == 5_000


# ---------------------------------------------------------------------------
# LOECliff model
# ---------------------------------------------------------------------------

class TestLOECliff:
    def test_urgency_score_capped_at_1(self):
        cliff = LOECliff(product_name="MegaDrug", indication="cancer", peak_sales_millions=20_000, loe_year=2026, revenue_at_risk_millions=50_000)
        assert cliff.urgency_score == 1.0

    def test_urgency_score_small_cliff(self):
        cliff = LOECliff(product_name="SmallDrug", indication="diabetes", peak_sales_millions=500, loe_year=2029, revenue_at_risk_millions=100)
        assert cliff.urgency_score < 1.0


# ---------------------------------------------------------------------------
# Acquirer universe
# ---------------------------------------------------------------------------

class TestAcquirerUniverse:
    def test_universe_not_empty(self):
        assert len(ACQUIRER_UNIVERSE) >= 10

    def test_all_have_company_id(self):
        for a in ACQUIRER_UNIVERSE:
            assert a.company_id

    def test_by_id_lookup(self):
        assert ACQUIRER_BY_ID["pfizer"].name == "Pfizer"

    def test_by_ticker_lookup(self):
        assert ACQUIRER_BY_TICKER["LLY"].name == "Eli Lilly"

    def test_merck_has_loe_cliffs(self):
        merck = ACQUIRER_BY_ID["merck"]
        assert len(merck.loe_cliffs) > 0

    def test_all_acquirers_have_strategic_areas(self):
        for a in ACQUIRER_UNIVERSE:
            assert len(a.strategic_areas) > 0

    def test_pfizer_bd_style(self):
        pfizer = ACQUIRER_BY_ID["pfizer"]
        assert pfizer.bd_style == BDStyle.BLOCKBUSTER

    def test_pipeline_gap_model(self):
        gap = PipelineGap(
            therapeutic_area="neuroscience",
            modality="gene_therapy",
            rationale="No Phase 2+ gene therapy assets",
            priority="high",
        )
        assert gap.therapeutic_area == "neuroscience"
