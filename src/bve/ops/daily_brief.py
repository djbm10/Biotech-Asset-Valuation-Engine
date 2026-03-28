"""
Daily Opportunity Brief — Sprint 19.

Integrates the full Sprint 10–18 pipeline into a single ranked output:
  1. Universe implied-PoS spread screen (Sprint 10–11)
  2. CalibratedPOSModel base-rate adjustment (Sprint 17)
  3. Expert note signals per ticker (Sprint 18)
  4. Event monitoring flags per ticker (Sprint 15)

Output: DailyBrief dataclass → markdown text via render_brief()

Usage
-----
    from bve.ops.daily_brief import build_daily_brief, render_brief
    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.ops.weekly_runner import UNIVERSE
    from bve.ops.universe_configs import load_params

    store = KnowledgeStore("outputs/intelligence/ops.db")
    params = load_params()
    brief = build_daily_brief(store, UNIVERSE, params, fetch_live=False)
    print(render_brief(brief))
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from bve.intelligence.knowledge_layer import KnowledgeStore


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

@dataclass
class BriefRow:
    """
    One row in the daily opportunity brief.

    Combines the mispricing spread, calibrated PoS adjustment,
    expert note signals, and event flags.
    """

    ticker: str
    program_label: str
    stage: str
    ta: str

    # Spread signal (Sprint 10-11)
    model_pos: float
    implied_pos: Optional[float]
    spread_pp: Optional[float]            # model_pos - implied_pos (pp)
    rnpv_millions: float
    ev_millions: Optional[float]

    # Calibrated PoS (Sprint 17)
    calibrated_base_rate: Optional[float] = None  # from CalibratedPOSModel
    calibrated_pos_delta: Optional[float] = None  # calibrated - model_pos (pp)

    # Catalyst
    next_catalyst: str = "unknown"
    days_to_catalyst: Optional[int] = None

    # Expert notes (Sprint 18)
    expert_note_count: int = 0
    expert_signal_types: set = field(default_factory=set)

    # Event monitoring (Sprint 15)
    recent_event_count: int = 0
    requires_recompute: bool = False

    # Composite score (0.0–1.0; higher = more actionable)
    composite_score: float = 0.0

    @property
    def spread_label(self) -> str:
        if self.spread_pp is None:
            return "n/a"
        return f"{self.spread_pp:+.1f}pp"

    @property
    def signal_flags(self) -> str:
        """Short flag string e.g. 'E,S,C' for efficacy/safety/commercial."""
        flags = []
        if "efficacy" in self.expert_signal_types:
            flags.append("E")
        if "safety" in self.expert_signal_types:
            flags.append("S")
        if "commercial" in self.expert_signal_types:
            flags.append("C")
        return ",".join(flags) if flags else "—"


@dataclass
class CalibrationStats:
    """Summary of CalibratedPOSModel state."""

    n_outcomes: int = 0
    n_bins_calibrated: int = 0
    is_live: bool = False       # True if loaded from KnowledgeStore (not fallback)


@dataclass
class DailyBrief:
    """Assembled daily opportunity brief."""

    as_of: date
    generated_at: datetime
    rows: list[BriefRow]           # ranked by composite_score DESC
    calibration: CalibrationStats
    n_universe: int = 0            # total names screened
    n_with_spread: int = 0         # names with valid implied_pos
    n_expert_notes: int = 0        # total expert notes considered
    n_recent_events: int = 0       # total detected events (last 7 days)
    n_requires_recompute: int = 0  # names flagged for recomputation


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

_SPREAD_WEIGHT = 0.50
_CALIBRATION_WEIGHT = 0.20
_EXPERT_WEIGHT = 0.20
_EVENT_WEIGHT = 0.10

_MAX_SPREAD_PP = 40.0   # spread ≥ 40pp → full spread score
_MAX_NOTES = 3          # ≥ 3 notes → full expert score


def _score_row(row: BriefRow) -> float:
    """
    Composite opportunity score 0.0–1.0.

    Components
    ----------
    - Spread (50%): normalized spread_pp capped at _MAX_SPREAD_PP
    - Calibration adjustment (20%): how much calibrated model shifts PoS upward
    - Expert signals (20%): note count + signal type diversity
    - Event flag (10%): requires_recompute + recent event density
    """
    # Spread component
    if row.spread_pp is not None and row.spread_pp > 0:
        spread_score = min(1.0, row.spread_pp / _MAX_SPREAD_PP)
    else:
        spread_score = 0.0

    # Calibration component — positive delta = calibrated PoS > model PoS (bullish)
    if row.calibrated_pos_delta is not None and row.calibrated_pos_delta > 0:
        cal_score = min(1.0, row.calibrated_pos_delta / 20.0)  # 20pp = full score
    else:
        cal_score = 0.0

    # Expert note component
    note_count_score = min(1.0, row.expert_note_count / _MAX_NOTES)
    sig_type_score = len(row.expert_signal_types) / 3.0    # 3 types = full score
    expert_score = (note_count_score + sig_type_score) / 2

    # Event component
    event_score = 0.0
    if row.requires_recompute:
        event_score += 0.6
    if row.recent_event_count > 0:
        event_score += min(0.4, row.recent_event_count * 0.2)
    event_score = min(1.0, event_score)

    return (
        _SPREAD_WEIGHT * spread_score
        + _CALIBRATION_WEIGHT * cal_score
        + _EXPERT_WEIGHT * expert_score
        + _EVENT_WEIGHT * event_score
    )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_daily_brief(
    store: "KnowledgeStore",
    universe: list[dict],
    *,
    as_of: Optional[date] = None,
    fetch_live: bool = True,
    expert_note_days: int = 30,
    event_days: int = 7,
    params_path: Optional[Path] = None,
) -> DailyBrief:
    """
    Build the daily opportunity brief.

    Parameters
    ----------
    store:
        KnowledgeStore (for calibration data, expert notes, events).
    universe:
        List of universe entry dicts (from UNIVERSE in weekly_runner.py).
    as_of:
        Override the "today" date for time-frozen analysis. Default: date.today().
    fetch_live:
        Whether to fetch live market data from yfinance. Set False for tests.
    expert_note_days:
        Look-back window for expert notes (days).
    event_days:
        Look-back window for detected events (days).

    Returns
    -------
    DailyBrief
    """
    from datetime import timedelta

    from bve.analysis.implied_pos_batch import run_screen
    from bve.intelligence.expert_notes import _ensure_schema
    from bve.models.pos_calibrated import CalibratedPOSModel

    as_of = as_of or date.today()
    generated_at = datetime.now(timezone.utc)

    # Step 1: Run universe screen (implied PoS spread)
    screen_rows = run_screen(universe, params_path=params_path, fetch_live=fetch_live)

    # Step 2: Build CalibratedPOSModel from KnowledgeStore
    try:
        cal_model = CalibratedPOSModel.from_store(getattr(store, "db_path", None))
        cal_stats = CalibrationStats(
            n_outcomes=cal_model.n_outcomes,
            n_bins_calibrated=cal_model.n_bins_calibrated,
            is_live=True,
        )
    except Exception:
        cal_model = None
        cal_stats = CalibrationStats(is_live=False)

    # Step 3: Load expert notes (last N days)
    _ensure_schema(store)
    cutoff_notes = (as_of - timedelta(days=expert_note_days)).isoformat()
    all_notes = _query_notes_since(store, cutoff_notes)

    # Step 4: Load detected events (last N days)
    cutoff_events = (as_of - timedelta(days=event_days)).isoformat()
    all_events = _query_events_since(store, cutoff_events)

    # Step 5: Build per-ticker lookups
    notes_by_ticker: dict[str, list[dict]] = {}
    for note in all_notes:
        notes_by_ticker.setdefault(note["ticker"].upper(), []).append(note)

    events_by_ticker: dict[str, list[dict]] = {}
    for evt in all_events:
        events_by_ticker.setdefault(evt["ticker"].upper(), []).append(evt)

    # Step 6: Assemble BriefRows
    brief_rows: list[BriefRow] = []
    n_with_spread = 0

    for sr in screen_rows:
        ticker = sr.ticker.upper()

        # Calibrated PoS
        cal_rate: Optional[float] = None
        cal_delta: Optional[float] = None
        if cal_model is not None:
            # Look up ta + phase from universe entry
            entry = _find_universe_entry(ticker, universe)
            if entry:
                ta = entry.get("ta", "other").lower()
                phase = entry.get("stage", "phase_2").lower()
                cal_rate = cal_model.base_rate(ta, phase)
                if cal_rate is not None and sr.model_pos:
                    cal_delta = round((cal_rate - sr.model_pos) * 100, 1)

        # Expert notes
        ticker_notes = notes_by_ticker.get(ticker, [])
        signal_types: set[str] = set()
        import json as _json
        for note in ticker_notes:
            try:
                sigs = _json.loads(note.get("signals_json") or "[]")
                for s in sigs:
                    signal_types.add(s.get("signal_type", ""))
            except Exception:
                pass

        # Events
        ticker_events = events_by_ticker.get(ticker, [])
        requires_recompute = any(e.get("requires_recompute") for e in ticker_events)

        if sr.spread_pp is not None:
            n_with_spread += 1

        row = BriefRow(
            ticker=ticker,
            program_label=sr.program_label,
            stage=sr.stage,
            ta=sr.ta,
            model_pos=sr.model_pos,
            implied_pos=sr.implied_pos,
            spread_pp=sr.spread_pp,
            rnpv_millions=sr.rnpv_millions,
            ev_millions=sr.ev_millions,
            calibrated_base_rate=round(cal_rate, 4) if cal_rate is not None else None,
            calibrated_pos_delta=cal_delta,
            next_catalyst=sr.next_catalyst,
            days_to_catalyst=sr.days_to_catalyst,
            expert_note_count=len(ticker_notes),
            expert_signal_types=signal_types,
            recent_event_count=len(ticker_events),
            requires_recompute=requires_recompute,
        )
        row.composite_score = round(_score_row(row), 4)
        brief_rows.append(row)

    brief_rows.sort(key=lambda r: r.composite_score, reverse=True)

    return DailyBrief(
        as_of=as_of,
        generated_at=generated_at,
        rows=brief_rows,
        calibration=cal_stats,
        n_universe=len(screen_rows),
        n_with_spread=n_with_spread,
        n_expert_notes=len(all_notes),
        n_recent_events=len(all_events),
        n_requires_recompute=sum(1 for r in brief_rows if r.requires_recompute),
    )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render_brief(brief: DailyBrief, top_n: int = 10) -> str:
    """
    Render a DailyBrief to a markdown-compatible text string.

    Parameters
    ----------
    brief:
        The assembled daily brief.
    top_n:
        Number of top-ranked opportunities to show.

    Returns
    -------
    str
        Formatted markdown text.
    """
    lines: list[str] = []

    lines.append(f"# Daily Opportunity Brief — {brief.as_of.isoformat()}")
    lines.append(f"Generated: {brief.generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    # Summary stats
    lines.append("## Summary")
    lines.append(f"- Universe screened: {brief.n_universe} names")
    lines.append(f"- Names with valid spread: {brief.n_with_spread}")
    lines.append(f"- Expert notes (last 30d): {brief.n_expert_notes}")
    lines.append(f"- Detected events (last 7d): {brief.n_recent_events}")
    lines.append(f"- Require recompute: {brief.n_requires_recompute}")

    cal = brief.calibration
    if cal.is_live:
        lines.append(
            f"- Calibration model: {cal.n_outcomes} outcomes, "
            f"{cal.n_bins_calibrated} calibrated bins"
        )
    else:
        lines.append("- Calibration model: fallback (no live outcomes)")
    lines.append("")

    # Top opportunities table
    lines.append(f"## Top {top_n} Opportunities")
    header = (
        f"{'TICKER':<7} {'SPREAD':>7} {'MODEL':>7} {'CAL_Δ':>7} "
        f"{'STAGE':<10} {'SIGNALS':<10} {'D2CAT':>6} {'SCORE':>7}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for row in brief.rows[:top_n]:
        spread_str = row.spread_label if row.spread_pp is not None else "n/a"
        model_str = f"{row.model_pos:.0%}"
        cal_delta_str = (
            f"{row.calibrated_pos_delta:+.1f}pp"
            if row.calibrated_pos_delta is not None
            else "—"
        )
        d2cat_str = str(row.days_to_catalyst) if row.days_to_catalyst is not None else "—"
        recompute_flag = "⚡" if row.requires_recompute else " "
        lines.append(
            f"{row.ticker:<7} {spread_str:>7} {model_str:>7} {cal_delta_str:>7} "
            f"{row.stage:<10} {row.signal_flags:<10} {d2cat_str:>6} "
            f"{row.composite_score:>6.3f}{recompute_flag}"
        )

    lines.append("")

    # Expert note summary (tickers with notes)
    noted_tickers = [r for r in brief.rows if r.expert_note_count > 0]
    if noted_tickers:
        lines.append("## Expert Note Signals")
        for r in noted_tickers[:5]:
            lines.append(
                f"- {r.ticker}: {r.expert_note_count} note(s) "
                f"[signals: {r.signal_flags}]"
            )
        lines.append("")

    # Recompute candidates
    recompute = [r for r in brief.rows if r.requires_recompute]
    if recompute:
        lines.append("## ⚡ Requires Recompute")
        for r in recompute:
            lines.append(
                f"- {r.ticker}: {r.recent_event_count} event(s) flagged"
            )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_universe_entry(ticker: str, universe: list[dict]) -> Optional[dict]:
    for entry in universe:
        if entry.get("ticker", "").upper() == ticker.upper():
            return entry
    return None


def _query_notes_since(store: "KnowledgeStore", cutoff_iso: str) -> list[dict]:
    """Pull expert notes at or after cutoff_iso (YYYY-MM-DD)."""
    try:
        cur = store._conn.execute(
            "SELECT * FROM expert_notes WHERE noted_at >= ? ORDER BY noted_at DESC",
            (cutoff_iso,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception:
        return []


def _query_events_since(store: "KnowledgeStore", cutoff_iso: str) -> list[dict]:
    """Pull detected events at or after cutoff_iso (YYYY-MM-DD)."""
    try:
        cur = store._conn.execute(
            "SELECT * FROM detected_events WHERE detected_date >= ? ORDER BY detected_date DESC",
            (cutoff_iso,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception:
        return []
