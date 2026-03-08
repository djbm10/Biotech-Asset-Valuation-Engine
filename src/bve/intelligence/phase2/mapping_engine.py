"""
Phase 2 mapping engine.

Converts a validated ``StructuredSignal`` into one or more
``AssumptionChangeProposal`` objects using deterministic, rule-based logic.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field

from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.intelligence.mapping import MappingRule, rules_for
from bve.intelligence.phase2.policy import MappingPolicy
from bve.intelligence.schemas.proposals import AssumptionChangeProposal
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import ChangeMode, EventType
from bve.models.market_model import MarketModel

_NON_SCALAR_PARAMETERS = {
    "market_model.lifecycle_events",
    "market_model.competition_model",
}

_MIN_SUCCESS_PROB = 1e-4
_MIN_DURATION_YEARS = 0.25
_MIN_COST_MILLIONS = 0.01
_MIN_POSITIVE = 1e-6


class MappingSkip(BaseModel):
    """Rule that could not be mapped to a numeric proposal."""

    event_type: EventType
    parameter_path: str
    reason: str


class MappingAuditEntry(BaseModel):
    """Explainable audit row for one generated proposal."""

    proposal_id: str
    event_type: EventType
    parameter_path: str
    change_mode: ChangeMode
    current_value: float
    proposed_value: float
    delta_pct: float
    extraction_confidence: float
    bound_pct: Optional[float]
    materiality_threshold_pct: float
    recommended_action: Literal["auto_apply", "manual_review"]
    explanation: str


class MappingBatchResult(BaseModel):
    """Output of one signal mapping pass."""

    signal_id: str
    proposals: list[AssumptionChangeProposal] = Field(default_factory=list)
    audit_log: list[MappingAuditEntry] = Field(default_factory=list)
    skipped: list[MappingSkip] = Field(default_factory=list)


class MappingEngine:
    """
    Rule-based mapper from ``StructuredSignal`` to ``AssumptionChangeProposal``.

    The mapper never mutates engine models directly. It only returns proposed
    numeric deltas plus an explicit audit trail.
    """

    def __init__(self, policy: Optional[MappingPolicy] = None) -> None:
        self.policy = policy or MappingPolicy.default()

    def map_signal(
        self,
        signal: StructuredSignal,
        *,
        engine_asset_id: str,
        asset: Asset,
        trials: list[ClinicalTrial],
        market_model: MarketModel,
        supporting_signal_ids: Optional[list[str]] = None,
        created_at: Optional[datetime] = None,
    ) -> MappingBatchResult:
        """
        Map one ``StructuredSignal`` to zero or more proposals.

        Parameters
        ----------
        signal:
            Input structured event.
        engine_asset_id:
            Target engine asset id for valuation updates.
        asset, trials, market_model:
            Current valuation state used to compute current values.
        """
        created_at = created_at or signal.created_at
        support_ids = sorted(set(supporting_signal_ids or []))
        event_policy = self.policy.for_event(signal.event_type)

        proposals: list[AssumptionChangeProposal] = []
        audit_log: list[MappingAuditEntry] = []
        skipped: list[MappingSkip] = []

        for rule in self._ordered_rules(signal.event_type):
            if rule.parameter not in event_policy.allowed_parameters:
                skipped.append(
                    MappingSkip(
                        event_type=signal.event_type,
                        parameter_path=rule.parameter,
                        reason="Parameter not allowed by event routing policy",
                    )
                )
                continue

            current_value = self._current_value(
                rule.parameter,
                signal=signal,
                asset=asset,
                trials=trials,
                market_model=market_model,
            )
            if current_value is None:
                skipped.append(
                    MappingSkip(
                        event_type=signal.event_type,
                        parameter_path=rule.parameter,
                        reason="Could not resolve a current value from valuation context",
                    )
                )
                continue

            proposed_value, explanation = self._proposed_value(
                current_value=current_value,
                signal=signal,
                rule=rule,
                materiality_threshold_pct=event_policy.materiality_threshold_pct,
            )

            rationale = (
                f"{rule.rationale} | current={current_value:.6g}, "
                f"proposed={proposed_value:.6g}. {explanation}"
            )

            try:
                proposal = AssumptionChangeProposal(
                    id=self._proposal_id(
                        signal_id=signal.id,
                        engine_asset_id=engine_asset_id,
                        event_type=signal.event_type,
                        parameter_path=rule.parameter,
                        current_value=float(current_value),
                        proposed_value=float(proposed_value),
                        change_mode=rule.change_mode,
                    ),
                    signal_id=signal.id,
                    asset_id=signal.asset_id,
                    engine_asset_id=engine_asset_id,
                    parameter_path=rule.parameter,
                    current_value=float(current_value),
                    proposed_value=float(proposed_value),
                    change_mode=rule.change_mode,
                    bound_pct=rule.bound_pct,
                    event_type=signal.event_type,
                    rationale=rationale,
                    supporting_signal_ids=support_ids,
                    created_at=created_at,
                )
            except Exception as exc:
                skipped.append(
                    MappingSkip(
                        event_type=signal.event_type,
                        parameter_path=rule.parameter,
                        reason=f"Proposal validation failed: {exc}",
                    )
                )
                continue

            recommended = self._recommended_action(
                proposal=proposal,
                confidence=signal.extraction_confidence,
                min_confidence=event_policy.min_confidence_score,
                materiality_threshold=event_policy.materiality_threshold_pct,
                review_requirement=event_policy.review_requirement,
            )
            proposals.append(proposal)
            audit_log.append(
                MappingAuditEntry(
                    proposal_id=proposal.id,
                    event_type=proposal.event_type,
                    parameter_path=proposal.parameter_path,
                    change_mode=proposal.change_mode,
                    current_value=proposal.current_value,
                    proposed_value=proposal.proposed_value,
                    delta_pct=proposal.proposed_delta_pct,
                    extraction_confidence=signal.extraction_confidence,
                    bound_pct=proposal.bound_pct,
                    materiality_threshold_pct=event_policy.materiality_threshold_pct,
                    recommended_action=recommended,
                    explanation=explanation,
                )
            )

        return MappingBatchResult(
            signal_id=signal.id,
            proposals=proposals,
            audit_log=audit_log,
            skipped=skipped,
        )

    @staticmethod
    def _recommended_action(
        *,
        proposal: AssumptionChangeProposal,
        confidence: float,
        min_confidence: float,
        materiality_threshold: float,
        review_requirement: str,
    ) -> Literal["auto_apply", "manual_review"]:
        if review_requirement == "manual_only":
            return "manual_review"
        if proposal.change_mode != ChangeMode.AUTO:
            return "manual_review"
        if confidence < min_confidence:
            return "manual_review"
        if abs(proposal.proposed_delta_pct) > materiality_threshold:
            return "manual_review"
        return "auto_apply"

    @staticmethod
    def _current_value(
        parameter_path: str,
        *,
        signal: StructuredSignal,
        asset: Asset,
        trials: list[ClinicalTrial],
        market_model: MarketModel,
    ) -> Optional[float]:
        if parameter_path in _NON_SCALAR_PARAMETERS:
            return 0.0

        if parameter_path == "asset.discount_rate":
            return float(asset.discount_rate)

        if parameter_path == "market_model.addressable_patients_annual":
            val = market_model.addressable_patients_annual
            return float(val) if val is not None else None
        if parameter_path == "market_model.total_addressable_market_millions":
            val = market_model.total_addressable_market_millions
            return float(val) if val is not None else None
        if parameter_path == "market_model.net_price_per_patient_usd":
            val = market_model.net_price_per_patient_usd
            return float(val) if val is not None else None
        if parameter_path == "market_model.peak_penetration":
            return float(market_model.peak_penetration)
        if parameter_path == "market_model.patent_life_years":
            return float(market_model.patent_life_years)

        if parameter_path.startswith("trials[*]."):
            if signal.trial_phase is None:
                return None
            trial = MappingEngine._trial_for_phase(trials, signal.trial_phase)
            if trial is None:
                return None
            field_name = parameter_path.split(".", 1)[1]
            return float(getattr(trial, field_name))

        return None

    @staticmethod
    def _trial_for_phase(
        trials: list[ClinicalTrial],
        phase: TrialPhase,
    ) -> Optional[ClinicalTrial]:
        for trial in trials:
            if trial.phase == phase:
                return trial
        return None

    @staticmethod
    def _ordered_rules(event_type: EventType) -> list[MappingRule]:
        """
        Deterministic rule ordering independent of source table insertion order.

        This ensures output ordering does not change even if EVENT_PARAMETER_MAP
        declaration order is edited.
        """
        return sorted(
            rules_for(event_type),
            key=lambda r: (r.parameter, r.change_mode.value, r.direction_hint, r.rationale),
        )

    @staticmethod
    def _proposal_id(
        *,
        signal_id: str,
        engine_asset_id: str,
        event_type: EventType,
        parameter_path: str,
        current_value: float,
        proposed_value: float,
        change_mode: ChangeMode,
    ) -> str:
        """
        Stable UUIDv5 for deterministic proposal identity.

        Identical signal + policy + valuation state -> identical proposal IDs.
        """
        key = "|".join(
            [
                signal_id,
                engine_asset_id,
                event_type.value,
                parameter_path,
                f"{current_value:.12g}",
                f"{proposed_value:.12g}",
                change_mode.value,
            ]
        )
        return str(uuid5(NAMESPACE_URL, key))

    def _proposed_value(
        self,
        *,
        current_value: float,
        signal: StructuredSignal,
        rule: MappingRule,
        materiality_threshold_pct: float,
    ) -> tuple[float, str]:
        if rule.parameter in _NON_SCALAR_PARAMETERS:
            return 0.0, "Non-scalar parameter requires manual analyst edit"

        if rule.change_mode == ChangeMode.MANUAL:
            return current_value, "Manual rule: proposal is a review flag without auto delta"

        if rule.parameter == "trials[*].success_probability":
            return self._propose_success_probability(current_value, signal, rule)
        if rule.parameter == "trials[*].duration_years":
            return self._propose_duration(current_value, signal, rule)
        if rule.parameter == "trials[*].cost_millions":
            return self._propose_positive_scalar(current_value, signal, rule, _MIN_COST_MILLIONS)
        if rule.parameter == "market_model.addressable_patients_annual":
            proposed, note = self._propose_positive_scalar(current_value, signal, rule, 1.0)
            return float(max(1, int(round(proposed)))), f"{note}; rounded to integer patients"
        if rule.parameter == "market_model.total_addressable_market_millions":
            return self._propose_positive_scalar(current_value, signal, rule, _MIN_POSITIVE)
        if rule.parameter == "market_model.net_price_per_patient_usd":
            return self._propose_positive_scalar(current_value, signal, rule, _MIN_POSITIVE)
        if rule.parameter == "market_model.peak_penetration":
            proposed, note = self._propose_positive_scalar(current_value, signal, rule, 0.01)
            return float(min(0.99, max(0.01, proposed))), f"{note}; clamped to [0.01, 0.99]"
        if rule.parameter == "market_model.patent_life_years":
            proposed, note = self._propose_positive_scalar(current_value, signal, rule, 1.0)
            return float(max(1, int(round(proposed)))), f"{note}; rounded to integer years"
        if rule.parameter == "asset.discount_rate":
            proposed, note = self._propose_positive_scalar(current_value, signal, rule, 0.01)
            return float(min(0.50, max(0.01, proposed))), f"{note}; clamped to [0.01, 0.50]"

        # Defensive default.
        return current_value, "Unsupported parameter path; no numeric change applied"

    def _propose_success_probability(
        self,
        current_value: float,
        signal: StructuredSignal,
        rule: MappingRule,
    ) -> tuple[float, str]:
        # Binary regulatory/program events.
        if signal.event_type == EventType.FDA_APPROVAL and signal.fda_action_type == "approval":
            proposed = min(0.99, current_value * 2.0)  # +100% max bound for AUTO rule
            return proposed, "FDA approval mapped to maximum allowed AUTO uplift"
        if signal.event_type in {EventType.FDA_REJECTION, EventType.PROGRAM_DISCONTINUATION}:
            return _MIN_SUCCESS_PROB, "CRL/discontinuation mapped to near-zero success_probability"

        sign = self._direction(signal, rule)
        magnitude = self._delta_magnitude_pct(signal, rule)
        proposed = current_value * (1.0 + sign * magnitude / 100.0)
        proposed = min(0.99, max(_MIN_SUCCESS_PROB, proposed))
        return proposed, f"Applied {sign:+d} sign with {magnitude:.2f}% bounded POS delta"

    def _propose_duration(
        self,
        current_value: float,
        signal: StructuredSignal,
        rule: MappingRule,
    ) -> tuple[float, str]:
        magnitude = self._delta_magnitude_pct(signal, rule)

        # Trial readout usually compresses the active phase timeline.
        if signal.event_type == EventType.TRIAL_READOUT and signal.primary_endpoint_met is not False:
            sign = -1
        else:
            sign = self._direction(signal, rule)

        proposed = current_value * (1.0 + sign * magnitude / 100.0)
        proposed = max(_MIN_DURATION_YEARS, proposed)
        return proposed, f"Applied {sign:+d} sign with {magnitude:.2f}% duration delta"

    def _propose_positive_scalar(
        self,
        current_value: float,
        signal: StructuredSignal,
        rule: MappingRule,
        floor_value: float,
    ) -> tuple[float, str]:
        sign = self._direction(signal, rule)
        magnitude = self._delta_magnitude_pct(signal, rule)
        proposed = current_value * (1.0 + sign * magnitude / 100.0)
        proposed = max(floor_value, proposed)
        return proposed, f"Applied {sign:+d} sign with {magnitude:.2f}% bounded delta"

    @staticmethod
    def _delta_magnitude_pct(signal: StructuredSignal, rule: MappingRule) -> float:
        bound = rule.bound_pct or 0.0
        if bound <= 0.0:
            return 0.0

        # Deterministic confidence-weighted magnitude (still hard-capped by bound).
        confidence = max(0.35, min(1.0, signal.extraction_confidence))
        raw = bound * confidence
        min_floor = min(bound, max(1.0, bound * 0.40))
        return round(min(bound, max(min_floor, raw)), 4)

    @staticmethod
    def _direction(signal: StructuredSignal, rule: MappingRule) -> int:
        if rule.direction_hint == "increase":
            return 1
        if rule.direction_hint == "decrease":
            return -1

        # direction_hint == "either": infer from signal content.
        if signal.primary_endpoint_met is not None:
            return 1 if signal.primary_endpoint_met else -1
        if signal.hazard_ratio is not None:
            return 1 if signal.hazard_ratio < 1.0 else -1
        if signal.fda_action_type in {"approval", "designation", "hold_lifted"}:
            return 1
        if signal.fda_action_type in {"crl", "hold"}:
            return -1
        if signal.event_type in {
            EventType.FDA_APPROVAL,
            EventType.FDA_DESIGNATION,
            EventType.LABEL_EXPANSION,
            EventType.PARTNERSHIP,
        }:
            return 1
        if signal.event_type in {
            EventType.FDA_REJECTION,
            EventType.PROGRAM_DISCONTINUATION,
            EventType.SAFETY_SIGNAL,
            EventType.REGULATORY_HOLD,
            EventType.COMPETITOR_EVENT,
        }:
            return -1
        return 1
