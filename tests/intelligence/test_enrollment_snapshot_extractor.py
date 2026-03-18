"""
Tests for EnrollmentSnapshotExtractor — Wave 3 enrollment metrics.

Eight required scenarios:
1. Happy path: fully-populated CT record → correct metrics
2. Site stalling alert: recruiting_ratio < 0.30 → site_stalling=True
3. Velocity alert: pace < 0.4× benchmark → velocity_low=True
4. Slippage alert: prior_completion_date shifted > 2 months → slippage_alert=True
5. No prior snapshot → slippage_months=None, slippage_alert=False
6. Missing enrollment info → enrollment_target/actual=None, no crash
7. No nct_id → extraction_skipped=True
8. Site count guard: sites_total < 10 → CV threshold not applied (max_activation_delay_days used)
"""
from __future__ import annotations

from datetime import date

import pytest

from bve.intelligence.enrollment_snapshot_extractor import (
    EnrollmentAlertFlags,
    EnrollmentSnapshot,
    EnrollmentSnapshotExtractor,
    EnrollmentSnapshotResult,
    _parse_ct_date,
    _months_between,
)


# ---------------------------------------------------------------------------
# Minimal CT record builder
# ---------------------------------------------------------------------------

def _build_ct_record(
    nct_id: str = "NCT12345678",
    enrollment_count: int | None = 200,
    enrollment_type: str = "ACTUAL",
    sites: list[dict] | None = None,
    start_date: str | None = "2023-01-15",
    primary_completion_date: str | None = "2025-06-01",
) -> dict:
    """Build a minimal ClinicalTrials.gov v2 protocolSection wrapper."""
    if sites is None:
        # Default: 20 sites, 15 recruiting
        sites = [
            {"status": "RECRUITING", "statusDate": "2023-03-01"}
            for _ in range(15)
        ] + [
            {"status": "NOT_YET_RECRUITING"}
            for _ in range(5)
        ]

    enroll_info: dict = {}
    if enrollment_count is not None:
        enroll_info = {"count": enrollment_count, "type": enrollment_type}

    status_mod: dict = {}
    if start_date:
        status_mod["startDateStruct"] = {"date": start_date}
    if primary_completion_date:
        status_mod["primaryCompletionDateStruct"] = {"date": primary_completion_date}

    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id},
            "designModule": {
                "enrollmentInfo": enroll_info,
            },
            "contactsLocationsModule": {
                "locations": sites,
            },
            "statusModule": status_mod,
        }
    }


# ---------------------------------------------------------------------------
# Extractor fixture with config injected (avoids YAML dependency)
# ---------------------------------------------------------------------------

_TEST_CONFIG = {
    "recruiting_ratio_warning_threshold":    0.30,
    "velocity_ratio_warning_threshold":      0.40,
    "slippage_alert_months":                 2.0,
    "min_sites_for_cv_threshold":            10,
    "max_activation_delay_days":             180,
    "activation_delay_cv_threshold":         1.0,
    "benchmark_patients_per_site_per_month": {
        "default": {
            "phase_2": 0.60,
            "phase_3": 0.40,
        }
    },
}


@pytest.fixture
def extractor() -> EnrollmentSnapshotExtractor:
    return EnrollmentSnapshotExtractor(config=_TEST_CONFIG)


# ---------------------------------------------------------------------------
# Scenario 1: Happy path — fully-populated record
# ---------------------------------------------------------------------------

class TestHappyPath:
    """Fully-populated CT record → all metrics computed, no alerts."""

    def test_nct_id_captured(self, extractor):
        record = _build_ct_record(nct_id="NCT99887766")
        result = extractor.extract(record, "asset-001", snapshot_date=date(2024, 6, 1))
        assert result.snapshot.nct_id == "NCT99887766"

    def test_not_skipped(self, extractor):
        record = _build_ct_record()
        result = extractor.extract(record, "asset-001", snapshot_date=date(2024, 6, 1))
        assert not result.extraction_skipped
        assert result.skip_reason is None

    def test_enrollment_actual_captured(self, extractor):
        record = _build_ct_record(enrollment_count=150, enrollment_type="ACTUAL")
        result = extractor.extract(record, "asset-001", snapshot_date=date(2024, 6, 1))
        assert result.snapshot.enrollment_actual == 150
        assert result.snapshot.enrollment_target is None

    def test_enrollment_estimated_is_target(self, extractor):
        record = _build_ct_record(enrollment_count=300, enrollment_type="ESTIMATED")
        result = extractor.extract(record, "asset-001", snapshot_date=date(2024, 6, 1))
        assert result.snapshot.enrollment_target == 300
        assert result.snapshot.enrollment_actual is None

    def test_sites_recruiting_count(self, extractor):
        record = _build_ct_record()  # 15 recruiting, 5 not
        result = extractor.extract(record, "asset-001", snapshot_date=date(2024, 6, 1))
        assert result.snapshot.sites_recruiting == 15
        assert result.snapshot.sites_total == 20

    def test_recruiting_ratio(self, extractor):
        record = _build_ct_record()  # 15/20 = 0.75
        result = extractor.extract(record, "asset-001", snapshot_date=date(2024, 6, 1))
        assert result.snapshot.recruiting_ratio == pytest.approx(0.75)

    def test_no_alerts_for_healthy_trial(self, extractor):
        record = _build_ct_record(
            enrollment_count=150, enrollment_type="ACTUAL",
            sites=[{"status": "RECRUITING", "statusDate": "2023-03-01"}] * 16
            + [{"status": "NOT_YET_RECRUITING"}] * 4,
            start_date="2023-01-01",
        )
        result = extractor.extract(record, "asset-001", snapshot_date=date(2024, 1, 1))
        assert not result.alert_flags.site_stalling
        assert not result.alert_flags.slippage_alert

    def test_trial_start_date_parsed(self, extractor):
        record = _build_ct_record(start_date="2023-03-15")
        result = extractor.extract(record, "asset-001", snapshot_date=date(2024, 6, 1))
        assert result.snapshot.trial_start_date == date(2023, 3, 15)

    def test_primary_completion_date_parsed(self, extractor):
        record = _build_ct_record(primary_completion_date="2025-12-01")
        result = extractor.extract(record, "asset-001", snapshot_date=date(2024, 6, 1))
        assert result.snapshot.primary_completion_date == date(2025, 12, 1)

    def test_asset_id_stored(self, extractor):
        record = _build_ct_record()
        result = extractor.extract(record, "asset-xyz", snapshot_date=date(2024, 1, 1))
        assert result.snapshot.asset_id == "asset-xyz"

    def test_snapshot_date_stored(self, extractor):
        record = _build_ct_record()
        snap_date = date(2024, 9, 15)
        result = extractor.extract(record, "asset-001", snapshot_date=snap_date)
        assert result.snapshot.snapshot_date == snap_date


# ---------------------------------------------------------------------------
# Scenario 2: Site stalling alert
# ---------------------------------------------------------------------------

class TestSiteStalling:
    """recruiting_ratio < 0.30 → site_stalling=True."""

    def test_stalling_flag_fires(self, extractor):
        # 4 recruiting out of 20 = 0.20 < 0.30
        sites = (
            [{"status": "RECRUITING"} for _ in range(4)]
            + [{"status": "NOT_YET_RECRUITING"} for _ in range(16)]
        )
        record = _build_ct_record(sites=sites)
        result = extractor.extract(record, "asset-002", snapshot_date=date(2024, 6, 1))
        assert result.alert_flags.site_stalling

    def test_stalling_flag_clear_above_threshold(self, extractor):
        # 8 recruiting out of 20 = 0.40 > 0.30
        sites = (
            [{"status": "RECRUITING"} for _ in range(8)]
            + [{"status": "NOT_YET_RECRUITING"} for _ in range(12)]
        )
        record = _build_ct_record(sites=sites)
        result = extractor.extract(record, "asset-002", snapshot_date=date(2024, 6, 1))
        assert not result.alert_flags.site_stalling

    def test_recruiting_ratio_below_threshold(self, extractor):
        sites = (
            [{"status": "RECRUITING"} for _ in range(2)]
            + [{"status": "CLOSED"} for _ in range(10)]
        )
        record = _build_ct_record(sites=sites)
        result = extractor.extract(record, "asset-002", snapshot_date=date(2024, 6, 1))
        assert result.snapshot.recruiting_ratio < 0.30


# ---------------------------------------------------------------------------
# Scenario 3: Velocity alert
# ---------------------------------------------------------------------------

class TestVelocityAlert:
    """patients_per_site_per_month < 0.4 × benchmark → velocity_low=True."""

    def test_velocity_low_flag_fires(self, extractor):
        # 5 patients enrolled, 20 sites, 12 months elapsed
        # pace = 5/(20*12) = 0.021 << 0.4 * 0.40 = 0.16
        sites = [{"status": "RECRUITING"}] * 20
        record = _build_ct_record(
            enrollment_count=5,
            enrollment_type="ACTUAL",
            sites=sites,
            start_date="2023-01-01",
        )
        result = extractor.extract(
            record, "asset-003",
            snapshot_date=date(2024, 1, 1),
            trial_phase="phase_3",
        )
        assert result.alert_flags.velocity_low

    def test_velocity_ok_flag_clear(self, extractor):
        # 240 patients, 20 sites, 12 months → 1.0/site/month >> 0.4*0.40
        sites = [{"status": "RECRUITING"}] * 20
        record = _build_ct_record(
            enrollment_count=240,
            enrollment_type="ACTUAL",
            sites=sites,
            start_date="2023-01-01",
        )
        result = extractor.extract(
            record, "asset-003",
            snapshot_date=date(2024, 1, 1),
            trial_phase="phase_3",
        )
        assert not result.alert_flags.velocity_low

    def test_velocity_none_when_no_actual_enrollment(self, extractor):
        record = _build_ct_record(enrollment_count=200, enrollment_type="ESTIMATED")
        result = extractor.extract(record, "asset-003", snapshot_date=date(2024, 1, 1))
        assert result.snapshot.patients_per_site_per_month is None
        # velocity_low should be False when metric is unavailable
        assert not result.alert_flags.velocity_low


# ---------------------------------------------------------------------------
# Scenario 4: Slippage alert
# ---------------------------------------------------------------------------

class TestSlippageAlert:
    """primary_completion_date shifted > 2 months → slippage_alert=True."""

    def test_slippage_alert_fires(self, extractor):
        prior = EnrollmentSnapshot(
            id="prior-id",
            nct_id="NCT12345678",
            asset_id="asset-004",
            snapshot_date=date(2024, 1, 1),
            primary_completion_date=date(2025, 3, 1),
        )
        record = _build_ct_record(primary_completion_date="2025-06-01")  # 3 months slip
        result = extractor.extract(
            record, "asset-004",
            prior_snapshot=prior,
            snapshot_date=date(2024, 6, 1),
        )
        assert result.alert_flags.slippage_alert
        assert result.snapshot.slippage_months is not None
        assert result.snapshot.slippage_months > 2.0

    def test_slippage_alert_clear_small_slip(self, extractor):
        prior = EnrollmentSnapshot(
            id="prior-id",
            nct_id="NCT12345678",
            asset_id="asset-004",
            snapshot_date=date(2024, 1, 1),
            primary_completion_date=date(2025, 3, 1),
        )
        record = _build_ct_record(primary_completion_date="2025-04-15")  # ~1.5 months
        result = extractor.extract(
            record, "asset-004",
            prior_snapshot=prior,
            snapshot_date=date(2024, 6, 1),
        )
        assert not result.alert_flags.slippage_alert

    def test_prior_completion_date_stored(self, extractor):
        prior = EnrollmentSnapshot(
            id="prior-id",
            nct_id="NCT12345678",
            asset_id="asset-004",
            snapshot_date=date(2024, 1, 1),
            primary_completion_date=date(2025, 3, 1),
        )
        record = _build_ct_record(primary_completion_date="2025-06-01")
        result = extractor.extract(
            record, "asset-004",
            prior_snapshot=prior,
            snapshot_date=date(2024, 6, 1),
        )
        assert result.snapshot.prior_completion_date == date(2025, 3, 1)


# ---------------------------------------------------------------------------
# Scenario 5: No prior snapshot
# ---------------------------------------------------------------------------

class TestNoPriorSnapshot:
    """No prior snapshot → slippage_months=None, slippage_alert=False."""

    def test_slippage_none_without_prior(self, extractor):
        record = _build_ct_record()
        result = extractor.extract(record, "asset-005", snapshot_date=date(2024, 6, 1))
        assert result.snapshot.slippage_months is None
        assert result.snapshot.prior_completion_date is None

    def test_slippage_alert_false_without_prior(self, extractor):
        record = _build_ct_record()
        result = extractor.extract(record, "asset-005", snapshot_date=date(2024, 6, 1))
        assert not result.alert_flags.slippage_alert


# ---------------------------------------------------------------------------
# Scenario 6: Missing enrollment info
# ---------------------------------------------------------------------------

class TestMissingEnrollmentInfo:
    """Missing enrollment fields → None values, no crash."""

    def test_no_enrollment_info(self, extractor):
        record = _build_ct_record(enrollment_count=None)
        result = extractor.extract(record, "asset-006", snapshot_date=date(2024, 6, 1))
        assert result.snapshot.enrollment_target is None
        assert result.snapshot.enrollment_actual is None

    def test_no_start_date(self, extractor):
        record = _build_ct_record(start_date=None)
        result = extractor.extract(record, "asset-006", snapshot_date=date(2024, 6, 1))
        assert result.snapshot.trial_start_date is None
        assert result.snapshot.patients_per_site_per_month is None

    def test_no_completion_date(self, extractor):
        record = _build_ct_record(primary_completion_date=None)
        result = extractor.extract(record, "asset-006", snapshot_date=date(2024, 6, 1))
        assert result.snapshot.primary_completion_date is None

    def test_no_locations(self, extractor):
        record = _build_ct_record(sites=[])
        result = extractor.extract(record, "asset-006", snapshot_date=date(2024, 6, 1))
        assert result.snapshot.sites_total == 0
        assert result.snapshot.sites_recruiting == 0
        assert result.snapshot.recruiting_ratio == pytest.approx(0.0)

    def test_no_crash_on_empty_record(self, extractor):
        result = extractor.extract({"protocolSection": {}}, "asset-006")
        assert result.extraction_skipped or result.snapshot.nct_id == ""


# ---------------------------------------------------------------------------
# Scenario 7: No nct_id → skip
# ---------------------------------------------------------------------------

class TestNoNctId:
    """CT record with no nct_id → extraction_skipped=True."""

    def test_skip_when_no_nct_id(self, extractor):
        record = {"protocolSection": {"identificationModule": {}}}
        result = extractor.extract(record, "asset-007")
        assert result.extraction_skipped

    def test_skip_reason_populated(self, extractor):
        record = {"protocolSection": {"identificationModule": {}}}
        result = extractor.extract(record, "asset-007")
        assert result.skip_reason is not None
        assert len(result.skip_reason) > 0

    def test_no_alerts_when_skipped(self, extractor):
        record = {"protocolSection": {"identificationModule": {}}}
        result = extractor.extract(record, "asset-007")
        assert not result.alert_flags.site_stalling
        assert not result.alert_flags.velocity_low
        assert not result.alert_flags.slippage_alert


# ---------------------------------------------------------------------------
# Scenario 8: Site count guard (< 10 sites)
# ---------------------------------------------------------------------------

class TestSiteCountGuard:
    """sites_total < 10 → extraction still works; CV threshold not the primary guard."""

    def test_small_trial_no_crash(self, extractor):
        sites = [{"status": "RECRUITING", "statusDate": "2023-06-01"} for _ in range(3)]
        record = _build_ct_record(sites=sites, start_date="2023-01-01")
        result = extractor.extract(record, "asset-008", snapshot_date=date(2024, 1, 1))
        assert not result.extraction_skipped
        assert result.snapshot.sites_total == 3

    def test_small_trial_recruiting_ratio_computed(self, extractor):
        sites = (
            [{"status": "RECRUITING"}] * 2
            + [{"status": "NOT_YET_RECRUITING"}] * 6
        )
        record = _build_ct_record(sites=sites)
        result = extractor.extract(record, "asset-008", snapshot_date=date(2024, 6, 1))
        assert result.snapshot.recruiting_ratio == pytest.approx(2 / 8)

    def test_site_stalling_still_fires_small_trial(self, extractor):
        # 1 recruiting out of 8 = 0.125 < 0.30 threshold
        sites = (
            [{"status": "RECRUITING"}]
            + [{"status": "NOT_YET_RECRUITING"}] * 7
        )
        record = _build_ct_record(sites=sites)
        result = extractor.extract(record, "asset-008", snapshot_date=date(2024, 6, 1))
        assert result.alert_flags.site_stalling

    def test_activation_delay_cv_none_for_single_site(self, extractor):
        sites = [{"status": "RECRUITING", "statusDate": "2023-06-01"}]
        record = _build_ct_record(sites=sites, start_date="2023-01-01")
        result = extractor.extract(record, "asset-008", snapshot_date=date(2024, 1, 1))
        # CV requires ≥ 2 sites with delay data
        assert result.snapshot.activation_delay_cv is None


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

class TestDateHelpers:
    def test_parse_full_date(self):
        assert _parse_ct_date("2024-06-15") == date(2024, 6, 15)

    def test_parse_partial_date(self):
        d = _parse_ct_date("2024-06")
        assert d == date(2024, 6, 1)

    def test_parse_none(self):
        assert _parse_ct_date(None) is None

    def test_parse_empty(self):
        assert _parse_ct_date("") is None

    def test_months_between(self):
        d1 = date(2023, 1, 1)
        d2 = date(2024, 1, 1)
        m = _months_between(d1, d2)
        assert 11.5 < m < 12.5

    def test_months_between_same_day(self):
        d = date(2024, 6, 1)
        assert _months_between(d, d) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Idempotency invariant
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_two_calls_same_record_same_nct_id(self, extractor):
        record = _build_ct_record(nct_id="NCT55555555")
        r1 = extractor.extract(record, "asset-x", snapshot_date=date(2024, 6, 1))
        r2 = extractor.extract(record, "asset-x", snapshot_date=date(2024, 6, 1))
        assert r1.snapshot.nct_id == r2.snapshot.nct_id
        assert r1.snapshot.recruiting_ratio == r2.snapshot.recruiting_ratio
        assert r1.alert_flags == r2.alert_flags

    def test_snapshot_has_uuid_id(self, extractor):
        record = _build_ct_record()
        result = extractor.extract(record, "asset-x", snapshot_date=date(2024, 6, 1))
        import uuid
        parsed = uuid.UUID(result.snapshot.id)
        assert str(parsed) == result.snapshot.id
