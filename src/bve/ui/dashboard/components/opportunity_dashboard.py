"""Opportunity dashboard component."""
from __future__ import annotations

from typing import Any


def render_opportunity_dashboard(st: Any, payload: dict) -> None:
    st.subheader("Opportunities")
    scan = payload.get("opportunity_scan", {})
    opportunities = scan.get("opportunities", [])
    alerts = scan.get("alerts_emitted", [])
    cols = st.columns(3)
    cols[0].metric("Opportunities", len(opportunities))
    cols[1].metric("Alerts Emitted", len(alerts))
    cols[2].metric(
        "Suppressed Duplicates",
        int(scan.get("alerts_suppressed_as_duplicate", 0) or 0),
    )
    if opportunities:
        st.dataframe(opportunities, use_container_width=True, hide_index=True)
    else:
        st.info("No opportunity rows in current cache.")
