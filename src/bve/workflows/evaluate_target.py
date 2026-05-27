"""Block 12 — evaluate_target workflow.

Produces a complete single-company decision report by orchestrating all
available BVE data surfaces for a given ticker:

  1. Valuation output (outputs/<TICKER>/valuation.json)
  2. M&A probability row (ops.db MAProbabilityScanner)
  3. Management quality (outputs/<TICKER>/management_quality.json, if present)
  4. Input integrity score (live market + financial refresh, graceful on fail)
  5. Prediction log history (outputs/intelligence/prediction_log.db)
  6. Validation summary (assembled from available surfaces)
  7. Provenance (auto-populated from valuation output)

All surfaces are optional — the report degrades gracefully, rendering
"Not available" for any section whose data is absent.

Usage (Python)
--------------
    from bve.workflows.evaluate_target import evaluate_target
    report = evaluate_target("SRPT")
    print(report)

Usage (CLI)
-----------
    bve-evaluate-target --ticker SRPT
    bve-evaluate-target --ticker SRPT --output outputs/srpt_decision.md
    bve-evaluate-target --ticker SRPT --no-refresh   # skip live market fetch
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data loaders (all return None / [] on failure — never raise)
# ---------------------------------------------------------------------------

class _ValuationShim:
    """Wraps a raw valuation JSON dict so report builder can call .summary_dict."""
    def __init__(self, raw: dict) -> None:
        self._raw = raw

    @property
    def summary_dict(self) -> dict:
        return self._raw

    def __getattr__(self, name: str):
        return self._raw.get(name)


def _load_valuation(ticker: str, outputs_dir: Path) -> Optional[object]:
    try:
        path = outputs_dir / ticker.upper() / "valuation.json"
        if not path.exists():
            return None
        return _ValuationShim(json.loads(path.read_text()))
    except Exception:
        return None


def _load_ma_row(ticker: str, db_path: Path) -> Optional[object]:
    try:
        if not db_path.exists():
            return None
        from bve.intelligence.ma_probability import MAProbabilityScanner
        from bve.intelligence.knowledge_layer import KnowledgeStore
        kb = KnowledgeStore(str(db_path))
        scanner = MAProbabilityScanner(knowledge_store=kb)
        rows = scanner.scan_watchlist(limit=200)
        upper = ticker.upper()
        for row in rows:
            if (row.ticker or "").upper() == upper:
                return row
        return None
    except Exception:
        return None


def _load_management_quality(ticker: str, outputs_dir: Path) -> Optional[object]:
    """Load a previously saved ManagementQualityScore JSON if present."""
    try:
        path = outputs_dir / ticker.upper() / "management_quality.json"
        if not path.exists():
            return None
        from bve.intelligence.ma_management_quality import (
            ManagementQualityInput,
            compute_management_quality_score,
        )
        raw = json.loads(path.read_text())
        inputs = ManagementQualityInput(**raw)
        return compute_management_quality_score(inputs)
    except Exception:
        return None


def _load_prediction_log(ticker: str, db_path: Path) -> list[dict]:
    try:
        if not db_path.exists():
            return []
        from bve.ops.prediction_log import PredictionLog
        log = PredictionLog(str(db_path))
        conn = getattr(log, "_conn", None)
        if conn is None:
            return []
        rows = conn.execute(
            "SELECT * FROM prediction_log ORDER BY logged_at"
        ).fetchall()
        upper = ticker.upper()
        return [
            dict(r) for r in rows
            if (dict(r).get("ticker") or "").upper() == upper
        ]
    except Exception:
        return []


def _load_input_integrity(ticker: str, *, skip_refresh: bool) -> Optional[object]:
    """Attempt a lightweight input integrity check.  Skipped when skip_refresh=True."""
    if skip_refresh:
        return None
    try:
        from bve.refresh.market_data_refresh import fetch_market_snapshot
        from bve.refresh.financial_refresh import fetch_financial_snapshot
        from bve.refresh.input_integrity import build_input_integrity_score

        market = fetch_market_snapshot(ticker)
        financial = fetch_financial_snapshot(ticker)
        return build_input_integrity_score(
            market_snapshot=market,
            financial_snapshot=financial,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_target(
    ticker: str,
    *,
    as_of_date: Optional[date] = None,
    outputs_dir: Optional[Path] = None,
    ops_db: Optional[Path] = None,
    prediction_log_db: Optional[Path] = None,
    skip_refresh: bool = False,
    notes: Optional[list[str]] = None,
) -> str:
    """Build and return a complete Markdown decision report for *ticker*.

    Parameters
    ----------
    ticker:
        Stock ticker (case-insensitive).
    as_of_date:
        Report date; defaults to today.
    outputs_dir:
        Root outputs directory; defaults to ``outputs/``.
    ops_db:
        Path to the intelligence ops SQLite; defaults to
        ``outputs/intelligence/ops.db``.
    prediction_log_db:
        Path to prediction log SQLite; defaults to
        ``outputs/intelligence/prediction_log.db``.
    skip_refresh:
        When True, skips live market/financial refresh (useful for tests
        and offline environments).
    notes:
        Optional free-text notes appended to the report.

    Returns
    -------
    str
        Complete Markdown report.
    """
    ticker = ticker.upper()
    as_of = as_of_date or date.today()

    root = Path("outputs")
    outputs_dir = outputs_dir or root
    ops_db = ops_db or (root / "intelligence" / "ops.db")
    pred_db = prediction_log_db or (root / "intelligence" / "prediction_log.db")

    valuation_output   = _load_valuation(ticker, outputs_dir)
    ma_row             = _load_ma_row(ticker, ops_db)
    management_quality = _load_management_quality(ticker, outputs_dir)
    log_entries        = _load_prediction_log(ticker, pred_db)
    input_integrity    = _load_input_integrity(ticker, skip_refresh=skip_refresh)

    from bve.reporting.validation_summary import build_validation_summary
    validation_summary = build_validation_summary()

    from bve.reporting.decision_report import DecisionReportInput, render_decision_report
    report_input = DecisionReportInput(
        ticker=ticker,
        as_of_date=as_of,
        valuation_output=valuation_output,
        ma_row=ma_row,
        management_quality=management_quality,
        prediction_log_entries=log_entries,
        validation_summary=validation_summary,
        input_integrity=input_integrity,
        notes=notes or [],
    )
    return render_decision_report(report_input)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="bve-evaluate-target",
        description=(
            "Generate a complete BVE decision report for a single ticker, "
            "composing valuation, M&A scoring, management quality, input "
            "integrity, prediction log, and validation evidence."
        ),
    )
    parser.add_argument("--ticker", required=True, help="Stock ticker (e.g. SRPT, VKTX).")
    parser.add_argument("--output", default=None, help="Output file. If omitted, prints to stdout.")
    parser.add_argument(
        "--as-of", default=None, dest="as_of",
        help="Report date (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--outputs-dir", default=None, dest="outputs_dir",
        help="Root outputs directory. Defaults to outputs/.",
    )
    parser.add_argument(
        "--ops-db", default=None, dest="ops_db",
        help="Path to ops.db. Defaults to outputs/intelligence/ops.db.",
    )
    parser.add_argument(
        "--prediction-log", default=None, dest="prediction_log",
        help="Path to prediction_log.db.",
    )
    parser.add_argument(
        "--no-refresh", action="store_true", dest="no_refresh",
        help="Skip live market/financial refresh.",
    )
    parser.add_argument(
        "--note", action="append", dest="notes", metavar="TEXT",
        help="Append a note to the report (repeatable).",
    )
    args = parser.parse_args(argv)

    as_of_date: Optional[date] = None
    if args.as_of:
        try:
            as_of_date = date.fromisoformat(args.as_of)
        except ValueError:
            print(f"ERROR: invalid --as-of date: {args.as_of!r}", file=sys.stderr)
            return 1

    ticker = args.ticker.upper()
    print(f"[bve-evaluate-target] Generating report for {ticker}...", file=sys.stderr)

    report = evaluate_target(
        ticker,
        as_of_date=as_of_date,
        outputs_dir=Path(args.outputs_dir) if args.outputs_dir else None,
        ops_db=Path(args.ops_db) if args.ops_db else None,
        prediction_log_db=Path(args.prediction_log) if args.prediction_log else None,
        skip_refresh=args.no_refresh,
        notes=args.notes or [],
    )

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"[bve-evaluate-target] Report written to {out}", file=sys.stderr)
    else:
        print(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
