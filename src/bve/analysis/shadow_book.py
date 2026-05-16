"""Shadow book — pre-registered paper trading with locked, immutable decision records.

Design rules
------------
1. Decisions are pre-registered BEFORE the catalyst/event resolves. No post-hoc edits.
2. Each decision is time-stamped and hash-locked at registration to detect tampering.
3. Outcomes (returns) are filled in after the hold period; they cannot backfill the
   decision rationale or score.
4. The book is append-only: decisions can be CLOSED but never deleted or amended.
5. Stored in a SQLite file (shadow_book.db) — separate from ops.db and replay.db.

Shadow book vs historical replay
---------------------------------
- Historical replay uses existing data with time-freezing to prevent lookahead.
- Shadow book uses LIVE weekly snapshots with decisions locked before outcomes are known.
- Shadow book accumulates real prospective decisions; replay accumulates simulated ones.

Usage
-----
    from bve.analysis.shadow_book import ShadowBook

    book = ShadowBook("outputs/intelligence/shadow_book.db")
    book.initialize()

    # Register a new decision (before catalyst resolves)
    decision_id = book.register(
        ticker="VKTX",
        asset_id="a-vktx",
        model_score=0.72,
        entry_price_usd=14.20,
        entry_date="2026-05-16",
        catalyst_date="2026-06-15",
        catalyst_type="phase_2_readout",
        rationale="Viking Therapeutics VK2735 obesity Phase 2 data expected mid-June",
        max_hold_days=28,
    )

    # Close after hold period
    book.close(
        decision_id=decision_id,
        exit_price_usd=18.50,
        exit_date="2026-06-13",
    )

    # P&L summary
    summary = book.pnl_summary()
    print(summary)

CLI
---
    python -m bve.analysis.shadow_book --db outputs/intelligence/shadow_book.db \
        register --ticker VKTX --score 0.72 --entry-price 14.20 \
        --entry-date 2026-05-16 --catalyst-date 2026-06-15

    python -m bve.analysis.shadow_book --db outputs/intelligence/shadow_book.db summary
    python -m bve.analysis.shadow_book --db outputs/intelligence/shadow_book.db list
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import statistics
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------
SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ShadowDecision:
    """One pre-registered paper trade."""
    decision_id: str
    ticker: str
    asset_id: str
    model_score: float
    entry_price_usd: float
    entry_date: str            # ISO date
    catalyst_date: Optional[str]
    catalyst_type: str
    rationale: str
    max_hold_days: int
    registered_at: str         # ISO datetime UTC
    integrity_hash: str        # SHA-256 of immutable fields
    # Outcome (filled in after close)
    exit_price_usd: Optional[float] = None
    exit_date: Optional[str] = None
    closed_at: Optional[str] = None
    status: str = "open"       # "open" | "closed"

    @property
    def return_pct(self) -> Optional[float]:
        if self.exit_price_usd is None or self.entry_price_usd <= 0:
            return None
        return round((self.exit_price_usd - self.entry_price_usd) / self.entry_price_usd * 100, 4)

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "ticker": self.ticker,
            "asset_id": self.asset_id,
            "model_score": self.model_score,
            "entry_price_usd": self.entry_price_usd,
            "entry_date": self.entry_date,
            "catalyst_date": self.catalyst_date,
            "catalyst_type": self.catalyst_type,
            "rationale": self.rationale,
            "max_hold_days": self.max_hold_days,
            "registered_at": self.registered_at,
            "integrity_hash": self.integrity_hash,
            "exit_price_usd": self.exit_price_usd,
            "exit_date": self.exit_date,
            "closed_at": self.closed_at,
            "status": self.status,
            "return_pct": self.return_pct,
        }


@dataclass
class ShadowBookSummary:
    """P&L summary across all closed shadow book decisions."""
    n_open: int
    n_closed: int
    n_winners: int
    n_losers: int
    mean_return_pct: Optional[float]
    median_return_pct: Optional[float]
    hit_rate: Optional[float]
    best_return_pct: Optional[float]
    worst_return_pct: Optional[float]
    paper_pnl_pct: Optional[float]   # cumulative additive return
    by_ticker: dict[str, dict]

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "  SHADOW BOOK — Paper P&L Summary",
            "=" * 60,
            f"  Open positions:  {self.n_open}",
            f"  Closed trades:   {self.n_closed}",
        ]
        if self.n_closed > 0:
            lines += [
                f"  Winners:         {self.n_winners}  "
                f"({self.hit_rate*100:.0f}% hit rate)" if self.hit_rate else "",
                f"  Losers:          {self.n_losers}",
                f"  Mean return:     {self.mean_return_pct:+.2f}%" if self.mean_return_pct else "  Mean return:     n/a",
                f"  Median return:   {self.median_return_pct:+.2f}%" if self.median_return_pct else "  Median return:   n/a",
                f"  Best trade:      {self.best_return_pct:+.2f}%" if self.best_return_pct else "  Best trade:      n/a",
                f"  Worst trade:     {self.worst_return_pct:+.2f}%" if self.worst_return_pct else "  Worst trade:     n/a",
                f"  Paper P&L:       {self.paper_pnl_pct:+.2f}%" if self.paper_pnl_pct else "  Paper P&L:       n/a",
            ]
            if self.by_ticker:
                lines.append("")
                lines.append("  By ticker:")
                for ticker, stats in sorted(self.by_ticker.items()):
                    r = stats.get("mean_return_pct")
                    n = stats.get("n", 0)
                    s = f"{r:+.2f}%" if r is not None else "n/a"
                    lines.append(f"    {ticker:<8} N={n}  mean={s}")
        else:
            lines.append("  No closed trades yet.")
        lines.append("=" * 60)
        return "\n".join(line for line in lines if line)

    def to_dict(self) -> dict:
        return {
            "n_open": self.n_open,
            "n_closed": self.n_closed,
            "n_winners": self.n_winners,
            "n_losers": self.n_losers,
            "mean_return_pct": self.mean_return_pct,
            "median_return_pct": self.median_return_pct,
            "hit_rate": self.hit_rate,
            "best_return_pct": self.best_return_pct,
            "worst_return_pct": self.worst_return_pct,
            "paper_pnl_pct": self.paper_pnl_pct,
            "by_ticker": self.by_ticker,
        }


# ---------------------------------------------------------------------------
# Core ShadowBook class
# ---------------------------------------------------------------------------

class ShadowBook:
    """Append-only pre-registered paper trading book stored in SQLite."""

    def __init__(self, db_path: str | Path = "outputs/intelligence/shadow_book.db") -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        """Create database tables if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                );
                INSERT OR IGNORE INTO schema_version (version) VALUES (1);

                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id        TEXT PRIMARY KEY,
                    ticker             TEXT NOT NULL,
                    asset_id           TEXT NOT NULL,
                    model_score        REAL NOT NULL,
                    entry_price_usd    REAL NOT NULL,
                    entry_date         TEXT NOT NULL,
                    catalyst_date      TEXT,
                    catalyst_type      TEXT NOT NULL DEFAULT 'unknown',
                    rationale          TEXT NOT NULL DEFAULT '',
                    max_hold_days      INTEGER NOT NULL DEFAULT 28,
                    registered_at      TEXT NOT NULL,
                    integrity_hash     TEXT NOT NULL,
                    exit_price_usd     REAL,
                    exit_date          TEXT,
                    closed_at          TEXT,
                    status             TEXT NOT NULL DEFAULT 'open'
                );

                CREATE INDEX IF NOT EXISTS idx_decisions_ticker ON decisions (ticker);
                CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions (status);
                CREATE INDEX IF NOT EXISTS idx_decisions_entry_date ON decisions (entry_date);
            """)

    def register(
        self,
        *,
        ticker: str,
        asset_id: str,
        model_score: float,
        entry_price_usd: float,
        entry_date: str,
        catalyst_date: Optional[str] = None,
        catalyst_type: str = "unknown",
        rationale: str = "",
        max_hold_days: int = 28,
    ) -> str:
        """Pre-register a new paper trade. Returns decision_id.

        This MUST be called before the catalyst resolves. The integrity_hash
        locks the immutable fields so any tampering is detectable.
        """
        decision_id = str(uuid.uuid4())[:16]
        registered_at = datetime.now(timezone.utc).isoformat()

        # Hash covers all immutable fields
        integrity_hash = _hash_fields({
            "decision_id": decision_id,
            "ticker": ticker,
            "asset_id": asset_id,
            "model_score": model_score,
            "entry_price_usd": entry_price_usd,
            "entry_date": entry_date,
            "catalyst_date": catalyst_date,
            "catalyst_type": catalyst_type,
            "rationale": rationale,
            "registered_at": registered_at,
        })

        with self._connect() as conn:
            conn.execute("""
                INSERT INTO decisions (
                    decision_id, ticker, asset_id, model_score, entry_price_usd,
                    entry_date, catalyst_date, catalyst_type, rationale, max_hold_days,
                    registered_at, integrity_hash, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
            """, (
                decision_id, ticker, asset_id, model_score, entry_price_usd,
                entry_date, catalyst_date, catalyst_type, rationale, max_hold_days,
                registered_at, integrity_hash,
            ))
        return decision_id

    def close(
        self,
        decision_id: str,
        *,
        exit_price_usd: float,
        exit_date: str,
    ) -> None:
        """Close an open position with the exit price.

        Raises ValueError if the decision is already closed or not found.
        """
        closed_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT status FROM decisions WHERE decision_id = ?", (decision_id,)
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"Decision {decision_id!r} not found")
            if row[0] == "closed":
                raise ValueError(f"Decision {decision_id!r} is already closed")
            conn.execute("""
                UPDATE decisions
                SET exit_price_usd = ?, exit_date = ?, closed_at = ?, status = 'closed'
                WHERE decision_id = ?
            """, (exit_price_usd, exit_date, closed_at, decision_id))

    def get(self, decision_id: str) -> Optional[ShadowDecision]:
        """Retrieve one decision by ID."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_decision(row)

    def list_open(self) -> list[ShadowDecision]:
        """Return all open decisions."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM decisions WHERE status = 'open' ORDER BY entry_date"
            )
            return [_row_to_decision(r) for r in cur.fetchall()]

    def list_closed(self) -> list[ShadowDecision]:
        """Return all closed decisions."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM decisions WHERE status = 'closed' ORDER BY exit_date"
            )
            return [_row_to_decision(r) for r in cur.fetchall()]

    def list_all(self) -> list[ShadowDecision]:
        """Return all decisions ordered by entry_date."""
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM decisions ORDER BY entry_date")
            return [_row_to_decision(r) for r in cur.fetchall()]

    def verify_integrity(self) -> list[dict]:
        """Check that all decisions have valid integrity hashes.

        Returns list of violations (empty if clean).
        """
        violations = []
        for d in self.list_all():
            expected = _hash_fields({
                "decision_id": d.decision_id,
                "ticker": d.ticker,
                "asset_id": d.asset_id,
                "model_score": d.model_score,
                "entry_price_usd": d.entry_price_usd,
                "entry_date": d.entry_date,
                "catalyst_date": d.catalyst_date,
                "catalyst_type": d.catalyst_type,
                "rationale": d.rationale,
                "registered_at": d.registered_at,
            })
            if d.integrity_hash != expected:
                violations.append({
                    "decision_id": d.decision_id,
                    "ticker": d.ticker,
                    "violation": "integrity_hash_mismatch",
                })
        return violations

    def pnl_summary(self) -> ShadowBookSummary:
        """Compute P&L summary across all closed decisions."""
        open_d = self.list_open()
        closed_d = self.list_closed()

        returns = [d.return_pct for d in closed_d if d.return_pct is not None]
        n_closed = len(closed_d)
        n_winners = sum(1 for r in returns if r > 0)
        n_losers = sum(1 for r in returns if r <= 0)

        mean_r = round(statistics.mean(returns), 4) if returns else None
        median_r = round(statistics.median(returns), 4) if returns else None
        hit_rate = round(n_winners / n_closed, 4) if n_closed > 0 else None
        best = round(max(returns), 4) if returns else None
        worst = round(min(returns), 4) if returns else None
        pnl = round(sum(returns), 4) if returns else None

        # Breakdown by ticker
        by_ticker: dict[str, dict] = {}
        for d in closed_d:
            r = d.return_pct
            if r is None:
                continue
            entry = by_ticker.setdefault(d.ticker, {"n": 0, "returns": []})
            entry["n"] += 1
            entry["returns"].append(r)
        by_ticker_clean = {}
        for ticker, data in by_ticker.items():
            rr = data["returns"]
            by_ticker_clean[ticker] = {
                "n": data["n"],
                "mean_return_pct": round(statistics.mean(rr), 4) if rr else None,
                "hit_rate": round(sum(1 for r in rr if r > 0) / len(rr), 4) if rr else None,
            }

        return ShadowBookSummary(
            n_open=len(open_d),
            n_closed=n_closed,
            n_winners=n_winners,
            n_losers=n_losers,
            mean_return_pct=mean_r,
            median_return_pct=median_r,
            hit_rate=hit_rate,
            best_return_pct=best,
            worst_return_pct=worst,
            paper_pnl_pct=pnl,
            by_ticker=by_ticker_clean,
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_fields(fields: dict) -> str:
    payload = json.dumps(fields, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _row_to_decision(row: sqlite3.Row) -> ShadowDecision:
    return ShadowDecision(
        decision_id=row["decision_id"],
        ticker=row["ticker"],
        asset_id=row["asset_id"],
        model_score=row["model_score"],
        entry_price_usd=row["entry_price_usd"],
        entry_date=row["entry_date"],
        catalyst_date=row["catalyst_date"],
        catalyst_type=row["catalyst_type"],
        rationale=row["rationale"],
        max_hold_days=row["max_hold_days"],
        registered_at=row["registered_at"],
        integrity_hash=row["integrity_hash"],
        exit_price_usd=row["exit_price_usd"],
        exit_date=row["exit_date"],
        closed_at=row["closed_at"],
        status=row["status"],
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    parser = argparse.ArgumentParser(prog="shadow_book", description="Shadow book CLI")
    parser.add_argument("--db", default="outputs/intelligence/shadow_book.db",
                        help="Path to shadow_book.db")
    sub = parser.add_subparsers(dest="command")

    # init
    sub.add_parser("init", help="Initialize the shadow book database")

    # register
    reg = sub.add_parser("register", help="Pre-register a new paper trade")
    reg.add_argument("--ticker", required=True)
    reg.add_argument("--asset-id", default="")
    reg.add_argument("--score", type=float, required=True, dest="model_score")
    reg.add_argument("--entry-price", type=float, required=True, dest="entry_price_usd")
    reg.add_argument("--entry-date", required=True, dest="entry_date")
    reg.add_argument("--catalyst-date", default=None, dest="catalyst_date")
    reg.add_argument("--catalyst-type", default="unknown", dest="catalyst_type")
    reg.add_argument("--rationale", default="", dest="rationale")
    reg.add_argument("--max-hold-days", type=int, default=28, dest="max_hold_days")

    # close
    cl = sub.add_parser("close", help="Close an open position")
    cl.add_argument("decision_id")
    cl.add_argument("--exit-price", type=float, required=True, dest="exit_price_usd")
    cl.add_argument("--exit-date", required=True, dest="exit_date")

    # list
    lst = sub.add_parser("list", help="List decisions")
    lst.add_argument("--status", choices=["open", "closed", "all"], default="all")

    # summary
    sub.add_parser("summary", help="Print P&L summary")

    # verify
    sub.add_parser("verify", help="Verify integrity hashes")

    args = parser.parse_args()
    book = ShadowBook(args.db)

    if args.command == "init":
        book.initialize()
        print(f"Shadow book initialized at {args.db}")

    elif args.command == "register":
        book.initialize()
        did = book.register(
            ticker=args.ticker,
            asset_id=args.asset_id or f"a-{args.ticker.lower()}",
            model_score=args.model_score,
            entry_price_usd=args.entry_price_usd,
            entry_date=args.entry_date,
            catalyst_date=args.catalyst_date,
            catalyst_type=args.catalyst_type,
            rationale=args.rationale,
            max_hold_days=args.max_hold_days,
        )
        print(f"Registered decision_id={did!r}")

    elif args.command == "close":
        book.close(
            decision_id=args.decision_id,
            exit_price_usd=args.exit_price_usd,
            exit_date=args.exit_date,
        )
        d = book.get(args.decision_id)
        if d and d.return_pct is not None:
            print(f"Closed {args.decision_id!r}: return={d.return_pct:+.2f}%")
        else:
            print(f"Closed {args.decision_id!r}")

    elif args.command == "list":
        book.initialize()
        if args.status == "open":
            decisions = book.list_open()
        elif args.status == "closed":
            decisions = book.list_closed()
        else:
            decisions = book.list_all()
        if not decisions:
            print("No decisions found.")
        for d in decisions:
            ret = f"  return={d.return_pct:+.2f}%" if d.return_pct is not None else ""
            print(f"[{d.status.upper()}] {d.decision_id} | {d.ticker} | "
                  f"entry={d.entry_date} | score={d.model_score:.2f}{ret}")

    elif args.command == "summary":
        book.initialize()
        summary = book.pnl_summary()
        print(summary.summary())

    elif args.command == "verify":
        book.initialize()
        violations = book.verify_integrity()
        if violations:
            print(f"⚠  {len(violations)} integrity violation(s):")
            for v in violations:
                print(f"  {v}")
        else:
            print("✓ All integrity hashes valid")

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
