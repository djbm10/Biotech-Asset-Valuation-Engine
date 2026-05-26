"""Block 9 — Live Data Refresh & Input Integrity tests.

Covers:
- market_data_refresh: MarketDataSnapshot, fetch_market_snapshot, render
- financial_refresh: FinancialSnapshot, fetch_financial_snapshot, render
- profile_audit: audit_acquirer_profiles, render_profile_audit
- trial_diff: run_trial_diff, TrialChange, render_trial_diff
- input_integrity: build_input_integrity_score, render_input_integrity
- decision_report: InputIntegrityScore wired in
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _today() -> date:
    return date.today()


def _days_ago(n: int) -> date:
    return _today() - timedelta(days=n)


# ---------------------------------------------------------------------------
# MarketDataSnapshot tests
# ---------------------------------------------------------------------------

class TestMarketDataSnapshot:
    def test_to_dict_has_required_keys(self):
        from bve.refresh.market_data_refresh import MarketDataSnapshot
        snap = MarketDataSnapshot(ticker="SRPT", price=50.0)
        d = snap.to_dict()
        for key in ("ticker", "price", "confidence", "source", "as_of"):
            assert key in d

    def test_to_dict_as_of_isoformat(self):
        from bve.refresh.market_data_refresh import MarketDataSnapshot
        snap = MarketDataSnapshot(ticker="SRPT", as_of=date(2025, 6, 1))
        assert snap.to_dict()["as_of"] == "2025-06-01"

    def test_to_dict_no_as_of(self):
        from bve.refresh.market_data_refresh import MarketDataSnapshot
        snap = MarketDataSnapshot(ticker="SRPT")
        assert snap.to_dict()["as_of"] is None

    def test_default_confidence_not_available(self):
        from bve.refresh.market_data_refresh import MarketDataSnapshot
        snap = MarketDataSnapshot(ticker="SRPT")
        assert snap.confidence == "not_available"
        assert snap.source == "not_available"


class TestConfidenceFromAge:
    def test_high_at_zero(self):
        from bve.refresh.market_data_refresh import _confidence_from_age
        assert _confidence_from_age(0) == "high"

    def test_high_at_one(self):
        from bve.refresh.market_data_refresh import _confidence_from_age
        assert _confidence_from_age(1) == "high"

    def test_medium_at_three(self):
        from bve.refresh.market_data_refresh import _confidence_from_age
        assert _confidence_from_age(3) == "medium"

    def test_low_at_fifteen(self):
        from bve.refresh.market_data_refresh import _confidence_from_age
        assert _confidence_from_age(15) == "low"

    def test_stale_at_forty(self):
        from bve.refresh.market_data_refresh import _confidence_from_age
        assert _confidence_from_age(40) == "stale"


class TestFetchMarketSnapshot:
    def _make_raw(self, price=42.0, shares=100.0, market_cap=4200.0):
        return {
            "current_price": price,
            "shares_outstanding_millions": shares,
            "market_cap_millions": market_cap,
            "avg_volume": 500_000,
        }

    def test_live_fetch_success(self):
        from bve.refresh.market_data_refresh import fetch_market_snapshot
        snap = fetch_market_snapshot("SRPT", fetcher=lambda t: self._make_raw())
        assert snap.price == 42.0
        assert snap.source == "yfinance"
        assert snap.confidence == "high"

    def test_live_fetch_derives_market_cap(self):
        from bve.refresh.market_data_refresh import fetch_market_snapshot
        raw = {"current_price": 10.0, "shares_outstanding_millions": 200.0}
        snap = fetch_market_snapshot("SRPT", fetcher=lambda t: raw)
        assert snap.market_cap_millions == pytest.approx(2000.0, abs=1)

    def test_fetcher_error_falls_back_to_yaml(self):
        from bve.refresh.market_data_refresh import fetch_market_snapshot

        def bad_fetcher(t):
            raise RuntimeError("network error")

        override = {"current_price": 30.0, "market_cap_millions": 3000.0, "as_of": "2025-01-01"}
        snap = fetch_market_snapshot("SRPT", fetcher=bad_fetcher, yaml_override=override)
        assert snap.source == "yaml_manual"
        assert snap.price == 30.0

    def test_fetcher_error_no_yaml_returns_not_available(self):
        from bve.refresh.market_data_refresh import fetch_market_snapshot

        def bad_fetcher(t):
            raise RuntimeError("network error")

        snap = fetch_market_snapshot("SRPT", fetcher=bad_fetcher)
        assert snap.source == "not_available"
        assert snap.confidence == "not_available"

    def test_ev_computed_from_market_cap_and_net_cash(self):
        from bve.refresh.market_data_refresh import fetch_market_snapshot
        snap = fetch_market_snapshot(
            "SRPT",
            fetcher=lambda t: self._make_raw(price=10.0, shares=100.0, market_cap=1000.0),
            yaml_override={"net_cash_millions": 200.0},
        )
        assert snap.enterprise_value_millions == pytest.approx(800.0, abs=1)

    def test_yaml_stale_sets_stale_confidence(self):
        from bve.refresh.market_data_refresh import fetch_market_snapshot
        old_date = (_today() - timedelta(days=60)).isoformat()
        override = {"current_price": 25.0, "as_of": old_date}
        snap = fetch_market_snapshot(
            "SRPT",
            fetcher=lambda t: {},
            yaml_override=override,
        )
        # 60 days old → "low" (>5d, ≤30d is low, >30d is stale)
        assert snap.confidence in ("low", "stale")

    def test_ticker_uppercased(self):
        from bve.refresh.market_data_refresh import fetch_market_snapshot
        snap = fetch_market_snapshot("srpt", fetcher=lambda t: self._make_raw())
        assert snap.ticker == "SRPT"

    def test_empty_raw_falls_through_to_not_available(self):
        from bve.refresh.market_data_refresh import fetch_market_snapshot
        snap = fetch_market_snapshot("SRPT", fetcher=lambda t: {})
        assert snap.source == "not_available"


class TestRenderMarketSnapshot:
    def test_renders_markdown_table(self):
        from bve.refresh.market_data_refresh import MarketDataSnapshot, render_market_snapshot
        snap = MarketDataSnapshot(
            ticker="SRPT",
            price=45.0,
            market_cap_millions=4500.0,
            as_of=_today(),
            source="yfinance",
            confidence="high",
        )
        out = render_market_snapshot(snap)
        assert "SRPT" in out
        assert "45.00" in out
        assert "4500" in out

    def test_renders_staleness_warning(self):
        from bve.refresh.market_data_refresh import MarketDataSnapshot, render_market_snapshot
        snap = MarketDataSnapshot(ticker="SRPT", staleness_warning="Price is 45 days old")
        out = render_market_snapshot(snap)
        assert "45 days old" in out

    def test_renders_not_available_for_missing_fields(self):
        from bve.refresh.market_data_refresh import MarketDataSnapshot, render_market_snapshot
        snap = MarketDataSnapshot(ticker="SRPT")
        out = render_market_snapshot(snap)
        assert "Not available" in out


# ---------------------------------------------------------------------------
# FinancialSnapshot tests
# ---------------------------------------------------------------------------

class TestFinancialSnapshot:
    def test_to_dict_has_required_keys(self):
        from bve.refresh.financial_refresh import FinancialSnapshot
        snap = FinancialSnapshot(ticker="SRPT", cash_millions=500.0)
        d = snap.to_dict()
        for key in ("ticker", "cash_millions", "net_cash_millions", "quarterly_burn_millions",
                    "runway_quarters", "confidence", "source"):
            assert key in d

    def test_default_confidence_not_available(self):
        from bve.refresh.financial_refresh import FinancialSnapshot
        snap = FinancialSnapshot(ticker="SRPT")
        assert snap.confidence == "not_available"


class TestFetchFinancialSnapshot:
    def _make_raw(self, cash=600.0, debt=50.0, shares=100.0):
        return {
            "cash_millions": cash,
            "total_debt_millions": debt,
            "shares_outstanding_millions": shares,
        }

    def test_live_fetch_success(self):
        from bve.refresh.financial_refresh import fetch_financial_snapshot
        snap = fetch_financial_snapshot("SRPT", fetcher=lambda t: self._make_raw())
        assert snap.cash_millions == 600.0
        assert snap.source == "yfinance"
        assert snap.confidence == "high"

    def test_net_cash_derived(self):
        from bve.refresh.financial_refresh import fetch_financial_snapshot
        snap = fetch_financial_snapshot("SRPT", fetcher=lambda t: self._make_raw(cash=600.0, debt=50.0))
        assert snap.net_cash_millions == pytest.approx(550.0, abs=1)

    def test_no_debt_net_cash_equals_cash(self):
        from bve.refresh.financial_refresh import fetch_financial_snapshot
        snap = fetch_financial_snapshot(
            "SRPT", fetcher=lambda t: {"cash_millions": 500.0}
        )
        assert snap.net_cash_millions == pytest.approx(500.0)

    def test_quarterly_burn_from_yaml(self):
        from bve.refresh.financial_refresh import fetch_financial_snapshot
        snap = fetch_financial_snapshot(
            "SRPT",
            fetcher=lambda t: {},
            yaml_override={"cash_millions": 500.0, "quarterly_burn_millions": 40.0},
        )
        assert snap.quarterly_burn_millions == 40.0

    def test_quarterly_burn_derived_from_annual_rd(self):
        from bve.refresh.financial_refresh import fetch_financial_snapshot
        snap = fetch_financial_snapshot(
            "SRPT",
            fetcher=lambda t: {"cash_millions": 500.0, "research_development": 160.0},
        )
        assert snap.quarterly_burn_millions == pytest.approx(40.0)

    def test_runway_computed(self):
        from bve.refresh.financial_refresh import fetch_financial_snapshot
        snap = fetch_financial_snapshot(
            "SRPT",
            fetcher=lambda t: {},
            yaml_override={"cash_millions": 400.0, "quarterly_burn_millions": 50.0},
        )
        assert snap.runway_quarters == pytest.approx(8.0)

    def test_fetcher_error_yaml_fallback(self):
        from bve.refresh.financial_refresh import fetch_financial_snapshot

        def bad_fetcher(t):
            raise RuntimeError("network error")

        override = {"cash_millions": 300.0, "as_of": "2025-01-01"}
        snap = fetch_financial_snapshot("SRPT", fetcher=bad_fetcher, yaml_override=override)
        assert snap.source == "yaml_manual"
        assert snap.cash_millions == 300.0

    def test_fetcher_error_no_yaml_returns_not_available(self):
        from bve.refresh.financial_refresh import fetch_financial_snapshot

        snap = fetch_financial_snapshot("SRPT", fetcher=lambda t: None)
        assert snap.source == "not_available"

    def test_ticker_uppercased(self):
        from bve.refresh.financial_refresh import fetch_financial_snapshot
        snap = fetch_financial_snapshot("srpt", fetcher=lambda t: self._make_raw())
        assert snap.ticker == "SRPT"


class TestRenderFinancialSnapshot:
    def test_renders_markdown(self):
        from bve.refresh.financial_refresh import FinancialSnapshot, render_financial_snapshot
        snap = FinancialSnapshot(
            ticker="SRPT",
            cash_millions=600.0,
            net_cash_millions=550.0,
            quarterly_burn_millions=40.0,
            runway_quarters=13.75,
            source="yfinance",
            confidence="high",
            as_of=_today(),
        )
        out = render_financial_snapshot(snap)
        assert "600" in out
        assert "550" in out
        assert "13.8" in out or "13.7" in out  # rounding variation

    def test_staleness_warning_shown(self):
        from bve.refresh.financial_refresh import FinancialSnapshot, render_financial_snapshot
        snap = FinancialSnapshot(ticker="SRPT", staleness_warning="180 days old")
        out = render_financial_snapshot(snap)
        assert "180 days old" in out


# ---------------------------------------------------------------------------
# ProfileAudit tests
# ---------------------------------------------------------------------------

def _make_profile(acquirer_id: str, company_name: str, profile_as_of: date):
    m = MagicMock()
    m.acquirer_id = acquirer_id
    m.company_name = company_name
    m.profile_as_of = profile_as_of
    return m


class TestProfileAudit:
    def test_fresh_profile(self):
        from bve.refresh.profile_audit import audit_acquirer_profiles
        profiles = [_make_profile("pfizer", "Pfizer", _days_ago(30))]
        result = audit_acquirer_profiles(profiles)
        assert result.n_fresh == 1
        assert result.n_stale == 0
        assert result.n_critical == 0
        assert result.overall_confidence_cap is None

    def test_stale_profile(self):
        from bve.refresh.profile_audit import audit_acquirer_profiles
        profiles = [_make_profile("pfizer", "Pfizer", _days_ago(180))]
        result = audit_acquirer_profiles(profiles)
        assert result.n_stale == 1
        assert result.overall_confidence_cap == "medium"

    def test_critical_profile(self):
        from bve.refresh.profile_audit import audit_acquirer_profiles
        profiles = [_make_profile("pfizer", "Pfizer", _days_ago(400))]
        result = audit_acquirer_profiles(profiles)
        assert result.n_critical == 1
        assert result.overall_confidence_cap == "low"

    def test_mixed_profiles(self):
        from bve.refresh.profile_audit import audit_acquirer_profiles
        profiles = [
            _make_profile("a", "A Corp", _days_ago(30)),
            _make_profile("b", "B Corp", _days_ago(180)),
            _make_profile("c", "C Corp", _days_ago(500)),
        ]
        result = audit_acquirer_profiles(profiles)
        assert result.n_fresh == 1
        assert result.n_stale == 1
        assert result.n_critical == 1
        assert result.overall_confidence_cap == "low"

    def test_empty_profiles(self):
        from bve.refresh.profile_audit import audit_acquirer_profiles
        result = audit_acquirer_profiles([])
        assert result.n_fresh == 0
        assert result.n_stale == 0
        assert result.overall_confidence_cap is None

    def test_missing_profile_as_of_treated_as_critical(self):
        from bve.refresh.profile_audit import audit_acquirer_profiles
        m = MagicMock()
        m.acquirer_id = "pfizer"
        m.company_name = "Pfizer"
        m.profile_as_of = None
        result = audit_acquirer_profiles([m])
        assert result.n_critical == 1

    def test_staleness_warning_populated(self):
        from bve.refresh.profile_audit import audit_acquirer_profiles
        profiles = [_make_profile("pfizer", "Pfizer", _days_ago(400))]
        result = audit_acquirer_profiles(profiles)
        assert result.items[0].staleness_warning is not None
        assert "critical" in result.items[0].staleness_warning.lower() or "400" in result.items[0].staleness_warning

    def test_to_dict(self):
        from bve.refresh.profile_audit import audit_acquirer_profiles
        profiles = [_make_profile("pfizer", "Pfizer", _days_ago(30))]
        result = audit_acquirer_profiles(profiles)
        d = result.to_dict()
        assert "n_fresh" in d
        assert "items" in d
        assert len(d["items"]) == 1

    def test_has_stale_profiles_false_when_all_fresh(self):
        from bve.refresh.profile_audit import audit_acquirer_profiles
        profiles = [_make_profile("pfizer", "Pfizer", _days_ago(10))]
        result = audit_acquirer_profiles(profiles)
        assert not result.has_stale_profiles()

    def test_has_stale_profiles_true_when_stale(self):
        from bve.refresh.profile_audit import audit_acquirer_profiles
        profiles = [_make_profile("pfizer", "Pfizer", _days_ago(200))]
        result = audit_acquirer_profiles(profiles)
        assert result.has_stale_profiles()


class TestRenderProfileAudit:
    def test_renders_table(self):
        from bve.refresh.profile_audit import audit_acquirer_profiles, render_profile_audit
        profiles = [
            _make_profile("pfizer", "Pfizer", _days_ago(30)),
            _make_profile("roche", "Roche", _days_ago(200)),
        ]
        result = audit_acquirer_profiles(profiles)
        out = render_profile_audit(result)
        assert "Pfizer" in out
        assert "Roche" in out

    def test_renders_warning_when_stale(self):
        from bve.refresh.profile_audit import audit_acquirer_profiles, render_profile_audit
        profiles = [_make_profile("pfizer", "Pfizer", _days_ago(400))]
        result = audit_acquirer_profiles(profiles)
        out = render_profile_audit(result)
        assert "low" in out.lower() or "critical" in out.lower()

    def test_renders_no_profiles_found(self):
        from bve.refresh.profile_audit import audit_acquirer_profiles, render_profile_audit
        result = audit_acquirer_profiles([])
        out = render_profile_audit(result)
        assert "No acquirer profiles found" in out


# ---------------------------------------------------------------------------
# TrialDiff tests
# ---------------------------------------------------------------------------

class TestStoredTrialRecord:
    def test_default_fields(self):
        from bve.refresh.trial_diff import StoredTrialRecord
        r = StoredTrialRecord(nct_id="NCT123")
        assert r.status is None
        assert r.phase is None
        assert r.enrollment is None


class TestRunTrialDiff:
    def _make_live(self, status="RECRUITING", phase="PHASE2", enrollment=100, title="Test Trial"):
        protocol = {
            "statusModule": {"overallStatus": status},
            "designModule": {
                "phases": [phase],
                "enrollmentInfo": {"count": str(enrollment)},
            },
            "identificationModule": {"briefTitle": title},
        }
        return protocol

    def test_no_changes_when_status_matches(self):
        from bve.refresh.trial_diff import StoredTrialRecord, run_trial_diff
        stored = [StoredTrialRecord(nct_id="NCT123", status="RECRUITING")]
        live_data = {"NCT123": self._make_live(status="RECRUITING")}
        result = run_trial_diff(stored, fetcher=lambda nct: live_data.get(nct))
        assert len([c for c in result.changes if c.change_type == "status_change"]) == 0

    def test_detects_status_change(self):
        from bve.refresh.trial_diff import StoredTrialRecord, run_trial_diff
        stored = [StoredTrialRecord(nct_id="NCT123", status="RECRUITING")]
        live_data = {"NCT123": self._make_live(status="COMPLETED")}
        result = run_trial_diff(stored, fetcher=lambda nct: live_data.get(nct))
        status_changes = [c for c in result.changes if c.change_type == "status_change"]
        assert len(status_changes) == 1
        assert status_changes[0].severity == "high"
        assert status_changes[0].new_value == "COMPLETED"

    def test_detects_phase_change(self):
        from bve.refresh.trial_diff import StoredTrialRecord, run_trial_diff
        stored = [StoredTrialRecord(nct_id="NCT123", phase="PHASE2")]
        live_data = {"NCT123": self._make_live(phase="PHASE3")}
        result = run_trial_diff(stored, fetcher=lambda nct: live_data.get(nct))
        phase_changes = [c for c in result.changes if c.change_type == "phase_change"]
        assert len(phase_changes) == 1
        assert phase_changes[0].severity == "high"

    def test_detects_enrollment_change(self):
        from bve.refresh.trial_diff import StoredTrialRecord, run_trial_diff
        stored = [StoredTrialRecord(nct_id="NCT123", enrollment=100)]
        live_data = {"NCT123": self._make_live(enrollment=150)}
        result = run_trial_diff(stored, fetcher=lambda nct: live_data.get(nct))
        enroll_changes = [c for c in result.changes if c.change_type == "enrollment_change"]
        assert len(enroll_changes) == 1
        assert enroll_changes[0].severity == "medium"

    def test_no_enrollment_change_below_threshold(self):
        from bve.refresh.trial_diff import StoredTrialRecord, run_trial_diff
        stored = [StoredTrialRecord(nct_id="NCT123", enrollment=100)]
        live_data = {"NCT123": self._make_live(enrollment=110)}  # 10% — below 20% threshold
        result = run_trial_diff(stored, fetcher=lambda nct: live_data.get(nct))
        enroll_changes = [c for c in result.changes if c.change_type == "enrollment_change"]
        assert len(enroll_changes) == 0

    def test_not_found_when_fetcher_returns_none(self):
        from bve.refresh.trial_diff import StoredTrialRecord, run_trial_diff
        stored = [StoredTrialRecord(nct_id="NCT999")]
        result = run_trial_diff(stored, fetcher=lambda nct: None)
        not_found = [c for c in result.changes if c.change_type == "not_found"]
        assert len(not_found) == 1
        assert not_found[0].severity == "high"
        assert result.n_not_found == 1

    def test_n_compared_count(self):
        from bve.refresh.trial_diff import StoredTrialRecord, run_trial_diff
        stored = [
            StoredTrialRecord(nct_id="NCT111"),
            StoredTrialRecord(nct_id="NCT222"),
        ]
        result = run_trial_diff(stored, fetcher=lambda nct: self._make_live())
        assert result.n_compared == 2

    def test_high_severity_changes_property(self):
        from bve.refresh.trial_diff import StoredTrialRecord, run_trial_diff
        stored = [StoredTrialRecord(nct_id="NCT123", status="RECRUITING")]
        live_data = {"NCT123": self._make_live(status="TERMINATED")}
        result = run_trial_diff(stored, fetcher=lambda nct: live_data.get(nct))
        assert len(result.high_severity_changes) >= 1

    def test_to_dict(self):
        from bve.refresh.trial_diff import StoredTrialRecord, run_trial_diff
        stored = [StoredTrialRecord(nct_id="NCT123", status="RECRUITING")]
        live_data = {"NCT123": self._make_live(status="COMPLETED")}
        result = run_trial_diff(stored, fetcher=lambda nct: live_data.get(nct))
        d = result.to_dict()
        assert "changes" in d
        assert "n_compared" in d

    def test_title_change_low_severity(self):
        from bve.refresh.trial_diff import StoredTrialRecord, run_trial_diff
        stored = [StoredTrialRecord(nct_id="NCT123", title="Old Title")]
        live_data = {"NCT123": self._make_live(title="New Title")}
        result = run_trial_diff(stored, fetcher=lambda nct: live_data.get(nct))
        title_changes = [c for c in result.changes if c.change_type == "title_change"]
        assert len(title_changes) == 1
        assert title_changes[0].severity == "low"


class TestBuildStoredRecordsFromTrials:
    def test_skips_trials_without_nct_id(self):
        from bve.refresh.trial_diff import build_stored_records_from_trials
        t = MagicMock()
        t.nct_id = None
        records = build_stored_records_from_trials([t])
        assert len(records) == 0

    def test_builds_record_from_trial(self):
        from bve.refresh.trial_diff import build_stored_records_from_trials
        t = MagicMock()
        t.nct_id = "NCT123"
        t.status = MagicMock()
        t.status.value = "RECRUITING"
        t.phase = MagicMock()
        t.phase.value = "PHASE2"
        t.enrollment = 200
        t.title = "A trial"
        records = build_stored_records_from_trials([t])
        assert len(records) == 1
        assert records[0].nct_id == "NCT123"
        assert records[0].status == "RECRUITING"


class TestRenderTrialDiff:
    def test_no_changes_renders_clean(self):
        from bve.refresh.trial_diff import StoredTrialRecord, run_trial_diff, render_trial_diff
        stored = [StoredTrialRecord(nct_id="NCT123")]
        result = run_trial_diff(stored, fetcher=lambda nct: {
            "statusModule": {}, "designModule": {}, "identificationModule": {}
        })
        out = render_trial_diff(result)
        assert "No trial changes detected" in out

    def test_high_severity_shown(self):
        from bve.refresh.trial_diff import StoredTrialRecord, run_trial_diff, render_trial_diff
        stored = [StoredTrialRecord(nct_id="NCT123", status="RECRUITING")]
        result = run_trial_diff(stored, fetcher=lambda nct: {
            "statusModule": {"overallStatus": "TERMINATED"},
            "designModule": {},
            "identificationModule": {},
        })
        out = render_trial_diff(result)
        assert "TERMINATED" in out


# ---------------------------------------------------------------------------
# InputIntegrityScore tests
# ---------------------------------------------------------------------------

def _make_market_snap(confidence="high", staleness_warning=None):
    from bve.refresh.market_data_refresh import MarketDataSnapshot
    return MarketDataSnapshot(
        ticker="SRPT",
        price=50.0,
        source="yfinance",
        confidence=confidence,
        staleness_warning=staleness_warning,
        as_of=_today(),
    )


def _make_fin_snap(confidence="high", staleness_warning=None):
    from bve.refresh.financial_refresh import FinancialSnapshot
    return FinancialSnapshot(
        ticker="SRPT",
        cash_millions=500.0,
        source="yfinance",
        confidence=confidence,
        staleness_warning=staleness_warning,
        as_of=_today(),
    )


def _make_profile_audit(n_fresh=5, n_stale=0, n_critical=0, overall_cap=None):
    from bve.refresh.profile_audit import AcquirerProfileAuditResult
    result = AcquirerProfileAuditResult(
        n_fresh=n_fresh,
        n_stale=n_stale,
        n_critical=n_critical,
        overall_confidence_cap=overall_cap,
        reference_date=_today(),
    )
    return result


def _make_trial_diff(n_compared=3, n_changed=0, n_not_found=0, changes=None):
    from bve.refresh.trial_diff import TrialDiffResult
    return TrialDiffResult(
        changes=changes or [],
        n_compared=n_compared,
        n_changed=n_changed,
        n_not_found=n_not_found,
        run_date=_today(),
    )


class TestInputIntegrityScore:
    def test_all_high_gives_good_score(self):
        from bve.refresh.input_integrity import build_input_integrity_score
        score = build_input_integrity_score(
            market_snapshot=_make_market_snap("high"),
            financial_snapshot=_make_fin_snap("high"),
            profile_audit=_make_profile_audit(n_fresh=5),
            trial_diff=_make_trial_diff(n_compared=3),
        )
        assert score.overall_score >= 0.85
        assert score.overall_grade == "A"

    def test_all_none_gives_zero(self):
        from bve.refresh.input_integrity import build_input_integrity_score
        score = build_input_integrity_score()
        assert score.overall_score == 0.0
        assert score.overall_grade == "D"

    def test_stale_market_reduces_score(self):
        from bve.refresh.input_integrity import build_input_integrity_score
        score = build_input_integrity_score(
            market_snapshot=_make_market_snap("stale"),
        )
        assert score.market_data.score < 0.25
        assert score.market_data.confidence == "stale"

    def test_not_available_market_contributes_zero(self):
        from bve.refresh.input_integrity import build_input_integrity_score
        score = build_input_integrity_score(
            market_snapshot=_make_market_snap("not_available"),
        )
        assert score.market_data.score == 0.0

    def test_staleness_warning_added_to_warnings(self):
        from bve.refresh.input_integrity import build_input_integrity_score
        score = build_input_integrity_score(
            market_snapshot=_make_market_snap("low", staleness_warning="Price is 45 days old"),
        )
        assert any("45 days old" in w for w in score.warnings)

    def test_critical_profiles_reduce_profile_score(self):
        from bve.refresh.input_integrity import build_input_integrity_score
        score = build_input_integrity_score(
            profile_audit=_make_profile_audit(n_fresh=0, n_critical=5, overall_cap="low"),
        )
        assert score.profiles.score < 0.25
        assert score.profiles.confidence == "low"

    def test_trial_high_severity_reduces_trial_score(self):
        from bve.refresh.trial_diff import TrialChange, TrialDiffResult
        from bve.refresh.input_integrity import build_input_integrity_score
        high_change = TrialChange(
            nct_id="NCT123",
            change_type="status_change",
            field_name="overall_status",
            old_value="RECRUITING",
            new_value="TERMINATED",
            severity="high",
            alert_text="Trial NCT123 status changed",
        )
        trial_diff = TrialDiffResult(
            changes=[high_change],
            n_compared=3,
            n_changed=1,
            n_not_found=0,
            run_date=_today(),
        )
        score = build_input_integrity_score(trial_diff=trial_diff)
        assert score.trials.score < 0.25
        assert any("NCT123" in w for w in score.warnings)

    def test_to_dict_structure(self):
        from bve.refresh.input_integrity import build_input_integrity_score
        score = build_input_integrity_score(
            market_snapshot=_make_market_snap("high"),
        )
        d = score.to_dict()
        assert "overall_score" in d
        assert "overall_grade" in d
        assert "surfaces" in d
        assert "market_data" in d["surfaces"]

    def test_grade_a_threshold(self):
        from bve.refresh.input_integrity import _grade
        assert _grade(0.85) == "A"
        assert _grade(1.0) == "A"

    def test_grade_b_threshold(self):
        from bve.refresh.input_integrity import _grade
        assert _grade(0.70) == "B"
        assert _grade(0.84) == "B"

    def test_grade_c_threshold(self):
        from bve.refresh.input_integrity import _grade
        assert _grade(0.50) == "C"
        assert _grade(0.69) == "C"

    def test_grade_d_threshold(self):
        from bve.refresh.input_integrity import _grade
        assert _grade(0.49) == "D"
        assert _grade(0.0) == "D"

    def test_fresh_profile_full_score(self):
        from bve.refresh.input_integrity import build_input_integrity_score
        score = build_input_integrity_score(
            profile_audit=_make_profile_audit(n_fresh=10, n_stale=0, n_critical=0)
        )
        assert score.profiles.score == pytest.approx(0.25, abs=0.01)
        assert score.profiles.confidence == "high"

    def test_mixed_profiles_medium_confidence(self):
        from bve.refresh.input_integrity import build_input_integrity_score
        score = build_input_integrity_score(
            profile_audit=_make_profile_audit(n_fresh=5, n_stale=5, n_critical=0, overall_cap="medium")
        )
        assert score.profiles.confidence == "medium"
        assert score.profiles.score < 0.25


class TestRenderInputIntegrity:
    def test_renders_grade_and_score(self):
        from bve.refresh.input_integrity import build_input_integrity_score, render_input_integrity
        score = build_input_integrity_score(
            market_snapshot=_make_market_snap("high"),
        )
        out = render_input_integrity(score)
        assert "Input Integrity" in out
        assert score.overall_grade in out

    def test_renders_surface_table(self):
        from bve.refresh.input_integrity import build_input_integrity_score, render_input_integrity
        score = build_input_integrity_score(
            market_snapshot=_make_market_snap("medium"),
        )
        out = render_input_integrity(score)
        assert "market_data" in out
        assert "medium" in out

    def test_renders_warnings(self):
        from bve.refresh.input_integrity import build_input_integrity_score, render_input_integrity
        score = build_input_integrity_score(
            market_snapshot=_make_market_snap("stale", staleness_warning="Price is 45 days old"),
        )
        out = render_input_integrity(score)
        assert "45 days old" in out

    def test_no_warnings_section_when_clean(self):
        from bve.refresh.input_integrity import build_input_integrity_score, render_input_integrity
        score = build_input_integrity_score(
            market_snapshot=_make_market_snap("high"),
        )
        out = render_input_integrity(score)
        assert "Integrity warnings" not in out


# ---------------------------------------------------------------------------
# Decision report integration: input_integrity field
# ---------------------------------------------------------------------------

class TestDecisionReportIntegrity:
    def test_integrity_section_present_when_supplied(self):
        from bve.reporting.decision_report import DecisionReportInput, render_decision_report
        from bve.refresh.input_integrity import build_input_integrity_score

        score = build_input_integrity_score(
            market_snapshot=_make_market_snap("high"),
        )
        ri = DecisionReportInput(
            ticker="SRPT",
            input_integrity=score,
        )
        out = render_decision_report(ri)
        assert "Input Integrity" in out

    def test_integrity_section_absent_when_not_supplied(self):
        from bve.reporting.decision_report import DecisionReportInput, render_decision_report

        ri = DecisionReportInput(ticker="SRPT")
        out = render_decision_report(ri)
        # Should render without error, integrity section absent
        assert "SRPT" in out

    def test_report_still_has_disclaimer(self):
        from bve.reporting.decision_report import DecisionReportInput, render_decision_report
        from bve.refresh.input_integrity import build_input_integrity_score

        score = build_input_integrity_score()
        ri = DecisionReportInput(ticker="SRPT", input_integrity=score)
        out = render_decision_report(ri)
        assert "Not investment advice" in out or "Research-grade" in out
