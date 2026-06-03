"""
Sprint D1 — Modality-aware COGS defaults.

Rules:
  1. Explicit MarketModel.cogs_rate wins unconditionally.
  2. If modality is set and cogs_rate is not explicit, load from YAML table.
  3. If neither, keep default 0.18 (same as 'other').
  4. ValuationEngine.from_program() auto-propagates asset modality → market model.
"""
from __future__ import annotations

import pytest

from bve.config.assumptions_loader import AssumptionsLoader
from bve.entities.asset import Asset, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.drug_asset_program import DrugAssetProgram
from bve.models.market_model import MarketModel
from bve.valuation.valuation_engine import ValuationEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_market(cogs_rate=None, modality=None) -> MarketModel:
    kwargs = dict(
        asset_id="test-asset",
        therapeutic_area="oncology",
        total_addressable_market_millions=1000.0,
        peak_penetration=0.05,
        patent_life_years=10,
    )
    if cogs_rate is not None:
        kwargs["cogs_rate"] = cogs_rate
    if modality is not None:
        kwargs["modality"] = modality
    return MarketModel(**kwargs)


def _asset(modality: Modality = Modality.BIOLOGIC) -> Asset:
    return Asset(
        id="test-asset",
        name="TestDrug",
        indication="NSCLC",
        modality=modality,
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage="phase_3",
        discount_rate=0.10,
    )


def _trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(asset_id="test-asset", phase=TrialPhase.PHASE_3,
                      success_probability=0.60, duration_years=3.0, cost_millions=200.0),
    ]


# ---------------------------------------------------------------------------
# Rule 1: AssumptionsLoader YAML values for Sprint D1
# ---------------------------------------------------------------------------

class TestYAMLValues:
    """YAML table must contain the Sprint D1 calibrated values."""

    def test_small_molecule(self):
        assert AssumptionsLoader.get().cogs_rate("small_molecule") == pytest.approx(0.12)

    def test_biologic(self):
        assert AssumptionsLoader.get().cogs_rate("biologic") == pytest.approx(0.28)

    def test_gene_therapy(self):
        assert AssumptionsLoader.get().cogs_rate("gene_therapy") == pytest.approx(0.45)

    def test_cell_therapy(self):
        assert AssumptionsLoader.get().cogs_rate("cell_therapy") == pytest.approx(0.60)

    def test_adc(self):
        assert AssumptionsLoader.get().cogs_rate("adc") == pytest.approx(0.30)

    def test_rna_therapy(self):
        assert AssumptionsLoader.get().cogs_rate("rna_therapy") == pytest.approx(0.22)

    def test_other(self):
        assert AssumptionsLoader.get().cogs_rate("other") == pytest.approx(0.18)

    def test_unknown_falls_back_to_other_with_warning(self):
        with pytest.warns(UserWarning, match="cogs_rate"):
            rate = AssumptionsLoader.get().cogs_rate("unknown_modality_xyz")
        assert rate == pytest.approx(0.18)


# ---------------------------------------------------------------------------
# Rule 2: MarketModel.modality field — direct construction
# ---------------------------------------------------------------------------

class TestMarketModelModalityField:
    """MarketModel uses modality to fill cogs_rate from YAML at construction."""

    def test_modality_biologic_loads_yaml_cogs(self):
        mm = _simple_market(modality="biologic")
        assert mm.cogs_rate == pytest.approx(0.28)

    def test_modality_gene_therapy_loads_yaml_cogs(self):
        mm = _simple_market(modality="gene_therapy")
        assert mm.cogs_rate == pytest.approx(0.45)

    def test_modality_cell_therapy_loads_yaml_cogs(self):
        mm = _simple_market(modality="cell_therapy")
        assert mm.cogs_rate == pytest.approx(0.60)

    def test_modality_adc_loads_yaml_cogs(self):
        mm = _simple_market(modality="adc")
        assert mm.cogs_rate == pytest.approx(0.30)

    def test_modality_rna_therapy_loads_yaml_cogs(self):
        mm = _simple_market(modality="rna_therapy")
        assert mm.cogs_rate == pytest.approx(0.22)

    def test_modality_small_molecule_loads_yaml_cogs(self):
        mm = _simple_market(modality="small_molecule")
        assert mm.cogs_rate == pytest.approx(0.12)

    def test_modality_other_loads_yaml_cogs(self):
        mm = _simple_market(modality="other")
        assert mm.cogs_rate == pytest.approx(0.18)

    def test_no_modality_uses_default(self):
        mm = _simple_market()
        assert mm.cogs_rate == pytest.approx(0.18)

    def test_unknown_modality_falls_back_with_warning(self):
        with pytest.warns(UserWarning):
            mm = _simple_market(modality="mystery_modality")
        assert mm.cogs_rate == pytest.approx(0.18)  # 'other' fallback

    def test_modality_field_stored(self):
        mm = _simple_market(modality="biologic")
        assert mm.modality == "biologic"

    def test_no_modality_field_is_none(self):
        mm = _simple_market()
        assert mm.modality is None


# ---------------------------------------------------------------------------
# Rule 3: Explicit cogs_rate always wins
# ---------------------------------------------------------------------------

class TestExplicitCogsRateWins:
    """Explicit cogs_rate must override YAML default regardless of modality."""

    def test_explicit_cogs_wins_over_modality(self):
        mm = _simple_market(cogs_rate=0.05, modality="biologic")
        # 0.05 should win over biologic's 0.28
        assert mm.cogs_rate == pytest.approx(0.05)

    def test_explicit_cogs_wins_for_gene_therapy(self):
        mm = _simple_market(cogs_rate=0.99, modality="gene_therapy")
        assert mm.cogs_rate == pytest.approx(0.99)

    def test_explicit_cogs_wins_no_modality(self):
        mm = _simple_market(cogs_rate=0.33)
        assert mm.cogs_rate == pytest.approx(0.33)

    def test_explicit_cogs_zero_is_preserved(self):
        """cogs_rate=0.0 is a valid override (e.g., partnership with no COGS exposure)."""
        mm = _simple_market(cogs_rate=0.0, modality="cell_therapy")
        assert mm.cogs_rate == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Rule 4: ValuationEngine.from_program() auto-propagates modality
# ---------------------------------------------------------------------------

class TestValuationEngineModality:
    """from_program() should auto-populate market_model.modality from asset.modality."""

    def _build_engine(self, asset_modality: Modality, cogs_rate=None) -> ValuationEngine:
        asset = _asset(modality=asset_modality)
        trials = _trials()
        kwargs = dict(
            asset_id="test-asset",
            therapeutic_area="oncology",
            total_addressable_market_millions=1000.0,
            peak_penetration=0.05,
            patent_life_years=10,
        )
        if cogs_rate is not None:
            kwargs["cogs_rate"] = cogs_rate
        mm = MarketModel(**kwargs)
        program = DrugAssetProgram.build(asset=asset, trials=trials, market_model=mm, load_loe=False)
        company = Company(id="co", name="TestCo", cash_millions=100.0, shares_outstanding_millions=50.0)
        return ValuationEngine.from_program(program, company)

    def test_engine_biologic_gets_yaml_cogs(self):
        engine = self._build_engine(Modality.BIOLOGIC)
        # _resolve_market_model_with_sgna applies the modality + cogs
        mm = engine._resolve_market_model_with_sgna()
        assert mm.modality == "biologic"
        assert mm.cogs_rate == pytest.approx(0.28)

    def test_engine_gene_therapy_gets_yaml_cogs(self):
        engine = self._build_engine(Modality.GENE_THERAPY)
        mm = engine._resolve_market_model_with_sgna()
        assert mm.modality == "gene_therapy"
        assert mm.cogs_rate == pytest.approx(0.45)

    def test_engine_cell_therapy_gets_yaml_cogs(self):
        engine = self._build_engine(Modality.CELL_THERAPY)
        mm = engine._resolve_market_model_with_sgna()
        assert mm.modality == "cell_therapy"
        assert mm.cogs_rate == pytest.approx(0.60)

    def test_engine_small_molecule_gets_yaml_cogs(self):
        engine = self._build_engine(Modality.SMALL_MOLECULE)
        mm = engine._resolve_market_model_with_sgna()
        assert mm.modality == "small_molecule"
        assert mm.cogs_rate == pytest.approx(0.12)

    def test_engine_explicit_cogs_not_overridden(self):
        """When caller sets cogs_rate explicitly, engine must not overwrite it."""
        engine = self._build_engine(Modality.BIOLOGIC, cogs_rate=0.05)
        mm = engine._resolve_market_model_with_sgna()
        assert mm.cogs_rate == pytest.approx(0.05)

    def test_engine_explicit_cogs_wins_over_gene_therapy(self):
        engine = self._build_engine(Modality.GENE_THERAPY, cogs_rate=0.10)
        mm = engine._resolve_market_model_with_sgna()
        assert mm.cogs_rate == pytest.approx(0.10)

    def test_market_model_modality_already_set_not_overridden(self):
        """If market_model.modality is set (e.g., from YAML), engine must not overwrite it."""
        asset = _asset(modality=Modality.BIOLOGIC)
        trials = _trials()
        # Market model says small_molecule explicitly; asset says biologic
        mm = MarketModel(
            asset_id="test-asset",
            therapeutic_area="oncology",
            total_addressable_market_millions=1000.0,
            peak_penetration=0.05,
            patent_life_years=10,
            modality="small_molecule",
        )
        program = DrugAssetProgram.build(asset=asset, trials=trials, market_model=mm, load_loe=False)
        company = Company(id="co", name="TestCo", cash_millions=100.0, shares_outstanding_millions=50.0)
        engine = ValuationEngine.from_program(program, company)
        mm_resolved = engine._resolve_market_model_with_sgna()
        # modality field set on market model wins — engine sees non-None modality
        assert mm_resolved.modality == "small_molecule"
        assert mm_resolved.cogs_rate == pytest.approx(0.12)

    def test_engine_adc_modality(self):
        asset = _asset(modality=Modality.ADC)
        trials = _trials()
        mm = MarketModel(
            asset_id="test-asset",
            therapeutic_area="oncology",
            total_addressable_market_millions=1000.0,
            peak_penetration=0.05,
            patent_life_years=10,
        )
        program = DrugAssetProgram.build(asset=asset, trials=trials, market_model=mm, load_loe=False)
        company = Company(id="co", name="TestCo", cash_millions=100.0, shares_outstanding_millions=50.0)
        engine = ValuationEngine.from_program(program, company)
        mm_resolved = engine._resolve_market_model_with_sgna()
        assert mm_resolved.cogs_rate == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# Rule 5: Backward compatibility — existing configs unchanged
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Configs that don't set modality keep existing default (0.18)."""

    def test_no_modality_no_change(self):
        mm = _simple_market()
        assert mm.cogs_rate == pytest.approx(0.18)

    def test_model_copy_without_modality_unchanged(self):
        mm = _simple_market()
        mm2 = mm.model_copy(update={"peak_penetration": 0.10})
        assert mm2.cogs_rate == pytest.approx(0.18)

    def test_explicit_cogs_in_old_config_unchanged(self):
        """Old configs with explicit cogs_rate continue to work."""
        mm = _simple_market(cogs_rate=0.25)
        assert mm.cogs_rate == pytest.approx(0.25)

    def test_yaml_example_config_relay(self):
        """Sanity check: relay YAML-derived market model with no modality stays at 0.22."""
        # relay_rly2608.yaml sets cogs_rate: 0.22 explicitly → must be preserved
        mm = MarketModel(
            asset_id="rly-2608",
            therapeutic_area="oncology",
            total_addressable_market_millions=2000.0,
            peak_penetration=0.08,
            patent_life_years=11,
            cogs_rate=0.22,
        )
        assert mm.cogs_rate == pytest.approx(0.22)

    def test_gross_profit_uses_resolved_cogs(self):
        """Gross profit calculation uses the resolved cogs_rate, not just the field default."""
        mm = _simple_market(modality="cell_therapy")
        assert mm.cogs_rate == pytest.approx(0.60)
        gp = mm.gross_profit_in_year(5)
        rev = mm.revenue_in_year(5)
        assert gp == pytest.approx(rev * (1.0 - 0.60))
