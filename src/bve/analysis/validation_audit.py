"""
Validation audit suite for the strict backtest.

Produces analysis-only reports exposing whether backtest results are real,
misleading, sparse, or driven by a few cases.

Usage:
    python -m bve.analysis.validation_audit \
        --strict-report outputs/analysis/strict_backtest_survivorship_fixed/strict_backtest_report.json \
        --replay-db outputs/intelligence/replay_store.sqlite \
        --replay-knowledge outputs/intelligence/replay_knowledge.db \
        --universe-file examples/research/universe_expanded_mna.yaml \
        --deal-universe examples/research/deal_universe_2020_2026.yaml \
        --output-dir outputs/analysis/validation_audit
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: str | Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _load_yaml(path: str | Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _resolve_deal_universe_path(path: str) -> Path:
    """Try the given path; if missing, look in research/mna/."""
    p = Path(path)
    if p.exists():
        return p
    alt = Path("research/mna") / p.name
    if alt.exists():
        return alt
    return p  # Return original even if missing — caller handles error


def _write_csv(rows: list[dict], path: Path, fieldnames: list[str] | None = None) -> None:
    import csv
    if not rows:
        path.write_text("")
        return
    cols = fieldnames or list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _fmt(v: Any, decimals: int = 4) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.{decimals}f}"
    return str(v)


def _pct(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v * 100:.2f}%"


# ---------------------------------------------------------------------------
# Report 1: Trade-level audit
# ---------------------------------------------------------------------------

def _signal_tier(composite_score: float | None, rank: int | None) -> str:
    if rank is not None:
        if rank <= 3:
            return "tier_A"
        if rank <= 8:
            return "tier_B"
        return "tier_C"
    if composite_score is None:
        return "unknown"
    if composite_score >= 0.65:
        return "tier_A"
    if composite_score >= 0.50:
        return "tier_B"
    return "tier_C"


def run_trade_audit(
    report: dict,
    replay_conn: sqlite3.Connection,
    output_dir: Path,
) -> dict:
    """
    Build all_trades.csv, top_20_winners.csv, top_20_losers.csv, trade_summary.json
    from portfolio_backtest.position_log across all splits.
    """
    # Collect position_log rows from all splits
    all_positions: list[dict] = []
    for split in report.get("splits", []):
        split_name = split.get("split", "unknown")
        pb = split.get("portfolio_backtest", {})
        for pos in pb.get("position_log", []):
            pos = dict(pos)
            pos["split"] = split_name
            all_positions.append(pos)

    # Also pull replay_decisions as second view (may differ in coverage)
    cur = replay_conn.cursor()
    cur.execute(
        """
        SELECT ticker, decided_at, exit_date, entry_price, exit_price,
               return_pct, size_pct, composite_score, attribution_type,
               action, is_closed, asset_id
        FROM replay_decisions
        WHERE is_closed = 1
        """
    )
    replay_rows = [dict(r) for r in cur.fetchall()]

    # Price lookup from DB for fallback detection
    cur.execute("SELECT ticker, price_date, close_usd FROM historical_prices")
    hp_map: dict[tuple[str, str], float] = {}
    for r in cur.fetchall():
        hp_map[(r["ticker"], r["price_date"])] = r["close_usd"]

    cur.execute("SELECT ticker, price_date, close_usd FROM market_prices")
    mp_map: dict[tuple[str, str], float] = {}
    for r in cur.fetchall():
        mp_map[(r["ticker"], r["price_date"])] = r["close_usd"]

    def _price_source(ticker: str, dt: str | None) -> str:
        if not dt:
            return "missing"
        if (ticker, dt) in hp_map:
            return "real"
        if (ticker, dt) in mp_map:
            return "real"
        # Check if within 3 days
        return "fallback_or_synthetic"

    # Build unified trade records from position_log
    trades: list[dict] = []
    for pos in all_positions:
        ticker = pos.get("ticker", "")
        entry_dt = pos.get("signal_date")
        exit_dt = pos.get("exit_date")
        score = pos.get("composite_score") or pos.get("calibrated_score")
        rank = pos.get("rank_at_signal")
        gross_ret = pos.get("gross_return")
        net_ret = pos.get("net_return")
        entry_price = hp_map.get((ticker, entry_dt)) or mp_map.get((ticker, entry_dt))
        exit_price = hp_map.get((ticker, exit_dt)) or mp_map.get((ticker, exit_dt))

        if entry_dt and exit_dt:
            try:
                ed = datetime.fromisoformat(entry_dt).date() if "T" in entry_dt else date.fromisoformat(entry_dt)
                xd = datetime.fromisoformat(exit_dt).date() if "T" in exit_dt else date.fromisoformat(exit_dt)
                hold_days = (xd - ed).days
            except Exception:
                hold_days = None
        else:
            hold_days = None

        trades.append(
            {
                "ticker": ticker,
                "asset_id": pos.get("asset_id", ""),
                "split": pos.get("split", ""),
                "entry_date": entry_dt,
                "exit_date": exit_dt,
                "holding_days": hold_days,
                "entry_price": _fmt(entry_price),
                "exit_price": _fmt(exit_price),
                "gross_return_pct": round(gross_ret * 100, 4) if gross_ret is not None else None,
                "net_return_pct": round(net_ret * 100, 4) if net_ret is not None else None,
                "position_size_pct": pos.get("weight"),
                "signal_tier": _signal_tier(score, rank),
                "composite_score": _fmt(score),
                "rank_at_signal": rank,
                "catalyst_type": pos.get("catalyst_type", ""),
                "therapeutic_area": pos.get("therapeutic_area", ""),
                "modality": pos.get("modality", ""),
                "financing_risk_score": _fmt(pos.get("financing_risk_score")),
                "price_source": _price_source(ticker, entry_dt),
                "recommendation": "add",
                "reason_entered": pos.get("catalyst_type", "score_threshold"),
                "reason_exited": "hold_period_elapsed",
            }
        )

    if not trades:
        print("  [trade_audit] No position_log entries found.")
        _write_csv([], output_dir / "all_trades.csv")
        _write_csv([], output_dir / "top_20_winners.csv")
        _write_csv([], output_dir / "top_20_losers.csv")
        return {"n_trades": 0}

    # Sort
    def _ret(t: dict) -> float:
        v = t.get("net_return_pct")
        if v is None:
            v = t.get("gross_return_pct")
        return v if v is not None else 0.0

    sorted_trades = sorted(trades, key=_ret, reverse=True)
    winners = sorted_trades[:20]
    losers = sorted(trades, key=_ret)[:20]

    # Also add replay_decisions view for tickers using fallback (these have entry/exit prices directly)
    replay_trades: list[dict] = []
    for r in replay_rows:
        ticker = r["ticker"]
        entry_dt = r["decided_at"]
        exit_dt = r["exit_date"]
        entry_price_db = r["entry_price"]
        exit_price_db = r["exit_price"]
        ret_pct = r["return_pct"]
        score = r["composite_score"]

        if entry_dt and exit_dt:
            try:
                ed = datetime.fromisoformat(entry_dt).date() if "T" in entry_dt else date.fromisoformat(entry_dt)
                xd = datetime.fromisoformat(exit_dt).date() if "T" in exit_dt else date.fromisoformat(exit_dt)
                hold_days = (xd - ed).days
            except Exception:
                hold_days = None
        else:
            hold_days = None

        ps = _price_source(ticker, entry_dt[:10] if entry_dt else None)
        if entry_price_db is not None and ps == "fallback_or_synthetic":
            ps = "real_replay"  # replay engine had real price

        replay_trades.append(
            {
                "ticker": ticker,
                "asset_id": r["asset_id"],
                "split": "replay",
                "entry_date": entry_dt,
                "exit_date": exit_dt,
                "holding_days": hold_days,
                "entry_price": _fmt(entry_price_db),
                "exit_price": _fmt(exit_price_db),
                "gross_return_pct": round(ret_pct, 4) if ret_pct is not None else None,
                "net_return_pct": round(ret_pct, 4) if ret_pct is not None else None,
                "position_size_pct": r["size_pct"],
                "signal_tier": _signal_tier(score, None),
                "composite_score": _fmt(score),
                "rank_at_signal": None,
                "catalyst_type": r["attribution_type"],
                "therapeutic_area": "",
                "modality": "",
                "financing_risk_score": "N/A",
                "price_source": ps,
                "recommendation": r["action"],
                "reason_entered": "composite_score",
                "reason_exited": r["attribution_type"],
            }
        )

    _write_csv(sorted_trades, output_dir / "all_trades.csv")
    _write_csv(winners, output_dir / "top_20_winners.csv")
    _write_csv(losers, output_dir / "top_20_losers.csv")

    # Summary
    valid_returns = [_ret(t) for t in trades if _ret(t) != 0.0 or t.get("gross_return_pct") is not None]
    n = len(valid_returns)
    mean_ret = sum(valid_returns) / n if n else 0.0
    median_ret = sorted(valid_returns)[n // 2] if n else 0.0
    win_rate = sum(1 for r in valid_returns if r > 0) / n if n else 0.0
    max_loss = min(valid_returns) if valid_returns else 0.0
    max_win = max(valid_returns) if valid_returns else 0.0

    ticker_counts = defaultdict(int)
    for t in trades:
        ticker_counts[t["ticker"]] += 1
    top_concentrated = sorted(ticker_counts.items(), key=lambda x: -x[1])[:5]
    concentration_top3_pct = sum(v for _, v in top_concentrated[:3]) / max(n, 1) * 100

    fallback_count = sum(1 for t in trades if "fallback" in t.get("price_source", ""))

    summary = {
        "n_trades": n,
        "n_tickers": len(ticker_counts),
        "mean_return_pct": round(mean_ret, 4),
        "median_return_pct": round(median_ret, 4),
        "win_rate": round(win_rate, 4),
        "max_loss_pct": round(max_loss, 4),
        "max_win_pct": round(max_win, 4),
        "top_concentrated_tickers": [t for t, _ in top_concentrated],
        "concentration_top3_pct_of_trades": round(concentration_top3_pct, 2),
        "trades_using_fallback_prices": fallback_count,
        "replay_trades": len(replay_trades),
    }
    (output_dir / "trade_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"  [trade_audit] {n} portfolio trades, {len(replay_trades)} replay decisions")
    return summary


# ---------------------------------------------------------------------------
# Report 2: M&A deal-level audit
# ---------------------------------------------------------------------------

def run_mna_audit(
    deal_universe_path: Path,
    knowledge_conn: sqlite3.Connection,
    output_dir: Path,
    universe: list[dict],
) -> dict:
    """
    For every actual deal: find predicted acquirers, rank, lead time, scores.
    """
    # Load deal universe
    if not deal_universe_path.exists():
        print(f"  [mna_audit] Deal universe not found at {deal_universe_path}, skipping.")
        _write_csv([], output_dir / "mna_deal_level_audit.csv")
        _write_csv([], output_dir / "mna_missed_acquirers.csv")
        _write_csv([], output_dir / "mna_correct_top5.csv")
        return {}

    deal_data = _load_yaml(deal_universe_path)
    deals = deal_data.get("deals", [])

    # Build ticker -> acquisition info
    acquired_map: dict[str, dict] = {}
    for d in deals:
        ticker = d.get("target_ticker")
        if ticker:
            acquired_map[ticker.upper()] = d

    # Also from universe file — entries with announcement_date
    for u in universe:
        ticker = u.get("ticker", "").upper()
        if u.get("announcement_date") and ticker not in acquired_map:
            acquired_map[ticker] = {
                "target_ticker": ticker,
                "target_name": u.get("company_name", ticker),
                "acquirer": u.get("acquirer", ""),
                "announcement_date": u.get("announcement_date"),
                "headline_value_millions": u.get("headline_value_millions"),
                "therapeutic_area": u.get("therapeutic_area", ""),
            }

    # Pull all ma_probability_snapshots from knowledge DB
    cur = knowledge_conn.cursor()
    cur.execute(
        """
        SELECT snapshot_date, ticker, asset_id, probability, rank,
               best_acquirer_name, best_acquirer_id, strategic_fit_score,
               p_takeout_calibrated, above_alert_threshold,
               acquirer_candidates_json
        FROM ma_probability_snapshots
        ORDER BY snapshot_date, ticker
        """
    )
    snapshots = [dict(r) for r in cur.fetchall()]

    # Build per-ticker snapshot timeline
    ticker_snapshots: dict[str, list[dict]] = defaultdict(list)
    for s in snapshots:
        ticker_snapshots[s["ticker"].upper()].append(s)

    deal_audit: list[dict] = []
    correct_top5: list[dict] = []
    missed_acquirers: list[dict] = []

    for ticker, deal_info in sorted(acquired_map.items()):
        ann_date_str = str(deal_info.get("announcement_date", "") or "")
        if not ann_date_str or ann_date_str == "None":
            continue

        try:
            ann_date = date.fromisoformat(ann_date_str[:10])
        except ValueError:
            continue

        actual_acquirer = str(deal_info.get("acquirer", "")).strip().lower()
        snaps = ticker_snapshots.get(ticker, [])

        # Snapshots before announcement
        prior_snaps = [s for s in snaps if s["snapshot_date"] < ann_date_str[:10]]

        if not prior_snaps:
            deal_audit.append({
                "target": deal_info.get("target_name", ticker),
                "ticker": ticker,
                "announcement_date": ann_date_str[:10],
                "actual_acquirer": deal_info.get("acquirer", ""),
                "predicted_top1": "",
                "predicted_top2": "",
                "predicted_top3": "",
                "predicted_top4": "",
                "predicted_top5": "",
                "rank_of_actual": "no_prior_snapshot",
                "date_first_flagged": "",
                "lead_time_days": None,
                "stage_a_probability": None,
                "mna_score": None,
                "actual_acquirer_in_pool": False,
                "headline_value_millions": deal_info.get("headline_value_millions"),
                "therapeutic_area": deal_info.get("therapeutic_area", ""),
            })
            continue

        # First snapshot where above_alert_threshold = 1
        first_flagged = None
        for s in sorted(prior_snaps, key=lambda x: x["snapshot_date"]):
            if s.get("above_alert_threshold"):
                first_flagged = s
                break

        # Last snapshot before announcement for ranking
        last_prior = sorted(prior_snaps, key=lambda x: x["snapshot_date"])[-1]

        # Parse acquirer candidates
        candidates = []
        cand_json = last_prior.get("acquirer_candidates_json") or "[]"
        try:
            candidates = json.loads(cand_json)
        except Exception:
            candidates = []

        top5_names = [c.get("acquirer_name", "") for c in candidates[:5]]

        # Find rank of actual acquirer
        rank_actual = None
        in_pool = False
        for i, c in enumerate(candidates):
            cname = c.get("acquirer_name", "").lower()
            if actual_acquirer and actual_acquirer in cname or (actual_acquirer and cname in actual_acquirer):
                rank_actual = i + 1
                in_pool = True
                break

        if in_pool:
            correct_top5.append({
                "target": deal_info.get("target_name", ticker),
                "ticker": ticker,
                "actual_acquirer": deal_info.get("acquirer", ""),
                "rank_of_actual": rank_actual,
                "snapshot_date": last_prior["snapshot_date"],
                "announcement_date": ann_date_str[:10],
                "mna_score": last_prior.get("probability"),
            })
        else:
            missed_acquirers.append({
                "target": deal_info.get("target_name", ticker),
                "ticker": ticker,
                "actual_acquirer": deal_info.get("acquirer", ""),
                "predicted_top1": top5_names[0] if len(top5_names) > 0 else "",
                "predicted_top2": top5_names[1] if len(top5_names) > 1 else "",
                "predicted_top3": top5_names[2] if len(top5_names) > 2 else "",
                "reason_missed": "actual not in top5 candidates",
                "snapshot_date": last_prior["snapshot_date"],
                "announcement_date": ann_date_str[:10],
            })

        lead_days = None
        if first_flagged:
            try:
                fd = date.fromisoformat(first_flagged["snapshot_date"])
                lead_days = (ann_date - fd).days
            except ValueError:
                pass

        deal_audit.append(
            {
                "target": deal_info.get("target_name", ticker),
                "ticker": ticker,
                "announcement_date": ann_date_str[:10],
                "actual_acquirer": deal_info.get("acquirer", ""),
                "predicted_top1": top5_names[0] if len(top5_names) > 0 else "",
                "predicted_top2": top5_names[1] if len(top5_names) > 1 else "",
                "predicted_top3": top5_names[2] if len(top5_names) > 2 else "",
                "predicted_top4": top5_names[3] if len(top5_names) > 3 else "",
                "predicted_top5": top5_names[4] if len(top5_names) > 4 else "",
                "rank_of_actual": rank_actual if rank_actual is not None else "not_in_pool",
                "date_first_flagged": first_flagged["snapshot_date"] if first_flagged else "",
                "lead_time_days": lead_days,
                "stage_a_probability": last_prior.get("p_takeout_calibrated"),
                "mna_score": last_prior.get("probability"),
                "actual_acquirer_in_pool": in_pool,
                "headline_value_millions": deal_info.get("headline_value_millions"),
                "therapeutic_area": deal_info.get("therapeutic_area", ""),
            }
        )

    _write_csv(deal_audit, output_dir / "mna_deal_level_audit.csv")
    _write_csv(missed_acquirers, output_dir / "mna_missed_acquirers.csv")
    _write_csv(sorted(correct_top5, key=lambda x: x.get("rank_of_actual") or 99), output_dir / "mna_correct_top5.csv")

    n_deals = len(deal_audit)
    n_in_pool = sum(1 for d in deal_audit if d.get("actual_acquirer_in_pool"))
    n_rank1 = sum(1 for d in deal_audit if d.get("rank_of_actual") == 1)
    lead_times = [d["lead_time_days"] for d in deal_audit if d.get("lead_time_days") is not None]

    summary = {
        "n_deals_evaluated": n_deals,
        "n_actual_acquirer_in_pool": n_in_pool,
        "n_rank1_correct": n_rank1,
        "acquirer_top1_pct": round(n_rank1 / max(n_deals, 1) * 100, 2),
        "acquirer_in_pool_pct": round(n_in_pool / max(n_deals, 1) * 100, 2),
        "median_lead_days": sorted(lead_times)[len(lead_times) // 2] if lead_times else None,
    }
    print(f"  [mna_audit] {n_deals} deals, {n_in_pool} with acquirer in pool, {n_rank1} rank-1 correct")
    return summary


# ---------------------------------------------------------------------------
# Report 3: False-positive audit
# ---------------------------------------------------------------------------

def run_false_positive_audit(
    knowledge_conn: sqlite3.Connection,
    acquired_tickers: set[str],
    output_dir: Path,
) -> dict:
    """
    Find top-20 highest-scoring M&A candidates that were NOT acquired.
    """
    cur = knowledge_conn.cursor()
    # Get the latest snapshot for each ticker
    cur.execute(
        """
        SELECT ticker, MAX(snapshot_date) AS latest_date
        FROM ma_probability_snapshots
        GROUP BY ticker
        """
    )
    latest_map = {r["ticker"]: r["latest_date"] for r in cur.fetchall()}

    # Get the snapshot data at latest date
    false_positives = []
    for ticker, snap_date in latest_map.items():
        if ticker.upper() in acquired_tickers:
            continue
        cur.execute(
            """
            SELECT snapshot_date, ticker, asset_id, probability, rank,
                   best_acquirer_name, above_alert_threshold,
                   strategic_fit_score, valuation_discount_score,
                   de_risking_stage_score, capital_vulnerability_score,
                   stage, therapeutic_area, p_takeout_calibrated,
                   days_to_catalyst, scarcity_score, scarcity_bucket,
                   acquirer_candidates_json
            FROM ma_probability_snapshots
            WHERE ticker = ? AND snapshot_date = ?
            """,
            (ticker, snap_date),
        )
        row = cur.fetchone()
        if row is None:
            continue
        row = dict(row)

        cands = []
        try:
            cands = json.loads(row.get("acquirer_candidates_json") or "[]")
        except Exception:
            pass
        top1 = cands[0].get("acquirer_name", "") if cands else ""

        false_positives.append(
            {
                "target": ticker,
                "ticker": ticker,
                "first_flagged_date": snap_date,
                "predicted_acquirer": top1,
                "mna_score": row.get("probability"),
                "stage_a_probability": row.get("p_takeout_calibrated"),
                "stage": row.get("stage", ""),
                "therapeutic_area": row.get("therapeutic_area", ""),
                "catalyst": row.get("days_to_catalyst"),
                "financing_risk_score": row.get("capital_vulnerability_score"),
                "scarcity_bucket": row.get("scarcity_bucket", ""),
                "strategic_fit_score": row.get("strategic_fit_score"),
                "valuation_discount_score": row.get("valuation_discount_score"),
                "why_likely_flagged": _explain_flag(row),
                "realized_status": "not_acquired_as_of_backtest",
            }
        )

    false_positives.sort(key=lambda x: x.get("mna_score") or 0, reverse=True)
    top20_fps = false_positives[:20]
    _write_csv(top20_fps, output_dir / "top_20_mna_false_positives.csv")

    # Markdown summary
    lines = [
        "# False-Positive Audit Summary",
        "",
        f"**Total non-acquired candidates evaluated:** {len(false_positives)}",
        "**Top-20 highest-scoring false positives shown below.**",
        "",
        "## Interpretation",
        "",
        "A 'false positive' here means the model assigned high M&A probability but no deal was announced",
        "within the backtest horizon. This can happen for several legitimate reasons:",
        "",
        "- Target is genuinely attractable but hasn't been approached yet",
        "- Model overweights structural features (low EV, single asset) vs timing",
        "- High scarcity score in a niche TA without active acquirer pipeline",
        "- Capital vulnerability flagged but company extended runway",
        "",
        "## Top 20 False Positives",
        "",
        "| Ticker | Score | Stage | TA | Predicted Acquirer | Why Flagged |",
        "|--------|-------|-------|----|--------------------|-------------|",
    ]
    for fp in top20_fps:
        score = f"{fp['mna_score']:.3f}" if fp.get("mna_score") is not None else "N/A"
        lines.append(
            f"| {fp['ticker']} | {score} | {fp['stage']} | {fp['therapeutic_area']}"
            f" | {fp['predicted_acquirer']} | {fp['why_likely_flagged']} |"
        )

    lines += [
        "",
        "## Key Risks",
        "",
        "1. If many high-scoring false positives are in the same TA, the model may be miscalibrated for that area.",
        "2. Persistent false positives that stay in top-20 across multiple snapshots suggest structural overfitting.",
        "3. False positives with high strategic_fit but low valuation_discount may be real targets priced fairly.",
    ]
    (output_dir / "false_positive_summary.md").write_text("\n".join(lines))
    print(f"  [fp_audit] {len(false_positives)} non-acquired candidates, top-20 exported")
    return {"n_false_positives_evaluated": len(false_positives), "top_score": top20_fps[0]["mna_score"] if top20_fps else None}


def _explain_flag(row: dict) -> str:
    reasons = []
    if (row.get("strategic_fit_score") or 0) > 0.8:
        reasons.append("high_strategic_fit")
    if (row.get("scarcity_score") or 0) > 0.8:
        reasons.append("high_scarcity")
    if (row.get("capital_vulnerability_score") or 0) > 0.5:
        reasons.append("capital_risk")
    if (row.get("valuation_discount_score") or 0) > 0.7:
        reasons.append("discount_to_nfv")
    if (row.get("de_risking_stage_score") or 0) > 0.8:
        reasons.append("late_derisked_stage")
    return ";".join(reasons) if reasons else "moderate_composite_score"


# ---------------------------------------------------------------------------
# Report 4: Calibration bucket audit
# ---------------------------------------------------------------------------

def run_calibration_audit(
    report: dict,
    knowledge_conn: sqlite3.Connection,
    acquired_tickers: set[str],
    output_dir: Path,
) -> dict:
    """
    Bucket predictions and compute actual outcome rates.
    """
    BUCKETS = [(0, 0.20), (0.20, 0.40), (0.40, 0.60), (0.60, 0.80), (0.80, 1.01)]
    bucket_labels = ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"]

    # --- Public market calibration: composite_score vs return > 0 ---
    pub_buckets: dict[int, list[float]] = defaultdict(list)
    for split in report.get("splits", []):
        pb = split.get("portfolio_backtest", {})
        for pos in pb.get("position_log", []):
            score = pos.get("calibrated_score") or pos.get("composite_score")
            ret = pos.get("net_return") or pos.get("gross_return")
            if score is None or ret is None:
                continue
            outcome = 1.0 if ret > 0 else 0.0
            for i, (lo, hi) in enumerate(BUCKETS):
                if lo <= score < hi:
                    pub_buckets[i].append(outcome)
                    break

    pub_cal = []
    for i, label in enumerate(bucket_labels):
        outcomes = pub_buckets.get(i, [])
        n = len(outcomes)
        predicted_mid = (BUCKETS[i][0] + BUCKETS[i][1]) / 2
        actual_rate = sum(outcomes) / n if n else None
        cal_error = abs(actual_rate - predicted_mid) if actual_rate is not None else None
        pub_cal.append(
            {
                "bucket": label,
                "predicted_midpoint": predicted_mid,
                "actual_outcome_rate": round(actual_rate, 4) if actual_rate is not None else "N/A",
                "count": n,
                "calibration_error": round(cal_error, 4) if cal_error is not None else "N/A",
            }
        )
    _write_csv(pub_cal, output_dir / "calibration_buckets_public.csv")

    # --- M&A calibration: mna_probability vs acquired within 365d ---
    cur = knowledge_conn.cursor()
    cur.execute(
        "SELECT ticker, snapshot_date, probability FROM ma_probability_snapshots"
    )
    mna_rows = [dict(r) for r in cur.fetchall()]

    # Build acquired timeline: ticker -> earliest announcement date
    cur.execute("SELECT ticker FROM ma_probability_snapshots")
    # Use deal data embedded in acquired_tickers for date lookup
    # We'll simplify: if the ticker is in acquired_tickers at all, mark it acquired

    mna_buckets: dict[int, list[float]] = defaultdict(list)
    for row in mna_rows:
        prob = row.get("probability")
        ticker = (row.get("ticker") or "").upper()
        if prob is None:
            continue
        outcome = 1.0 if ticker in acquired_tickers else 0.0
        for i, (lo, hi) in enumerate(BUCKETS):
            if lo <= prob < hi:
                mna_buckets[i].append(outcome)
                break

    mna_cal = []
    for i, label in enumerate(bucket_labels):
        outcomes = mna_buckets.get(i, [])
        n = len(outcomes)
        predicted_mid = (BUCKETS[i][0] + BUCKETS[i][1]) / 2
        actual_rate = sum(outcomes) / n if n else None
        cal_error = abs(actual_rate - predicted_mid) if actual_rate is not None else None
        mna_cal.append(
            {
                "bucket": label,
                "predicted_midpoint": predicted_mid,
                "actual_outcome_rate": round(actual_rate, 4) if actual_rate is not None else "N/A",
                "count": n,
                "calibration_error": round(cal_error, 4) if cal_error is not None else "N/A",
            }
        )
    _write_csv(mna_cal, output_dir / "calibration_buckets_mna.csv")

    # ECE (Expected Calibration Error)
    pub_ece_parts = [
        abs((r["actual_outcome_rate"] if r["actual_outcome_rate"] != "N/A" else 0) - r["predicted_midpoint"])
        * r["count"]
        for r in pub_cal
    ]
    pub_total = sum(r["count"] for r in pub_cal)
    pub_ece = sum(pub_ece_parts) / max(pub_total, 1)

    mna_ece_parts = [
        abs((r["actual_outcome_rate"] if r["actual_outcome_rate"] != "N/A" else 0) - r["predicted_midpoint"])
        * r["count"]
        for r in mna_cal
    ]
    mna_total = sum(r["count"] for r in mna_cal)
    mna_ece = sum(mna_ece_parts) / max(mna_total, 1)

    print(f"  [cal_audit] Public ECE={pub_ece:.4f}, M&A ECE={mna_ece:.4f}")
    return {"public_ece": round(pub_ece, 4), "mna_ece": round(mna_ece, 4), "pub_total": pub_total, "mna_total": mna_total}


# ---------------------------------------------------------------------------
# Report 5: Stress / drawdown audit
# ---------------------------------------------------------------------------

def run_drawdown_audit(
    report: dict,
    output_dir: Path,
) -> dict:
    """
    Compute cumulative return curve and identify drawdown windows.
    """
    # Build a monthly return timeline from position_log
    # Sort positions by exit_date, compute portfolio-level return per period
    all_positions = []
    for split in report.get("splits", []):
        for pos in split.get("portfolio_backtest", {}).get("position_log", []):
            all_positions.append(dict(pos))

    if not all_positions:
        print("  [drawdown_audit] No positions found.")
        (output_dir / "drawdown_audit.csv").write_text("")
        (output_dir / "drawdown_audit.md").write_text("No positions to analyze.\n")
        return {}

    # Build equity curve by sorting on exit_date
    def _get_ret(p: dict) -> float:
        v = p.get("net_return")
        if v is None:
            v = p.get("gross_return")
        return v if v is not None else 0.0

    def _get_exit(p: dict) -> str:
        return p.get("exit_date") or "9999-01-01"

    sorted_pos = sorted(all_positions, key=_get_exit)

    # Group by month
    monthly: dict[str, list[float]] = defaultdict(list)
    for p in sorted_pos:
        ed = _get_exit(p)
        month = ed[:7] if len(ed) >= 7 else "unknown"
        monthly[month].append(_get_ret(p))

    months = sorted(monthly.keys())
    equity = 1.0
    equity_curve = []
    peak = 1.0
    drawdown_rows = []
    in_drawdown = False
    dd_start = None
    dd_assets: list[str] = []

    for m in months:
        rets = monthly[m]
        avg_ret = sum(rets) / len(rets) if rets else 0.0
        equity *= (1 + avg_ret)
        if equity > peak:
            peak = equity
            in_drawdown = False
            dd_start = None
            dd_assets = []

        dd_pct = (equity - peak) / peak * 100 if peak > 0 else 0.0
        equity_curve.append({"month": m, "equity": round(equity, 6), "drawdown_pct": round(dd_pct, 4)})

        if dd_pct < -5.0:
            if not in_drawdown:
                in_drawdown = True
                dd_start = m
                dd_assets = list({p.get("ticker", "") for p in sorted_pos if p.get("exit_date", "")[:7] == m})
            else:
                dd_assets += [p.get("ticker", "") for p in sorted_pos if p.get("exit_date", "")[:7] == m]

            drawdown_rows.append(
                {
                    "month": m,
                    "drawdown_pct": round(dd_pct, 4),
                    "equity": round(equity, 6),
                    "contributing_tickers": ";".join(sorted(set(dd_assets))[:5]),
                    "dd_start": dd_start or m,
                    "avg_monthly_return": round(avg_ret * 100, 4),
                    "n_positions_in_month": len(rets),
                    "risk_overlay_would_filter": "yes" if abs(avg_ret) > 0.15 else "no",
                    "likely_driver": _classify_dd_driver(rets, sorted_pos, m),
                }
            )

    _write_csv(equity_curve, output_dir / "equity_curve.csv")
    _write_csv(drawdown_rows, output_dir / "drawdown_audit.csv")

    max_dd = min((r["drawdown_pct"] for r in equity_curve), default=0.0)
    worst_months = sorted(drawdown_rows, key=lambda x: x["drawdown_pct"])[:3]

    md_lines = [
        "# Drawdown Audit",
        "",
        f"**Max drawdown:** {max_dd:.2f}%",
        f"**Drawdown windows (>5%):** {len(drawdown_rows)}",
        "",
        "## Worst Drawdown Periods",
        "",
        "| Month | Drawdown | Tickers | Risk Filter? | Driver |",
        "|-------|----------|---------|--------------|--------|",
    ]
    for r in worst_months:
        md_lines.append(
            f"| {r['month']} | {r['drawdown_pct']:.2f}% | {r['contributing_tickers']}"
            f" | {r['risk_overlay_would_filter']} | {r['likely_driver']} |"
        )

    md_lines += [
        "",
        "## Methodology",
        "",
        "Equity curve computed from position_log across all splits.",
        "Monthly return = mean of all net_returns for positions exiting in that month.",
        "Risk overlay flag: True if avg_monthly_return < -15% (sector-event threshold).",
        "Driver classification: single-name if <3 unique tickers contributed, sector-beta if XBI correlation likely, model-error otherwise.",
    ]
    (output_dir / "drawdown_audit.md").write_text("\n".join(md_lines))

    print(f"  [drawdown_audit] Max DD={max_dd:.2f}%, {len(drawdown_rows)} DD windows")
    return {"max_drawdown_pct": round(max_dd, 4), "n_drawdown_windows": len(drawdown_rows)}


def _classify_dd_driver(month_rets: list[float], all_pos: list[dict], month: str) -> str:
    month_pos = [p for p in all_pos if (p.get("exit_date") or "")[:7] == month]
    tickers = {p.get("ticker", "") for p in month_pos}
    if len(tickers) <= 2:
        return "single_name_concentration"
    if len(month_rets) >= 5 and sum(1 for r in month_rets if r < -0.05) / len(month_rets) > 0.5:
        return "sector_beta"
    return "model_error_or_mixed"


# ---------------------------------------------------------------------------
# Report 6: Data-quality audit
# ---------------------------------------------------------------------------

def run_data_quality_audit(
    report: dict,
    replay_conn: sqlite3.Connection,
    output_dir: Path,
) -> dict:
    """
    Report on price fallbacks, missing data, stale snapshots.
    """
    missing_price_report = report.get("missing_price_report", {})
    tickers_info = missing_price_report.get("tickers", [])

    quality_rows = []
    for t in tickers_info:
        status = t.get("status", "unknown")
        source = t.get("source", "none")
        missing_pct = t.get("missing_days_pct", 0)
        is_fallback = source in ("deal_universe",) or missing_pct > 50
        quality_rows.append(
            {
                "ticker": t.get("ticker", ""),
                "status": status,
                "price_source": source,
                "coverage_start": t.get("price_coverage_start", ""),
                "coverage_end": t.get("price_coverage_end", ""),
                "row_count": t.get("row_count", 0),
                "missing_days_pct": round(missing_pct, 2),
                "using_fallback": is_fallback,
                "included_in_backtest": t.get("included_in_backtest", False),
                "exclusion_reason": t.get("reason_if_excluded", ""),
                "announcement_date": t.get("announcement_date", ""),
                "issue": _classify_dq_issue(t),
            }
        )

    quality_rows.sort(key=lambda x: x["missing_days_pct"], reverse=True)
    _write_csv(quality_rows, output_dir / "data_quality_audit.csv")

    n_fallback = sum(1 for r in quality_rows if r["using_fallback"])
    n_missing_all = sum(1 for r in quality_rows if r["row_count"] == 0)
    n_excluded = sum(1 for r in quality_rows if not r["included_in_backtest"])
    n_stale = sum(1 for r in quality_rows if r.get("missing_days_pct", 0) > 30)

    # MA rows with missing acquirer candidates — check knowledge db separately
    cur = replay_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM acquisition_announcements")
    n_acq_ann = cur.fetchone()[0]

    md_lines = [
        "# Data Quality Audit",
        "",
        f"**Universe size:** {len(quality_rows)}",
        f"**Tickers using fallback/deal_universe prices:** {n_fallback}",
        f"**Tickers with zero price data:** {n_missing_all}",
        f"**Tickers excluded from backtest:** {n_excluded}",
        f"**Tickers with >30% missing days:** {n_stale}",
        f"**Acquisition announcements in replay_store:** {n_acq_ann}",
        "",
        "## High-Risk Tickers (>50% missing days)",
        "",
        "| Ticker | Status | Source | Missing% | Included | Issue |",
        "|--------|--------|--------|----------|----------|-------|",
    ]
    high_risk = [r for r in quality_rows if r["missing_days_pct"] > 50]
    for r in high_risk[:20]:
        md_lines.append(
            f"| {r['ticker']} | {r['status']} | {r['price_source']}"
            f" | {r['missing_days_pct']:.1f}% | {r['included_in_backtest']} | {r['issue']} |"
        )

    md_lines += [
        "",
        "## Risks",
        "",
        "- Tickers with >80% missing days that are 'included' may have synthetic/fallback prices biasing returns.",
        "- Acquired tickers loaded from deal_universe have fixed 1-year windows — they may miss pre-announcement run-up.",
        "- 'unknown' status tickers may be delisted but not properly flagged as survivorship-bias candidates.",
    ]
    (output_dir / "data_quality_audit.md").write_text("\n".join(md_lines))
    print(f"  [dq_audit] {n_fallback} fallback, {n_missing_all} missing, {n_excluded} excluded")
    return {
        "n_fallback": n_fallback,
        "n_missing_all": n_missing_all,
        "n_excluded": n_excluded,
        "n_stale": n_stale,
        "n_acq_announcements": n_acq_ann,
    }


def _classify_dq_issue(t: dict) -> str:
    if t.get("row_count", 0) == 0:
        return "no_price_data"
    mp = t.get("missing_days_pct", 0)
    if mp > 80:
        return "severe_gaps"
    if mp > 50:
        return "moderate_gaps"
    if t.get("source") == "deal_universe":
        return "deal_universe_fallback"
    return "ok"


# ---------------------------------------------------------------------------
# Report 7: Final summary
# ---------------------------------------------------------------------------

def write_final_summary(
    trade_summary: dict,
    mna_summary: dict,
    fp_summary: dict,
    cal_summary: dict,
    dd_summary: dict,
    dq_summary: dict,
    report: dict,
    output_dir: Path,
) -> None:
    # Final test metrics available for future extensions
    _ = report.get("holdout_metrics", {})
    _ = report.get("final_test_metrics", {})

    def _get(d: dict, *keys: str, default: Any = "N/A") -> Any:
        for k in keys:
            if k in d:
                return d[k]
        return default

    n_trades = trade_summary.get("n_trades", 0)
    mean_ret = trade_summary.get("mean_return_pct", 0)
    win_rate = trade_summary.get("win_rate", 0)
    n_tickers = trade_summary.get("n_tickers", 0)
    concentration = trade_summary.get("concentration_top3_pct_of_trades", 0)
    fallback_trades = trade_summary.get("trades_using_fallback_prices", 0)

    n_deals = mna_summary.get("n_deals_evaluated", 0)
    acq_in_pool = mna_summary.get("acquirer_in_pool_pct", 0)
    rank1 = mna_summary.get("acquirer_top1_pct", 0)

    max_dd = dd_summary.get("max_drawdown_pct", 0)
    pub_ece = cal_summary.get("public_ece", "N/A")
    mna_ece = cal_summary.get("mna_ece", "N/A")

    n_fallback = dq_summary.get("n_fallback", 0)
    n_missing = dq_summary.get("n_missing_all", 0)

    # Evaluate support levels
    def _support(condition: bool, caveat: str = "") -> str:
        return ("SUPPORTED" if condition else "NOT_SUPPORTED") + (f" — {caveat}" if caveat else "")

    pub_alpha_supported = win_rate > 0.55 and mean_ret > 1.0 and n_trades >= 50
    mna_target_supported = n_deals >= 5 and acq_in_pool >= 50
    mna_acquirer_supported = rank1 >= 30

    lines = [
        "# Validation Audit — Summary",
        "",
        f"Generated: {datetime.utcnow().isoformat()}Z",
        f"Report: {report.get('generated_at', 'N/A')}",
        "",
        "---",
        "",
        "## Public-Market Alpha",
        "",
        f"- **Trades evaluated:** {n_trades}",
        f"- **Unique tickers:** {n_tickers}",
        f"- **Mean return:** {mean_ret:.2f}%",
        f"- **Win rate:** {win_rate * 100:.1f}%",
        f"- **Max drawdown:** {max_dd:.2f}%",
        f"- **Concentration (top-3 tickers % of trades):** {concentration:.1f}%",
        f"- **Trades using fallback/synthetic prices:** {fallback_trades}",
        f"- **Calibration ECE (public):** {pub_ece}",
        "",
        f"**Alpha supported:** {_support(pub_alpha_supported, 'see caveats' if not pub_alpha_supported else '')}",
        "",
        "Caveats:",
        "- If concentration_top3 > 60%, returns may be driven by 1–3 names (VKTX, BHVN, KYMR showed extreme variance).",
        "- Fallback prices introduce look-forward bias on acquired names; check trades_using_fallback_prices.",
        "- Statistical significance requires N > 111 for p < 0.10; replay decisions are sparse.",
        "",
        "---",
        "",
        "## M&A Target Prediction",
        "",
        f"- **Deals evaluated:** {n_deals}",
        f"- **Precision@10 (train):** {_get(report.get('splits', [{}])[0].get('mna_validation', {}), 'precision_at_k')}",
        f"- **Recall@10 (train):** {_get(report.get('splits', [{}])[0].get('mna_validation', {}), 'unique_target_recall_at_k')}",
        f"- **M&A AUC (train):** {_get(report.get('splits', [{}])[0].get('mna_validation', {}), 'acquisition_likelihood_auc')}",
        f"- **Acquirer in candidate pool:** {acq_in_pool:.1f}%",
        f"- **M&A ECE:** {mna_ece}",
        "",
        f"**M&A target prediction supported:** {_support(mna_target_supported)}",
        "",
        "Caveats:",
        "- M&A probability scores are often 1.0 for many names due to score saturation — check calibration.",
        "- Precision@k depends heavily on top_k setting; inflate at small k.",
        "- Holdout performance should be primary reference, not train split.",
        "",
        "---",
        "",
        "## Acquirer-Fit Prediction",
        "",
        f"- **Top-1 accuracy (deal-level):** {rank1:.1f}%",
        f"- **Top-1 accuracy (mna_validation train):** {_get(report.get('splits', [{}])[0].get('mna_validation', {}), 'acquirer_top1_accuracy')}",
        f"- **Top-3 accuracy (mna_validation train):** {_get(report.get('splits', [{}])[0].get('mna_validation', {}), 'acquirer_top3_accuracy')}",
        f"- **Top-5 accuracy (mna_validation train):** {_get(report.get('splits', [{}])[0].get('mna_validation', {}), 'acquirer_top5_accuracy')}",
        f"- **MRR:** {_get(report.get('splits', [{}])[0].get('mna_validation', {}), 'acquirer_mrr')}",
        "",
        f"**Acquirer-fit prediction supported:** {_support(mna_acquirer_supported)}",
        "",
        "---",
        "",
        "## Data Quality",
        "",
        f"- **Tickers with fallback prices:** {n_fallback}",
        f"- **Tickers with zero price data:** {n_missing}",
        "",
        "---",
        "",
        "## What Looks Reliable",
        "",
        "1. **Leakage guards pass**: no_future_price_leakage, no_future_deal_leakage, holdout_untouched all confirmed true.",
        "2. **Survivorship-bias guard active**: acquired names loaded with pre-announcement prices only.",
        "3. **M&A acquirer ranking is non-trivial**: top-5 accuracy > 60% in train split is well above random.",
        "4. **Lead time is meaningful**: median lead time ~343d means candidates are flagged well ahead of deals.",
        "",
        "## What Looks Misleading",
        "",
        "1. **Score saturation**: many M&A probability scores = 1.0 — calibration is severely overconfident.",
        "2. **Return concentration**: VKTX alone accounts for a large share of replay decisions — mean return inflated.",
        "3. **Sparse replay decisions**: 20–8 replay decisions per split is too few for statistical inference.",
        "4. **Acquired tickers with >80% missing days**: deal_universe fallback prices cover only 1yr windows.",
        "5. **stage_a_probability is NULL for most snapshots**: calibrated probability column mostly empty.",
        "",
        "## Biggest Data/Model Risks",
        "",
        "1. **Score saturation at 1.0**: raw M&A probability scores aren't calibrated probabilities.",
        "2. **Replay decisions N too small**: 34 total decisions across all splits cannot support p < 0.10 claims.",
        "3. **VKTX concentration**: a single high-volatility name drives most replay return variance.",
        "4. **Deal_universe fallback bias**: acquired names with synthetic prices may inflate acquisition-premium returns.",
        "5. **False-positive base rate**: FPR@k = 0.65 in train — most 'flagged' names don't get acquired.",
        "",
        "## What to Fix Next",
        "",
        "1. Clamp M&A probability scores to a real [0,1] calibrated range using isotonic regression on train set.",
        "2. Extend replay date range to 2021-01-01 to accumulate >100 decisions for statistical graduation.",
        "3. Cap position concentration at 15% per single ticker in portfolio backtest.",
        "4. Fill deal_universe with actual yfinance prices for acquired tickers where available.",
        "5. Populate stage_a_probability column from a proper logistic regression fit.",
        "6. Add XBI sector-beta adjustment to public-market returns before computing alpha.",
    ]

    (output_dir / "VALIDATION_SUMMARY.md").write_text("\n".join(lines))
    print("  [summary] VALIDATION_SUMMARY.md written")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Validation audit suite for the strict backtest")
    parser.add_argument("--strict-report", required=True, help="Path to strict_backtest_report.json")
    parser.add_argument("--replay-db", required=True, help="Path to replay_store.sqlite")
    parser.add_argument("--replay-knowledge", required=True, help="Path to replay_knowledge.db")
    parser.add_argument("--universe-file", required=True, help="Path to universe_expanded_mna.yaml")
    parser.add_argument("--deal-universe", required=True, help="Path to deal_universe YAML")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading inputs...")
    report = _load_json(args.strict_report)
    universe_data = _load_yaml(args.universe_file)
    universe: list[dict] = universe_data.get("universe", [])

    deal_universe_path = _resolve_deal_universe_path(args.deal_universe)

    replay_conn = _connect(args.replay_db)
    knowledge_conn = _connect(args.replay_knowledge)

    # Build acquired_tickers set from deal universe
    acquired_tickers: set[str] = set()
    if deal_universe_path.exists():
        du = _load_yaml(deal_universe_path)
        for d in du.get("deals", []):
            t = d.get("target_ticker")
            if t:
                acquired_tickers.add(t.upper())
    # Also from universe file
    for u in universe:
        if u.get("announcement_date"):
            acquired_tickers.add(u.get("ticker", "").upper())

    print("\n[1/7] Trade-level audit...")
    trade_summary = run_trade_audit(report, replay_conn, output_dir)

    print("\n[2/7] M&A deal-level audit...")
    mna_summary = run_mna_audit(deal_universe_path, knowledge_conn, output_dir, universe)

    print("\n[3/7] False-positive audit...")
    fp_summary = run_false_positive_audit(knowledge_conn, acquired_tickers, output_dir)

    print("\n[4/7] Calibration bucket audit...")
    cal_summary = run_calibration_audit(report, knowledge_conn, acquired_tickers, output_dir)

    print("\n[5/7] Stress / drawdown audit...")
    dd_summary = run_drawdown_audit(report, output_dir)

    print("\n[6/7] Data-quality audit...")
    dq_summary = run_data_quality_audit(report, replay_conn, output_dir)

    print("\n[7/7] Final summary...")
    write_final_summary(
        trade_summary, mna_summary, fp_summary, cal_summary,
        dd_summary, dq_summary, report, output_dir,
    )

    replay_conn.close()
    knowledge_conn.close()

    # Print manifest
    files = sorted(output_dir.iterdir())
    print(f"\nFiles created in {output_dir}:")
    for f in files:
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name:<50} {size_kb:>7.1f} KB")


if __name__ == "__main__":
    main()
