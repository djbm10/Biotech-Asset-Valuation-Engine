"""Block 16 — Catalyst Edge Calendar.

Combines model POS, market-implied POS, upcoming catalyst events, and binary
event volatility to produce a ranked ``CatalystEdgeRecord`` list — the
"catalyst edge screen" that surfaces where BVE's model disagrees with the
market ahead of a near-term binary event.

Output fields per record
------------------------
ticker, asset_name, event_type, expected_date, days_to_event
model_pos, market_implied_pos, pos_gap
market_cap_millions, ev_millions
expected_move_proxy   — median absolute move % (historical prior, not options)
edge_score            — POS_gap × event_materiality × confidence_weight × timing_weight
confidence            — "high" | "medium" | "low" | "insufficient_data"
staleness_warnings    — list of data quality issues

Edge score formula
------------------
    edge_score = clip(pos_gap, 0, 1)
               × event_materiality(event_type)
               × confidence_weight(model_age, has_implied_pos)
               × timing_weight(days_to_event)

Design notes
------------
- All data loaders are wrapped in try/except; never raises.
- ``market_fetcher`` is injectable so tests run offline.
- ``skip_market_refresh=True`` suppresses live fetch (for morning screen / batch).
- POS gap is only positive (model > market); negative gaps are clipped to 0.
- Confidence is classified by how many of the three key inputs are present.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

#: Materiality of each CatalystType relative to a full approval event (1.0).
_EVENT_MATERIALITY: dict[str, float] = {
    "pdufa_decision":       1.00,
    "adcom_meeting":        0.85,
    "trial_readout":        0.70,
    "conference_abstract":  0.35,
    "enrollment_complete":  0.20,
    "competitor_readout":   0.15,
}
_DEFAULT_MATERIALITY: float = 0.40

#: Median absolute move (%) by event type and market-cap bucket.
#: Source: published event-study medians (BioPharmaCatalyst, BioPharma Dive,
#: Evaluate Pharma).  Explicit priors — not statistically calibrated.
_EXPECTED_MOVE_PCT: dict[str, dict[str, float]] = {
    "pdufa_decision":       {"large": 0.18, "mid": 0.28, "small": 0.45},
    "adcom_meeting":        {"large": 0.15, "mid": 0.22, "small": 0.38},
    "trial_readout":        {"large": 0.15, "mid": 0.28, "small": 0.50},
    "enrollment_complete":  {"large": 0.03, "mid": 0.05, "small": 0.08},
    "conference_abstract":  {"large": 0.10, "mid": 0.18, "small": 0.30},
    "competitor_readout":   {"large": 0.05, "mid": 0.08, "small": 0.15},
}
_DEFAULT_MOVE: dict[str, float] = {"large": 0.08, "mid": 0.12, "small": 0.20}


# ---------------------------------------------------------------------------
# Formula component functions (pure — no I/O)
# ---------------------------------------------------------------------------

def _timing_weight(days_to_event: int) -> float:
    """Return timing weight for the edge score formula.

    Peaks at 14–60 days: ideal action window.
    Below 14 days: too close to act with conviction → reduced weight.
    Above 120 days: too distant to maintain high conviction → low weight.
    """
    if days_to_event < 0:
        return 0.0
    if days_to_event < 14:
        return 0.7
    if days_to_event <= 60:
        return 1.0
    if days_to_event <= 120:
        return 0.5
    return 0.3


def _event_materiality(event_type: str) -> float:
    """Return materiality weight for *event_type*."""
    return _EVENT_MATERIALITY.get(event_type, _DEFAULT_MATERIALITY)


def _confidence_weight(
    model_pos_age_days: Optional[int],
    has_implied_pos: bool,
) -> float:
    """Return confidence weight penalising stale model POS and missing implied POS."""
    base = 1.0 if has_implied_pos else 0.4
    if model_pos_age_days is None:
        return round(base * 0.7, 4)
    if model_pos_age_days > 180:
        return round(base * 0.5, 4)
    if model_pos_age_days > 90:
        return round(base * 0.7, 4)
    return round(base, 4)


def _cap_bucket(market_cap_millions: Optional[float]) -> str:
    """Return market-cap bucket: 'large' ≥$5B, 'mid' $500M–$5B, 'small' <$500M."""
    if market_cap_millions is None:
        return "mid"
    if market_cap_millions >= 5_000:
        return "large"
    if market_cap_millions >= 500:
        return "mid"
    return "small"


def _expected_move_proxy(
    event_type: str,
    market_cap_millions: Optional[float],
) -> float:
    """Return the expected absolute move % for *event_type* at this cap level."""
    tbl = _EXPECTED_MOVE_PCT.get(event_type, _DEFAULT_MOVE)
    return tbl[_cap_bucket(market_cap_millions)]


def _compute_implied_pos(
    market_cap: Optional[float],
    net_cash: Optional[float],
    gross_revenue_pv: Optional[float],
    trial_costs_pv: Optional[float],
) -> Optional[float]:
    """Back-solve market-implied POS from market cap and valuation PV components.

    Formula: P_implied = (implied_EV + trial_costs_pv) / gross_revenue_pv
    where implied_EV = market_cap − net_cash.

    Returns None when any input is missing or gross_revenue_pv ≤ 0.
    Negative implied POS (deep discount) returns None.
    """
    if None in (market_cap, net_cash, gross_revenue_pv, trial_costs_pv):
        return None
    if gross_revenue_pv <= 0:
        return None
    implied_ev = market_cap - net_cash  # type: ignore[operator]
    raw = (implied_ev + trial_costs_pv) / gross_revenue_pv  # type: ignore[operator]
    if raw < 0:
        return None
    return round(min(1.0, raw), 4)


def _compute_edge_score(
    pos_gap: Optional[float],
    event_materiality_val: float,
    confidence_weight_val: float,
    timing_weight_val: float,
) -> Optional[float]:
    """Compute edge_score ∈ [0, 1].

    Only positive POS gaps count (model > market).  Negative gaps are clipped
    to 0, so the score is also 0 — a non-recommendation, not an error.
    Returns None only when pos_gap itself is unavailable.
    """
    if pos_gap is None:
        return None
    clipped = max(0.0, min(1.0, pos_gap))
    raw = clipped * event_materiality_val * confidence_weight_val * timing_weight_val
    return round(min(1.0, raw), 4)


# ---------------------------------------------------------------------------
# CatalystEdgeRecord — output row
# ---------------------------------------------------------------------------

@dataclass
class CatalystEdgeRecord:
    """One row of the catalyst edge calendar screen.

    All numeric fields are ``None`` when data is unavailable.
    ``edge_score`` is None when market-implied POS cannot be computed.
    """

    ticker: str
    asset_name: str
    event_type: str           # CatalystType.value string or "unknown"
    expected_date: Optional[date]
    days_to_event: Optional[int]
    model_pos: Optional[float]
    market_implied_pos: Optional[float]
    pos_gap: Optional[float]  # model_pos − market_implied_pos; positive = undervalued
    market_cap_millions: Optional[float]
    ev_millions: Optional[float]
    expected_move_proxy: Optional[float]   # median absolute move % (not options-derived)
    edge_score: Optional[float]            # ∈ [0, 1]; None when data insufficient
    confidence: str                        # "high"|"medium"|"low"|"insufficient_data"
    staleness_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "asset_name": self.asset_name,
            "event_type": self.event_type,
            "expected_date": self.expected_date.isoformat() if self.expected_date else None,
            "days_to_event": self.days_to_event,
            "model_pos": self.model_pos,
            "market_implied_pos": self.market_implied_pos,
            "pos_gap": self.pos_gap,
            "market_cap_millions": self.market_cap_millions,
            "ev_millions": self.ev_millions,
            "expected_move_proxy": self.expected_move_proxy,
            "edge_score": self.edge_score,
            "confidence": self.confidence,
            "staleness_warnings": self.staleness_warnings,
        }


# ---------------------------------------------------------------------------
# Private data helpers (graceful — never raise)
# ---------------------------------------------------------------------------

def _load_valuation_data(ticker: str, outputs_dir: Path) -> dict:
    """Load ``outputs/<TICKER>/valuation.json`` as a dict. Returns {} on failure."""
    try:
        path = outputs_dir / ticker.upper() / "valuation.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_model_pos(val_data: dict) -> Optional[float]:
    """Extract model P(approval) from the valuation JSON dict."""
    # Top-level key set by ValuationOutput.summary_dict (line 394 of outputs.py)
    v = val_data.get("model_pos")
    if v is not None:
        return float(v)
    # Fallback: nested rnpv block from the full export
    rnpv = val_data.get("rnpv", {})
    v2 = rnpv.get("cumulative_success_probability")
    return float(v2) if v2 is not None else None


def _get_rnpv_pvs(val_data: dict) -> tuple[Optional[float], Optional[float]]:
    """Return ``(gross_revenue_pv, trial_costs_pv)`` from valuation JSON."""
    rnpv = val_data.get("rnpv", {})
    gross = rnpv.get("gross_revenue_pv_millions")
    costs = rnpv.get("trial_costs_pv_millions")
    return (
        float(gross) if gross is not None else None,
        float(costs) if costs is not None else None,
    )


def _load_catalyst_events_for_ticker(
    ticker: str,
    ops_db: Path,
    max_days_forward: int,
) -> list:
    """Return active catalyst events for *ticker* from the KnowledgeStore."""
    try:
        if not ops_db.exists():
            return []
        from bve.intelligence.knowledge_layer import KnowledgeStore
        from bve.ops.weekly_runner import UNIVERSE

        # Resolve asset_id from UNIVERSE first
        asset_ids: list[str] = [
            a["asset_id"]
            for a in UNIVERSE
            if a.get("ticker", "").upper() == ticker.upper()
        ]
        if not asset_ids:
            asset_ids = [ticker.lower() + "_lead"]

        ks = KnowledgeStore(str(ops_db))
        events: list = []
        for aid in asset_ids:
            events.extend(
                ks.get_catalyst_events(
                    asset_id=aid,
                    active_only=True,
                    days_ahead=max_days_forward,
                )
            )
        return events
    except Exception:
        return []


def _classify_confidence(
    model_pos: Optional[float],
    implied_pos: Optional[float],
    market_cap: Optional[float],
) -> str:
    """Classify confidence based on how many key inputs are present."""
    missing = sum(x is None for x in [model_pos, implied_pos, market_cap])
    if missing == 0:
        return "high"
    if missing == 1:
        return "medium"
    if missing == 2:
        return "low"
    return "insufficient_data"


# ---------------------------------------------------------------------------
# CatalystEdgeCalendar — orchestrator
# ---------------------------------------------------------------------------

class CatalystEdgeCalendar:
    """Build a ranked catalyst edge calendar across the tracked universe.

    Parameters
    ----------
    ops_db:
        Path to the intelligence ops SQLite (KnowledgeStore).
    outputs_dir:
        Root outputs directory (``outputs/``).
    market_fetcher:
        Optional injectable fetcher ``(ticker: str) -> dict`` for testing without
        network access.  Passed through to ``fetch_market_snapshot``.
    max_days_forward:
        Only include catalyst events within this many calendar days.
    skip_market_refresh:
        When True, skip the live market/financial data fetch entirely.
        ``market_cap_millions`` and ``ev_millions`` will be None.
        Use in the morning screen and batch contexts to avoid slow network calls.
    """

    def __init__(
        self,
        ops_db: Path,
        outputs_dir: Path,
        *,
        market_fetcher: Optional[Callable] = None,
        max_days_forward: int = 180,
        skip_market_refresh: bool = False,
    ) -> None:
        self._ops_db = ops_db
        self._outputs_dir = outputs_dir
        self._market_fetcher = market_fetcher
        self._max_days = max_days_forward
        self._skip_refresh = skip_market_refresh

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, tickers: Optional[list[str]] = None) -> list[CatalystEdgeRecord]:
        """Build ranked catalyst edge records.

        Parameters
        ----------
        tickers:
            Tickers to include.  Defaults to the tracked UNIVERSE.

        Returns
        -------
        list[CatalystEdgeRecord]
            Sorted by edge_score descending (None last), then days_to_event ascending.
        """
        if tickers is None:
            tickers = self._universe_tickers()

        today = date.today()
        records: list[CatalystEdgeRecord] = []

        for raw_ticker in tickers:
            ticker = raw_ticker.upper()
            try:
                recs = self._build_ticker_records(ticker, today)
                records.extend(recs)
            except Exception:
                continue

        records.sort(
            key=lambda r: (
                -(r.edge_score if r.edge_score is not None else -1.0),
                r.days_to_event if r.days_to_event is not None else 9999,
            )
        )
        return records

    def render_markdown(self, records: list[CatalystEdgeRecord]) -> str:
        """Render *records* as a Markdown table, best edge first."""
        if not records:
            return "\n".join([
                "## Catalyst Edge Opportunities",
                "",
                "_No catalyst edge data available. Seed catalysts with `bve-seed-catalysts`._",
                "",
            ])

        lines = [
            "## Catalyst Edge Opportunities",
            "",
            "| Ticker | Event | Date | Days | Model P | Mkt P | Gap | Mkt Cap $M"
            " | Move% | Edge | Conf |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in records:
            def _p(v: Optional[float]) -> str:
                return f"{v:.1%}" if v is not None else "—"

            def _f(v: Optional[float], fmt: str = ".0f") -> str:
                return f"{v:{fmt}}" if v is not None else "—"

            gap_raw = r.pos_gap
            if gap_raw is None:
                gap_s = "—"
            elif gap_raw > 0:
                gap_s = f"+{gap_raw:.1%}"
            else:
                gap_s = f"{gap_raw:.1%}"

            lines.append(
                f"| {r.ticker} | {r.event_type[:22]} | {r.expected_date or '—'}"
                f" | {r.days_to_event or '—'}"
                f" | {_p(r.model_pos)} | {_p(r.market_implied_pos)} | {gap_s}"
                f" | {_f(r.market_cap_millions)} | {_f(r.expected_move_proxy, '.0%')}"
                f" | {_f(r.edge_score, '.3f')} | {r.confidence} |"
            )
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_ticker_records(
        self, ticker: str, today: date
    ) -> list[CatalystEdgeRecord]:
        events = _load_catalyst_events_for_ticker(ticker, self._ops_db, self._max_days)
        val_data = _load_valuation_data(ticker, self._outputs_dir)
        market_snap, fin_snap = self._fetch_market_data(ticker)

        model_pos = _get_model_pos(val_data)
        gross_pv, costs_pv = _get_rnpv_pvs(val_data)

        market_cap: Optional[float] = (
            getattr(market_snap, "market_cap_millions", None) if market_snap else None
        )
        net_cash: Optional[float] = (
            getattr(fin_snap, "net_cash_millions", None) if fin_snap else None
        )

        implied_pos = _compute_implied_pos(market_cap, net_cash, gross_pv, costs_pv)

        stale: list[str] = []
        if market_snap and getattr(market_snap, "staleness_warning", None):
            stale.append(market_snap.staleness_warning)
        if fin_snap and getattr(fin_snap, "staleness_warning", None):
            stale.append(fin_snap.staleness_warning)
        if not val_data:
            stale.append(f"{ticker}: no valuation output — run bve-asset first")

        if not events:
            if val_data and model_pos is not None:
                return [self._no_catalyst_record(
                    ticker, val_data, model_pos, implied_pos,
                    market_cap, net_cash, stale,
                )]
            return []

        return [
            self._event_record(
                ticker, ev, val_data, model_pos, implied_pos,
                market_cap, net_cash, stale, today,
            )
            for ev in events
        ]

    def _event_record(
        self, ticker, event, val_data, model_pos, implied_pos,
        market_cap, net_cash, stale, today,
    ) -> CatalystEdgeRecord:
        event_type = (
            event.catalyst_type.value
            if hasattr(event.catalyst_type, "value")
            else str(event.catalyst_type)
        )
        expected_date: Optional[date] = getattr(event, "expected_date", None)
        days = (expected_date - today).days if expected_date else None

        pos_gap = (
            round(model_pos - implied_pos, 4)
            if model_pos is not None and implied_pos is not None
            else None
        )

        mat = _event_materiality(event_type)
        timing_w = _timing_weight(days if days is not None else 9999)
        conf_w = _confidence_weight(None, implied_pos is not None)

        edge = _compute_edge_score(pos_gap, mat, conf_w, timing_w)
        confidence = _classify_confidence(model_pos, implied_pos, market_cap)
        move_proxy = _expected_move_proxy(event_type, market_cap)
        ev = (market_cap - net_cash) if market_cap is not None and net_cash is not None else None
        asset_name = str(val_data.get("asset_name") or ticker)

        return CatalystEdgeRecord(
            ticker=ticker,
            asset_name=asset_name,
            event_type=event_type,
            expected_date=expected_date,
            days_to_event=days,
            model_pos=model_pos,
            market_implied_pos=implied_pos,
            pos_gap=pos_gap,
            market_cap_millions=market_cap,
            ev_millions=ev,
            expected_move_proxy=move_proxy,
            edge_score=edge,
            confidence=confidence,
            staleness_warnings=stale[:],
        )

    def _no_catalyst_record(
        self, ticker, val_data, model_pos, implied_pos,
        market_cap, net_cash, stale,
    ) -> CatalystEdgeRecord:
        ev = (market_cap - net_cash) if market_cap is not None and net_cash is not None else None
        pos_gap = (
            round(model_pos - implied_pos, 4)
            if model_pos is not None and implied_pos is not None
            else None
        )
        asset_name = str(val_data.get("asset_name") or ticker)
        return CatalystEdgeRecord(
            ticker=ticker,
            asset_name=asset_name,
            event_type="unknown",
            expected_date=None,
            days_to_event=None,
            model_pos=model_pos,
            market_implied_pos=implied_pos,
            pos_gap=pos_gap,
            market_cap_millions=market_cap,
            ev_millions=ev,
            expected_move_proxy=None,
            edge_score=None,
            confidence="insufficient_data",
            staleness_warnings=stale + ["No catalyst events seeded — use bve-seed-catalysts"],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fetch_market_data(self, ticker: str):
        """Return ``(MarketDataSnapshot, FinancialSnapshot)``, both None on failure."""
        if self._skip_refresh:
            return None, None
        try:
            from bve.refresh.financial_refresh import fetch_financial_snapshot
            from bve.refresh.market_data_refresh import fetch_market_snapshot

            mds = fetch_market_snapshot(ticker, fetcher=self._market_fetcher)
            fin = fetch_financial_snapshot(ticker)
            return mds, fin
        except Exception:
            return None, None

    def _universe_tickers(self) -> list[str]:
        """Return tickers from UNIVERSE; graceful empty list on import failure."""
        try:
            from bve.ops.weekly_runner import UNIVERSE

            return [a["ticker"] for a in UNIVERSE if a.get("ticker")]
        except Exception:
            return []
