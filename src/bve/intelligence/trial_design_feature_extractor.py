"""
Pre-readout trial design scoring from ClinicalTrials.gov structured fields.

Maps CT v2 protocol fields to ``TrialDesignFeatureSet`` and produces a
BOUNDED ``AssumptionChangeProposal`` for pre-readout PoS updates.

All proposals use ``ChangeMode.BOUNDED`` and are always routed to manual
review (ReviewQueue). No auto-apply path exists for pre-readout adjustments.

Design decisions
----------------
- Phase is required for ``compute_design_adjusted_pos()``. When phase cannot
  be mapped from the CT record, assessment is skipped (``assessment_skipped=True``).
- Power is computed using a two-sided z-test approximation. The test uses the
  historical median effect size for the TA/phase from YAML as the assumed effect.
- Breakthrough relaxation: when ``prior_phase_effect > breakthrough_multiplier ×
  historical_effect_size_default``, the observed effect is used instead and the
  power penalty is suppressed.
- Absolute PoS change is capped at ``design_scoring_max_update_pp`` (default 0.15).
  An additional relative clamp ensures the proposal stays within ``bound_pct``
  (default 50%) to pass ``AssumptionChangeProposal`` validation.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from scipy.stats import norm

from bve.intelligence.schemas.proposals import AssumptionChangeProposal
from bve.intelligence.taxonomy import ChangeMode, EventType
from bve.models.trial_design_features import (
    ApprovalPathway,
    EndpointBasis,
    EvidenceDesign,
    TrialDesignFeatureSet,
    compute_design_adjusted_pos,
)

# ---------------------------------------------------------------------------
# Keyword sets for endpoint basis classification
# ---------------------------------------------------------------------------

_HARD_CLINICAL_KW = frozenset({
    "overall survival",
    "event-free survival",
    "efs ",
    "complete remission",
    "complete response",
    "dialysis",
    "major adverse cardiovascular events",
    "mace",
    "disease-free survival",
    "dfs ",
    "relapse-free survival",
    "myocardial infarction",
    "stroke",
    "time to death",
    "all-cause mortality",
    "cardiovascular death",
})

_SURROGATE_VALIDATED_KW = frozenset({
    "progression-free survival",
    "pfs",
    "hba1c",
    "hemoglobin a1c",
    "fev1",
    "forced expiratory volume",
    "svr",
    "sustained virologic",
    "ldl",
    "blood pressure",
    "viral load",
    "acr20",
    "acr50",
})

_BIOMARKER_KW = frozenset({
    "pharmacodynamic",
    "receptor occupancy",
    "pharmacokinetic",
    "area under the curve",
    "maximum concentration",
})

# ---------------------------------------------------------------------------
# CT phase strings → internal phase keys
# ---------------------------------------------------------------------------

_CT_PHASE_MAP: dict[str, str] = {
    "PHASE1":       "phase_1",
    "PHASE2":       "phase_2",
    "PHASE3":       "phase_3",
    "PHASE4":       "nda_bla",
    "EARLY_PHASE1": "phase_1",
    "NA":           "",         # empty string → skip
}

_PHASE_PRIORITY = {"phase_1": 1, "phase_2": 2, "phase_3": 3, "nda_bla": 4}

# ---------------------------------------------------------------------------
# Config defaults (fallback when pre_readout_scoring absent from YAML)
# ---------------------------------------------------------------------------

_CONFIG_DEFAULTS: dict = {
    "design_scoring_max_update_pp": 0.15,
    "low_power_threshold": 0.70,
    "low_power_logodds_penalty_scale": 0.20,
    "breakthrough_effect_multiplier": 1.5,
    "proposal_bound_pct": 50.0,
    "historical_median_n": {
        "oncology":     {"phase_2": 180, "phase_3": 420},
        "rare_disease": {"phase_2": 80,  "phase_3": 200},
        "cns":          {"phase_2": 200, "phase_3": 500},
        "default":      {"phase_2": 150, "phase_3": 380},
    },
    "historical_effect_size_default": 0.15,
}


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

class PreReadoutAssessment(BaseModel):
    """
    Result of pre-readout trial design scoring for a single CT record.

    Attributes
    ----------
    nct_id:
        NCT identifier from the CT record.
    asset_id:
        Intelligence layer asset ID.
    phase:
        Internal phase key used for design adjustment (e.g. "phase_3").
    assessment_skipped:
        True when phase is unknown or un-mappable — no proposal is generated.
    skip_reason:
        Human-readable reason when assessment_skipped is True.
    features:
        Extracted TrialDesignFeatureSet. None when skipped.
    base_pos:
        Input success probability before adjustment.
    adjusted_pos:
        Final PoS after design + power adjustment and clamping.
    design_logodds_adjustment:
        Log-odds shift from trial design features (before power penalty).
    adjustment_breakdown:
        Per-dimension log-odds contributions from compute_design_adjusted_pos().
    enrollment_n:
        Extracted enrollment count from CT enrollmentInfo.count.
    effect_size_used:
        Effect size used in the power calculation (may be prior_phase_effect
        when breakthrough relaxation is applied).
    power:
        Estimated statistical power. None when enrollment_n is unavailable.
    low_power_flag:
        True when power < low_power_threshold and breakthrough relaxation
        was not applied.
    breakthrough_relaxation_applied:
        True when prior_phase_effect exceeded breakthrough_multiplier ×
        historical_effect_size_default; power penalty is suppressed.
    proposal:
        BOUNDED AssumptionChangeProposal routed to ReviewQueue. None when
        assessment_skipped is True.
    """

    model_config = {"frozen": True}

    nct_id:                       str
    asset_id:                     str
    phase:                        str

    assessment_skipped:           bool                          = False
    skip_reason:                  Optional[str]                 = None

    features:                     Optional[TrialDesignFeatureSet] = None

    base_pos:                     float                         = 0.0
    adjusted_pos:                 float                         = 0.0
    design_logodds_adjustment:    float                         = 0.0
    adjustment_breakdown:         dict[str, float]              = Field(default_factory=dict)

    enrollment_n:                 Optional[int]                 = None
    effect_size_used:             float                         = 0.0
    power:                        Optional[float]               = None
    low_power_flag:               bool                          = False
    breakthrough_relaxation_applied: bool                       = False

    proposal:                     Optional[AssumptionChangeProposal] = None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _power_from_params(n: int, effect: float, alpha: float = 0.05) -> float:
    """
    Two-sided z-test power approximation.

    power = Φ(|effect| × √(n/2) − z_{α/2})
    """
    z_alpha = norm.ppf(1.0 - alpha / 2.0)
    z_beta = abs(effect) * math.sqrt(n / 2.0) - z_alpha
    return float(norm.cdf(z_beta))


def _clamp_proposed_pos(
    base_pos: float,
    raw_proposed: float,
    max_update_pp: float,
    bound_pct: float,
) -> float:
    """
    Clamp adjusted_pos so it satisfies both constraints:

    1. Absolute: |adjusted − base| ≤ max_update_pp
    2. Relative: |adjusted − base| / base ≤ bound_pct / 100

    The tighter constraint applies. Returns value in [0.01, 0.99].
    """
    delta = raw_proposed - base_pos

    if abs(delta) > max_update_pp:
        delta = math.copysign(max_update_pp, delta)

    max_rel = abs(base_pos) * (bound_pct / 100.0)
    if max_rel > 0 and abs(delta) > max_rel:
        delta = math.copysign(max_rel, delta)

    return max(0.01, min(0.99, base_pos + delta))


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class TrialDesignFeatureExtractor:
    """
    Extracts trial design features from a ClinicalTrials.gov v2 protocol record
    and produces a pre-readout ``AssumptionChangeProposal``.

    Parameters
    ----------
    config:
        Override dict for pre_readout_scoring thresholds. When None, loaded
        from ``industry_assumptions.yaml`` with ``_CONFIG_DEFAULTS`` fallback.
    therapeutic_area:
        Therapeutic area key for historical_median_n lookup (e.g. "oncology").
        Default "default" uses the cross-indication median.
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        therapeutic_area: str = "default",
    ) -> None:
        self._cfg = config if config is not None else self._load_config()
        self._therapeutic_area = therapeutic_area

    @staticmethod
    def _load_config() -> dict:
        try:
            from bve.config.assumptions_loader import AssumptionsLoader
            data = AssumptionsLoader.get()._data
            section = data.get("pre_readout_scoring")
            if section:
                return _unfreeze(section)
        except Exception:
            pass
        return dict(_CONFIG_DEFAULTS)

    def assess(
        self,
        ct_record: dict,
        asset_id: str,
        engine_asset_id: str,
        base_pos: float,
        prior_phase_effect: Optional[float] = None,
    ) -> PreReadoutAssessment:
        """
        Score pre-readout trial design from a ClinicalTrials.gov v2 record.

        Parameters
        ----------
        ct_record:
            Raw ClinicalTrials.gov v2 dict. Accepts both protocolSection-wrapped
            and flat module formats.
        asset_id:
            Intelligence layer asset ID.
        engine_asset_id:
            Frozen engine ``Asset.id`` used in the proposal.
        base_pos:
            Current success probability for this trial phase.
        prior_phase_effect:
            Effect size observed in the prior phase (e.g. Phase 2 HR or delta).
            Used for breakthrough relaxation. When None, relaxation is disabled.

        Returns
        -------
        PreReadoutAssessment
            Contains extracted features, adjusted PoS, power analysis, and a
            BOUNDED AssumptionChangeProposal. When phase is unmappable,
            ``assessment_skipped=True`` and ``proposal`` is None.
        """
        proto = ct_record.get("protocolSection", ct_record)
        id_mod     = proto.get("identificationModule", {})
        design_mod = proto.get("designModule", {})

        nct_id = (id_mod.get("nctId") or "").strip()
        title  = (id_mod.get("briefTitle") or id_mod.get("officialTitle") or "")

        # Map phase
        phases = design_mod.get("phases", [])
        if hasattr(phases, '__iter__') and not isinstance(phases, str):
            phases = list(phases)
        else:
            phases = [phases] if phases else []

        phase = self._map_phase(phases)
        if not phase:
            return PreReadoutAssessment(
                nct_id=nct_id,
                asset_id=asset_id,
                phase="unknown",
                assessment_skipped=True,
                skip_reason="Phase unknown or not mappable from CT record",
            )

        # Extract features
        features = self._extract_features(proto, title)

        # Design-adjusted PoS
        design_result = compute_design_adjusted_pos(base_pos, features, phase=phase)
        adjusted_pos = design_result.adjusted_pos

        # Config values
        cfg                = self._cfg
        historical_effect  = float(cfg.get("historical_effect_size_default", 0.15))
        low_power_thr      = float(cfg.get("low_power_threshold", 0.70))
        penalty_scale      = float(cfg.get("low_power_logodds_penalty_scale", 0.20))
        btd_mult           = float(cfg.get("breakthrough_effect_multiplier", 1.5))
        max_update_pp      = float(cfg.get("design_scoring_max_update_pp", 0.15))
        bound_pct          = float(cfg.get("proposal_bound_pct", 50.0))

        enrollment_n                 = self._extract_enrollment(design_mod)
        power: Optional[float]       = None
        low_power_flag               = False
        breakthrough_relaxation      = False
        effect_size_used             = historical_effect

        if enrollment_n is not None and enrollment_n > 0:
            # Breakthrough relaxation: observed prior effect exceeds 1.5× historical
            if (
                prior_phase_effect is not None
                and prior_phase_effect > btd_mult * historical_effect
            ):
                effect_size_used     = prior_phase_effect
                breakthrough_relaxation = True

            power = _power_from_params(enrollment_n, effect_size_used, alpha=0.05)

            if not breakthrough_relaxation and power < low_power_thr:
                low_power_flag = True
                power_gap  = low_power_thr - power
                lo_penalty = -penalty_scale * (power_gap / low_power_thr)
                lo = math.log(adjusted_pos / (1.0 - adjusted_pos))
                lo += lo_penalty
                adjusted_pos = 1.0 / (1.0 + math.exp(-lo))

        # Clamp to satisfy both absolute and bound_pct constraints
        adjusted_pos = _clamp_proposed_pos(base_pos, adjusted_pos, max_update_pp, bound_pct)

        # Build proposal
        signal_id = f"pre_readout:{nct_id}" if nct_id else f"pre_readout:{asset_id}"
        now       = datetime.now(timezone.utc)
        delta_pp  = adjusted_pos - base_pos

        rationale_parts = [
            f"Pre-readout design scoring for {nct_id or 'unknown NCT'} ({phase}).",
            f"Endpoint: {features.endpoint_basis.value},",
            f"Design: {features.evidence_design.value},",
            f"Pathway: {features.approval_pathway.value}.",
            f"ΔPoS: {delta_pp:+.3f} ({delta_pp / base_pos * 100.0:+.1f}% relative).",
        ]
        if low_power_flag and power is not None:
            rationale_parts.append(
                f"Low power: estimated power={power:.2f} < threshold={low_power_thr:.2f};"
                f" log-odds penalty applied."
            )
        if breakthrough_relaxation and prior_phase_effect is not None:
            rationale_parts.append(
                f"Breakthrough relaxation: prior_phase_effect={prior_phase_effect:.3f}"
                f" > {btd_mult}×historical ({historical_effect:.3f}); power penalty suppressed."
            )

        proposal = AssumptionChangeProposal(
            id                  = str(uuid.uuid4()),
            signal_id           = signal_id,
            asset_id            = asset_id,
            engine_asset_id     = engine_asset_id,
            parameter_path      = "trials[*].success_probability",
            current_value       = base_pos,
            proposed_value      = adjusted_pos,
            change_mode         = ChangeMode.BOUNDED,
            bound_pct           = bound_pct,
            event_type          = EventType.TRIAL_READOUT,
            rationale           = " ".join(rationale_parts),
            created_at          = now,
        )

        return PreReadoutAssessment(
            nct_id                       = nct_id,
            asset_id                     = asset_id,
            phase                        = phase,
            features                     = features,
            base_pos                     = base_pos,
            adjusted_pos                 = adjusted_pos,
            design_logodds_adjustment    = design_result.total_logodds_adjustment,
            adjustment_breakdown         = dict(design_result.adjustment_breakdown),
            enrollment_n                 = enrollment_n,
            effect_size_used             = effect_size_used,
            power                        = power,
            low_power_flag               = low_power_flag,
            breakthrough_relaxation_applied = breakthrough_relaxation,
            proposal                     = proposal,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _map_phase(self, phases: list) -> str:
        """
        Return the highest-priority mappable phase from the CT phases list.

        For Phase 2/3 trials (phases=["PHASE2","PHASE3"]) the highest phase
        (phase_3) is used — the trial is designed to support a pivotal claim
        and should be evaluated at Phase 3 design standards.

        Returns empty string when no phase is mappable.
        """
        best      = ""
        best_prio = -1
        for p in phases:
            p_str  = str(p).strip()
            mapped = _CT_PHASE_MAP.get(p_str, "")
            prio   = _PHASE_PRIORITY.get(mapped, 0)
            if mapped and prio > best_prio:
                best      = mapped
                best_prio = prio
        return best

    def _extract_features(self, proto: dict, title: str) -> TrialDesignFeatureSet:
        design_mod   = proto.get("designModule", {})
        outcomes_mod = proto.get("outcomesModule", {})

        # Endpoint basis — from first primary outcome measure text
        primary_outcomes = outcomes_mod.get("primaryOutcomes", [])
        if isinstance(primary_outcomes, (list, tuple)) and primary_outcomes:
            first        = primary_outcomes[0]
            measure_text = (first.get("measure") or "").lower() if isinstance(first, dict) else ""
        else:
            measure_text = ""
        endpoint_basis = self._classify_endpoint(measure_text)

        # Evidence design — from designInfo.allocation and maskingInfo.masking
        design_info  = design_mod.get("designInfo", {})
        allocation   = (design_info.get("allocation") or design_mod.get("allocation") or "").upper()
        masking_info = design_info.get("maskingInfo", {})
        masking      = (masking_info.get("masking") or "").upper()
        evidence_design = self._classify_evidence_design(allocation, masking)

        # Approval pathway — from title keywords
        approval_pathway = self._classify_approval_pathway(title, proto)

        return TrialDesignFeatureSet(
            endpoint_basis   = endpoint_basis,
            evidence_design  = evidence_design,
            approval_pathway = approval_pathway,
        )

    @staticmethod
    def _classify_endpoint(measure_lower: str) -> EndpointBasis:
        for kw in _HARD_CLINICAL_KW:
            if kw in measure_lower:
                return EndpointBasis.HARD_CLINICAL
        for kw in _SURROGATE_VALIDATED_KW:
            if kw in measure_lower:
                return EndpointBasis.SURROGATE_VALIDATED
        for kw in _BIOMARKER_KW:
            if kw in measure_lower:
                return EndpointBasis.BIOMARKER_ONLY
        return EndpointBasis.SURROGATE_VALIDATED  # reference default

    @staticmethod
    def _classify_evidence_design(allocation: str, masking: str) -> EvidenceDesign:
        is_randomized  = "RANDOMIZED" in allocation
        is_double_plus = any(m in masking for m in ("DOUBLE", "TRIPLE", "QUADRUPLE"))
        if is_randomized and is_double_plus:
            return EvidenceDesign.RCT_COMPARATIVE
        if is_randomized:
            return EvidenceDesign.RCT_NON_COMPARATIVE
        return EvidenceDesign.SINGLE_ARM

    @staticmethod
    def _classify_approval_pathway(title: str, proto: dict) -> ApprovalPathway:
        id_mod         = proto.get("identificationModule", {})
        official_title = (id_mod.get("officialTitle") or "").lower()
        combined       = title.lower() + " " + official_title
        if "breakthrough" in combined:
            return ApprovalPathway.BREAKTHROUGH_DESIGNATION
        if "orphan" in combined:
            return ApprovalPathway.ORPHAN_DRUG
        if "accelerated" in combined:
            return ApprovalPathway.ACCELERATED_APPROVAL
        return ApprovalPathway.STANDARD

    @staticmethod
    def _extract_enrollment(design_mod: dict) -> Optional[int]:
        count = design_mod.get("enrollmentInfo", {}).get("count")
        if count is not None:
            try:
                return int(count)
            except (TypeError, ValueError):
                pass
        return None


# ---------------------------------------------------------------------------
# Utility: convert MappingProxyType tree to plain dict
# ---------------------------------------------------------------------------

def _unfreeze(obj: object) -> object:
    """Recursively convert MappingProxyType / tuple to plain dict / list."""
    from types import MappingProxyType
    if isinstance(obj, MappingProxyType):
        return {k: _unfreeze(v) for k, v in obj.items()}
    if isinstance(obj, tuple):
        return [_unfreeze(v) for v in obj]
    return obj
