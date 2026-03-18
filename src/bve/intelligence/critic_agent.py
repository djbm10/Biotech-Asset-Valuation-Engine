"""
Wave H — Critic Agent (advisory only).

Generates a structured critique of a valuation diff, surfacing the strongest
counter-arguments to the bull case.  The output is purely advisory — it does
NOT modify any valuation, score, or ranking.  Callers must never use the
critique to gate pipeline execution.

Design constraints
------------------
- Advisory only: CritiqueReport has no ``approved`` / ``block`` field.
- Stateless per invocation: no side effects beyond returning the report.
- Lightweight: all inputs come from the existing intelligence layer objects.
  No external API calls, no LLM calls.  Pattern-based heuristics only.
- Deterministic: given the same inputs the same critique is produced.

Critique dimensions
-------------------
1. Confidence sanity   — extraction_confidence vs signal complexity
2. Magnitude sanity    — delta_npv vs typical range for this event type
3. Recency staleness   — signal older than ``stale_days``
4. Phase mismatch      — early-phase signal driving large late-phase delta
5. Missing indicators  — no primary_endpoint_met / fda_action_type set
6. Concentration risk  — asset already at or above max_position_pct
7. Competitor pressure — active high-confidence competitor signals present

Each dimension returns a ``CritiqueFinding`` with a severity
(INFO / WARNING / CAUTION) and a plain-text rationale.

Usage
-----
>>> from bve.intelligence.critic_agent import CriticAgent
>>> agent = CriticAgent()
>>> report = agent.critique(signal=signal, diff=saved_diff)
>>> for f in report.findings:
...     print(f.severity, f.message)
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Finding severity
# ---------------------------------------------------------------------------

class FindingSeverity(str, Enum):
    INFO    = "info"
    WARNING = "warning"
    CAUTION = "caution"


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class CritiqueFinding(BaseModel):
    """One critic observation."""

    model_config = {"frozen": True}

    dimension: str          # short label for the check (e.g. "confidence_sanity")
    severity: FindingSeverity
    message: str            # human-readable explanation


class CritiqueReport(BaseModel):
    """
    Advisory critique of a signal + valuation diff pair.

    Attributes
    ----------
    signal_id:
        ID of the StructuredSignal being critiqued.
    diff_run_id:
        run_id of the StoredValuationDiff being critiqued.
    generated_at:
        UTC timestamp of report generation.
    findings:
        List of CritiqueFinding objects, ordered by severity descending.
    overall_severity:
        Highest severity across all findings.  None when no findings.
    n_caution:
        Count of CAUTION findings.
    n_warning:
        Count of WARNING findings.
    advisory_note:
        Pre-formatted human-readable summary of the highest-priority concerns.
    """

    signal_id: str
    diff_run_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    findings: list[CritiqueFinding] = Field(default_factory=list)
    overall_severity: Optional[FindingSeverity] = None
    n_caution: int = 0
    n_warning: int = 0
    advisory_note: str = ""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class CriticConfig(BaseModel):
    """Tunable thresholds for the critic agent."""

    model_config = {"frozen": True}

    # Confidence sanity
    min_confidence_for_high_delta: float = 0.70
    high_delta_threshold_millions: float = 50.0

    # Magnitude sanity
    extreme_delta_pct: float = 0.50    # > 50% rNPV change = extreme

    # Staleness
    stale_days: int = 90               # signal older than this is stale

    # Phase mismatch
    early_phases: frozenset[str] = frozenset({"phase_1", "phase_1a", "phase_1b"})
    large_late_phase_delta: float = 30.0  # Δnpv suggesting late-phase magnitude

    # Concentration
    max_position_pct: float = 0.20

    # Competitor pressure
    competitor_confidence_threshold: float = 0.75


# ---------------------------------------------------------------------------
# CriticAgent
# ---------------------------------------------------------------------------

class CriticAgent:
    """
    Pattern-based critique generator.  Advisory only — no side effects.

    Parameters
    ----------
    config:
        Tuning thresholds.  Defaults to ``CriticConfig()``.
    """

    def __init__(self, config: Optional[CriticConfig] = None) -> None:
        self.config = config or CriticConfig()

    def critique(
        self,
        signal: Any,
        diff: Any,
        *,
        current_position_weight: Optional[float] = None,
        competitor_signals: Optional[list[Any]] = None,
    ) -> CritiqueReport:
        """
        Generate a CritiqueReport for a (signal, diff) pair.

        Parameters
        ----------
        signal:
            A ``StructuredSignal`` instance.
        diff:
            A ``StoredValuationDiff`` instance.
        current_position_weight:
            Current portfolio weight for this asset (0.0–1.0).  When provided,
            the concentration-risk check is enabled.
        competitor_signals:
            List of recent ``StructuredSignal`` objects for competing programs.
            When provided, the competitor-pressure check is enabled.

        Returns
        -------
        CritiqueReport
        """
        findings: list[CritiqueFinding] = []
        cfg = self.config

        # 1. Confidence sanity
        findings.extend(self._check_confidence_sanity(signal, diff, cfg))

        # 2. Magnitude sanity
        findings.extend(self._check_magnitude_sanity(diff, cfg))

        # 3. Staleness
        findings.extend(self._check_staleness(signal, cfg))

        # 4. Phase mismatch
        findings.extend(self._check_phase_mismatch(signal, diff, cfg))

        # 5. Missing indicators
        findings.extend(self._check_missing_indicators(signal))

        # 6. Concentration risk
        if current_position_weight is not None:
            findings.extend(
                self._check_concentration(current_position_weight, cfg)
            )

        # 7. Competitor pressure
        if competitor_signals:
            findings.extend(
                self._check_competitor_pressure(competitor_signals, cfg)
            )

        # Sort by severity (CAUTION > WARNING > INFO)
        _order = {FindingSeverity.CAUTION: 0, FindingSeverity.WARNING: 1, FindingSeverity.INFO: 2}
        findings.sort(key=lambda f: _order.get(f.severity, 3))

        overall = findings[0].severity if findings else None
        n_caution = sum(1 for f in findings if f.severity == FindingSeverity.CAUTION)
        n_warning = sum(1 for f in findings if f.severity == FindingSeverity.WARNING)

        advisory = self._build_advisory_note(findings)

        return CritiqueReport(
            signal_id=str(getattr(signal, "id", "")),
            diff_run_id=str(getattr(diff, "run_id", "")),
            findings=findings,
            overall_severity=overall,
            n_caution=n_caution,
            n_warning=n_warning,
            advisory_note=advisory,
        )

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_confidence_sanity(
        signal: Any,
        diff: Any,
        cfg: CriticConfig,
    ) -> list[CritiqueFinding]:
        findings = []
        confidence = float(getattr(signal, "extraction_confidence", 1.0) or 0.0)
        delta_npv = abs(float(getattr(diff, "delta_npv", 0.0) or 0.0))

        if (
            delta_npv >= cfg.high_delta_threshold_millions
            and confidence < cfg.min_confidence_for_high_delta
        ):
            findings.append(CritiqueFinding(
                dimension="confidence_sanity",
                severity=FindingSeverity.CAUTION,
                message=(
                    f"Large valuation move (Δnpv ${delta_npv:.0f}M) on low-confidence "
                    f"extraction ({confidence:.0%}).  "
                    f"Consider re-extracting with a domain expert review."
                ),
            ))
        return findings

    @staticmethod
    def _check_magnitude_sanity(diff: Any, cfg: CriticConfig) -> list[CritiqueFinding]:
        findings = []
        delta_npv = float(getattr(diff, "delta_npv", 0.0) or 0.0)
        before_val = getattr(diff, "valuation_before", {}) or {}
        before_rnpv = (
            float(before_val.get("rnpv_millions") or 0.0)
            if isinstance(before_val, dict)
            else 0.0
        )

        if before_rnpv > 0:
            change_frac = abs(delta_npv) / before_rnpv
            if change_frac > cfg.extreme_delta_pct:
                findings.append(CritiqueFinding(
                    dimension="magnitude_sanity",
                    severity=FindingSeverity.WARNING,
                    message=(
                        f"Valuation change ({change_frac:.0%} of prior rNPV) exceeds "
                        f"the extreme threshold ({cfg.extreme_delta_pct:.0%}).  "
                        f"Verify that the signal magnitude is correctly calibrated."
                    ),
                ))
        return findings

    @staticmethod
    def _check_staleness(signal: Any, cfg: CriticConfig) -> list[CritiqueFinding]:
        findings = []
        signal_date = getattr(signal, "signal_date", None)
        if signal_date is not None:
            today = date.today()
            if isinstance(signal_date, datetime):
                signal_date = signal_date.date()
            age_days = (today - signal_date).days
            if age_days > cfg.stale_days:
                findings.append(CritiqueFinding(
                    dimension="staleness",
                    severity=FindingSeverity.WARNING,
                    message=(
                        f"Signal is {age_days} days old (threshold: {cfg.stale_days}).  "
                        f"Market conditions may have changed since {signal_date}."
                    ),
                ))
        return findings

    @staticmethod
    def _check_phase_mismatch(
        signal: Any,
        diff: Any,
        cfg: CriticConfig,
    ) -> list[CritiqueFinding]:
        findings = []
        phase = str(getattr(signal, "trial_phase", "") or "").lower()
        if phase in cfg.early_phases:
            delta_npv = abs(float(getattr(diff, "delta_npv", 0.0) or 0.0))
            if delta_npv >= cfg.large_late_phase_delta:
                findings.append(CritiqueFinding(
                    dimension="phase_mismatch",
                    severity=FindingSeverity.CAUTION,
                    message=(
                        f"Early-phase signal ({phase}) is driving a large valuation "
                        f"move (${delta_npv:.0f}M).  "
                        f"Early readouts carry high uncertainty — consider a wider "
                        f"bear-case scenario."
                    ),
                ))
        return findings

    @staticmethod
    def _check_missing_indicators(signal: Any) -> list[CritiqueFinding]:
        findings = []
        has_endpoint = getattr(signal, "primary_endpoint_met", None) is not None
        has_fda = getattr(signal, "fda_action_type", None) is not None
        event_type = str(getattr(signal, "event_type", "") or "")

        clinical_event = any(
            kw in event_type.lower()
            for kw in ("trial_readout", "phase", "topline", "data")
        )
        fda_event = any(
            kw in event_type.lower()
            for kw in ("fda", "approval", "advisory", "pdufa")
        )

        if clinical_event and not has_endpoint:
            findings.append(CritiqueFinding(
                dimension="missing_indicators",
                severity=FindingSeverity.INFO,
                message=(
                    "Clinical readout signal lacks primary_endpoint_met flag.  "
                    "Direction inference is based solely on Δnpv sign — verify "
                    "that the endpoint outcome was correctly parsed."
                ),
            ))
        if fda_event and not has_fda:
            findings.append(CritiqueFinding(
                dimension="missing_indicators",
                severity=FindingSeverity.INFO,
                message=(
                    "FDA-type signal lacks fda_action_type flag.  "
                    "Regulatory outcome may be ambiguous in the extracted data."
                ),
            ))
        return findings

    @staticmethod
    def _check_concentration(
        current_weight: float,
        cfg: CriticConfig,
    ) -> list[CritiqueFinding]:
        findings = []
        if current_weight >= cfg.max_position_pct:
            findings.append(CritiqueFinding(
                dimension="concentration_risk",
                severity=FindingSeverity.CAUTION,
                message=(
                    f"Position weight ({current_weight:.1%}) is at or above the "
                    f"configured maximum ({cfg.max_position_pct:.1%}).  "
                    f"Adding to this position increases concentration risk."
                ),
            ))
        return findings

    @staticmethod
    def _check_competitor_pressure(
        competitor_signals: list[Any],
        cfg: CriticConfig,
    ) -> list[CritiqueFinding]:
        findings = []
        high_conf = [
            s for s in competitor_signals
            if float(getattr(s, "extraction_confidence", 0.0) or 0.0)
               >= cfg.competitor_confidence_threshold
        ]
        if high_conf:
            n = len(high_conf)
            findings.append(CritiqueFinding(
                dimension="competitor_pressure",
                severity=FindingSeverity.WARNING,
                message=(
                    f"{n} high-confidence competitor signal(s) detected.  "
                    f"Market share assumptions may not reflect current competitive "
                    f"dynamics — consider updating the competition model."
                ),
            ))
        return findings

    # ------------------------------------------------------------------
    # Advisory note builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_advisory_note(findings: list[CritiqueFinding]) -> str:
        if not findings:
            return "No material concerns identified."
        cautions = [f for f in findings if f.severity == FindingSeverity.CAUTION]
        warnings = [f for f in findings if f.severity == FindingSeverity.WARNING]
        parts: list[str] = []
        if cautions:
            parts.append(
                f"CAUTION ({len(cautions)}): " + "; ".join(f.message[:80] for f in cautions[:2])
            )
        if warnings:
            parts.append(
                f"WARNING ({len(warnings)}): " + "; ".join(f.message[:80] for f in warnings[:2])
            )
        return "  ".join(parts)
