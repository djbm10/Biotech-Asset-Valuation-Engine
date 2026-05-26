"""
Historical Replay Mode for the Biotech Asset Valuation Engine.

Walk through historical weekly decisions using frozen-clock evaluation,
record simulated decisions in an isolated SQLite store, resolve exits,
and produce attribution-tagged performance summaries.

Usage
-----
    python -m bve.ops.historical_replay seed --tickers VKTX ALNY SRPT NTLA VRTX CRSP BEAM RXRX \\
                                              --start 2025-04-01 --end 2026-03-01

    python -m bve.ops.historical_replay run  --start 2025-04-01 --end 2026-03-01 \\
                                              --cadence weekly \\
                                              --decision-policy top2_add

    python -m bve.ops.historical_replay run  --profile mna \\
                                              --universe-file examples/research/universe_expanded_mna.yaml \\
                                              --start 2021-01-01 --end 2026-03-22

    python -m bve.ops.historical_replay summary --run-id <run_id>

    python -m bve.ops.historical_replay inspect --run-id <run_id> --week 2025-09-15
"""
from __future__ import annotations

import json
import statistics
import sqlite3
import sys
import uuid
from dataclasses import asdict
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import yaml

if TYPE_CHECKING:
    from bve.intelligence.composite_scorer import CompositeScoreContext

from bve.intelligence.actionable_output import (
    ActionableGenerator,
    ScoredCandidate,
)
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.replay_clock import ReplayClock
from bve.intelligence.replay_policy import ReplayDecision, ReplayPolicy, ReplayPolicyConfig
from bve.intelligence.replay_summary import ReplaySummary
from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker


# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_OUTPUTS_DIR = Path(__file__).parent.parent.parent.parent / "outputs" / "intelligence"
REPLAY_STORE_PATH = _OUTPUTS_DIR / "replay_store.sqlite"
REPLAY_KNOWLEDGE_PATH = _OUTPUTS_DIR / "replay_knowledge.db"
_DEFAULT_DEAL_UNIVERSE = (
    Path(__file__).parent.parent.parent.parent / "research" / "mna" / "deal_universe_2020_2026.yaml"
)


# ---------------------------------------------------------------------------
# Deal universe fallback price loader
# ---------------------------------------------------------------------------


def load_deal_fallback_prices(
    deal_universe_path: str | Path | None = None,
) -> dict[str, tuple[date, float]]:
    """Load per-share consideration prices from the deal universe YAML.

    Returns a dict of ``ticker → (announcement_date, consideration_per_share)``
    for every deal entry that has both ``target_ticker`` and
    ``consideration_per_share`` populated.  Used as the primary source for
    :meth:`HistoricalReplay.seed_prices` acquisition fallback, replacing the
    need for a hand-crafted caller-side dict.

    Parameters
    ----------
    deal_universe_path:
        Path to the deal universe YAML.  Defaults to
        ``research/mna/deal_universe_2020_2026.yaml`` relative to the repo root.
    """
    path = Path(deal_universe_path or _DEFAULT_DEAL_UNIVERSE)
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    deals = raw.get("deals", []) if isinstance(raw, dict) else raw
    result: dict[str, tuple[date, float]] = {}
    for deal in deals:
        ticker = deal.get("target_ticker")
        price = deal.get("consideration_per_share")
        ann_str = deal.get("announcement_date")
        if ticker and price is not None and ann_str:
            try:
                result[ticker] = (date.fromisoformat(ann_str), float(price))
            except (ValueError, TypeError):
                continue
    return result


# ---------------------------------------------------------------------------
# ReplayStore
# ---------------------------------------------------------------------------

class ReplayStore:
    """
    Isolated SQLite store for replay data.

    Completely separate from the live ops.db — no contamination of live tables.

    Parameters
    ----------
    db_path:
        Path to the SQLite database.  Pass ``":memory:"`` for tests.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS replay_runs (
                run_id           TEXT PRIMARY KEY,
                start_date       TEXT NOT NULL,
                end_date         TEXT NOT NULL,
                cadence          TEXT NOT NULL,
                decision_policy  TEXT NOT NULL,
                score_version    TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                run_metadata_json TEXT,
                created_at       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS historical_prices (
                ticker     TEXT NOT NULL,
                price_date TEXT NOT NULL,
                close_usd  REAL NOT NULL,
                PRIMARY KEY (ticker, price_date)
            );

            CREATE TABLE IF NOT EXISTS acquisition_announcements (
                ticker            TEXT PRIMARY KEY,
                announcement_date TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS historical_events (
                event_id       TEXT PRIMARY KEY,
                asset_id       TEXT NOT NULL,
                ticker         TEXT NOT NULL,
                event_type     TEXT NOT NULL,
                announced_at   TEXT NOT NULL,
                effective_date TEXT,
                outcome_label  TEXT,
                headline       TEXT
            );

            CREATE TABLE IF NOT EXISTS replay_decisions (
                decision_id     TEXT PRIMARY KEY,
                run_id          TEXT NOT NULL,
                asset_id        TEXT NOT NULL,
                ticker          TEXT NOT NULL,
                decided_at      TEXT NOT NULL,
                action          TEXT NOT NULL,
                size_pct        REAL NOT NULL,
                composite_score REAL NOT NULL,
                entry_price     REAL,
                exit_date       TEXT,
                exit_price      REAL,
                return_pct      REAL,
                attribution_type TEXT,
                is_closed       INTEGER NOT NULL DEFAULT 0,
                days_to_catalyst_at_entry INTEGER,
                decision_cluster_id TEXT,
                catalyst_event_id TEXT,
                phase TEXT,
                xbi_return_during_hold REAL,
                ibb_return_during_hold REAL,
                spy_return_during_hold REAL,
                xbi_above_20d_ma_at_entry INTEGER,
                gross_return_pct REAL,
                friction_cost_bps REAL,
                net_return_pct REAL
            );

            CREATE INDEX IF NOT EXISTS idx_replay_decisions_run
                ON replay_decisions(run_id, is_closed);

            CREATE INDEX IF NOT EXISTS idx_historical_events_asset
                ON historical_events(asset_id, announced_at);

            CREATE INDEX IF NOT EXISTS idx_historical_prices_ticker
                ON historical_prices(ticker, price_date);

            CREATE TABLE IF NOT EXISTS catalyst_events (
                event_id        TEXT PRIMARY KEY,
                asset_id        TEXT NOT NULL,
                ticker          TEXT NOT NULL,
                event_type      TEXT NOT NULL,
                event_date      TEXT NOT NULL,
                signal_strength REAL,
                snapshot_date   TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_catalyst_events_asset
                ON catalyst_events(asset_id, event_date);

            CREATE TABLE IF NOT EXISTS enrollment_snapshots (
                snapshot_id    TEXT PRIMARY KEY,
                asset_id       TEXT NOT NULL,
                snapshot_date  TEXT NOT NULL,
                site_stalling  INTEGER NOT NULL DEFAULT 0,
                velocity_low   INTEGER NOT NULL DEFAULT 0,
                slippage_alert INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_enrollment_snapshots_asset
                ON enrollment_snapshots(asset_id, snapshot_date);

            CREATE TABLE IF NOT EXISTS structured_signals (
                signal_id           TEXT PRIMARY KEY,
                asset_id            TEXT NOT NULL,
                signal_date         TEXT NOT NULL,
                signal_type         TEXT NOT NULL,
                z_score             REAL,
                phase_prior_pos     REAL,
                phase_posterior_pos REAL
            );

            CREATE INDEX IF NOT EXISTS idx_structured_signals_asset
                ON structured_signals(asset_id, signal_date);

            CREATE TABLE IF NOT EXISTS capital_snapshots (
                snapshot_id          TEXT PRIMARY KEY,
                asset_id             TEXT NOT NULL,
                snapshot_date        TEXT NOT NULL,
                cash_runway_quarters REAL,
                capital_risk_level   TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_capital_snapshots_asset
                ON capital_snapshots(asset_id, snapshot_date);

            CREATE TABLE IF NOT EXISTS balance_sheet_snapshots (
                snapshot_id                   TEXT PRIMARY KEY,
                ticker                        TEXT NOT NULL,
                snapshot_date                 TEXT NOT NULL,
                period_end_date               TEXT,
                form_type                     TEXT,
                cash_millions                 REAL,
                debt_millions                 REAL,
                shares_outstanding_millions   REAL,
                burn_rate_millions_per_quarter REAL,
                source_type                   TEXT NOT NULL,
                source_ref                    TEXT NOT NULL,
                created_at                    TEXT NOT NULL,
                UNIQUE(ticker, snapshot_date, source_ref)
            );

            CREATE INDEX IF NOT EXISTS idx_balance_sheet_snapshots_ticker
                ON balance_sheet_snapshots(ticker, snapshot_date);
            """
        )
        self._conn.commit()
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        """Apply backward-compatible schema migrations for existing databases."""
        # acquisition_announcements was added in Sprint 16 audit
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS acquisition_announcements (
                ticker            TEXT PRIMARY KEY,
                announcement_date TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

        existing = {
            row[1]
            for row in self._conn.execute(
                "PRAGMA table_info(catalyst_events)"
            ).fetchall()
        }
        if "snapshot_date" not in existing:
            self._conn.execute(
                "ALTER TABLE catalyst_events ADD COLUMN snapshot_date TEXT"
            )
            self._conn.commit()
        replay_run_columns = {
            row[1]
            for row in self._conn.execute(
                "PRAGMA table_info(replay_runs)"
            ).fetchall()
        }
        if "run_metadata_json" not in replay_run_columns:
            self._conn.execute(
                "ALTER TABLE replay_runs ADD COLUMN run_metadata_json TEXT"
            )
            self._conn.commit()
        replay_decision_columns = {
            row[1]
            for row in self._conn.execute(
                "PRAGMA table_info(replay_decisions)"
            ).fetchall()
        }
        for column_name, column_type in {
            "days_to_catalyst_at_entry": "INTEGER",
            "decision_cluster_id": "TEXT",
            "catalyst_event_id": "TEXT",
            "phase": "TEXT",
            "xbi_return_during_hold": "REAL",
            "ibb_return_during_hold": "REAL",
            "spy_return_during_hold": "REAL",
            "xbi_above_20d_ma_at_entry": "INTEGER",
            "gross_return_pct": "REAL",
            "friction_cost_bps": "REAL",
            "net_return_pct": "REAL",
        }.items():
            if column_name not in replay_decision_columns:
                try:
                    self._conn.execute(
                        f"ALTER TABLE replay_decisions ADD COLUMN {column_name} {column_type}"
                    )
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" not in str(exc).lower():
                        raise
        self._conn.commit()

    # ------------------------------------------------------------------
    # Prices
    # ------------------------------------------------------------------

    def insert_prices(self, ticker: str, rows: list[tuple[date, float]]) -> None:
        """Bulk-insert (date, close_usd) pairs for *ticker*."""
        self._conn.executemany(
            "INSERT OR REPLACE INTO historical_prices (ticker, price_date, close_usd) "
            "VALUES (?, ?, ?)",
            [(ticker, d.isoformat(), price) for d, price in rows],
        )
        self._conn.commit()

    def seed_acquisition_price(
        self,
        ticker: str,
        announcement_date: date,
        price_per_share: float,
        *,
        lookback_days: int = 365,
    ) -> int:
        """Seed synthetic flat price history for an acquired / delisted ticker.

        For tickers that no longer trade on yfinance, this creates a constant
        price series (equal to the deal consideration price) covering the
        ``lookback_days``-day window ending on *announcement_date*.  The flat
        series lets replay attribution work correctly even when live data is
        unavailable.

        Parameters
        ----------
        ticker:
            The acquired company's ticker (e.g. "TPTX").
        announcement_date:
            The M&A announcement date.  This is the last synthetic row date.
        price_per_share:
            The deal consideration per share (e.g. $76.00 for TPTX).
        lookback_days:
            How many calendar days before *announcement_date* to cover.
            Defaults to 365 (12 months).

        Returns
        -------
        int
            Number of price rows inserted.
        """
        start = announcement_date - timedelta(days=lookback_days)
        rows: list[tuple[date, float]] = []
        current = start
        while current <= announcement_date:
            # Include all calendar days — ReplayStore.get_price() uses
            # a floor-to-most-recent query so gaps are fine, but denser data
            # prevents gaps in weekly replay windows.
            rows.append((current, price_per_share))
            current += timedelta(days=1)
        if rows:
            self.insert_prices(ticker, rows)
        # Record announcement date so get_price() can enforce the pre-announcement
        # leakage guard: queries before this date will return None.
        self._conn.execute(
            "INSERT OR REPLACE INTO acquisition_announcements (ticker, announcement_date) "
            "VALUES (?, ?)",
            (ticker, announcement_date.isoformat()),
        )
        self._conn.commit()
        return len(rows)

    def get_price(self, ticker: str, price_date: date) -> Optional[float]:
        """
        Return the most recent closing price for *ticker* on or before *price_date*.

        Returns None if no data is available on or before *price_date*
        (enforces no lookahead bias — callers must not pass a future date
        relative to their clock).

        Anti-leakage guard: if *ticker* has a synthetic price series seeded
        via ``seed_acquisition_price()``, queries for dates strictly before
        the recorded announcement date return None — the deal consideration
        price must not be used as a pre-announcement market price.
        """
        # Check acquisition announcement guard before querying prices.
        ann_row = self._conn.execute(
            "SELECT announcement_date FROM acquisition_announcements WHERE ticker = ?",
            (ticker,),
        ).fetchone()
        if ann_row is not None:
            ann_date = date.fromisoformat(str(ann_row["announcement_date"]))
            if price_date < ann_date:
                return None

        row = self._conn.execute(
            "SELECT close_usd FROM historical_prices "
            "WHERE ticker = ? AND price_date <= ? "
            "ORDER BY price_date DESC LIMIT 1",
            (ticker, price_date.isoformat()),
        ).fetchone()
        return float(row["close_usd"]) if row else None

    @staticmethod
    def compute_return_pct(
        entry_price: Optional[float],
        exit_price: Optional[float],
    ) -> Optional[float]:
        """Return percentage price change, or None when it cannot be computed."""
        if entry_price is None or exit_price is None or entry_price == 0.0:
            return None
        return (exit_price / entry_price - 1.0) * 100.0

    def get_return(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
    ) -> Optional[float]:
        """
        Compute the simple return from the most recent available close on or
        before *from_date* to the most recent available close on or before
        *to_date*.

        Returns None if either price is missing.
        """
        entry = self.get_price(ticker, from_date)
        exit_ = self.get_price(ticker, to_date)
        return self.compute_return_pct(entry, exit_)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def insert_event(
        self,
        asset_id: str,
        ticker: str,
        event_type: str,
        announced_at: date,
        effective_date: date,
        outcome_label: str,
        headline: str,
    ) -> str:
        """Insert a historical event. Returns the generated event_id."""
        event_id = str(uuid.uuid4())
        self._conn.execute(
            """
            INSERT INTO historical_events
                (event_id, asset_id, ticker, event_type, announced_at,
                 effective_date, outcome_label, headline)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                asset_id,
                ticker,
                event_type,
                announced_at.isoformat(),
                effective_date.isoformat(),
                outcome_label,
                headline,
            ),
        )
        self._conn.commit()
        return event_id

    def get_events_as_of(self, asset_id: str, as_of_date: date) -> list[dict]:
        """
        Return events for *asset_id* where ``announced_at <= as_of_date``.

        No-lookahead: events announced after *as_of_date* are invisible.
        """
        rows = self._conn.execute(
            "SELECT * FROM historical_events "
            "WHERE asset_id = ? AND announced_at <= ? "
            "ORDER BY announced_at",
            (asset_id, as_of_date.isoformat()),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_events_in_window(
        self,
        asset_id: str,
        from_date: date,
        to_date: date,
    ) -> list[dict]:
        """
        Return events for *asset_id* that occurred within [from_date, to_date].

        Used for hold-window attribution: only events that happened AFTER entry
        and ON OR BEFORE exit can causally explain the position's return.
        """
        rows = self._conn.execute(
            "SELECT * FROM historical_events "
            "WHERE asset_id = ? AND announced_at >= ? AND announced_at <= ? "
            "ORDER BY announced_at",
            (asset_id, from_date.isoformat(), to_date.isoformat()),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_ma(self, ticker: str, as_of_date: date, window_days: int = 20) -> Optional[float]:
        """
        Return the simple moving average of *ticker* close prices over the
        *window_days* calendar days ending on (and including) *as_of_date*.

        Returns None if fewer than half the requested bars are available.
        """
        from datetime import timedelta

        since = (as_of_date - timedelta(days=window_days * 2)).isoformat()
        rows = self._conn.execute(
            "SELECT close_usd FROM historical_prices "
            "WHERE ticker = ? AND price_date <= ? AND price_date >= ? "
            "ORDER BY price_date DESC LIMIT ?",
            (ticker, as_of_date.isoformat(), since, window_days),
        ).fetchall()
        if len(rows) < window_days // 2:
            return None
        return sum(r["close_usd"] for r in rows) / len(rows)

    def get_upcoming_catalysts(
        self,
        as_of_date: date,
        lookahead_days: int = 90,
    ) -> dict[str, date]:
        """
        Return the nearest upcoming catalyst date per asset_id.

        Models catalyst dates that are *already on the calendar* (scheduled
        in advance) but have not yet resolved as of *as_of_date*.  Returns
        events where ``as_of_date < announced_at <= as_of_date + lookahead_days``.

        Returns
        -------
        dict mapping asset_id → next catalyst date (the earliest upcoming one).
        """
        from datetime import timedelta

        window_end = (as_of_date + timedelta(days=lookahead_days)).isoformat()
        rows = self._conn.execute(
            "SELECT asset_id, MIN(announced_at) as next_catalyst "
            "FROM historical_events "
            "WHERE announced_at > ? AND announced_at <= ? "
            "GROUP BY asset_id",
            (as_of_date.isoformat(), window_end),
        ).fetchall()
        result: dict[str, date] = {}
        for row in rows:
            try:
                result[row["asset_id"]] = date.fromisoformat(row["next_catalyst"][:10])
            except (ValueError, TypeError):
                pass
        return result

    def get_nearest_upcoming_event(
        self,
        asset_id: str,
        as_of_date: date,
        lookahead_days: int = 365,
    ) -> Optional[dict]:
        """Return the nearest upcoming historical event for an asset."""
        window_end = (as_of_date + timedelta(days=lookahead_days)).isoformat()
        row = self._conn.execute(
            """
            SELECT event_id, asset_id, ticker, event_type, announced_at, effective_date
            FROM historical_events
            WHERE asset_id = ?
              AND announced_at > ?
              AND announced_at <= ?
            ORDER BY announced_at ASC
            LIMIT 1
            """,
            (asset_id, as_of_date.isoformat(), window_end),
        ).fetchone()
        return dict(row) if row else None

    def get_recent_attributions(
        self,
        run_id: str,
        asset_id: str,
        limit: int = 5,
    ) -> list[dict]:
        """
        Return most recent closed decisions for *asset_id* in *run_id*.

        Used by the cooling rule: inspect last N outcomes to determine
        whether entry should be blocked for the next cycle(s).
        """
        rows = self._conn.execute(
            "SELECT attribution_type, exit_date, decided_at "
            "FROM replay_decisions "
            "WHERE run_id = ? AND asset_id = ? AND is_closed = 1 "
            "ORDER BY exit_date DESC LIMIT ?",
            (run_id, asset_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def create_run(
        self,
        start_date: date,
        end_date: date,
        cadence: str,
        decision_policy: str,
        score_version: str,
        strategy_version: str,
        run_metadata_json: Optional[str] = None,
    ) -> str:
        """Create a new replay run record. Returns run_id."""
        run_id = str(uuid.uuid4())
        self._conn.execute(
            """
            INSERT INTO replay_runs
                (run_id, start_date, end_date, cadence, decision_policy,
                 score_version, strategy_version, run_metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                start_date.isoformat(),
                end_date.isoformat(),
                cadence,
                decision_policy,
                score_version,
                strategy_version,
                run_metadata_json,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()
        return run_id

    def get_run(self, run_id: str) -> Optional[dict]:
        """Return run metadata or None."""
        row = self._conn.execute(
            "SELECT * FROM replay_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    def insert_decision(
        self,
        run_id: str,
        decision: ReplayDecision,
        entry_price: Optional[float],
    ) -> str:
        """Persist a simulated decision. Returns decision_id."""
        decision_id = str(uuid.uuid4())
        self._conn.execute(
            """
            INSERT INTO replay_decisions
                (decision_id, run_id, asset_id, ticker, decided_at, action,
                 size_pct, composite_score, entry_price, is_closed,
                 days_to_catalyst_at_entry, decision_cluster_id, catalyst_event_id, phase)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """,
            (
                decision_id,
                run_id,
                decision.asset_id,
                decision.ticker,
                decision.decided_at.isoformat(),
                decision.recommended_action,
                decision.recommended_size_pct,
                decision.composite_score,
                entry_price,
                decision.days_to_catalyst_at_entry,
                decision.decision_cluster_id,
                decision.catalyst_event_id,
                decision.phase,
            ),
        )
        self._conn.commit()
        return decision_id

    def get_open_decisions(self, run_id: str) -> list[dict]:
        """Return all open (not yet closed) decisions for *run_id*."""
        rows = self._conn.execute(
            "SELECT * FROM replay_decisions "
            "WHERE run_id = ? AND is_closed = 0 "
            "ORDER BY decided_at",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close_decision(
        self,
        decision_id: str,
        exit_price: Optional[float],
        exit_date: date,
        return_pct: Optional[float],
        attribution_type: str,
        *,
        xbi_return_during_hold: Optional[float] = None,
        ibb_return_during_hold: Optional[float] = None,
        spy_return_during_hold: Optional[float] = None,
        xbi_above_20d_ma_at_entry: Optional[bool] = None,
        friction_cost_bps: Optional[float] = None,
        net_return_pct: Optional[float] = None,
    ) -> None:
        """Close a decision by recording exit data."""
        self._conn.execute(
            """
            UPDATE replay_decisions
               SET exit_date        = ?,
                   exit_price       = ?,
                   return_pct       = ?,
                   attribution_type = ?,
                   xbi_return_during_hold = ?,
                   ibb_return_during_hold = ?,
                   spy_return_during_hold = ?,
                   xbi_above_20d_ma_at_entry = ?,
                   gross_return_pct = ?,
                   friction_cost_bps = ?,
                   net_return_pct = ?,
                   is_closed        = 1
             WHERE decision_id = ?
            """,
            (
                exit_date.isoformat(),
                exit_price,
                return_pct,
                attribution_type,
                xbi_return_during_hold,
                ibb_return_during_hold,
                spy_return_during_hold,
                int(xbi_above_20d_ma_at_entry)
                if xbi_above_20d_ma_at_entry is not None else None,
                return_pct,
                friction_cost_bps,
                net_return_pct,
                decision_id,
            ),
        )
        self._conn.commit()

    def get_run_decisions(self, run_id: str) -> list[dict]:
        """Return all decisions (open and closed) for *run_id*."""
        rows = self._conn.execute(
            "SELECT * FROM replay_decisions WHERE run_id = ? ORDER BY decided_at",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def backfill_decision_prices(self, run_id: str) -> int:
        """
        Backfill missing entry prices for decisions in *run_id*.

        For closed decisions, also refresh ``exit_price`` from
        ``historical_prices`` using the recorded ``exit_date`` and recompute
        ``return_pct`` when both prices are available.
        """
        rows = self._conn.execute(
            """
            SELECT decision_id, ticker, decided_at, exit_date, exit_price, return_pct, is_closed
            FROM replay_decisions
            WHERE run_id = ? AND entry_price IS NULL
            ORDER BY decided_at
            """,
            (run_id,),
        ).fetchall()

        updated = 0
        for row in rows:
            decision_id = str(row["decision_id"])
            ticker = str(row["ticker"])
            try:
                decided_at = date.fromisoformat(str(row["decided_at"])[:10])
            except (TypeError, ValueError):
                continue

            entry_price = self.get_price(ticker, decided_at)
            if entry_price is None:
                continue

            exit_price = row["exit_price"]
            return_pct = row["return_pct"]
            if row["is_closed"] and row["exit_date"]:
                try:
                    exit_date = date.fromisoformat(str(row["exit_date"])[:10])
                except (TypeError, ValueError):
                    exit_date = None

                if exit_date is not None:
                    looked_up_exit = self.get_price(ticker, exit_date)
                    if looked_up_exit is not None:
                        exit_price = looked_up_exit
                    return_pct = self.compute_return_pct(entry_price, exit_price)

            self._conn.execute(
                """
                UPDATE replay_decisions
                   SET entry_price = ?,
                       exit_price  = ?,
                       return_pct  = ?
                 WHERE decision_id = ?
                """,
                (entry_price, exit_price, return_pct, decision_id),
            )
            updated += 1

        self._conn.commit()
        return updated

    # ------------------------------------------------------------------
    # v2.0 signal queries  (all enforce no-lookahead via <= as_of_date)
    # ------------------------------------------------------------------

    def get_catalyst_signal_strength(
        self,
        asset_id: str,
        as_of_date: date,
    ) -> Optional[float]:
        """
        Return the most-recently-measured signal_strength for own-asset catalysts
        on or before *as_of_date*.  Uses snapshot_date when available, falling back
        to event_date for rows that pre-date the migration.
        Excludes COMPETITOR_READOUT events.
        Returns None when no catalyst data is available.
        """
        as_of = as_of_date.isoformat()
        row = self._conn.execute(
            "SELECT signal_strength "
            "FROM catalyst_events "
            "WHERE asset_id = ? "
            "  AND COALESCE(snapshot_date, event_date) <= ? "
            "  AND event_type != 'COMPETITOR_READOUT' "
            "  AND signal_strength IS NOT NULL "
            "ORDER BY COALESCE(snapshot_date, event_date) DESC "
            "LIMIT 1",
            (asset_id, as_of),
        ).fetchone()
        if row is not None:
            return float(row["signal_strength"])
        return None

    def get_enrollment_flags(
        self,
        asset_id: str,
        as_of_date: date,
    ) -> Optional[dict]:
        """
        Return the most recent enrollment snapshot for *asset_id* on or before
        *as_of_date* as a dict with boolean keys ``site_stalling``,
        ``velocity_low``, ``slippage_alert``.
        Returns None when no snapshot is available.
        """
        row = self._conn.execute(
            "SELECT site_stalling, velocity_low, slippage_alert "
            "FROM enrollment_snapshots "
            "WHERE asset_id = ? AND snapshot_date <= ? "
            "ORDER BY snapshot_date DESC LIMIT 1",
            (asset_id, as_of_date.isoformat()),
        ).fetchone()
        if row:
            return {
                "site_stalling": bool(row["site_stalling"]),
                "velocity_low": bool(row["velocity_low"]),
                "slippage_alert": bool(row["slippage_alert"]),
            }
        return None

    def get_phase_correlation(
        self,
        asset_id: str,
        as_of_date: date,
    ) -> tuple[Optional[float], Optional[float]]:
        """
        Return ``(phase_prior_pos, phase_posterior_pos)`` from the most recent
        structured signal of type ``phase_correlation`` for *asset_id* on or
        before *as_of_date*.
        Returns ``(None, None)`` when no signal is available.
        """
        row = self._conn.execute(
            "SELECT phase_prior_pos, phase_posterior_pos "
            "FROM structured_signals "
            "WHERE asset_id = ? AND signal_date <= ? "
            "  AND signal_type = 'phase_correlation' "
            "  AND phase_prior_pos IS NOT NULL "
            "  AND phase_posterior_pos IS NOT NULL "
            "ORDER BY signal_date DESC LIMIT 1",
            (asset_id, as_of_date.isoformat()),
        ).fetchone()
        if row:
            return float(row["phase_prior_pos"]), float(row["phase_posterior_pos"])
        return None, None

    def get_endpoint_z_score(
        self,
        asset_id: str,
        as_of_date: date,
    ) -> Optional[float]:
        """
        Return the z_score from the most recent structured signal with a
        non-null z_score for *asset_id* on or before *as_of_date*.
        Returns None when no signal is available.
        """
        row = self._conn.execute(
            "SELECT z_score FROM structured_signals "
            "WHERE asset_id = ? AND signal_date <= ? "
            "  AND z_score IS NOT NULL "
            "ORDER BY signal_date DESC LIMIT 1",
            (asset_id, as_of_date.isoformat()),
        ).fetchone()
        if row:
            return float(row["z_score"])
        return None

    def get_competitor_signals(
        self,
        asset_id: str,
        as_of_date: date,
        window_days: int = 60,
    ) -> list[float]:
        """
        Return signal_strength values for COMPETITOR_READOUT catalyst events
        associated with *asset_id* within the *window_days* window ending on
        *as_of_date*.  Empty list when none are found.
        """
        from datetime import timedelta

        window_start = (as_of_date - timedelta(days=window_days)).isoformat()
        rows = self._conn.execute(
            "SELECT signal_strength FROM catalyst_events "
            "WHERE asset_id = ? AND event_type = 'COMPETITOR_READOUT' "
            "  AND event_date > ? AND event_date <= ? "
            "  AND signal_strength IS NOT NULL",
            (asset_id, window_start, as_of_date.isoformat()),
        ).fetchall()
        return [float(r["signal_strength"]) for r in rows]

    def get_capital_risk_level(
        self,
        asset_id: str,
        as_of_date: date,
    ) -> Optional[str]:
        """
        Return the most recent capital_risk_level string for *asset_id* on
        or before *as_of_date* from capital_snapshots.
        Returns None when no snapshot is available.
        """
        row = self._conn.execute(
            "SELECT capital_risk_level FROM capital_snapshots "
            "WHERE asset_id = ? AND snapshot_date <= ? "
            "  AND capital_risk_level IS NOT NULL "
            "ORDER BY snapshot_date DESC LIMIT 1",
            (asset_id, as_of_date.isoformat()),
        ).fetchone()
        if row:
            return str(row["capital_risk_level"])
        return None

    def upsert_balance_sheet_snapshot(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        period_end_date: Optional[date] = None,
        form_type: Optional[str] = None,
        cash_millions: Optional[float] = None,
        debt_millions: Optional[float] = None,
        shares_outstanding_millions: Optional[float] = None,
        burn_rate_millions_per_quarter: Optional[float] = None,
        source_type: str = "sec_edgar",
        source_ref: str,
    ) -> None:
        snapshot_key = (
            f"bs:{ticker.upper()}:{snapshot_date.isoformat()}:{source_ref}"
        )
        self._conn.execute(
            """
            INSERT OR REPLACE INTO balance_sheet_snapshots(
                snapshot_id,
                ticker,
                snapshot_date,
                period_end_date,
                form_type,
                cash_millions,
                debt_millions,
                shares_outstanding_millions,
                burn_rate_millions_per_quarter,
                source_type,
                source_ref,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_key,
                ticker.upper(),
                snapshot_date.isoformat(),
                period_end_date.isoformat() if period_end_date else None,
                form_type,
                cash_millions,
                debt_millions,
                shares_outstanding_millions,
                burn_rate_millions_per_quarter,
                source_type,
                source_ref,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def get_balance_sheet_snapshot(
        self,
        ticker: str,
        as_of_date: date,
    ) -> Optional[dict[str, object]]:
        row = self._conn.execute(
            """
            SELECT ticker,
                   snapshot_date,
                   period_end_date,
                   form_type,
                   cash_millions,
                   debt_millions,
                   shares_outstanding_millions,
                   burn_rate_millions_per_quarter,
                   source_type,
                   source_ref,
                   created_at
            FROM balance_sheet_snapshots
            WHERE ticker = ? AND snapshot_date <= ?
            ORDER BY snapshot_date DESC, created_at DESC
            LIMIT 1
            """,
            (ticker.upper(), as_of_date.isoformat()),
        ).fetchone()
        return dict(row) if row is not None else None

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()


# ---------------------------------------------------------------------------
# HistoricalReplay
# ---------------------------------------------------------------------------

class HistoricalReplay:
    """
    Main loop controller for historical replay.

    Parameters
    ----------
    replay_store:
        The ``ReplayStore`` instance (isolated from live DB).
    knowledge_store_path:
        Path to the replay's KnowledgeStore (thesis claims, decisions).
        Should be distinct from the live ops.db.
    universe:
        List of universe dicts (same structure as ``weekly_runner.UNIVERSE``).
    policy_config:
        ReplayPolicyConfig to use (defaults to top2_add).
    """

    def __init__(
        self,
        replay_store: ReplayStore,
        knowledge_store_path: str,
        universe: Optional[list[dict]] = None,
        policy_config: Optional[ReplayPolicyConfig] = None,
    ) -> None:
        self._rs = replay_store
        self._ks_path = knowledge_store_path
        self._universe = universe or []
        self._policy = ReplayPolicy(policy_config)

    # ------------------------------------------------------------------
    # Seeding
    # ------------------------------------------------------------------

    def seed_prices(
        self,
        tickers: list[str],
        start: date,
        end: date,
        *,
        acquisition_fallback: Optional[dict[str, tuple[date, float]]] = None,
        deal_universe_path: str | Path | None = None,
    ) -> None:
        """Download historical prices from yfinance and store them.

        Failures are handled gracefully — a warning is printed and the loop
        continues with partial data.

        Parameters
        ----------
        tickers:
            List of tickers to seed.
        start, end:
            Date range to request from yfinance.
        acquisition_fallback:
            Optional mapping of ``ticker → (announcement_date, price_per_share)``
            for acquired / delisted names where yfinance returns no data.
            When yfinance returns an empty or failed result *and* the ticker is
            present in this dict, synthetic flat price history is seeded via
            :meth:`ReplayStore.seed_acquisition_price` (365-day window ending
            at *announcement_date*).  Takes precedence over deal-universe lookup.
        deal_universe_path:
            Optional path to ``deal_universe_2020_2026.yaml``.  When provided
            (or when the default path exists), consideration prices from the YAML
            are used as a fallback *after* ``acquisition_fallback`` is checked.
            Pass ``False`` to disable deal-universe lookup entirely.
        """
        from bve.ingestion.market_data import fetch_price_history

        # Build the merged fallback table: caller dict takes precedence;
        # deal-universe provides the remaining entries automatically.
        _deal_fb: dict[str, tuple[date, float]] = (
            {}
            if deal_universe_path is False
            else load_deal_fallback_prices(deal_universe_path or None)
        )
        _fb: dict[str, tuple[date, float]] = {**_deal_fb, **(acquisition_fallback or {})}

        def _apply_fallback(ticker: str, source_label: str) -> None:
            if ticker in _fb:
                ann_date, price = _fb[ticker]
                src = "caller" if (acquisition_fallback or {}).get(ticker) else "deal_universe"
                n = self._rs.seed_acquisition_price(ticker, ann_date, price)
                print(f"  {ticker}: {n} synthetic rows seeded from {src} fallback @ ${price:.2f}")

        for ticker in tickers:
            try:
                df = fetch_price_history(
                    ticker,
                    start=start.isoformat(),
                    end=end.isoformat(),
                )
                if df.empty:
                    print(f"  [WARN] No price data for {ticker}")
                    _apply_fallback(ticker, "empty_df")
                    continue

                rows: list[tuple[date, float]] = []
                for idx, row in df.iterrows():
                    try:
                        d = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
                        close = float(row["Close"])
                        rows.append((d, close))
                    except (ValueError, KeyError, TypeError):
                        continue

                if rows:
                    self._rs.insert_prices(ticker, rows)
                    print(f"  {ticker}: {len(rows)} price rows inserted")
                else:
                    print(f"  [WARN] No valid rows parsed for {ticker}")
                    _apply_fallback(ticker, "empty_rows")

            except Exception as exc:  # noqa: BLE001
                print(f"  [WARN] Failed to seed prices for {ticker}: {exc}")
                _apply_fallback(ticker, "exception")

    def seed_claims(
        self,
        tickers_universe: list[dict],
        seed_date: date,
    ) -> None:
        """
        Insert thesis claims into the replay knowledge store at *seed_date*.

        Claims are inserted with ``created_at = seed_date`` so the time-freeze
        SQL filter works correctly.
        """
        ks = KnowledgeStore(self._ks_path)
        tt = ThesisTracker(ks)

        # Incremental: check which asset_ids already have a claim
        existing_ids: set[str] = set()
        rows = ks._conn.execute("SELECT DISTINCT asset_id FROM thesis_claims").fetchall()
        for row in rows:
            existing_ids.add(row["asset_id"] if isinstance(row, dict) else row[0])

        new_entries = [u for u in tickers_universe if u["asset_id"] not in existing_ids]
        if not new_entries:
            print(f"Replay knowledge store already has all {len(tickers_universe)} claims.")
            ks.close()
            return

        seed_dt = datetime(seed_date.year, seed_date.month, seed_date.day, tzinfo=timezone.utc)
        print(f"Seeding {len(new_entries)} new claims at {seed_date} into replay KB "
              f"(skipping {len(existing_ids)} already present)...")
        for u in new_entries:
            tt.add_claim(
                asset_id=u["asset_id"],
                company_id=u["company_id"],
                claim_type=u["claim_type"],
                assertion=u["claim_assertion"],
                created_at=seed_dt,
            )
        ks.close()
        print(f"Seeded {len(new_entries)} new claims.")

    def seed_signals_from_knowledge_store(self, knowledge_db_path: str) -> dict[str, int]:
        """
        Approach A — Copy live signal data from a knowledge store into the
        replay store's v2.0 signal tables.

        Opens *knowledge_db_path* directly via sqlite3 so there is no
        circular dependency on KnowledgeStore.  Only data that already exists
        in the live KB is copied — no fabrication.  Original timestamps are
        preserved so the replay's no-lookahead queries (``<= as_of_date``)
        work correctly.

        Tables populated
        ----------------
        catalyst_events:
            All rows from the KB's ``catalyst_events`` table.  ``signal_strength``
            is extracted from ``payload_json``.  Rows without a signal_strength
            value are still copied (signal_strength = NULL → neutral).
        enrollment_snapshots:
            All rows from the KB's ``enrollment_snapshots`` table.  The three
            alert flags (``site_stalling``, ``velocity_low``, ``slippage_alert``)
            are extracted from ``payload_json``.
        structured_signals:
            Rows from the KB's ``structured_signals`` that contain a
            ``z_score`` field in ``payload_json``.  Phase-correlation prior/posterior
            fields are also extracted when present.

        Note: ``capital_snapshots`` are not copied because the KB does not yet
        store serialised capital-risk assessments.  Those signals default to
        neutral (None) during replay scoring.

        Parameters
        ----------
        knowledge_db_path:
            Path to the live ops.db (or any KnowledgeStore-formatted SQLite).

        Returns
        -------
        Dict mapping table name → number of rows inserted.
        """
        import json

        # Build a ticker lookup from the universe so we can populate the
        # replay's catalyst_events.ticker column.
        ticker_map: dict[str, str] = {u["asset_id"]: u["ticker"] for u in self._universe}

        counts: dict[str, int] = {
            "catalyst_events": 0,
            "enrollment_snapshots": 0,
            "structured_signals": 0,
        }

        try:
            src = sqlite3.connect(knowledge_db_path)
            src.row_factory = sqlite3.Row
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Cannot open knowledge store at {knowledge_db_path!r}: {exc}")
            return counts

        try:
            # ── 1. catalyst_events ───────────────────────────────────────
            try:
                rows = src.execute(
                    "SELECT id, asset_id, catalyst_type, expected_date, payload_json "
                    "FROM catalyst_events"
                ).fetchall()
            except Exception:  # noqa: BLE001
                rows = []

            for row in rows:
                row = dict(row)
                asset_id = row.get("asset_id") or ""
                ticker = ticker_map.get(asset_id, "")
                event_type = row.get("catalyst_type") or "unknown"
                event_date = (row.get("expected_date") or "")[:10]
                if not event_date:
                    continue

                # Extract signal_strength from payload_json
                signal_strength: Optional[float] = None
                try:
                    payload = json.loads(row.get("payload_json") or "{}")
                    ss = payload.get("signal_strength")
                    if ss is not None:
                        signal_strength = float(ss)
                except Exception:  # noqa: BLE001
                    pass

                try:
                    self._rs._conn.execute(
                        "INSERT OR REPLACE INTO catalyst_events "
                        "(event_id, asset_id, ticker, event_type, event_date, signal_strength) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (row["id"], asset_id, ticker, event_type, event_date, signal_strength),
                    )
                    counts["catalyst_events"] += 1
                except Exception:  # noqa: BLE001
                    pass

            self._rs._conn.commit()

            # ── 2. enrollment_snapshots ──────────────────────────────────
            try:
                rows = src.execute(
                    "SELECT id, asset_id, snapshot_date, payload_json "
                    "FROM enrollment_snapshots"
                ).fetchall()
            except Exception:  # noqa: BLE001
                rows = []

            for row in rows:
                row = dict(row)
                asset_id = row.get("asset_id") or ""
                snapshot_date = (row.get("snapshot_date") or "")[:10]
                if not snapshot_date:
                    continue

                site_stalling = 0
                velocity_low = 0
                slippage_alert = 0
                try:
                    payload = json.loads(row.get("payload_json") or "{}")
                    site_stalling = int(bool(payload.get("site_stalling", False)))
                    velocity_low = int(bool(payload.get("velocity_low", False)))
                    slippage_alert = int(bool(payload.get("slippage_alert", False)))
                except Exception:  # noqa: BLE001
                    pass

                try:
                    self._rs._conn.execute(
                        "INSERT OR REPLACE INTO enrollment_snapshots "
                        "(snapshot_id, asset_id, snapshot_date, "
                        " site_stalling, velocity_low, slippage_alert) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (row["id"], asset_id, snapshot_date,
                         site_stalling, velocity_low, slippage_alert),
                    )
                    counts["enrollment_snapshots"] += 1
                except Exception:  # noqa: BLE001
                    pass

            self._rs._conn.commit()

            # ── 3. structured_signals  (z_score + phase correlation) ─────
            try:
                rows = src.execute(
                    "SELECT id, asset_id, signal_date, event_type, payload_json "
                    "FROM structured_signals "
                    "WHERE asset_id IS NOT NULL"
                ).fetchall()
            except Exception:  # noqa: BLE001
                rows = []

            for row in rows:
                row = dict(row)
                asset_id = row.get("asset_id") or ""
                signal_date = (row.get("signal_date") or "")[:10]
                signal_type = row.get("event_type") or "unknown"
                if not signal_date:
                    continue

                z_score: Optional[float] = None
                phase_prior_pos: Optional[float] = None
                phase_posterior_pos: Optional[float] = None
                try:
                    payload = json.loads(row.get("payload_json") or "{}")
                    if "z_score" in payload and payload["z_score"] is not None:
                        z_score = float(payload["z_score"])
                    if "prior_pos" in payload and payload["prior_pos"] is not None:
                        phase_prior_pos = float(payload["prior_pos"])
                    if "posterior_pos" in payload and payload["posterior_pos"] is not None:
                        phase_posterior_pos = float(payload["posterior_pos"])
                except Exception:  # noqa: BLE001
                    pass

                # Only insert rows that carry at least one v2.0 signal value
                if z_score is None and phase_prior_pos is None:
                    continue

                try:
                    self._rs._conn.execute(
                        "INSERT OR REPLACE INTO structured_signals "
                        "(signal_id, asset_id, signal_date, signal_type, "
                        " z_score, phase_prior_pos, phase_posterior_pos) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (row["id"], asset_id, signal_date, signal_type,
                         z_score, phase_prior_pos, phase_posterior_pos),
                    )
                    counts["structured_signals"] += 1
                except Exception:  # noqa: BLE001
                    pass

            self._rs._conn.commit()

        finally:
            src.close()

        print(f"Signals seeded from {knowledge_db_path!r}:")
        for table, n in counts.items():
            print(f"  {table}: {n} rows")
        return counts

    def seed_signals_from_event_calendar(self) -> int:
        """
        Approach B — Synthetic signal seeder from the replay's own event calendar.

        For each asset in the universe that has at least one entry in the
        replay's ``historical_events`` table, this method creates a synthetic
        ``catalyst_events`` row with a conservative ``signal_strength`` derived
        from the asset's ``ranking_score`` and ``opportunity_score``.

        This ensures v2.0 scoring activates even when the live knowledge store
        has no signal data.  Conservative defaults keep the signal small
        (0.05–0.15) so the synthetic lift doesn't dominate the base composite.

        Formula
        -------
        ``signal_strength = (ranking_score + opportunity_score) / 2 * 0.25``

        For typical universe assets (ranking_score ≈ 0.6–0.7, opportunity_score
        ≈ 0.5–0.8) this yields signal_strength in [0.07, 0.15].

        Returns
        -------
        int — number of rows inserted.
        """
        import uuid as _uuid

        n_inserted = 0
        for u in self._universe:
            asset_id = u["asset_id"]
            ticker = u.get("ticker", "")
            ranking = float(u.get("ranking_score", 0.5))
            opportunity = float(u.get("opportunity_score", 0.5))
            signal_strength = round((ranking + opportunity) / 2.0 * 0.25, 4)

            # Find the earliest known catalyst date for this asset from
            # historical_events (use announced_at as the "known-by" date).
            rows = self._rs._conn.execute(
                "SELECT MIN(announced_at) as first_event FROM historical_events "
                "WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()

            if rows and rows["first_event"]:
                event_date = rows["first_event"][:10]
            else:
                # No events for this asset — skip synthetic seeding.
                continue

            event_id = str(_uuid.uuid4())
            try:
                self._rs._conn.execute(
                    "INSERT OR IGNORE INTO catalyst_events "
                    "(event_id, asset_id, ticker, event_type, event_date, signal_strength) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (event_id, asset_id, ticker, "trial_readout", event_date, signal_strength),
                )
                n_inserted += 1
            except Exception:  # noqa: BLE001
                pass

        self._rs._conn.commit()
        print(f"Synthetic signal seed: {n_inserted} rows inserted into catalyst_events.")
        return n_inserted

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(
        self,
        start: date,
        end: date,
        cadence: str = "weekly",
        decision_policy: str = "top2_add",
        profile: str = "standard",
    ) -> str:
        """
        Execute the replay loop from *start* to *end*.

        Parameters
        ----------
        start, end:
            Inclusive date range.
        cadence:
            "weekly" (advance 7 days per step) or "biweekly" (14 days).
        decision_policy:
            Policy name tag stored in run metadata.

        Returns
        -------
        run_id (str)
        """
        run_id = self._rs.create_run(
            start_date=start,
            end_date=end,
            cadence=cadence,
            decision_policy=decision_policy,
            score_version="v2.0",
            strategy_version=self._policy.config.name,
            run_metadata_json=json.dumps(
                {
                    "profile": profile,
                    "policy_config": _serialize_policy_config(self._policy.config),
                    "universe_snapshot": self._universe,
                    "no_lookahead_rule": "all replay queries require timestamp/date <= as_of",
                }
            ),
        )
        print(f"Replay run created: {run_id}")

        # Reset per-run processed-event set so re-running doesn't skip events
        self._resolved_event_ids: set[int] = set()
        self._policy.reset_run_state()

        clock = ReplayClock(start)
        n_steps = 0

        while clock.today() <= end:
            print(f"  Step {clock.today()} ...")
            # Resolve any thesis claims whose catalyst events have now fired,
            # BEFORE scoring so the composite score reflects current thesis_strength.
            n_resolved = self._step_claim_resolution(clock)
            if n_resolved:
                print(f"    Resolved {n_resolved} claim(s).")
            self._step_stop_loss(clock, run_id)
            decisions = self._step_decision(clock, run_id, self._universe)
            print(f"    Made {len(decisions)} decision(s).")
            self._step_resolve(clock, run_id)
            clock = ReplayClock(_advance_cadence(clock.today(), cadence))
            n_steps += 1

        # Final resolve pass at end date
        final_clock = ReplayClock(end)
        self._step_resolve(final_clock, run_id)

        print(f"Replay complete: {n_steps} steps, run_id={run_id}")
        return run_id

    # ------------------------------------------------------------------
    # Step helpers
    # ------------------------------------------------------------------

    def _step_decision(
        self,
        clock: ReplayClock,
        run_id: str,
        universe: list[dict],
    ) -> list[ReplayDecision]:
        """Run one decision step at the clock's current date."""
        ks = KnowledgeStore(self._ks_path)
        tt = ThesisTracker(ks)
        gen = ActionableGenerator(
            max_position_pct=self._policy.config.max_single_pct,
            min_position_pct=min(0.01, self._policy.config.max_single_pct),
        )

        as_of = clock.today()

        # Build candidates with time-frozen thesis snapshots
        candidates: list[ScoredCandidate] = []
        for u in universe:
            # Only rank assets that were actually tradable on this replay step.
            if self._rs.get_price(u["ticker"], as_of) is None:
                continue
            snap = tt.snapshot(u["asset_id"], as_of_date=as_of)
            n_resolved = snap.n_confirmed + snap.n_refuted + snap.n_expired
            thesis_strength = snap.thesis_strength if n_resolved > 0 else None
            company_snapshot = ks.get_company_sotp_snapshot_for_ticker_on_or_before(
                ticker=str(u["ticker"]),
                as_of=as_of,
            )
            candidates.append(ScoredCandidate(
                asset_id=u["asset_id"],
                ticker=u["ticker"],
                ranking_score=u.get("ranking_score", 0.5),
                opportunity_score=u.get("opportunity_score", 0.5),
                thesis_strength=thesis_strength,
                n_open_claims=snap.n_open,
                catalyst_description=u.get("catalyst", ""),
                indication=u.get("indication", ""),
                company_id=u.get("company_id", ""),
                company_action_policy=(
                    str(company_snapshot.get("action_policy"))
                    if company_snapshot and company_snapshot.get("action_policy")
                    else None
                ),
                company_action_reason=(
                    str(company_snapshot.get("action_reason"))
                    if company_snapshot and company_snapshot.get("action_reason")
                    else ""
                ),
                company_snapshot_date=(
                    company_snapshot.get("snapshot_date")
                    if company_snapshot is not None
                    else None
                ),
            ))

        # Build v2.0 composite score contexts (no-lookahead: all signals as of as_of)
        contexts = self._build_score_contexts(universe, as_of)

        report = gen.generate(candidates, top_n=20, week_ending=as_of, contexts=contexts)

        # Log v2.0 signal attribution summary for this step
        n_with_signals = sum(
            1 for opp in report.opportunities if opp.signal_adjustment_total != 0.0
        )
        if report.opportunities:
            mean_adj = sum(opp.signal_adjustment_total for opp in report.opportunities) / len(
                report.opportunities
            )
            sign = "+" if mean_adj >= 0 else ""
            print(
                f"    v2.0 signals: {n_with_signals}/{len(report.opportunities)} assets, "
                f"mean adjustment: {sign}{mean_adj:.3f}"
            )

        # Track open asset IDs from replay decisions
        open_decisions = self._rs.get_open_decisions(run_id)
        open_asset_ids = {d["asset_id"] for d in open_decisions}
        current_total_exposure = sum(float(d.get("size_pct") or 0.0) for d in open_decisions)

        # Build catalyst timing map if timing filter or density gate is enabled
        catalyst_dates: Optional[dict[str, date]] = None
        if self._policy.config.catalyst_timing or self._policy.config.require_catalyst_within_days > 0:
            catalyst_dates = self._rs.get_upcoming_catalysts(as_of)

        # XBI sector trend check
        xbi_above_ma: Optional[bool] = None
        if self._policy.config.xbi_filter:
            xbi_price = self._rs.get_price("XBI", as_of)
            xbi_ma = self._rs.get_ma("XBI", as_of, window_days=20)
            if xbi_price is not None and xbi_ma is not None:
                xbi_above_ma = xbi_price >= xbi_ma

        # Build cooling set: assets blocked for N days after consecutive thesis_errors.
        # Rule: 1 thesis_error → cool for 7 days; 2+ consecutive → cool for 14 days.
        # We measure from the exit_date of the most recent thesis_error trade.
        cooling_asset_ids: Optional[set] = None
        if self._policy.config.cooling_enabled:
            from datetime import timedelta as _td
            cooling_asset_ids = set()
            for u in universe:
                aid = u["asset_id"]
                recent = self._rs.get_recent_attributions(run_id, aid, limit=5)
                if not recent:
                    continue
                # Count consecutive thesis_errors from most recent backward
                consecutive = 0
                last_exit: Optional[date] = None
                for rec in recent:
                    if rec["attribution_type"] == "thesis_error":
                        if consecutive == 0:
                            try:
                                last_exit = date.fromisoformat(str(rec["exit_date"])[:10])
                            except (ValueError, TypeError):
                                pass
                        consecutive += 1
                    else:
                        break
                if consecutive == 0 or last_exit is None:
                    continue
                # Determine cooling window: 1 error → 7 days, 2+ → 14 days
                cool_days = 14 if consecutive >= 2 else 7
                if as_of < last_exit + _td(days=cool_days):
                    cooling_asset_ids.add(aid)

        decisions = self._policy.select(
            report,
            open_asset_ids=open_asset_ids,
            current_total_exposure=current_total_exposure,
            catalyst_dates=catalyst_dates,
            xbi_above_ma=xbi_above_ma,
            cooling_asset_ids=cooling_asset_ids,
        )

        # Persist each decision
        universe_by_asset = {u["asset_id"]: u for u in universe}
        for dec in decisions:
            upcoming = self._rs.get_nearest_upcoming_event(dec.asset_id, as_of)
            if upcoming is not None:
                try:
                    event_date = date.fromisoformat(str(upcoming["announced_at"])[:10])
                    dec.days_to_catalyst_at_entry = (event_date - as_of).days
                except (TypeError, ValueError):
                    dec.days_to_catalyst_at_entry = None
                dec.catalyst_event_id = str(upcoming.get("event_id") or "")
                dec.decision_cluster_id = f"{dec.ticker}_{dec.catalyst_event_id}"
            else:
                dec.decision_cluster_id = f"{dec.ticker}_no_catalyst"
            raw_phase = universe_by_asset.get(dec.asset_id, {}).get("phase")
            dec.phase = str(raw_phase) if raw_phase not in (None, "") else None
            entry_price = self._rs.get_price(dec.ticker, as_of)
            self._rs.insert_decision(run_id, dec, entry_price)

        ks.close()
        return decisions

    def _build_score_contexts(
        self,
        universe: list[dict],
        as_of: date,
    ) -> "dict[str, CompositeScoreContext]":
        """
        Build a ``CompositeScoreContext`` for each asset in *universe* using
        only data available at *as_of* (no-lookahead).

        All six signal fields are populated from the replay store's signal
        tables.  When a table has no data for an asset, the corresponding
        field is left at its None/False default, which produces a neutral
        (zero) adjustment in CompositeScorer.

        Returns a dict mapping asset_id → CompositeScoreContext.
        """
        from bve.intelligence.composite_scorer import CompositeScoreContext
        from bve.intelligence.capital_structure import CapitalRiskLevel

        contexts: dict[str, CompositeScoreContext] = {}
        for u in universe:
            asset_id = u["asset_id"]

            # Signal 1: highest own-asset catalyst signal_strength on or before as_of
            cat_strength = self._rs.get_catalyst_signal_strength(asset_id, as_of)

            # Signal 2: enrollment flags from latest snapshot on or before as_of
            enroll = self._rs.get_enrollment_flags(asset_id, as_of)

            # Signal 3: phase correlation prior/posterior from structured_signals
            prior_pos, posterior_pos = self._rs.get_phase_correlation(asset_id, as_of)

            # Signal 4: endpoint z-score from structured_signals
            z_score = self._rs.get_endpoint_z_score(asset_id, as_of)

            # Signal 5: competitor COMPETITOR_READOUT signals within 60 days of as_of
            comp_signals = self._rs.get_competitor_signals(asset_id, as_of, window_days=60)

            # Signal 6: capital risk level from capital_snapshots
            cap_risk_raw = self._rs.get_capital_risk_level(asset_id, as_of)
            cap_risk: Optional[CapitalRiskLevel] = None
            if cap_risk_raw is not None:
                try:
                    cap_risk = CapitalRiskLevel(cap_risk_raw)
                except ValueError:
                    pass

            contexts[asset_id] = CompositeScoreContext(
                catalyst_signal_strength=cat_strength,
                enrollment_site_stalling=enroll.get("site_stalling", False) if enroll else False,
                enrollment_velocity_low=enroll.get("velocity_low", False) if enroll else False,
                enrollment_slippage_alert=enroll.get("slippage_alert", False) if enroll else False,
                phase_prior_pos=prior_pos,
                phase_posterior_pos=posterior_pos,
                endpoint_z_score=z_score,
                competitor_signal_strengths=comp_signals,
                capital_risk=cap_risk,
            )

        return contexts

    def _step_resolve(self, clock: ReplayClock, run_id: str) -> None:
        """Check all open decisions; close those whose exit date has passed."""
        as_of = clock.today()
        open_decisions = self._rs.get_open_decisions(run_id)

        for dec in open_decisions:
            entry_date_str = dec.get("decided_at", "")
            try:
                entry_date = date.fromisoformat(str(entry_date_str)[:10])
            except (ValueError, TypeError):
                continue

            exit_target = self._policy.exit_date(entry_date)
            if as_of < exit_target:
                continue

            # Look up actual exit price
            exit_price = self._rs.get_price(dec["ticker"], as_of)
            entry_price = dec.get("entry_price")

            return_pct = self._rs.compute_return_pct(entry_price, exit_price)
            from bve.analysis.friction_model import INSTITUTIONAL_FRICTIONS

            friction_cost_bps = INSTITUTIONAL_FRICTIONS.round_trip_cost_bps
            net_return_pct = (
                INSTITUTIONAL_FRICTIONS.net_return(return_pct)
                if return_pct is not None else None
            )
            xbi_return = self._rs.get_return("XBI", entry_date, as_of)
            ibb_return = self._rs.get_return("IBB", entry_date, as_of)
            spy_return = self._rs.get_return("SPY", entry_date, as_of)
            xbi_entry = self._rs.get_price("XBI", entry_date)
            xbi_ma = self._rs.get_ma("XBI", entry_date, window_days=20)
            xbi_above_ma = (
                xbi_entry >= xbi_ma
                if xbi_entry is not None and xbi_ma is not None else None
            )

            # Check for events within the hold window (entry → exit) only.
            # Using all-history events would attribute a June catalyst to an
            # October position — causal contamination.
            events = self._rs.get_events_in_window(dec["asset_id"], entry_date, as_of)
            has_event = len(events) > 0
            event_outcome = events[-1]["outcome_label"] if events else None

            attribution = self._classify_return(return_pct, has_event, event_outcome)

            self._rs.close_decision(
                decision_id=dec["decision_id"],
                exit_price=exit_price,
                exit_date=as_of,
                return_pct=return_pct,
                attribution_type=attribution,
                xbi_return_during_hold=xbi_return,
                ibb_return_during_hold=ibb_return,
                spy_return_during_hold=spy_return,
                xbi_above_20d_ma_at_entry=xbi_above_ma,
                friction_cost_bps=friction_cost_bps,
                net_return_pct=net_return_pct,
            )
            self._policy.record_closed_position(
                asset_id=str(dec["asset_id"]),
                exit_date=as_of,
                return_pct=return_pct,
            )

    def _step_stop_loss(self, clock: ReplayClock, run_id: str) -> int:
        """
        Check open positions for stop-loss exits before making new decisions.

        Uses the latest available close on or before the current step date to
        compute unrealized P&L with no lookahead.
        """
        as_of = clock.today()
        open_decisions = self._rs.get_open_decisions(run_id)
        triggered = 0

        for dec in open_decisions:
            current_price = self._rs.get_price(str(dec["ticker"]), as_of)
            unrealized_return = self._rs.compute_return_pct(
                dec.get("entry_price"),
                current_price,
            )
            if unrealized_return is None:
                continue
            if unrealized_return > self._policy.config.stop_loss_pct:
                continue

            asset_id = str(dec["asset_id"])
            from bve.analysis.friction_model import INSTITUTIONAL_FRICTIONS

            friction_cost_bps = INSTITUTIONAL_FRICTIONS.round_trip_cost_bps
            net_return_pct = INSTITUTIONAL_FRICTIONS.net_return(unrealized_return)
            print(f"Stop-loss triggered: {asset_id} at {unrealized_return:.1f}%")
            self._rs.close_decision(
                decision_id=str(dec["decision_id"]),
                exit_price=current_price,
                exit_date=as_of,
                return_pct=unrealized_return,
                attribution_type="stop_loss",
                friction_cost_bps=friction_cost_bps,
                net_return_pct=net_return_pct,
            )
            self._policy.record_closed_position(
                asset_id=asset_id,
                exit_date=as_of,
                return_pct=unrealized_return,
                force_loss_block=True,
            )
            triggered += 1

        return triggered

    def _step_claim_resolution(self, clock: ReplayClock) -> int:
        """
        Resolve thesis claims whose catalyst events have fired as of this step.

        Scans ``historical_events`` for all events with ``announced_at <= as_of``
        and maps each event's ``outcome_label`` to a claim resolution status:

        - ``"positive"`` / ``"success"`` → ``"confirmed"``
        - ``"negative"`` / ``"fail"``    → ``"refuted"``

        Only processes each event once: an event is skipped if its asset already
        has a claim resolved to a terminal state (confirmed / refuted / expired)
        that was resolved on or before ``announced_at``.  This prevents
        re-processing events across replay runs via a per-run processed-events
        set tracked on the instance.

        Returns the number of claims newly resolved in this step.
        """
        as_of = clock.today()

        # Guard: ensure set exists if called outside run() (e.g. in tests)
        if not hasattr(self, "_resolved_event_ids"):
            self._resolved_event_ids = set()

        # Fetch all events up to as_of not yet processed
        rows = self._rs._conn.execute(
            "SELECT rowid, asset_id, outcome_label, announced_at, headline "
            "FROM historical_events "
            "WHERE announced_at <= ?",
            (as_of.isoformat(),),
        ).fetchall()

        ks = KnowledgeStore(self._ks_path)
        tt = ThesisTracker(ks)
        n_resolved = 0

        for row in rows:
            row = dict(row)
            rowid = row["rowid"]
            if rowid in self._resolved_event_ids:
                continue

            outcome = (row["outcome_label"] or "").lower()
            if "positive" in outcome or "success" in outcome:
                claim_status = "confirmed"
            elif "negative" in outcome or "fail" in outcome:
                claim_status = "refuted"
            else:
                # Neutral / enrollment events — don't resolve the claim
                self._resolved_event_ids.add(rowid)
                continue

            asset_id = row["asset_id"]
            # Find the open claim for this asset
            open_claims = tt.get_claims(asset_id=asset_id, status="open")
            if not open_claims:
                # Already resolved or no claim — mark processed so we skip next time
                self._resolved_event_ids.add(rowid)
                continue

            # Resolve the most recent open claim
            claim = open_claims[-1]
            try:
                announced_dt = datetime.fromisoformat(str(row["announced_at"])[:10])
            except (ValueError, TypeError):
                announced_dt = datetime.now(timezone.utc)
            resolved_at = datetime(
                announced_dt.year, announced_dt.month, announced_dt.day,
                tzinfo=timezone.utc,
            )
            tt.resolve_claim(
                claim_id=claim.claim_id,
                status=claim_status,
                evidence=row["headline"][:200] if row["headline"] else "",
                resolved_at=resolved_at,
            )
            self._resolved_event_ids.add(rowid)
            n_resolved += 1

        ks.close()
        return n_resolved

    @staticmethod
    def _classify_return(
        return_pct: Optional[float],
        has_event: bool,
        event_outcome: Optional[str],
    ) -> str:
        """Rule-based attribution classification."""
        if has_event and event_outcome:
            outcome_lower = event_outcome.lower()
            if return_pct is not None and return_pct > 0:
                if "positive" in outcome_lower or "success" in outcome_lower:
                    return "confirmed_thesis"
                if "negative" in outcome_lower or "fail" in outcome_lower:
                    return "market_drift"
            elif return_pct is not None and return_pct <= 0:
                if "negative" in outcome_lower or "fail" in outcome_lower:
                    return "pos_error"
                if "positive" in outcome_lower or "success" in outcome_lower:
                    return "timing_error"
        if return_pct is None:
            return "unclassified"
        # No event data — can't confirm thesis; classify by direction
        if return_pct > 0:
            return "market_drift"   # moved up but no event to attribute it to
        return "thesis_error"       # position lost without a resolved catalyst

    # ------------------------------------------------------------------
    # Summarize
    # ------------------------------------------------------------------

    def summarize(self, run_id: str) -> ReplaySummary:
        """Build a ReplaySummary for a completed run."""
        from bve.intelligence.actionable_output import CURRENT_SCORE_VERSION

        run = self._rs.get_run(run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")

        all_decisions = self._rs.get_run_decisions(run_id)
        closed = [d for d in all_decisions if d["is_closed"]]
        actionable = [d for d in all_decisions if d["action"] in ("buy", "add")]

        # Attribution counts
        attribution_counts: dict[str, int] = {
            "confirmed_thesis": 0,
            "pos_error": 0,
            "timing_error": 0,
            "thesis_error": 0,
            "market_drift": 0,
            "stop_loss": 0,
            "unclassified": 0,
        }
        returns: list[float] = []
        net_returns: list[float] = []
        friction_costs: list[float] = []
        returns_by_action: dict[str, list[float]] = {}
        returns_by_attribution: dict[str, list[float]] = {}
        returns_by_tier: dict[str, list[float]] = {}
        brier_terms: list[float] = []

        for d in closed:
            attr = d.get("attribution_type") or "unclassified"
            if attr in attribution_counts:
                attribution_counts[attr] += 1
            else:
                attribution_counts["unclassified"] += 1

            r = d.get("return_pct")
            if r is not None:
                realized_return = float(r)
                returns.append(realized_return)
                returns_by_attribution.setdefault(attr, []).append(realized_return)
                action = d.get("action", "unknown")
                returns_by_action.setdefault(action, []).append(realized_return)
                tier = _tier_for_score(d.get("composite_score"))
                returns_by_tier.setdefault(tier, []).append(realized_return)
                predicted = max(0.0, min(1.0, _coerce_float(d.get("composite_score"), 0.0)))
                actual = 1.0 if realized_return > 0.0 else 0.0
                brier_terms.append((predicted - actual) ** 2)
            if d.get("net_return_pct") is not None:
                net_returns.append(float(d["net_return_pct"]))
            if d.get("friction_cost_bps") is not None:
                friction_costs.append(float(d["friction_cost_bps"]))

        mean_return = (sum(returns) / len(returns)) if returns else None
        net_mean_return = (sum(net_returns) / len(net_returns)) if net_returns else None
        friction_mean = (sum(friction_costs) / len(friction_costs)) if friction_costs else None
        hit_rate = (
            sum(1 for r in returns if r > 0) / len(returns)
            if returns else None
        )
        total_abs_pnl = sum(abs(r) for values in returns_by_attribution.values() for r in values)
        mean_by_attr: dict[str, Optional[float]] = {}
        median_by_attr: dict[str, Optional[float]] = {}
        pnl_by_attr: dict[str, Optional[float]] = {}
        for attr, values in returns_by_attribution.items():
            mean_by_attr[attr] = round(statistics.mean(values), 4) if values else None
            median_by_attr[attr] = round(statistics.median(values), 4) if values else None
            pnl_by_attr[attr] = (
                round(sum(values) / total_abs_pnl, 6)
                if values and total_abs_pnl > 0 else None
            )

        cluster_ids: set[str] = set()
        independent_n = 0
        for d in closed:
            cid = d.get("decision_cluster_id")
            if cid and not str(cid).endswith("_no_catalyst"):
                cluster_ids.add(str(cid))
            else:
                independent_n += 1
        independent_n += len(cluster_ids)

        # Skill-adjusted return excludes pos_error and market_drift so beta/luck
        # cannot inflate stated model skill.
        skill_returns: list[float] = []
        for d in closed:
            attr = d.get("attribution_type") or "unclassified"
            r = d.get("net_return_pct")
            if r is None:
                r = d.get("return_pct")
            if r is not None and attr not in {"pos_error", "market_drift"}:
                skill_returns.append(float(r))
        skill_mean = (sum(skill_returns) / len(skill_returns)) if skill_returns else None

        # Estimate n_decision_dates from run metadata
        start = date.fromisoformat(run["start_date"])
        end = date.fromisoformat(run["end_date"])
        cadence = run.get("cadence", "weekly")
        n_dates = _count_decision_dates(start, end, cadence)
        run_metadata = self._load_run_metadata(run)
        mna_metrics = self._compute_mna_metrics(
            all_decisions=all_decisions,
            start_date=start,
            end_date=end,
            run_metadata=run_metadata,
        )

        summary = ReplaySummary(
            run_id=run_id,
            start_date=start,
            end_date=end,
            strategy_version=run.get("strategy_version", "unknown"),
            score_version=run.get("score_version", CURRENT_SCORE_VERSION),
            n_decision_dates=n_dates,
            n_decisions=len(all_decisions),
            n_actionable=len(actionable),
            n_resolved=len(closed),
            mean_return_pct=round(mean_return, 4) if mean_return is not None else None,
            gross_mean_return_pct=round(mean_return, 4) if mean_return is not None else None,
            net_mean_return_pct=(
                round(net_mean_return, 4) if net_mean_return is not None else None
            ),
            friction_cost_mean_bps=round(friction_mean, 4) if friction_mean is not None else None,
            hit_rate=round(hit_rate, 4) if hit_rate is not None else None,
            brier_score=round(sum(brier_terms) / len(brier_terms), 6) if brier_terms else None,
            max_drawdown_pct=round(_max_drawdown_from_return_pcts(returns), 4),
            avg_return_by_tier={
                tier: round(sum(values) / len(values), 4)
                for tier, values in sorted(returns_by_tier.items())
                if values
            },
            mna_precision_at_k=mna_metrics["precision_at_k"],
            mna_top_k=mna_metrics["top_k"],
            mna_acquirer_top1_accuracy=mna_metrics["acquirer_top1_accuracy"],
            mna_acquirer_top3_accuracy=mna_metrics["acquirer_top3_accuracy"],
            n_dead_or_acquired_names_in_universe=mna_metrics["n_labeled_names"],
            n_confirmed_thesis=attribution_counts["confirmed_thesis"],
            n_pos_error=attribution_counts["pos_error"],
            n_timing_error=attribution_counts["timing_error"],
            n_thesis_error=attribution_counts["thesis_error"],
            n_market_drift=attribution_counts["market_drift"],
            n_stop_loss=attribution_counts["stop_loss"],
            n_unclassified=attribution_counts["unclassified"],
            returns_by_action={k: v for k, v in returns_by_action.items()},
            returns_by_attribution=returns_by_attribution,
            mean_return_by_attribution=mean_by_attr,
            median_return_by_attribution=median_by_attr,
            pnl_contribution_by_attribution=pnl_by_attr,
            n_independent_decisions=independent_n,
            skill_adjusted_mean_return_pct=(
                round(skill_mean, 4) if skill_mean is not None else None
            ),
            n_skill_adjusted_decisions=len(skill_returns),
            validation_status="directional_only",
            notes=[
                "point_in_time_only=historical_prices,historical_events,and signal snapshots use <= as_of_date",
                "dated_snapshots_only=true",
                "skill_adjusted_return_excludes=pos_error_and_market_drift_decisions",
                *mna_metrics["notes"],
            ],
        )
        return summary

    @staticmethod
    def _load_run_metadata(run: dict[str, Any]) -> dict[str, Any]:
        raw = run.get("run_metadata_json")
        if not raw:
            return {}
        try:
            value = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _normalize_text(value: object) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).strip().lower().split())
        return normalized or None

    def _compute_mna_metrics(
        self,
        *,
        all_decisions: list[dict[str, Any]],
        start_date: date,
        end_date: date,
        run_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        notes: list[str] = []
        universe_snapshot = run_metadata.get("universe_snapshot")
        if not isinstance(universe_snapshot, list):
            universe_snapshot = self._universe

        policy_cfg = run_metadata.get("policy_config")
        max_positions = 0
        lookahead_days = 365
        if isinstance(policy_cfg, dict):
            try:
                max_positions = int(policy_cfg.get("max_positions") or 0)
            except (TypeError, ValueError):
                max_positions = 0
            try:
                lookahead_days = int(policy_cfg.get("max_hold_days") or 365)
            except (TypeError, ValueError):
                lookahead_days = 365
        if max_positions <= 0:
            max_positions = max(1, self._policy.config.max_positions)

        labels_by_asset: dict[str, dict[str, Any]] = {}
        labels_by_ticker: dict[str, dict[str, Any]] = {}
        n_labeled_names = 0
        for raw in universe_snapshot:
            if not isinstance(raw, dict):
                continue
            announcement_raw = raw.get("announcement_date")
            acquirer_raw = raw.get("acquirer")
            if not announcement_raw and not acquirer_raw:
                continue
            try:
                announcement_date = (
                    date.fromisoformat(str(announcement_raw))
                    if announcement_raw not in (None, "")
                    else None
                )
            except ValueError:
                announcement_date = None
            label = {
                "announcement_date": announcement_date,
                "acquirer": acquirer_raw,
            }
            asset_id = str(raw.get("asset_id") or "").strip()
            ticker = str(raw.get("ticker") or "").strip().upper()
            if asset_id:
                labels_by_asset[asset_id] = label
            if ticker:
                labels_by_ticker[ticker] = label
            n_labeled_names += 1

        if not all_decisions:
            return {
                "precision_at_k": None,
                "top_k": max_positions,
                "acquirer_top1_accuracy": None,
                "acquirer_top3_accuracy": None,
                "n_labeled_names": n_labeled_names,
                "notes": notes,
            }

        from bve.intelligence.knowledge_layer import KnowledgeStore

        def _lookup_label(decision: dict[str, Any]) -> dict[str, Any] | None:
            asset_id = str(decision.get("asset_id") or "").strip()
            ticker = str(decision.get("ticker") or "").strip().upper()
            return labels_by_asset.get(asset_id) or labels_by_ticker.get(ticker)

        decisions_by_date: dict[date, list[dict[str, Any]]] = {}
        for decision in all_decisions:
            try:
                decided_at = date.fromisoformat(str(decision["decided_at"])[:10])
            except (KeyError, TypeError, ValueError):
                continue
            decisions_by_date.setdefault(decided_at, []).append(decision)

        top_total = 0
        top_hits = 0
        positive_with_acquirer = 0
        acquirer_top1_hits = 0
        ks = KnowledgeStore(self._ks_path)
        try:
            rows = ks._conn.execute(
                """
                SELECT asset_id, ticker, snapshot_date, best_acquirer_id, best_acquirer_name, created_at
                FROM ma_probability_snapshots
                WHERE snapshot_date <= ? AND snapshot_date >= ?
                ORDER BY snapshot_date ASC, rank ASC, asset_id ASC
                """,
                (end_date.isoformat(), start_date.isoformat()),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []

        snapshots_by_asset: dict[str, list[dict[str, Any]]] = {}
        snapshots_by_ticker: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            record = dict(row)
            snapshots_by_asset.setdefault(str(record.get("asset_id") or ""), []).append(record)
            ticker = str(record.get("ticker") or "").strip().upper()
            if ticker:
                snapshots_by_ticker.setdefault(ticker, []).append(record)

        for values in snapshots_by_asset.values():
            values.sort(key=lambda item: (item["snapshot_date"], item["created_at"]))
        for values in snapshots_by_ticker.values():
            values.sort(key=lambda item: (item["snapshot_date"], item["created_at"]))

        def _latest_prediction(decision: dict[str, Any]) -> dict[str, Any] | None:
            try:
                decided_at = date.fromisoformat(str(decision["decided_at"])[:10])
            except (KeyError, TypeError, ValueError):
                return None
            asset_id = str(decision.get("asset_id") or "")
            ticker = str(decision.get("ticker") or "").strip().upper()
            candidates = snapshots_by_asset.get(asset_id) or snapshots_by_ticker.get(ticker) or []
            best: dict[str, Any] | None = None
            for item in candidates:
                try:
                    snapshot_date = date.fromisoformat(str(item["snapshot_date"]))
                    created_at = ks._coerce_datetime(item["created_at"])
                except (TypeError, ValueError):
                    continue
                if snapshot_date > decided_at or created_at.date() > decided_at:
                    continue
                best = item
            return best

        for decided_at in sorted(decisions_by_date):
            ranked = sorted(
                decisions_by_date[decided_at],
                key=lambda row: (
                    -_coerce_float(row.get("composite_score"), 0.0),
                    str(row.get("ticker") or ""),
                ),
            )
            top_rows = ranked[:max_positions]
            top_total += len(top_rows)
            for row in top_rows:
                label = _lookup_label(row)
                if not label:
                    continue
                announced_at = label.get("announcement_date")
                if not isinstance(announced_at, date):
                    continue
                if announced_at <= decided_at:
                    continue
                if announced_at > min(end_date, decided_at + timedelta(days=lookahead_days)):
                    continue
                top_hits += 1
                actual_acquirer = self._normalize_text(label.get("acquirer"))
                predicted = _latest_prediction(row)
                predicted_acquirer = None
                if predicted is not None:
                    predicted_acquirer = self._normalize_text(
                        predicted.get("best_acquirer_name") or predicted.get("best_acquirer_id")
                    )
                if actual_acquirer is not None and predicted_acquirer is not None:
                    positive_with_acquirer += 1
                    if actual_acquirer == predicted_acquirer:
                        acquirer_top1_hits += 1

        ks.close()
        if rows:
            notes.append("mna_predictions=ma_probability_snapshots_as_of_decision_date")
        else:
            notes.append("mna_predictions=unavailable_no_ma_probability_snapshots")
        notes.append(f"mna_dead_or_acquired_names_in_universe={n_labeled_names}")
        if positive_with_acquirer > 0:
            notes.append("mna_top3_equals_top1_until_multi_acquirer_candidates_are_persisted")

        return {
            "precision_at_k": round(top_hits / top_total, 6) if top_total > 0 else None,
            "top_k": max_positions,
            "acquirer_top1_accuracy": (
                round(acquirer_top1_hits / positive_with_acquirer, 6)
                if positive_with_acquirer > 0
                else None
            ),
            "acquirer_top3_accuracy": (
                round(acquirer_top1_hits / positive_with_acquirer, 6)
                if positive_with_acquirer > 0
                else None
            ),
            "n_labeled_names": n_labeled_names,
            "notes": notes,
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _advance_cadence(current: date, cadence: str) -> date:
    normalized = str(cadence or "weekly").strip().lower()
    if normalized == "weekly":
        return current + timedelta(days=7)
    if normalized == "biweekly":
        return current + timedelta(days=14)
    if normalized == "quarterly":
        return _add_months(current, 3)
    raise ValueError(f"Unsupported replay cadence: {cadence!r}")


def _count_decision_dates(start: date, end: date, cadence: str) -> int:
    if start > end:
        return 1
    n_dates = 0
    current = start
    while current <= end:
        n_dates += 1
        current = _advance_cadence(current, cadence)
    return max(1, n_dates)


def _coerce_float(raw: object, default: float) -> float:
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _normalize_claim_type(raw: object) -> ClaimType:
    if isinstance(raw, ClaimType):
        return raw

    label = str(raw or "efficacy").strip().lower()
    mapping = {
        "efficacy": ClaimType.ENDPOINT_MET,
        "endpoint": ClaimType.ENDPOINT_MET,
        "endpoint_met": ClaimType.ENDPOINT_MET,
        "readout": ClaimType.ENDPOINT_MET,
        "regulatory": ClaimType.REGULATORY_PATHWAY,
        "regulatory_pathway": ClaimType.REGULATORY_PATHWAY,
        "fda": ClaimType.REGULATORY_PATHWAY,
        "competitor": ClaimType.COMPETITOR_FAILURE,
        "competition": ClaimType.COMPETITOR_FAILURE,
        "competitor_failure": ClaimType.COMPETITOR_FAILURE,
        "label_expansion": ClaimType.LABEL_EXPANSION,
        "enrollment": ClaimType.ENROLLMENT_ON_TRACK,
        "enrollment_on_track": ClaimType.ENROLLMENT_ON_TRACK,
        "market_reaction": ClaimType.MARKET_REACTION_POSITIVE,
        "market_reaction_positive": ClaimType.MARKET_REACTION_POSITIVE,
        "valuation": ClaimType.POS_ABOVE_THRESHOLD,
        "pos_above_threshold": ClaimType.POS_ABOVE_THRESHOLD,
        "custom": ClaimType.CUSTOM,
    }
    return mapping.get(label, ClaimType.CUSTOM)


def _tier_for_score(score: object) -> str:
    value = _coerce_float(score, 0.0)
    if value >= 0.70:
        return "high"
    if value >= 0.50:
        return "medium"
    return "low"


def _max_drawdown_from_return_pcts(return_pcts: list[float]) -> float:
    if not return_pcts:
        return 0.0
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for return_pct in return_pcts:
        equity *= 1.0 + (return_pct / 100.0)
        peak = max(peak, equity)
        if peak <= 0.0:
            continue
        max_drawdown = max(max_drawdown, (peak - equity) / peak)
    return max_drawdown * 100.0


def _serialize_policy_config(config: ReplayPolicyConfig) -> dict[str, Any]:
    payload = asdict(config)
    payload["actionable_actions"] = sorted(str(item) for item in config.actionable_actions)
    return payload


def _normalize_universe_entry(raw: dict[str, Any]) -> dict[str, Any]:
    ticker = str(raw.get("ticker") or "").strip().upper()
    asset_id = str(raw.get("asset_id") or "").strip()
    if not ticker:
        raise ValueError("Universe entry missing required field: ticker")
    if not asset_id:
        raise ValueError(f"Universe entry for ticker={ticker} missing required field: asset_id")

    company_id_raw = raw.get("company_id")
    company_id = (
        str(company_id_raw).strip()
        if company_id_raw not in (None, "")
        else f"{ticker.lower()}-auto"
    )
    conviction = raw.get("conviction", 0.50)
    if conviction in (None, ""):
        conviction = 0.50

    return {
        **raw,
        "ticker": ticker,
        "company_id": company_id,
        "asset_id": asset_id,
        "ranking_score": _coerce_float(raw.get("ranking_score"), 0.50),
        "opportunity_score": _coerce_float(raw.get("opportunity_score"), 0.50),
        "conviction": conviction,
        "claim_type": _normalize_claim_type(raw.get("claim_type", "efficacy")),
        "claim_assertion": str(raw.get("claim_assertion") or ""),
        "catalyst": str(raw.get("catalyst") or ""),
        "indication": str(raw.get("indication") or ""),
    }


def load_replay_universe(universe_file: Optional[str] = None) -> list[dict[str, Any]]:
    """
    Load and normalize the replay universe.

    When *universe_file* is not provided, falls back to ``weekly_runner.UNIVERSE``
    for backward compatibility.
    """
    if universe_file is None:
        from bve.ops.weekly_runner import UNIVERSE

        return [_normalize_universe_entry(dict(entry)) for entry in UNIVERSE]

    path = Path(universe_file)
    raw_text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(raw_text)
    else:
        payload = yaml.safe_load(raw_text)

    records: Any = payload
    if isinstance(payload, dict):
        records = payload.get("universe") or payload.get("assets") or []
    if not isinstance(records, list):
        raise ValueError("Replay universe file must be a list or contain an 'assets'/'universe' list")
    normalized: list[dict[str, Any]] = []
    for idx, entry in enumerate(records):
        if not isinstance(entry, dict):
            raise ValueError(f"Replay universe entry at index {idx} must be an object")
        normalized.append(_normalize_universe_entry(dict(entry)))
    return normalized


def _cmd_seed(args: list[str]) -> None:
    """seed --tickers T1 T2 ... --start YYYY-MM-DD --end YYYY-MM-DD"""
    tickers: list[str] = []
    start: Optional[date] = None
    end: Optional[date] = None

    i = 0
    while i < len(args):
        if args[i] == "--tickers":
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                tickers.append(args[i])
                i += 1
        elif args[i] == "--start":
            start = _parse_date(args[i + 1])
            i += 2
        elif args[i] == "--end":
            end = _parse_date(args[i + 1])
            i += 2
        else:
            i += 1

    if not tickers or not start or not end:
        print("Usage: seed --tickers T1 T2 ... --start YYYY-MM-DD --end YYYY-MM-DD")
        sys.exit(1)

    _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    rs = ReplayStore(str(REPLAY_STORE_PATH))

    from bve.ops.weekly_runner import UNIVERSE

    replay = HistoricalReplay(rs, str(REPLAY_KNOWLEDGE_PATH), universe=UNIVERSE)
    print(f"Seeding prices for {tickers} ({start} → {end})...")
    replay.seed_prices(tickers, start, end)
    replay.seed_claims(UNIVERSE, start)
    rs.close()
    print("Seed complete.")


def _cmd_run(args: list[str]) -> None:
    """run --start YYYY-MM-DD --end YYYY-MM-DD [--profile standard|mna] [--universe-file PATH] [--cadence weekly|biweekly|quarterly] [--decision-policy NAME]"""
    start: Optional[date] = None
    end: Optional[date] = None
    cadence: Optional[str] = None
    policy: Optional[str] = None
    max_hold_days: Optional[int] = None
    max_positions: Optional[int] = None
    max_open_positions: Optional[int] = None
    max_single_pct: Optional[float] = None
    max_total_exposure_pct: Optional[float] = None
    loss_block_threshold_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    catalyst_timing = False
    xbi_filter = False
    cooling = False
    require_catalyst_days = 0
    max_decisions_per_asset = 0
    min_thesis_score = 0.0
    require_open_claim = False
    universe_file: Optional[str] = None
    profile = "standard"

    i = 0
    while i < len(args):
        if args[i] == "--start":
            start = _parse_date(args[i + 1])
            i += 2
        elif args[i] == "--end":
            end = _parse_date(args[i + 1])
            i += 2
        elif args[i] == "--cadence":
            cadence = args[i + 1]
            i += 2
        elif args[i] == "--decision-policy":
            policy = args[i + 1]
            i += 2
        elif args[i] == "--profile":
            profile = args[i + 1]
            i += 2
        elif args[i] == "--max-hold-days":
            max_hold_days = int(args[i + 1])
            i += 2
        elif args[i] == "--max-positions":
            max_positions = int(args[i + 1])
            i += 2
        elif args[i] == "--max-open-positions":
            max_open_positions = int(args[i + 1])
            i += 2
        elif args[i] == "--max-single-pct":
            max_single_pct = float(args[i + 1])
            i += 2
        elif args[i] == "--max-total-exposure-pct":
            max_total_exposure_pct = float(args[i + 1])
            i += 2
        elif args[i] == "--loss-block-threshold-pct":
            loss_block_threshold_pct = float(args[i + 1])
            i += 2
        elif args[i] == "--stop-loss-pct":
            stop_loss_pct = float(args[i + 1])
            i += 2
        elif args[i] == "--catalyst-timing":
            catalyst_timing = True
            i += 1
        elif args[i] == "--xbi-filter":
            xbi_filter = True
            i += 1
        elif args[i] == "--cooling":
            cooling = True
            i += 1
        elif args[i] in ("--require-catalyst-days", "--require-catalyst-within-days"):
            require_catalyst_days = int(args[i + 1])
            i += 2
        elif args[i] == "--max-decisions-per-asset":
            max_decisions_per_asset = int(args[i + 1])
            i += 2
        elif args[i] == "--min-thesis-score":
            min_thesis_score = float(args[i + 1])
            i += 2
        elif args[i] == "--require-open-claim":
            require_open_claim = True
            i += 1
        elif args[i] == "--universe-file":
            universe_file = args[i + 1]
            i += 2
        else:
            i += 1

    if not start or not end:
        print("Usage: run --start YYYY-MM-DD --end YYYY-MM-DD [--profile standard|mna] [--universe-file PATH] [--cadence weekly|biweekly|quarterly] [--max-hold-days N]")
        sys.exit(1)

    _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    rs = ReplayStore(str(REPLAY_STORE_PATH))
    universe = load_replay_universe(universe_file)

    if profile == "mna":
        policy_cfg = ReplayPolicyConfig.mna_profile()
    elif profile == "standard":
        policy_cfg = ReplayPolicyConfig()
    else:
        raise ValueError(f"Unsupported replay profile: {profile!r}")

    resolved_cadence = cadence or ("quarterly" if profile == "mna" else "weekly")
    if policy is not None:
        policy_cfg.name = policy
    if max_hold_days is not None:
        policy_cfg.max_hold_days = max_hold_days
    if max_positions is not None:
        policy_cfg.max_positions = max_positions
    if max_open_positions is not None:
        policy_cfg.max_open_positions = max_open_positions
    if max_single_pct is not None:
        policy_cfg.max_single_pct = max_single_pct
    if max_total_exposure_pct is not None:
        policy_cfg.max_total_exposure_pct = max_total_exposure_pct
    if loss_block_threshold_pct is not None:
        policy_cfg.loss_block_threshold_pct = loss_block_threshold_pct
    if stop_loss_pct is not None:
        policy_cfg.stop_loss_pct = stop_loss_pct
    if catalyst_timing:
        policy_cfg.catalyst_timing = True
    if xbi_filter:
        policy_cfg.xbi_filter = True
    if cooling:
        policy_cfg.cooling_enabled = True
    if require_catalyst_days > 0:
        policy_cfg.require_catalyst_within_days = require_catalyst_days
    if max_decisions_per_asset > 0:
        policy_cfg.max_decisions_per_asset = max_decisions_per_asset
    if min_thesis_score > 0.0:
        policy_cfg.min_thesis_score = min_thesis_score
    if require_open_claim:
        policy_cfg.require_open_claim = True

    policy_tag = (
        f"{policy_cfg.name}_hold{policy_cfg.max_hold_days}d"
        + (f"_open{policy_cfg.max_open_positions}" if policy_cfg.max_open_positions is not None else "")
        + ("_cattiming" if policy_cfg.catalyst_timing else "")
        + ("_xbi" if policy_cfg.xbi_filter else "")
        + ("_cooling" if policy_cfg.cooling_enabled else "")
        + (f"_catden{policy_cfg.require_catalyst_within_days}d" if policy_cfg.require_catalyst_within_days > 0 else "")
        + (f"_cap{policy_cfg.max_decisions_per_asset}" if policy_cfg.max_decisions_per_asset > 0 else "")
        + (f"_thesis{int(policy_cfg.min_thesis_score * 100)}" if policy_cfg.min_thesis_score > 0.0 else "")
        + ("_openclaim" if policy_cfg.require_open_claim else "")
    )
    replay = HistoricalReplay(rs, str(REPLAY_KNOWLEDGE_PATH), universe=universe, policy_config=policy_cfg)
    run_id = replay.run(
        start=start,
        end=end,
        cadence=resolved_cadence,
        decision_policy=policy_tag,
        profile=profile,
    )
    print(f"\nRun ID: {run_id}")
    summary = replay.summarize(run_id)
    summary.print()
    rs.close()


def _cmd_summary(args: list[str]) -> None:
    """summary --run-id <run_id>"""
    run_id: Optional[str] = None
    i = 0
    while i < len(args):
        if args[i] == "--run-id":
            run_id = args[i + 1]
            i += 2
        else:
            i += 1

    if not run_id:
        print("Usage: summary --run-id <run_id>")
        sys.exit(1)

    rs = ReplayStore(str(REPLAY_STORE_PATH))

    from bve.ops.weekly_runner import UNIVERSE

    replay = HistoricalReplay(rs, str(REPLAY_KNOWLEDGE_PATH), universe=UNIVERSE)
    summary = replay.summarize(run_id)
    summary.print()
    decisions = rs.get_run_decisions(run_id)
    closed = [d for d in decisions if d.get("return_pct") is not None and d.get("is_closed")]

    if len(closed) >= 5:
        from bve.analysis.replay_significance import analyze, print_report

        return_field = (
            "net_return_pct"
            if any(d.get("net_return_pct") is not None for d in closed)
            else "return_pct"
        )
        sig_result = analyze(
            closed,
            run_id=run_id,
            bootstrap_samples=2000,
            cluster_by="asset_catalyst",
            return_field=return_field,
        )
        print_report(sig_result)
    else:
        print(f"  Significance: N={len(closed)} — minimum 5 closed decisions required")

    if len(closed) >= 15:
        from bve.analysis.replay_significance import (
            permutation_test,
            print_permutation_report,
        )

        try:
            print_permutation_report(permutation_test(closed))
        except ValueError as exc:
            print(f"  Permutation test skipped: {exc}")

    if closed and summary.mean_return_pct is not None:
        from bve.analysis.baselines import BaselineCandidate, BaselineConfig, BaselineRunner

        candidates = [
            BaselineCandidate(
                ticker=str(d.get("ticker") or ""),
                return_pct=d.get("return_pct"),
                phase=d.get("phase") or "phase_2",
                catalyst_days_away=d.get("days_to_catalyst_at_entry"),
                ranking_score=d.get("composite_score"),
            )
            for d in closed
        ]
        runner = BaselineRunner(BaselineConfig(top_n=max(1, min(5, len(candidates)))))
        baselines = runner.run_all(candidates)
        print(runner.print_comparison(summary.mean_return_pct, len(closed), baselines))

    losers = [d for d in closed if d.get("return_pct") is not None and float(d["return_pct"]) < 0]
    if losers:
        from bve.analysis.failure_diagnostics import FailureTrade, diagnose_failures

        trades = [
            FailureTrade(
                decision_id=str(d.get("decision_id") or ""),
                asset_id=str(d.get("asset_id") or ""),
                company_id="",
                model_score=_coerce_float(d.get("composite_score"), 0.0),
                return_pct=float(d["return_pct"]),
                attribution=str(d.get("attribution_type") or "unclassified"),
                entry_date=str(d.get("decided_at") or "")[:10] or None,
                days_to_catalyst_at_entry=d.get("days_to_catalyst_at_entry"),
                xbi_return_over_hold=d.get("xbi_return_during_hold"),
            )
            for d in losers
        ]
        print(diagnose_failures(trades, model_name=f"run_{run_id[:8]}").summary())

    if any(d.get("xbi_return_during_hold") is not None for d in closed):
        from bve.analysis.regime_analysis import compute_regime_report

        print(compute_regime_report(closed).summary())
    rs.close()


def _cmd_walk_forward(args: list[str]) -> None:
    """walk-forward --run-id <run_id> [--save-csv PATH] [--save-yaml PATH] [--stability-report]"""
    run_id: Optional[str] = None
    save_csv: Optional[str] = None
    save_yaml: Optional[str] = None
    stability_report = False
    i = 0
    while i < len(args):
        if args[i] == "--run-id":
            run_id = args[i + 1]
            i += 2
        elif args[i] == "--save-csv":
            save_csv = args[i + 1]
            i += 2
        elif args[i] == "--save-yaml":
            save_yaml = args[i + 1]
            i += 2
        elif args[i] == "--stability-report":
            stability_report = True
            i += 1
        else:
            i += 1
    if not run_id:
        print("Usage: walk-forward --run-id <run_id> [--save-csv PATH] [--save-yaml PATH]")
        sys.exit(1)

    rs = ReplayStore(str(REPLAY_STORE_PATH))
    decisions = [
        d for d in rs.get_run_decisions(run_id)
        if d.get("return_pct") is not None and d.get("is_closed")
    ]
    rs.close()
    if len(decisions) < 20:
        print(f"Walk-forward requires >=20 closed decisions; found {len(decisions)}.")
        return

    from bve.analysis.walk_forward import run_walk_forward

    decision_dicts = [
        {
            "entry_date": str(d.get("decided_at") or "")[:10],
            "return_pct": d.get("net_return_pct")
            if d.get("net_return_pct") is not None else d.get("return_pct"),
            "composite_score": d.get("composite_score"),
            "asset_id": d.get("asset_id"),
            "days_to_catalyst": d.get("days_to_catalyst_at_entry"),
        }
        for d in decisions
    ]
    report = run_walk_forward(decision_dicts, model_name=f"run_{run_id[:8]}")
    print(report.summary())
    if save_csv:
        Path(save_csv).parent.mkdir(parents=True, exist_ok=True)
        report.save_csv(save_csv)
    if save_yaml:
        Path(save_yaml).parent.mkdir(parents=True, exist_ok=True)
        report.save_locked_policy_yaml(save_yaml)
    if stability_report:
        print(report.parameter_stability_report())


def _cmd_inspect(args: list[str]) -> None:
    """inspect --run-id <run_id> --week YYYY-MM-DD"""
    run_id: Optional[str] = None
    week: Optional[date] = None
    i = 0
    while i < len(args):
        if args[i] == "--run-id":
            run_id = args[i + 1]
            i += 2
        elif args[i] == "--week":
            week = _parse_date(args[i + 1])
            i += 2
        else:
            i += 1

    if not run_id:
        print("Usage: inspect --run-id <run_id> --week YYYY-MM-DD")
        sys.exit(1)

    rs = ReplayStore(str(REPLAY_STORE_PATH))
    all_decisions = rs.get_run_decisions(run_id)

    if week:
        decisions = [d for d in all_decisions if d["decided_at"][:10] == week.isoformat()]
    else:
        decisions = all_decisions

    print(f"\nDecisions for run {run_id[:8]}... (week={week or 'all'}):")
    print(f"{'TICKER':8s} {'ACTION':8s} {'SCORE':6s} {'SIZE':6s} {'ENTRY':8s} {'EXIT':8s} {'RETURN':8s} {'ATTR'}")
    print("-" * 80)
    for d in decisions:
        r = d.get("return_pct")
        r_str = f"{r:+.1f}%" if r is not None else "open"
        print(
            f"  {d['ticker']:6s}  {d['action']:8s}  "
            f"{d['composite_score']:.3f}  {d['size_pct']:.1%}  "
            f"{d.get('entry_price') or 'n/a':>8}  "
            f"{d.get('exit_date') or 'open':>10}  "
            f"{r_str:>8}  {d.get('attribution_type') or '-'}"
        )

    rs.close()


def _cmd_seed_signals(args: list[str]) -> None:
    """
    seed-signals [--knowledge-db <path>] [--universe-file <path>] [--synthetic] [--backfill]
                 [--start <YYYY-MM-DD>] [--end <YYYY-MM-DD>]

    Populate the replay store's v2.0 signal tables so the replay loop uses
    composite score v2.0 during backtesting.

    --knowledge-db <path>
        Approach A (preferred): copy signals from a live KnowledgeStore SQLite.
        Default: outputs/intelligence/ops.db

    --synthetic
        Approach B: generate conservative synthetic signals from the replay
        store's event calendar.  Use when the knowledge store has sparse data.
        Can be combined with --knowledge-db (synthetic runs first, then live
        signals overwrite where available).

    --backfill
        Approach C: run SignalBackfiller to populate time-varying signals from
        EDGAR historical cash data and historical_events proximity math.
        --start / --end control the catalyst signal date range (default:
        2021-01-01 to today).
    """
    knowledge_db: Optional[str] = None
    synthetic = False
    backfill = False
    backfill_start: Optional[str] = None
    backfill_end: Optional[str] = None
    universe_file: Optional[str] = None

    i = 0
    while i < len(args):
        if args[i] == "--knowledge-db":
            knowledge_db = args[i + 1]
            i += 2
        elif args[i] == "--universe-file":
            universe_file = args[i + 1]
            i += 2
        elif args[i] == "--synthetic":
            synthetic = True
            i += 1
        elif args[i] == "--backfill":
            backfill = True
            i += 1
        elif args[i] == "--start":
            backfill_start = args[i + 1]
            i += 2
        elif args[i] == "--end":
            backfill_end = args[i + 1]
            i += 2
        else:
            i += 1

    _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    rs = ReplayStore(str(REPLAY_STORE_PATH))
    universe = load_replay_universe(universe_file)
    replay = HistoricalReplay(rs, str(REPLAY_KNOWLEDGE_PATH), universe=universe)

    if synthetic:
        n = replay.seed_signals_from_event_calendar()
        print(f"Synthetic seeder: {n} catalyst_events rows inserted.")

    if backfill:
        from bve.ops.signal_backfiller import COMPETITOR_MAP, SignalBackfiller
        from datetime import date as _date

        bf = SignalBackfiller(rs)

        print("Running backfill_capital_risk...")
        bf.backfill_capital_risk(universe)

        bf_start = _date.fromisoformat(backfill_start) if backfill_start else _date(2024, 1, 1)
        bf_end = _date.fromisoformat(backfill_end) if backfill_end else _date.today()
        print(f"Running backfill_catalyst_signals ({bf_start} → {bf_end})...")
        bf.backfill_catalyst_signals(universe, bf_start, bf_end)

        print("Running backfill_competitor_signals...")
        bf.backfill_competitor_signals(COMPETITOR_MAP)

    if not backfill:
        # Default knowledge DB path when not supplied
        kb_path = knowledge_db or str(_OUTPUTS_DIR / "ops.db")
        counts = replay.seed_signals_from_knowledge_store(kb_path)
        total = sum(counts.values())
        print(f"Knowledge store seeder: {total} total rows copied.")

    rs.close()
    print("seed-signals complete.")


def _cmd_significance(args: list[str]) -> None:
    """significance --run-id <run_id> [--bootstrap-samples N] [--seed N]"""
    run_id: Optional[str] = None
    bootstrap_samples = 2000
    seed = 42
    i = 0
    while i < len(args):
        if args[i] == "--run-id":
            run_id = args[i + 1]
            i += 2
        elif args[i] == "--bootstrap-samples":
            bootstrap_samples = int(args[i + 1])
            i += 2
        elif args[i] == "--seed":
            seed = int(args[i + 1])
            i += 2
        else:
            i += 1

    if not run_id:
        print("Usage: significance --run-id <run_id> [--bootstrap-samples N] [--seed N]")
        sys.exit(1)

    rs = ReplayStore(str(REPLAY_STORE_PATH))
    decisions = rs.get_run_decisions(run_id)
    closed = [d for d in decisions if d.get("return_pct") is not None and d.get("is_closed")]
    rs.close()

    if not closed:
        print(f"No closed decisions found for run {run_id!r}")
        sys.exit(1)

    from bve.analysis.replay_significance import analyze, print_report
    return_field = (
        "net_return_pct"
        if any(d.get("net_return_pct") is not None for d in closed)
        else "return_pct"
    )
    result = analyze(
        closed,
        run_id=run_id,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
        cluster_by="asset_catalyst",
        return_field=return_field,
    )
    print_report(result)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    rest = sys.argv[2:]

    dispatch = {
        "seed": _cmd_seed,
        "seed-signals": _cmd_seed_signals,
        "run": _cmd_run,
        "summary": _cmd_summary,
        "walk-forward": _cmd_walk_forward,
        "inspect": _cmd_inspect,
        "significance": _cmd_significance,
    }

    if cmd not in dispatch:
        print(f"Unknown command: {cmd!r}. Valid: {sorted(dispatch)}")
        sys.exit(1)

    dispatch[cmd](rest)
