"""
Wave 2 — Competitor Catalyst Linking.

Bridges competitor programs (from KG COMPETES_WITH edges) to the tracked
asset's catalyst calendar.  For each competitor program with an estimable
readout date, produces a COMPETITOR_READOUT CatalystEvent on the tracked
asset with pre-computed EV impact fields.

MoA propagation rules
---------------------
same_moa + competitor_success
    Market share compression.  PoS change: None.
    Rationale: MoA validation is already priced; success shifts market share,
    not PoS for the tracked asset.

same_moa + competitor_failure (efficacy)
    PoS increase + market share increase.
    Rationale: efficacy failure suggests the indication is harder; market may
    re-rate the competitive field, leaving more room for the tracked asset.

same_moa + competitor_failure (safety)
    PoS decrease (class concern) + market share increase.
    Rationale: a safety signal for the same MoA raises the FDA bar and may
    block or delay the tracked asset regardless of its own profile.

different_moa + competitor_success
    Market share compression only.  PoS: None.
    Rationale: competitor validates indication but via a different mechanism;
    market share is split but the tracked asset's own PoS is unchanged.

different_moa + competitor_failure
    Market share increase only.  PoS: None.
    Rationale: no class signal; the field just becomes less crowded.

Temporal decay
--------------
    market_awareness_date = max(competitor_readout_date, our_trial_start_date)
    effective_delta_years = (our_readout_date − market_awareness_date).days / 365.25
    decay = exp(−effective_delta_years / tau_years)   if effective_delta_years > 0
    decay = 1.0                                        otherwise

The market_awareness_date heuristic captures that if the competitor reads out
before our trial even starts, the market has already incorporated the signal
by the time our own readout matters.

EV calculation for COMPETITOR_READOUT events
--------------------------------------------
  current_value            — latest rNPV of the tracked asset from KnowledgeStore
  value_if_competitor_success — current_value × (1 + market_share_delta × decay)
  value_if_competitor_failure — current_value × (1 + pos_delta × decay)
  competitor_pos               — neutral prior 0.50 (no view on competitor outcome)
  delta_ev = competitor_pos × (value_if_success − current_value)
           + (1 − competitor_pos) × (value_if_failure − current_value)

std_dev, signal_strength, and asymmetry_ratio are computed with the same
floor-guarded formula used by CatalystEVCalculator.

No new network calls
--------------------
All CT records are pre-fetched by the caller (CompetitorDiscoveryEngine or
WatchlistRunner).  link_competitor_program() and link_all() accept dicts.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from bve.intelligence.catalyst_calendar import CatalystEvent, CatalystType
from bve.intelligence.competitor_discovery import CompetitorProgram
from bve.intelligence.trial_readout_estimator import TrialReadoutEstimator

# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------

_CONFIG_DEFAULTS: dict = {
    "tau_years": {
        "oncology":       1.2,
        "rare_disease":   2.0,
        "cardiovascular": 1.5,
        "immunology":     1.3,
        "cns":            1.8,
        "default":        1.5,
    },
    "pos_delta_competitor_failure":            0.05,
    "pos_delta_competitor_failure_safety":    -0.03,
    "market_share_delta_competitor_success":  -0.08,
    "market_share_delta_competitor_failure":   0.05,
    "competitor_default_pos":                  0.50,
    "std_floor_multiplier":                    0.50,
}

# Failure type sentinel
_EFFICACY_FAILURE = "efficacy"
_SAFETY_FAILURE   = "safety"


# ---------------------------------------------------------------------------
# MoA impact scenarios
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _ImpactScenarios:
    """
    Fractional rNPV change under each competitor outcome.

    positive = tracked asset value increases
    negative = tracked asset value decreases
    """
    market_share_delta_on_success: float   # applied when competitor succeeds
    pos_delta_on_failure:          float   # applied when competitor fails
    pos_impact_label:              str     # "none" | "increase" | "class_concern"


def _resolve_impact(
    same_moa: bool,
    failure_type: str,     # "efficacy" | "safety"
    cfg: dict,
) -> _ImpactScenarios:
    """
    Return impact fractions based on MoA relationship and failure type.

    Parameters
    ----------
    same_moa:
        True when tracked asset and competitor share the same mechanism of action.
    failure_type:
        ``"efficacy"`` or ``"safety"`` — determines PoS direction on failure.
        Only meaningful for same-MoA failures; different-MoA failure always
        gives market_share_delta only.
    cfg:
        Loaded config dict.
    """
    ms_success = float(cfg.get("market_share_delta_competitor_success", -0.08))

    if same_moa:
        if failure_type == _SAFETY_FAILURE:
            # Class concern: PoS *decreases* for tracked asset
            return _ImpactScenarios(
                market_share_delta_on_success = ms_success,
                pos_delta_on_failure          = float(cfg.get("pos_delta_competitor_failure_safety", -0.03)),
                pos_impact_label              = "class_concern",
            )
        else:
            # Efficacy failure: PoS *increases* (less competition for indication)
            return _ImpactScenarios(
                market_share_delta_on_success = ms_success,
                pos_delta_on_failure          = float(cfg.get("pos_delta_competitor_failure", 0.05)),
                pos_impact_label              = "increase",
            )
    else:
        # Different MoA — failure gives market share increase only, no PoS signal
        return _ImpactScenarios(
            market_share_delta_on_success = ms_success,
            pos_delta_on_failure          = float(cfg.get("market_share_delta_competitor_failure", 0.05)),
            pos_impact_label              = "none",
        )


# ---------------------------------------------------------------------------
# Temporal decay
# ---------------------------------------------------------------------------

def competitor_decay_factor(
    competitor_readout_date: date,
    our_trial_start_date: date,
    our_readout_date: date,
    indication: str,
    tau_years: float,
) -> float:
    """
    Decay factor in [0, 1] representing how much of the competitor's
    impact remains novel at the time of our readout.

    Market prices competitor impact from the later of:
      (a) competitor readout date, (b) our trial start date.

    ``decay = exp(−effective_delta_years / tau_years)``

    Returns 1.0 when the competitor reads out at or after our readout
    (impact is fully contemporary).
    """
    market_awareness_date = max(competitor_readout_date, our_trial_start_date)
    effective_delta_years = (our_readout_date - market_awareness_date).days / 365.25
    if effective_delta_years <= 0:
        return 1.0
    return math.exp(-effective_delta_years / tau_years)


def _tau_for_indication(indication: str, tau_map: dict) -> float:
    """Return tau_years for the given indication from config dict."""
    ind_lower = indication.lower() if indication else ""
    for key in ("oncology", "rare_disease", "cardiovascular", "immunology", "cns"):
        if key in ind_lower or ind_lower.replace(" ", "_") == key:
            v = tau_map.get(key)
            if v is not None:
                return float(v)
    return float(tau_map.get("default", 1.5))


# ---------------------------------------------------------------------------
# EV math helpers (same formula as CatalystEVCalculator)
# ---------------------------------------------------------------------------

def _compute_ev(
    current_value: float,
    value_if_success: float,
    value_if_failure: float,
    competitor_pos: float,
    std_floor_mult: float,
) -> dict:
    upside   = value_if_success - current_value
    downside = current_value - value_if_failure

    delta_ev = competitor_pos * upside - (1.0 - competitor_pos) * downside

    ev = delta_ev
    outcome_success = upside
    outcome_failure = -downside
    variance = (
        competitor_pos * (outcome_success - ev) ** 2
        + (1.0 - competitor_pos) * (outcome_failure - ev) ** 2
    )
    std_dev = math.sqrt(max(variance, 0.0))

    std_floor = max(std_dev, abs(ev) * std_floor_mult)
    signal_strength = (ev / std_floor) if std_floor > 0.0 else 0.0

    asymmetry_ratio = (
        upside / downside if downside > 0.0 else float("inf")
    )
    return {
        "delta_ev":         delta_ev,
        "upside":           upside,
        "downside":         downside,
        "std_dev":          std_dev,
        "signal_strength":  signal_strength,
        "asymmetry_ratio":  asymmetry_ratio,
    }


# ---------------------------------------------------------------------------
# Linker
# ---------------------------------------------------------------------------

class CompetitorCatalystLinker:
    """
    For each competitor program linked to a tracked asset via KG edges,
    estimate the competitor's readout date and pre-compute the EV impact
    on the tracked asset under success/failure scenarios.

    Parameters
    ----------
    config:
        Override dict for ``competitor_impact`` thresholds.  When ``None``,
        loaded from ``industry_assumptions.yaml`` with ``_CONFIG_DEFAULTS``
        as fallback.
    readout_estimator:
        Optional TrialReadoutEstimator; constructed with ``config`` when None.
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        readout_estimator: Optional[TrialReadoutEstimator] = None,
    ) -> None:
        self._cfg = config if config is not None else self._load_config()
        self._estimator = readout_estimator or TrialReadoutEstimator(
            config=self._cfg
        )

    @staticmethod
    def _load_config() -> dict:
        try:
            from bve.config.assumptions_loader import AssumptionsLoader
            from bve.intelligence.trial_design_feature_extractor import _unfreeze
            data = AssumptionsLoader.get()._data
            section = data.get("competitor_impact")
            if section:
                return _unfreeze(section)
        except Exception:
            pass
        return dict(_CONFIG_DEFAULTS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def link_all(
        self,
        tracked_asset_id: str,
        competitor_programs: list[CompetitorProgram],
        knowledge_store,
        *,
        tracked_asset_indication: str = "",
        our_trial_start_date: Optional[date] = None,
        our_readout_date: Optional[date] = None,
        asset_config_path: Optional[str] = None,
    ) -> list[CatalystEvent]:
        """
        Create COMPETITOR_READOUT CatalystEvents for all linked programs.

        Parameters
        ----------
        tracked_asset_id:
            Intelligence layer asset ID of the asset we are ranking.
        competitor_programs:
            CompetitorProgram objects for this asset (from competitor_programs table).
        knowledge_store:
            KnowledgeStore — used to pull current rNPV and upsert events.
        tracked_asset_indication:
            Indication string (used for tau selection).
        our_trial_start_date:
            Start date of the tracked asset's own trial (for decay calculation).
            When None, date.today() is used as a conservative fallback.
        our_readout_date:
            Estimated readout of the tracked asset's own trial.
            When None, 2 years from today is used as a conservative fallback.
        asset_config_path:
            Path to asset YAML config — passed through to _current_value_from_store.

        Returns
        -------
        List of upserted CatalystEvents.
        """
        if not competitor_programs:
            return []

        current_value = self._resolve_current_value(tracked_asset_id, knowledge_store)

        events: list[CatalystEvent] = []
        for program in competitor_programs:
            ev = self._link_program(
                tracked_asset_id        = tracked_asset_id,
                program                 = program,
                current_value           = current_value,
                tracked_asset_indication= tracked_asset_indication,
                our_trial_start_date    = our_trial_start_date,
                our_readout_date        = our_readout_date,
            )
            if ev is not None:
                knowledge_store.upsert_catalyst_event(ev)
                events.append(ev)

        return events

    def link_competitor_program(
        self,
        tracked_asset_id: str,
        competitor_nct_id: str,
        competitor_drug_name: str,
        same_moa: bool,
        indication: str,
        *,
        failure_type: str = _EFFICACY_FAILURE,
        competitor_ct_record: Optional[dict] = None,
        current_value: float = 0.0,
        company_id: Optional[str] = None,
        our_trial_start_date: Optional[date] = None,
        our_readout_date: Optional[date] = None,
    ) -> Optional[CatalystEvent]:
        """
        Create a single COMPETITOR_READOUT CatalystEvent for one competitor.

        Parameters
        ----------
        tracked_asset_id:
            Asset ID of the tracked program.
        competitor_nct_id:
            NCT ID of the competitor trial.
        competitor_drug_name:
            Display name of the competitor drug.
        same_moa:
            True when tracked asset and competitor share the same mechanism.
        indication:
            Shared indication string (for tau selection).
        failure_type:
            ``"efficacy"`` (default) or ``"safety"`` — determines PoS direction
            on competitor failure.
        competitor_ct_record:
            Pre-fetched CT v2 API record dict.  When None, no readout date is
            estimated and the event carries only directional information.
        current_value:
            Tracked asset's current rNPV ($M).
        company_id:
            Optional company identifier for the tracked asset.
        our_trial_start_date:
            Trial start date of the tracked asset (for decay).
        our_readout_date:
            Estimated readout of the tracked asset (for decay).

        Returns
        -------
        CatalystEvent or None when no readout date can be estimated.
        """
        cfg = self._cfg

        # ---- Step 1: estimate competitor readout date --------------------
        competitor_readout_date: Optional[date] = None
        if competitor_ct_record is not None:
            ev_est = self._estimator.estimate(competitor_ct_record, tracked_asset_id)
            if ev_est is not None:
                competitor_readout_date = ev_est.expected_date

        if competitor_readout_date is None:
            return None

        # ---- Step 2: temporal decay --------------------------------------
        today = date.today()
        trial_start = our_trial_start_date or today
        readout     = our_readout_date or date(today.year + 2, today.month, today.day)

        tau_map = cfg.get("tau_years", _CONFIG_DEFAULTS["tau_years"])
        if not isinstance(tau_map, dict):
            tau_map = _CONFIG_DEFAULTS["tau_years"]
        tau = _tau_for_indication(indication, tau_map)

        decay = competitor_decay_factor(
            competitor_readout_date = competitor_readout_date,
            our_trial_start_date    = trial_start,
            our_readout_date        = readout,
            indication              = indication,
            tau_years               = tau,
        )

        # ---- Step 3: impact magnitudes -----------------------------------
        scenarios = _resolve_impact(same_moa, failure_type, cfg)

        ms_delta   = scenarios.market_share_delta_on_success * decay   # < 0
        pos_delta  = scenarios.pos_delta_on_failure * decay            # sign varies

        competitor_pos   = float(cfg.get("competitor_default_pos", 0.50))
        std_floor_mult   = float(cfg.get("std_floor_multiplier", 0.50))

        value_if_success = current_value * (1.0 + ms_delta)
        value_if_failure = current_value * (1.0 + pos_delta)

        ev_fields = _compute_ev(
            current_value    = current_value,
            value_if_success = value_if_success,
            value_if_failure = value_if_failure,
            competitor_pos   = competitor_pos,
            std_floor_mult   = std_floor_mult,
        )

        # ---- Step 4: build CatalystEvent --------------------------------
        now = datetime.now(timezone.utc)
        description = (
            f"Competitor readout: {competitor_drug_name}"
            + (f" ({competitor_nct_id})" if competitor_nct_id else "")
            + f" in {indication}"
            + f" | same_moa={same_moa}"
            + f" | pos_impact={scenarios.pos_impact_label}"
            + f" | decay={decay:.2f}"
        )

        return CatalystEvent(
            id              = str(uuid.uuid4()),
            asset_id        = tracked_asset_id,
            company_id      = company_id,
            catalyst_type   = CatalystType.COMPETITOR_READOUT,
            expected_date   = competitor_readout_date,
            date_confidence = "quarter",
            source          = f"competitor_linker/{competitor_nct_id or competitor_drug_name}",
            description     = description,
            current_pos     = competitor_pos,
            value_if_success= round(value_if_success, 2),
            value_if_failure= round(value_if_failure, 2),
            current_value   = round(current_value, 2),
            delta_ev        = round(ev_fields["delta_ev"], 2),
            upside          = round(ev_fields["upside"], 2),
            downside        = round(ev_fields["downside"], 2),
            std_dev         = round(ev_fields["std_dev"], 4),
            signal_strength = round(ev_fields["signal_strength"], 4),
            asymmetry_ratio = (
                round(ev_fields["asymmetry_ratio"], 4)
                if math.isfinite(ev_fields["asymmetry_ratio"])
                else ev_fields["asymmetry_ratio"]
            ),
            is_active       = True,
            resolved        = False,
            created_at      = now,
            updated_at      = now,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _link_program(
        self,
        *,
        tracked_asset_id: str,
        program: CompetitorProgram,
        current_value: float,
        tracked_asset_indication: str,
        our_trial_start_date: Optional[date],
        our_readout_date: Optional[date],
    ) -> Optional[CatalystEvent]:
        """Create a CatalystEvent for one CompetitorProgram."""
        if not program.nct_id:
            return None

        # Determine same_moa from KG (not available here → default to False)
        # Callers who have MoA info should use link_competitor_program() directly.
        same_moa = False

        return self.link_competitor_program(
            tracked_asset_id        = tracked_asset_id,
            competitor_nct_id       = program.nct_id,
            competitor_drug_name    = program.drug_name,
            same_moa                = same_moa,
            indication              = tracked_asset_indication or program.indication,
            current_value           = current_value,
            our_trial_start_date    = our_trial_start_date,
            our_readout_date        = our_readout_date,
        )

    @staticmethod
    def _resolve_current_value(asset_id: str, knowledge_store) -> float:
        """
        Pull the latest rNPV for the tracked asset from the stored valuation diffs.
        Returns 0.0 when no diff is available.
        """
        try:
            diffs = knowledge_store.get_valuation_diffs(asset_id=asset_id, limit=1)
            if diffs:
                after = diffs[0].valuation_after.get("rnpv_millions")
                if after is not None:
                    return float(after)
        except Exception:
            pass
        return 0.0
