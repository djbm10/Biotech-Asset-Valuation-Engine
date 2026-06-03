"""
Sprint D2 — SG&A profiles by commercial model.

Rules:
  1. Explicit SG&A fields (sgna_rate_launch, sgna_rate_mature, sgna_ramp_years) win
     unconditionally on a per-field basis.
  2. If commercial_model is set and a SG&A field is not explicit, load from YAML profile.
  3. If commercial_model is absent, preserve current behavior (no change).
  4. commercial_model suppresses ValuationEngine modality/TA auto-selection of SG&A.
"""
from __future__ import annotations

import pytest

from bve.config.assumptions_loader import AssumptionsLoader
from bve.entities.asset import Asset, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.commercial_model_profile import CommercialModelProfile
from bve.models.drug_asset_program import DrugAssetProgram
from bve.models.market_model import MarketModel
from bve.valuation.valuation_engine import ValuationEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _market(**kwargs) -> MarketModel:
    base = dict(
        asset_id="test",
        therapeutic_area="oncology",
        total_addressable_market_millions=1000.0,
        peak_penetration=0.05,
        patent_life_years=10,
    )
    base.update(kwargs)
    return MarketModel(**base)


def _asset(modality: Modality = Modality.BIOLOGIC, ta: TherapeuticArea = TherapeuticArea.ONCOLOGY) -> Asset:
    return Asset(
        id="test",
        name="TestDrug",
        indication="NSCLC",
        modality=modality,
        therapeutic_area=ta,
        stage="phase_3",
        discount_rate=0.10,
    )


def _trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(asset_id="test", phase=TrialPhase.PHASE_3,
                      success_probability=0.60, duration_years=3.0, cost_millions=200.0),
    ]


def _company() -> Company:
    return Company(id="co", name="TestCo", cash_millions=100.0, shares_outstanding_millions=50.0)


def _engine(asset: Asset, mm: MarketModel) -> ValuationEngine:
    program = DrugAssetProgram.build(asset=asset, trials=_trials(), market_model=mm, load_loe=False)
    return ValuationEngine.from_program(program, _company())


# ---------------------------------------------------------------------------
# Section 1: YAML profile values
# ---------------------------------------------------------------------------

class TestYAMLProfileValues:
    """Loader returns the correct calibrated values for each profile."""

    def _profile(self, name: str) -> dict:
        return dict(AssumptionsLoader.get().commercial_model_profile(name))

    def test_self_commercialized_specialty(self):
        p = self._profile("self_commercialized_specialty")
        assert p["sgna_rate_launch"] == pytest.approx(0.40)
        assert p["sgna_rate_mature"] == pytest.approx(0.20)
        assert p["sgna_ramp_years"] == 5

    def test_rare_disease_kol(self):
        p = self._profile("rare_disease_kol")
        assert p["sgna_rate_launch"] == pytest.approx(0.25)
        assert p["sgna_rate_mature"] == pytest.approx(0.12)
        assert p["sgna_ramp_years"] == 4

    def test_partnered(self):
        p = self._profile("partnered")
        assert p["sgna_rate_launch"] == pytest.approx(0.12)
        assert p["sgna_rate_mature"] == pytest.approx(0.08)
        assert p["sgna_ramp_years"] == 3

    def test_royalty_only(self):
        p = self._profile("royalty_only")
        assert p["sgna_rate_launch"] == pytest.approx(0.02)
        assert p["sgna_rate_mature"] == pytest.approx(0.02)
        assert p["sgna_ramp_years"] == 1

    def test_primary_care_salesforce(self):
        p = self._profile("primary_care_salesforce")
        assert p["sgna_rate_launch"] == pytest.approx(0.55)
        assert p["sgna_rate_mature"] == pytest.approx(0.30)
        assert p["sgna_ramp_years"] == 7

    def test_hospital_specialty(self):
        p = self._profile("hospital_specialty")
        assert p["sgna_rate_launch"] == pytest.approx(0.20)
        assert p["sgna_rate_mature"] == pytest.approx(0.12)
        assert p["sgna_ramp_years"] == 4

    def test_unknown_profile_falls_back_with_warning(self):
        with pytest.warns(UserWarning, match="CommercialModelProfile"):
            p = dict(AssumptionsLoader.get().commercial_model_profile("nonexistent_profile"))
        # falls back to self_commercialized_specialty
        assert p["sgna_rate_launch"] == pytest.approx(0.40)


# ---------------------------------------------------------------------------
# Section 2: CommercialModelProfile enum
# ---------------------------------------------------------------------------

class TestCommercialModelProfileEnum:
    """Enum values match YAML keys exactly."""

    def test_all_values_present(self):
        values = {p.value for p in CommercialModelProfile}
        assert "self_commercialized_specialty" in values
        assert "rare_disease_kol" in values
        assert "partnered" in values
        assert "royalty_only" in values
        assert "primary_care_salesforce" in values
        assert "hospital_specialty" in values

    def test_is_string_enum(self):
        assert CommercialModelProfile.PARTNERED == "partnered"

    def test_round_trip_from_string(self):
        assert CommercialModelProfile("royalty_only") is CommercialModelProfile.ROYALTY_ONLY


# ---------------------------------------------------------------------------
# Section 3: MarketModel — profile auto-population
# ---------------------------------------------------------------------------

class TestMarketModelProfileAutoPopulation:
    """MarketModel loads the correct SG&A from profile at construction."""

    def test_self_commercialized_specialty_populates_sgna(self):
        mm = _market(commercial_model=CommercialModelProfile.SELF_COMMERCIALIZED_SPECIALTY)
        assert mm.sgna_rate_launch == pytest.approx(0.40)
        assert mm.sgna_rate_mature == pytest.approx(0.20)
        assert mm.sgna_ramp_years == 5

    def test_rare_disease_kol_populates_sgna(self):
        mm = _market(commercial_model=CommercialModelProfile.RARE_DISEASE_KOL)
        assert mm.sgna_rate_launch == pytest.approx(0.25)
        assert mm.sgna_rate_mature == pytest.approx(0.12)
        assert mm.sgna_ramp_years == 4

    def test_partnered_populates_sgna(self):
        mm = _market(commercial_model=CommercialModelProfile.PARTNERED)
        assert mm.sgna_rate_launch == pytest.approx(0.12)
        assert mm.sgna_rate_mature == pytest.approx(0.08)
        assert mm.sgna_ramp_years == 3

    def test_royalty_only_populates_sgna(self):
        mm = _market(commercial_model=CommercialModelProfile.ROYALTY_ONLY)
        assert mm.sgna_rate_launch == pytest.approx(0.02)
        assert mm.sgna_rate_mature == pytest.approx(0.02)
        assert mm.sgna_ramp_years == 1

    def test_primary_care_salesforce_populates_sgna(self):
        mm = _market(commercial_model=CommercialModelProfile.PRIMARY_CARE_SALESFORCE)
        assert mm.sgna_rate_launch == pytest.approx(0.55)
        assert mm.sgna_rate_mature == pytest.approx(0.30)
        assert mm.sgna_ramp_years == 7

    def test_hospital_specialty_populates_sgna(self):
        mm = _market(commercial_model=CommercialModelProfile.HOSPITAL_SPECIALTY)
        assert mm.sgna_rate_launch == pytest.approx(0.20)
        assert mm.sgna_rate_mature == pytest.approx(0.12)
        assert mm.sgna_ramp_years == 4

    def test_commercial_model_stored_on_model(self):
        mm = _market(commercial_model=CommercialModelProfile.PARTNERED)
        assert mm.commercial_model is CommercialModelProfile.PARTNERED

    def test_no_commercial_model_preserves_defaults(self):
        mm = _market()
        assert mm.commercial_model is None
        assert mm.sgna_rate_launch == pytest.approx(0.40)
        assert mm.sgna_rate_mature == pytest.approx(0.20)
        assert mm.sgna_ramp_years == 5

    def test_string_value_accepted(self):
        """YAML configs pass the string value; Pydantic should coerce it."""
        mm = _market(commercial_model="partnered")
        assert mm.commercial_model is CommercialModelProfile.PARTNERED
        assert mm.sgna_rate_launch == pytest.approx(0.12)


# ---------------------------------------------------------------------------
# Section 4: Explicit SG&A fields win (per-field granularity)
# ---------------------------------------------------------------------------

class TestExplicitSGnAWins:
    """Explicit fields override profile defaults on a per-field basis."""

    def test_explicit_launch_overrides_profile(self):
        mm = _market(commercial_model=CommercialModelProfile.PARTNERED, sgna_rate_launch=0.50)
        assert mm.sgna_rate_launch == pytest.approx(0.50)  # explicit wins
        assert mm.sgna_rate_mature == pytest.approx(0.08)  # profile
        assert mm.sgna_ramp_years == 3                      # profile

    def test_explicit_mature_overrides_profile(self):
        mm = _market(commercial_model=CommercialModelProfile.ROYALTY_ONLY, sgna_rate_mature=0.15)
        assert mm.sgna_rate_launch == pytest.approx(0.02)  # profile
        assert mm.sgna_rate_mature == pytest.approx(0.15)  # explicit wins
        assert mm.sgna_ramp_years == 1                      # profile

    def test_explicit_ramp_years_overrides_profile(self):
        mm = _market(commercial_model=CommercialModelProfile.PRIMARY_CARE_SALESFORCE, sgna_ramp_years=3)
        assert mm.sgna_rate_launch == pytest.approx(0.55)  # profile
        assert mm.sgna_rate_mature == pytest.approx(0.30)  # profile
        assert mm.sgna_ramp_years == 3                      # explicit wins

    def test_all_three_explicit_ignores_profile_entirely(self):
        mm = _market(
            commercial_model=CommercialModelProfile.HOSPITAL_SPECIALTY,
            sgna_rate_launch=0.99,
            sgna_rate_mature=0.50,
            sgna_ramp_years=1,
        )
        assert mm.sgna_rate_launch == pytest.approx(0.99)
        assert mm.sgna_rate_mature == pytest.approx(0.50)
        assert mm.sgna_ramp_years == 1

    def test_zero_explicit_launch_preserved(self):
        """Zero is a valid override — should not be treated as falsy."""
        mm = _market(commercial_model=CommercialModelProfile.PRIMARY_CARE_SALESFORCE, sgna_rate_launch=0.0)
        assert mm.sgna_rate_launch == pytest.approx(0.0)
        assert mm.sgna_rate_mature == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# Section 5: Backward compatibility — no commercial_model
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Existing configs without commercial_model are completely unaffected."""

    def test_no_commercial_model_no_change(self):
        mm = _market()
        assert mm.sgna_rate_launch == pytest.approx(0.40)
        assert mm.sgna_rate_mature == pytest.approx(0.20)
        assert mm.sgna_ramp_years == 5

    def test_explicit_sgna_no_commercial_model_unchanged(self):
        mm = _market(sgna_rate_launch=0.30, sgna_rate_mature=0.15, sgna_ramp_years=4)
        assert mm.sgna_rate_launch == pytest.approx(0.30)
        assert mm.sgna_rate_mature == pytest.approx(0.15)
        assert mm.sgna_ramp_years == 4

    def test_model_copy_without_commercial_model_unchanged(self):
        mm = _market(sgna_rate_launch=0.35)
        mm2 = mm.model_copy(update={"peak_penetration": 0.10})
        assert mm2.sgna_rate_launch == pytest.approx(0.35)

    def test_ebit_uses_resolved_sgna(self):
        """EBIT calculation uses the profile-derived SG&A, not just defaults."""
        mm_royalty = _market(commercial_model=CommercialModelProfile.ROYALTY_ONLY)
        mm_pc = _market(commercial_model=CommercialModelProfile.PRIMARY_CARE_SALESFORCE)
        # royalty_only has lower SG&A → higher EBIT for same revenue year
        ebit_royalty = mm_royalty.ebit_in_year(3)
        ebit_pc = mm_pc.ebit_in_year(3)
        assert ebit_royalty > ebit_pc


# ---------------------------------------------------------------------------
# Section 6: ValuationEngine — commercial_model suppresses engine auto-selection
# ---------------------------------------------------------------------------

class TestEngineAutoSelectionSuppressed:
    """
    ValuationEngine auto-selects SG&A for gene_therapy/cell_therapy/rare_disease.
    When commercial_model is set, that auto-selection must be skipped.
    """

    def test_gene_therapy_without_commercial_model_gets_auto_sgna(self):
        asset = _asset(modality=Modality.GENE_THERAPY)
        mm = _market()
        engine = _engine(asset, mm)
        with pytest.warns(UserWarning, match="auto-selected SG&A profile"):
            mm_resolved = engine._resolve_market_model_with_sgna()
        # engine would auto-select gene_cell_therapy: launch=0.55
        assert mm_resolved.sgna_rate_launch == pytest.approx(0.55)

    def test_gene_therapy_with_commercial_model_skips_auto_sgna(self):
        asset = _asset(modality=Modality.GENE_THERAPY)
        mm = _market(commercial_model=CommercialModelProfile.PARTNERED)
        engine = _engine(asset, mm)
        # No auto-selection warning expected
        import warnings as _w
        with _w.catch_warnings():
            _w.simplefilter("error", UserWarning)
            mm_resolved = engine._resolve_market_model_with_sgna()
        assert mm_resolved.sgna_rate_launch == pytest.approx(0.12)  # partnered profile
        assert mm_resolved.commercial_model is CommercialModelProfile.PARTNERED

    def test_rare_disease_without_commercial_model_gets_auto_sgna(self):
        asset = _asset(ta=TherapeuticArea.RARE_DISEASE)
        mm = _market()
        engine = _engine(asset, mm)
        with pytest.warns(UserWarning, match="auto-selected SG&A profile"):
            mm_resolved = engine._resolve_market_model_with_sgna()
        assert mm_resolved.sgna_rate_launch == pytest.approx(0.45)

    def test_rare_disease_with_commercial_model_skips_auto_sgna(self):
        asset = _asset(ta=TherapeuticArea.RARE_DISEASE)
        mm = _market(commercial_model=CommercialModelProfile.RARE_DISEASE_KOL)
        engine = _engine(asset, mm)
        import warnings as _w
        with _w.catch_warnings():
            _w.simplefilter("error", UserWarning)
            mm_resolved = engine._resolve_market_model_with_sgna()
        assert mm_resolved.sgna_rate_launch == pytest.approx(0.25)

    def test_self_commercialized_specialty_suppresses_auto_even_with_default_values(self):
        """
        self_commercialized_specialty has the same values as the engine default.
        Setting commercial_model must still suppress auto-selection so that
        a gene_therapy asset doesn't get overridden with gene_cell_therapy profile.
        """
        asset = _asset(modality=Modality.GENE_THERAPY)
        mm = _market(commercial_model=CommercialModelProfile.SELF_COMMERCIALIZED_SPECIALTY)
        engine = _engine(asset, mm)
        import warnings as _w
        with _w.catch_warnings():
            _w.simplefilter("error", UserWarning)
            mm_resolved = engine._resolve_market_model_with_sgna()
        # Must stay at 0.40 (self_commercialized_specialty), NOT be overridden to 0.55
        assert mm_resolved.sgna_rate_launch == pytest.approx(0.40)

    def test_oncology_without_commercial_model_uses_default(self):
        """Oncology asset with no gene/rare modality — engine returns mm unchanged."""
        asset = _asset(modality=Modality.SMALL_MOLECULE)
        mm = _market()
        engine = _engine(asset, mm)
        mm_resolved = engine._resolve_market_model_with_sgna()
        assert mm_resolved.sgna_rate_launch == pytest.approx(0.40)
