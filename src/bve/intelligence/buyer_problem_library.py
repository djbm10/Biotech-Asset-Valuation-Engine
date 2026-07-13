"""Config-backed buyer problem library for Layer 1.5 BD matching."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from bve.intelligence.science_thesis import BuyerProblem


class BuyerProblemRecord(BuyerProblem):
    problem_id: str


class BuyerProblemConfig(BaseModel):
    buyer_id: str
    buyer_name: str = ""
    problems: list[BuyerProblemRecord] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _inject_buyer_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        buyer_id = data.get("buyer_id")
        buyer_name = data.get("buyer_name", "")
        problems = []
        for problem in data.get("problems", []) or []:
            if isinstance(problem, dict):
                merged = {"buyer_id": buyer_id, "buyer_name": buyer_name, **problem}
                problems.append(merged)
            else:
                problems.append(problem)
        return {**data, "problems": problems}


class BuyerProblemLibrary:
    """Load and query buyer problems from YAML configs."""

    def __init__(self, problems: list[BuyerProblemRecord] | None = None) -> None:
        self._problems = problems or []

    @classmethod
    def from_yaml(cls, path: str | Path) -> "BuyerProblemLibrary":
        config = load_buyer_problem_config(path)
        return cls(config.problems)

    @classmethod
    def from_directory(cls, directory: str | Path) -> "BuyerProblemLibrary":
        problems: list[BuyerProblemRecord] = []
        for path in sorted(Path(directory).glob("*.yaml")):
            problems.extend(load_buyer_problem_config(path).problems)
        return cls(problems)

    @property
    def problems(self) -> list[BuyerProblemRecord]:
        return list(self._problems)

    def for_buyer(self, buyer_id: str) -> list[BuyerProblemRecord]:
        return [problem for problem in self._problems if problem.buyer_id == buyer_id]


def load_buyer_problem_config(path: str | Path) -> BuyerProblemConfig:
    loaded = yaml.safe_load(Path(path).read_text())
    try:
        return BuyerProblemConfig.model_validate(loaded)
    except ValidationError as exc:
        raise ValueError(f"Invalid buyer problem config: {path}") from exc
