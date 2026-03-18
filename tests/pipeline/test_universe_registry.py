from __future__ import annotations

from pathlib import Path

import pytest

from bve.pipeline.universe_registry import UniverseRegistryEntry, load_universe_registry


def test_load_universe_registry_returns_30_entries() -> None:
    entries = load_universe_registry(Path("examples/configs/universe_registry.yaml"))
    assert len(entries) == 30
    assert all(isinstance(entry, UniverseRegistryEntry) for entry in entries)


def test_universe_registry_entry_validation_rejects_invalid_peak_penetration() -> None:
    with pytest.raises(Exception):
        UniverseRegistryEntry(
            ticker="ABC",
            company_name="ABC Bio",
            asset_id="asset-abc",
            drug_name="ABC-101",
            indication="Test indication",
            therapeutic_area="oncology",
            stage="phase_2",
            modality="small_molecule",
            peak_penetration=1.5,
        )
