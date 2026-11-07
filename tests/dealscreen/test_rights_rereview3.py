"""Cycle R1 revision 5: the inputs from adversarial re-review 3 (research/dealscreen_rights_v1/REREVIEW3.md).

Revision 5 makes the top-tier gate fail closed on every path (REREVIEW3 section 13): ended grants are checked beside an
availability statement, the party a clear position rests on must be the landscape company, every landscape and
analyst U.S.-rights statement and holder is read, and rights rows that were not applied guard the programs they may
concern. Each test is tagged with its review id.

Per-program cases run through ``screening.program_transaction``, the function screening calls for each program.
Defaults as in the review: buyer territory US, as-of 2025-06-01, maximum evidence age 730 days, encumbered rights
deprioritized, landscape company and licensor "Origin Bio" unless stated. Parties are fictional; the tests assert no
real-world facts."""

from __future__ import annotations

import csv
import itertools
import shutil
from datetime import date

import pytest
import yaml

from bve.dealscreen import rights as r
from bve.dealscreen import rights_position as rp
from bve.dealscreen.commercial import AVAILABLE, ENCUMBERED, NOT_AVAILABLE, assess
from bve.dealscreen.models import ClaimOrigin, LandscapeAsset, SourceClaim
from bve.dealscreen.rights_reader import rights_reading
from bve.dealscreen.rights_territory import parse_territory
from bve.dealscreen.rights_words import FIELD_STATEMENT
from bve.dealscreen.screening import program_transaction
from bve.dealscreen.transaction import TransactionPreferences, TransactionView

US = frozenset({"US"})
AS_OF = date(2025, 6, 1)
PREFS = TransactionPreferences(encumbered_rights="deprioritize")
TOP = frozenset({"AVAILABILITY_STATED_UNVERIFIED", "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"})
TIER0, TIER1, UNRESOLVED = "AVAILABILITY_STATED_UNVERIFIED", "NO_THIRD_PARTY_GRANT_IN_EVIDENCE", "RIGHTS_UNRESOLVED"
L, O, T, RR = r.LICENSE, r.OPTION, r.TERMINATION, r.RIGHTS_RETURNED
AV, AQ, OX, OL, CD = r.AVAILABILITY_STATED, r.ACQUISITION, r.OPTION_EXERCISED, r.OPTION_LAPSED, r.CO_DEVELOPMENT
_N = itertools.count(1)


def ev(kind: str, *, grantee: str | None = None, grantor: str | None = "Origin Bio", territory: str | None = None,
       d: str | None = "2025-01-01", status: str = "UNKNOWN", deal: str | None = None, related: str | None = None,
       src: str | None = None) -> r.RightsEvent:
    """``d`` / ``src`` as written: "2024" is a year, "2024-05" a month, "2024-05-02" a day; None = absent."""
    n = next(_N)
    regions = parse_territory(territory)
    when, precision = r.parse_date(d) if d else (None, "day")
    source, source_precision = r.parse_date(src) if src else (None, "day")
    return r.RightsEvent(
        event_id=f"rx:t:{n}", deal_id=deal or f"D{n}", external_id="P1", event_type=kind, exclusivity="EXCLUSIVE",
        grantee=grantee, grantor=grantor, territory_as_written=territory,
        territory=sorted(regions) if regions is not None else None, event_date=when, event_date_precision=precision,
        status=status, related_deal_id=related, source_system="TEST", dataset_version="TEST:x", row_number=n,
        source_reference=f"https://example.test/{n}", evidence_quote=None, source_date=source,
        source_date_precision=source_precision)


def cell(field: str, value: str, src: str | None = None) -> SourceClaim:
    """A landscape cell."""
    n = next(_N)
    return SourceClaim(claim_id=f"c{n}", asset_id="A1", field=field, value_as_written=value,
                       origin=ClaimOrigin.SOURCE_PROVIDED, source_system="T", dataset_version="T", row_number=1,
                       column=field, source_reference=f"https://example.test/c{n}",
                       source_date=date.fromisoformat(src) if src else None, evidence_span=f"span {n}")


def analyst(field: str, value: str, src: str | None = "2025-03-01") -> SourceClaim:
    """An analyst assertion with a citation (screening passes these as confirmed findings)."""
    n = next(_N)
    return SourceClaim(claim_id=f"a{n}", asset_id="A1", field=field, value_as_written=value,
                       origin=ClaimOrigin.ANALYST_ASSERTED, source_system="analyst:x", dataset_version="T",
                       row_number=None, column=field, source_reference=f"https://example.test/a{n}",
                       source_date=date.fromisoformat(src) if src else None, evidence_span=f"span {n}")


#: The program's own landscape words, as screening passes them (cycle R1 revision 11): a quote may name its disease.
PROGRAM_TEXT = ("NB-7", "gastric cancer")


def run(events: list[r.RightsEvent], *, company: str = "Origin Bio", landscape: tuple[SourceClaim, ...] = (),
        analysts: tuple[SourceClaim, ...] = (), territory: frozenset[str] = US,
        guard: list[str] | None = None, program_text: tuple[str, ...] = PROGRAM_TEXT) -> TransactionView:
    asset = LandscapeAsset(asset_id="A1", source_system="T", external_id="P1", program_name="Prog", company=company,
                           row_numbers=[1], claims=list(landscape))
    commercial = assess(asset, questions=["Q?"], confirmed_findings=analysts)
    # revision 12: the program's own names are masked as the program; the rest of its text may describe it
    names = [t for t in program_text if any(c.isdigit() for c in t)]
    return program_transaction(events, commercial, company=company, territory=territory, as_of=AS_OF,
                               max_age_days=730, prefs=PREFS, guard=guard, program_names=["Prog", *names],
                               program_text=[t for t in program_text if t not in names])


def blocked(v: TransactionView, words: str) -> bool:
    return any(words in b for b in v.top_tier_blockers)


def cites(v: TransactionView, value: str) -> bool:
    return any(e.get("type") == FIELD_STATEMENT and e.get("value") == value for e in v.evidence)


US_LICENSE = {"grantee": "Alpha Bio", "territory": "United States", "d": "2024-03-01"}
CHINA = {"grantee": "ChinaCo", "territory": "mainland China", "d": "2025-01-01"}
STATED = {"territory": "United States", "d": "2025-03-01"}


# -- A1: an ended grant is checked beside an availability statement (section 13, rule 1) ---------------------------
@pytest.mark.parametrize(("events", "words"), [
    ([ev(L, **US_LICENSE), ev(T, d="2025-01-01"), ev(AV, **STATED)],
     "names only the licensor and is not linked to its deal by id"),  # A1a
    ([ev(L, **US_LICENSE), ev(T, grantee="Alpha Bio", d=None), ev(AV, **STATED)],
     "has no date of its own, so it cannot be ordered against the availability statement"),  # A1b
    ([ev(L, grantee="Alpha Bio", territory="United States", d=None), ev(T, grantee="Alpha Bio"), ev(AV, **STATED)],
     "has no date, so its ending cannot be ordered against it"),  # A1c
    ([ev(L, territory="United States", d="2024-03-01"), ev(T, d="2025-01-01"), ev(AV, **STATED)],
     "names no licensee"),  # A1e
], ids=["A1a", "A1b", "A1c", "A1e"])
def test_a1_an_ended_grant_beside_an_availability_statement_passes_the_returned_path_checks(events, words):
    v = run(events)
    assert v.position == rp.P_AVAILABILITY and v.tier == UNRESOLVED
    assert blocked(v, words), v.top_tier_blockers
    assert len(v.evidence) == len(events)  # the grant and its ending are cited beside the statement


def test_a1d_an_undated_acquisition_never_merges_a_license_into_the_company():
    """Revision 6 (review R1v5 O1): an undated acquisition is not applied, so Alpha Bio's U.S. license stays in force
    beside the statement: a conflict, held out of the top tiers, with the acquisition named."""
    v = run([ev(L, **US_LICENSE), ev(AQ, grantee="Origin Bio", grantor="Alpha Bio", d=None), ev(AV, **STATED)])
    assert v.position == rp.P_CONFLICTING and v.tier == UNRESOLVED


# -- A2: the party a statement comes from must be the landscape company (rule 2) ----------------------------------
@pytest.mark.parametrize(("events", "party"), [
    ([ev(AV, grantor="BigPharma Inc", **STATED)], "BigPharma Inc"),  # A2a
    ([ev(L, **CHINA), ev(AV, grantor="BigPharma Inc", **STATED)], "BigPharma Inc"),  # A2b
    ([ev(AV, grantee="Kappa Pharma", grantor=None, **STATED)], "Kappa Pharma"),  # A2c
], ids=["A2a", "A2b", "A2c"])
def test_a2_a_statement_by_a_party_other_than_the_company_is_not_shown_as_the_companys(events, party):
    v = run(events)
    assert v.tier == UNRESOLVED and v.holder is None
    assert blocked(v, f"an availability statement (2025-03-01) is made by {party}, but the landscape names Origin Bio")
    assert f"Does {party} own this program, or hold it under a license from Origin Bio?" in v.questions
    assert f"stated by {party}, which the landscape does not name as the program's company" in v.position_reasons


# -- A3 and T: every analyst and landscape statement and holder is read (rule 3) ----------------------------------
def test_a3a_an_analyst_holder_contests_an_analyst_availability_statement():
    v = run([], analysts=(analyst("us_rights", "Available"), analyst("us_rights_holder", "BigPharma Inc.")))
    assert v.position == rp.P_CONFLICTING and v.tier == UNRESOLVED
    assert any("Does BigPharma Inc. hold U.S. rights" in q for q in v.questions)
    assert sum(e.get("value") == "BigPharma Inc." for e in v.evidence) == 1  # cited once
    assert not any("labeler: BigPharma Inc." in x for x in v.position_reasons)  # the contest replaces the plain line


def test_a3b_conflicting_landscape_holders_are_read_on_the_field_path():
    v = run([], analysts=(analyst("us_rights", "Seeking a partner for U.S. rights"),),
            landscape=(cell("us_rights_holder", "Origin Bio"), cell("us_rights_holder", "BigPharma Inc.")))
    assert v.position == rp.P_CONFLICTING and v.tier == UNRESOLVED
    assert any("no rights record shows a grant to BigPharma Inc." in x for x in v.position_reasons)


def test_a3c_an_analyst_statement_dated_after_the_as_of_date_is_not_counted():
    v = run([], analysts=(analyst("us_rights", "Available", src="2026-01-01"),))
    assert v.position == rp.P_NONE and v.tier == UNRESOLVED
    assert any("is dated 2026-01-01, after the as-of date 2025-06-01, so it is not counted" in x
               for x in v.position_reasons)


@pytest.mark.parametrize(("landscape", "analysts"), [
    ((cell("us_rights", "Not available", src="2025-05-01"),), (analyst("us_rights", "Available", src="2024-01-01"),)),
    ((), (analyst("us_rights", "Not available", src="2025-05-01"), analyst("us_rights", "Available", src="2024-01-01"))),
], ids=["A3d", "A3e"])
def test_a3d_a3e_a_contrary_statement_is_cited_and_both_are_named_in_the_question(landscape, analysts):
    v = run([], landscape=landscape, analysts=analysts)
    assert v.position == rp.P_CONFLICTING and v.tier == UNRESOLVED
    assert cites(v, "Not available") and cites(v, "Available")
    assert any("('Not available') or an analyst assertion's statement ('Available')? Reject the one that is wrong."
               in q for q in v.questions)


@pytest.mark.parametrize("text", [
    "Available in Latin America", "No U.S. rights available", "May be available",
    "Available upon expiry of the BigPharma Inc. license in 2028",
    "BigPharma Inc. holds U.S. rights; available in Europe", "Available?", "Available - no"])
def test_t_an_analyst_statement_that_does_not_offer_us_rights_never_reaches_tier_0(text):
    v = run([], analysts=(analyst("us_rights", text),))
    assert v.tier not in TOP and cites(v, text)


def test_t_the_assert_command_says_how_it_read_the_statement():
    from bve.cli.dealscreen import rights_reading_note

    assert rights_reading_note("No U.S. rights available") == "DealScreen reads it as: not available."
    assert "cannot read all of it" in rights_reading_note("Available in Latin America")
    note = rights_reading_note("Acme Bio is seeking a partner for U.S. rights")
    assert "made by Acme Bio." in note and "not one of the plain forms" in note
    # Revision 7 (review R1v6 L3b): the note names the buyer territory the gate reads against.
    assert "accepts it as a plain form for the buyer territory (US): an offer" in rights_reading_note("Acme Bio is seeking a partner for U.S. "
                                                                          "rights", "Acme Bio")


def test_a7a_a_statement_covering_part_of_the_buyer_territory_is_blocked():
    v = run([ev(AV, **STATED)], territory=frozenset({"US", "CA"}))
    assert v.tier == UNRESOLVED and blocked(v, "covers only part of CA/US (United States)")


@pytest.mark.parametrize("text", [
    "U.S. rights held by BigPharma Inc.", "Sublicensed to BigPharma Inc. (U.S.)", "Acquired by BigPharma Inc.",
    "BigPharma Inc. has U.S. commercialization rights", "U.S. rights sold to BigPharma Inc.",
    "Collaboration with BigPharma Inc. covering the U.S.", "BigPharma Inc. (U.S. rights)", "U.S. rights: BigPharma Inc.",
    "Assigned to BigPharma Inc. in 2024"])
def test_a4_a_landscape_cell_naming_a_third_party_keeps_a_china_license_out_of_tier_1_and_is_cited(text):
    v = run([ev(L, **CHINA)], landscape=(cell("us_rights", text, src="2025-04-01"),))
    assert v.tier == UNRESOLVED and cites(v, text)
    assert v.position == rp.P_CONFLICTING or blocked(v, "cannot read as a rights statement")


@pytest.mark.parametrize(("events", "holder", "note"), [
    ([ev(L, **CHINA)], "Origin Bio (U.S. rights licensed to BigPharma Inc.)", "U.S. rights licensed to BigPharma Inc."),
    ([ev(L, grantee="Alpha Bio", territory="United States", d="2023-06-01"), ev(T, grantee="Alpha Bio", d="2025-02-01")],
     "Origin Bio (partnered with BigPharma Inc. in the U.S.)", "partnered with BigPharma Inc. in the U.S."),
], ids=["A5a", "A5b"])
def test_a5_a_note_beside_the_company_name_is_content_and_blocks(events, holder, note):
    v = run(events, landscape=(cell("us_rights_holder", holder),))
    assert v.tier == UNRESOLVED and blocked(v, f"the note '{note}' is not read, and it may name a third party")
    assert any(f"Does the note '{note}' that the landscape writes beside Origin Bio mean" in q for q in v.questions)


@pytest.mark.parametrize(("events", "company", "owner"), [
    ([ev(L, grantee="ChinaCo", grantor="Kappa Pharma", territory="mainland China", d="2025-01-01")], "Origin Bio",
     "Kappa Pharma"),  # H2
    ([ev(L, **US_LICENSE), ev(RR, grantee="Alpha Bio", d="2025-02-01")], "Kappa Pharma", "Origin Bio"),  # H1
], ids=["H2", "H1"])
def test_h1_h2_a_licensor_other_than_the_landscape_company_is_asked_about_not_assumed_owner(events, company, owner):
    v = run(events, company=company)
    assert v.tier == UNRESOLVED
    assert blocked(v, f"the owner per the rights evidence is {owner}, but the landscape names {company}")
    assert f"Does {owner} own this program, or hold it under a license from {company}?" in v.questions


@pytest.mark.parametrize("source", ["analyst", "landscape"])
def test_t2_no_us_rights_available_beside_a_china_license_is_a_cited_conflict(source):
    text = "No U.S. rights available"
    claims = {"analysts": (analyst("us_rights", text),)} if source == "analyst" else {
        "landscape": (cell("us_rights", text, src="2025-04-01"),)}
    v = run([ev(L, **CHINA)], **claims)
    assert v.position == rp.P_CONFLICTING and v.tier == UNRESOLVED and cites(v, text)


def test_a6_an_undated_analyst_holder_does_not_hide_a_landscape_holder():
    v = run([ev(L, **CHINA)], landscape=(cell("us_rights_holder", "BigPharma Inc."),),
            analysts=(analyst("us_rights_holder", "Origin Bio", src=None),))
    assert v.position == rp.P_CONFLICTING and v.tier == UNRESOLVED
    assert v.holder is not None and "BigPharma Inc." in v.holder


def test_o12_the_successor_question_never_names_one_party_twice():
    v = run([ev(L, **CHINA), ev(T, grantee="BigPharma Inc", territory="United States", d="2025-03-01"),
             ev(OX, grantee="BigPharma Inc", territory="United States", d="2025-04-01")])
    assert v.position == rp.P_CONFLICTING and v.questions
    assert not any("Is BigPharma Inc the successor of BigPharma Inc" in q for q in v.questions)


# -- FE and over-caution: wording that offers rights, and old or other-territory grants --------------------------
def test_g12_a_cell_that_agrees_with_the_rights_file_is_not_a_conflict():
    v = run([ev(L, **CHINA)],
            landscape=(cell("us_rights", "Exclusive China license to ChinaCo; U.S. rights retained", "2025-04-01"),))
    assert v.position == rp.P_NOT_ENCUMBERED and v.tier == TIER1


def test_g13_an_owner_seeking_a_co_development_partner_is_availability_not_encumbrance():
    v = run([], analysts=(analyst("us_rights", "Seeking a co-development partner for U.S. rights"),))
    assert v.position == rp.P_AVAILABILITY and v.tier == TIER0


@pytest.mark.parametrize("text", ["Licensed in China only", "Available for exclusive licensing",
                                  "Seeking a co-development partner"])
def test_fe_a_landscape_cell_offering_rights_or_naming_another_place_is_not_a_us_license(text):
    v = run([], landscape=(cell("us_rights", text, src="2025-04-01"),))
    assert v.position != rp.P_LICENSED and v.tier != "DEPRIORITIZED"


@pytest.mark.parametrize(("events", "landscape"), [
    ([ev(L, grantee="Alpha Bio", territory="United States", d="2021-05-01", status="TERMINATED", src="2025-02-01"),
      ev(RR, grantee="Alpha Bio", d="2025-02-01")], ()),  # G5b: a dated return is not discarded as a repeat
    ([ev(L, **CHINA), ev(L, grantee="JapanCo", territory="Japan", d="2012-01-01")], ()),  # G6: an old Japan deal
    ([ev(CD, grantee="Alpha Bio", territory="worldwide", d="2023-01-01"), ev(T, grantee="Alpha Bio", d="2025-02-01")],
     ()),  # G8: co-development ended by both; the company was a partner
    ([ev(RR, grantee="Delta Bio", grantor="Origin Bio U.S., Inc.", territory="United States", d="2025-02-01")],
     ()),  # G10: the company's U.S. affiliate
    ([ev(L, grantee="Alpha Bio", territory="United States", d="2023-06-01"), ev(T, grantee="Alpha Bio", d="2025-02-01")],
     (cell("us_rights_holder", "Origin Bio U.S., Inc."),)),  # G11
], ids=["G5b", "G6", "G8", "G10", "G11"])
def test_over_caution_cases_from_the_review_now_reach_tier_1(events, landscape):
    v = run(events, landscape=landscape)
    assert v.tier == TIER1 and not v.stale, (v.top_tier_blockers, v.position_reasons)


# -- Clean cases stay in the top tiers -------------------------------------------------------------------------
@pytest.mark.parametrize(("events", "company", "tier"), [
    ([ev(L, grantee="Alpha Bio", territory="United States", d="2023-06-01", deal="G1"),
      ev(T, grantee="Alpha Bio", d="2025-02-01")], "Origin Bio", TIER1),  # G1
    ([ev(L, grantee="Alpha Bio", territory="United States", d="2023-06-01", deal="G1b"),
      ev(T, d="2025-02-01", related="G1b")], "Origin Bio", TIER1),  # G1b
    ([ev(AV, **STATED)], "Origin Bio", TIER0),  # G2
    ([ev(L, **CHINA)], "Origin Bio", TIER1),  # G3
    ([ev(RR, grantee="Delta Bio", territory="United States", d="2024-09-01"), ev(AV, **STATED)], "Origin Bio",
     TIER0),  # G4
    ([ev(O, grantee="Alpha Bio", territory="United States", d="2023-06-01"), ev(OL, grantee="Alpha Bio", d="2025-02-01")],
     "Origin Bio", TIER1),  # G7
    ([ev(L, grantee="ChinaCo", territory="Greater China", d="2025-01-01"),
      ev(AV, territory="worldwide excluding Greater China", d="2025-03-01")], "Origin Bio", TIER0),  # G9
    ([ev(L, grantee="Alpha Bio", territory="United States", d="2023-06-01"), ev(T, grantee="Alpha Bio", d="2025-02-01"),
      ev(RR, grantee="Alpha Bio", d="2025-02-03")], "Origin Bio", TIER1),  # G14
    ([ev(L, grantee="Alpha Bio", territory="United States", d="2023-06-01"),
      ev(T, grantee="Alpha Bio Ltd", grantor="Origin Bio Inc.", d="2025-02-01")], "Origin Bio", TIER1),  # G15
    ([ev(RR, grantee="Delta Bio", territory="worldwide", d="2025-02-01")], "Origin Bio Co., Ltd.", TIER1),  # G16
    ([ev(L, grantee="Alpha Bio", territory="United States", d="2020-01-01"), ev(T, grantee="Alpha Bio", d="2025-03-01")],
     "Origin Bio", TIER1),  # G18
    ([ev(L, grantee="Alpha Bio", territory="United States", d="2020-01-01", deal="G18b"),
      ev(T, grantee="Alpha Bio", d="2025-03-01", related="G18b")], "Origin Bio", TIER1),  # G18b
    ([ev(L, grantee="Alpha Bio", territory="United States", d="2020-01-01"), ev(T, grantee="Alpha Bio", d="2025-03-01"),
      ev(AV, territory="United States", d="2025-04-01")], "Origin Bio", TIER0),  # G18c
    ([ev(RR, grantee="BigCo", territory="worldwide", d="2024-08-01")], "Origin Bio", TIER1),  # K1
    ([ev(RR, grantee="BigCo", territory="worldwide", d="2024-08-01"), ev(AV, territory="worldwide", d="2025-02-01")],
     "Origin Bio", TIER0),  # K3
], ids=["G1", "G1b", "G2", "G3", "G4", "G7", "G9", "G14", "G15", "G16", "G18", "G18b", "G18c", "K1", "K3"])
def test_clean_cases_stay_in_the_top_tiers(events, company, tier):
    v = run(events, company=company)
    assert v.tier == tier and not v.top_tier_blockers, (v.top_tier_blockers, v.position_reasons)


def test_judgements_kept_an_unknown_termination_date_and_a_near_namesake_company_are_held_with_a_question():
    """G5: a status flag on a 2021 deal says it ended, not when, so the evidence is stale. G17: "Origin Bio" and
    "Origin Biosciences" may be one company or two; names alone cannot tell, so the program is held and asked about
    (a usefulness cost of the revision-5 owner check, recorded in REREVIEW3_RESPONSE.md)."""
    g5 = run([ev(L, grantee="Alpha Bio", territory="United States", d="2021-05-01", status="TERMINATED",
                 src="2025-02-01")])
    assert g5.tier == UNRESOLVED and g5.stale
    g17 = run([ev(L, grantee="Alpha Bio", territory="United States", d="2023-06-01"),
               ev(T, grantee="Alpha Bio", d="2025-02-01")], company="Origin Biosciences")
    assert g17.tier == UNRESOLVED
    assert "Does Origin Bio own this program, or hold it under a license from Origin Biosciences?" in g17.questions


def test_a_guard_from_a_row_not_applied_is_recorded_whatever_the_position():
    guard = [("rights row 9 names program id 'P-01', close to this program's id; it was not attached and may concern "
             "this program")]
    clear = run([ev(L, **CHINA)], guard=guard)
    licensed = run([ev(L, **US_LICENSE)], guard=guard)
    assert clear.tier == UNRESOLVED and clear.guards == guard
    assert licensed.guards == guard  # kept on the record even where the tier is already lower


# -- The reader on the review's phrasings (section 3) ------------------------------------------------------------
@pytest.mark.parametrize("text", [
    # other places, rest of world, hedges, encumbered wording, third parties, controls
    "Available in Latin America", "Rights available in South America", "Available in Asia", "Available in Asia-Pacific",
    "Available in Australia", "Available in Germany", "Available in Brazil and Mexico", "Available in the Middle East",
    "Available in emerging markets", "Seeking a partner for India", "Available in rest of world", "Available for ROW",
    "May be available", "Possibly available", "Could become available in 2027", "Expected to become available",
    "Available from 2027", "Available after 2027", "Available?", "Available? TBD",
    "Available subject to BigPharma Inc.'s right of first negotiation",
    "Available upon expiry of the BigPharma Inc. license in 2028", "BigPharma Inc. holds U.S. rights; available in Europe",
    "U.S. rights held by BigPharma Inc.; rest of world available",
    "Sublicensable rights available from BigPharma Inc. (U.S. licensee)", "U.S. rights held by BigPharma Inc.",
    "Sublicensed to BigPharma Inc.", "Acquired by BigPharma Inc.", "BigPharma Inc. has U.S. commercialization rights",
    "Assigned to BigPharma Inc.", "Available in China", "Available ex-U.S.", "Available, but not in the U.S.",
    "China rights available", "Previously available", "Will be available after the option period ends",
    "Available if BigPharma Inc. declines its option"])
def test_reader_never_reads_these_as_us_availability(text):
    assert rights_reading(text).status != AVAILABLE


@pytest.mark.parametrize("text", [
    "No U.S. rights available", "None available", "Nothing available for licensing", "Available - no", "Available = No",
    "Available? Not anymore", "Available: not at this time", "Available: N", "Available (no)", "Rights: none available",
    "Available for licensing: no", "Available? No.", "Not available"])
def test_reader_reads_negations_as_not_available(text):
    assert rights_reading(text).status == NOT_AVAILABLE


@pytest.mark.parametrize(("text", "available"), [
    ("Seeking a co-development partner", True), ("Available for exclusive licensing", True),
    ("Open to co-promotion partnerships in the U.S.", True), ("Not encumbered", False),
    ("Licensed in China only", False), ("Out-licensed to ChinaCo for Greater China", False),
    ("Not licensed in the U.S.; licensed in China to ChinaCo", False),
    ("Exclusive China license to ChinaCo; U.S. rights retained", False)])
def test_reader_fe_offers_and_other_territory_grants_are_never_read_as_us_encumbrance(text, available):
    reading = rights_reading(text)
    assert reading.status != ENCUMBERED and reading.understood
    assert (reading.status == AVAILABLE) is available


def test_reader_residual_an_option_offered_to_partners_is_not_read_and_so_blocks():
    """Recorded residual: "Option available to partners" is not read (an option is usually an encumbrance word)."""
    reading = rights_reading("Option available to partners")
    assert reading.status != AVAILABLE and not reading.understood


# -- Rows that were not applied (R-lost, near-match ids) and the outputs (O-8, O-9, O-11, O-13) -------------------
RIGHTS_PROFILE = {
    "name": "rr3", "source_system": "VENDOR_X", "license_status": "licensed", "allowed_use": "internal_only",
    "columns": {"deal_id": "Deal", "external_id": "Drug ID", "event_type": "Type", "grantee": "Licensee",
                "grantor": "Licensor", "territory": "Territory", "event_date": "Date", "status": "Status",
                "source_reference": "URL", "evidence_quote": "Quote"},
    "event_type_map": {"licensing": "LICENSE"},
    "status_map": {"active": "ACTIVE"},
}


def _workspace(tmp_path, demo_dir, rows: list[list[str]]):
    from bve.dealscreen.workspace import Workspace

    buyer = tmp_path / "buyer.yaml"
    shutil.copyfile(demo_dir / "buyer_tl1a_ibd.yaml", buyer)
    with buyer.open("a", encoding="utf-8") as f:
        f.write("\ntransaction:\n  encumbered_rights: deprioritize\n")
    ws = Workspace(tmp_path / "ws")
    ws.import_landscape(demo_dir / "landscape_200.csv", demo_dir / "profile_synthetic_vendor.yaml", buyer)
    rights = tmp_path / "deals.csv"
    with rights.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(RIGHTS_PROFILE["columns"].values()))
        w.writerows(rows)
    profile = tmp_path / "rights_profile.yaml"
    profile.write_text(yaml.safe_dump(RIGHTS_PROFILE), encoding="utf-8")
    ws.import_rights(rights, profile)
    return ws


def _row(n: int, program: str, licensee: str, licensor: str, territory: str, status: str = "Active") -> list[str]:
    return [f"R{n}", program, "Licensing", licensee, licensor, territory, "2026-03-01", status, f"https://x.test/{n}",
            f"{territory} rights"]


def test_r_lost_a_rejected_row_with_an_unmatched_id_is_reported_and_guards_every_program(tmp_path, demo_dir,
                                                                                          normalizer):
    import openpyxl

    from bve.dealscreen.memo import build_memo
    from bve.dealscreen.workbook import export_workbook

    ws = _workspace(tmp_path, demo_dir, [
        _row(1, "SYN-0154", "ChinaCo", "Pellucid Pharma", "mainland China"),
        _row(2, "SYN-9998", "BigPharma Inc", "Pellucid Pharma", "United States", status="Actv"),  # rejected
    ])
    ws.screen(normalizer)
    screening = ws.screening()
    rejected = screening["rights_import_issues"]["unattributed_rejected_rows"]
    assert [(u["row"], u["program_id"]) for u in rejected] == [(2, "SYN-9998")]
    assert not {s["transaction"]["tier"] for s in screening["screens"]} & TOP
    ids = {a.external_id: a.asset_id for a in ws.assets()}
    t = {s["asset_id"]: s for s in screening["screens"]}[ids["SYN-0154"]]["transaction"]
    assert t["rights_position"] == rp.P_NOT_ENCUMBERED and t["tier"] == UNRESOLVED
    assert any("names program id 'SYN-9998', which matches no program," in g for g in t["rights_rows_not_applied"])
    memo = build_memo(ws)
    assert "Rejected rights rows not attached to any program." in memo
    assert ("row 2 ('SYN-9998', 'Licensing', 2026-03-01; grantee BigPharma Inc, grantor Pellucid Pharma; United States; "
            "rejected: unknown status label 'Actv')") in memo
    sheet = openpyxl.load_workbook(export_workbook(ws, tmp_path / "out.xlsx"))["Diligence"]
    assert any(row[2] == "RIGHTS_ROW_REJECTED_NO_PROGRAM" and row[3] == "SYN-9998"
               and "grantee BigPharma Inc" in row[4] for row in sheet.iter_rows(values_only=True))


def test_near_match_an_unattached_row_with_an_id_close_to_a_programs_holds_that_program(tmp_path, demo_dir,
                                                                                         normalizer):
    from bve.dealscreen.memo import build_memo

    ws = _workspace(tmp_path, demo_dir, [
        _row(1, "SYN-0154", "ChinaCo", "Pellucid Pharma", "mainland China"),
        _row(2, "SYN 154", "BigPharma Inc", "Pellucid Pharma", "United States"),  # accepted, attached to nothing
    ])
    ws.screen(normalizer)
    screening = ws.screening()
    ids = {a.external_id: a.asset_id for a in ws.assets()}
    screen = {s["asset_id"]: s for s in screening["screens"]}[ids["SYN-0154"]]
    unlinked = screening["rights_import_issues"]["unlinked_rows"]
    assert [(u["program_id"], u["near_programs"]) for u in unlinked] == [("SYN 154", [screen["program_name"]])]
    t = screen["transaction"]
    assert t["tier"] == UNRESOLVED
    assert any("Is rights row 2 (program id 'SYN 154') about this program?" in q for q in t["diligence_questions"])
    memo = build_memo(ws)  # O-9: the line names the parties, the territory and the program it may concern
    assert (f"row 2 ('SYN 154', license, 2026-03-01; BigPharma Inc from Pellucid Pharma; United States; id close to "
            f"{screen['program_name']})") in memo


def test_o8_o13_the_memo_counts_what_it_claims_and_prints_words_not_codes(tmp_path, demo_dir, normalizer):
    from bve.dealscreen.memo import build_memo

    ws = _workspace(tmp_path, demo_dir, [_row(1, "SYN-0154", "ChinaCo", "Pellucid Pharma", "mainland China")])
    ws.screen(normalizer)
    memo = build_memo(ws)
    assert "Nothing is shown as available without an explicit, dated statement." not in memo
    assert "None reaches the availability position" in memo or "A source states availability for" in memo
    for code in ("NO_RIGHTS_EVIDENCE", "no rights evidence 1", "not encumbered in territory per evidence",
                 "strategy.indication (", "target.expression (", "rights unresolved 1"):
        assert code not in memo, code


def test_o11_the_other_programs_line_shows_a_blocker_and_counts_the_rest():
    from bve.dealscreen.memo import _other_line

    t = {"rights_position": rp.P_NOT_ENCUMBERED, "rights_holder_per_evidence": None, "stale": False,
         "evidence": [{"type": r.LICENSE, "row": 4, "date": "2025-01-01"}],
         "position_reasons": ["recorded grants do not cover US; this is not a statement of availability",
                              "the landscape also names a U.S. rights holder or labeler: Origin Bio (licensed to X)"],
         "top_tier_blockers": ["uncontested: the note 'licensed to X' is not read, and it may name a third party"],
         "reasons": []}
    line = _other_line({"program_name": "PZ-1", "disposition": "UNRESOLVED", "transaction": t})
    assert "not counted for the top tiers: uncontested: the note 'licensed to X' is not read" in line
    assert "(and 1 more reason(s) in the workbook)" in line


# -- Names: an address after the corporate form is not part of the name (section 4, real legal names) -------------
@pytest.mark.parametrize(("short", "legal", "same"), [
    ("Acme Bio", "Acme Bio Co., Ltd., Lakeside, China", True),
    ("Acme Bio", "Acme Bio Ltd., Hong Kong", True),
    ("Acme", "Acme Inc., USA", True),
    ("Acme Bio", "Acme Bio Inc., Beta Bio", False),  # a second party, not an address
    ("Acme Bio", "Acme Bio Inc., Beta Bio, China", False),
    ("BigPharma Inc", "BigPharma Inc. / Origin Bio", False),
    ("Acme", "Acme Inc., Springfield", False),  # the last item is no known country: kept
    ("Acme Pharma", "Acme Pharma GmbH, Germany", False),  # a country the territory reader does not know: kept
    ("Origin Bio", "Origin Bio and BigPharma Inc.", False),
    ("Acme", "Acme KGaA", False),
])
def test_names_an_address_written_after_the_corporate_form_is_dropped_and_nothing_else(short, legal, same):
    from bve.dealscreen.rights_territory import same_company

    assert same_company(short, legal) is same


def test_names_a_licensor_written_short_matches_the_landscape_legal_name_with_its_address():
    v = run([ev(L, grantee="ChinaCo", grantor="Acme Bio", territory="mainland China", d="2025-01-01")],
            company="Acme Bio Co., Ltd., Lakeside, China")
    assert v.tier == TIER1 and not v.top_tier_blockers


def test_a_rejected_row_close_to_a_programs_id_is_named_once_for_that_program(tmp_path, demo_dir, normalizer):
    ws = _workspace(tmp_path, demo_dir, [
        _row(1, "SYN-0154", "ChinaCo", "Pellucid Pharma", "mainland China"),
        _row(2, "SYN 154", "BigPharma Inc", "Pellucid Pharma", "United States", status="Actv"),  # rejected
    ])
    ws.screen(normalizer)
    screening = ws.screening()
    ids = {a.external_id: a.asset_id for a in ws.assets()}
    screens = {s["asset_id"]: s for s in screening["screens"]}
    near = screens[ids["SYN-0154"]]["transaction"]["rights_rows_not_applied"]
    assert len(near) == 1 and "close to this program's id" in near[0]
    other = screens[ids["SYN-0051"]]["transaction"]["rights_rows_not_applied"]
    assert len(other) == 1 and "may concern any program" in other[0]
