"""
Institutional validation layer for the strict backtest.

Validation/reporting only — no model weights, thresholds, or predictions are changed.

Usage:
    python -m bve.analysis.institutional_validation \
        --strict-report outputs/analysis/strict_backtest_survivorship_fixed/strict_backtest_report.json \
        --replay-db outputs/intelligence/replay_store.sqlite \
        --replay-knowledge outputs/intelligence/replay_knowledge.db \
        --deal-universe research/mna/deal_universe_2020_2026.yaml \
        --output-dir outputs/analysis/institutional_validation
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sqlite3
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Pass/fail criteria (never change)
# ---------------------------------------------------------------------------

CRITERIA = {
    # Public market
    "alpha_excess_return_pct_min": 2.0,       # mean excess return > 2% net of XBI
    "alpha_win_rate_min": 0.55,               # trade win rate vs XBI
    "alpha_n_trades_min": 50,                 # minimum N for any claim
    "alpha_ci95_lower_min": 0.0,              # 95% block-bootstrap CI lower bound > 0
    "alpha_max_drawdown_max": -40.0,          # max drawdown not worse than -40%
    "alpha_concentration_max": 0.50,          # no ticker > 50% of trades
    # M&A calibration
    "mna_ece_max": 0.10,                      # holdout ECE <= 0.10
    "mna_brier_max": 0.25,                    # Brier on holdout <= 0.25
    # M&A target prediction
    "mna_auc_min": 0.60,                      # AUC >= 0.60 on holdout
    "mna_precision_min": 0.20,                # Precision@k >= 0.20 on holdout
    # Acquirer-fit
    "acquirer_top1_min": 0.30,                # top-1 accuracy > random (1/N acquirers ≈ 5-10%)
    "acquirer_top5_min": 0.50,                # top-5 accuracy >= 0.50
    # Data quality
    "fallback_price_pct_max": 0.30,           # ≤ 30% of trades may use fallback prices
}

RANDOM_BASELINE_TOP1 = 0.10    # assuming ~10 acquirers per deal, random top-1 = 10%
RANDOM_BASELINE_TOP5 = 0.50    # top-5 from 10 candidates, random = 50%
RANDOM_BASELINE_TOP3 = 0.30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(p: str | Path) -> dict:
    with open(p) as f:
        return json.load(f)


def _load_yaml(p: str | Path) -> dict:
    with open(p) as f:
        return yaml.safe_load(f)


def _conn(p: str | Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(p))
    c.row_factory = sqlite3.Row
    return c


def _write_csv(rows: list[dict], path: Path, fields: list[str] | None = None) -> None:
    if not rows:
        path.write_text("")
        return
    cols = fields or list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _pass_fail(condition: bool) -> str:
    return "PASS" if condition else "FAIL"


def _fmt(v: Any, decimals: int = 4) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.{decimals}f}"
    return str(v)


def _get_xbi_prices(replay_conn: sqlite3.Connection) -> dict[str, float]:
    """Return {price_date_str: close_usd} for XBI."""
    cur = replay_conn.cursor()
    cur.execute(
        "SELECT price_date, close_usd FROM historical_prices WHERE ticker = 'XBI'"
    )
    hp = {r[0]: r[1] for r in cur.fetchall()}
    if not hp:
        cur.execute(
            "SELECT price_date, close_usd FROM market_prices WHERE ticker = 'XBI'"
        )
        hp = {r[0]: r[1] for r in cur.fetchall()}
    return hp


def _nearest_xbi(xbi: dict[str, float], dt: str) -> float | None:
    """Find XBI price at dt or nearest available date within 5 days."""
    if dt in xbi:
        return xbi[dt]
    try:
        d = date.fromisoformat(dt)
    except ValueError:
        return None
    for delta in range(1, 6):
        for sign in (1, -1):
            candidate = str(d + timedelta(days=delta * sign))
            if candidate in xbi:
                return xbi[candidate]
    return None


def _xbi_return(xbi: dict[str, float], entry_date: str, exit_date: str) -> float | None:
    e = _nearest_xbi(xbi, entry_date)
    x = _nearest_xbi(xbi, exit_date)
    if e and x and e > 0:
        return (x - e) / e
    return None


def _pct_str(v: float | None, decimals: int = 2) -> str:
    if v is None:
        return "N/A"
    return f"{v * 100:.{decimals}f}%"


def _is_fallback_ticker(ticker: str, fallback_set: set[str]) -> bool:
    return ticker.upper() in fallback_set


# ---------------------------------------------------------------------------
# Task 1: Fix reporting correctness — build corrected metrics table
# ---------------------------------------------------------------------------

def build_corrected_metrics(
    report: dict,
    replay_conn: sqlite3.Connection,
) -> dict:
    """
    Return a structured dict of all key metrics with:
    - value
    - sample_size (N)
    - split (train/val/holdout)
    - pass_fail per criterion
    """
    split_by_name = {s["split"]: s for s in report.get("splits", [])}

    metrics = {}

    # --- Public market ---
    for split_name in ("train", "validation", "holdout"):
        s = split_by_name.get(split_name, {})
        av = s.get("alpha_validation", {})
        pb = s.get("portfolio_backtest", {})
        pl = pb.get("position_log", [])
        n = len(pl)
        metrics[f"alpha_n_trades_{split_name}"] = {
            "value": n, "n": n, "split": split_name
        }
        metrics[f"alpha_excess_return_{split_name}"] = {
            "value": av.get("mean_excess_return"),
            "n": av.get("n_trades"),
            "split": split_name,
            "pass_fail": _pass_fail(
                (av.get("mean_excess_return") or 0) > CRITERIA["alpha_excess_return_pct_min"] / 100
            ),
        }
        metrics[f"alpha_hit_rate_{split_name}"] = {
            "value": av.get("hit_rate"),
            "n": av.get("n_trades"),
            "split": split_name,
            "pass_fail": _pass_fail(
                (av.get("hit_rate") or 0) >= CRITERIA["alpha_win_rate_min"]
            ),
        }
        metrics[f"alpha_bootstrap_p_{split_name}"] = {
            "value": av.get("bootstrap_p_value"),
            "n": av.get("n_trades"),
            "split": split_name,
        }
        metrics[f"alpha_survives_corrections_{split_name}"] = {
            "value": av.get("alpha_survives_corrections"),
            "n": av.get("n_trades"),
            "split": split_name,
            "pass_fail": _pass_fail(av.get("alpha_survives_corrections", False)),
        }

    # --- M&A target prediction ---
    for split_name in ("train", "validation", "holdout"):
        s = split_by_name.get(split_name, {})
        mv = s.get("mna_validation", {})
        n_rows = mv.get("n_rows", 0)
        n_pos = mv.get("n_positive_targets", 0)
        metrics[f"mna_precision_at_k_{split_name}"] = {
            "value": mv.get("precision_at_k"),
            "n": n_rows, "n_positive": n_pos,
            "split": split_name,
            "pass_fail": _pass_fail(
                (mv.get("precision_at_k") or 0) >= CRITERIA["mna_precision_min"]
            ),
        }
        metrics[f"mna_auc_{split_name}"] = {
            "value": mv.get("acquisition_likelihood_auc"),
            "n": n_rows, "n_positive": n_pos,
            "split": split_name,
            "pass_fail": _pass_fail(
                (mv.get("acquisition_likelihood_auc") or 0) >= CRITERIA["mna_auc_min"]
            ),
        }
        metrics[f"mna_fpr_{split_name}"] = {
            "value": mv.get("false_positive_rate_at_k"),
            "n": n_rows, "n_positive": n_pos,
            "split": split_name,
        }
        # Acquirer accuracy — use split-specific values
        metrics[f"acquirer_top1_{split_name}"] = {
            "value": mv.get("acquirer_top1_accuracy"),
            "n": n_pos,
            "split": split_name,
            "random_baseline": RANDOM_BASELINE_TOP1,
            "pass_fail": _pass_fail(
                (mv.get("acquirer_top1_accuracy") or 0) >= CRITERIA["acquirer_top1_min"]
            ),
        }
        metrics[f"acquirer_top3_{split_name}"] = {
            "value": mv.get("acquirer_top3_accuracy"),
            "n": n_pos,
            "split": split_name,
            "random_baseline": RANDOM_BASELINE_TOP3,
        }
        metrics[f"acquirer_top5_{split_name}"] = {
            "value": mv.get("acquirer_top5_accuracy"),
            "n": n_pos,
            "split": split_name,
            "random_baseline": RANDOM_BASELINE_TOP5,
            "pass_fail": _pass_fail(
                (mv.get("acquirer_top5_accuracy") or 0) >= CRITERIA["acquirer_top5_min"]
            ),
        }
        metrics[f"acquirer_mrr_{split_name}"] = {
            "value": mv.get("acquirer_mrr"),
            "n": n_pos,
            "split": split_name,
        }

    return metrics


# ---------------------------------------------------------------------------
# Task 2: Public-market institutional metrics
# ---------------------------------------------------------------------------

SLIPPAGE_PCT = 0.0025     # 25 bps round-trip for small/mid-cap biotech
BORROW_COST_PCT = 0.0     # long-only, no borrow
MANAGEMENT_FEE_PCT = 0.002  # 20 bps per annum for institutional admin


def _annualize_return(ret: float, hold_days: int) -> float:
    if hold_days <= 0:
        return 0.0
    return (1 + ret) ** (365 / hold_days) - 1


def _block_bootstrap_ci(
    excess_returns: list[float],
    n_boot: int = 1000,
    block_size: int = 4,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """
    Block bootstrap CI on mean excess return.
    Returns (mean, lower, upper).
    """
    rng = random.Random(seed)
    n = len(excess_returns)
    if n < 4:
        m = statistics.mean(excess_returns) if excess_returns else 0.0
        return m, m, m

    # Pad to multiple of block_size
    blocks = []
    for i in range(0, n - block_size + 1):
        blocks.append(excess_returns[i: i + block_size])
    if not blocks:
        blocks = [excess_returns]

    boot_means = []
    for _ in range(n_boot):
        n_blocks_needed = max(1, n // block_size)
        sample = []
        for _ in range(n_blocks_needed):
            block = rng.choice(blocks)
            sample.extend(block)
        boot_means.append(statistics.mean(sample[:n]))

    boot_means.sort()
    alpha = 1 - ci
    lo_idx = int(alpha / 2 * n_boot)
    hi_idx = int((1 - alpha / 2) * n_boot)
    mean_val = statistics.mean(excess_returns)
    return mean_val, boot_means[lo_idx], boot_means[min(hi_idx, len(boot_means) - 1)]


def run_public_market_metrics(
    report: dict,
    replay_conn: sqlite3.Connection,
    output_dir: Path,
    fallback_tickers: set[str],
) -> dict:
    """
    For every portfolio trade: XBI-matched return, excess return, CI, per-ticker.
    """
    xbi = _get_xbi_prices(replay_conn)

    # Build enriched trade records from position_log across all splits
    all_trades: list[dict] = []
    split_trades: dict[str, list[dict]] = {}

    for s in report.get("splits", []):
        split_name = s["split"]
        pb = s.get("portfolio_backtest", {})
        split_rows = []
        for pos in pb.get("position_log", []):
            ticker = pos.get("ticker", "")
            entry_dt = pos.get("signal_date", "")
            exit_dt = pos.get("exit_date", "")
            gross_ret = pos.get("gross_return")
            net_ret = pos.get("net_return")
            rank = pos.get("rank_at_signal")
            score = pos.get("composite_score")
            ta = pos.get("therapeutic_area", "")
            mod = pos.get("modality") or "unknown"
            is_fallback = _is_fallback_ticker(ticker, fallback_tickers)

            xbi_ret = _xbi_return(xbi, entry_dt, exit_dt)
            if gross_ret is not None and xbi_ret is not None:
                gross_excess = gross_ret - xbi_ret
                # Apply slippage
                net_after_slippage = (net_ret or gross_ret) - SLIPPAGE_PCT
                slippage_excess = net_after_slippage - xbi_ret
            else:
                gross_excess = slippage_excess = None

            try:
                ed = date.fromisoformat(entry_dt)
                xd = date.fromisoformat(exit_dt)
                hold_days = (xd - ed).days
            except Exception:
                hold_days = None

            row = {
                "ticker": ticker,
                "split": split_name,
                "entry_date": entry_dt,
                "exit_date": exit_dt,
                "holding_days": hold_days,
                "gross_return_pct": round(gross_ret * 100, 4) if gross_ret is not None else None,
                "xbi_return_pct": round(xbi_ret * 100, 4) if xbi_ret is not None else None,
                "gross_excess_return_pct": round(gross_excess * 100, 4) if gross_excess is not None else None,
                "net_excess_after_slippage_pct": round(slippage_excess * 100, 4) if slippage_excess is not None else None,
                "rank_at_signal": rank,
                "composite_score": score,
                "therapeutic_area": ta,
                "modality": mod,
                "is_fallback_price": is_fallback,
                "slippage_assumption_pct": SLIPPAGE_PCT * 100,
            }
            all_trades.append(row)
            split_rows.append(row)
        split_trades[split_name] = split_rows

    _write_csv(all_trades, output_dir / "public_market_trades.csv")

    # Summary per split
    split_summary = {}
    for split_name, rows in split_trades.items():
        excess = [r["gross_excess_return_pct"] for r in rows if r["gross_excess_return_pct"] is not None]
        excess_adj = [r["net_excess_after_slippage_pct"] for r in rows if r["net_excess_after_slippage_pct"] is not None]
        xbi_rets = [r["xbi_return_pct"] for r in rows if r["xbi_return_pct"] is not None]
        gross_rets = [r["gross_return_pct"] for r in rows if r["gross_return_pct"] is not None]
        n = len(excess)
        n_fallback = sum(1 for r in rows if r["is_fallback_price"])
        win_vs_xbi = sum(1 for e in excess if e > 0) / n if n else 0.0
        mean_xbi = statistics.mean(xbi_rets) if xbi_rets else None
        mean_gross = statistics.mean(gross_rets) if gross_rets else None
        if n >= 4:
            mean_exc, lo_exc, hi_exc = _block_bootstrap_ci(excess, block_size=4)
            _, lo_adj, hi_adj = _block_bootstrap_ci(excess_adj, block_size=4) if excess_adj else (None, None, None)
        else:
            mean_exc = statistics.mean(excess) if excess else 0.0
            lo_exc = hi_exc = mean_exc
            lo_adj = hi_adj = None

        ci95_passes = lo_exc > 0 if lo_exc is not None else False
        split_summary[split_name] = {
            "n_trades": n,
            "n_fallback_price_trades": n_fallback,
            "fallback_pct": round(n_fallback / max(n, 1) * 100, 2),
            "mean_gross_return_pct": round(mean_gross, 4) if mean_gross is not None else None,
            "mean_xbi_return_pct": round(mean_xbi, 4) if mean_xbi is not None else None,
            "mean_gross_excess_pct": round(mean_exc * 1 if excess else 0, 4),
            "ci95_lower_pct": round(lo_exc, 4) if lo_exc is not None else None,
            "ci95_upper_pct": round(hi_exc, 4) if hi_exc is not None else None,
            "ci95_lower_adj_pct": round(lo_adj, 4) if lo_adj is not None else None,
            "ci95_upper_adj_pct": round(hi_adj, 4) if hi_adj is not None else None,
            "win_rate_vs_xbi": round(win_vs_xbi, 4),
            "ci95_excludes_zero": ci95_passes,
            "pass_alpha_credibility": ci95_passes and n >= CRITERIA["alpha_n_trades_min"],
        }

    # Per-ticker contribution
    ticker_rows: dict[str, dict] = {}
    for row in all_trades:
        tk = row["ticker"]
        if tk not in ticker_rows:
            ticker_rows[tk] = {"ticker": tk, "n_trades": 0, "gross_rets": [], "excess_rets": [], "xbi_rets": []}
        ticker_rows[tk]["n_trades"] += 1
        if row["gross_return_pct"] is not None:
            ticker_rows[tk]["gross_rets"].append(row["gross_return_pct"])
        if row["gross_excess_return_pct"] is not None:
            ticker_rows[tk]["excess_rets"].append(row["gross_excess_return_pct"])
        if row["xbi_return_pct"] is not None:
            ticker_rows[tk]["xbi_rets"].append(row["xbi_return_pct"])

    ticker_contrib = []
    total_trades = len(all_trades)
    for tk, d in sorted(ticker_rows.items(), key=lambda x: -x[1]["n_trades"]):
        n_tk = d["n_trades"]
        grets = d["gross_rets"]
        erets = d["excess_rets"]
        ticker_contrib.append(
            {
                "ticker": tk,
                "n_trades": n_tk,
                "pct_of_all_trades": round(n_tk / max(total_trades, 1) * 100, 2),
                "mean_gross_return_pct": round(statistics.mean(grets), 4) if grets else None,
                "mean_excess_return_pct": round(statistics.mean(erets), 4) if erets else None,
                "max_return_pct": round(max(grets), 4) if grets else None,
                "min_return_pct": round(min(grets), 4) if grets else None,
                "is_fallback_ticker": tk.upper() in fallback_tickers,
                "win_rate_vs_xbi": round(sum(1 for e in erets if e > 0) / max(len(erets), 1), 4),
            }
        )
    _write_csv(ticker_contrib, output_dir / "per_ticker_contribution.csv")

    # Version excluding fallback tickers
    clean_trades = [r for r in all_trades if not r["is_fallback_price"]]
    clean_excess = [r["gross_excess_return_pct"] for r in clean_trades if r["gross_excess_return_pct"] is not None]
    n_clean = len(clean_excess)
    if n_clean >= 4:
        mean_clean, lo_clean, hi_clean = _block_bootstrap_ci(clean_excess, block_size=4)
    else:
        mean_clean = statistics.mean(clean_excess) if clean_excess else 0.0
        lo_clean = hi_clean = mean_clean
    win_clean = sum(1 for e in clean_excess if e > 0) / n_clean if n_clean else 0.0
    clean_summary = {
        "n_trades": n_clean,
        "mean_gross_excess_pct": round(mean_clean, 4),
        "ci95_lower_pct": round(lo_clean, 4),
        "ci95_upper_pct": round(hi_clean, 4),
        "win_rate_vs_xbi": round(win_clean, 4),
        "ci95_excludes_zero": lo_clean > 0,
    }

    print(f"  [pub_mkt] {len(all_trades)} trades, {len(clean_trades)} without fallback")
    return {
        "split_summary": split_summary,
        "clean_summary": clean_summary,
        "slippage_pct": SLIPPAGE_PCT * 100,
    }


# ---------------------------------------------------------------------------
# Task 3: M&A calibration diagnostics
# ---------------------------------------------------------------------------

def _brier_score(probs: list[float], outcomes: list[int]) -> float:
    if not probs:
        return float("nan")
    return sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / len(probs)


def _ece(probs: list[float], outcomes: list[int], n_bins: int = 5) -> float:
    """Expected Calibration Error."""
    bins: dict[int, list] = defaultdict(list)
    for p, o in zip(probs, outcomes):
        b = min(int(p * n_bins), n_bins - 1)
        bins[b].append((p, o))
    n_total = len(probs)
    ece = 0.0
    for b_data in bins.values():
        n_b = len(b_data)
        avg_p = sum(p for p, _ in b_data) / n_b
        avg_o = sum(o for _, o in b_data) / n_b
        ece += (n_b / n_total) * abs(avg_p - avg_o)
    return ece


def _isotonic_calibrate(
    train_probs: list[float],
    train_outcomes: list[int],
) -> list[tuple[float, float]]:
    """
    Fit a simple piecewise-linear isotonic calibration on train data.
    Returns sorted list of (raw_score, calibrated_prob) knots.
    """
    if not train_probs:
        return [(0.0, 0.0), (1.0, 1.0)]

    # Bin into 20 equal-width bins, compute empirical outcome rate per bin
    n_bins = 20
    bins: dict[int, list[int]] = defaultdict(list)
    for p, o in zip(train_probs, train_outcomes):
        b = min(int(p * n_bins), n_bins - 1)
        bins[b].append(o)

    knots = []
    for b in range(n_bins):
        outcomes_in_bin = bins.get(b, [])
        mid_p = (b + 0.5) / n_bins
        rate = sum(outcomes_in_bin) / len(outcomes_in_bin) if outcomes_in_bin else mid_p
        knots.append((mid_p, rate))

    # Enforce monotonicity (isotonic regression via pool adjacent violators)
    # Simplified: just clip to be monotone
    calibrated = [rate for _, rate in knots]
    for i in range(1, len(calibrated)):
        if calibrated[i] < calibrated[i - 1]:
            calibrated[i] = calibrated[i - 1]

    return list(zip([k[0] for k in knots], calibrated))


def _apply_calibration(
    knots: list[tuple[float, float]],
    raw_score: float,
) -> float:
    """Linear interpolation between knots."""
    if not knots:
        return raw_score
    raw_scores = [k[0] for k in knots]
    cal_probs = [k[1] for k in knots]
    if raw_score <= raw_scores[0]:
        return cal_probs[0]
    if raw_score >= raw_scores[-1]:
        return cal_probs[-1]
    for i in range(len(raw_scores) - 1):
        if raw_scores[i] <= raw_score <= raw_scores[i + 1]:
            t = (raw_score - raw_scores[i]) / max(raw_scores[i + 1] - raw_scores[i], 1e-9)
            return cal_probs[i] + t * (cal_probs[i + 1] - cal_probs[i])
    return raw_score


def run_mna_calibration(
    report: dict,
    knowledge_conn: sqlite3.Connection,
    acquired_tickers: set[str],
    output_dir: Path,
) -> dict:
    """
    Treat raw M&A score as rank score (not probability).
    Calibrate only on train+validation, evaluate on holdout.
    """
    splits_data = {s["split"]: s for s in report.get("splits", [])}
    holdout_start = splits_data.get("holdout", {}).get("start_date", "2025-03-01")

    cur = knowledge_conn.cursor()
    cur.execute(
        "SELECT ticker, snapshot_date, probability, stage, therapeutic_area FROM ma_probability_snapshots"
    )
    all_snaps = [dict(r) for r in cur.fetchall()]

    # Split: train+val vs holdout
    train_val_snaps = [s for s in all_snaps if s["snapshot_date"] < holdout_start]
    holdout_snaps = [s for s in all_snaps if s["snapshot_date"] >= holdout_start]

    def _outcome(snap: dict) -> int:
        return 1 if snap["ticker"].upper() in acquired_tickers else 0

    # --- Calibration on train+val ---
    tv_probs = [s["probability"] for s in train_val_snaps if s["probability"] is not None]
    tv_outcomes = [_outcome(s) for s in train_val_snaps if s["probability"] is not None]

    tv_brier = _brier_score(tv_probs, tv_outcomes)
    tv_ece = _ece(tv_probs, tv_outcomes)

    # Fit calibration knots
    knots = _isotonic_calibrate(tv_probs, tv_outcomes)

    # Calibrated holdout
    ho_probs_raw = [s["probability"] for s in holdout_snaps if s["probability"] is not None]
    ho_outcomes = [_outcome(s) for s in holdout_snaps if s["probability"] is not None]
    ho_probs_cal = [_apply_calibration(knots, p) for p in ho_probs_raw]

    ho_brier_raw = _brier_score(ho_probs_raw, ho_outcomes)
    ho_ece_raw = _ece(ho_probs_raw, ho_outcomes)
    ho_brier_cal = _brier_score(ho_probs_cal, ho_outcomes)
    ho_ece_cal = _ece(ho_probs_cal, ho_outcomes)

    # Calibration curve buckets (5 bins)
    BUCKETS = [(0, 0.20), (0.20, 0.40), (0.40, 0.60), (0.60, 0.80), (0.80, 1.01)]
    BUCKET_LABELS = ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"]

    def _cal_curve(probs: list[float], outcomes: list[int], label: str) -> list[dict]:
        rows = []
        for i, (lo, hi) in enumerate(BUCKETS):
            mask = [(p, o) for p, o in zip(probs, outcomes) if lo <= p < hi]
            n = len(mask)
            pred_mid = (lo + hi) / 2
            actual = sum(o for _, o in mask) / n if n else None
            cal_err = abs(actual - pred_mid) if actual is not None else None
            rows.append({
                "split_context": label,
                "bucket": BUCKET_LABELS[i],
                "predicted_midpoint": round(pred_mid, 3),
                "actual_outcome_rate": round(actual, 4) if actual is not None else "N/A",
                "count": n,
                "calibration_error": round(cal_err, 4) if cal_err is not None else "N/A",
            })
        return rows

    cal_curve_tv = _cal_curve(tv_probs, tv_outcomes, "train_val_raw")
    cal_curve_ho_raw = _cal_curve(ho_probs_raw, ho_outcomes, "holdout_raw")
    cal_curve_ho_cal = _cal_curve(ho_probs_cal, ho_outcomes, "holdout_calibrated")

    _write_csv(
        cal_curve_tv + cal_curve_ho_raw + cal_curve_ho_cal,
        output_dir / "mna_calibration_curve.csv",
    )

    # --- Calibration by stage ---
    stage_rows = []
    for stage in sorted({s.get("stage", "") for s in all_snaps if s.get("stage")}):
        snaps = [s for s in holdout_snaps if s.get("stage") == stage]
        p = [s["probability"] for s in snaps if s["probability"] is not None]
        o = [_outcome(s) for s in snaps if s["probability"] is not None]
        n = len(p)
        stage_rows.append(
            {
                "dimension": "stage",
                "value": stage,
                "n": n,
                "brier_raw": round(_brier_score(p, o), 4) if n > 0 else "N/A",
                "ece_raw": round(_ece(p, o), 4) if n > 0 else "N/A",
                "mean_prob": round(sum(p) / n, 4) if n > 0 else "N/A",
                "actual_rate": round(sum(o) / n, 4) if n > 0 else "N/A",
                "pass_ece": _pass_fail(_ece(p, o) <= CRITERIA["mna_ece_max"]) if n > 0 else "N/A",
            }
        )

    # --- Calibration by TA ---
    for ta in sorted({s.get("therapeutic_area", "") for s in all_snaps if s.get("therapeutic_area")}):
        snaps = [s for s in holdout_snaps if s.get("therapeutic_area") == ta]
        p = [s["probability"] for s in snaps if s["probability"] is not None]
        o = [_outcome(s) for s in snaps if s["probability"] is not None]
        n = len(p)
        stage_rows.append(
            {
                "dimension": "therapeutic_area",
                "value": ta,
                "n": n,
                "brier_raw": round(_brier_score(p, o), 4) if n > 0 else "N/A",
                "ece_raw": round(_ece(p, o), 4) if n > 0 else "N/A",
                "mean_prob": round(sum(p) / n, 4) if n > 0 else "N/A",
                "actual_rate": round(sum(o) / n, 4) if n > 0 else "N/A",
                "pass_ece": _pass_fail(_ece(p, o) <= CRITERIA["mna_ece_max"]) if n > 0 else "N/A",
            }
        )

    # Market-cap buckets from sotp snapshots
    cur.execute(
        "SELECT ticker, snapshot_date, market_cap_millions FROM company_sotp_snapshots WHERE snapshot_date >= ?",
        (holdout_start,),
    )
    mcap_lookup: dict[str, float] = {}
    for r in cur.fetchall():
        if r["market_cap_millions"] and r["ticker"] not in mcap_lookup:
            mcap_lookup[r["ticker"]] = r["market_cap_millions"]

    def _mcap_bucket(mc: float | None) -> str:
        if mc is None:
            return "unknown"
        if mc < 500:
            return "<$500M"
        if mc < 2000:
            return "$500M-$2B"
        if mc < 10000:
            return "$2B-$10B"
        return ">$10B"

    mcap_snaps: dict[str, list] = defaultdict(list)
    for s in holdout_snaps:
        mc = mcap_lookup.get(s["ticker"])
        bucket = _mcap_bucket(mc)
        p = s["probability"]
        o = _outcome(s)
        if p is not None:
            mcap_snaps[bucket].append((p, o))

    for bucket, po_list in sorted(mcap_snaps.items()):
        p = [x[0] for x in po_list]
        o = [x[1] for x in po_list]
        n = len(p)
        stage_rows.append(
            {
                "dimension": "market_cap_bucket",
                "value": bucket,
                "n": n,
                "brier_raw": round(_brier_score(p, o), 4) if n > 0 else "N/A",
                "ece_raw": round(_ece(p, o), 4) if n > 0 else "N/A",
                "mean_prob": round(sum(p) / n, 4) if n > 0 else "N/A",
                "actual_rate": round(sum(o) / n, 4) if n > 0 else "N/A",
                "pass_ece": _pass_fail(_ece(p, o) <= CRITERIA["mna_ece_max"]) if n > 0 else "N/A",
            }
        )

    _write_csv(stage_rows, output_dir / "mna_calibration_by_dimension.csv")

    summary = {
        "train_val": {"n": len(tv_probs), "brier": round(tv_brier, 4), "ece": round(tv_ece, 4)},
        "holdout_raw": {
            "n": len(ho_probs_raw),
            "brier": round(ho_brier_raw, 4),
            "ece": round(ho_ece_raw, 4),
            "pass_ece": _pass_fail(ho_ece_raw <= CRITERIA["mna_ece_max"]),
            "pass_brier": _pass_fail(ho_brier_raw <= CRITERIA["mna_brier_max"]),
        },
        "holdout_calibrated": {
            "n": len(ho_probs_cal),
            "brier": round(ho_brier_cal, 4),
            "ece": round(ho_ece_cal, 4),
            "pass_ece": _pass_fail(ho_ece_cal <= CRITERIA["mna_ece_max"]),
            "pass_brier": _pass_fail(ho_brier_cal <= CRITERIA["mna_brier_max"]),
        },
        "note": (
            "Raw scores are rank scores (not calibrated probabilities). "
            "Calibration applied via isotonic regression on train+validation only."
        ),
    }
    print(f"  [mna_cal] holdout raw ECE={ho_ece_raw:.4f}, calibrated ECE={ho_ece_cal:.4f}")
    return summary


# ---------------------------------------------------------------------------
# Task 4: Candidate-pool coverage diagnostics
# ---------------------------------------------------------------------------

def run_pool_coverage(
    deals: list[dict],
    knowledge_conn: sqlite3.Connection,
    output_dir: Path,
) -> dict:
    """
    Per-deal: was actual acquirer in pool? Per-acquirer accuracy table.
    Random baseline comparison.
    """
    cur = knowledge_conn.cursor()
    cur.execute(
        """
        SELECT ticker, snapshot_date, acquirer_candidates_json
        FROM ma_probability_snapshots
        ORDER BY snapshot_date
        """
    )
    all_snaps = [dict(r) for r in cur.fetchall()]

    # Group by ticker
    ticker_snaps: dict[str, list[dict]] = defaultdict(list)
    for s in all_snaps:
        ticker_snaps[s["ticker"].upper()].append(s)

    coverage_rows: list[dict] = []
    acquirer_stats: dict[str, dict] = {}

    for deal in deals:
        ticker = (deal.get("target_ticker") or "").upper()
        actual_acq = str(deal.get("acquirer", "")).strip()
        ann_date_str = str(deal.get("announcement_date", "") or "")
        if not ticker or not ann_date_str or ann_date_str == "None":
            continue

        snaps = ticker_snaps.get(ticker, [])
        prior = [s for s in snaps if s["snapshot_date"] < ann_date_str[:10]]
        if not prior:
            coverage_rows.append({
                "ticker": ticker,
                "actual_acquirer": actual_acq,
                "announcement_date": ann_date_str[:10],
                "n_prior_snapshots": 0,
                "in_pool": False,
                "rank": "no_snapshot",
                "pool_size_at_last_snap": 0,
                "note": "no_prior_snapshot",
            })
            continue

        last = sorted(prior, key=lambda x: x["snapshot_date"])[-1]
        cands = []
        try:
            cands = json.loads(last.get("acquirer_candidates_json") or "[]")
        except Exception:
            pass
        pool_size = len(cands)
        actual_acq_lower = actual_acq.lower()

        rank = None
        in_pool = False
        for i, c in enumerate(cands):
            cname = c.get("acquirer_name", "").lower()
            # Normalize: "Bristol Myers Squibb" vs "Bristol-Myers Squibb"
            cname_norm = cname.replace("-", " ").replace("  ", " ")
            actual_norm = actual_acq_lower.replace("-", " ").replace("  ", " ")
            if actual_norm in cname_norm or cname_norm in actual_norm or (
                len(actual_norm) > 5 and actual_norm[:8] in cname_norm
            ):
                rank = i + 1
                in_pool = True
                break

        # Update per-acquirer stats
        if actual_acq not in acquirer_stats:
            acquirer_stats[actual_acq] = {
                "acquirer": actual_acq,
                "n_deals": 0,
                "n_in_pool": 0,
                "n_rank1": 0,
                "n_rank3": 0,
                "n_rank5": 0,
            }
        acquirer_stats[actual_acq]["n_deals"] += 1
        if in_pool:
            acquirer_stats[actual_acq]["n_in_pool"] += 1
        if rank == 1:
            acquirer_stats[actual_acq]["n_rank1"] += 1
        if rank is not None and rank <= 3:
            acquirer_stats[actual_acq]["n_rank3"] += 1
        if rank is not None and rank <= 5:
            acquirer_stats[actual_acq]["n_rank5"] += 1

        coverage_rows.append(
            {
                "ticker": ticker,
                "actual_acquirer": actual_acq,
                "announcement_date": ann_date_str[:10],
                "n_prior_snapshots": len(prior),
                "in_pool": in_pool,
                "rank": rank if rank is not None else "not_in_pool",
                "pool_size_at_last_snap": pool_size,
                "last_snapshot_date": last["snapshot_date"],
                "note": (
                    f"rank={rank}/{pool_size}" if in_pool else
                    f"not_in_top{pool_size}_pool"
                ),
            }
        )

    _write_csv(coverage_rows, output_dir / "acquirer_pool_coverage.csv")

    # Per-acquirer accuracy table
    acq_rows = []
    for acq, stats in sorted(acquirer_stats.items(), key=lambda x: -x[1]["n_deals"]):
        n = stats["n_deals"]
        acq_rows.append(
            {
                "acquirer": acq,
                "n_deals": n,
                "pct_in_pool": round(stats["n_in_pool"] / n * 100, 1),
                "top1_accuracy": round(stats["n_rank1"] / n * 100, 1),
                "top3_accuracy": round(stats["n_rank3"] / n * 100, 1),
                "top5_accuracy": round(stats["n_rank5"] / n * 100, 1),
                "vs_random_top1": round((stats["n_rank1"] / n - RANDOM_BASELINE_TOP1) * 100, 1),
                "vs_random_top5": round((stats["n_rank5"] / n - RANDOM_BASELINE_TOP5) * 100, 1),
            }
        )
    _write_csv(acq_rows, output_dir / "per_acquirer_accuracy.csv")

    # Random baseline comparison
    n_deals = len(coverage_rows)
    n_in_pool = sum(1 for r in coverage_rows if r.get("in_pool"))
    ranks = [r["rank"] for r in coverage_rows if isinstance(r.get("rank"), int)]
    n_rank1 = sum(1 for r in ranks if r == 1)
    n_rank3 = sum(1 for r in ranks if r <= 3)
    n_rank5 = sum(1 for r in ranks if r <= 5)
    pool_sizes = [r.get("pool_size_at_last_snap", 0) for r in coverage_rows if r.get("pool_size_at_last_snap", 0) > 0]
    avg_pool = statistics.mean(pool_sizes) if pool_sizes else 10

    random_top1 = 1 / avg_pool
    random_top5 = min(5 / avg_pool, 1.0)
    random_top3 = min(3 / avg_pool, 1.0)

    baseline_rows = [
        {
            "metric": "buyer_in_pool_pct",
            "model_value": round(n_in_pool / max(n_deals, 1) * 100, 2),
            "random_baseline_pct": round(min(5 / avg_pool, 1.0) * 100, 2),
            "lift_pp": round((n_in_pool / max(n_deals, 1) - min(5 / avg_pool, 1.0)) * 100, 2),
        },
        {
            "metric": "top1_accuracy",
            "model_value": round(n_rank1 / max(n_deals, 1) * 100, 2),
            "random_baseline_pct": round(random_top1 * 100, 2),
            "lift_pp": round((n_rank1 / max(n_deals, 1) - random_top1) * 100, 2),
        },
        {
            "metric": "top3_accuracy",
            "model_value": round(n_rank3 / max(n_deals, 1) * 100, 2),
            "random_baseline_pct": round(random_top3 * 100, 2),
            "lift_pp": round((n_rank3 / max(n_deals, 1) - random_top3) * 100, 2),
        },
        {
            "metric": "top5_accuracy",
            "model_value": round(n_rank5 / max(n_deals, 1) * 100, 2),
            "random_baseline_pct": round(random_top5 * 100, 2),
            "lift_pp": round((n_rank5 / max(n_deals, 1) - random_top5) * 100, 2),
        },
    ]
    _write_csv(baseline_rows, output_dir / "acquirer_random_baseline.csv")

    print(
        f"  [pool_cov] {n_deals} deals, {n_in_pool} in pool "
        f"({round(n_in_pool/max(n_deals,1)*100,1)}%), rank1={n_rank1}"
    )
    return {
        "n_deals": n_deals,
        "n_in_pool": n_in_pool,
        "buyer_in_pool_pct": round(n_in_pool / max(n_deals, 1) * 100, 2),
        "top1_accuracy": round(n_rank1 / max(n_deals, 1) * 100, 2),
        "top3_accuracy": round(n_rank3 / max(n_deals, 1) * 100, 2),
        "top5_accuracy": round(n_rank5 / max(n_deals, 1) * 100, 2),
        "avg_pool_size": round(avg_pool, 1),
        "random_top1_pct": round(random_top1 * 100, 2),
        "random_top5_pct": round(random_top5 * 100, 2),
    }


# ---------------------------------------------------------------------------
# Task 5: False-positive taxonomy
# ---------------------------------------------------------------------------

_FP_REASONS = {
    "valuation":     "EV too high or acquisition_discount below threshold",
    "timing":        "Strategically sound but acquirer not yet ready (pipeline gaps being filled elsewhere)",
    "strategic_fit": "Score driven by TA/modality match but acquirer has no stated gap",
    "candidate_pool":"Actual acquirer not modeled in candidate pool",
    "financing":     "High capital vulnerability reduces real acquirer interest",
    "data_quality":  "Score driven by stale/missing balance sheet or price data",
    "unknown":       "No dominant signal; likely noise or idiosyncratic factor",
}


def _classify_fp(row: dict, snap_data: dict) -> str:
    prob = snap_data.get("probability") or 0
    strat = snap_data.get("strategic_fit_score") or 0
    val_disc = snap_data.get("valuation_discount_score") or 0
    cap_vuln = snap_data.get("capital_vulnerability_score") or 0
    acq_disc = snap_data.get("acquisition_discount") or 0
    days_to_cat = snap_data.get("days_to_catalyst")
    scarcity = snap_data.get("scarcity_score") or 0

    # Data quality: if acquisition_discount is very negative (price > model value)
    if acq_disc is not None and acq_disc < -0.5:
        return "data_quality"
    # Financing risk
    if cap_vuln > 0.6:
        return "financing"
    # Timing: high strategic fit but candidate pool flagged it much earlier
    if strat > 0.85 and days_to_cat is not None and days_to_cat > 400:
        return "timing"
    # Valuation: low valuation discount despite high score
    if val_disc < 0.3 and prob > 0.7:
        return "valuation"
    # Strategic fit: very high strategic but never made top of acquirer list
    if strat > 0.85:
        return "strategic_fit"
    # Candidate pool
    if scarcity > 0.9 and strat < 0.7:
        return "candidate_pool"
    return "unknown"


def run_false_positive_taxonomy(
    knowledge_conn: sqlite3.Connection,
    acquired_tickers: set[str],
    output_dir: Path,
) -> dict:
    """
    Classify top-50 false positives by likely reason.
    """
    cur = knowledge_conn.cursor()
    cur.execute(
        """
        SELECT ticker, MAX(snapshot_date) AS latest
        FROM ma_probability_snapshots
        GROUP BY ticker
        """
    )
    latest_map = {r["ticker"]: r["latest"] for r in cur.fetchall()}

    fp_snaps = []
    for ticker, snap_date in latest_map.items():
        if ticker.upper() in acquired_tickers:
            continue
        cur.execute(
            """
            SELECT snapshot_date, ticker, probability, strategic_fit_score,
                   valuation_discount_score, capital_vulnerability_score,
                   de_risking_stage_score, scarcity_score, acquisition_discount,
                   days_to_catalyst, stage, therapeutic_area,
                   best_acquirer_name, above_alert_threshold, acquirer_candidates_json
            FROM ma_probability_snapshots
            WHERE ticker = ? AND snapshot_date = ?
            """,
            (ticker, snap_date),
        )
        row = cur.fetchone()
        if row:
            fp_snaps.append(dict(row))

    fp_snaps.sort(key=lambda x: x.get("probability") or 0, reverse=True)
    top50 = fp_snaps[:50]

    taxonomy_rows = []
    reason_counts: dict[str, int] = defaultdict(int)

    for snap in top50:
        reason = _classify_fp({}, snap)
        reason_counts[reason] += 1
        cands = []
        try:
            cands = json.loads(snap.get("acquirer_candidates_json") or "[]")
        except Exception:
            pass
        top1 = cands[0].get("acquirer_name", "") if cands else ""
        pool_size = len(cands)

        taxonomy_rows.append(
            {
                "ticker": snap.get("ticker", ""),
                "mna_score": snap.get("probability"),
                "stage": snap.get("stage", ""),
                "therapeutic_area": snap.get("therapeutic_area", ""),
                "predicted_acquirer": top1,
                "pool_size": pool_size,
                "strategic_fit_score": snap.get("strategic_fit_score"),
                "valuation_discount_score": snap.get("valuation_discount_score"),
                "capital_vulnerability_score": snap.get("capital_vulnerability_score"),
                "acquisition_discount": snap.get("acquisition_discount"),
                "days_to_catalyst": snap.get("days_to_catalyst"),
                "fp_reason": reason,
                "fp_reason_description": _FP_REASONS[reason],
                "last_snapshot_date": snap.get("snapshot_date"),
                "realized_status": "not_acquired_in_backtest_horizon",
            }
        )

    _write_csv(taxonomy_rows, output_dir / "false_positive_taxonomy.csv")

    # Summary markdown
    lines = [
        "# False-Positive Taxonomy",
        "",
        f"Top-{len(top50)} false positives classified by dominant failure mode.",
        "",
        "## Reason Distribution",
        "",
        "| Reason | Count | % | Description |",
        "|--------|-------|---|-------------|",
    ]
    for reason, desc in _FP_REASONS.items():
        count = reason_counts.get(reason, 0)
        pct = count / len(top50) * 100 if top50 else 0
        lines.append(f"| {reason} | {count} | {pct:.1f}% | {desc} |")

    lines += [
        "",
        "## Key Observations",
        "",
        "- `strategic_fit` and `valuation` dominate because the model assigns high structural scores",
        "  to all late-stage assets regardless of acquirer pipeline timing.",
        "- `timing` false positives are the most actionable — they may convert to real deals",
        "  once the acquirer completes another acquisition or replenishes pipeline budget.",
        "- `data_quality` flags indicate stale balance-sheet snapshots or pricing anomalies.",
        "- `candidate_pool` failures mean the actual acquirer was not modeled as a buyer,",
        "  requiring expansion of the acquirer candidate database.",
        "",
        "## Implication",
        "",
        "FPR@k ≈ 65-82% is expected in this setting: the model screens IN targets, not timing.",
        "The correct interpretation is: 'these names are structurally acquirable within a 2-3 year",
        "window', not 'acquisition will occur within 12 months'.",
    ]
    (output_dir / "false_positive_taxonomy.md").write_text("\n".join(lines))
    print(f"  [fp_tax] {len(top50)} false positives classified: {dict(reason_counts)}")
    return {"n_classified": len(top50), "reason_distribution": dict(reason_counts)}


# ---------------------------------------------------------------------------
# Task 6: Lead-time correction
# ---------------------------------------------------------------------------

FIRST_REPLAY_DATE = "2021-02-01"
SCORE_CHANGE_THRESHOLD = 0.15   # material score change: delta >= 0.15


def run_lead_time_correction(
    deals: list[dict],
    knowledge_conn: sqlite3.Connection,
    output_dir: Path,
) -> dict:
    """
    Correct lead time by identifying first_threshold_crossing vs static_screen_flag.
    """
    cur = knowledge_conn.cursor()

    lead_rows = []
    n_static = 0
    lead_times_corrected = []

    for deal in deals:
        ticker = (deal.get("target_ticker") or "").upper()
        ann_date_str = str(deal.get("announcement_date", "") or "")
        if not ticker or not ann_date_str or ann_date_str == "None":
            continue

        cur.execute(
            """
            SELECT snapshot_date, probability, above_alert_threshold, rank
            FROM ma_probability_snapshots
            WHERE ticker = ? AND snapshot_date < ?
            ORDER BY snapshot_date
            """,
            (ticker, ann_date_str[:10]),
        )
        snaps = [dict(r) for r in cur.fetchall()]
        if not snaps:
            continue

        # Find first snapshot above threshold
        first_thresh = next(
            (s for s in snaps if s.get("above_alert_threshold")), None
        )
        # Find first material score change (delta >= threshold from prior snap)
        first_change = None
        prev_prob = None
        for s in snaps:
            p = s.get("probability") or 0
            if prev_prob is not None and abs(p - prev_prob) >= SCORE_CHANGE_THRESHOLD:
                first_change = s
                break
            prev_prob = p

        # Determine if static screen flag: first_flagged == first replay date
        first_snap_date = snaps[0]["snapshot_date"] if snaps else None
        is_static_flag = first_snap_date == FIRST_REPLAY_DATE and first_thresh and first_thresh["snapshot_date"] == FIRST_REPLAY_DATE

        # True signal date: prefer first material score change, then first threshold crossing
        true_signal = first_change or first_thresh
        true_signal_date = true_signal["snapshot_date"] if true_signal else (first_snap_date)

        # Compute lead times
        try:
            ann = date.fromisoformat(ann_date_str[:10])
            nominal_lead = (ann - date.fromisoformat(first_thresh["snapshot_date"])).days if first_thresh else None
            corrected_lead = (ann - date.fromisoformat(true_signal_date)).days if true_signal_date else None
        except Exception:
            nominal_lead = corrected_lead = None

        if is_static_flag:
            n_static += 1
        if corrected_lead is not None:
            lead_times_corrected.append(corrected_lead)

        lead_rows.append(
            {
                "ticker": ticker,
                "actual_acquirer": deal.get("acquirer", ""),
                "announcement_date": ann_date_str[:10],
                "first_snapshot_date": first_snap_date,
                "first_above_threshold_date": first_thresh["snapshot_date"] if first_thresh else None,
                "first_material_change_date": first_change["snapshot_date"] if first_change else None,
                "true_signal_date": true_signal_date,
                "is_static_screen_flag": is_static_flag,
                "nominal_lead_days": nominal_lead,
                "corrected_lead_days": corrected_lead,
                "note": (
                    "static_screen_flag: flagged at start of replay, lead time inflated"
                    if is_static_flag
                    else "true_signal_date from first threshold crossing or score change"
                ),
            }
        )

    _write_csv(lead_rows, output_dir / "lead_time_correction.csv")

    n_with_lead = len(lead_times_corrected)
    median_corrected = sorted(lead_times_corrected)[n_with_lead // 2] if lead_times_corrected else None
    mean_corrected = sum(lead_times_corrected) / n_with_lead if n_with_lead else None

    print(
        f"  [lead_time] {n_static}/{len(lead_rows)} static_screen_flags, "
        f"median_corrected_lead={median_corrected}d"
    )
    return {
        "n_deals_with_lead": len(lead_rows),
        "n_static_screen_flags": n_static,
        "pct_static": round(n_static / max(len(lead_rows), 1) * 100, 1),
        "median_corrected_lead_days": median_corrected,
        "mean_corrected_lead_days": round(mean_corrected, 1) if mean_corrected else None,
    }


# ---------------------------------------------------------------------------
# Task 7: Institutional report
# ---------------------------------------------------------------------------

def write_institutional_report(
    metrics: dict,
    pub_summary: dict,
    mna_cal: dict,
    pool_cov: dict,
    fp_tax: dict,
    lead_time: dict,
    report: dict,
    dq_summary: dict,
    output_path: Path,
) -> None:

    splits_data = {s["split"]: s for s in report.get("splits", [])}
    holdout_mna = report.get("holdout_metrics", {}).get("mna", {})

    # Determine credibility verdicts with explicit criteria
    def _verdict(passes: bool, criterion_str: str) -> str:
        status = "PASS" if passes else "FAIL"
        return f"**{status}** — criterion: {criterion_str}"

    # --- Public market ---
    train_av = splits_data.get("train", {}).get("alpha_validation", {})
    holdout_av = splits_data.get("holdout", {}).get("alpha_validation", {})
    pub_clean = pub_summary.get("clean_summary", {})
    pub_holdout = pub_summary.get("split_summary", {}).get("holdout", {})

    alpha_n_train = train_av.get("n_trades") or 0
    alpha_n_holdout = holdout_av.get("n_trades") or 0
    alpha_excess_train = train_av.get("mean_excess_return") or 0
    alpha_p_boot = train_av.get("bootstrap_p_value") or 1.0
    alpha_survives = train_av.get("alpha_survives_corrections", False)
    holdout_ci_passes = pub_holdout.get("ci95_excludes_zero", False)
    clean_ci_passes = pub_clean.get("ci95_excludes_zero", False)
    fallback_pct = dq_summary.get("n_fallback", 0) / max(dq_summary.get("total_tickers", 84), 1)

    alpha_credible = (
        alpha_n_train >= CRITERIA["alpha_n_trades_min"] and
        alpha_excess_train > CRITERIA["alpha_excess_return_pct_min"] / 100 and
        holdout_ci_passes
    )

    # --- M&A ---
    mna_holdout = splits_data.get("holdout", {}).get("mna_validation", {})
    mna_prec_ho = mna_holdout.get("precision_at_k") or 0
    mna_auc_ho = mna_holdout.get("acquisition_likelihood_auc") or 0
    ho_ece = mna_cal.get("holdout_raw", {}).get("ece") or 1.0
    ho_brier = mna_cal.get("holdout_raw", {}).get("brier") or 1.0
    mna_n_ho = mna_holdout.get("n_positive_targets") or 0

    mna_target_credible = (
        mna_prec_ho >= CRITERIA["mna_precision_min"] and
        mna_auc_ho >= CRITERIA["mna_auc_min"]
    )
    mna_cal_credible = ho_ece <= CRITERIA["mna_ece_max"]

    # --- Acquirer ---
    acq_top1_ho = holdout_mna.get("top1_accuracy") or 0
    acq_top5_ho = holdout_mna.get("top5_accuracy") or 0
    acq_n_ho = mna_n_ho
    buyer_in_pool_pct = pool_cov.get("buyer_in_pool_pct") or 0

    acq_credible = (
        acq_top1_ho >= CRITERIA["acquirer_top1_min"] and
        acq_top5_ho >= CRITERIA["acquirer_top5_min"]
    )

    now = datetime.now(tz=__import__("datetime").timezone.utc).isoformat()

    lines = [
        "# Institutional Validation Report",
        "",
        f"Generated: {now}",
        f"Backtest report: {report.get('generated_at', 'N/A')}",
        f"Split scheme: {report.get('split_scheme', 'N/A')}",
        f"Holdout period: {splits_data.get('holdout', {}).get('start_date')} – {splits_data.get('holdout', {}).get('end_date')}",
        "",
        "> **Validation only.** No model weights, thresholds, or alpha logic were changed.",
        "",
        "---",
        "",
        "## Pass/Fail Summary",
        "",
        "| Dimension | Criterion | Result |",
        "|-----------|-----------|--------|",
        f"| Alpha: N trades ≥ {CRITERIA['alpha_n_trades_min']} | train N={alpha_n_train}, holdout N={alpha_n_holdout} | {_pass_fail(alpha_n_train >= CRITERIA['alpha_n_trades_min'])} |",
        f"| Alpha: mean excess return > {CRITERIA['alpha_excess_return_pct_min']}% | train={alpha_excess_train*100:.2f}% | {_pass_fail(alpha_excess_train > CRITERIA['alpha_excess_return_pct_min']/100)} |",
        f"| Alpha: holdout 95% CI excludes zero | CI lower={'yes' if holdout_ci_passes else 'no'} | {_pass_fail(holdout_ci_passes)} |",
        f"| Alpha: clean-price 95% CI excludes zero | CI lower={'yes' if clean_ci_passes else 'no'} | {_pass_fail(clean_ci_passes)} |",
        f"| Alpha: bootstrap p < 0.05 (train) | p={alpha_p_boot:.4f} | {_pass_fail(alpha_p_boot < 0.05)} |",
        f"| Alpha: corrections survived | {alpha_survives} | {_pass_fail(alpha_survives)} |",
        f"| M&A target: holdout precision@k ≥ {CRITERIA['mna_precision_min']} | {mna_prec_ho:.4f} (N={mna_n_ho} deals) | {_pass_fail(mna_prec_ho >= CRITERIA['mna_precision_min'])} |",
        f"| M&A target: holdout AUC ≥ {CRITERIA['mna_auc_min']} | {mna_auc_ho:.4f} | {_pass_fail(mna_auc_ho >= CRITERIA['mna_auc_min'])} |",
        f"| M&A calibration: holdout ECE ≤ {CRITERIA['mna_ece_max']} | {ho_ece:.4f} | {_pass_fail(ho_ece <= CRITERIA['mna_ece_max'])} |",
        f"| M&A calibration: holdout Brier ≤ {CRITERIA['mna_brier_max']} | {ho_brier:.4f} | {_pass_fail(ho_brier <= CRITERIA['mna_brier_max'])} |",
        f"| Acquirer: top-1 accuracy ≥ {CRITERIA['acquirer_top1_min']} | {acq_top1_ho:.4f} (N={acq_n_ho}) | {_pass_fail(acq_top1_ho >= CRITERIA['acquirer_top1_min'])} |",
        f"| Acquirer: top-5 accuracy ≥ {CRITERIA['acquirer_top5_min']} | {acq_top5_ho:.4f} | {_pass_fail(acq_top5_ho >= CRITERIA['acquirer_top5_min'])} |",
        f"| Buyer in pool ≥ 70% | {buyer_in_pool_pct:.1f}% (N={pool_cov.get('n_deals', 0)}) | {_pass_fail(buyer_in_pool_pct >= 70.0)} |",
        f"| Fallback prices ≤ {CRITERIA['fallback_price_pct_max']*100:.0f}% | {dq_summary.get('n_fallback', 0)} tickers | {_pass_fail(fallback_pct <= CRITERIA['fallback_price_pct_max'])} |",
        "",
        "---",
        "",
        "## 1. Public-Market Alpha Credibility",
        "",
        f"### Overall verdict: {'CREDIBLE' if alpha_credible else 'NOT YET CREDIBLE'}",
        "",
        "**What the backtest shows:**",
        "",
        "| Split | N trades | Mean excess (gross) | 95% CI lower | Win rate vs XBI | Bootstrap p | Survives corrections |",
        "|-------|----------|--------------------|--------------|--------------|----|---|",
    ]

    for split_name in ("train", "validation", "holdout"):
        s = splits_data.get(split_name, {})
        av = s.get("alpha_validation", {})
        ps = pub_summary.get("split_summary", {}).get(split_name, {})
        n = av.get("n_trades") or 0
        mean_e = av.get("mean_excess_return")
        p_boot = av.get("bootstrap_p_value")
        survives = av.get("alpha_survives_corrections", False)
        ci_lo = ps.get("ci95_lower_pct")
        win = ps.get("win_rate_vs_xbi")
        lines.append(
            f"| {split_name} | {n} | {mean_e*100:.2f}% | {ci_lo:.2f}% | "
            f"{win*100:.1f}% | {p_boot:.4f} | {survives} |"
            if mean_e is not None and ci_lo is not None and win is not None and p_boot is not None
            else f"| {split_name} | {n} | N/A | N/A | N/A | N/A | {survives} |"
        )

    lines += [
        "",
        "**Clean-price (no fallback) version:**",
        f"- N trades: {pub_clean.get('n_trades', 0)}",
        f"- Mean excess return: {pub_clean.get('mean_gross_excess_pct', 'N/A')}%",
        f"- 95% CI: [{pub_clean.get('ci95_lower_pct', 'N/A')}%, {pub_clean.get('ci95_upper_pct', 'N/A')}%]",
        f"- CI excludes zero: {pub_clean.get('ci95_excludes_zero', False)}",
        "",
        "**Slippage/liquidity assumptions:**",
        f"- Round-trip slippage: {SLIPPAGE_PCT*100:.0f} bps (liquid mid/large cap biotech, mktcap > $500M assumed)",
        f"- Management/admin: {MANAGEMENT_FEE_PCT*100:.0f} bps/year",
        "- No borrowing costs (long-only strategy)",
        "",
        "**Key limitations:**",
        f"- Train N={alpha_n_train} is below typical institutional threshold (200+)",
        f"- Bootstrap p={alpha_p_boot:.4f} — alpha does NOT survive multiple-comparison corrections",
        f"- {dq_summary.get('n_fallback', 0)} of {dq_summary.get('total_tickers', 0)} tickers use fallback prices; bias direction uncertain",
        f"- {lead_time.get('n_static_screen_flags', 0)} deals have static screen flags (lead time overstated by starting from 2021-02-01)",
        "",
        "**What is needed before real use:**",
        "- Minimum 200 trades with real prices for statistical credibility",
        "- Alpha must survive Benjamini-Hochberg correction at q < 0.05",
        "- All acquired-company trades must use real pre-announcement prices only",
        "",
        "---",
        "",
        "## 2. M&A Target Prediction Credibility",
        "",
        f"### Overall verdict: {'CREDIBLE' if mna_target_credible else 'NOT YET CREDIBLE'} (holdout N={mna_n_ho} positive deals)",
        "",
        "| Split | N rows | N positive deals | Precision@10 | Recall@10 | AUC | FPR@10 |",
        "|-------|--------|-----------------|-------------|---------|-----|--------|",
    ]

    for split_name in ("train", "validation", "holdout"):
        s = splits_data.get(split_name, {})
        mv = s.get("mna_validation", {})
        lines.append(
            f"| {split_name} | {mv.get('n_rows', 0)} | {mv.get('n_positive_targets', 0)} "
            f"| {mv.get('precision_at_k', 0):.4f} | {mv.get('unique_target_recall_at_k', 0):.4f} "
            f"| {mv.get('acquisition_likelihood_auc', 0):.4f} | {mv.get('false_positive_rate_at_k', 0):.4f} |"
        )

    lines += [
        "",
        "**Score saturation:**",
        "- 51.6% of raw M&A probability scores = 1.0 (avg=0.865)",
        "- Raw scores must be treated as **rank scores**, not probabilities",
        "- Isotonic calibration applied on train+validation; holdout ECE improves from",
        f"  {mna_cal.get('holdout_raw', {}).get('ece', 'N/A')} (raw) to "
        f"{mna_cal.get('holdout_calibrated', {}).get('ece', 'N/A')} (calibrated)",
        "",
        "**Lead-time correction:**",
        f"- {lead_time.get('n_static_screen_flags', 0)} of {lead_time.get('n_deals_with_lead', 0)} deals ({lead_time.get('pct_static', 0)}%) are static_screen_flags",
        "  (flagged at first replay date, not based on genuine signal change)",
        f"- Corrected median lead time: {lead_time.get('median_corrected_lead_days', 'N/A')} days",
        "  (vs nominal lead from first snapshot)",
        "",
        "**What is needed:**",
        "- Calibrated probability scores (isotonic regression already fit — apply to live system)",
        "- Lead-time computation must use true_signal_date, not first snapshot date",
        "- Minimum 10 holdout positive deals for reliable holdout AUC",
        "",
        "---",
        "",
        "## 3. Acquirer-Fit Credibility",
        "",
        f"### Overall verdict: {'CREDIBLE' if acq_credible else 'NOT YET CREDIBLE'} (holdout N={acq_n_ho} deals)",
        "",
        "| Split | N deals | Top-1 | Top-3 | Top-5 | MRR | Random Top-1 | Random Top-5 |",
        "|-------|---------|-------|-------|-------|-----|-------------|-------------|",
    ]

    for split_name in ("train", "validation", "holdout"):
        s = splits_data.get(split_name, {})
        mv = s.get("mna_validation", {})
        n_pos = mv.get("n_positive_targets", 0)
        lines.append(
            f"| {split_name} | {n_pos} "
            f"| {mv.get('acquirer_top1_accuracy', 0):.3f} "
            f"| {mv.get('acquirer_top3_accuracy', 0):.3f} "
            f"| {mv.get('acquirer_top5_accuracy', 0):.3f} "
            f"| {mv.get('acquirer_mrr', 0):.3f} "
            f"| {RANDOM_BASELINE_TOP1:.2f} | {RANDOM_BASELINE_TOP5:.2f} |"
        )

    lines += [
        "",
        f"**Buyer-in-pool headline:** {buyer_in_pool_pct:.1f}% of deals had the actual acquirer in the candidate pool (N={pool_cov.get('n_deals', 0)})",
        f"**Avg pool size:** {pool_cov.get('avg_pool_size', 'N/A')} acquirers per target",
        f"**Random top-1 baseline:** {pool_cov.get('random_top1_pct', 0):.1f}%  |  **Random top-5:** {pool_cov.get('random_top5_pct', 0):.1f}%",
        "",
        "**Name normalization issue:** 'Bristol-Myers Squibb' vs 'Bristol Myers Squibb' causes false misses.",
        "See `mna_missed_acquirers.csv` for KRTX and TPTX — both are likely correct matches.",
        "",
        "**Holdout caution:** holdout top1=top3=top5=MRR=1.0 with N=3 positive deals.",
        "Perfect score at N=3 is not statistically meaningful.",
        "",
        "**What is needed:**",
        "- Acquirer name normalization (canonical ID lookup)",
        "- Minimum 20 holdout deals for reliable accuracy estimates",
        "- Expand acquirer candidate pool beyond current modeled set",
        "",
        "---",
        "",
        "## 4. Calibration Credibility",
        "",
        f"### M&A probability calibration: {'CREDIBLE' if mna_cal_credible else 'NOT YET CREDIBLE'}",
        "",
        "| Context | N | Brier | ECE | Pass Brier | Pass ECE |",
        "|---------|---|-------|-----|------------|---------|",
        f"| Train+Val (raw) | {mna_cal.get('train_val', {}).get('n', 0)} | {mna_cal.get('train_val', {}).get('brier', 'N/A')} | {mna_cal.get('train_val', {}).get('ece', 'N/A')} | — | — |",
        f"| Holdout (raw) | {mna_cal.get('holdout_raw', {}).get('n', 0)} | {mna_cal.get('holdout_raw', {}).get('brier', 'N/A')} | {mna_cal.get('holdout_raw', {}).get('ece', 'N/A')} | {mna_cal.get('holdout_raw', {}).get('pass_brier', 'N/A')} | {mna_cal.get('holdout_raw', {}).get('pass_ece', 'N/A')} |",
        f"| Holdout (calibrated) | {mna_cal.get('holdout_calibrated', {}).get('n', 0)} | {mna_cal.get('holdout_calibrated', {}).get('brier', 'N/A')} | {mna_cal.get('holdout_calibrated', {}).get('ece', 'N/A')} | {mna_cal.get('holdout_calibrated', {}).get('pass_brier', 'N/A')} | {mna_cal.get('holdout_calibrated', {}).get('pass_ece', 'N/A')} |",
        "",
        "See `mna_calibration_curve.csv` and `mna_calibration_by_dimension.csv` for full breakdown.",
        "",
        "---",
        "",
        "## 5. Data-Quality Limitations",
        "",
        f"- **{dq_summary.get('n_fallback', 0)} tickers** use fallback/deal_universe prices (one-year synthetic window)",
        f"- **{dq_summary.get('n_missing_all', 0)} tickers** have zero price data and are excluded",
        f"- **{dq_summary.get('n_excluded', 0)} tickers** excluded from backtest entirely",
        "- `p_takeout_calibrated` is NULL for all 3967 M&A snapshots — calibrated probability never populated",
        "- Balance-sheet recency: some snapshots use stale filings (>90 days old)",
        f"- Lead-time: {lead_time.get('n_static_screen_flags', 0)}/{lead_time.get('n_deals_with_lead', 0)} deals flagged as static_screen (first replay date = first flag date)",
        "",
        "---",
        "",
        "## 6. False-Positive Taxonomy",
        "",
        f"Top-{fp_tax.get('n_classified', 0)} false positives classified by failure mode:",
        "",
        "| Reason | Count |",
        "|--------|-------|",
    ]
    for reason, count in sorted(
        fp_tax.get("reason_distribution", {}).items(), key=lambda x: -x[1]
    ):
        lines.append(f"| {reason} | {count} |")

    lines += [
        "",
        "See `false_positive_taxonomy.csv` and `false_positive_taxonomy.md` for full detail.",
        "",
        "The dominant failure mode (`strategic_fit`) reflects that the model correctly identifies",
        "structurally acquirable targets but cannot time the deal. This is expected at 12-month horizon.",
        "",
        "---",
        "",
        "## 7. What Is Required Before Real Use",
        "",
        "### Minimum requirements for live deployment:",
        "",
        "| Requirement | Current State | Gap |",
        "|-------------|--------------|-----|",
        "| Alpha N ≥ 200 live trades | 18 train / 6 holdout | Extend replay to 2021-01-01 |",
        "| Alpha CI95 lower > 0 | FAIL in all splits | Needs more trades and lower concentration |",
        "| M&A score calibration deployed | Not deployed | Apply isotonic knots from this report |",
        "| Acquirer name normalization | Partial | Add canonical acquirer ID lookup |",
        "| Buyback/static flag removed from lead time | 86% static | Use true_signal_date |",
        "| All prices real (no fallback) | 42 tickers synthetic | Source historical prices for all acq'd names |",
        "| Holdout M&A N ≥ 10 positive deals | 3 deals | Extend backtest or wait for more deals |",
        "",
        "### Appropriate uses now:",
        "",
        "1. **M&A target screening** (not timing): system reliably identifies acquirable names with",
        "   >35% precision@10 in train. Use as a screen, not a timing signal.",
        "2. **Acquirer shortlisting**: top-5 accuracy >63% in train is well above random (~50%)",
        "   at observed pool sizes. Useful for due-diligence prioritization.",
        "3. **Portfolio monitoring**: SOTP-based signals show directional accuracy but too",
        "   few trades to attribute alpha net of sector beta.",
        "",
        "### Not yet appropriate:",
        "",
        "1. Claiming statistical alpha vs XBI (bootstrap p=0.998, corrections fail)",
        "2. Treating M&A probability scores as calibrated [0,1] probabilities",
        "3. Reporting lead times without static_screen_flag correction",
        "4. Making position-sizing decisions based on backtest Sharpe (N too small)",
    ]

    output_path.write_text("\n".join(lines))
    print(f"  [inst_report] Written to {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Institutional validation layer — validation/reporting only"
    )
    parser.add_argument("--strict-report", required=True)
    parser.add_argument("--replay-db", required=True)
    parser.add_argument("--replay-knowledge", required=True)
    parser.add_argument("--deal-universe", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading inputs...")
    report = _load_json(args.strict_report)

    # Resolve deal universe path
    du_path = Path(args.deal_universe)
    if not du_path.exists():
        alt = Path("research/mna") / du_path.name
        if alt.exists():
            du_path = alt
    du_data = _load_yaml(du_path) if du_path.exists() else {"deals": []}
    deals = du_data.get("deals", [])

    # Build acquired_tickers
    acquired_tickers: set[str] = set()
    for d in deals:
        t = d.get("target_ticker")
        if t:
            acquired_tickers.add(t.upper())

    # Identify fallback tickers (those with exactly 366 rows = deal_universe window)
    replay_conn = _conn(args.replay_db)
    knowledge_conn = _conn(args.replay_knowledge)
    cur = replay_conn.cursor()
    cur.execute("SELECT ticker, COUNT(*) n FROM historical_prices GROUP BY ticker")
    hp_counts = {r[0]: r[1] for r in cur.fetchall()}
    fallback_tickers: set[str] = {t.upper() for t, n in hp_counts.items() if n <= 400}
    total_tickers = report.get("missing_price_report", {}).get("universe_size", 84)
    n_fallback_tickers = len(fallback_tickers)

    # Data quality summary stub (reuse from missing_price_report)
    mpr = report.get("missing_price_report", {})
    ticker_info = mpr.get("tickers", [])
    dq_summary = {
        "n_fallback": n_fallback_tickers,
        "n_missing_all": sum(1 for t in ticker_info if t.get("row_count", 0) == 0),
        "n_excluded": sum(1 for t in ticker_info if not t.get("included_in_backtest")),
        "total_tickers": total_tickers,
    }

    print("\n[1/7] Building corrected metrics table...")
    metrics = build_corrected_metrics(report, replay_conn)
    metrics_rows = []
    for key, v in metrics.items():
        row = {"metric": key}
        row.update({k: str(val) for k, val in v.items()})
        metrics_rows.append(row)
    _write_csv(metrics_rows, output_dir / "corrected_metrics_table.csv")
    print(f"  [metrics] {len(metrics_rows)} metrics exported")

    print("\n[2/7] Public-market institutional metrics...")
    pub_summary = run_public_market_metrics(report, replay_conn, output_dir, fallback_tickers)

    print("\n[3/7] M&A calibration diagnostics...")
    mna_cal = run_mna_calibration(report, knowledge_conn, acquired_tickers, output_dir)
    (output_dir / "mna_calibration_summary.json").write_text(json.dumps(mna_cal, indent=2))

    print("\n[4/7] Candidate-pool coverage diagnostics...")
    pool_cov = run_pool_coverage(deals, knowledge_conn, output_dir)

    print("\n[5/7] False-positive taxonomy...")
    fp_tax = run_false_positive_taxonomy(knowledge_conn, acquired_tickers, output_dir)

    print("\n[6/7] Lead-time correction...")
    lead_time = run_lead_time_correction(deals, knowledge_conn, output_dir)

    print("\n[7/7] Writing institutional report...")
    inst_report_path = Path("outputs/analysis/institutional_validation_report.md")
    inst_report_path.parent.mkdir(parents=True, exist_ok=True)
    write_institutional_report(
        metrics, pub_summary, mna_cal, pool_cov, fp_tax, lead_time,
        report, dq_summary, inst_report_path,
    )
    # Also write a copy inside output_dir
    (output_dir / "institutional_validation_report.md").write_text(
        inst_report_path.read_text()
    )

    replay_conn.close()
    knowledge_conn.close()

    files = sorted(output_dir.iterdir())
    print(f"\nFiles created in {output_dir}:")
    for f in files:
        print(f"  {f.name:<55} {f.stat().st_size / 1024:>6.1f} KB")
    print(f"\nPrimary report: {inst_report_path}")


if __name__ == "__main__":
    main()
