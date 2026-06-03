"""Extend replay knowledge screen_snapshots to cover new monthly dates.

Copies the last existing screen_snapshot date as a template into each new
monthly date from --start to --end, refreshing ev_millions and implied_pos
from replay-store prices.  This makes the dates available to the
company_sotp_backfiller and ma_probability_backfiller, enabling a new
out-of-sample holdout without touching the old frozen holdout.

Usage::

    python -m bve.cli.extend_snapshot_dates \\
        --replay-knowledge outputs/intelligence/replay_knowledge.db \\
        --replay-store outputs/intelligence/replay_store.sqlite \\
        --start 2024-04-01 --end 2026-03-01
"""
from __future__ import annotations

import argparse
import sqlite3
import uuid
from datetime import date, timedelta
from pathlib import Path


def _first_business_day_of_month(d: date) -> date:
    """Return the first day of the month for d (as-is; caller passes YYYY-MM-01)."""
    return d


def _monthly_dates(start: date, end: date) -> list[date]:
    """Return the 1st of each month in [start, end]."""
    result = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        result.append(cur)
        # Advance to next month
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return result


def _nearest_close(
    cur_replay: sqlite3.Cursor,
    ticker: str,
    target_date: date,
    window_days: int = 7,
) -> tuple[float | None, float | None]:
    """Return (close_usd, market_cap_millions) for ticker nearest to target_date.

    Tries market_prices first (has market_cap_millions); falls back to
    historical_prices (close_usd only, market_cap_millions=None).
    """
    lo = (target_date - timedelta(days=window_days)).isoformat()
    hi = (target_date + timedelta(days=window_days)).isoformat()
    target_iso = target_date.isoformat()

    # market_prices has market_cap_millions
    cur_replay.execute(
        """
        SELECT close_usd, market_cap_millions
        FROM market_prices
        WHERE ticker = ?
          AND price_date >= ?
          AND price_date <= ?
          AND close_usd IS NOT NULL
        ORDER BY ABS(julianday(price_date) - julianday(?))
        LIMIT 1
        """,
        (ticker, lo, hi, target_iso),
    )
    row = cur_replay.fetchone()
    if row is not None:
        return row[0], row[1]

    # Fall back to historical_prices (no market_cap_millions)
    cur_replay.execute(
        """
        SELECT close_usd
        FROM historical_prices
        WHERE ticker = ?
          AND price_date >= ?
          AND price_date <= ?
          AND close_usd IS NOT NULL
        ORDER BY ABS(julianday(price_date) - julianday(?))
        LIMIT 1
        """,
        (ticker, lo, hi, target_iso),
    )
    row = cur_replay.fetchone()
    if row is None:
        return None, None
    return row[0], None


def extend_screen_snapshots(
    *,
    knowledge_db_path: str | Path,
    replay_store_path: str | Path,
    start_date: date,
    end_date: date,
    template_date: date | None = None,
    dry_run: bool = False,
) -> int:
    """Seed screen_snapshots for monthly dates in [start_date, end_date].

    Returns the number of rows inserted (or that would be inserted in dry_run).
    """
    kb = sqlite3.connect(str(knowledge_db_path))
    kb.row_factory = sqlite3.Row
    rs = sqlite3.connect(str(replay_store_path))

    try:
        kb_cur = kb.cursor()
        rs_cur = rs.cursor()

        # Find the template date — last available screen_snapshot date
        kb_cur.execute(
            "SELECT MAX(snapshot_date) FROM screen_snapshots"
        )
        last_row = kb_cur.fetchone()
        if last_row is None or last_row[0] is None:
            raise ValueError("No screen_snapshots found to use as template")

        effective_template = template_date or date.fromisoformat(last_row[0])
        print(f"Template date: {effective_template}")

        # Load template rows
        kb_cur.execute(
            "SELECT * FROM screen_snapshots WHERE snapshot_date = ?",
            (effective_template.isoformat(),),
        )
        template_rows = [dict(row) for row in kb_cur.fetchall()]
        if not template_rows:
            raise ValueError(f"No template rows found for {effective_template}")
        print(f"Template rows: {len(template_rows)} tickers")

        new_dates = [
            d for d in _monthly_dates(start_date, end_date)
            if d > effective_template
        ]
        if not new_dates:
            print("No new dates to seed.")
            return 0

        # Check existing
        kb_cur.execute("SELECT DISTINCT snapshot_date FROM screen_snapshots")
        existing_dates = {row[0] for row in kb_cur.fetchall()}

        inserted = 0
        for new_date in new_dates:
            if new_date.isoformat() in existing_dates:
                print(f"  {new_date}: already exists, skipping")
                continue

            rows_for_date = []
            for tmpl in template_rows:
                ticker = str(tmpl.get("ticker") or "").upper()
                close, market_cap = _nearest_close(rs_cur, ticker, new_date)

                rnpv = tmpl.get("rnpv_millions")
                ev = market_cap if market_cap is not None else tmpl.get("ev_millions")
                implied_pos = tmpl.get("implied_pos")
                if rnpv and ev and float(rnpv) > 0 and float(ev) > 0:
                    implied_pos = round(float(ev) / float(rnpv), 6)

                rows_for_date.append({
                    "snapshot_id": str(uuid.uuid4()),
                    "ticker": tmpl.get("ticker"),
                    "asset_id": tmpl.get("asset_id"),
                    "snapshot_date": new_date.isoformat(),
                    "program_label": tmpl.get("program_label"),
                    "stage": tmpl.get("stage"),
                    "ta": tmpl.get("ta"),
                    "model_pos": tmpl.get("model_pos"),
                    "implied_pos": implied_pos,
                    "spread_pp": tmpl.get("spread_pp"),
                    "rnpv_millions": rnpv,
                    "ev_millions": ev,
                    "acquisition_discount_pct": tmpl.get("acquisition_discount_pct"),
                    "next_catalyst": tmpl.get("next_catalyst"),
                    "catalyst_date": tmpl.get("catalyst_date"),
                    "days_to_catalyst": tmpl.get("days_to_catalyst"),
                    "single_asset": tmpl.get("single_asset"),
                    "approximation_warning": tmpl.get("approximation_warning"),
                    "thesis_strength": tmpl.get("thesis_strength"),
                    "market_exceeds_model": tmpl.get("market_exceeds_model"),
                    "config_quality": tmpl.get("config_quality"),
                    "created_at": new_date.isoformat() + "T12:00:00+00:00",
                })

            if not dry_run:
                cols = list(rows_for_date[0].keys())
                placeholders = ",".join("?" for _ in cols)
                col_sql = ",".join(cols)
                kb_cur.executemany(
                    f"INSERT OR IGNORE INTO screen_snapshots ({col_sql}) VALUES ({placeholders})",
                    [[r[c] for c in cols] for r in rows_for_date],
                )
                kb.commit()

            inserted += len(rows_for_date)
            print(f"  {new_date}: {'would insert' if dry_run else 'inserted'} {len(rows_for_date)} rows")

        return inserted

    finally:
        kb.close()
        rs.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Extend screen_snapshots to new monthly dates")
    parser.add_argument("--replay-knowledge", default="outputs/intelligence/replay_knowledge.db")
    parser.add_argument("--replay-store", default="outputs/intelligence/replay_store.sqlite")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    inserted = extend_screen_snapshots(
        knowledge_db_path=args.replay_knowledge,
        replay_store_path=args.replay_store,
        start_date=date.fromisoformat(args.start),
        end_date=date.fromisoformat(args.end),
        dry_run=args.dry_run,
    )
    print(f"\nTotal rows {'would be' if args.dry_run else ''} inserted: {inserted}")


if __name__ == "__main__":
    main()
