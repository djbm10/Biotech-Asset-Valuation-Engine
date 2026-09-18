"""Punctuation must separate tokens, not weld them together.

``normalize_identity_name`` joins a letter run to an adjacent digit run so that the three
spellings of a development code -- ``CLN-978``, ``CLN 978``, ``CLN978`` -- normalize to one
key. That rule is correct and load-bearing, but it was unbounded, so it also fired between
an ordinary word and an ordinary number. Because punctuation is *replaced* by a space
rather than treated as a boundary, the ``.`` in a dose is deleted first and the join then
welds the fragment on:

    'Plitidepsin 1.5 mg/day'  ->  'plitidepsin1 5mg day'

The molecule name is destroyed. No downstream dose-stripping, salt normalization or
combination splitting can recover a name that has had a digit fused into it, which makes
this the precondition for the whole identity layer rather than a cosmetic issue.

The discriminator is length. A development-code prefix is short -- CLN, BW, MK, SCH, R --
while a molecule or an English word is not. Nothing here is specific to any target,
company or naming scheme.
"""

from __future__ import annotations

import pytest

from bve.se.resolution.registry import normalize_identity_name

# Spellings of one development code must still collapse to one key. These are the cases the
# join rule exists for and they must not regress.
DEVELOPMENT_CODES = [
    (["CLN-978", "CLN 978", "CLN978"], "cln978"),
    (["MK-3475", "MK 3475", "MK3475"], "mk3475"),
    (["BW 825C", "BW-825C", "BW825C"], "bw825c"),
    (["R 89674", "R-89674", "R89674"], "r89674"),
    (["SCH 10649", "SCH-10649"], "sch10649"),
    (["TAU-284", "TAU 284"], "tau284"),
    (["GSK-1004723", "GSK 1004723"], "gsk1004723"),
]


@pytest.mark.parametrize("spellings,expected", DEVELOPMENT_CODES)
def test_development_code_spellings_still_collapse_to_one_key(spellings, expected) -> None:
    assert {normalize_identity_name(value) for value in spellings} == {expected}


@pytest.mark.parametrize(
    "raw,must_contain_token",
    [
        # The observed M15 mentions, verbatim.
        ("Plitidepsin 1.5 mg/day", "plitidepsin"),
        ("Placebo and Plitidepsin 1.5mg/day", "plitidepsin"),
        ("Olanzapine 5 MG", "olanzapine"),
        ("5 mg Desloratadine", "desloratadine"),
        ("azelastine/fluticasone 137/50 mcg nasal spray", "azelastine"),
        ("sotorasib 960 mg", "sotorasib"),
        # A number adjacent to an ordinary word is not a development code either.
        ("H1 receptor blockade", "receptor"),
    ],
)
def test_a_molecule_name_survives_as_its_own_token(raw, must_contain_token) -> None:
    """The molecule must remain addressable as a whole word after normalization."""

    normalized = normalize_identity_name(raw)
    assert normalized is not None
    assert must_contain_token in normalized.split(), (
        f"{raw!r} normalized to {normalized!r}, which no longer contains "
        f"{must_contain_token!r} as a token"
    )


def test_short_prefix_before_a_digit_is_still_a_code_not_a_word() -> None:
    """``H1`` is a receptor designation and must stay joined; ``receptor`` must not."""

    assert normalize_identity_name("H1 receptor blockade") == "h1 receptor blockade"


def test_normalization_is_idempotent() -> None:
    """Normalizing an already-normalized key must not move it again.

    An identity key that changes on a second pass would make merge results depend on how
    many times a name happened to be round-tripped.
    """

    for raw, _ in [(value, None) for spellings, _ in DEVELOPMENT_CODES for value in spellings]:
        once = normalize_identity_name(raw)
        assert normalize_identity_name(once) == once
    for raw in ("Plitidepsin 1.5 mg/day", "H1 receptor blockade", "azelastine/fluticasone"):
        once = normalize_identity_name(raw)
        assert normalize_identity_name(once) == once
