"""No-lookahead audit for historical M&A calibration cases.

Validates that every case in ``historical_calibration_cases.yaml`` satisfies
the no-lookahead constraint:

- ``lookahead_pass`` must be ``true``
- Positive cases must resolve at least 30 days after the observation date
- Feature ``as-of`` dates must not post-date the observation date
- Positive cases must have a non-null ``outcome_date``
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml


_DEFAULT_YAML = (
    Path(__file__).resolve().parents[3] / "research" / "mna" / "historical_calibration_cases.yaml"
)


@dataclass
class CaseViolation:
    ticker: str
    observation_date: str
    violation_type: str
    detail: str


@dataclass
class AuditResult:
    n_total: int
    n_positive: int
    n_negative: int
    n_clean: int
    n_violations: int
    violations: list[CaseViolation] = field(default_factory=list)
    has_violations: bool = False
    summary: str = ""


def _parse_date(value: Any) -> date | None:
    """Return a ``date`` from a string or ``date`` object; ``None`` if blank."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _audit_case(case: dict[str, Any]) -> list[CaseViolation]:
    """Return all violations found in a single case dict."""
    violations: list[CaseViolation] = []

    ticker = case.get("ticker", "UNKNOWN")
    obs_raw = case.get("observation_date")
    observation_date = _parse_date(obs_raw)
    obs_str = str(obs_raw) if obs_raw else "?"
    is_positive = bool(case.get("outcome_12m", False))

    # ── LOOKAHEAD_FLAG_FALSE ────────────────────────────────────────────────
    if not case.get("lookahead_pass", True):
        violations.append(
            CaseViolation(
                ticker=ticker,
                observation_date=obs_str,
                violation_type="LOOKAHEAD_FLAG_FALSE",
                detail="lookahead_pass is false — case was manually flagged as having lookahead",
            )
        )

    if observation_date is None:
        # Cannot perform date comparisons without observation_date; skip further checks
        violations.append(
            CaseViolation(
                ticker=ticker,
                observation_date=obs_str,
                violation_type="MISSING_OBSERVATION_DATE",
                detail="observation_date is null or missing",
            )
        )
        return violations

    # ── MISSING_OUTCOME_DATE (positives only) ──────────────────────────────
    if is_positive:
        outcome_date_raw = case.get("outcome_date")
        if outcome_date_raw is None:
            violations.append(
                CaseViolation(
                    ticker=ticker,
                    observation_date=obs_str,
                    violation_type="MISSING_OUTCOME_DATE",
                    detail="outcome_12m=true but outcome_date is null",
                )
            )
        else:
            # ── INSUFFICIENT_LEAD_TIME (positives only) ────────────────────
            outcome_date = _parse_date(outcome_date_raw)
            if outcome_date is not None:
                min_allowed = observation_date + timedelta(days=30)
                if outcome_date < min_allowed:
                    violations.append(
                        CaseViolation(
                            ticker=ticker,
                            observation_date=obs_str,
                            violation_type="INSUFFICIENT_LEAD_TIME",
                            detail=(
                                f"outcome_date {outcome_date} is only "
                                f"{(outcome_date - observation_date).days} days after "
                                f"observation_date {observation_date} "
                                f"(minimum 30 days required)"
                            ),
                        )
                    )

    # ── FEATURE_DATE_AFTER_OBSERVATION (any case) ──────────────────────────
    feature_dates: dict[str, Any] = case.get("feature_as_of_dates") or {}
    for feature_key, feature_date_raw in feature_dates.items():
        feature_date = _parse_date(feature_date_raw)
        if feature_date is not None and feature_date > observation_date:
            violations.append(
                CaseViolation(
                    ticker=ticker,
                    observation_date=obs_str,
                    violation_type="FEATURE_DATE_AFTER_OBSERVATION",
                    detail=(
                        f"feature '{feature_key}' has as-of date {feature_date} "
                        f"which is after observation_date {observation_date}"
                    ),
                )
            )

    return violations


def run_no_lookahead_audit(yaml_path: str | Path | None = None) -> AuditResult:
    """Audit all cases in the calibration YAML for lookahead violations.

    Parameters
    ----------
    yaml_path:
        Path to ``historical_calibration_cases.yaml``.  Defaults to the
        canonical file at ``research/mna/historical_calibration_cases.yaml``.

    Returns
    -------
    AuditResult
    """
    path = Path(yaml_path) if yaml_path is not None else _DEFAULT_YAML

    with path.open() as fh:
        raw = yaml.safe_load(fh)

    cases: list[dict[str, Any]] = raw.get("cases", []) if isinstance(raw, dict) else raw or []

    n_positive = sum(1 for c in cases if c.get("outcome_12m", False))
    n_negative = len(cases) - n_positive

    all_violations: list[CaseViolation] = []
    for case in cases:
        all_violations.extend(_audit_case(case))

    # Cases are considered "clean" when they contributed zero violations.
    violating_tickers: set[str] = {v.ticker for v in all_violations}
    n_violations = len(all_violations)
    n_clean = len(cases) - len(violating_tickers)

    has_violations = n_violations > 0

    if has_violations:
        summary = (
            f"FAIL — {n_violations} violation(s) found across "
            f"{len(violating_tickers)} case(s) "
            f"(total {len(cases)}: {n_positive} positive / {n_negative} negative)"
        )
    else:
        summary = (
            f"PASS — all {len(cases)} cases clean "
            f"({n_positive} positive / {n_negative} negative)"
        )

    return AuditResult(
        n_total=len(cases),
        n_positive=n_positive,
        n_negative=n_negative,
        n_clean=n_clean,
        n_violations=n_violations,
        violations=all_violations,
        has_violations=has_violations,
        summary=summary,
    )


def print_audit_report(result: AuditResult) -> None:
    """Print a clean ASCII audit report to stdout."""
    width = 72
    bar = "=" * width

    print()
    print(bar)
    print("  BVE M&A Calibration Cases — No-Lookahead Audit")
    print(bar)
    print(f"  Total cases : {result.n_total}")
    print(f"  Positives   : {result.n_positive}")
    print(f"  Negatives   : {result.n_negative}")
    print(f"  Clean cases : {result.n_clean}")
    print(f"  Violations  : {result.n_violations}")
    print()

    if not result.has_violations:
        print("  STATUS: PASS")
        print(f"  {result.summary}")
        print()
        print(bar)
        return

    print("  STATUS: FAIL")
    print(f"  {result.summary}")
    print()

    # Group violations by type for the summary table
    by_type: dict[str, int] = {}
    for v in result.violations:
        by_type[v.violation_type] = by_type.get(v.violation_type, 0) + 1

    print("  Violation breakdown:")
    for vtype, count in sorted(by_type.items()):
        print(f"    {vtype:<40s}  {count:>3}")
    print()

    print("  Detail:")
    print("  " + "-" * (width - 2))
    for v in result.violations:
        print(f"  [{v.violation_type}]")
        print(f"    ticker           : {v.ticker}")
        print(f"    observation_date : {v.observation_date}")
        print(f"    detail           : {v.detail}")
        print()

    print(bar)
