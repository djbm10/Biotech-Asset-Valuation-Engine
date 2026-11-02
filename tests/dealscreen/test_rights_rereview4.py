"""Cycle R1 revision 6: the inputs from adversarial re-review 4 (research/dealscreen_rights_v1/REREVIEW4.md).

Revision 6 inverts the top-tier gate's default (REREVIEW4 section 13): beside a clear position, a rights text passes
only if every clause is one of the plain forms in ``rights_allow``; anything else blocks, quoted and cited. It also
reads Partnerships and Geographic Notes, notes in company and rights-row party names, dates ledger endings and
acquisitions, limits the landscape-field path to a buyer territory of exactly the U.S., and widens the rows that guard
a program. Each test is tagged with its review id.

Per-program cases run through ``screening.program_transaction``. Defaults as in ``test_rights_rereview3``: buyer
territory US, as-of 2025-06-01, landscape company and licensor "Origin Bio". Parties are fictional; the tests assert
no real-world facts."""

from __future__ import annotations

from datetime import date

import pytest
from test_rights_rereview3 import (
    AV,
    CHINA,
    RR,
    STATED,
    TIER0,
    TIER1,
    TOP,
    UNRESOLVED,
    US_LICENSE,
    L,
    analyst,
    blocked,
    cell,
    cites,
    ev,
    run,
)

from bve.dealscreen import rights as r
from bve.dealscreen import rights_position as rp
from bve.dealscreen.rights_allow import is_rights_text, plain_form
from bve.dealscreen.rights_gate import ids_close, program_key, row_guards
from bve.dealscreen.rights_reader import rights_reading
from bve.dealscreen.rights_territory import content_note

EU = frozenset({"EU"})
OTHER = "Other Pharma"


def _no_top(text: str, *, field: str = "us_rights", source: str = "analyst", events=None) -> None:
    claim = analyst(field, text) if source == "analyst" else cell(field, text, src="2025-04-01")
    events = events if events is not None else [ev(L, **CHINA)]
    v = run(events, analysts=(claim,)) if source == "analyst" else run(events, landscape=(claim,))
    assert v.tier not in TOP, (text, v.tier, v.top_tier_blockers)


# R1: a date is not a program code; an offer "2H26" or "post-2026" is not an offer now.
@pytest.mark.parametrize("text", ["U.S. rights available Q3", "Available 2H26", "Available in 1H2027",
                                  "US rights available post-2026", "Partner sought 2H22", "Available FY27",
                                  "Rights available after-2027", "Available Q4-2026 for all territories"])
def test_r1_a_dated_offer_never_reaches_a_top_tier(text):
    assert not rights_reading(text).understood
    _no_top(text, events=[])
    _no_top(text, source="landscape")


# R2 / R3: a role noun ("the licensee") as the one who offers, or as the one rights are available to.
@pytest.mark.parametrize("text", ["The licensee is seeking a partner for U.S. rights",
                                  "Our licensee seeks a partner for US rights", "The acquirer is open to a deal",
                                  "Its partner is seeking a licensee", "U.S. rights available to the partner",
                                  "Available to licensee", "U.S. rights available to the licensee",
                                  "Available to Other Pharma", "Open to Other Pharma",
                                  "Collaborator open to licensing U.S. rights"])
def test_r2_r3_another_partys_offer_or_an_offer_to_a_party_never_reaches_a_top_tier(text):
    assert plain_form(text, "Origin Bio") is None
    _no_top(text, events=[])
    _no_top(text, source="landscape")


# R4: a U.S. grant or option written after a non-U.S. license.
@pytest.mark.parametrize("text", ["Licensed in Japan to Kappa Ltd, later expanded to North America",
                                  "Licensed in China and Japan, extended to the U.S. in 2024",
                                  "Licensed in Greater China, with an option to U.S. rights",
                                  "Licensed in China, option to US", "Licensed in China, co-promotion with US partner",
                                  "Licensed in China to Chinaco Pharma, sublicensed to US partner"])
def test_r4_a_us_grant_after_a_non_us_license_is_never_erased(text):
    assert plain_form(text, "Origin Bio") is None
    _no_top(text, source="landscape")


# R5: a return to anyone but the company.
@pytest.mark.parametrize("text", ["U.S. rights returned to Other Pharma", "Rights reverted to Other Pharma in 2024",
                                  "Other Pharma regained U.S. rights", "US rights returned to licensor Other Pharma"])
def test_r5_a_return_to_a_third_party_is_never_a_plain_form(text):
    assert plain_form(text, "Origin Bio") is None
    _no_top(text, source="landscape")


# P: Partnerships and Geographic Notes are read by the gate.
@pytest.mark.parametrize(("field", "text"), [
    ("partnerships", "Exclusive U.S. license to Other Pharma (2025)"),
    ("geographic_rights", "U.S. rights licensed to Other Pharma; China to Chinaco Pharma"),
    ("geographic_rights", "U.S. rights licensed to Other Pharma (2025)"),
])
@pytest.mark.parametrize("source", ["analyst", "landscape"])
def test_p_partnerships_and_geographic_notes_that_name_a_us_grant_block(field, text, source):
    _no_top(text, field=field, source=source)


def test_p_partnerships_that_only_name_organisations_are_not_read():
    assert not is_rights_text("Other Pharma; Beta Bio")
    v = run([ev(L, **CHINA)], landscape=(cell("partnerships", "Other Pharma; Beta Bio"),))
    assert v.tier == TIER1


def test_p_a_plain_geographic_note_is_listed_as_consistent_and_does_not_block():
    v = run([ev(L, **CHINA)], landscape=(cell("geographic_rights", "Licensed in Greater China only"),))
    assert v.tier == TIER1
    assert any("a grant over other places only" in x for x in v.position_reasons)


# N / CN: notes in rights-row party names and in the landscape company name.
@pytest.mark.parametrize("company", ["Origin Bio (U.S. rights licensed to Other Pharma)",
                                     "Origin Bio (in-licensed from Other Pharma)"])
def test_cn_a_note_in_the_company_name_blocks(company):
    v = run([ev(L, grantee="ChinaCo", grantor="Origin Bio", territory="mainland China", d="2025-01-01")],
            company=company)
    assert v.tier not in TOP and blocked(v, "names the program's company as")


@pytest.mark.parametrize("party", ["grantor", "grantee"])
def test_n_a_note_in_a_rights_row_party_name_blocks(party):
    names = {"grantor": "Origin Bio (U.S. sublicensed to Other Pharma)", "grantee": "ChinaCo"}
    if party == "grantee":
        names = {"grantor": "Origin Bio", "grantee": "ChinaCo (on behalf of Other Pharma)"}
    v = run([ev(L, territory="mainland China", d="2025-01-01", **names)])
    assert v.tier not in TOP


def test_n1_a_statement_maker_with_a_note_is_never_the_holder():
    v = run([ev(AV, grantor="Origin Bio (U.S. rights licensed to Other Pharma)", **STATED)])
    assert v.tier not in TOP and v.holder is None


def test_u3_a_one_word_place_inside_a_legal_name_is_not_a_note():
    name = "Origin Bio (Suzhou) Co., Ltd."
    assert not content_note(name)
    v = run([ev(L, **CHINA)], landscape=(cell("us_rights_holder", name),))
    assert v.tier == TIER1


def test_u3_judgement_a_parenthesis_after_the_corporate_form_is_still_a_note():
    """Kept: "(Delaware)" and "(Other)" have the same shape after "Inc.", and a one-word party must not be dropped."""
    assert content_note("Origin Bio, Inc. (Delaware)") == "Delaware"
    v = run([ev(L, **CHINA)], landscape=(cell("us_rights_holder", "Origin Bio, Inc. (Delaware)"),))
    assert v.tier not in TOP


# E1 / E3: an ending stated only by a status flag cannot be ordered against a statement.
@pytest.mark.parametrize("kind", [L, r.OPTION])
def test_e1_e3_a_status_flag_ending_beside_a_statement_blocks(kind):
    status = "TERMINATED" if kind == L else "EXPIRED"
    v = run([ev(kind, status=status, src="2025-05-01", **US_LICENSE), ev(AV, **STATED)])
    assert v.tier not in TOP and blocked(v, "is stated only by the record's status")


def test_e2_a_status_reported_after_the_as_of_date_is_not_applied():
    v = run([ev(L, status="TERMINATED", src="2025-09-01", **US_LICENSE)])
    assert v.position == rp.P_LICENSED and v.tier not in TOP
    assert any("after the as-of date" in x for x in v.position_reasons)


# O1: an undated acquisition never makes a third party the company.
def test_o1_an_undated_acquisition_blocks_and_asks_for_its_date():
    v = run([ev(r.ACQUISITION, grantee="Origin Bio", grantor=OTHER, d=None),
             ev(AV, grantor=OTHER, **STATED)])
    assert v.tier not in TOP and blocked(v, "has no date")
    assert any("When did Origin Bio acquire Other Pharma?" in q for q in v.questions)


# TER-F / TER-G / TER2: buyer territories other than exactly the U.S.
@pytest.mark.parametrize("territory", [EU, frozenset({"US", "CA"})])
def test_ter_f_the_us_rights_fields_are_not_read_as_a_position_outside_a_us_only_territory(territory):
    v = run([], analysts=(analyst("us_rights", "U.S. rights available"),), territory=territory)
    assert v.tier not in TOP
    assert any("speak to the U.S. only" in x for x in v.position_reasons)


def test_ter2_a_us_only_license_cell_is_not_an_eu_encumbrance():
    v = run([], landscape=(cell("us_rights", "Licensed to Other Pharma for the U.S. only", src="2025-04-01"),),
            territory=EU)
    assert v.position != rp.P_LICENSED


def test_ter_g_the_gate_reads_holders_for_a_non_us_territory():
    v = run([ev(L, **CHINA)], landscape=(cell("us_rights_holder", "Other Pharma (worldwide licensee)"),),
            territory=EU)
    assert v.tier not in TOP


# K2, FE4, RET: false conflicts and false encumbrance.
def test_k2_a_dated_return_with_a_return_and_offer_cell_is_not_a_conflict():
    v = run([ev(L, **US_LICENSE), ev(RR, grantee="Alpha Bio", territory="United States", d="2025-02-01")],
            landscape=(cell("us_rights", "Rights returned by Alpha Bio in 2025; seeking a partner", "2025-04-01"),))
    assert v.position != rp.P_CONFLICTING


def test_fe4_licensed_elsewhere_and_available_in_the_us_is_not_a_us_license():
    v = run([], analysts=(analyst("us_rights", "Licensed in China and Japan and available in US"),))
    assert v.position != rp.P_LICENSED


@pytest.mark.parametrize("text", ["US rights retained by Origin Bio", "Rights retained by the company",
                                  "Global rights retained by Origin Bio"])
def test_ret_rights_retained_by_the_company_is_not_a_conflict_or_an_encumbrance(text):
    assert plain_form(text, "Origin Bio") == "rights kept by the company"
    v = run([ev(L, **CHINA)], landscape=(cell("us_rights", text, "2025-04-01"),))
    assert v.tier == TIER1


# U1 / U2: plain forms the company uses reach the top tiers.
def test_u1_ex_china_rights_available_is_an_offer():
    v = run([], analysts=(analyst("us_rights", "Ex-China rights available"),))
    assert v.tier == TIER0


@pytest.mark.parametrize("text", ["Origin Bio retains U.S. rights", "Wholly owned by Origin Bio",
                                  "Company retains all rights outside Greater China"])
def test_u2_the_company_keeping_rights_beside_a_china_license_reaches_tier_1(text):
    v = run([ev(L, **CHINA)], landscape=(cell("us_rights", text, "2025-04-01"),))
    assert v.tier == TIER1
    assert any("rights kept by the company" in x for x in v.position_reasons)


# ROW: ids close to a program's id, and rows naming the program's company.
@pytest.mark.parametrize(("row_id", "program", "close"), [
    ("AB-24 (ADC)", "AB-24", True), ("AB-24A", "AB-24", True), ("LB4330-01", "LB4330", True),
    ("ABDN-24", "AB-24", True), ("AB 024", "AB-24", True), ("RC-148 (ADC)", "RC148", True),
    ("AB-42", "AB-24", False), ("AB-2", "AB-24", False), ("NB-71", "NB-7", False), ("24", "AB-24", False),
])
def test_row_ids_close(row_id, program, close):
    assert ids_close(row_id, program) is close


def test_row_an_unattached_row_naming_a_programs_company_guards_that_program():
    row = ev(L, grantee=OTHER, grantor="Origin Bio", territory="United States", d="2025-02-01")
    row = row.model_copy(update={"external_id": "ZZ-9"})
    keys = {program_key("P1"), program_key("Q2")}
    guards = row_guards(keys, [row], [], {program_key("P1"): "Origin Bio", program_key("Q2"): "Beta Bio"})
    assert [k for k, _ in guards.per_program.items()] == [program_key("P1")]
    assert "names this program's company (Origin Bio)" in guards.per_program[program_key("P1")][0][1]


# L1 / L2 / L4: memo wording.
def test_l1_l2_l4_memo_wording(tmp_path, demo_dir, normalizer):
    from test_rights_rereview3 import _row, _workspace

    from bve.dealscreen.memo import build_memo

    (tmp_path / "probe").mkdir()
    (tmp_path / "ws").mkdir()
    probe = _workspace(tmp_path / "probe", demo_dir, [_row(1, "SYN-0154", "ChinaCo", "Pellucid Pharma",
                                                           "mainland China")])
    probe.screen(normalizer)
    external = {a.asset_id: a.external_id for a in probe.assets()}
    ranked = next(external[s["asset_id"]] for s in probe.screening()["screens"]
                  if s.get("transaction_rank") and external[s["asset_id"]] != "SYN-0154")
    ws = _workspace(tmp_path / "ws", demo_dir, [
        _row(1, "SYN-0154", "ChinaCo", "Pellucid Pharma", "mainland China"),
        _row(2, ranked, "BigPharma Inc", "Pellucid Pharma", "United States", status="Actv"),  # rejected, own id
    ])
    ws.screen(normalizer)
    memo = build_memo(ws)
    assert "pass every rights check" not in memo
    assert "feed the transaction view" not in memo
    ids = {a.external_id: a.asset_id for a in ws.assets()}
    screen = {s["asset_id"]: s for s in ws.screening()["screens"]}[ids[ranked]]
    line = next(x for x in memo.splitlines() if x.startswith(f"- #{screen['transaction_rank']} "))
    assert "rights row 2 for this program was rejected at import" in line


# L3: the assert note says what the gate does with the text.
def test_l3_the_assert_note_says_whether_the_gate_accepts_the_text():
    from bve.cli.dealscreen import rights_reading_note

    assert "not one of the plain forms" in rights_reading_note("Available 2H27", "Origin Bio") or \
        "cannot read" in rights_reading_note("Available 2H27", "Origin Bio")
    assert "plain form for the buyer territory (US): an offer" in rights_reading_note("U.S. rights available",
                                                                                     "Origin Bio")
    note = rights_reading_note("Exclusive U.S. license to Other Pharma (2025)", "Origin Bio", "partnerships")
    assert "not one of the plain forms" in note
    assert "names of organisations only" in rights_reading_note("Other Pharma", "Origin Bio", "partnerships")


# Allow-list: the plain forms and their near misses.
@pytest.mark.parametrize(("text", "form"), [
    ("U.S. rights available", "an offer"), ("Seeking a co-development partner", "an offer"),
    ("Origin Bio is open to partnering", "an offer"), ("Unpartnered", "no grant stated"),
    ("Not licensed in the U.S.", "no grant stated"), ("U.S. rights returned to Origin Bio (2024)",
                                                       "rights returned to the company"),
    ("Origin Bio regained U.S. rights", "rights returned to the company"),
    ("Licensed in Greater China", "a grant over other places only"),
    ("Exclusive China license to Chinaco Pharma", "a grant over other places only"),
    ("U.S. rights returned to Origin Bio (2026)", None), ("Licensed to Other Pharma in the U.S.", None),
    ("U.S. rights available to Other Pharma", None), ("Seeking a partner; option held by Other Pharma", None),
    # Revision 7 (review R1v6 PF1): "U.S." is read as written, even inside a party's name, so this blocks.
    ("Licensed in Greater China to Other Pharma U.S. Inc.", None),
    ("Licensed in Greater China to Other Pharma, with U.S. rights", None),
])
def test_allow_list_forms(text, form):
    assert plain_form(text, "Origin Bio", date(2025, 6, 1)) == form


def test_an_availability_statement_row_beside_a_clean_record_still_reaches_tier_0():
    assert run([ev(AV, **STATED)]).tier == TIER0


def test_a_tier_change_keeps_the_text_cited():
    text = "Licensed in Greater China, with an option to U.S. rights"
    v = run([ev(L, **CHINA)], landscape=(cell("us_rights", text, "2025-04-01"),))
    assert v.tier == UNRESOLVED
    assert cites(v, text) or any(text in b for b in v.top_tier_blockers)


def test_l1_the_summary_keeps_the_holder_sentence_beside_the_availability_count():
    from collections import Counter

    from bve.dealscreen.memo import _rights_summary

    def screen(blockers: list[str]) -> dict:
        return {"commercial": {"us_rights_holder": "Origin Bio"},
                "transaction": {"rights_position": "AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED", "evidence": [{"row": 1}],
                                "top_tier_blockers": blockers, "stale": False, "rights_rows_not_applied": [],
                                "rights_holder_per_evidence": "Origin Bio"}}

    text = _rights_summary(2, [screen([]), screen(["current: x"])], Counter())
    assert "A holder or labeler is named in cited evidence for 2" in text
    # Revision 8 (review R1v7 L1c): the sentence says these are word rules.
    assert "for 1 DealScreen's word rules found nothing else" in text and "and 1 have a blocker" in text
    assert "not a check that any statement is true" in text
    assert "all 1 have a blocker" in _rights_summary(1, [screen(["current: x"])], Counter())
