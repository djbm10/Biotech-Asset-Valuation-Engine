"""Buyer-declared transaction preferences and the transaction view (cycle C1 X5, cycle R1).

Scientific eligibility answers "does this program fit the biology the buyer wants?". The transaction
view answers "is it an opportunity this buyer can pursue?", from the rights evidence and the buyer's
declared preferences only. It never changes a gate, a disposition or the scientific rank.

Cycle R1 removed the ``OPEN`` tier. It read as "pursuable" while it only meant "no obstacle declared",
including when the tool held no rights evidence at all. The tiers now say what the evidence shows:

- ``AVAILABILITY_STATED_UNVERIFIED``: a dated, current source states availability or a partner search.
- ``NO_THIRD_PARTY_GRANT_IN_EVIDENCE``: current rights evidence exists and shows no third-party grant over
  the buyer territory (rights returned, an option lapsed, deals covering other territories only, or the
  owner itself acquired). This is not availability.
- ``RIGHTS_UNRESOLVED``: no rights evidence, conflicting evidence, a grant with an unreadable territory,
  shared rights, an encumbrance the buyer chose to ignore, an incomplete import, or a clear position
  whose evidence is older than the buyer's maximum age (as a stale availability statement is not counted,
  stale evidence of a return does not show the current position; review R1v2 S1).
- ``DEPRIORITIZED`` / ``EXCLUDED_BY_BUYER_PREFERENCE``: per the buyer's declared preferences.

Revision 4 (re-review 2): the two top tiers are an allow-list. A clear position enters them only when it carries
no ``top_tier_blockers`` (it is complete, specific and current; ``rights_position``), no import guard applies, and
no landscape or analyst statement contests it (``screening``). Otherwise it stays ``RIGHTS_UNRESOLVED`` with the
failed checks as reasons and a question naming them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from bve.dealscreen import rights_position as rp
from bve.dealscreen.commercial import (
    AVAILABLE,
    AVAILABLE_CONFIRMED,
    CONFLICTING,
    ENCUMBERED,
    NOT_AVAILABLE,
    OPTION,
    RETURNED,
    RIGHTS_STATUS_WORDS,
)
from bve.dealscreen.rights_gate import field_evidence, field_source
from bve.dealscreen.rights_territory import GENERIC_NAME_WORDS, REGIONS, name_matches, party_key

Treatment = Literal["exclude", "deprioritize", "ignore"]


class TransactionPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    #: What to do with a program marketed in the U.S. per source.
    marketed: Treatment = "ignore"
    #: Counterparties the buyer considers unattractive. Matched (whole words, punctuation and corporate
    #: suffixes ignored) against the holders and owner per rights evidence, and otherwise, flagged as not a
    #: rights statement, against the registry sponsor / labeler.
    deprioritized_holders: list[str] = Field(default_factory=list)
    #: A third party holds a license or an option over the buyer territory, per evidence.
    encumbered_rights: Treatment = "ignore"
    #: Rights shared with a partner (co-development, co-promotion, non-exclusive license), per evidence.
    shared_rights: Treatment = "ignore"
    #: Whether rights returned to the originator sort ahead of other programs in the same tier.
    returned_rights: Literal["prefer", "neutral"] = "neutral"
    #: Buyer territory (region codes, see ``rights_territory.REGIONS``). Empty -> ``required_market``.
    territory: list[str] = Field(default_factory=list)
    #: Rights evidence older than this before the buyer's as-of date is flagged stale.
    max_evidence_age_days: int = Field(default=730, ge=1)

    @field_validator("territory")
    @classmethod
    def _known_regions(cls, value: list[str]) -> list[str]:
        return [region_code(v) for v in value]


def region_code(value: str) -> str:
    """A buyer territory code, checked against ``REGIONS``. An unknown code is refused: it would match no
    grant and silently read every licensed program as unencumbered (review R1v2 B1)."""
    code = value.strip().upper()
    if code not in REGIONS:
        raise ValueError(f"unknown territory code {value!r}; use one of {sorted(REGIONS)} (for example US, not USA)")
    return code


TIER_ORDER = {
    "AVAILABILITY_STATED_UNVERIFIED": 0,
    "NO_THIRD_PARTY_GRANT_IN_EVIDENCE": 1,
    "RIGHTS_UNRESOLVED": 2,
    "DEPRIORITIZED": 3,
    "EXCLUDED_BY_BUYER_PREFERENCE": 4,
}
#: The tiers in words, for prose. The codes stay in the JSON and the workbook.
TIER_WORDS = {
    "AVAILABILITY_STATED_UNVERIFIED": "availability stated, unverified",
    "NO_THIRD_PARTY_GRANT_IN_EVIDENCE": "no third-party grant in evidence",
    "RIGHTS_UNRESOLVED": "rights unresolved",
    "DEPRIORITIZED": "deprioritized by buyer preference",
    "EXCLUDED_BY_BUYER_PREFERENCE": "excluded by buyer preference",
    "NOT_DECLARED": "no transaction preferences declared",
}
#: The note added when evidence is stale (the position's reasons and questions already say so).
STALE_NOTE = "rights evidence is stale; confirm it is current"
_NO_THIRD_PARTY = frozenset({rp.P_RETURNED, rp.P_NOT_ENCUMBERED, rp.P_OWNER_ACQUIRED})


@dataclass
class TransactionView:
    tier: str
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    position: str = rp.P_NONE
    holder: str | None = None
    owner: str | None = None
    questions: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    stale: bool = False
    sort_bonus: int = 0
    #: Why a clear position stays out of the two top tiers ("check: detail"); see ``rights_position``.
    top_tier_blockers: list[str] = field(default_factory=list)
    #: Why the rights position is what it is, without the buyer-preference and tier reasons ``reasons`` adds.
    position_reasons: list[str] = field(default_factory=list)
    #: Rights rows not applied that may concern this program (rejected, or an unattached id close to its own). They
    #: keep a clear position out of the top tiers; recorded whether or not preferences are declared.
    guards: list[str] = field(default_factory=list)


_FROM_FIELD = {  # the landscape's free-text U.S.-rights field, when no rights record covers the program
    ENCUMBERED: rp.P_LICENSED, OPTION: rp.P_OPTION, RETURNED: rp.P_RETURNED,
    AVAILABLE_CONFIRMED: rp.P_AVAILABILITY, CONFLICTING: rp.P_CONFLICTING, NOT_AVAILABLE: rp.P_NOT_AVAILABLE,
}


def _dated_within(basis: list[dict[str, Any]] | None, as_of: date | None, max_age_days: int) -> bool:
    """A statement's own source date is within the age limit and not after the as-of date (review R1v4 A3c). With no
    as-of date it is at least dated."""
    dates = [date.fromisoformat(str(c["source_date"])) for c in basis or [] if c.get("source_date")]
    return any(as_of is None or 0 <= (as_of - d).days <= max_age_days for d in dates)


def _why_not_dated(basis: list[dict[str, Any]] | None, as_of: date | None, max_age_days: int) -> str:
    """Which dating rule a statement fails, in words (``_dated_within``)."""
    dates = sorted(date.fromisoformat(str(c["source_date"])) for c in basis or [] if c.get("source_date"))
    if not dates:
        return "has no source date"
    if as_of is not None and dates[0] > as_of:
        return f"is dated {dates[0]}, after the as-of date {as_of}"
    return f"is dated {dates[-1]}, more than {max_age_days} days before {as_of}"


def _values(basis: list[dict[str, Any]] | None) -> str:
    return "; ".join(f"'{' '.join(str(c.get('value') or '').split())}'" for c in basis or [] if c.get("value"))


def position_from_field(rights_status: str, holder: str | None, first_contact: str | None = None, *,
                        basis: list[dict[str, Any]] | None = None, as_of: date | None = None,
                        max_age_days: int = 730, holder_basis: list[dict[str, Any]] | None = None
                        ) -> rp.RightsPosition:
    """The landscape's own rights columns, used only when no rights record covers the program.

    A vendor cell saying "available" is unverified (a row's date is when the vendor recorded it, not when the owner
    said it), so it is not counted as availability (the same rule as for rights records, review R1v2 F1). An
    analyst-confirmed or -asserted statement counts only when its source is dated within the buyer's age limit and
    not after the as-of date, and is cited (review R1v3 F1-analyst, R1v4 A3c). A field reading "returned" names no
    parties or territory, so it never reaches the top tiers. ``basis`` is the claims the status was read from
    (``CommercialAssessment.us_rights_basis``); ``holder_basis`` the claims naming the holder. A clear position
    carries no holder here: the top-tier gate (``rights_gate``) compares each named holder with the program's
    company (review R1v4 A3a)."""
    position = _FROM_FIELD.get(rights_status, rp.P_NONE)
    words = RIGHTS_STATUS_WORDS.get(rights_status, rights_status)
    written = _values(basis)
    if rights_status == AVAILABLE:
        pos = rp.no_evidence_position(first_contact)
        pos.reasons.append(f"the landscape U.S.-rights field reads {written or 'available'} (availability); a vendor "
                           "field is unverified, so it is not counted")
        pos.questions.append("When, and by whom, was availability stated? Confirm with a dated source (an analyst can "
                             "assert it with a citation).")
    elif rights_status == AVAILABLE_CONFIRMED and not _dated_within(basis, as_of, max_age_days):
        pos = rp.no_evidence_position(first_contact)
        pos.reasons.append(f"an analyst statement of availability ({written}) "
                           f"{_why_not_dated(basis, as_of, max_age_days)}, so it is not counted")
        pos.questions.append("Is availability still stated? Cite a source dated within the buyer's age limit.")
    elif position == rp.P_NONE:
        pos = rp.no_evidence_position(first_contact)
        if written:  # review R1v4 O-6: say what the cell holds, not only how it was read
            pos.reasons.append(f"the U.S.-rights field reads {written}; DealScreen does not read it as a statement "
                               "that rights are available, licensed or returned")
    else:
        pos = rp.RightsPosition(position, reasons=[(f"the U.S.-rights field reads {written or words} ({words}; no "
                                                   "rights record)")],
                                questions=["Confirm the U.S.-rights statement against a primary source."])
        if position == rp.P_RETURNED:
            pos.top_tier_blockers.append("specific: the U.S.-rights field says rights were returned but names no "
                                         "parties, territory or date")
        if position in rp.CLEAR_POSITIONS and as_of is None:
            pos.top_tier_blockers.append("current: no as-of date, so the age of the evidence cannot be judged")
    pos.evidence = field_evidence(basis)
    pos.event_ids = [str(e["event_id"]) for e in pos.evidence]
    if holder:
        source = field_source(holder_basis or [])
        if pos.position not in rp.CLEAR_POSITIONS:
            pos.holder, pos.holders = holder, [holder]
        pos.reasons.append(f"{source} names a U.S. rights holder or labeler: {holder} (a holder or labeler is not "
                           "shown to own the program, and neither says whether rights are available)")
        pos.evidence += field_evidence(holder_basis, "U.S. rights holder")
    return pos


def _blocker_question(blockers: list[str]) -> str:
    """One question naming the failed checks and the first thing missing."""
    checks = list(dict.fromkeys(b.split(":", 1)[0] for b in blockers))
    first = blockers[0].split(": ", 1)[-1]
    more = f" (and {len(blockers) - 1} more; see the reasons)" if len(blockers) > 1 else ""
    return f"What record would make this rights evidence {' and '.join(checks)}? Not yet: {first}{more}."


def _holder_hit(prefs: TransactionPreferences, pos: rp.RightsPosition, company: str | None) -> str | None:
    names = [n for n in [*pos.holders, pos.owner] if n]
    for declared in prefs.deprioritized_holders:
        for name in names:
            if name_matches(declared, name):
                return f"rights holder or owner per evidence '{name}' matches declared '{declared}'"
    for declared in prefs.deprioritized_holders:
        if name_matches(declared, company):
            return f"registry sponsor / labeler '{company}' matches declared '{declared}' (not a rights statement; verify)"
    return None


def _preference_reasons(prefs: TransactionPreferences, pos: rp.RightsPosition, market_status: str | None,
                        company: str | None) -> tuple[list[str], list[str]]:
    excluded: list[str] = []
    deprioritized: list[str] = []

    def apply(treatment: str, reasons: list[str]) -> None:
        if treatment != "ignore":
            (excluded if treatment == "exclude" else deprioritized).extend(reasons)

    if market_status == "US_MARKETED":
        apply(prefs.marketed, ["marketed in the U.S. per source"])
    if hit := _holder_hit(prefs, pos, company):
        deprioritized.append(hit)
    if pos.position in rp.ENCUMBRANCE_POSITIONS:
        apply(prefs.encumbered_rights, pos.reasons)
    if pos.position in rp.SHARED_POSITIONS:
        apply(prefs.shared_rights, pos.reasons)
    return excluded, deprioritized


def assess_transaction(
    prefs: TransactionPreferences | None,
    *,
    market_status: str | None,
    rights_status: str,
    rights_holder: str | None,
    company: str | None,
    identity_twins: list[str],
    position: rp.RightsPosition | None = None,
    guard: list[str] | None = None,
) -> TransactionView:
    """``guard``: reasons the rights evidence is incomplete (a rejected rights row, for example). A guarded
    program never reaches the two top tiers."""
    notes = [f"may be the same molecule as {', '.join(identity_twins)} (identity flag; check its resolution)"] if identity_twins else []
    pos = position or position_from_field(rights_status, rights_holder, company)
    if pos.position == rp.P_RETURNED:  # names the recipient only, never "the originator" (review R1v3)
        notes.append(f"rights returned per source{' to ' + pos.holder if pos.holder else ''} (not a statement of "
                     "availability)")
    if pos.stale:
        notes.append(STALE_NOTE)
    blockers = list(pos.top_tier_blockers) if pos.position in rp.CLEAR_POSITIONS else []
    base: dict[str, Any] = {"position": pos.position, "holder": pos.holder, "owner": pos.owner,
                            "questions": list(pos.questions), "evidence": list(pos.evidence), "stale": pos.stale,
                            "top_tier_blockers": blockers, "position_reasons": list(pos.reasons),
                            "guards": list(guard or [])}
    if prefs is None:
        return TransactionView("NOT_DECLARED", [], notes, **base)
    excluded, deprioritized = _preference_reasons(prefs, pos, market_status, company)
    rest = [x for x in pos.reasons if x not in excluded + deprioritized]
    if excluded:
        return TransactionView("EXCLUDED_BY_BUYER_PREFERENCE", excluded + deprioritized + rest, notes, **base)
    if deprioritized:
        return TransactionView("DEPRIORITIZED", deprioritized + rest, notes, **base)
    if pos.position in rp.CLEAR_POSITIONS and (guard or pos.stale or blockers):
        why = [*(guard or []), *pos.reasons]
        if pos.stale:
            why.append("stale evidence does not show the current position, so it is not counted for the top tiers")
        if blockers:
            why.append("not counted for the top tiers: " + "; ".join(blockers))
            base["questions"] = [*base["questions"], _blocker_question(blockers)]
        return TransactionView("RIGHTS_UNRESOLVED", [*why, "availability not evidenced"], notes, **base)
    if pos.position == rp.P_AVAILABILITY:
        return TransactionView("AVAILABILITY_STATED_UNVERIFIED", list(pos.reasons), notes, **base)
    tier = "NO_THIRD_PARTY_GRANT_IN_EVIDENCE" if pos.position in _NO_THIRD_PARTY else "RIGHTS_UNRESOLVED"
    bonus = 1 if (pos.position == rp.P_RETURNED and prefs.returned_rights == "prefer") else 0
    return TransactionView(tier, [*pos.reasons, "availability not evidenced"], notes, sort_bonus=bonus, **base)


def transaction_ranks(screens: list[dict[str, Any]]) -> dict[str, int]:
    """Rank ELIGIBLE programs by tier, then buyer-declared bonus, then scientific rank."""
    eligible = [s for s in screens if s["disposition"] == "ELIGIBLE" and s.get("transaction", {}).get("tier")
                and s["transaction"]["tier"] != "NOT_DECLARED"]
    ordered = sorted(eligible, key=lambda s: (TIER_ORDER.get(s["transaction"]["tier"], 9),
                                              -s["transaction"].get("sort_bonus", 0), s["rank"] or 10**6))
    return {s["asset_id"]: i + 1 for i, s in enumerate(ordered)}


def holder_ambiguities(prefs: TransactionPreferences | None, names: list[str]) -> dict[str, list[str]]:
    """Declared counterparties that match parties distinguished by the word after the declared name, e.g.
    a declared "Acme" matching both "Acme KGaA" and "Acme Sharp & Dohme". Subsidiary names ("Example
    Pharma US", "Example Pharma Global Development") are not flagged."""
    out: dict[str, list[str]] = {}
    for declared in (prefs.deprioritized_holders if prefs else []):
        key = party_key(declared)
        distinguishing: dict[str, str] = {}
        for name in names:
            if not (name and name_matches(declared, name)):
                continue
            after = party_key(name).split(key, 1)[-1].split()
            word = after[0] if after else ""
            if word and word not in GENERIC_NAME_WORDS:  # one list for every name comparison
                distinguishing.setdefault(word, name)
        if len(distinguishing) > 1:
            out[declared] = sorted(distinguishing.values())
    return out


__all__ = ["STALE_NOTE", "TIER_ORDER", "TIER_WORDS", "TransactionPreferences", "TransactionView", "assess_transaction",
           "field_evidence", "holder_ambiguities", "position_from_field", "region_code", "transaction_ranks"]
