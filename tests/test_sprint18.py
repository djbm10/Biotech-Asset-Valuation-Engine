"""
Sprint 18 tests — Expert network integration layer.

Tests signal extraction, note persistence, ThesisClaim conversion,
and CLI argument parsing. No live DB calls in most tests.
"""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

from bve.intelligence.expert_notes import (
    ExpertNote,
    ExtractedSignal,
    _ensure_schema,
    extract_signals,
    get_expert_notes,
    note_to_claims,
    save_expert_note,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_note(
    ticker="VKTX",
    asset_id="vktx_vk2735",
    company_id="vktx",
    note_type="physician_call",
    content="12% weight loss at 24 weeks. Well tolerated. Prescribing more often.",
    confidence=0.70,
    noted_at=None,
):
    return ExpertNote(
        ticker=ticker,
        asset_id=asset_id,
        company_id=company_id,
        note_type=note_type,
        content=content,
        confidence=confidence,
        noted_at=noted_at or date(2026, 4, 15),
    )


@pytest.fixture()
def store():
    from bve.intelligence.knowledge_layer import KnowledgeStore
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        ks = KnowledgeStore(db_path)
        _ensure_schema(ks)
        yield ks
        ks.close()


# ===========================================================================
# TestExtractedSignal
# ===========================================================================

class TestExtractedSignal:
    def test_dataclass_fields(self):
        sig = ExtractedSignal(
            signal_type="efficacy",
            matched_text="12% weight loss",
            pattern=r"(\d+)%\s+(weight loss|...)",
        )
        assert sig.signal_type == "efficacy"
        assert sig.matched_text == "12% weight loss"

    def test_repr_contains_type(self):
        sig = ExtractedSignal("safety", "well tolerated", "pat")
        assert "safety" in repr(sig)


# ===========================================================================
# TestExtractSignals — efficacy
# ===========================================================================

class TestExtractSignalsEfficacy:
    def test_percent_weight_loss(self):
        sigs = extract_signals("Patients saw 12% weight loss at 24 weeks.")
        types = [s.signal_type for s in sigs]
        assert "efficacy" in types

    def test_percent_HbA1c(self):
        # Pattern requires: \d+% <keyword> — keyword must follow the percent
        sigs = extract_signals("Achieved 15% HbA1c reduction at week 24.")
        assert any(s.signal_type == "efficacy" for s in sigs)

    def test_statistically_significant(self):
        sigs = extract_signals("Statistically significant improvement in OS was observed.")
        assert any(s.signal_type == "efficacy" for s in sigs)

    def test_complete_response(self):
        sigs = extract_signals("40% complete response rate seen in cohort.")
        assert any(s.signal_type == "efficacy" for s in sigs)

    def test_no_efficacy_in_commercial_text(self):
        sigs = extract_signals("Formulary positioning improved. Payer coverage expanding.")
        efficacy = [s for s in sigs if s.signal_type == "efficacy"]
        assert len(efficacy) == 0


# ===========================================================================
# TestExtractSignalsSafety
# ===========================================================================

class TestExtractSignalsSafety:
    def test_well_tolerated(self):
        sigs = extract_signals("Drug was well tolerated with few side effects.")
        assert any(s.signal_type == "safety" for s in sigs)

    def test_adverse(self):
        sigs = extract_signals("Some adverse events reported.")
        assert any(s.signal_type == "safety" for s in sigs)

    def test_discontinuation(self):
        sigs = extract_signals("Low discontinuation rate observed.")
        assert any(s.signal_type == "safety" for s in sigs)

    def test_safety_profile_phrase(self):
        sigs = extract_signals("Safety profile was clean in all cohorts.")
        assert any(s.signal_type == "safety" for s in sigs)


# ===========================================================================
# TestExtractSignalsCommercial
# ===========================================================================

class TestExtractSignalsCommercial:
    def test_switching(self):
        sigs = extract_signals("Physicians are switching patients from semaglutide.")
        assert any(s.signal_type == "commercial" for s in sigs)

    def test_formulary(self):
        sigs = extract_signals("Won formulary position at major PBM.")
        assert any(s.signal_type == "commercial" for s in sigs)

    def test_prescribing(self):
        sigs = extract_signals("Prescribing behavior has changed significantly.")
        assert any(s.signal_type == "commercial" for s in sigs)

    def test_reimbursement(self):
        sigs = extract_signals("Reimbursement approved for obesity indication.")
        assert any(s.signal_type == "commercial" for s in sigs)


# ===========================================================================
# TestExtractSignalsMulti
# ===========================================================================

class TestExtractSignalsMulti:
    def test_mixed_content_extracts_all_three(self):
        content = (
            "20% weight loss at 24 weeks. "
            "Well tolerated with low discontinuation. "
            "Formulary access improving."
        )
        sigs = extract_signals(content)
        types = {s.signal_type for s in sigs}
        assert "efficacy" in types
        assert "safety" in types
        assert "commercial" in types

    def test_deduplication_same_match(self):
        # Same phrase repeated — should only appear once per signal_type
        content = "Well tolerated. Well tolerated."
        sigs = extract_signals(content)
        safety = [s for s in sigs if s.signal_type == "safety"]
        assert len(safety) == 1

    def test_empty_content_returns_empty(self):
        sigs = extract_signals("")
        assert sigs == []

    def test_unrelated_text_returns_empty(self):
        sigs = extract_signals("The company reported quarterly results today.")
        assert sigs == []


# ===========================================================================
# TestExpertNote
# ===========================================================================

class TestExpertNote:
    def test_note_id_generated(self):
        note = _make_note()
        assert len(note.note_id) == 36  # UUID4

    def test_two_notes_different_ids(self):
        n1 = _make_note()
        n2 = _make_note()
        assert n1.note_id != n2.note_id

    def test_optional_author_none(self):
        note = _make_note()
        assert note.author is None

    def test_custom_author(self):
        note = ExpertNote(
            ticker="ALNY",
            asset_id="alny_inclisiran",
            company_id="alny",
            note_type="conference",
            content="Strong efficacy data.",
            confidence=0.80,
            noted_at=date(2026, 3, 1),
            author="DJM",
        )
        assert note.author == "DJM"


# ===========================================================================
# TestSaveExpertNote
# ===========================================================================

class TestSaveExpertNote:
    def test_save_returns_note_id(self, store):
        note = _make_note()
        signals = extract_signals(note.content)
        note_id = save_expert_note(note, signals, store)
        assert note_id == note.note_id

    def test_save_and_retrieve(self, store):
        note = _make_note()
        signals = extract_signals(note.content)
        save_expert_note(note, signals, store)
        rows = get_expert_notes(store)
        assert len(rows) == 1
        assert rows[0]["ticker"] == "VKTX"

    def test_duplicate_note_id_ignored(self, store):
        note = _make_note()
        signals = extract_signals(note.content)
        save_expert_note(note, signals, store)
        save_expert_note(note, signals, store)  # same note_id → INSERT OR IGNORE
        rows = get_expert_notes(store)
        assert len(rows) == 1

    def test_multiple_notes_stored(self, store):
        n1 = _make_note(ticker="VKTX", content="12% weight loss.")
        n2 = _make_note(ticker="ALNY", asset_id="alny_incl", company_id="alny",
                        content="Prescribing increasing.")
        save_expert_note(n1, extract_signals(n1.content), store)
        save_expert_note(n2, extract_signals(n2.content), store)
        rows = get_expert_notes(store)
        assert len(rows) == 2

    def test_signals_json_persisted(self, store):
        note = _make_note(content="20% weight loss. Well tolerated.")
        signals = extract_signals(note.content)
        save_expert_note(note, signals, store)
        rows = get_expert_notes(store)
        import json
        sigs = json.loads(rows[0]["signals_json"])
        assert len(sigs) >= 1


# ===========================================================================
# TestGetExpertNotes
# ===========================================================================

class TestGetExpertNotes:
    def test_filter_by_ticker(self, store):
        n1 = _make_note(ticker="VKTX", content="12% weight loss.")
        n2 = _make_note(ticker="ALNY", asset_id="alny_incl", company_id="alny",
                        content="Prescribing increasing.")
        save_expert_note(n1, [], store)
        save_expert_note(n2, [], store)
        rows = get_expert_notes(store, ticker="VKTX")
        assert len(rows) == 1
        assert rows[0]["ticker"] == "VKTX"

    def test_filter_by_note_type(self, store):
        n1 = _make_note(note_type="physician_call")
        n2 = ExpertNote(
            ticker="VKTX", asset_id="vktx_vk2735", company_id="vktx",
            note_type="conference",
            content="Presented at ASCO.",
            confidence=0.60, noted_at=date(2026, 6, 1),
        )
        save_expert_note(n1, [], store)
        save_expert_note(n2, [], store)
        rows = get_expert_notes(store, note_type="conference")
        assert len(rows) == 1
        assert rows[0]["note_type"] == "conference"

    def test_empty_returns_empty(self, store):
        rows = get_expert_notes(store)
        assert rows == []

    def test_case_insensitive_ticker(self, store):
        note = _make_note(ticker="VKTX")
        save_expert_note(note, [], store)
        rows = get_expert_notes(store, ticker="vktx")  # lowercase
        # tickers stored uppercase; filter is uppercase too
        assert len(rows) == 1


# ===========================================================================
# TestNoteToClaims
# ===========================================================================

class TestNoteToClaims:
    def test_efficacy_creates_endpoint_met_claim(self, store):
        from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
        tracker = ThesisTracker(store)
        note = _make_note(content="20% weight loss at 24 weeks.")
        signals = extract_signals(note.content)
        claims = note_to_claims(note, signals, tracker)
        assert any(c.claim_type == ClaimType.ENDPOINT_MET for c in claims)

    def test_safety_creates_custom_claim(self, store):
        from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
        tracker = ThesisTracker(store)
        note = _make_note(content="Well tolerated profile.")
        signals = extract_signals(note.content)
        claims = note_to_claims(note, signals, tracker)
        custom = [c for c in claims if c.claim_type == ClaimType.CUSTOM]
        assert any(c.categorical_value == "safety_signal" for c in custom)

    def test_commercial_creates_custom_claim(self, store):
        from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
        tracker = ThesisTracker(store)
        note = _make_note(content="Formulary access improving.")
        signals = extract_signals(note.content)
        claims = note_to_claims(note, signals, tracker)
        custom = [c for c in claims if c.claim_type == ClaimType.CUSTOM]
        assert any(c.categorical_value == "commercial_signal" for c in custom)

    def test_no_signals_returns_empty(self, store):
        from bve.intelligence.thesis_tracker import ThesisTracker
        tracker = ThesisTracker(store)
        note = _make_note(content="Nothing relevant here.")
        signals = extract_signals(note.content)
        claims = note_to_claims(note, signals, tracker)
        assert claims == []

    def test_mixed_content_creates_multiple_claims(self, store):
        from bve.intelligence.thesis_tracker import ThesisTracker
        tracker = ThesisTracker(store)
        content = "20% weight loss. Well tolerated. Formulary won."
        note = _make_note(content=content)
        signals = extract_signals(note.content)
        claims = note_to_claims(note, signals, tracker)
        assert len(claims) == 3

    def test_claim_assertion_contains_note_type(self, store):
        from bve.intelligence.thesis_tracker import ThesisTracker
        tracker = ThesisTracker(store)
        note = _make_note(note_type="kol_interview", content="20% weight loss.")
        signals = extract_signals(note.content)
        claims = note_to_claims(note, signals, tracker)
        assert any("kol_interview" in c.assertion for c in claims)

    def test_claim_source_signal_id_is_note_id(self, store):
        from bve.intelligence.thesis_tracker import ThesisTracker
        tracker = ThesisTracker(store)
        note = _make_note(content="20% weight loss.")
        signals = extract_signals(note.content)
        claims = note_to_claims(note, signals, tracker)
        assert all(c.created_by_signal_id == note.note_id for c in claims)


# ===========================================================================
# TestCLIParsing
# ===========================================================================

class TestCLIParsing:
    def test_dry_run_no_db_write(self, capsys):
        from bve.cli.note_entry import main
        main([
            "--ticker", "VKTX",
            "--type", "physician_call",
            "--date", "2026-04-15",
            "--content", "20% weight loss. Well tolerated.",
            "--confidence", "0.70",
            "--dry-run",
        ])
        captured = capsys.readouterr()
        assert "dry-run" in captured.out.lower()
        assert "efficacy" in captured.out.lower()

    def test_invalid_confidence_exits(self):
        from bve.cli.note_entry import main
        with pytest.raises(SystemExit):
            main([
                "--ticker", "VKTX",
                "--type", "physician_call",
                "--date", "2026-04-15",
                "--content", "x",
                "--confidence", "1.5",
            ])

    def test_invalid_date_exits(self):
        from bve.cli.note_entry import main
        with pytest.raises(SystemExit):
            main([
                "--ticker", "VKTX",
                "--type", "physician_call",
                "--date", "not-a-date",
                "--content", "x",
                "--confidence", "0.5",
            ])

    def test_invalid_type_exits(self):
        from bve.cli.note_entry import main
        with pytest.raises(SystemExit):
            main([
                "--ticker", "VKTX",
                "--type", "unknown_type",
                "--date", "2026-04-15",
                "--content", "x",
                "--confidence", "0.5",
            ])
