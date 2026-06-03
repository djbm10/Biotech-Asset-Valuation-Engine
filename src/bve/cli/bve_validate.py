"""bve-validate CLI: print validation evidence summary to stdout.

Usage
-----
    bve-validate
    bve-validate --output outputs/validation_summary.md
    bve-validate --replay-run-id <run_id>
    bve-validate --ma-backtest-records research/mna/deal_universe_2020_2026.yaml

Loads all available validation evidence and renders a Markdown summary.
Individual surfaces that are unavailable are shown as "Not available" — the
command always succeeds.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _load_replay_summary(run_id: str | None) -> object | None:
    """Load the most recent (or specific) replay summary."""
    try:
        from bve.ops.historical_replay import ReplayStore

        default_db = Path("outputs") / "intelligence" / "replay_store.sqlite"
        if not default_db.exists():
            return None

        store = ReplayStore(str(default_db))

        if run_id:
            runs = [run_id]
        else:
            # Get most recent run
            conn = getattr(store, "_conn", None)
            if conn is None:
                return None
            row = conn.execute(
                "SELECT run_id FROM replay_runs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            runs = [row[0]]

        from bve.ops.historical_replay import HistoricalReplay
        kb_path = str(Path("outputs") / "intelligence" / "replay_knowledge.db")
        replay = HistoricalReplay(replay_store=store, knowledge_store_path=kb_path)
        return replay.summarize(runs[0])

    except Exception:
        return None


def _load_ma_backtest_result(records_path: str | None) -> object | None:
    """Load M&A backtest result (from deal universe YAML or None)."""
    try:
        from bve.intelligence.ma_backtest import (
            build_backtest_records_from_deal_universe,
            run_backtest,
        )
        path = records_path
        if path and not Path(path).exists():
            return None
        records = build_backtest_records_from_deal_universe(path)
        if not records:
            return None
        return run_backtest(records)
    except Exception:
        return None


def _load_pos_backtest_result() -> object | None:
    """Load POS calibration backtest result from the oncology dataset."""
    try:
        from bve.analysis.backtest import run_backtest_from_csv

        default_csv = Path("research") / "data" / "oncology_phase_transitions.csv"
        if not default_csv.exists():
            return None
        return run_backtest_from_csv(str(default_csv))
    except Exception:
        return None


def _load_known_answer_suite(cases_path: str | None) -> object | None:
    """Run the known-answer validation suite (definitions-only mode)."""
    try:
        from bve.validation.known_answer_cases import load_cases
        from bve.validation.known_answer_validator import run_suite

        cases = load_cases(cases_path)
        if not cases:
            return None
        return run_suite(cases)
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-validate",
        description="Print the BVE validation evidence summary.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--replay-run-id",
        default=None,
        dest="replay_run_id",
        help="Specific replay run ID to include. Defaults to most recent.",
    )
    parser.add_argument(
        "--ma-backtest-records",
        default=None,
        dest="ma_backtest_records",
        help="Path to deal universe YAML for M&A backtest. "
             "Defaults to research/mna/deal_universe_2020_2026.yaml.",
    )
    parser.add_argument(
        "--no-replay",
        action="store_true",
        help="Skip replay summary loading.",
    )
    parser.add_argument(
        "--no-ma-backtest",
        action="store_true",
        help="Skip M&A backtest loading.",
    )
    parser.add_argument(
        "--no-pos-backtest",
        action="store_true",
        help="Skip POS calibration loading.",
    )
    parser.add_argument(
        "--no-known-answers",
        action="store_true",
        help="Skip known-answer suite.",
    )
    parser.add_argument(
        "--known-answer-cases",
        default=None,
        dest="known_answer_cases",
        help="Path to known-answer cases YAML. Defaults to bundled cases.yaml.",
    )
    args = parser.parse_args(argv)

    print("[bve-validate] Loading validation evidence...", file=sys.stderr)

    replay_summary = (
        None if args.no_replay
        else _load_replay_summary(args.replay_run_id)
    )
    ma_result = (
        None if args.no_ma_backtest
        else _load_ma_backtest_result(args.ma_backtest_records)
    )
    pos_result = (
        None if args.no_pos_backtest
        else _load_pos_backtest_result()
    )
    ka_result = (
        None if args.no_known_answers
        else _load_known_answer_suite(args.known_answer_cases)
    )

    from bve.reporting.validation_summary import (
        build_validation_summary,
        render_validation_summary,
    )
    data = build_validation_summary(
        replay_summary=replay_summary,
        ma_backtest_result=ma_result,
        pos_backtest_result=pos_result,
        known_answer_suite_result=ka_result,
    )
    rendered = render_validation_summary(data)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        print(f"[bve-validate] Validation summary written to {out_path}", file=sys.stderr)
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
