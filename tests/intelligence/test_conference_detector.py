"""Tests for Wave F — Conference Event Detection."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pytest

from bve.intelligence.conference_detector import (
    ConferenceCalendar,
    ConferenceEntry,
    ConferenceEventDetector,
    ConferencePresentation,
    _detect_presentation_type,
    _extract_abstract_number,
)


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

@dataclass
class _Signal:
    id: str = "sig-1"
    event_id: str = "evt-1"
    asset_id: str = "asset-1"
    company_id: str = "co-1"
    event_type: str = "conference_abstract"
    headline: str = ""
    raw_text: str = ""
    source_url: str = ""


@dataclass
class _Event:
    id: str = "evt-1"
    headline: str = ""
    raw_text: str = ""
    source_url: str = ""
    source_type: str = "conference_abstract"


# ---------------------------------------------------------------------------
# ConferenceCalendar
# ---------------------------------------------------------------------------

def test_calendar_lookup_asco():
    cal = ConferenceCalendar()
    entry = cal.lookup("Presented at ASCO 2025 in Chicago")
    assert entry is not None
    assert entry.key == "asco"


def test_calendar_lookup_ash():
    cal = ConferenceCalendar()
    entry = cal.lookup("ASH Annual Meeting poster presentation")
    assert entry is not None
    assert entry.key == "ash"


def test_calendar_lookup_case_insensitive():
    cal = ConferenceCalendar()
    entry = cal.lookup("results presented at esmo 2024")
    assert entry is not None
    assert entry.key == "esmo"


def test_calendar_lookup_full_name():
    cal = ConferenceCalendar()
    entry = cal.lookup("European Society for Medical Oncology presentation")
    assert entry is not None
    assert entry.key == "esmo"


def test_calendar_lookup_no_match():
    cal = ConferenceCalendar()
    entry = cal.lookup("press release about Q3 earnings")
    assert entry is None


def test_calendar_lookup_by_key():
    cal = ConferenceCalendar()
    entry = cal.lookup_by_key("ada")
    assert entry is not None
    assert "ADA" in entry.display_name or "Diabetes" in entry.display_name or entry.therapeutic_area == "diabetes"


def test_calendar_lookup_by_key_missing():
    cal = ConferenceCalendar()
    assert cal.lookup_by_key("nonexistent") is None


def test_calendar_all_entries():
    cal = ConferenceCalendar()
    entries = cal.all_entries
    assert len(entries) >= 10
    keys = {e.key for e in entries}
    assert "asco" in keys
    assert "ash" in keys
    assert "esmo" in keys


def test_calendar_custom_entry():
    custom = [
        ConferenceEntry(
            key="mypharma_conf",
            display_name="My Pharma Conference",
            aliases=["mypharma", "mpc"],
            typical_month_range=(3, 3),
        )
    ]
    cal = ConferenceCalendar(entries=custom)
    entry = cal.lookup("data presented at mypharma 2025")
    assert entry is not None
    assert entry.key == "mypharma_conf"


# ---------------------------------------------------------------------------
# Presentation type detection
# ---------------------------------------------------------------------------

def test_detect_oral():
    assert _detect_presentation_type("Oral presentation at ASCO") == "oral"


def test_detect_poster():
    assert _detect_presentation_type("Poster #4521 at ESMO") == "poster"


def test_detect_late_breaking():
    assert _detect_presentation_type("Late-breaking abstract LBA45") == "late_breaking"


def test_detect_late_breaking_lba():
    assert _detect_presentation_type("LBA23 presented at ASH") == "late_breaking"


def test_detect_symposium():
    assert _detect_presentation_type("Invited symposium at AHA 2024") == "symposium"


def test_detect_unknown():
    assert _detect_presentation_type("Results discussed at medical meeting") == "unknown"


def test_late_breaking_takes_precedence_over_oral():
    # Late-breaking should win even if "oral" is also present
    result = _detect_presentation_type("Late-breaking oral abstract")
    assert result == "late_breaking"


# ---------------------------------------------------------------------------
# Abstract number extraction
# ---------------------------------------------------------------------------

def test_extract_abstract_number_hash():
    assert _extract_abstract_number("Abstract #1234") == "1234"


def test_extract_abstract_number_lba():
    assert _extract_abstract_number("LBA45 presented at ASCO") == "45"


def test_extract_abstract_number_word():
    assert _extract_abstract_number("Abstract 567 presented at ASH") == "567"


def test_extract_abstract_number_none():
    assert _extract_abstract_number("No abstract number here") is None


# ---------------------------------------------------------------------------
# ConferenceEventDetector — detect_from_signal
# ---------------------------------------------------------------------------

def test_detect_from_signal_returns_list():
    detector = ConferenceEventDetector()
    signal = _Signal(event_type="conference_abstract")
    event = _Event(headline="ASCO 2025: Oral presentation of Phase 3 trial results")
    result = detector.detect_from_signal(signal, event=event)
    assert isinstance(result, list)


def test_detect_from_signal_asco_oral():
    detector = ConferenceEventDetector()
    signal = _Signal()
    event = _Event(headline="ASCO 2025: Oral Abstract #1234 — Phase 3 trial results")
    result = detector.detect_from_signal(signal, event=event)
    assert len(result) == 1
    p = result[0]
    assert p.conference_key == "asco"
    assert p.presentation_type == "oral"
    assert p.abstract_number == "1234"


def test_detect_from_signal_links_ids():
    detector = ConferenceEventDetector()
    signal = _Signal(id="sig-abc", event_id="evt-xyz", asset_id="asset-2", company_id="co-2")
    event = _Event(headline="ESMO 2024: Late-Breaking Abstract LBA12")
    result = detector.detect_from_signal(signal, event=event)
    assert len(result) == 1
    p = result[0]
    assert p.signal_id == "sig-abc"
    assert p.event_id == "evt-xyz"
    assert p.asset_id == "asset-2"
    assert p.company_id == "co-2"


def test_detect_from_signal_late_breaking():
    detector = ConferenceEventDetector()
    signal = _Signal()
    event = _Event(headline="ASH 2024: Late-Breaking Abstract on BTK inhibitor data")
    result = detector.detect_from_signal(signal, event=event)
    assert len(result) == 1
    assert result[0].conference_key == "ash"
    assert result[0].presentation_type == "late_breaking"


def test_detect_from_signal_no_conference_text_returns_empty():
    detector = ConferenceEventDetector()
    # Non-conference event type + no conference mention
    signal = _Signal(event_type="press_release")
    event = _Event(headline="Q3 2025 Earnings Beat Expectations", source_type="press_release")
    result = detector.detect_from_signal(signal, event=event)
    assert result == []


def test_detect_from_signal_conference_source_type_no_match():
    """conference_abstract source_type with no conference name → unknown key."""
    detector = ConferenceEventDetector()
    signal = _Signal(event_type="conference_abstract")
    event = _Event(
        headline="Oral presentation of Phase 2 data",
        source_type="conference_abstract",
    )
    result = detector.detect_from_signal(signal, event=event)
    # conference_abstract event_type → is_conference_source=True, but no name match
    assert len(result) == 1
    assert result[0].conference_key == "unknown"


def test_detect_from_signal_without_event():
    """Can detect from signal alone when event is not provided."""
    detector = ConferenceEventDetector()
    signal = _Signal(
        event_type="conference_abstract",
        headline="ASCO 2025 Poster: Phase 2 results",
    )
    result = detector.detect_from_signal(signal)
    assert len(result) == 1
    assert result[0].conference_key == "asco"
    assert result[0].presentation_type == "poster"


def test_detect_from_signal_headline_populated():
    detector = ConferenceEventDetector()
    signal = _Signal()
    event = _Event(headline="ASCO 2025: Oral Abstract — new data for oncology drug")
    result = detector.detect_from_signal(signal, event=event)
    assert len(result) == 1
    assert "ASCO" in result[0].headline


def test_detect_from_signal_source_url_provides_conference():
    detector = ConferenceEventDetector()
    signal = _Signal(event_type="data_presentation")
    event = _Event(
        headline="Phase 3 data results",
        source_url="https://meeting.asco.org/abstract/12345",
    )
    result = detector.detect_from_signal(signal, event=event)
    assert len(result) == 1
    assert result[0].conference_key == "asco"


# ---------------------------------------------------------------------------
# ConferenceEventDetector — detect_from_text
# ---------------------------------------------------------------------------

def test_detect_from_text_basic():
    detector = ConferenceEventDetector()
    result = detector.detect_from_text(
        "Poster presentation at ESMO 2024 Congress",
        asset_id="a-1",
        company_id="co-1",
    )
    assert len(result) == 1
    assert result[0].conference_key == "esmo"
    assert result[0].presentation_type == "poster"


def test_detect_from_text_no_match_returns_empty():
    detector = ConferenceEventDetector()
    result = detector.detect_from_text(
        "Quarterly earnings beat analyst estimates",
        asset_id="a-1",
        company_id="co-1",
    )
    assert result == []


def test_detect_from_text_empty_returns_empty():
    detector = ConferenceEventDetector()
    result = detector.detect_from_text("", asset_id="a-1", company_id="co-1")
    assert result == []


def test_detect_from_text_populates_ids():
    detector = ConferenceEventDetector()
    result = detector.detect_from_text(
        "ASH 2024: LBA23",
        asset_id="asset-99",
        company_id="co-99",
        signal_id="s-1",
        event_id="e-1",
    )
    assert len(result) == 1
    p = result[0]
    assert p.asset_id == "asset-99"
    assert p.signal_id == "s-1"
    assert p.event_id == "e-1"


def test_detect_from_text_presentation_date():
    detector = ConferenceEventDetector()
    pdate = date(2025, 6, 2)
    result = detector.detect_from_text(
        "ASCO abstract",
        asset_id="a",
        company_id="c",
        presentation_date=pdate,
    )
    assert result[0].presentation_date == pdate


# ---------------------------------------------------------------------------
# ConferencePresentation model
# ---------------------------------------------------------------------------

def test_presentation_has_unique_id():
    p1 = ConferencePresentation(asset_id="a", company_id="c")
    p2 = ConferencePresentation(asset_id="a", company_id="c")
    assert p1.presentation_id != p2.presentation_id


def test_presentation_defaults():
    p = ConferencePresentation(asset_id="a", company_id="c")
    assert p.conference_key == "unknown"
    assert p.presentation_type == "unknown"
    assert p.abstract_number is None
