"""Error bucket assignment for resolved predictions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from bve.learning.prediction_log import (
    DecisionPredictionRecord as PredictionRecord,
    DecisionPredictionOutcome as PredictionOutcome,
)


class ErrorCategory(str, Enum):
    # New Step 12 values
    CORRECT = "correct"                  # no error
    POS_ERROR = "pos_error"              # wrong probability estimate
    TIMING_ERROR = "timing_error"        # right direction, wrong timing
    SCIENCE_ERROR = "science_error"      # science diligence missed key risk
    COMPETITION_ERROR = "competition_error"  # competitor impact underestimated
    FINANCING_ERROR = "financing_error"  # dilution/runway not factored
    MARKET_DRIFT = "market_drift"        # macro/sentiment drove outcome not model
    THESIS_ERROR = "thesis_error"        # thesis framework was wrong
    UNCLASSIFIED = "unclassified"
    # Legacy values for backward compatibility
    POS_OVERESTIMATE = "pos_overestimate"
    POS_UNDERESTIMATE = "pos_underestimate"
    MARKET_EXPECTATIONS_GAP = "market_expectations_gap"
    LABEL_BREADTH_ERROR = "label_breadth_error"
    COMPETITION_SURPRISE = "competition_surprise"
    FINANCING_SURPRISE = "financing_surprise"


# ---------------------------------------------------------------------------
# Legacy PostmortemEntry (Pydantic model) for backward compatibility
# ---------------------------------------------------------------------------


class PostmortemEntry(BaseModel):
    """A complete postmortem record for one resolved catalyst event (legacy API)."""

    postmortem_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    ticker: Optional[str] = None
    catalyst_date: date
    created_date: date
    catalyst_type: str
    actual_result: str  # "success" | "failure" | "partial"
    model_pos_at_entry: float
    market_implied_pos_at_entry: Optional[float] = None
    price_change_pct: Optional[float] = None
    primary_error: ErrorCategory
    secondary_errors: list[ErrorCategory] = Field(default_factory=list)
    what_model_got_right: str = ""
    what_model_got_wrong: str = ""
    rule_changes_suggested: list[str] = Field(default_factory=list)
    lessons: str = ""


@dataclass(frozen=True)
class PostmortemResult:
    prediction_id: str
    asset_id: str
    error_category: ErrorCategory
    predicted_pos: float
    realized_outcome: PredictionOutcome
    realized_return: float
    predicted_return: float
    pos_error: float              # abs(predicted_pos - binary_outcome)
    return_error: float           # predicted_return - realized_return
    notes: str


class PostmortemStore:
    """In-memory store for postmortem results (supports both PostmortemResult and legacy PostmortemEntry)."""

    def __init__(self) -> None:
        self._results: dict[str, PostmortemResult] = {}
        # Legacy entry store (for backward compatibility with test_phase4_learning_layer.py)
        self._entries: dict[str, PostmortemEntry] = {}

    def add(self, result: "PostmortemResult | PostmortemEntry") -> None:
        """Add a postmortem result or legacy PostmortemEntry."""
        if isinstance(result, PostmortemEntry):
            self._entries[result.postmortem_id] = result
        else:
            self._results[result.prediction_id] = result

    def get(self, prediction_id: str) -> "PostmortemResult | PostmortemEntry | None":
        """Retrieve by prediction_id (or postmortem_id for legacy entries)."""
        if prediction_id in self._results:
            return self._results[prediction_id]
        return self._entries.get(prediction_id)

    def all(self) -> list[PostmortemResult]:
        """Return all new-style postmortem results."""
        return list(self._results.values())

    def by_category(self, category: ErrorCategory) -> list[PostmortemResult]:
        """Return new-style results with the given error category."""
        return [r for r in self._results.values() if r.error_category == category]

    def error_distribution(self) -> dict[str, int]:
        """Returns {ErrorCategory.value: count} for all stored results + legacy entries."""
        dist: dict[str, int] = {}
        for result in self._results.values():
            key = result.error_category.value
            dist[key] = dist.get(key, 0) + 1
        for entry in self._entries.values():
            key = entry.primary_error.value
            dist[key] = dist.get(key, 0) + 1
        return dist

    # ------------------------------------------------------------------
    # Legacy API (backward compatibility)
    # ------------------------------------------------------------------

    def list_all(self) -> list[PostmortemEntry]:
        """Return all legacy entries, sorted by catalyst_date ascending."""
        return sorted(self._entries.values(), key=lambda e: e.catalyst_date)

    def by_error_category(self, category: ErrorCategory) -> list[PostmortemEntry]:
        """Return legacy entries whose primary_error matches category."""
        return [e for e in self._entries.values() if e.primary_error == category]

    def by_asset(self, asset_id: str) -> list[PostmortemEntry]:
        """Return all legacy entries for a given asset_id."""
        return [e for e in self._entries.values() if e.asset_id == asset_id]

    def most_common_error(self) -> Optional[ErrorCategory]:
        """Return the most frequent primary ErrorCategory from legacy entries, or None."""
        dist_legacy: dict[str, int] = {}
        for entry in self._entries.values():
            key = entry.primary_error.value
            dist_legacy[key] = dist_legacy.get(key, 0) + 1
        if not dist_legacy:
            return None
        top_key = max(dist_legacy, key=lambda k: dist_legacy[k])
        return ErrorCategory(top_key)


def binary_outcome(record: PredictionRecord) -> float:
    """1.0 if CORRECT, 0.0 if INCORRECT, 0.5 if PARTIAL, 0.5 if PENDING."""
    if record.outcome == PredictionOutcome.CORRECT:
        return 1.0
    elif record.outcome == PredictionOutcome.INCORRECT:
        return 0.0
    else:
        # PARTIAL or PENDING
        return 0.5


def classify_error(record: PredictionRecord) -> ErrorCategory:
    """
    Deterministic error classification:
    - CORRECT if outcome == CORRECT
    - UNCLASSIFIED if outcome == PENDING
    - POS_ERROR if abs(predicted_pos - binary_outcome(record)) > 0.25
    - TIMING_ERROR if outcome == PARTIAL (right direction but mixed result)
    - FINANCING_ERROR if 'financing' in record.domain_scores and domain_scores['financing'] < 0.30 and outcome == INCORRECT
    - COMPETITION_ERROR if 'competition' in record.domain_scores and domain_scores['competition'] < 0.30 and outcome == INCORRECT
    - SCIENCE_ERROR if 'science' in record.domain_scores and domain_scores['science'] < 0.35 and outcome == INCORRECT
    - MARKET_DRIFT if outcome == INCORRECT and abs(record.predicted_return) < 0.15 (small conviction, market moved)
    - THESIS_ERROR otherwise for INCORRECT
    """
    if record.outcome == PredictionOutcome.CORRECT:
        return ErrorCategory.CORRECT

    if record.outcome == PredictionOutcome.PENDING:
        return ErrorCategory.UNCLASSIFIED

    binary = binary_outcome(record)
    pos_err = abs(record.predicted_pos - binary)

    if pos_err > 0.25:
        return ErrorCategory.POS_ERROR

    if record.outcome == PredictionOutcome.PARTIAL:
        return ErrorCategory.TIMING_ERROR

    # INCORRECT from here on
    if (
        "financing" in record.domain_scores
        and record.domain_scores["financing"] < 0.30
        and record.outcome == PredictionOutcome.INCORRECT
    ):
        return ErrorCategory.FINANCING_ERROR

    if (
        "competition" in record.domain_scores
        and record.domain_scores["competition"] < 0.30
        and record.outcome == PredictionOutcome.INCORRECT
    ):
        return ErrorCategory.COMPETITION_ERROR

    if (
        "science" in record.domain_scores
        and record.domain_scores["science"] < 0.35
        and record.outcome == PredictionOutcome.INCORRECT
    ):
        return ErrorCategory.SCIENCE_ERROR

    if record.outcome == PredictionOutcome.INCORRECT and abs(record.predicted_return) < 0.15:
        return ErrorCategory.MARKET_DRIFT

    return ErrorCategory.THESIS_ERROR


def run_postmortem(
    record: PredictionRecord,
    notes: str = "",
) -> PostmortemResult:
    """Classify error and build PostmortemResult."""
    category = classify_error(record)
    binary = binary_outcome(record)
    pos_err = abs(record.predicted_pos - binary)
    realized_ret = record.realized_return if record.realized_return is not None else 0.0
    return_err = record.predicted_return - realized_ret

    return PostmortemResult(
        prediction_id=record.prediction_id,
        asset_id=record.asset_id,
        error_category=category,
        predicted_pos=record.predicted_pos,
        realized_outcome=record.outcome,
        realized_return=realized_ret,
        predicted_return=record.predicted_return,
        pos_error=pos_err,
        return_error=return_err,
        notes=notes,
    )
