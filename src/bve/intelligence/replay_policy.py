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
    max_open_positions:
        Maximum number of open positions allowed across the whole replay.
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
    max_open_positions: Optional[int] = None
    max_single_pct: float = 0.05
    max_total_exposure_pct: float = 0.10
    skip_critic_warning: bool = True
    max_hold_days: int = 30
    stop_loss_pct: float = -40.0
    actionable_actions: frozenset = field(
        default_factory=lambda: frozenset({"buy", "add"})
    )
    # Catalyst timing bias (v1 rule)
    # True → apply timing gate before allowing entry.
    # False → ignore catalyst timing (default, backward-compatible).
    catalyst_timing: bool = False
    catalyst_min_days: int = 3    # entry allowed when catalyst is ≥ this many days away
    catalyst_max_days: int = 10   # entry blocked when catalyst is > this many days away
    catalyst_gap_days: int = 2    # < this many days → reduce size by half (gap risk)
    # XBI sector trend filter
    # True → block all new entries when XBI is below its 20-day MA.
    xbi_filter: bool = False
    # Post-loss cooling rule
    # True → after consecutive thesis_errors, skip N cycles for that asset.
    #   1 thesis_error  → skip 1 cycle
    #   2+ consecutive  → skip 2 cycles
    cooling_enabled: bool = False
    # Catalyst density gate
    # 0 = disabled; N>0 = require a catalyst within N days to allow entry.
    require_catalyst_within_days: int = 0
    # Loss-based temporary entry block
    loss_block_threshold_pct: float = -15.0
    loss_block_weeks: int = 8
    # Permanent block after repeated losses
    max_consecutive_losses: int = 3
    # Per-run per-asset concentration cap
    # 0 = no cap; N > 0 = block asset after N decisions this run.
    # Use to prevent any single name dominating the backtest (e.g. ALNY cluster).
    max_decisions_per_asset: int = 0
    # Thesis-strength entry gate
    # 0.0 = disabled (allow all, including None thesis_strength).
    # > 0 = require thesis_strength >= threshold; None thesis_strength also blocked.
    # E.g. 0.5 → only enter when confirmed claims outnumber refuted + expired.
    min_thesis_score: float = 0.0

    @classmethod
    def mna_profile(cls) -> "ReplayPolicyConfig":
        """Return the default replay profile for acquisition/M&A studies."""
        return cls(
            name="mna_top8",
            max_positions=8,
            max_open_positions=8,
            max_single_pct=0.125,
            max_total_exposure_pct=1.0,
            max_hold_days=365,
            stop_loss_pct=-40.0,
            catalyst_timing=False,
            require_catalyst_within_days=0,
            loss_block_threshold_pct=-40.0,
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
        self.reset_run_state()

    def reset_run_state(self) -> None:
        """Reset all per-run blocking state."""
        self._blocked_until: dict[str, date] = {}
        self._consecutive_losses: dict[str, int] = {}
        self._permanently_blocked_asset_ids: set[str] = set()
        self._per_asset_decisions: dict[str, int] = {}

    def record_closed_position(
        self,
        asset_id: str,
        exit_date: date,
        return_pct: Optional[float],
        *,
        force_loss_block: bool = False,
    ) -> None:
        """
        Update per-asset loss state from a newly closed position.

        A sufficiently negative return applies a temporary block, while
        consecutive losing trades can permanently block the asset for the
        remainder of the replay run.
        """
        if return_pct is None:
            return

        if force_loss_block or return_pct <= self.config.loss_block_threshold_pct:
            blocked_until = exit_date + timedelta(weeks=self.config.loss_block_weeks)
            self._blocked_until[asset_id] = blocked_until
            print(
                f"Blocked {asset_id}: prior loss of {return_pct:.1f}% "
                f"on {exit_date.isoformat()}"
            )

        if return_pct < 0.0:
            losses = self._consecutive_losses.get(asset_id, 0) + 1
            self._consecutive_losses[asset_id] = losses
            if (
                losses >= self.config.max_consecutive_losses
                and asset_id not in self._permanently_blocked_asset_ids
            ):
                self._permanently_blocked_asset_ids.add(asset_id)
                print(
                    f"Permanently blocked {asset_id}: {losses} consecutive losses"
                )
            return

        self._consecutive_losses[asset_id] = 0

    def is_asset_blocked(self, asset_id: str, current_date: date) -> bool:
        """Return True when *asset_id* is blocked from new entries."""
        if asset_id in self._permanently_blocked_asset_ids:
            return True

        blocked_until = self._blocked_until.get(asset_id)
        if blocked_until is None:
            return False
        if current_date < blocked_until:
            return True

        self._blocked_until.pop(asset_id, None)
        return False

    def select(
        self,
        report: "WeeklyActionableReport",
        *,
        open_asset_ids: Optional[set] = None,
        current_total_exposure: float = 0.0,
        catalyst_dates: Optional[dict[str, date]] = None,
        xbi_above_ma: Optional[bool] = None,
        cooling_asset_ids: Optional[set] = None,
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
        catalyst_dates:
            Optional mapping of asset_id → next upcoming catalyst date.
            When provided and ``config.catalyst_timing=True``, applies the
            timing gate rule before allowing entry.
        cooling_asset_ids:
            Set of asset_ids currently in a cooling-off period.
            When ``config.cooling_enabled=True``, these are blocked from new entry.

        Returns
        -------
        List of ``ReplayDecision`` objects, at most ``config.max_positions`` long.
        """
        cfg = self.config
        if open_asset_ids is None:
            open_asset_ids = set()

        # XBI sector trend gate: block all new entries in biotech downtrend
        if cfg.xbi_filter and xbi_above_ma is False:
            return []

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
        selected_asset_ids: set[str] = set()
        remaining_exposure = cfg.max_total_exposure_pct - current_total_exposure
        remaining_open_slots: Optional[int] = None
        if cfg.max_open_positions is not None:
            remaining_open_slots = max(0, cfg.max_open_positions - len(open_asset_ids))
            if remaining_open_slots == 0:
                return []

        for opp in candidates:
            if len(decisions) >= cfg.max_positions:
                break
            if remaining_open_slots is not None and len(decisions) >= remaining_open_slots:
                break

            # Skip open positions
            if opp.asset_id in open_asset_ids:
                continue

            if self.is_asset_blocked(opp.asset_id, report.week_ending):
                continue

            # Skip critic warning when configured
            if cfg.skip_critic_warning and opp.critic_severity == "warning":
                continue

            # Post-loss cooling gate
            if cfg.cooling_enabled and cooling_asset_ids and opp.asset_id in cooling_asset_ids:
                continue

            # Catalyst timing gate (v1 rule)
            size_modifier = 1.0
            if cfg.catalyst_timing and catalyst_dates is not None:
                cat_date = catalyst_dates.get(opp.asset_id)
                if cat_date is not None:
                    days_to_cat = (cat_date - report.week_ending).days
                    if days_to_cat > cfg.catalyst_max_days:
                        # Too far from catalyst — not the right entry window
                        continue
                    if days_to_cat < cfg.catalyst_gap_days:
                        # Gap-risk zone — reduce size
                        size_modifier = 0.5
                    # 3–10 days: optimal window, no modification
                # No catalyst on calendar for this asset → allow entry normally

            # Catalyst density gate: require a catalyst within N days
            if cfg.require_catalyst_within_days > 0:
                cat_date = (catalyst_dates or {}).get(opp.asset_id)
                if cat_date is None:
                    # No upcoming catalyst on calendar → skip
                    continue
                days_to_cat = (cat_date - report.week_ending).days
                if days_to_cat > cfg.require_catalyst_within_days:
                    # Nearest catalyst is too far out → skip
                    continue

            # Cap individual size and apply timing modifier
            size = min(opp.recommended_size_pct, cfg.max_single_pct) * size_modifier

            # Cap total exposure
            if remaining_exposure <= 0.0:
                break
            size = min(size, remaining_exposure)

            if size <= 0.0:
                continue

            if opp.asset_id in selected_asset_ids:
                print(
                    f"Skipped duplicate entry for {opp.asset_id} on "
                    f"{report.week_ending.isoformat()}"
                )
                continue

            # Per-run per-asset concentration cap
            if cfg.max_decisions_per_asset > 0:
                prior = self._per_asset_decisions.get(opp.asset_id, 0)
                if prior >= cfg.max_decisions_per_asset:
                    continue

            # Thesis-strength entry gate
            if cfg.min_thesis_score > 0.0:
                ts = getattr(opp, "thesis_strength", None)
                if ts is None or ts < cfg.min_thesis_score:
                    continue

            timing_note = ""
            if cfg.catalyst_timing and catalyst_dates and opp.asset_id in catalyst_dates:
                cat_date = catalyst_dates[opp.asset_id]
                days_to_cat = (cat_date - report.week_ending).days
                timing_note = f"; catalyst_in={days_to_cat}d"

            decisions.append(
                ReplayDecision(
                    asset_id=opp.asset_id,
                    ticker=opp.ticker,
                    recommended_action=opp.recommended_action,
                    recommended_size_pct=round(size, 4),
                    composite_score=opp.composite_score,
                    decided_at=report.week_ending,
                    reasoning=opp.one_line_summary + timing_note,
                    is_simulated=True,
                )
            )
            selected_asset_ids.add(opp.asset_id)
            self._per_asset_decisions[opp.asset_id] = (
                self._per_asset_decisions.get(opp.asset_id, 0) + 1
            )
            remaining_exposure -= size
            if remaining_open_slots is not None:
                remaining_open_slots -= 1

        return decisions

    def exit_date(self, entry_date: date) -> date:
        """Return the forced-exit date for a position opened on *entry_date*."""
        return entry_date + timedelta(days=self.config.max_hold_days)
