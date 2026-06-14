"""Tests for ProfileBuilder (mocked fetchers, offline)."""
from __future__ import annotations

import pytest

from bve.config.assumptions_loader import AssumptionsLoader
from bve.pipeline.profile_builder import ProfileBuilder, economics_prior
from bve.pipeline.universe_registry import UniverseRegistryEntry


def _seed(**overrides) -> UniverseRegistryEntry:
    base = dict(
        ticker="ABC",
        company_name="ABC Bio",
        asset_id="asset-abc-1",
        drug_name="ABC-101",
        indication="NSCLC",
        therapeutic_area="oncology",
        stage="phase_2",
        modality="small_molecule",
        nct_id="NCT12345678",
    )
    base.update(overrides)
    return UniverseRegistryEntry(**base)


def _builder(*, sec=None, ctgov=None, market=None) -> ProfileBuilder:
    return ProfileBuilder(
        sec_fetcher=lambda t: sec or {},
        ctgov_fetcher=lambda n: ctgov or {},
        market_fetcher=lambda t: market or {},
    )


def test_identity_from_seed_is_high_confidence():
    profile = _builder().build(_seed())
    asset = profile.lead_asset
    assert asset.drug_name.value == "ABC-101"
    assert asset.drug_name.confidence == "high"
    assert asset.indication.value == "NSCLC"
    assert profile.ticker == "ABC"
    assert profile.company_id == "abc-auto"
    assert profile.evidence_level == "coarse"


def test_economics_default_to_low_confidence_heuristic_priors():
    # Seed carries NO economics → builder must use heuristic priors, flagged low.
    profile = _builder().build(_seed())
    asset = profile.lead_asset
    prior = economics_prior("oncology")

    assert asset.peak_penetration.value == prior["peak_penetration"]
    assert asset.peak_penetration.confidence == "low"
    assert asset.peak_penetration.source == "heuristic_prior"
    assert asset.total_addressable_market_millions.confidence == "low"
    # These are exactly the fields the analyst is expected to override.
    assert "peak_penetration" in asset.low_confidence_fields()
    assert "total_addressable_market_millions" in asset.low_confidence_fields()


def test_seed_economics_override_priors_at_medium_confidence():
    profile = _builder().build(_seed(tam_millions=12000.0, peak_penetration=0.4))
    asset = profile.lead_asset
    assert asset.total_addressable_market_millions.value == 12000.0
    assert asset.total_addressable_market_millions.confidence == "medium"
    assert asset.peak_penetration.value == 0.4
    assert asset.peak_penetration.confidence == "medium"


def test_ctgov_facts_are_high_confidence_when_present():
    ctgov = {
        "phase": "PHASE3",
        "enrollment": 450,
        "primary_endpoint": "Overall survival",
        "estimated_completion_date": "2027-06-01",
    }
    profile = _builder(ctgov=ctgov).build(_seed(stage="phase_2"))
    asset = profile.lead_asset
    # CT.gov phase refines the seed stage.
    assert asset.stage.value == "phase_3"
    assert asset.stage.source == "clinicaltrials_gov"
    assert asset.enrollment.value == 450
    assert asset.enrollment.confidence == "high"
    assert asset.primary_endpoint.value == "Overall survival"


def test_company_financials_from_sec_and_market():
    sec = {
        "cash_millions": 800.0,
        "shares_outstanding_millions": 120.0,
        "long_term_debt_millions": 50.0,
        "rd_expense_millions": 400.0,
    }
    market = {"current_price": 25.5, "market_cap_millions": 3060.0}
    profile = _builder(sec=sec, market=market).build(_seed())
    assert profile.cash_millions.value == 800.0
    assert profile.cash_millions.confidence == "high"
    assert profile.current_price.value == 25.5
    # rd_expense → quarterly burn derived by the default-style normalizer path
    assert profile.burn_rate_millions_per_quarter.value == 100.0


def test_missing_public_sources_yield_low_confidence_unset_fields():
    profile = _builder().build(_seed())  # all fetchers return {}
    assert profile.cash_millions.value is None
    assert profile.cash_millions.confidence == "low"
    assert profile.current_price.value is None


def test_pos_uses_cumulative_approval_not_transition_rate():
    # A Phase 1 asset's success_probability must be the CUMULATIVE probability of
    # approval from Phase 1 — not the Phase 1->2 transition rate, which would make
    # the single-trial engine model treat it as ~67% approval odds.
    loader = AssumptionsLoader.get()
    cumulative = loader.prob_approval_from_phase.get("rare_disease", {}).get("phase_1")
    transition = loader.phase_success_rates_for("rare_disease").get("phase_1")
    assert cumulative is not None and transition is not None
    assert cumulative < transition  # sanity: cumulative-to-approval < single transition

    profile = _builder(ctgov={"phase": "PHASE1"}).build(
        _seed(therapeutic_area="rare_disease", stage="phase_1")
    )
    sp = profile.lead_asset.success_probability
    assert sp.value == pytest.approx(cumulative, rel=1e-6)
    assert sp.value != pytest.approx(transition, rel=1e-6)
    # Realistic Phase 1 rare-disease cumulative PoS is ~17%, not ~67%.
    assert 0.10 < sp.value < 0.25


def test_pos_phase1_2_uses_cumulative_for_normalized_phase():
    # A Phase 1/2 trial normalizes to phase_2; PoS must be the cumulative
    # approval probability from phase_2 (not the phase_2->3 transition).
    loader = AssumptionsLoader.get()
    cumulative_p2 = loader.prob_approval_from_phase.get("oncology", {}).get("phase_2")
    profile = _builder(ctgov={"phase": "PHASE1/PHASE2"}).build(
        _seed(therapeutic_area="oncology", stage="phase_1")
    )
    asset = profile.lead_asset
    assert asset.stage.value == "phase_2"  # CT.gov phase 1/2 -> phase_2
    assert asset.success_probability.value == pytest.approx(cumulative_p2, rel=1e-6)


def test_ctgov_phase_does_not_downgrade_a_late_stage_seed():
    # A curated nda_bla seed linked to a registrational trial that CT.gov lists as
    # Phase 1/2 must STAY nda_bla — but still pick up the trial facts.
    ctgov = {"phase": "PHASE1", "enrollment": 447, "primary_endpoint": "ORR"}
    profile = _builder(ctgov=ctgov).build(_seed(stage="nda_bla"))
    asset = profile.lead_asset
    assert asset.stage.value == "nda_bla"  # not downgraded to phase_1
    assert asset.stage.source == "seed"
    assert asset.enrollment.value == 447  # trial facts still sourced
    assert asset.enrollment.confidence == "high"


def test_failing_fetcher_does_not_abort_build():
    def boom(_):
        raise RuntimeError("network down")

    builder = ProfileBuilder(sec_fetcher=boom, ctgov_fetcher=boom, market_fetcher=boom)
    profile = builder.build(_seed())
    # Build still succeeds with seed identity + heuristic economics.
    assert profile.lead_asset.drug_name.value == "ABC-101"
    assert profile.lead_asset.peak_penetration.source == "heuristic_prior"
