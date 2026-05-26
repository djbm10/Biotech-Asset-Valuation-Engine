"""bve-report CLI: generate a decision-grade Markdown report for a ticker.

Usage
-----
    bve-report --ticker SRPT
    bve-report --ticker SRPT --output outputs/srpt_report.md
    bve-report --ticker SRPT --prediction-log outputs/intelligence/prediction_log.db

The command attempts to load all available data for the ticker from:
- The M&A probability snapshot store (most recent snapshot)
- The prediction log database
- The valuation output JSON in outputs/<TICKER>/valuation.json

All missing data is handled gracefully — the report is always generated,
with "Not available" substituted for any section whose data is absent.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


def _load_ma_row(ticker: str) -> object | None:
    """Try to load the most recent MAProbabilityRow snapshot for the ticker."""
    try:
        from bve.intelligence.ma_probability import MAProbabilityScanner
        from bve.intelligence.knowledge_layer import KnowledgeStore

        default_db = Path("outputs") / "intelligence" / "ops.db"
        if not default_db.exists():
            return None

        kb = KnowledgeStore(str(default_db))
        scanner = MAProbabilityScanner(knowledge_store=kb)
        rows = scanner.scan_watchlist(limit=200)
        ticker_upper = ticker.upper()
        for row in rows:
            if (row.ticker or "").upper() == ticker_upper:
                return row
        return None
    except Exception:
        return None


def _load_valuation_output(ticker: str) -> object | None:
    """Try to load the most recent valuation output JSON for the ticker."""
    try:
        candidate = Path("outputs") / ticker.upper() / "valuation.json"
        if not candidate.exists():
            return None
        import json
        # ValuationOutput.from_json not universally available — return raw dict
        # wrapped in a lightweight namespace for the report builder
        raw = json.loads(candidate.read_text())
        return _ValuationOutputShim(raw)
    except Exception:
        return None


class _ValuationOutputShim:
    """Minimal shim so the report builder can call .summary_dict on a raw dict."""

    def __init__(self, raw: dict) -> None:
        self._raw = raw

    @property
    def summary_dict(self) -> dict:
        return self._raw

    def __getattr__(self, name: str):
        # Support getattr(shim, "pos_comparison_text") etc.
        return self._raw.get(name)


def _load_prediction_log_entries(ticker: str, db_path: str | None) -> list[dict]:
    """Load prediction log entries for the given ticker."""
    try:
        from bve.ops.prediction_log import PredictionLog

        path = db_path or str(
            Path("outputs") / "intelligence" / "prediction_log.db"
        )
        if not Path(path).exists():
            return []

        log = PredictionLog(path)
        all_entries = log.unresolved() + [
            r for r in _load_all_entries(log) if r.get("outcome")
        ]
        ticker_upper = ticker.upper()
        return [
            e for e in all_entries
            if (e.get("ticker") or "").upper() == ticker_upper
        ]
    except Exception:
        return []


def _load_all_entries(log: object) -> list[dict]:
    """Load all entries from the prediction log (resolved + unresolved)."""
    try:
        conn = getattr(log, "_conn", None)
        if conn is None:
            return []
        rows = conn.execute("SELECT * FROM prediction_log ORDER BY logged_at").fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-report",
        description="Generate a decision-grade Markdown report for a ticker.",
    )
    parser.add_argument(
        "--ticker",
        required=True,
        help="Stock ticker (e.g. SRPT, VKTX).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--prediction-log",
        default=None,
        dest="prediction_log",
        help="Path to prediction_log.db. Defaults to outputs/intelligence/prediction_log.db.",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        dest="as_of",
        help="Report date (YYYY-MM-DD). Defaults to today.",
    )
    args = parser.parse_args(argv)

    # Parse date
    as_of_date: date
    if args.as_of:
        try:
            as_of_date = date.fromisoformat(args.as_of)
        except ValueError:
            print(f"ERROR: invalid --as-of date: {args.as_of!r}", file=sys.stderr)
            return 1
    else:
        as_of_date = date.today()

    ticker = args.ticker.upper()
    print(f"[bve-report] Generating report for {ticker} as of {as_of_date}...", file=sys.stderr)

    # Load data (all optional — report degrades gracefully on missing data)
    ma_row = _load_ma_row(ticker)
    valuation_output = _load_valuation_output(ticker)
    log_entries = _load_prediction_log_entries(ticker, args.prediction_log)

    # Assemble validation summary from available evidence
    from bve.reporting.validation_summary import build_validation_summary
    validation_summary = build_validation_summary()

    # Build report
    from bve.reporting.decision_report import DecisionReportInput, render_decision_report
    report_input = DecisionReportInput(
        ticker=ticker,
        as_of_date=as_of_date,
        valuation_output=valuation_output,
        ma_row=ma_row,
        prediction_log_entries=log_entries,
        validation_summary=validation_summary,
    )
    report = render_decision_report(report_input)

    # Output
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"[bve-report] Report written to {out_path}", file=sys.stderr)
    else:
        print(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
