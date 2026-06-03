"""
Wave 4A — Streamlit Review Queue

Interactive UI for reviewing valuation diffs (proposed model changes) generated
by the intelligence pipeline.  Analysts can Accept, Reject, or Modify each
pending diff; decisions are persisted to the KnowledgeStore via
``add_review_decision()``, which also appends an immutable audit log entry.

Launch
------
    streamlit run src/bve/review_app.py -- --db outputs/intelligence_phase2/knowledge.db

Optional flags (passed after ``--``)
    --db PATH     Path to KnowledgeStore SQLite database (default: see below)
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import streamlit as st

# ---------------------------------------------------------------------------
# Path bootstrap so the package can be imported when launched from the repo root
# ---------------------------------------------------------------------------
_SRC = Path(__file__).resolve().parent.parent  # src/
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace  # noqa: E402
from bve.intelligence.schemas.runs import ReviewDecision  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_DB = "outputs/intelligence_phase2/knowledge.db"
_APP_TITLE = "BVE Review Queue"
_REVIEWER_STATE_KEY = "reviewer_id"


# ---------------------------------------------------------------------------
# Argument parsing (Streamlit passes CLI args after --)
# ---------------------------------------------------------------------------

def _parse_db_path() -> str:
    """Extract --db from sys.argv without conflicting with Streamlit's own args."""
    args = sys.argv[1:]
    try:
        idx = args.index("--db")
        return args[idx + 1]
    except (ValueError, IndexError):
        return _DEFAULT_DB


# ---------------------------------------------------------------------------
# DB helpers — queries run directly on _conn to avoid overhead
# ---------------------------------------------------------------------------

@st.cache_resource
def _open_store(db_path: str) -> KnowledgeStore:
    return KnowledgeStore(db_path=db_path)


def _pending_diffs(store: KnowledgeStore) -> list[dict]:
    """Return valuation_diffs rows that have no matching review_decision."""
    rows = store._conn.execute(
        """
        SELECT
            vd.run_id,
            vd.asset_id,
            vd.event_id,
            vd.delta_npv,
            vd.created_at,
            vd.payload_json
        FROM valuation_diffs vd
        WHERE NOT EXISTS (
            SELECT 1 FROM review_decisions rd WHERE rd.run_id = vd.run_id
        )
        ORDER BY vd.created_at DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _reviewed_diffs(store: KnowledgeStore, limit: int = 50) -> list[dict]:
    """Return valuation_diffs rows that have a review_decision, newest first."""
    rows = store._conn.execute(
        """
        SELECT
            vd.run_id,
            vd.asset_id,
            vd.event_id,
            vd.delta_npv,
            vd.created_at,
            rd.decision,
            rd.reviewer_id,
            rd.reviewed_at
        FROM valuation_diffs vd
        JOIN review_decisions rd ON rd.run_id = vd.run_id
        ORDER BY rd.reviewed_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def _signal_for_event(store: KnowledgeStore, event_id: str) -> Optional[dict]:
    """Return structured_signals payload dict for an event_id, or None."""
    row = store._conn.execute(
        "SELECT payload_json FROM structured_signals WHERE event_id = ? LIMIT 1",
        (event_id,),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload_json"])


def _event_for_id(store: KnowledgeStore, event_id: str) -> Optional[dict]:
    row = store._conn.execute(
        "SELECT payload_json FROM events WHERE id = ? LIMIT 1",
        (event_id,),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload_json"])


def _submit_decision(
    store: KnowledgeStore,
    *,
    run_id: str,
    asset_id: str,
    decision: str,
    reviewer_id: str,
    rationale: str,
    override_value: Optional[float],
    reviewer_confidence: Optional[float],
    analyst_tags: list[str],
    supporting_quote: Optional[str],
) -> None:
    """Build and persist a ReviewDecision for the given diff."""
    rec = ReviewDecision(
        id=str(uuid.uuid4()),
        proposal_id=run_id,   # valuation_diff run_id acts as the proposal identifier
        run_id=run_id,
        decision=decision,    # type: ignore[arg-type]
        reviewer_id=reviewer_id,
        reviewed_at=datetime.now(timezone.utc),
        override_value=override_value if override_value is not None else None,
        rationale=rationale,
        reviewer_confidence=reviewer_confidence if reviewer_confidence is not None else None,
        analyst_tags=analyst_tags,
        supporting_quote=supporting_quote or None,
    )
    trace = SourceTrace(source_type="review_app", source_ref="streamlit")
    store.add_review_decision(
        rec,
        company_id=None,
        asset_id=asset_id,
        source_trace=trace,
    )


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _confidence_badge(conf: Optional[float]) -> str:
    if conf is None:
        return "⬜ n/a"
    if conf >= 0.80:
        return f"🟢 {conf:.0%}"
    if conf >= 0.50:
        return f"🟡 {conf:.0%}"
    return f"🔴 {conf:.0%}"


def _delta_colour(delta: Optional[float]) -> str:
    if delta is None:
        return "gray"
    return "green" if delta >= 0 else "red"


def _severity_icon(delta_npv: Optional[float]) -> str:
    """Triage severity based on absolute ΔNPV magnitude."""
    if delta_npv is None:
        return "⚪"
    if abs(delta_npv) > 100:
        return "🔴"
    if abs(delta_npv) >= 25:
        return "🟡"
    return "⚪"


def _render_signal_card(signal: Optional[dict]) -> None:
    """Render structured_signal facts in a compact table."""
    if signal is None:
        st.caption("No linked structured signal found for this event.")
        return

    FIELD_LABELS = {
        "event_type":          "Event type",
        "signal_date":         "Signal date",
        "trial_phase":         "Trial phase",
        "primary_endpoint_met": "Primary endpoint met",
        "interim_flag":        "Interim data",
        "endpoint_type":       "Endpoint type",
        "hazard_ratio":        "Hazard ratio",
        "p_value":             "P-value",
        "response_rate":       "Response rate",
        "safety_grade":        "Safety grade (CTCAE)",
        "fda_action_type":     "FDA action",
        "designation_type":    "Designation",
        "deal_value_millions": "Deal value ($M)",
        "design_quality_tier": "Trial design tier",
        "design_quality_multiplier": "Design multiplier",
        "statistical_power": "Estimated statistical power",
        "low_power_flag": "Low-power flag",
        "extraction_model":    "Extraction model",
        "extraction_confidence": "LLM confidence",
    }

    rows = []
    for key, label in FIELD_LABELS.items():
        val = signal.get(key)
        if val is not None:
            if key == "extraction_confidence":
                val = f"{val:.1%}"
            elif key == "response_rate":
                val = f"{val:.1%}"
            elif key == "primary_endpoint_met":
                val = "Yes" if val else "No"
            elif key == "interim_flag":
                val = "Yes" if val else "No"
            rows.append({"Field": label, "Value": str(val)})

    if rows:
        import pandas as pd
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No structured signal fields to display.")


def _render_assumptions_changed(payload: dict) -> None:
    """Render the assumptions_changed list from a valuation_diff payload."""
    changes = payload.get("assumptions_changed", [])
    if not changes:
        st.caption("No assumption changes recorded.")
        return

    import pandas as pd
    rows = []
    for ch in changes:
        rows.append({
            "Parameter": ch.get("parameter_path", ch.get("parameter", "?")),
            "Before": ch.get("before", ch.get("current_value", "?")),
            "After":  ch.get("after", ch.get("proposed_value", "?")),
            "Delta %": ch.get("delta_pct", ""),
            "Rationale": ch.get("rationale", ""),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Per-diff review form
# ---------------------------------------------------------------------------

def _review_form(store: KnowledgeStore, diff: dict, reviewer_id: str) -> None:
    """Render the decision form for one pending diff inside an expander."""
    run_id = diff["run_id"]
    asset_id = diff.get("asset_id", "")
    event_id = diff.get("event_id", "")
    delta_npv = diff.get("delta_npv")
    created_at = diff.get("created_at", "")
    payload = json.loads(diff.get("payload_json", "{}"))

    # --- Signal extraction
    signal = _signal_for_event(store, event_id)
    event = _event_for_id(store, event_id)
    conf = signal.get("extraction_confidence") if signal else None

    severity = _severity_icon(delta_npv)
    label = (
        f"{severity}  {'↑' if (delta_npv or 0) >= 0 else '↓'}  "
        f"Asset: {asset_id or '—'}  |  "
        f"ΔNPV: ${delta_npv:+.1f}M  |  "
        f"Confidence: {_confidence_badge(conf)}  |  "
        f"{created_at[:10]}"
        if delta_npv is not None
        else f"{severity}  Asset: {asset_id or '—'}  |  {created_at[:10]}"
    )

    with st.expander(label, expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("ΔNPV ($M)", f"{delta_npv:+.1f}" if delta_npv is not None else "n/a")
        with col2:
            before_npv = payload.get("valuation_before", {}).get("rnpv_millions") or \
                         payload.get("valuation_before", {}).get("npv_millions")
            after_npv  = payload.get("valuation_after",  {}).get("rnpv_millions") or \
                         payload.get("valuation_after",  {}).get("npv_millions")
            if before_npv and after_npv:
                st.metric("NPV Before → After",
                          f"${after_npv:.1f}M",
                          delta=f"${delta_npv:+.1f}M" if delta_npv is not None else None)
            else:
                st.metric("Valuation before", f"${before_npv:.1f}M" if before_npv else "n/a")
        with col3:
            mkt_cap = payload.get("market_cap_snapshot_millions")
            st.metric("Mkt Cap Snapshot",
                      f"${mkt_cap:.0f}M" if mkt_cap else "n/a")

        st.markdown("**LLM Extraction**")
        if event is not None:
            st.caption(
                "Source: "
                f"{event.get('source_type', 'n/a')} | "
                f"{event.get('source_url', 'n/a')}"
            )
            if event.get("headline"):
                st.caption(f"Headline: {event.get('headline')}")
        _render_signal_card(signal)

        st.markdown("**Assumptions Changed**")
        _render_assumptions_changed(payload)

        st.divider()
        st.markdown("**Decision**")

        form_key = f"form_{run_id}"
        with st.form(key=form_key, clear_on_submit=True):
            dec_col, conf_col = st.columns(2)
            with dec_col:
                action = st.radio(
                    "Action",
                    options=["accepted", "modify", "rejected", "deferred"],
                    horizontal=True,
                    key=f"action_{run_id}",
                )
            with conf_col:
                rev_confidence = st.slider(
                    "Your confidence (0 = unsure, 1 = certain)",
                    min_value=0.0, max_value=1.0, value=0.7, step=0.05,
                    key=f"rconf_{run_id}",
                )

            rationale = st.text_area(
                "Rationale (required)",
                placeholder="Briefly explain your decision…",
                key=f"rationale_{run_id}",
            )

            override_str = st.text_input(
                "Override value (optional — leave blank to accept proposed value)",
                value="",
                key=f"override_{run_id}",
            )

            tags_str = st.text_input(
                "Analyst tags (comma-separated, e.g. interim_only, surrogate_endpoint)",
                value="",
                key=f"tags_{run_id}",
            )

            quote = st.text_area(
                "Supporting quote (optional — verbatim excerpt from source)",
                value="",
                key=f"quote_{run_id}",
            )

            submitted = st.form_submit_button("Submit decision")

        if submitted:
            if not rationale.strip():
                st.error("Rationale is required.")
                return

            override_value: Optional[float] = None
            if override_str.strip():
                try:
                    override_value = float(override_str.strip())
                except ValueError:
                    st.error(f"Override value must be a number, got: {override_str!r}")
                    return

            tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            decision = action
            if action == "modify":
                if override_value is None:
                    st.error("Modify requires an override value.")
                    return
                decision = "accepted"
                tags = sorted(set(tags + ["modified"]))

            _submit_decision(
                store,
                run_id=run_id,
                asset_id=asset_id,
                decision=decision,
                reviewer_id=reviewer_id,
                rationale=rationale.strip(),
                override_value=override_value,
                reviewer_confidence=rev_confidence,
                analyst_tags=tags,
                supporting_quote=quote.strip() or None,
            )
            st.success(f"Decision recorded: **{action}**")
            st.rerun()


# ---------------------------------------------------------------------------
# Reviewed items table
# ---------------------------------------------------------------------------

def _render_reviewed_table(store: KnowledgeStore) -> None:
    reviewed = _reviewed_diffs(store, limit=100)
    if not reviewed:
        st.info("No reviewed items yet.")
        return

    import pandas as pd
    rows = []
    for r in reviewed:
        rows.append({
            "Reviewed At": r.get("reviewed_at", "")[:16],
            "Decision":    r.get("decision", ""),
            "Asset":       r.get("asset_id", ""),
            "ΔNPV ($M)":  r.get("delta_npv"),
            "Reviewer":    r.get("reviewer_id", ""),
            "Diff Date":   (r.get("created_at") or "")[:10],
        })

    decision_icon = {"accepted": "✅", "rejected": "❌", "deferred": "🔁"}
    df = pd.DataFrame(rows)
    df["Decision"] = df["Decision"].map(lambda d: f"{decision_icon.get(d, '')} {d}")
    st.dataframe(df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title=_APP_TITLE,
        page_icon="🧬",
        layout="wide",
    )

    # --- Sidebar
    with st.sidebar:
        st.title("🧬 BVE Review Queue")
        db_path = st.text_input(
            "Database path",
            value=_parse_db_path(),
            help="Path to the KnowledgeStore SQLite file",
        )
        reviewer_id = st.text_input(
            "Reviewer ID",
            value=st.session_state.get(_REVIEWER_STATE_KEY, ""),
            placeholder="e.g. analyst-dj",
        )
        if reviewer_id:
            st.session_state[_REVIEWER_STATE_KEY] = reviewer_id

        st.divider()
        if st.button("Refresh"):
            st.cache_resource.clear()
            st.rerun()

    if not reviewer_id:
        st.warning("Enter your Reviewer ID in the sidebar to begin.")
        return

    # --- Load store
    try:
        store = _open_store(db_path)
    except Exception as exc:
        st.error(f"Cannot open database: {exc}")
        return

    # --- Header metrics
    pending = _pending_diffs(store)
    reviewed = _reviewed_diffs(store, limit=1000)
    accepted = sum(1 for r in reviewed if r.get("decision") == "accepted")
    rejected  = sum(1 for r in reviewed if r.get("decision") == "rejected")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Pending Review", len(pending))
    m2.metric("Accepted", accepted)
    m3.metric("Rejected", rejected)
    m4.metric("Deferred", len(reviewed) - accepted - rejected)

    st.divider()

    # --- Tabs
    tab_pending, tab_reviewed = st.tabs(["Pending", "Reviewed"])

    with tab_pending:
        if not pending:
            st.success("Queue is empty — no pending diffs.")
        else:
            st.markdown(f"### {len(pending)} item(s) awaiting review")
            for diff in pending:
                _review_form(store, diff, reviewer_id)

    with tab_reviewed:
        st.markdown("### Recently reviewed")
        _render_reviewed_table(store)


if __name__ == "__main__":
    main()
