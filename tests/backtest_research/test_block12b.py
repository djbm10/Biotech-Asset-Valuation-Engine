"""
test_block12b — Block 12B dataset maturity and loader tests.

Covers:
- Bucket CSV minimum candidate counts per deal bucket
- No-deal-year audit coverage (2010–2025 for VRTX and REGN)
- Deal seed label_set integrity
- BucketCandidateLoader filtering by deal_id
- CandidateUniverseBuilder uses BucketCandidateLoader when CSV is available
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path fixtures
# ---------------------------------------------------------------------------

_REPO = Path(__file__).parent.parent.parent

BUCKET_CSV = _REPO / "research/backtests/vrtx_regn_2010/curated/candidate_universe_by_deal_bucket.csv"
NO_DEAL_CSV = _REPO / "research/backtests/vrtx_regn_2010/seeds/no_deal_year_audit.csv"
DEAL_SEED_CSV = _REPO / "research/backtests/vrtx_regn_2010/seeds/deal_seed_vrtx_regn.csv"

_EXPECTED_BUCKETS = [
    "VRTX_SEMMA_2019",
    "VRTX_VIACYTE_2022",
    "VRTX_ALPINE_2024",
    "VRTX_EXONICS_2019",
    "REGN_DECIBEL_2023",
    "REGN_CHECKMATE_2022",
    "REGN_2SEVENTY_2024",
]

_MINIMUM_COUNTS: dict[str, int] = {
    "VRTX_SEMMA_2019":    35,
    "VRTX_ALPINE_2024":   12,
    "REGN_DECIBEL_2023":  10,
    "REGN_CHECKMATE_2022":10,
    "VRTX_EXONICS_2019":  10,
    "VRTX_VIACYTE_2022":  10,
    "REGN_2SEVENTY_2024": 10,
}


def _load_csv(path: Path) -> list[dict]:
    if not path.exists():
        pytest.skip(f"CSV not found: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# BucketCandidateLoader
# ---------------------------------------------------------------------------

class TestBucketCandidateLoader:

    def test_csv_exists(self):
        assert BUCKET_CSV.exists(), f"Bucket CSV missing: {BUCKET_CSV}"

    def test_loader_is_available(self):
        from bve.backtest_research.bucket_candidate_loader import BucketCandidateLoader
        loader = BucketCandidateLoader()
        assert loader.is_available()

    def test_all_expected_buckets_present(self):
        from bve.backtest_research.bucket_candidate_loader import BucketCandidateLoader
        loader = BucketCandidateLoader()
        buckets = loader.available_buckets()
        for expected in _EXPECTED_BUCKETS:
            assert expected in buckets, f"Bucket missing: {expected}"

    def test_load_for_deal_exact_match(self):
        """Exact bucket_name match returns non-empty list."""
        from bve.backtest_research.bucket_candidate_loader import BucketCandidateLoader
        loader = BucketCandidateLoader()
        rows = loader.load_for_deal("VRTX_SEMMA_2019")
        assert len(rows) > 0

    def test_load_for_deal_prefix_match(self):
        """deal_id VRTX_SEMMA_20190903 matches bucket VRTX_SEMMA_2019."""
        from bve.backtest_research.bucket_candidate_loader import BucketCandidateLoader
        loader = BucketCandidateLoader()
        rows = loader.load_for_deal("VRTX_SEMMA_20190903")
        assert len(rows) > 0

    def test_load_for_deal_unknown_returns_empty(self):
        from bve.backtest_research.bucket_candidate_loader import BucketCandidateLoader
        loader = BucketCandidateLoader()
        rows = loader.load_for_deal("NONEXISTENT_DEAL_99999")
        assert rows == []

    def test_normalised_rows_have_required_keys(self):
        from bve.backtest_research.bucket_candidate_loader import BucketCandidateLoader
        loader = BucketCandidateLoader()
        rows = loader.load_for_deal("VRTX_SEMMA_2019")
        required = {"ticker", "name", "ta", "modality", "stage"}
        for row in rows[:5]:
            assert required.issubset(row.keys()), (
                f"Row missing keys: {required - row.keys()}"
            )

    def test_private_prefix_stripped_from_ticker(self):
        """Tickers like private_VCYT should have private_ stripped."""
        from bve.backtest_research.bucket_candidate_loader import BucketCandidateLoader
        loader = BucketCandidateLoader()
        rows = loader.load_for_deal("VRTX_SEMMA_2019")
        for row in rows:
            assert not row["ticker"].startswith("private_"), (
                f"Ticker still has private_ prefix: {row['ticker']}"
            )


# ---------------------------------------------------------------------------
# Bucket CSV minimum counts
# ---------------------------------------------------------------------------

class TestBucketMinimumCounts:

    def _counts_by_bucket(self) -> dict[str, int]:
        rows = _load_csv(BUCKET_CSV)
        counts: dict[str, int] = {}
        for row in rows:
            bucket = row.get("bucket_name", "")
            counts[bucket] = counts.get(bucket, 0) + 1
        return counts

    def test_all_seven_buckets_present_in_csv(self):
        counts = self._counts_by_bucket()
        for bucket in _EXPECTED_BUCKETS:
            assert bucket in counts, f"Bucket not found in CSV: {bucket}"

    @pytest.mark.parametrize("bucket,minimum", _MINIMUM_COUNTS.items())
    def test_bucket_meets_minimum_count(self, bucket: str, minimum: int):
        counts = self._counts_by_bucket()
        actual = counts.get(bucket, 0)
        assert actual >= minimum, (
            f"Bucket {bucket} has only {actual} candidates; need ≥{minimum}"
        )

    def test_no_row_missing_bucket_name(self):
        rows = _load_csv(BUCKET_CSV)
        for i, row in enumerate(rows, 1):
            assert row.get("bucket_name", "").strip(), (
                f"Row {i} has empty bucket_name"
            )

    def test_no_row_missing_candidate_ticker(self):
        rows = _load_csv(BUCKET_CSV)
        for i, row in enumerate(rows, 1):
            assert row.get("candidate_ticker", "").strip(), (
                f"Row {i} has empty candidate_ticker"
            )

    def test_bucket_types_are_valid(self):
        valid_types = {"core", "adjacent", "stretch", "decoy"}
        rows = _load_csv(BUCKET_CSV)
        for i, row in enumerate(rows, 1):
            bt = row.get("bucket_type", "").strip()
            assert bt in valid_types, (
                f"Row {i} has invalid bucket_type '{bt}'; valid: {valid_types}"
            )


# ---------------------------------------------------------------------------
# No-deal year audit coverage
# ---------------------------------------------------------------------------

class TestNoDealYearAudit:

    def test_csv_exists(self):
        assert NO_DEAL_CSV.exists(), f"No-deal audit CSV missing: {NO_DEAL_CSV}"

    def test_vrtx_years_covered_2010_to_2025(self):
        rows = _load_csv(NO_DEAL_CSV)
        vrtx_years = {
            int(r["year"]) for r in rows if r.get("acquirer") == "VRTX"
        }
        for yr in range(2010, 2026):
            assert yr in vrtx_years, f"VRTX year {yr} missing from no-deal audit"

    def test_regn_years_covered_2010_to_2025(self):
        rows = _load_csv(NO_DEAL_CSV)
        regn_years = {
            int(r["year"]) for r in rows if r.get("acquirer") == "REGN"
        }
        for yr in range(2010, 2026):
            assert yr in regn_years, f"REGN year {yr} missing from no-deal audit"

    def test_no_duplicate_acquirer_year(self):
        rows = _load_csv(NO_DEAL_CSV)
        seen: set[tuple[str, str]] = set()
        for r in rows:
            key = (r.get("acquirer", ""), r.get("year", ""))
            assert key not in seen, f"Duplicate row: {key}"
            seen.add(key)

    def test_high_confidence_no_deal_years_have_notes(self):
        rows = _load_csv(NO_DEAL_CSV)
        for r in rows:
            if r.get("no_deal_confidence") == "high":
                assert r.get("notes", "").strip(), (
                    f"High-confidence no-deal row {r.get('acquirer')}/{r.get('year')} has no notes"
                )


# ---------------------------------------------------------------------------
# Deal seed label_set integrity
# ---------------------------------------------------------------------------

class TestDealSeedLabelSets:

    _VALID_LABEL_SETS = {
        "primary_full_company_acquisition",
        "secondary_asset_acquisition",
        "tertiary_rights_or_collaboration",
        "failed_bid_or_lost_auction",
    }

    def test_csv_exists(self):
        assert DEAL_SEED_CSV.exists(), f"Deal seed CSV missing: {DEAL_SEED_CSV}"

    def test_all_rows_have_label_set(self):
        rows = _load_csv(DEAL_SEED_CSV)
        for r in rows:
            ls = r.get("label_set", "").strip()
            assert ls, (
                f"Deal {r.get('acquirer_ticker')}/{r.get('target_ticker')} has empty label_set"
            )

    def test_all_label_sets_are_valid(self):
        rows = _load_csv(DEAL_SEED_CSV)
        for r in rows:
            ls = r.get("label_set", "").strip()
            if ls:
                assert ls in self._VALID_LABEL_SETS, (
                    f"Deal {r.get('acquirer_ticker')}/{r.get('target_ticker')} has "
                    f"unknown label_set '{ls}'"
                )

    def test_verified_deals_are_primary_full_company_acquisition(self):
        rows = _load_csv(DEAL_SEED_CSV)
        for r in rows:
            if r.get("verified", "").upper() == "TRUE":
                assert r.get("label_set") == "primary_full_company_acquisition", (
                    f"Verified deal {r.get('acquirer_ticker')}/{r.get('target_ticker')} "
                    "should be primary_full_company_acquisition"
                )

    def test_rights_deal_is_tertiary(self):
        """Libtayo rights deal from Sanofi must be tertiary, never primary."""
        rows = _load_csv(DEAL_SEED_CSV)
        libtayo = [r for r in rows if r.get("target_ticker") == "LIBTAYO_SANOFI"]
        assert libtayo, "LIBTAYO_SANOFI row missing from deal seed"
        assert libtayo[0].get("label_set") == "tertiary_rights_or_collaboration"

    def test_failed_bid_not_included_in_primary_backtest(self):
        """23andMe failed bid must have include_in_primary_backtest=FALSE."""
        rows = _load_csv(DEAL_SEED_CSV)
        failed = [r for r in rows if r.get("label_set") == "failed_bid_or_lost_auction"]
        assert failed, "No failed_bid_or_lost_auction rows found"
        for r in failed:
            assert r.get("include_in_primary_backtest", "").upper() == "FALSE", (
                f"Failed bid {r.get('target_ticker')} should not be in primary backtest"
            )


# ---------------------------------------------------------------------------
# CandidateUniverseBuilder integration with BucketCandidateLoader
# ---------------------------------------------------------------------------

class TestCandidateUniverseBuilderBucketIntegration:

    def _make_deal(self, deal_id: str, acquirer: str, target: str, ta: str, modality: str, stage: str):
        """Create a minimal DealRecord-like object for testing."""
        from bve.backtest_research.deal_seed_loader import DealRecord
        return DealRecord(
            deal_id=deal_id,
            acquirer_ticker=acquirer,
            acquirer_name=acquirer,
            target_ticker=target,
            target_name=target,
            deal_type="full_acquisition",
            announced_date="2019-09-03",
            deal_value_usd_millions=950.0,
            deal_value_type="cash",
            upfront_usd_millions=950.0,
            cvr_max_usd_millions=0.0,
            therapeutic_area=ta,
            lead_asset="test_asset",
            lead_asset_modality=modality,
            lead_asset_stage_at_deal=stage,
            indication="test_indication",
            verified=True,
            verification_source="test",
            verification_url="https://example.com",
            notes="",
        )

    def test_builder_uses_bucket_csv_when_available(self):
        """Builder should return bucket candidates, not just the 25-company seed."""
        from datetime import date
        from bve.backtest_research.candidate_universe_builder import CandidateUniverseBuilder

        builder = CandidateUniverseBuilder()
        deal = self._make_deal(
            deal_id="VRTX_SEMMA_20190903",
            acquirer="VRTX",
            target="SEMMA",
            ta="diabetes_endocrine",
            modality="cell_therapy",
            stage="preclinical",
        )
        universe = builder.build(
            deal=deal,
            snapshot_date=date(2019, 6, 3),
            days_before=90,
            min_negatives=10,
            max_negatives=60,
        )
        # Must have actual target + at least some negatives
        assert universe.n_candidates >= 2
        actual_targets = [c for c in universe.candidates if c.is_actual_target]
        assert len(actual_targets) == 1

    def test_builder_negatives_come_from_bucket(self):
        """Negatives should have negative_reason='bucket_curated' when bucket CSV is used."""
        from datetime import date
        from bve.backtest_research.candidate_universe_builder import CandidateUniverseBuilder
        from bve.backtest_research.bucket_candidate_loader import BucketCandidateLoader

        if not BucketCandidateLoader().is_available():
            pytest.skip("Bucket CSV not available")

        builder = CandidateUniverseBuilder()
        deal = self._make_deal(
            deal_id="VRTX_SEMMA_20190903",
            acquirer="VRTX",
            target="SEMMA",
            ta="diabetes_endocrine",
            modality="cell_therapy",
            stage="preclinical",
        )
        universe = builder.build(
            deal=deal,
            snapshot_date=date(2019, 6, 3),
            days_before=90,
            min_negatives=5,
            max_negatives=60,
        )
        hard_negatives = [c for c in universe.candidates if c.is_hard_negative]
        assert len(hard_negatives) > 0
        reasons = {c.negative_reason for c in hard_negatives}
        assert "bucket_curated" in reasons, (
            f"Expected bucket_curated reason but got: {reasons}"
        )

    def test_builder_falls_back_to_seed_for_unknown_deal(self):
        """For a deal not in the bucket CSV, fall back to the generic seed."""
        from datetime import date
        from bve.backtest_research.candidate_universe_builder import CandidateUniverseBuilder

        builder = CandidateUniverseBuilder()
        deal = self._make_deal(
            deal_id="UNKNOWN_DEAL_99999",
            acquirer="TEST",
            target="TGT",
            ta="oncology",
            modality="small_molecule",
            stage="phase2",
        )
        universe = builder.build(
            deal=deal,
            snapshot_date=date(2020, 1, 1),
            days_before=90,
            min_negatives=1,
            max_negatives=10,
        )
        # Falls back to seed — should still get the actual target at minimum
        actual_targets = [c for c in universe.candidates if c.is_actual_target]
        assert len(actual_targets) == 1
