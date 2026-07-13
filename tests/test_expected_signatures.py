"""PR-3 steps 1-3: expected-signature library loader, validation, and no-op surfacing.

These tests pin the *plumbing only*. There is no conviction producer yet, so the
central invariant is: nothing here moves a posterior — every surfaced row is
``scored=False``, including for an ``approved`` entry (which is only wired to
scoring in the gated step 4).
"""
from __future__ import annotations

from types import MappingProxyType

import pytest

from bve.config.expected_signatures import (
    ExpectedSignatures,
    describe_signature_availability,
)

_APPROVED_LIB = """
schema_version: expected_signatures_v1
entries:
  approved_mech:
    mechanism_tags: ["kras", "g12c"]
    review_status: approved
    expected_changes:
      - biomarker: "perk"
        direction: "down"
        informativeness: "proximal_target_engagement"
        required: true
"""


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure each test starts and ends on the real default library."""
    ExpectedSignatures.reset()
    yield
    ExpectedSignatures.reset()


def _write(tmp_path, text: str):
    path = tmp_path / "sig.yaml"
    path.write_text(text)
    return path


# --------------------------------------------------------------------------- #
# Loading / schema
# --------------------------------------------------------------------------- #

def test_default_library_approved_set_is_the_reviewed_five():
    """The approved set is exactly the five domain-reviewed proximal-engagement
    signatures (JAK + the four cleared 2026-07-03). Pinned so an accidental
    approval/de-approval is caught."""
    lib = ExpectedSignatures.get()
    assert lib.schema_version == "expected_signatures_v1"
    approved = lib.approved_entries()
    assert set(approved) == {
        "jak_stat_pathway",
        "cdk4_6_inhibition",
        "bcr_abl_inhibition",
        "egfr_inhibition",
        "her2_inhibition",
    }
    assert approved["jak_stat_pathway"]["expected_changes"][0]["biomarker"] == "pSTAT"
    assert approved["cdk4_6_inhibition"]["expected_changes"][0]["biomarker"] == "pRb"


def test_step3_signature_review_outcomes_are_pinned():
    """Records the 2026-07-03 domain-review decisions: four approved, VEGFR
    rejected. VEGFR must never be approved (no clean proximal marker -> false
    falsification risk); the four must not silently revert to draft."""
    lib = ExpectedSignatures.get()
    for key in ("cdk4_6_inhibition", "bcr_abl_inhibition", "egfr_inhibition", "her2_inhibition"):
        assert lib.entries[key]["review_status"] == "approved", f"{key} must stay approved"
    assert lib.entries["vegfr_inhibition"]["review_status"] == "rejected"
    assert "vegfr_inhibition" not in lib.approved_entries()


def test_entries_are_read_only():
    lib = ExpectedSignatures.get()
    assert isinstance(lib.entries, MappingProxyType)
    with pytest.raises(TypeError):
        lib.entries["x"] = {}  # type: ignore[index]


# --------------------------------------------------------------------------- #
# Validation (fail fast at the config boundary)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "bad",
    [
        "schema_version: wrong_version\nentries: {}\n",
        # bad review_status
        (
            "schema_version: expected_signatures_v1\nentries:\n  m:\n"
            "    mechanism_tags: ['a']\n    review_status: bogus\n"
            "    expected_changes:\n      - {biomarker: x, direction: up, "
            "informativeness: i, required: true}\n"
        ),
        # bad direction
        (
            "schema_version: expected_signatures_v1\nentries:\n  m:\n"
            "    mechanism_tags: ['a']\n    review_status: draft\n"
            "    expected_changes:\n      - {biomarker: x, direction: sideways, "
            "informativeness: i, required: true}\n"
        ),
        # empty mechanism_tags
        (
            "schema_version: expected_signatures_v1\nentries:\n  m:\n"
            "    mechanism_tags: []\n    review_status: draft\n"
            "    expected_changes:\n      - {biomarker: x, direction: up, "
            "informativeness: i, required: true}\n"
        ),
        # required not a bool
        (
            "schema_version: expected_signatures_v1\nentries:\n  m:\n"
            "    mechanism_tags: ['a']\n    review_status: draft\n"
            "    expected_changes:\n      - {biomarker: x, direction: up, "
            "informativeness: i, required: maybe}\n"
        ),
        # empty expected_changes
        (
            "schema_version: expected_signatures_v1\nentries:\n  m:\n"
            "    mechanism_tags: ['a']\n    review_status: draft\n"
            "    expected_changes: []\n"
        ),
    ],
)
def test_malformed_library_raises(tmp_path, bad):
    with pytest.raises(ValueError):
        ExpectedSignatures.reset(_write(tmp_path, bad))


# --------------------------------------------------------------------------- #
# No-op surfacing — the core invariant
# --------------------------------------------------------------------------- #

def test_surfacing_matches_by_mechanism_tag_and_is_never_scored():
    rows = describe_signature_availability(context_text="oral JAK1 inhibitor")
    assert rows, "expected jak_stat_pathway approved entry to surface"
    assert all(r["scored"] is False for r in rows)
    assert all(
        r["status_label"] == "approved signature — not yet wired to conviction updates"
        for r in rows
    )


def test_surfacing_matches_by_biomarker_hint():
    rows = describe_signature_availability(biomarker_hints=["pSTAT reduction"])
    assert any(r["signature_key"] == "jak_stat_pathway" for r in rows)
    assert all(r["scored"] is False for r in rows)


def test_no_match_returns_empty():
    rows = describe_signature_availability(
        context_text="unrelated mechanism", biomarker_hints=["nothing"]
    )
    assert rows == []


def test_approved_entry_still_not_scored_in_this_pr(tmp_path):
    ExpectedSignatures.reset(_write(tmp_path, _APPROVED_LIB))
    rows = describe_signature_availability(context_text="a KRAS G12C inhibitor")
    assert len(rows) == 1
    row = rows[0]
    assert row["review_status"] == "approved"
    # HARD RULE: no producer is wired, so even approved surfaces unscored.
    assert row["scored"] is False
    assert row["status_label"] == "approved signature — not yet wired to conviction updates"


# --------------------------------------------------------------------------- #
# Surfacing reaches the JSON science summary (presentation only)
# --------------------------------------------------------------------------- #

def test_science_summary_includes_untested_signature_status():
    from bve.intelligence.science_thesis import ScienceQuestion, ScienceThesis
    from bve.intelligence.science_thesis_summary import build_science_summary

    thesis = ScienceThesis(
        asset_id="asset-1",
        binding_science_question=ScienceQuestion.ENOUGH_DRUG,
        core_biological_hypothesis="a JAK-STAT pathway inhibitor",
        expected_biomarker_changes=["pSTAT decrease"],
    )
    summary = build_science_summary(thesis, modifier_applied=False)
    assert summary is not None
    status = summary.get("expected_signature_status")
    assert status, "expected the untested signature candidate to surface in the summary"
    assert all(r["scored"] is False for r in status)
