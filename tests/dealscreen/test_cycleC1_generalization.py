"""Cycle C1: generic fixes from the CLDN18.2 comparison (AI-SIMULATED analysts; INTERNAL DEVELOPMENT).

Criteria: research/dealscreen_comparison_v1/FIXES_C1.md (X1-X5). Nothing here is specific to
CLDN18.2; the cases cover other targets and diseases on purpose.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bve.dealscreen.agent import OfflineEvidenceProvider, parse_document_date
from bve.dealscreen.commercial import AVAILABLE, ENCUMBERED, OPTION, RETURNED, rights_status
from bve.dealscreen.indications import indication_readings
from bve.dealscreen.targets import isoform_base
from bve.dealscreen.transaction import TransactionPreferences, assess_transaction


# -- X1 isoform target names ------------------------------------------------------------
@pytest.mark.parametrize("text, base", [
    ("Claudin 18.2", "Claudin 18"), ("CLDN18.2", "CLDN18"), ("claudin 18 isoform 2", "claudin 18"),
    ("FGFR2 isoform 3", "FGFR2"), ("PD-1", None), ("CD3", None), ("IL-23", None), ("HER2", None),
])
def test_x1_isoform_base(text, base):
    assert isoform_base(text) == base


def test_x1_fact_builder_reads_isoform_and_discloses():
    from bve.dealscreen.facts import FactBuilder
    from bve.dealscreen.mapping import MappingProfile

    profile = MappingProfile.from_yaml(Path(__file__).resolve().parents[2] / "examples" / "dealscreen_real"
                                       / "profile_public_landscape_v2.yaml")
    builder = FactBuilder(profile, {"CLDN18": "CLDN18", "FGFR2": "FGFR2"}.get)
    assert builder._targets("CLDN18.2; FGFR2 isoform 3") == ["CLDN18", "FGFR2"]
    readings = builder.target_readings("CLDN18.2")
    assert readings and readings[0]["read_as"] == "CLDN18" and "isoform not distinguished" in readings[0]["rule"]
    assert builder.readable("target", "CLDN18.2")
    assert builder._targets("CLDN99.2") is None  # unknown gene stays unreadable


# -- X2 partial dates ----------------------------------------------------------------------
@pytest.mark.parametrize("raw, parsed, written", [
    ("2016-10", None, "2016-10"), ("2016", None, "2016"), ("garbage", None, "garbage"),
    ("2024-08-01", "2024-08-01", None), (None, None, None), ("", None, None),
])
def test_x2_parse_document_date(raw, parsed, written):
    d, w = parse_document_date(raw)
    assert (d.isoformat() if d else None) == parsed and w == written


def test_x2_partial_date_library_does_not_crash(tmp_path):
    lib = tmp_path / "lib.json"
    lib.write_text(json.dumps({"documents": [
        {"url": "https://example.org/a", "title": "t", "date": "2016-10", "text": "x"}]}))
    provider = OfflineEvidenceProvider(lib, lambda _t: None)
    assert provider.documents[0].document_date is None and provider.documents[0].date_as_written == "2016-10"


# -- X3 indication reading v2 -----------------------------------------------------------------
@pytest.mark.parametrize("text, expected", [
    ("Gastric or Gastroesophageal Junction Adenocarcinoma",
     {"Gastric Adenocarcinoma", "Gastroesophageal Junction Adenocarcinoma"}),
    ("Relapsed or Refractory Multiple Myeloma", {"Multiple Myeloma"}),   # qualifier coordination
    ("Ulcerative Colitis (UC)", {"Ulcerative Colitis"}),
    ("Severe asthma", {"Asthma"}),                     # v1 still applies
])
def test_x3_readings(text, expected):
    assert {r["read_as"] for r in indication_readings(text)} == expected


@pytest.mark.parametrize("text", [
    "Gastric Cancer", "Solid Tumor", "Advanced Solid Tumors", "Pancreatic Cancer", "Breast or Ovarian Cancer",
    "Non-small Cell Lung Cancer", "Unresectable or Metastatic Gastric or Gastroesophageal Junction Adenocarcinoma",
    "Chronic Disease", "Myasthenia Gravis",
])
def test_x3_no_reading(text):
    assert indication_readings(text) == []


def test_x3_every_reading_is_disclosed_with_rule():
    for r in indication_readings("CLDN18.2-positive Adenocarcinoma of the Gastroesophageal Junction"):
        assert r["observed"] and r["read_as"] and "biomarker subset" in r["rule"]


# -- X4 rights vocabulary -------------------------------------------------------------------
@pytest.mark.parametrize("text, status", [
    ("Merck has returned global rights to the candidate", RETURNED),
    ("BMS terminated its license agreement", RETURNED),
    ("obtained an option to license ex-China rights", OPTION),
    ("exercised its option to license", ENCUMBERED),
    ("exclusively licensed to a partner", ENCUMBERED),
    ("seeking a partner for U.S. rights", AVAILABLE),
])
def test_x4_rights_status(text, status):
    assert rights_status(text) == status


def test_x4_returned_and_option_are_never_available():
    assert RETURNED != AVAILABLE and OPTION != AVAILABLE


# -- X5 transaction view ----------------------------------------------------------------------
PREFS = TransactionPreferences(marketed="exclude", deprioritized_holders=["BigPharma Inc"],
                               encumbered_rights="deprioritize")


def _view(**over):
    base = {"market_status": None, "rights_status": "UNKNOWN", "rights_holder": None,
            "company": "Small Bio", "identity_twins": []}
    return assess_transaction(PREFS, **(base | over))


def test_x5_tiers_and_reasons():
    assert _view().tier == "OPEN" and "availability not evidenced" in _view().reasons[0]
    assert _view(market_status="US_MARKETED").tier == "EXCLUDED_BY_BUYER_PREFERENCE"
    v = _view(company="BigPharma Inc (sponsor)")
    assert v.tier == "DEPRIORITIZED" and "not a rights statement" in v.reasons[0]
    v = _view(rights_holder="BigPharma Inc", company="Small Bio")
    assert "per cited evidence" in v.reasons[0]
    assert _view(rights_status=OPTION).tier == "DEPRIORITIZED"
    assert "returned" in " ".join(_view(rights_status=RETURNED).notes)
    assert _view(rights_status=RETURNED).tier == "OPEN"  # returned is not availability, nor an obstacle


def test_x5_not_declared_changes_nothing():
    v = assess_transaction(None, market_status="US_MARKETED", rights_status=ENCUMBERED, rights_holder="X",
                           company="X", identity_twins=["Y"])
    assert v.tier == "NOT_DECLARED" and v.reasons == []


REAL = Path(__file__).resolve().parents[2] / "examples" / "dealscreen_real"


def test_x5_transaction_view_never_changes_gates_or_scientific_rank(tmp_path, monkeypatch):
    import yaml

    from bve.dealscreen.workspace import Workspace
    from bve.se.ontology.targets import reset_resolver_cache

    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "absent"))
    reset_resolver_cache()
    norm = {"fcgrt": "FCGRT", "c5": "C5", "fcrn": "FCGRT"}.get

    def run(buyer: Path, name: str) -> dict:
        ws = Workspace(tmp_path / name)
        ws.import_landscape(REAL / "landscape_fcrn_gmg_v2.csv", REAL / "profile_public_landscape_v2.yaml", buyer)
        return {s["asset_id"]: s for s in ws.screen(lambda t: norm(t.strip().casefold())).to_dict()["screens"]}

    plain = run(REAL / "buyer_fcrn_gmg.yaml", "plain")
    doc = yaml.safe_load((REAL / "buyer_fcrn_gmg.yaml").read_text())
    doc["transaction"] = {"marketed": "exclude", "deprioritized_holders": ["Janssen"]}
    declared_path = tmp_path / "buyer_tx.yaml"
    declared_path.write_text(yaml.safe_dump(doc))
    declared = run(declared_path, "declared")
    for asset_id, s in plain.items():
        d = declared[asset_id]
        assert (s["disposition"], s["rank"], s["decisions"]) == (d["disposition"], d["rank"], d["decisions"])
    tiers = {d["program_name"]: d["transaction"]["tier"] for d in declared.values() if d["disposition"] == "ELIGIBLE"}
    assert tiers["Nipocalimab"] == "EXCLUDED_BY_BUYER_PREFERENCE"   # U.S.-marketed per source
    assert all(s["transaction"]["tier"] == "NOT_DECLARED" for s in plain.values())
    reset_resolver_cache()


# -- X6 partial target set as a positive witness only ---------------------------------------
def _facts(text: str, witness):
    from bve.dealscreen.facts import FactBuilder, ReviewInputs
    from bve.dealscreen.mapping import MappingProfile
    from bve.dealscreen.models import LandscapeAsset, SourceClaim

    profile = MappingProfile.from_yaml(REAL / "profile_public_landscape_v2.yaml")
    claim = SourceClaim(claim_id="a:target:1", asset_id="a", field="target", value_as_written=text,
                        source_system="t", dataset_version="t", row_number=1, column="Target")
    asset = LandscapeAsset(asset_id="a", source_system="t", external_id="X", program_name="X", aliases=[],
                           company=None, row_numbers=[1], claims=[claim])
    facts = FactBuilder(profile, {"CLDN18": "CLDN18", "EGFR": "EGFR"}.get).build(
        asset, ReviewInputs(), None, witness)
    return next((f.value for f in facts.facts if f.fact_type == "construct_target_set"), None), facts.unreadable


def test_x6_partial_set_is_a_witness_of_a_requested_target():
    value, notes = _facts("CLDN18.2; CD3", frozenset({"CLDN18"}))
    assert value == ["CLDN18"] and any("positive witness" in n.get("reason", "") for n in notes)


def test_x6_partial_set_without_requested_target_emits_nothing():
    assert _facts("EGFR; CD3", frozenset({"CLDN18"}))[0] is None   # could otherwise FAIL wrongly
    assert _facts("CLDN18.2; CD3", None)[0] is None                 # no witness (e.g. EXACT_COMBINATION)
    assert _facts("EGFR", frozenset({"CLDN18"}))[0] == ["EGFR"]      # fully readable: unchanged


# -- regressions from the C1 code review (AI reviewer) ------------------------------------------
@pytest.mark.parametrize("text", ["IL-1.2", "IL-2.5", "TGF-beta 1.2", "p53.1", "GPRC5D 1.5"])
def test_review_c1_3_dose_and_variant_strings_are_not_isoforms(text):
    assert isoform_base(text) is None


def test_review_c1_3_isoform_consistency():
    from bve.dealscreen.targets import isoform_consistent, requested_isoforms

    wanted = requested_isoforms([("CLDN18", "Claudin 18.2")])
    assert wanted == {"CLDN18": "2"}
    assert not isoform_consistent("CLDN18.1", "CLDN18", wanted)        # different isoform: not read
    assert isoform_consistent("Claudin 18.2", "CLDN18", wanted)
    assert not isoform_consistent("Claudin 1.2", "CLDN7", {})           # gene number must match


def test_review_c1_1_all_operator_needs_every_target():
    assert _facts_all("CLDN18.2; CD3", frozenset({"CLDN18", "CD3E"})) is None   # would have been a FAIL
    assert _facts_all("CLDN18.2; CD3", frozenset({"CLDN18"})) == ["CLDN18"]


def _facts_all(text, witness):
    from bve.dealscreen.facts import FactBuilder, ReviewInputs
    from bve.dealscreen.mapping import MappingProfile
    from bve.dealscreen.models import LandscapeAsset, SourceClaim

    profile = MappingProfile.from_yaml(REAL / "profile_public_landscape_v2.yaml")
    claim = SourceClaim(claim_id="a:target:1", asset_id="a", field="target", value_as_written=text,
                        source_system="t", dataset_version="t", row_number=1, column="Target")
    asset = LandscapeAsset(asset_id="a", source_system="t", external_id="X", program_name="X", aliases=[],
                           company=None, row_numbers=[1], claims=[claim])
    facts = FactBuilder(profile, {"CLDN18": "CLDN18"}.get).build(asset, ReviewInputs(), None, witness, True)
    return next((f.value for f in facts.facts if f.fact_type == "construct_target_set"), None)


def test_review_c1_2_contradictory_partial_claims_emit_nothing():
    from bve.dealscreen.facts import FactBuilder, ReviewInputs
    from bve.dealscreen.mapping import MappingProfile
    from bve.dealscreen.models import LandscapeAsset, SourceClaim

    profile = MappingProfile.from_yaml(REAL / "profile_public_landscape_v2.yaml")
    claims = [SourceClaim(claim_id=f"a:target:{i}", asset_id="a", field="target", value_as_written=v,
                          source_system="t", dataset_version="t", row_number=1, column="Target")
              for i, v in enumerate(["CLDN18.2; CD3", "EGFR; foo"])]
    asset = LandscapeAsset(asset_id="a", source_system="t", external_id="X", program_name="X", aliases=[],
                           company=None, row_numbers=[1], claims=claims)
    facts = FactBuilder(profile, {"CLDN18": "CLDN18", "EGFR": "EGFR"}.get).build(
        asset, ReviewInputs(), None, frozenset({"CLDN18"}))
    assert not [f for f in facts.facts if f.fact_type == "construct_target_set"]


@pytest.mark.parametrize("text, expected", [
    ("Small Cell or Non-Small Cell Lung Cancer", {"Lung Non-Small Cell Carcinoma", "Lung Small Cell Carcinoma"}),
    ("Locally Advanced or Metastatic Gastric Adenocarcinoma", {"Gastric Adenocarcinoma"}),
    ("Gram-negative Sepsis", set()),
])
def test_review_c1_4_5_coordination_and_marker_shape(text, expected):
    assert {r["read_as"] for r in indication_readings(text)} == expected


def test_review_c1_6_rights_need_a_rights_object():
    assert rights_status("patients returned to the clinic") == "UNKNOWN"
    assert rights_status("the program is one treatment option") != OPTION


def test_review_c1_7_holder_match_is_whole_word():
    prefs = TransactionPreferences(deprioritized_holders=["Ono"])
    v = assess_transaction(prefs, market_status=None, rights_status="UNKNOWN", rights_holder=None,
                           company="Sonoma Biotherapeutics", identity_twins=[])
    assert v.tier == "OPEN"


# -- X7 working-directory independence; P8/P10 prototype disclosures -----------------------------
def test_x7_paths_made_absolute_and_repository_anchored(tmp_path, monkeypatch):
    import argparse
    import os

    from bve.cli.dealscreen import _anchor_to_repository

    monkeypatch.chdir(tmp_path)
    args = argparse.Namespace(command="queue", workspace="ws", provider="offline:lib.json", target_map=None)
    _anchor_to_repository(args)
    assert args.workspace == str(tmp_path / "ws") and args.provider == f"offline:{tmp_path / 'lib.json'}"
    assert Path(os.getcwd()) == Path(__file__).resolve().parents[2]   # data/se is found from here


def test_p10_ordering_warning():
    from bve.cli.dealscreen_value import ordering_warning

    assert ordering_warning({"bear_rnpv": -10, "base_rnpv": 5, "bull_rnpv": 20}) is None
    assert "out of order" in ordering_warning({"bear_rnpv": 10, "base_rnpv": 5, "bull_rnpv": 20})
