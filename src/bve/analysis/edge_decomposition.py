"""
Edge decomposition for replay-run excess returns.

Consumes the paired same-window excess-return series produced by
``bve.analysis.alpha_validation`` and breaks the edge down into cohorts:

- first entry vs re-entry
- by asset
- by days to nearest catalyst
- by score decile
- by attribution type
- by blocking impact versus a baseline run

Usage
-----
    python -m bve.analysis.edge_decomposition --run-id <run_id>
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np

from bve.analysis.alpha_validation import (
    DEFAULT_BENCHMARK_TICKER,
    OUTPUT_DIR,
    AlphaValidator,
    PairedExcessTrade,
)
from bve.ops.historical_replay import REPLAY_STORE_PATH, ReplayStore


CATALYST_BUCKETS = ("[0-7]", "[8-14]", "[15-30]", "[31-45]", "[46+]", "no_catalyst")
ATTRIBUTION_ORDER = (
    "confirmed_thesis",
    "thesis_error",
    "timing_error",
    "pos_error",
    "market_drift",
    "unclassified",
)


@dataclass(frozen=True)
class EnrichedTrade:
    """Paired excess-return trade with replay metadata attached."""

    trade_id: str
    asset_id: str
    ticker: str
    entry_date: date
    exit_date: date
    trade_return: float
    xbi_return: float
    excess_return: float
    composite_score: float
    attribution_type: str
    entry_kind: str
    days_to_catalyst: Optional[int]
    catalyst_bucket: str

    @property
    def holding_days(self) -> int:
        return max(1, (self.exit_date - self.entry_date).days + 1)


@dataclass(frozen=True)
class DecompositionRow:
    """One row in a decomposition table."""

    section: str
    label: str
    n: int
    mean_excess_return: Optional[float] = None
    std_excess_return: Optional[float] = None
    hit_rate: Optional[float] = None
    t_statistic: Optional[float] = None
    mean_trade_return: Optional[float] = None
    mean_xbi_return: Optional[float] = None
    mean_hold_days: Optional[float] = None
    score_range_low: Optional[float] = None
    score_range_high: Optional[float] = None


@dataclass(frozen=True)
class BlockingValueSummary:
    """Summary of blocking impact versus a baseline run."""

    baseline_run_id: Optional[str]
    survived_row: DecompositionRow
    blocked_row: DecompositionRow
    saved_per_blocked_trade: Optional[float] = None


@dataclass(frozen=True)
class EdgeDecompositionReport:
    """Full decomposition report for one replay run."""

    run_id: str
    first_entry_rows: list[DecompositionRow] = field(default_factory=list)
    asset_rows: list[DecompositionRow] = field(default_factory=list)
    catalyst_rows: list[DecompositionRow] = field(default_factory=list)
    score_decile_rows: list[DecompositionRow] = field(default_factory=list)
    attribution_rows: list[DecompositionRow] = field(default_factory=list)
    blocking_summary: Optional[BlockingValueSummary] = None
    strongest_cohort: str = "n/a"
    weakest_cohort: str = "n/a"
    recommendation: str = "Insufficient data."
    csv_path: Optional[Path] = None


def _parse_date(raw: object) -> date:
    return date.fromisoformat(str(raw)[:10])


def _format_pct(value: Optional[float], *, show_sign: bool = False) -> str:
    if value is None:
        return "n/a"
    fmt = "{:+.2f}%" if show_sign else "{:.2f}%"
    return fmt.format(value)


def _format_hit_rate(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100.0:.1f}%"


def _format_stat(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return f"{value:.2f}"


def _compute_t_stat(values: np.ndarray) -> Optional[float]:
    """Compute a naive t-statistic for one cohort."""
    if values.size == 0:
        return None
    mean_value = float(values.mean())
    if values.size == 1:
        return None
    std_value = float(values.std(ddof=1))
    if std_value == 0.0:
        if mean_value == 0.0:
            return 0.0
        return math.copysign(math.inf, mean_value)
    return mean_value / (std_value / math.sqrt(values.size))


def _build_row(
    section: str,
    label: str,
    trades: list[EnrichedTrade],
    *,
    score_range_low: Optional[float] = None,
    score_range_high: Optional[float] = None,
) -> DecompositionRow:
    """Aggregate a list of enriched trades into one cohort row."""
    if not trades:
        return DecompositionRow(section=section, label=label, n=0)

    excess = np.array([trade.excess_return for trade in trades], dtype=float)
    trade_returns = np.array([trade.trade_return for trade in trades], dtype=float)
    xbi_returns = np.array([trade.xbi_return for trade in trades], dtype=float)
    hold_days = np.array([trade.holding_days for trade in trades], dtype=float)

    return DecompositionRow(
        section=section,
        label=label,
        n=len(trades),
        mean_excess_return=float(excess.mean()),
        std_excess_return=float(excess.std(ddof=1)) if len(trades) > 1 else 0.0,
        hit_rate=float(np.mean(excess > 0.0)),
        t_statistic=_compute_t_stat(excess),
        mean_trade_return=float(trade_returns.mean()),
        mean_xbi_return=float(xbi_returns.mean()),
        mean_hold_days=float(hold_days.mean()),
        score_range_low=score_range_low,
        score_range_high=score_range_high,
    )


def _alpha_csv_path(output_dir: Path, run_id: str) -> Path:
    return output_dir / f"alpha_validation_{run_id}.csv"


def _edge_csv_path(output_dir: Path, run_id: str) -> Path:
    return output_dir / f"edge_decomposition_{run_id}.csv"


def _bucket_days_to_catalyst(days_to_catalyst: Optional[int]) -> str:
    """Map an optional catalyst distance to a bucket label."""
    if days_to_catalyst is None:
        return "no_catalyst"
    if days_to_catalyst <= 7:
        return "[0-7]"
    if days_to_catalyst <= 14:
        return "[8-14]"
    if days_to_catalyst <= 30:
        return "[15-30]"
    if days_to_catalyst <= 45:
        return "[31-45]"
    return "[46+]"


def _assign_entry_kinds(paired_trades: list[PairedExcessTrade]) -> dict[str, str]:
    """Return trade_id -> first_entry/re_entry classification."""
    kinds: dict[str, str] = {}
    by_asset: dict[str, list[PairedExcessTrade]] = defaultdict(list)
    for trade in paired_trades:
        by_asset[trade.asset_id].append(trade)

    for asset_trades in by_asset.values():
        ordered = sorted(asset_trades, key=lambda trade: (trade.entry_date, trade.trade_id))
        for idx, trade in enumerate(ordered):
            kinds[trade.trade_id] = "first_entry" if idx == 0 else "re_entry"
    return kinds


def _score_decile_assignments(trades: list[EnrichedTrade]) -> dict[str, int]:
    """Assign each trade to a score decile, 1=lowest and 10=highest."""
    if not trades:
        return {}

    ordered = sorted(trades, key=lambda trade: (trade.composite_score, trade.trade_id))
    assignments: dict[str, int] = {}
    n_obs = len(ordered)
    for rank, trade in enumerate(ordered):
        decile = min(10, int(math.floor(rank * 10 / n_obs)) + 1)
        assignments[trade.trade_id] = decile
    return assignments


def _score_decile_rows(trades: list[EnrichedTrade]) -> list[DecompositionRow]:
    """Aggregate trades into ten score deciles."""
    assignments = _score_decile_assignments(trades)
    grouped: dict[int, list[EnrichedTrade]] = {decile: [] for decile in range(1, 11)}
    for trade in trades:
        grouped[assignments[trade.trade_id]].append(trade)

    rows: list[DecompositionRow] = []
    for decile in range(10, 0, -1):
        cohort = grouped[decile]
        if cohort:
            scores = [trade.composite_score for trade in cohort]
            rows.append(_build_row(
                "score_decile",
                str(decile),
                cohort,
                score_range_low=min(scores),
                score_range_high=max(scores),
            ))
        else:
            rows.append(DecompositionRow(section="score_decile", label=str(decile), n=0))
    return rows


def _load_alpha_trades(
    *,
    run_id: str,
    replay_db_path: str,
    benchmark_ticker: str,
    output_dir: Path,
    price_fetcher=None,
) -> list[PairedExcessTrade]:
    """Load paired trades from CSV, regenerating via AlphaValidator if missing."""
    path = _alpha_csv_path(output_dir, run_id)
    if not path.exists():
        validator = AlphaValidator(
            replay_db_path=replay_db_path,
            benchmark_ticker=benchmark_ticker,
            output_dir=output_dir,
            price_fetcher=price_fetcher,
        )
        validator.validate(run_id)

    trades: list[PairedExcessTrade] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            trades.append(PairedExcessTrade(
                trade_id=str(row["trade_id"]),
                asset_id=str(row["asset_id"]),
                ticker=str(row["ticker"]),
                entry_date=_parse_date(row["entry_date"]),
                exit_date=_parse_date(row["exit_date"]),
                trade_return=float(row["trade_return"]),
                xbi_return=float(row["xbi_return"]),
                excess_return=float(row["excess_return"]),
            ))
    return trades


def _next_catalyst_days(store: ReplayStore, asset_id: str, entry_date: date) -> Optional[int]:
    """Return days to the nearest catalyst on or after *entry_date*."""
    row = store._conn.execute(
        "SELECT MIN(announced_at) AS next_event "
        "FROM historical_events WHERE asset_id = ? AND announced_at >= ?",
        (asset_id, entry_date.isoformat()),
    ).fetchone()
    if row is None or row["next_event"] is None:
        return None
    next_event = _parse_date(row["next_event"])
    return max(0, (next_event - entry_date).days)


def _load_enriched_trades(
    *,
    run_id: str,
    replay_db_path: str,
    benchmark_ticker: str,
    output_dir: Path,
    price_fetcher=None,
) -> list[EnrichedTrade]:
    """Load paired trades and enrich them with replay metadata."""
    paired_trades = _load_alpha_trades(
        run_id=run_id,
        replay_db_path=replay_db_path,
        benchmark_ticker=benchmark_ticker,
        output_dir=output_dir,
        price_fetcher=price_fetcher,
    )
    entry_kinds = _assign_entry_kinds(paired_trades)

    store = ReplayStore(replay_db_path)
    try:
        decisions = {
            str(decision["decision_id"]): decision
            for decision in store.get_run_decisions(run_id)
        }
        enriched: list[EnrichedTrade] = []
        for trade in paired_trades:
            decision = decisions.get(trade.trade_id)
            if decision is None:
                raise ValueError(f"Replay decision not found for trade_id={trade.trade_id}")

            days_to_catalyst = _next_catalyst_days(store, trade.asset_id, trade.entry_date)
            enriched.append(EnrichedTrade(
                trade_id=trade.trade_id,
                asset_id=trade.asset_id,
                ticker=trade.ticker,
                entry_date=trade.entry_date,
                exit_date=trade.exit_date,
                trade_return=trade.trade_return,
                xbi_return=trade.xbi_return,
                excess_return=trade.excess_return,
                composite_score=float(decision.get("composite_score") or 0.0),
                attribution_type=str(decision.get("attribution_type") or "unclassified"),
                entry_kind=entry_kinds.get(trade.trade_id, "first_entry"),
                days_to_catalyst=days_to_catalyst,
                catalyst_bucket=_bucket_days_to_catalyst(days_to_catalyst),
            ))
    finally:
        store.close()
    return enriched


def _first_entry_rows(trades: list[EnrichedTrade]) -> list[DecompositionRow]:
    first_entries = [trade for trade in trades if trade.entry_kind == "first_entry"]
    re_entries = [trade for trade in trades if trade.entry_kind == "re_entry"]
    return [
        _build_row("entry_kind", "First Entry", first_entries),
        _build_row("entry_kind", "Re-Entry", re_entries),
    ]


def _asset_rows(trades: list[EnrichedTrade]) -> list[DecompositionRow]:
    grouped: dict[str, list[EnrichedTrade]] = defaultdict(list)
    for trade in trades:
        grouped[trade.asset_id].append(trade)

    rows = [_build_row("asset", asset_id, asset_trades) for asset_id, asset_trades in grouped.items()]
    rows.sort(
        key=lambda row: (
            row.mean_excess_return is None,
            -(row.mean_excess_return or float("-inf")),
            row.label,
        ),
    )
    return rows


def _catalyst_rows(trades: list[EnrichedTrade]) -> list[DecompositionRow]:
    grouped: dict[str, list[EnrichedTrade]] = defaultdict(list)
    for trade in trades:
        grouped[trade.catalyst_bucket].append(trade)

    return [
        _build_row("catalyst_bucket", bucket, grouped.get(bucket, []))
        for bucket in CATALYST_BUCKETS
    ]


def _attribution_rows(trades: list[EnrichedTrade]) -> list[DecompositionRow]:
    grouped: dict[str, list[EnrichedTrade]] = defaultdict(list)
    for trade in trades:
        grouped[trade.attribution_type].append(trade)

    ordered_labels = list(ATTRIBUTION_ORDER) + sorted(
        label for label in grouped.keys() if label not in ATTRIBUTION_ORDER
    )
    return [
        _build_row("attribution_type", label, grouped.get(label, []))
        for label in ordered_labels
    ]


def _earliest_run_id(replay_db_path: str) -> Optional[str]:
    """Return the earliest replay run_id by created_at."""
    store = ReplayStore(replay_db_path)
    try:
        row = store._conn.execute(
            "SELECT run_id FROM replay_runs ORDER BY created_at ASC, run_id ASC LIMIT 1"
        ).fetchone()
    finally:
        store.close()
    return str(row["run_id"]) if row else None


def _blocking_summary(
    *,
    baseline_run_id: Optional[str],
    current_run_id: str,
    replay_db_path: str,
    benchmark_ticker: str,
    output_dir: Path,
    price_fetcher=None,
) -> BlockingValueSummary:
    """Compare current-run trades to baseline-run trades for blocking value."""
    current_trades = _load_enriched_trades(
        run_id=current_run_id,
        replay_db_path=replay_db_path,
        benchmark_ticker=benchmark_ticker,
        output_dir=output_dir,
        price_fetcher=price_fetcher,
    )
    if baseline_run_id is None:
        baseline_run_id = _earliest_run_id(replay_db_path)

    if baseline_run_id is None or baseline_run_id == current_run_id:
        survived_row = _build_row("blocking_value", "Survived", current_trades)
        blocked_row = _build_row("blocking_value", "Blocked", [])
        return BlockingValueSummary(
            baseline_run_id=baseline_run_id,
            survived_row=survived_row,
            blocked_row=blocked_row,
            saved_per_blocked_trade=None,
        )

    baseline_trades = _load_enriched_trades(
        run_id=baseline_run_id,
        replay_db_path=replay_db_path,
        benchmark_ticker=benchmark_ticker,
        output_dir=output_dir,
        price_fetcher=price_fetcher,
    )
    current_keys = {(trade.asset_id, trade.entry_date) for trade in current_trades}
    blocked = [
        trade for trade in baseline_trades
        if (trade.asset_id, trade.entry_date) not in current_keys
    ]
    survived_row = _build_row("blocking_value", "Survived", current_trades)
    blocked_row = _build_row("blocking_value", "Blocked", blocked)
    saved = None
    if survived_row.mean_excess_return is not None and blocked_row.mean_excess_return is not None:
        saved = survived_row.mean_excess_return - blocked_row.mean_excess_return
    return BlockingValueSummary(
        baseline_run_id=baseline_run_id,
        survived_row=survived_row,
        blocked_row=blocked_row,
        saved_per_blocked_trade=saved,
    )


def _describe_row(row: DecompositionRow) -> str:
    return f"{row.section}:{row.label} ({_format_pct(row.mean_excess_return, show_sign=True)}, N={row.n})"


def _key_findings(
    first_entry_rows: list[DecompositionRow],
    catalyst_rows: list[DecompositionRow],
    score_decile_rows: list[DecompositionRow],
) -> tuple[str, str, str]:
    """Derive strongest/weakest cohorts and one-line recommendation."""
    actionable_rows = [
        *first_entry_rows,
        *[row for row in catalyst_rows if row.n > 0],
        *[row for row in score_decile_rows if row.n > 0],
    ]
    scored_rows = [
        row for row in actionable_rows
        if row.mean_excess_return is not None
    ]
    if not scored_rows:
        return "n/a", "n/a", "Insufficient data for cohort analysis."

    strongest = max(scored_rows, key=lambda row: row.mean_excess_return or float("-inf"))
    weakest = min(scored_rows, key=lambda row: row.mean_excess_return or float("inf"))

    recommendation = "Keep monitoring; no single cohort dominates yet."
    first_entry = next((row for row in first_entry_rows if row.label == "First Entry"), None)
    re_entry = next((row for row in first_entry_rows if row.label == "Re-Entry"), None)
    decile_10 = next((row for row in score_decile_rows if row.label == "10"), None)
    decile_1 = next((row for row in score_decile_rows if row.label == "1"), None)
    near_catalyst = next(
        (row for row in catalyst_rows if row.label in {"[0-7]", "[8-14]"} and row.n > 0),
        None,
    )
    if (
        first_entry
        and re_entry
        and first_entry.mean_excess_return is not None
        and re_entry.mean_excess_return is not None
        and first_entry.mean_excess_return > re_entry.mean_excess_return + 1.0
    ):
        recommendation = "Favor first entries and keep strict re-entry controls."
    elif (
        decile_10
        and decile_1
        and decile_10.mean_excess_return is not None
        and decile_1.mean_excess_return is not None
        and decile_10.mean_excess_return > decile_1.mean_excess_return + 1.0
    ):
        recommendation = "Concentrate capital in the highest score deciles."
    elif near_catalyst and near_catalyst.mean_excess_return is not None:
        best_catalyst = max(
            (row for row in catalyst_rows if row.n > 0 and row.mean_excess_return is not None),
            key=lambda row: row.mean_excess_return or float("-inf"),
        )
        if best_catalyst.label in {"[0-7]", "[8-14]"}:
            recommendation = "Tighten entries around the catalyst window."

    return _describe_row(strongest), _describe_row(weakest), recommendation


def render_edge_decomposition_report(report: EdgeDecompositionReport) -> str:
    """Render the formatted edge decomposition report."""
    sep = "=" * 60
    lines = [
        sep,
        "EDGE DECOMPOSITION REPORT",
        f"Run: {report.run_id}",
        sep,
        "",
        "1. FIRST ENTRY vs RE-ENTRY",
    ]
    for row in report.first_entry_rows:
        lines.append(
            f"   {row.label:<12} N={row.n:<3}  "
            f"excess={_format_pct(row.mean_excess_return, show_sign=True):>8}  "
            f"t={_format_stat(row.t_statistic):>5}"
        )

    lines.extend(["", "2. BY ASSET", "   Asset          N   Excess    HitRate"])
    for row in report.asset_rows:
        lines.append(
            f"   {row.label:<14} {row.n:>2}  "
            f"{_format_pct(row.mean_excess_return, show_sign=True):>8}  "
            f"{_format_hit_rate(row.hit_rate):>7}"
        )

    lines.extend(["", "3. BY DAYS TO CATALYST", "   Bucket       N   Excess    HitRate  t-stat"])
    for row in report.catalyst_rows:
        lines.append(
            f"   {row.label:<11} {row.n:>2}  "
            f"{_format_pct(row.mean_excess_return, show_sign=True):>8}  "
            f"{_format_hit_rate(row.hit_rate):>7}  "
            f"{_format_stat(row.t_statistic):>6}"
        )

    lines.extend(["", "4. BY SCORE DECILE", "   Decile  N  Score Range    Excess    HitRate"])
    for row in report.score_decile_rows:
        if row.score_range_low is None or row.score_range_high is None:
            score_range = "n/a"
        else:
            score_range = f"[{row.score_range_low:.2f}-{row.score_range_high:.2f}]"
        lines.append(
            f"   {row.label:>2}      {row.n:>2}  {score_range:<13}  "
            f"{_format_pct(row.mean_excess_return, show_sign=True):>8}  "
            f"{_format_hit_rate(row.hit_rate):>7}"
        )

    lines.extend(["", "5. BY ATTRIBUTION TYPE", "   Type               N   Excess    Trade     XBI"])
    for row in report.attribution_rows:
        lines.append(
            f"   {row.label:<18} {row.n:>2}  "
            f"{_format_pct(row.mean_excess_return, show_sign=True):>8}  "
            f"{_format_pct(row.mean_trade_return, show_sign=True):>8}  "
            f"{_format_pct(row.mean_xbi_return, show_sign=True):>8}"
        )

    lines.extend(["", "6. BLOCKING VALUE"])
    if report.blocking_summary is None:
        lines.append("   Blocking comparison unavailable.")
    else:
        survived = report.blocking_summary.survived_row
        blocked = report.blocking_summary.blocked_row
        lines.append(
            f"   Survived:     N={survived.n:<3} "
            f"excess={_format_pct(survived.mean_excess_return, show_sign=True)}"
        )
        lines.append(
            f"   Blocked:      N={blocked.n:<3} "
            f"excess={_format_pct(blocked.mean_excess_return, show_sign=True)}"
        )
        lines.append(
            "   Saved:        "
            f"{_format_pct(report.blocking_summary.saved_per_blocked_trade, show_sign=True)} "
            "per blocked trade"
        )

    lines.extend([
        "",
        "KEY FINDINGS",
        f"  Strongest cohort: {report.strongest_cohort}",
        f"  Weakest cohort: {report.weakest_cohort}",
        f"  Recommendation: {report.recommendation}",
        sep,
    ])
    return "\n".join(lines)


class EdgeDecomposer:
    """Generate cohort decompositions for replay excess returns."""

    def __init__(
        self,
        *,
        replay_db_path: str = str(REPLAY_STORE_PATH),
        benchmark_ticker: str = DEFAULT_BENCHMARK_TICKER,
        output_dir: Path = OUTPUT_DIR,
        price_fetcher=None,
    ) -> None:
        self.replay_db_path = replay_db_path
        self.benchmark_ticker = benchmark_ticker
        self.output_dir = output_dir
        self.price_fetcher = price_fetcher

    def _export_csv(self, run_id: str, rows: list[DecompositionRow], *, blocking: Optional[BlockingValueSummary]) -> Path:
        """Write all decomposition rows to one CSV file."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = _edge_csv_path(self.output_dir, run_id)
        fieldnames = [
            "section",
            "label",
            "n",
            "mean_excess_return",
            "std_excess_return",
            "hit_rate",
            "t_statistic",
            "mean_trade_return",
            "mean_xbi_return",
            "mean_hold_days",
            "score_range_low",
            "score_range_high",
            "saved_per_blocked_trade",
        ]
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "section": row.section,
                    "label": row.label,
                    "n": row.n,
                    "mean_excess_return": row.mean_excess_return,
                    "std_excess_return": row.std_excess_return,
                    "hit_rate": row.hit_rate,
                    "t_statistic": row.t_statistic,
                    "mean_trade_return": row.mean_trade_return,
                    "mean_xbi_return": row.mean_xbi_return,
                    "mean_hold_days": row.mean_hold_days,
                    "score_range_low": row.score_range_low,
                    "score_range_high": row.score_range_high,
                    "saved_per_blocked_trade": "",
                })
            if blocking is not None:
                writer.writerow({
                    "section": "blocking_value",
                    "label": "saved_per_blocked_trade",
                    "n": "",
                    "mean_excess_return": "",
                    "std_excess_return": "",
                    "hit_rate": "",
                    "t_statistic": "",
                    "mean_trade_return": "",
                    "mean_xbi_return": "",
                    "mean_hold_days": "",
                    "score_range_low": "",
                    "score_range_high": "",
                    "saved_per_blocked_trade": blocking.saved_per_blocked_trade,
                })
        return path

    def generate(
        self,
        run_id: str,
        *,
        baseline_run_id: Optional[str] = None,
    ) -> EdgeDecompositionReport:
        """Generate the edge decomposition report for *run_id*."""
        trades = _load_enriched_trades(
            run_id=run_id,
            replay_db_path=self.replay_db_path,
            benchmark_ticker=self.benchmark_ticker,
            output_dir=self.output_dir,
            price_fetcher=self.price_fetcher,
        )
        first_entry_rows = _first_entry_rows(trades)
        asset_rows = _asset_rows(trades)
        catalyst_rows = _catalyst_rows(trades)
        score_decile_rows = _score_decile_rows(trades)
        attribution_rows = _attribution_rows(trades)
        blocking = _blocking_summary(
            baseline_run_id=baseline_run_id,
            current_run_id=run_id,
            replay_db_path=self.replay_db_path,
            benchmark_ticker=self.benchmark_ticker,
            output_dir=self.output_dir,
            price_fetcher=self.price_fetcher,
        )
        strongest, weakest, recommendation = _key_findings(
            first_entry_rows,
            catalyst_rows,
            score_decile_rows,
        )
        flat_rows = [
            *first_entry_rows,
            *asset_rows,
            *catalyst_rows,
            *score_decile_rows,
            *attribution_rows,
            blocking.survived_row,
            blocking.blocked_row,
        ]
        csv_path = self._export_csv(run_id, flat_rows, blocking=blocking)
        return EdgeDecompositionReport(
            run_id=run_id,
            first_entry_rows=first_entry_rows,
            asset_rows=asset_rows,
            catalyst_rows=catalyst_rows,
            score_decile_rows=score_decile_rows,
            attribution_rows=attribution_rows,
            blocking_summary=blocking,
            strongest_cohort=strongest,
            weakest_cohort=weakest,
            recommendation=recommendation,
            csv_path=csv_path,
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decompose replay excess returns into cohorts")
    parser.add_argument("--run-id", required=True, help="Replay run ID")
    parser.add_argument(
        "--baseline-run-id",
        default=None,
        help="Optional baseline run ID for blocking comparison",
    )
    parser.add_argument(
        "--db",
        default=str(REPLAY_STORE_PATH),
        help="Replay SQLite store path",
    )
    parser.add_argument(
        "--benchmark",
        default=DEFAULT_BENCHMARK_TICKER,
        help="Benchmark ticker used for alpha validation",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    report = EdgeDecomposer(
        replay_db_path=args.db,
        benchmark_ticker=args.benchmark,
    ).generate(args.run_id, baseline_run_id=args.baseline_run_id)
    print(render_edge_decomposition_report(report))


if __name__ == "__main__":
    main()
