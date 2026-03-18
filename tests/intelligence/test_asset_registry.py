from __future__ import annotations

from datetime import datetime, timezone

from bve.intelligence.competitor_discovery import CompetitorProgram
from bve.intelligence.knowledge_layer import AssetRegistryEntry, KnowledgeStore


def _entry() -> AssetRegistryEntry:
    return AssetRegistryEntry(
        asset_id="asset-1",
        ticker="VRTX",
        company_id="vrtx-auto",
        drug_name="VX-test",
        indication="Cystic fibrosis",
        therapeutic_area="rare_disease",
        modality="small_molecule",
        stage="phase_3",
        nct_id="NCT001",
        tam_millions=12000.0,
        source="auto_generated",
    )


def test_asset_registry_upsert_and_get_roundtrip() -> None:
    store = KnowledgeStore(":memory:")
    try:
        entry = _entry()
        store.upsert_asset_registry_entry(entry)

        got = store.get_asset_registry_entry("asset-1")
        assert got is not None
        assert got.asset_id == "asset-1"
        assert got.ticker == "VRTX"
        assert got.last_competitor_discovery_at is None
    finally:
        store.close()


def test_asset_registry_upsert_same_entry_twice_no_error() -> None:
    store = KnowledgeStore(":memory:")
    try:
        entry = _entry()
        store.upsert_asset_registry_entry(entry)
        store.upsert_asset_registry_entry(entry)

        rows = store.list_asset_registry()
        assert len(rows) == 1
    finally:
        store.close()


def test_asset_registry_unique_ticker_drug_indication_prevents_duplicates() -> None:
    store = KnowledgeStore(":memory:")
    try:
        base = _entry()
        store.upsert_asset_registry_entry(base)
        store.upsert_asset_registry_entry(
            base.model_copy(update={"asset_id": "asset-2"})
        )

        rows = store.list_asset_registry()
        assert len(rows) == 1
    finally:
        store.close()


def test_asset_registry_filters_by_ta_and_stage() -> None:
    store = KnowledgeStore(":memory:")
    try:
        store.upsert_asset_registry_entry(_entry())
        store.upsert_asset_registry_entry(
            AssetRegistryEntry(
                asset_id="asset-2",
                ticker="MRNA",
                company_id="mrna-auto",
                drug_name="mRNA-X",
                indication="Melanoma",
                therapeutic_area="oncology",
                modality="biologic",
                stage="phase_2",
                nct_id="NCT002",
                tam_millions=5000.0,
                source="auto_generated",
            )
        )

        assert len(store.list_asset_registry(ta="rare_disease")) == 1
        assert len(store.list_asset_registry(stage="phase_2")) == 1
    finally:
        store.close()


def test_count_competitor_programs_and_discovery_timestamp_update() -> None:
    store = KnowledgeStore(":memory:")
    try:
        store.upsert_asset_registry_entry(_entry())
        store.add_competitor_program(
            CompetitorProgram(
                asset_id="asset-1",
                company="CompCo",
                drug_name="CompDrug",
                nct_id="NCT-COMP-1",
                indication="Cystic fibrosis",
            )
        )

        assert store.count_competitor_programs("asset-1") == 1

        ts = datetime(2026, 3, 9, 13, 0, tzinfo=timezone.utc)
        store.update_competitor_discovery_timestamp("asset-1", ts)
        got = store.get_asset_registry_entry("asset-1")
        assert got is not None
        assert got.last_competitor_discovery_at == ts
    finally:
        store.close()
