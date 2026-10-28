"""Cycle 3: U.S. rights holder kept separate from licensing availability (R1-R5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bve.dealscreen.review import Action, ReviewerKind
from bve.dealscreen.workspace import Workspace

REAL = Path(__file__).resolve().parents[2] / "examples" / "dealscreen_real"
TARGETS = {t.casefold(): t for t in ["BTK", "C5", "CD19", "CD38", "CD40", "CFB", "FCGRT", "IL6R",
                                      "MS4A1", "TNFSF13B"]} | {"bcma": "TNFRSF17"}
LABELLED_GMG = {"RW-01", "RW-02", "RW-04", "RW-10", "RW-11", "RW-12", "RW-13", "RW-14"}


def norm(text: str) -> str | None:
    return TARGETS.get(text.strip().casefold())


@pytest.fixture
def ws(tmp_path, monkeypatch):
    from bve.se.ontology.targets import reset_resolver_cache

    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "absent"))
    reset_resolver_cache()
    w = Workspace(tmp_path / "ws")
    w.import_landscape(REAL / "landscape_fcrn_gmg_v2.csv", REAL / "profile_public_landscape_v2.yaml",
                       REAL / "buyer_fcrn_gmg.yaml")
    w.screen(norm)
    yield w
    reset_resolver_cache()


def _screens(ws):
    ext = {a.asset_id: a.external_id for a in ws.assets()}
    return {ext[s["asset_id"]]: s for s in ws.screen(norm).to_dict()["screens"]}


def test_r3_r5_holder_only_from_fda_labeler_and_availability_unchanged(ws):
    s = _screens(ws)
    with_holder = {p for p, x in s.items() if x["commercial"]["us_rights_holder"]}
    assert with_holder == LABELLED_GMG
    assert all("labeler per FDA label; not a rights statement" in s[p]["commercial"]["us_rights_holder"] for p in with_holder)
    assert s["RW-05"]["commercial"]["us_rights_holder"] is None  # registry sponsor is not a holder
    assert {x["commercial"]["us_rights_status"] for x in s.values()} == {"UNKNOWN"}  # R2


def test_r5_dispositions_identical_to_v1(ws):
    f = ws.screening()["funnel"]
    assert (f["eligible"], f["unresolved"], f["excluded"]) == (4, 14, 22)


def test_r1_r4_asserted_holder_conflicting_with_source_is_shown_not_resolved(ws):
    ids = {a.external_id: a.asset_id for a in ws.assets()}
    ws.decision_log().record(
        action=Action.ASSERT_FACT, subject_id=ids["RW-05"], new_state="ASSERTED", reviewer_id="analyst-1",
        rationale="10-Q licensed territory", reviewer_kind=ReviewerKind.HUMAN,
        detail={"field": "us_rights_holder", "value": "Immunovant (licensee of HanAll for the U.S.)",
                "source_url": "https://www.sec.gov/Archives/edgar/data/1764013/000176401326000011/imvt-20251231.htm",
                "evidence_span": "in the United States of America (the \"U.S.\"), Canada, Mexico, the European Union"},
        context=ws.decision_context(norm))
    c = _screens(ws)["RW-05"]["commercial"]
    assert c["us_rights_holder"].startswith("Immunovant") and c["us_rights_status"] == "UNKNOWN"


def test_r4_two_source_holders_are_conflicting(tmp_path):
    import csv

    from bve.dealscreen.commercial import assess
    from bve.dealscreen.importer import import_landscape
    from bve.dealscreen.mapping import MappingProfile

    profile = MappingProfile.from_yaml(REAL / "profile_public_landscape_v2.yaml")
    headers = list(profile.columns.values())
    path = tmp_path / "h.csv"
    with path.open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=headers)
        w.writeheader()
        for holder in ("Co A", "Co B"):
            w.writerow({**dict.fromkeys(headers, ""), "Program ID": "X", "Program": "Drugmab",
                        "US Rights Holder": holder})
    asset = import_landscape(path, profile).assets[0]
    c = assess(asset, questions=[])
    assert c.us_rights_holder is None and c.us_rights_holder_conflict == ["Co A", "Co B"]
    assert c.holder_display.startswith("CONFLICTING") and c.us_rights_status == "UNKNOWN"
