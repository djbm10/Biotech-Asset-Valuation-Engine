from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from bve.entities.asset import DevelopmentStage
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.intelligence.acquisition_readiness import AcquisitionReadinessAssessor
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType


def test_phase3_asset_is_acquisition_ready_without_signals():
    assessment = AcquisitionReadinessAssessor().assess(
        asset_id="asset-1",
        asset_stage=DevelopmentStage.PHASE_3,
        engine_asset_id="engine-1",
        trials=[],
        as_of_date=date(2026, 3, 21),
    )

    assert assessment.is_acquisition_ready is True
    assert assessment.readiness_bucket == "phase_3_or_later"
    assert assessment.evidence_source == "asset_stage"


def test_phase2_asset_without_knowledge_store_is_not_ready():
    assessment = AcquisitionReadinessAssessor().assess(
        asset_id="asset-1",
        asset_stage=DevelopmentStage.PHASE_2,
        engine_asset_id="engine-1",
        trials=[],
        as_of_date=date(2026, 3, 21),
    )

    assert assessment.is_acquisition_ready is False
    assert assessment.exclusion_reason == "missing_knowledge_store"


def test_phase2_positive_readout_with_adequate_power_is_ready(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        _store_phase2_signal(store)
        assessment = AcquisitionReadinessAssessor(knowledge_store=store).assess(
            asset_id="asset-1",
            asset_stage=DevelopmentStage.PHASE_2,
            engine_asset_id="engine-1",
            trials=[_phase3_trial()],
            as_of_date=date(2026, 3, 21),
        )

        assert assessment.is_acquisition_ready is True
        assert assessment.readiness_bucket == "phase_2_poc"
        assert assessment.evidence_source == "phase_correlation"
        assert assessment.trial_design_tier == "standard"
        assert assessment.low_power_flag is False
        assert assessment.phase_posterior_pos is not None
        assert assessment.phase_prior_pos is not None
        assert assessment.phase_posterior_pos > assessment.phase_prior_pos
    finally:
        store.close()


def test_phase2_positive_readout_with_low_power_is_not_ready(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        _store_phase2_signal(
            store,
            n_patients=20,
            estimated_effect_size=0.10,
            p_value=0.04,
        )
        assessment = AcquisitionReadinessAssessor(knowledge_store=store).assess(
            asset_id="asset-1",
            asset_stage=DevelopmentStage.PHASE_2,
            engine_asset_id="engine-1",
            trials=[_phase3_trial()],
            as_of_date=date(2026, 3, 21),
        )

        assert assessment.is_acquisition_ready is False
        assert assessment.exclusion_reason == "phase_2_low_power"
        assert assessment.low_power_flag is True
    finally:
        store.close()


def test_phase2_negative_readout_is_not_ready(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        _store_phase2_signal(
            store,
            primary_endpoint_met=False,
            p_value=0.40,
        )
        assessment = AcquisitionReadinessAssessor(knowledge_store=store).assess(
            asset_id="asset-1",
            asset_stage=DevelopmentStage.PHASE_2,
            engine_asset_id="engine-1",
            trials=[_phase3_trial()],
            as_of_date=date(2026, 3, 21),
        )

        assert assessment.is_acquisition_ready is False
        assert assessment.exclusion_reason == "phase_2_negative_readout"
    finally:
        store.close()


def _phase3_trial() -> ClinicalTrial:
    return ClinicalTrial(
        asset_id="asset-1",
        phase=TrialPhase.PHASE_3,
        success_probability=0.55,
        duration_years=3.0,
        cost_millions=120.0,
    )


def _store_phase2_signal(
    store: KnowledgeStore,
    *,
    primary_endpoint_met: bool = True,
    p_value: float = 0.01,
    randomization: str = "randomized",
    n_patients: int = 160,
    estimated_effect_size: float = 0.45,
    alpha_level: float = 0.05,
) -> None:
    store.add_structured_signal(
        StructuredSignal(
            id="sig-asset-1",
            event_id="evt-asset-1",
            asset_id="asset-1",
            company_id="co-1",
            event_type=EventType.TRIAL_READOUT,
            signal_date=date(2026, 3, 1),
            trial_phase=TrialPhase.PHASE_2,
            randomization=randomization,
            comparator_type="active_comparator" if randomization == "randomized" else "none",
            n_patients=n_patients,
            estimated_effect_size=estimated_effect_size,
            alpha_level=alpha_level,
            primary_endpoint_met=primary_endpoint_met,
            p_value=p_value,
            extraction_confidence=0.95,
            extraction_model="unit-test",
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        ),
        SourceTrace(
            source_type="unit_test",
            source_ref="phase2-signal",
            ingested_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        ),
        extraction_result_id="ext-asset-1",
    )
