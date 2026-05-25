"""Layer 5 — 5B: No-Lookahead Historical Replay.

Validates that layer snapshots contain no future data relative to the
prediction date, and provides a skeleton for reconstructing layer outputs
as they would have appeared on a given as-of date.

Hard rules:
  - source_date            <= prediction_date
  - feature_snapshot_date  <= prediction_date
  - acquirer_profile_as_of <= prediction_date
  - market_data_as_of      <= prediction_date
  - clinical_data_as_of    <= prediction_date
  - regulatory_data_as_of  <= prediction_date

If any rule fails:
  - leakage_checks_passed = False
  - leakage_warnings populated
  - case excluded from training by default
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from bve.intelligence.ma_calibration_models import HistoricalMAOutcome


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------

_DATE_FIELDS = (
    "source_date",
    "feature_snapshot_date",
    "acquirer_profile_as_of",
    "market_data_as_of",
    "clinical_data_as_of",
    "regulatory_data_as_of",
)


def _coerce_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def validate_as_of_integrity(
    snapshot: dict[str, Any],
    prediction_date: date,
) -> tuple[bool, list[str]]:
    """Validate a snapshot dict against the prediction_date.

    Args:
        snapshot: Dict that may contain date-stamped source fields.
        prediction_date: The as-of date for the prediction.

    Returns:
        (passed, warnings) where passed=True means no leakage detected.
    """
    warnings: list[str] = []
    for field in _DATE_FIELDS:
        raw = snapshot.get(field)
        if raw is None:
            continue
        d = _coerce_date(raw)
        if d is None:
            continue
        if d > prediction_date:
            warnings.append(
                f"No-lookahead violation: {field}={d.isoformat()} > "
                f"prediction_date={prediction_date.isoformat()}"
            )
    return len(warnings) == 0, warnings


def snapshot_layers_as_of(
    layer0: dict[str, Any],
    layer1: dict[str, Any],
    layer2: dict[str, Any],
    prediction_date: date,
    *,
    layer3: Optional[dict[str, Any]] = None,
    layer4: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Return a validated snapshot bundle keyed by layer.

    Validates each layer snapshot against prediction_date and marks any that
    contain future data. Does NOT mutate input dicts.
    """
    bundle: dict[str, Any] = {}
    for name, snap in (
        ("layer0", layer0),
        ("layer1", layer1),
        ("layer2", layer2),
        ("layer3", layer3),
        ("layer4", layer4),
    ):
        if snap is None:
            continue
        passed, warnings = validate_as_of_integrity(snap, prediction_date)
        bundle[name] = {
            "snapshot": snap,
            "leakage_checks_passed": passed,
            "leakage_warnings": warnings,
        }
    return bundle


def run_no_lookahead_replay(
    case: HistoricalMAOutcome,
    *,
    additional_snapshots: Optional[dict[str, Any]] = None,
) -> tuple[bool, list[str]]:
    """Run full no-lookahead integrity check on a HistoricalMAOutcome.

    Args:
        case: The historical case to validate.
        additional_snapshots: Optional extra snapshot dicts (e.g. external sources).

    Returns:
        (all_passed, all_warnings)
    """
    all_warnings: list[str] = list(case.leakage_warnings)

    # Re-validate each stored snapshot against prediction_date
    for layer_name, snap in (
        ("layer0", case.layer0_snapshot),
        ("layer1", case.layer1_snapshot),
        ("layer2", case.layer2_snapshot),
        ("layer3", case.layer3_snapshot),
        ("layer4", case.layer4_snapshot),
    ):
        if not snap:
            continue
        passed, warnings = validate_as_of_integrity(snap, case.prediction_date)
        for w in warnings:
            all_warnings.append(f"[{layer_name}] {w}")

    # Check any extra snapshots
    for key, snap in (additional_snapshots or {}).items():
        if not snap:
            continue
        passed, warnings = validate_as_of_integrity(snap, case.prediction_date)
        for w in warnings:
            all_warnings.append(f"[{key}] {w}")

    # Outcome date must be after prediction date (otherwise we knew the outcome)
    if case.outcome_date is not None and case.outcome_date <= case.prediction_date:
        all_warnings.append(
            f"outcome_date={case.outcome_date.isoformat()} <= "
            f"prediction_date={case.prediction_date.isoformat()}; "
            "outcome was known at prediction time — leakage"
        )

    return len(all_warnings) == 0, all_warnings


def replay_ma_pipeline_as_of(
    raw_layer_outputs: dict[str, Any],
    prediction_date: date,
) -> dict[str, Any]:
    """Validate raw layer outputs and return replay-validated bundle.

    This is the adapter for historical replay: takes the outputs that would
    have been produced on prediction_date and validates them for no-lookahead
    compliance.

    Returns a dict with:
        - validated_snapshots: per-layer validated snapshot bundles
        - all_passed: True if no leakage detected
        - warnings: list of leakage warnings
    """
    l0 = raw_layer_outputs.get("layer0") or {}
    l1 = raw_layer_outputs.get("layer1") or {}
    l2 = raw_layer_outputs.get("layer2") or {}
    l3 = raw_layer_outputs.get("layer3")
    l4 = raw_layer_outputs.get("layer4")

    validated = snapshot_layers_as_of(
        l0, l1, l2, prediction_date, layer3=l3, layer4=l4
    )
    all_warnings: list[str] = []
    for layer_name, bundle in validated.items():
        all_warnings.extend(bundle.get("leakage_warnings") or [])

    return {
        "validated_snapshots": validated,
        "all_passed": len(all_warnings) == 0,
        "warnings": all_warnings,
        "prediction_date": prediction_date.isoformat(),
    }
