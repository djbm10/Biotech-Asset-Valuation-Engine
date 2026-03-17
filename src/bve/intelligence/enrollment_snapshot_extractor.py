"""
Wave 3: Structured enrollment metrics from ClinicalTrials.gov.

Extracts enrollment velocity, site activation patterns, and completion
slippage from a CT v2 API ``protocolSection`` record.

Data sources
------------
- ``designModule.enrollmentInfo``        → enrollment_target / enrollment_actual
- ``contactsLocationsModule.locations``  → sites_recruiting, site_activation_dates
- ``statusModule.startDateStruct``       → trial_start_date
- ``statusModule.primaryCompletionDateStruct`` → primary_completion_date

Derived metrics
---------------
- ``recruiting_ratio``           sites_recruiting / sites_total  (0.0 when sites_total=0)
- ``patients_per_site_per_month``  enrollment_actual / (sites_total × elapsed_months)
- ``site_activation_rate``       sites_recruiting / elapsed_months since trial_start
- ``median_activation_delay_days`` median(site_activation_dates − trial_start_date)
- ``activation_delay_cv``        cv of activation delays (IQR / median; NaN when < 2 sites)
- ``slippage_months``            primary_completion_date − prior_completion_date
- ``projected_completion_date``  extrapolated from current pace

Alert thresholds (from ``enrollment_quality`` section in industry_assumptions.yaml)
---------------------------------------------------------------------
- recruiting_ratio < 0.30      → AlertTrigger.ENROLLMENT_SITE_STALLING  (WARNING)
- velocity < 0.4× benchmark    → AlertTrigger.ENROLLMENT_VELOCITY_LOW   (WARNING)
- slippage > 2 months          → EventType.ENROLLMENT_UPDATE event

Site count guard
----------------
- sites_total ≥ 10: CV-based threshold is applied
- sites_total <  10: max_activation_delay_days absolute threshold is used instead

No network calls
----------------
``EnrollmentSnapshotExtractor.extract()`` accepts a pre-fetched CT record dict.
The caller is responsible for fetching from ClinicalTrials.gov.
"""
from __future__ import annotations

import statistics
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config defaults (fallback when enrollment_quality absent from YAML)
# ---------------------------------------------------------------------------

_CONFIG_DEFAULTS: dict = {
    "recruiting_ratio_warning_threshold":   0.30,
    "velocity_ratio_warning_threshold":     0.40,    # fraction of benchmark
    "slippage_alert_months":                2.0,
    "min_sites_for_cv_threshold":           10,
    "max_activation_delay_days":            180,
    "activation_delay_cv_threshold":        1.0,
    "benchmark_patients_per_site_per_month": {
        "default": {
            "phase_2": 0.60,
            "phase_3": 0.40,
        }
    },
}


# ---------------------------------------------------------------------------
# Core snapshot model
# ---------------------------------------------------------------------------

class EnrollmentSnapshot(BaseModel):
    """
    Enrollment metrics snapshot for a single CT record.

    Attributes
    ----------
    id:
        UUID row identifier.
    nct_id:
        ClinicalTrials.gov identifier.
    asset_id:
        Intelligence layer asset ID.
    snapshot_date:
        Date on which this snapshot was extracted.
    enrollment_target:
        Total enrollment target from ``enrollmentInfo.count``.
    enrollment_actual:
        Enrolled count when ``enrollmentInfo.type == "ACTUAL"``; ``None`` otherwise.
    sites_recruiting:
        Count of locations with status ``RECRUITING``.
    sites_total:
        Total location count.
    recruiting_ratio:
        ``sites_recruiting / sites_total``; 0.0 when ``sites_total == 0``.
    site_activation_dates:
        List of ``statusDate`` values for recruiting sites (ISO strings).
    trial_start_date:
        Trial start from ``statusModule.startDateStruct.date``.
    site_activation_delays:
        Days between each site activation date and ``trial_start_date``.
    median_activation_delay_days:
        Median of ``site_activation_delays``; ``None`` when no delay data.
    activation_delay_cv:
        IQR / median of activation delays; ``None`` when < 2 sites or median == 0.
    patients_per_site_per_month:
        ``enrollment_actual / (sites_total × elapsed_months)``; ``None`` when
        enrollment_actual or sites_total is unavailable.
    site_activation_rate:
        ``sites_recruiting / elapsed_months``; ``None`` when elapsed_months == 0.
    primary_completion_date:
        Primary completion date from CT record.
    prior_completion_date:
        Previous primary_completion_date from the prior stored snapshot; ``None``
        if this is the first snapshot.
    slippage_months:
        ``primary_completion_date − prior_completion_date`` in months (fractional);
        ``None`` when either date is missing.
    projected_completion_date:
        Extrapolated from current ``patients_per_site_per_month``; ``None`` when
        pace or target unavailable.
    """

    model_config = {"frozen": True}

    id:                         str
    nct_id:                     str
    asset_id:                   str
    snapshot_date:              date

    enrollment_target:          Optional[int]   = None
    enrollment_actual:          Optional[int]   = None
    sites_recruiting:           int             = 0
    sites_total:                int             = 0
    recruiting_ratio:           float           = 0.0

    site_activation_dates:      list[str]       = []
    trial_start_date:           Optional[date]  = None

    site_activation_delays:     list[float]     = []
    median_activation_delay_days: Optional[float] = None
    activation_delay_cv:        Optional[float] = None

    patients_per_site_per_month: Optional[float] = None
    site_activation_rate:        Optional[float] = None

    primary_completion_date:    Optional[date]  = None
    prior_completion_date:      Optional[date]  = None
    slippage_months:            Optional[float] = None
    projected_completion_date:  Optional[date]  = None


# ---------------------------------------------------------------------------
# Alert / trigger result
# ---------------------------------------------------------------------------

class EnrollmentAlertFlags(BaseModel):
    """Boolean flags summarising which alert conditions fired."""

    model_config = {"frozen": True}

    site_stalling:    bool = False   # recruiting_ratio < threshold
    velocity_low:     bool = False   # pace < fraction × benchmark
    slippage_alert:   bool = False   # slippage > slippage_alert_months


# ---------------------------------------------------------------------------
# Extraction result
# ---------------------------------------------------------------------------

class EnrollmentSnapshotResult(BaseModel):
    """Combined output of EnrollmentSnapshotExtractor.extract()."""

    model_config = {"frozen": True}

    snapshot:           EnrollmentSnapshot
    alert_flags:        EnrollmentAlertFlags
    extraction_skipped: bool = False
    skip_reason:        Optional[str] = None


# ---------------------------------------------------------------------------
# Date parsing helpers
# ---------------------------------------------------------------------------

def _parse_ct_date(value: Optional[str]) -> Optional[date]:
    """Parse CT API date strings: YYYY-MM-DD or YYYY-MM."""
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _months_between(d1: date, d2: date) -> float:
    """Approximate elapsed months between two dates (fractional)."""
    delta = d2 - d1
    return delta.days / 30.44


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class EnrollmentSnapshotExtractor:
    """
    Extracts enrollment metrics from a ClinicalTrials.gov v2 API record.

    Parameters
    ----------
    config:
        Override dict for ``enrollment_quality`` thresholds.  When ``None``,
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
            section = data.get("enrollment_quality")
            if section:
                return _unfreeze(section)
        except Exception:
            pass
        return dict(_CONFIG_DEFAULTS)

    def extract(
        self,
        ct_record: dict,
        asset_id: str,
        *,
        prior_snapshot: Optional[EnrollmentSnapshot] = None,
        snapshot_date: Optional[date] = None,
        therapeutic_area: str = "default",
        trial_phase: str = "phase_3",
    ) -> EnrollmentSnapshotResult:
        """
        Extract enrollment metrics from a pre-fetched CT record.

        Parameters
        ----------
        ct_record:
            ClinicalTrials.gov v2 ``protocolSection`` wrapper dict
            (i.e. the dict with a ``protocolSection`` key).
        asset_id:
            Intelligence layer asset ID.
        prior_snapshot:
            Previous ``EnrollmentSnapshot`` for this nct_id; used to compute
            ``slippage_months``.
        snapshot_date:
            Override today's date (used in tests).
        therapeutic_area:
            Used to look up benchmark ``patients_per_site_per_month``.
        trial_phase:
            ``"phase_2"`` or ``"phase_3"``; selects benchmark column.

        Returns
        -------
        EnrollmentSnapshotResult
        """
        proto = ct_record.get("protocolSection") or {}
        nct_id = (
            proto.get("identificationModule", {}).get("nctId")
            or ct_record.get("nctId")
            or ""
        )
        if not nct_id:
            return self._skip("no nct_id in CT record", asset_id)

        today = snapshot_date or date.today()

        # ---- enrollment counts --------------------------------------------
        design_mod = proto.get("designModule", {})
        enroll_info = design_mod.get("enrollmentInfo", {})
        enrollment_target: Optional[int] = None
        enrollment_actual: Optional[int] = None
        if enroll_info:
            count = enroll_info.get("count")
            if count is not None:
                try:
                    count_int = int(count)
                    if enroll_info.get("type", "").upper() == "ACTUAL":
                        enrollment_actual = count_int
                    else:
                        enrollment_target = count_int
                except (TypeError, ValueError):
                    pass

        # ---- site metrics -------------------------------------------------
        locations: list[dict] = (
            proto.get("contactsLocationsModule", {}).get("locations") or []
        )
        sites_total = len(locations)
        recruiting_sites = [
            loc for loc in locations
            if (loc.get("status") or "").upper() == "RECRUITING"
        ]
        sites_recruiting = len(recruiting_sites)
        recruiting_ratio = sites_recruiting / sites_total if sites_total > 0 else 0.0

        # site activation dates for recruiting sites
        activation_dates_raw: list[str] = [
            loc["statusDate"]
            for loc in recruiting_sites
            if loc.get("statusDate")
        ]

        # ---- trial start date ---------------------------------------------
        status_mod = proto.get("statusModule", {})
        start_struct = status_mod.get("startDateStruct", {})
        trial_start_date = _parse_ct_date(start_struct.get("date"))

        # ---- activation delays --------------------------------------------
        delays: list[float] = []
        if trial_start_date:
            for ds in activation_dates_raw:
                d = _parse_ct_date(ds)
                if d is not None:
                    delays.append(float((d - trial_start_date).days))

        median_delay: Optional[float] = None
        delay_cv: Optional[float] = None
        if delays:
            median_delay = statistics.median(delays)
            if len(delays) >= 2 and median_delay and median_delay > 0:
                q1 = statistics.quantiles(delays, n=4)[0]
                q3 = statistics.quantiles(delays, n=4)[2]
                delay_cv = (q3 - q1) / median_delay

        # ---- velocity metrics ---------------------------------------------
        elapsed_months: Optional[float] = None
        if trial_start_date:
            em = _months_between(trial_start_date, today)
            elapsed_months = em if em > 0 else None

        patients_per_site_per_month: Optional[float] = None
        if enrollment_actual is not None and sites_total > 0 and elapsed_months:
            patients_per_site_per_month = enrollment_actual / (sites_total * elapsed_months)

        site_activation_rate: Optional[float] = None
        if elapsed_months:
            site_activation_rate = sites_recruiting / elapsed_months

        # ---- completion / slippage ----------------------------------------
        pcd_struct = status_mod.get("primaryCompletionDateStruct", {})
        primary_completion_date = _parse_ct_date(pcd_struct.get("date"))

        prior_completion_date: Optional[date] = None
        slippage_months: Optional[float] = None
        if prior_snapshot is not None:
            prior_completion_date = prior_snapshot.primary_completion_date
            if primary_completion_date and prior_completion_date:
                slippage_months = _months_between(prior_completion_date, primary_completion_date)

        # ---- projected completion -----------------------------------------
        projected_completion_date: Optional[date] = None
        if (
            enrollment_target is not None
            and enrollment_actual is not None
            and patients_per_site_per_month is not None
            and sites_total > 0
            and patients_per_site_per_month > 0
            and trial_start_date is not None
        ):
            remaining = enrollment_target - enrollment_actual
            if remaining > 0:
                months_remaining = remaining / (sites_total * patients_per_site_per_month)
                projected_completion_date = today + timedelta(days=int(months_remaining * 30.44))

        # ---- alert flags --------------------------------------------------
        cfg = self._cfg
        ratio_threshold = float(cfg.get("recruiting_ratio_warning_threshold", 0.30))
        velocity_ratio  = float(cfg.get("velocity_ratio_warning_threshold", 0.40))
        slippage_alert_months = float(cfg.get("slippage_alert_months", 2.0))

        # benchmarks by TA / phase
        benchmarks = cfg.get("benchmark_patients_per_site_per_month", {})
        ta_benchmarks = benchmarks.get(therapeutic_area, benchmarks.get("default", {}))
        if isinstance(ta_benchmarks, dict):
            benchmark_velocity = ta_benchmarks.get(trial_phase, 0.40)
        else:
            benchmark_velocity = 0.40

        site_stalling = (
            sites_total > 0
            and recruiting_ratio < ratio_threshold
        )

        velocity_low = False
        if patients_per_site_per_month is not None:
            velocity_low = patients_per_site_per_month < velocity_ratio * float(benchmark_velocity)

        slippage_alert = bool(
            slippage_months is not None
            and slippage_months > slippage_alert_months
        )

        snapshot = EnrollmentSnapshot(
            id                          = str(uuid.uuid4()),
            nct_id                      = nct_id,
            asset_id                    = asset_id,
            snapshot_date               = today,
            enrollment_target           = enrollment_target,
            enrollment_actual           = enrollment_actual,
            sites_recruiting            = sites_recruiting,
            sites_total                 = sites_total,
            recruiting_ratio            = recruiting_ratio,
            site_activation_dates       = activation_dates_raw,
            trial_start_date            = trial_start_date,
            site_activation_delays      = delays,
            median_activation_delay_days = median_delay,
            activation_delay_cv         = delay_cv,
            patients_per_site_per_month = patients_per_site_per_month,
            site_activation_rate        = site_activation_rate,
            primary_completion_date     = primary_completion_date,
            prior_completion_date       = prior_completion_date,
            slippage_months             = slippage_months,
            projected_completion_date   = projected_completion_date,
        )

        flags = EnrollmentAlertFlags(
            site_stalling  = site_stalling,
            velocity_low   = velocity_low,
            slippage_alert = slippage_alert,
        )

        return EnrollmentSnapshotResult(snapshot=snapshot, alert_flags=flags)

    @staticmethod
    def _skip(reason: str, asset_id: str) -> EnrollmentSnapshotResult:
        dummy = EnrollmentSnapshot(
            id            = str(uuid.uuid4()),
            nct_id        = "",
            asset_id      = asset_id,
            snapshot_date = date.today(),
        )
        return EnrollmentSnapshotResult(
            snapshot           = dummy,
            alert_flags        = EnrollmentAlertFlags(),
            extraction_skipped = True,
            skip_reason        = reason,
        )
