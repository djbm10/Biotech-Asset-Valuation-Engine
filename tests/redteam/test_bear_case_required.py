"""Tests for red-team bear case enforcement."""

import pytest

from bve.redteam.bear_case import BearCase, BearCaseType, Probability, Severity
from bve.redteam.kill_criteria import KillCriteria, KillCriteriaChecker
from bve.redteam.redteam_generator import AssetContext, RedTeamGenerator, RedTeamReport


def make_bear_case(bear_case_type=BearCaseType.CLINICAL, severity=Severity.HIGH) -> BearCase:
    return BearCase(
        bear_case_type=bear_case_type,
        claim="Primary endpoint may not be robust",
        evidence="No randomised Phase 2 data",
        severity=severity,
        probability=Probability.MEDIUM,
        what_would_confirm="Phase 3 misses primary endpoint",
        what_would_refute="Phase 2 shows strong PFS signal",
        rnpv_impact_pct=-60.0,
    )


def make_context(**kwargs) -> AssetContext:
    defaults = dict(
        asset_id="VKTX-001",
        ticker="VKTX",
        phase="phase_2",
        therapeutic_area="oncology",
        mechanism_of_action="GLP-1 receptor agonist",
        endpoint_type="PFS",
        competitive_entrants=2,
        cash_runway_months=24.0,
        acquirer_interest="high",
    )
    defaults.update(kwargs)
    return AssetContext(**defaults)


class TestBearCase:
    def test_bear_case_creates_correctly(self):
        bc = make_bear_case()
        assert bc.bear_case_type == BearCaseType.CLINICAL
        assert bc.rnpv_impact_pct == -60.0

    def test_is_critical_for_critical_severity(self):
        bc = make_bear_case(severity=Severity.CRITICAL)
        assert bc.is_critical

    def test_is_not_critical_for_high_severity(self):
        bc = make_bear_case(severity=Severity.HIGH)
        assert not bc.is_critical

    def test_expected_impact_probability_weighted(self):
        bc = BearCase(
            bear_case_type=BearCaseType.CLINICAL,
            claim="test",
            severity=Severity.HIGH,
            probability=Probability.HIGH,  # 0.60
            what_would_confirm="x",
            what_would_refute="y",
            rnpv_impact_pct=-100.0,
        )
        assert abs(bc.expected_impact - (-60.0)) < 0.1

    def test_to_dict_contains_required_keys(self):
        bc = make_bear_case()
        d = bc.to_dict()
        assert "type" in d
        assert "claim" in d
        assert "severity" in d
        assert "rnpv_impact_pct" in d
        assert "expected_impact_pct" in d


class TestKillCriteriaChecker:
    def setup_method(self):
        self.checker = KillCriteriaChecker()

    def _make_full_set(self):
        types = ["clinical", "commercial", "regulatory", "competitive", "financing", "mna"]
        bear_cases = [
            BearCase(
                bear_case_type=BearCaseType(t),
                claim=f"{t} bear case",
                severity=Severity.HIGH,
                probability=Probability.MEDIUM,
                what_would_confirm=f"Confirm {t}",
                what_would_refute=f"Refute {t}",
                rnpv_impact_pct=-30.0,
            )
            for t in types
        ]
        kill_criteria = [
            KillCriteria(trigger_event=f"Kill {t}", bear_case_type=t)
            for t in types
        ]
        return bear_cases, kill_criteria

    def test_valid_with_full_set(self):
        bear_cases, kill_criteria = self._make_full_set()
        valid, issues = self.checker.validate(bear_cases, kill_criteria)
        assert valid
        assert len(issues) == 0

    def test_invalid_when_too_few_bear_cases(self):
        bear_cases = [make_bear_case()]  # only 1, need >= 3
        kill_criteria = [KillCriteria(trigger_event="Kill clinical", bear_case_type="clinical")]
        valid, issues = self.checker.validate(bear_cases, kill_criteria)
        assert not valid
        assert any("Insufficient bear cases" in i for i in issues)

    def test_invalid_when_no_kill_criteria(self):
        bear_cases, _ = self._make_full_set()
        valid, issues = self.checker.validate(bear_cases, [])
        assert not valid
        assert any("kill criteria" in i for i in issues)

    def test_invalid_when_bear_case_missing_kill_criterion(self):
        bear_cases, kill_criteria = self._make_full_set()
        # Remove one kill criterion
        missing_type = kill_criteria[0].bear_case_type
        kill_criteria = kill_criteria[1:]
        valid, issues = self.checker.validate(bear_cases, kill_criteria)
        assert not valid
        assert any(missing_type in i for i in issues)


class TestRedTeamGenerator:
    def setup_method(self):
        self.gen = RedTeamGenerator()

    def test_generates_required_bear_case_types(self):
        ctx = make_context()
        report = self.gen.generate(ctx)
        types = {bc.bear_case_type.value for bc in report.bear_cases}
        assert "clinical" in types
        assert "commercial" in types
        assert "regulatory" in types
        assert "financing" in types
        assert "mna" in types

    def test_generates_at_least_three_bear_cases(self):
        ctx = make_context()
        report = self.gen.generate(ctx)
        assert len(report.bear_cases) >= 3

    def test_generates_kill_criteria_for_each_bear_case(self):
        ctx = make_context()
        report = self.gen.generate(ctx)
        assert len(report.kill_criteria) == len(report.bear_cases)

    def test_is_valid_for_active_pursuit_when_complete(self):
        ctx = make_context()
        report = self.gen.generate(ctx)
        assert report.is_valid_for_active_pursuit

    def test_total_expected_impact_negative(self):
        ctx = make_context()
        report = self.gen.generate(ctx)
        assert report.total_expected_rnpv_impact_pct < 0

    def test_worst_case_impact_is_most_negative(self):
        ctx = make_context()
        report = self.gen.generate(ctx)
        worst = report.worst_case_impact()
        assert all(bc.rnpv_impact_pct >= worst for bc in report.bear_cases)

    def test_low_cash_runway_generates_high_probability_financing_case(self):
        ctx = make_context(cash_runway_months=10)
        report = self.gen.generate(ctx)
        financing = [bc for bc in report.bear_cases if bc.bear_case_type == BearCaseType.FINANCING]
        assert len(financing) >= 1
        assert financing[0].probability == Probability.HIGH

    def test_summary_contains_ticker(self):
        ctx = make_context()
        report = self.gen.generate(ctx)
        summary = report.summary()
        assert "VKTX" in summary
