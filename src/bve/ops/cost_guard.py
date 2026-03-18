"""Hard daily LLM cost guard for continuously running extraction pipelines."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DailyLLMCostState(BaseModel):
    """Persisted UTC-day cost state."""

    utc_date: date
    total_cost_usd: float = Field(default=0.0, ge=0.0)
    updated_at: datetime = Field(default_factory=_utcnow)


class CostGuard:
    """Persists and enforces a daily UTC-denominated LLM cost budget."""

    def __init__(
        self,
        *,
        state_path: str | Path = "outputs/watchlist/daily_llm_cost.json",
        daily_limit_usd: float = 2.50,
        now_fn: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.state_path = Path(state_path)
        self.daily_limit_usd = max(0.0, float(daily_limit_usd))
        self._now_fn = now_fn
        self._cap_reached_on_last_record = False

    def allow_llm_call(self) -> bool:
        """Return True while the current UTC-day spend remains below the cap."""
        state = self._load_state()
        return state.total_cost_usd < self.daily_limit_usd

    def record_llm_cost(self, estimated_cost: float) -> None:
        """Add one estimated request cost to the current UTC-day total."""
        increment = float(estimated_cost)
        if not math.isfinite(increment) or increment <= 0.0:
            self._cap_reached_on_last_record = False
            return

        state = self._load_state()
        prior_total = state.total_cost_usd
        state.total_cost_usd = round(prior_total + increment, 6)
        state.updated_at = self._coerce_datetime(self._now_fn())
        self._write_state(state)
        self._cap_reached_on_last_record = (
            prior_total < self.daily_limit_usd <= state.total_cost_usd
        )

    @property
    def current_total_usd(self) -> float:
        return self._load_state().total_cost_usd

    @property
    def current_utc_date(self) -> date:
        return self._load_state().utc_date

    @property
    def cap_reached(self) -> bool:
        return self.current_total_usd >= self.daily_limit_usd

    @property
    def cap_reached_on_last_record(self) -> bool:
        return self._cap_reached_on_last_record

    def _load_state(self) -> DailyLLMCostState:
        state = self._read_state()
        today = self._coerce_datetime(self._now_fn()).date()
        if state.utc_date != today:
            state = DailyLLMCostState(utc_date=today)
            self._write_state(state)
        return state

    def _read_state(self) -> DailyLLMCostState:
        today = self._coerce_datetime(self._now_fn()).date()
        if not self.state_path.exists():
            return DailyLLMCostState(utc_date=today)

        try:
            payload: Any = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return DailyLLMCostState(utc_date=today)

        if not isinstance(payload, dict):
            return DailyLLMCostState(utc_date=today)

        try:
            return DailyLLMCostState.model_validate(payload)
        except Exception:
            return DailyLLMCostState(utc_date=today)

    def _write_state(self, state: DailyLLMCostState) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(state.model_dump(mode="json"), ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self.state_path)

    @staticmethod
    def _coerce_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
