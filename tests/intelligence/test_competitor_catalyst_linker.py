"""
Wave 2 — Competitor Catalyst Linker: 10 required tests.

Tests cover:
  1.  Same MoA + competitor success → market share compression only, no PoS change
  2.  Same MoA + competitor failure (efficacy) → PoS increase + market share increase
  3.  Same MoA + competitor failure (safety) → PoS decrease (class concern)
  4.  Different MoA + competitor success → market share compression only
  5.  Temporal decay: competitor reads out 2 years before us → decay applied
  6.  Temporal decay: competitor reads out after us → decay = 1.0
  7.  Temporal decay: our trial started after competitor readout → uses our_trial_start
  8.  CatalystEvent created with type=COMPETITOR_READOUT on tracked asset
  9.  No competitor programs → empty list returned
  10. Conservative defaults used when propagation priors unavailable
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional
from unittest.mock import MagicMock

import pytest

from bve.intelligence.catalyst_calendar import CatalystType
from bve.intelligence.competitor_catalyst_linker import (
    CompetitorCatalystLinker,
    _CONFIG_DEFAULTS,
    _ImpactScenarios,
    _resolve_impact,
    competitor_decay_factor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ct_record(primary_completion_date: str) -> dict:
    """Minimal CT v2 record with a primary completion date."""
    return {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT99999999", "briefTitle": "Test Trial"},
            "statusModule": {
                "primaryCompletionDateStruct": {"date": primary_completion_date}
            },
        }
    }


def _linker(cfg: Optional[dict] = None) -> CompetitorCatalystLinker:
    return CompetitorCatalystLinker(config=cfg or dict(_CONFIG_DEFAULTS))


def _today() -> date:
    return date.today()


# ---------------------------------------------------------------------------
# Test 1: Same MoA + competitor success → market share compression, no PoS
# ---------------------------------------------------------------------------

class TestMoARulesSameMoASuccess:
    def test_same_moa_success_market_share_only(self):
        scenarios = _resolve_impact(same_moa=True, failure_type="efficacy", cfg=dict(_CONFIG_DEFAULTS))
        # Success scenario: market share is compressed (< 0)
        assert scenarios.market_share_delta_on_success < 0, "Competitor success must compress market share"

    def test_same_moa_success_pos_impact_not_none(self):
        """pos_delta_on_failure applies to competitor *failure* scenario.
        The *success* scenario uses market_share_delta_on_success only.
        Verify via link_competitor_program that value_if_success < current_value."""
        linker = _linker()
        today = _today()
        ct = _make_ct_record((today + timedelta(days=90)).strftime("%Y-%m-%d"))
        event = linker.link_competitor_program(
            tracked_asset_id="asset-1",
            competitor_nct_id="NCT99999999",
            competitor_drug_name="CompDrug",
            same_moa=True,
            indication="oncology",
            failure_type="efficacy",
            competitor_ct_record=ct,
            current_value=500.0,
            our_readout_date=today + timedelta(days=730),
        )
        assert event is not None
        # success → market share compression → value_if_success < current_value
        assert event.value_if_success < event.current_value


# ---------------------------------------------------------------------------
# Test 2: Same MoA + competitor failure (efficacy) → PoS increase
# ---------------------------------------------------------------------------

class TestMoARulesSameMoAEfficacyFailure:
    def test_efficacy_failure_pos_delta_positive(self):
        scenarios = _resolve_impact(same_moa=True, failure_type="efficacy", cfg=dict(_CONFIG_DEFAULTS))
        assert scenarios.pos_delta_on_failure > 0, "Efficacy failure should increase tracked asset PoS"
        assert scenarios.pos_impact_label == "increase"

    def test_efficacy_failure_value_if_failure_above_current(self):
        linker = _linker()
        today = _today()
        ct = _make_ct_record((today + timedelta(days=90)).strftime("%Y-%m-%d"))
        event = linker.link_competitor_program(
            tracked_asset_id="asset-1",
            competitor_nct_id="NCT99999999",
            competitor_drug_name="CompDrug",
            same_moa=True,
            indication="oncology",
            failure_type="efficacy",
            competitor_ct_record=ct,
            current_value=500.0,
            our_readout_date=today + timedelta(days=730),
        )
        assert event is not None
        # failure → PoS increase → value_if_failure > current_value
        assert event.value_if_failure > event.current_value


# ---------------------------------------------------------------------------
# Test 3: Same MoA + competitor failure (safety) → PoS decrease
# ---------------------------------------------------------------------------

class TestMoARulesSameMoASafetyFailure:
    def test_safety_failure_pos_delta_negative(self):
        scenarios = _resolve_impact(same_moa=True, failure_type="safety", cfg=dict(_CONFIG_DEFAULTS))
        assert scenarios.pos_delta_on_failure < 0, "Safety failure must raise class concern (PoS decreases)"
        assert scenarios.pos_impact_label == "class_concern"

    def test_safety_failure_value_if_failure_below_current(self):
        linker = _linker()
        today = _today()
        ct = _make_ct_record((today + timedelta(days=90)).strftime("%Y-%m-%d"))
        event = linker.link_competitor_program(
            tracked_asset_id="asset-1",
            competitor_nct_id="NCT99999999",
            competitor_drug_name="CompDrug",
            same_moa=True,
            indication="oncology",
            failure_type="safety",
            competitor_ct_record=ct,
            current_value=500.0,
            our_readout_date=today + timedelta(days=730),
        )
        assert event is not None
        # failure → class concern → value_if_failure < current_value
        assert event.value_if_failure < event.current_value


# ---------------------------------------------------------------------------
# Test 4: Different MoA + competitor success → market share compression only
# ---------------------------------------------------------------------------

class TestMoARulesDifferentMoASuccess:
    def test_different_moa_pos_impact_label_none(self):
        scenarios = _resolve_impact(same_moa=False, failure_type="efficacy", cfg=dict(_CONFIG_DEFAULTS))
        assert scenarios.pos_impact_label == "none", "Different MoA: no PoS signal"

    def test_different_moa_success_compresses_share(self):
        scenarios = _resolve_impact(same_moa=False, failure_type="efficacy", cfg=dict(_CONFIG_DEFAULTS))
        assert scenarios.market_share_delta_on_success < 0

    def test_different_moa_via_linker_value_if_success_below_current(self):
        linker = _linker()
        today = _today()
        ct = _make_ct_record((today + timedelta(days=60)).strftime("%Y-%m-%d"))
        event = linker.link_competitor_program(
            tracked_asset_id="asset-2",
            competitor_nct_id="NCT11111111",
            competitor_drug_name="OtherDrug",
            same_moa=False,
            indication="immunology",
            failure_type="efficacy",
            competitor_ct_record=ct,
            current_value=300.0,
            our_readout_date=today + timedelta(days=600),
        )
        assert event is not None
        assert event.value_if_success < event.current_value


# ---------------------------------------------------------------------------
# Test 5: Temporal decay — competitor reads out 2 years before our readout
# ---------------------------------------------------------------------------

class TestTemporalDecayBeforeOurReadout:
    def test_decay_less_than_one_when_readout_precedes_ours(self):
        today = _today()
        competitor_readout = today - timedelta(days=730)  # 2 years ago
        our_start          = today - timedelta(days=900)  # started 2.5 yrs ago
        our_readout        = today + timedelta(days=90)   # 3 months from now

        decay = competitor_decay_factor(
            competitor_readout_date = competitor_readout,
            our_trial_start_date    = our_start,
            our_readout_date        = our_readout,
            indication              = "oncology",
            tau_years               = 1.2,
        )
        assert 0.0 < decay < 1.0, f"Expected decay < 1.0, got {decay}"

    def test_decay_magnitude_matches_formula(self):
        """Verify exact exponential: exp(-delta / tau)."""
        today = _today()
        competitor_readout = today - timedelta(days=365)
        our_start          = today - timedelta(days=500)
        our_readout        = today + timedelta(days=60)

        tau = 1.5
        decay = competitor_decay_factor(
            competitor_readout_date = competitor_readout,
            our_trial_start_date    = our_start,
            our_readout_date        = our_readout,
            indication              = "cardiovascular",
            tau_years               = tau,
        )
        market_awareness = max(competitor_readout, our_start)
        delta = (our_readout - market_awareness).days / 365.25
        expected = math.exp(-delta / tau)
        assert abs(decay - expected) < 1e-9


# ---------------------------------------------------------------------------
# Test 6: Temporal decay — competitor reads out after our readout → decay = 1.0
# ---------------------------------------------------------------------------

class TestTemporalDecayAfterOurReadout:
    def test_decay_is_one_when_competitor_after_our_readout(self):
        today = _today()
        our_readout        = today + timedelta(days=180)
        competitor_readout = today + timedelta(days=365)  # after our readout

        decay = competitor_decay_factor(
            competitor_readout_date = competitor_readout,
            our_trial_start_date    = today,
            our_readout_date        = our_readout,
            indication              = "oncology",
            tau_years               = 1.2,
        )
        assert decay == 1.0

    def test_decay_is_one_when_competitor_same_day_as_our_readout(self):
        today = _today()
        readout = today + timedelta(days=180)
        decay = competitor_decay_factor(
            competitor_readout_date = readout,
            our_trial_start_date    = today,
            our_readout_date        = readout,
            indication              = "oncology",
            tau_years               = 1.2,
        )
        assert decay == 1.0


# ---------------------------------------------------------------------------
# Test 7: Temporal decay — our trial started AFTER competitor readout → uses trial_start
# ---------------------------------------------------------------------------

class TestTemporalDecayUseTrialStart:
    def test_market_awareness_uses_trial_start_when_later(self):
        """
        If competitor read out before our trial started, the market has already
        priced the signal from trial_start, not from competitor readout.
        Effective delta = our_readout - our_trial_start  (shorter → less decay).
        """
        today = _today()
        competitor_readout = today - timedelta(days=900)   # long ago
        our_trial_start    = today - timedelta(days=180)   # recent start (later)
        our_readout        = today + timedelta(days=180)   # 6 months away

        tau = 1.5
        decay = competitor_decay_factor(
            competitor_readout_date = competitor_readout,
            our_trial_start_date    = our_trial_start,
            our_readout_date        = our_readout,
            indication              = "default",
            tau_years               = tau,
        )

        # market_awareness_date = max(competitor_readout, trial_start) = trial_start
        # effective_delta = (our_readout - our_trial_start).days / 365.25
        effective_delta = (our_readout - our_trial_start).days / 365.25
        expected = math.exp(-effective_delta / tau)
        assert abs(decay - expected) < 1e-9

        # Also verify it's more decayed than if we used competitor_readout directly
        decay_naive = competitor_decay_factor(
            competitor_readout_date = competitor_readout,
            our_trial_start_date    = competitor_readout - timedelta(days=1),  # never binding
            our_readout_date        = our_readout,
            indication              = "default",
            tau_years               = tau,
        )
        # decay_naive would use competitor_readout → longer delta → lower decay
        assert decay > decay_naive


# ---------------------------------------------------------------------------
# Test 8: CatalystEvent created with type=COMPETITOR_READOUT
# ---------------------------------------------------------------------------

class TestCatalystEventType:
    def test_event_type_is_competitor_readout(self):
        linker = _linker()
        today = _today()
        ct = _make_ct_record((today + timedelta(days=120)).strftime("%Y-%m-%d"))
        event = linker.link_competitor_program(
            tracked_asset_id="asset-3",
            competitor_nct_id="NCT22222222",
            competitor_drug_name="TestDrug",
            same_moa=False,
            indication="rare_disease",
            competitor_ct_record=ct,
            current_value=200.0,
        )
        assert event is not None
        assert event.catalyst_type == CatalystType.COMPETITOR_READOUT

    def test_event_asset_id_is_tracked_asset(self):
        linker = _linker()
        today = _today()
        ct = _make_ct_record((today + timedelta(days=120)).strftime("%Y-%m-%d"))
        event = linker.link_competitor_program(
            tracked_asset_id="tracked-asset-xyz",
            competitor_nct_id="NCT33333333",
            competitor_drug_name="TestDrug",
            same_moa=False,
            indication="immunology",
            competitor_ct_record=ct,
            current_value=400.0,
        )
        assert event is not None
        assert event.asset_id == "tracked-asset-xyz"

    def test_event_fields_populated(self):
        linker = _linker()
        today = _today()
        ct = _make_ct_record((today + timedelta(days=90)).strftime("%Y-%m-%d"))
        event = linker.link_competitor_program(
            tracked_asset_id="asset-4",
            competitor_nct_id="NCT44444444",
            competitor_drug_name="Drug4",
            same_moa=True,
            indication="oncology",
            failure_type="efficacy",
            competitor_ct_record=ct,
            current_value=600.0,
        )
        assert event is not None
        assert event.delta_ev != 0.0
        assert event.signal_strength is not None
        assert event.asymmetry_ratio is not None
        assert event.std_dev >= 0.0


# ---------------------------------------------------------------------------
# Test 9: No competitor programs → empty list returned
# ---------------------------------------------------------------------------

class TestNoCompetitorPrograms:
    def test_empty_list_returns_empty(self):
        linker = _linker()
        ks = MagicMock()
        result = linker.link_all(
            tracked_asset_id="asset-empty",
            competitor_programs=[],
            knowledge_store=ks,
        )
        assert result == []
        ks.upsert_catalyst_event.assert_not_called()

    def test_none_ct_record_returns_none(self):
        """No CT record → no readout date estimable → returns None."""
        linker = _linker()
        event = linker.link_competitor_program(
            tracked_asset_id="asset-5",
            competitor_nct_id="NCT55555555",
            competitor_drug_name="Drug5",
            same_moa=False,
            indication="cns",
            competitor_ct_record=None,  # no record
            current_value=100.0,
        )
        assert event is None


# ---------------------------------------------------------------------------
# Test 10: Conservative defaults when propagation priors unavailable
# ---------------------------------------------------------------------------

class TestConservativeDefaults:
    def test_defaults_match_conservative_priors(self):
        """CONFIG_DEFAULTS must use conservative (smaller) magnitude values."""
        cfg = dict(_CONFIG_DEFAULTS)
        # market share compression on success: -8%
        assert cfg["market_share_delta_competitor_success"] == pytest.approx(-0.08)
        # PoS increase on efficacy failure: +5%
        assert cfg["pos_delta_competitor_failure"] == pytest.approx(0.05)
        # PoS decrease on safety failure: -3%
        assert cfg["pos_delta_competitor_failure_safety"] == pytest.approx(-0.03)
        # competitor neutral prior: 50%
        assert cfg["competitor_default_pos"] == pytest.approx(0.50)

    def test_yaml_section_loads_or_falls_back(self):
        """CompetitorCatalystLinker with no config arg uses YAML or defaults safely."""
        # Pass an empty dict to simulate no YAML section → should fall back to defaults
        linker = CompetitorCatalystLinker(config={})
        today = _today()
        ct = _make_ct_record((today + timedelta(days=90)).strftime("%Y-%m-%d"))
        # Should not raise; defaults embedded in the linker code
        event = linker.link_competitor_program(
            tracked_asset_id="asset-fallback",
            competitor_nct_id="NCT66666666",
            competitor_drug_name="FallbackDrug",
            same_moa=False,
            indication="oncology",
            competitor_ct_record=ct,
            current_value=200.0,
        )
        # With empty config, tau_years dict lookup falls back to default=1.5
        # event may be None if tau_map is not a dict — we test robustness
        # Actually with empty config, cfg.get("tau_years", ...) returns None → uses defaults
        # The function should still return an event (not crash)
        # (competitor_readout_date is set from CT record; current_value=200 > 0)
        assert event is not None

    def test_defaults_are_loaded_from_config_defaults_constant(self):
        """_CONFIG_DEFAULTS is the canonical fallback — verify it's complete."""
        required_keys = {
            "tau_years",
            "pos_delta_competitor_failure",
            "pos_delta_competitor_failure_safety",
            "market_share_delta_competitor_success",
            "market_share_delta_competitor_failure",
            "competitor_default_pos",
            "std_floor_multiplier",
        }
        assert required_keys.issubset(_CONFIG_DEFAULTS.keys())
