"""Layer 5 — 5A: Outcome Dataset Builder.

Builds clean HistoricalMAOutcome records from raw case dicts,
applies time-window labels, validates for data leakage, and
excludes cases that fail leakage checks.

Key design:
- Does NOT exclude non-events (remained independent, false positives, etc.)
- Labels are time-window specific (6m / 12m / 24m)
- Leakage check: source_date must be <= prediction_date
- All OutcomeType values produce a retained record (no survivorship bias)
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

from bve.intelligence.ma_calibration_models import (
    ACTIVE_PROCESS_OUTCOME_TYPES,
    FULL_ACQUISITION_OUTCOME_TYPES,
    LICENSE_OR_PARTNER_OUTCOME_TYPES,
    STRATEGIC_TRANSACTION_OUTCOME_TYPES,
    HistoricalAcquirerFeatures,
    HistoricalMAOutcome,
    HistoricalTargetFeatures,
    OutcomeDatasetConfig,
    OutcomeLabels,
    OutcomeType,
)

# Approximate month-to-days conversion
_DAYS_PER_MONTH = 30.4375

# Outcome types that indicate distressed financing
_DISTRESSED_TYPES = frozenset({
    OutcomeType.DISTRESSED_FINANCING,
    OutcomeType.BANKRUPTCY_OR_WIND_DOWN,
})


def label_outcomes(
    prediction_date: date,
    outcome_date: Optional[date],
    outcome_type: OutcomeType,
    *,
    observation_window_months: int = 12,
) -> OutcomeLabels:
    """Compute time-window outcome labels for a single case.

    Args:
        prediction_date: Date the prediction was made (as-of date).
        outcome_date: Date the outcome was observed (may be None for unresolved).
        outcome_type: Outcome category.
        observation_window_months: Observation window in months (default 12).

    Returns:
        OutcomeLabels with all boolean flags set.
    """
    if outcome_date is None or outcome_date <= prediction_date:
        # No outcome observed within window or outcome predates prediction
        return OutcomeLabels(
            remained_independent_12m=(
                outcome_type in (
                    OutcomeType.REMAINED_INDEPENDENT_PERFORMED_WELL,
                    OutcomeType.REMAINED_INDEPENDENT_FAILED,
                    OutcomeType.UNKNOWN_OR_UNRESOLVED,
                )
            ),
        )

    days_to_outcome = (outcome_date - prediction_date).days

    def _within(months: int) -> bool:
        return days_to_outcome <= int(months * _DAYS_PER_MONTH)

    is_full_acq = outcome_type in FULL_ACQUISITION_OUTCOME_TYPES
    is_strategic = outcome_type in STRATEGIC_TRANSACTION_OUTCOME_TYPES
    is_license = outcome_type in LICENSE_OR_PARTNER_OUTCOME_TYPES
    is_active = outcome_type in ACTIVE_PROCESS_OUTCOME_TYPES
    is_remained = outcome_type in (
        OutcomeType.REMAINED_INDEPENDENT_PERFORMED_WELL,
        OutcomeType.REMAINED_INDEPENDENT_FAILED,
    )
    is_clinical_fail = outcome_type == OutcomeType.CLINICAL_FAILURE
    is_distressed = outcome_type in _DISTRESSED_TYPES

    return OutcomeLabels(
        acquired_within_6m=is_full_acq and _within(6),
        acquired_within_12m=is_full_acq and _within(12),
        acquired_within_24m=is_full_acq and _within(24),
        any_strategic_transaction_12m=is_strategic and _within(12),
        any_strategic_transaction_24m=is_strategic and _within(24),
        license_or_partner_12m=is_license and _within(12),
        license_or_partner_24m=is_license and _within(24),
        active_process_observed_12m=is_active and _within(12),
        remained_independent_12m=is_remained and _within(12),
        clinical_failure_12m=is_clinical_fail and _within(12),
        distressed_financing_12m=is_distressed and _within(12),
    )


def validate_as_of_integrity(
    case_dict: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Check a raw case dict for data leakage.

    Returns:
        (leakage_checks_passed, leakage_warnings)
    """
    warnings: list[str] = []
    prediction_date = _parse_date(case_dict.get("prediction_date"))
    if prediction_date is None:
        warnings.append("prediction_date is missing — cannot validate leakage")
        return False, warnings

    # Each date field must be <= prediction_date
    date_fields = {
        "source_date": "source_date",
        "feature_snapshot_date": "feature_snapshot_date",
        "acquirer_profile_as_of": "acquirer_profile_as_of",
        "market_data_as_of": "market_data_as_of",
        "clinical_data_as_of": "clinical_data_as_of",
        "regulatory_data_as_of": "regulatory_data_as_of",
    }
    for field, label in date_fields.items():
        raw = case_dict.get(field)
        if raw is None:
            continue
        d = _parse_date(raw)
        if d is None:
            continue
        if d > prediction_date:
            warnings.append(
                f"Leakage detected: {label}={d.isoformat()} > "
                f"prediction_date={prediction_date.isoformat()}"
            )

    # Outcome date must not precede prediction date (would be impossible to know)
    outcome_date = _parse_date(case_dict.get("outcome_date"))
    if outcome_date is not None and outcome_date <= prediction_date:
        warnings.append(
            f"Leakage risk: outcome_date={outcome_date.isoformat()} "
            f"<= prediction_date={prediction_date.isoformat()}; "
            "cannot know outcome at prediction time"
        )

    return len(warnings) == 0, warnings


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def create_historical_outcome_record(
    case_dict: dict[str, Any],
    *,
    config: OutcomeDatasetConfig = OutcomeDatasetConfig(),
) -> HistoricalMAOutcome:
    """Build a HistoricalMAOutcome from a raw case dict.

    The raw dict should have at minimum:
        - target_id
        - prediction_date
        - outcome_type (OutcomeType value string or enum)
        - as_of_date (defaults to prediction_date if absent)

    Optional:
        - acquirer_id, outcome_date, deal_value, premium, ...
        - layer0_snapshot, layer1_snapshot, layer2_snapshot
        - target_features (dict matching HistoricalTargetFeatures fields)
        - source_refs, leakage check date fields
    """
    leakage_ok, leakage_warnings = validate_as_of_integrity(case_dict)

    prediction_date = _parse_date(case_dict.get("prediction_date")) or date.today()
    outcome_date = _parse_date(case_dict.get("outcome_date"))
    as_of_date = _parse_date(case_dict.get("as_of_date")) or prediction_date

    outcome_type_raw = case_dict.get("outcome_type", OutcomeType.UNKNOWN_OR_UNRESOLVED)
    outcome_type = (
        OutcomeType(outcome_type_raw)
        if isinstance(outcome_type_raw, str)
        else outcome_type_raw
    )

    labels = label_outcomes(
        prediction_date=prediction_date,
        outcome_date=outcome_date,
        outcome_type=outcome_type,
        observation_window_months=config.observation_window_months,
    )

    # Target features
    tf_dict = case_dict.get("target_features") or {}
    target_features = HistoricalTargetFeatures(**{
        k: v for k, v in tf_dict.items()
        if k in HistoricalTargetFeatures.model_fields
    })

    # Acquirer features (optional)
    af_dict = case_dict.get("acquirer_features")
    acquirer_features: Optional[HistoricalAcquirerFeatures] = None
    if af_dict is not None:
        acquirer_features = HistoricalAcquirerFeatures(**{
            k: v for k, v in af_dict.items()
            if k in HistoricalAcquirerFeatures.model_fields
        })

    # Time to outcome
    time_to_outcome_days: Optional[int] = None
    if outcome_date is not None and outcome_date > prediction_date:
        time_to_outcome_days = (outcome_date - prediction_date).days

    excluded = config.exclude_leaky_cases and not leakage_ok

    return HistoricalMAOutcome(
        case_id=case_dict.get("case_id") or str(uuid.uuid4()),
        target_id=str(case_dict.get("target_id", "unknown")),
        acquirer_id=case_dict.get("acquirer_id"),
        prediction_date=prediction_date,
        outcome_date=outcome_date,
        observation_window_months=config.observation_window_months,
        as_of_date=as_of_date,
        layer0_snapshot=case_dict.get("layer0_snapshot") or {},
        layer1_snapshot=case_dict.get("layer1_snapshot") or {},
        layer2_snapshot=case_dict.get("layer2_snapshot") or {},
        layer3_snapshot=case_dict.get("layer3_snapshot"),
        layer4_snapshot=case_dict.get("layer4_snapshot"),
        target_features=target_features,
        acquirer_features=acquirer_features,
        outcome_type=outcome_type,
        deal_value=case_dict.get("deal_value"),
        premium=case_dict.get("premium"),
        consideration_mix=case_dict.get("consideration_mix"),
        deal_structure=case_dict.get("deal_structure"),
        time_to_outcome_days=time_to_outcome_days,
        successful_close=case_dict.get("successful_close"),
        reason_no_deal=case_dict.get("reason_no_deal"),
        labels=labels,
        source_refs=list(case_dict.get("source_refs") or []),
        leakage_checks_passed=leakage_ok,
        leakage_warnings=leakage_warnings,
        excluded_from_training=excluded,
        exclusion_reason="leakage_detected" if excluded else None,
    )


def build_historical_ma_outcome_dataset(
    raw_cases: list[dict[str, Any]],
    config: OutcomeDatasetConfig = OutcomeDatasetConfig(),
) -> list[HistoricalMAOutcome]:
    """Build a list of HistoricalMAOutcome from raw case dicts.

    Non-events (remained independent, false positives, etc.) are always
    retained in the dataset to avoid survivorship bias.
    """
    results: list[HistoricalMAOutcome] = []
    for case_dict in raw_cases:
        record = create_historical_outcome_record(case_dict, config=config)
        results.append(record)
    return results


def exclude_leaky_cases(
    cases: list[HistoricalMAOutcome],
) -> tuple[list[HistoricalMAOutcome], list[HistoricalMAOutcome]]:
    """Split cases into (clean, excluded).

    Returns:
        (clean_cases, excluded_cases) where clean_cases passed leakage checks.
    """
    clean = [c for c in cases if c.leakage_checks_passed and not c.excluded_from_training]
    excluded = [c for c in cases if not c.leakage_checks_passed or c.excluded_from_training]
    return clean, excluded
