"""Portfolio-level chart spec builders."""
from __future__ import annotations

from typing import Mapping, Sequence


def plot_portfolio_exposure(exposure_by_indication: Mapping[str, float]) -> dict:
    labels = list(exposure_by_indication.keys())
    values = [float(v) for v in exposure_by_indication.values()]
    return {
        "data": [
            {
                "type": "pie",
                "labels": labels,
                "values": values,
                "hole": 0.35,
            }
        ],
        "layout": {
            "title": {"text": "Portfolio Exposure by Indication"},
            "template": "plotly_white",
        },
    }


def plot_opportunity_scores(rows: Sequence[dict]) -> dict:
    asset_ids = [str(r.get("asset_id", "")) for r in rows]
    scores = [float(r.get("composite_score", 0.0) or 0.0) for r in rows]
    return {
        "data": [
            {
                "type": "bar",
                "x": asset_ids,
                "y": scores,
                "name": "Opportunity Score",
            }
        ],
        "layout": {
            "title": {"text": "Top Opportunities"},
            "xaxis": {"title": {"text": "Asset"}},
            "yaxis": {"title": {"text": "Score"}, "range": [0, 1]},
            "template": "plotly_white",
        },
    }
