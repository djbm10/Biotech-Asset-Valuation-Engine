"""Tests for enumerating routing candidates from the universe screen."""
from __future__ import annotations

from datetime import date

from bve.discovery.candidate_source import (
    candidates_from_universe,
    enumerate_candidates,
)
from bve.discovery.routing import CandidateCompany
from bve.ops.universe_builder import UniverseCandidate


def _uc(ticker, name, *, passed=True, mktcap=1000.0):
    return UniverseCandidate(
        ticker=ticker, company_name=name, market_cap_m=mktcap, adv_m=5.0,
        as_of=date(2026, 6, 15), has_phase2_plus=True, active_phase2_studies=[],
        passed=passed, exclusion_reason=None if passed else "mktcap",
    )


class TestCandidatesFromUniverse:
    def test_maps_ticker_and_name(self):
        out = candidates_from_universe([_uc("BEAM", "Beam Therapeutics")])
        assert out == [CandidateCompany(ticker="BEAM", company_name="Beam Therapeutics")]

    def test_passed_only_filters_failures(self):
        out = candidates_from_universe([
            _uc("BEAM", "Beam Therapeutics", passed=True),
            _uc("FAIL", "Fail Bio", passed=False),
        ])
        assert [c.ticker for c in out] == ["BEAM"]

    def test_keep_failures_when_passed_only_false(self):
        out = candidates_from_universe(
            [_uc("FAIL", "Fail Bio", passed=False)], passed_only=False
        )
        assert [c.ticker for c in out] == ["FAIL"]

    def test_name_falls_back_to_ticker(self):
        out = candidates_from_universe([_uc("XXXX", "")])
        assert out[0].company_name == "XXXX"

    def test_dedupes_tickers(self):
        out = candidates_from_universe([
            _uc("BEAM", "Beam Therapeutics"),
            _uc("BEAM", "Beam Therapeutics Inc"),
        ])
        assert [c.ticker for c in out] == ["BEAM"]

    def test_limit(self):
        rows = [_uc(f"T{i}", f"Co {i}") for i in range(5)]
        assert len(candidates_from_universe(rows, limit=2)) == 2


class TestEnumerateCandidates:
    def test_uses_injected_builder_and_skips_clinical_by_default(self):
        seen = {}

        def fake_builder(as_of, filt, *, seed_tickers, skip_clinical_check, max_tickers):
            seen["skip_clinical_check"] = skip_clinical_check
            return [_uc("BEAM", "Beam Therapeutics"), _uc("FAIL", "Fail Bio", passed=False)]

        out = enumerate_candidates(builder=fake_builder)
        assert seen["skip_clinical_check"] is True       # routing does its own CT.gov
        assert [c.ticker for c in out] == ["BEAM"]       # failures dropped

    def test_passes_through_max_tickers(self):
        captured = {}

        def fake_builder(as_of, filt, *, seed_tickers, skip_clinical_check, max_tickers):
            captured["max_tickers"] = max_tickers
            return []

        enumerate_candidates(builder=fake_builder, max_tickers=7)
        assert captured["max_tickers"] == 7
