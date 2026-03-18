"""
Pydantic configuration models for the alerting layer.

All optional dependencies (requests, smtplib wrappers) are guarded at
channel-instantiation time; this config module has zero non-stdlib imports.
Environment variable expansion is supported for secrets via os.path.expandvars.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SlackChannelConfig(BaseModel):
    webhook_url: str
    min_severity: str = "medium"

    @field_validator("webhook_url")
    @classmethod
    def _expand_env(cls, v: str) -> str:
        return os.path.expandvars(v)


class EmailChannelConfig(BaseModel):
    smtp_host: str
    smtp_port: int = Field(default=587, ge=1, le=65535)
    username: str
    password: str
    from_addr: str
    to_addrs: list[str] = Field(min_length=1)
    use_tls: bool = True
    subject_prefix: str = "[BVE Alert]"
    min_severity: str = "medium"

    @field_validator("password", "username")
    @classmethod
    def _expand_env(cls, v: str) -> str:
        return os.path.expandvars(v)


class TelegramChannelConfig(BaseModel):
    bot_token: str
    chat_id: str
    min_severity: str = "medium"

    @field_validator("bot_token")
    @classmethod
    def _expand_env(cls, v: str) -> str:
        return os.path.expandvars(v)


class LocalChannelConfig(BaseModel):
    output_path: str = "outputs/watchlist/alerts.jsonl"
    min_severity: str = "low"


class AlertThresholdsConfig(BaseModel):
    """Numeric trigger thresholds for all three conditions."""

    # Condition 2: material valuation change — must pass BOTH tests.
    # Absolute floor prevents noise from small-NPV programs ($5M → $7M = 40% but irrelevant).
    material_change_abs_floor_millions: float = Field(default=25.0, ge=0.0)
    material_change_pct: float = Field(default=15.0, ge=0.0)

    # Condition 3: low confidence on critical event type.
    # Severity is MEDIUM (not LOW) because it signals potential model corruption.
    low_confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    high_severity_event_types: list[str] = Field(
        default_factory=lambda: [
            "safety_signal",
            "fda_approval",
            "fda_rejection",
            "fda_designation",
            "regulatory_hold",
            "program_discontinuation",
        ]
    )

    # Dedup window: suppress duplicate alerts for the same (asset, event_type, trigger).
    dedup_window_hours: float = Field(default=24.0, ge=0.0)
    dedup_state_path: str = "outputs/watchlist/alert_dedup.json"


class SuppressionRule(BaseModel):
    """
    Suppress alerts for a specific asset/event combination until a given datetime.

    Useful for known events under active review where alert fatigue is a concern.
    All fields except `until` are optional matchers — a None field matches anything.
    """

    asset_id: Optional[str] = None
    event_type: Optional[str] = None
    trigger: Optional[str] = None
    until: datetime  # UTC; rule expires after this datetime


class AlertsConfig(BaseModel):
    enabled: bool = True
    thresholds: AlertThresholdsConfig = Field(default_factory=AlertThresholdsConfig)
    local: Optional[LocalChannelConfig] = None
    slack: Optional[SlackChannelConfig] = None
    email: Optional[EmailChannelConfig] = None
    telegram: Optional[TelegramChannelConfig] = None
    # Suppression rules: matched alerts are silently dropped until `until`.
    suppression_rules: list[SuppressionRule] = Field(default_factory=list)
