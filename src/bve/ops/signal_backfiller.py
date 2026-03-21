"""
Signal backfiller for historical replay v2.0.

Populates the replay store's v2.0 signal tables (catalyst_events,
capital_snapshots) with time-stamped historical data so the replay
loop has non-static, non-circular signals.

Three entry points:

    SignalBackfiller.backfill_capital_risk(universe)
        → capital_snapshots: quarterly EDGAR cash data per ticker

    SignalBackfiller.backfill_catalyst_signals(universe, start, end)
        → catalyst_events: time-varying proximity signals per (asset, step)

    SignalBackfiller.backfill_competitor_signals(competitor_map)
        → catalyst_events: COMPETITOR_READOUT rows from historical_events

Usage via CLI:
    python -m bve.ops.historical_replay seed-signals --backfill \\
        --start 2024-01-01 --end 2026-03-21
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bve.ops.historical_replay import ReplayStore

# ---------------------------------------------------------------------------
# Competitor peer map
# Gene editing: crsp / ntla / beam compete in same space
# Obesity / GLP-1 adjacent: vktx / mrna
# ---------------------------------------------------------------------------

COMPETITOR_MAP: dict[str, list[str]] = {
    "a-crsp": ["a-ntla", "a-beam"],
    "a-ntla": ["a-crsp", "a-beam"],
    "a-beam": ["a-crsp", "a-ntla"],
    "a-vktx": ["a-mrna"],
    "a-mrna": ["a-vktx"],
}

# Proximity signal base score — deliberately conservative and NOT derived from
# ranking_score or opportunity_score to avoid circularity in the composite.
_BASE_SCORE = 0.10

# Standard competitor event drag weight
_COMPETITOR_SIGNAL_STRENGTH = 0.30


class SignalBackfiller:
    """
    Populates replay store signal tables with historical time-series data.

    All inserts use INSERT OR REPLACE so re-runs are idempotent.
    """

    def __init__(self, replay_store: "ReplayStore") -> None:
        self._rs = replay_store

    # ------------------------------------------------------------------
    # 1. Capital risk — quarterly EDGAR cash snapshots
    # ------------------------------------------------------------------

    def backfill_capital_risk(self, universe: list[dict]) -> int:
        """
        Fetch quarterly SEC EDGAR cash data for each ticker and insert
        time-stamped capital_snapshots rows.

        snapshot_date = SEC filing date ("filed") — when investors knew the
        balance sheet, preserving the no-lookahead guarantee.

        Returns the number of rows inserted.
        """
        from bve.ingestion.sec_edgar import get_cik, get_company_facts

        _CASH_CONCEPTS = [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsAndShortTermInvestments",
            "CashAndCashEquivalentsAndShortTermInvestments",
        ]
        _RD_CONCEPTS = [
            "ResearchAndDevelopmentExpense",
            "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
        ]

        inserted = 0
        seen_tickers: set[str] = set()

        for entry in universe:
            ticker: str = entry.get("ticker", "").upper()
            asset_id: str = entry.get("asset_id", "")
            if not ticker or not asset_id or ticker in seen_tickers:
                continue
            seen_tickers.add(ticker)

            try:
                cik = get_cik(ticker)
                if not cik:
                    print(f"  [capital] no CIK for {ticker}, skipping")
                    continue

                facts = get_company_facts(cik)
                gaap = facts.get("us-gaap", {})

                # Extract quarterly cash time-series
                cash_series: list[dict] = []
                for concept in _CASH_CONCEPTS:
                    units = gaap.get(concept, {}).get("units", {}).get("USD", [])
                    if units:
                        quarterly = [
                            u for u in units
                            if u.get("form") in ("10-K", "10-Q")
                            and u.get("val") is not None
                            and u.get("filed")
                        ]
                        if quarterly:
                            cash_series = quarterly
                            break

                if not cash_series:
                    print(f"  [capital] no cash data for {ticker}, skipping")
                    continue

                # Estimate monthly burn from most recent annual R&D expense
                burn_monthly: float = 10.0  # conservative default ($10M/month)
                for concept in _RD_CONCEPTS:
                    units = gaap.get(concept, {}).get("units", {}).get("USD", [])
                    annual = [u for u in units if u.get("form") == "10-K" and u.get("val")]
                    if annual:
                        latest_rd = max(annual, key=lambda u: u.get("end", ""))
                        burn_monthly = round(latest_rd["val"] / 1e6 / 12, 2)
                        break

                rows_for_ticker = 0
                for q in cash_series:
                    cash_usd = q.get("val")
                    filed = (q.get("filed") or "")[:10]
                    if not filed or cash_usd is None:
                        continue

                    cash_millions = cash_usd / 1e6
                    burn_per_quarter = max(burn_monthly * 3.0, 0.1)
                    cash_runway_quarters = round(cash_millions / burn_per_quarter, 2)

                    # Deterministic ID so INSERT OR REPLACE is idempotent
                    snapshot_id = f"bf-cap:{asset_id}:{filed}"
                    self._rs._conn.execute(
                        "INSERT OR REPLACE INTO capital_snapshots "
                        "(snapshot_id, asset_id, snapshot_date, "
                        " cash_runway_quarters, capital_risk_level) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            snapshot_id,
                            asset_id,
                            filed,
                            cash_runway_quarters,
                            None,  # computed dynamically at query time from runway + catalyst date
                        ),
                    )
                    rows_for_ticker += 1

                self._rs._conn.commit()
                inserted += rows_for_ticker
                print(f"  [capital] {ticker}: {rows_for_ticker} quarterly snapshots")

            except Exception as exc:  # noqa: BLE001
                print(f"  [capital] {ticker}: error — {exc}")

        print(f"backfill_capital_risk: {inserted} rows inserted into capital_snapshots")
        return inserted

    # ------------------------------------------------------------------
    # 2. Catalyst signals — time-varying proximity per (asset, step_date)
    # ------------------------------------------------------------------

    def backfill_catalyst_signals(
        self,
        universe: list[dict],
        start_date: date,
        end_date: date,
        step_days: int = 30,
    ) -> int:
        """
        Insert time-varying catalyst signal rows into catalyst_events.

        At each step_date, compute a proximity-based signal for each asset
        from the nearest seeded future catalyst in historical_events.

        base_score = 0.10 — conservative default; deliberately NOT derived
        from ranking_score or opportunity_score to avoid circularity.

        Proximity formula:
            days < 0  (catalyst already passed):  0.0
            0 ≤ days ≤ 90:                        0.10 × (1 − days / 90)
            days > 90:                            0.10 × 0.20 = 0.02

        snapshot_date = step_date  (when signal was measured)
        event_date    = upcoming catalyst date

        Returns the number of rows inserted.
        """
        inserted = 0
        step = timedelta(days=step_days)
        current = start_date

        while current <= end_date:
            as_of = current.isoformat()

            for entry in universe:
                asset_id: str = entry.get("asset_id", "")
                ticker: str = entry.get("ticker", "").upper()
                if not asset_id or not ticker:
                    continue

                row = self._rs._conn.execute(
                    "SELECT announced_at FROM historical_events "
                    "WHERE asset_id = ? AND announced_at > ? "
                    "ORDER BY announced_at ASC LIMIT 1",
                    (asset_id, as_of),
                ).fetchone()

                if row is None:
                    continue

                catalyst_date_str = row["announced_at"][:10]
                try:
                    catalyst_date = date.fromisoformat(catalyst_date_str)
                except ValueError:
                    continue

                days_to_catalyst = (catalyst_date - current).days
                if days_to_catalyst < 0:
                    signal_strength = 0.0
                elif days_to_catalyst <= 90:
                    signal_strength = round(_BASE_SCORE * (1.0 - days_to_catalyst / 90.0), 4)
                else:
                    signal_strength = round(_BASE_SCORE * 0.20, 4)

                # Deterministic ID so INSERT OR REPLACE is truly idempotent
                event_id = f"bf-cat:{asset_id}:{as_of}"
                self._rs._conn.execute(
                    "INSERT OR REPLACE INTO catalyst_events "
                    "(event_id, asset_id, ticker, event_type, "
                    " event_date, signal_strength, snapshot_date) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        event_id,
                        asset_id,
                        ticker,
                        "trial_readout",
                        catalyst_date_str,
                        signal_strength,
                        as_of,
                    ),
                )
                inserted += 1

            self._rs._conn.commit()
            current = current + step

        print(f"backfill_catalyst_signals: {inserted} rows inserted into catalyst_events")
        return inserted

    # ------------------------------------------------------------------
    # 3. Competitor signals — from historical_events for peer asset_ids
    # ------------------------------------------------------------------

    def backfill_competitor_signals(
        self,
        competitor_map: dict[str, list[str]] | None = None,
    ) -> int:
        """
        Insert COMPETITOR_READOUT rows into catalyst_events for each asset
        that has peers in competitor_map.

        For each competitor event in historical_events, inserts one row
        linked to the peer asset so the composite scorer applies a drag.

        signal_strength = 0.30 (standard competitor event weight).
        snapshot_date   = announced_at of the competitor event.

        Returns the number of rows inserted.
        """
        cmap = competitor_map if competitor_map is not None else COMPETITOR_MAP
        inserted = 0

        for asset_id, competitor_asset_ids in cmap.items():
            for comp_asset_id in competitor_asset_ids:
                events = self._rs._conn.execute(
                    "SELECT ticker, announced_at FROM historical_events "
                    "WHERE asset_id = ? ORDER BY announced_at",
                    (comp_asset_id,),
                ).fetchall()

                if not events:
                    continue

                for ev in events:
                    comp_ticker = (ev["ticker"] or "").upper()
                    announced_at = (ev["announced_at"] or "")[:10]
                    if not announced_at:
                        continue

                    # Deterministic ID so INSERT OR REPLACE is truly idempotent
                    event_id = f"bf-comp:{asset_id}:{comp_asset_id}:{announced_at}"
                    self._rs._conn.execute(
                        "INSERT OR REPLACE INTO catalyst_events "
                        "(event_id, asset_id, ticker, event_type, "
                        " event_date, signal_strength, snapshot_date) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            event_id,
                            asset_id,
                            comp_ticker,
                            "COMPETITOR_READOUT",
                            announced_at,
                            _COMPETITOR_SIGNAL_STRENGTH,
                            announced_at,
                        ),
                    )
                    inserted += 1

            self._rs._conn.commit()

        print(f"backfill_competitor_signals: {inserted} rows inserted into catalyst_events")
        return inserted
