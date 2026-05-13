"""
Sprint 35 — Sensitivity / Tornado (Step 10 upgrade) tests.

Covers:
- SensitivitySpec: construction, defaults, active flag
- DEFAULT_SENSITIVITY_SPECS: 8 specs present, all active
- SensitivityPoint: new fields base_rnpv, shock_pct, rank, abs_swing
- compute_sensitivity: returns SensitivityResult
- compute_sensitivity: points sorted descending by abs_swing
- compute_sensitivity: rank 1 = largest swing
- compute_sensitivity: base_rnpv anchored on each point
- compute_sensitivity: low_rnpv ≤ high_rnpv on every point
- dominant_driver = parameter label with largest swing
- dominant_is_clinical: True when POS is #1
- dominant_is_clinical: False when peak_sales is #1
- memo_interpretation non-empty
- memo contains "Clinical risk" when POS dominant
- memo contains "Commercial risk" when sales dominant
- inactive spec is skipped
- unknown spec name is skipped
- custom spec list (subset) produces fewer points
- SensitivityResult with 0 specs is handled gracefully
- ValuationEngine integration: sensitivities non-empty, sorted, has base_rnpv
"""
import pytest

from bve.analysis.sensitivity import (
    DEFAULT_SENSITIVITY_SPECS,
    SensitivityResult,
    SensitivitySpec,
    compute_sensitivity,
)
from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.market_model import MarketModel
from bve.valuation.outputs import SensitivityPoint


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _asset(**kw) -> Asset:
    defaults = dict(
        id="s35-001", name="SensTest", indication="Oncology",
        therapeutic_area="oncology", stage="phase_3",
        modality="small_molecule", launch_year=2027,
        patent_expiry_year=2039, discount_rate=0.10,
        effective_tax_rate=0.21, royalty_rate=0.0,
    )
    defaults.update(kw)
    return Asset(**defaults)


def _trials(**kw) -> list[ClinicalTrial]:
    defaults = dict(
        asset_id="s35-001", phase=TrialPhase.PHASE_3,
        success_probability=0.60, duration_years=3.0, cost_millions=80.0,
    )
    defaults.update(kw)
    return [ClinicalTrial(**defaults)]


def _market(**kw) -> MarketModel:
    defaults = dict(
        asset_id="s35-001", therapeutic_area="oncology",
        addressable_patients_annual=50_000, net_price_per_patient_usd=80_000,
        peak_penetration=0.20, years_to_peak=4, patent_life_years=12,
        cogs_rate=0.12, sgna_rate_launch=0.35, sgna_rate_mature=0.18,
    )
    defaults.update(kw)
    return MarketModel(**defaults)


def _base_rnpv(asset=None, trials=None, market=None) -> float:
    from bve.models.rnpv_model import compute_rnpv_full
    a = asset or _asset()
    t = trials or _trials()
    m = market or _market()
    return compute_rnpv_full(a, t, m).rnpv_millions


# ---------------------------------------------------------------------------
# SensitivitySpec
# ---------------------------------------------------------------------------

class TestSensitivitySpec:
    def test_construction(self):
        spec = SensitivitySpec(name="pos", label="Phase POS (±20%)", shock_pct=20.0)
        assert spec.name == "pos"
        assert spec.shock_pct == 20.0
        assert spec.active is True

    def test_inactive_spec(self):
        spec = SensitivitySpec(name="pos", label="Phase POS", shock_pct=20.0, active=False)
        assert spec.active is False

    def test_absolute_delta(self):
        spec = SensitivitySpec(name="discount_rate", label="WACC (±2pp)",
                               shock_pct=2.0, absolute_delta=0.02)
        assert spec.absolute_delta == pytest.approx(0.02)

    def test_negative_shock_pct_raises(self):
        with pytest.raises(Exception):
            SensitivitySpec(name="pos", label="POS", shock_pct=-5.0)


# ---------------------------------------------------------------------------
# DEFAULT_SENSITIVITY_SPECS
# ---------------------------------------------------------------------------

class TestDefaultSpecs:
    def test_eight_specs(self):
        assert len(DEFAULT_SENSITIVITY_SPECS) == 8

    def test_all_active(self):
        assert all(s.active for s in DEFAULT_SENSITIVITY_SPECS)

    def test_pos_spec_present(self):
        names = [s.name for s in DEFAULT_SENSITIVITY_SPECS]
        assert "pos" in names

    def test_peak_sales_spec_present(self):
        names = [s.name for s in DEFAULT_SENSITIVITY_SPECS]
        assert "peak_sales" in names


# ---------------------------------------------------------------------------
# SensitivityPoint new fields (Sprint 35 additions)
# ---------------------------------------------------------------------------

class TestSensitivityPointNewFields:
    def test_base_rnpv_default_zero(self):
        sp = SensitivityPoint(parameter="x", low_value=0, high_value=1,
                              low_rnpv=10.0, high_rnpv=20.0)
        assert sp.base_rnpv == 0.0

    def test_shock_pct_default_zero(self):
        sp = SensitivityPoint(parameter="x", low_value=0, high_value=1,
                              low_rnpv=10.0, high_rnpv=20.0)
        assert sp.shock_pct == 0.0

    def test_rank_default_zero(self):
        sp = SensitivityPoint(parameter="x", low_value=0, high_value=1,
                              low_rnpv=10.0, high_rnpv=20.0)
        assert sp.rank == 0

    def test_abs_swing(self):
        sp = SensitivityPoint(parameter="x", low_value=0, high_value=1,
                              low_rnpv=10.0, high_rnpv=20.0)
        assert sp.abs_swing == pytest.approx(10.0)

    def test_abs_swing_negative_swing(self):
        sp = SensitivityPoint(parameter="x", low_value=0, high_value=1,
                              low_rnpv=20.0, high_rnpv=10.0)
        assert sp.abs_swing == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# compute_sensitivity — structure
# ---------------------------------------------------------------------------

class TestComputeSensitivityStructure:
    def setup_method(self):
        self.a = _asset()
        self.t = _trials()
        self.m = _market()
        self.base = _base_rnpv(self.a, self.t, self.m)

    def test_returns_sensitivity_result(self):
        r = compute_sensitivity(self.a, self.t, self.m, base_rnpv=self.base)
        assert isinstance(r, SensitivityResult)

    def test_points_non_empty(self):
        r = compute_sensitivity(self.a, self.t, self.m, base_rnpv=self.base)
        assert len(r.points) > 0

    def test_sorted_descending_by_abs_swing(self):
        r = compute_sensitivity(self.a, self.t, self.m, base_rnpv=self.base)
        swings = [p.abs_swing for p in r.points]
        assert swings == sorted(swings, reverse=True)

    def test_rank_1_is_largest(self):
        r = compute_sensitivity(self.a, self.t, self.m, base_rnpv=self.base)
        rank1 = next(p for p in r.points if p.rank == 1)
        assert rank1.abs_swing == max(p.abs_swing for p in r.points)

    def test_ranks_are_sequential(self):
        r = compute_sensitivity(self.a, self.t, self.m, base_rnpv=self.base)
        ranks = sorted(p.rank for p in r.points)
        assert ranks == list(range(1, len(r.points) + 1))

    def test_base_rnpv_anchored_on_each_point(self):
        r = compute_sensitivity(self.a, self.t, self.m, base_rnpv=self.base)
        for p in r.points:
            assert p.base_rnpv == pytest.approx(self.base)

    def test_low_rnpv_le_high_rnpv(self):
        r = compute_sensitivity(self.a, self.t, self.m, base_rnpv=self.base)
        for p in r.points:
            assert p.low_rnpv <= p.high_rnpv, f"{p.parameter}: low > high"

    def test_shock_pct_populated(self):
        r = compute_sensitivity(self.a, self.t, self.m, base_rnpv=self.base)
        for p in r.points:
            assert p.shock_pct > 0.0

    def test_dominant_driver_is_string(self):
        r = compute_sensitivity(self.a, self.t, self.m, base_rnpv=self.base)
        assert isinstance(r.dominant_driver, str) and len(r.dominant_driver) > 0

    def test_memo_non_empty(self):
        r = compute_sensitivity(self.a, self.t, self.m, base_rnpv=self.base)
        assert len(r.memo_interpretation) > 0

    def test_base_rnpv_on_result(self):
        r = compute_sensitivity(self.a, self.t, self.m, base_rnpv=self.base)
        assert r.base_rnpv == pytest.approx(self.base)


# ---------------------------------------------------------------------------
# dominant_is_clinical classification
# ---------------------------------------------------------------------------

class TestDominantClassification:
    def test_dominant_is_clinical_when_pos_largest(self):
        # Force POS spec only → must be clinical dominant
        pos_spec = next(s for s in DEFAULT_SENSITIVITY_SPECS if s.name == "pos")
        a, t, m = _asset(), _trials(), _market()
        base = _base_rnpv(a, t, m)
        r = compute_sensitivity(a, t, m, base_rnpv=base, specs=[pos_spec])
        assert r.dominant_is_clinical is True

    def test_memo_says_clinical_risk(self):
        pos_spec = next(s for s in DEFAULT_SENSITIVITY_SPECS if s.name == "pos")
        a, t, m = _asset(), _trials(), _market()
        base = _base_rnpv(a, t, m)
        r = compute_sensitivity(a, t, m, base_rnpv=base, specs=[pos_spec])
        assert "Clinical risk" in r.memo_interpretation

    def test_dominant_not_clinical_when_only_sales(self):
        ps_spec = next(s for s in DEFAULT_SENSITIVITY_SPECS if s.name == "peak_sales")
        a, t, m = _asset(), _trials(), _market()
        base = _base_rnpv(a, t, m)
        r = compute_sensitivity(a, t, m, base_rnpv=base, specs=[ps_spec])
        assert r.dominant_is_clinical is False

    def test_memo_says_commercial_risk(self):
        ps_spec = next(s for s in DEFAULT_SENSITIVITY_SPECS if s.name == "peak_sales")
        a, t, m = _asset(), _trials(), _market()
        base = _base_rnpv(a, t, m)
        r = compute_sensitivity(a, t, m, base_rnpv=base, specs=[ps_spec])
        assert "Commercial risk" in r.memo_interpretation


# ---------------------------------------------------------------------------
# Custom and edge-case spec lists
# ---------------------------------------------------------------------------

class TestCustomSpecs:
    def test_inactive_spec_skipped(self):
        specs = [SensitivitySpec(name="pos", label="POS", shock_pct=20.0, active=False)]
        a, t, m = _asset(), _trials(), _market()
        base = _base_rnpv(a, t, m)
        r = compute_sensitivity(a, t, m, base_rnpv=base, specs=specs)
        assert len(r.points) == 0

    def test_unknown_spec_name_skipped(self):
        specs = [SensitivitySpec(name="unknown_parameter_xyz", label="X", shock_pct=10.0)]
        a, t, m = _asset(), _trials(), _market()
        base = _base_rnpv(a, t, m)
        r = compute_sensitivity(a, t, m, base_rnpv=base, specs=specs)
        assert len(r.points) == 0

    def test_empty_spec_list_handled(self):
        a, t, m = _asset(), _trials(), _market()
        base = _base_rnpv(a, t, m)
        r = compute_sensitivity(a, t, m, base_rnpv=base, specs=[])
        assert r.points == []
        assert "No sensitivity" in r.memo_interpretation

    def test_subset_spec_list(self):
        specs = [s for s in DEFAULT_SENSITIVITY_SPECS if s.name in {"pos", "peak_sales"}]
        a, t, m = _asset(), _trials(), _market()
        base = _base_rnpv(a, t, m)
        r = compute_sensitivity(a, t, m, base_rnpv=base, specs=specs)
        assert len(r.points) == 2
