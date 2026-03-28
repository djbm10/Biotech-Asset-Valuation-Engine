"""
Sprint 12 tests.

12A — POS backtest dataset (data quality guards).
12B — universe_builder.py (offline/mocked tests only; no live yfinance or ClinicalTrials calls).
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

DATASET_PATH = Path(__file__).parents[1] / "research" / "data" / "oncology_phase_transitions.csv"


# ===========================================================================
# Sprint 12A — POS dataset targets
# ===========================================================================

class TestDatasetTargets:
    """Verify updated dataset hits the ~40% Phase 2 / ~60% Phase 3 targets."""

    @pytest.fixture(scope="class")
    def rows(self):
        with open(DATASET_PATH, newline="") as f:
            return list(csv.DictReader(f))

    def _success(self, r: dict) -> bool:
        return r["outcome"] in ("advanced", "approved")

    def test_total_n_at_least_90(self, rows):
        assert len(rows) >= 90, f"Dataset N={len(rows)}, expected ≥ 90 after Sprint 12A additions"

    def test_phase_2_success_rate_near_40pct(self, rows):
        ph2 = [r for r in rows if r["phase_start"] == "phase_2"]
        rate = sum(1 for r in ph2 if self._success(r)) / len(ph2)
        assert 0.35 <= rate <= 0.45, \
            f"Phase 2 success rate {rate:.1%} should be 35–45% (target ~40%)"

    def test_phase_3_success_rate_near_60pct(self, rows):
        ph3 = [r for r in rows if r["phase_start"] == "phase_3"]
        rate = sum(1 for r in ph3 if self._success(r)) / len(ph3)
        assert 0.50 <= rate <= 0.70, \
            f"Phase 3 success rate {rate:.1%} should be 50–70% (target ~60%)"

    def test_overall_success_rate_between_45_and_56pct(self, rows):
        """Balanced dataset: ~50% overall."""
        ph = [r for r in rows if r["phase_start"] in ("phase_2", "phase_3")]
        rate = sum(1 for r in ph if self._success(r)) / len(ph)
        assert 0.45 <= rate <= 0.56, \
            f"Overall success rate {rate:.1%} outside 45–56% target"

    def test_sprint12a_phase3_success_entries_present(self, rows):
        """Spot-check that Sprint 12A Phase 3 success entries were added."""
        ph3_success = {r["drug"] for r in rows
                       if r["phase_start"] == "phase_3" and self._success(r)}
        for expected in ["osimertinib_adj", "pembrolizumab_tnbc", "capivasertib_breast",
                         "belzutifan_rcc", "tarlatamab"]:
            assert expected in ph3_success, f"Expected {expected} in Phase 3 successes"

    def test_sprint12a_phase2_failure_entries_present(self, rows):
        """Spot-check that Sprint 12A Phase 2 failure entries were added."""
        ph2_fail = {r["drug"] for r in rows
                    if r["phase_start"] == "phase_2" and r["outcome"] == "failed"}
        for expected in ["AMG_386", "sapacitabine", "sorafenib_tnbc"]:
            assert expected in ph2_fail, f"Expected {expected} in Phase 2 failures"


# ===========================================================================
# Sprint 12B — universe_builder.py
# ===========================================================================

class TestUniverseFilter:
    def test_default_values(self):
        from bve.ops.universe_builder import UniverseFilter
        f = UniverseFilter()
        assert f.min_mktcap_m == 200.0
        assert f.max_mktcap_m == 10_000.0
        assert f.min_adv_m == 2.0
        assert f.require_phase2_plus is True

    def test_custom_values(self):
        from bve.ops.universe_builder import UniverseFilter
        f = UniverseFilter(min_mktcap_m=500, max_mktcap_m=5000, min_adv_m=5.0)
        assert f.min_mktcap_m == 500


class TestUniverseCandidate:
    def test_passed_candidate(self):
        from bve.ops.universe_builder import UniverseCandidate
        c = UniverseCandidate(
            ticker="VKTX", company_name="Viking Therapeutics",
            market_cap_m=2100.0, adv_m=55.0, as_of=date(2026, 3, 28),
            has_phase2_plus=True, active_phase2_studies=["NCT05234567"],
            sources=["yfinance"], passed=True,
        )
        assert c.passed is True
        assert c.exclusion_reason is None

    def test_filtered_candidate(self):
        from bve.ops.universe_builder import UniverseCandidate
        c = UniverseCandidate(
            ticker="TINY", company_name="Tiny Bio",
            market_cap_m=50.0, adv_m=0.1, as_of=date(2026, 3, 28),
            has_phase2_plus=False, active_phase2_studies=[],
            sources=["yfinance"], passed=False,
            exclusion_reason="mktcap_$50M < min_$200M",
        )
        assert c.passed is False
        assert "mktcap" in c.exclusion_reason


class TestBuildUniverseOffline:
    """Tests that mock both yfinance and ClinicalTrials.gov calls."""

    def _fake_mdata(self, ticker: str, mktcap_m: float = 2000.0, adv_m: float = 30.0):
        return {
            "market_cap_m": mktcap_m,
            "adv_m": adv_m,
            "company_name": f"{ticker} Inc.",
            "current_price": 15.0,
        }

    @patch("bve.ops.universe_builder._fetch_market_data")
    def test_passes_when_all_criteria_met(self, mock_fetch):
        from bve.ops.universe_builder import UniverseFilter, build_universe
        mock_fetch.return_value = self._fake_mdata("VKTX")

        results = build_universe(
            date(2026, 3, 28), UniverseFilter(),
            seed_tickers=["VKTX"],
            skip_clinical_check=True,
        )
        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].ticker == "VKTX"

    @patch("bve.ops.universe_builder._fetch_market_data")
    def test_excluded_when_mktcap_too_small(self, mock_fetch):
        from bve.ops.universe_builder import UniverseFilter, build_universe
        mock_fetch.return_value = self._fake_mdata("TINY", mktcap_m=50.0)

        results = build_universe(
            date(2026, 3, 28), UniverseFilter(min_mktcap_m=200.0),
            seed_tickers=["TINY"],
            skip_clinical_check=True,
        )
        assert results[0].passed is False
        assert "mktcap" in results[0].exclusion_reason

    @patch("bve.ops.universe_builder._fetch_market_data")
    def test_excluded_when_mktcap_too_large(self, mock_fetch):
        from bve.ops.universe_builder import UniverseFilter, build_universe
        mock_fetch.return_value = self._fake_mdata("BIG", mktcap_m=50_000.0)

        results = build_universe(
            date(2026, 3, 28), UniverseFilter(max_mktcap_m=10_000.0),
            seed_tickers=["BIG"],
            skip_clinical_check=True,
        )
        assert results[0].passed is False
        assert "mktcap" in results[0].exclusion_reason

    @patch("bve.ops.universe_builder._fetch_market_data")
    def test_excluded_when_adv_too_low(self, mock_fetch):
        from bve.ops.universe_builder import UniverseFilter, build_universe
        mock_fetch.return_value = self._fake_mdata("ILLIQUID", adv_m=0.5)

        results = build_universe(
            date(2026, 3, 28), UniverseFilter(min_adv_m=2.0),
            seed_tickers=["ILLIQUID"],
            skip_clinical_check=True,
        )
        assert results[0].passed is False
        assert "adv" in results[0].exclusion_reason

    @patch("bve.ops.universe_builder._fetch_market_data")
    def test_market_data_unavailable_excluded(self, mock_fetch):
        from bve.ops.universe_builder import UniverseFilter, build_universe
        mock_fetch.return_value = None

        results = build_universe(
            date(2026, 3, 28), UniverseFilter(),
            seed_tickers=["UNKNOWN"],
            skip_clinical_check=True,
        )
        assert results[0].passed is False
        assert results[0].exclusion_reason == "market_data_unavailable"

    @patch("bve.ops.universe_builder._has_phase2_plus_trials")
    @patch("bve.ops.universe_builder._fetch_market_data")
    def test_excluded_when_no_phase2_trials(self, mock_fetch, mock_ct):
        from bve.ops.universe_builder import UniverseFilter, build_universe
        mock_fetch.return_value = self._fake_mdata("PRECLIN")
        mock_ct.return_value = (False, [])

        results = build_universe(
            date(2026, 3, 28),
            UniverseFilter(require_phase2_plus=True),
            seed_tickers=["PRECLIN"],
        )
        assert results[0].passed is False
        assert results[0].exclusion_reason == "no_active_phase2_plus_trials"

    @patch("bve.ops.universe_builder._has_phase2_plus_trials")
    @patch("bve.ops.universe_builder._fetch_market_data")
    def test_passed_with_phase2_trials(self, mock_fetch, mock_ct):
        from bve.ops.universe_builder import UniverseFilter, build_universe
        mock_fetch.return_value = self._fake_mdata("KYMR")
        mock_ct.return_value = (True, ["NCT04570267"])

        results = build_universe(
            date(2026, 3, 28),
            UniverseFilter(require_phase2_plus=True),
            seed_tickers=["KYMR"],
        )
        assert results[0].passed is True
        assert results[0].active_phase2_studies == ["NCT04570267"]

    @patch("bve.ops.universe_builder._fetch_market_data")
    def test_sorted_passed_first_then_by_mktcap(self, mock_fetch):
        from bve.ops.universe_builder import UniverseFilter, build_universe

        def side_effect(ticker, *args, **kwargs):
            return {"VKTX": self._fake_mdata("VKTX", mktcap_m=2100.0, adv_m=55.0),
                    "TINY": self._fake_mdata("TINY", mktcap_m=50.0, adv_m=1.0),
                    "KYMR": self._fake_mdata("KYMR", mktcap_m=1800.0, adv_m=40.0)
                    }.get(ticker)

        mock_fetch.side_effect = side_effect
        results = build_universe(
            date(2026, 3, 28), UniverseFilter(),
            seed_tickers=["TINY", "KYMR", "VKTX"],
            skip_clinical_check=True,
        )
        passed = [c for c in results if c.passed]
        # Passed tickers sorted by mktcap desc
        assert passed[0].ticker == "VKTX"
        assert passed[1].ticker == "KYMR"
        # TINY should be excluded (mktcap too small)
        excluded = [c for c in results if not c.passed]
        assert excluded[0].ticker == "TINY"

    @patch("bve.ops.universe_builder._fetch_market_data")
    def test_require_phase2_false_skips_clinical_check(self, mock_fetch):
        from bve.ops.universe_builder import UniverseFilter, build_universe
        mock_fetch.return_value = self._fake_mdata("NOPIPELINE")

        results = build_universe(
            date(2026, 3, 28),
            UniverseFilter(require_phase2_plus=False),
            seed_tickers=["NOPIPELINE"],
        )
        assert results[0].passed is True

    @patch("bve.ops.universe_builder._fetch_market_data")
    def test_max_tickers_limits_evaluation(self, mock_fetch):
        from bve.ops.universe_builder import UniverseFilter, build_universe
        mock_fetch.return_value = self._fake_mdata("X")
        results = build_universe(
            date(2026, 3, 28), UniverseFilter(),
            max_tickers=5,
            skip_clinical_check=True,
        )
        assert len(results) == 5


class TestUniverseSnapshotPersistence:
    """Test KnowledgeStore write/read for universe_snapshots."""

    def _make_candidates(self):
        from bve.ops.universe_builder import UniverseCandidate
        return [
            UniverseCandidate(
                ticker="VKTX", company_name="Viking Therapeutics",
                market_cap_m=2100.0, adv_m=55.0, as_of=date(2026, 3, 28),
                has_phase2_plus=True, active_phase2_studies=["NCT05234567"],
                sources=["yfinance", "clinicaltrials"], passed=True,
            ),
            UniverseCandidate(
                ticker="TINY", company_name="Tiny Bio",
                market_cap_m=50.0, adv_m=0.1, as_of=date(2026, 3, 28),
                has_phase2_plus=False, active_phase2_studies=[],
                sources=["yfinance"], passed=False,
                exclusion_reason="mktcap_$50M < min_$200M",
            ),
        ]

    def test_write_and_read_back(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "test.db")
        candidates = self._make_candidates()
        n = store.write_universe_snapshot(candidates)
        assert n == 2

        result = store.get_universe_snapshot()
        assert len(result) == 2
        tickers = {r["ticker"] for r in result}
        assert tickers == {"VKTX", "TINY"}
        store.close()

    def test_passed_only_filter(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "test.db")
        store.write_universe_snapshot(self._make_candidates())
        passed = store.get_universe_snapshot(passed_only=True)
        assert len(passed) == 1
        assert passed[0]["ticker"] == "VKTX"
        assert passed[0]["passed"] is True
        store.close()

    def test_nct_ids_round_trip(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "test.db")
        store.write_universe_snapshot(self._make_candidates())
        result = store.get_universe_snapshot()
        vktx = next(r for r in result if r["ticker"] == "VKTX")
        assert vktx["active_nct_ids"] == ["NCT05234567"]
        store.close()

    def test_upsert_replaces_same_ticker_date(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        from bve.ops.universe_builder import UniverseCandidate
        store = KnowledgeStore(tmp_path / "test.db")
        c1 = UniverseCandidate(
            ticker="VKTX", company_name="Viking v1",
            market_cap_m=2000.0, adv_m=50.0, as_of=date(2026, 3, 28),
            has_phase2_plus=True, active_phase2_studies=[],
            sources=["yfinance"], passed=True,
        )
        c2 = UniverseCandidate(
            ticker="VKTX", company_name="Viking v2",
            market_cap_m=2200.0, adv_m=55.0, as_of=date(2026, 3, 28),
            has_phase2_plus=True, active_phase2_studies=["NCT99999"],
            sources=["yfinance"], passed=True,
        )
        store.write_universe_snapshot([c1])
        store.write_universe_snapshot([c2])
        result = store.get_universe_snapshot()
        vktx = [r for r in result if r["ticker"] == "VKTX"]
        assert len(vktx) == 1
        assert vktx[0]["market_cap_m"] == 2200.0
        store.close()

    def test_list_build_dates(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        from bve.ops.universe_builder import UniverseCandidate
        store = KnowledgeStore(tmp_path / "test.db")
        c1 = UniverseCandidate(
            ticker="VKTX", company_name="Viking",
            market_cap_m=2000.0, adv_m=50.0, as_of=date(2026, 3, 21),
            has_phase2_plus=True, active_phase2_studies=[],
            sources=["yfinance"], passed=True,
        )
        c2 = UniverseCandidate(
            ticker="VKTX", company_name="Viking",
            market_cap_m=2100.0, adv_m=55.0, as_of=date(2026, 3, 28),
            has_phase2_plus=True, active_phase2_studies=[],
            sources=["yfinance"], passed=True,
        )
        store.write_universe_snapshot([c1])
        store.write_universe_snapshot([c2])
        dates = store.list_universe_build_dates()
        assert dates[0] == date(2026, 3, 28)  # most recent first
        assert dates[1] == date(2026, 3, 21)
        store.close()

    def test_empty_db_returns_empty(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "test.db")
        assert store.get_universe_snapshot() == []
        assert store.list_universe_build_dates() == []
        store.close()
