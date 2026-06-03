"""
bve-note CLI — Expert network note entry (Sprint 18).

Usage
-----
    bve-note --ticker VKTX \\
             --type physician_call \\
             --date 2026-04-15 \\
             --content "12% weight loss at 24 weeks. Well tolerated." \\
             --confidence 0.70

    # Also save as ThesisClaims:
    bve-note --ticker VKTX --type physician_call --date 2026-04-15 \\
             --content "..." --confidence 0.70 --asset-id vktx_vk2735 --company-id vktx

    # Custom DB path:
    bve-note ... --db outputs/intelligence/ops.db
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path


def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date '{s}' — expected YYYY-MM-DD")


def _parse_confidence(s: str) -> float:
    try:
        v = float(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid confidence '{s}' — expected float 0.0–1.0")
    if not (0.0 <= v <= 1.0):
        raise argparse.ArgumentTypeError(f"Confidence must be 0.0–1.0, got {v}")
    return v


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bve-note",
        description="Store a structured expert network note and extract investment signals.",
    )
    p.add_argument("--ticker", required=True, help="Equity ticker (e.g. VKTX)")
    p.add_argument(
        "--type",
        dest="note_type",
        required=True,
        choices=["physician_call", "kol_interview", "conference", "channel_check", "other"],
        help="Note source type",
    )
    p.add_argument(
        "--date",
        dest="noted_at",
        required=True,
        type=_parse_date,
        metavar="YYYY-MM-DD",
        help="Date of the interview/call",
    )
    p.add_argument("--content", required=True, help="Free-text note content")
    p.add_argument(
        "--confidence",
        required=True,
        type=_parse_confidence,
        metavar="0.0-1.0",
        help="Analyst confidence in the note",
    )
    p.add_argument("--asset-id", default=None, help="Asset ID (for ThesisClaim creation)")
    p.add_argument("--company-id", default=None, help="Company ID (for ThesisClaim creation)")
    p.add_argument("--author", default=None, help="Author identifier (initials, pseudonym)")
    p.add_argument("--source-ref", default=None, help="Reference (transcript ID, session)")
    p.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="Path to KnowledgeStore SQLite database (default: outputs/intelligence/ops.db)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and extract signals without writing to DB",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    from bve.intelligence.expert_notes import (
        ExpertNote,
        extract_signals,
        note_to_claims,
        save_expert_note,
    )

    note = ExpertNote(
        ticker=args.ticker,
        asset_id=args.asset_id or args.ticker.lower(),
        company_id=args.company_id or args.ticker.lower(),
        note_type=args.note_type,
        content=args.content,
        confidence=args.confidence,
        noted_at=args.noted_at,
        author=args.author,
        source_ref=args.source_ref,
    )

    signals = extract_signals(note.content)

    # Print extracted signals
    print(f"\nExpert note: {note.ticker} / {note.note_type} / {note.noted_at}")
    print(f"Confidence : {note.confidence:.0%}")
    if signals:
        print(f"Signals    : {len(signals)} extracted")
        for s in signals:
            print(f"  [{s.signal_type:10s}] {s.matched_text}")
    else:
        print("Signals    : none extracted")

    if args.dry_run:
        print("\n[dry-run] No data written.")
        return

    # Resolve DB path
    if args.db:
        db_path = Path(args.db)
    else:
        from bve.ops.weekly_runner import DB_PATH
        db_path = DB_PATH

    from bve.intelligence.knowledge_layer import KnowledgeStore

    store = KnowledgeStore(db_path)
    try:
        note_id = save_expert_note(note, signals, store)
        print(f"\nSaved note : {note_id}")

        # Create ThesisClaims if asset_id provided
        if args.asset_id and signals:
            from bve.intelligence.thesis_tracker import ThesisTracker
            tracker = ThesisTracker(store)
            claims = note_to_claims(note, signals, tracker)
            if claims:
                print(f"Claims     : {len(claims)} created")
                for c in claims:
                    print(f"  {c.claim_type.value}: {c.assertion[:80]}...")
    finally:
        store.close()


if __name__ == "__main__":
    main()
