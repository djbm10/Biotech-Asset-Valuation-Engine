"""Validation evidence aggregator for the bve-validate command and decision reports.

Pulls together evidence from four independent validation surfaces:
1. Historical replay alpha (from ReplaySummary)
2. M&A backtest metrics (from MABacktestResult — Block 7)
3. POS calibration metrics (from analysis/backtest.py BacktestResult)
4. Logistic calibration parameter source (fitted JSON vs hard-coded fallback)

Design principles
-----------------
- All inputs are Optional; missing data renders as "Not available" not an error.
- ``build_validation_summary`` never touches disk (callers load data first).
- ``render_validation_summary`` returns a self-contained Markdown section.
- Validation status disclaimers are always rendered — they cannot be suppressed.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class ValidationSummaryData:
    """Aggregated validation evidence from all available surfaces.

    All numeric fields default to None (= not available).
    ``generated_at`` is set automatically by ``build_validation_summary``.
    """

    # --- Replay alpha (historical_replay.py) ---
    replay_mean_return_pct: Optional[float] = None
    replay_mean_alpha_pct: Optional[float] = None
    replay_alpha_hit_rate: Optional[float] = None
    replay_n_resolved: int = 0
    replay_n_with_xbi_data: int = 0
    replay_validation_status: str = "directional_only"
    replay_hit_rate: Optional[float] = None
    replay_brier_score: Optional[float] = None
    replay_run_id: Optional[str] = None
    replay_strategy: Optional[str] = None
    replay_period: Optional[str] = None

    # --- M&A backtest (ma_backtest.py — Block 7) ---
    ma_auc: Optional[float] = None
    ma_brier_score: Optional[float] = None
    ma_base_rate: Optional[float] = None
    ma_score_separation: Optional[float] = None
    ma_n: int = 0
    ma_n_positive: int = 0
    ma_training_window: Optional[str] = None

    # --- POS calibration (analysis/backtest.py) ---
    pos_heuristic_brier: Optional[float] = None
    pos_heuristic_auc: Optional[float] = None
    pos_n_programs: int = 0
    pos_base_rate_phase2: Optional[float] = None
    pos_base_rate_phase3: Optional[float] = None

    # --- Logistic calibration parameters ---
    calibration_slope: float = 8.0
    calibration_midpoint: float = 0.68
    calibration_source: str = "hardcoded_fallback"  # "fitted" | "hardcoded_fallback"
    calibration_params_n_positive: int = 0
    calibration_params_training_window: Optional[str] = None

    # --- Known-answer suite (Block 10) ---
    known_answer_n_cases: int = 0
    known_answer_n_pass: int = 0
    known_answer_n_fail: int = 0
    known_answer_n_definitions_only: int = 0
    known_answer_overall_pass: Optional[bool] = None  # None = not run

    # --- Metadata ---
    generated_at: str = ""
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_validation_summary(
    *,
    replay_summary: Optional[object] = None,
    ma_backtest_result: Optional[object] = None,
    pos_backtest_result: Optional[object] = None,
    calibration_params_path: Optional[Path] = None,
    known_answer_suite_result: Optional[object] = None,
) -> ValidationSummaryData:
    """Assemble a ValidationSummaryData from available evidence objects.

    Parameters
    ----------
    replay_summary:
        ``bve.intelligence.replay_summary.ReplaySummary`` instance (or None).
    ma_backtest_result:
        ``bve.intelligence.ma_backtest.MABacktestResult`` instance (or None).
    pos_backtest_result:
        ``bve.analysis.backtest.BacktestResult`` instance (or None).
    calibration_params_path:
        Path to fitted ``ma_calibration_params.json``. When None, the default
        path from ``ma_backtest._DEFAULT_PARAMS_PATH`` is used.

    Returns
    -------
    ValidationSummaryData
    """
    data = ValidationSummaryData(
        generated_at=datetime.now(timezone.utc).isoformat()
    )

    # 1. Replay alpha
    if replay_summary is not None:
        data.replay_mean_return_pct = getattr(replay_summary, "mean_return_pct", None)
        data.replay_mean_alpha_pct = getattr(replay_summary, "mean_alpha_pct", None)
        data.replay_alpha_hit_rate = getattr(replay_summary, "alpha_hit_rate", None)
        data.replay_n_resolved = getattr(replay_summary, "n_resolved", 0)
        data.replay_n_with_xbi_data = getattr(replay_summary, "n_with_xbi_data", 0)
        data.replay_validation_status = getattr(
            replay_summary, "validation_status", "directional_only"
        )
        data.replay_hit_rate = getattr(replay_summary, "hit_rate", None)
        data.replay_brier_score = getattr(replay_summary, "brier_score", None)
        data.replay_run_id = getattr(replay_summary, "run_id", None)
        data.replay_strategy = getattr(replay_summary, "strategy_version", None)
        start = getattr(replay_summary, "start_date", None)
        end = getattr(replay_summary, "end_date", None)
        if start and end:
            data.replay_period = f"{start} → {end}"

    # 2. M&A backtest
    if ma_backtest_result is not None:
        data.ma_auc = getattr(ma_backtest_result, "auc", None)
        data.ma_brier_score = getattr(ma_backtest_result, "brier_score", None)
        data.ma_base_rate = getattr(ma_backtest_result, "base_rate", None)
        data.ma_score_separation = getattr(ma_backtest_result, "score_separation", None)
        data.ma_n = getattr(ma_backtest_result, "n", 0)
        data.ma_n_positive = getattr(ma_backtest_result, "n_positive", 0)
        data.ma_training_window = getattr(ma_backtest_result, "training_window", None)

    # 3. POS calibration
    if pos_backtest_result is not None:
        data.pos_heuristic_brier = getattr(pos_backtest_result, "heuristic_brier_score", None)
        data.pos_heuristic_auc = getattr(pos_backtest_result, "heuristic_auc", None)
        data.pos_n_programs = getattr(pos_backtest_result, "n_programs", 0)
        # phase-specific base rates
        data.pos_base_rate_phase2 = getattr(pos_backtest_result, "phase2_base_rate", None)
        data.pos_base_rate_phase3 = getattr(pos_backtest_result, "phase3_base_rate", None)

    # 4. Logistic calibration params
    try:
        from bve.intelligence.ma_backtest import (
            load_calibration_params,
            _DEFAULT_PARAMS_PATH,
        )
        params_path = calibration_params_path or _DEFAULT_PARAMS_PATH

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            slope, midpoint = load_calibration_params(params_path)

        if caught_warnings:
            data.calibration_source = "hardcoded_fallback"
            data.notes.append(
                "Logistic calibration using hard-coded defaults (no fitted params found). "
                "Run `bve-ma-probability --fit` to generate fitted parameters."
            )
        else:
            data.calibration_source = "fitted"

        data.calibration_slope = slope
        data.calibration_midpoint = midpoint

        # Try to read metadata from the JSON
        if params_path is not None and Path(params_path).exists():
            import json
            try:
                raw = json.loads(Path(params_path).read_text())
                data.calibration_params_n_positive = int(raw.get("n_positive", 0))
                data.calibration_params_training_window = raw.get("training_window")
            except (json.JSONDecodeError, KeyError, ValueError):
                pass

    except ImportError:
        data.notes.append("ma_backtest module not available — calibration param status unknown.")

    # 5. Known-answer suite
    if known_answer_suite_result is not None:
        data.known_answer_n_cases = getattr(known_answer_suite_result, "n_cases", 0)
        data.known_answer_n_pass = getattr(known_answer_suite_result, "n_pass", 0)
        data.known_answer_n_fail = getattr(known_answer_suite_result, "n_fail", 0)
        data.known_answer_n_definitions_only = getattr(
            known_answer_suite_result, "n_definitions_only", 0
        )
        data.known_answer_overall_pass = getattr(
            known_answer_suite_result, "overall_pass", None
        )

    return data


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

_NA = "Not available"


def _fmt_opt(value: Optional[float], fmt: str = ".4f") -> str:
    if value is None:
        return _NA
    return format(value, fmt)


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return _NA
    return f"{value:+.2f}%"


def _fmt_plain(value: Optional[float], fmt: str = ".4f") -> str:
    return _NA if value is None else format(value, fmt)


def render_validation_summary(data: ValidationSummaryData) -> str:
    """Render a self-contained Markdown validation evidence section.

    Always includes the validation status disclaimer — this cannot be
    suppressed so that every human-readable output carries appropriate caveats.

    Parameters
    ----------
    data:
        Assembled ``ValidationSummaryData``.

    Returns
    -------
    str
        Markdown string.
    """
    lines: list[str] = []

    # Hard disclaimer
    lines += [
        "## Validation Evidence",
        "",
        "> **VALIDATION STATUS**: This tool produces *directional research outputs*, "
        "not investment advice. All metrics shown below are out-of-sample estimates "
        "on a limited dataset and should be interpreted with appropriate caution. "
        "N < 50 for most surfaces — statistical significance has not been established.",
        "",
    ]

    # --- Replay alpha ---
    lines += [
        "### Historical Replay Alpha",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Resolved decisions | {data.replay_n_resolved} |",
        f"| Mean return | {_fmt_pct(data.replay_mean_return_pct)} |",
        f"| XBI-adj alpha | {_fmt_pct(data.replay_mean_alpha_pct)} |",
        f"| Alpha hit rate | {_fmt_plain(data.replay_alpha_hit_rate, '.1%') if data.replay_alpha_hit_rate is not None else _NA} |",
        f"| Decisions w/ XBI data | {data.replay_n_with_xbi_data} |",
        f"| Hit rate | {_fmt_plain(data.replay_hit_rate, '.1%') if data.replay_hit_rate is not None else _NA} |",
        f"| Brier score | {_fmt_plain(data.replay_brier_score, '.4f')} |",
        f"| Strategy | {data.replay_strategy or _NA} |",
        f"| Period | {data.replay_period or _NA} |",
        f"| Validation status | `{data.replay_validation_status}` |",
        "",
    ]

    # --- M&A Backtest ---
    lines += [
        "### M&A Backtest Metrics (Block 7)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| N (total) | {data.ma_n if data.ma_n else _NA} |",
        f"| N (positive) | {data.ma_n_positive if data.ma_n_positive else _NA} |",
        f"| AUC | {_fmt_plain(data.ma_auc, '.4f')} |",
        f"| Brier score | {_fmt_plain(data.ma_brier_score, '.6f')} |",
        f"| Base rate | {_fmt_plain(data.ma_base_rate, '.4f')} |",
        f"| Score separation (acq − non-acq) | {_fmt_plain(data.ma_score_separation, '.4f')} |",
        f"| Training window | {data.ma_training_window or _NA} |",
        "",
        "> N.B. Positive examples scored using heuristic phase-to-score mapping (v1). "
        "Replace with historical scan outputs for production validation.",
        "",
    ]

    # --- POS calibration ---
    lines += [
        "### POS Model Calibration (Oncology Dataset)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| N programs | {data.pos_n_programs if data.pos_n_programs else _NA} |",
        f"| Heuristic Brier | {_fmt_plain(data.pos_heuristic_brier, '.4f')} |",
        f"| Heuristic AUC | {_fmt_plain(data.pos_heuristic_auc, '.4f')} |",
        f"| Phase 2 base rate | {_fmt_plain(data.pos_base_rate_phase2, '.1%') if data.pos_base_rate_phase2 is not None else _NA} |",
        f"| Phase 3 base rate | {_fmt_plain(data.pos_base_rate_phase3, '.1%') if data.pos_base_rate_phase3 is not None else _NA} |",
        "",
    ]

    # --- Calibration params ---
    source_label = (
        "**Fitted (JSON)**" if data.calibration_source == "fitted"
        else "⚠ Hard-coded fallback (no fitted file)"
    )
    lines += [
        "### Logistic Calibration Parameters",
        "",
        "| Parameter | Value |",
        "|---|---|",
        f"| Source | {source_label} |",
        f"| Slope | {data.calibration_slope:.4f} |",
        f"| Midpoint | {data.calibration_midpoint:.4f} |",
        f"| N positive (training) | {data.calibration_params_n_positive if data.calibration_params_n_positive else _NA} |",
        f"| Training window | {data.calibration_params_training_window or _NA} |",
        "",
    ]

    # --- Known-answer suite ---
    if data.known_answer_n_cases > 0 or data.known_answer_overall_pass is not None:
        ka_status = _NA
        if data.known_answer_overall_pass is True:
            ka_status = "PASS"
        elif (
            data.known_answer_n_cases > 0
            and data.known_answer_n_definitions_only == data.known_answer_n_cases
        ):
            ka_status = "DEFINITIONS ONLY"
        elif data.known_answer_overall_pass is False:
            ka_status = "FAIL"
        lines += [
            "### Known-Answer Suite (Block 10)",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Cases | {data.known_answer_n_cases if data.known_answer_n_cases else _NA} |",
            f"| Pass | {data.known_answer_n_pass} |",
            f"| Fail | {data.known_answer_n_fail} |",
            f"| Definitions only | {data.known_answer_n_definitions_only} |",
            f"| Overall status | `{ka_status}` |",
            "",
        ]

    # Notes
    if data.notes:
        lines += ["### Notes", ""]
        for note in data.notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.append(f"*Generated: {data.generated_at}*")
    lines.append("")

    return "\n".join(lines)
