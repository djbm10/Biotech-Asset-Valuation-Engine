from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml

from bve.ops.replay_universe_builder import (
    DEFAULT_OUTPUT_PATH,
    ReplayUniverseBuilder,
)


def test_builder_merges_sources_and_preserves_primary_ticker_entry(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            [
                {
                    "ticker": "ABC",
                    "asset_id": "a-abc",
                    "company_id": "co-abc",
                    "ranking_score": 0.7,
                    "opportunity_score": 0.65,
                    "claim_type": "endpoint_met",
                    "claim_assertion": "ABC has an underappreciated catalyst.",
                    "catalyst": "ABC baseline catalyst",
                }
            ]
        ),
        encoding="utf-8",
    )
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        yaml.safe_dump(
            [
                {
                    "ticker": "ABC",
                    "company_name": "ABC Corp",
                    "asset_id": "asset-abc-registry",
                    "drug_name": "ABC-001",
                    "indication": "oncology",
                    "therapeutic_area": "oncology",
                    "stage": "phase_2",
                    "modality": "small_molecule",
                },
                {
                    "ticker": "DEF",
                    "company_name": "DEF Corp",
                    "asset_id": "asset-def",
                    "drug_name": "DEF-001",
                    "indication": "rare disease",
                    "therapeutic_area": "rare_disease",
                    "stage": "phase_3",
                    "modality": "biologic",
                },
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    deal_universe_path = tmp_path / "deals.yaml"
    deal_universe_path.write_text(
        yaml.safe_dump(
            {
                "as_of_date": "2026-03-22",
                "deals": [
                    {
                        "target_name": "ABC Corp",
                        "target_ticker": "ABC",
                        "acquirer": "Big Pharma",
                        "announcement_date": "2025-02-01",
                        "lead_asset": "ABC-001",
                        "indication": "oncology",
                        "therapeutic_area": "oncology",
                        "phase_at_acquisition": "phase_2",
                    },
                    {
                        "target_name": "XYZ Corp",
                        "target_ticker": "XYZ",
                        "acquirer": "Big Pharma",
                        "announcement_date": "2025-03-01",
                        "lead_asset": "XYZ-001",
                        "indication": "immunology",
                        "therapeutic_area": "immunology",
                        "phase_at_acquisition": "phase_3",
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    target_monitor_path = tmp_path / "targets.yaml"
    target_monitor_path.write_text(
        yaml.safe_dump(
            {
                "as_of_date": "2026-03-22",
                "targets": [
                    {
                        "company_name": "ABC Corp",
                        "ticker": "ABC",
                        "status": "independent_public_target",
                        "therapeutic_area": "oncology",
                        "lead_assets": "ABC-001",
                        "stage": "phase_2",
                        "source_url": "https://example.com/abc",
                    },
                    {
                        "company_name": "MON Corp",
                        "ticker": "MON",
                        "status": "independent_public_target",
                        "therapeutic_area": "cns",
                        "lead_assets": "MON-001",
                        "stage": "phase_1 / phase_2",
                        "source_url": "https://example.com/mon",
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    builder = ReplayUniverseBuilder(
        baseline_universe_path=baseline_path,
        registry_path=registry_path,
        deal_universe_path=deal_universe_path,
        target_monitor_path=target_monitor_path,
        replay_start=date(2021, 1, 1),
    )

    result = builder.build()

    assert len(result.universe) == 4
    abc = next(entry for entry in result.universe if entry["ticker"] == "ABC")
    xyz = next(entry for entry in result.universe if entry["ticker"] == "XYZ")
    assert abc["asset_id"] == "a-abc"
    assert abc["source"] == "baseline_replay_universe"
    assert abc["source_tags"] == [
        "baseline_replay_universe",
        "mna_public_deal_universe",
        "mna_target_monitor",
        "universe_registry",
    ]
    assert xyz["asset_id"] == "a-xyz"
    assert xyz["ranking_score"] == 0.58
    assert result.recommended_replay_start == date(2021, 1, 1)
    assert result.recommended_backfill_end == date(2026, 3, 22)


def test_committed_expanded_universe_matches_builder_and_exceeds_60_names() -> None:
    builder = ReplayUniverseBuilder()
    result = builder.build()
    committed = yaml.safe_load(DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8"))

    assert len(result.universe) >= 60
    assert result.to_payload() == committed
