"""
vrtx_regn_backtest_runner — leakage audit + scoring + ranking + metrics.

Loads the curated feature store, runs the leakage audit (refuses if
violations found), scores each candidate pair with AcquirerPairScorer,
ranks within each (acquirer, snapshot_date) group, and computes all
evaluation metrics.

Usage::

    python -m bve.backtest_research.vrtx_regn_backtest_runner \\
      --dataset research/backtests/vrtx_regn_2010/curated \\
      --score-mode approved_only \\
      --output research/backtests/vrtx_regn_2010/outputs
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@dataclass
class RankingMetrics:
    acquirer: str
    days_before: int
    n_groups: int
    n_total_candidates: int

    top_1_hit_rate:       float = 0.0
    top_3_hit_rate:       float = 0.0
    top_5_hit_rate:       float = 0.0
    top_10_hit_rate:      float = 0.0
    top_decile_hit_rate:  float = 0.0
    mean_percentile_rank: float = 0.0
    median_percentile_rank: float = 0.0
    mean_reciprocal_rank: float = 0.0
    auc_roc:              float = 0.0
    brier_score:          float = 0.0
    precision_at_5:       float = 0.0
    precision_at_10:      float = 0.0
    calibration_error:    float = 0.0

    n_verified_deals:     int = 0
    caveats:              str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# ScoredRow
# ---------------------------------------------------------------------------

@dataclass
class ScoredRow:
    deal_id: str
    acquirer_ticker: str
    target_ticker: str
    snapshot_date: str
    days_before: int
    is_actual_target: bool

    # Pair scorer outputs
    pair_score: float
    log_odds: float

    # Rank within (acquirer, snapshot_date) group
    rank: int
    n_candidates: int
    percentile: float    # 0=bottom, 1=top

    # Label (evaluation only, never input to scorer)
    label_is_positive: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# BacktestRunner
# ---------------------------------------------------------------------------

class BacktestRunner:
    """
    Load feature store → leakage audit → score → rank → metrics.

    Scoring uses the existing frozen AcquirerPairScorer (no weight changes).
    """

    def __init__(self, score_mode: str = "approved_only") -> None:
        self._score_mode = score_mode

    def run(
        self,
        feature_store_path: Path,
        output_dir: Path,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        from bve.backtest_research.leakage_guard import LeakageGuard, LeakageViolationError
        from bve.intelligence.acquirer_pair_scorer import AcquirerPairScorer, PairFeatures

        # 1. Load feature store
        rows = _load_feature_store(feature_store_path)
        print(f"Loaded {len(rows)} rows from feature store")

        # 2. Leakage audit (hard block)
        guard = LeakageGuard()
        audit = guard.audit_dataframe(rows, snapshot_date_col="snapshot_date")
        if audit.has_violations:
            print(audit.summary(), file=sys.stderr)
            raise LeakageViolationError(
                f"Backtest refused: {len(audit.violations)} leakage violation(s) found."
            )
        print("Leakage audit: PASSED")

        # 3. Score each pair
        scorer = AcquirerPairScorer()
        scored: list[ScoredRow] = []
        for row in rows:
            try:
                features = PairFeatures(
                    asset_quality=float(row.get("asset_quality", 0.3)),
                    acquirer_appetite=float(row.get("acquirer_appetite", 0.3)),
                    ta_overlap=float(row.get("ta_overlap", 0.3)),
                    size_fit=float(row.get("size_fit", 0.3)),
                    acquirer_urgency=float(row.get("acquirer_urgency", 0.3)),
                    integration_capacity=float(row.get("integration_capacity", 0.3)),
                    acquirer_id=str(row.get("acquirer_ticker", "")),
                    target_ticker=str(row.get("target_ticker", "")),
                    as_of_date=str(row.get("snapshot_date", "")),
                )
                result = scorer.score(features)
                pair_score = result.probability
                log_odds = result.log_odds
            except Exception:
                pair_score = 0.0
                log_odds = 0.0

            scored.append(ScoredRow(
                deal_id=str(row.get("deal_id", "")),
                acquirer_ticker=str(row.get("acquirer_ticker", "")),
                target_ticker=str(row.get("target_ticker", "")),
                snapshot_date=str(row.get("snapshot_date", "")),
                days_before=int(row.get("days_before", 0)),
                is_actual_target=str(row.get("is_actual_target", "")).lower() in ("true", "1"),
                pair_score=pair_score,
                log_odds=log_odds,
                rank=0,
                n_candidates=0,
                percentile=0.0,
                label_is_positive=str(row.get("is_actual_target", "")).lower() in ("true", "1"),
            ))

        # 4. Rank within groups
        scored = _rank_within_groups(scored)

        # 5. Compute metrics
        all_metrics = _compute_metrics(scored)

        # 6. Write outputs
        if not dry_run:
            output_dir.mkdir(parents=True, exist_ok=True)
            _write_csv([s.to_dict() for s in scored],
                       output_dir / "vrtx_regn_backtest_results.csv")
            _write_csv([m.to_dict() for m in all_metrics],
                       output_dir / "vrtx_regn_metrics_summary.csv")
            error_rows = _collect_error_rows(scored)
            _write_csv(error_rows, output_dir / "vrtx_regn_error_review.csv")
            # Leakage audit output (passed, but save for provenance)
            Path(output_dir / "vrtx_regn_leakage_audit.csv").write_text(
                "status,rows_audited,columns_audited,violations\n"
                f"PASSED,{audit.rows_audited},{audit.columns_audited},0\n",
                encoding="utf-8",
            )
            print(f"Outputs written to: {output_dir}")

        return {
            "n_rows": len(scored),
            "n_metrics": len(all_metrics),
            "leakage_violations": 0,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_feature_store(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Feature store not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(dict(row))
    return rows


def _rank_within_groups(scored: list[ScoredRow]) -> list[ScoredRow]:
    """Rank targets within each (acquirer, snapshot_date) group by score descending."""
    from collections import defaultdict
    groups: dict[str, list[ScoredRow]] = defaultdict(list)
    for s in scored:
        key = f"{s.acquirer_ticker}_{s.snapshot_date}"
        groups[key].append(s)

    result: list[ScoredRow] = []
    for group in groups.values():
        n = len(group)
        sorted_group = sorted(group, key=lambda x: x.pair_score, reverse=True)
        for rank_idx, row in enumerate(sorted_group, start=1):
            result.append(ScoredRow(
                **{**asdict(row),
                   "rank": rank_idx,
                   "n_candidates": n,
                   "percentile": 1.0 - (rank_idx - 1) / max(n - 1, 1),
                   }
            ))
    return result


def _compute_metrics(scored: list[ScoredRow]) -> list[RankingMetrics]:
    """Compute ranking metrics for each (acquirer, days_before) combination."""
    from collections import defaultdict
    import statistics

    groups: dict[tuple[str, int], list[ScoredRow]] = defaultdict(list)
    for s in scored:
        groups[(s.acquirer_ticker, s.days_before)].append(s)

    metrics: list[RankingMetrics] = []
    for (acquirer, days_before), group in sorted(groups.items()):
        # Find snapshots (groups within groups by snapshot_date)
        snap_groups: dict[str, list[ScoredRow]] = defaultdict(list)
        for s in group:
            snap_groups[s.snapshot_date].append(s)

        n_groups = len(snap_groups)
        positives = [s for s in group if s.label_is_positive]
        n_pos = len(positives)

        if n_pos == 0:
            continue

        hit_k: dict[int, int] = {1: 0, 3: 0, 5: 0, 10: 0}
        percentiles: list[float] = []
        reciprocal_ranks: list[float] = []
        brier_scores: list[float] = []
        all_scores: list[float] = []
        all_labels: list[int] = []

        for snap_date, snap_group in snap_groups.items():
            sorted_snap = sorted(snap_group, key=lambda x: x.pair_score, reverse=True)
            n_snap = len(sorted_snap)
            decile_cutoff = max(1, n_snap // 10)
            positives_in_snap = [s for s in sorted_snap if s.label_is_positive]
            if not positives_in_snap:
                continue
            pos = positives_in_snap[0]
            for k in hit_k:
                if pos.rank <= k:
                    hit_k[k] += 1
            if n_snap > decile_cutoff and pos.rank <= decile_cutoff:
                hit_k[1] += 0  # tracked separately for top_decile
            percentiles.append(pos.percentile)
            reciprocal_ranks.append(1.0 / pos.rank)
            for s in sorted_snap:
                brier_scores.append((s.pair_score - float(s.label_is_positive)) ** 2)
                all_scores.append(s.pair_score)
                all_labels.append(int(s.label_is_positive))

        def safe_div(n: int) -> float:
            return n / n_groups if n_groups > 0 else 0.0

        auc = _compute_auc(all_labels, all_scores)
        calibration_err = _compute_calibration_error(all_labels, all_scores)

        # top_decile: re-check
        top_decile_hits = 0
        for snap_date, snap_group in snap_groups.items():
            sorted_snap = sorted(snap_group, key=lambda x: x.pair_score, reverse=True)
            n_snap = len(sorted_snap)
            decile_cutoff = max(1, round(n_snap * 0.10))
            positives_in_snap = [s for s in sorted_snap if s.label_is_positive]
            if positives_in_snap and positives_in_snap[0].rank <= decile_cutoff:
                top_decile_hits += 1

        metrics.append(RankingMetrics(
            acquirer=acquirer,
            days_before=days_before,
            n_groups=n_groups,
            n_total_candidates=len(group),
            top_1_hit_rate=safe_div(hit_k[1]),
            top_3_hit_rate=safe_div(hit_k[3]),
            top_5_hit_rate=safe_div(hit_k[5]),
            top_10_hit_rate=safe_div(hit_k[10]),
            top_decile_hit_rate=safe_div(top_decile_hits),
            mean_percentile_rank=statistics.mean(percentiles) if percentiles else 0.0,
            median_percentile_rank=statistics.median(percentiles) if percentiles else 0.0,
            mean_reciprocal_rank=statistics.mean(reciprocal_ranks) if reciprocal_ranks else 0.0,
            auc_roc=auc,
            brier_score=statistics.mean(brier_scores) if brier_scores else 0.0,
            precision_at_5=safe_div(hit_k[5]),
            precision_at_10=safe_div(hit_k[10]),
            calibration_error=calibration_err,
            n_verified_deals=n_pos,
            caveats=f"N={n_pos} verified deals. Wide CIs. Do not overclaim.",
        ))
    return metrics


def _compute_auc(labels: list[int], scores: list[float]) -> float:
    if len(set(labels)) < 2:
        return 0.5
    try:
        n_pos = sum(labels)
        n_neg = len(labels) - n_pos
        if n_pos == 0 or n_neg == 0:
            return 0.5
        pairs = sorted(zip(scores, labels), reverse=True)
        auc = 0.0
        tp = 0
        fp = 0
        prev_score = None
        prev_tp = 0
        prev_fp = 0
        for score, label in pairs:
            if score != prev_score:
                auc += (fp - prev_fp) * (tp + prev_tp) / 2.0
                prev_score = score
                prev_tp = tp
                prev_fp = fp
            if label == 1:
                tp += 1
            else:
                fp += 1
        auc += (fp - prev_fp) * (tp + prev_tp) / 2.0
        return auc / (n_pos * n_neg) if n_pos * n_neg > 0 else 0.5
    except Exception:
        return 0.5


def _compute_calibration_error(labels: list[int], scores: list[float], n_bins: int = 5) -> float:
    if not labels:
        return 0.0
    try:
        bin_size = 1.0 / n_bins
        errors = []
        for b in range(n_bins):
            lo = b * bin_size
            hi = lo + bin_size
            bin_pairs = [(lb, sc) for lb, sc in zip(labels, scores) if lo <= sc < hi]
            if not bin_pairs:
                continue
            avg_label = sum(lb for lb, sc in bin_pairs) / len(bin_pairs)
            avg_score = sum(sc for lb, sc in bin_pairs) / len(bin_pairs)
            errors.append(abs(avg_score - avg_label))
        return sum(errors) / len(errors) if errors else 0.0
    except Exception:
        return 0.0


def _collect_error_rows(scored: list[ScoredRow]) -> list[dict[str, Any]]:
    """Collect false positives and false negatives for review."""
    errors: list[dict[str, Any]] = []
    for s in scored:
        if s.label_is_positive and s.rank > 5:
            errors.append({**s.to_dict(), "error_type": "false_negative",
                           "note": f"Actual target ranked {s.rank}/{s.n_candidates}"})
        elif not s.label_is_positive and s.rank <= 3:
            errors.append({**s.to_dict(), "error_type": "false_positive",
                           "note": f"Non-target ranked {s.rank}/{s.n_candidates}"})
    return errors


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve.backtest_research.vrtx_regn_backtest_runner",
        description="Run VRTX/REGN M&A backtest.",
    )
    parser.add_argument("--dataset", default="research/backtests/vrtx_regn_2010/curated")
    parser.add_argument("--score-mode", default="approved_only",
                        choices=["approved_only", "provisional", "structural", "evidence_backed"])
    parser.add_argument("--output", default="research/backtests/vrtx_regn_2010/outputs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    dataset_dir = Path(args.dataset)
    feature_store_path = dataset_dir / "vrtx_regn_feature_store.csv"
    if not feature_store_path.exists():
        print(f"ERROR: feature store not found at {feature_store_path}", file=sys.stderr)
        print("Run vrtx_regn_dataset_builder first.", file=sys.stderr)
        return 1

    from bve.backtest_research.leakage_guard import LeakageViolationError

    runner = BacktestRunner(score_mode=args.score_mode)
    output_dir = Path(args.output)
    try:
        summary = runner.run(
            feature_store_path=feature_store_path,
            output_dir=output_dir,
            dry_run=args.dry_run,
        )
    except LeakageViolationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print(f"Rows scored: {summary['n_rows']}")
    print(f"Metrics computed: {summary['n_metrics']}")

    if not args.dry_run:
        from bve.backtest_research.report_writer import ReportWriter
        report = ReportWriter(output_dir)
        report.write(
            results_path=output_dir / "vrtx_regn_backtest_results.csv",
            metrics_path=output_dir / "vrtx_regn_metrics_summary.csv",
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
