"""Case-level holdout scoring boundary.

The holdout data contains only unlabeled case evidence. Labels are deliberately not accepted by
this module or the CLI; scoring is performed by the independent custodian after predictions are
sealed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Disposition = Literal["INCLUDE", "EXCLUDE", "UNKNOWN"]


class HoldoutCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    modality: str = Field(min_length=1)
    source_text: str = ""


class HoldoutPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    disposition: Disposition


def load_holdout_cases(path: Path) -> list[HoldoutCase]:
    """Load unlabeled JSONL cases without ever accepting a label field."""

    cases: list[HoldoutCase] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = HoldoutCase.model_validate_json(line)
        except ValueError as exc:
            raise ValueError(f"invalid holdout case on line {line_number}: {exc}") from exc
        if case.case_id in seen:
            raise ValueError(f"duplicate holdout case_id: {case.case_id}")
        seen.add(case.case_id)
        cases.append(case)
    return cases


def predict_case(case: HoldoutCase) -> HoldoutPrediction:
    """Apply the frozen evidence sufficiency rule to one case.

    Explicit insufficiency routes to UNKNOWN. Explicit exclusion language routes to EXCLUDE;
    otherwise a target/modality evidence record is included. This is intentionally deterministic
    and label-free so the custodian can score the complete output after sealing it.
    """

    text = case.source_text.casefold()
    if any(term in text for term in ("incomplete", "insufficient", "unknown")):
        disposition: Disposition = "UNKNOWN"
    elif any(term in text for term in ("not eligible", "excluded", "fails the gate")):
        disposition = "EXCLUDE"
    else:
        disposition = "INCLUDE"
    return HoldoutPrediction(case_id=case.case_id, disposition=disposition)


def predict_holdout(path: Path) -> list[HoldoutPrediction]:
    """Produce exactly one prediction for every input case in canonical case-id order."""

    cases = load_holdout_cases(path)
    return [predict_case(case) for case in sorted(cases, key=lambda case: case.case_id)]


def validate_predictions(
    expected_case_ids: Iterable[str],
    predictions: Iterable[HoldoutPrediction | Mapping[str, object]],
) -> list[HoldoutPrediction]:
    """Validate cardinality, identity, and disposition before serialization."""

    expected = list(expected_case_ids)
    if len(expected) != len(set(expected)):
        raise ValueError("expected case IDs contain duplicates")
    normalized = [HoldoutPrediction.model_validate(prediction) for prediction in predictions]
    observed = [prediction.case_id for prediction in normalized]
    if len(observed) != len(set(observed)):
        raise ValueError("predictions contain duplicate case IDs")
    missing = set(expected) - set(observed)
    extra = set(observed) - set(expected)
    if missing or extra:
        raise ValueError(f"prediction case mismatch: missing={sorted(missing)}, extra={sorted(extra)}")
    return sorted(normalized, key=lambda prediction: prediction.case_id)


def predictions_json(predictions: list[HoldoutPrediction]) -> list[dict[str, str]]:
    return [prediction.model_dump(mode="json") for prediction in predictions]
