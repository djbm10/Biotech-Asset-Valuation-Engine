"""Data quality checks enforced at ingestion boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence


@dataclass
class DataQualityResult:
    """Result of a data quality check."""

    source_name: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0


class DataQualityChecker:
    """Validates that a data record meets minimum quality standards."""

    def validate(
        self,
        source_name: str,
        record: dict[str, Any],
        required_fields: Sequence[str],
        timestamp_field: str | None = None,
        primary_key_field: str | None = None,
    ) -> DataQualityResult:
        errors = []
        warnings = []

        # Required fields check
        for f in required_fields:
            if f not in record:
                errors.append(f"Missing required field: {f}")
            elif record[f] is None:
                warnings.append(f"Null value for field: {f}")

        # Timestamp check
        if timestamp_field:
            if timestamp_field not in record:
                errors.append(f"Missing timestamp field: {timestamp_field}")
            elif record.get(timestamp_field) is None:
                errors.append(f"Null timestamp: {timestamp_field}")

        # Primary key check
        if primary_key_field:
            if primary_key_field not in record:
                errors.append(f"Missing primary key: {primary_key_field}")
            elif not record[primary_key_field]:
                errors.append(f"Empty primary key: {primary_key_field}")

        return DataQualityResult(
            source_name=source_name,
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_batch(
        self,
        source_name: str,
        records: Sequence[dict[str, Any]],
        required_fields: Sequence[str],
        timestamp_field: str | None = None,
        primary_key_field: str | None = None,
    ) -> list[DataQualityResult]:
        return [
            self.validate(source_name, r, required_fields, timestamp_field, primary_key_field)
            for r in records
        ]

    def summary(self, results: Sequence[DataQualityResult]) -> dict:
        n = len(results)
        passed = sum(1 for r in results if r.passed)
        return {
            "total": n,
            "passed": passed,
            "failed": n - passed,
            "pass_rate": passed / n if n > 0 else 0.0,
        }
