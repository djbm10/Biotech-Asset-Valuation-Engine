from __future__ import annotations

from bve.visualization import (
    plot_competitor_pipeline,
    plot_npv_distribution,
    plot_opportunity_scores,
    plot_portfolio_exposure,
    plot_probability_tree,
    plot_trial_timeline,
)


def test_visualization_builders_return_plotly_json_shape():
    specs = [
        plot_npv_distribution([10, 20, 30]),
        plot_probability_tree([("phase_2", 0.4), ("phase_3", 0.2)]),
        plot_trial_timeline([{"name": "trial-1", "start_date": "2025-01-01", "end_date": "2026-01-01"}]),
        plot_portfolio_exposure({"oncology": 0.6, "immunology": 0.4}),
        plot_opportunity_scores([{"asset_id": "A", "composite_score": 0.7}]),
        plot_competitor_pipeline([{"drug": "Drug X", "phase": "phase_3", "risk_score": 0.5}]),
    ]
    for spec in specs:
        assert isinstance(spec, dict)
        assert "data" in spec
        assert "layout" in spec
