"""CANDIDATE_QUALIFICATION v7: a treatment-category head is not a product.

Policy: ``docs/se_policies/candidate_qualification_v7.md``.
"""

from __future__ import annotations

import pytest

from bve.se.discovery.asset_qualification import qualification_veto, treatment_category_head


@pytest.mark.parametrize(
    "name",
    [
        "Lymphodepletion Chemotherapy",
        "Chemotherapy Agents",
        "Post-CR Consolidation Regimens",
        "Cyclophosphamide-based chemotherapy",
        "MMF Immunosuppression",
        "Standard of Care Treatment",
    ],
)
def test_a_category_head_is_a_descriptor(name) -> None:
    assert qualification_veto(name)[0] == "TREATMENT_CATEGORY_DESCRIPTOR"


def test_an_attributive_left_without_its_head_is_a_descriptor() -> None:
    assert treatment_category_head("Fludarabine-based") == "elliptical_based"


@pytest.mark.parametrize(
    "name",
    [
        "Senl_B19 autologous CAR-T (S1904) treatment",
        "Bispecific antibody-based combined with CAR-T cell therapy",
        "Nanobody-based biepitope BCMA-targeting CAR-T cells",
        "NKTR-255",
        "Tecartus",
        "fludarabine",
    ],
)
def test_products_and_constructs_are_protected(name) -> None:
    assert treatment_category_head(name) is None


def test_a_head_inside_parentheses_is_not_the_head() -> None:
    assert treatment_category_head("Withhold IS (B cell depletion therapy)") is None


def test_a_sponsor_code_protects_the_name() -> None:
    assert treatment_category_head("ABC-123 therapy") is None
