"""Reporting-only safety contracts; no scientific qualification is changed."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from bve.se.reporting.bd_brief import (
    Assessed,
    CandidateCard,
    EvidenceStatus,
    ResearchFollowup,
    _h_card,
    _md_card,
)
from bve.se.reporting.research_followup import attach_followup, load_followup

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "research/se_lead_verification_v1"
DAY = date(2026, 10, 24)


def card(name="Example", asset_id="example"):
    unknown = Assessed(value=None, status=EvidenceStatus.UNKNOWN, basis="No engine evidence")
    return CandidateCard(
        asset_id=asset_id,
        name=name,
        position=3,
        eligibility="REVIEW",
        disposition="NEEDS_REVIEW",
        why="existing run",
        company=unknown,
        target=unknown,
        modality=unknown,
        stage=unknown,
        human_efficacy=unknown,
        failed_requirements=("human_poc",),
        conflicts=("existing conflict",),
    )


def followup(**updates):
    pointer = {
        "id": "company",
        "url": "https://example.org/primary",
        "path": "raw/a.txt",
        "file_sha256": "a" * 64,
        "selection_sha256": "b" * 64,
        "start": 0,
        "end": 5,
    }
    supported = {
        "value": "Acquired program",
        "status": "SUPPORTED",
        "basis": "Manual audit",
        "sources": [{"label": "company", "url": pointer["url"]}],
    }
    data = {
        "asset_id": "example",
        "name": "Example",
        "observed_on": DAY,
        "verified_on": DAY,
        "display_as_of": DAY,
        "verification": "Manual implementing-agent review",
        "record_sha256": "c" * 64,
        "ledger_sha256": "d" * 64,
        "record_locator": "leads.json",
        "ledger_locator": "evidence.json",
        "evidence": [pointer],
        "facts": {"company_relationship": supported},
        "commercial_context": "ACQUIRED_PROGRAM",
    }
    data.update(updates)
    return ResearchFollowup.model_validate(data)


def test_acquisition_never_supplies_rights_or_availability():
    r = followup()
    assert r.commercial_context == "ACQUIRED_PROGRAM"
    for key in ("territorial_rights", "availability", "identity", "development"):
        assert r.facts[key].status == EvidenceStatus.UNKNOWN
        assert r.facts[key].value is None
    assert r.research_category == "UNKNOWN"


def test_attachment_preserves_all_engine_fields_and_serialization():
    original = card()
    old = original.model_dump()
    new = attach_followup(original, followup())
    assert "research_followup" not in old
    assert {k: v for k, v in new.model_dump().items() if k != "research_followup"} == old
    assert original.model_dump() == old
    assert CandidateCard.model_validate_json(new.model_dump_json()) == new
    assert "Manual research follow-up" in _h_card(new)
    assert "Manual research follow-up" not in _h_card(original)
    assert _h_card(new) == _h_card(new)
    assert _md_card(new) == _md_card(new)


@pytest.mark.parametrize("changes", [{"name": "EXAMPLE"}, {"asset_id": "other"}])
def test_no_alias_or_id_inference(changes):
    with pytest.raises(ValidationError, match="exact display name"):
        attach_followup(card(), followup(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"display_as_of": date(2026, 10, 23)},
        {"verified_on": date(2026, 10, 23)},
        {"verified_on": date(2026, 10, 25)},
    ],
)
def test_dates_cannot_backdate_manual_verification(changes):
    with pytest.raises(ValidationError, match="observation"):
        followup(**changes)


@pytest.mark.parametrize("status", ["SUPPORTED", "UNVERIFIED", "UNKNOWN"])
def test_unsourced_assertions_never_display_as_known(status):
    r = followup(
        facts={
            "availability": {
                "value": "Available globally",
                "status": status,
                "basis": "No documentation",
                "sources": [],
            }
        }
    )
    assert r.facts["availability"].value is None
    assert r.facts["availability"].status == EvidenceStatus.UNKNOWN
    assert "Available globally" not in _h_card(attach_followup(card(), r))


@pytest.mark.parametrize("status", ["SUPPORTED", "UNVERIFIED"])
def test_manual_efficacy_never_confirms_poc(status):
    data = followup().model_dump()
    fact = data["facts"]["company_relationship"]
    fact.update(value="Claimed efficacy", status=status)
    data["facts"] = {"human_evidence": fact}
    new = attach_followup(card(), ResearchFollowup.model_validate(data))
    assert new.research_followup.facts["human_evidence"].status == EvidenceStatus.UNVERIFIED
    assert new.human_efficacy.status == EvidenceStatus.UNKNOWN
    assert new.failed_requirements == ("human_poc",)


def test_source_pointer_mismatch_downgrades_and_html_escapes():
    r = followup(evidence=[])
    assert r.facts["company_relationship"].status == EvidenceStatus.UNKNOWN
    assert r.commercial_context == "UNKNOWN"
    r = followup(next_actions=("<script>alert(1)</script>",))
    rendered = _h_card(attach_followup(card(), r))
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered


def test_real_records_preserve_pointers_and_unknowns():
    for name in ("HXN-1031", "cizutamig"):
        r = load_followup(
            SOURCE / "leads.json",
            SOURCE / "evidence.json",
            asset_id="manual",
            name=name,
            verified_on=DAY,
            display_as_of=DAY,
            verification="Prior manual review, not independent BD review",
        )
        lead = next(
            x for x in json.loads((SOURCE / "leads.json").read_text())["leads"] if x["name"] == name
        )
        assert {k: v.model_dump(mode="json") for k, v in r.facts.items()} == {
            k: Assessed.model_validate(v).model_dump(mode="json") for k, v in lead["facts"].items()
        }
        assert r.evidence
        assert r.record_sha256 == hashlib.sha256((SOURCE / "leads.json").read_bytes()).hexdigest()
        assert r.facts["territorial_rights"].status == EvidenceStatus.UNKNOWN
        assert r.facts["availability"].status == EvidenceStatus.UNKNOWN


def test_package_is_deterministic_custodied_and_unreviewed(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "review_demo", ROOT / "research/se_reviewer_pilot_v1/generate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    a, b = tmp_path / "a", tmp_path / "b"
    module.generate(a)
    module.generate(b)
    assert {p.name: p.read_bytes() for p in a.iterdir()} == {
        p.name: p.read_bytes() for p in b.iterdir()
    }
    manifest = json.loads((a / "MANIFEST.json").read_text())
    assert all(hashlib.sha256((a / k).read_bytes()).hexdigest() == v for k, v in manifest.items())
    assert (a / "BRIEF.md").read_bytes() == (SOURCE / "BRIEF.md").read_bytes()
    status = json.loads((a / "review_status.json").read_text())
    assert status["independent_bd_review"] == "PENDING"
    assert status["response_count"] == 0 and status["usefulness"] is None
    assert status["original_card_fields_unchanged"]
    with pytest.raises(FileExistsError):
        module.generate(a)


def test_manual_category_does_not_make_unsupported_approval_known():
    supported = followup().facts["company_relationship"]
    r = followup(
        research_category="APPROVED_COMPARATOR",
        facts={"identity": supported, "development": supported},
    )
    assert r.research_category == "UNKNOWN"
    assert r.facts["approval"].status == EvidenceStatus.UNKNOWN


def test_unrecognized_manual_categories_are_rejected():
    with pytest.raises(ValidationError):
        followup(commercial_context="AVAILABLE_FOR_ACQUISITION")
