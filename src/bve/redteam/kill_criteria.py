"""Kill criteria — specific events that would terminate the thesis."""

from __future__ import annotations

from pydantic import BaseModel, Field


class KillCriteria(BaseModel):
    """A specific observable event that would kill the investment thesis."""

    trigger_event: str = Field(description="Specific observable event that kills the thesis")
    bear_case_type: str
    severity: str = "critical"
    monitoring_source: str | None = None
    time_horizon_days: int | None = Field(
        default=None, description="How many days out to monitor for this trigger"
    )

    def describe(self) -> str:
        horizon = f" (within {self.time_horizon_days}d)" if self.time_horizon_days else ""
        return f"[{self.bear_case_type.upper()}]{horizon} {self.trigger_event}"


class KillCriteriaChecker:
    """Validates that a set of bear cases covers all required types and has kill criteria."""

    REQUIRED_TYPES = {
        "clinical",
        "commercial",
        "regulatory",
        "competitive",
        "financing",
        "mna",
    }
    MIN_BEAR_CASES_FOR_ACTIVE_PURSUIT = 3

    def validate(
        self,
        bear_cases: list,
        kill_criteria: list[KillCriteria],
    ) -> tuple[bool, list[str]]:
        """
        Returns (is_valid, list_of_issues).
        For active_pursuit classification, must have >= 3 bear cases and >= 1 kill criterion per bear case.
        """
        issues = []

        if len(bear_cases) < self.MIN_BEAR_CASES_FOR_ACTIVE_PURSUIT:
            issues.append(
                f"Insufficient bear cases: {len(bear_cases)} < minimum {self.MIN_BEAR_CASES_FOR_ACTIVE_PURSUIT}"
            )

        if len(kill_criteria) == 0:
            issues.append("No kill criteria defined — required for active_pursuit")

        covered_types = {kc.bear_case_type for kc in kill_criteria}
        bear_types = {bc.bear_case_type.value for bc in bear_cases}
        uncovered = bear_types - covered_types
        if uncovered:
            issues.append(f"Bear cases without kill criteria: {', '.join(sorted(uncovered))}")

        return len(issues) == 0, issues
