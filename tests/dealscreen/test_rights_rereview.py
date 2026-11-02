"""Cycle R1 revision 3: the failing inputs from the adversarial re-review (research/dealscreen_rights_v1/REREVIEW.md).

Held-back fixtures with fictional parties. Each test is tagged with its re-review case id. They test logic
only and assert no real-world facts."""

from __future__ import annotations

import csv
import shutil
from datetime import date
from types import SimpleNamespace

import pytest
import yaml
from pydantic import ValidationError

from bve.dealscreen import commercial as c
from bve.dealscreen import rights as r
from bve.dealscreen import rights_position as rp
from bve.dealscreen.buyer import CommercialDiligence
from bve.dealscreen.rights_territory import parse_territory
from bve.dealscreen.screening import _reconcile_with_field
from bve.dealscreen.transaction import (
    TransactionPreferences,
    assess_transaction,
    position_from_field,
)

US = frozenset({"US"})
_N = iter(range(1, 10_000))


def ev(kind: str, *, grantee: str | None = None, grantor: str | None = "Origin Bio", territory: str | None = None,
       d: str | None = "2025-01-01", excl: str = "EXCLUSIVE", status: str = "UNKNOWN", deal: str | None = None,
       related: str | None = None, src: str | None = None) -> r.RightsEvent:
    """``d`` / ``src`` as written: "2024" is a year, "2024-05" a month, "2024-05-02" a day."""
    n = next(_N)
    regions = parse_territory(territory)
    when, precision = r.parse_date(d) if d else (None, "day")
    source, source_precision = r.parse_date(src) if src else (None, "day")
    return r.RightsEvent(
        event_id=f"rx:rr:{n}", deal_id=deal or f"D{n}", external_id="P1", event_type=kind, exclusivity=excl,
        grantee=grantee, grantor=grantor, territory_as_written=territory,
        territory=sorted(regions) if regions is not None else None,
        event_date=when, event_date_precision=precision, status=status, related_deal_id=related,
        source_system="TEST", dataset_version="TEST:x", row_number=n, source_reference=f"https://example.test/{n}",
        evidence_quote=f"quote {n}", source_date=source, source_date_precision=source_precision)


def pos(events, territory=US, as_of=date(2025, 6, 1), max_age=730, company: str | None = "Origin Bio"):
    """``company``: the landscape company (revision 5: a clear position must rest on it)."""
    return rp.rights_position(events, territory=territory, as_of=as_of, max_age_days=max_age, first_contact=company)


PREFS = TransactionPreferences(encumbered_rights="deprioritize")


def view(p, prefs=PREFS, guard=None):
    return assess_transaction(prefs, market_status=None, rights_status="UNKNOWN", rights_holder=None,
                              company="Origin Bio", identity_twins=[], position=p, guard=guard)


def top_tier(p) -> bool:
    return view(p, TransactionPreferences()).tier in {"AVAILABILITY_STATED_UNVERIFIED", "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"}


def text(p) -> str:
    return " ".join(p.reasons + p.questions)


# -- D: dates and ordering ------------------------------------------------------------------------------
def test_d1_a_second_record_of_one_termination_never_clears_a_re_license():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2020-01-01"),
             ev(r.TERMINATION, grantee="Alpha", d="2022-03-01"),
             ev(r.TERMINATION, grantee="Alpha", d=None),
             ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2025-03-01")])
    assert p.position in {rp.P_LICENSED, rp.P_CONFLICTING} and not top_tier(p)


def test_d2_licensor_only_undated_termination_does_not_clear_a_later_license():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2020-01-01"),
             ev(r.TERMINATION, grantee="Alpha", d="2022-03-01"),
             ev(r.TERMINATION, grantee=None, grantor="Origin Bio", d=None),
             ev(r.LICENSE, grantee="Beta", territory="United States", d="2025-03-01")])
    assert p.position in {rp.P_LICENSED, rp.P_CONFLICTING} and "Beta" in p.holders and not top_tier(p)


def test_d3_a_report_date_bounds_an_outcome_from_above_only():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2020-01-01"),
             ev(r.TERMINATION, grantee="Alpha", d="2021-06-01"),
             ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2024-06-01"),
             ev(r.TERMINATION, grantee="Alpha", d=None, src="2025-02")])
    assert p.position in {rp.P_LICENSED, rp.P_CONFLICTING} and not top_tier(p)


def test_d4_an_ending_before_the_report_of_a_report_dated_grant_cannot_be_ordered():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d=None, src="2025-03"),
             ev(r.TERMINATION, grantee="Alpha", d="2024-05-10")])
    assert p.position == rp.P_CONFLICTING
    assert "reported 2025-03" in text(p) and any("cannot order" in q for q in p.questions)
    assert not any("dated before every recorded grant" in x for x in p.reasons)  # that would overstate it
    # linked by deal id, the ending follows its grant by definition: the deal existed before the ending
    linked = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d=None, src="2025-03", deal="DX"),
                  ev(r.TERMINATION, grantee="Alpha", d="2024-05-10", related="DX")])
    assert linked.position == rp.P_RETURNED
    # an ending after the report still applies
    after = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d=None, src="2024-03"),
                 ev(r.TERMINATION, grantee="Alpha", d="2025-01-10")])
    assert after.position == rp.P_RETURNED


def test_d5_d6_linked_or_option_outcomes_in_the_grant_period_still_apply():
    linked = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2024", deal="DX"),
                  ev(r.TERMINATION, grantee="Alpha", d="2024-09-01", related="DX")])
    assert linked.position == rp.P_RETURNED
    lapsed = pos([ev(r.OPTION, grantee="Alpha", territory="worldwide", d="2023", deal="DY"),
                  ev(r.OPTION_LAPSED, grantee="Alpha", d="2023-11-01", related="DY")])
    assert lapsed.position == rp.P_NOT_ENCUMBERED
    # revision 4 (review R1v3 R1): one ordering rule for options and licenses; only a deal-id link orders an
    # outcome after its grant, so an unlinked lapse inside the option's year cannot be ordered against it
    unlinked = pos([ev(r.OPTION, grantee="Alpha", territory="worldwide", d="2023"),
                    ev(r.OPTION_LAPSED, grantee="Alpha", d="2023-11-01")])
    assert unlinked.position == rp.P_CONFLICTING


# -- U: outcome territories ---------------------------------------------------------------------------------
@pytest.mark.parametrize(("grant", "outcome", "where", "expected"), [
    ("worldwide", r.TERMINATION, "Latin America", rp.P_LICENSED),  # U1: unreadable outcome territory
    ("North America", r.TERMINATION, "Mexico", rp.P_LICENSED),  # U1b
    ("ex-China", r.RIGHTS_RETURNED, "Asia ex-Japan", rp.P_LICENSED),  # U3
])
def test_u_an_outcome_for_an_unreadable_territory_keeps_the_grant_and_asks(grant, outcome, where, expected):
    p = pos([ev(r.LICENSE, grantee="Alpha", territory=grant, d="2023-01-01"),
             ev(outcome, grantee="Alpha", territory=where, d="2024-01-01")])
    assert p.position == expected and not top_tier(p)
    assert any(where in q for q in p.questions)


def test_u2_a_lapse_for_one_country_leaves_the_option_elsewhere():
    p = pos([ev(r.OPTION, grantee="Alpha", territory="worldwide", d="2023-01-01"),
             ev(r.OPTION_LAPSED, grantee="Alpha", territory="Japan", d="2024-01-01")])
    assert p.position == rp.P_OPTION and p.holder == "Alpha"


# -- A: availability statements -------------------------------------------------------------------------------
@pytest.mark.parametrize("where", ["Australia and New Zealand", "Europe and Latin America"])
def test_a1_a_statement_for_an_unreadable_territory_is_not_us_availability(where):
    p = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory=where, d="2025-03-01")])
    assert p.position != rp.P_AVAILABILITY and not top_tier(p)
    assert any(where in q for q in p.questions)


@pytest.mark.parametrize("status", ["COMPLETED", "TERMINATED"])
def test_a2_a_statement_whose_search_concluded_is_not_counted(status):
    p = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide", d="2025-03-01", status=status)])
    assert p.position != rp.P_AVAILABILITY and not top_tier(p)


def test_a3_a_statement_answered_by_a_later_license_is_not_a_current_offer():
    p = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide", d="2024-01-01"),
             ev(r.LICENSE, grantee="Alpha", territory="United States", d="2024-03-01"),
             ev(r.TERMINATION, grantee="Alpha", d="2025-01-01")])
    assert p.position == rp.P_RETURNED and view(p).tier != "AVAILABILITY_STATED_UNVERIFIED"


# -- G: grants beside the deciding grant, holders, owners -----------------------------------------------------
def test_g1_two_exclusive_options_to_different_parties_conflict():
    p = pos([ev(r.OPTION, grantee="Alpha", territory="United States", d="2024-01-01"),
             ev(r.OPTION, grantee="Beta", territory="worldwide", d="2024-02-01")])
    assert p.position == rp.P_CONFLICTING and {"Alpha", "Beta"} <= set(p.holders)


def test_g2_a_grant_with_an_unreadable_territory_is_named_beside_the_deciding_one():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="United States", d="2024-01-01"),
             ev(r.LICENSE, grantee="Bigpharma Inc", territory="the Americas", d="2024-02-01")])
    assert p.position in {rp.P_LICENSED, rp.P_CONFLICTING} and "Bigpharma Inc" in p.holders
    assert any("Bigpharma Inc" in q for q in p.questions)


def test_g3_the_head_licensee_is_named_and_counts_for_the_preference():
    p = pos([ev(r.LICENSE, grantee="Bigpharma Inc", territory="worldwide", d="2024-01-01"),
             ev(r.LICENSE, grantee="Smallco", grantor="Bigpharma Inc", territory="United States", d="2024-06-01")])
    assert p.position == rp.P_LICENSED and p.holder == "Smallco" and "Bigpharma Inc" in p.holders
    assert any("head licensee" in q for q in p.questions)
    v = view(p, TransactionPreferences(deprioritized_holders=["Bigpharma"]))
    assert v.tier == "DEPRIORITIZED" and any("Bigpharma" in x for x in v.reasons)


def test_g4_a_licensor_buying_its_licensee_holds_the_rights_itself():
    p = pos([ev(r.LICENSE, grantee="Smallco", grantor="Origin Bio", territory="worldwide", d="2021-01-01"),
             ev(r.ACQUISITION, grantee="Origin Bio", grantor="Smallco", d="2024-01-01")])
    assert p.position == rp.P_OWNER_ACQUIRED and p.holder == "Origin Bio"
    assert not any("license to Origin Bio" in x for x in p.reasons)
    assert len(p.evidence) == 2


def test_g5_an_acquisition_that_moves_a_license_is_cited():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2024-01-01"),
             ev(r.ACQUISITION, grantee="Bigco", grantor="Alpha", d="2024-06-01")])
    assert p.position == rp.P_LICENSED and p.holder == "Bigco"
    assert {e["type"] for e in p.evidence} == {r.LICENSE, r.ACQUISITION}


def test_m2_a_co_promotion_option_holder_is_named_and_counts_for_the_preference():
    p = pos([ev(r.LICENSE, grantee="Smallco", territory="United States", d="2025-01-01"),
             ev(r.CO_PROMOTION_OPTION, grantee="Bigpharma Inc", territory="United States", d="2025-02-01")])
    assert p.position == rp.P_LICENSED and {"Smallco", "Bigpharma Inc"} <= set(p.holders)
    assert view(p, TransactionPreferences(deprioritized_holders=["Bigpharma"])).tier == "DEPRIORITIZED"


# -- K: outcomes recorded without their grant, partial exercises -----------------------------------------------
def test_k1_a_return_without_its_grant_is_a_return():
    p = pos([ev(r.RIGHTS_RETURNED, grantee="Bigco", grantor="Origin Bio", territory="worldwide", d="2024-08-01")])
    assert p.position == rp.P_RETURNED and p.holder == "Origin Bio"
    assert any("original grant" in q for q in p.questions)


def test_k2_a_termination_without_its_grant_and_without_a_territory_ended_the_whole_deal():
    p = pos([ev(r.TERMINATION, grantee="Bigco", grantor="Origin Bio", d="2024-08-01")])
    assert p.position == rp.P_RETURNED and p.holder == "Origin Bio"
    assert "whole deal" in text(p) and any("Which territories" in q for q in p.questions)


@pytest.mark.parametrize("where", ["Japan", "Latin America"])
def test_k2_a_termination_without_its_grant_elsewhere_or_unreadable_is_only_a_question(where):
    p = pos([ev(r.TERMINATION, grantee="Bigco", grantor="Origin Bio", territory=where, d="2024-08-01")])
    assert p.position == rp.P_NOT_APPLIED and not top_tier(p)
    assert "Bigco" in " ".join(p.questions + p.reasons)


def test_k5_a_partial_exercise_is_cited_and_the_option_kept_elsewhere():
    events = [ev(r.OPTION, grantee="Alpha", territory="worldwide", d="2022-01-01"),
              ev(r.OPTION_EXERCISED, grantee="Alpha", territory="Japan", d="2024-01-01")]
    p = pos(events)
    assert p.position == rp.P_OPTION and len(p.evidence) == 2
    assert not p.stale  # the exercise shows the option agreement was live in 2024
    assert any("Recorded so far: exercised for Japan" in q for q in p.questions)
    assert not any("No outcome is recorded" in q for q in p.questions)
    jp = pos(events, territory=frozenset({"JP"}))
    assert jp.position == rp.P_LICENSED


def test_m1_a_chain_through_an_acquirer_cites_every_row():
    p = pos([ev(r.LICENSE, grantee="Turnco Therapeutics", grantor="Lanco Medicines",
                territory="worldwide excluding Greater China and South Korea", d="2022-05-04", src="2022-08"),
             ev(r.TERMINATION, grantee="Bigco Squibb", grantor="Lanco Medicines", d=None, status="TERMINATED"),
             ev(r.RIGHTS_RETURNED, grantee="Bigco Squibb", grantor="Lanco", d="2024", src="2025-07"),
             ev(r.ACQUISITION, grantee="Bigco Squibb Company", grantor="Turnco Therapeutics, Inc.", d="2022-08")],
            as_of=date(2026, 10, 29), company="Lanco Medicines")
    # revision 4 (review R1v3 N7a): the return is judged on its own date (2024), not on its 2025 report
    assert p.position == rp.P_RETURNED and len(p.evidence) == 4 and p.stale
    stale_return = "current: a rights return (2024) naming Bigco Squibb is more than 730 days before 2026-10-29"
    assert p.top_tier_blockers == [stale_return]


def test_m3_an_exercise_is_cited_and_keeps_the_license_current():
    p = pos([ev(r.OPTION, grantee="Alpha", territory="worldwide", d="2021-01-01"),
             ev(r.OPTION_EXERCISED, grantee="Alpha", d="2025-03-01")])
    assert p.position == rp.P_LICENSED and len(p.evidence) == 2 and not p.stale


# -- S: staleness ------------------------------------------------------------------------------------------
def test_s1_a_stale_return_does_not_outrank_programs_with_no_evidence():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2012-01-01"),
             ev(r.RIGHTS_RETURNED, grantee="Alpha", d="2015-01-01")])
    assert p.position == rp.P_RETURNED and p.stale
    v = view(p)
    assert v.tier == "RIGHTS_UNRESOLVED" and any("stale evidence" in x for x in v.reasons)
    fresh = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2022-01-01"),
                 ev(r.RIGHTS_RETURNED, grantee="Alpha", d="2025-01-01")])
    assert view(fresh).tier == "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"


def test_s1_the_buyer_sets_the_age_limit():
    # The program's company is given: a return recorded without its grant counts only when it returns the rights to
    # that company (revision 4, review R1v3 N4d).
    p = rp.rights_position([ev(r.RIGHTS_RETURNED, grantee="Alpha", territory="worldwide", d="2021-01-01")],
                           territory=US, as_of=date(2025, 6, 1), max_age_days=3650, first_contact="Origin Bio")
    assert not p.stale and view(p).tier == "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"


def test_s2_an_old_grant_in_a_conflict_is_named_as_possibly_ended():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="United States", d="2016-01-01"),
             ev(r.OPTION, grantee="Beta", territory="United States", d="2025-01-01")])
    assert p.position == rp.P_CONFLICTING
    assert any("license to Alpha" in x and "may have ended" in x for x in p.reasons)
    assert any("license to Alpha (2016-01-01) still in force" in q for q in p.questions)
    assert not any("option to Beta" in x and "may have ended" in x for x in p.reasons)


def test_s2_an_old_grant_beside_a_fresh_deciding_one_is_named():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="United States", d="2025-01-01"),
             ev(r.CO_PROMOTION_OPTION, grantee="Beta", territory="United States", d="2016-01-01")])
    assert p.position == rp.P_LICENSED and not p.stale
    assert any("option to Beta" in x and "may have ended" in x for x in p.reasons)


# -- B1, P: buyer territory and territory text --------------------------------------------------------------
@pytest.mark.parametrize("code", ["USA", "U.S.", "UNITED STATES", "us "])
def test_b1_a_buyer_territory_that_is_not_a_region_code_is_refused(code):
    events = [ev(r.LICENSE, grantee="Alpha", territory="United States", d="2025-01-01")]
    if code.strip().upper() == "US":  # case and spaces are normalised by the buyer spec, not the ledger
        assert TransactionPreferences(territory=[code]).territory == ["US"]
        return
    with pytest.raises(ValueError):
        pos(events, territory=frozenset({code}))
    with pytest.raises(ValidationError):
        TransactionPreferences(territory=[code])
    with pytest.raises(ValidationError):
        CommercialDiligence(required_market=code)
    with pytest.raises(ValueError):
        pos(events, territory=frozenset())


@pytest.mark.parametrize("written", ["Worldwide excluding U.S", "Worldwide, ex-U.S", "All countries other than the U.S."])
def test_p_us_abbreviation_without_a_final_period_is_read(written):
    covered = parse_territory(written)
    assert covered is not None and "US" not in covered and "JP" in covered


# -- F1, E2, E3: other rights evidence beside the rights file ---------------------------------------------------
@pytest.mark.parametrize(("written", "expected"), [
    ("Not currently available", c.NOT_AVAILABLE),
    ("Rights no longer available", c.NOT_AVAILABLE),
    ("available only in China", c.UNKNOWN),
    ("U.S. rights available; company seeking a partner", c.AVAILABLE),
])
def test_f1_landscape_text_is_read_conservatively(written, expected):
    assert c.rights_status(written) == expected


def test_f1_an_undated_landscape_availability_cell_is_not_counted():
    p = position_from_field(c.AVAILABLE, None, "Origin Bio")
    assert p.position == rp.P_NONE and any("not counted" in x for x in p.reasons)
    assert view(None).tier == "RIGHTS_UNRESOLVED"
    v = assess_transaction(PREFS, market_status=None, rights_status=c.AVAILABLE, rights_holder=None,
                           company="Origin Bio", identity_twins=[])
    assert v.tier == "RIGHTS_UNRESOLVED"


def test_e3_a_rejected_rights_row_keeps_a_clear_position_out_of_the_top_tiers():
    p = pos([ev(r.LICENSE, grantee="Chinaco", territory="mainland China", d="2025-01-01")])
    assert view(p).tier == "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"
    v = view(p, guard=["rights row 20 for this program was rejected at import"])
    assert v.tier == "RIGHTS_UNRESOLVED" and "rejected" in v.reasons[0]


def test_e2_a_field_encumbrance_against_a_clear_position_is_a_conflict():
    p = pos([ev(r.LICENSE, grantee="Chinaco", territory="mainland China", d="2025-01-01")])
    screen = SimpleNamespace(commercial=SimpleNamespace(
        us_rights_status=c.ENCUMBERED, us_rights_holder=None, us_rights_holder_conflict=[], us_rights_holder_basis=[],
        us_rights_basis=[{"claim_id": "a1", "value": "U.S. rights licensed to Otherco", "origin": "ANALYST_ASSERTED",
                          "source": "https://example.test/a1", "source_date": "2025-04-01"}]))
    _reconcile_with_field(p, screen, US)
    assert p.position == rp.P_CONFLICTING and any("analyst" in x for x in p.reasons)
    assert not top_tier(p)


# -- E2/E3/F1 through the workspace (synthetic landscape) -----------------------------------------------------
RIGHTS_PROFILE = {
    "name": "rr", "source_system": "VENDOR_X", "license_status": "licensed", "allowed_use": "internal_only",
    "columns": {"deal_id": "Deal", "external_id": "Drug ID", "event_type": "Type", "grantee": "Licensee",
                "grantor": "Licensor", "territory": "Territory", "event_date": "Date", "status": "Status",
                "source_reference": "URL", "evidence_quote": "Quote"},
    "event_type_map": {"licensing": "LICENSE"},
    "status_map": {"active": "ACTIVE"},
}


def test_rights_file_reaches_each_program_through_the_workspace(tmp_path, demo_dir, normalizer):
    from bve.dealscreen.workspace import Workspace

    buyer = tmp_path / "buyer.yaml"
    shutil.copyfile(demo_dir / "buyer_tl1a_ibd.yaml", buyer)
    with buyer.open("a", encoding="utf-8") as f:
        f.write("\ntransaction:\n  encumbered_rights: deprioritize\n")
    ws = Workspace(tmp_path / "ws")
    ws.import_landscape(demo_dir / "landscape_200.csv", demo_dir / "profile_synthetic_vendor.yaml", buyer)
    rows = [  # SYN-0012: landscape says U.S. exclusively licensed; the rights file holds a China-only deal (E2)
        ["R1", "SYN-0012", "Licensing", "Chinaco", "Originco", "mainland China", "2026-03-01", "Active",
         "https://x.test/1", "China rights"],
        # SYN-0013: an accepted China-only deal and a rejected U.S. deal with an unreadable date (E3)
        ["R2", "SYN-0013", "Licensing", "Chinaco", "Originco", "mainland China", "2026-03-01", "Active",
         "https://x.test/2", "China rights"],
        ["R3", "SYN-0013", "Licensing", "Bigco", "Originco", "United States", "Q3 2025", "Active",
         "https://x.test/3", "U.S. rights"],
    ]
    rights = tmp_path / "deals.csv"
    with rights.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(RIGHTS_PROFILE["columns"].values()))
        w.writerows(rows)
    profile = tmp_path / "rights_profile.yaml"
    profile.write_text(yaml.safe_dump(RIGHTS_PROFILE), encoding="utf-8")
    imported = ws.import_rights(rights, profile)
    assert len(imported.events) == 2 and len(imported.rejected) == 1
    ws.screen(normalizer)
    by_external = {a.external_id: a.asset_id for a in ws.assets()}
    screens = {s["asset_id"]: s for s in ws.screening()["screens"]}

    e2 = screens[by_external["SYN-0012"]]["transaction"]
    assert e2["rights_position"] == rp.P_CONFLICTING and e2["tier"] == "RIGHTS_UNRESOLVED"
    e3 = screens[by_external["SYN-0013"]]["transaction"]
    assert e3["tier"] == "RIGHTS_UNRESOLVED" and any("rejected at import" in x for x in e3["reasons"])
    assert any("Correct rights row" in q for q in e3["diligence_questions"])
    # F1: "available; seeking a partner" in the landscape alone is undated, so never the availability tier
    tiers = {s["transaction"]["tier"] for s in screens.values()}
    assert "AVAILABILITY_STATED_UNVERIFIED" not in tiers
    f1 = screens[by_external["SYN-0004"]]["transaction"]
    assert f1["tier"] == "RIGHTS_UNRESOLVED" and any("not counted" in x for x in f1["reasons"])


def test_e2_an_analyst_rights_assertion_against_the_rights_file_is_a_conflict(tmp_path, demo_dir, normalizer):
    from bve.dealscreen.review import Action, ReviewerKind
    from bve.dealscreen.workspace import Workspace

    buyer = tmp_path / "buyer.yaml"
    shutil.copyfile(demo_dir / "buyer_tl1a_ibd.yaml", buyer)
    with buyer.open("a", encoding="utf-8") as f:
        f.write("\ntransaction:\n  encumbered_rights: deprioritize\n")
    ws = Workspace(tmp_path / "ws")
    ws.import_landscape(demo_dir / "landscape_200.csv", demo_dir / "profile_synthetic_vendor.yaml", buyer)
    rows = [  # both programs have an empty U.S.-rights cell; each licensor is the program's landscape originator
        ["R1", "SYN-0051", "Licensing", "Chinaco", "Corvane Bio", "mainland China", "2026-03-01", "Active",
         "https://x.test/1", "China rights"],
        ["R2", "SYN-0154", "Licensing", "Bigco", "Pellucid Pharma", "United States", "2026-03-01", "Active",
         "https://x.test/2", "U.S. rights"],
    ]
    rights = tmp_path / "deals.csv"
    with rights.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(RIGHTS_PROFILE["columns"].values()))
        w.writerows(rows)
    profile = tmp_path / "rights_profile.yaml"
    profile.write_text(yaml.safe_dump(RIGHTS_PROFILE), encoding="utf-8")
    ws.import_rights(rights, profile)
    ws.screen(normalizer)
    ids = {a.external_id: a.asset_id for a in ws.assets()}

    def txn(external: str) -> dict:
        return {s["asset_id"]: s for s in ws.screening()["screens"]}[ids[external]]["transaction"]

    assert txn("SYN-0051")["rights_position"] == rp.P_NOT_ENCUMBERED
    assert txn("SYN-0051")["tier"] == "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"
    assert txn("SYN-0154")["rights_position"] == rp.P_LICENSED
    decisions = {}
    for external, value in (("SYN-0051", "U.S. rights exclusively licensed to Otherco"),
                            ("SYN-0154", "U.S. rights available; seeking a partner")):
        decisions[external] = ws.decision_log().record(
            action=Action.ASSERT_FACT, subject_id=ids[external], new_state="ASSERTED", reviewer_id="analyst-1",
            rationale="press release", reviewer_kind=ReviewerKind.HUMAN,
            detail={"field": "us_rights", "value": value, "source_url": "https://x.test/pr",
                    "source_date": "2026-04-01", "evidence_span": value},
            context=ws.decision_context(normalizer))
    ws.screen(normalizer)
    for external in ("SYN-0051", "SYN-0154"):
        t = txn(external)
        assert t["rights_position"] == rp.P_CONFLICTING and t["tier"] == "RIGHTS_UNRESOLVED", (external, t)
        assert any("Which is current" in q for q in t["diligence_questions"])
    assert any("analyst" in x for x in txn("SYN-0051")["reasons"])
    # retracting the assertion restores the rights-file position
    ws.decision_log().record(action=Action.RETRACT_FACT, subject_id=decisions["SYN-0051"]["decision_id"],
                             new_state="RETRACTED", reviewer_id="analyst-1", rationale="wrong program",
                             reviewer_kind=ReviewerKind.HUMAN, context=ws.decision_context(normalizer))
    ws.screen(normalizer)
    assert txn("SYN-0051")["tier"] == "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"


# -- Output honesty (re-review section 4) ---------------------------------------------------------------------
def _txn(p, v) -> dict:
    return {"tier": v.tier, "reasons": v.reasons, "notes": v.notes, "rights_position": v.position,
            "rights_holder_per_evidence": v.holder, "owner_per_evidence": v.owner, "evidence": v.evidence,
            "stale": v.stale, "diligence_questions": v.questions}


def test_quotes_are_clipped_with_an_ellipsis_never_silently():
    from bve.dealscreen.rights_words import evidence_quote

    long = "The licensee receives rights in " + "x" * 400 + " worldwide outside of Greater China."
    assert evidence_quote({"quote": long}, 1000) == long
    clipped = evidence_quote({"quote": long}, 200)
    assert len(clipped) == 200 and clipped.endswith("…")
    assert evidence_quote({"quote": None}, 50) == ""


def test_workbook_evidence_names_the_rights_row_and_event_id():
    from bve.dealscreen.workbook import _rights_cells

    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2024-01-01")])
    cells = _rights_cells(_txn(p, view(p)))
    row = p.evidence[0]["row"]
    assert f"rights row {row};" in cells[3] and f"event {p.evidence[0]['event_id']}" in cells[3]


def test_memo_lines_use_words_cite_rows_and_quotes_and_say_stale_once():
    from bve.dealscreen.memo import _other_line, _transaction_line

    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2012-01-01"),
             ev(r.RIGHTS_RETURNED, grantee="Alpha", d="2015-01-01")])
    v = view(p)
    s = {"transaction_rank": 4, "program_name": "Prog-1", "company": "Origin Bio", "disposition": "ELIGIBLE",
         "asset_id": "a1", "transaction": _txn(p, v)}
    line = _transaction_line(s)
    for code in ("RIGHTS_UNRESOLVED", "RIGHTS_RETURNED_PER_EVIDENCE", "_PER_EVIDENCE"):
        assert code not in line
    assert "rights unresolved" in line and "rights returned per evidence (stale evidence)" in line
    assert all(f"rights row {e['row']}" in line for e in p.evidence) and '"quote' in line
    assert "rights evidence is stale; confirm it is current" not in line  # the position words already say it
    other = _other_line(s)
    assert "stale evidence" in other and "rights rows" in other and "_" not in other.split(":", 1)[1]


def test_memo_says_how_many_evidence_rows_are_not_shown():
    from bve.dealscreen.memo import _transaction_line

    p = pos([ev(r.LICENSE, grantee="Turnco", territory="worldwide", d="2024-01-01"),
             ev(r.ACQUISITION, grantee="Bigco", grantor="Turnco", d="2024-03-01"),
             ev(r.TERMINATION, grantee="Bigco", d="2025-01-01"),
             ev(r.RIGHTS_RETURNED, grantee="Bigco", d="2025-02-01")])
    assert len(p.evidence) == 4
    s = {"transaction_rank": 1, "program_name": "Prog-2", "company": "Origin Bio", "transaction": _txn(p, view(p))}
    assert "and 1 more evidence row(s) in the workbook" in _transaction_line(s)


def test_the_outcome_that_makes_a_conflict_counts_for_its_staleness():
    # an old grant and a fresh return that matches no recorded grant: the conflict is current
    p = pos([ev(r.LICENSE, grantee="Turnco", territory="worldwide", d="2022-05-04", src="2022-08"),
             ev(r.RIGHTS_RETURNED, grantee="Bigco", d="2024", src="2025-07")], as_of=date(2026, 10, 29))
    assert p.position == rp.P_CONFLICTING and not p.stale
    assert any("license to Turnco" in x and "may have ended" in x for x in p.reasons)


def test_k6_an_ended_co_development_names_both_partners_and_claims_no_owner():
    # revision 4 (review R1v3 N8): one partner's exit does not end the co-development; the other may hold all rights
    p = pos([ev(r.CO_DEVELOPMENT, grantee="Alpha", grantor="Beta", territory="worldwide", d="2024-01-01"),
             ev(r.TERMINATION, grantee="Beta", grantor=None, d="2025-01-01")])
    assert p.position == rp.P_SHARED and p.holders == ["Alpha", "Beta"]
    assert any("Beta ended its part of the co-development" in x for x in p.reasons)
    assert any("Does Alpha hold all US rights after Beta's exit" in q for q in p.questions)
    both = pos([ev(r.CO_DEVELOPMENT, grantee="Alpha", grantor="Beta", territory="worldwide", d="2024-01-01",
                   deal="DC"), ev(r.TERMINATION, grantee=None, grantor=None, d="2025-01-01", related="DC")])
    assert both.position == rp.P_RETURNED and both.holder is None
    assert any("Alpha and Beta" in x for x in both.reasons)
    assert any("owner not established" in q for q in both.questions)
    assert "specific: who holds the US rights now is not established" in both.top_tier_blockers
