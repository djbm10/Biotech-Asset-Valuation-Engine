"""
Weekly M&A report generator — Block 2E.

Converts a WeeklyMAScreenResult into six output files:

    ranked_targets.csv
    top_acquirer_pairs.csv
    suppressed_targets.csv
    score_changes.csv
    audit_report.md
    validation_snapshot.json

This module is pure formatting. No scoring, no ledger, no network.

Usage::

    gen = WeeklyReportGenerator()
    paths = gen.write_outputs(result, Path("outputs/weekly"), prev_result=prev)
"""
from __future__ import annotations

import csv
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from bve.ingestion.model_versions import (
    BASELINE_VERSION,
    CLASSIFIER_VERSION,
    DELTA_MAP_VERSION,
    PAIR_SCORER_VERSION,
)
from bve.intelligence.weekly_ma_screen import (
    TargetScreenResult,
    WeeklyMAScreenResult,
    pair_results_to_rows,
    ranked_targets_to_rows,
)

REPORT_VERSION = "phase2_report_v1"
_TOP_PAIRS_MAX = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_probability(x: float) -> str:
    return f"{x:.1%}"


def _join(items: list[str]) -> str:
    return "; ".join(items or [])


def _result_by_ticker(
    result: WeeklyMAScreenResult,
) -> dict[str, TargetScreenResult]:
    return {
        r.ticker: r
        for r in result.ranked_targets + result.suppressed_targets
    }


def compute_score_changes(
    result: WeeklyMAScreenResult,
    prev_result: Optional[WeeklyMAScreenResult],
) -> list[dict[str, Any]]:
    """
    Diff two screen results.

    rank_change = old_rank - new_rank (positive = moved up in rankings).
    Returns empty list when prev_result is None.
    """
    if prev_result is None:
        return []

    current = _result_by_ticker(result)
    previous = _result_by_ticker(prev_result)

    # Build a rank lookup — suppressed targets get a sentinel rank > any real rank
    _SUPPRESSED_SENTINEL = 9999

    def _rank(res_dict: dict[str, TargetScreenResult], ticker: str) -> int:
        t = res_dict.get(ticker)
        if t is None:
            return _SUPPRESSED_SENTINEL
        return t.rank if t.rank > 0 else _SUPPRESSED_SENTINEL

    all_tickers = set(current.keys()) | set(previous.keys())
    rows = []
    for ticker in sorted(all_tickers):
        curr = current.get(ticker)
        prev = previous.get(ticker)
        if curr is None and prev is None:
            continue

        old_rank = _rank(previous, ticker)
        new_rank = _rank(current, ticker)
        rank_change = (
            old_rank - new_rank
            if old_rank != _SUPPRESSED_SENTINEL and new_rank != _SUPPRESSED_SENTINEL
            else None
        )

        old_prob = prev.ma_probability if prev else None
        new_prob = curr.ma_probability if curr else None
        prob_change = (
            round(new_prob - old_prob, 4)
            if old_prob is not None and new_prob is not None
            else None
        )

        rows.append({
            "ticker": ticker,
            "name": (curr or prev).name,
            "old_rank": old_rank if old_rank != _SUPPRESSED_SENTINEL else "",
            "new_rank": new_rank if new_rank != _SUPPRESSED_SENTINEL else "",
            "rank_change": rank_change if rank_change is not None else "",
            "old_ma_score": old_prob if old_prob is not None else "",
            "new_ma_score": new_prob if new_prob is not None else "",
            "ma_score_change": prob_change if prob_change is not None else "",
            "old_top_acquirer": prev.top_acquirer or "" if prev else "",
            "new_top_acquirer": curr.top_acquirer or "" if curr else "",
            "changed_drivers": _diff_list(
                prev.main_drivers if prev else [],
                curr.main_drivers if curr else [],
            ),
            "changed_risks": _diff_list(
                prev.key_risks if prev else [],
                curr.key_risks if curr else [],
            ),
        })

    # Sort by |rank_change| descending, then by ticker
    rows.sort(key=lambda r: (-(abs(r["rank_change"]) if isinstance(r["rank_change"], int) else 0), r["ticker"]))
    return rows


def _diff_list(old: list[str], new: list[str]) -> str:
    """Return items that appear in new but not old (added), prefixed with '+'."""
    added = [f"+{x}" for x in new if x not in old]
    removed = [f"-{x}" for x in old if x not in new]
    return "; ".join(added + removed)


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


_RANKED_TARGETS_FIELDS = [
    "rank", "ticker", "name",
    "ma_score", "score_low", "score_high", "confidence_label",
    "asset_quality", "seller_willingness", "financing_risk", "ma_attractiveness", "catalyst_timing",
    "evidence_coverage_overall", "profile_quality_score",
    "top_acquirer", "top_acquirer_pair_score",
    "main_drivers", "key_risks",
]

_PAIRS_FIELDS = [
    "target_ticker", "acquirer_ticker", "pair_score",
    "ta_overlap", "modality_fit", "stage_fit",
    "deal_size_fit", "pipeline_gap_fill", "integration_complexity",
]

_SUPPRESSED_FIELDS = [
    "ticker", "name", "suppression_reason",
    "evidence_coverage_overall", "profile_quality_score",
    "asset_quality", "seller_willingness", "financing_risk", "ma_attractiveness", "catalyst_timing",
]

_SCORE_CHANGES_FIELDS = [
    "ticker", "name",
    "old_rank", "new_rank", "rank_change",
    "old_ma_score", "new_ma_score", "ma_score_change",
    "old_top_acquirer", "new_top_acquirer",
    "changed_drivers", "changed_risks",
]


def _ranked_targets_rows(result: WeeklyMAScreenResult) -> list[dict[str, Any]]:
    rows = ranked_targets_to_rows(result)
    # Rename internal ma_probability to ma_score for external output to signal
    # that these are ranking scores, not calibrated acquisition probabilities.
    for row in rows:
        row["ma_score"] = row.pop("ma_probability", None)
        row["score_low"] = row.pop("probability_low", None)
        row["score_high"] = row.pop("probability_high", None)
    return rows


def _suppressed_rows(result: WeeklyMAScreenResult) -> list[dict[str, Any]]:
    return [
        {
            "ticker": t.ticker,
            "name": t.name,
            "suppression_reason": t.suppression_reason or "",
            "evidence_coverage_overall": t.evidence_coverage_overall,
            "profile_quality_score": t.profile_quality_score,
            "asset_quality": t.asset_quality,
            "seller_willingness": t.seller_willingness,
            "financing_risk": t.financing_risk,
            "ma_attractiveness": t.ma_attractiveness,
            "catalyst_timing": t.catalyst_timing,
        }
        for t in result.suppressed_targets
    ]


def _pairs_rows(result: WeeklyMAScreenResult) -> list[dict[str, Any]]:
    rows = pair_results_to_rows(result)
    rows.sort(key=lambda r: r["pair_score"], reverse=True)
    return rows[:_TOP_PAIRS_MAX]


# ---------------------------------------------------------------------------
# Validation snapshot
# ---------------------------------------------------------------------------


def _build_validation_snapshot(result: WeeklyMAScreenResult) -> dict[str, Any]:
    ranked = result.ranked_targets
    top = ranked[0] if ranked else None
    probs = [t.ma_probability for t in ranked]
    median_prob = round(statistics.median(probs), 4) if probs else None

    return {
        "as_of_date": result.as_of_date.isoformat(),
        "score_mode": result.score_mode,
        "n_targets_input": result.diagnostics.get("n_targets_input", 0),
        "n_ranked_targets": len(ranked),
        "n_suppressed_targets": len(result.suppressed_targets),
        "n_acquirer_pairs": result.diagnostics.get("n_pair_scores", 0),
        "top_target": top.ticker if top else None,
        "top_ma_score": top.ma_probability if top else None,
        "median_ma_score": median_prob,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "diagnostics": result.diagnostics,
        "classifier_version": CLASSIFIER_VERSION,
        "delta_map_version": DELTA_MAP_VERSION,
        "baseline_model_version": BASELINE_VERSION,
        "pair_scorer_version": PAIR_SCORER_VERSION,
        "schema_version": REPORT_VERSION,
        # Calibration metadata — machine-readable flag for downstream consumers
        "calibration_status": "uncalibrated",
        "output_interpretation": (
            "ma_score is a ranked diligence priority score (0-1), not a "
            "validated acquisition probability. Do not interpret absolute values "
            "as likelihood estimates. Use rank ordering only."
        ),
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    col_widths = [max(len(h), max((len(str(r[i])) for r in rows), default=0)) for i, h in enumerate(headers)]
    sep = "| " + " | ".join("-" * w for w in col_widths) + " |"
    header_row = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
    lines = [header_row, sep]
    for row in rows:
        lines.append("| " + " | ".join(str(row[i]).ljust(col_widths[i]) for i in range(len(headers))) + " |")
    return "\n".join(lines)


class WeeklyReportGenerator:
    """
    Convert a WeeklyMAScreenResult into human-readable output files.

    No scoring logic here — pure formatting.
    """

    def generate_markdown(
        self,
        result: WeeklyMAScreenResult,
        prev_result: Optional[WeeklyMAScreenResult] = None,
    ) -> str:
        """Build the full audit_report.md content as a string."""
        ranked = result.ranked_targets
        suppressed = result.suppressed_targets
        pairs = _pairs_rows(result)
        changes = compute_score_changes(result, prev_result)

        probs = [t.ma_probability for t in ranked]
        median_prob = statistics.median(probs) if probs else 0.0
        top = ranked[0] if ranked else None

        lines: list[str] = []

        # ── Header ─────────────────────────────────────────────────────────
        lines.append(f"# Weekly Biotech M&A Screen — {result.as_of_date.isoformat()}")
        lines.append("")
        lines.append(
            "> **UNCALIBRATED** — `ma_score` is a ranked diligence priority score, "
            "not a validated acquisition probability. "
            "Absolute values (e.g. 0.63) are not meaningful in isolation. "
            "Use rank ordering only. Do not cite these scores as likelihood estimates."
        )
        lines.append("")

        # ── Run summary ────────────────────────────────────────────────────
        lines.append("## Run Summary")
        lines.append("")
        lines.append(f"- Score mode: `{result.score_mode}`")
        lines.append(f"- Targets ranked: {len(ranked)}")
        lines.append(f"- Targets suppressed: {len(suppressed)}")
        lines.append(f"- Acquirer pairs scored: {result.diagnostics.get('n_pair_scores', 0)}")
        lines.append(f"- Top target: **{top.ticker if top else 'none'}**"
                     + (f" (ma_score={_format_probability(top.ma_probability)})" if top else ""))
        lines.append(f"- Median ma_score: {_format_probability(median_prob)}")
        lines.append("")

        # ── Top 25 targets ─────────────────────────────────────────────────
        lines.append("## Top 25 Targets")
        lines.append("")
        top25 = ranked[:25]
        if top25:
            rows = [
                [
                    str(t.rank),
                    t.ticker,
                    _format_probability(t.ma_probability),
                    f"{_format_probability(t.probability_low)}–{_format_probability(t.probability_high)}",
                    t.confidence_label,
                    t.top_acquirer or "—",
                    (t.main_drivers[0] if t.main_drivers else "—"),
                    (t.key_risks[0] if t.key_risks else "—"),
                ]
                for t in top25
            ]
            lines.append(_md_table(
                ["Rank", "Ticker", "ma_score", "Range", "Confidence", "Top Acquirer",
                 "Main Driver", "Key Risk"],
                rows,
            ))
        else:
            lines.append("_No ranked targets._")
        lines.append("")

        # ── Top 20 acquirer pairs ──────────────────────────────────────────
        lines.append("## Top 20 Acquirer Pairs")
        lines.append("")
        top_pairs = pairs[:20]
        if top_pairs:
            pair_rows = [
                [
                    p["target_ticker"],
                    p["acquirer_ticker"],
                    f"{p['pair_score']:.2f}",
                    f"{p['ta_overlap']:.2f}",
                    "Yes" if p["modality_fit"] == 1.0 else "No",
                    f"{p['deal_size_fit']:.2f}",
                ]
                for p in top_pairs
            ]
            lines.append(_md_table(
                ["Target", "Acquirer", "Pair Score", "TA Fit", "Modality Fit", "Deal Size Fit"],
                pair_rows,
            ))
        else:
            lines.append("_No pair scores available._")
        lines.append("")

        # ── Score changes ──────────────────────────────────────────────────
        lines.append("## Biggest Score Changes")
        lines.append("")
        if changes:
            top_changes = [c for c in changes if isinstance(c["rank_change"], int)][:10]
            if top_changes:
                change_rows = [
                    [
                        c["ticker"],
                        f"{c['rank_change']:+d}" if isinstance(c["rank_change"], int) else "—",
                        (f"{c['ma_score_change']:+.1%}"
                         if isinstance(c["ma_score_change"], float) else "—"),
                        str(c["old_top_acquirer"] or "—"),
                        str(c["new_top_acquirer"] or "—"),
                    ]
                    for c in top_changes
                ]
                lines.append(_md_table(
                    ["Ticker", "Rank Change", "ma_score Change",
                     "Old Top Acquirer", "New Top Acquirer"],
                    change_rows,
                ))
            else:
                lines.append("_No rank changes to report._")
        else:
            lines.append("_No previous result available for comparison._")
        lines.append("")

        # ── Suppressed targets ─────────────────────────────────────────────
        lines.append("## Suppressed Targets")
        lines.append("")
        if suppressed:
            sup_rows = [
                [
                    t.ticker,
                    t.suppression_reason or "—",
                    f"{t.evidence_coverage_overall:.2f}",
                    f"{t.profile_quality_score:.2f}",
                ]
                for t in suppressed
            ]
            lines.append(_md_table(
                ["Ticker", "Reason", "Coverage", "Profile Quality"],
                sup_rows,
            ))
        else:
            lines.append("_No targets suppressed._")
        lines.append("")

        # ── Pending review / provisional ──────────────────────────────────
        lines.append("## Pending Review / Provisional Signals")
        lines.append("")
        if result.score_mode == "provisional":
            lines.append(
                "_Score mode is `provisional`. Pending events count at 50% weight. "
                "Switch to `approved_only` once a review pipeline is staffed._"
            )
        elif result.score_mode == "all_auto":
            lines.append(
                "_Score mode is `all_auto`. All events count at full weight. "
                "This mode is suitable for backtesting only._"
            )
        else:
            lines.append("_Score mode is `approved_only`. Only reviewed events count._")
        lines.append("")

        # ── Model diagnostics ──────────────────────────────────────────────
        lines.append("## Model Diagnostics")
        lines.append("")
        lines.append(f"- Pair score count: {result.diagnostics.get('n_pair_scores', 0)}")
        lines.append(f"- Score mode: `{result.score_mode}`")
        lines.append(f"- Classifier version: `{CLASSIFIER_VERSION}`")
        lines.append(f"- Baseline model version: `{BASELINE_VERSION}`")
        lines.append(f"- Pair scorer version: `{PAIR_SCORER_VERSION}`")
        lines.append(f"- Report version: `{REPORT_VERSION}`")
        lines.append("")

        # ── Notes ──────────────────────────────────────────────────────────
        lines.append("## Notes")
        lines.append("")
        lines.append(
            "This report is a research output, not an investment recommendation. "
            "All scores are model estimates subject to revision as new evidence arrives."
        )
        lines.append("")

        return "\n".join(lines)

    def write_outputs(
        self,
        result: WeeklyMAScreenResult,
        output_dir: Path,
        prev_result: Optional[WeeklyMAScreenResult] = None,
    ) -> list[Path]:
        """
        Write all six output files to output_dir.

        Returns list of paths written.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []

        # 1. ranked_targets.csv
        p = output_dir / "ranked_targets.csv"
        _write_csv(p, _ranked_targets_rows(result), _RANKED_TARGETS_FIELDS)
        written.append(p)

        # 2. top_acquirer_pairs.csv
        p = output_dir / "top_acquirer_pairs.csv"
        _write_csv(p, _pairs_rows(result), _PAIRS_FIELDS)
        written.append(p)

        # 3. suppressed_targets.csv
        p = output_dir / "suppressed_targets.csv"
        _write_csv(p, _suppressed_rows(result), _SUPPRESSED_FIELDS)
        written.append(p)

        # 4. score_changes.csv (headers always written)
        p = output_dir / "score_changes.csv"
        _write_csv(p, compute_score_changes(result, prev_result), _SCORE_CHANGES_FIELDS)
        written.append(p)

        # 5. audit_report.md
        p = output_dir / "audit_report.md"
        p.write_text(self.generate_markdown(result, prev_result), encoding="utf-8")
        written.append(p)

        # 6. validation_snapshot.json
        p = output_dir / "validation_snapshot.json"
        p.write_text(
            json.dumps(_build_validation_snapshot(result), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        written.append(p)

        return written
