"""Run observability — metrics and reporting for production runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class RunObservation:
    """Snapshot of all observability metrics for a completed run."""

    run_id: str
    duration_seconds: float | None
    asset_count: int
    failed_count: int
    stale_warning_count: int
    source_failure_count: int
    model_error_count: int
    assumption_override_count: int
    score_delta_mean: float | None
    score_delta_max: float | None
    completed_at: datetime | None = None
    environment: str = "development"


class RunObserver:
    """Collects and reports observability metrics from a RunContext."""

    def observe(self, ctx: "RunContext") -> RunObservation:  # noqa: F821
        obs = ctx.to_observation_dict()
        score_deltas = list(obs.get("score_deltas", {}).values())
        return RunObservation(
            run_id=obs["run_id"],
            duration_seconds=obs.get("duration_seconds"),
            asset_count=len(obs.get("score_deltas", {})),
            failed_count=len(obs.get("failed_assets", [])),
            stale_warning_count=len(obs.get("stale_data_warnings", [])),
            source_failure_count=0,
            model_error_count=0,
            assumption_override_count=0,
            score_delta_mean=sum(score_deltas) / len(score_deltas) if score_deltas else None,
            score_delta_max=max(abs(d) for d in score_deltas) if score_deltas else None,
            completed_at=datetime.fromisoformat(obs["completed_at"]) if obs.get("completed_at") else None,
            environment=obs.get("runtime_environment", "development"),
        )

    def format_summary(self, obs: RunObservation) -> str:
        lines = [f"Run {obs.run_id} | {obs.environment}"]
        duration = f"{obs.duration_seconds:.1f}s" if obs.duration_seconds else "n/a"
        lines.append(f"  Duration: {duration}")
        lines.append(f"  Assets: {obs.asset_count} | Failed: {obs.failed_count}")
        lines.append(f"  Stale warnings: {obs.stale_warning_count}")
        if obs.score_delta_mean is not None:
            lines.append(f"  Score delta vs prior: mean={obs.score_delta_mean:.3f} max={obs.score_delta_max:.3f}")
        return "\n".join(lines)
