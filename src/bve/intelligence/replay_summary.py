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
    hit_rate: Optional[float] = None
    n_confirmed_thesis: int = 0
    n_pos_error: int = 0
    n_timing_error: int = 0
    n_thesis_error: int = 0
    n_market_drift: int = 0
    n_unclassified: int = 0
    returns_by_action: dict = field(default_factory=dict)
    n_skipped_critic_warning: int = 0
    notes: list[str] = field(default_factory=list)

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
            "hit_rate": self.hit_rate,
            "n_confirmed_thesis": self.n_confirmed_thesis,
            "n_pos_error": self.n_pos_error,
            "n_timing_error": self.n_timing_error,
            "n_thesis_error": self.n_thesis_error,
            "n_market_drift": self.n_market_drift,
            "n_unclassified": self.n_unclassified,
            "returns_by_action": self.returns_by_action,
            "n_skipped_critic_warning": self.n_skipped_critic_warning,
            "notes": self.notes,
        }

    def print(self) -> None:
        """Print a human-readable summary to stdout."""
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
        if self.mean_return_pct is not None:
            print(f"  Mean return    : {self.mean_return_pct:+.2f}%")
        else:
            print("  Mean return    : n/a")
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
        print(f"    unclassified     : {self.n_unclassified}")
        if self.n_skipped_critic_warning:
            print(f"\n  Skipped (critic warning) : {self.n_skipped_critic_warning}")
        if self.notes:
            print("\n  Notes:")
            for note in self.notes:
                print(f"    - {note}")
        print(sep)
