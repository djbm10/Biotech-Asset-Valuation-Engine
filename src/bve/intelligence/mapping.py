"""
Event-to-assumption mapping rules for the biotech intelligence layer.

Source of truth:
    src/bve/intelligence/config/mapping_rules.yaml

The YAML is loaded at import-time into ``EVENT_PARAMETER_MAP`` as validated
``MappingRule`` objects. This keeps mapping tunable without changing code in
``MappingEngine``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

from bve.intelligence.taxonomy import ChangeMode, EventType

# ---------------------------------------------------------------------------
# Canonical parameter namespace
# ---------------------------------------------------------------------------

#: All legal parameter paths in AssumptionChangeProposal.parameter_path.
LEGAL_PARAMETER_PATHS: frozenset[str] = frozenset({
    "trials[*].success_probability",
    "trials[*].cost_millions",
    "trials[*].duration_years",
    "market_model.addressable_patients_annual",
    "market_model.total_addressable_market_millions",
    "market_model.net_price_per_patient_usd",
    "market_model.peak_penetration",
    "market_model.patent_life_years",
    "market_model.lifecycle_events",
    "market_model.competition_model",
    "asset.discount_rate",
})

_RULES_YAML_PATH = Path(__file__).parent / "config" / "mapping_rules.yaml"


# ---------------------------------------------------------------------------
# MappingRule model
# ---------------------------------------------------------------------------

class MappingRule(BaseModel):
    """
    One row in the event-to-assumption mapping table.
    """

    event_type: EventType
    parameter: str
    change_mode: ChangeMode
    bound_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    direction_hint: Literal["increase", "decrease", "either"] = "either"
    rationale: str = ""

    @model_validator(mode="after")
    def _validate_bound_consistency(self) -> "MappingRule":
        if self.change_mode in (ChangeMode.AUTO, ChangeMode.BOUNDED):
            if self.bound_pct is None:
                raise ValueError(
                    f"MappingRule with change_mode={self.change_mode} must "
                    f"have bound_pct set (parameter: {self.parameter!r})"
                )
        elif self.change_mode == ChangeMode.MANUAL:
            if self.bound_pct is not None:
                raise ValueError(
                    f"MappingRule with change_mode=MANUAL must have "
                    f"bound_pct=None (parameter: {self.parameter!r})"
                )
        return self


def _load_event_parameter_map(path: Path = _RULES_YAML_PATH) -> dict[EventType, list[MappingRule]]:
    """
    Load mapping rules from YAML into validated ``MappingRule`` objects.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid mapping rules file {path}: expected top-level mapping")

    table: dict[EventType, list[MappingRule]] = {}
    for event_key, rules in raw.items():
        event_type = EventType(event_key)
        if not isinstance(rules, list):
            raise ValueError(f"Invalid rules entry for {event_key!r}: expected list")
        parsed_rules: list[MappingRule] = []
        for rule in rules:
            if not isinstance(rule, dict):
                raise ValueError(
                    f"Invalid rule for {event_key!r}: expected mapping, got {type(rule).__name__}"
                )
            parsed_rules.append(
                MappingRule(
                    event_type=event_type,
                    parameter=rule["parameter"],
                    change_mode=ChangeMode(rule["change_mode"]),
                    bound_pct=rule.get("bound_pct"),
                    direction_hint=rule.get("direction_hint", "either"),
                    rationale=rule.get("rationale", ""),
                )
            )
        table[event_type] = parsed_rules

    missing = set(EventType) - set(table)
    if missing:
        missing_values = ", ".join(sorted(e.value for e in missing))
        raise ValueError(
            f"Mapping rules file {path} missing event types: {missing_values}"
        )
    return table


#: Master mapping table loaded from YAML.
EVENT_PARAMETER_MAP: dict[EventType, list[MappingRule]] = _load_event_parameter_map()


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def rules_for(event_type: EventType) -> list[MappingRule]:
    """Return all mapping rules for *event_type*."""
    return EVENT_PARAMETER_MAP.get(event_type, [])


def auto_rules(event_type: EventType) -> list[MappingRule]:
    """Return only AUTO-mode rules for *event_type*."""
    return [r for r in rules_for(event_type) if r.change_mode == ChangeMode.AUTO]


def requires_review(event_type: EventType) -> bool:
    """True if *event_type* has any MANUAL or BOUNDED rules."""
    return any(
        r.change_mode in (ChangeMode.MANUAL, ChangeMode.BOUNDED)
        for r in rules_for(event_type)
    )
