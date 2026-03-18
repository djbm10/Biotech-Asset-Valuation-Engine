"""
Wave 1 Part B — PDUFA date extractor from SEC filing text.

Applies regex patterns to 8-K / 10-K / 10-Q text.  No LLM needed; PDUFA
language is highly formulaic.

date_confidence
---------------
``"exact"``   — full month-day-year date found in text
``"quarter"`` — only Q#/year found (e.g. "Q3 2025")

Returns ``None`` when no PDUFA date is found.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from bve.intelligence.catalyst_calendar import CatalystEvent, CatalystType

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches: "PDUFA date is January 15, 2025" / "PDUFA goal date of March 2025"
# Capture group 1: full date string
_PDUFA_FULL_DATE = re.compile(
    r"PDUFA\s+(?:action\s+)?(?:goal\s+)?date\s+(?:is\s+|of\s+|on\s+)?"
    r"([A-Z][a-z]+\s+\d{1,2},?\s+\d{4}|Q[1-4]\s+\d{4})",
    re.IGNORECASE,
)

# Matches: "target action date of April 30, 2025"
_TARGET_ACTION_DATE = re.compile(
    r"target\s+action\s+date\s+(?:of\s+|on\s+)?([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})",
    re.IGNORECASE,
)

# Matches standalone quarter pattern: "Q1 2025" or "first quarter of 2025"
_QUARTER_PATTERN = re.compile(
    r"\bQ([1-4])\s+(\d{4})\b",
    re.IGNORECASE,
)

# Full month+day+year
_FULL_DATE_FMTS = [
    "%B %d %Y",   # January 15 2025
    "%B %d, %Y",  # January 15, 2025
    "%b %d %Y",   # Jan 15 2025
    "%b %d, %Y",  # Jan 15, 2025
]

# Quarter → approximate mid-quarter month
_QUARTER_MONTH: dict[int, int] = {1: 2, 2: 5, 3: 8, 4: 11}


def _parse_full_date(text: str) -> Optional[date]:
    """Try each full-date format on *text*; return date or None."""
    text = text.strip()
    for fmt in _FULL_DATE_FMTS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_quarter(text: str) -> Optional[date]:
    """Parse ``Q#YYYY`` → mid-quarter date."""
    m = _QUARTER_PATTERN.search(text)
    if not m:
        return None
    quarter = int(m.group(1))
    year = int(m.group(2))
    month = _QUARTER_MONTH[quarter]
    return date(year, month, 1)


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class PDUFAExtractor:
    """
    Extract PDUFA catalyst events from SEC filing text.

    Parameters
    ----------
    source_ref:
        SEC EDGAR accession number or URL — stored as CatalystEvent.source.
    """

    def extract(
        self,
        raw_text: str,
        entity_hints: dict,
    ) -> Optional[CatalystEvent]:
        """
        Scan *raw_text* for PDUFA date language.

        Parameters
        ----------
        raw_text:
            SEC 8-K / 10-K / 10-Q filing text (plain text, not HTML).
        entity_hints:
            dict with optional keys:
              ``asset_id``   — intelligence layer asset ID
              ``company_id`` — company identifier
              ``source``     — document source ref (accession / URL)

        Returns
        -------
        CatalystEvent with ``date_confidence="exact"`` or ``"quarter"``,
        or ``None`` when no PDUFA date is found.
        """
        asset_id  = entity_hints.get("asset_id")
        company_id = entity_hints.get("company_id")
        source    = entity_hints.get("source", "sec_edgar")

        # ---- Try exact-date patterns first --------------------------------
        for pattern in (_PDUFA_FULL_DATE, _TARGET_ACTION_DATE):
            m = pattern.search(raw_text)
            if m:
                captured = m.group(1).strip()

                # Is captured a quarter string?
                if _QUARTER_PATTERN.search(captured):
                    d = _parse_quarter(captured)
                    if d is not None:
                        return self._build(
                            asset_id, company_id, source, d, "quarter", captured
                        )
                    continue

                d = _parse_full_date(captured)
                if d is not None:
                    return self._build(
                        asset_id, company_id, source, d, "exact", captured
                    )

        return None

    @staticmethod
    def _build(
        asset_id: Optional[str],
        company_id: Optional[str],
        source: str,
        expected_date: date,
        confidence: str,
        raw_date_str: str,
    ) -> CatalystEvent:
        now = datetime.now(timezone.utc)
        return CatalystEvent(
            id              = str(uuid.uuid4()),
            asset_id        = asset_id,
            company_id      = company_id,
            catalyst_type   = CatalystType.PDUFA_DECISION,
            expected_date   = expected_date,
            date_confidence = confidence,  # type: ignore[arg-type]
            source          = source,
            description     = f"PDUFA decision date ({raw_date_str})",
            created_at      = now,
            updated_at      = now,
        )
