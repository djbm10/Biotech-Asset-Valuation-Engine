from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from bve.intelligence.comparable_deals import (
    ComparableDeal,
    ComparableDealLoader,
    ComparableDealMatcher,
)


def test_comparable_deal_loader_populates_ev_to_peak_sales(tmp_path: Path):
    path = tmp_path / "comps.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "deals": [
                    {
                        "target_name": "Example Therapeutics",
                        "indication": "Indication X",
                        "therapeutic_area": "oncology",
                        "phase_at_acquisition": "phase_2",
                        "acquirer": "Large Pharma",
                        "deal_date": "2025-02-14",
                        "enterprise_value_millions": 3200,
                        "peak_sales_millions": 1600,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    deal_set = ComparableDealLoader.load(path)

    assert len(deal_set.deals) == 1
    assert deal_set.deals[0].ev_to_peak_sales == pytest.approx(2.0, abs=1e-9)


def test_comparable_deal_loader_accepts_direct_multiple_without_raw_inputs(tmp_path: Path):
    path = tmp_path / "comps.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "deals": [
                    {
                        "target_name": "Example Therapeutics",
                        "indication": "Indication X",
                        "therapeutic_area": "oncology",
                        "phase_at_acquisition": "phase_2",
                        "acquirer": "Large Pharma",
                        "deal_date": "2025-02-14",
                        "ev_to_peak_sales": 2.75,
                        "source": "Press release + analyst note",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    deal_set = ComparableDealLoader.load(path)

    assert len(deal_set.deals) == 1
    assert deal_set.deals[0].ev_to_peak_sales == pytest.approx(2.75, abs=1e-9)
    assert deal_set.deals[0].enterprise_value_millions is None
    assert deal_set.deals[0].peak_sales_millions is None


def test_comparable_deal_requires_multiple_or_raw_inputs():
    with pytest.raises(ValidationError):
        ComparableDeal.model_validate(
            {
                "target_name": "Example Therapeutics",
                "indication": "Indication X",
                "therapeutic_area": "oncology",
                "phase_at_acquisition": "phase_2",
                "acquirer": "Large Pharma",
                "deal_date": "2025-02-14",
            }
        )


def test_comparable_deal_matcher_prefers_exact_indication_phase():
    deals = [
        _deal(
            target_name="Exact A",
            indication="Ulcerative colitis",
            therapeutic_area="immunology",
            phase_at_acquisition="phase_2",
            enterprise_value_millions=3000,
            peak_sales_millions=1000,
            acquirer="Pharma A",
            deal_date="2024-03-01",
        ),
        _deal(
            target_name="Exact B",
            indication="Ulcerative colitis",
            therapeutic_area="immunology",
            phase_at_acquisition="phase ii",
            enterprise_value_millions=2000,
            peak_sales_millions=1000,
            acquirer="Pharma B",
            deal_date="2025-06-20",
        ),
        _deal(
            target_name="TA Only",
            indication="Crohn's disease",
            therapeutic_area="immunology",
            phase_at_acquisition="phase_2",
            enterprise_value_millions=1000,
            peak_sales_millions=1000,
            acquirer="Pharma C",
            deal_date="2025-10-01",
        ),
    ]

    analysis = ComparableDealMatcher.analyze(
        asset_indication="Ulcerative Colitis",
        asset_therapeutic_area="Immunology",
        asset_stage="phase_2",
        asset_ev_to_peak_sales=2.0,
        deals=deals,
    )

    assert analysis.match_tier == "exact_indication_phase"
    assert analysis.n_comps == 2
    assert analysis.peer_min_ev_to_peak_sales == pytest.approx(2.0, abs=1e-9)
    assert analysis.peer_median_ev_to_peak_sales == pytest.approx(2.5, abs=1e-9)
    assert analysis.peer_max_ev_to_peak_sales == pytest.approx(3.0, abs=1e-9)
    assert analysis.percentile_vs_comps == pytest.approx(0.25, abs=1e-9)
    assert analysis.premium_discount_vs_median == pytest.approx(-0.2, abs=1e-9)
    assert analysis.matched_targets == ["Exact A", "Exact B"]


def test_comparable_deal_matcher_falls_back_to_therapeutic_area_then_phase_only():
    deals = [
        _deal(
            target_name="TA Match",
            indication="Psoriasis",
            therapeutic_area="immunology",
            phase_at_acquisition="phase_2",
            enterprise_value_millions=1800,
            peak_sales_millions=1000,
            acquirer="Pharma A",
            deal_date="2024-04-01",
        ),
        _deal(
            target_name="Phase Only",
            indication="Rare disease",
            therapeutic_area="genetic medicine",
            phase_at_acquisition="phase_2",
            enterprise_value_millions=2400,
            peak_sales_millions=1000,
            acquirer="Pharma B",
            deal_date="2025-01-15",
        ),
    ]

    ta_analysis = ComparableDealMatcher.analyze(
        asset_indication="Ulcerative colitis",
        asset_therapeutic_area="immunology",
        asset_stage="phase_2",
        asset_ev_to_peak_sales=1.8,
        deals=deals,
    )
    phase_analysis = ComparableDealMatcher.analyze(
        asset_indication="Amyotrophic lateral sclerosis",
        asset_therapeutic_area="neuroscience",
        asset_stage="phase_2",
        asset_ev_to_peak_sales=2.4,
        deals=deals,
    )

    assert ta_analysis.match_tier == "therapeutic_area_phase"
    assert ta_analysis.n_comps == 1
    assert ta_analysis.peer_median_ev_to_peak_sales == pytest.approx(1.8, abs=1e-9)
    assert phase_analysis.match_tier == "phase_only"
    assert phase_analysis.n_comps == 2
    assert phase_analysis.percentile_vs_comps == pytest.approx(0.75, abs=1e-9)


def test_comparable_deal_matcher_returns_no_comps_without_asset_multiple():
    deals = [
        _deal(
            target_name="Exact A",
            indication="Ulcerative colitis",
            therapeutic_area="immunology",
            phase_at_acquisition="phase_2",
            enterprise_value_millions=3000,
            peak_sales_millions=1000,
            acquirer="Pharma A",
            deal_date="2024-03-01",
        )
    ]

    analysis = ComparableDealMatcher.analyze(
        asset_indication="Ulcerative colitis",
        asset_therapeutic_area="immunology",
        asset_stage="phase_2",
        asset_ev_to_peak_sales=None,
        deals=deals,
    )

    assert analysis.match_tier == "no_comps"
    assert analysis.n_comps == 0
    assert analysis.percentile_vs_comps is None


def _deal(**overrides: object) -> ComparableDeal:
    return ComparableDeal.model_validate(overrides)
