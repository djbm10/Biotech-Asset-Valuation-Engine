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
