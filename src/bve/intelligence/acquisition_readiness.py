"""Acquisition-readiness gate for the M&A screen."""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.intelligence.phase_correlation_updater import PhaseCorrelationUpdater
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType
from bve.intelligence.trial_design_assessment import assess_trial_design

if TYPE_CHECKING:  # pragma: no cover
    from bve.intelligence.knowledge_layer import KnowledgeStore, StructuredSignalRecord


_PRE_PHASE_2_STAGES = {"preclinical", "phase_1"}
_LATE_STAGE_STAGES = {"phase_3", "nda_bla", "approved", "commercial"}


def _normalize_stage(value: object) -> Optional[str]:
    if value is None:
        return None
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    if isinstance(value, str):
        normalized = " ".join(value.strip().lower().split())
        mapping = {
            "phase 1": "phase_1",
            "phase 2": "phase_2",
            "phase 3": "phase_3",
            "nda/bla": "nda_bla",
        }
        return mapping.get(normalized, normalized)
    return None


class AcquisitionReadinessAssessment(BaseModel):
    """Acquisition-readiness classification for one asset."""

    asset_id: str
    is_acquisition_ready: bool
    readiness_bucket: str
    evidence_source: Optional[str] = None
    exclusion_reason: Optional[str] = None
    source_signal_id: Optional[str] = None
    phase_2_primary_endpoint_met: Optional[bool] = None
    trial_design_tier: Optional[str] = None
    trial_design_multiplier: Optional[float] = None
    statistical_power: Optional[float] = None
    low_power_flag: bool = False
    phase_prior_pos: Optional[float] = None
    phase_posterior_pos: Optional[float] = None
    phase_data_source: Optional[str] = None
    single_arm_penalty_applied: bool = False


class AcquisitionReadinessAssessor:
    """Assess whether an asset is acquisition-ready for the M&A screen."""

    def __init__(
        self,
        *,
        knowledge_store: Optional["KnowledgeStore"] = None,
        phase_correlation_updater: Optional[PhaseCorrelationUpdater] = None,
    ) -> None:
        self.knowledge = knowledge_store
        self.phase_correlation = phase_correlation_updater or PhaseCorrelationUpdater()

    def assess(
        self,
        *,
        asset_id: str,
        asset_stage: object,
        engine_asset_id: Optional[str] = None,
        trials: Optional[list[ClinicalTrial]] = None,
        as_of_date: Optional[date] = None,
    ) -> AcquisitionReadinessAssessment:
        stage = _normalize_stage(asset_stage)
        if stage in _LATE_STAGE_STAGES:
            return AcquisitionReadinessAssessment(
                asset_id=asset_id,
                is_acquisition_ready=True,
                readiness_bucket="phase_3_or_later",
                evidence_source="asset_stage",
            )
        if stage in _PRE_PHASE_2_STAGES:
            return AcquisitionReadinessAssessment(
                asset_id=asset_id,
                is_acquisition_ready=False,
                readiness_bucket="pre_phase_2",
                evidence_source="asset_stage",
                exclusion_reason="pre_phase_2_stage",
            )
        if stage != "phase_2":
            return AcquisitionReadinessAssessment(
                asset_id=asset_id,
                is_acquisition_ready=False,
                readiness_bucket="unknown",
                exclusion_reason="unknown_asset_stage",
            )

        if self.knowledge is None:
            return AcquisitionReadinessAssessment(
                asset_id=asset_id,
                is_acquisition_ready=False,
                readiness_bucket="phase_2_pre_poc",
                evidence_source="knowledge_gap",
                exclusion_reason="missing_knowledge_store",
            )

        signals = self.knowledge.get_structured_signals(
            asset_id=asset_id,
            event_type=EventType.TRIAL_READOUT,
            date_to=as_of_date,
            limit=50,
        )
        phase2_records = [
            record
            for record in signals
            if (record.payload_json or {}).get("trial_phase") == TrialPhase.PHASE_2.value
        ]
        signal_record, signal = self._first_valid_signal(phase2_records)
        if signal_record is None or signal is None:
            return AcquisitionReadinessAssessment(
                asset_id=asset_id,
                is_acquisition_ready=False,
                readiness_bucket="phase_2_pre_poc",
                evidence_source="knowledge_store",
                exclusion_reason="missing_phase_2_readout",
            )

        design = assess_trial_design(signal)
        prior_pos = self._phase3_prior(trials) or 0.50
        phase_result = self.phase_correlation.update(
            asset_id=asset_id,
            engine_asset_id=engine_asset_id or asset_id,
            prior_pos=prior_pos,
            signals=phase2_records,
        )
        base = {
            "asset_id": asset_id,
            "readiness_bucket": "phase_2_pre_poc",
            "evidence_source": "phase_correlation" if phase_result.update_applied else "phase_2_readout",
            "source_signal_id": signal_record.id,
            "phase_2_primary_endpoint_met": signal.primary_endpoint_met,
            "trial_design_tier": design.design_quality_tier.value,
            "trial_design_multiplier": round(float(design.design_quality_multiplier), 6),
            "statistical_power": (
                round(float(design.statistical_power), 6)
                if design.statistical_power is not None
                else None
            ),
            "low_power_flag": bool(design.low_power_flag),
            "phase_prior_pos": round(float(phase_result.prior_pos), 6),
            "phase_posterior_pos": round(float(phase_result.posterior_pos), 6),
            "phase_data_source": phase_result.phase_data_source,
            "single_arm_penalty_applied": bool(phase_result.single_arm_penalty_applied),
        }

        if signal.primary_endpoint_met is False:
            return AcquisitionReadinessAssessment(
                **base,
                is_acquisition_ready=False,
                exclusion_reason="phase_2_negative_readout",
            )
        if not phase_result.update_applied or phase_result.phase_data_source != "phase_2":
            return AcquisitionReadinessAssessment(
                **base,
                is_acquisition_ready=False,
                exclusion_reason="missing_quantitative_phase_2_signal",
            )
        if design.low_power_flag:
            return AcquisitionReadinessAssessment(
                **base,
                is_acquisition_ready=False,
                exclusion_reason="phase_2_low_power",
            )
        if phase_result.posterior_pos <= phase_result.prior_pos:
            return AcquisitionReadinessAssessment(
                **base,
                is_acquisition_ready=False,
                exclusion_reason="phase_2_not_de_risked",
            )
        return AcquisitionReadinessAssessment(
            **{
                **base,
                "readiness_bucket": "phase_2_poc",
                "evidence_source": "phase_correlation",
            },
            is_acquisition_ready=True,
        )

    @staticmethod
    def _first_valid_signal(
        records: list["StructuredSignalRecord"],
    ) -> tuple[Optional["StructuredSignalRecord"], Optional[StructuredSignal]]:
        for record in records:
            try:
                signal = StructuredSignal.model_validate(record.payload_json)
            except Exception:
                continue
            return record, signal
        return None, None

    @staticmethod
    def _phase3_prior(trials: Optional[list[ClinicalTrial]]) -> Optional[float]:
        for trial in trials or []:
            if trial.phase == TrialPhase.PHASE_3:
                return float(trial.success_probability)
        return None
