"""Scenario library loader and stress runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class ScenarioDefinition:
    """A named reusable stress scenario."""

    scenario_id: str
    name: str
    category: str
    description: str
    affected_inputs: list[str]
    shocks: dict[str, float]
    rationale: str
    expected_output_effect: str


@dataclass
class StressResult:
    """Result of applying a scenario to a base-case parameter set."""

    scenario_id: str
    scenario_name: str
    base_values: dict[str, float]
    stressed_values: dict[str, float]
    shocked_params: dict[str, float]

    def describe(self) -> str:
        lines = [f"Scenario: {self.scenario_name}"]
        for param, shock in self.shocked_params.items():
            base = self.base_values.get(param, 0.0)
            stressed = self.stressed_values.get(param, 0.0)
            direction = "+" if shock >= 0 else ""
            lines.append(f"  {param}: {base:.4g} → {stressed:.4g} ({direction}{shock})")
        return "\n".join(lines)


class ScenarioLibrary:
    """Loads and retrieves named scenarios from the YAML library."""

    def __init__(self, library_path: str | Path | None = None) -> None:
        if library_path is None:
            library_path = Path(__file__).parent / "library.yaml"
        self._path = Path(library_path)
        self._scenarios: dict[str, ScenarioDefinition] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        with open(self._path) as f:
            raw = yaml.safe_load(f)
        for scenario_id, spec in raw.get("scenarios", {}).items():
            self._scenarios[scenario_id] = ScenarioDefinition(
                scenario_id=scenario_id,
                name=spec["name"],
                category=spec["category"],
                description=spec["description"],
                affected_inputs=spec.get("affected_inputs", []),
                shocks=spec.get("shocks", {}),
                rationale=spec["rationale"],
                expected_output_effect=spec["expected_output_effect"],
            )

    def get(self, scenario_id: str) -> ScenarioDefinition | None:
        return self._scenarios.get(scenario_id)

    def all(self) -> list[ScenarioDefinition]:
        return list(self._scenarios.values())

    def by_category(self, category: str) -> list[ScenarioDefinition]:
        return [s for s in self._scenarios.values() if s.category == category]

    def scenario_ids(self) -> list[str]:
        return list(self._scenarios.keys())


class StressRunner:
    """Applies scenario shocks to a base-case parameter set."""

    def __init__(self, library: ScenarioLibrary | None = None) -> None:
        self._library = library or ScenarioLibrary()

    def run(
        self,
        scenario_id: str,
        base_params: dict[str, float],
    ) -> StressResult:
        scenario = self._library.get(scenario_id)
        if scenario is None:
            raise KeyError(f"Scenario '{scenario_id}' not found in library")

        stressed = dict(base_params)
        shocked_params = {}
        for param, shock in scenario.shocks.items():
            if param in stressed:
                base_val = stressed[param]
                if isinstance(shock, float) and abs(shock) < 5:
                    # Additive shock (e.g., +1.5 years, -0.10 POS)
                    new_val = base_val + shock
                else:
                    # Multiplicative shock
                    new_val = base_val * (1 + shock)
                stressed[param] = new_val
                shocked_params[param] = shock

        return StressResult(
            scenario_id=scenario_id,
            scenario_name=scenario.name,
            base_values=dict(base_params),
            stressed_values=stressed,
            shocked_params=shocked_params,
        )

    def run_top_n(
        self,
        scenario_ids: list[str],
        base_params: dict[str, float],
        n: int = 3,
    ) -> list[StressResult]:
        results = []
        for sid in scenario_ids[:n]:
            try:
                results.append(self.run(sid, base_params))
            except KeyError:
                pass
        return results

    def run_all(self, base_params: dict[str, float]) -> list[StressResult]:
        return self.run_top_n(self._library.scenario_ids(), base_params, n=len(self._library.all()))
