from __future__ import annotations

import json
from datetime import datetime, timezone

from bve.ops.cost_guard import CostGuard


def test_cost_guard_blocks_calls_after_daily_limit(tmp_path):
    now = {"value": datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc)}
    guard = CostGuard(
        state_path=tmp_path / "daily_llm_cost.json",
        daily_limit_usd=0.50,
        now_fn=lambda: now["value"],
    )

    assert guard.allow_llm_call() is True

    guard.record_llm_cost(0.35)
    assert guard.allow_llm_call() is True

    guard.record_llm_cost(0.20)
    assert guard.cap_reached_on_last_record is True
    assert guard.allow_llm_call() is False


def test_cost_guard_resets_at_next_utc_day(tmp_path):
    now = {"value": datetime(2026, 3, 11, 23, 59, tzinfo=timezone.utc)}
    state_path = tmp_path / "daily_llm_cost.json"
    guard = CostGuard(
        state_path=state_path,
        daily_limit_usd=2.50,
        now_fn=lambda: now["value"],
    )

    guard.record_llm_cost(1.25)
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["utc_date"] == "2026-03-11"
    assert payload["total_cost_usd"] == 1.25

    now["value"] = datetime(2026, 3, 12, 0, 1, tzinfo=timezone.utc)
    assert guard.allow_llm_call() is True

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["utc_date"] == "2026-03-12"
    assert payload["total_cost_usd"] == 0.0
