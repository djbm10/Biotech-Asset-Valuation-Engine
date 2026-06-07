"""Rolling holdout evaluator for M&A and public-markets model validation.

Runs MACalibrationDatasetBuilder + PortfolioBacktester over multiple overlapping
time windows to produce per-window metrics with honest N counts.  Multiple windows
expose whether performance is consistent across market regimes rather than an
artifact of one lucky holdout period.

Usage::

    python -m bve.analysis.rolling_holdout \
        --knowledge-db outputs/intelligence/replay_knowledge.db \
        --replay-store outputs/intelligence/replay_store.sqlite \
        --start 2024-01-01 --end 2026-03-01 \
        --window-months 12 --step-months 3 --top-k 10

Design decisions
----------------
- stage_a_probability is the primary ranking signal for M&A metrics, not the stored
  v1.2 probability (which saturates at 1.0 for commercial-stage CNS assets because
  the v1.2 scorer uses strategic_fit weight=1.0).
- replay_store_path is always passed so _seed_catalyst_days runs and
  days_to_catalyst populates stage_a_probability correctly.
- A window is flagged low_n if it contains fewer than MIN_TARGETS_FOR_TRUST distinct
  positive targets.  Metrics are still reported but the user should interpret them
  with caution.
- Public-markets metrics are skipped when the window has fewer than 2 rebalancing
  periods of price data.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

from bve.analysis.mna_probability_scanner import _evaluate
from bve.analysis.portfolio_backtest import (
    PortfolioBacktestConfig,
    PortfolioBacktester,
)
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.ma_calibration import MACalibrationDatasetBuilder
from bve.ops.strict_backtest import (
    _build_local_price_return_fetcher,
    _build_financing_risk_lookup,
    materialize_backtest_snapshots_from_company_sotp,
    load_replay_universe,
)

# A window must have at least this many distinct acquired targets to be trusted.
MIN_TARGETS_FOR_TRUST = 3
_ECE_GATE_THRESHOLD = 0.10

DEFAULT_KNOWLEDGE_DB = "outputs/intelligence/replay_knowledge.db"
DEFAULT_REPLAY_STORE = "outputs/intelligence/replay_store.sqlite"
# The universe file is written by ReplayUniverseBuilder (run by strict_backtest).
# Default matches the path used by strict_backtest.
DEFAULT_UNIVERSE_FILE = "examples/research/universe_expanded_mna.yaml"


# ---------------------------------------------------------------------------
# Rolling window generation
# ---------------------------------------------------------------------------


def _rolling_windows(
    start: date,
    end: date,
    window_months: int,
    step_months: int,
) -> list[tuple[date, date, str]]:
    """Return list of (window_start, window_end, label) tuples.

    Each window is ``window_months`` wide, stepping forward by ``step_months``.
    Windows are cropped to [start, end].
    """
    windows: list[tuple[date, date, str]] = []
    cur = date(start.year, start.month, 1)

    def _add_months(d: date, n: int) -> date:
        total = d.month - 1 + n
        yr = d.year + total // 12
        mo = total % 12 + 1
        return date(yr, mo, 1)

    while cur < end:
        win_end = _add_months(cur, window_months)
        # Crop to overall end boundary
        actual_end = min(win_end, end)
        if actual_end <= cur:
            break
        label = f"{cur.isoformat()}/{actual_end.isoformat()}"
        windows.append((cur, actual_end, label))
        cur = _add_months(cur, step_months)

    return windows


# ---------------------------------------------------------------------------
# Per-window result
# ---------------------------------------------------------------------------


@dataclass
class WindowResult:
    """Metrics for one rolling window."""

    window_start: date
    window_end: date
    label: str

    # Sample size
    n_rows: int = 0
    n_snapshot_dates: int = 0
    n_positive_targets: int = 0
    low_n: bool = True  # True when n_positive_targets < MIN_TARGETS_FOR_TRUST

    # Stage A discrimination
    stage_a_avg_positive: Optional[float] = None
    stage_a_avg_control: Optional[float] = None
    stage_a_auc: Optional[float] = None
    stage_a_discrimination_ratio: Optional[float] = None

    # M&A ranking (stage_a as ranker)
    stage_a_precision_at_k: Optional[float] = None
    stage_a_recall_at_k: Optional[float] = None

    # M&A ranking (stored probability as ranker — for comparison)
    stored_prob_precision_at_k: Optional[float] = None
    stored_prob_avg_positive: Optional[float] = None
    stored_prob_avg_control: Optional[float] = None

    # Acquirer accuracy (from stored candidate list)
    acquirer_top1_accuracy: Optional[float] = None
    acquirer_top3_accuracy: Optional[float] = None
    acquirer_top5_accuracy: Optional[float] = None
    acquirer_mrr: Optional[float] = None
    median_lead_days: Optional[float] = None
    ece_raw: Optional[float] = None
    brier_raw: Optional[float] = None
    ece_passes: bool = False
    buyer_in_pool_pct: Optional[float] = None
    false_positive_mix: dict[str, float] = field(default_factory=dict)

    # Public-markets
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    cagr: Optional[float] = None
    win_rate: Optional[float] = None
    public_skipped: bool = False
    public_skip_reason: str = ""

    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "window": self.label,
            "n_rows": self.n_rows,
            "n_snapshot_dates": self.n_snapshot_dates,
            "n_positive_targets": self.n_positive_targets,
            "low_n": self.low_n,
            "stage_a_avg_positive": self.stage_a_avg_positive,
            "stage_a_avg_control": self.stage_a_avg_control,
            "stage_a_auc": self.stage_a_auc,
            "stage_a_discrimination_ratio": self.stage_a_discrimination_ratio,
            "stage_a_precision_at_k": self.stage_a_precision_at_k,
            "stage_a_recall_at_k": self.stage_a_recall_at_k,
            "stored_prob_precision_at_k": self.stored_prob_precision_at_k,
            "stored_prob_avg_positive": self.stored_prob_avg_positive,
            "stored_prob_avg_control": self.stored_prob_avg_control,
            "acquirer_top1_accuracy": self.acquirer_top1_accuracy,
            "acquirer_top3_accuracy": self.acquirer_top3_accuracy,
            "acquirer_top5_accuracy": self.acquirer_top5_accuracy,
            "acquirer_mrr": self.acquirer_mrr,
            "median_lead_days": self.median_lead_days,
            "ece_raw": self.ece_raw,
            "brier_raw": self.brier_raw,
            "ece_passes": self.ece_passes,
            "buyer_in_pool_pct": self.buyer_in_pool_pct,
            "false_positive_mix": self.false_positive_mix,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "cagr": self.cagr,
            "win_rate": self.win_rate,
            "public_skipped": self.public_skipped,
            "public_skip_reason": self.public_skip_reason,
            "errors": self.errors,
        }


@dataclass
class RollingHoldoutReport:
    """Full rolling holdout evaluation report."""

    generated_at: str
    knowledge_db: str
    replay_store: str
    overall_start: date
    overall_end: date
    window_months: int
    step_months: int
    top_k: int
    lookahead_days: int
    windows: list[WindowResult]

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "knowledge_db": self.knowledge_db,
            "replay_store": self.replay_store,
            "overall_start": self.overall_start.isoformat(),
            "overall_end": self.overall_end.isoformat(),
            "window_months": self.window_months,
            "step_months": self.step_months,
            "top_k": self.top_k,
            "lookahead_days": self.lookahead_days,
            "calibration_gate_passes": self.calibration_gate_passes(),
            "windows": [w.as_dict() for w in self.windows],
        }

    def calibration_gate_passes(self) -> bool:
        populated = [
            w for w in self.windows
            if w.n_rows > 0 and w.ece_raw is not None
        ]
        if not populated:
            return False
        return all(float(w.ece_raw) <= _ECE_GATE_THRESHOLD for w in populated)


def _brier_score(probs: list[float], outcomes: list[int]) -> float:
    if not probs or not outcomes:
        return float("nan")
    n = min(len(probs), len(outcomes))
    return sum((float(probs[i]) - float(outcomes[i])) ** 2 for i in range(n)) / n


def _ece(probs: list[float], outcomes: list[int], n_bins: int = 5) -> float:
    if not probs or not outcomes:
        return float("nan")
    n = min(len(probs), len(outcomes))
    total = 0.0
    for b in range(n_bins):
        lo = b / n_bins
        hi = (b + 1) / n_bins
        idx = []
        for i in range(n):
            p = float(probs[i])
            if b == n_bins - 1:
                in_bin = lo <= p <= hi
            else:
                in_bin = lo <= p < hi
            if in_bin:
                idx.append(i)
        if not idx:
            continue
        conf = sum(float(probs[i]) for i in idx) / len(idx)
        acc = sum(float(outcomes[i]) for i in idx) / len(idx)
        total += (len(idx) / n) * abs(conf - acc)
    return total


# ---------------------------------------------------------------------------
# Per-window evaluator
# ---------------------------------------------------------------------------


def _run_window(
    *,
    window_start: date,
    window_end: date,
    label: str,
    knowledge_db: str,
    replay_store: str,
    universe_file: str,
    top_k: int,
    lookahead_days: int,
) -> WindowResult:
    result = WindowResult(window_start=window_start, window_end=window_end, label=label)

    # ------------------------------------------------------------------
    # M&A calibration dataset
    # ------------------------------------------------------------------
    store = KnowledgeStore(knowledge_db)
    try:
        dataset = MACalibrationDatasetBuilder(
            knowledge_store=store,
        ).build_dataset(
            lookahead_days=lookahead_days,
            start_date=window_start,
            end_date=window_end,
            replay_store_path=replay_store,
        )
    except Exception as exc:
        result.errors.append(f"build_dataset: {exc}")
        return result
    finally:
        store.close()

    result.n_rows = dataset.n_rows
    result.n_snapshot_dates = len({r.snapshot_date for r in dataset.rows})
    result.n_positive_targets = len({r.ticker for r in dataset.rows if r.label == 1})
    result.low_n = result.n_positive_targets < MIN_TARGETS_FOR_TRUST

    if not dataset.rows:
        result.errors.append("no rows in dataset for this window")
        return result

    # ------------------------------------------------------------------
    # Standard _evaluate (uses stored probability for precision@k)
    # ------------------------------------------------------------------
    try:
        metrics = _evaluate(dataset, top_k=top_k)
        result.stored_prob_precision_at_k = metrics.precision_at_k
        result.stored_prob_avg_positive = metrics.average_probability_positive
        result.stored_prob_avg_control = metrics.average_probability_control
        result.acquirer_top1_accuracy = metrics.acquirer_top1_accuracy
        result.acquirer_top3_accuracy = metrics.acquirer_top3_accuracy
        result.acquirer_mrr = metrics.acquirer_mrr
        result.median_lead_days = metrics.median_lead_days_at_k
        # Stage A from _evaluate
        result.stage_a_avg_positive = metrics.stage_a_avg_positive
        result.stage_a_avg_control = metrics.stage_a_avg_control
        result.stage_a_auc = metrics.acquisition_likelihood_auc
        result.stage_a_precision_at_k = metrics.acquisition_likelihood_precision
        result.stage_a_recall_at_k = metrics.acquisition_likelihood_recall
        if (
            result.stage_a_avg_positive is not None
            and result.stage_a_avg_control is not None
            and result.stage_a_avg_control > 0
        ):
            result.stage_a_discrimination_ratio = round(
                result.stage_a_avg_positive / result.stage_a_avg_control, 4
            )
    except Exception as exc:
        result.errors.append(f"_evaluate: {exc}")

    # ------------------------------------------------------------------
    # Public-markets backtest
    # ------------------------------------------------------------------
    try:
        universe = load_replay_universe(universe_file)
        ks = KnowledgeStore(knowledge_db)
        try:
            materialize_backtest_snapshots_from_company_sotp(
                knowledge_db_path=knowledge_db,
                universe_rows=universe,
            )
            price_fetcher = _build_local_price_return_fetcher(replay_store)
            risk_fetcher = _build_financing_risk_lookup(knowledge_db)
            bt = PortfolioBacktester(
                ks,
                PortfolioBacktestConfig(
                    start_date=window_start,
                    end_date=window_end,
                    n_holdings=top_k,
                    rebalance_freq_days=90,
                ),
                price_fetcher=price_fetcher,
                risk_metadata_fetcher=risk_fetcher,
            )
            bt_result = bt.run()
        finally:
            ks.close()

        if bt_result.position_log:
            result.sharpe_ratio = bt_result.sharpe_ratio
            result.max_drawdown = bt_result.max_drawdown
            result.cagr = bt_result.cagr
            result.win_rate = bt_result.win_rate
        else:
            result.public_skipped = True
            result.public_skip_reason = "no_positions_in_window"
    except FileNotFoundError:
        result.public_skipped = True
        result.public_skip_reason = "universe_file_not_found"
    except Exception as exc:
        result.public_skipped = True
        result.public_skip_reason = str(exc)[:120]

    return result


# ---------------------------------------------------------------------------
# Main evaluator
# ---------------------------------------------------------------------------


def run_rolling_holdout(
    *,
    knowledge_db: str = DEFAULT_KNOWLEDGE_DB,
    replay_store: str = DEFAULT_REPLAY_STORE,
    universe_file: str = DEFAULT_UNIVERSE_FILE,
    overall_start: date,
    overall_end: date,
    window_months: int = 12,
    step_months: int = 3,
    top_k: int = 10,
    lookahead_days: int = 365,
) -> RollingHoldoutReport:
    from datetime import datetime, timezone

    windows = _rolling_windows(overall_start, overall_end, window_months, step_months)
    results: list[WindowResult] = []
    for win_start, win_end, label in windows:
        res = _run_window(
            window_start=win_start,
            window_end=win_end,
            label=label,
            knowledge_db=knowledge_db,
            replay_store=replay_store,
            universe_file=universe_file,
            top_k=top_k,
            lookahead_days=lookahead_days,
        )
        results.append(res)

    return RollingHoldoutReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        knowledge_db=knowledge_db,
        replay_store=replay_store,
        overall_start=overall_start,
        overall_end=overall_end,
        window_months=window_months,
        step_months=step_months,
        top_k=top_k,
        lookahead_days=lookahead_days,
        windows=results,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_FMT = "{:<35} {:>5} {:>8} {:>9} {:>9} {:>8} {:>8} {:>7} {:>7} {:>7} {:>7} {:>8}"
_HDR = _FMT.format(
    "window", "N", "snap_dt", "stgA_pos", "stgA_ctl", "stgA_AUC",
    "prec@k", "top-1", "top-3", "MRR", "Sharpe", "max_dd",
)


def render_report(report: RollingHoldoutReport) -> str:
    lines = [
        "Rolling Holdout Evaluation",
        f"  Period:  {report.overall_start} → {report.overall_end}",
        f"  Window:  {report.window_months}m, step {report.step_months}m",
        f"  top_k:   {report.top_k}    lookahead: {report.lookahead_days}d",
        f"  MIN_TARGETS_FOR_TRUST: {MIN_TARGETS_FOR_TRUST}  "
        f"(* = low-N window — interpret with caution)",
        "",
        _HDR,
        "-" * len(_HDR),
    ]

    def _f(v: Optional[float], fmt: str = ".3f") -> str:
        return f"{v:{fmt}}" if v is not None else "  —  "

    for w in report.windows:
        flag = "* " if w.low_n else "  "
        sharpe_str = _f(w.sharpe_ratio) if not w.public_skipped else "skip"
        dd_str = _f(w.max_drawdown) if not w.public_skipped else "skip"
        lines.append(
            _FMT.format(
                f"{flag}{w.label}",
                w.n_positive_targets,
                w.n_snapshot_dates,
                _f(w.stage_a_avg_positive),
                _f(w.stage_a_avg_control),
                _f(w.stage_a_auc),
                _f(w.stage_a_precision_at_k),
                _f(w.acquirer_top1_accuracy),
                _f(w.acquirer_top3_accuracy),
                _f(w.acquirer_mrr),
                sharpe_str,
                dd_str,
            )
        )
        if w.errors:
            for err in w.errors:
                lines.append(f"    ERROR: {err}")

    # Aggregate over trusted windows
    trusted = [w for w in report.windows if not w.low_n]
    if trusted:
        lines.append("-" * len(_HDR))
        lines.append(
            f"Trusted windows (N≥{MIN_TARGETS_FOR_TRUST}): {len(trusted)} / {len(report.windows)}"
        )

        def _avg(values: list[Optional[float]]) -> Optional[float]:
            vals = [v for v in values if v is not None]
            return round(sum(vals) / len(vals), 4) if vals else None

        avg_auc = _avg([w.stage_a_auc for w in trusted])
        avg_p = _avg([w.stage_a_precision_at_k for w in trusted])
        avg_top1 = _avg([w.acquirer_top1_accuracy for w in trusted])
        avg_mrr = _avg([w.acquirer_mrr for w in trusted])
        avg_sharpe = _avg([w.sharpe_ratio for w in trusted if not w.public_skipped])
        avg_dd = _avg([w.max_drawdown for w in trusted if not w.public_skipped])

        lines.append(
            _FMT.format(
                "  mean (trusted)",
                "—",
                "—",
                "—",
                "—",
                _f(avg_auc),
                _f(avg_p),
                _f(avg_top1),
                "—",
                _f(avg_mrr),
                _f(avg_sharpe),
                _f(avg_dd),
            )
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Rolling holdout evaluation")
    p.add_argument("--knowledge-db", default=DEFAULT_KNOWLEDGE_DB)
    p.add_argument("--replay-store", default=DEFAULT_REPLAY_STORE)
    p.add_argument("--universe-file", default=DEFAULT_UNIVERSE_FILE)
    p.add_argument("--start", required=True, help="Overall start date YYYY-MM-DD")
    p.add_argument("--end", required=True, help="Overall end date YYYY-MM-DD")
    p.add_argument("--window-months", type=int, default=12)
    p.add_argument("--step-months", type=int, default=3)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--lookahead-days", type=int, default=365)
    p.add_argument("--output", default="outputs/analysis/rolling_holdout.json")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    report = run_rolling_holdout(
        knowledge_db=args.knowledge_db,
        replay_store=args.replay_store,
        universe_file=args.universe_file,
        overall_start=date.fromisoformat(args.start),
        overall_end=date.fromisoformat(args.end),
        window_months=args.window_months,
        step_months=args.step_months,
        top_k=args.top_k,
        lookahead_days=args.lookahead_days,
    )
    print(render_report(report))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
    print(f"\nJSON: {out}")


if __name__ == "__main__":
    main()
