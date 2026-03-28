"""
Expert network integration layer — Sprint 18.

Stores structured expert notes in KnowledgeStore and extracts signals from
free text using keyword-based rules. Converts signals to ThesisClaims.

Signal types extracted
----------------------
- efficacy : quantitative outcome mentions (% weight loss, HbA1c, etc.)
- safety   : tolerability and adverse event mentions
- commercial: prescribing behaviour, formulary, switching signals

Usage
-----
    from bve.intelligence.expert_notes import ExpertNote, extract_signals, save_expert_note
    from bve.intelligence.knowledge_layer import KnowledgeStore

    store = KnowledgeStore("outputs/intelligence/ops.db")
    note = ExpertNote(
        ticker="VKTX",
        asset_id="vktx_vk2735",
        company_id="vktx",
        note_type="physician_call",
        content="12% weight loss at 24 weeks. Well tolerated. Switching semaglutide patients.",
        confidence=0.70,
        noted_at=date(2026, 4, 15),
    )
    signals = extract_signals(note.content)
    save_expert_note(note, signals, store)
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.intelligence.thesis_tracker import ThesisClaim, ThesisTracker


# ---------------------------------------------------------------------------
# Signal types
# ---------------------------------------------------------------------------

SignalType = Literal["efficacy", "safety", "commercial"]

NOTE_TYPES = frozenset(
    {"physician_call", "kol_interview", "conference", "channel_check", "other"}
)

# ---------------------------------------------------------------------------
# Regex patterns for signal extraction
# ---------------------------------------------------------------------------

_EFFICACY_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        r"(\d+)%\s+(weight loss|HbA1c|EASI|TTP|reduction|response|OS|PFS|ORR|remission)",
        re.compile(
            r"(\d+)%\s+(weight loss|HbA1c|EASI|TTP|reduction|response|OS|PFS|ORR|remission)",
            re.IGNORECASE,
        ),
    ),
    (
        r"(statistically significant|clinically meaningful|significant improvement)",
        re.compile(
            r"(statistically significant|clinically meaningful|significant improvement)",
            re.IGNORECASE,
        ),
    ),
    (
        r"(durable response|complete response|partial response|disease-free)",
        re.compile(
            r"(durable response|complete response|partial response|disease-free)",
            re.IGNORECASE,
        ),
    ),
]

_SAFETY_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        r"(well tolerated|well-tolerated|discontinuation|adverse|side effect|toxicity|safety profile)",
        re.compile(
            r"(well tolerated|well-tolerated|discontinuation|adverse|side effect|toxicity|safety profile)",
            re.IGNORECASE,
        ),
    ),
]

_COMMERCIAL_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        r"(switching|prescribing|formulary|market share|adoption|payer|reimbursement|prior auth)",
        re.compile(
            r"(switching|prescribing|formulary|market share|adoption|payer|reimbursement|prior auth)",
            re.IGNORECASE,
        ),
    ),
]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ExtractedSignal:
    """One extracted signal from expert note content."""

    signal_type: str           # efficacy | safety | commercial
    matched_text: str          # exact text match
    pattern: str               # regex pattern description


@dataclass
class ExpertNote:
    """
    One structured expert network note.

    Parameters
    ----------
    ticker:
        Equity ticker (e.g. "VKTX").
    asset_id:
        Asset ID in the knowledge store (e.g. "vktx_vk2735").
    company_id:
        Company ID (e.g. "vktx").
    note_type:
        Source type: physician_call | kol_interview | conference |
        channel_check | other.
    content:
        Free-text content of the note.
    confidence:
        Analyst confidence in the note (0.0–1.0).
    noted_at:
        Date the interview/call was conducted.
    note_id:
        UUID generated automatically.
    author:
        Optional author identifier (analyst initials, pseudonym).
    source_ref:
        Optional reference string (call transcript ID, conference session).
    """

    ticker: str
    asset_id: str
    company_id: str
    note_type: str
    content: str
    confidence: float
    noted_at: date
    note_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    author: Optional[str] = None
    source_ref: Optional[str] = None


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------

def extract_signals(content: str) -> list[ExtractedSignal]:
    """
    Extract structured signals from expert note free text.

    Returns a list of ExtractedSignal objects — one per match.
    Duplicate matches within the same signal_type are deduplicated
    by (signal_type, matched_text.lower()).
    """
    signals: list[ExtractedSignal] = []
    seen: set[tuple[str, str]] = set()

    def _add(sig_type: str, text: str, pat_desc: str) -> None:
        key = (sig_type, text.lower())
        if key not in seen:
            seen.add(key)
            signals.append(ExtractedSignal(
                signal_type=sig_type,
                matched_text=text,
                pattern=pat_desc,
            ))

    for pat_desc, pattern in _EFFICACY_PATTERNS:
        for m in pattern.finditer(content):
            _add("efficacy", m.group(0), pat_desc)

    for pat_desc, pattern in _SAFETY_PATTERNS:
        for m in pattern.finditer(content):
            _add("safety", m.group(0), pat_desc)

    for pat_desc, pattern in _COMMERCIAL_PATTERNS:
        for m in pattern.finditer(content):
            _add("commercial", m.group(0), pat_desc)

    return signals


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_expert_note(
    note: ExpertNote,
    signals: list[ExtractedSignal],
    store: "KnowledgeStore",
) -> str:
    """
    Persist an ExpertNote and its extracted signals to the KnowledgeStore.

    The `expert_notes` table is created lazily (INSERT OR IGNORE pattern).

    Returns
    -------
    str
        The note_id of the saved record.
    """
    _ensure_schema(store)

    signals_json = json.dumps(
        [
            {"signal_type": s.signal_type, "matched_text": s.matched_text, "pattern": s.pattern}
            for s in signals
        ]
    )
    now = datetime.now(timezone.utc).isoformat()

    store._conn.execute(
        """
        INSERT OR IGNORE INTO expert_notes
            (id, ticker, asset_id, company_id, note_type, content,
             confidence, noted_at, author, source_ref, signals_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            note.note_id,
            note.ticker.upper(),
            note.asset_id,
            note.company_id,
            note.note_type,
            note.content,
            note.confidence,
            note.noted_at.isoformat(),
            note.author,
            note.source_ref,
            signals_json,
            now,
        ),
    )
    store._conn.commit()
    return note.note_id


def get_expert_notes(
    store: "KnowledgeStore",
    ticker: Optional[str] = None,
    asset_id: Optional[str] = None,
    note_type: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """
    Retrieve expert notes from KnowledgeStore, with optional filters.

    Returns list of row dicts ordered by noted_at DESC.
    """
    _ensure_schema(store)

    clauses: list[str] = []
    params: list = []

    if ticker is not None:
        clauses.append("ticker = ?")
        params.append(ticker.upper())
    if asset_id is not None:
        clauses.append("asset_id = ?")
        params.append(asset_id)
    if note_type is not None:
        clauses.append("note_type = ?")
        params.append(note_type)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM expert_notes {where} ORDER BY noted_at DESC LIMIT ?"
    params.append(limit)

    cur = store._conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Claim conversion
# ---------------------------------------------------------------------------

def note_to_claims(
    note: ExpertNote,
    signals: list[ExtractedSignal],
    tracker: "ThesisTracker",
) -> list["ThesisClaim"]:
    """
    Convert an ExpertNote and its signals into ThesisClaims via ThesisTracker.

    One claim is generated per signal_type group (at most three claims):
    - efficacy signals  → ClaimType.ENDPOINT_MET (assertion: efficacy evidence)
    - safety signals    → ClaimType.CUSTOM (assertion: safety profile evidence)
    - commercial signals → ClaimType.CUSTOM (assertion: commercial traction signal)

    Returns
    -------
    list[ThesisClaim]
        The newly created claims (already persisted via tracker).
    """
    from bve.intelligence.thesis_tracker import ClaimType

    if not signals:
        return []

    claims = []
    sig_by_type: dict[str, list[ExtractedSignal]] = {}
    for s in signals:
        sig_by_type.setdefault(s.signal_type, []).append(s)

    if "efficacy" in sig_by_type:
        texts = "; ".join(s.matched_text for s in sig_by_type["efficacy"])
        assertion = (
            f"Expert note ({note.note_type}): efficacy evidence — {texts} "
            f"[confidence={note.confidence:.0%}]"
        )
        claim = tracker.add_claim(
            asset_id=note.asset_id,
            company_id=note.company_id,
            claim_type=ClaimType.ENDPOINT_MET,
            assertion=assertion,
            created_by_signal_id=note.note_id,
        )
        claims.append(claim)

    if "safety" in sig_by_type:
        texts = "; ".join(s.matched_text for s in sig_by_type["safety"])
        assertion = (
            f"Expert note ({note.note_type}): safety signal — {texts} "
            f"[confidence={note.confidence:.0%}]"
        )
        claim = tracker.add_claim(
            asset_id=note.asset_id,
            company_id=note.company_id,
            claim_type=ClaimType.CUSTOM,
            assertion=assertion,
            categorical_value="safety_signal",
            created_by_signal_id=note.note_id,
        )
        claims.append(claim)

    if "commercial" in sig_by_type:
        texts = "; ".join(s.matched_text for s in sig_by_type["commercial"])
        assertion = (
            f"Expert note ({note.note_type}): commercial signal — {texts} "
            f"[confidence={note.confidence:.0%}]"
        )
        claim = tracker.add_claim(
            asset_id=note.asset_id,
            company_id=note.company_id,
            claim_type=ClaimType.CUSTOM,
            assertion=assertion,
            categorical_value="commercial_signal",
            created_by_signal_id=note.note_id,
        )
        claims.append(claim)

    return claims


# ---------------------------------------------------------------------------
# Schema helper
# ---------------------------------------------------------------------------

def _ensure_schema(store: "KnowledgeStore") -> None:
    store._conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expert_notes (
            id          TEXT PRIMARY KEY,
            ticker      TEXT NOT NULL,
            asset_id    TEXT NOT NULL,
            company_id  TEXT NOT NULL,
            note_type   TEXT NOT NULL,
            content     TEXT NOT NULL,
            confidence  REAL NOT NULL,
            noted_at    TEXT NOT NULL,
            author      TEXT,
            source_ref  TEXT,
            signals_json TEXT,
            created_at  TEXT NOT NULL
        )
        """
    )
    store._conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_expert_notes_ticker
            ON expert_notes(ticker, noted_at)
        """
    )
    store._conn.commit()
