"""
Wave 1 Part C — Trial readout date estimator from ClinicalTrials.gov records.

Uses ``primaryCompletionDateStruct.date`` and adds a configurable lag
(data lock + analysis + disclosure) to estimate when results will be
publicly disclosed.

date_confidence is always ``"quarter"`` — the lag window spans several months
and the primary completion date itself may be provisional.

No new network calls — accepts pre-fetched CT v2 API record dict.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from bve.intelligence.catalyst_calendar import CatalystEvent, CatalystType
from bve.intelligence.enrollment_snapshot_extractor import _parse_ct_date

# ---------------------------------------------------------------------------
# Config defaults (fallback when catalyst_calendar absent from YAML)
# ---------------------------------------------------------------------------

_CONFIG_DEFAULTS: dict = {
    "readout_lag_days_min":     120,
    "readout_lag_days_max":     270,
    "readout_lag_days_default": 180,
}


class TrialReadoutEstimator:
    """
    Estimate trial readout dates from a CT v2 API record.

    Parameters
    ----------
    config:
        Override dict for ``catalyst_calendar`` thresholds.  When ``None``,
        loaded from ``industry_assumptions.yaml`` with ``_CONFIG_DEFAULTS``
        as fallback.
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        self._cfg = config if config is not None else self._load_config()

    @staticmethod
    def _load_config() -> dict:
        try:
            from bve.config.assumptions_loader import AssumptionsLoader
            from bve.intelligence.trial_design_feature_extractor import _unfreeze
            data = AssumptionsLoader.get()._data
            section = data.get("catalyst_calendar")
            if section:
                cfg = _unfreeze(section)
                return cfg
        except Exception:
            pass
        return dict(_CONFIG_DEFAULTS)

    def estimate(
        self,
        ct_record: dict,
        asset_id: str,
        *,
        company_id: Optional[str] = None,
        source: str = "clinicaltrials_gov",
    ) -> Optional[CatalystEvent]:
        """
        Estimate a trial readout CatalystEvent from a CT record.

        Parameters
        ----------
        ct_record:
            ClinicalTrials.gov v2 ``protocolSection`` wrapper dict.
        asset_id:
            Intelligence layer asset ID.
        company_id:
            Optional company identifier.
        source:
            Source reference string stored on the event.

        Returns
        -------
        CatalystEvent with ``catalyst_type=TRIAL_READOUT`` and
        ``date_confidence="quarter"``, or ``None`` when no primary
        completion date is found.
        """
        proto = ct_record.get("protocolSection") or {}

        nct_id = (
            proto.get("identificationModule", {}).get("nctId")
            or ct_record.get("nctId")
            or ""
        )

        status_mod = proto.get("statusModule", {})
        pcd_struct = status_mod.get("primaryCompletionDateStruct", {})
        primary_completion_date = _parse_ct_date(pcd_struct.get("date"))

        if primary_completion_date is None:
            return None

        cfg = self._cfg
        lag_days = int(cfg.get("readout_lag_days_default", 180))

        estimated_date = primary_completion_date + timedelta(days=lag_days)

        # Get trial title for description
        title = (
            proto.get("identificationModule", {}).get("briefTitle")
            or nct_id
            or "unnamed trial"
        )

        now = datetime.now(timezone.utc)
        return CatalystEvent(
            id              = str(uuid.uuid4()),
            asset_id        = asset_id,
            company_id      = company_id,
            catalyst_type   = CatalystType.TRIAL_READOUT,
            expected_date   = estimated_date,
            date_confidence = "quarter",
            source          = source,
            description     = (
                f"Trial readout: {title}"
                + (f" ({nct_id})" if nct_id else "")
                + f" — estimated +{lag_days}d from primary completion "
                  f"({primary_completion_date.isoformat()})"
            ),
            created_at      = now,
            updated_at      = now,
        )
