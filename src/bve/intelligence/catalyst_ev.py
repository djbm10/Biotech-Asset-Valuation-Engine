"""
Wave 1 Part D — Catalyst EV Calculator.

For each active CatalystEvent with a linked asset_id, computes:

    value_if_success  = rNPV with all trial success_probabilities forced to 1.0
    value_if_failure  = rNPV with all trial success_probabilities forced to 0.0

    upside   = value_if_success − current_value
    downside = current_value − value_if_failure

    delta_ev = pos × upside − (1 − pos) × downside

    # Variance around the EV (corrected Sharpe-like formula)
    outcome_success = upside
    outcome_failure = −downside
    ev = delta_ev
    variance = pos × (outcome_success − ev)² + (1 − pos) × (outcome_failure − ev)²
    std_dev = sqrt(variance)

    # Signal strength with floor guard
    std_floor = max(std_dev, abs(ev) × std_floor_multiplier)
    signal_strength = ev / std_floor  if std_floor > 0  else 0.0

    asymmetry_ratio = upside / downside  if downside > 0  else inf

No new network calls — uses pre-fetched YAML config + KnowledgeStore.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bve.intelligence.catalyst_calendar import CatalystEvent

# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------

_CONFIG_DEFAULTS: dict = {
    "readout_lag_days_min":              120,
    "readout_lag_days_max":              270,
    "readout_lag_days_default":          180,
    "min_displayable_signal_strength":   0.03,
    "std_floor_multiplier":              0.50,
}


class CatalystEVCalculator:
    """
    Compute EV metrics for a CatalystEvent by running two scenario valuations.

    Parameters
    ----------
    config:
        Override dict for ``catalyst_calendar`` thresholds.  When ``None``,
        loaded from ``industry_assumptions.yaml`` with ``_CONFIG_DEFAULTS``
        as fallback.
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        self._cfg = config if config is not None else self._load_config()

    @staticmethod
    def _load_config() -> dict:
        try:
            from bve.config.assumptions_loader import AssumptionsLoader
            from bve.intelligence.trial_design_feature_extractor import _unfreeze
            data = AssumptionsLoader.get()._data
            section = data.get("catalyst_calendar")
            if section:
                return _unfreeze(section)
        except Exception:
            pass
        return dict(_CONFIG_DEFAULTS)

    def compute(
        self,
        catalyst: CatalystEvent,
        asset_config_path: str,
        knowledge_store=None,
    ) -> CatalystEvent:
        """
        Compute EV fields for *catalyst* using the asset YAML at *asset_config_path*.

        Parameters
        ----------
        catalyst:
            The CatalystEvent to enrich with EV metrics.
        asset_config_path:
            Path to the asset YAML config (e.g. ``examples/configs/relay_rly2608.yaml``).
        knowledge_store:
            Optional KnowledgeStore — when supplied the updated event is
            immediately upserted.

        Returns
        -------
        Updated (non-frozen copy) CatalystEvent with EV fields populated.
        """
        cfg = self._cfg
        std_floor_mult = float(cfg.get("std_floor_multiplier", 0.50))

        try:
            result = self._run_scenarios(asset_config_path)
        except Exception:
            return catalyst

        current_value, value_if_success, value_if_failure, current_pos = result

        upside   = value_if_success - current_value
        downside = current_value - value_if_failure

        delta_ev = current_pos * upside - (1.0 - current_pos) * downside

        # Variance / std_dev
        outcome_success = upside
        outcome_failure = -downside
        ev = delta_ev
        variance = (
            current_pos * (outcome_success - ev) ** 2
            + (1.0 - current_pos) * (outcome_failure - ev) ** 2
        )
        std_dev = math.sqrt(max(variance, 0.0))

        std_floor = max(std_dev, abs(ev) * std_floor_mult)
        signal_strength = (ev / std_floor) if std_floor > 0.0 else 0.0

        asymmetry_ratio = (
            upside / downside if downside > 0.0 else float("inf")
        )

        updated = catalyst.model_copy(update={
            "current_pos":      current_pos,
            "value_if_success": round(value_if_success, 2),
            "value_if_failure": round(value_if_failure, 2),
            "current_value":    round(current_value, 2),
            "delta_ev":         round(delta_ev, 2),
            "upside":           round(upside, 2),
            "downside":         round(downside, 2),
            "std_dev":          round(std_dev, 4),
            "signal_strength":  round(signal_strength, 4),
            "asymmetry_ratio":  (
                round(asymmetry_ratio, 4)
                if math.isfinite(asymmetry_ratio)
                else asymmetry_ratio
            ),
            "updated_at": datetime.now(timezone.utc),
        })

        if knowledge_store is not None:
            knowledge_store.upsert_catalyst_event(updated)

        return updated

    # ------------------------------------------------------------------
    # Internal: load config and run three scenario valuations
    # ------------------------------------------------------------------

    @staticmethod
    def _run_scenarios(
        asset_config_path: str,
    ) -> tuple[float, float, float, float]:
        """
        Return (current_value, value_if_success, value_if_failure, current_pos).

        Loads the YAML config, builds engine objects, and runs:
          - baseline  → current_value, current_pos
          - success   → all trial success_probability = 1.0
          - failure   → all trial success_probability = 0.0
        """
        from bve.cli.run_asset import _build_objects, _load_config
        from bve.models.rnpv_model import compute_rnpv_full

        path = Path(asset_config_path)
        cfg = _load_config(path)
        asset, company, trials, market_model = _build_objects(cfg)

        # Baseline
        base_result = compute_rnpv_full(asset, trials, market_model)
        current_value = float(base_result.rnpv_millions)
        current_pos   = float(base_result.cumulative_success_probability)

        # Success scenario: force all trial PoS = 1.0
        success_trials = [
            t.model_copy(update={"success_probability": 1.0})
            for t in trials
        ]
        success_result = compute_rnpv_full(asset, success_trials, market_model)
        value_if_success = float(success_result.rnpv_millions)

        # Failure scenario: force all trial PoS = 0.0
        failure_trials = [
            t.model_copy(update={"success_probability": 0.0})
            for t in trials
        ]
        failure_result = compute_rnpv_full(asset, failure_trials, market_model)
        value_if_failure = float(failure_result.rnpv_millions)

        return current_value, value_if_success, value_if_failure, current_pos
