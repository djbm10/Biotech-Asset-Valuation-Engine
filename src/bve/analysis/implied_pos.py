"""
Market-implied PoS back-solver for YAML valuation configs.

Usage
-----
    python -m bve.analysis.implied_pos \
        --config examples/configs/relay_rly2608.yaml \
        --ev 500
"""
from __future__ import annotations

import argparse
import contextlib
import io
import math
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from bve.cli.run_asset import (
    _build_design_adjusters,
    _build_objects,
    _build_pos_adjusters,
    _load_config,
    _validate_config,
)
from bve.entities.trial import ClinicalTrial
from bve.models.monte_carlo import MonteCarloParams
from bve.valuation.outputs import ValuationOutput
from bve.valuation.valuation_engine import ValuationEngine

_PHASE_PROB_FLOOR = 1e-6
_PHASE_PROB_CEILING = 1.0 - 1e-6


class ImpliedPoSResult(BaseModel, frozen=True):
    asset_id: str
    ticker: str
    current_ev_millions: float
    implied_pos: float = Field(ge=0.0, le=1.0)
    model_pos: float = Field(ge=0.0, le=1.0)
    pos_spread: float
    model_rnpv_millions: float
    implied_rnpv_millions: float
    acquisition_discount: float
    market_exceeds_model: bool = False
    iterations: int = Field(default=0, ge=0)


@dataclass
class _SolverContext:
    engine: ValuationEngine
    base_output: ValuationOutput
    base_trials: list[ClinicalTrial]


class ImpliedPoSSolver:
    def __init__(
        self,
        *,
        min_pos: float = 0.01,
        max_pos: float = 0.99,
        tolerance_millions: float = 1.0,
        tolerance_pct: float = 0.005,
        max_iterations: int = 50,
        mc_simulations: int = 1,
        random_seed: int = 42,
    ) -> None:
        self.min_pos = float(min_pos)
        self.max_pos = float(max_pos)
        self.tolerance_millions = float(tolerance_millions)
        self.tolerance_pct = float(tolerance_pct)
        self.max_iterations = int(max_iterations)
        self.mc_simulations = int(mc_simulations)
        self.random_seed = int(random_seed)

    def solve(
        self,
        config_path: str,
        current_ev_millions: float,
    ) -> Optional[ImpliedPoSResult]:
        """
        Binary search for the PoS that makes rNPV approximately equal to EV.
        """
        if current_ev_millions <= 0:
            return None

        context = self._build_context(config_path)
        if context is None:
            return None

        tolerance = self._tolerance_for_ev(current_ev_millions)

        if not context.base_trials:
            return self._solve_no_remaining_trials(
                context.base_output,
                current_ev_millions=current_ev_millions,
                tolerance=tolerance,
            )

        lo_pos = self.min_pos
        hi_pos = self.max_pos
        lo_actual_pos, lo_rnpv = self._value_at_target_pos(context, lo_pos)
        hi_actual_pos, hi_rnpv = self._value_at_target_pos(context, hi_pos)

        best_pos = lo_actual_pos
        best_rnpv = lo_rnpv
        best_error = abs(lo_rnpv - current_ev_millions)

        if abs(hi_rnpv - current_ev_millions) < best_error:
            best_pos = hi_actual_pos
            best_rnpv = hi_rnpv
            best_error = abs(hi_rnpv - current_ev_millions)

        if hi_rnpv < current_ev_millions - tolerance:
            return self._build_result(
                context.base_output,
                current_ev_millions=current_ev_millions,
                implied_pos=hi_actual_pos,
                implied_rnpv_millions=hi_rnpv,
                iterations=0,
                market_exceeds_model=True,
            )

        if lo_rnpv > current_ev_millions + tolerance:
            return self._build_result(
                context.base_output,
                current_ev_millions=current_ev_millions,
                implied_pos=lo_actual_pos,
                implied_rnpv_millions=lo_rnpv,
                iterations=0,
                market_exceeds_model=False,
            )

        iterations = 0
        for iterations in range(1, self.max_iterations + 1):
            mid_pos = (lo_pos + hi_pos) / 2.0
            actual_pos, mid_rnpv = self._value_at_target_pos(context, mid_pos)
            error = abs(mid_rnpv - current_ev_millions)

            if error < best_error:
                best_pos = actual_pos
                best_rnpv = mid_rnpv
                best_error = error

            if error <= tolerance:
                best_pos = actual_pos
                best_rnpv = mid_rnpv
                break

            if mid_rnpv > current_ev_millions:
                hi_pos = mid_pos
            else:
                lo_pos = mid_pos

        return self._build_result(
            context.base_output,
            current_ev_millions=current_ev_millions,
            implied_pos=best_pos,
            implied_rnpv_millions=best_rnpv,
            iterations=iterations,
            market_exceeds_model=False,
        )

    def _build_context(self, config_path: str | Path) -> Optional[_SolverContext]:
        path = Path(config_path)
        engine = self._load_engine(path)
        if engine is None:
            return None

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                base_output = engine.run()
        except Exception:  # noqa: BLE001
            return None

        base_trials = [trial.model_copy() for trial in base_output.trials]

        # Search should operate on the engine's prepared phase PoS, not re-run the
        # PoS/design layers from YAML on every iteration.
        engine.trials = [trial.model_copy() for trial in base_trials]
        engine.apply_pos_model = False
        engine.apply_design_model = False
        engine._compute_sensitivities = lambda *args, **kwargs: []  # type: ignore[method-assign]

        return _SolverContext(
            engine=engine,
            base_output=base_output,
            base_trials=base_trials,
        )

    def _load_engine(self, config_path: Path) -> Optional[ValuationEngine]:
        if not config_path.exists():
            return None

        try:
            cfg = _load_config(config_path)
            with contextlib.redirect_stderr(io.StringIO()):
                _validate_config(cfg, config_path)

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                asset, company, trials, market_model = _build_objects(cfg)
            pos_adjusters, apply_pos = _build_pos_adjusters(cfg)
            design_adjusters, apply_design = _build_design_adjusters(cfg)
        except (SystemExit, KeyError, TypeError, ValueError):  # malformed config
            return None
        except Exception:  # noqa: BLE001
            return None

        engine = ValuationEngine(
            asset,
            company,
            trials,
            market_model,
            pos_adjusters=pos_adjusters,
            design_adjusters=design_adjusters,
            mc_params=MonteCarloParams(
                n_simulations=self.mc_simulations,
                random_seed=self.random_seed,
            ),
            apply_pos_model=apply_pos,
            apply_design_model=apply_design,
            analyst_notes=cfg.get("analyst_notes"),
            config_path=str(config_path.resolve()),
            limitations=cfg.get("limitations"),
            thesis_changers=cfg.get("thesis_changers"),
        )
        engine.sources = cfg.get("sources")
        return engine

    def _solve_no_remaining_trials(
        self,
        base_output: ValuationOutput,
        *,
        current_ev_millions: float,
        tolerance: float,
    ) -> Optional[ImpliedPoSResult]:
        gross_pv = float(base_output.rnpv.gross_revenue_pv_millions)
        if gross_pv <= 0:
            return None

        max_rnpv = gross_pv * self.max_pos
        if max_rnpv < current_ev_millions - tolerance:
            return self._build_result(
                base_output,
                current_ev_millions=current_ev_millions,
                implied_pos=self.max_pos,
                implied_rnpv_millions=max_rnpv,
                iterations=0,
                market_exceeds_model=True,
            )

        implied_pos = max(self.min_pos, min(self.max_pos, current_ev_millions / gross_pv))
        implied_rnpv = gross_pv * implied_pos
        return self._build_result(
            base_output,
            current_ev_millions=current_ev_millions,
            implied_pos=implied_pos,
            implied_rnpv_millions=implied_rnpv,
            iterations=0,
            market_exceeds_model=False,
        )

    def _value_at_target_pos(
        self,
        context: _SolverContext,
        target_pos: float,
    ) -> tuple[float, float]:
        scaled_trials = self._scale_trials_to_target_pos(context.base_trials, target_pos)
        context.engine.trials = scaled_trials
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            output = context.engine.run()
        actual_pos = float(output.rnpv.cumulative_success_probability)
        rnpv = float(output.rnpv.rnpv_millions)
        return actual_pos, rnpv

    def _scale_trials_to_target_pos(
        self,
        base_trials: list[ClinicalTrial],
        target_pos: float,
    ) -> list[ClinicalTrial]:
        if not base_trials:
            return []

        base_probs = [float(trial.success_probability) for trial in base_trials]
        scale = self._solve_scale_factor(base_probs, target_pos)

        return [
            trial.model_copy(
                update={
                    "success_probability": self._clamp_phase_probability(
                        float(trial.success_probability) * scale
                    )
                }
            )
            for trial in base_trials
        ]

    def _solve_scale_factor(self, base_probs: list[float], target_pos: float) -> float:
        low = 0.0
        high = 1.0

        while self._compound_probability(base_probs, high) < target_pos:
            high *= 2.0
            if high > 1e6:
                break

        for _ in range(80):
            mid = (low + high) / 2.0
            compound = self._compound_probability(base_probs, mid)
            if abs(compound - target_pos) <= 1e-8:
                return mid
            if compound < target_pos:
                low = mid
            else:
                high = mid

        return (low + high) / 2.0

    def _compound_probability(self, base_probs: list[float], scale: float) -> float:
        return math.prod(
            self._clamp_phase_probability(prob * scale)
            for prob in base_probs
        )

    @staticmethod
    def _clamp_phase_probability(value: float) -> float:
        return max(_PHASE_PROB_FLOOR, min(_PHASE_PROB_CEILING, float(value)))

    def _tolerance_for_ev(self, current_ev_millions: float) -> float:
        return max(self.tolerance_millions, abs(current_ev_millions) * self.tolerance_pct)

    def _build_result(
        self,
        base_output: ValuationOutput,
        *,
        current_ev_millions: float,
        implied_pos: float,
        implied_rnpv_millions: float,
        iterations: int,
        market_exceeds_model: bool,
    ) -> ImpliedPoSResult:
        model_pos = float(base_output.rnpv.cumulative_success_probability)
        model_rnpv = float(base_output.rnpv.rnpv_millions)
        ticker = base_output.company.ticker or base_output.asset.id.upper()
        return ImpliedPoSResult(
            asset_id=base_output.asset.id,
            ticker=ticker,
            current_ev_millions=float(current_ev_millions),
            implied_pos=round(float(implied_pos), 6),
            model_pos=round(model_pos, 6),
            pos_spread=round(model_pos - float(implied_pos), 6),
            model_rnpv_millions=round(model_rnpv, 6),
            implied_rnpv_millions=round(float(implied_rnpv_millions), 6),
            acquisition_discount=round(model_rnpv / float(current_ev_millions), 6),
            market_exceeds_model=market_exceeds_model,
            iterations=iterations,
        )


def _format_pos(pos: float) -> str:
    return f"{pos * 100:.1f}%"


def _format_millions(value: float) -> str:
    if value == round(value):
        return f"${value:,.0f}M"
    return f"${value:,.1f}M"


def _format_spread(pos_spread: float) -> str:
    sign = "+" if pos_spread >= 0 else ""
    return f"{sign}{pos_spread * 100:.1f}pp"


def _direction_label(pos_spread: float) -> str:
    if pos_spread > 0:
        return "model higher -> undervalued"
    if pos_spread < 0:
        return "model lower -> overvalued"
    return "model aligned with market"


def _asset_label(config_path: str, fallback: str) -> str:
    try:
        cfg = _load_config(Path(config_path))
    except Exception:  # noqa: BLE001
        return fallback
    asset = cfg.get("asset", {})
    return str(asset.get("name") or asset.get("id") or fallback)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Solve market-implied PoS from a YAML valuation config")
    parser.add_argument("--config", required=True, help="Path to asset YAML config")
    parser.add_argument("--ev", required=True, type=float, help="Current enterprise value in $M")
    args = parser.parse_args(argv)

    solver = ImpliedPoSSolver()
    result = solver.solve(args.config, args.ev)
    if result is None:
        print("Unable to compute implied PoS.", file=sys.stderr)
        return 1

    asset_label = _asset_label(args.config, result.asset_id)
    print(f"Asset: {asset_label}")
    print(f"Current EV:      {_format_millions(result.current_ev_millions)}")
    print(f"Model PoS:       {_format_pos(result.model_pos)}")
    print(f"Implied PoS:     {_format_pos(result.implied_pos)}")
    print(
        f"PoS Spread:      {_format_spread(result.pos_spread)} "
        f"({ _direction_label(result.pos_spread) })"
    )
    print(f"Model rNPV:      {_format_millions(result.model_rnpv_millions)}")
    print(f"Acq. Discount:   {result.acquisition_discount:.2f}x")
    if result.market_exceeds_model:
        print("Note: market EV exceeds the model's value even at 99% PoS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
