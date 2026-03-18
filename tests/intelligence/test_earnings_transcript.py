"""Tests for Wave G — Earnings Transcript Ingestion."""
from __future__ import annotations

from datetime import date

import pytest

from bve.intelligence.earnings_transcript import (
    CatalystMention,
    EarningsTranscript,
    EarningsTranscriptParser,
    GuidanceItem,
    TonalSignal,
    _detect_guidance_direction,
    _detect_section,
    _detect_tone,
    _extract_revenue_amount,
)


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

def test_section_prepared_remarks():
    text = "Good morning, and thank you for joining us for our prepared remarks."
    assert _detect_section(text) == "prepared_remarks"


def test_section_qa():
    text = "We will now open the question-and-answer session."
    assert _detect_section(text) == "qa"


def test_section_qa_questions():
    text = "We now begin taking questions from analysts."
    assert _detect_section(text) == "qa"


def test_section_unknown():
    text = "Revenue was $500 million for the quarter."
    assert _detect_section(text) == "unknown"


# ---------------------------------------------------------------------------
# Guidance direction
# ---------------------------------------------------------------------------

def test_guidance_raised():
    assert _detect_guidance_direction("We raised our full-year guidance to $1.2B.") == "raised"


def test_guidance_lowered():
    assert _detect_guidance_direction("We are lowering guidance due to headwinds.") == "lowered"


def test_guidance_maintained():
    assert _detect_guidance_direction("We reaffirm our prior guidance range.") == "maintained"


def test_guidance_initiated():
    assert _detect_guidance_direction("We are providing initial guidance for the first time.") == "initiated"


def test_guidance_withdrawn():
    assert _detect_guidance_direction("We are withdrawing guidance due to uncertainty.") == "withdrawn"


def test_guidance_unknown():
    assert _detect_guidance_direction("Revenue was in line with expectations.") == "unknown"


# ---------------------------------------------------------------------------
# Revenue amount extraction
# ---------------------------------------------------------------------------

def test_revenue_millions():
    assert _extract_revenue_amount("revenue of $450 million") == pytest.approx(450.0)


def test_revenue_billions_converts():
    assert _extract_revenue_amount("guidance of $1.5 billion") == pytest.approx(1500.0)


def test_revenue_abbreviated_b():
    result = _extract_revenue_amount("$2.0B in net sales")
    assert result == pytest.approx(2000.0)


def test_revenue_abbreviated_m():
    result = _extract_revenue_amount("$350M for the year")
    assert result == pytest.approx(350.0)


def test_revenue_not_found():
    assert _extract_revenue_amount("No dollar amounts here") is None


def test_revenue_with_commas():
    result = _extract_revenue_amount("$1,200 million in revenue")
    assert result == pytest.approx(1200.0)


# ---------------------------------------------------------------------------
# Tone detection
# ---------------------------------------------------------------------------

def test_tone_confident():
    assert _detect_tone("We are confident this will be a transformative year.") == "confident"


def test_tone_cautious():
    assert _detect_tone("There is uncertainty in the regulatory pathway.") == "cautious"


def test_tone_neutral():
    # Pure factual with no directional language
    assert _detect_tone("The quarter ended March 31, 2025.") == "neutral"


# ---------------------------------------------------------------------------
# EarningsTranscriptParser — parse
# ---------------------------------------------------------------------------

SAMPLE_TRANSCRIPT = """
Good morning, and welcome to our prepared remarks for Q1 2025 earnings.

We are confident in our pipeline progress.
Our Phase 3 trial NCT01234567 is on track for a topline readout in H2 2025.
We raised our full-year revenue guidance to $1.2 billion.
There remains uncertainty in reimbursement coverage.
We expect Phase 2 results for our oncology program in Q3 2025.
"""


def test_parse_returns_transcript():
    parser = EarningsTranscriptParser()
    result = parser.parse(SAMPLE_TRANSCRIPT, company_id="co-1", ticker="XYZ", fiscal_period="Q1 2025")
    assert isinstance(result, EarningsTranscript)


def test_parse_passes_through_metadata():
    parser = EarningsTranscriptParser()
    result = parser.parse(
        SAMPLE_TRANSCRIPT,
        company_id="co-1",
        ticker="XYZ",
        fiscal_period="Q1 2025",
        call_date=date(2025, 4, 28),
    )
    assert result.company_id == "co-1"
    assert result.ticker == "XYZ"
    assert result.fiscal_period == "Q1 2025"
    assert result.call_date == date(2025, 4, 28)


def test_parse_detects_prepared_remarks_section():
    parser = EarningsTranscriptParser()
    result = parser.parse(SAMPLE_TRANSCRIPT)
    assert result.section == "prepared_remarks"


def test_parse_source_text_length():
    parser = EarningsTranscriptParser()
    result = parser.parse(SAMPLE_TRANSCRIPT)
    assert result.source_text_length == len(SAMPLE_TRANSCRIPT)


def test_parse_has_catalyst_mentions():
    parser = EarningsTranscriptParser()
    result = parser.parse(SAMPLE_TRANSCRIPT)
    assert len(result.catalyst_mentions) >= 1


def test_parse_catalyst_has_nct():
    parser = EarningsTranscriptParser()
    result = parser.parse(SAMPLE_TRANSCRIPT)
    nct_mentions = [m for m in result.catalyst_mentions if m.nct_id is not None]
    assert len(nct_mentions) >= 1
    assert nct_mentions[0].nct_id == "NCT01234567"


def test_parse_catalyst_has_phase():
    parser = EarningsTranscriptParser()
    result = parser.parse(SAMPLE_TRANSCRIPT)
    phase_mentions = [m for m in result.catalyst_mentions if m.trial_phase is not None]
    assert len(phase_mentions) >= 1


def test_parse_catalyst_has_readout_date():
    parser = EarningsTranscriptParser()
    result = parser.parse(SAMPLE_TRANSCRIPT)
    date_mentions = [m for m in result.catalyst_mentions if m.expected_readout is not None]
    assert len(date_mentions) >= 1


def test_parse_has_guidance_items():
    parser = EarningsTranscriptParser()
    result = parser.parse(SAMPLE_TRANSCRIPT)
    assert len(result.guidance_items) >= 1


def test_parse_guidance_direction_raised():
    parser = EarningsTranscriptParser()
    result = parser.parse(SAMPLE_TRANSCRIPT)
    raised = [g for g in result.guidance_items if g.direction == "raised"]
    assert len(raised) >= 1


def test_parse_guidance_revenue_type():
    parser = EarningsTranscriptParser()
    result = parser.parse(SAMPLE_TRANSCRIPT)
    revenue_guidance = [g for g in result.guidance_items if g.guidance_type == "revenue"]
    assert len(revenue_guidance) >= 1


def test_parse_guidance_amount():
    parser = EarningsTranscriptParser()
    result = parser.parse(SAMPLE_TRANSCRIPT)
    with_amount = [g for g in result.guidance_items if g.amount_millions is not None]
    assert len(with_amount) >= 1
    assert with_amount[0].amount_millions == pytest.approx(1200.0)


def test_parse_has_tonal_signals():
    parser = EarningsTranscriptParser()
    result = parser.parse(SAMPLE_TRANSCRIPT)
    assert len(result.tonal_signals) >= 1


def test_parse_tone_counts():
    parser = EarningsTranscriptParser()
    result = parser.parse(SAMPLE_TRANSCRIPT)
    # Transcript has confident + cautious statements
    assert result.n_confident >= 1
    assert result.n_cautious >= 1


def test_parse_overall_tone_set():
    parser = EarningsTranscriptParser()
    result = parser.parse(SAMPLE_TRANSCRIPT)
    assert result.overall_tone in ("confident", "cautious", "neutral")


def test_parse_unique_transcript_id():
    parser = EarningsTranscriptParser()
    r1 = parser.parse(SAMPLE_TRANSCRIPT)
    r2 = parser.parse(SAMPLE_TRANSCRIPT)
    assert r1.transcript_id != r2.transcript_id


def test_parse_empty_text():
    parser = EarningsTranscriptParser()
    result = parser.parse("")
    assert result.source_text_length == 0
    assert result.catalyst_mentions == []
    assert result.guidance_items == []
    assert result.overall_tone == "neutral"


# ---------------------------------------------------------------------------
# QA section detection
# ---------------------------------------------------------------------------

QA_TRANSCRIPT = """
We will now open the question-and-answer session.
Analyst: Can you discuss the Phase 3 readout timing for H1 2026?
Management: We are confident in the H1 2026 topline readout for NCT98765432.
"""


def test_parse_qa_section():
    parser = EarningsTranscriptParser()
    result = parser.parse(QA_TRANSCRIPT)
    assert result.section == "qa"


def test_parse_qa_catalyst_detected():
    parser = EarningsTranscriptParser()
    result = parser.parse(QA_TRANSCRIPT)
    assert any(m.nct_id == "NCT98765432" for m in result.catalyst_mentions)


# ---------------------------------------------------------------------------
# CatalystMention model
# ---------------------------------------------------------------------------

def test_catalyst_mention_frozen():
    cm = CatalystMention(drug_name="drug-X", nct_id="NCT12345678", mention_text="trial data")
    with pytest.raises(Exception):  # ValidationError on frozen model
        cm.drug_name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# GuidanceItem model
# ---------------------------------------------------------------------------

def test_guidance_item_fields():
    g = GuidanceItem(
        guidance_type="revenue",
        direction="raised",
        amount_millions=500.0,
        mention_text="We raised revenue guidance to $500M",
    )
    assert g.guidance_type == "revenue"
    assert g.direction == "raised"
    assert g.amount_millions == 500.0
