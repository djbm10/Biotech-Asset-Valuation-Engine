"""Portfolio dashboard component."""
from __future__ import annotations

from typing import Any


def render_portfolio_dashboard(st: Any, payload: dict) -> None:
    st.subheader("Portfolio Summary")
    run = payload.get("watchlist_summary", {})
    assets = run.get("assets", [])
    total_assets = len(assets)
    failed = sum(1 for a in assets if a.get("status") == "failure")
    diffs = sum(int(a.get("valuation_diffs_persisted", 0) or 0) for a in assets)
    memos = sum(1 for a in assets if a.get("memo_generated"))
    cols = st.columns(4)
    cols[0].metric("Assets", total_assets)
    cols[1].metric("Failures", failed)
    cols[2].metric("Valuation Diffs", diffs)
    cols[3].metric("Memos", memos)
    st.dataframe(assets, use_container_width=True, hide_index=True)

    metrics = payload.get("metrics_dashboard", {})
    top_company_rows = metrics.get("top_opportunities", [])
    if top_company_rows:
        st.subheader("Top Company Decisions")
        st.caption(
            "Source: "
            f"{metrics.get('top_opportunities_source_mode', 'unknown')}"
            + (
                f" | Reference snapshot: {metrics.get('top_opportunities_reference_date')}"
                if metrics.get("top_opportunities_reference_date")
                else ""
            )
        )
        display_rows = []
        for row in top_company_rows:
            display_rows.append(
                {
                    "rank": row.get("rank"),
                    "ticker": row.get("ticker") or row.get("asset_id"),
                    "company_name": row.get("company_name"),
                    "disc_x": row.get("ranked_sotp_discount") or row.get("score"),
                    "action_policy": row.get("action_policy"),
                    "coverage_pct": row.get("modeled_asset_coverage_pct"),
                    "sotp_m": row.get("sotp_equity_value_millions"),
                    "ev_m": row.get("enterprise_value_millions"),
                    "bs_snapshot": row.get("balance_sheet_snapshot_date"),
                }
            )
        st.dataframe(display_rows, use_container_width=True, hide_index=True)
