"""DUAL_TARGET_SEPARATOR_SAFETY v3: a target is never asserted from a fragment of a name.

Policy: ``docs/se_policies/dual_target_separator_safety_v1.md`` §7-§9.
"""

from __future__ import annotations

import pytest

from bve.se.intent.parser import parse_query
from bve.se.ontology.targets import resolve_target

pytestmark = pytest.mark.skipif(resolve_target("CD19") is None, reason="no ontology snapshot")


def _targets(query: str) -> list[str]:
    return sorted(t.canonical_id for t in parse_query(query).targets)


def test_a_fragment_of_an_unresolved_name_is_not_a_target() -> None:
    assert _targets("Find clinical-stage anti-ABP/ZF therapies for cancer.") == []


def test_a_whole_name_the_authority_resolves_wins_over_its_fragments() -> None:
    assert _targets("Find clinical-stage TaxREB107 therapies for cancer.") == ["RPL6"]


@pytest.mark.parametrize(
    "query, expected",
    [
        ("Find clinical-stage CD19/BCMA CAR-T therapies for lupus.", ["CD19", "TNFRSF17"]),
        ("Find clinical-stage CD19xBCMA bispecifics for myeloma.", ["CD19", "TNFRSF17"]),
        ("Find clinical-stage CD19×CD22 CAR-T cells for leukemia.", ["CD19", "CD22"]),
    ],
)
def test_dual_target_expressions_are_unchanged(query, expected) -> None:
    assert _targets(query) == expected
