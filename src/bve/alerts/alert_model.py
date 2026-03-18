"""
Alert data model for the BVE alerting layer.

AlertSeverity ordering: LOW < MEDIUM < HIGH < CRITICAL.
AlertTrigger identifies which condition fired the alert.
Alert is a frozen, immutable record — once created it never changes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class AlertSeverity(str, Enum):
    LOW      = "low"       # informational
    MEDIUM   = "medium"    # review-required (material change OR low-conf on critical event)
    HIGH     = "high"      # FDA events, regulatory hold
    CRITICAL = "critical"  # safety signal, program discontinuation


_SEVERITY_ORDER: dict[AlertSeverity, int] = {
    AlertSeverity.LOW:      0,
    AlertSeverity.MEDIUM:   1,
    AlertSeverity.HIGH:     2,
    AlertSeverity.CRITICAL: 3,
}


def severity_gte(s: AlertSeverity, threshold: AlertSeverity) -> bool:
    """Returns True if *s* is at least as severe as *threshold*."""
    return _SEVERITY_ORDER[s] >= _SEVERITY_ORDER[threshold]


class AlertTrigger(str, Enum):
    SAFETY_SIGNAL_DETECTED          = "safety_signal_detected"
    MATERIAL_VALUATION_CHANGE       = "material_valuation_change"
    LOW_CONFIDENCE_HIGH_SEVERITY    = "low_confidence_high_severity"
    LOW_STATISTICAL_POWER           = "low_statistical_power"
    SYSTEM_COST_LIMIT_REACHED       = "system_cost_limit_reached"
    ENROLLMENT_SITE_STALLING        = "enrollment_site_stalling"
    ENROLLMENT_VELOCITY_LOW         = "enrollment_velocity_low"
    CATALYST_APPROACHING            = "catalyst_approaching"
    CAPITAL_RISK_HIGH               = "capital_risk_high"
    UNUSUAL_VOLUME_BEFORE_CATALYST  = "unusual_volume_before_catalyst"


class Alert(BaseModel):
    """Immutable alert record created when a trigger condition fires."""

    model_config = {"frozen": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    severity: AlertSeverity
    trigger: AlertTrigger
    asset_id: str
    company_id: str
    run_id: Optional[str] = None
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Contextual metadata
    signal_event_type: Optional[str] = None
    valuation_delta_npv: Optional[float] = None
    extraction_confidence: Optional[float] = None
