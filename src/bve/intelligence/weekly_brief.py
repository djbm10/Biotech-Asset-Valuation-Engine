"""
Wave 4B — Weekly Opportunity Brief.

Assembles a one-page executive summary of the past week's intelligence activity:
  - Review throughput (signals processed, accepted/rejected/deferred/pending)
  - Net model-value movement from accepted changes
  - Top-N ranked opportunities (re-uses existing AssetRankingEngine)
  - Event-type distribution
  - Accepted changes detail table
  - Open-queue snapshot

Flow
----
1. ``WeeklyBriefGenerator.generate(store)`` — queries KnowledgeStore, applies
   ``AssetRankingEngine``, assembles a ``WeeklyOpportunityBrief``.
2. ``WeeklyBriefRenderer.render(brief)`` — renders the brief via a Jinja2
   template to a Markdown string.
3. CLI ``bve-weekly-brief`` — calls both and prints / writes output.

Usage
-----
    bve-weekly-brief --db outputs/intelligence_phase2/knowledge.db
    bve-weekly-brief --db knowledge.db --days 14 --top-n 10 --out brief.md
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from bve.intelligence.knowledge_layer import KnowledgeStore


# ---------------------------------------------------------------------------
# Output models  (Step 1)
# ---------------------------------------------------------------------------


class AcceptedChange(BaseModel):
    """One accepted valuation change, for the detail table in the brief."""

    run_id: str
    asset_id: str
    event_type: Optional[str] = None
    signal_date: Optional[str] = None
    delta_npv_millions: float
    # delta_npv scaled by reviewer_confidence (1.0 when confidence is None).
    # Prevents low-confidence signals from dominating the aggregate.
    confidence_weighted_delta_npv_millions: float = 0.0
    parameter_path: Optional[str] = None   # first assumptions_changed entry
    reviewer_id: Optional[str] = None
    reviewer_confidence: Optional[float] = None
    reviewed_at: Optional[str] = None      # ISO date string (date part only)


class PendingItem(BaseModel):
    """Snapshot of one unreviewed diff, for the open-queue section."""

    run_id: str
    asset_id: str
    event_type: Optional[str] = None
    delta_npv_millions: float
    created_at: Optional[str] = None       # ISO date string (date part only)
    severity: str                          # "high" | "medium" | "low"


class WeeklyOpportunityBrief(BaseModel):
    """
    Assembled data for one weekly opportunity brief.

    Produced by ``WeeklyBriefGenerator.generate()`` and consumed by
    ``WeeklyBriefRenderer.render()``.
    """

    period_start: date
    period_end: date
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # --- Throughput stats ---
    n_signals_processed: int = 0
    n_diffs_generated: int = 0
    n_reviewed: int = 0
    n_accepted: int = 0
    n_rejected: int = 0
    n_deferred: int = 0
    n_pending: int = 0
    n_alerts_fired: int = 0

    # --- Value movement ---
    # Raw sum of delta_npv for accepted diffs.
    net_delta_npv_accepted_millions: float = 0.0
    # Confidence-weighted sum: delta_npv × reviewer_confidence (1.0 when None).
    # Use this as the primary figure — it down-weights low-confidence signals.
    net_confidence_weighted_delta_npv_millions: float = 0.0

    # --- Top opportunities from the ranking engine ---
    top_opportunities: list[dict] = Field(default_factory=list)
    top_opportunities_source_mode: str = "valuation_diffs"
    top_opportunities_reference_date: Optional[date] = None

    # --- Event-type distribution (event_type -> count of diffs) ---
    event_type_counts: dict[str, int] = Field(default_factory=dict)

    # --- Accepted changes detail ---
    accepted_changes: list[AcceptedChange] = Field(default_factory=list)

    # --- Open-queue snapshot (up to top_n pending items by |ΔNPV|) ---
    pending_items: list[PendingItem] = Field(default_factory=list)
    # --- Competitive changes discovered during period ---
    competitive_developments: list[dict] = Field(default_factory=list)

    # Config echoed for auditability
    lookback_days: int = 7
    top_n: int = 5


# ---------------------------------------------------------------------------
# Generator  (Step 2)
# ---------------------------------------------------------------------------


def _severity_label(delta_npv: Optional[float]) -> str:
    if delta_npv is None:
        return "low"
    if abs(delta_npv) > 100:
        return "high"
    if abs(delta_npv) >= 25:
        return "medium"
    return "low"


class WeeklyBriefGenerator:
    """
    Assembles a ``WeeklyOpportunityBrief`` from a live ``KnowledgeStore``.

    Parameters
    ----------
    lookback_days:
        Number of calendar days to include in the brief (default: 7).
    top_n:
        Number of top-ranked opportunities to include (default: 5).
    """

    def __init__(
        self,
        *,
        lookback_days: int = 7,
        top_n: int = 5,
    ) -> None:
        self.lookback_days = lookback_days
        self.top_n = top_n

    def generate(self, store: "KnowledgeStore") -> WeeklyOpportunityBrief:  # type: ignore[name-defined]
        """
        Query *store* and return a fully populated ``WeeklyOpportunityBrief``.
        """
        period_end = date.today()
        period_start = period_end - timedelta(days=self.lookback_days)
        since_dt = datetime(
            period_start.year, period_start.month, period_start.day,
            tzinfo=timezone.utc,
        )
        since_iso = since_dt.isoformat()

        brief = WeeklyOpportunityBrief(
            period_start=period_start,
            period_end=period_end,
            lookback_days=self.lookback_days,
            top_n=self.top_n,
        )

        # ------------------------------------------------------------------
        # 1. Count structured_signals in window
        # ------------------------------------------------------------------
        row = store._conn.execute(
            "SELECT COUNT(*) AS n FROM structured_signals WHERE created_at >= ?",
            (since_iso,),
        ).fetchone()
        brief.n_signals_processed = row["n"] if row else 0
        alert_row = store._conn.execute(
            "SELECT COUNT(*) AS n FROM opportunity_alerts WHERE created_at >= ?",
            (since_iso,),
        ).fetchone()
        brief.n_alerts_fired = alert_row["n"] if alert_row else 0

        # ------------------------------------------------------------------
        # 2. Load all valuation_diffs in the window
        # ------------------------------------------------------------------
        diff_rows = store._conn.execute(
            """
            SELECT
                vd.run_id, vd.asset_id, vd.event_id, vd.delta_npv,
                vd.created_at, vd.payload_json,
                e.event_type
            FROM valuation_diffs vd
            LEFT JOIN events e ON e.id = vd.event_id
            WHERE vd.created_at >= ?
            ORDER BY vd.created_at DESC
            """,
            (since_iso,),
        ).fetchall()
        brief.n_diffs_generated = len(diff_rows)

        # Event-type distribution
        for row in diff_rows:
            et = row["event_type"] or "unknown"
            brief.event_type_counts[et] = brief.event_type_counts.get(et, 0) + 1

        # Index by run_id for join with review_decisions
        diffs_by_run: dict[str, dict] = {}
        for row in diff_rows:
            diffs_by_run[row["run_id"]] = dict(row)

        # ------------------------------------------------------------------
        # 3. Load review_decisions in window
        # ------------------------------------------------------------------
        decision_rows = store._conn.execute(
            """
            SELECT
                rd.id, rd.run_id, rd.proposal_id, rd.decision,
                rd.reviewer_id, rd.reviewed_at, rd.override_value,
                rd.reviewer_confidence
            FROM review_decisions rd
            WHERE rd.reviewed_at >= ?
            ORDER BY rd.reviewed_at DESC
            """,
            (since_iso,),
        ).fetchall()

        brief.n_reviewed = len(decision_rows)
        brief.n_accepted  = sum(1 for r in decision_rows if r["decision"] == "accepted")
        brief.n_rejected  = sum(1 for r in decision_rows if r["decision"] == "rejected")
        brief.n_deferred  = sum(1 for r in decision_rows if r["decision"] == "deferred")

        reviewed_run_ids = {r["run_id"] for r in decision_rows}

        # Pending = diffs in window that have not been reviewed
        pending_rows = [d for d in diff_rows if d["run_id"] not in reviewed_run_ids]
        brief.n_pending = len(pending_rows)

        # Also count all-time pending (not just in window), for the queue snapshot
        all_pending_rows = store._conn.execute(
            """
            SELECT
                vd.run_id, vd.asset_id, vd.event_id, vd.delta_npv,
                vd.created_at, e.event_type
            FROM valuation_diffs vd
            LEFT JOIN events e ON e.id = vd.event_id
            WHERE NOT EXISTS (
                SELECT 1 FROM review_decisions rd WHERE rd.run_id = vd.run_id
            )
            ORDER BY ABS(vd.delta_npv) DESC
            LIMIT ?
            """,
            (self.top_n,),
        ).fetchall()
        brief.pending_items = [
            PendingItem(
                run_id=r["run_id"],
                asset_id=r["asset_id"] or "",
                event_type=r["event_type"],
                delta_npv_millions=r["delta_npv"] or 0.0,
                created_at=(r["created_at"] or "")[:10],
                severity=_severity_label(r["delta_npv"]),
            )
            for r in all_pending_rows
        ]
        comp_rows = store._conn.execute(
            """
            SELECT asset_id, company, drug_name, phase, status, indication, discovered_at
            FROM competitor_programs
            WHERE discovered_at >= ?
            ORDER BY discovered_at DESC
            LIMIT ?
            """,
            (since_iso, self.top_n),
        ).fetchall()
        brief.competitive_developments = [dict(r) for r in comp_rows]

        # ------------------------------------------------------------------
        # 4. Accepted changes detail + net ΔNPV
        # ------------------------------------------------------------------
        accepted_rows = [r for r in decision_rows if r["decision"] == "accepted"]
        net_delta = 0.0
        net_weighted_delta = 0.0
        accepted_changes: list[AcceptedChange] = []

        for dec in accepted_rows:
            diff = diffs_by_run.get(dec["run_id"])
            if diff is None:
                # Decision was on a diff outside the current window; fetch it
                diff_row = store._conn.execute(
                    "SELECT * FROM valuation_diffs WHERE run_id = ? LIMIT 1",
                    (dec["run_id"],),
                ).fetchone()
                diff = dict(diff_row) if diff_row else {}

            delta = dec["override_value"] if dec["override_value"] is not None \
                else (diff.get("delta_npv") or 0.0)
            conf = dec["reviewer_confidence"]
            weight = conf if conf is not None else 1.0
            weighted_delta = delta * weight

            net_delta += delta
            net_weighted_delta += weighted_delta

            payload = json.loads(diff.get("payload_json") or "{}")
            first_change = (payload.get("assumptions_changed") or [{}])[0]

            # Fetch event_type from events table if not on the diff row
            event_type = diff.get("event_type")
            if not event_type and diff.get("event_id"):
                et_row = store._conn.execute(
                    "SELECT event_type FROM events WHERE id = ? LIMIT 1",
                    (diff["event_id"],),
                ).fetchone()
                event_type = et_row["event_type"] if et_row else None

            accepted_changes.append(AcceptedChange(
                run_id=dec["run_id"],
                asset_id=diff.get("asset_id") or "",
                event_type=event_type,
                signal_date=payload.get("signal_date") or (diff.get("created_at") or "")[:10],
                delta_npv_millions=delta,
                confidence_weighted_delta_npv_millions=round(weighted_delta, 2),
                parameter_path=first_change.get("parameter_path") or first_change.get("parameter"),
                reviewer_id=dec["reviewer_id"],
                reviewer_confidence=dec["reviewer_confidence"],
                reviewed_at=(dec["reviewed_at"] or "")[:10],
            ))

        # Sort accepted changes by |confidence-weighted ΔNPV| descending
        accepted_changes.sort(
            key=lambda c: abs(c.confidence_weighted_delta_npv_millions), reverse=True
        )
        brief.accepted_changes = accepted_changes
        brief.net_delta_npv_accepted_millions = round(net_delta, 2)
        brief.net_confidence_weighted_delta_npv_millions = round(net_weighted_delta, 2)

        company_snapshot_date, company_top = self._top_opportunities_from_company_snapshots(
            store,
            as_of=period_end,
        )
        if company_top:
            brief.top_opportunities_source_mode = "company_sotp_snapshot"
            brief.top_opportunities_reference_date = company_snapshot_date
            brief.top_opportunities = company_top
        else:
            brief.top_opportunities_source_mode = "valuation_diffs"
            brief.top_opportunities = self._top_opportunities_from_diffs(store)

        return brief

    def _top_opportunities_from_company_snapshots(
        self,
        store: "KnowledgeStore",  # type: ignore[name-defined]
        *,
        as_of: date,
    ) -> tuple[Optional[date], list[dict]]:
        snapshot_date, raw_rows = store.get_company_sotp_snapshots_on_or_before(as_of, limit=500)
        if snapshot_date is None or not raw_rows:
            return None, []

        filtered = [
            row
            for row in raw_rows
            if bool(row.get("balance_sheet_passes_recency_gate", False))
            and str(row.get("action_policy") or "") in {"buy", "watch"}
        ]
        filtered.sort(
            key=lambda row: (
                -float(row.get("ranked_sotp_discount") or 0.0),
                str(row.get("ticker") or ""),
            )
        )
        top: list[dict] = []
        for idx, row in enumerate(filtered[: self.top_n], start=1):
            top.append(
                {
                    "rank": idx,
                    "ticker": row.get("ticker") or "",
                    "company_name": row.get("company_name") or "",
                    "ranked_sotp_discount": float(row.get("ranked_sotp_discount") or 0.0),
                    "action_policy": row.get("action_policy") or "—",
                    "enterprise_value_millions": row.get("enterprise_value_millions"),
                    "sotp_equity_value_millions": row.get("sotp_equity_value_millions"),
                    "modeled_asset_coverage_pct": row.get("modeled_asset_coverage_pct"),
                    "balance_sheet_snapshot_date": row.get("balance_sheet_snapshot_date"),
                }
            )
        return snapshot_date, top

    def _top_opportunities_from_diffs(
        self,
        store: "KnowledgeStore",  # type: ignore[name-defined]
    ) -> list[dict]:
        # ------------------------------------------------------------------
        # Top opportunities — lightweight ranking from all-time diffs
        #
        # Score = sigmoid(|delta_npv| / 50) × extraction_confidence × recency
        # where recency = 0.5 ^ (days_since / half_life=14).
        # This keeps the brief self-contained without requiring a watchlist config.
        # ------------------------------------------------------------------
        all_diff_rows = store._conn.execute(
            """
            SELECT
                vd.run_id, vd.asset_id, vd.event_id, vd.delta_npv,
                vd.created_at, vd.payload_json,
                e.event_type
            FROM valuation_diffs vd
            LEFT JOIN events e ON e.id = vd.event_id
            ORDER BY vd.created_at DESC
            LIMIT 500
            """,
        ).fetchall()

        today_dt = datetime.now(timezone.utc)
        scored: list[dict] = []
        for r in all_diff_rows:
            delta = r["delta_npv"] or 0.0
            conf: float = 0.5
            if r["event_id"]:
                sig_row = store._conn.execute(
                    "SELECT payload_json FROM structured_signals WHERE event_id = ? LIMIT 1",
                    (r["event_id"],),
                ).fetchone()
                if sig_row:
                    try:
                        conf = json.loads(sig_row["payload_json"]).get(
                            "extraction_confidence", 0.5
                        )
                    except Exception:
                        pass

            try:
                from datetime import timezone as _tz
                created_str = (r["created_at"] or "")[:19]
                created_dt = datetime.fromisoformat(created_str).replace(tzinfo=_tz.utc)
                days_old = max(0.0, (today_dt - created_dt).total_seconds() / 86400)
            except Exception:
                days_old = self.lookback_days

            recency = 0.5 ** (days_old / 14.0)
            val_score = 1.0 / (1.0 + math.exp(-abs(delta) / 50.0))
            composite = 0.50 * val_score + 0.25 * conf + 0.25 * recency

            scored.append(
                {
                    "rank": 0,
                    "asset_id": r["asset_id"] or "",
                    "delta_npv_millions": delta,
                    "composite_score": round(composite, 4),
                    "signal_event_type": r["event_type"],
                    "extraction_confidence": conf,
                    "run_id": r["run_id"],
                }
            )

        seen: dict[str, dict] = {}
        for s in scored:
            key = s["asset_id"]
            if key not in seen or s["composite_score"] > seen[key]["composite_score"]:
                seen[key] = s

        top = sorted(seen.values(), key=lambda x: x["composite_score"], reverse=True)[: self.top_n]
        for i, opp in enumerate(top, start=1):
            opp["rank"] = i
        return top


# ---------------------------------------------------------------------------
# Renderer  (Step 3 — template lookup)
# ---------------------------------------------------------------------------

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / \
    "src" / "bve" / "reporting" / "templates" / "weekly_brief.md.j2"

# Fallback: look relative to this file (installed package layout)
_TEMPLATE_PATH_ALT = Path(__file__).resolve().parent.parent / \
    "reporting" / "templates" / "weekly_brief.md.j2"


class WeeklyBriefRenderer:
    """
    Renders a ``WeeklyOpportunityBrief`` to Markdown via a Jinja2 template.
    """

    def __init__(self, template_path: Optional[Path] = None) -> None:
        if template_path is not None:
            self._tpl_path = template_path
        elif _TEMPLATE_PATH.exists():
            self._tpl_path = _TEMPLATE_PATH
        elif _TEMPLATE_PATH_ALT.exists():
            self._tpl_path = _TEMPLATE_PATH_ALT
        else:
            self._tpl_path = _TEMPLATE_PATH_ALT  # will fail at render time with a clear error

    def render(self, brief: WeeklyOpportunityBrief) -> str:
        """Return the brief as a Markdown string."""
        try:
            from jinja2 import Environment, FileSystemLoader, StrictUndefined
        except ImportError as exc:
            raise RuntimeError("jinja2 is required for WeeklyBriefRenderer") from exc

        env = Environment(
            loader=FileSystemLoader(str(self._tpl_path.parent)),
            undefined=StrictUndefined,
            autoescape=False,
        )
        env.filters["abs"] = abs
        env.filters["pct"] = lambda v: f"{v:.1%}" if v is not None else "n/a"
        env.filters["dollar"] = lambda v: f"${v:+.1f}M" if v is not None else "n/a"
        env.filters["severity_emoji"] = lambda s: {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(s, "⚪")

        tpl = env.get_template(self._tpl_path.name)
        return tpl.render(brief=brief)
