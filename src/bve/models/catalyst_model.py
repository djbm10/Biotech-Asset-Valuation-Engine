"""Catalyst scoring layer used by opportunity ranking (not valuation math)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field

from bve.intelligence.knowledge_layer import KnowledgeStore


def _default_calibration_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "catalyst_calibration.yaml"


class CatalystMoveProfile(BaseModel):
    """Historical move profile for one catalyst type (optionally phase-specific)."""

    model_config = {"frozen": True}

    event_type: str
    phase: Optional[str] = None
    p_positive_outcome: float = Field(ge=0.0, le=1.0)
    median_move_positive_pct: float = Field(ge=0.0)
    median_move_negative_pct: float = Field(ge=0.0)
    move_volatility: float = Field(ge=0.0)
    n_observations: int = Field(ge=0)
    last_calibrated: str


class CatalystValuation(BaseModel):
    """Expected directional move for a catalyst event."""

    event_key: str
    asset_id: str
    event_type: str
    catalyst_date: Optional[date] = None
    days_to_catalyst: Optional[int] = None
    # Base catalyst prior from calibration profile (not design-adjusted).
    p_positive_outcome: float = Field(ge=0.0, le=1.0)
    # Design-adjusted probability exposed for auditability.
    design_adjusted_p_positive_outcome: float = Field(ge=0.0, le=1.0)
    # Confidence-layer multiplier only (used by ranking, never valuation math).
    design_quality_multiplier: float = Field(gt=0.0)
    expected_return_pct: float
    expected_move_magnitude_pct: float = Field(ge=0.0)
    current_price: Optional[float] = None
    expected_move_dollars: Optional[float] = None
    profile_source: Literal["calibrated", "default", "override"]


_DEFAULT_PROFILE = CatalystMoveProfile(
    event_type="unknown",
    phase=None,
    p_positive_outcome=0.5,
    median_move_positive_pct=12.0,
    median_move_negative_pct=14.0,
    move_volatility=0.15,
    n_observations=0,
    last_calibrated="1970-01-01",
)


class CatalystModel:
    """Loads calibrated catalyst profiles and scores expected move/return."""

    def __init__(
        self,
        store: KnowledgeStore,
        calibration_path: Optional[Path] = None,
    ) -> None:
        self._store = store
        self._calibration_path = calibration_path or _default_calibration_path()
        self._profiles = self.load_profiles()

    @staticmethod
    def _key(event_type: str, phase: Optional[str]) -> str:
        phase_key = (phase or "").strip().lower()
        if phase_key:
            return f"{event_type.strip().lower()}::{phase_key}"
        return event_type.strip().lower()

    def load_profiles(self) -> dict[str, CatalystMoveProfile]:
        """Load profile map keyed by `event_type` or `event_type::phase`."""
        path = self._calibration_path
        if not path.exists():
            return {}

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rows = raw.get("profiles") or []
        out: dict[str, CatalystMoveProfile] = {}
        for row in rows:
            try:
                profile = CatalystMoveProfile.model_validate(row)
            except Exception:
                continue
            out[self._key(profile.event_type, profile.phase)] = profile
        return out

    def _resolve_profile(
        self,
        *,
        event_type: str,
        phase: Optional[str],
        override: Optional[dict[str, object]] = None,
    ) -> tuple[CatalystMoveProfile, Literal["calibrated", "default", "override"]]:
        if override:
            merged = _DEFAULT_PROFILE.model_dump(mode="json")
            merged.update(override)
            merged["event_type"] = event_type
            merged["phase"] = phase
            return CatalystMoveProfile.model_validate(merged), "override"

        exact = self._profiles.get(self._key(event_type, phase))
        if exact is not None:
            return exact, "calibrated"

        fallback = self._profiles.get(self._key(event_type, None))
        if fallback is not None:
            return fallback, "calibrated"

        return _DEFAULT_PROFILE, "default"

    def score_catalyst(
        self,
        event_type: str,
        phase: Optional[str],
        signal_id: Optional[str] = None,
        *,
        event_key: Optional[str] = None,
        asset_id: Optional[str] = None,
        catalyst_date: Optional[date] = None,
        days_to_catalyst: Optional[int] = None,
        current_price: Optional[float] = None,
        override: Optional[dict[str, object]] = None,
    ) -> CatalystValuation:
        """Score one catalyst event using calibrated move priors."""
        profile, profile_source = self._resolve_profile(
            event_type=event_type,
            phase=phase,
            override=override,
        )

        design_multiplier = 1.0
        if signal_id:
            assessment = self._store.get_design_assessment(signal_id)
            if assessment is not None:
                design_multiplier = float(assessment.design_quality_multiplier)

        base_p_positive = profile.p_positive_outcome
        adjusted_p_positive = min(1.0, max(0.0, base_p_positive * design_multiplier))

        expected_return_pct = (
            base_p_positive * profile.median_move_positive_pct
            - (1.0 - base_p_positive) * profile.median_move_negative_pct
        )
        expected_move_magnitude_pct = (
            base_p_positive * profile.median_move_positive_pct
            + (1.0 - base_p_positive) * profile.median_move_negative_pct
        )

        expected_move_dollars: Optional[float] = None
        if current_price is not None:
            expected_move_dollars = current_price * (expected_move_magnitude_pct / 100.0)

        return CatalystValuation(
            event_key=event_key or (signal_id or "unknown"),
            asset_id=asset_id or "unknown",
            event_type=event_type,
            catalyst_date=catalyst_date,
            days_to_catalyst=days_to_catalyst,
            p_positive_outcome=round(base_p_positive, 6),
            design_adjusted_p_positive_outcome=round(adjusted_p_positive, 6),
            design_quality_multiplier=round(design_multiplier, 6),
            expected_return_pct=round(expected_return_pct, 6),
            expected_move_magnitude_pct=round(expected_move_magnitude_pct, 6),
            current_price=current_price,
            expected_move_dollars=(
                round(expected_move_dollars, 6) if expected_move_dollars is not None else None
            ),
            profile_source=profile_source,
        )
