"""
Wave G — Earnings Transcript Ingestion.

Provides structured parsing of biotech earnings call transcripts.  The parser
is pattern-based (no LLM calls) and extracts:

- Transcript sections (prepared remarks vs Q&A).
- Revenue guidance language (raised / lowered / maintained / initiated).
- Pipeline catalyst mentions (drug names, NCT IDs, trial phases, readout dates).
- Management tone signals (confidence phrases vs cautious hedges).
- R&D spend guidance mentions.

Design principles
-----------------
- Stateless: ``EarningsTranscriptParser.parse(text)`` has no side effects.
- Pattern-based only: heuristic regexes, no external API or LLM calls.
- Source-traced: every ``EarningsTranscript`` records ``company_id``,
  ``ticker``, and ``fiscal_period``.
- Structured output: ``CatalystMention``, ``GuidanceItem``, and
  ``TonalSignal`` are typed Pydantic models, not free text.

Section taxonomy
----------------
``prepared_remarks``   — management-prepared opening statements
``qa``                 — analyst Q&A portion
``operator``           — operator introductions / call logistics
``unknown``            — section not determinable

Guidance direction taxonomy
----------------------------
``raised``             — guidance increased from prior
``lowered``            — guidance decreased from prior
``maintained``         — guidance reaffirmed / unchanged
``initiated``          — first-time guidance issuance
``withdrawn``          — guidance withdrawn
``unknown``            — direction not determinable

Tone taxonomy
-------------
``confident``          — strong positive forward-looking language
``cautious``           — hedged / uncertain language
``neutral``            — factual statements without directional tone
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Section boundaries
# ---------------------------------------------------------------------------

_PREPARED_REMARKS_PATTERNS = [
    re.compile(r"\bprepared remarks?\b", re.IGNORECASE),
    re.compile(r"\bopening (remarks?|statement)\b", re.IGNORECASE),
    re.compile(r"\boperator\b.*?please go ahead", re.IGNORECASE | re.DOTALL),
]
_QA_PATTERNS = [
    re.compile(r"\b(question.and.answer|q\s*&\s*a|q&a) session\b", re.IGNORECASE),
    re.compile(r"\boperator\b.*?\bquestion\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bwe (will )?now (open|begin|take) .*?question", re.IGNORECASE),
]


def _detect_section(text: str) -> str:
    """Return 'prepared_remarks', 'qa', or 'unknown'."""
    for pat in _QA_PATTERNS:
        if pat.search(text):
            return "qa"
    for pat in _PREPARED_REMARKS_PATTERNS:
        if pat.search(text):
            return "prepared_remarks"
    return "unknown"


# ---------------------------------------------------------------------------
# Guidance direction detection
# ---------------------------------------------------------------------------

_GUIDANCE_RAISED_RE = re.compile(
    r"\b(raise[sd]?|increas(e|ed|ing)|upward(ly)?|lift(ed)?|"
    r"above.*prior|above.*guidance|higher.than.*prior|"
    r"upside(d)?|upgr(?:ade|aded))\b",
    re.IGNORECASE,
)
_GUIDANCE_LOWERED_RE = re.compile(
    r"\b(lower(ed|ing)?|decreas(e|ed|ing)|reduc(e|ed|ing)|downward(ly)?|"
    r"cut.*guidance|below.*prior)\b",
    re.IGNORECASE,
)
_GUIDANCE_MAINTAINED_RE = re.compile(
    r"\b(reaffirm(ed|ing)?|maintain(ed|ing)?|reiterat(e|ed|ing)?|"
    r"unchanged|in.line.with.*prior|consistent.with)\b",
    re.IGNORECASE,
)
_GUIDANCE_INITIATED_RE = re.compile(
    r"\b(initiat(e|ed|ing)?.*guidance|first.time.*guidance|"
    r"provid(e|ed|ing).*initial.*guidance)\b",
    re.IGNORECASE,
)
_GUIDANCE_WITHDRAWN_RE = re.compile(
    r"\b(withdraw(n|ing)?.*guidance|suspend.*guidance|"
    r"no longer.*guidance|pull(ed|ing)?.*guidance)\b",
    re.IGNORECASE,
)

_GUIDANCE_KEYWORD_RE = re.compile(
    r"\b(guidance|outlook|forecast|expect(ation)?s?|full.year|fy\s*\d{4}|"
    r"revenue range|revenue target)\b",
    re.IGNORECASE,
)

_REVENUE_AMOUNT_RE = re.compile(
    r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(billion|million|B|M)\b",
    re.IGNORECASE,
)


def _detect_guidance_direction(text: str) -> str:
    if _GUIDANCE_INITIATED_RE.search(text):
        return "initiated"
    if _GUIDANCE_WITHDRAWN_RE.search(text):
        return "withdrawn"
    if _GUIDANCE_RAISED_RE.search(text):
        return "raised"
    if _GUIDANCE_LOWERED_RE.search(text):
        return "lowered"
    if _GUIDANCE_MAINTAINED_RE.search(text):
        return "maintained"
    return "unknown"


def _extract_revenue_amount(text: str) -> Optional[float]:
    """
    Extract the first dollar figure and normalise to millions.

    Returns ``None`` if no dollar amount found.
    """
    m = _REVENUE_AMOUNT_RE.search(text)
    if not m:
        return None
    raw = float(m.group(1).replace(",", ""))
    unit = m.group(2).lower()
    if unit in ("billion", "b"):
        return raw * 1_000
    return raw


# ---------------------------------------------------------------------------
# Catalyst mention detection
# ---------------------------------------------------------------------------

_NCT_RE = re.compile(r"\bNCT\d{8}\b", re.IGNORECASE)
_PHASE_RE = re.compile(
    r"\b(phase\s*[123](?:[ab])?|phase\s*2/3|pivotal|registration)\b",
    re.IGNORECASE,
)
_READOUT_DATE_RE = re.compile(
    r"\b((?:H[12]|[Qq][1-4])\s*\d{4}|mid.year\s*\d{4}|"
    r"(?:first|second|third|fourth) half\s*\d{4})\b",
    re.IGNORECASE,
)
_TOPLINE_RE = re.compile(
    r"\b(topline|top.line|primary endpoint|data read(?:out)?|results)\b",
    re.IGNORECASE,
)


class CatalystMention(BaseModel):
    """A single pipeline catalyst reference extracted from transcript text."""

    model_config = {"frozen": True}

    drug_name: Optional[str] = None
    nct_id: Optional[str] = None
    trial_phase: Optional[str] = None
    expected_readout: Optional[str] = None
    mention_text: str = ""           # raw sentence containing the mention


# ---------------------------------------------------------------------------
# Guidance item
# ---------------------------------------------------------------------------

class GuidanceItem(BaseModel):
    """One revenue/pipeline guidance statement."""

    model_config = {"frozen": True}

    guidance_type: str                  # "revenue" | "pipeline" | "rd_spend" | "other"
    direction: str = "unknown"          # raised / lowered / maintained / initiated / withdrawn
    amount_millions: Optional[float] = None
    mention_text: str = ""


# ---------------------------------------------------------------------------
# Tonal signal
# ---------------------------------------------------------------------------

_CONFIDENT_PATTERNS = [
    re.compile(r"\b(confident(ly)?|strong(ly)?|excel(lent|ling)?|"
               r"best.in.class|transformative|compelling|conviction|"
               r"on.track|ahead.of.schedule)\b", re.IGNORECASE),
]
_CAUTIOUS_PATTERNS = [
    re.compile(r"\b(uncertain(ty)?|risk(s|y)?|challeng(e|ing|es)|"
               r"cautious(ly)?|headwind|difficult(y|ies)?|"
               r"may|might|could|subject.to|contingent|pending)\b", re.IGNORECASE),
]


class TonalSignal(BaseModel):
    """Detected tone in a sentence or paragraph."""

    model_config = {"frozen": True}

    tone: str            # "confident" | "cautious" | "neutral"
    mention_text: str = ""


def _detect_tone(text: str) -> str:
    confident_count = sum(
        1 for p in _CONFIDENT_PATTERNS if p.search(text)
    )
    cautious_count = sum(
        1 for p in _CAUTIOUS_PATTERNS if p.search(text)
    )
    if confident_count > cautious_count:
        return "confident"
    if cautious_count > confident_count:
        return "cautious"
    return "neutral"


# ---------------------------------------------------------------------------
# EarningsTranscript — output model
# ---------------------------------------------------------------------------

class EarningsTranscript(BaseModel):
    """
    Structured representation of a parsed earnings call transcript.

    Attributes
    ----------
    transcript_id:
        UUID for this parsed record.
    company_id:
        Company identifier.
    ticker:
        Equity ticker symbol.
    fiscal_period:
        E.g. ``"Q1 2025"`` or ``"FY 2024"``.
    call_date:
        Date of the earnings call.
    section:
        Dominant transcript section detected (``"prepared_remarks"`` /
        ``"qa"`` / ``"unknown"``).
    catalyst_mentions:
        Pipeline catalyst references extracted from the text.
    guidance_items:
        Revenue and pipeline guidance statements.
    tonal_signals:
        Detected tone across the transcript.
    n_confident:
        Count of confident-tone sentences.
    n_cautious:
        Count of cautious-tone sentences.
    overall_tone:
        ``"confident"`` if n_confident > n_cautious, else ``"cautious"``
        if n_cautious > n_confident, else ``"neutral"``.
    source_text_length:
        Character count of the original source text.
    parsed_at:
        UTC timestamp when parsing ran.
    """

    transcript_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""
    ticker: str = ""
    fiscal_period: str = ""
    call_date: Optional[date] = None
    section: str = "unknown"
    catalyst_mentions: list[CatalystMention] = Field(default_factory=list)
    guidance_items: list[GuidanceItem] = Field(default_factory=list)
    tonal_signals: list[TonalSignal] = Field(default_factory=list)
    n_confident: int = 0
    n_cautious: int = 0
    overall_tone: str = "neutral"
    source_text_length: int = 0
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# EarningsTranscriptParser
# ---------------------------------------------------------------------------

class EarningsTranscriptParser:
    """
    Pattern-based parser for biotech earnings call transcripts.

    Parameters
    ----------
    min_sentence_length:
        Sentences shorter than this (characters) are skipped for tone
        and catalyst extraction.  Default 30.

    Examples
    --------
    >>> parser = EarningsTranscriptParser()
    >>> transcript = parser.parse(raw_text, company_id="co-regen", ticker="REGN")
    >>> print(transcript.overall_tone, len(transcript.catalyst_mentions))
    """

    def __init__(self, min_sentence_length: int = 30) -> None:
        self.min_sentence_length = min_sentence_length

    def parse(
        self,
        text: str,
        *,
        company_id: str = "",
        ticker: str = "",
        fiscal_period: str = "",
        call_date: Optional[date] = None,
    ) -> EarningsTranscript:
        """
        Parse *text* into a structured :class:`EarningsTranscript`.

        Parameters
        ----------
        text:
            Full transcript text.
        company_id:
            Company identifier (passed through to output).
        ticker:
            Equity ticker (passed through to output).
        fiscal_period:
            E.g. ``"Q1 2025"``.
        call_date:
            Date of the call.

        Returns
        -------
        EarningsTranscript
        """
        section = _detect_section(text)
        sentences = self._split_sentences(text)

        catalyst_mentions: list[CatalystMention] = []
        guidance_items: list[GuidanceItem] = []
        tonal_signals: list[TonalSignal] = []
        n_confident = 0
        n_cautious = 0

        for sentence in sentences:
            if len(sentence) < self.min_sentence_length:
                continue

            # --- Catalyst extraction ---
            catalyst = self._extract_catalyst(sentence)
            if catalyst:
                catalyst_mentions.append(catalyst)

            # --- Guidance extraction ---
            if _GUIDANCE_KEYWORD_RE.search(sentence):
                guidance = self._extract_guidance(sentence)
                guidance_items.append(guidance)

            # --- Tone ---
            tone = _detect_tone(sentence)
            tonal_signals.append(TonalSignal(tone=tone, mention_text=sentence[:200]))
            if tone == "confident":
                n_confident += 1
            elif tone == "cautious":
                n_cautious += 1

        if n_confident > n_cautious:
            overall_tone = "confident"
        elif n_cautious > n_confident:
            overall_tone = "cautious"
        else:
            overall_tone = "neutral"

        return EarningsTranscript(
            company_id=company_id,
            ticker=ticker,
            fiscal_period=fiscal_period,
            call_date=call_date,
            section=section,
            catalyst_mentions=catalyst_mentions,
            guidance_items=guidance_items,
            tonal_signals=tonal_signals,
            n_confident=n_confident,
            n_cautious=n_cautious,
            overall_tone=overall_tone,
            source_text_length=len(text),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split text into sentences on '.', '!', '?' boundaries."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _extract_catalyst(self, sentence: str) -> Optional[CatalystMention]:
        """Extract a catalyst mention from a single sentence if present."""
        nct_match = _NCT_RE.search(sentence)
        phase_match = _PHASE_RE.search(sentence)
        readout_match = _READOUT_DATE_RE.search(sentence)
        topline_match = _TOPLINE_RE.search(sentence)

        has_catalyst = any([nct_match, phase_match, readout_match, topline_match])
        if not has_catalyst:
            return None

        nct_id = nct_match.group(0) if nct_match else None
        trial_phase = phase_match.group(0) if phase_match else None
        expected_readout = readout_match.group(0) if readout_match else None

        return CatalystMention(
            nct_id=nct_id,
            trial_phase=trial_phase,
            expected_readout=expected_readout,
            mention_text=sentence[:300],
        )

    @staticmethod
    def _extract_guidance(sentence: str) -> GuidanceItem:
        """Extract a guidance item from a sentence that contains a guidance keyword."""
        direction = _detect_guidance_direction(sentence)
        amount = _extract_revenue_amount(sentence)

        # Classify guidance type
        if any(kw in sentence.lower() for kw in ("revenue", "net sales", "product sales")):
            guidance_type = "revenue"
        elif any(kw in sentence.lower() for kw in ("r&d", "research and development", "pipeline")):
            guidance_type = "rd_spend"
        elif any(kw in sentence.lower() for kw in ("readout", "data", "topline", "trial")):
            guidance_type = "pipeline"
        else:
            guidance_type = "other"

        return GuidanceItem(
            guidance_type=guidance_type,
            direction=direction,
            amount_millions=amount,
            mention_text=sentence[:300],
        )
