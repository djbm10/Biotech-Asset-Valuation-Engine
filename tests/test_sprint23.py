"""
Sprint 23 — Historical Trial Event Seeder
Tests for TrialEventBackfiller: YAML parsing, deterministic IDs, idempotency,
outcome_label validation, no-lookahead invariant, CLI dry-run, and default YAML.
"""
from __future__ import annotations

import textwrap
import warnings
from datetime import date
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def minimal_events_yaml(tmp_path: Path) -> Path:
    """Minimal YAML with two valid trial readout entries."""
    content = textwrap.dedent("""\
        meta:
          description: test
        events:
          - asset_id: a-alny
            ticker: ALNY
            event_type: trial_readout
            announced_at: "2022-11-14"
            outcome_label: positive
            headline: "HELIOS-B inclisiran Phase 3 positive"
          - asset_id: a-vktx
            ticker: VKTX
            event_type: trial_readout
            announced_at: "2023-06-12"
            outcome_label: negative
            headline: "VK2809 Phase 2b NASH — missed primary endpoint"
    """)
    path = tmp_path / "events.yaml"
    path.write_text(content)
    return path


@pytest.fixture()
def all_types_events_yaml(tmp_path: Path) -> Path:
    """YAML exercising all valid event_type values."""
    rows = [
        ("a-alny",  "ALNY",  "trial_readout",       "2022-11-14", "positive"),
        ("a-zyme",  "ZYME",  "pdufa_decision",       "2022-06-01", "positive"),
        ("a-regn",  "REGN",  "adcom_meeting",        "2022-03-10", "mixed"),
        ("a-kymr",  "KYMR",  "enrollment_complete",  "2022-09-01", "neutral"),
        ("a-mdgl",  "MDGL",  "conference_abstract",  "2022-11-05", "positive"),
        ("a-rvmd",  "RVMD",  "competitor_readout",   "2023-02-01", "negative"),
    ]
    entries = "\n".join(
        f"  - asset_id: {a}\n"
        f"    ticker: {t}\n"
        f"    event_type: {et}\n"
        f"    announced_at: \"{dt}\"\n"
        f"    outcome_label: {ol}\n"
        f"    headline: \"test headline\"\n"
        for a, t, et, dt, ol in rows
    )
    path = tmp_path / "all_types.yaml"
    path.write_text(f"events:\n{entries}")
    return path


@pytest.fixture()
def replay_store(tmp_path: Path):
    """In-memory ReplayStore for fast tests."""
    from bve.ops.historical_replay import ReplayStore
    db_path = str(tmp_path / "test_replay.sqlite")
    store = ReplayStore(db_path)
    yield store
    store.close()


# ---------------------------------------------------------------------------
# TrialEventBackfiller — load()
# ---------------------------------------------------------------------------

class TestBackfillerLoad:
    def test_load_returns_entries(self, minimal_events_yaml):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        backfiller = TrialEventBackfiller(events_path=minimal_events_yaml)
        rows = backfiller.load()
        assert len(rows) == 2

    def test_tickers_uppercased(self, minimal_events_yaml):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        rows = TrialEventBackfiller(events_path=minimal_events_yaml).load()
        tickers = {r["ticker"] for r in rows}
        assert tickers == {"ALNY", "VKTX"}

    def test_dates_preserved_as_strings(self, minimal_events_yaml):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        rows = TrialEventBackfiller(events_path=minimal_events_yaml).load()
        dates = {r["ticker"]: r["announced_at"] for r in rows}
        assert dates["ALNY"] == "2022-11-14"
        assert dates["VKTX"] == "2023-06-12"

    def test_outcome_labels_preserved(self, minimal_events_yaml):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        rows = TrialEventBackfiller(events_path=minimal_events_yaml).load()
        labels = {r["ticker"]: r["outcome_label"] for r in rows}
        assert labels["ALNY"] == "positive"
        assert labels["VKTX"] == "negative"

    def test_event_type_preserved(self, minimal_events_yaml):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        rows = TrialEventBackfiller(events_path=minimal_events_yaml).load()
        assert all(r["event_type"] == "trial_readout" for r in rows)

    def test_all_six_event_types_accepted(self, all_types_events_yaml):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        rows = TrialEventBackfiller(events_path=all_types_events_yaml).load()
        assert len(rows) == 6

    def test_unknown_event_type_skipped_with_warning(self, tmp_path):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        content = textwrap.dedent("""\
            events:
              - asset_id: a-alny
                ticker: ALNY
                event_type: mystery_event
                announced_at: "2022-11-14"
                outcome_label: positive
                headline: test
        """)
        path = tmp_path / "bad_type.yaml"
        path.write_text(content)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rows = TrialEventBackfiller(events_path=path).load()
        assert len(rows) == 0
        assert len(w) >= 1

    def test_invalid_outcome_label_skipped_with_warning(self, tmp_path):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        content = textwrap.dedent("""\
            events:
              - asset_id: a-alny
                ticker: ALNY
                event_type: trial_readout
                announced_at: "2022-11-14"
                outcome_label: INVALID_LABEL
                headline: test
        """)
        path = tmp_path / "bad_label.yaml"
        path.write_text(content)
        with warnings.catch_warnings(record=True):
            rows = TrialEventBackfiller(events_path=path).load()
        assert len(rows) == 0

    def test_empty_events_list_returns_empty(self, tmp_path):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        path = tmp_path / "empty.yaml"
        path.write_text("meta:\n  description: test\nevents: []\n")
        rows = TrialEventBackfiller(events_path=path).load()
        assert rows == []

    def test_missing_events_key_returns_empty(self, tmp_path):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        path = tmp_path / "no_key.yaml"
        path.write_text("meta:\n  description: test\n")
        rows = TrialEventBackfiller(events_path=path).load()
        assert rows == []

    def test_invalid_date_skipped_with_warning(self, tmp_path):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        content = textwrap.dedent("""\
            events:
              - asset_id: a-alny
                ticker: ALNY
                event_type: trial_readout
                announced_at: "not-a-date"
                outcome_label: positive
                headline: test
        """)
        path = tmp_path / "bad_date.yaml"
        path.write_text(content)
        with warnings.catch_warnings(record=True):
            rows = TrialEventBackfiller(events_path=path).load()
        assert len(rows) == 0


# ---------------------------------------------------------------------------
# Deterministic event_id
# ---------------------------------------------------------------------------

class TestDeterministicID:
    def test_event_id_format(self, minimal_events_yaml, tmp_path):
        """Verifies deterministic id is trial:TICKER:DATE."""
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        db_path = str(tmp_path / "r.sqlite")
        backfiller = TrialEventBackfiller(
            events_path=minimal_events_yaml, replay_db_path=db_path
        )
        backfiller.backfill()

        from bve.ops.historical_replay import ReplayStore
        store = ReplayStore(db_path)
        rows = store._conn.execute(
            "SELECT event_id FROM historical_events ORDER BY announced_at"
        ).fetchall()
        store.close()
        ids = [r[0] for r in rows]
        assert "trial:ALNY:2022-11-14" in ids
        assert "trial:VKTX:2023-06-12" in ids

    def test_same_inputs_same_id(self, minimal_events_yaml, tmp_path):
        """Re-seeding same YAML twice produces the same event_ids (idempotent)."""
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        db_path = str(tmp_path / "r.sqlite")
        backfiller = TrialEventBackfiller(
            events_path=minimal_events_yaml, replay_db_path=db_path
        )
        backfiller.backfill()
        backfiller.backfill()

        from bve.ops.historical_replay import ReplayStore
        store = ReplayStore(db_path)
        count = store._conn.execute(
            "SELECT COUNT(*) FROM historical_events"
        ).fetchone()[0]
        store.close()
        assert count == 2   # no duplicates


# ---------------------------------------------------------------------------
# backfill() — dry_run
# ---------------------------------------------------------------------------

class TestBackfillDryRun:
    def test_dry_run_returns_correct_count(self, minimal_events_yaml, tmp_path):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        db_path = str(tmp_path / "r.sqlite")
        result = TrialEventBackfiller(
            events_path=minimal_events_yaml, replay_db_path=db_path
        ).backfill(dry_run=True)
        assert result.inserted == 2
        assert result.skipped == 0

    def test_dry_run_does_not_write(self, minimal_events_yaml, tmp_path):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        from bve.ops.historical_replay import ReplayStore
        db_path = str(tmp_path / "r.sqlite")
        TrialEventBackfiller(
            events_path=minimal_events_yaml, replay_db_path=db_path
        ).backfill(dry_run=True)
        store = ReplayStore(db_path)
        count = store._conn.execute(
            "SELECT COUNT(*) FROM historical_events"
        ).fetchone()[0]
        store.close()
        assert count == 0


# ---------------------------------------------------------------------------
# backfill() — live write + idempotency
# ---------------------------------------------------------------------------

class TestBackfillLive:
    def test_backfill_inserts_events(self, minimal_events_yaml, tmp_path):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        from bve.ops.historical_replay import ReplayStore
        db_path = str(tmp_path / "r.sqlite")
        result = TrialEventBackfiller(
            events_path=minimal_events_yaml, replay_db_path=db_path
        ).backfill()
        assert result.inserted == 2
        store = ReplayStore(db_path)
        count = store._conn.execute(
            "SELECT COUNT(*) FROM historical_events"
        ).fetchone()[0]
        store.close()
        assert count == 2

    def test_backfill_idempotent(self, minimal_events_yaml, tmp_path):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        from bve.ops.historical_replay import ReplayStore
        db_path = str(tmp_path / "r.sqlite")
        bf = TrialEventBackfiller(events_path=minimal_events_yaml, replay_db_path=db_path)
        bf.backfill()
        bf.backfill()
        store = ReplayStore(db_path)
        count = store._conn.execute(
            "SELECT COUNT(*) FROM historical_events"
        ).fetchone()[0]
        store.close()
        assert count == 2  # no duplicates

    def test_backfill_outcome_labels_correct(self, minimal_events_yaml, tmp_path):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        from bve.ops.historical_replay import ReplayStore
        db_path = str(tmp_path / "r.sqlite")
        TrialEventBackfiller(events_path=minimal_events_yaml, replay_db_path=db_path).backfill()
        store = ReplayStore(db_path)
        rows = store._conn.execute(
            "SELECT ticker, outcome_label FROM historical_events ORDER BY ticker"
        ).fetchall()
        store.close()
        by_ticker = {r[0]: r[1] for r in rows}
        assert by_ticker["ALNY"] == "positive"
        assert by_ticker["VKTX"] == "negative"

    def test_backfill_asset_ids_correct(self, minimal_events_yaml, tmp_path):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        from bve.ops.historical_replay import ReplayStore
        db_path = str(tmp_path / "r.sqlite")
        TrialEventBackfiller(events_path=minimal_events_yaml, replay_db_path=db_path).backfill()
        store = ReplayStore(db_path)
        rows = store._conn.execute(
            "SELECT asset_id FROM historical_events"
        ).fetchall()
        store.close()
        asset_ids = {r[0] for r in rows}
        assert "a-alny" in asset_ids
        assert "a-vktx" in asset_ids


# ---------------------------------------------------------------------------
# No-lookahead invariant (get_events_as_of)
# ---------------------------------------------------------------------------

class TestNoLookahead:
    def test_events_invisible_before_announced_at(self, minimal_events_yaml, tmp_path):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        from bve.ops.historical_replay import ReplayStore
        db_path = str(tmp_path / "r.sqlite")
        TrialEventBackfiller(events_path=minimal_events_yaml, replay_db_path=db_path).backfill()
        store = ReplayStore(db_path)
        # 2022-11-13 is one day before ALNY's event
        events = store.get_events_as_of("a-alny", date(2022, 11, 13))
        store.close()
        assert len(events) == 0

    def test_event_visible_on_announced_at(self, minimal_events_yaml, tmp_path):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        from bve.ops.historical_replay import ReplayStore
        db_path = str(tmp_path / "r.sqlite")
        TrialEventBackfiller(events_path=minimal_events_yaml, replay_db_path=db_path).backfill()
        store = ReplayStore(db_path)
        events = store.get_events_as_of("a-alny", date(2022, 11, 14))
        store.close()
        assert len(events) == 1

    def test_event_visible_after_announced_at(self, minimal_events_yaml, tmp_path):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        from bve.ops.historical_replay import ReplayStore
        db_path = str(tmp_path / "r.sqlite")
        TrialEventBackfiller(events_path=minimal_events_yaml, replay_db_path=db_path).backfill()
        store = ReplayStore(db_path)
        events = store.get_events_as_of("a-alny", date(2023, 1, 1))
        store.close()
        assert len(events) == 1

    def test_different_assets_isolated(self, minimal_events_yaml, tmp_path):
        """VKTX events should not appear when querying a-alny."""
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        from bve.ops.historical_replay import ReplayStore
        db_path = str(tmp_path / "r.sqlite")
        TrialEventBackfiller(events_path=minimal_events_yaml, replay_db_path=db_path).backfill()
        store = ReplayStore(db_path)
        events = store.get_events_as_of("a-alny", date(2023, 12, 31))
        store.close()
        assert all(e["ticker"] == "ALNY" for e in events)


# ---------------------------------------------------------------------------
# Default YAML (research/replay/events_2021_2023.yaml)
# ---------------------------------------------------------------------------

class TestDefaultYAML:
    def test_default_yaml_loads(self):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        rows = TrialEventBackfiller().load()
        assert len(rows) >= 30

    def test_default_yaml_has_both_positive_and_negative(self):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        rows = TrialEventBackfiller().load()
        labels = {r["outcome_label"] for r in rows}
        assert "positive" in labels
        assert "negative" in labels

    def test_default_yaml_all_dates_in_range(self):
        """All events should be between 2021-01-01 and 2023-12-31."""
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        rows = TrialEventBackfiller().load()
        for r in rows:
            d = date.fromisoformat(r["announced_at"])
            assert date(2021, 1, 1) <= d <= date(2023, 12, 31), (
                f"{r['ticker']} has out-of-range date {r['announced_at']}"
            )

    def test_default_yaml_covers_multiple_tickers(self):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        rows = TrialEventBackfiller().load()
        tickers = {r["ticker"] for r in rows}
        assert len(tickers) >= 10

    def test_default_yaml_asset_ids_follow_convention(self):
        from bve.ops.trial_event_backfiller import TrialEventBackfiller
        rows = TrialEventBackfiller().load()
        for r in rows:
            assert r["asset_id"].startswith("a-"), (
                f"Unexpected asset_id format: {r['asset_id']}"
            )
