"""
EmpiricalPOSEngine — empirically-grounded POS model backed by real outcome data.

Integration
-----------
Drop-in replacement for heuristic compute_pos() when real outcome data is
available. The engine:

    1. Looks up an empirical base rate from BaseRateTable (stratified by
       phase, MoA precedent, and biomarker enrichment).
    2. Optionally blends sponsor track record (Bayesian shrinkage) into the rate.
    3. Optionally applies heuristic log-odds adjusters (from pos_model.py)
       on top of the empirical rate.
    4. Optionally applies a CalibrationArtifact (Platt or isotonic).

Prediction transparency
-----------------------
Every compute_pos_* method has a _with_provenance variant that returns a
POSProvenance object decomposing every step of the computation.

Fallback
--------
The heuristic model (pos_model.py) remains the default (feature flag
apply_pos_model=False). EmpiricalPOSEngine is activated only when
empirical_pos_engine is explicitly supplied.
"""
from __future__ import annotations

import math
import logging
from pathlib import Path
from typing import Optional

from bve.empirical.base_rate_table import BaseRateTable
from bve.empirical.pos_outcome import (
    POSOutcomeRecord,
    SponsorTrackRecord,
    build_sponsor_tracks,
    load_bundled_records,
    load_outcome_records,
)

logger = logging.getLogger(__name__)

_L1_CAP_POSITIVE = 0.80
_L1_CAP_NEGATIVE = -0.80

# Sparse-cell warning: fewer than this many observations in the matched cell.
_THIN_DATA_THRESHOLD = 5

# Sponsor Bayesian shrinkage: prior_weight equivalent sample size.
# blended = (n_sponsor_success + prior_weight * cell_rate) / (n_sponsor + prior_weight)
# Higher prior_weight → stronger shrinkage toward cell rate.
_SPONSOR_PRIOR_WEIGHT = 10.0
# Minimum sponsor phase observations to enable sponsor blending.
_MIN_SPONSOR_N_FOR_BLEND = 3


class EmpiricalPOSEngine:
    """
    POS engine backed by real clinical trial outcome data.

    Parameters
    ----------
    records:
        Validated POSOutcomeRecord list. Censored rows must be excluded.
    smoothing_alpha:
        Laplace smoothing parameter for BaseRateTable. Default 1.0.
    min_n_for_stratified:
        Minimum cell count before falling back to a less-specific stratum.
    use_sponsor_adjustment:
        When True, Bayesian-shrink the empirical base rate toward the sponsor's
        own phase-level success rate when the sponsor has >= min_sponsor_n records
        for that phase. Reported in provenance. Default False.
    min_sponsor_n:
        Minimum sponsor phase observations to enable sponsor blending.
    """

    def __init__(
        self,
        records: list[POSOutcomeRecord],
        smoothing_alpha: float = 1.0,
        min_n_for_stratified: int = 3,
        use_sponsor_adjustment: bool = False,
        min_sponsor_n: int = _MIN_SPONSOR_N_FOR_BLEND,
    ):
        if not records:
            raise ValueError("EmpiricalPOSEngine requires at least one outcome record")
        self._records = records
        self._table = BaseRateTable(
            records,
            smoothing_alpha=smoothing_alpha,
            min_n_for_stratified=min_n_for_stratified,
        )
        self._sponsor_tracks: dict[str, SponsorTrackRecord] = build_sponsor_tracks(records)
        self._n = len(records)
        self._use_sponsor_adjustment = use_sponsor_adjustment
        self._min_sponsor_n = min_sponsor_n
        # CalibrationArtifact — set via attach_calibration()
        self.calibration = None  # Optional[CalibrationArtifact]
        # OverlayArtifact — set via attach_overlay()
        self.overlay = None      # Optional[OverlayArtifact]

    # ------------------------------------------------------------------
    # Alternate constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_csv(
        cls,
        csv_path: str | Path,
        smoothing_alpha: float = 1.0,
        min_n_for_stratified: int = 3,
        skip_invalid: bool = True,
        use_sponsor_adjustment: bool = False,
    ) -> "EmpiricalPOSEngine":
        """Load from a CSV file and build the engine."""
        records = load_outcome_records(
            csv_path, skip_censored=True, skip_invalid=skip_invalid
        )
        return cls(records, smoothing_alpha=smoothing_alpha,
                   min_n_for_stratified=min_n_for_stratified,
                   use_sponsor_adjustment=use_sponsor_adjustment)

    @classmethod
    def from_bundled(
        cls,
        smoothing_alpha: float = 1.0,
        min_n_for_stratified: int = 3,
        use_sponsor_adjustment: bool = False,
    ) -> "EmpiricalPOSEngine":
        """Load from the bundled oncology dataset (research/data/oncology_phase_transitions.csv)."""
        records = load_bundled_records()
        return cls(records, smoothing_alpha=smoothing_alpha,
                   min_n_for_stratified=min_n_for_stratified,
                   use_sponsor_adjustment=use_sponsor_adjustment)

    # ------------------------------------------------------------------
    # Calibration attachment
    # ------------------------------------------------------------------

    def attach_calibration(self, artifact) -> None:
        """
        Attach a CalibrationArtifact to the engine.

        After attaching, compute_calibrated_pos() and compute_pos_with_provenance()
        (when calibrate=True) will apply the artifact's calibration.

        Parameters
        ----------
        artifact:
            A fitted CalibrationArtifact from bve.empirical.calibration.
        """
        self.calibration = artifact

    def attach_overlay(self, artifact) -> None:
        """
        Attach a fitted OverlayArtifact to the engine.

        After attaching, compute_fitted_pos() uses the overlay's logistic
        regression coefficients instead of the hand-tuned heuristic adjusters.

        Parameters
        ----------
        artifact:
            A fitted OverlayArtifact from bve.empirical.overlay_model.
        """
        self.overlay = artifact

    # ------------------------------------------------------------------
    # Core prediction API
    # ------------------------------------------------------------------

    def predict(
        self,
        phase: str,
        moa_precedent: Optional[str] = None,
        biomarker_selected: Optional[bool] = None,
    ) -> float:
        """
        Return the Laplace-smoothed empirical base rate for the given characteristics.

        This is the raw empirical rate — no heuristic adjusters or sponsor blending.
        Use compute_pos_with_adjusters() to layer the full stack.

        Parameters
        ----------
        phase:
            "phase_1", "phase_2", "phase_3", or "nda_bla".
        moa_precedent:
            "validated", "partial", "novel", or None.
        biomarker_selected:
            True/False to use the biomarker-stratified rate; None (default) to
            use the broader phase/MoA cell (no biomarker stratification).

        Returns
        -------
        float in (0, 1).
        """
        return self._table.get(
            phase=phase,
            moa_precedent=moa_precedent,
            biomarker_selected=biomarker_selected,
        )

    def compute_pos_with_adjusters(
        self,
        phase,                   # TrialPhase enum or str
        therapeutic_area=None,   # TherapeuticArea enum (API compat; not used in lookup)
        adjusters=None,          # POSAdjusters | None
        sponsor: Optional[str] = None,
    ) -> float:
        """
        Compute POS: empirical base rate + optional sponsor blend + heuristic adjusters.

        Returns only the final probability. Use compute_pos_with_provenance()
        for the full decomposition.

        Parameters
        ----------
        phase:      TrialPhase enum or its .value string.
        adjusters:  POSAdjusters. If None, pure empirical rate is returned.
        sponsor:    Sponsor name for track-record blending (requires use_sponsor_adjustment=True).

        Returns
        -------
        float in (0, 1).
        """
        pos, _ = self._compute(phase, adjusters, sponsor, apply_calibration=False)
        return pos

    def compute_calibrated_pos(
        self,
        phase,
        therapeutic_area=None,
        adjusters=None,
        sponsor: Optional[str] = None,
    ) -> float:
        """
        Compute POS with calibration applied (requires attached CalibrationArtifact).

        Falls back to uncalibrated if no calibration artifact is attached.
        """
        if self.calibration is None:
            logger.warning("No CalibrationArtifact attached; returning uncalibrated POS.")
            return self.compute_pos_with_adjusters(phase, therapeutic_area, adjusters, sponsor)
        pos, _ = self._compute(phase, adjusters, sponsor, apply_calibration=True)
        return pos

    def compute_fitted_pos(
        self,
        phase,
        therapeutic_area=None,
        adjusters=None,
        sponsor: Optional[str] = None,
        apply_calibration: bool = False,
    ) -> float:
        """
        Compute POS using the fitted logistic overlay (empirical_fitted mode).

        Uses the phase-level base rate as a fixed offset, then applies the
        OverlayArtifact's learned coefficients.  Falls back to
        compute_pos_with_adjusters() when no overlay is attached (with a warning).

        Parameters
        ----------
        phase:             TrialPhase enum or str.
        adjusters:         POSAdjusters — used for feature extraction.
        sponsor:           Sponsor name (optional; for sponsor blending).
        apply_calibration: Apply attached CalibrationArtifact on top.

        Returns
        -------
        float in (0, 1).
        """
        if self.overlay is None:
            logger.warning(
                "compute_fitted_pos: no OverlayArtifact attached; "
                "falling back to compute_pos_with_adjusters."
            )
            return self.compute_pos_with_adjusters(
                phase, therapeutic_area, adjusters, sponsor
            )
        pos, _ = self._compute(
            phase, adjusters, sponsor,
            apply_calibration=apply_calibration,
            use_overlay=True,
        )
        return pos

    def compute_pos_with_provenance(
        self,
        phase,
        therapeutic_area=None,
        adjusters=None,
        sponsor: Optional[str] = None,
        apply_calibration: bool = False,
    ):  # -> tuple[float, POSProvenance]
        """
        Compute POS and return a full POSProvenance decomposition.

        Parameters
        ----------
        phase:             TrialPhase enum or str.
        adjusters:         POSAdjusters or None.
        sponsor:           Sponsor name for track-record lookup.
        apply_calibration: When True and calibration artifact is attached,
                           apply calibration and record it in provenance.

        Returns
        -------
        (final_pos: float, provenance: POSProvenance)
        """
        return self._compute(phase, adjusters, sponsor, apply_calibration=apply_calibration)

    # ------------------------------------------------------------------
    # Internal computation pipeline (returns pos + provenance)
    # ------------------------------------------------------------------

    def _compute(
        self,
        phase,
        adjusters,
        sponsor: Optional[str],
        apply_calibration: bool,
        use_overlay: bool = False,
    ):
        from bve.empirical.provenance import (
            FittedOverlayContribution,
            HeuristicAdjustment, POSProvenance,
            SponsorContribution,
        )

        phase_str = phase.value if hasattr(phase, "value") else str(phase)

        # Resolve stratification fields from adjusters
        moa_str: Optional[str] = None
        biomarker: Optional[bool] = None
        if adjusters is not None:
            moa_val = getattr(adjusters, "moa_precedent", None)
            if moa_val is not None:
                moa_str = moa_val.value if hasattr(moa_val, "value") else str(moa_val)
            bio_flag = getattr(adjusters, "biomarker_selected_population", None)
            if bio_flag:
                biomarker = True

        # ---- Step 1: empirical base rate + lookup provenance ----
        base_rate, lookup = self._table.get_with_provenance(phase_str, moa_str, biomarker)
        base_rate = max(0.01, min(0.99, base_rate))
        base_log_odds = math.log(base_rate / (1.0 - base_rate))

        # Thin-data warning
        thin_warning: Optional[str] = None
        if lookup.is_published_fallback:
            thin_warning = (
                f"No empirical data for phase={phase_str!r}: using published industry fallback "
                f"{base_rate:.1%}. Treat this estimate as heuristic."
            )
        elif lookup.n < _THIN_DATA_THRESHOLD:
            thin_warning = (
                f"Cell {lookup.cell_key} has only {lookup.n} observations "
                f"(< threshold {_THIN_DATA_THRESHOLD}). Estimate may be unstable."
            )

        # ---- Step 2: sponsor Bayesian blending ----
        sponsor_contribution: Optional[SponsorContribution] = None
        rate_after_sponsor: Optional[float] = None
        log_odds_after_sponsor: Optional[float] = base_log_odds

        if self._use_sponsor_adjustment and sponsor is not None:
            track = self._sponsor_tracks.get(sponsor)
            if track is not None:
                phase_data = track.phases.get(phase_str)
                if phase_data is not None and phase_data["n"] >= self._min_sponsor_n:
                    n_sp = phase_data["n"]
                    n_sp_success = phase_data["n_success"]
                    sponsor_phase_rate = phase_data["rate"]

                    # Bayesian shrinkage: blend sponsor rate toward cell rate
                    blended = (n_sp_success + _SPONSOR_PRIOR_WEIGHT * base_rate) / (n_sp + _SPONSOR_PRIOR_WEIGHT)
                    blended = max(0.01, min(0.99, blended))
                    blended_log_odds = math.log(blended / (1.0 - blended))
                    delta_lo = blended_log_odds - base_log_odds

                    blend_weight = n_sp / (n_sp + _SPONSOR_PRIOR_WEIGHT)
                    sponsor_contribution = SponsorContribution(
                        sponsor=sponsor,
                        n_sponsor_total=track.n_trials,
                        n_sponsor_phase=n_sp,
                        n_sponsor_phase_success=n_sp_success,
                        sponsor_phase_rate=round(sponsor_phase_rate, 4),
                        prior_weight=_SPONSOR_PRIOR_WEIGHT,
                        blend_weight=round(blend_weight, 4),
                        blended_rate=round(blended, 4),
                        log_odds_delta=round(delta_lo, 4),
                    )
                    rate_after_sponsor = round(blended, 4)
                    log_odds_after_sponsor = blended_log_odds

        current_log_odds = log_odds_after_sponsor if log_odds_after_sponsor is not None else base_log_odds

        # ---- Step 3: adjustment layer — heuristic OR fitted overlay ----
        heuristic_adjustments: list[HeuristicAdjustment] = []
        net_adj = 0.0
        capped_adj = 0.0

        overlay_contribution: Optional[FittedOverlayContribution] = None
        rate_after_overlay: Optional[float] = None
        log_odds_after_overlay: Optional[float] = None

        if use_overlay and self.overlay is not None:
            # --- Step 3b: fitted overlay (empirical_fitted mode) ---
            # For the overlay, use the phase-only base rate as the fixed offset
            # so that coefficients are comparable to heuristic log-odds values.
            from bve.empirical.features import build_feature_vector_from_adjusters
            fv = build_feature_vector_from_adjusters(adjusters)
            p_base_phase = self._table.get(phase_str)  # phase-only (no moa/biomarker)
            p_base_phase = max(0.01, min(0.99, p_base_phase))
            phase_only_lo = math.log(p_base_phase / (1.0 - p_base_phase))

            # Include sponsor-blended current_log_odds as starting point if blending occurred
            # For overlay, we use phase-only offset directly per the architecture spec:
            # logit(p_final) = logit(p_base_phase) + intercept + X @ beta
            contrib_values = self.overlay.feature_contributions(fv)
            contribs = [contrib_values[name] for name in self.overlay.feature_names]
            net_overlay_delta = self.overlay.net_log_odds_delta(fv)
            overlay_lo = phase_only_lo + net_overlay_delta
            rate_overlay = round(float(1.0 / (1.0 + math.exp(-overlay_lo))), 4)

            overlay_contribution = FittedOverlayContribution(
                feature_names=list(self.overlay.feature_names),
                feature_values=fv,
                feature_contributions=contribs,
                intercept=self.overlay.intercept,
                net_log_odds_delta=round(net_overlay_delta, 6),
            )
            rate_after_overlay = rate_overlay
            log_odds_after_overlay = round(overlay_lo, 6)
            current_log_odds = overlay_lo

        elif adjusters is not None:
            # --- Step 3a: heuristic adjusters (empirical_raw / empirical_calibrated modes) ---
            adj_details = self._layer1_adjustment_detailed(adjusters)
            net_adj = sum(a.log_odds for a in adj_details)
            capped_adj = max(_L1_CAP_NEGATIVE, min(_L1_CAP_POSITIVE, net_adj))
            heuristic_adjustments = adj_details
            current_log_odds += capped_adj

        pre_calib_pos = round(1.0 / (1.0 + math.exp(-current_log_odds)), 4)

        # ---- Step 4: calibration ----
        calibrated = False
        calibrated_pos: Optional[float] = None
        calib_method: Optional[str] = None

        if apply_calibration and self.calibration is not None:
            calibrated_pos = round(self.calibration.apply(pre_calib_pos), 4)
            calib_method = self.calibration.method
            calibrated = True

        final_pos = calibrated_pos if calibrated else pre_calib_pos

        prov = POSProvenance(
            phase=phase_str,
            moa_precedent=moa_str,
            biomarker_selected=biomarker,
            sponsor=sponsor,
            lookup=lookup,
            base_empirical_rate=round(base_rate, 4),
            base_empirical_log_odds=round(base_log_odds, 4),
            sponsor_contribution=sponsor_contribution,
            rate_after_sponsor=rate_after_sponsor,
            log_odds_after_sponsor=round(log_odds_after_sponsor, 4) if log_odds_after_sponsor is not None else None,
            heuristic_adjustments=heuristic_adjustments,
            net_heuristic_adjustment=round(net_adj, 4),
            capped_heuristic_adjustment=round(capped_adj, 4),
            log_odds_after_adjusters=round(current_log_odds, 4),
            overlay_contribution=overlay_contribution,
            rate_after_overlay=rate_after_overlay,
            log_odds_after_overlay=log_odds_after_overlay,
            calibrated=calibrated,
            pre_calibration_pos=pre_calib_pos if calibrated else None,
            calibration_method=calib_method,
            calibrated_pos=calibrated_pos,
            final_pos=final_pos,
            thin_data_warning=thin_warning,
        )

        return final_pos, prov

    @staticmethod
    def _layer1_adjustment(adjusters) -> float:
        from bve.models.pos_model import _compute_layer1_adjustment
        delta, _flags = _compute_layer1_adjustment(adjusters)
        return delta

    @staticmethod
    def _layer1_adjustment_detailed(adjusters) -> list:
        """
        Return per-adjuster log-odds contributions as HeuristicAdjustment objects.
        """
        from bve.empirical.provenance import HeuristicAdjustment
        from bve.models.pos_model import (
            _ENDPOINT_LOGODDS, _MOA_LOGODDS, _SAMPLE_LOGODDS,
            _SAFETY_LOGODDS, _COMPETITION_LOGODDS,
            _BIOMARKER_SELECTION_BONUS, _PRIOR_PHASE_SUCCESS_BONUS, _BTD_LOGODDS,
        )
        result = []
        result.append(HeuristicAdjustment(
            name="endpoint_type",
            value=adjusters.endpoint_type.value if hasattr(adjusters.endpoint_type, "value") else str(adjusters.endpoint_type),
            log_odds=_ENDPOINT_LOGODDS.get(adjusters.endpoint_type, 0.0),
        ))
        result.append(HeuristicAdjustment(
            name="moa_precedent",
            value=adjusters.moa_precedent.value if hasattr(adjusters.moa_precedent, "value") else str(adjusters.moa_precedent),
            log_odds=_MOA_LOGODDS.get(adjusters.moa_precedent, 0.0),
        ))
        result.append(HeuristicAdjustment(
            name="sample_size_adequacy",
            value=adjusters.sample_size_adequacy.value if hasattr(adjusters.sample_size_adequacy, "value") else str(adjusters.sample_size_adequacy),
            log_odds=_SAMPLE_LOGODDS.get(adjusters.sample_size_adequacy, 0.0),
        ))
        result.append(HeuristicAdjustment(
            name="safety_profile",
            value=adjusters.safety_profile.value if hasattr(adjusters.safety_profile, "value") else str(adjusters.safety_profile),
            log_odds=_SAFETY_LOGODDS.get(adjusters.safety_profile, 0.0),
        ))
        result.append(HeuristicAdjustment(
            name="competitive_pressure",
            value=adjusters.competitive_pressure.value if hasattr(adjusters.competitive_pressure, "value") else str(adjusters.competitive_pressure),
            log_odds=_COMPETITION_LOGODDS.get(adjusters.competitive_pressure, 0.0),
        ))
        if getattr(adjusters, "biomarker_selected_population", False):
            result.append(HeuristicAdjustment(
                name="biomarker_selected_population",
                value="true",
                log_odds=_BIOMARKER_SELECTION_BONUS,
            ))
        if getattr(adjusters, "strong_prior_phase_data", False):
            result.append(HeuristicAdjustment(
                name="strong_prior_phase_data",
                value="true",
                log_odds=_PRIOR_PHASE_SUCCESS_BONUS,
            ))
        if getattr(adjusters, "has_breakthrough_designation", False):
            result.append(HeuristicAdjustment(
                name="has_breakthrough_designation",
                value="true",
                log_odds=_BTD_LOGODDS,
            ))
        return result

    # ------------------------------------------------------------------
    # Coverage report
    # ------------------------------------------------------------------

    def coverage_report(self, sparse_threshold: int = 5, top_n_sponsors: int = 20):
        """
        Build and return a CoverageReport for this engine's dataset.

        Returns
        -------
        CoverageReport
        """
        from bve.empirical.coverage import build_coverage_report
        return build_coverage_report(
            self._records, self._table,
            sparse_threshold=sparse_threshold,
            top_n_sponsors=top_n_sponsors,
        )

    # ------------------------------------------------------------------
    # Sponsor context
    # ------------------------------------------------------------------

    def sponsor_track(self, sponsor: str) -> Optional[SponsorTrackRecord]:
        """Return aggregated sponsor history, or None if not found."""
        return self._sponsor_tracks.get(sponsor)

    def all_sponsor_tracks(self) -> dict[str, SponsorTrackRecord]:
        """Return the full sponsor-level track record dict."""
        return dict(self._sponsor_tracks)

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------

    @property
    def n_records(self) -> int:
        """Number of outcome records used to build the engine."""
        return self._n

    def phase_rates(self) -> dict[str, float]:
        """Phase-level empirical rates (Laplace-smoothed, no stratification)."""
        return self._table.phase_rates()

    def provenance(self) -> dict:
        """
        Return a machine-readable provenance summary.

        Useful for embedding in ValuationOutput or audit logs.
        """
        return {
            "model": "EmpiricalPOSEngine",
            "n_records": self._n,
            "smoothing_alpha": self._table.smoothing_alpha,
            "min_n_for_stratified": self._table.min_n,
            "n_sponsors": len(self._sponsor_tracks),
            "use_sponsor_adjustment": self._use_sponsor_adjustment,
            "phase_rates": self.phase_rates(),
            "is_empirically_calibrated": True,
            "calibration_method": self.calibration.method if self.calibration else None,
            "overlay_attached": self.overlay is not None,
            "overlay_converged": self.overlay.converged if self.overlay else None,
        }
