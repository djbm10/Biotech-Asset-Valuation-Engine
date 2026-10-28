"""Cycle 4: import-time target cache and the ontology-free screen path (P1, P2, P4).

P3 (byte equality against the real ontology) needs the 1.7 GB snapshot and is measured by
research/dealscreen_product_program/cycle4/equivalence.py, recorded in equivalence_result.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bve.dealscreen import workspace as wsmod
from bve.dealscreen.workspace import Workspace

REAL = Path(__file__).resolve().parents[2] / "examples" / "dealscreen_real"
TARGETS = {t.casefold(): t for t in ["BTK", "C5", "CD19", "CD38", "CD40", "CFB", "FCGRT", "IL6R",
                                      "MS4A1", "TNFSF13B"]} | {"bcma": "TNFRSF17"}


def norm(text: str) -> str | None:
    return TARGETS.get(text.strip().casefold())


@pytest.fixture
def ws(tmp_path, monkeypatch):
    from bve.se.ontology.targets import reset_resolver_cache

    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "absent"))
    reset_resolver_cache()
    w = Workspace(tmp_path / "ws")
    w.import_landscape(REAL / "landscape_fcrn_gmg.csv", REAL / "profile_public_landscape.yaml",
                       REAL / "buyer_fcrn_gmg.yaml", target_normalizer=norm)
    yield w
    reset_resolver_cache()


def test_p1_cache_holds_every_target_string_and_buyer_target(ws):
    cache = json.loads(ws.target_cache_path.read_text())
    assert cache["BCMA"] == "TNFRSF17" and cache["FCGRT"] == "FCGRT"
    assert all(t.canonical_id in cache for t in ws.buyer().problem.strategic_gap.target_expression.targets)


def test_p2_cached_screen_equals_explicit_normalizer_screen(ws):
    ws.screen(norm)
    explicit = (ws.root / "screening.json").read_bytes()
    ws.screen(None)
    assert (ws.root / "screening.json").read_bytes() == explicit
    assert ws.can_screen_without_ontology()


def test_p2_non_canonical_buyer_target_disables_the_fast_path(ws):
    cache = json.loads(ws.target_cache_path.read_text())
    cache["FCGRT"] = "SOMETHING_ELSE"  # buyer target id is not canonical per the cache
    ws.target_cache_path.write_text(json.dumps(cache))
    assert not ws.can_screen_without_ontology()


def test_p4_cache_miss_falls_back_to_the_ontology(ws, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(wsmod, "ontology_target_normalizer", lambda: (lambda t: calls.append(t) or "X"))
    cached = ws.cached_normalizer()
    assert cached is not None
    assert cached("FCGRT") == "FCGRT" and calls == []
    assert cached("NEWTARGET") == "X" and calls == ["NEWTARGET"]


def test_ontology_setting_is_restored_after_the_fast_path(ws, monkeypatch):
    import os

    before = os.environ["BVE_SE_ONTOLOGY_SNAPSHOT"]
    ws.screen(None)
    assert os.environ["BVE_SE_ONTOLOGY_SNAPSHOT"] == before
