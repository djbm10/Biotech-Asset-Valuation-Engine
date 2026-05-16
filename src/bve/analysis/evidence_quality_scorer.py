"""
P3.3 — Evidence-quality scoring: per-component penalty multiplier on rNPV.

Each model input (peak_sales, pos, pricing, etc.) carries an EvidenceGrade.
The scorer maps each grade to a penalty multiplier, then computes a
composite penalty as the importance-weighted average across all graded
components. The composite penalty is applied to the base rNPV to produce
an evidence-adjusted (conservative) valuation.

Penalty multipliers by EvidenceGrade
--------------------------------------
CALIBRATED          1.00 — formally fitted; no haircut
EVIDENCE_INFORMED   0.93 — grounded in data; 7% haircut
JUDGMENT            0.82 — expert prior; 18% haircut
UNVALIDATED         0.68 — placeholder; 32% haircut

Default component importance weights (must sum to 1.0)
-------------------------------------------------------
pos           0.30  — P(approval) drives rNPV more than any other single input
peak_sales    0.35  — commercial peak determines ceiling
pricing       0.15  — net price per patient
market_size   0.10  — addressable patient pool or TAM fraction
trial_costs   0.05  — probability-weighted development costs
discount_rate 0.05  — cost of capital

A component not present in ``component_grades`` contributes UNVALIDATED
(the most conservative assumption) to the composite.  Override by passing
``default_missing_grade=EvidenceGrade.JUDGMENT`` if analysts have provided
partial coverage.

Usage
-----
>>> from bve.analysis.evidence_quality_scorer import EvidenceQualityScorer
>>> scorer = EvidenceQualityScorer()
>>> result = scorer.score(
...     base_rnpv_millions=250.0,
...     net_cash_millions=100.0,
...     shares_outstanding_millions=80.0,
...     component_grades={
...         "pos": EvidenceGrade.EVIDENCE_INFORMED,
...         "peak_sales": EvidenceGrade.JUDGMENT,
...         "pricing": EvidenceGrade.UNVALIDATED,
...     },
... )
>>> result.adjusted_rnpv_millions
174.3
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from bve.models.evidence_grade import EvidenceGrade


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Penalty multiplier per EvidenceGrade.
GRADE_PENALTIES: dict[str, float] = {
    EvidenceGrade.CALIBRATED.value:        1.00,
    EvidenceGrade.EVIDENCE_INFORMED.value: 0.93,
    EvidenceGrade.JUDGMENT.value:          0.82,
    EvidenceGrade.UNVALIDATED.value:       0.68,
}

#: Default importance weights for each scoreable component (must sum to 1.0).
DEFAULT_COMPONENT_WEIGHTS: dict[str, float] = {
    "peak_sales":    0.35,
    "pos":           0.30,
    "pricing":       0.15,
    "market_size":   0.10,
    "trial_costs":   0.05,
    "discount_rate": 0.05,
}

#: All recognised component names for validation.
KNOWN_COMPONENTS = frozenset(DEFAULT_COMPONENT_WEIGHTS)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceAdjustedValuation:
    """
    Evidence-quality-adjusted valuation output.

    Attributes
    ----------
    base_rnpv_millions : float
        Unadjusted rNPV from the model (before evidence quality haircut).
    composite_penalty : float
        Importance-weighted average penalty multiplier [0–1].
        1.0 = all inputs calibrated (no haircut); lower = more uncertainty.
    adjusted_rnpv_millions : float
        base_rnpv_millions × composite_penalty.
    adjusted_nav_millions : float
        adjusted_rnpv_millions + net_cash_millions.
    adjusted_nav_per_share : float
        adjusted_nav_millions / shares_outstanding_millions.
        None when shares_outstanding_millions is None or zero.
    net_cash_millions : float
        Net cash used for NAV computation (passed through unchanged).
    shares_outstanding_millions : Optional[float]
        Share count used for per-share NAV (may be None).
    component_grades : dict[str, EvidenceGrade]
        Input grade for each component scored.
    component_penalties : dict[str, float]
        Penalty multiplier applied to each component.
    component_weights : dict[str, float]
        Importance weights used for each component in the composite.
    missing_components : list[str]
        Components not supplied in component_grades; filled with default_missing_grade.
    default_missing_grade : EvidenceGrade
        Grade used for missing components (default: UNVALIDATED).
    composite_grade : EvidenceGrade
        The single grade that, uniformly applied, would produce composite_penalty.
        Nearest grade by penalty distance.
    explanation : str
        Human-readable one-paragraph explanation of the adjustment.
    """
    base_rnpv_millions: float
    composite_penalty: float
    adjusted_rnpv_millions: float
    adjusted_nav_millions: float
    adjusted_nav_per_share: Optional[float]
    net_cash_millions: float
    shares_outstanding_millions: Optional[float]
    component_grades: dict[str, EvidenceGrade]
    component_penalties: dict[str, float]
    component_weights: dict[str, float]
    missing_components: list[str]
    default_missing_grade: EvidenceGrade
    composite_grade: EvidenceGrade
    explanation: str

    @property
    def haircut_pct(self) -> float:
        """Percentage haircut applied: (1 − composite_penalty) × 100."""
        return round((1.0 - self.composite_penalty) * 100, 1)

    @property
    def all_calibrated(self) -> bool:
        """True when every supplied component is CALIBRATED."""
        return all(g == EvidenceGrade.CALIBRATED for g in self.component_grades.values())

    @property
    def has_unvalidated_inputs(self) -> bool:
        """True when any component (including missing defaults) is UNVALIDATED."""
        return (
            any(g == EvidenceGrade.UNVALIDATED for g in self.component_grades.values())
            or (
                bool(self.missing_components)
                and self.default_missing_grade == EvidenceGrade.UNVALIDATED
            )
        )

    def summary_dict(self) -> dict:
        """Flat dict of key metrics for reporting and templates."""
        return {
            "base_rnpv_millions": self.base_rnpv_millions,
            "adjusted_rnpv_millions": self.adjusted_rnpv_millions,
            "composite_penalty": self.composite_penalty,
            "haircut_pct": self.haircut_pct,
            "composite_grade": self.composite_grade.value,
            "composite_grade_label": self.composite_grade.label(),
            "adjusted_nav_millions": self.adjusted_nav_millions,
            "adjusted_nav_per_share": self.adjusted_nav_per_share,
            "has_unvalidated_inputs": self.has_unvalidated_inputs,
            "n_missing_components": len(self.missing_components),
        }


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class EvidenceQualityScorer:
    """
    Compute evidence-quality penalty multipliers and apply them to rNPV.

    Parameters
    ----------
    component_weights : dict[str, float], optional
        Importance weights per component. Must sum to 1.0. Defaults to
        ``DEFAULT_COMPONENT_WEIGHTS``.
    grade_penalties : dict[str, float], optional
        Penalty per EvidenceGrade value. Defaults to ``GRADE_PENALTIES``.
    default_missing_grade : EvidenceGrade
        Grade applied to components not in ``component_grades``. Default:
        ``EvidenceGrade.UNVALIDATED`` (most conservative).
    """

    def __init__(
        self,
        component_weights: Optional[dict[str, float]] = None,
        grade_penalties: Optional[dict[str, float]] = None,
        default_missing_grade: EvidenceGrade = EvidenceGrade.UNVALIDATED,
    ) -> None:
        self.component_weights = component_weights or DEFAULT_COMPONENT_WEIGHTS
        self.grade_penalties = grade_penalties or GRADE_PENALTIES
        self.default_missing_grade = default_missing_grade
        self._validate_weights()

    def _validate_weights(self) -> None:
        total = sum(self.component_weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"component_weights must sum to 1.0; got {total:.4f}"
            )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def component_penalty(self, grade: EvidenceGrade) -> float:
        """Return the penalty multiplier for a single EvidenceGrade."""
        return self.grade_penalties.get(grade.value, GRADE_PENALTIES[EvidenceGrade.UNVALIDATED.value])

    def score(
        self,
        base_rnpv_millions: float,
        net_cash_millions: float = 0.0,
        shares_outstanding_millions: Optional[float] = None,
        component_grades: Optional[dict[str, EvidenceGrade]] = None,
    ) -> EvidenceAdjustedValuation:
        """
        Compute evidence-adjusted valuation.

        Parameters
        ----------
        base_rnpv_millions : float
            Unadjusted rNPV from the model.
        net_cash_millions : float
            Net cash added to adjusted rNPV to derive NAV.
        shares_outstanding_millions : Optional[float]
            Used for per-share NAV; pass None to skip per-share calc.
        component_grades : dict[str, EvidenceGrade], optional
            Evidence grade for each model component. Keys should be from
            ``KNOWN_COMPONENTS``. Unrecognised keys are included with a
            UserWarning. Missing components default to ``default_missing_grade``.

        Returns
        -------
        EvidenceAdjustedValuation
        """
        grades = component_grades or {}

        # Fill in missing components
        missing = [k for k in self.component_weights if k not in grades]
        effective_grades: dict[str, EvidenceGrade] = {**grades}
        for k in missing:
            effective_grades[k] = self.default_missing_grade

        # Per-component penalties
        penalties: dict[str, float] = {
            k: self.component_penalty(g)
            for k, g in effective_grades.items()
            if k in self.component_weights
        }

        # Composite penalty = importance-weighted average of per-component penalties
        composite = sum(
            self.component_weights[k] * penalties[k]
            for k in self.component_weights
            if k in penalties
        )
        composite = round(max(0.0, min(1.0, composite)), 6)

        adjusted_rnpv = round(base_rnpv_millions * composite, 2)
        adjusted_nav = round(adjusted_rnpv + net_cash_millions, 2)
        adjusted_nav_ps: Optional[float] = None
        if shares_outstanding_millions and shares_outstanding_millions > 0:
            adjusted_nav_ps = round(adjusted_nav / shares_outstanding_millions, 2)

        composite_grade = self._nearest_grade(composite)
        explanation = self._build_explanation(
            base_rnpv_millions, adjusted_rnpv, composite, composite_grade,
            penalties, missing,
        )

        return EvidenceAdjustedValuation(
            base_rnpv_millions=round(base_rnpv_millions, 2),
            composite_penalty=composite,
            adjusted_rnpv_millions=adjusted_rnpv,
            adjusted_nav_millions=adjusted_nav,
            adjusted_nav_per_share=adjusted_nav_ps,
            net_cash_millions=round(net_cash_millions, 2),
            shares_outstanding_millions=shares_outstanding_millions,
            component_grades={k: effective_grades[k] for k in self.component_weights},
            component_penalties=penalties,
            component_weights=self.component_weights,
            missing_components=missing,
            default_missing_grade=self.default_missing_grade,
            composite_grade=composite_grade,
            explanation=explanation,
        )

    def score_from_output(
        self,
        output: object,
        component_grades: Optional[dict[str, EvidenceGrade]] = None,
    ) -> EvidenceAdjustedValuation:
        """
        Convenience wrapper: extract rNPV and company fields from a ValuationOutput.

        Parameters
        ----------
        output : ValuationOutput
            Full output from ValuationEngine.run().
        component_grades : dict[str, EvidenceGrade], optional
            Evidence grades. Falls back to output.confidence_tags when None.

        Returns
        -------
        EvidenceAdjustedValuation
        """
        rnpv = output.rnpv.rnpv_millions  # type: ignore[attr-defined]
        net_cash = output.company.net_cash_millions  # type: ignore[attr-defined]
        shares = output.company.shares_outstanding_millions  # type: ignore[attr-defined]

        grades = component_grades
        if grades is None:
            # Use confidence_tags from the output (may be empty)
            raw_tags: dict = getattr(output, "confidence_tags", {})
            grades = {
                k: EvidenceGrade(v) if isinstance(v, str) else v
                for k, v in raw_tags.items()
                if isinstance(v, (str, EvidenceGrade))
            }

        return self.score(
            base_rnpv_millions=rnpv,
            net_cash_millions=net_cash,
            shares_outstanding_millions=shares,
            component_grades=grades,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _nearest_grade(self, composite_penalty: float) -> EvidenceGrade:
        """Map a composite penalty to the nearest EvidenceGrade by penalty distance."""
        best_grade = EvidenceGrade.UNVALIDATED
        best_dist = float("inf")
        for grade in EvidenceGrade:
            penalty = self.grade_penalties.get(grade.value, 0.0)
            dist = abs(penalty - composite_penalty)
            if dist < best_dist:
                best_dist = dist
                best_grade = grade
        return best_grade

    @staticmethod
    def _build_explanation(
        base_rnpv: float,
        adjusted_rnpv: float,
        composite: float,
        composite_grade: EvidenceGrade,
        penalties: dict[str, float],
        missing: list[str],
    ) -> str:
        haircut_pct = round((1.0 - composite) * 100, 1)

        # Find the weakest component
        weakest = min(penalties, key=lambda k: penalties[k]) if penalties else None

        parts = [
            f"Evidence quality penalty: {composite:.2f}× multiplier applied "
            f"({haircut_pct:.0f}% haircut on base rNPV of ${base_rnpv:,.0f}M). "
            f"Adjusted rNPV: ${adjusted_rnpv:,.0f}M. "
            f"Composite evidence grade: {composite_grade.label()}."
        ]
        if weakest:
            parts.append(
                f" Weakest component: '{weakest}' ({penalties[weakest]:.2f}× multiplier)."
            )
        if missing:
            parts.append(
                f" {len(missing)} component(s) lacked explicit grades "
                f"and defaulted to UNVALIDATED: {', '.join(missing)}."
            )
        return "".join(parts)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def score_evidence_quality(
    base_rnpv_millions: float,
    component_grades: dict[str, EvidenceGrade],
    net_cash_millions: float = 0.0,
    shares_outstanding_millions: Optional[float] = None,
) -> EvidenceAdjustedValuation:
    """
    One-shot evidence quality scoring with default weights and penalties.

    Parameters
    ----------
    base_rnpv_millions : float
        Unadjusted model rNPV.
    component_grades : dict[str, EvidenceGrade]
        Evidence grade for each model component.
    net_cash_millions : float
        Net cash (for NAV). Default 0.
    shares_outstanding_millions : Optional[float]
        Share count for per-share NAV.

    Returns
    -------
    EvidenceAdjustedValuation
    """
    return EvidenceQualityScorer().score(
        base_rnpv_millions=base_rnpv_millions,
        net_cash_millions=net_cash_millions,
        shares_outstanding_millions=shares_outstanding_millions,
        component_grades=component_grades,
    )
