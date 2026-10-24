"""Opt-in adapter for previously audited manual records; no retrieval or identity matching."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from bve.se.reporting.bd_brief import CandidateCard, ResearchFollowup


def load_followup(
    records_path: Path,
    ledger_path: Path,
    *,
    asset_id: str,
    name: str,
    verified_on: date,
    display_as_of: date,
    verification: str,
) -> ResearchFollowup:
    """Select one exact manual record. Hashes attest input bytes, not factual entailment.

    Locators refer to the supplied files; archived raw evidence is not re-audited here.
    The caller supplies manual-review provenance, never an inferred reviewer or date.
    """
    record_bytes, ledger_bytes = records_path.read_bytes(), ledger_path.read_bytes()
    records, ledger = json.loads(record_bytes), json.loads(ledger_bytes)
    matches = [lead for lead in records["leads"] if lead["name"] == name]
    if len(matches) != 1:
        raise ValueError("exactly one exact-name manual record required")
    if records["observed_date"] != ledger["observed_date"]:
        raise ValueError("record/ledger observation dates disagree")
    lead = matches[0]
    references = {
        (s["label"], s.get("url")) for f in lead["facts"].values() for s in f.get("sources", [])
    }
    return ResearchFollowup(
        asset_id=asset_id,
        name=name,
        observed_on=records["observed_date"],
        verified_on=verified_on,
        display_as_of=display_as_of,
        verification=verification,
        record_sha256=hashlib.sha256(record_bytes).hexdigest(),
        ledger_sha256=hashlib.sha256(ledger_bytes).hexdigest(),
        record_locator=records_path.as_posix(),
        ledger_locator=ledger_path.as_posix(),
        evidence=tuple(e for e in ledger["evidence"] if (e["id"], e["url"]) in references),
        facts=lead["facts"],
        research_category=lead["research_category"],
        commercial_context=lead["commercial_context"],
        next_actions=lead["next_actions"],
    )


def attach_followup(card: CandidateCard, followup: ResearchFollowup) -> CandidateCard:
    """Return a validated copy; never alter an original engine field or infer an alias."""
    return CandidateCard.model_validate({**card.model_dump(), "research_followup": followup})
