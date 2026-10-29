"""Cycle A3: fixes from the frozen A2 re-test (AI-SIMULATED analyst; INTERNAL DEVELOPMENT).

Criteria: research/dealscreen_product_program/analyst_simulation/PRIORITIZED_FIXES.md (H1-H5).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bve.dealscreen.review import Action, DecisionRejected, ReviewerKind
from bve.dealscreen.workspace import Workspace

REAL = Path(__file__).resolve().parents[2] / "examples" / "dealscreen_real"
TARGETS = {t.casefold(): t for t in ["BTK", "C5", "CD19", "CD38", "CD40", "CFB", "FCGRT", "IL6R",
                                      "MS4A1", "TNFSF13B"]} | {"fcrn": "FCGRT"}
AUTHORITY = {"batoclimab": "DRUG:BATOCLIMAB", "hbm9161": "DRUG:BATOCLIMAB", "rvt-1401": "DRUG:BATOCLIMAB",
             "gefurulimab": "DRUG:GEFURULIMAB", "alxn1720": "DRUG:GEFURULIMAB"}


def normalizer(text: str) -> str | None:
    return TARGETS.get(text.strip().casefold())


def _ws(tmp_path, monkeypatch, buyer: str) -> Workspace:
    from bve.se.ontology.targets import reset_resolver_cache

    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "absent"))
    reset_resolver_cache()
    ws = Workspace(tmp_path / buyer)
    ws.import_landscape(REAL / "landscape_fcrn_gmg_v2.csv", REAL / "profile_public_landscape_v2.yaml",
                        REAL / buyer, drug_authority=lambda n: AUTHORITY.get(n.casefold()))
    ws.screen(normalizer)
    return ws


@pytest.fixture
def fcrn(tmp_path, monkeypatch):
    yield _ws(tmp_path, monkeypatch, "buyer_fcrn_gmg.yaml")


@pytest.fixture
def c5(tmp_path, monkeypatch):
    yield _ws(tmp_path, monkeypatch, "buyer_c5_gmg_heldout.yaml")


def _by_ext(ws) -> dict[str, dict]:
    ext = {a.asset_id: a.external_id for a in ws.assets()}
    return {ext[s["asset_id"]]: s for s in ws.screening()["screens"]}


# -- H1 ----------------------------------------------------------------------------------
def test_h1_combination_modality_is_unknown_with_a_reason(c5):
    s = _by_ext(c5)["RW-17"]
    gate = next(d for d in s["decisions"] if d["requirement_id"] == "modality.required")
    assert gate["status"] == "UNKNOWN"
    assert s["disposition"] != "ELIGIBLE"
    assert any("combination product" in n.get("reason", "") for n in s["unreadable_claims"])


def test_h1_only_the_combination_row_changes(c5):
    from bve.dealscreen.facts import is_combination

    names = {a.external_id: a.program_name for a in c5.assets()}
    assert [e for e, n in names.items() if is_combination(n)] == ["RW-17"]


def test_h1_human_asserted_modality_still_applies(c5):
    ids = {a.external_id: a.asset_id for a in c5.assets()}
    c5.decision_log().record(
        action=Action.ASSERT_FACT, subject_id=ids["RW-17"], new_state="ASSERTED", reviewer_id="analyst-1",
        rationale="label", reviewer_kind=ReviewerKind.HUMAN,
        detail={"field": "modality", "value": "monoclonal antibody", "source_url": "https://example.org/x",
                "evidence_span": "pozelimab is a monoclonal antibody"},
        context=c5.decision_context(normalizer))
    s = {x["asset_id"]: x for x in c5.screen(normalizer).to_dict()["screens"]}[ids["RW-17"]]
    gate = next(d for d in s["decisions"] if d["requirement_id"] == "modality.required")
    assert gate["status"] == "PASS"


# -- H2 ----------------------------------------------------------------------------------
def test_h2_rank_reasons_shown_and_ranks_unchanged(fcrn):
    from bve.dealscreen.screening import explain_preference_key

    spec = fcrn.buyer()
    s = _by_ext(fcrn)["RW-04"]
    text = explain_preference_key(spec, s["preference_key"], s["activity"])
    assert "meets preferred phase: yes" in text and "activity MARKETED" in text
    assert {e: x["rank"] for e, x in _by_ext(fcrn).items() if x["disposition"] == "ELIGIBLE"} == {
        "RW-03": 1, "RW-04": 2, "RW-06": 3, "RW-05": 4, "RW-09": 5, "RW-07": 6}


# -- H3 ----------------------------------------------------------------------------------
def test_h3_preview_config_matches_the_handoff_and_records_nothing(fcrn, tmp_path):
    from bve.cli.dealscreen import main
    from bve.cli.dealscreen_value import check_top_level_keys

    out = tmp_path / "rw08.yaml"
    code = main(["value-config", "--workspace", str(fcrn.root), "--asset", "RW-08",
                 "--assumptions", str(REAL / "valuation_assumptions_hypothetical.yaml"), "--out", str(out)])
    assert code == 0
    text = out.read_text()
    assert text.startswith("# PREVIEW - not human-approved")
    config = yaml.safe_load(text)
    check_top_level_keys(config)
    assert config["company"]["shares_outstanding_millions"] == 1.0
    assert not fcrn.decisions_path.exists()


def test_h3_preview_refused_when_not_ready_or_commercial(fcrn, tmp_path):
    ids = {a.external_id: a.asset_id for a in fcrn.assets()}
    assumptions = REAL / "valuation_assumptions_hypothetical.yaml"
    with pytest.raises(DecisionRejected, match="NOT READY"):
        fcrn.preview_config(ids["RW-05"], assumptions)   # deliberately incomplete inputs
    with pytest.raises(DecisionRejected, match="NOT READY"):
        fcrn.preview_config(ids["RW-04"], assumptions)   # marketed: pre-approval model blocked


# -- H4 / H5 -----------------------------------------------------------------------------
def test_h4_identity_subject_by_name_is_unique_or_lists_ids(fcrn):
    from bve.cli.dealscreen import resolve_subject

    with pytest.raises(DecisionRejected, match="idflag:"):
        resolve_subject(fcrn, Action.RESOLVE_IDENTITY_FLAG, "batoclimab")   # three flags
    flag = resolve_subject(fcrn, Action.RESOLVE_IDENTITY_FLAG, "gefurulimab")  # one flag
    assert flag.startswith("idflag:")


def test_h5_queue_is_in_rank_order_and_prints_flag_ids(fcrn, capsys):
    from bve.cli.dealscreen import _print_queue

    _print_queue(fcrn)
    out = capsys.readouterr().out
    ranks = [int(line.split()[0][1:]) for line in out.splitlines() if line.strip().startswith("#")]
    assert ranks == sorted(ranks)
    assert "idflag:" in out


# -- regressions from the A3 code review (AI reviewer) ---------------------------------
@pytest.mark.parametrize("name, expected", [
    ("Pozelimab + Cemdisiran", True), ("Pozelimab+Cemdisiran", True), ("A +B", True),
    ("T-DXd + pembrolizumab", True),            # two drugs: a combination (reviewer's example disputed)
    ("Efgartigimod + Thymectomy", False), ("X + placebo", False), ("Drug A plus standard of care", False),
    ("Efgartigimod alfa and hyaluronidase (SC)", False), ("Vitamin C+", False),
])
def test_review_a3_1_combination_detection(name, expected):
    from bve.dealscreen.facts import is_combination

    assert is_combination(name) is expected


def test_review_a3_2_preview_is_labelled_inside_the_data_and_refuses_excluded(fcrn):
    ids = {a.external_id: a.asset_id for a in fcrn.assets()}
    assumptions = REAL / "valuation_assumptions_hypothetical.yaml"
    config = fcrn.preview_config(ids["RW-08"], assumptions)
    assert config["analyst_notes"].startswith("PREVIEW, NOT APPROVED")
    assert "NOT a human-approved finalist" in config["analyst_notes"]
    with pytest.raises(DecisionRejected, match="EXCLUDED"):
        fcrn.preview_config(ids["RW-10"], assumptions)


def test_review_a3_3_unused_source_values_are_listed_in_the_workbook(c5, tmp_path):
    import openpyxl

    from bve.dealscreen.workbook import export_workbook

    path = tmp_path / "w.xlsx"
    export_workbook(c5, path)
    sheet = openpyxl.load_workbook(path)["Screening"]
    rows = list(sheet.iter_rows(values_only=True))
    header = next(r for r in rows if r and "Source values not used, and why" in r)
    col = header.index("Source values not used, and why")
    texts = [r[col] for r in rows[rows.index(header) + 1:] if r and r[col]]
    assert any("combination product" in t for t in texts)


# -- cycle A4 (from the frozen A3 re-test) ---------------------------------------------
def test_j1_unread_market_keys_refused_and_compliance_disclosed(fcrn, tmp_path):
    from bve.cli.dealscreen_value import ConfigKeyError, check_top_level_keys

    ids = {a.external_id: a.asset_id for a in fcrn.assets()}
    config = fcrn.preview_config(ids["RW-08"], REAL / "valuation_assumptions_hypothetical.yaml")
    check_top_level_keys(config)  # the handoff's own config passes
    assert any("0.80 compliance" in lim for lim in config["limitations"])
    config["market_model"]["compliance_rate"] = 1.0
    with pytest.raises(ConfigKeyError, match="compliance_rate"):
        check_top_level_keys(config)


def test_j3_funnel_line_warns_about_open_identity_flags(fcrn):
    from bve.dealscreen.memo import build_memo

    funnel = next(line for line in build_memo(fcrn).splitlines() if line.startswith("**Funnel.**"))
    assert "3 of the eligible records share open identity flags" in funnel


def test_j4_no_empty_reviewer_heading(fcrn):
    from bve.dealscreen.memo import build_memo

    text = build_memo(fcrn)
    assert "( reviewers)" not in text and "**Finalists: none recorded**" in text
