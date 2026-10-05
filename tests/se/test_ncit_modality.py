"""NCIT_MODALITY v1: a Cell-typed NCIt product fills a missing modality, never overrides.

Policy: ``docs/se_policies/ncit_modality_v1.md``.
"""

from __future__ import annotations

import json

import pytest

from bve.se import pipeline
from bve.se.ontology.ncit_cell_products import build_cell_products, reset_cell_products_cache
from bve.se.schemas.contracts import CanonicalAsset


@pytest.fixture
def cells(tmp_path, monkeypatch):
    flat = tmp_path / "Thesaurus.txt"
    flat.write_text(
        "C1\t\t\tCAR-T X\t\t\t\tCell|Pharmacologic Substance\n"
        "C2\t\t\tPeptide Y\t\t\t\tPharmacologic Substance\n"
    )
    payload = build_cell_products(flat, {"C1", "C2"}, release_zip_sha256="z")
    path = tmp_path / "cells.json"
    path.write_text(json.dumps(payload))
    monkeypatch.setenv("BVE_SE_NCIT_CELL_PRODUCTS", str(path))
    reset_cell_products_cache()
    yield payload
    reset_cell_products_cache()


def _asset(asset_id: str, name: str) -> CanonicalAsset:
    return CanonicalAsset(asset_id=asset_id, canonical_name=name, aliases=[name])


def test_only_cell_typed_concepts_enter_the_sidecar(cells) -> None:
    assert cells["cell_product_codes"] == ["C1"]


def test_a_cell_product_link_fills_cell_therapy(cells, monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "modality_authority", lambda: None)
    (asset,) = pipeline._with_authority_modality([_asset("a", "X")], ["CELL_THERAPY"], {"a": "C1"})
    assert asset.authority_modality == "CELL_THERAPY"
    assert asset.authority_modality_basis == "NCIt:C1 (Cell)"
    assert asset.modality_match == "MATCH"


def test_a_non_cell_concept_fills_nothing(cells, monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "modality_authority", lambda: None)
    (asset,) = pipeline._with_authority_modality([_asset("a", "Y")], ["CELL_THERAPY"], {"a": "C2"})
    assert asset.authority_modality is None
    assert asset.modality_match == "UNKNOWN"


def test_chembl_modality_is_never_overridden(cells, monkeypatch) -> None:
    class _Authority:
        def modality_of_names(self, names):
            from bve.se.ontology.drug_modality import AuthorityModality

            return AuthorityModality("ANTIBODY", "DRUG:X", ("CHEMBL1",), "Antibody")

    monkeypatch.setattr(pipeline, "modality_authority", lambda: _Authority())
    (asset,) = pipeline._with_authority_modality([_asset("a", "X")], ["CELL_THERAPY"], {"a": "C1"})
    assert asset.authority_modality == "ANTIBODY"


def test_no_link_or_no_sidecar_fills_nothing(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "modality_authority", lambda: None)
    (asset,) = pipeline._with_authority_modality([_asset("a", "X")], ["CELL_THERAPY"], {"a": "C1"})
    assert asset.authority_modality is None
