from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase
from bve.intelligence.phase2 import ValuationSession
from bve.intelligence.schemas.proposals import AssumptionChangeProposal
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import ChangeMode, EventType
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import MonteCarloParams

_NOW = datetime(2026, 1, 8, 11, 0, tzinfo=timezone.utc)


def _context():
    asset = Asset(
        id="asset-rly2608",
        name="RLY-2608",
        indication="HR+/HER2- mBC",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=0.10,
    )
    company = Company(
        id="company-rly",
        name="Relay Therapeutics",
        ticker="RLAY",
        cash_millions=410.0,
        debt_millions=0.0,
        shares_outstanding_millions=93.6,
        asset_ids=[asset.id],
    )
    trials = [
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
    market = MarketModel(
        asset_id=asset.id,
        addressable_patients_annual=17000,
        net_price_per_patient_usd=180000,
        peak_penetration=0.22,
        years_to_peak=5,
        patent_life_years=12,
    )
    return asset, company, trials, market


def test_valuation_diff_logging_and_rollback(tmp_path: Path):
    asset, company, trials, market = _context()
    session = ValuationSession(
        asset=asset,
        company=company,
        trials=trials,
        market_model=market,
        output_dir=tmp_path / "phase2_runs",
        mc_params=MonteCarloParams(n_simulations=150, random_seed=123),
    )

    before = session.current_output()
    signal = StructuredSignal(
        id="sig-1",
        event_id="evt-1",
        asset_id=asset.id,
        company_id=company.id,
        event_type=EventType.TRIAL_READOUT,
        signal_date=date(2026, 1, 8),
        trial_phase=TrialPhase.PHASE_2,
        primary_endpoint_met=True,
        extraction_confidence=0.95,
        extraction_model="test",
        created_at=_NOW,
    )
    proposal = AssumptionChangeProposal(
        id="prop-1",
        signal_id=signal.id,
        asset_id=asset.id,
        engine_asset_id=asset.id,
        parameter_path="trials[*].success_probability",
        current_value=0.45,
        proposed_value=0.54,
        change_mode=ChangeMode.AUTO,
        bound_pct=20.0,
        event_type=EventType.TRIAL_READOUT,
        rationale="positive readout",
        created_at=_NOW,
    )

    record = session.apply_proposals(
        proposals=[proposal],
        effective_values={proposal.id: proposal.proposed_value},
        signals_by_id={signal.id: signal},
        analyst_id="analyst-1",
        notes="phase2 integration test",
        run_at=_NOW,
    )

    assert record.run.rnpv_millions_before is not None
    assert record.run.rnpv_millions_after is not None
    assert record.diff.delta_npv != 0.0
    assert record.diff.asset_id == asset.id
    assert record.diff.event_id == signal.event_id
    assert len(record.diff.assumptions_changed) == 1
    fc = record.diff.assumptions_changed[0]
    assert fc.field == "trials[phase_2].success_probability"
    assert fc.old_value == 0.45
    assert fc.new_value == 0.54
    assert fc.delta > 0
    assert record.diff.valuation_before.rnpv_millions == before.rnpv.rnpv_millions
    assert record.diff.valuation_after.rnpv_millions == record.run.rnpv_millions_after
    assert "trials[phase_2].success_probability" in record.run.parameter_overrides
    assert Path(record.before_path).exists()
    assert Path(record.after_path).exists()
    assert Path(record.diff_path).exists()
    assert Path(record.manifest_path).exists()

    rollback = session.rollback_last()
    assert rollback.rolled_back_run_id == record.run.id
    assert rollback.remaining_run_ids == []

    restored = session.current_output()
    assert restored.rnpv.rnpv_millions == before.rnpv.rnpv_millions
    assert restored.nav_per_share == before.nav_per_share
