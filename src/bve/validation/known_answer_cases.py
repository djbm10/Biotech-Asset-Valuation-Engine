"""KnownAnswerCase — typed definition for a historical deal validation case.

Each case records the observable facts of a completed biotech acquisition and
the expected range a well-calibrated BVE run should produce. Cases are loaded
from ``known_answers/cases.yaml`` (or a user-supplied path) and are entirely
editable without code changes.

Design notes
------------
- ``KnownAnswerCase`` is a frozen dataclass; load via ``load_cases()``.
- The YAML schema is validated at load time; malformed cases are skipped with
  a warning rather than crashing the entire suite.
- ``_DEFAULT_CASES_PATH`` points to the bundled starter cases; callers can
  override with any YAML file that follows the same schema.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_DEFAULT_CASES_PATH: Path = Path(__file__).parent / "known_answers" / "cases.yaml"


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KnownAnswerCase:
    """One historical deal used as a directional validation anchor.

    Parameters
    ----------
    case_id:
        Unique identifier (e.g. ``"prometheus_merck_2023"``).
    company_name:
        Target company name (e.g. ``"Prometheus Biosciences"``).
    ticker:
        Stock ticker at the time of the deal (optional).
    description:
        Plain-English deal description.
    deal_year:
        Year the deal closed or was announced.
    observed_deal_value_millions:
        Actual acquisition price in USD millions.
    deal_premium_pct:
        Reported premium to unaffected stock price (percent). Optional.
    expected_deal_type:
        Expected deal classification (e.g. ``"acquisition"``).
    expected_primary_buyer:
        Name of the expected acquirer.
    expected_buyer_therapeutic_areas:
        List of TA strings the buyer operates in.
    model_value_range_millions_low:
        Lower bound of the expected BVE rNPV range.
    model_value_range_millions_high:
        Upper bound of the expected BVE rNPV range.
    thesis_direction:
        Expected model signal: ``"long"`` (acquisition target) or ``"short"``.
    validation_notes:
        Optional free-text annotation explaining the case rationale.
    """

    case_id: str
    company_name: str
    deal_year: int
    observed_deal_value_millions: float
    expected_deal_type: str
    expected_primary_buyer: str
    model_value_range_millions_low: float
    model_value_range_millions_high: float
    thesis_direction: str
    ticker: Optional[str] = None
    description: str = ""
    deal_premium_pct: Optional[float] = None
    expected_buyer_therapeutic_areas: tuple[str, ...] = field(default_factory=tuple)
    validation_notes: Optional[str] = None

    @property
    def range_midpoint_millions(self) -> float:
        return (self.model_value_range_millions_low + self.model_value_range_millions_high) / 2.0

    @property
    def range_width_millions(self) -> float:
        return self.model_value_range_millions_high - self.model_value_range_millions_low


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_cases(path: Optional[str | Path] = None) -> list[KnownAnswerCase]:
    """Load KnownAnswerCase objects from a YAML file.

    Parameters
    ----------
    path:
        Path to YAML file. Defaults to the bundled ``cases.yaml``.

    Returns
    -------
    list[KnownAnswerCase]
        Successfully parsed cases. Malformed entries are skipped with a
        ``UserWarning``; an empty list is returned when the file is missing.
    """
    import yaml

    yaml_path = Path(path) if path else _DEFAULT_CASES_PATH

    if not yaml_path.exists():
        warnings.warn(
            f"Known-answer cases file not found: {yaml_path}. "
            "No cases loaded.",
            UserWarning,
            stacklevel=2,
        )
        return []

    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        warnings.warn(
            f"Could not parse known-answer cases YAML ({yaml_path}): {exc}",
            UserWarning,
            stacklevel=2,
        )
        return []

    raw_cases = raw.get("cases") or []
    result: list[KnownAnswerCase] = []

    for entry in raw_cases:
        try:
            result.append(_parse_case(entry))
        except Exception as exc:
            cid = entry.get("case_id", "<unknown>") if isinstance(entry, dict) else "<unknown>"
            warnings.warn(
                f"Skipping malformed known-answer case '{cid}': {exc}",
                UserWarning,
                stacklevel=2,
            )

    return result


def _parse_case(entry: dict) -> KnownAnswerCase:
    """Parse one raw YAML dict into a KnownAnswerCase."""
    required = (
        "case_id", "company_name", "deal_year",
        "observed_deal_value_millions", "expected_deal_type",
        "expected_primary_buyer", "model_value_range_millions_low",
        "model_value_range_millions_high", "thesis_direction",
    )
    for key in required:
        if key not in entry:
            raise ValueError(f"Missing required field: {key!r}")

    low = float(entry["model_value_range_millions_low"])
    high = float(entry["model_value_range_millions_high"])
    if high < low:
        raise ValueError(
            f"model_value_range_millions_high ({high}) must be >= low ({low})"
        )
    if float(entry["observed_deal_value_millions"]) <= 0:
        raise ValueError("observed_deal_value_millions must be positive")

    ta_list = entry.get("expected_buyer_therapeutic_areas") or []
    ta_tuple = tuple(str(t) for t in ta_list)

    return KnownAnswerCase(
        case_id=str(entry["case_id"]),
        company_name=str(entry["company_name"]),
        ticker=str(entry["ticker"]) if entry.get("ticker") else None,
        description=str(entry.get("description") or "").strip(),
        deal_year=int(entry["deal_year"]),
        observed_deal_value_millions=float(entry["observed_deal_value_millions"]),
        deal_premium_pct=float(entry["deal_premium_pct"]) if entry.get("deal_premium_pct") is not None else None,
        expected_deal_type=str(entry["expected_deal_type"]),
        expected_primary_buyer=str(entry["expected_primary_buyer"]),
        expected_buyer_therapeutic_areas=ta_tuple,
        model_value_range_millions_low=low,
        model_value_range_millions_high=high,
        thesis_direction=str(entry["thesis_direction"]),
        validation_notes=str(entry["validation_notes"]).strip() if entry.get("validation_notes") else None,
    )
