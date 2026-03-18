"""Competitor map chart spec builders."""
from __future__ import annotations

from typing import Sequence


def plot_competitor_pipeline(entries: Sequence[dict]) -> dict:
    drugs = [str(e.get("drug") or e.get("drug_name") or "unknown") for e in entries]
    phases = [str(e.get("phase") or "unknown") for e in entries]
    scores = [float(e.get("risk_score", 0.0) or 0.0) for e in entries]
    return {
        "data": [
            {
                "type": "scatter",
                "mode": "markers",
                "x": phases,
                "y": scores,
                "text": drugs,
                "name": "Competitors",
            }
        ],
        "layout": {
            "title": {"text": "Competitor Pipeline Map"},
            "xaxis": {"title": {"text": "Phase"}},
            "yaxis": {"title": {"text": "Risk Score"}, "range": [0, 1]},
            "template": "plotly_white",
        },
    }
