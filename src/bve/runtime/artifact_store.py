"""ArtifactStore — persists run artifacts for reproducibility."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .run_context import RunContext


class ArtifactStore:
    """Writes and reads run artifacts to/from a local directory."""

    def __init__(self, base_dir: str | Path = "outputs/runs") -> None:
        self._base = Path(base_dir)

    def _run_dir(self, run_id: str) -> Path:
        return self._base / run_id

    def save(
        self,
        ctx: RunContext,
        output: dict[str, Any],
        extra_files: dict[str, str | bytes] | None = None,
    ) -> Path:
        """Save all artifacts for a run. Returns the run directory."""
        run_dir = self._run_dir(ctx.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        # Save provenance
        provenance_path = run_dir / "provenance.json"
        provenance_path.write_text(
            json.dumps(ctx.to_observation_dict(), indent=2, default=str)
        )

        # Save main output
        output_path = run_dir / "output.json"
        output_path.write_text(json.dumps(output, indent=2, default=str))

        # Save extra files (memos, charts, etc.)
        if extra_files:
            for filename, content in extra_files.items():
                artifact_path = run_dir / filename
                if isinstance(content, bytes):
                    artifact_path.write_bytes(content)
                else:
                    artifact_path.write_text(content)

        return run_dir

    def load(self, run_id: str) -> dict[str, Any] | None:
        """Load the output.json for a previous run."""
        output_path = self._run_dir(run_id) / "output.json"
        if not output_path.exists():
            return None
        return json.loads(output_path.read_text())

    def load_provenance(self, run_id: str) -> dict | None:
        prov_path = self._run_dir(run_id) / "provenance.json"
        if not prov_path.exists():
            return None
        return json.loads(prov_path.read_text())

    def list_runs(self) -> list[str]:
        if not self._base.exists():
            return []
        return [d.name for d in sorted(self._base.iterdir()) if d.is_dir()]

    def exists(self, run_id: str) -> bool:
        return (self._run_dir(run_id) / "output.json").exists()
