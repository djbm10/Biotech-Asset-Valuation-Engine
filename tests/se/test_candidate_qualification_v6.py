"""CANDIDATE_QUALIFICATION v6: regimens, procedures and lists are not products.

Policy: ``docs/se_policies/candidate_qualification_v6.md``.
"""

from __future__ import annotations

import json

import pytest

from bve.se.discovery import asset_qualification as q
from bve.se.ontology.ncit_entity_types import (
    NcitEntityTypes,
    build_entity_types,
    reset_entity_types_cache,
)


def _flat(tmp_path):
    rows = [
        # code, iri, parents, synonyms, definition, display, status, semantic types
        ("C1", "", "", "R-mini-CHOP Regimen|R-mini-CHOP", "", "", "", "Therapeutic or Preventive Procedure"),
        ("C2", "", "", "Avipendekin Pegol|NKTR-255", "", "", "", "Pharmacologic Substance"),
        ("C3", "", "", "Treatment", "", "", "", "Health Care Activity"),
        ("C4", "", "", "Treatment", "", "", "", "Pharmacologic Substance"),
        ("C5", "", "", "Standard of Care", "", "", "", "Health Care Activity"),
    ]
    path = tmp_path / "Thesaurus.txt"
    path.write_text("\n".join("\t".join(row) for row in rows) + "\n")
    return path


@pytest.fixture
def types(tmp_path, monkeypatch):
    payload = build_entity_types(_flat(tmp_path), release_zip_sha256="z")
    file = tmp_path / "types.json"
    file.write_text(json.dumps(payload))
    monkeypatch.setenv("BVE_SE_NCIT_ENTITY_TYPES", str(file))
    reset_entity_types_cache()
    yield payload
    reset_entity_types_cache()


class TestNcitEntityType:
    def test_a_regimen_name_is_a_procedure(self, types) -> None:
        assert q.qualification_veto("R-mini-CHOP") == ("NCIT_NON_PRODUCT_TYPE", ["C1"])

    def test_a_care_descriptor_is_an_activity(self, types) -> None:
        assert q.qualification_veto("Standard of Care")[0] == "NCIT_NON_PRODUCT_TYPE"

    def test_a_real_asset_with_an_unusual_name_is_kept(self, types) -> None:
        assert q.qualification_veto("NKTR-255") is None

    def test_any_product_typed_concept_blocks_the_veto(self, types) -> None:
        # "Treatment" is an activity in C3 and (hypothetically) a substance in C4.
        assert "treatment" not in types["non_product_names"]

    def test_an_unknown_name_is_not_vetoed(self, types) -> None:
        assert q.qualification_veto("ZZQ-9001") is None

    def test_no_sidecar_means_no_type_veto(self) -> None:
        assert q.qualification_veto("R-mini-CHOP") is None


class TestComposite:
    @pytest.fixture(autouse=True)
    def _ontology(self, monkeypatch):
        known = {"fludarabine", "cyclophosphamide", "elranatamab", "lenalidomide", "pf-06863135"}
        monkeypatch.setattr(
            q.drug_name_shape,
            "is_identity_bearing_drug_name",
            lambda value: value.strip().casefold() in known,
        )

    @pytest.mark.parametrize(
        "name",
        [
            "Fludarabine, Cyclophosphamide",
            "fludarabine and cyclophosphamide",
            "Elranatamab + lenalidomide",
            "PF-06863135 followed by lenalidomide",
        ],
    )
    def test_two_named_drugs_are_a_list(self, name) -> None:
        assert q.qualification_veto(name)[0] == "COMPOSITE_OF_NAMED_DRUGS"

    def test_a_drug_with_its_own_code_is_one_product(self) -> None:
        # Two names of one asset are not two segments the coordinator split.
        assert q.qualification_veto("Elranatamab (PF-06863135)") is None

    def test_one_named_drug_plus_prose_is_not_a_list(self) -> None:
        assert q.qualification_veto("Fludarabine + CAR-T cells") is None

    def test_a_repeated_name_is_not_two_products(self) -> None:
        assert q.qualification_veto("Fludarabine / fludarabine") is None


def test_the_vetoes_name_no_asset() -> None:
    import ast
    from pathlib import Path

    tree = ast.parse(Path(q.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in (
            "qualification_veto", "composite_drug_segments"
        ):
            node.body = node.body[1:]
            code = ast.unparse(node).casefold()
            for token in ("chop", "fludarabine", "nktr", "standard of care", "cvad"):
                assert token not in code


def test_entity_types_token_is_stable(tmp_path) -> None:
    payload = build_entity_types(_flat(tmp_path), release_zip_sha256="z")
    a = NcitEntityTypes(payload, "a" * 64)
    assert a.version_token == "ncit_entity_types_v1@ncit_26.08e@aaaaaaaaaaaaaaaa"
