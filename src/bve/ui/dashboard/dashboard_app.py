"""Streamlit dashboard shell for cached intelligence views."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from bve.ui.dashboard.cache import DashboardCacheMetadata, DashboardCacheStore
from bve.ui.dashboard.components import (
    render_asset_dashboard,
    render_opportunity_dashboard,
    render_portfolio_dashboard,
)


def format_cache_metadata_text(meta: DashboardCacheMetadata) -> str:
    return (
        f"cache_version={meta.cache_version} | "
        f"source_run_id={meta.source_run_id} | "
        f"source_model_version={meta.source_model_version} | "
        f"generated_at={meta.generated_at.isoformat()}"
    )


def load_cache(path: str | Path) -> Optional[dict]:
    rec = DashboardCacheStore(path).read()
    if rec is None:
        return None
    return rec.model_dump(mode="json")


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="BVE Dashboard", layout="wide")
    st.title("Biotech Intelligence Dashboard")

    cache_path = st.sidebar.text_input("Cache path", value="outputs/dashboard/cache.json")
    rec = DashboardCacheStore(cache_path).read()
    if rec is None:
        st.warning("No dashboard cache found. Run intelligence service first.")
        return

    st.caption(format_cache_metadata_text(rec.metadata))

    payload = rec.payload
    tab_portfolio, tab_opportunities, tab_assets = st.tabs(
        ["Portfolio", "Opportunities", "Asset"]
    )

    with tab_portfolio:
        render_portfolio_dashboard(st, payload)

    with tab_opportunities:
        render_opportunity_dashboard(st, payload)

    with tab_assets:
        assets = payload.get("watchlist_summary", {}).get("assets", [])
        ids = [a.get("asset_id") for a in assets if a.get("asset_id")]
        if not ids:
            st.info("No assets in cached payload.")
        else:
            selected = st.selectbox("Asset", options=ids, index=0)
            render_asset_dashboard(st, payload, selected)


if __name__ == "__main__":
    main()
