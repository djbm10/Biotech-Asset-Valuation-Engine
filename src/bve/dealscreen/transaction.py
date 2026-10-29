"""Buyer-declared transaction preferences and the transaction view (cycle C1 X5).

Scientific eligibility answers "does this program fit the biology the buyer wants?". The transaction
view answers "is it an opportunity this buyer can pursue?", from the buyer's declared preferences
only. It never changes a gate, a disposition or the scientific rank, and it never infers availability:
OPEN means "no declared obstacle found", not "available".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from bve.dealscreen.commercial import ENCUMBERED, OPTION, RETURNED


class TransactionPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    #: What to do with a program marketed in the U.S. per source.
    marketed: Literal["exclude", "deprioritize", "ignore"] = "ignore"
    #: Holders the buyer considers unattractive counterparties (e.g. companies already holding U.S.
    #: rights). Matched against cited holder evidence first, then the registry sponsor / labeler.
    deprioritized_holders: list[str] = Field(default_factory=list)
    #: Licensed or optioned rights per source.
    encumbered_rights: Literal["deprioritize", "ignore"] = "ignore"


TIER_ORDER = {"OPEN": 0, "DEPRIORITIZED": 1, "EXCLUDED_BY_BUYER_PREFERENCE": 2}


@dataclass
class TransactionView:
    tier: str  # OPEN / DEPRIORITIZED / EXCLUDED_BY_BUYER_PREFERENCE / NOT_DECLARED
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _matches(name: str | None, holders: list[str]) -> str | None:
    """Whole-word match of a declared holder name (review C1-7): "Ono" does not match "Sonoma".
    A declared "Merck" matches both "Merck KGaA" and "Merck & Co"; declare the full name to narrow it."""
    import re

    for holder in holders:
        if holder.strip() and re.search(rf"(?<!\w){re.escape(holder.strip())}(?!\w)", name or "", re.IGNORECASE):
            return holder
    return None


def assess_transaction(
    prefs: TransactionPreferences | None,
    *,
    market_status: str | None,
    rights_status: str,
    rights_holder: str | None,
    company: str | None,
    identity_twins: list[str],
) -> TransactionView:
    notes = [f"may be the same molecule as {', '.join(identity_twins)} (identity flag; check its resolution)"] if identity_twins else []
    if rights_status == RETURNED:
        notes.append("rights returned to the originator per source (not a statement of availability)")
    if prefs is None:
        return TransactionView("NOT_DECLARED", [], notes)
    excluded: list[str] = []
    deprioritized: list[str] = []
    if market_status == "US_MARKETED" and prefs.marketed != "ignore":
        (excluded if prefs.marketed == "exclude" else deprioritized).append("marketed in the U.S. per source")
    if (hit := _matches(rights_holder, prefs.deprioritized_holders)):
        deprioritized.append(f"U.S. rights holder per cited evidence matches '{hit}'")
    elif (hit := _matches(company, prefs.deprioritized_holders)):
        deprioritized.append(f"registry sponsor / labeler matches '{hit}' (not a rights statement; verify)")
    if prefs.encumbered_rights == "deprioritize" and rights_status in (ENCUMBERED, OPTION):
        deprioritized.append("rights licensed or optioned per source")
    if excluded:
        return TransactionView("EXCLUDED_BY_BUYER_PREFERENCE", excluded + deprioritized, notes)
    if deprioritized:
        return TransactionView("DEPRIORITIZED", deprioritized, notes)
    return TransactionView("OPEN", ["no declared obstacle found; availability not evidenced"], notes)


def transaction_ranks(screens: list[dict[str, Any]]) -> dict[str, int]:
    """Rank ELIGIBLE programs by tier, then scientific rank. Separate from the scientific rank."""
    eligible = [s for s in screens if s["disposition"] == "ELIGIBLE" and s.get("transaction", {}).get("tier")
                and s["transaction"]["tier"] != "NOT_DECLARED"]
    ordered = sorted(eligible, key=lambda s: (TIER_ORDER.get(s["transaction"]["tier"], 9), s["rank"] or 10**6))
    return {s["asset_id"]: i + 1 for i, s in enumerate(ordered)}


__all__ = ["TIER_ORDER", "TransactionPreferences", "TransactionView", "assess_transaction", "transaction_ranks"]
