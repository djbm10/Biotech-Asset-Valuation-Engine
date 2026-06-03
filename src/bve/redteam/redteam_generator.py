"""RedTeamGenerator — produces structured counter-theses for an asset."""

from __future__ import annotations

from dataclasses import dataclass, field

from .bear_case import BearCase, BearCaseType, Probability, Severity
from .kill_criteria import KillCriteria, KillCriteriaChecker


@dataclass
class AssetContext:
    """Minimal context needed to generate bear cases."""

    asset_id: str
    ticker: str
    phase: str
    therapeutic_area: str
    mechanism_of_action: str | None = None
    endpoint_type: str | None = None
    competitive_entrants: int = 0
    cash_runway_months: float = 24.0
    acquirer_interest: str = "unknown"


@dataclass
class RedTeamReport:
    """Full red-team output for an asset."""

    asset_id: str
    ticker: str
    bear_cases: list[BearCase] = field(default_factory=list)
    kill_criteria: list[KillCriteria] = field(default_factory=list)
    is_valid_for_active_pursuit: bool = False
    validation_issues: list[str] = field(default_factory=list)
    total_expected_rnpv_impact_pct: float = 0.0

    def worst_case_impact(self) -> float:
        if not self.bear_cases:
            return 0.0
        return min(bc.rnpv_impact_pct for bc in self.bear_cases)

    def summary(self) -> str:
        lines = [f"Red-Team Report: {self.ticker}"]
        lines.append(f"  Bear cases: {len(self.bear_cases)}")
        lines.append(f"  Kill criteria: {len(self.kill_criteria)}")
        lines.append(f"  Valid for active pursuit: {self.is_valid_for_active_pursuit}")
        if self.validation_issues:
            lines.append("  Issues:")
            for issue in self.validation_issues:
                lines.append(f"    - {issue}")
        lines.append(f"  Worst case rNPV impact: {self.worst_case_impact():.0f}%")
        return "\n".join(lines)


class RedTeamGenerator:
    """Generates structured bear cases and kill criteria from asset context."""

    def generate(self, ctx: AssetContext) -> RedTeamReport:
        bear_cases = self._generate_bear_cases(ctx)
        kill_criteria = self._generate_kill_criteria(ctx, bear_cases)

        checker = KillCriteriaChecker()
        valid, issues = checker.validate(bear_cases, kill_criteria)
        total_expected = sum(bc.expected_impact for bc in bear_cases)

        return RedTeamReport(
            asset_id=ctx.asset_id,
            ticker=ctx.ticker,
            bear_cases=bear_cases,
            kill_criteria=kill_criteria,
            is_valid_for_active_pursuit=valid,
            validation_issues=issues,
            total_expected_rnpv_impact_pct=round(total_expected, 1),
        )

    def _generate_bear_cases(self, ctx: AssetContext) -> list[BearCase]:
        cases = []

        # Clinical bear case
        endpoint_note = (
            f"'{ctx.endpoint_type}' may not satisfy regulatory endpoints"
            if ctx.endpoint_type
            else "Surrogate endpoint may not translate to survival benefit"
        )
        cases.append(
            BearCase(
                bear_case_type=BearCaseType.CLINICAL,
                claim=endpoint_note,
                severity=Severity.HIGH,
                probability=Probability.MEDIUM,
                what_would_confirm="Phase 2/3 data shows no statistically significant benefit on primary endpoint",
                what_would_refute="Phase 2 data shows robust PFS/OS signal with p<0.05",
                rnpv_impact_pct=-75.0,
            )
        )

        # Commercial bear case
        cases.append(
            BearCase(
                bear_case_type=BearCaseType.COMMERCIAL,
                claim="Payer access may be restricted due to cost-effectiveness threshold",
                severity=Severity.MEDIUM,
                probability=Probability.MEDIUM,
                what_would_confirm="CMS/payer issues restrictive coverage policy on drug class",
                what_would_refute="Comparable drug class receives broad payer coverage with minimal step therapy",
                rnpv_impact_pct=-30.0,
            )
        )

        # Regulatory bear case
        cases.append(
            BearCase(
                bear_case_type=BearCaseType.REGULATORY,
                claim="FDA may require additional safety data or raise Complete Response Letter",
                severity=Severity.HIGH,
                probability=Probability.LOW,
                what_would_confirm="FDA issues CRL citing inadequate safety data or manufacturing",
                what_would_refute="FDA grants priority review and schedules PDUFA date on schedule",
                rnpv_impact_pct=-60.0,
            )
        )

        # Competitive bear case
        if ctx.competitive_entrants > 0:
            cases.append(
                BearCase(
                    bear_case_type=BearCaseType.COMPETITIVE,
                    claim=f"{ctx.competitive_entrants} competitor(s) may launch before or alongside asset",
                    severity=Severity.MEDIUM,
                    probability=Probability.MEDIUM,
                    what_would_confirm="Competitor receives FDA approval ahead of schedule",
                    what_would_refute="Competitor trial fails or is delayed by 12+ months",
                    rnpv_impact_pct=-35.0,
                )
            )

        # Financing bear case
        if ctx.cash_runway_months < 18:
            cases.append(
                BearCase(
                    bear_case_type=BearCaseType.FINANCING,
                    claim=f"Cash runway of {ctx.cash_runway_months:.0f} months may be insufficient to reach next catalyst",
                    severity=Severity.HIGH,
                    probability=Probability.HIGH,
                    what_would_confirm="Company announces dilutive offering at current market price",
                    what_would_refute="Company announces non-dilutive partnership or debt financing",
                    rnpv_impact_pct=-20.0,
                )
            )
        else:
            cases.append(
                BearCase(
                    bear_case_type=BearCaseType.FINANCING,
                    claim="Risk-off biotech environment may force dilutive capital raise",
                    severity=Severity.MEDIUM,
                    probability=Probability.LOW,
                    what_would_confirm="XBI falls >30% and company raises equity at >20% discount",
                    what_would_refute="Company executes non-dilutive deal or reaches catalyst before capital needed",
                    rnpv_impact_pct=-15.0,
                )
            )

        # M&A bear case
        cases.append(
            BearCase(
                bear_case_type=BearCaseType.MNA,
                claim="Potential acquirers may fill gap with alternative asset or internal program",
                severity=Severity.MEDIUM,
                probability=Probability.MEDIUM,
                what_would_confirm="Primary acquirer candidate announces competing in-license or acquisition of rival asset",
                what_would_refute="Acquirer confirms pipeline gap persists and this asset remains on watch list",
                rnpv_impact_pct=-25.0,
                mna_score_impact=-0.25,
            )
        )

        return cases

    def _generate_kill_criteria(
        self, ctx: AssetContext, bear_cases: list[BearCase]
    ) -> list[KillCriteria]:
        criteria = []
        for bc in bear_cases:
            criteria.append(
                KillCriteria(
                    trigger_event=bc.what_would_confirm,
                    bear_case_type=bc.bear_case_type.value,
                    severity=bc.severity.value,
                    time_horizon_days=180,
                )
            )
        return criteria
