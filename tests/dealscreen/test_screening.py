"""Screening reuses the S&E gate engine; rights stay independent of science."""

from __future__ import annotations

import json
from collections import defaultdict

import pytest

from bve.dealscreen.buyer import BuyerSpec
from bve.dealscreen.commercial import (
    AVAILABLE,
    CONFLICTING,
    ENCUMBERED,
    UNKNOWN,
    assess,
    rights_status,
)
from bve.dealscreen.facts import FactBuilder, ReviewInputs, mechanism_direction
from bve.dealscreen.identity import identity_flags
from bve.dealscreen.importer import import_landscape
from bve.dealscreen.mapping import MappingProfile
from bve.dealscreen.screening import screen_landscape


@pytest.fixture(scope="module")
def setup(demo_dir, normalizer):
    profile = MappingProfile.from_yaml(demo_dir / "profile_synthetic_vendor.yaml")
    spec = BuyerSpec.from_yaml(demo_dir / "buyer_tl1a_ibd.yaml")
    result = import_landscape(demo_dir / "landscape_200.csv", profile)
    truth = json.loads((demo_dir / "ground_truth.json").read_text())["programs"]
    return profile, spec, result, truth


@pytest.fixture(scope="module")
def screened(setup, normalizer):
    profile, spec, result, truth = setup
    out = screen_landscape(result.assets, spec, FactBuilder(profile, normalizer),
                           identity_flags=identity_flags(result.assets))
    ext = {a.asset_id: a.external_id for a in result.assets}
    return out, ext, truth, result


def test_no_false_exclusions_or_false_eligibles_against_synthetic_truth(screened):
    out, ext, truth, _ = screened
    wrong = defaultdict(list)
    for s in out.screens:
        expected = truth[ext[s.asset_id]]["expected_disposition"]
        if expected != s.disposition:
            wrong[(expected, s.disposition)].append(truth[ext[s.asset_id]]["archetype"])
    assert ("ELIGIBLE", "EXCLUDED") not in wrong and ("UNRESOLVED", "EXCLUDED") not in wrong
    assert not any(actual == "ELIGIBLE" for (_, actual) in wrong)
    # The only disagreements are the declared conservative cases: registry text cannot
    # establish indication incompatibility, and "IL-23" is not a resolvable target symbol.
    assert set(wrong) <= {("EXCLUDED", "UNRESOLVED")}
    assert set(wrong[("EXCLUDED", "UNRESOLVED")]) <= {"tl1a_non_ibd", "other_target_ibd"}


@pytest.mark.parametrize(("archetype", "requirement", "status"), [
    ("dr3_agonist_antibody", "biology.mechanism_direction", "FAIL"),
    ("tl1a_cell_therapy", "modality.required", "FAIL"),
    ("tl1a_small_molecule", "modality.required", "FAIL"),
    ("tl1a_preclinical", "evidence.phase_constraint", "FAIL"),
    ("missing_target_researchable", "target.expression", "UNKNOWN"),
    ("undisclosed_target", "target.expression", "UNKNOWN"),
    ("unreadable_modality", "modality.required", "UNKNOWN"),
    ("conflicting_phase", "evidence.phase_constraint", "UNKNOWN"),
    ("conflicting_target", "target.expression", "UNKNOWN"),
    ("in_scope_bispecific", "target.expression", "PASS"),
])
def test_gate_decisions_per_case(screened, archetype, requirement, status):
    out, ext, truth, _ = screened
    cases = [s for s in out.screens if truth[ext[s.asset_id]]["archetype"] == archetype]
    assert cases
    assert {s.gate_status(requirement) for s in cases} == {status}


def test_every_pass_or_fail_cites_an_imported_row_and_column(screened):
    out, _, _, result = screened
    claims = {c.claim_id: c for a in result.assets for c in a.claims}
    for s in out.screens:
        for d in s.decisions:
            if d["status"] in ("PASS", "FAIL"):
                assert d["supporting_or_contradictory_claim_ids"]
                for cid in d["supporting_or_contradictory_claim_ids"]:
                    assert claims[cid].row_number and claims[cid].column


def test_conflict_carries_both_claims(screened):
    out, ext, truth, _ = screened
    s = next(s for s in out.screens if truth[ext[s.asset_id]]["archetype"] == "conflicting_phase")
    decision = next(d for d in s.decisions if d["requirement_id"] == "evidence.phase_constraint")
    assert len(decision["supporting_or_contradictory_claim_ids"]) == 2
    assert decision["next_action"] == "Reconcile the conflicting claims."


def test_funnel_reconciles_and_ranking_is_only_within_disposition(screened):
    out, _, _, result = screened
    f = out.funnel
    assert f["eligible"] + f["unresolved"] + f["excluded"] == len(result.assets) == f["assets_screened"]
    assert all(s.rank is None for s in out.screens if s.disposition == "EXCLUDED")
    ranks = sorted(s.rank for s in out.screens if s.disposition == "ELIGIBLE")
    assert ranks == list(range(1, f["eligible"] + 1))


def test_scientific_disposition_independent_of_rights(setup, normalizer, screened):
    out, _, _, result = screened
    eligible_rights = {s.commercial.us_rights_status for s in out.screens if s.disposition == "ELIGIBLE"}
    assert UNKNOWN in eligible_rights and ENCUMBERED in eligible_rights
    profile, spec, _, _ = setup
    # Rejecting every rights claim changes rights status, never a disposition.
    rights_ids = frozenset(c.claim_id for a in result.assets for c in a.claims_for("us_rights"))
    again = screen_landscape(result.assets, spec, FactBuilder(profile, normalizer),
                             review=ReviewInputs(rejected_claim_ids=rights_ids))
    assert [s.disposition for s in again.screens] == [s.disposition for s in out.screens]
    assert {s.commercial.us_rights_status for s in again.screens} == {UNKNOWN}


@pytest.mark.parametrize(("text", "status"), [
    ("", UNKNOWN), ("Not reported", UNKNOWN), ("Unpartnered", UNKNOWN), ("No partner recorded", UNKNOWN),
    ("U.S. rights available; company seeking a partner", AVAILABLE),
    ("U.S. rights exclusively licensed to X", ENCUMBERED),
    ("Ex-US rights partnered with X; U.S. rights not reported", UNKNOWN),
    ("Rights not available", "NOT_AVAILABLE_PER_SOURCE"),
])
def test_rights_reading_never_infers_availability_from_silence(text, status):
    assert rights_status(text) == status


def test_available_alongside_a_partnership_needs_a_human(setup):
    _, _, result, _ = setup
    asset = next(a for a in result.assets if a.claims_for("us_rights"))
    from bve.dealscreen.models import SourceClaim

    claims = [c for c in asset.claims if c.field not in {"us_rights", "partnerships"}] + [
        SourceClaim(**{**asset.claims[0].model_dump(), "claim_id": "x1", "field": "us_rights",
                       "value_as_written": "U.S. rights available"}),
        SourceClaim(**{**asset.claims[0].model_dump(), "claim_id": "x2", "field": "partnerships",
                       "value_as_written": "Co-development with Y"}),
    ]
    assert assess(asset.model_copy(update={"claims": claims}), questions=[]).us_rights_status == CONFLICTING


@pytest.mark.parametrize(("text", "direction"), [
    ("TL1A antagonist; blocks TL1A-DR3 binding", "ANTAGONIST"),
    ("DR3 agonist antibody (Treg expansion)", "AGONIST"),
    ("Neutralizing antibody", "ANTAGONIST"),
    ("S1P1 receptor modulator", None),
    ("partial agonist and antagonist", None),
])
def test_mechanism_direction(text, direction):
    assert mechanism_direction(text) == direction


def test_screening_is_deterministic(setup, normalizer):
    profile, spec, result, _ = setup
    a = screen_landscape(result.assets, spec, FactBuilder(profile, normalizer)).to_dict()
    b = screen_landscape(result.assets, spec, FactBuilder(profile, normalizer)).to_dict()
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
