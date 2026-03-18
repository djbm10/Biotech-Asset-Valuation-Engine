"""Valuation chart spec builders (Plotly JSON-like dicts)."""
from __future__ import annotations

from typing import Sequence


def plot_npv_distribution(npv_samples: Sequence[float], *, title: str = "rNPV Distribution") -> dict:
    values = [float(v) for v in npv_samples]
    return {
        "data": [
            {
                "type": "histogram",
                "x": values,
                "nbinsx": min(60, max(10, len(values) // 20 or 10)),
                "name": "rNPV ($M)",
            }
        ],
        "layout": {
            "title": {"text": title},
            "xaxis": {"title": {"text": "rNPV ($M)"}},
            "yaxis": {"title": {"text": "Frequency"}},
            "template": "plotly_white",
        },
    }


def plot_probability_tree(stages: Sequence[tuple[str, float]], *, title: str = "Probability Tree") -> dict:
    labels = [s[0] for s in stages]
    values = [float(s[1]) for s in stages]
    return {
        "data": [
            {
                "type": "bar",
                "x": labels,
                "y": values,
                "name": "Probability",
            }
        ],
        "layout": {
            "title": {"text": title},
            "xaxis": {"title": {"text": "Stage"}},
            "yaxis": {"title": {"text": "Probability"}, "range": [0, 1]},
            "template": "plotly_white",
        },
    }
