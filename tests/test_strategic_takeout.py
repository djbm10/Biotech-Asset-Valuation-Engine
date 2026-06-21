"""Tests for the strategic takeout value (control-premium-over-rNPV layer, v1).

Covers the pure model (compute_strategic_takeout) and the ValuationOutput
computed field. The layer is purely additive over rNPV — these tests assert it
never alters rNPV and is suppressed for non-positive rNPV.
"""
from __future__ import annotations

import pytest

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import MonteCarloParams
from bve.models.strategic_takeout import (
    DEFAULT_STRATEGIC_TAKEOUT_PREMIUM,
    NON_POSITIVE_RNPV_NOTE,
    StrategicTakeoutPremium,
    StrategicTakeoutValue,
    compute_strategic_takeout,
)
from bve.valuation.valuation_engine import ValuationEngine


# ── Pure model ────────────────────────────────────────────────────────────────────

class TestComputeStrategicTakeout:
    def test_default_band_30_50_80(self):
        out = compute_strategic_takeout(100.0)
        assert isinstance(out, StrategicTakeoutValue)
        assert out.floor_millions == 100.0
        assert out.low_millions == 130.0
        assert out.base_millions == 150.0
        assert out.high_millions == 180.0
        assert out.low_premium_pct == 0.30
        assert out.base_premium_pct == 0.50
        assert out.high_premium_pct == 0.80

    def test_custom_premium_band(self):
        prem = StrategicTakeoutPremium(
            low_premium_pct=0.20, base_premium_pct=0.40, high_premium_pct=0.60
        )
        out = compute_strategic_takeout(200.0, prem)
        assert out.low_millions == 240.0
        assert out.base_millions == 280.0
        assert out.high_millions == 320.0

    def test_floor_equals_rnpv_band_is_monotonic(self):
        out = compute_strategic_takeout(57.5)
        assert out.floor_millions == 57.5
        assert out.floor_millions < out.low_millions < out.base_millions < out.high_millions

    def test_rationale_named_not_quantified(self):
        out = compute_strategic_takeout(100.0)
        # Drivers are named qualitatively; none carry a separate dollar figure.
        assert len(out.rationale) >= 1
        assert any("control premium" in r.lower() for r in out.rationale)

    @pytest.mark.parametrize("rnpv", [0.0, -0.01, -317.69])
    def test_suppressed_when_rnpv_non_positive(self, rnpv):
        assert compute_strategic_takeout(rnpv) is None

    def test_premium_ordering_enforced(self):
        with pytest.raises(ValueError):
            StrategicTakeoutPremium(
                low_premium_pct=0.60, base_premium_pct=0.40, high_premium_pct=0.80
            )

    def test_default_premium_is_30_50_80(self):
        p = DEFAULT_STRATEGIC_TAKEOUT_PREMIUM
        assert (p.low_premium_pct, p.base_premium_pct, p.high_premium_pct) == (0.30, 0.50, 0.80)


# ── ValuationOutput computed field ─────────────────────────────────────────────────

_MC_FAST = MonteCarloParams(n_simulations=200, random_seed=42)


def _run_engine() -> "object":
    """Run a small positive-rNPV asset through the engine and return ValuationOutput."""
    asset = Asset(
        id="a-test", name="TEST-101", indication="ulcerative colitis",
        therapeutic_area=TherapeuticArea.IMMUNOLOGY, stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE, discount_rate=0.12,
    )
    company = Company(
        id="co-test", name="Test Therapeutics", ticker="TEST", cash_millions=200.0,
        shares_outstanding_millions=80.0, burn_rate_millions_per_quarter=20.0,
        current_price=15.00,
    )
    trials = [
        ClinicalTrial(asset_id=asset.id, phase=TrialPhase.PHASE_2,
                      success_probability=0.40, duration_years=2.5, cost_millions=60.0),
        ClinicalTrial(asset_id=asset.id, phase=TrialPhase.PHASE_3,
                      success_probability=0.60, duration_years=3.0, cost_millions=180.0),
        ClinicalTrial(asset_id=asset.id, phase=TrialPhase.NDA_BLA,
                      success_probability=0.90, duration_years=1.0, cost_millions=20.0),
    ]
    market = MarketModel(
        asset_id=asset.id, total_addressable_market_millions=5_000.0, peak_penetration=0.10,
        years_to_peak=5, patent_life_years=10, cogs_rate=0.20,
        sgna_rate_launch=0.40, sgna_rate_mature=0.20,
    )
    return ValuationEngine(asset, company, trials, market, mc_params=_MC_FAST).run()


class TestValuationOutputIntegration:
    def test_field_present_and_matches_rnpv(self):
        out = _run_engine()
        st = out.strategic_takeout
        assert st is not None
        # Floor is exactly the intrinsic rNPV — the layer never moves rNPV.
        assert st.floor_millions == round(out.rnpv.rnpv_millions, 2)
        assert st.base_millions == round(out.rnpv.rnpv_millions * 1.5, 2)
        assert out.strategic_takeout_note is None

    def test_does_not_mutate_rnpv(self):
        out = _run_engine()
        rnpv_before = out.rnpv.rnpv_millions
        _ = out.strategic_takeout  # accessing the computed field must not mutate rNPV
        assert out.rnpv.rnpv_millions == rnpv_before

    def test_serialized_in_model_dump(self):
        out = _run_engine()
        dumped = out.model_dump()
        assert "strategic_takeout" in dumped
        assert dumped["strategic_takeout"]["floor_millions"] == round(out.rnpv.rnpv_millions, 2)

    def test_note_present_when_suppressed(self):
        out = _run_engine()
        neg_rnpv = out.rnpv.model_copy(update={"rnpv_millions": -50.0})
        neg = out.model_copy(update={"rnpv": neg_rnpv})
        assert neg.strategic_takeout is None
        assert neg.strategic_takeout_note == NON_POSITIVE_RNPV_NOTE
