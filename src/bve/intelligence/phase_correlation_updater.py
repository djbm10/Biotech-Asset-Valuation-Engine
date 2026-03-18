"""
Bayesian Phase 2 → Phase 3 PoS update.

For each asset with a Phase 3 trial, uses resolved Phase 1/2 StructuredSignals
from the knowledge store to compute a continuous posterior update via a
sigmoid likelihood model.

Sigmoid likelihood model
------------------------
    P(Phase 3 success | z) = σ(α + β·z)

where z is a continuous z-score derived from the Phase 2 readout (p-value,
hazard ratio, or estimated effect size) and α, β are calibrated in YAML.

Bayesian posterior
------------------
    posterior = (prior · L) / (prior · L + (1 − prior) · (1 − L))

Critical adjustments
--------------------
Single-arm Phase 2
    If ``randomization`` is not ``"randomized"``, the z-score is shrunk:
    ``z_adjusted = z_raw × single_arm_z_shrinkage`` (default 0.60).
    Rationale: single-arm Phase 2 results are systematically over-optimistic
    (no comparator arm controls for secular trend, patient selection bias, etc.)

Posterior cap
    ``posterior = clamp(posterior, prior − max_update_pp, prior + max_update_pp)``
    Default ``max_update_pp = 0.25``.

Phase 1 only path
    When only Phase 1 data exists, a safety-based update is applied using the
    CTCAE ``safety_grade`` field and a smaller sigmoid slope (``phase1_beta``).
    The absolute cap is ``max_update_pp × phase1_max_update_fraction``.
    The full sigmoid efficacy model is NOT applied in this path.

Output
------
All proposals use ``ChangeMode.BOUNDED`` → always routed to ReviewQueue.
Rationale format:
    "Ph2 z={z:.2f} likelihood={L:.2f} → posterior {post:.1%}
    (prior {prior:.1%}, cap=applied|not applied)"

No network calls
----------------
``PhaseCorrelationUpdater.update()`` accepts pre-fetched signal records.
The caller is responsible for querying ``KnowledgeStore.get_structured_signals``.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
from scipy.stats import norm

from bve.entities.trial import TrialPhase
from bve.intelligence.schemas.proposals import AssumptionChangeProposal
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import ChangeMode, EventType
from bve.intelligence.trial_design_feature_extractor import (
    _clamp_proposed_pos,
    _unfreeze,
)

# ---------------------------------------------------------------------------
# Config defaults (fallback when phase_correlation absent from YAML)
# ---------------------------------------------------------------------------

_CONFIG_DEFAULTS: dict = {
    "alpha":                      0.0,
    "beta":                       0.50,
    "max_update_pp":              0.25,
    "single_arm_z_shrinkage":     0.60,
    "phase1_beta":                0.25,
    "phase1_max_update_fraction": 0.33,
    "proposal_bound_pct":         80.0,
}


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

class PhaseCorrelationResult(BaseModel):
    """
    Result of the Bayesian Phase 2→3 PoS update.

    Attributes
    ----------
    asset_id:
        Intelligence layer asset ID.
    prior_pos:
        Phase 3 base PoS before update.
    posterior_pos:
        Final clamped PoS. Equals ``prior_pos`` when ``update_applied=False``.
    z_raw:
        Z-score derived from the Phase 2 signal before single-arm adjustment.
        ``None`` when no quantitative data is available.
    z_adjusted:
        Z-score after shrinkage. Equals ``z_raw`` when the Phase 2 trial was
        randomized (``single_arm_penalty_applied=False``).
    single_arm_penalty_applied:
        True when ``randomization != "randomized"`` and z was shrunk.
    likelihood:
        ``P(Phase 3 success | z_adjusted)`` from the sigmoid model.
    raw_posterior:
        Posterior before the ±max_update_pp and bound_pct clamps.
    cap_applied:
        True when ``raw_posterior`` was outside ``prior ± max_update_pp``
        or the relative bound clamp further reduced the delta.
    update_applied:
        False when no usable Phase 1/2 signal was found.
    skip_reason:
        Human-readable explanation when ``update_applied=False``.
    phase_data_source:
        ``"phase_2"``, ``"phase_1"``, or ``None``.
    signal_id:
        ``StructuredSignalRecord.id`` of the signal used for the update.
    proposal:
        BOUNDED ``AssumptionChangeProposal`` for ``ReviewQueue``.
        ``None`` when ``update_applied=False``.
    """

    model_config = {"frozen": True}

    asset_id:                    str
    prior_pos:                   float
    posterior_pos:               float

    z_raw:                       Optional[float]  = None
    z_adjusted:                  Optional[float]  = None
    single_arm_penalty_applied:  bool             = False
    likelihood:                  Optional[float]  = None
    raw_posterior:               Optional[float]  = None
    cap_applied:                 bool             = False
    update_applied:              bool             = False
    skip_reason:                 Optional[str]    = None
    phase_data_source:           Optional[str]    = None
    signal_id:                   Optional[str]    = None

    proposal:                    Optional[AssumptionChangeProposal] = None


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _bayesian_update(prior: float, likelihood: float) -> float:
    """
    Bayesian posterior update.

    posterior = (prior × L) / (prior × L + (1−prior) × (1−L))
    """
    num = prior * likelihood
    den = num + (1.0 - prior) * (1.0 - likelihood)
    if den < 1e-12:
        return prior
    return num / den


def _z_from_signal(signal: StructuredSignal) -> Optional[float]:
    """
    Derive a continuous z-score from available StructuredSignal fields.

    Priority
    --------
    1. ``p_value`` + ``primary_endpoint_met``
       z = ±norm.ppf(1 − p/2); sign from endpoint_met direction.
    2. ``hazard_ratio`` → z = −log(HR)
       Positive when HR < 1 (treatment benefit); negative when HR > 1.
    3. ``estimated_effect_size`` (Cohen's d or similar) → z = effect_size.
    4. Binary ``primary_endpoint_met`` → z = ±1.96.

    Returns ``None`` when no quantitative data is available.
    """
    # 1. p-value is the most direct source
    if signal.p_value is not None:
        z_magnitude = float(norm.ppf(1.0 - signal.p_value / 2.0))
        direction = -1.0 if signal.primary_endpoint_met is False else 1.0
        return direction * z_magnitude

    # 2. Hazard ratio (time-to-event endpoints)
    if signal.hazard_ratio is not None and signal.hazard_ratio > 0:
        return -math.log(float(signal.hazard_ratio))

    # 3. Estimated effect size
    if signal.estimated_effect_size is not None:
        return float(signal.estimated_effect_size)

    # 4. Binary endpoint met
    if signal.primary_endpoint_met is not None:
        return 1.96 if signal.primary_endpoint_met else -1.96

    return None


def _safety_z_from_grade(safety_grade: Optional[int]) -> Optional[float]:
    """
    Map CTCAE safety_grade (1–5) to a safety z-score for the Phase 1 path.

    Grade 1 (clean) → +1.0; Grade 2 (acceptable) → +0.5; Grade 3 → 0.0;
    Grade 4 (serious) → −1.0; Grade 5 (fatal) → −2.0.

    Returns ``None`` when ``safety_grade`` is ``None``.
    """
    if safety_grade is None:
        return None
    return {1: 1.0, 2: 0.5, 3: 0.0, 4: -1.0, 5: -2.0}.get(safety_grade)


def _parse_structured_signal(payload_json: dict) -> Optional[StructuredSignal]:
    """Deserialize payload_json into a StructuredSignal; return None on error."""
    try:
        return StructuredSignal.model_validate(payload_json)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Updater
# ---------------------------------------------------------------------------

class PhaseCorrelationUpdater:
    """
    Computes a Bayesian Phase 2 → Phase 3 PoS update from prior-phase signals.

    Parameters
    ----------
    config:
        Override dict for ``phase_correlation`` thresholds. When ``None``,
        loaded from ``industry_assumptions.yaml`` with ``_CONFIG_DEFAULTS``
        as fallback.
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        self._cfg = config if config is not None else self._load_config()

    @staticmethod
    def _load_config() -> dict:
        try:
            from bve.config.assumptions_loader import AssumptionsLoader
            data = AssumptionsLoader.get()._data
            section = data.get("phase_correlation")
            if section:
                return _unfreeze(section)
        except Exception:
            pass
        return dict(_CONFIG_DEFAULTS)

    def update(
        self,
        asset_id: str,
        engine_asset_id: str,
        prior_pos: float,
        signals: list,
    ) -> PhaseCorrelationResult:
        """
        Apply a Bayesian Phase 2→3 PoS update using pre-fetched signal records.

        Parameters
        ----------
        asset_id:
            Intelligence layer asset ID.
        engine_asset_id:
            Frozen engine ``Asset.id`` used in the ``AssumptionChangeProposal``.
        prior_pos:
            Current Phase 3 success probability (e.g. from ``POSAdjusters``).
        signals:
            Pre-fetched ``StructuredSignalRecord`` objects from
            ``KnowledgeStore.get_structured_signals(asset_id=..., event_type=TRIAL_READOUT)``.
            This method makes **no** I/O or network calls.

        Returns
        -------
        PhaseCorrelationResult
        """
        cfg             = self._cfg
        alpha           = float(cfg.get("alpha",                      0.0))
        beta            = float(cfg.get("beta",                       0.50))
        max_update_pp   = float(cfg.get("max_update_pp",              0.25))
        shrinkage       = float(cfg.get("single_arm_z_shrinkage",     0.60))
        ph1_beta        = float(cfg.get("phase1_beta",                0.25))
        ph1_frac        = float(cfg.get("phase1_max_update_fraction", 0.33))
        bound_pct       = float(cfg.get("proposal_bound_pct",         80.0))
        ph1_max_update  = max_update_pp * ph1_frac

        # Partition signals by phase
        phase2_records: list = []
        phase1_records: list = []
        for rec in signals:
            ph = (rec.payload_json or {}).get("trial_phase")
            if ph == TrialPhase.PHASE_2.value:
                phase2_records.append(rec)
            elif ph == TrialPhase.PHASE_1.value:
                phase1_records.append(rec)

        # ------------------------------------------------------------------
        # Phase 2 path — full sigmoid likelihood model
        # ------------------------------------------------------------------
        if phase2_records:
            rec = phase2_records[0]   # most recent (caller sorts by signal_date DESC)
            sig = _parse_structured_signal(rec.payload_json)
            if sig is None:
                return self._no_data(asset_id, prior_pos, "Phase 2 signal parse error")

            z_raw = _z_from_signal(sig)
            if z_raw is None:
                return self._no_data(
                    asset_id, prior_pos,
                    "Phase 2 signal has no quantitative endpoint data (p_value, HR, or effect_size)",
                )

            single_arm = sig.randomization in ("non_randomized", "single_arm")
            z_adj      = z_raw * shrinkage if single_arm else z_raw

            likelihood  = _sigmoid(alpha + beta * z_adj)
            raw_post    = _bayesian_update(prior_pos, likelihood)

            # Absolute cap: prior ± max_update_pp, then relative bound (bound_pct)
            abs_capped  = max(prior_pos - max_update_pp, min(prior_pos + max_update_pp, raw_post))
            final_post  = _clamp_proposed_pos(prior_pos, abs_capped, max_update_pp, bound_pct)
            cap_applied = abs(raw_post - prior_pos) > abs(final_post - prior_pos) + 1e-9

            proposal = self._make_proposal(
                asset_id, engine_asset_id, prior_pos, final_post,
                bound_pct, rec.id,
                z=z_adj, likelihood=likelihood, cap_applied=cap_applied,
            )
            return PhaseCorrelationResult(
                asset_id                   = asset_id,
                prior_pos                  = prior_pos,
                posterior_pos              = final_post,
                z_raw                      = z_raw,
                z_adjusted                 = z_adj,
                single_arm_penalty_applied = single_arm,
                likelihood                 = likelihood,
                raw_posterior              = raw_post,
                cap_applied                = cap_applied,
                update_applied             = True,
                phase_data_source          = "phase_2",
                signal_id                  = rec.id,
                proposal                   = proposal,
            )

        # ------------------------------------------------------------------
        # Phase 1 only path — safety-based smaller update
        # ------------------------------------------------------------------
        if phase1_records:
            rec = phase1_records[0]
            sig = _parse_structured_signal(rec.payload_json)
            if sig is None:
                return self._no_data(asset_id, prior_pos, "Phase 1 signal parse error")

            safety_z = _safety_z_from_grade(sig.safety_grade)
            if safety_z is None:
                return self._no_data(
                    asset_id, prior_pos,
                    "Phase 1 signal has no safety_grade data; cannot apply Phase 1 update",
                )

            likelihood  = _sigmoid(alpha + ph1_beta * safety_z)
            raw_post    = _bayesian_update(prior_pos, likelihood)

            abs_capped  = max(prior_pos - ph1_max_update, min(prior_pos + ph1_max_update, raw_post))
            final_post  = _clamp_proposed_pos(prior_pos, abs_capped, ph1_max_update, bound_pct)
            cap_applied = abs(raw_post - prior_pos) > abs(final_post - prior_pos) + 1e-9

            proposal = self._make_proposal(
                asset_id, engine_asset_id, prior_pos, final_post,
                bound_pct, rec.id,
                z=safety_z, likelihood=likelihood, cap_applied=cap_applied,
            )
            return PhaseCorrelationResult(
                asset_id                   = asset_id,
                prior_pos                  = prior_pos,
                posterior_pos              = final_post,
                z_raw                      = safety_z,
                z_adjusted                 = safety_z,
                single_arm_penalty_applied = False,
                likelihood                 = likelihood,
                raw_posterior              = raw_post,
                cap_applied                = cap_applied,
                update_applied             = True,
                phase_data_source          = "phase_1",
                signal_id                  = rec.id,
                proposal                   = proposal,
            )

        # ------------------------------------------------------------------
        # No prior phase data
        # ------------------------------------------------------------------
        return self._no_data(asset_id, prior_pos, "No Phase 1 or Phase 2 signals found")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _no_data(
        asset_id: str, prior_pos: float, reason: str
    ) -> PhaseCorrelationResult:
        return PhaseCorrelationResult(
            asset_id      = asset_id,
            prior_pos     = prior_pos,
            posterior_pos = prior_pos,
            update_applied = False,
            skip_reason    = reason,
        )

    @staticmethod
    def _make_proposal(
        asset_id: str,
        engine_asset_id: str,
        prior: float,
        posterior: float,
        bound_pct: float,
        signal_id: str,
        z: float,
        likelihood: float,
        cap_applied: bool,
    ) -> AssumptionChangeProposal:
        cap_str   = "applied" if cap_applied else "not applied"
        rationale = (
            f"Ph2 z={z:.2f} likelihood={likelihood:.2f} → "
            f"posterior {posterior:.1%} (prior {prior:.1%}, cap={cap_str})"
        )
        return AssumptionChangeProposal(
            id              = str(uuid.uuid4()),
            signal_id       = signal_id,
            asset_id        = asset_id,
            engine_asset_id = engine_asset_id,
            parameter_path  = "trials[*].success_probability",
            current_value   = prior,
            proposed_value  = posterior,
            change_mode     = ChangeMode.BOUNDED,
            bound_pct       = bound_pct,
            event_type      = EventType.TRIAL_READOUT,
            rationale       = rationale,
            created_at      = datetime.now(timezone.utc),
        )
