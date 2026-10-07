"""DISPLAY_NAME_NORMALIZATION v1: a pasted registry field header is stripped from the shown name only.

Policy: ``docs/se_policies/display_name_normalization_v1.md``.
"""

from __future__ import annotations

import pytest

from bve.se.reporting.shortlist import display_name


@pytest.mark.parametrize(
    "raw, shown",
    [
        ("Assigned Interventions CD19/BCMA CAR T-cells", "CD19/BCMA CAR T-cells"),
        ("Intervention: XYZ-101", "XYZ-101"),
        ("assigned intervention  ABC cells", "ABC cells"),
    ],
)
def test_field_headers_are_stripped_for_display(raw, shown) -> None:
    assert display_name(raw) == shown


@pytest.mark.parametrize(
    "raw", ["Interventions", "Interventional CAR-T", "CD19 CAR-T Intervention", "Tisagenlecleucel"]
)
def test_other_names_are_shown_unchanged(raw) -> None:
    assert display_name(raw) == raw
