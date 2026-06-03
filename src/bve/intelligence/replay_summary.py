"""Aggregated metrics over one completed replay run."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class ReplaySummary:
    """
    Aggregated performance and attribution metrics for a completed replay run.

    Attributes
    ----------
    run_id:
        UUID of the replay run.
    start_date, end_date:
        Date range the replay covered.
    strategy_version:
        Human-readable strategy label (e.g. "top2_add").
    score_version:
        Scoring regime version used (e.g. "v1.0").
    n_decision_dates:
        Number of decision steps (weeks) in the run.
    n_decisions:
        Total simulated decisions made.
    n_actionable:
        Decisions with action "buy" or "add".
    n_resolved:
        Decisions that were closed (exit price recorded).
    mean_return_pct:
        Average return across closed decisions (None if no closed decisions).
    hit_rate:
        Fraction of closed decisions with return_pct > 0 (None if none).
    n_confirmed_thesis:
        Closed decisions attributed as ``confirmed_thesis``.
    n_pos_error:
        Closed decisions attributed as ``pos_error``.
    n_timing_error:
        Closed decisions attributed as ``timing_error``.
    n_thesis_error:
        Closed decisions attributed as ``thesis_error``.
    n_market_drift:
        Closed decisions attributed as ``market_drift``.
    n_stop_loss:
        Closed decisions attributed as ``stop_loss``.
    n_unclassified:
        Closed decisions with no clear attribution.
    returns_by_action:
        Dict mapping action label → list of return_pct values.
    n_skipped_critic_warning:
        Number of candidates skipped due to critic_severity == "warning".
    notes:
        Free-text notes appended during summarize().
    """

    run_id: str
    start_date: date
    end_date: date
    strategy_version: str
    score_version: str
    n_decision_dates: int = 0
    n_decisions: int = 0
    n_actionable: int = 0
    n_resolved: int = 0
    mean_return_pct: Optional[float] = None
    gross_mean_return_pct: Optional[float] = None
    net_mean_return_pct: Optional[float] = None
    friction_cost_mean_bps: Optional[float] = None
    friction_model_label: str = "institutional"
    hit_rate: Optional[float] = None
    brier_score: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    avg_return_by_tier: dict[str, float] = field(default_factory=dict)
    mna_precision_at_k: Optional[float] = None
    mna_top_k: Optional[int] = None
    mna_acquirer_top1_accuracy: Optional[float] = None
    mna_acquirer_top3_accuracy: Optional[float] = None
    n_dead_or_acquired_names_in_universe: int = 0
    n_confirmed_thesis: int = 0
    n_pos_error: int = 0
    n_timing_error: int = 0
    n_thesis_error: int = 0
    n_market_drift: int = 0
    n_stop_loss: int = 0
    n_unclassified: int = 0
    returns_by_action: dict = field(default_factory=dict)
    returns_by_attribution: dict[str, list[float]] = field(default_factory=dict)
    mean_return_by_attribution: dict[str, Optional[float]] = field(default_factory=dict)
    median_return_by_attribution: dict[str, Optional[float]] = field(default_factory=dict)
    pnl_contribution_by_attribution: dict[str, Optional[float]] = field(default_factory=dict)
    n_independent_decisions: int = 0
    n_skipped_critic_warning: int = 0
    notes: list[str] = field(default_factory=list)

    # ---------- skill-adjusted return (Sprint 1) ----------------------------
    # pos_error decisions: model scored positive but event was negative;
    # position still made money (luck, not skill). These are excluded from
    # skill-adjusted return so the stat does not overstate validated alpha.
    skill_adjusted_mean_return_pct: Optional[float] = None
    n_skill_adjusted_decisions: int = 0

    # ---------- XBI-adjusted alpha ------------------------------------------
    # alpha = return_pct - xbi_return_during_hold per closed decision.
    # Measures how much of the return was idiosyncratic vs. sector beta.
    mean_xbi_return_pct: Optional[float] = None
    mean_alpha_pct: Optional[float] = None
    alpha_hit_rate: Optional[float] = None   # fraction of decisions where alpha > 0
    n_with_xbi_data: int = 0                 # decisions with non-null xbi_return_during_hold

    # Validation status — must always be displayed on human-readable output
    validation_status: str = "directional_only"

    def to_dict(self) -> dict:
        """Serialise to a plain dict (JSON-compatible)."""
        return {
            "run_id": self.run_id,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "strategy_version": self.strategy_version,
            "score_version": self.score_version,
            "n_decision_dates": self.n_decision_dates,
            "n_decisions": self.n_decisions,
            "n_actionable": self.n_actionable,
            "n_resolved": self.n_resolved,
            "mean_return_pct": self.mean_return_pct,
            "gross_mean_return_pct": self.gross_mean_return_pct,
            "net_mean_return_pct": self.net_mean_return_pct,
            "friction_cost_mean_bps": self.friction_cost_mean_bps,
            "friction_model_label": self.friction_model_label,
            "hit_rate": self.hit_rate,
            "brier_score": self.brier_score,
            "max_drawdown_pct": self.max_drawdown_pct,
            "avg_return_by_tier": self.avg_return_by_tier,
            "mna_precision_at_k": self.mna_precision_at_k,
            "mna_top_k": self.mna_top_k,
            "mna_acquirer_top1_accuracy": self.mna_acquirer_top1_accuracy,
            "mna_acquirer_top3_accuracy": self.mna_acquirer_top3_accuracy,
            "n_dead_or_acquired_names_in_universe": self.n_dead_or_acquired_names_in_universe,
            "n_confirmed_thesis": self.n_confirmed_thesis,
            "n_pos_error": self.n_pos_error,
            "n_timing_error": self.n_timing_error,
            "n_thesis_error": self.n_thesis_error,
            "n_market_drift": self.n_market_drift,
            "n_stop_loss": self.n_stop_loss,
            "n_unclassified": self.n_unclassified,
            "returns_by_action": self.returns_by_action,
            "returns_by_attribution": self.returns_by_attribution,
            "mean_return_by_attribution": self.mean_return_by_attribution,
            "median_return_by_attribution": self.median_return_by_attribution,
            "pnl_contribution_by_attribution": self.pnl_contribution_by_attribution,
            "n_independent_decisions": self.n_independent_decisions,
            "n_skipped_critic_warning": self.n_skipped_critic_warning,
            "notes": self.notes,
            "skill_adjusted_mean_return_pct": self.skill_adjusted_mean_return_pct,
            "n_skill_adjusted_decisions": self.n_skill_adjusted_decisions,
            "mean_xbi_return_pct": self.mean_xbi_return_pct,
            "mean_alpha_pct": self.mean_alpha_pct,
            "alpha_hit_rate": self.alpha_hit_rate,
            "n_with_xbi_data": self.n_with_xbi_data,
            "validation_status": self.validation_status,
        }

    def print(self) -> None:
        """Print a human-readable summary to stdout.

        Always displays the hard validation disclaimer. The disclaimer cannot
        be suppressed — every human-readable replay output must show it.
        """
        from bve.validation.model_grade import (
            BacktestValidationStatus,
            validation_disclaimer,
        )
        try:
            status = BacktestValidationStatus(self.validation_status)
        except ValueError:
            status = BacktestValidationStatus.DIRECTIONAL_ONLY
        print(validation_disclaimer(status))

        sep = "=" * 60
        print(sep)
        print(f"REPLAY SUMMARY — run {self.run_id[:8]}...")
        print(f"  Period         : {self.start_date} → {self.end_date}")
        print(f"  Strategy       : {self.strategy_version}")
        print(f"  Score version  : {self.score_version}")
        print(sep)
        print(f"  Decision dates : {self.n_decision_dates}")
        print(f"  Decisions made : {self.n_decisions}  (actionable: {self.n_actionable})")
        print(f"  Resolved       : {self.n_resolved}")
        gross = self.gross_mean_return_pct if self.gross_mean_return_pct is not None else self.mean_return_pct
        if gross is not None:
            print(f"  Mean return    : {gross:+.2f}% gross")
        else:
            print("  Mean return    : n/a")
        if self.net_mean_return_pct is not None:
            friction = (
                f"after {self.friction_cost_mean_bps:.0f} bps"
                if self.friction_cost_mean_bps is not None else "after frictions"
            )
            print(f"  Net return     : {self.net_mean_return_pct:+.2f}%  ({friction})")
        if self.skill_adjusted_mean_return_pct is not None:
            print(f"  Skill-adj return: {self.skill_adjusted_mean_return_pct:+.2f}%  "
                  f"(N={self.n_skill_adjusted_decisions}; excludes pos_error and market_drift)")
        else:
            print("  Skill-adj return: n/a")
        if self.mean_alpha_pct is not None and self.n_with_xbi_data > 0:
            xbi_str = (
                f"{self.mean_xbi_return_pct:+.2f}%" if self.mean_xbi_return_pct is not None else "n/a"
            )
            alpha_hr_str = (
                f"{self.alpha_hit_rate:.1%}" if self.alpha_hit_rate is not None else "n/a"
            )
            print(
                f"  XBI-adj alpha  : {self.mean_alpha_pct:+.2f}%  "
                f"(XBI mean={xbi_str}, alpha hit rate={alpha_hr_str}, N={self.n_with_xbi_data})"
            )
        else:
            print("  XBI-adj alpha  : n/a")
        if self.hit_rate is not None:
            print(f"  Hit rate       : {self.hit_rate:.1%}")
        else:
            print("  Hit rate       : n/a")
        print()
        print("  Attribution breakdown:")
        print(f"    confirmed_thesis : {self.n_confirmed_thesis}")
        print(f"    pos_error        : {self.n_pos_error}")
        print(f"    timing_error     : {self.n_timing_error}")
        print(f"    thesis_error     : {self.n_thesis_error}")
        print(f"    market_drift     : {self.n_market_drift}")
        print(f"    stop_loss        : {self.n_stop_loss}")
        print(f"    unclassified     : {self.n_unclassified}")
        if self.mean_return_by_attribution:
            print()
            print(
                f"  Attribution return breakdown "
                f"(N={self.n_resolved} raw | {self.n_independent_decisions} independent):"
            )
            print(f"    {'Type':<18} {'N':>4} {'Mean':>9} {'Median':>9} {'P&L':>9}")
            for key in [
                "confirmed_thesis",
                "market_drift",
                "pos_error",
                "timing_error",
                "thesis_error",
                "stop_loss",
                "unclassified",
            ]:
                returns = self.returns_by_attribution.get(key, [])
                mean = self.mean_return_by_attribution.get(key)
                median = self.median_return_by_attribution.get(key)
                pnl = self.pnl_contribution_by_attribution.get(key)
                print(
                    f"    {key:<18} {len(returns):>4} "
                    f"{_fmt_pct(mean):>9} {_fmt_pct(median):>9} {_fmt_pct(pnl, scale=100):>9}"
                )
        if self.n_skipped_critic_warning:
            print(f"\n  Skipped (critic warning) : {self.n_skipped_critic_warning}")
        if self.notes:
            print("\n  Notes:")
            for note in self.notes:
                print(f"    - {note}")
        print(sep)


def _fmt_pct(value: Optional[float], *, scale: float = 1.0) -> str:
    if value is None:
        return "n/a"
    return f"{value * scale:+.1f}%"
