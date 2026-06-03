"""
Tests for Sprint B2: LaunchArchetype presets for UptakeCurve.

Coverage areas
--------------
1. ArchetypeSpec completeness — all 6 archetypes present and fields valid
2. UptakeCurve.from_archetype() — each archetype produces the right shape
3. slow_s_curve vs s_curve — year-1 suppression invariant
4. bolus curve mechanics — Year 1 at peak, Year 2+ at ongoing fraction
5. MarketModel.launch_archetype field — builds uptake curve automatically
6. Override precedence — explicit years_to_peak / use_s_curve / adoption_curve_mode
   beats archetype defaults
7. Backward compatibility — existing models without launch_archetype are unaffected
8. No shape warning when archetype is set
9. __init__ export
"""
from __future__ import annotations

import math
import warnings

import pytest

from bve.models.launch_archetype import (
    ARCHETYPE_SPECS,
    ArchetypeSpec,
    LaunchArchetype,
)
from bve.models.market_model import MarketModel, UptakeCurve


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tam_market(
    archetype: LaunchArchetype | None = None,
    peak_pen: float = 0.20,
    years_to_peak: int | None = None,
    patent_life: int = 12,
    adoption_curve_mode: str = "auto",
    use_s_curve: bool = False,
    **extra,
) -> MarketModel:
    """Build a minimal TAM-based MarketModel, optionally with an archetype."""
    kwargs: dict = dict(
        asset_id="test",
        total_addressable_market_millions=1_000.0,
        peak_penetration=peak_pen,
        patent_life_years=patent_life,
    )
    if archetype is not None:
        kwargs["launch_archetype"] = archetype
    if years_to_peak is not None:
        kwargs["years_to_peak"] = years_to_peak
    if adoption_curve_mode != "auto":
        kwargs["adoption_curve_mode"] = adoption_curve_mode
    if use_s_curve:
        kwargs["use_s_curve"] = True
    kwargs.update(extra)
    return MarketModel(**kwargs)


# ---------------------------------------------------------------------------
# 1. ArchetypeSpec completeness
# ---------------------------------------------------------------------------

class TestArchetypeSpecs:
    def test_all_six_archetypes_present(self):
        assert set(ARCHETYPE_SPECS.keys()) == set(LaunchArchetype)

    def test_rapid_orphan_spec(self):
        spec = ARCHETYPE_SPECS[LaunchArchetype.RAPID_ORPHAN]
        assert spec.years_to_peak == 2
        assert spec.shape == "s_curve"

    def test_oncology_specialist_spec(self):
        spec = ARCHETYPE_SPECS[LaunchArchetype.ONCOLOGY_SPECIALIST]
        assert spec.years_to_peak == 4
        assert spec.shape == "s_curve"

    def test_primary_care_slow_spec(self):
        spec = ARCHETYPE_SPECS[LaunchArchetype.PRIMARY_CARE_SLOW]
        assert spec.years_to_peak == 7
        assert spec.shape == "linear"

    def test_competitive_late_spec(self):
        spec = ARCHETYPE_SPECS[LaunchArchetype.COMPETITIVE_LATE]
        assert spec.years_to_peak == 5
        assert spec.shape == "slow_s_curve"

    def test_step_edit_restricted_spec(self):
        spec = ARCHETYPE_SPECS[LaunchArchetype.STEP_EDIT_RESTRICTED]
        assert spec.years_to_peak == 4
        assert spec.shape == "slow_s_curve"

    def test_gene_therapy_bolus_spec(self):
        spec = ARCHETYPE_SPECS[LaunchArchetype.GENE_THERAPY_BOLUS]
        assert spec.years_to_peak == 1
        assert spec.shape == "bolus"
        assert spec.bolus_ongoing_fraction == pytest.approx(0.08)

    def test_all_specs_have_descriptions(self):
        for a, spec in ARCHETYPE_SPECS.items():
            assert len(spec.description) > 10, f"{a} missing description"
            assert len(spec.when_to_use) > 10, f"{a} missing when_to_use"

    def test_archetype_spec_is_frozen(self):
        spec = ARCHETYPE_SPECS[LaunchArchetype.RAPID_ORPHAN]
        with pytest.raises((AttributeError, TypeError)):
            spec.years_to_peak = 99  # type: ignore[misc]

    def test_archetype_enum_string_values(self):
        assert LaunchArchetype.RAPID_ORPHAN == "rapid_orphan"
        assert LaunchArchetype.GENE_THERAPY_BOLUS == "gene_therapy_bolus"


# ---------------------------------------------------------------------------
# 2. UptakeCurve.from_archetype() — shape per archetype
# ---------------------------------------------------------------------------

class TestFromArchetype:
    PEAK = 0.25
    LIFE = 12

    def _curve(self, arch: LaunchArchetype, **kw) -> UptakeCurve:
        return UptakeCurve.from_archetype(arch, self.PEAK, self.LIFE, **kw)

    def test_rapid_orphan_returns_uptake_curve(self):
        c = self._curve(LaunchArchetype.RAPID_ORPHAN)
        assert isinstance(c, UptakeCurve)
        assert len(c.penetrations) == self.LIFE

    def test_rapid_orphan_peak_at_year2(self):
        c = self._curve(LaunchArchetype.RAPID_ORPHAN)
        assert c.penetrations[-1] == pytest.approx(self.PEAK)

    def test_oncology_specialist_length(self):
        c = self._curve(LaunchArchetype.ONCOLOGY_SPECIALIST)
        assert len(c.penetrations) == self.LIFE

    def test_primary_care_slow_is_linear(self):
        c_arch = self._curve(LaunchArchetype.PRIMARY_CARE_SLOW)
        c_linear = UptakeCurve.linear_ramp(7, self.PEAK, self.LIFE)
        assert c_arch.penetrations == pytest.approx(c_linear.penetrations, rel=1e-6)

    def test_gene_therapy_bolus_year1_is_peak(self):
        c = self._curve(LaunchArchetype.GENE_THERAPY_BOLUS)
        assert c.penetrations[0] == pytest.approx(self.PEAK)

    def test_gene_therapy_bolus_year2_is_ongoing(self):
        c = self._curve(LaunchArchetype.GENE_THERAPY_BOLUS)
        expected = self.PEAK * 0.08
        for p in c.penetrations[1:]:
            assert p == pytest.approx(expected)

    def test_gene_therapy_bolus_custom_ongoing_fraction(self):
        c = UptakeCurve.from_archetype(
            LaunchArchetype.GENE_THERAPY_BOLUS,
            self.PEAK, self.LIFE,
            optional_overrides={"bolus_ongoing_fraction": 0.04},
        )
        assert c.penetrations[1] == pytest.approx(self.PEAK * 0.04)

    def test_competitive_late_length(self):
        c = self._curve(LaunchArchetype.COMPETITIVE_LATE)
        assert len(c.penetrations) == self.LIFE

    def test_step_edit_restricted_length(self):
        c = self._curve(LaunchArchetype.STEP_EDIT_RESTRICTED)
        assert len(c.penetrations) == self.LIFE

    def test_all_penetrations_bounded(self):
        for arch in LaunchArchetype:
            c = self._curve(arch)
            for p in c.penetrations:
                assert 0.0 <= p <= self.PEAK + 1e-9, f"{arch}: penetration {p} out of range"

    def test_peak_reached_by_end_of_patent_life(self):
        # Non-bolus archetypes should reach (or be near) peak by year patent_life
        for arch in LaunchArchetype:
            if arch == LaunchArchetype.GENE_THERAPY_BOLUS:
                continue
            c = self._curve(arch)
            assert c.penetrations[-1] == pytest.approx(self.PEAK, rel=1e-2)


# ---------------------------------------------------------------------------
# 3. slow_s_curve vs s_curve — Year 1 suppression
# ---------------------------------------------------------------------------

class TestSlowSCurveVsStandard:
    PEAK = 0.30
    LIFE = 12

    def test_slow_s_year1_lower_than_standard(self):
        slow = UptakeCurve.from_archetype(
            LaunchArchetype.COMPETITIVE_LATE, self.PEAK, self.LIFE
        )
        std = UptakeCurve.from_archetype(
            LaunchArchetype.ONCOLOGY_SPECIALIST, self.PEAK, self.LIFE
        )
        # slow_s (ytp=5, midpoint=3.25) should have less Year-1 penetration
        # than s_curve (ytp=4, midpoint=2), but comparing by shape not ytp
        # Use same ytp for direct comparison
        slow_ytp5 = UptakeCurve._slow_s_curve(5, self.PEAK, self.LIFE)
        std_ytp5 = UptakeCurve.s_curve(5, self.PEAK, self.LIFE)
        assert slow_ytp5.penetrations[0] < std_ytp5.penetrations[0]

    def test_slow_s_year1_substantially_suppressed(self):
        """slow_s Year-1 should be materially lower than standard S at same ytp."""
        ytp = 5
        slow = UptakeCurve._slow_s_curve(ytp, self.PEAK, self.LIFE)
        std = UptakeCurve.s_curve(ytp, self.PEAK, self.LIFE)
        # At ytp=5, slow_s midpoint is 3.25 vs 2.5 — expect ~30–50% suppression in Y1
        ratio = slow.penetrations[0] / std.penetrations[0]
        assert ratio < 0.85, f"slow_s Year-1 not suppressed enough: ratio={ratio:.3f}"

    def test_slow_s_k_parameter(self):
        """Verify slow_s_curve uses k=6/ytp (flatter than k=8/ytp for standard)."""
        ytp = 4
        peak = 0.20
        life = 10
        k_slow = 6.0 / ytp
        midpoint_slow = ytp * 0.65
        expected_y1 = peak / (1.0 + math.exp(-k_slow * (1 - midpoint_slow)))
        c = UptakeCurve._slow_s_curve(ytp, peak, life)
        assert c.penetrations[0] == pytest.approx(min(expected_y1, peak), rel=1e-6)


# ---------------------------------------------------------------------------
# 4. Bolus curve mechanics
# ---------------------------------------------------------------------------

class TestBolusCurve:
    def test_bolus_year1_equals_peak(self):
        c = UptakeCurve._bolus_curve(0.50, 12)
        assert c.penetrations[0] == pytest.approx(0.50)

    def test_bolus_year2_plus_at_ongoing_fraction(self):
        c = UptakeCurve._bolus_curve(0.50, 12, ongoing_fraction=0.06)
        for p in c.penetrations[1:]:
            assert p == pytest.approx(0.50 * 0.06)

    def test_bolus_default_fraction_is_0_08(self):
        c = UptakeCurve._bolus_curve(0.40, 10)
        assert c.penetrations[1] == pytest.approx(0.40 * 0.08)

    def test_bolus_length_matches_patent_life(self):
        c = UptakeCurve._bolus_curve(0.30, 15)
        assert len(c.penetrations) == 15


# ---------------------------------------------------------------------------
# 5. MarketModel.launch_archetype field
# ---------------------------------------------------------------------------

class TestMarketModelArchetype:
    def test_no_archetype_still_works(self):
        m = _tam_market()
        assert m.uptake_curve is not None
        assert len(m.uptake_curve.penetrations) == 12

    def test_rapid_orphan_builds_curve(self):
        m = _tam_market(LaunchArchetype.RAPID_ORPHAN)
        assert m.uptake_curve is not None
        assert len(m.uptake_curve.penetrations) == 12

    def test_rapid_orphan_peak_penetration_respected(self):
        m = _tam_market(LaunchArchetype.RAPID_ORPHAN, peak_pen=0.40)
        assert m.uptake_curve.penetrations[-1] == pytest.approx(0.40)

    def test_gene_therapy_bolus_builds_bolus_curve(self):
        m = _tam_market(LaunchArchetype.GENE_THERAPY_BOLUS, peak_pen=0.60)
        assert m.uptake_curve.penetrations[0] == pytest.approx(0.60)
        assert m.uptake_curve.penetrations[1] == pytest.approx(0.60 * 0.08)

    def test_primary_care_slow_builds_linear_curve(self):
        m = _tam_market(LaunchArchetype.PRIMARY_CARE_SLOW, peak_pen=0.15)
        expected = UptakeCurve.linear_ramp(7, 0.15, 12)
        assert m.uptake_curve.penetrations == pytest.approx(expected.penetrations)

    def test_competitive_late_curve_is_slow_s(self):
        m = _tam_market(LaunchArchetype.COMPETITIVE_LATE, peak_pen=0.20)
        expected = UptakeCurve._slow_s_curve(5, 0.20, 12)
        assert m.uptake_curve.penetrations == pytest.approx(expected.penetrations)

    def test_oncology_specialist_curve_is_s_curve(self):
        m = _tam_market(LaunchArchetype.ONCOLOGY_SPECIALIST, peak_pen=0.25)
        expected = UptakeCurve.s_curve(4, 0.25, 12)
        assert m.uptake_curve.penetrations == pytest.approx(expected.penetrations)

    def test_archetype_stored_on_model(self):
        m = _tam_market(LaunchArchetype.RAPID_ORPHAN)
        assert m.launch_archetype == LaunchArchetype.RAPID_ORPHAN

    def test_no_archetype_none_by_default(self):
        m = _tam_market()
        assert m.launch_archetype is None


# ---------------------------------------------------------------------------
# 6. Override precedence
# ---------------------------------------------------------------------------

class TestOverridePrecedence:
    def test_explicit_years_to_peak_overrides_archetype(self):
        # RAPID_ORPHAN default is 2 ytp; override to 4
        m_arch = _tam_market(LaunchArchetype.RAPID_ORPHAN, peak_pen=0.25, years_to_peak=4)
        m_manual = MarketModel(
            asset_id="test",
            total_addressable_market_millions=1_000.0,
            peak_penetration=0.25,
            patent_life_years=12,
            launch_archetype=LaunchArchetype.RAPID_ORPHAN,
            years_to_peak=4,
        )
        # Should use s_curve with ytp=4, not ytp=2
        expected = UptakeCurve.s_curve(4, 0.25, 12)
        assert m_manual.uptake_curve.penetrations == pytest.approx(expected.penetrations)

    def test_explicit_uptake_curve_bypasses_archetype(self):
        manual_curve = UptakeCurve.linear_ramp(6, 0.20, 12)
        m = MarketModel(
            asset_id="test",
            total_addressable_market_millions=1_000.0,
            peak_penetration=0.20,
            patent_life_years=12,
            launch_archetype=LaunchArchetype.ONCOLOGY_SPECIALIST,
            uptake_curve=manual_curve,
        )
        # Explicit curve wins; archetype curve not applied
        assert m.uptake_curve.penetrations == pytest.approx(manual_curve.penetrations)

    def test_adoption_curve_mode_s_curve_overrides_linear_archetype(self):
        # PRIMARY_CARE_SLOW defaults to linear; override to s_curve
        m = MarketModel(
            asset_id="test",
            total_addressable_market_millions=1_000.0,
            peak_penetration=0.15,
            patent_life_years=12,
            launch_archetype=LaunchArchetype.PRIMARY_CARE_SLOW,
            adoption_curve_mode="s_curve",
        )
        expected = UptakeCurve.s_curve(7, 0.15, 12)
        assert m.uptake_curve.penetrations == pytest.approx(expected.penetrations)

    def test_use_s_curve_true_overrides_linear_archetype(self):
        m = MarketModel(
            asset_id="test",
            total_addressable_market_millions=1_000.0,
            peak_penetration=0.15,
            patent_life_years=12,
            launch_archetype=LaunchArchetype.PRIMARY_CARE_SLOW,
            use_s_curve=True,
        )
        # use_s_curve=True should produce s_curve with archetype's ytp=7
        expected = UptakeCurve.s_curve(7, 0.15, 12)
        assert m.uptake_curve.penetrations == pytest.approx(expected.penetrations)


# ---------------------------------------------------------------------------
# 7. Backward compatibility — no archetype set
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_no_archetype_linear_ramp_unaffected(self):
        m = MarketModel(
            asset_id="test",
            total_addressable_market_millions=500.0,
            peak_penetration=0.10,
            years_to_peak=5,
            patent_life_years=10,
        )
        expected = UptakeCurve.linear_ramp(5, 0.10, 10)
        assert m.uptake_curve.penetrations == pytest.approx(expected.penetrations)

    def test_no_archetype_s_curve_unaffected(self):
        m = MarketModel(
            asset_id="test",
            total_addressable_market_millions=500.0,
            peak_penetration=0.10,
            years_to_peak=5,
            patent_life_years=10,
            adoption_curve_mode="s_curve",
        )
        expected = UptakeCurve.s_curve(5, 0.10, 10)
        assert m.uptake_curve.penetrations == pytest.approx(expected.penetrations)

    def test_no_archetype_with_explicit_uptake_curve_unaffected(self):
        manual = UptakeCurve.linear_ramp(3, 0.20, 8)
        m = MarketModel(
            asset_id="test",
            total_addressable_market_millions=500.0,
            peak_penetration=0.20,
            patent_life_years=8,
            uptake_curve=manual,
        )
        assert m.uptake_curve.penetrations == pytest.approx(manual.penetrations)

    def test_archetype_does_not_affect_revenue_calculation(self):
        """Revenue in year 1 is the same whether derived from archetype or direct curve."""
        m_arch = _tam_market(LaunchArchetype.ONCOLOGY_SPECIALIST, peak_pen=0.25, patent_life=12)
        m_manual = MarketModel(
            asset_id="test",
            total_addressable_market_millions=1_000.0,
            peak_penetration=0.25,
            patent_life_years=12,
            adoption_curve_mode="s_curve",
            years_to_peak=4,
        )
        # Both should use s_curve ytp=4 → same penetration curves → same revenue
        assert m_arch.revenue_in_year(1) == pytest.approx(m_manual.revenue_in_year(1), rel=1e-4)
        assert m_arch.revenue_in_year(6) == pytest.approx(m_manual.revenue_in_year(6), rel=1e-4)


# ---------------------------------------------------------------------------
# 8. No shape warning when archetype is set
# ---------------------------------------------------------------------------

class TestNoWarningWithArchetype:
    def test_no_linear_warning_for_primary_care_slow(self):
        """primary_care_slow uses linear shape; should NOT trigger the specialty-pharma warning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _tam_market(LaunchArchetype.PRIMARY_CARE_SLOW)
        linear_warnings = [
            w for w in caught if "linear uptake" in str(w.message)
        ]
        assert len(linear_warnings) == 0

    def test_no_warning_for_competitive_late(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _tam_market(LaunchArchetype.COMPETITIVE_LATE)
        linear_warnings = [w for w in caught if "linear uptake" in str(w.message)]
        assert len(linear_warnings) == 0


# ---------------------------------------------------------------------------
# 9. __init__ export
# ---------------------------------------------------------------------------

class TestInitExport:
    def test_launch_archetype_exported(self):
        from bve.models import LaunchArchetype as LA  # noqa: F401
        assert LA.RAPID_ORPHAN is not None

    def test_all_archetypes_accessible_via_init(self):
        from bve.models import LaunchArchetype as LA
        assert len(list(LA)) == 6
