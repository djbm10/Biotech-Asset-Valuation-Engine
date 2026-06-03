"""
Block 37B — M&A Calibration Dataset Framework.

Provides:
  MACalibrationCase     — Pydantic model for a single historical deal/non-deal observation
  NoLookaheadResult     — result of the no-lookahead validator
  validate_no_lookahead — validates that all feature_as_of_dates predate observation_date
  FitReadinessResult    — result of the fit readiness gate
  check_fit_readiness   — blocks fitting until ≥50 positives, ≥100 negatives, all lookahead pass
  MACalibrationDataset  — container for a list of cases with summary stats
  load_dataset_from_yaml / save_dataset_to_yaml — YAML I/O

DO NOT call fit_logistic_calibration() until check_fit_readiness().ready is True.
A poorly curated calibration dataset produces false confidence — worse than no calibration.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# MACalibrationCase
# ---------------------------------------------------------------------------

class MACalibrationCase(BaseModel):
    """
    A single historical M&A calibration observation.

    All ``*_as_of`` feature fields represent information observable BEFORE
    or ON ``observation_date``.  The no-lookahead validator checks
    ``feature_as_of_dates`` to enforce this invariant.

    Fields
    ------
    ticker : str
        Exchange ticker of the target company.
    company_name : str
        Human-readable name.
    observation_date : date
        The date at which the observation was made (start of the 12-month window).
    target_stage : str
        Pipeline stage of the lead asset (e.g. "phase_2", "phase_3", "nda_bla").
    therapeutic_area : str
        Broad therapeutic area key (matches industry_assumptions.yaml).
    modality : str
        Drug modality (e.g. "small_molecule", "biologic_antibody").
    cash_runway_months_as_of : float
        Estimated cash runway in months as of observation_date.
    seller_willingness_as_of : float  [0, 1]
        Analyst estimate of seller willingness as of observation_date.
    catalyst_days_as_of : Optional[int]
        Days to next material catalyst as of observation_date; None if unknown.
    asset_quality_score_as_of : float  [0, 1]
        Asset quality composite score as of observation_date.
    acquirer_fit_score_as_of : float  [0, 1]
        Acquirer strategic fit score as of observation_date.
    outcome_12m : bool
        True if a material transaction (acquisition/license/partnership) closed
        within 12 months of observation_date.
    outcome_type : str
        One of "acquisition", "license", "partnership", "none".
    outcome_date : Optional[date]
        Date the transaction closed; None when outcome_12m=False.
    source_refs : list[str]
        URLs or filing citations supporting feature values and outcome.
    feature_as_of_dates : dict[str, str]
        Mapping of field name → ISO date string ("YYYY-MM-DD") at which the
        feature value was sourced.  Used by validate_no_lookahead().
    lookahead_pass : bool
        Set to True only after manually confirming no lookahead bias.
        Populated by validate_no_lookahead() or set by analyst after review.
    """
    ticker: str
    company_name: str
    observation_date: datetime.date
    target_stage: str
    therapeutic_area: str
    modality: str
    cash_runway_months_as_of: float
    seller_willingness_as_of: float = Field(ge=0.0, le=1.0)
    catalyst_days_as_of: Optional[int] = Field(default=None, ge=0)
    asset_quality_score_as_of: float = Field(ge=0.0, le=1.0)
    acquirer_fit_score_as_of: float = Field(ge=0.0, le=1.0)
    outcome_12m: bool
    outcome_type: str  # "acquisition" | "license" | "partnership" | "none"
    outcome_date: Optional[datetime.date] = None
    source_refs: list[str] = Field(default_factory=list)
    feature_as_of_dates: dict[str, str] = Field(default_factory=dict)
    lookahead_pass: bool = False


# ---------------------------------------------------------------------------
# No-lookahead validator
# ---------------------------------------------------------------------------

@dataclass
class NoLookaheadResult:
    """Result of validate_no_lookahead()."""
    passed: bool
    violations: list[str] = dc_field(default_factory=list)
    message: str = ""


def validate_no_lookahead(case: MACalibrationCase) -> NoLookaheadResult:
    """
    Check that all feature_as_of_dates entries predate or match observation_date.

    Returns a NoLookaheadResult with:
      passed = True  → no violations found
      passed = False → violations list populated with offending field names
    """
    violations: list[str] = []
    for field_name, date_str in case.feature_as_of_dates.items():
        try:
            as_of = datetime.date.fromisoformat(date_str)
        except ValueError:
            violations.append(f"{field_name}:invalid_date({date_str!r})")
            continue
        if as_of > case.observation_date:
            violations.append(field_name)

    if violations:
        return NoLookaheadResult(
            passed=False,
            violations=violations,
            message=(
                f"Lookahead detected in case {case.ticker!r} "
                f"(observation_date={case.observation_date}): "
                f"fields {violations} have as_of dates after observation_date."
            ),
        )
    return NoLookaheadResult(passed=True, violations=[], message="")


# ---------------------------------------------------------------------------
# Fit readiness gate
# ---------------------------------------------------------------------------

@dataclass
class FitReadinessResult:
    """Result of check_fit_readiness()."""
    ready: bool
    reason: str = ""


_MIN_POSITIVES: int = 50
_MIN_NEGATIVES: int = 100


def check_fit_readiness(dataset: MACalibrationDataset) -> FitReadinessResult:
    """
    Gate that prevents premature logistic calibration fitting.

    Requirements:
      1. ≥ 50 positive cases (outcome_12m=True)
      2. ≥ 100 negative cases (outcome_12m=False)
      3. All cases must have lookahead_pass=True

    Returns FitReadinessResult(ready=True) only when all three conditions hold.
    """
    n_pos = dataset.positive_count
    n_neg = dataset.negative_count
    n_pass = dataset.lookahead_passed_count
    n_total = len(dataset.cases)

    if n_pos < _MIN_POSITIVES:
        return FitReadinessResult(
            ready=False,
            reason=(
                f"Insufficient positives: {n_pos} < {_MIN_POSITIVES} required. "
                "Add more confirmed deal cases before fitting."
            ),
        )
    if n_neg < _MIN_NEGATIVES:
        return FitReadinessResult(
            ready=False,
            reason=(
                f"Insufficient negatives: {n_neg} < {_MIN_NEGATIVES} required. "
                "Add more confirmed non-deal cases before fitting."
            ),
        )
    if n_pass < n_total:
        n_fail = n_total - n_pass
        return FitReadinessResult(
            ready=False,
            reason=(
                f"Lookahead violations: {n_fail} case(s) have lookahead_pass=False. "
                "Run validate_no_lookahead() on all cases and fix violations before fitting."
            ),
        )
    return FitReadinessResult(ready=True, reason="All conditions met.")


# ---------------------------------------------------------------------------
# MACalibrationDataset
# ---------------------------------------------------------------------------

class MACalibrationDataset(BaseModel):
    """Container for a collection of MACalibrationCase records."""

    cases: list[MACalibrationCase] = Field(default_factory=list)

    @property
    def positive_count(self) -> int:
        return sum(1 for c in self.cases if c.outcome_12m)

    @property
    def negative_count(self) -> int:
        return sum(1 for c in self.cases if not c.outcome_12m)

    @property
    def lookahead_passed_count(self) -> int:
        return sum(1 for c in self.cases if c.lookahead_pass)

    def summary(self) -> dict:
        return {
            "total": len(self.cases),
            "positives": self.positive_count,
            "negatives": self.negative_count,
            "lookahead_passed": self.lookahead_passed_count,
            "fit_ready": check_fit_readiness(self).ready,
        }


# ---------------------------------------------------------------------------
# YAML I/O
# ---------------------------------------------------------------------------

def _case_to_dict(case: MACalibrationCase) -> dict:
    """Serialize a case to a plain dict suitable for YAML."""
    d = case.model_dump()
    # Convert date objects to ISO strings
    for key in ("observation_date", "outcome_date"):
        if d[key] is not None:
            d[key] = d[key].isoformat()
    return d


def _case_from_dict(d: dict) -> MACalibrationCase:
    """Deserialize a case from a plain dict (YAML-loaded)."""
    for key in ("observation_date", "outcome_date"):
        if isinstance(d.get(key), str):
            d[key] = datetime.date.fromisoformat(d[key])
    return MACalibrationCase(**d)


def save_dataset_to_yaml(dataset: MACalibrationDataset, path: Path | str) -> None:
    """Write dataset to a YAML file."""
    path = Path(path)
    payload = {"cases": [_case_to_dict(c) for c in dataset.cases]}
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False)


def load_dataset_from_yaml(path: Path | str) -> MACalibrationDataset:
    """Load dataset from a YAML file."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}
    cases = [_case_from_dict(c) for c in payload.get("cases", [])]
    return MACalibrationDataset(cases=cases)
