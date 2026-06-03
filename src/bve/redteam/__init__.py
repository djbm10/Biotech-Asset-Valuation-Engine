"""Red-team / disconfirming evidence engine."""

from .bear_case import BearCase, BearCaseType, Severity, Probability
from .redteam_generator import RedTeamGenerator, RedTeamReport
from .kill_criteria import KillCriteria, KillCriteriaChecker

__all__ = [
    "BearCase", "BearCaseType", "Severity", "Probability",
    "RedTeamGenerator", "RedTeamReport",
    "KillCriteria", "KillCriteriaChecker",
]
