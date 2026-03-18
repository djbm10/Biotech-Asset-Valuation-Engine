"""Clinical timeline chart spec builders."""
from __future__ import annotations

from typing import Sequence


def plot_trial_timeline(trials: Sequence[dict], *, title: str = "Clinical Timeline") -> dict:
    names: list[str] = []
    starts: list[str] = []
    ends: list[str] = []
    for trial in trials:
        names.append(str(trial.get("name") or trial.get("id") or "trial"))
        starts.append(str(trial.get("start_date") or trial.get("start") or ""))
        ends.append(str(trial.get("end_date") or trial.get("primary_completion_date") or ""))
    return {
        "data": [
            {
                "type": "bar",
                "orientation": "h",
                "y": names,
                "x": [1 for _ in names],
                "base": starts,
                "customdata": ends,
                "hovertemplate": "%{y}<br>Start: %{base}<br>End: %{customdata}<extra></extra>",
                "name": "Trials",
            }
        ],
        "layout": {
            "title": {"text": title},
            "xaxis": {"title": {"text": "Timeline"}},
            "yaxis": {"title": {"text": "Trial"}},
            "template": "plotly_white",
        },
    }
