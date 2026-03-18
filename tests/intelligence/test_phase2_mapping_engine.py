from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase
from bve.intelligence.mapping import EVENT_PARAMETER_MAP
from bve.intelligence.phase2 import EventRoutingPolicy, MappingEngine, MappingPolicy
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType
from bve.models.market_model import MarketModel

_NOW = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def asset() -> Asset:
    return Asset(
        id="asset-rly2608",
        name="RLY-2608",
        indication="HR+/HER2- mBC",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=0.10,
    )


@pytest.fixture
def trials(asset: Asset) -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id=asset.id,
            phase=TrialPhase.PHASE_2,
            success_probability=0.45,
            duration_years=2.0,
            cost_millions=80.0,
            endpoint_type=EndpointType.SURROGATE_VALIDATED,
        ),
        ClinicalTrial(
            asset_id=asset.id,
            phase=TrialPhase.PHASE_3,
            success_probability=0.70,
            duration_years=2.5,
            cost_millions=140.0,
            endpoint_type=EndpointType.SURROGATE_VALIDATED,
        ),
        ClinicalTrial(
            asset_id=asset.id,
            phase=TrialPhase.NDA_BLA,
            success_probability=0.85,
            duration_years=1.0,
            cost_millions=20.0,
            endpoint_type=EndpointType.SURROGATE_VALIDATED,
        ),
    ]


@pytest.fixture
def market(asset: Asset) -> MarketModel:
    # Keep both patient and TAM fields populated so all legal parameter paths
    # can resolve current values during mapping tests.
    return MarketModel(
        asset_id=asset.id,
        addressable_patients_annual=18000,
        net_price_per_patient_usd=180000,
        total_addressable_market_millions=1200.0,
        peak_penetration=0.22,
        years_to_peak=5,
        patent_life_years=12,
    )


def _signal(event_type: EventType) -> StructuredSignal:
    fda_action = None
    if event_type == EventType.FDA_APPROVAL:
        fda_action = "approval"
    elif event_type == EventType.FDA_REJECTION:
        fda_action = "crl"
    elif event_type == EventType.REGULATORY_HOLD:
        fda_action = "hold"
    elif event_type == EventType.FDA_DESIGNATION:
        fda_action = "designation"

    return StructuredSignal(
        id=f"sig-{event_type.value}",
        event_id=f"evt-{event_type.value}",
        asset_id="asset-rly2608",
        company_id="company-rly",
        event_type=event_type,
        signal_date=date(2026, 1, 5),
        trial_phase=TrialPhase.PHASE_2,
        primary_endpoint_met=True,
        fda_action_type=fda_action,
        extraction_model="test",
        extraction_confidence=0.92,
        created_at=_NOW,
    )


def test_default_policy_keeps_allowed_fields_in_sync():
    policy = MappingPolicy.default()
    for event_type, rules in EVENT_PARAMETER_MAP.items():
        allowed = set(policy.for_event(event_type).allowed_parameters)
        expected = {r.parameter for r in rules}
        assert allowed == expected


def test_default_policy_materiality_thresholds_allow_major_event_auto_rules():
    policy = MappingPolicy.default()
    assert policy.for_event(EventType.TRIAL_READOUT).materiality_threshold_pct == 20.0
    assert policy.for_event(EventType.FDA_APPROVAL).materiality_threshold_pct == 100.0
    assert policy.for_event(EventType.FDA_REJECTION).materiality_threshold_pct == 100.0
    assert policy.for_event(EventType.FDA_DESIGNATION).materiality_threshold_pct == 20.0


@pytest.mark.parametrize("event_type", list(EventType))
def test_mapping_engine_emits_one_proposal_per_rule(
    event_type: EventType,
    asset: Asset,
    trials: list[ClinicalTrial],
    market: MarketModel,
):
    engine = MappingEngine()
    signal = _signal(event_type)
    result = engine.map_signal(
        signal,
        engine_asset_id=asset.id,
        asset=asset,
        trials=trials,
        market_model=market,
    )

    expected_rules = EVENT_PARAMETER_MAP[event_type]
    expected_params = {r.parameter for r in expected_rules}
    actual_params = {p.parameter_path for p in result.proposals}

    assert actual_params == expected_params
    assert len(result.audit_log) == len(result.proposals)
    assert result.skipped == []

    rule_by_param = {r.parameter: r for r in expected_rules}
    for proposal in result.proposals:
        rule = rule_by_param[proposal.parameter_path]
        assert proposal.change_mode == rule.change_mode
        assert proposal.event_type == event_type
        assert proposal.asset_id == signal.asset_id
        if rule.bound_pct is not None:
            assert abs(proposal.proposed_delta_pct) <= rule.bound_pct + 1e-6


def test_trial_readout_primary_endpoint_failure_reduces_pos(
    asset: Asset,
    trials: list[ClinicalTrial],
    market: MarketModel,
):
    engine = MappingEngine()
    signal = _signal(EventType.TRIAL_READOUT).model_copy(update={"primary_endpoint_met": False})
    result = engine.map_signal(
        signal,
        engine_asset_id=asset.id,
        asset=asset,
        trials=trials,
        market_model=market,
    )
    proposal = next(p for p in result.proposals if p.parameter_path == "trials[*].success_probability")
    assert proposal.proposed_value < proposal.current_value


def test_mapping_is_deterministic_for_identical_input(
    asset: Asset,
    trials: list[ClinicalTrial],
    market: MarketModel,
):
    engine = MappingEngine()
    signal = _signal(EventType.TRIAL_READOUT)

    result_a = engine.map_signal(
        signal,
        engine_asset_id=asset.id,
        asset=asset,
        trials=trials,
        market_model=market,
    )
    result_b = engine.map_signal(
        signal,
        engine_asset_id=asset.id,
        asset=asset,
        trials=trials,
        market_model=market,
    )

    assert result_a.model_dump() == result_b.model_dump()


def test_rule_order_does_not_change_behavior(
    monkeypatch: pytest.MonkeyPatch,
    asset: Asset,
    trials: list[ClinicalTrial],
    market: MarketModel,
):
    import bve.intelligence.phase2.mapping_engine as mapping_engine_module

    signal = _signal(EventType.TRIAL_READOUT)
    engine = MappingEngine()
    baseline = engine.map_signal(
        signal,
        engine_asset_id=asset.id,
        asset=asset,
        trials=trials,
        market_model=market,
    )

    def _reversed_rules(event_type: EventType):
        return list(reversed(EVENT_PARAMETER_MAP[event_type]))

    monkeypatch.setattr(mapping_engine_module, "rules_for", _reversed_rules)

    reordered = engine.map_signal(
        signal,
        engine_asset_id=asset.id,
        asset=asset,
        trials=trials,
        market_model=market,
    )

    assert baseline.model_dump() == reordered.model_dump()


def test_allowed_fields_enforced_by_policy(
    asset: Asset,
    trials: list[ClinicalTrial],
    market: MarketModel,
):
    policy = MappingPolicy.default()
    policy.events[EventType.TRIAL_READOUT] = EventRoutingPolicy(
        event_type=EventType.TRIAL_READOUT,
        allowed_parameters=("trials[*].success_probability",),
        min_confidence_score=0.60,
        materiality_threshold_pct=12.0,
        review_requirement="rule_based",
    )
    engine = MappingEngine(policy=policy)
    signal = _signal(EventType.TRIAL_READOUT)

    result = engine.map_signal(
        signal,
        engine_asset_id=asset.id,
        asset=asset,
        trials=trials,
        market_model=market,
    )

    assert {p.parameter_path for p in result.proposals} == {"trials[*].success_probability"}
    skipped_params = {s.parameter_path for s in result.skipped}
    assert skipped_params == {
        "trials[*].duration_years",
        "market_model.peak_penetration",
    }
