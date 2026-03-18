from __future__ import annotations

from pathlib import Path

from bve.cli.run_asset import _build_objects
from bve.pipeline.auto_config_generator import AutoConfigGenerator
from bve.pipeline.disk_cache import DiskCache
from bve.pipeline.universe_registry import UniverseRegistryEntry
from bve.services.rate_limiter import ServiceRateLimiter


class _FakeGenerator(AutoConfigGenerator):
    def _fetch_ctgov_by_nct_id(self, nct_id: str) -> dict:  # type: ignore[override]
        return {
            "nct_id": nct_id,
            "phase": "PHASE3",
            "enrollment": 420,
            "primary_endpoint": "Progression-free survival",
            "estimated_completion_date": "2026-12",
        }

    def _fetch_sec_financials(self, ticker: str) -> dict:  # type: ignore[override]
        return {
            "ticker": ticker,
            "cash_millions": 800.0,
            "shares_outstanding_millions": 150.0,
            "burn_rate_millions_per_quarter": 45.0,
        }

    def _fetch_market_snapshot(self, ticker: str) -> dict:  # type: ignore[override]
        return {
            "ticker": ticker,
            "market_cap_millions": 24000.0,
            "current_price": 63.5,
        }


class _BrokenGenerator(_FakeGenerator):
    def generate(self, entry: UniverseRegistryEntry) -> dict:  # type: ignore[override]
        if entry.ticker == "FAIL":
            raise RuntimeError("forced failure")
        return super().generate(entry)


def _entry() -> UniverseRegistryEntry:
    return UniverseRegistryEntry(
        ticker="VRTX",
        company_name="Vertex Pharmaceuticals",
        asset_id="asset-vrtx-test",
        drug_name="VX-test",
        indication="Cystic fibrosis",
        therapeutic_area="rare_disease",
        stage="phase_3",
        modality="small_molecule",
        nct_id="NCT05033080",
        tam_millions=12000.0,
        net_price_per_patient_usd=250000.0,
        addressable_patients_annual=50000,
        peak_penetration=0.4,
        patent_life_years=10,
        discount_rate=0.1,
    )


def test_generate_builds_config_with_meta_and_is_parseable(tmp_path: Path) -> None:
    generator = _FakeGenerator(
        cache=DiskCache(root=tmp_path / "cache"),
        rate_limiter=ServiceRateLimiter(),
    )

    cfg = generator.generate(_entry())
    assert cfg["_meta"]["config_version"] == "auto-v1"
    assert cfg["_meta"]["generator_version"] == "0.3"

    asset, company, trials, market_model = _build_objects(cfg)
    assert asset.id == "asset-vrtx-test"
    assert company.ticker == "VRTX"
    assert len(trials) == 1
    assert market_model.asset_id == "asset-vrtx-test"


def test_generate_batch_continues_when_one_entry_fails(tmp_path: Path) -> None:
    good = _entry()
    bad = good.model_copy(update={"ticker": "FAIL"})
    generator = _BrokenGenerator(
        cache=DiskCache(root=tmp_path / "cache"),
        rate_limiter=ServiceRateLimiter(),
    )

    results = generator.generate_batch([good, bad])
    assert len(results) == 2
    assert results[0][2] is None
    assert results[0][1]
    assert results[1][2] is not None


def test_generate_reuses_cache_on_second_run(tmp_path: Path) -> None:
    class CountingGenerator(_FakeGenerator):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.ctgov_calls = 0
            self.sec_calls = 0
            self.market_calls = 0

        def _fetch_ctgov_by_nct_id(self, nct_id: str) -> dict:  # type: ignore[override]
            self.ctgov_calls += 1
            return super()._fetch_ctgov_by_nct_id(nct_id)

        def _fetch_sec_financials(self, ticker: str) -> dict:  # type: ignore[override]
            self.sec_calls += 1
            return super()._fetch_sec_financials(ticker)

        def _fetch_market_snapshot(self, ticker: str) -> dict:  # type: ignore[override]
            self.market_calls += 1
            return super()._fetch_market_snapshot(ticker)

    generator = CountingGenerator(
        cache=DiskCache(root=tmp_path / "cache"),
        rate_limiter=ServiceRateLimiter(),
    )
    entry = _entry()

    generator.generate(entry)
    generator.generate(entry)

    assert generator.ctgov_calls == 1
    assert generator.sec_calls == 1
    assert generator.market_calls == 1


def test_generate_normalizes_cell_gene_modality_to_valid_asset_enum(tmp_path: Path) -> None:
    generator = _FakeGenerator(
        cache=DiskCache(root=tmp_path / "cache"),
        rate_limiter=ServiceRateLimiter(),
    )
    cfg = generator.generate(_entry().model_copy(update={"modality": "cell_gene"}))
    assert cfg["asset"]["modality"] == "gene_therapy"
