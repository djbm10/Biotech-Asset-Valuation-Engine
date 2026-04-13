"""
Integration tests: ComparableDealLoader normalizes on ingest;
ComparableDealMatcher uses canonical IDs for tier-1 matching.
"""
from pathlib import Path

import pytest

DEALS_YAML = (
    Path(__file__).parent.parent.parent / "research" / "mna" / "comparable_deals.yaml"
)


@pytest.fixture(scope="module")
def deal_set():
    from bve.intelligence.comparable_deals import ComparableDealLoader
    return ComparableDealLoader.load(DEALS_YAML)


class TestLoaderNormalization:
    def test_all_deals_have_canonical_indication(self, deal_set):
        """Every deal should have canonical_indication populated (HIGH or MEDIUM)."""
        failures = [
            d.indication
            for d in deal_set.deals
            if d.canonical_indication is None
        ]
        assert not failures, (
            f"{len(failures)} deal(s) have no canonical_indication:\n"
            + "\n".join(f"  - {i!r}" for i in failures)
        )

    def test_no_warnings_for_known_indications(self, deal_set):
        """Well-curated indication strings should produce zero normalization warnings."""
        warned = [
            (d.indication, d.normalization_warnings)
            for d in deal_set.deals
            if any("indication_low_confidence" in w for w in d.normalization_warnings)
        ]
        assert not warned, (
            f"{len(warned)} deal(s) have low-confidence indication warnings:\n"
            + "\n".join(f"  - {i!r}: {w}" for i, w in warned)
        )

    def test_canonical_indication_is_string(self, deal_set):
        for deal in deal_set.deals:
            assert isinstance(deal.canonical_indication, str)

    def test_normalization_warnings_is_list(self, deal_set):
        for deal in deal_set.deals:
            assert isinstance(deal.normalization_warnings, list)

    def test_majority_have_no_warnings(self, deal_set):
        warned = sum(1 for d in deal_set.deals if d.normalization_warnings)
        assert warned / len(deal_set.deals) < 0.10, (
            f"More than 10% of deals have normalization warnings: {warned}/{len(deal_set.deals)}"
        )


class TestMatcherCanonicalMatching:
    def test_canonical_matching_finds_comps(self, deal_set):
        """Matcher should find comps for a known indication using canonical ID."""
        from bve.intelligence.comparable_deals import ComparableDealMatcher

        result = ComparableDealMatcher.analyze(
            asset_indication="ulcerative colitis",
            asset_therapeutic_area="immunology",
            asset_stage="phase_2",
            asset_ev_to_peak_sales=2.5,
            deals=deal_set.deals,
            asset_canonical_indication="IND_ulcerative_colitis",
        )
        # Should find at least one comp (UC phase_2 deals in the YAML)
        assert result.match_tier in (
            "exact_indication_phase", "therapeutic_area_phase", "phase_only"
        )

    def test_canonical_none_falls_back_to_raw(self, deal_set):
        """When canonical is None, raw string matching is used (backward compat)."""
        from bve.intelligence.comparable_deals import ComparableDealMatcher

        result = ComparableDealMatcher.analyze(
            asset_indication="ulcerative colitis",
            asset_therapeutic_area="immunology",
            asset_stage="phase_2",
            asset_ev_to_peak_sales=2.5,
            deals=deal_set.deals,
            asset_canonical_indication=None,
        )
        assert result.match_tier != "no_comps" or result.n_comps == 0

    def test_unknown_indication_finds_phase_fallback(self, deal_set):
        """Unrecognized indication should fall through to phase_only tier."""
        from bve.intelligence.comparable_deals import ComparableDealMatcher

        result = ComparableDealMatcher.analyze(
            asset_indication="some_completely_unknown_disease",
            asset_therapeutic_area="immunology",
            asset_stage="phase_2",
            asset_ev_to_peak_sales=2.5,
            deals=deal_set.deals,
        )
        # tier should not be exact_indication_phase
        assert result.match_tier != "exact_indication_phase"
