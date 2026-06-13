"""Refresh company market economics in the synthetic ``auto_generated`` configs.

The ``auto_generated/*.yaml`` configs ship with uniform placeholder economics
(every name: current_price 25.0, shares 120.0, cash 500.0 -> a fake $2.5B EV),
which inverts the dual-track coarse investment stance for large caps (e.g. VRTX
reads "long +428%" against a fake low EV). This script overwrites only the
``company:`` market-data fields with a live yfinance snapshot so the coarse
rNPV-vs-EV read uses real enterprise value.

Scope guard: it touches ONLY ``examples/configs/auto_generated/*.yaml`` that are
covered by the M&A scan. It never edits ``replay_generated/`` or named configs —
those carry frozen point-in-time prices for the no-lookahead backtest.

Fields updated within the ``company:`` block (nothing else in the file changes):
    current_price, shares_outstanding_millions, market_cap_millions,
    cash_millions, debt_millions  (the last two -> Company.net_cash_millions)

Usage::

    python -m tools.refresh_auto_generated_economics            # dry-run preview
    python -m tools.refresh_auto_generated_economics --apply    # write changes
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _covered_auto_generated_configs() -> dict[str, str]:
    """Return ``{ticker: abs_path}`` for covered configs under auto_generated/."""
    from bve.ops.weekly_runner import _load_valuation_config_map

    return {
        tkr: path
        for tkr, path in _load_valuation_config_map().items()
        if "auto_generated" in path
    }


def _company_block_span(lines: list[str]) -> tuple[int, int]:
    """Index range [start, end) of the top-level ``company:`` block."""
    start = next(i for i, ln in enumerate(lines) if ln.rstrip() == "company:")
    end = len(lines)
    for i in range(start + 1, len(lines)):
        # next top-level key (column-0, non-blank, non-comment) ends the block
        if lines[i] and not lines[i][0].isspace() and not lines[i].lstrip().startswith("#"):
            end = i
            break
    return start, end


def _fmt(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _refresh_one(path: Path, snapshot, as_of: str) -> tuple[str, dict[str, str]]:
    """Rewrite the company block of one config. Returns (new_text, changes)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start, end = _company_block_span(lines)

    raw = getattr(snapshot, "raw", {}) or {}
    cash = raw.get("cash_millions")
    debt = raw.get("total_debt_millions")
    updates: dict[str, float] = {}
    if snapshot.price is not None:
        updates["current_price"] = float(snapshot.price)
    if snapshot.shares_outstanding_millions is not None:
        updates["shares_outstanding_millions"] = float(snapshot.shares_outstanding_millions)
    if snapshot.market_cap_millions is not None:
        updates["market_cap_millions"] = float(snapshot.market_cap_millions)
    if cash is not None:
        updates["cash_millions"] = float(cash)
    if debt is not None:
        updates["debt_millions"] = float(debt)

    changes: dict[str, str] = {}
    block = lines[start:end]
    present: set[str] = set()
    for j, ln in enumerate(block):
        m = re.match(r"^(\s+)([a-z_]+):\s*(\S.*)?$", ln)
        if not m:
            continue
        indent, key, old = m.group(1), m.group(2), (m.group(3) or "").strip()
        if key in updates:
            present.add(key)
            new_val = _fmt(updates[key])
            changes[key] = f"{old} -> {new_val}"
            block[j] = f"{indent}{key}: {new_val}"

    # Insert any missing keys (e.g. market_cap_millions, debt_millions) and a
    # provenance comment, right after the company `ticker:` line for stability.
    insert_at = next(
        (j for j, ln in enumerate(block) if re.match(r"^\s+ticker:", ln)), 0
    ) + 1
    indent = "  "
    to_insert: list[str] = []
    for key in ("market_cap_millions", "cash_millions", "debt_millions"):
        if key in updates and key not in present:
            new_val = _fmt(updates[key])
            to_insert.append(f"{indent}{key}: {new_val}")
            changes[key] = f"(added) {new_val}"
    if to_insert:
        to_insert.append(f"{indent}# market economics refreshed from yfinance {as_of}")
        block[insert_at:insert_at] = to_insert

    new_lines = lines[:start] + block + lines[end:]
    return "\n".join(new_lines) + "\n", changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="refresh_auto_generated_economics")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run).")
    args = parser.parse_args(argv)

    from bve.refresh.market_data_refresh import fetch_market_snapshot

    as_of = date.today().isoformat()
    configs = _covered_auto_generated_configs()
    print(f"[refresh] {len(configs)} covered auto_generated configs "
          f"({'APPLY' if args.apply else 'dry-run'})\n", file=sys.stderr)

    ok = failed = 0
    for ticker in sorted(configs):
        path = Path(configs[ticker])
        try:
            snap = fetch_market_snapshot(ticker)
        except Exception as e:  # network / delisted / rename — keep original
            print(f"  {ticker:6s} FETCH FAILED ({type(e).__name__}: {str(e)[:60]}) — skipped")
            failed += 1
            continue
        if snap.price is None and snap.market_cap_millions is None:
            print(f"  {ticker:6s} no usable market data — skipped")
            failed += 1
            continue
        new_text, changes = _refresh_one(path, snap, as_of)
        summary = ", ".join(f"{k}: {v}" for k, v in changes.items())
        print(f"  {ticker:6s} {summary}")
        if args.apply:
            path.write_text(new_text, encoding="utf-8")
        ok += 1

    print(f"\n[refresh] {ok} refreshed, {failed} skipped "
          f"({'written' if args.apply else 'dry-run — re-run with --apply'}).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
