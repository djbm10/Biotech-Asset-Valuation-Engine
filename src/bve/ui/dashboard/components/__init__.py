"""Dashboard components."""

from bve.ui.dashboard.components.asset_dashboard import render_asset_dashboard
from bve.ui.dashboard.components.opportunity_dashboard import render_opportunity_dashboard
from bve.ui.dashboard.components.portfolio_dashboard import render_portfolio_dashboard

__all__ = [
    "render_asset_dashboard",
    "render_opportunity_dashboard",
    "render_portfolio_dashboard",
]
