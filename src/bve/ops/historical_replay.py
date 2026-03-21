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

    python -m bve.ops.historical_replay summary --run-id <run_id>

    python -m bve.ops.historical_replay inspect --run-id <run_id> --week 2025-09-15
"""
from __future__ import annotations

import sqlite3
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

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
from bve.intelligence.thesis_tracker import ThesisTracker


# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_OUTPUTS_DIR = Path(__file__).parent.parent.parent.parent / "outputs" / "intelligence"
REPLAY_STORE_PATH = _OUTPUTS_DIR / "replay_store.sqlite"
REPLAY_KNOWLEDGE_PATH = _OUTPUTS_DIR / "replay_knowledge.db"


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
                created_at       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS historical_prices (
                ticker     TEXT NOT NULL,
                price_date TEXT NOT NULL,
                close_usd  REAL NOT NULL,
                PRIMARY KEY (ticker, price_date)
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
                is_closed       INTEGER NOT NULL DEFAULT 0
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
            """
        )
        self._conn.commit()
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        """Apply backward-compatible schema migrations for existing databases."""
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

    def get_price(self, ticker: str, price_date: date) -> Optional[float]:
        """
        Return the closing price for *ticker* on *price_date*.

        Returns None if no data is available (enforces no lookahead bias —
        callers must not pass a future date relative to their clock).
        """
        row = self._conn.execute(
            "SELECT close_usd FROM historical_prices "
            "WHERE ticker = ? AND price_date = ?",
            (ticker, price_date.isoformat()),
        ).fetchone()
        return float(row["close_usd"]) if row else None

    def get_return(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
    ) -> Optional[float]:
        """
        Compute the simple return from *from_date* close to *to_date* close.

        Returns None if either price is missing.
        """
        entry = self.get_price(ticker, from_date)
        exit_ = self.get_price(ticker, to_date)
        if entry is None or exit_ is None or entry == 0.0:
            return None
        return (exit_ - entry) / entry * 100.0

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
    ) -> str:
        """Create a new replay run record. Returns run_id."""
        run_id = str(uuid.uuid4())
        self._conn.execute(
            """
            INSERT INTO replay_runs
                (run_id, start_date, end_date, cadence, decision_policy,
                 score_version, strategy_version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                start_date.isoformat(),
                end_date.isoformat(),
                cadence,
                decision_policy,
                score_version,
                strategy_version,
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
                 size_pct, composite_score, entry_price, is_closed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
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
    ) -> None:
        """Close a decision by recording exit data."""
        self._conn.execute(
            """
            UPDATE replay_decisions
               SET exit_date        = ?,
                   exit_price       = ?,
                   return_pct       = ?,
                   attribution_type = ?,
                   is_closed        = 1
             WHERE decision_id = ?
            """,
            (
                exit_date.isoformat(),
                exit_price,
                return_pct,
                attribution_type,
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
    ) -> None:
        """
        Download historical prices from yfinance and store them.

        Failures are handled gracefully — a warning is printed and the loop
        continues with partial data.
        """
        from bve.ingestion.market_data import fetch_price_history

        for ticker in tickers:
            try:
                df = fetch_price_history(
                    ticker,
                    start=start.isoformat(),
                    end=end.isoformat(),
                )
                if df.empty:
                    print(f"  [WARN] No price data for {ticker}")
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

            except Exception as exc:  # noqa: BLE001
                print(f"  [WARN] Failed to seed prices for {ticker}: {exc}")

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
        step_days = 14 if cadence == "biweekly" else 7

        run_id = self._rs.create_run(
            start_date=start,
            end_date=end,
            cadence=cadence,
            decision_policy=decision_policy,
            score_version="v2.0",
            strategy_version=self._policy.config.name,
        )
        print(f"Replay run created: {run_id}")

        # Reset per-run processed-event set so re-running doesn't skip events
        self._resolved_event_ids: set[int] = set()

        clock = ReplayClock(start)
        n_steps = 0

        while clock.today() <= end:
            print(f"  Step {clock.today()} ...")
            # Resolve any thesis claims whose catalyst events have now fired,
            # BEFORE scoring so the composite score reflects current thesis_strength.
            n_resolved = self._step_claim_resolution(clock)
            if n_resolved:
                print(f"    Resolved {n_resolved} claim(s).")
            decisions = self._step_decision(clock, run_id, self._universe)
            print(f"    Made {len(decisions)} decision(s).")
            self._step_resolve(clock, run_id)
            clock = clock.advance(step_days)
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
        gen = ActionableGenerator()

        as_of = clock.today()

        # Build candidates with time-frozen thesis snapshots
        candidates: list[ScoredCandidate] = []
        for u in universe:
            snap = tt.snapshot(u["asset_id"], as_of_date=as_of)
            n_resolved = snap.n_confirmed + snap.n_refuted + snap.n_expired
            thesis_strength = snap.thesis_strength if n_resolved > 0 else None
            candidates.append(ScoredCandidate(
                asset_id=u["asset_id"],
                ticker=u["ticker"],
                ranking_score=u.get("ranking_score", 0.5),
                opportunity_score=u.get("opportunity_score", 0.5),
                thesis_strength=thesis_strength,
                catalyst_description=u.get("catalyst", ""),
                indication=u.get("indication", ""),
                company_id=u.get("company_id", ""),
            ))

        # Build v2.0 composite score contexts (no-lookahead: all signals as of as_of)
        contexts = self._build_score_contexts(universe, as_of)

        report = gen.generate(candidates, top_n=10, week_ending=as_of, contexts=contexts)

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
            current_total_exposure=0.0,
            catalyst_dates=catalyst_dates,
            xbi_above_ma=xbi_above_ma,
            cooling_asset_ids=cooling_asset_ids,
        )

        # Persist each decision
        for dec in decisions:
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

            return_pct: Optional[float] = None
            if entry_price and exit_price and entry_price != 0.0:
                return_pct = (exit_price - entry_price) / entry_price * 100.0

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
            )

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
            "unclassified": 0,
        }
        returns: list[float] = []
        returns_by_action: dict[str, list[float]] = {}

        for d in closed:
            attr = d.get("attribution_type") or "unclassified"
            if attr in attribution_counts:
                attribution_counts[attr] += 1
            else:
                attribution_counts["unclassified"] += 1

            r = d.get("return_pct")
            if r is not None:
                returns.append(float(r))
                action = d.get("action", "unknown")
                returns_by_action.setdefault(action, []).append(float(r))

        mean_return = (sum(returns) / len(returns)) if returns else None
        hit_rate = (
            sum(1 for r in returns if r > 0) / len(returns)
            if returns else None
        )

        # Estimate n_decision_dates from run metadata
        start = date.fromisoformat(run["start_date"])
        end = date.fromisoformat(run["end_date"])
        cadence = run.get("cadence", "weekly")
        step_days = 14 if cadence == "biweekly" else 7
        n_dates = max(1, (end - start).days // step_days + 1)

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
            hit_rate=round(hit_rate, 4) if hit_rate is not None else None,
            n_confirmed_thesis=attribution_counts["confirmed_thesis"],
            n_pos_error=attribution_counts["pos_error"],
            n_timing_error=attribution_counts["timing_error"],
            n_thesis_error=attribution_counts["thesis_error"],
            n_market_drift=attribution_counts["market_drift"],
            n_unclassified=attribution_counts["unclassified"],
            returns_by_action={k: v for k, v in returns_by_action.items()},
        )
        return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


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
    """run --start YYYY-MM-DD --end YYYY-MM-DD [--cadence weekly] [--decision-policy top2_add] [--max-hold-days 30] [--catalyst-timing] [--cooling] [--require-catalyst-days N]"""
    start: Optional[date] = None
    end: Optional[date] = None
    cadence = "weekly"
    policy = "top2_add"
    max_hold_days = 30
    catalyst_timing = False
    xbi_filter = False
    cooling = False
    require_catalyst_days = 0

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
        elif args[i] == "--max-hold-days":
            max_hold_days = int(args[i + 1])
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
        elif args[i] == "--require-catalyst-days":
            require_catalyst_days = int(args[i + 1])
            i += 2
        else:
            i += 1

    if not start or not end:
        print("Usage: run --start YYYY-MM-DD --end YYYY-MM-DD [--cadence weekly] [--max-hold-days 30] [--catalyst-timing] [--cooling] [--require-catalyst-days N]")
        sys.exit(1)

    _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    rs = ReplayStore(str(REPLAY_STORE_PATH))

    from bve.ops.weekly_runner import UNIVERSE

    policy_tag = (
        f"{policy}_hold{max_hold_days}d"
        + ("_cattiming" if catalyst_timing else "")
        + ("_xbi" if xbi_filter else "")
        + ("_cooling" if cooling else "")
        + (f"_catden{require_catalyst_days}d" if require_catalyst_days > 0 else "")
    )
    policy_cfg = ReplayPolicyConfig(
        name=policy,
        max_hold_days=max_hold_days,
        catalyst_timing=catalyst_timing,
        xbi_filter=xbi_filter,
        cooling_enabled=cooling,
        require_catalyst_within_days=require_catalyst_days,
    )
    replay = HistoricalReplay(rs, str(REPLAY_KNOWLEDGE_PATH), universe=UNIVERSE, policy_config=policy_cfg)
    run_id = replay.run(start=start, end=end, cadence=cadence, decision_policy=policy_tag)
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
    rs.close()


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
    seed-signals [--knowledge-db <path>] [--synthetic] [--backfill]
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
        2024-01-01 to today).
    """
    knowledge_db: Optional[str] = None
    synthetic = False
    backfill = False
    backfill_start: Optional[str] = None
    backfill_end: Optional[str] = None

    i = 0
    while i < len(args):
        if args[i] == "--knowledge-db":
            knowledge_db = args[i + 1]
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

    from bve.ops.weekly_runner import UNIVERSE

    replay = HistoricalReplay(rs, str(REPLAY_KNOWLEDGE_PATH), universe=UNIVERSE)

    if synthetic:
        n = replay.seed_signals_from_event_calendar()
        print(f"Synthetic seeder: {n} catalyst_events rows inserted.")

    if backfill:
        from bve.ops.signal_backfiller import COMPETITOR_MAP, SignalBackfiller
        from datetime import date as _date

        bf = SignalBackfiller(rs)

        print("Running backfill_capital_risk...")
        bf.backfill_capital_risk(UNIVERSE)

        bf_start = _date.fromisoformat(backfill_start) if backfill_start else _date(2024, 1, 1)
        bf_end = _date.fromisoformat(backfill_end) if backfill_end else _date.today()
        print(f"Running backfill_catalyst_signals ({bf_start} → {bf_end})...")
        bf.backfill_catalyst_signals(UNIVERSE, bf_start, bf_end)

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
        "inspect": _cmd_inspect,
    }

    if cmd not in dispatch:
        print(f"Unknown command: {cmd!r}. Valid: {sorted(dispatch)}")
        sys.exit(1)

    dispatch[cmd](rest)
