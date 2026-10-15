"""BD opportunity triage (bd_opportunity_triage_v1.md): research categories, never availability."""

from __future__ import annotations

from bve.se.reporting.bd_brief import build_bd_brief, render_markdown
from bve.se.reporting.bd_triage import (
    ApprovalStatus,
    LabelSnapshot,
    NameKind,
    SponsorKind,
    TriageCategory,
    classify_name,
    classify_sponsors,
    triage,
)
from tests.se.test_bd_brief import _entry, _result, _run

LABELS = LabelSnapshot(
    {
        "retrieved": "2026-10-15",
        "labels": {
            "a": {
                "set_id": "a",
                "brand_name": ["KYMRIAH"],
                "generic_name": ["TISAGENLECLEUCEL"],
                "application_number": ["BLA125646"],
                "effective_time": "20250101",
                "url": "https://dailymed.example/a",
            },
            "b": {
                "set_id": "b",
                "brand_name": ["TECVAYLI"],
                "generic_name": ["TECLISTAMAB-CQYV"],
                "application_number": ["BLA761291"],
                "effective_time": "20250101",
                "url": "https://dailymed.example/b",
            },
            "c1": {
                "set_id": "c1",
                "brand_name": ["Duo"],
                "generic_name": ["ALPHAMAB"],
                "application_number": ["BLA1"],
                "url": "u1",
            },
            "c2": {
                "set_id": "c2",
                "brand_name": ["Duo"],
                "generic_name": ["BETAMAB"],
                "application_number": ["BLA2"],
                "url": "u2",
            },
        },
    }
)


def _t(name, sponsors="Example Therapeutics, Inc.", authority=None, reasons=()):
    return triage(
        name=name,
        authority_name=authority,
        sponsors=sponsors,
        review_reasons=reasons,
        labels=LABELS,
    )


def test_known_us_approval_is_an_approved_reference_not_excluded():
    t = _t("KYMRIAH")
    assert t.category is TriageCategory.APPROVED_REFERENCE
    assert t.approval is ApprovalStatus.US_LABEL_FOUND
    assert "BLA125646" in t.approval_basis and "US only" in t.approval_basis


def test_authority_name_and_biologic_suffix_match_exactly():
    assert _t("tisa-cel", authority="TISAGENLECLEUCEL").approval is ApprovalStatus.US_LABEL_FOUND
    assert _t("teclistamab").approval is ApprovalStatus.US_LABEL_FOUND


def test_no_label_is_unknown_never_not_approved():
    t = _t("ABC-123")
    assert t.category is TriageCategory.NAMED_INVESTIGATIONAL
    assert t.approval is ApprovalStatus.UNKNOWN
    assert "not evidence of non-approval" in t.approval_basis


def test_loose_or_partial_names_do_not_match_labels():
    assert (
        _t("Kymriah-like CAR-T cells", sponsors="City Hospital").approval is ApprovalStatus.UNKNOWN
    )
    assert _t("tisagen").approval is ApprovalStatus.UNKNOWN


def test_ambiguous_product_name_is_conflicting():
    t = _t("Duo")
    assert t.approval is ApprovalStatus.CONFLICTING
    assert t.category is TriageCategory.UNKNOWN_OR_CONFLICTING


def test_academic_construct_and_commercial_descriptive_name():
    assert (
        _t("anti-CD19/BCMA CAR T cells", sponsors="Changhai Hospital").category
        is TriageCategory.ACADEMIC_CONSTRUCT
    )
    assert (
        _t(
            "allogeneic CAR-T targeting CD19 and BCMA", sponsors="Example Biotechnology Co., Ltd."
        ).category
        is TriageCategory.INSUFFICIENTLY_IDENTIFIED
    )


def test_non_products_and_class_labels_are_insufficiently_identified():
    for name in ("Biospecimen Collection", "Allo-HSCT Protocol", "autoleucel", "CAR-T"):
        assert _t(name).category is TriageCategory.INSUFFICIENTLY_IDENTIFIED, name
    assert (
        _t(
            "CART19", reasons=("Nominated name 'CART19' denotes a class of therapies rather",)
        ).category
        is TriageCategory.INSUFFICIENTLY_IDENTIFIED
    )


def test_name_shapes():
    assert classify_name("ALLO-501A")[0] is NameKind.NAMED_PRODUCT
    assert classify_name("anbalcabtagene autoleucel")[0] is NameKind.NAMED_PRODUCT
    assert classify_name("Breyanzi")[0] is NameKind.NAMED_PRODUCT
    assert classify_name("CD19 CAR-T cells")[0] is not NameKind.NAMED_PRODUCT


def test_sponsor_is_an_organisation_type_never_ownership():
    assert classify_sponsors("Allogene Therapeutics") is SponsorKind.COMMERCIAL
    assert classify_sponsors("Zhejiang University") is SponsorKind.ACADEMIC
    assert classify_sponsors(None) is SponsorKind.UNKNOWN
    assert "not ownership" in _t("ABC-123").reasons[1]


def test_brief_overview_never_claims_rights_and_keeps_unverified_poc_label():
    gates = [("target.expression", "PASS"), ("evidence.human_poc", "PASS")]
    brief = build_bd_brief(
        _run(
            [_entry(disposition="ELIGIBLE", target_status="UNRESOLVED")],
            result=_result(gates=gates),
        ),
        labels=LABELS,
    )
    card = brief.candidates[0]
    assert card.eligibility == "Engine gates pass; human-PoC unverified (not confirmed eligibility)"
    md = render_markdown(brief)
    assert "## BD opportunity overview" in md
    assert "Ownership is never established" in md
    assert "available for licens" not in md.lower()


def test_named_products_are_tagged_with_target_confirmation():
    brief = build_bd_brief(
        _run(
            [_entry("asset:a", "ABC-123"), _entry("asset:b", "XYZ-456", target_status="UNRESOLVED")]
        ),
        labels=LABELS,
    )
    named = next(v for k, v in brief.overview.items() if k.startswith("Named product"))
    assert named == ("ABC-123 [target confirmed: CD19]", "XYZ-456 [target unconfirmed]")
