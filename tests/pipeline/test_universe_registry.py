from __future__ import annotations

from pathlib import Path

import pytest

from bve.pipeline.universe_registry import UniverseRegistryEntry, load_universe_registry


def test_load_universe_registry_returns_all_entries() -> None:
    entries = load_universe_registry(Path("examples/configs/universe_registry.yaml"))
    # The registry grows as seeds are added; assert a floor + structural validity
    # rather than an exact count so seed expansion does not break this test.
    assert len(entries) >= 50
    assert all(isinstance(entry, UniverseRegistryEntry) for entry in entries)
    tickers = [e.ticker.upper() for e in entries]
    assert len(tickers) == len(set(tickers)), "registry tickers must be unique"


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
