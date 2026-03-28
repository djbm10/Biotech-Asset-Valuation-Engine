"""
Sprint 15 tests — Real-time event monitoring.

All tests mock network calls. No live FDA or EDGAR requests.
"""
from __future__ import annotations

import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bve.ops.event_monitor import (
    DetectedEvent,
    _classify_8k,
    _match_ticker,
    poll_edgar_8k,
    poll_fda_events,
)
from bve.ops.recompute_trigger import check_and_trigger, pending_trigger_count

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    ticker="VKTX",
    event_type="fda_approval",
    headline="VKTX: FDA AP — NDA 12345",
    requires_recompute=True,
    dt=None,
) -> DetectedEvent:
    return DetectedEvent(
        ticker=ticker,
        asset_id=ticker,
        event_type=event_type,
        headline=headline,
        source_url="https://example.com",
        detected_at=dt or datetime.now(tz=timezone.utc),
        requires_recompute=requires_recompute,
    )


# ===========================================================================
# TestDetectedEvent
# ===========================================================================

class TestDetectedEvent:
    def test_basic_construction(self):
        ev = _make_event()
        assert ev.ticker == "VKTX"
        assert ev.event_type == "fda_approval"
        assert ev.requires_recompute is True

    def test_extra_defaults_to_empty_dict(self):
        ev = _make_event()
        assert isinstance(ev.extra, dict)

    def test_extra_can_be_set(self):
        ev = DetectedEvent(
            ticker="X", asset_id="X", event_type="fda_crl",
            headline="X: CRL", source_url="", detected_at=datetime.now(tz=timezone.utc),
            requires_recompute=True, extra={"app": "NDA123"},
        )
        assert ev.extra["app"] == "NDA123"


# ===========================================================================
# TestClassify8k
# ===========================================================================

class TestClassify8k:
    def test_clinical_keyword_detected(self):
        assert _classify_8k("VKTX 8-K: Phase 3 primary endpoint met") == "8k_clinical"

    def test_partnership_detected(self):
        assert _classify_8k("ALNY 8-K: License collaboration agreement") == "8k_partnership"

    def test_general_filing(self):
        assert _classify_8k("VKTX 8-K: Corporate governance update") == "8k_general"

    def test_fda_keyword_is_clinical(self):
        assert _classify_8k("Company 8-K: FDA approval granted") == "8k_clinical"

    def test_phase_ii_roman_is_clinical(self):
        assert _classify_8k("Phase ii results announced") == "8k_clinical"


# ===========================================================================
# TestMatchTicker
# ===========================================================================

class TestMatchTicker:
    def test_exact_ticker_in_name(self):
        assert _match_ticker("VKTX PHARMACEUTICALS", ["VKTX", "ALNY"]) == "VKTX"

    def test_no_match_returns_none(self):
        assert _match_ticker("RANDOM CORP", ["VKTX", "ALNY"]) is None

    def test_case_insensitive_sponsor(self):
        assert _match_ticker("vktx biopharma", ["VKTX"]) == "VKTX"


# ===========================================================================
# TestPollFdaEvents — mocked
# ===========================================================================

class TestPollFdaEvents:
    def test_returns_empty_on_network_error(self):
        with patch("requests.get", side_effect=Exception("network error")):
            result = poll_fda_events(["VKTX"])
        assert result == []

    def test_returns_empty_when_no_match(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "sponsor_name": "UNRELATED CORP",
                    "application_number": "NDA099",
                    "submissions": [{"submission_status": "AP", "submission_status_date": "20260101"}],
                }
            ]
        }
        with patch("requests.get", return_value=mock_resp):
            result = poll_fda_events(["VKTX"])
        assert result == []

    def test_returns_event_when_ticker_matched(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "sponsor_name": "VKTX BIOPHARMA",
                    "application_number": "NDA123456",
                    "submissions": [
                        {
                            "submission_status": "AP",
                            "submission_status_date": "20260101",
                            "submission_type": "ORIG",
                            "submission_number": "1",
                        }
                    ],
                }
            ]
        }
        with patch("requests.get", return_value=mock_resp):
            result = poll_fda_events(["VKTX"], lookback_days=365)
        assert len(result) >= 1
        assert result[0].ticker == "VKTX"
        assert result[0].event_type == "fda_approval"
        assert result[0].requires_recompute is True

    def test_crl_detected(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "sponsor_name": "VKTX PHARMA",
                    "application_number": "NDA999",
                    "submissions": [
                        {
                            "submission_status": "CR",
                            "submission_status_date": "20260201",
                            "submission_type": "ORIG",
                            "submission_number": "1",
                        }
                    ],
                }
            ]
        }
        with patch("requests.get", return_value=mock_resp):
            result = poll_fda_events(["VKTX"], lookback_days=365)
        assert any(e.event_type == "fda_crl" for e in result)

    def test_non_200_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("requests.get", return_value=mock_resp):
            result = poll_fda_events(["VKTX"])
        assert result == []


# ===========================================================================
# TestPollEdgar8k — mocked
# ===========================================================================

class TestPollEdgar8k:
    def test_returns_empty_on_network_error(self):
        with patch("requests.get", side_effect=Exception("network error")):
            result = poll_edgar_8k(["VKTX"])
        assert result == []

    def test_returns_event_for_8k_filing(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "hits": {
                "hits": [
                    {
                        "_id": "0001234567-26-000001",
                        "_source": {
                            "entity_name": "Viking Therapeutics Inc",
                            "file_date": "2026-03-20",
                            "period_of_report": "2026-03-19",
                        },
                    }
                ]
            }
        }
        with patch("requests.get", return_value=mock_resp):
            result = poll_edgar_8k(["VKTX"])
        assert len(result) >= 1
        assert result[0].ticker == "VKTX"

    def test_empty_hits_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"hits": {"hits": []}}
        with patch("requests.get", return_value=mock_resp):
            result = poll_edgar_8k(["VKTX"])
        assert result == []


# ===========================================================================
# TestKnowledgeStoreDetectedEvents — persistence
# ===========================================================================

class TestKnowledgeStoreDetectedEvents:
    @pytest.fixture()
    def store(self):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            ks = KnowledgeStore(db_path)
            yield ks
            ks.close()

    def test_insert_and_retrieve(self, store):
        ev = _make_event()
        n = store.insert_detected_events([ev])
        assert n == 1
        rows = store.get_detected_events()
        assert len(rows) == 1
        assert rows[0]["ticker"] == "VKTX"

    def test_deduplication_same_event(self, store):
        ev = _make_event()
        store.insert_detected_events([ev])
        store.insert_detected_events([ev])  # second insert: duplicate
        rows = store.get_detected_events()
        assert len(rows) == 1  # deduplicated

    def test_filter_by_ticker(self, store):
        store.insert_detected_events([_make_event(ticker="VKTX")])
        store.insert_detected_events([_make_event(ticker="ALNY", headline="ALNY: approval")])
        rows = store.get_detected_events(ticker="VKTX")
        assert all(r["ticker"] == "VKTX" for r in rows)

    def test_filter_requires_recompute(self, store):
        store.insert_detected_events([
            _make_event(requires_recompute=True),
            _make_event(ticker="ALNY", headline="ALNY general", event_type="8k_general", requires_recompute=False),
        ])
        rows = store.get_detected_events(requires_recompute=True)
        assert all(r["requires_recompute"] == 1 for r in rows)

    def test_empty_db_returns_empty(self, store):
        rows = store.get_detected_events()
        assert rows == []

    def test_requires_recompute_stored_as_int(self, store):
        ev = _make_event(requires_recompute=True)
        store.insert_detected_events([ev])
        rows = store.get_detected_events()
        assert rows[0]["requires_recompute"] in (1, True)


# ===========================================================================
# TestRecomputeTrigger
# ===========================================================================

class TestRecomputeTrigger:
    @pytest.fixture()
    def store(self):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            ks = KnowledgeStore(db_path)
            yield ks
            ks.close()

    def test_empty_store_returns_empty(self, store):
        result = check_and_trigger(store, as_of=date.today())
        assert result == []

    def test_returns_ticker_with_recompute_event(self, store):
        ev = _make_event(ticker="VKTX", requires_recompute=True)
        store.insert_detected_events([ev])
        result = check_and_trigger(store, as_of=date.today(), lookback_days=30)
        assert "VKTX" in result

    def test_no_recompute_events_excluded(self, store):
        ev = _make_event(ticker="VKTX", requires_recompute=False, event_type="8k_general")
        store.insert_detected_events([ev])
        result = check_and_trigger(store, as_of=date.today(), lookback_days=30)
        assert result == []

    def test_multiple_tickers_sorted(self, store):
        store.insert_detected_events([
            _make_event(ticker="ALNY", headline="ALNY approval", requires_recompute=True),
            _make_event(ticker="VKTX", requires_recompute=True),
        ])
        result = check_and_trigger(store, as_of=date.today(), lookback_days=30)
        assert result == sorted(result)

    def test_pending_count_matches(self, store):
        store.insert_detected_events([_make_event()])
        count = pending_trigger_count(store, as_of=date.today(), lookback_days=30)
        assert count == 1
