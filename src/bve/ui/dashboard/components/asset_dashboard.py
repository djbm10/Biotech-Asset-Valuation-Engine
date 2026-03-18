"""Asset dashboard component."""
from __future__ import annotations

from typing import Any


def render_asset_dashboard(st: Any, payload: dict, asset_id: str) -> None:
    st.subheader(f"Asset: {asset_id}")
    run = payload.get("watchlist_summary", {})
    assets = run.get("assets", [])
    row = next((a for a in assets if a.get("asset_id") == asset_id), None)
    if row is None:
        st.info("No cached row for this asset.")
        return
    cols = st.columns(4)
    cols[0].metric("Docs Fetched", int(row.get("documents_fetched", 0)))
    cols[1].metric("Signals", int(row.get("signals_created", 0)))
    cols[2].metric("Events", int(row.get("events_created", 0)))
    cols[3].metric("Valuation Diffs", int(row.get("valuation_diffs_persisted", 0)))
    st.json(row)
