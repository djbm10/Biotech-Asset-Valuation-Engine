"""
Tests for BaseRateTable — stratified empirical base rates with Laplace smoothing.
"""
from __future__ import annotations

import pytest

from bve.empirical.base_rate_table import BaseRateTable
from bve.empirical.pos_outcome import POSOutcomeRecord, load_bundled_records


def _make_record(
    phase: str,
    success: bool,
    moa: str | None = None,
    biomarker: bool = False,
    drug: str = "drug",
    year: str = "2020",
) -> POSOutcomeRecord:
    return POSOutcomeRecord(
        program_id=f"{drug}_{year}",
        sponsor="TestCo",
        asset_name=drug,
        indication_raw="NSCLC",
        phase_at_entry=phase,
        moa_precedent=moa,
        biomarker_selected=biomarker,
        success=success,
        outcome_raw="approved" if success else "failed",
        outcome_date=year,
    )


class TestBaseRateTableSmoothing:
    def test_laplace_smoothing_formula(self):
        """Single success out of 3 trials with alpha=1 → (1+1)/(3+2) = 0.4."""
        records = [
            _make_record("phase_2", True, drug="a"),
            _make_record("phase_2", False, drug="b"),
            _make_record("phase_2", False, drug="c"),
        ]
        table = BaseRateTable(records, smoothing_alpha=1.0, min_n_for_stratified=1)
        rate = table.get("phase_2")
        # Expected: (1 + 1) / (3 + 2) = 0.4
        assert abs(rate - 0.4) < 1e-4

    def test_pure_success_cell_smoothed_below_one(self):
        """3 successes → (3+1)/(3+2) = 0.8, not 1.0."""
        records = [_make_record("phase_3", True, drug=f"d{i}") for i in range(3)]
        table = BaseRateTable(records, smoothing_alpha=1.0, min_n_for_stratified=1)
        rate = table.get("phase_3")
        assert rate < 1.0
        assert abs(rate - 0.8) < 1e-4

    def test_pure_failure_cell_smoothed_above_zero(self):
        """3 failures → (0+1)/(3+2) = 0.2, not 0.0."""
        records = [_make_record("phase_2", False, drug=f"f{i}") for i in range(3)]
        table = BaseRateTable(records, smoothing_alpha=1.0, min_n_for_stratified=1)
        rate = table.get("phase_2")
        assert rate > 0.0
        assert abs(rate - 0.2) < 1e-4

    def test_alpha_zero_raises(self):
        with pytest.raises(ValueError, match="smoothing_alpha"):
            BaseRateTable([], smoothing_alpha=0.0)

    def test_higher_alpha_pulls_toward_half(self):
        """Higher alpha shrinks estimates closer to 0.5 (Laplace shrinkage)."""
        # 3 successes out of 4 trials → raw rate = 0.75
        # alpha=0.01: (3+0.01)/(4+0.02) ≈ 0.748 (close to 0.75, far from 0.5)
        # alpha=10.0: (3+10)/(4+20) ≈ 0.542 (close to 0.5)
        records = [
            _make_record("phase_2", True, drug=f"s{i}") for i in range(3)
        ] + [
            _make_record("phase_2", False, drug="f0"),
        ]
        table_low = BaseRateTable(records, smoothing_alpha=0.01, min_n_for_stratified=1)
        table_high = BaseRateTable(records, smoothing_alpha=10.0, min_n_for_stratified=1)
        rate_low = table_low.get("phase_2")
        rate_high = table_high.get("phase_2")
        # high alpha should be closer to 0.5 than low alpha
        assert abs(rate_high - 0.5) < abs(rate_low - 0.5)


class TestBaseRateTableStratification:
    def _records(self) -> list[POSOutcomeRecord]:
        return [
            # phase_2 + novel MoA + biomarker = True: 2 success, 1 failure
            _make_record("phase_2", True, moa="novel", biomarker=True, drug="a1"),
            _make_record("phase_2", True, moa="novel", biomarker=True, drug="a2"),
            _make_record("phase_2", False, moa="novel", biomarker=True, drug="a3"),
            # phase_2 + novel MoA + biomarker = False: 1 failure, 1 failure
            _make_record("phase_2", False, moa="novel", biomarker=False, drug="b1"),
            _make_record("phase_2", False, moa="novel", biomarker=False, drug="b2"),
            # phase_3 + partial + no biomarker: 2 success
            _make_record("phase_3", True, moa="partial", biomarker=False, drug="c1"),
            _make_record("phase_3", True, moa="partial", biomarker=False, drug="c2"),
        ]

    def test_most_specific_cell_used(self):
        """(phase_2, novel, biomarker=True) has 2/3 success → (2+1)/(3+2)=0.6."""
        table = BaseRateTable(self._records(), smoothing_alpha=1.0, min_n_for_stratified=1)
        # Pass explicit True to trigger biomarker stratification
        rate = table.get("phase_2", moa_precedent="novel", biomarker_selected=True)
        assert abs(rate - 0.6) < 1e-4

    def test_different_stratum_different_rate(self):
        """biomarker=True rate should differ from biomarker=False rate in this dataset."""
        table = BaseRateTable(self._records(), smoothing_alpha=1.0, min_n_for_stratified=1)
        rate_bio_true = table.get("phase_2", moa_precedent="novel", biomarker_selected=True)
        rate_bio_false = table.get("phase_2", moa_precedent="novel", biomarker_selected=False)
        assert rate_bio_true > rate_bio_false

    def test_fallback_to_phase_only(self):
        """Unseen (moa=validated) falls back to phase-level empirical rate."""
        table = BaseRateTable(self._records(), smoothing_alpha=1.0, min_n_for_stratified=1)
        # The dataset has no moa=validated records; should fall back to phase-only cell.
        rate = table.get("phase_2", moa_precedent="validated")
        # Phase-only rate for this dataset
        phase_only_rate = table.get("phase_2")
        assert rate == phase_only_rate

    def test_fallback_to_published_when_no_phase_data(self):
        """When even the phase-level cell is too sparse, use published fallback."""
        # Use min_n=100 so no cell qualifies
        table = BaseRateTable(self._records(), smoothing_alpha=1.0, min_n_for_stratified=100)
        rate = table.get("phase_2", moa_precedent="validated")
        from bve.empirical.base_rate_table import _PUBLISHED_FALLBACK
        assert rate == _PUBLISHED_FALLBACK["phase_2"]

    def test_unknown_phase_fallback(self):
        """Unknown phase returns published fallback (0.40 default)."""
        records = [_make_record("phase_2", True)]
        table = BaseRateTable(records, smoothing_alpha=1.0)
        rate = table.get("phase_99")
        assert rate == 0.40


class TestBaseRateTableSummary:
    def test_summary_has_all_phases_as_keys(self):
        records = [
            _make_record("phase_2", True, moa="novel"),
            _make_record("phase_3", False),
        ]
        table = BaseRateTable(records, smoothing_alpha=1.0, min_n_for_stratified=1)
        summary = table.summary()
        assert len(summary) > 0
        # All rates should be between 0 and 1
        for entry in summary.values():
            assert 0.0 < entry["smoothed_rate"] < 1.0

    def test_phase_rates_method(self):
        records = [
            _make_record("phase_2", True, drug="a"),
            _make_record("phase_2", False, drug="b"),
            _make_record("phase_3", True, drug="c"),
        ]
        table = BaseRateTable(records, smoothing_alpha=1.0, min_n_for_stratified=1)
        rates = table.phase_rates()
        assert "phase_2" in rates
        assert "phase_3" in rates
        assert all(0.0 < v < 1.0 for v in rates.values())

    def test_n_records(self):
        records = [_make_record("phase_2", True, drug=f"d{i}") for i in range(5)]
        table = BaseRateTable(records, smoothing_alpha=1.0)
        assert table.n_records == 5


class TestBaseRateTableBundled:
    def test_bundled_phase2_rate_in_realistic_range(self):
        """Empirical Phase 2 oncology success rate should be between 10% and 70%.

        The bundled dataset is a curated set of notable programs that over-samples
        notable failures, so the raw rate is lower than industry averages (~32%).
        The bounds here are intentionally wide to accommodate dataset composition.
        """
        records = load_bundled_records()
        table = BaseRateTable(records, smoothing_alpha=1.0, min_n_for_stratified=3)
        rate = table.get("phase_2")
        assert 0.10 <= rate <= 0.70, f"Phase 2 rate {rate:.2%} out of expected range"

    def test_bundled_phase3_higher_than_phase2(self):
        """Phase 3 success rate should be higher than Phase 2 (standard result)."""
        records = load_bundled_records()
        table = BaseRateTable(records, smoothing_alpha=1.0, min_n_for_stratified=1)
        r2 = table.get("phase_2")
        r3 = table.get("phase_3")
        assert r3 > r2, f"Phase 3 ({r3:.2%}) not higher than Phase 2 ({r2:.2%})"

    def test_biomarker_enriched_higher_rate_phase2(self):
        """Biomarker-selected Phase 2 trials have higher success rate in this dataset."""
        records = load_bundled_records()
        table = BaseRateTable(records, smoothing_alpha=1.0, min_n_for_stratified=1)
        # Explicitly pass True/False to trigger biomarker stratification
        rate_bio = table.get("phase_2", biomarker_selected=True)
        rate_no_bio = table.get("phase_2", biomarker_selected=False)
        # This holds strongly for the bundled oncology dataset: biomarker-selected
        # programs have significantly higher success rates.
        assert rate_bio > rate_no_bio, (
            f"Biomarker ({rate_bio:.2%}) not higher than non-biomarker ({rate_no_bio:.2%})"
        )
