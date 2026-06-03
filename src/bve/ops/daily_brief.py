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
    from bve.analysis.implied_pos_batch import ScreenRow


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
    company_ranked_discount: Optional[float] = None
    company_action_policy: Optional[str] = None
    company_action_reason: Optional[str] = None
    company_snapshot_date: Optional[date] = None
    equity_policy_action: Optional[str] = None
    equity_policy_size_pct: Optional[float] = None
    equity_policy_rationale: Optional[str] = None
    equity_policy_current_price: Optional[float] = None
    equity_policy_base_sotp_per_share: Optional[float] = None
    equity_policy_bear_sotp_per_share: Optional[float] = None
    equity_policy_bull_sotp_per_share: Optional[float] = None
    equity_policy_conviction: Optional[float] = None
    equity_policy_adv_millions: Optional[float] = None
    equity_policy_next_catalyst_days: Optional[int] = None
    equity_policy_catalyst_description: Optional[str] = None

    @property
    def spread_label(self) -> str:
        if self.spread_pp is None:
            return "n/a"
        return f"{self.spread_pp:+.1f}pp"

    @property
    def company_discount_label(self) -> str:
        if self.company_ranked_discount is None:
            return "n/a"
        return f"{self.company_ranked_discount:.2f}x"

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
    source_mode: str = "live_recomputed"
    reference_snapshot_date: Optional[date] = None


@dataclass
class EquityPolicyPreview:
    ticker: str
    action: str
    sizing_pct: float
    rationale: str
    source_mode: str = "heuristic_company_snapshot"
    company_action_policy: Optional[str] = None
    company_action_reason: Optional[str] = None
    company_ranked_discount: Optional[float] = None
    company_snapshot_date: Optional[date] = None
    current_price: Optional[float] = None
    base_sotp_per_share: Optional[float] = None
    bear_sotp_per_share: Optional[float] = None
    bull_sotp_per_share: Optional[float] = None
    conviction: Optional[float] = None
    adv_millions: Optional[float] = None
    next_catalyst_days: Optional[int] = None
    catalyst_description: Optional[str] = None


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
    if row.company_ranked_discount is not None and row.company_ranked_discount > 1.0:
        company_discount_score = min(1.0, (row.company_ranked_discount - 1.0) / 1.5)
        spread_score = max(spread_score, company_discount_score)

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
    persist_policy_snapshots: bool = False,
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

    # Step 1: Prefer persisted company SOTP snapshots for company-facing ranking.
    company_reference_date, company_rows = _load_company_rows_from_store(
        store,
        as_of=as_of,
        universe=universe,
    )
    source_mode = "stored_company_snapshot"
    reference_snapshot_date = company_reference_date

    if company_rows:
        screen_rows = _build_screen_context_for_company_rows(
            store,
            company_rows=company_rows,
            as_of=company_reference_date or as_of,
        )
    else:
        # Step 1b: Fall back to persisted asset-level screen snapshots.
        screen_rows = _load_screen_rows_from_store(store, as_of=as_of)
        if screen_rows:
            source_mode = "stored_screen_snapshot"
            reference_snapshot_date = screen_rows[0].data_date

    if not screen_rows and not company_rows:
        screen_rows = run_screen(
            universe,
            params_path=params_path,
            fetch_live=fetch_live,
            as_of=as_of,
        )
        source_mode = "live_recomputed"
        reference_snapshot_date = as_of

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
    company_by_ticker = {
        str(row.get("ticker") or "").upper(): row
        for row in company_rows
    }

    for sr in screen_rows:
        ticker = sr.ticker.upper()
        company_snapshot = company_by_ticker.get(ticker)

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
            company_ranked_discount=(
                float(company_snapshot["ranked_sotp_discount"])
                if company_snapshot is not None
                and company_snapshot.get("ranked_sotp_discount") is not None
                else None
            ),
            company_action_policy=(
                str(company_snapshot.get("action_policy"))
                if company_snapshot is not None and company_snapshot.get("action_policy")
                else None
            ),
            company_action_reason=(
                str(company_snapshot.get("action_reason"))
                if company_snapshot is not None and company_snapshot.get("action_reason")
                else None
            ),
            company_snapshot_date=(
                company_snapshot.get("snapshot_date")
                if company_snapshot is not None
                else None
            ),
        )
        policy_preview = _build_equity_policy_preview(
            store,
            company_snapshot=company_snapshot,
            brief_row=row,
            as_of=reference_snapshot_date or as_of,
        )
        if policy_preview is not None:
            row.equity_policy_action = policy_preview.action
            row.equity_policy_size_pct = round(policy_preview.sizing_pct, 2)
            row.equity_policy_rationale = policy_preview.rationale
            row.equity_policy_current_price = policy_preview.current_price
            row.equity_policy_base_sotp_per_share = policy_preview.base_sotp_per_share
            row.equity_policy_bear_sotp_per_share = policy_preview.bear_sotp_per_share
            row.equity_policy_bull_sotp_per_share = policy_preview.bull_sotp_per_share
            row.equity_policy_conviction = policy_preview.conviction
            row.equity_policy_adv_millions = policy_preview.adv_millions
            row.equity_policy_next_catalyst_days = policy_preview.next_catalyst_days
            row.equity_policy_catalyst_description = policy_preview.catalyst_description
        row.composite_score = round(_score_row(row), 4)
        brief_rows.append(row)

    brief_rows.sort(key=lambda r: r.composite_score, reverse=True)

    if persist_policy_snapshots:
        _persist_equity_policy_snapshots(
            store,
            rows=brief_rows,
            as_of=as_of,
            reference_snapshot_date=reference_snapshot_date,
        )

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
        source_mode=source_mode,
        reference_snapshot_date=reference_snapshot_date,
    )


def _load_company_rows_from_store(
    store: "KnowledgeStore",
    *,
    as_of: date,
    universe: list[dict],
) -> tuple[Optional[date], list[dict]]:
    try:
        snapshot_date, raw_rows = store.get_company_sotp_snapshots_on_or_before(as_of, limit=1000)
    except Exception:
        return None, []
    if snapshot_date is None or not raw_rows:
        return None, []

    allowed_tickers = {
        str(entry.get("ticker") or "").upper()
        for entry in universe
        if entry.get("ticker")
    }
    filtered = [
        row
        for row in raw_rows
        if str(row.get("ticker") or "").upper() in allowed_tickers
        and bool(row.get("balance_sheet_passes_recency_gate", False))
    ]
    filtered.sort(
        key=lambda row: (-float(row.get("ranked_sotp_discount") or 0.0), str(row.get("ticker") or ""))
    )
    return snapshot_date, filtered


def _build_screen_context_for_company_rows(
    store: "KnowledgeStore",
    *,
    company_rows: list[dict],
    as_of: date,
) -> list["ScreenRow"]:
    screen_rows: list["ScreenRow"] = []
    for company_row in company_rows:
        snapshot = _best_asset_snapshot_for_company(store, company_row=company_row, as_of=as_of)
        if snapshot is not None:
            data_date = date.fromisoformat(snapshot["snapshot_date"])
            screen_rows.append(_screen_row_from_snapshot_dict(snapshot, data_date=data_date))
            continue

        ticker = str(company_row.get("ticker") or "")
        screen_rows.append(
            _company_snapshot_to_screen_row(company_row, data_date=as_of, ticker=ticker)
        )
    return screen_rows


def _best_asset_snapshot_for_company(
    store: "KnowledgeStore",
    *,
    company_row: dict,
    as_of: date,
) -> Optional[dict]:
    best: Optional[dict] = None
    for asset_id in company_row.get("modeled_asset_ids", []) or []:
        candidate = store.get_screen_snapshot_for_asset_on_or_before(asset_id=str(asset_id), as_of=as_of)
        if candidate is None:
            continue
        if best is None:
            best = candidate
            continue
        best_value = float(best.get("rnpv_millions") or 0.0)
        candidate_value = float(candidate.get("rnpv_millions") or 0.0)
        if candidate_value > best_value:
            best = candidate
    if best is not None:
        return best
    ticker = str(company_row.get("ticker") or "")
    if not ticker:
        return None
    return store.get_screen_snapshot_for_ticker_on_or_before(ticker=ticker, as_of=as_of)


def _company_snapshot_to_screen_row(
    row: dict,
    *,
    data_date: date,
    ticker: str,
) -> "ScreenRow":
    from bve.analysis.implied_pos_batch import ScreenRow

    company_name = str(row.get("company_name") or ticker)
    return ScreenRow(
        ticker=ticker,
        program_label=company_name,
        stage="company",
        ta="mixed",
        model_pos=0.0,
        implied_pos=None,
        spread_pp=None,
        rnpv_millions=float(row.get("sotp_equity_value_millions") or 0.0),
        ev_millions=float(row.get("enterprise_value_millions") or 0.0),
        acquisition_discount_pct=(
            round((float(row["ranked_sotp_discount"]) - 1.0) * 100.0, 4)
            if row.get("ranked_sotp_discount") is not None
            else None
        ),
        next_catalyst="",
        catalyst_date=None,
        days_to_catalyst=None,
        single_asset=False,
        approximation_warning="company_snapshot_without_asset_screen_context",
        thesis_strength=None,
        data_date=data_date,
        asset_id="",
        market_exceeds_model=False,
        config_quality=row.get("config_quality_summary"),
    )


def _load_screen_rows_from_store(
    store: "KnowledgeStore",
    *,
    as_of: date,
) -> list["ScreenRow"]:
    """Load the most recent screen snapshot on or before *as_of*."""
    try:
        snapshot_date, raw_rows = store.get_screen_snapshots_on_or_before(as_of, limit=1000)
    except Exception:
        return []
    if snapshot_date is None or not raw_rows:
        return []
    return [_screen_row_from_snapshot_dict(row, data_date=snapshot_date) for row in raw_rows]


def _build_equity_policy_preview(
    store: "KnowledgeStore",
    *,
    company_snapshot: Optional[dict],
    brief_row: BriefRow,
    as_of: date,
) -> Optional[EquityPolicyPreview]:
    from bve.intelligence.position_policy import PositionPolicyEngine, PositionPolicyInput

    if company_snapshot is None:
        return None

    ticker = brief_row.ticker.upper()
    current_price = _current_price_from_company_snapshot(company_snapshot)
    base_sotp = float(company_snapshot.get("sotp_per_share") or 0.0)
    if current_price <= 0 or base_sotp <= 0:
        return None

    company_gate = str(company_snapshot.get("action_policy") or "")
    if company_gate == "needs_manual_review":
        return EquityPolicyPreview(
            ticker=ticker,
            action="monitor",
            sizing_pct=0.0,
            rationale="Company SOTP governance gate requires manual review; policy preview suppressed.",
            company_action_policy=company_gate,
            company_action_reason=str(company_snapshot.get("action_reason") or "") or None,
            company_ranked_discount=(
                float(company_snapshot.get("ranked_sotp_discount"))
                if company_snapshot.get("ranked_sotp_discount") is not None
                else None
            ),
            company_snapshot_date=company_snapshot.get("snapshot_date"),
            current_price=current_price,
            base_sotp_per_share=base_sotp,
            next_catalyst_days=brief_row.days_to_catalyst,
            catalyst_description=brief_row.next_catalyst or "",
        )
    if company_gate == "avoid":
        return EquityPolicyPreview(
            ticker=ticker,
            action="avoid",
            sizing_pct=0.0,
            rationale="Company SOTP governance gate is avoid; equity policy preview blocked upstream.",
            company_action_policy=company_gate,
            company_action_reason=str(company_snapshot.get("action_reason") or "") or None,
            company_ranked_discount=(
                float(company_snapshot.get("ranked_sotp_discount"))
                if company_snapshot.get("ranked_sotp_discount") is not None
                else None
            ),
            company_snapshot_date=company_snapshot.get("snapshot_date"),
            current_price=current_price,
            base_sotp_per_share=base_sotp,
            next_catalyst_days=brief_row.days_to_catalyst,
            catalyst_description=brief_row.next_catalyst or "",
        )

    conviction = _heuristic_policy_conviction(company_snapshot, brief_row=brief_row)
    if company_gate == "watch":
        conviction = min(conviction, 0.54)

    adv_millions = _adv_millions(store, ticker=ticker, as_of=as_of) or 2.0
    bear_sotp = max(
        current_price * 0.55,
        base_sotp * (0.45 + 0.20 * conviction),
    )
    bull_sotp = max(base_sotp, base_sotp * (1.25 + 0.25 * conviction))

    policy = PositionPolicyEngine().evaluate(
        PositionPolicyInput(
            ticker=ticker,
            current_price=current_price,
            base_sotp_per_share=base_sotp,
            bear_sotp_per_share=bear_sotp,
            bull_sotp_per_share=bull_sotp,
            conviction=conviction,
            next_catalyst_days=brief_row.days_to_catalyst if brief_row.days_to_catalyst is not None else 365,
            adv_millions=adv_millions,
            catalyst_description=brief_row.next_catalyst or "",
        )
    )
    return EquityPolicyPreview(
        ticker=ticker,
        action=policy.action,
        sizing_pct=policy.sizing_pct,
        rationale="Heuristic preview from company snapshot + stored catalyst/liquidity context. "
        + policy.rationale,
        company_action_policy=company_gate or None,
        company_action_reason=str(company_snapshot.get("action_reason") or "") or None,
        company_ranked_discount=(
            float(company_snapshot.get("ranked_sotp_discount"))
            if company_snapshot.get("ranked_sotp_discount") is not None
            else None
        ),
        company_snapshot_date=company_snapshot.get("snapshot_date"),
        current_price=current_price,
        base_sotp_per_share=base_sotp,
        bear_sotp_per_share=bear_sotp,
        bull_sotp_per_share=bull_sotp,
        conviction=conviction,
        adv_millions=adv_millions,
        next_catalyst_days=brief_row.days_to_catalyst if brief_row.days_to_catalyst is not None else 365,
        catalyst_description=brief_row.next_catalyst or "",
    )


def _persist_equity_policy_snapshots(
    store: "KnowledgeStore",
    *,
    rows: list[BriefRow],
    as_of: date,
    reference_snapshot_date: Optional[date],
) -> int:
    from bve.intelligence.knowledge_layer import EquityPolicySnapshotRecord

    snapshots: list[EquityPolicySnapshotRecord] = []
    for row in rows:
        if row.equity_policy_action is None or row.equity_policy_rationale is None:
            continue
        snapshots.append(
            EquityPolicySnapshotRecord(
                ticker=row.ticker,
                as_of_date=as_of,
                reference_snapshot_date=reference_snapshot_date,
                company_snapshot_date=row.company_snapshot_date,
                source_mode="heuristic_company_snapshot",
                company_action_policy=row.company_action_policy,
                company_action_reason=row.company_action_reason,
                company_ranked_discount=row.company_ranked_discount,
                composite_score=row.composite_score,
                current_price=getattr(row, "equity_policy_current_price", None),
                base_sotp_per_share=getattr(row, "equity_policy_base_sotp_per_share", None),
                bear_sotp_per_share=getattr(row, "equity_policy_bear_sotp_per_share", None),
                bull_sotp_per_share=getattr(row, "equity_policy_bull_sotp_per_share", None),
                conviction=getattr(row, "equity_policy_conviction", None),
                adv_millions=getattr(row, "equity_policy_adv_millions", None),
                next_catalyst_days=getattr(row, "equity_policy_next_catalyst_days", None),
                catalyst_description=getattr(row, "equity_policy_catalyst_description", None),
                action=row.equity_policy_action,
                sizing_pct=row.equity_policy_size_pct or 0.0,
                rationale=row.equity_policy_rationale,
            )
        )
    return store.write_equity_policy_snapshots(snapshots)


def _current_price_from_company_snapshot(company_snapshot: dict) -> float:
    market_cap = float(company_snapshot.get("market_cap_millions") or 0.0)
    shares = float(company_snapshot.get("shares_outstanding_millions") or 0.0)
    if shares <= 0:
        sotp_equity = float(company_snapshot.get("sotp_equity_value_millions") or 0.0)
        sotp_per_share = float(company_snapshot.get("sotp_per_share") or 0.0)
        if sotp_equity > 0 and sotp_per_share > 0:
            shares = sotp_equity / sotp_per_share
    if market_cap <= 0 or shares <= 0:
        return 0.0
    return market_cap / shares


def _heuristic_policy_conviction(company_snapshot: dict, *, brief_row: BriefRow) -> float:
    confidence = float(
        company_snapshot.get("actionable_confidence_pct")
        or company_snapshot.get("modeled_asset_confidence_avg")
        or 0.50
    )
    discount = float(company_snapshot.get("ranked_sotp_discount") or 1.0)
    discount_signal = min(max((discount - 1.0) / 2.5, 0.0), 1.0)
    manual_share = min(max(float(company_snapshot.get("manual_bucket_share_pct") or 0.0), 0.0), 1.0)
    quality = str(company_snapshot.get("config_quality_summary") or "").strip().lower()
    quality_bonus = {
        "gold": 0.08,
        "curated": 0.04,
        "screening_grade": -0.10,
        "auto_generated": -0.15,
    }.get(quality, 0.0)
    catalyst_bonus = 0.05 if brief_row.days_to_catalyst is not None and brief_row.days_to_catalyst <= 90 else 0.0
    conviction = (
        confidence * 0.60
        + discount_signal * 0.25
        + catalyst_bonus
        + quality_bonus
        - manual_share * 0.20
    )
    return min(max(round(conviction, 6), 0.05), 0.95)


def _adv_millions(store: "KnowledgeStore", *, ticker: str, as_of: date) -> Optional[float]:
    try:
        price_row = store.get_price_on_or_before(ticker, as_of)
        avg_volume = store.get_20day_avg_volume(ticker, as_of)
    except Exception:
        return None
    if price_row is None or avg_volume is None or price_row.close_usd is None:
        return None
    return round(float(price_row.close_usd) * float(avg_volume) / 1_000_000.0, 6)


def _screen_row_from_snapshot_dict(row: dict, *, data_date: date) -> "ScreenRow":
    from bve.analysis.implied_pos_batch import ScreenRow

    return ScreenRow(
        ticker=row["ticker"],
        program_label=row.get("program_label") or row["ticker"],
        stage=row.get("stage") or "unknown",
        ta=row.get("ta") or "other",
        model_pos=row.get("model_pos") or 0.0,
        implied_pos=row.get("implied_pos"),
        spread_pp=row.get("spread_pp"),
        rnpv_millions=row.get("rnpv_millions") or 0.0,
        ev_millions=row.get("ev_millions"),
        acquisition_discount_pct=row.get("acquisition_discount_pct"),
        next_catalyst=row.get("next_catalyst") or "",
        catalyst_date=(
            date.fromisoformat(row["catalyst_date"]) if row.get("catalyst_date") else None
        ),
        days_to_catalyst=row.get("days_to_catalyst"),
        single_asset=bool(row.get("single_asset", True)),
        approximation_warning=row.get("approximation_warning"),
        thesis_strength=row.get("thesis_strength"),
        data_date=data_date,
        asset_id=str(row.get("asset_id") or ""),
        market_exceeds_model=bool(row.get("market_exceeds_model", False)),
        config_quality=row.get("config_quality"),
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
    lines.append("[MODE: SCREENING]  Heuristic-grade rankings. Equity policy preview is heuristic and not a deployment order.")
    lines.append(f"Generated: {brief.generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Source mode: {brief.source_mode}")
    if brief.reference_snapshot_date is not None:
        lines.append(f"Reference snapshot: {brief.reference_snapshot_date.isoformat()}")
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
        f"{'TICKER':<7} {'DISC':>7} {'SOTP':<8} {'EQPOL':<8} {'SIZE':>6} {'SPREAD':>7} "
        f"{'MODEL':>7} {'CAL_Δ':>7} {'STAGE':<10} {'SIGNALS':<10} {'D2CAT':>6} {'SCORE':>7}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for row in brief.rows[:top_n]:
        spread_str = row.spread_label if row.spread_pp is not None else "n/a"
        discount_str = row.company_discount_label
        model_str = f"{row.model_pos:.0%}"
        cal_delta_str = (
            f"{row.calibrated_pos_delta:+.1f}pp"
            if row.calibrated_pos_delta is not None
            else "—"
        )
        d2cat_str = str(row.days_to_catalyst) if row.days_to_catalyst is not None else "—"
        recompute_flag = "⚡" if row.requires_recompute else " "
        company_policy_str = row.company_action_policy or "—"
        equity_policy_str = row.equity_policy_action or "—"
        size_str = (
            f"{row.equity_policy_size_pct:.1f}%"
            if row.equity_policy_size_pct is not None
            else "—"
        )
        lines.append(
            f"{row.ticker:<7} {discount_str:>7} {company_policy_str:<8} {equity_policy_str:<8} "
            f"{size_str:>6} {spread_str:>7} {model_str:>7} {cal_delta_str:>7} "
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
