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


@pytest.mark.parametrize("name", ["AK/ATPase", "AK/ATPase-directed", "anti-AK/ATPase"])
def test_a_name_fragment_never_becomes_a_target(name) -> None:
    # The fragment ``AK`` alone resolves to ADK; the whole name is an authority alias of AK6.
    assert "ADK" not in _targets(f"Find clinical-stage {name} therapies for cancer.")


def test_the_whole_name_target_is_kept() -> None:
    assert _targets("Find clinical-stage AK/ATPase therapies for cancer.") == ["AK6"]


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
