"""
Phase 2 valuation integration service.

Applies reviewed proposal overrides to a valuation state, runs the existing
valuation engine before/after, logs a structured diff, and supports rollback.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from bve.entities.asset import Asset
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial
from bve.intelligence.schemas.proposals import AssumptionChangeProposal
from bve.intelligence.schemas.runs import ValuationRun
from bve.intelligence.schemas.signals import StructuredSignal
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import MonteCarloParams
from bve.valuation.outputs import ValuationOutput
from bve.valuation.valuation_engine import ValuationEngine

_NON_SCALAR_PARAMETERS = {
    "market_model.lifecycle_events",
    "market_model.competition_model",
}

_MIN_SUCCESS_PROB = 1e-4
_MIN_DURATION_YEARS = 0.25
_MIN_COST_MILLIONS = 0.01
_MIN_POSITIVE = 1e-6


class ScenarioSnapshot(BaseModel):
    """Compact valuation snapshot for before/after comparisons."""

    rnpv_millions: float
    nav_millions: float
    nav_per_share: float
    approval_probability: float
    mc_mean_millions: float
    bull_rnpv_millions: float
    base_rnpv_millions: float
    bear_rnpv_millions: float


class AssumptionFieldChange(BaseModel):
    """Field-level assumption change used in valuation diffs."""

    field: str
    old_value: float
    new_value: float
    delta: float
    delta_pct: Optional[float] = None


class ValuationDiffLog(BaseModel):
    """Auditable, field-level before/after valuation diff."""

    run_id: str
    asset_id: str
    event_id: str
    generated_at: datetime
    assumptions_changed: list[AssumptionFieldChange] = Field(default_factory=list)
    valuation_before: ScenarioSnapshot
    valuation_after: ScenarioSnapshot
    delta_npv: float
    delta_nav_per_share: float
    delta_mc_mean_millions: float
    delta_bull_rnpv_millions: float
    delta_base_rnpv_millions: float
    delta_bear_rnpv_millions: float
    applied_overrides: dict[str, float] = Field(default_factory=dict)


class ValuationRunRecord(BaseModel):
    """Returned artifact from one applied proposal batch."""

    run: ValuationRun
    before_path: str
    after_path: str
    diff_path: str
    manifest_path: str
    diff: ValuationDiffLog


class RollbackResult(BaseModel):
    """Result of rolling back the latest applied run."""

    rolled_back_run_id: str
    restored_rnpv_millions: float
    restored_nav_per_share: float
    restored_snapshot: ScenarioSnapshot
    remaining_run_ids: list[str] = Field(default_factory=list)
    rolled_back_at: datetime


@dataclass
class _HistoryEntry:
    run_id: str
    pre_asset: Asset
    pre_trials: list[ClinicalTrial]
    pre_market_model: MarketModel


class ValuationSession:
    """
    Stateful Phase 2 valuation session with audit logging and rollback.

    Notes
    -----
    - Uses existing ``ValuationEngine`` as-is (no formula changes).
    - Applies only scalar overrides.
    - Writes before/after/diff artifacts to disk per run.
    """

    def __init__(
        self,
        *,
        asset: Asset,
        company: Company,
        trials: list[ClinicalTrial],
        market_model: MarketModel,
        output_dir: str | Path = "outputs/intelligence_phase2",
        mc_params: Optional[MonteCarloParams] = None,
    ) -> None:
        self._asset = asset
        self._company = company
        self._trials = [t.model_copy() for t in trials]
        self._market_model = market_model
        self._output_dir = Path(output_dir)
        self._mc_params = mc_params or MonteCarloParams(random_seed=42)
        self._history: list[_HistoryEntry] = []
        self._run_records: dict[str, ValuationRunRecord] = {}
        self._run_order: list[str] = []

    @property
    def run_history(self) -> list[ValuationRunRecord]:
        return [self._run_records[rid] for rid in self._run_order if rid in self._run_records]

    def current_output(self) -> ValuationOutput:
        """Run valuation on the current in-session state."""
        return self._run_engine(self._asset, self._trials, self._market_model)

    def apply_proposals(
        self,
        *,
        proposals: list[AssumptionChangeProposal],
        effective_values: dict[str, float],
        signals_by_id: dict[str, StructuredSignal],
        analyst_id: Optional[str] = None,
        notes: Optional[str] = None,
        run_at: Optional[datetime] = None,
    ) -> ValuationRunRecord:
        """
        Apply effective overrides and execute a before/after valuation run.

        ``effective_values`` should be resolved by review logic:
          proposal_id -> value_to_apply.
        """
        run_at = run_at or datetime.now(timezone.utc)
        by_id = {p.id: p for p in proposals}
        selected: list[tuple[AssumptionChangeProposal, float]] = []
        for proposal_id in sorted(effective_values):
            value = effective_values[proposal_id]
            proposal = by_id.get(proposal_id)
            if proposal is not None:
                selected.append((proposal, value))

        if not selected:
            raise ValueError("No effective proposals to apply")

        # Snapshot current state for rollback.
        run_id = str(uuid.uuid4())
        self._history.append(
            _HistoryEntry(
                run_id=run_id,
                pre_asset=self._asset.model_copy(),
                pre_trials=[t.model_copy() for t in self._trials],
                pre_market_model=self._market_model.model_copy(),
            )
        )

        before_output = self._run_engine(self._asset, self._trials, self._market_model)
        updated_asset = self._asset
        updated_trials = [t.model_copy() for t in self._trials]
        updated_market = self._market_model

        applied_overrides: dict[str, float] = {}
        assumption_changes: list[AssumptionFieldChange] = []
        for proposal, effective_value in selected:
            signal = signals_by_id.get(proposal.signal_id)
            updated_asset, updated_trials, updated_market, resolved_path, old_value, applied_value = self._apply_override(
                proposal=proposal,
                value=effective_value,
                signal=signal,
                asset=updated_asset,
                trials=updated_trials,
                market_model=updated_market,
            )
            applied_overrides[resolved_path] = float(applied_value)
            denom = abs(old_value)
            delta = float(applied_value - old_value)
            delta_pct = (delta / denom * 100.0) if denom > 0 else None
            assumption_changes.append(
                AssumptionFieldChange(
                    field=resolved_path,
                    old_value=float(old_value),
                    new_value=float(applied_value),
                    delta=round(delta, 8),
                    delta_pct=round(delta_pct, 6) if delta_pct is not None else None,
                )
            )

        after_output = self._run_engine(updated_asset, updated_trials, updated_market)
        first_signal = signals_by_id.get(selected[0][0].signal_id)
        event_id = first_signal.event_id if first_signal is not None else selected[0][0].signal_id
        diff = self._build_diff(
            run_id=run_id,
            asset_id=self._asset.id,
            event_id=event_id,
            before=before_output,
            after=after_output,
            applied_overrides=applied_overrides,
            assumptions_changed=assumption_changes,
            generated_at=run_at,
        )

        run_dir = self._output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        before_path = before_output.save_json(run_dir / "before_valuation.json")
        after_path = after_output.save_json(run_dir / "after_valuation.json")
        diff_path = run_dir / "valuation_diff.json"
        diff_path.write_text(diff.model_dump_json(indent=2), encoding="utf-8")

        run = ValuationRun(
            id=run_id,
            engine_asset_id=self._asset.id,
            triggered_by_signal_id=selected[0][0].signal_id,
            triggered_by_proposal_ids=[p.id for p, _ in selected],
            parameter_overrides=applied_overrides,
            valuation_output_json_path=str(after_path),
            rnpv_millions_before=before_output.rnpv.rnpv_millions,
            rnpv_millions_after=after_output.rnpv.rnpv_millions,
            run_at=run_at,
            analyst_id=analyst_id,
            notes=notes,
            status="completed",
        )

        # Commit state.
        self._asset = updated_asset
        self._trials = updated_trials
        self._market_model = updated_market

        manifest_path = run_dir / "run_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_at": run_at.isoformat(),
                    "asset_id": self._asset.id,
                    "engine_asset_id": self._asset.id,
                    "triggered_by_signal_id": selected[0][0].signal_id,
                    "triggered_by_proposal_ids": [p.id for p, _ in selected],
                    "assumptions_snapshot": {
                        "applied_overrides": applied_overrides,
                        "changes": [c.model_dump(mode="json") for c in assumption_changes],
                    },
                    "valuation_outputs": {
                        "before_path": str(before_path),
                        "after_path": str(after_path),
                        "diff_path": str(diff_path),
                    },
                    "valuation_summary": {
                        "rnpv_before": before_output.rnpv.rnpv_millions,
                        "rnpv_after": after_output.rnpv.rnpv_millions,
                        "delta_npv": diff.delta_npv,
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        record = ValuationRunRecord(
            run=run,
            before_path=str(before_path),
            after_path=str(after_path),
            diff_path=str(diff_path),
            manifest_path=str(manifest_path),
            diff=diff,
        )
        self._run_records[run_id] = record
        self._run_order.append(run_id)
        return record

    def rollback_last(self) -> RollbackResult:
        """Revert the session to the state before the most recent applied run."""
        if not self._history:
            raise ValueError("No prior run to roll back")

        entry = self._history.pop()
        self._asset = entry.pre_asset
        self._trials = [t.model_copy() for t in entry.pre_trials]
        self._market_model = entry.pre_market_model

        restored = self._run_engine(self._asset, self._trials, self._market_model)
        if entry.run_id in self._run_records:
            del self._run_records[entry.run_id]
        if self._run_order and self._run_order[-1] == entry.run_id:
            self._run_order.pop()
        else:
            self._run_order = [rid for rid in self._run_order if rid != entry.run_id]
        rolled_back_at = datetime.now(timezone.utc)

        marker_path = self._output_dir / entry.run_id / "rollback.json"
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(
            json.dumps(
                {
                    "rolled_back_run_id": entry.run_id,
                    "rolled_back_at": rolled_back_at.isoformat(),
                    "restored_rnpv_millions": restored.rnpv.rnpv_millions,
                    "restored_nav_per_share": restored.nav_per_share,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        return RollbackResult(
            rolled_back_run_id=entry.run_id,
            restored_rnpv_millions=restored.rnpv.rnpv_millions,
            restored_nav_per_share=restored.nav_per_share,
            restored_snapshot=self._snapshot(restored),
            remaining_run_ids=list(self._run_order),
            rolled_back_at=rolled_back_at,
        )

    def _run_engine(
        self,
        asset: Asset,
        trials: list[ClinicalTrial],
        market_model: MarketModel,
    ) -> ValuationOutput:
        engine = ValuationEngine(
            asset=asset,
            company=self._company,
            trials=trials,
            market_model=market_model,
            mc_params=self._mc_params,
        )
        return engine.run()

    @staticmethod
    def _snapshot(output: ValuationOutput) -> ScenarioSnapshot:
        return ScenarioSnapshot(
            rnpv_millions=output.rnpv.rnpv_millions,
            nav_millions=output.nav_millions,
            nav_per_share=output.nav_per_share,
            approval_probability=output.rnpv.cumulative_success_probability,
            mc_mean_millions=output.monte_carlo.mean_millions,
            bull_rnpv_millions=output.scenarios.bull.rnpv_millions,
            base_rnpv_millions=output.scenarios.base.rnpv_millions,
            bear_rnpv_millions=output.scenarios.bear.rnpv_millions,
        )

    def _build_diff(
        self,
        *,
        run_id: str,
        asset_id: str,
        event_id: str,
        before: ValuationOutput,
        after: ValuationOutput,
        applied_overrides: dict[str, float],
        assumptions_changed: list[AssumptionFieldChange],
        generated_at: datetime,
    ) -> ValuationDiffLog:
        before_s = self._snapshot(before)
        after_s = self._snapshot(after)
        return ValuationDiffLog(
            run_id=run_id,
            asset_id=asset_id,
            event_id=event_id,
            generated_at=generated_at,
            assumptions_changed=assumptions_changed,
            valuation_before=before_s,
            valuation_after=after_s,
            delta_npv=round(after_s.rnpv_millions - before_s.rnpv_millions, 2),
            delta_nav_per_share=round(after_s.nav_per_share - before_s.nav_per_share, 4),
            delta_mc_mean_millions=round(after_s.mc_mean_millions - before_s.mc_mean_millions, 2),
            delta_bull_rnpv_millions=round(
                after_s.bull_rnpv_millions - before_s.bull_rnpv_millions, 2
            ),
            delta_base_rnpv_millions=round(
                after_s.base_rnpv_millions - before_s.base_rnpv_millions, 2
            ),
            delta_bear_rnpv_millions=round(
                after_s.bear_rnpv_millions - before_s.bear_rnpv_millions, 2
            ),
            applied_overrides=applied_overrides,
        )

    @staticmethod
    def _apply_override(
        *,
        proposal: AssumptionChangeProposal,
        value: float,
        signal: Optional[StructuredSignal],
        asset: Asset,
        trials: list[ClinicalTrial],
        market_model: MarketModel,
    ) -> tuple[Asset, list[ClinicalTrial], MarketModel, str, float, float]:
        parameter = proposal.parameter_path

        if parameter in _NON_SCALAR_PARAMETERS:
            raise ValueError(
                f"Cannot auto-apply non-scalar parameter {parameter!r}; manual YAML update required"
            )

        if parameter == "asset.discount_rate":
            old = float(asset.discount_rate)
            applied = min(0.50, max(0.01, float(value)))
            return asset.model_copy(update={"discount_rate": applied}), trials, market_model, parameter, old, applied

        if parameter.startswith("market_model."):
            field_name = parameter.split(".", 1)[1]
            updates: dict[str, object] = {}
            raw_old = getattr(market_model, field_name)
            if raw_old is None:
                raise ValueError(
                    f"Current value for market_model field {field_name!r} is None; cannot apply scalar override"
                )
            old = float(raw_old)

            if field_name == "addressable_patients_annual":
                updates[field_name] = max(1, int(round(value)))
            elif field_name == "total_addressable_market_millions":
                updates[field_name] = max(_MIN_POSITIVE, float(value))
            elif field_name == "net_price_per_patient_usd":
                updates[field_name] = max(_MIN_POSITIVE, float(value))
            elif field_name == "peak_penetration":
                updates[field_name] = min(0.99, max(0.01, float(value)))
            elif field_name == "patent_life_years":
                updates[field_name] = max(1, int(round(value)))
            else:
                raise ValueError(f"Unsupported market_model override field: {field_name!r}")

            # Force uptake curve rebuild when core commercial inputs move.
            updates["uptake_curve"] = None
            applied = float(updates[field_name])
            return asset, trials, market_model.model_copy(update=updates), parameter, old, applied

        if parameter.startswith("trials[*]."):
            if signal is None or signal.trial_phase is None:
                raise ValueError(
                    f"Signal with trial_phase is required to apply trial wildcard path {parameter!r}"
                )

            field_name = parameter.split(".", 1)[1]
            resolved = f"trials[{signal.trial_phase.value}].{field_name}"

            updated_trials: list[ClinicalTrial] = []
            matched = False
            old: Optional[float] = None
            applied: Optional[float] = None
            for trial in trials:
                if trial.phase != signal.trial_phase:
                    updated_trials.append(trial)
                    continue

                matched = True
                old = float(getattr(trial, field_name))
                if field_name == "success_probability":
                    applied = min(0.99, max(_MIN_SUCCESS_PROB, float(value)))
                elif field_name == "duration_years":
                    applied = max(_MIN_DURATION_YEARS, float(value))
                elif field_name == "cost_millions":
                    applied = max(_MIN_COST_MILLIONS, float(value))
                else:
                    raise ValueError(f"Unsupported trial field override: {field_name!r}")

                updated_trials.append(trial.model_copy(update={field_name: applied}))

            if not matched:
                raise ValueError(
                    f"No trial found for phase={signal.trial_phase.value!r} while applying {parameter!r}"
                )
            assert old is not None
            assert applied is not None
            return asset, updated_trials, market_model, resolved, old, float(applied)

        raise ValueError(f"Unsupported override parameter path: {parameter!r}")
