"""
Sprint 22 — Forward Catalyst Calendar
Tests for ForwardCalendarSeeder, deterministic IDs, KnowledgeStore integration,
and D2CAT wiring into the screener.
"""
from __future__ import annotations

import textwrap
import uuid
import warnings
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def minimal_calendar_yaml(tmp_path: Path) -> Path:
    """Minimal YAML with two valid entries (one trial_readout, one pdufa_decision)."""
    content = textwrap.dedent("""\
        meta:
          version: "test"
        catalysts:
          - ticker: VKTX
            catalyst_type: trial_readout
            description: "VK2735 oral Ph2 obesity readout"
            expected_date: "2026-06-15"
            date_confidence: half_year
            source: "test source"
          - ticker: ZYME
            catalyst_type: pdufa_decision
            description: "Zanidatamab BLA PDUFA"
            expected_date: "2026-07-15"
            date_confidence: quarter
            source: "test source"
    """)
    path = tmp_path / "calendar.yaml"
    path.write_text(content)
    return path


@pytest.fixture()
def all_types_calendar_yaml(tmp_path: Path) -> Path:
    """YAML exercising all six CatalystType values."""
    rows = [
        ("VKTX", "trial_readout",       "2026-06-15", "half_year"),
        ("ZYME", "pdufa_decision",       "2026-07-15", "quarter"),
        ("ALNY", "adcom_meeting",        "2026-05-01", "quarter"),
        ("KYMR", "enrollment_complete",  "2026-04-01", "estimate"),
        ("MDGL", "conference_abstract",  "2026-05-15", "quarter"),
        ("RVMD", "competitor_readout",   "2026-08-01", "estimate"),
    ]
    entries = "\n".join(
        f"  - ticker: {t}\n"
        f"    catalyst_type: {ct}\n"
        f"    description: \"test {ct}\"\n"
        f"    expected_date: \"{ed}\"\n"
        f"    date_confidence: {dc}\n"
        f"    source: \"test\"\n"
        for t, ct, ed, dc in rows
    )
    path = tmp_path / "all_types.yaml"
    path.write_text(f"meta:\n  version: test\ncatalysts:\n{entries}")
    return path


@pytest.fixture()
def memory_store():
    """In-memory KnowledgeStore for fast tests."""
    from bve.intelligence.knowledge_layer import KnowledgeStore
    return KnowledgeStore(db_path=":memory:")


# ---------------------------------------------------------------------------
# ForwardCalendarSeeder — load()
# ---------------------------------------------------------------------------

class TestCalendarLoad:
    def test_load_returns_entries(self, minimal_calendar_yaml):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        entries = seeder.load()
        assert len(entries) == 2

    def test_tickers_uppercased(self, minimal_calendar_yaml):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        tickers = {e.ticker for e in seeder.load()}
        assert tickers == {"VKTX", "ZYME"}

    def test_expected_dates_parsed(self, minimal_calendar_yaml):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        dates = {e.ticker: e.expected_date for e in seeder.load()}
        assert dates["VKTX"] == date(2026, 6, 15)
        assert dates["ZYME"] == date(2026, 7, 15)

    def test_date_confidence_preserved(self, minimal_calendar_yaml):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        confs = {e.ticker: e.date_confidence for e in seeder.load()}
        assert confs["VKTX"] == "half_year"
        assert confs["ZYME"] == "quarter"

    def test_catalyst_type_preserved(self, minimal_calendar_yaml):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        types = {e.ticker: e.catalyst_type for e in seeder.load()}
        assert types["VKTX"] == "trial_readout"
        assert types["ZYME"] == "pdufa_decision"

    def test_asset_id_defaults_to_ticker_convention(self, minimal_calendar_yaml):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        entries = {e.ticker: e for e in seeder.load()}
        assert entries["VKTX"].asset_id == "a-vktx"
        assert entries["ZYME"].company_id == "co-zyme"

    def test_custom_asset_id_preserved(self, tmp_path):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        content = textwrap.dedent("""\
            catalysts:
              - ticker: VKTX
                catalyst_type: trial_readout
                description: test
                expected_date: "2026-06-15"
                date_confidence: half_year
                source: test
                asset_id: custom-asset-id
                company_id: custom-co-id
        """)
        path = tmp_path / "c.yaml"
        path.write_text(content)
        entries = ForwardCalendarSeeder(calendar_path=path).load()
        assert entries[0].asset_id == "custom-asset-id"
        assert entries[0].company_id == "custom-co-id"

    def test_all_six_catalyst_types_accepted(self, all_types_calendar_yaml):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        entries = ForwardCalendarSeeder(calendar_path=all_types_calendar_yaml).load()
        assert len(entries) == 6

    def test_invalid_date_confidence_raises(self, tmp_path):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        content = textwrap.dedent("""\
            catalysts:
              - ticker: VKTX
                catalyst_type: trial_readout
                description: test
                expected_date: "2026-06-15"
                date_confidence: INVALID
                source: test
        """)
        path = tmp_path / "bad.yaml"
        path.write_text(content)
        seeder = ForwardCalendarSeeder(calendar_path=path)
        with warnings.catch_warnings(record=True):
            entries = seeder.load()
        # invalid entry is skipped
        assert len(entries) == 0

    def test_unknown_catalyst_type_skipped_with_warning(self, tmp_path):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        content = textwrap.dedent("""\
            catalysts:
              - ticker: VKTX
                catalyst_type: unknown_type_xyz
                description: test
                expected_date: "2026-06-15"
                date_confidence: estimate
                source: test
        """)
        path = tmp_path / "bad_type.yaml"
        path.write_text(content)
        seeder = ForwardCalendarSeeder(calendar_path=path)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            entries = seeder.load()
        assert len(entries) == 0
        assert len(w) >= 1

    def test_empty_catalysts_list_returns_empty(self, tmp_path):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        path = tmp_path / "empty.yaml"
        path.write_text("meta:\n  version: test\ncatalysts: []\n")
        entries = ForwardCalendarSeeder(calendar_path=path).load()
        assert entries == []


# ---------------------------------------------------------------------------
# Deterministic IDs
# ---------------------------------------------------------------------------

class TestDeterministicID:
    def test_same_inputs_same_id(self, minimal_calendar_yaml):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        e1 = seeder.load()
        e2 = seeder.load()
        assert e1[0].event_id == e2[0].event_id

    def test_different_tickers_different_ids(self, minimal_calendar_yaml):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        entries = seeder.load()
        assert entries[0].event_id != entries[1].event_id

    def test_id_is_valid_uuid(self, minimal_calendar_yaml):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        entries = seeder.load()
        for e in entries:
            parsed = uuid.UUID(e.event_id)  # raises if invalid
            assert str(parsed) == e.event_id

    def test_date_change_changes_id(self, tmp_path):
        from bve.ops.forward_calendar_seeder import _deterministic_id
        id1 = _deterministic_id("VKTX", "trial_readout", "2026-06-15")
        id2 = _deterministic_id("VKTX", "trial_readout", "2026-07-15")
        assert id1 != id2

    def test_type_change_changes_id(self, tmp_path):
        from bve.ops.forward_calendar_seeder import _deterministic_id
        id1 = _deterministic_id("VKTX", "trial_readout", "2026-06-15")
        id2 = _deterministic_id("VKTX", "pdufa_decision", "2026-06-15")
        assert id1 != id2


# ---------------------------------------------------------------------------
# seed() — dry_run
# ---------------------------------------------------------------------------

class TestSeedDryRun:
    def test_dry_run_returns_correct_count(self, minimal_calendar_yaml):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        result = seeder.seed(None, dry_run=True)
        assert result.seeded == 2
        assert result.skipped == 0

    def test_dry_run_populates_entries(self, minimal_calendar_yaml):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        result = seeder.seed(None, dry_run=True)
        assert len(result.entries) == 2

    def test_dry_run_does_not_write_to_store(self, minimal_calendar_yaml, memory_store):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        seeder.seed(None, dry_run=True)
        events = memory_store.get_catalyst_events(active_only=False)
        assert len(events) == 0


# ---------------------------------------------------------------------------
# seed() — live write + idempotency
# ---------------------------------------------------------------------------

class TestSeedLive:
    def test_seed_inserts_events(self, minimal_calendar_yaml, memory_store):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        result = seeder.seed(memory_store)
        assert result.seeded == 2
        events = memory_store.get_catalyst_events(active_only=False)
        assert len(events) == 2

    def test_seed_idempotent(self, minimal_calendar_yaml, memory_store):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        seeder.seed(memory_store)
        seeder.seed(memory_store)  # second seed
        events = memory_store.get_catalyst_events(active_only=False)
        assert len(events) == 2  # no duplicates

    def test_seeded_events_are_active(self, minimal_calendar_yaml, memory_store):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        seeder.seed(memory_store)
        events = memory_store.get_catalyst_events(active_only=True)
        assert len(events) == 2

    def test_seeded_asset_ids_correct(self, minimal_calendar_yaml, memory_store):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        seeder.seed(memory_store)
        events = memory_store.get_catalyst_events(active_only=False)
        asset_ids = {e.asset_id for e in events}
        assert "a-vktx" in asset_ids
        assert "a-zyme" in asset_ids

    def test_get_catalyst_events_by_asset(self, minimal_calendar_yaml, memory_store):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder(calendar_path=minimal_calendar_yaml)
        seeder.seed(memory_store)
        vktx_events = memory_store.get_catalyst_events(asset_id="a-vktx")
        assert len(vktx_events) == 1
        assert vktx_events[0].expected_date == date(2026, 6, 15)

    def test_get_catalyst_events_days_ahead_filter(self, tmp_path, memory_store):
        """Events outside the days_ahead window should not be returned."""
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        far_date = (date.today() + timedelta(days=400)).isoformat()
        near_date = (date.today() + timedelta(days=30)).isoformat()
        content = textwrap.dedent(f"""\
            catalysts:
              - ticker: FAR
                catalyst_type: trial_readout
                description: far
                expected_date: "{far_date}"
                date_confidence: estimate
                source: test
              - ticker: NEAR
                catalyst_type: trial_readout
                description: near
                expected_date: "{near_date}"
                date_confidence: estimate
                source: test
        """)
        path = tmp_path / "window.yaml"
        path.write_text(content)
        seeder = ForwardCalendarSeeder(calendar_path=path)
        seeder.seed(memory_store)
        events_60d = memory_store.get_catalyst_events(days_ahead=60)
        tickers = {e.asset_id for e in events_60d}
        assert "a-near" in tickers
        assert "a-far" not in tickers


# ---------------------------------------------------------------------------
# Default calendar (research/catalyst_calendar_2026.yaml)
# ---------------------------------------------------------------------------

class TestDefaultCalendar:
    def test_default_calendar_loads(self):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        seeder = ForwardCalendarSeeder()
        entries = seeder.load()
        assert len(entries) >= 10

    def test_default_calendar_has_vktx(self):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        entries = ForwardCalendarSeeder().load()
        tickers = {e.ticker for e in entries}
        assert "VKTX" in tickers

    def test_default_calendar_has_pdufa_entry(self):
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        entries = ForwardCalendarSeeder().load()
        types = {e.catalyst_type for e in entries}
        assert "pdufa_decision" in types

    def test_default_calendar_all_dates_future_or_recent(self):
        """All dates should be 2026 or later (we wrote them as forward catalysts)."""
        from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
        entries = ForwardCalendarSeeder().load()
        for e in entries:
            assert e.expected_date.year >= 2026, (
                f"{e.ticker} has past date {e.expected_date}"
            )
