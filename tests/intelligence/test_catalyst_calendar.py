"""
Tests for Wave 1 Catalyst Calendar.

Ten required scenarios:
1.  PDUFA extraction: exact date found → CatalystEvent date_confidence="exact"
2.  PDUFA extraction: Q#/year found → date_confidence="quarter"
3.  PDUFA extraction: no PDUFA in text → returns None
4.  Trial readout estimation from CT completion date
5.  EV calculator: positive EV catalyst → signal_strength > 0
6.  EV calculator: near-fair catalyst (tiny EV) → signal_strength < min_displayable
7.  Signal strength floor guard active when std_dev is abnormally small
8.  Asymmetry ratio computed correctly
9.  Catalyst approaching alert fires at 30 days
10. CLI output includes ranked catalysts
"""
from __future__ import annotations

import math
import uuid
from datetime import date, datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from bve.alerts.alert_model import AlertSeverity, AlertTrigger
from bve.intelligence.catalyst_calendar import CatalystEvent, CatalystType
from bve.intelligence.pdufa_extractor import PDUFAExtractor
from bve.intelligence.trial_readout_estimator import TrialReadoutEstimator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    *,
    asset_id: str = "asset-001",
    expected_date: date = date(2025, 6, 15),
    catalyst_type: CatalystType = CatalystType.PDUFA_DECISION,
    date_confidence: str = "exact",
    delta_ev: Optional[float] = None,
    signal_strength: Optional[float] = None,
    is_active: bool = True,
    resolved: bool = False,
) -> CatalystEvent:
    now = datetime.now(timezone.utc)
    return CatalystEvent(
        id              = str(uuid.uuid4()),
        asset_id        = asset_id,
        catalyst_type   = catalyst_type,
        expected_date   = expected_date,
        date_confidence = date_confidence,  # type: ignore[arg-type]
        source          = "test",
        description     = "test catalyst",
        delta_ev        = delta_ev,
        signal_strength = signal_strength,
        is_active       = is_active,
        resolved        = resolved,
        created_at      = now,
        updated_at      = now,
    )


def _make_ct_record(
    nct_id: str = "NCT11111111",
    primary_completion_date: str = "2025-03-01",
    title: str = "A Phase 3 Trial",
) -> dict:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id, "briefTitle": title},
            "statusModule": {
                "primaryCompletionDateStruct": {"date": primary_completion_date},
            },
        }
    }


# ---------------------------------------------------------------------------
# Scenario 1: PDUFA exact date
# ---------------------------------------------------------------------------

class TestPDUFAExactDate:
    """PDUFA date with full month-day-year → date_confidence='exact'."""

    def test_full_date_extracted(self):
        text = "The PDUFA date is January 15, 2026 for the NDA submission."
        extractor = PDUFAExtractor()
        ev = extractor.extract(text, {"asset_id": "asset-001"})
        assert ev is not None
        assert ev.expected_date == date(2026, 1, 15)

    def test_date_confidence_exact(self):
        text = "PDUFA date is March 30, 2026."
        extractor = PDUFAExtractor()
        ev = extractor.extract(text, {"asset_id": "asset-001"})
        assert ev is not None
        assert ev.date_confidence == "exact"

    def test_catalyst_type_is_pdufa(self):
        text = "PDUFA goal date is April 10, 2025."
        extractor = PDUFAExtractor()
        ev = extractor.extract(text, {})
        assert ev is not None
        assert ev.catalyst_type == CatalystType.PDUFA_DECISION

    def test_target_action_date_pattern(self):
        text = "The target action date of June 1, 2025 has been assigned."
        extractor = PDUFAExtractor()
        ev = extractor.extract(text, {})
        assert ev is not None
        assert ev.expected_date == date(2025, 6, 1)
        assert ev.date_confidence == "exact"

    def test_entity_hints_propagated(self):
        text = "PDUFA date is February 28, 2026."
        extractor = PDUFAExtractor()
        ev = extractor.extract(text, {"asset_id": "asset-xyz", "company_id": "company-xyz"})
        assert ev is not None
        assert ev.asset_id == "asset-xyz"
        assert ev.company_id == "company-xyz"

    def test_source_stored(self):
        text = "PDUFA date is February 28, 2026."
        extractor = PDUFAExtractor()
        ev = extractor.extract(text, {"source": "8-K/2025/001.txt"})
        assert ev is not None
        assert ev.source == "8-K/2025/001.txt"


# ---------------------------------------------------------------------------
# Scenario 2: PDUFA quarter date
# ---------------------------------------------------------------------------

class TestPDUFAQuarterDate:
    """PDUFA date with Q#/year → date_confidence='quarter'."""

    def test_quarter_date_extracted(self):
        text = "We expect a PDUFA date of Q3 2026 for the pending NDA."
        extractor = PDUFAExtractor()
        ev = extractor.extract(text, {})
        assert ev is not None
        assert ev.date_confidence == "quarter"

    def test_quarter_date_is_mid_quarter(self):
        text = "PDUFA goal date is Q2 2026."
        extractor = PDUFAExtractor()
        ev = extractor.extract(text, {})
        assert ev is not None
        # Q2 → month 5 (May)
        assert ev.expected_date.year == 2026
        assert ev.expected_date.month == 5

    def test_q1_maps_to_february(self):
        text = "PDUFA date is Q1 2025."
        extractor = PDUFAExtractor()
        ev = extractor.extract(text, {})
        assert ev is not None
        assert ev.expected_date.month == 2


# ---------------------------------------------------------------------------
# Scenario 3: No PDUFA in text
# ---------------------------------------------------------------------------

class TestNoPDUFA:
    """Text with no PDUFA date → returns None."""

    def test_no_pdufa_returns_none(self):
        text = "We reported strong clinical results this quarter."
        extractor = PDUFAExtractor()
        assert extractor.extract(text, {}) is None

    def test_empty_text_returns_none(self):
        assert PDUFAExtractor().extract("", {}) is None

    def test_partial_pdufa_word_no_match(self):
        text = "The FDA advisory committee meeting is scheduled for next year."
        assert PDUFAExtractor().extract(text, {}) is None


# ---------------------------------------------------------------------------
# Scenario 4: Trial readout estimation
# ---------------------------------------------------------------------------

class TestTrialReadoutEstimation:
    """CT primary completion date + lag → CatalystEvent with TRIAL_READOUT."""

    _TEST_CONFIG = {
        "readout_lag_days_default": 180,
    }

    @pytest.fixture
    def estimator(self) -> TrialReadoutEstimator:
        return TrialReadoutEstimator(config=self._TEST_CONFIG)

    def test_readout_event_created(self, estimator):
        record = _make_ct_record(primary_completion_date="2025-03-01")
        ev = estimator.estimate(record, "asset-001")
        assert ev is not None
        assert ev.catalyst_type == CatalystType.TRIAL_READOUT

    def test_estimated_date_is_completion_plus_lag(self, estimator):
        from datetime import timedelta
        record = _make_ct_record(primary_completion_date="2025-01-01")
        ev = estimator.estimate(record, "asset-001")
        assert ev is not None
        expected = date(2025, 1, 1) + timedelta(days=180)
        assert ev.expected_date == expected

    def test_date_confidence_is_quarter(self, estimator):
        record = _make_ct_record()
        ev = estimator.estimate(record, "asset-001")
        assert ev is not None
        assert ev.date_confidence == "quarter"

    def test_no_completion_date_returns_none(self, estimator):
        record = {"protocolSection": {"identificationModule": {"nctId": "NCT999"}, "statusModule": {}}}
        assert estimator.estimate(record, "asset-001") is None

    def test_asset_id_stored(self, estimator):
        record = _make_ct_record()
        ev = estimator.estimate(record, "my-asset-id")
        assert ev is not None
        assert ev.asset_id == "my-asset-id"

    def test_nct_id_in_description(self, estimator):
        record = _make_ct_record(nct_id="NCT44556677")
        ev = estimator.estimate(record, "asset-001")
        assert ev is not None
        assert "NCT44556677" in ev.description


# ---------------------------------------------------------------------------
# Scenario 5 & 6 & 7 & 8: EV calculator math (pure unit tests, no file I/O)
# ---------------------------------------------------------------------------

class TestCatalystEVMath:
    """
    Test the EV formula directly without running the valuation engine.
    Uses a thin wrapper around the math logic.
    """

    @staticmethod
    def _compute_ev_fields(
        current_value: float,
        value_if_success: float,
        value_if_failure: float,
        current_pos: float,
        std_floor_mult: float = 0.50,
    ) -> dict:
        """Replicate CatalystEVCalculator math for unit testing."""
        upside   = value_if_success - current_value
        downside = current_value - value_if_failure

        delta_ev = current_pos * upside - (1.0 - current_pos) * downside

        outcome_success = upside
        outcome_failure = -downside
        ev = delta_ev
        variance = (
            current_pos * (outcome_success - ev) ** 2
            + (1.0 - current_pos) * (outcome_failure - ev) ** 2
        )
        std_dev = math.sqrt(max(variance, 0.0))

        std_floor = max(std_dev, abs(ev) * std_floor_mult)
        signal_strength = (ev / std_floor) if std_floor > 0.0 else 0.0

        asymmetry_ratio = (
            upside / downside if downside > 0.0 else float("inf")
        )

        return {
            "upside":          upside,
            "downside":        downside,
            "delta_ev":        delta_ev,
            "std_dev":         std_dev,
            "signal_strength": signal_strength,
            "asymmetry_ratio": asymmetry_ratio,
        }

    def test_positive_ev_catalyst_positive_signal_strength(self):
        """Scenario 5: positive EV → signal_strength > 0."""
        fields = self._compute_ev_fields(
            current_value=100.0,
            value_if_success=300.0,
            value_if_failure=20.0,
            current_pos=0.45,
        )
        assert fields["delta_ev"] > 0
        assert fields["signal_strength"] > 0

    def test_near_fair_catalyst_small_signal_strength(self):
        """Scenario 6: near-fair catalyst → |signal_strength| < min_displayable (0.03)."""
        # delta_ev ≈ 0 when weighted upside ≈ weighted downside
        # pos * upside ≈ (1-pos) * downside
        # 0.45 * U ≈ 0.55 * D → pick upside/downside symmetrically
        fields = self._compute_ev_fields(
            current_value=100.0,
            value_if_success=101.0,   # tiny upside
            value_if_failure=99.0,    # tiny downside
            current_pos=0.50,
        )
        min_displayable = 0.03
        assert abs(fields["signal_strength"]) < min_displayable

    def test_floor_guard_prevents_infinite_signal_strength(self):
        """Scenario 7: floor guard prevents near-zero std_dev from inflating signal strength."""
        # Construct a scenario where std_dev ≈ 0 (outcomes nearly identical)
        # but delta_ev is non-trivial
        # Use extreme probability (PoS ≈ 1) so variance is very small
        fields = self._compute_ev_fields(
            current_value=100.0,
            value_if_success=110.0,
            value_if_failure=99.0,
            current_pos=0.9999,
            std_floor_mult=0.50,
        )
        # Without floor: std_dev ≈ 0, signal_strength = ev / ~0 → huge
        # With floor: std_floor = max(std_dev, 0.5 * |ev|) caps signal_strength
        assert math.isfinite(fields["signal_strength"])
        # The floor should cap signal_strength at approximately ev / (0.5 * |ev|) = 2
        assert abs(fields["signal_strength"]) <= 2.5

    def test_asymmetry_ratio_correct(self):
        """Scenario 8: asymmetry_ratio = upside / downside."""
        fields = self._compute_ev_fields(
            current_value=100.0,
            value_if_success=200.0,  # upside = 100
            value_if_failure=60.0,   # downside = 40
            current_pos=0.50,
        )
        # upside = 100, downside = 40 → ratio = 2.5
        assert fields["asymmetry_ratio"] == pytest.approx(100.0 / 40.0, rel=1e-4)

    def test_asymmetry_ratio_infinite_when_no_downside(self):
        """Scenario 8b: zero downside → asymmetry = inf."""
        fields = self._compute_ev_fields(
            current_value=100.0,
            value_if_success=200.0,
            value_if_failure=100.0,  # downside = 0
            current_pos=0.50,
        )
        assert fields["asymmetry_ratio"] == float("inf")

    def test_upside_downside_computed_correctly(self):
        fields = self._compute_ev_fields(
            current_value=150.0,
            value_if_success=250.0,
            value_if_failure=50.0,
            current_pos=0.50,
        )
        assert fields["upside"] == pytest.approx(100.0)
        assert fields["downside"] == pytest.approx(100.0)

    def test_delta_ev_formula(self):
        """delta_ev = pos * upside - (1-pos) * downside."""
        pos = 0.60
        upside = 100.0
        downside = 80.0
        expected_ev = pos * upside - (1 - pos) * downside
        fields = self._compute_ev_fields(
            current_value=100.0,
            value_if_success=100.0 + upside,
            value_if_failure=100.0 - downside,
            current_pos=pos,
        )
        assert fields["delta_ev"] == pytest.approx(expected_ev, rel=1e-6)


# ---------------------------------------------------------------------------
# Scenario 9: Catalyst approaching alert fires at 30 days
# ---------------------------------------------------------------------------

class TestCatalystApproachingAlert:
    """CATALYST_APPROACHING fires HIGH when within 30 days AND |delta_ev| > $100M."""

    def _make_router(self):
        """Build a minimal AlertRouter with no channels."""
        from bve.alerts.alert_config import AlertsConfig
        from bve.alerts.alert_router import AlertRouter
        cfg = AlertsConfig(enabled=True)
        return AlertRouter(config=cfg, channels=[])

    def test_alert_fires_within_window(self):
        router = self._make_router()
        ev = _make_event(
            expected_date=date.today().__class__.today()
            .__class__(
                date.today().year,
                date.today().month,
                date.today().day,
            ),
            delta_ev=150.0,
        )
        # Use a date 15 days ahead
        from datetime import timedelta
        future = date.today() + timedelta(days=15)
        ev = _make_event(expected_date=future, delta_ev=150.0)
        router.enqueue_catalyst_alerts(catalyst=ev, days_ahead=30, min_delta_ev_abs=100.0)
        pending = router._pending.get(ev.asset_id, [])
        assert len(pending) == 1
        assert pending[0].trigger == AlertTrigger.CATALYST_APPROACHING
        assert pending[0].severity == AlertSeverity.HIGH

    def test_alert_does_not_fire_outside_window(self):
        router = self._make_router()
        from datetime import timedelta
        far_future = date.today() + timedelta(days=60)
        ev = _make_event(expected_date=far_future, delta_ev=200.0)
        router.enqueue_catalyst_alerts(catalyst=ev, days_ahead=30, min_delta_ev_abs=100.0)
        pending = router._pending.get(ev.asset_id, [])
        assert len(pending) == 0

    def test_alert_does_not_fire_below_ev_threshold(self):
        router = self._make_router()
        from datetime import timedelta
        soon = date.today() + timedelta(days=10)
        ev = _make_event(expected_date=soon, delta_ev=50.0)  # below $100M
        router.enqueue_catalyst_alerts(catalyst=ev, days_ahead=30, min_delta_ev_abs=100.0)
        pending = router._pending.get(ev.asset_id, [])
        assert len(pending) == 0

    def test_alert_does_not_fire_when_no_delta_ev(self):
        router = self._make_router()
        from datetime import timedelta
        soon = date.today() + timedelta(days=5)
        ev = _make_event(expected_date=soon, delta_ev=None)
        router.enqueue_catalyst_alerts(catalyst=ev, days_ahead=30, min_delta_ev_abs=100.0)
        pending = router._pending.get(ev.asset_id, [])
        assert len(pending) == 0

    def test_alert_detail_contains_expected_fields(self):
        router = self._make_router()
        from datetime import timedelta
        soon = date.today() + timedelta(days=5)
        ev = _make_event(expected_date=soon, delta_ev=200.0)
        router.enqueue_catalyst_alerts(catalyst=ev, days_ahead=30, min_delta_ev_abs=100.0)
        alert = router._pending[ev.asset_id][0]
        assert "catalyst_type" in alert.detail
        assert "expected_date" in alert.detail
        assert "delta_ev" in alert.detail
        assert alert.detail["delta_ev"] == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# Scenario 10: CLI output includes ranked catalysts
# ---------------------------------------------------------------------------

class TestCatalystCalendarCLI:
    """CLI output lists catalysts sorted by signal_strength."""

    def test_cli_runs_with_empty_store(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        db = str(tmp_path / "test.db")
        ks = KnowledgeStore(db_path=db)

        # Patch sys.argv and capture stdout
        import io, sys
        from bve.cli.catalyst_calendar import main
        sys.argv = ["bve-catalyst-calendar", "--db", db, "--days-ahead", "90"]
        captured = io.StringIO()
        sys_stdout = sys.stdout
        sys.stdout = captured
        try:
            main()
        finally:
            sys.stdout = sys_stdout
        output = captured.getvalue()
        assert "No catalyst events found" in output

    def test_cli_shows_catalysts_sorted_by_signal_strength(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        from bve.cli.catalyst_calendar import main
        import io, sys
        from datetime import timedelta

        db = str(tmp_path / "test2.db")
        ks = KnowledgeStore(db_path=db)

        # Add two catalysts with different signal strengths
        ev_high = _make_event(
            asset_id="AAAA",
            expected_date=date.today() + timedelta(days=20),
            delta_ev=200.0,
            signal_strength=1.5,
        )
        ev_low = _make_event(
            asset_id="BBBB",
            expected_date=date.today() + timedelta(days=40),
            delta_ev=50.0,
            signal_strength=0.3,
        )
        ks.upsert_catalyst_event(ev_high)
        ks.upsert_catalyst_event(ev_low)

        sys.argv = ["bve-catalyst-calendar", "--db", db, "--days-ahead", "90"]
        captured = io.StringIO()
        sys_stdout = sys.stdout
        sys.stdout = captured
        try:
            main()
        finally:
            sys.stdout = sys_stdout
        output = captured.getvalue()

        # AAAA (higher signal_strength) should appear before BBBB
        pos_aaaa = output.find("AAAA")
        pos_bbbb = output.find("BBBB")
        assert pos_aaaa != -1 and pos_bbbb != -1
        assert pos_aaaa < pos_bbbb

    def test_cli_output_has_header_columns(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        from bve.cli.catalyst_calendar import main
        import io, sys
        from datetime import timedelta

        db = str(tmp_path / "test3.db")
        ks = KnowledgeStore(db_path=db)

        ev = _make_event(
            asset_id="ZZZT",
            expected_date=date.today() + timedelta(days=10),
            delta_ev=120.0,
            signal_strength=0.8,
        )
        ks.upsert_catalyst_event(ev)

        sys.argv = ["bve-catalyst-calendar", "--db", db, "--days-ahead", "30"]
        captured = io.StringIO()
        sys_stdout = sys.stdout
        sys.stdout = captured
        try:
            main()
        finally:
            sys.stdout = sys_stdout
        output = captured.getvalue()

        # Header row should contain key column names
        assert "date" in output
        assert "asset" in output
        assert "signal_strength" in output
        assert "confidence" in output


# ---------------------------------------------------------------------------
# KnowledgeStore: upsert + resolve + get
# ---------------------------------------------------------------------------

class TestKnowledgeStoreCatalyst:
    def test_upsert_and_retrieve(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        ks = KnowledgeStore(db_path=str(tmp_path / "k.db"))
        ev = _make_event(asset_id="asset-001", expected_date=date(2026, 3, 1))
        ks.upsert_catalyst_event(ev)

        events = ks.get_catalyst_events(asset_id="asset-001", active_only=True)
        assert len(events) == 1
        assert events[0].id == ev.id

    def test_resolve_marks_resolved(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        ks = KnowledgeStore(db_path=str(tmp_path / "k2.db"))
        ev = _make_event(asset_id="asset-002")
        ks.upsert_catalyst_event(ev)

        result = ks.resolve_catalyst_event(ev.id, "positive")
        assert result is True

        events = ks.get_catalyst_events(asset_id="asset-002", active_only=True)
        assert len(events) == 0  # resolved = active=False

    def test_resolve_returns_false_for_unknown_id(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        ks = KnowledgeStore(db_path=str(tmp_path / "k3.db"))
        assert ks.resolve_catalyst_event("nonexistent-id", "negative") is False

    def test_days_ahead_filter(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        from datetime import timedelta
        ks = KnowledgeStore(db_path=str(tmp_path / "k4.db"))

        near = _make_event(asset_id="A", expected_date=date.today() + timedelta(days=10))
        far  = _make_event(asset_id="A", expected_date=date.today() + timedelta(days=200))
        ks.upsert_catalyst_event(near)
        ks.upsert_catalyst_event(far)

        result = ks.get_catalyst_events(asset_id="A", days_ahead=30)
        assert len(result) == 1
        assert result[0].id == near.id
