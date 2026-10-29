"""Cycle A1: fixes driven by the AI-simulated analyst run (INTERNAL DEVELOPMENT).

Criteria: research/dealscreen_product_program/analyst_simulation/PRIORITIZED_FIXES.md
"""

from __future__ import annotations

import pytest

from bve.dealscreen.facts import activity_status
from bve.dealscreen.indications import qualified_indication


# -- F1: activity status ---------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Registry: no recruiting gMG trial (COMPLETED)",
    "Not recruiting",
    "no active trial",
    "Not active in registry",
    "No ongoing development reported",
    "No longer active",                     # review A1-4
    "Active - not developed",
])
def test_f1_negated_activity_is_never_active(text: str) -> None:
    assert activity_status(text) != "ACTIVE"


@pytest.mark.parametrize("text, expected", [
    ("Active trial in registry", "ACTIVE"),
    ("Recruiting", "ACTIVE"),
    ("All registered gMG trials terminated or withdrawn", "INACTIVE"),
    ("Marketed in U.S. (FDA label lists myasthenia gravis)", "MARKETED"),
    ("", "UNKNOWN"),
])
def test_f1_activity_values(text: str, expected: str) -> None:
    assert activity_status(text) == expected


def test_f1_marketed_with_discontinued_is_inactive() -> None:
    # A stated discontinuation outranks a marketing word: never silently ACTIVE.
    assert activity_status("Marketed; development discontinued in gMG") == "INACTIVE"


# -- F2: qualified indication readings -------------------------------------------------
@pytest.mark.parametrize("text", [
    "Severe asthma",
    "Moderate to severe ulcerative colitis",
    "Generalized Myasthenia Gravis",
    "generalized myasthenia gravis",
    "Myasthenia Gravis, Generalized",
    "Generalized Myasthenia Gravis (gMG)",
    "Refractory Myasthenia Gravis",
    "Moderate to severe myasthenia gravis",
])
def test_f2_qualified_form_reads_as_parent(text: str) -> None:
    reading = qualified_indication(text)
    assert reading is not None
    assert text.casefold().endswith(reading["read_as"].casefold()) or "myasthenia" in text.casefold()
    assert reading["observed"] == text
    assert reading["rule"]


@pytest.mark.parametrize("text", [
    "Myasthenia Gravis",                    # resolves on its own: no derivation
    "Refractory Generalized Myasthenia Gravis",  # an NCIt concept itself
    "Ocular Myasthenia Gravis",             # qualifier not in the closed list
    "Acute myasthenia gravis",              # 'acute' deliberately excluded
    # review A1-2: generic parents and population / activity terms are never read
    "Chronic Disease", "Mild Disease", "Severe Cancer", "Active Cancer", "Chronic Infection",
    "Pediatric Epilepsy", "Adult myasthenia gravis", "Active Hepatitis B",
    "Non-small cell lung cancer",
    "Anti-myasthenia gravis",
    "AChR+ generalized myasthenia gravis",  # serostatus prefix is not stripped
    "Generalized nonsense disease",         # remainder not an NCIt concept
    "Generalized Myasthenia Gravis (Phase 3 cohort)",  # parenthetical is not an acronym
    "",
])
def test_f2_no_reading(text: str) -> None:
    assert qualified_indication(text) is None


def test_f2_subtype_request_not_satisfied_by_parent() -> None:
    # A buyer asking for the subtype must not be satisfied by the parent reading.
    from bve.se.ontology.indication_compatibility import compatibility

    reading = qualified_indication("Generalized Myasthenia Gravis")
    assert reading is not None
    assert compatibility("Refractory Generalized Myasthenia Gravis", reading["read_as"]) is None
    assert compatibility("myasthenia gravis", reading["read_as"]) is not None


# -- F3: the deal CLI fails closed on keys it does not read ----------------------------
def test_f3_unknown_top_level_keys_refused_with_hint() -> None:
    from bve.cli.dealscreen_value import ConfigKeyError, check_top_level_keys

    with pytest.raises(ConfigKeyError, match=r"asset\.discount_rate"):
        check_top_level_keys({"asset": {}, "trials": [], "discount_rate": 0.1})
    with pytest.raises(ConfigKeyError, match="deal_economics"):
        check_top_level_keys({"asset": {}, "deal_options": {}})
    check_top_level_keys({"asset": {}, "company": {}, "trials": [], "market_model": {}, "deal_economics": {}})


def test_f3_cli_exit_code_2_and_nothing_written(tmp_path) -> None:
    import yaml

    from bve.cli.dealscreen_value import main

    cfg = tmp_path / "c.yaml"
    cfg.write_text(yaml.safe_dump({"asset": {"id": "X"}, "trials": [], "discount_rate": 0.1}))
    out = tmp_path / "o.json"
    assert main(["--config", str(cfg), "--output-json", str(out)]) == 2
    assert not out.exists()


# -- F4: finalist counts never call AI or fixture rows "approved" by a human -----------
def test_f4_finalist_count_text() -> None:
    from bve.dealscreen.workbook import finalist_count_text

    ai = {f"a{i}": {"state": "CANDIDATE_NOT_APPROVED", "reviewer_kind": "AI_PREPARED"} for i in range(7)}
    text = finalist_count_text(ai)
    assert "approved by a human" not in text
    assert text.startswith("7 candidate not approved (AI_PREPARED)")
    mixed = {"h": {"state": "APPROVED", "reviewer_kind": "HUMAN"},
             "s": {"state": "APPROVED", "reviewer_kind": "SYNTHETIC_FIXTURE"}}
    text = finalist_count_text(mixed)
    assert "1 approved by a human analyst" in text
    assert "1 approved by SYNTHETIC_FIXTURE (not a human analyst)" in text
    assert finalist_count_text({}) == "No finalists recorded"


# -- F8: a vendor area label alone cannot exclude ---------------------------------------
def _builder_and_asset(area: str, indication: str):
    from bve.dealscreen.facts import FactBuilder
    from bve.dealscreen.mapping import MappingProfile
    from bve.dealscreen.models import LandscapeAsset, SourceClaim

    profile = MappingProfile.from_yaml(
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "examples" / "dealscreen_real" / "profile_public_landscape_v2.yaml")
    claims = [SourceClaim(claim_id=f"a:{f}:1", asset_id="a", field=f, value_as_written=v,
                          source_system="t", dataset_version="t", row_number=1, column=f)
              for f, v in (("therapeutic_area", area), ("indication", indication)) if v]
    asset = LandscapeAsset(asset_id="a", source_system="t", external_id="X", program_name="X",
                           aliases=[], company=None, row_numbers=[1], claims=claims)
    return FactBuilder(profile, lambda _t: None), asset


def _areas(area: str, indication: str, requested=frozenset({"AUTOIMMUNE"})):
    from bve.dealscreen.facts import ReviewInputs

    builder, asset = _builder_and_asset(area, indication)
    facts = builder.build(asset, ReviewInputs(), requested)
    found = [f.value for f in facts.facts if f.fact_type == "therapeutic_area"]
    return (found[0] if found else None), facts.unreadable


def test_f8_label_only_mismatch_gives_no_area_fact_and_says_why() -> None:
    value, notes = _areas("Neurology", "gMG")
    assert value is None
    assert any("cannot exclude" in n.get("reason", "") for n in notes)


def test_f8_readable_indication_keeps_previous_behaviour() -> None:
    value, _ = _areas("Neurology", "Myasthenia Gravis")
    assert value == ["AUTOIMMUNE", "NEUROLOGY"]
    value, _ = _areas("Oncology", "Breast cancer")  # indication-derived area can still exclude
    assert value and "AUTOIMMUNE" not in value


def test_f8_matching_label_still_passes_and_no_buyer_means_no_change() -> None:
    assert _areas("Autoimmune", "gMG")[0] == ["AUTOIMMUNE"]
    assert _areas("Neurology", "gMG", requested=None)[0] == ["NEUROLOGY"]


# -- F7 / F5: identity flags and holder wording in deliverables ------------------------
def test_f5_memo_never_calls_a_labeler_a_rights_holder() -> None:
    import inspect

    from bve.dealscreen import memo

    source = inspect.getsource(memo)
    assert "A U.S. rights holder is evidenced" not in source
    assert "an FDA labeler is" in source


def test_f2_assertion_validation_matches_import() -> None:
    # review A1-3: a value read on import must also be accepted as an assertion value
    from pathlib import Path

    from bve.dealscreen.facts import FactBuilder
    from bve.dealscreen.mapping import MappingProfile

    profile = MappingProfile.from_yaml(
        Path(__file__).resolve().parents[2] / "examples" / "dealscreen_real" / "profile_public_landscape_v2.yaml")
    builder = FactBuilder(profile, lambda _t: None)
    assert builder.readable("indication", "Generalized Myasthenia Gravis")
    assert not builder.readable("indication", "Chronic Disease")


def test_f8_area_comparison_is_canonical_and_unspecified_means_no_requirement() -> None:
    # review A1-1: canonical vs canonical; the UNSPECIFIED sentinel is "no requirement"
    from bve.se.ontology.therapeutic_areas import UNSPECIFIED

    assert _areas("Oncology", "gMG", requested=frozenset({"ONCOLOGY"}))[0] == ["ONCOLOGY"]
    assert _areas("Neurology", "gMG", requested=frozenset())[0] == ["NEUROLOGY"]
    assert UNSPECIFIED  # the sentinel exists; screening removes it before calling build()


def test_f3_handoff_config_passes_the_key_check() -> None:
    from pathlib import Path

    import yaml

    from bve.cli.dealscreen_value import check_top_level_keys
    from bve.dealscreen.models import LandscapeAsset
    from bve.dealscreen.valuation_handoff import build_config

    doc = yaml.safe_load((Path(__file__).resolve().parents[2] / "examples" / "dealscreen"
                          / "valuation_assumptions.yaml").read_text())
    ext, block = next(iter(doc["assets"].items()))
    asset = LandscapeAsset(asset_id="ds:x", source_system="t", external_id=ext, program_name="X",
                           aliases=[], company="C", row_numbers=[1], claims=[])
    deal = next(iter((block.get("deal_options") or {"d": {"upfront_cost_millions": 1.0}}).values()))
    for d in (None, deal):
        check_top_level_keys(build_config(asset, block, indication_label="UC", deal=d))
