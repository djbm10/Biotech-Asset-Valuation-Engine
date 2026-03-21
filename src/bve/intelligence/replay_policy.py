"""Rules-based executor for replay. Deterministic. No LLM calls."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from bve.intelligence.actionable_output import WeeklyActionableReport


# ---------------------------------------------------------------------------
# ReplayDecision
# ---------------------------------------------------------------------------

@dataclass
class ReplayDecision:
    """One simulated investment decision produced by ReplayPolicy."""

    asset_id: str
    ticker: str
    recommended_action: str
    recommended_size_pct: float
    composite_score: float
    decided_at: date
    reasoning: str = ""
    is_simulated: bool = True


# ---------------------------------------------------------------------------
# ReplayPolicyConfig
# ---------------------------------------------------------------------------

@dataclass
class ReplayPolicyConfig:
    """
    Configuration for the ``top2_add`` replay policy.

    Parameters
    ----------
    name:
        Policy identifier (used for run metadata).
    max_positions:
        Maximum number of decisions per step.
    max_single_pct:
        Maximum allocation for any single position (0–1).
    max_total_exposure_pct:
        Maximum total new exposure added in a single step (0–1).
    skip_critic_warning:
        When True, candidates with ``critic_severity == "warning"`` are skipped.
    max_hold_days:
        Maximum number of calendar days to hold a position before forced exit.
    actionable_actions:
        Set of action labels that are considered actionable (buy/add).
    """

    name: str = "top2_add"
    max_positions: int = 2
    max_single_pct: float = 0.05
    max_total_exposure_pct: float = 0.10
    skip_critic_warning: bool = True
    max_hold_days: int = 30
    actionable_actions: frozenset = field(
        default_factory=lambda: frozenset({"buy", "add"})
    )


# ---------------------------------------------------------------------------
# ReplayPolicy
# ---------------------------------------------------------------------------

class ReplayPolicy:
    """
    Deterministic decision selector for replay runs.

    Implements the ``top2_add`` strategy:
    - Take top ``max_positions`` BUY/ADD opportunities by composite score.
    - Skip assets in ``open_asset_ids``.
    - Skip critic_severity == "warning" when ``skip_critic_warning=True``.
    - Cap individual position at ``max_single_pct``.
    - Cap total new exposure at ``max_total_exposure_pct``.
    """

    def __init__(self, config: Optional[ReplayPolicyConfig] = None) -> None:
        self.config = config or ReplayPolicyConfig()

    def select(
        self,
        report: "WeeklyActionableReport",
        *,
        open_asset_ids: Optional[set] = None,
        current_total_exposure: float = 0.0,
    ) -> list[ReplayDecision]:
        """
        Produce a deterministic list of decisions from a WeeklyActionableReport.

        Parameters
        ----------
        report:
            The ``WeeklyActionableReport`` to evaluate.
        open_asset_ids:
            Set of asset IDs that are already in open positions (skip them).
        current_total_exposure:
            Existing total exposure fraction (0–1); limits additional allocation.

        Returns
        -------
        List of ``ReplayDecision`` objects, at most ``config.max_positions`` long.
        """
        cfg = self.config
        if open_asset_ids is None:
            open_asset_ids = set()

        # Filter candidates to actionable actions only
        candidates = [
            opp
            for opp in report.opportunities
            if opp.recommended_action in cfg.actionable_actions
        ]

        # Deterministic sort: highest composite_score first, then ticker as tiebreaker
        candidates = sorted(
            candidates,
            key=lambda o: (-o.composite_score, o.ticker),
        )

        decisions: list[ReplayDecision] = []
        remaining_exposure = cfg.max_total_exposure_pct - current_total_exposure

        for opp in candidates:
            if len(decisions) >= cfg.max_positions:
                break

            # Skip open positions
            if opp.asset_id in open_asset_ids:
                continue

            # Skip critic warning when configured
            if cfg.skip_critic_warning and opp.critic_severity == "warning":
                continue

            # Cap individual size
            size = min(opp.recommended_size_pct, cfg.max_single_pct)

            # Cap total exposure
            if remaining_exposure <= 0.0:
                break
            size = min(size, remaining_exposure)

            if size <= 0.0:
                continue

            decisions.append(
                ReplayDecision(
                    asset_id=opp.asset_id,
                    ticker=opp.ticker,
                    recommended_action=opp.recommended_action,
                    recommended_size_pct=round(size, 4),
                    composite_score=opp.composite_score,
                    decided_at=report.week_ending,
                    reasoning=opp.one_line_summary,
                    is_simulated=True,
                )
            )
            remaining_exposure -= size

        return decisions

    def exit_date(self, entry_date: date) -> date:
        """Return the forced-exit date for a position opened on *entry_date*."""
        return entry_date + timedelta(days=self.config.max_hold_days)
