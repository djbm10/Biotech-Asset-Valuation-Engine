"""
Wave F — Conference Event Detection with source fan-out.

Detects medical conference events from signals/events and maps them to
structured ConferencePresentation records.  One abstract signal can fan out
into multiple per-asset presentation records.

Design principles
-----------------
- Pattern-based, deterministic: no LLM calls, no external API calls.
- Fan-out: a single source signal may produce N presentations (one per asset
  mentioned or one per known conference found in the source text).
- Source traceability: every ConferencePresentation records the originating
  signal_id and event_id.
- Registry-driven: ConferenceCalendar is the single source of truth for
  known conference metadata.  Unknown conference names are stored as
  ``conference_key="unknown"``.

Conference taxonomy
-------------------
  ``asco``         — American Society of Clinical Oncology Annual Meeting
  ``esmo``         — European Society for Medical Oncology Congress
  ``ash``          — American Society of Hematology Annual Meeting
  ``asco_gio``     — ASCO Gastrointestinal Cancers Symposium
  ``aacr``         — American Association for Cancer Research Annual Meeting
  ``ada``          — American Diabetes Association Scientific Sessions
  ``acc``          — American College of Cardiology Scientific Sessions
  ``aha``          — American Heart Association Scientific Sessions
  ``idsa``         — Infectious Diseases Society of America
  ``easl``         — European Association for the Study of the Liver
  ``ean``          — European Academy of Neurology
  ``child_neurology`` — Child Neurology Society (for rare neurological diseases)
  ``rare_diseases`` — NORD Rare Diseases and Orphan Products Breakthrough Summit

Presentation types
------------------
  ``oral``         — oral presentation
  ``poster``       — poster presentation
  ``late_breaking`` — late-breaking abstract or trial
  ``symposium``    — invited symposium/mini-oral
  ``unknown``      — type not determinable
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Conference registry entry
# ---------------------------------------------------------------------------

class ConferenceEntry(BaseModel):
    """One known medical conference."""

    model_config = {"frozen": True}

    key: str                       # short code, e.g. "asco"
    display_name: str              # full name
    aliases: list[str]             # lower-case alternate spellings / acronyms
    typical_month_range: tuple[int, int]  # (month_start, month_end) inclusive
    therapeutic_area: Optional[str] = None  # primary TA focus


# ---------------------------------------------------------------------------
# ConferenceCalendar — known conferences
# ---------------------------------------------------------------------------

_CONFERENCES: list[ConferenceEntry] = [
    ConferenceEntry(
        key="asco",
        display_name="ASCO Annual Meeting",
        aliases=["asco", "american society of clinical oncology", "asco annual"],
        typical_month_range=(5, 6),
        therapeutic_area="oncology",
    ),
    ConferenceEntry(
        key="esmo",
        display_name="ESMO Congress",
        aliases=["esmo", "european society for medical oncology", "esmo congress"],
        typical_month_range=(9, 10),
        therapeutic_area="oncology",
    ),
    ConferenceEntry(
        key="ash",
        display_name="ASH Annual Meeting",
        aliases=["ash", "american society of hematology", "ash annual meeting"],
        typical_month_range=(12, 12),
        therapeutic_area="hematology",
    ),
    ConferenceEntry(
        key="asco_gio",
        display_name="ASCO GI Cancers Symposium",
        aliases=["asco gi", "asco gastrointestinal", "asco gio"],
        typical_month_range=(1, 1),
        therapeutic_area="gastrointestinal_oncology",
    ),
    ConferenceEntry(
        key="aacr",
        display_name="AACR Annual Meeting",
        aliases=["aacr", "american association for cancer research"],
        typical_month_range=(4, 4),
        therapeutic_area="oncology",
    ),
    ConferenceEntry(
        key="ada",
        display_name="ADA Scientific Sessions",
        aliases=["ada", "american diabetes association", "ada scientific sessions"],
        typical_month_range=(6, 6),
        therapeutic_area="diabetes",
    ),
    ConferenceEntry(
        key="acc",
        display_name="ACC Scientific Sessions",
        aliases=["acc", "american college of cardiology"],
        typical_month_range=(3, 4),
        therapeutic_area="cardiology",
    ),
    ConferenceEntry(
        key="aha",
        display_name="AHA Scientific Sessions",
        aliases=["aha", "american heart association scientific sessions"],
        typical_month_range=(11, 11),
        therapeutic_area="cardiology",
    ),
    ConferenceEntry(
        key="idsa",
        display_name="IDWeek (IDSA/SHEA)",
        aliases=["idsa", "idweek", "infectious diseases society"],
        typical_month_range=(10, 10),
        therapeutic_area="infectious_disease",
    ),
    ConferenceEntry(
        key="easl",
        display_name="EASL Congress",
        aliases=["easl", "european association for the study of the liver"],
        typical_month_range=(5, 6),
        therapeutic_area="hepatology",
    ),
    ConferenceEntry(
        key="ean",
        display_name="EAN Congress",
        aliases=["ean", "european academy of neurology"],
        typical_month_range=(6, 7),
        therapeutic_area="neurology",
    ),
    ConferenceEntry(
        key="nord",
        display_name="NORD Rare Diseases Summit",
        aliases=["nord", "rare diseases summit", "nord summit"],
        typical_month_range=(10, 10),
        therapeutic_area="rare_disease",
    ),
]


class ConferenceCalendar:
    """
    Registry of known medical conferences.

    Parameters
    ----------
    entries:
        Custom conference list.  Defaults to the built-in ``_CONFERENCES``.
    """

    def __init__(self, entries: Optional[list[ConferenceEntry]] = None) -> None:
        self._entries = entries if entries is not None else _CONFERENCES
        # Build alias lookup: lower(alias) → ConferenceEntry
        self._alias_map: dict[str, ConferenceEntry] = {}
        for entry in self._entries:
            for alias in entry.aliases:
                self._alias_map[alias.lower()] = entry

    def lookup(self, text: str) -> Optional[ConferenceEntry]:
        """
        Return the first conference whose alias appears in *text* (case-insensitive).

        Tries exact alias matches from longest to shortest to avoid false
        positives on short acronyms (e.g. "ash" inside "crash").
        """
        lower = text.lower()
        # Sort by alias length descending to prefer longer / more specific matches
        for alias in sorted(self._alias_map, key=len, reverse=True):
            if alias in lower:
                return self._alias_map[alias]
        return None

    def lookup_by_key(self, key: str) -> Optional[ConferenceEntry]:
        """Return a conference by its canonical key."""
        for entry in self._entries:
            if entry.key == key:
                return entry
        return None

    @property
    def all_entries(self) -> list[ConferenceEntry]:
        return list(self._entries)


# ---------------------------------------------------------------------------
# Presentation type detection
# ---------------------------------------------------------------------------

PresentationType = str  # "oral" | "poster" | "late_breaking" | "symposium" | "unknown"

_ORAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(oral(ly)?|oral abstract|oral presentation)\b", re.IGNORECASE),
]
_POSTER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bposter\b", re.IGNORECASE),
]
_LATE_BREAKING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(late.breaking|lba\s*\d+|lba\b)", re.IGNORECASE),
]
_SYMPOSIUM_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(symposium|mini.oral|mini oral|invited)\b", re.IGNORECASE),
]


def _detect_presentation_type(text: str) -> PresentationType:
    """Infer presentation type from *text*."""
    for pattern in _LATE_BREAKING_PATTERNS:
        if pattern.search(text):
            return "late_breaking"
    for pattern in _ORAL_PATTERNS:
        if pattern.search(text):
            return "oral"
    for pattern in _SYMPOSIUM_PATTERNS:
        if pattern.search(text):
            return "symposium"
    for pattern in _POSTER_PATTERNS:
        if pattern.search(text):
            return "poster"
    return "unknown"


def _extract_abstract_number(text: str) -> Optional[str]:
    """Extract an abstract number like '#1234', 'Abstract 1234', or 'LBA12'."""
    # Must be followed by actual digits (not plain words)
    m = re.search(
        r"(?:abstract\s*#?\s*|#\s*|lba\s*)(\d[\w]{0,7})\b",
        text,
        re.IGNORECASE,
    )
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# ConferencePresentation model
# ---------------------------------------------------------------------------

class ConferencePresentation(BaseModel):
    """
    A single asset's presentation at a medical conference.

    Produced by :class:`ConferenceEventDetector`.  Multiple presentations
    can be generated from one source signal (fan-out).

    Attributes
    ----------
    presentation_id:
        UUID for this record.
    signal_id:
        Originating StructuredSignal id.
    event_id:
        Originating Event id.
    asset_id:
        Asset being presented.
    company_id:
        Company presenting.
    conference_key:
        Short code from :class:`ConferenceCalendar` (e.g. ``"asco"``).
        ``"unknown"`` when the conference was not identified.
    conference_display_name:
        Human-readable conference name.
    presentation_type:
        One of ``"oral"``, ``"poster"``, ``"late_breaking"``,
        ``"symposium"``, ``"unknown"``.
    abstract_number:
        Parsed abstract number if present in the source text.
    presentation_date:
        Expected or announced presentation date (may be approximate).
    headline:
        Short description of what is being presented.
    source_text:
        Snippet of source text that triggered detection.
    detected_at:
        UTC timestamp when detection ran.
    """

    presentation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: Optional[str] = None
    event_id: Optional[str] = None
    asset_id: str
    company_id: str
    conference_key: str = "unknown"
    conference_display_name: str = "Unknown Conference"
    presentation_type: PresentationType = "unknown"
    abstract_number: Optional[str] = None
    presentation_date: Optional[date] = None
    headline: str = ""
    source_text: str = ""
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# ConferenceEventDetector
# ---------------------------------------------------------------------------

class ConferenceEventDetector:
    """
    Pattern-based detector for medical conference events.

    Parameters
    ----------
    calendar:
        :class:`ConferenceCalendar` to use for conference lookup.
        Defaults to the built-in registry.

    Examples
    --------
    >>> detector = ConferenceEventDetector()
    >>> presentations = detector.detect_from_signal(signal, event=event)
    >>> for p in presentations:
    ...     print(p.conference_key, p.presentation_type)
    """

    #: Event types that imply conference-sourced data.
    CONFERENCE_EVENT_TYPES: frozenset[str] = frozenset({
        "conference_abstract",
        "conference_presentation",
        "congress_abstract",
        "data_presentation",
        "trial_readout",     # readouts often announced at conferences
        "topline_results",
    })

    def __init__(
        self,
        calendar: Optional[ConferenceCalendar] = None,
    ) -> None:
        self.calendar = calendar or ConferenceCalendar()

    def detect_from_signal(
        self,
        signal: object,
        *,
        event: Optional[object] = None,
    ) -> list[ConferencePresentation]:
        """
        Fan-out detection from a StructuredSignal (with optional raw Event).

        Returns a list of :class:`ConferencePresentation` records.  Returns
        an empty list when no conference context is found.

        Parameters
        ----------
        signal:
            A ``StructuredSignal``-like object.
        event:
            The parent ``Event``-like object.  Used for source_url,
            raw_text, and source_type enrichment.
        """
        # Gather all text sources
        text_parts: list[str] = []
        signal_id = str(getattr(signal, "id", "") or "")
        event_id = str(getattr(signal, "event_id", "") or "")
        asset_id = str(getattr(signal, "asset_id", "") or "")
        company_id = str(getattr(signal, "company_id", "") or "")

        event_type_str = str(getattr(signal, "event_type", "") or "")
        headline = ""
        source_url = ""
        raw_text = ""

        source_type = ""
        if event is not None:
            headline = str(getattr(event, "headline", "") or "")
            raw_text = str(getattr(event, "raw_text", "") or "")
            source_url = str(getattr(event, "source_url", "") or "")
            source_type = str(getattr(event, "source_type", "") or "")
            text_parts.extend([headline, raw_text, source_url])
        else:
            # Try to get headline / raw_text from signal if no event given
            headline = str(getattr(signal, "headline", "") or "")
            raw_text = str(getattr(signal, "raw_text", "") or "")
            source_url = str(getattr(signal, "source_url", "") or "")
            text_parts.extend([headline, raw_text, source_url])

        text_parts.append(event_type_str)
        combined_text = " ".join(t for t in text_parts if t)

        # source_type is a strong indicator if it names a conference channel,
        # but we do NOT add it to combined_text to avoid keyword false-positives.
        is_conference_source_type = source_type.lower() in {
            "conference_abstract", "conference_presentation", "congress_abstract"
        }
        is_conference_event_type = event_type_str.lower() in {
            et.lower() for et in self.CONFERENCE_EVENT_TYPES
        }

        # Check if source_type is conference_abstract — strong signal
        is_conference_source = (
            is_conference_source_type
            or is_conference_event_type
            or "conference" in combined_text.lower()
            or "congress" in combined_text.lower()
            or "abstract" in combined_text.lower()
        )

        if not is_conference_source and not combined_text.strip():
            return []

        # Try to identify which conference
        conference_entry = self.calendar.lookup(combined_text)

        # If no conference found but the source is clearly conference-typed, still emit
        if conference_entry is None and not is_conference_source:
            return []

        conf_key = conference_entry.key if conference_entry else "unknown"
        conf_name = conference_entry.display_name if conference_entry else "Unknown Conference"

        presentation_type = _detect_presentation_type(combined_text)
        abstract_number = _extract_abstract_number(combined_text)

        # Build source_text snippet (first 300 chars of headline + raw_text)
        snippet = (headline + " " + raw_text[:200]).strip()[:300]

        presentation = ConferencePresentation(
            signal_id=signal_id or None,
            event_id=event_id or None,
            asset_id=asset_id,
            company_id=company_id,
            conference_key=conf_key,
            conference_display_name=conf_name,
            presentation_type=presentation_type,
            abstract_number=abstract_number,
            headline=headline[:280],
            source_text=snippet,
        )
        return [presentation]

    def detect_from_text(
        self,
        text: str,
        *,
        asset_id: str,
        company_id: str,
        signal_id: Optional[str] = None,
        event_id: Optional[str] = None,
        presentation_date: Optional[date] = None,
    ) -> list[ConferencePresentation]:
        """
        Detect conference presentations directly from raw text.

        Useful for batch processing of free-text news feeds or abstract
        archives.  Returns an empty list if no conference context found.
        """
        if not text.strip():
            return []

        conference_entry = self.calendar.lookup(text)
        is_conference_context = (
            conference_entry is not None
            or "conference" in text.lower()
            or "congress" in text.lower()
            or "abstract" in text.lower()
        )
        if not is_conference_context:
            return []

        conf_key = conference_entry.key if conference_entry else "unknown"
        conf_name = conference_entry.display_name if conference_entry else "Unknown Conference"
        presentation_type = _detect_presentation_type(text)
        abstract_number = _extract_abstract_number(text)

        return [
            ConferencePresentation(
                signal_id=signal_id,
                event_id=event_id,
                asset_id=asset_id,
                company_id=company_id,
                conference_key=conf_key,
                conference_display_name=conf_name,
                presentation_type=presentation_type,
                abstract_number=abstract_number,
                presentation_date=presentation_date,
                headline=text[:280],
                source_text=text[:300],
            )
        ]
