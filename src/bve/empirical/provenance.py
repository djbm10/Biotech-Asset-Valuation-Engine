"""
Prediction provenance — structured explanation of every EmpiricalPOS prediction.

Every call to EmpiricalPOSEngine.compute_pos_with_provenance() returns both
the final probability AND a POSProvenance object that shows exactly how the
prediction was computed: which cell was matched, what the fallback tier was,
what heuristic adjusters contributed, whether sponsor history was used, and
whether there is a thin-data warning.

Design principle: no hidden computations. The provenance object contains
enough information to fully reproduce the prediction by hand.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Fallback tier labels (in descending specificity order)
# ---------------------------------------------------------------------------

TIER_FULL = "phase+moa+biomarker"          # most specific
TIER_PHASE_MOA = "phase+moa"
TIER_PHASE_BIO = "phase+biomarker"
TIER_PHASE = "phase_only"
TIER_PUBLISHED = "published_fallback"      # least specific


@dataclass
class LookupProvenance:
    """Which stratification cell was matched and what it contained."""
    cell_key: str       # human-readable key, e.g. "('phase_2', 'novel')"
    fallback_tier: str  # one of the TIER_* constants above
    n: int              # raw count in the matched cell
    n_success: int      # raw success count
    smoothed_rate: float  # Laplace-smoothed rate returned as base
    is_published_fallback: bool = False

    @property
    def specificity_rank(self) -> int:
        """Lower = more specific (1 = most specific, 5 = published fallback)."""
        order = [TIER_FULL, TIER_PHASE_MOA, TIER_PHASE_BIO, TIER_PHASE, TIER_PUBLISHED]
        try:
            return order.index(self.fallback_tier) + 1
        except ValueError:
            return 99

    def __str__(self) -> str:
        fb = " [PUBLISHED FALLBACK]" if self.is_published_fallback else ""
        return (
            f"LookupProvenance(key={self.cell_key}, tier={self.fallback_tier}, "
            f"n={self.n}, n_success={self.n_success}, "
            f"smoothed={self.smoothed_rate:.3f}{fb})"
        )


@dataclass
class SponsorContribution:
    """Sponsor track record blending applied to the base empirical rate."""
    sponsor: str
    n_sponsor_total: int
    n_sponsor_phase: int
    n_sponsor_phase_success: int
    sponsor_phase_rate: float       # raw sponsor success rate for this phase
    prior_weight: float             # effective prior count used for shrinkage
    blend_weight: float             # fraction from sponsor data
    blended_rate: float             # result after shrinkage toward cell rate
    log_odds_delta: float           # change in log-odds from sponsor blending

    def __str__(self) -> str:
        return (
            f"SponsorContribution({self.sponsor!r}, "
            f"n_phase={self.n_sponsor_phase}, "
            f"sponsor_rate={self.sponsor_phase_rate:.1%} → "
            f"blended={self.blended_rate:.1%}, "
            f"Δlog-odds={self.log_odds_delta:+.3f})"
        )


@dataclass
class HeuristicAdjustment:
    """One heuristic log-odds adjuster applied on top of the empirical base."""
    name: str
    value: str      # human-readable enum value
    log_odds: float

    def __str__(self) -> str:
        return f"{self.name}={self.value!r} → {self.log_odds:+.3f} log-odds"


@dataclass
class FittedOverlayContribution:
    """
    Fitted logistic regression overlay applied instead of heuristic adjusters.

    Attributes are ordered to mirror the computation:
      1. feature_names, feature_values  — binary indicators (11 features)
      2. feature_contributions          — feature_value × coefficient per feature
      3. intercept                      — global bias term
      4. net_log_odds_delta             — intercept + Σ feature_contributions
    """
    feature_names: list[str]
    feature_values: list[float]         # 0.0 or 1.0 for each feature
    feature_contributions: list[float]  # feature_value × coefficient
    intercept: float                    # global bias (not regularized)
    net_log_odds_delta: float           # total shift: intercept + Σ contributions

    def active_features(self) -> list[tuple[str, float]]:
        """Return (feature_name, contribution) pairs where feature_value == 1."""
        return [
            (name, contrib)
            for name, val, contrib in zip(
                self.feature_names, self.feature_values, self.feature_contributions
            )
            if val > 0.0
        ]

    def __str__(self) -> str:
        active = self.active_features()
        if not active:
            return (
                f"FittedOverlay(all_baseline, intercept={self.intercept:+.4f},"
                f" net_Δ={self.net_log_odds_delta:+.4f})"
            )
        parts = ", ".join(f"{n}:{c:+.4f}" for n, c in active)
        return (
            f"FittedOverlay(intercept={self.intercept:+.4f}, "
            f"active=[{parts}], net_Δ={self.net_log_odds_delta:+.4f})"
        )


@dataclass
class POSProvenance:
    """
    Full decomposition of one EmpiricalPOS prediction.

    Attributes are ordered to mirror the computation pipeline:
      1. Lookup → base empirical rate
      2. Sponsor blending (optional)
      3. Heuristic adjusters (optional)
      4. Calibration (optional)
      5. Final probability
      6. Warnings
    """
    # --- Context ---
    phase: str
    moa_precedent: Optional[str]
    biomarker_selected: Optional[bool]
    sponsor: Optional[str]

    # --- Step 1: empirical base rate ---
    lookup: LookupProvenance
    base_empirical_rate: float
    base_empirical_log_odds: float

    # --- Step 2: sponsor blending ---
    sponsor_contribution: Optional[SponsorContribution] = None
    rate_after_sponsor: Optional[float] = None
    log_odds_after_sponsor: Optional[float] = None

    # --- Step 3a: heuristic adjusters (empirical_raw / empirical_calibrated modes) ---
    heuristic_adjustments: list[HeuristicAdjustment] = field(default_factory=list)
    net_heuristic_adjustment: float = 0.0
    capped_heuristic_adjustment: float = 0.0  # after ±0.80 cap
    log_odds_after_adjusters: float = 0.0

    # --- Step 3b: fitted overlay (empirical_fitted mode; alternative to heuristic) ---
    overlay_contribution: Optional[FittedOverlayContribution] = None
    rate_after_overlay: Optional[float] = None
    log_odds_after_overlay: Optional[float] = None

    # --- Step 4: calibration ---
    calibrated: bool = False
    pre_calibration_pos: Optional[float] = None
    calibration_method: Optional[str] = None
    calibrated_pos: Optional[float] = None

    # --- Step 5: final ---
    final_pos: float = 0.0

    # --- Step 6: warnings ---
    thin_data_warning: Optional[str] = None

    @property
    def has_thin_data(self) -> bool:
        return self.thin_data_warning is not None

    def summary(self) -> str:
        """Multi-line human-readable decomposition."""
        lines = [
            f"POS Provenance — {self.phase} / moa={self.moa_precedent} / bio={self.biomarker_selected}",
            f"  1. Empirical base    : {self.base_empirical_rate:.3f} ({self.lookup.fallback_tier}, n={self.lookup.n})",
        ]
        if self.sponsor_contribution is not None:
            sc = self.sponsor_contribution
            lines.append(
                f"  2. Sponsor blend     : {self.rate_after_sponsor:.3f} "
                f"({sc.sponsor!r} n_phase={sc.n_sponsor_phase}, "
                f"Δlog-odds={sc.log_odds_delta:+.3f})"
            )
        else:
            lines.append("  2. Sponsor blend     : n/a")
        if self.overlay_contribution is not None:
            oc = self.overlay_contribution
            lines.append(
                f"  3b. Fitted overlay   : {self.rate_after_overlay:.3f} "
                f"(Δlog-odds={oc.net_log_odds_delta:+.3f})"
            )
            for name, contrib in oc.active_features():
                lines.append(f"       {name}: {contrib:+.4f}")
            if not oc.active_features():
                lines.append(f"       (all features at baseline)")
        elif self.heuristic_adjustments:
            lines.append(f"  3a. Heuristic adj.   : {self.net_heuristic_adjustment:+.3f} log-odds (capped: {self.capped_heuristic_adjustment:+.3f})")
            for adj in self.heuristic_adjustments:
                lines.append(f"       {adj}")
        else:
            lines.append("  3. Adjusters         : none")
        if self.calibrated and self.calibrated_pos is not None:
            lines.append(
                f"  4. Calibration       : {self.pre_calibration_pos:.3f} → "
                f"{self.calibrated_pos:.3f} ({self.calibration_method})"
            )
        else:
            lines.append("  4. Calibration       : not applied")
        lines.append(f"  5. Final POS         : {self.final_pos:.3f} ({self.final_pos:.1%})")
        if self.thin_data_warning:
            lines.append(f"  ⚠️  Warning          : {self.thin_data_warning}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """JSON-serializable representation."""
        return {
            "phase": self.phase,
            "moa_precedent": self.moa_precedent,
            "biomarker_selected": self.biomarker_selected,
            "sponsor": self.sponsor,
            "lookup": {
                "cell_key": self.lookup.cell_key,
                "fallback_tier": self.lookup.fallback_tier,
                "n": self.lookup.n,
                "n_success": self.lookup.n_success,
                "smoothed_rate": self.lookup.smoothed_rate,
                "is_published_fallback": self.lookup.is_published_fallback,
            },
            "base_empirical_rate": self.base_empirical_rate,
            "base_empirical_log_odds": self.base_empirical_log_odds,
            "sponsor_contribution": (
                {
                    "sponsor": self.sponsor_contribution.sponsor,
                    "n_sponsor_phase": self.sponsor_contribution.n_sponsor_phase,
                    "sponsor_phase_rate": self.sponsor_contribution.sponsor_phase_rate,
                    "blended_rate": self.sponsor_contribution.blended_rate,
                    "log_odds_delta": self.sponsor_contribution.log_odds_delta,
                }
                if self.sponsor_contribution else None
            ),
            "heuristic_adjustments": [
                {"name": a.name, "value": a.value, "log_odds": a.log_odds}
                for a in self.heuristic_adjustments
            ],
            "net_heuristic_adjustment": self.net_heuristic_adjustment,
            "capped_heuristic_adjustment": self.capped_heuristic_adjustment,
            "log_odds_after_adjusters": self.log_odds_after_adjusters,
            "overlay_contribution": (
                {
                    "feature_names": self.overlay_contribution.feature_names,
                    "feature_values": self.overlay_contribution.feature_values,
                    "feature_contributions": self.overlay_contribution.feature_contributions,
                    "intercept": self.overlay_contribution.intercept,
                    "net_log_odds_delta": self.overlay_contribution.net_log_odds_delta,
                }
                if self.overlay_contribution else None
            ),
            "rate_after_overlay": self.rate_after_overlay,
            "log_odds_after_overlay": self.log_odds_after_overlay,
            "calibrated": self.calibrated,
            "pre_calibration_pos": self.pre_calibration_pos,
            "calibration_method": self.calibration_method,
            "calibrated_pos": self.calibrated_pos,
            "final_pos": self.final_pos,
            "thin_data_warning": self.thin_data_warning,
        }
