"""
leakage_guard — strict no-look-ahead enforcement.

LeakageGuard raises LeakageViolationError if any of the following are true:

  1. source_published_date > snapshot_date  (future source)
  2. data_as_of_date       > snapshot_date  (future data)
  3. Any label field name appears in model input columns
  4. Any feature column name matches a known label-contamination pattern

The backtest runner calls ``LeakageGuard.audit_dataframe()`` and refuses
to proceed if ``LeakageAuditResult.has_violations`` is True.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, Sequence


# ---------------------------------------------------------------------------
# Label field patterns (case-insensitive substring match)
# ---------------------------------------------------------------------------

REQUIRED_PROVENANCE_FIELDS: tuple[str, ...] = (
    "source_url",
    "source_published_date",
    "data_as_of_date",
    "extraction_method",
    "confidence",
)

LABEL_PATTERNS: tuple[str, ...] = (
    r"actual_deal",
    r"acquired",
    r"acquisition",
    r"premium",
    r"deal_premium",
    r"post_deal",
    r"future_",
    r"later_approved",
    r"outcome_",
    r"deal_value",
    r"announced_date",
    r"announcement_date",
)

_COMPILED_LABEL_PATTERNS = [re.compile(p, re.IGNORECASE) for p in LABEL_PATTERNS]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LeakageViolationError(Exception):
    """Raised when a leakage violation is detected and cannot be ignored."""


# ---------------------------------------------------------------------------
# Violation dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Violation:
    row_index: Optional[int]
    column: str
    violation_type: str   # "future_source" | "future_data" | "label_column" | "label_pattern"
    detail: str


# ---------------------------------------------------------------------------
# LeakageAuditResult
# ---------------------------------------------------------------------------

@dataclass
class LeakageAuditResult:
    violations: list[Violation] = field(default_factory=list)
    rows_audited: int = 0
    columns_audited: int = 0

    @property
    def has_violations(self) -> bool:
        return len(self.violations) > 0

    @property
    def n_future_source_violations(self) -> int:
        return sum(1 for v in self.violations if v.violation_type == "future_source")

    @property
    def n_future_data_violations(self) -> int:
        return sum(1 for v in self.violations if v.violation_type == "future_data")

    @property
    def n_label_violations(self) -> int:
        return sum(1 for v in self.violations
                   if v.violation_type in ("label_column", "label_pattern"))

    def summary(self) -> str:
        lines = [
            f"Leakage Audit: {self.rows_audited} rows, {self.columns_audited} columns",
            f"  Future-source violations : {self.n_future_source_violations}",
            f"  Future-data violations   : {self.n_future_data_violations}",
            f"  Label-field violations   : {self.n_label_violations}",
            f"  Total violations         : {len(self.violations)}",
        ]
        for v in self.violations[:10]:
            lines.append(f"  [{v.violation_type}] row={v.row_index} col={v.column}: {v.detail}")
        if len(self.violations) > 10:
            lines.append(f"  ... and {len(self.violations) - 10} more")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# LeakageGuard
# ---------------------------------------------------------------------------

class LeakageGuard:
    """
    Enforce no-look-ahead constraints on feature data.

    Usage (dict-based)::

        guard = LeakageGuard()
        guard.check_feature_row(row, snapshot_date=date(2023, 5, 10))

    Usage (DataFrame / list-of-dicts)::

        result = guard.audit_dataframe(rows, snapshot_date_col="snapshot_date")
        if result.has_violations:
            raise LeakageViolationError(result.summary())

    Extra label columns can be passed at construction time to extend the
    default label-pattern list.
    """

    def __init__(
        self,
        extra_label_patterns: Sequence[str] = (),
    ) -> None:
        self._patterns = list(_COMPILED_LABEL_PATTERNS)
        for p in extra_label_patterns:
            self._patterns.append(re.compile(p, re.IGNORECASE))

    # ------------------------------------------------------------------
    # Single-row checks
    # ------------------------------------------------------------------

    def check_feature_row(
        self,
        row: dict[str, Any],
        snapshot_date: date,
    ) -> list[Violation]:
        """Return violations for a single feature row."""
        violations: list[Violation] = []

        # 1. source_published_date must be <= snapshot_date
        spd = row.get("source_published_date")
        if spd is not None:
            spd_date = self._parse_date(spd)
            if spd_date is not None and spd_date > snapshot_date:
                violations.append(Violation(
                    row_index=None,
                    column="source_published_date",
                    violation_type="future_source",
                    detail=(
                        f"source_published_date={spd_date.isoformat()} > "
                        f"snapshot_date={snapshot_date.isoformat()}"
                    ),
                ))

        # 2. data_as_of_date must be <= snapshot_date
        dad = row.get("data_as_of_date")
        if dad is not None:
            dad_date = self._parse_date(dad)
            if dad_date is not None and dad_date > snapshot_date:
                violations.append(Violation(
                    row_index=None,
                    column="data_as_of_date",
                    violation_type="future_data",
                    detail=(
                        f"data_as_of_date={dad_date.isoformat()} > "
                        f"snapshot_date={snapshot_date.isoformat()}"
                    ),
                ))
        return violations

    def check_column_names(self, columns: Sequence[str]) -> list[Violation]:
        """Return violations for label-contaminated column names."""
        violations: list[Violation] = []
        for col in columns:
            for pat in self._patterns:
                if pat.search(col):
                    violations.append(Violation(
                        row_index=None,
                        column=col,
                        violation_type="label_pattern",
                        detail=f"Column name matches label pattern: {pat.pattern!r}",
                    ))
                    break  # one violation per column
        return violations

    # ------------------------------------------------------------------
    # DataFrame / list-of-dicts audit
    # ------------------------------------------------------------------

    def audit_dataframe(
        self,
        rows: "list[dict[str, Any]] | Any",
        snapshot_date_col: str = "snapshot_date",
        extra_model_input_cols: Sequence[str] | None = None,
    ) -> LeakageAuditResult:
        """
        Full leakage audit over a list of rows (or pandas DataFrame).

        Steps:
          1. Check column names for label patterns.
          2. For each row, check source_published_date and data_as_of_date
             against the row's snapshot_date.

        Parameters
        ----------
        rows                 : list of dicts or pandas DataFrame
        snapshot_date_col    : column that holds the snapshot date per row
        extra_model_input_cols : additional columns to check for label patterns
        """
        # Support pandas DataFrame
        try:
            import pandas as pd
            if isinstance(rows, pd.DataFrame):
                rows = rows.to_dict("records")
        except ImportError:
            pass

        result = LeakageAuditResult()

        # -- Column-level check
        if rows:
            all_cols = list(rows[0].keys())
        else:
            all_cols = list(extra_model_input_cols or [])
        col_violations = self.check_column_names(all_cols)
        result.violations.extend(col_violations)
        result.columns_audited = len(all_cols)

        # -- Row-level check
        for idx, row in enumerate(rows):
            snap_raw = row.get(snapshot_date_col)
            if snap_raw is None:
                continue
            snap = self._parse_date(snap_raw)
            if snap is None:
                continue
            row_violations = self.check_feature_row(row, snap)
            for v in row_violations:
                result.violations.append(
                    Violation(idx, v.column, v.violation_type, v.detail)
                )

        result.rows_audited = len(rows)
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
        return None

    def assert_clean(
        self,
        rows: "list[dict[str, Any]] | Any",
        snapshot_date_col: str = "snapshot_date",
    ) -> LeakageAuditResult:
        """Audit and raise LeakageViolationError if any violations found."""
        result = self.audit_dataframe(rows, snapshot_date_col=snapshot_date_col)
        if result.has_violations:
            raise LeakageViolationError(
                f"Leakage audit failed with {len(result.violations)} violation(s).\n"
                + result.summary()
            )
        return result
