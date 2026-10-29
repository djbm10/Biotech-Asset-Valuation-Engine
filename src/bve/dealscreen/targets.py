"""Read protein-isoform target names as their gene (cycle C1 X1). INTERNAL DEVELOPMENT.

Landscapes write targets as isoforms ("Claudin 18.2", "CLDN18.2", "claudin 18 isoform 2"). The S&E
target authority is gene-level, so these are unreadable and every such program stays UNKNOWN. This
reads ``<name> <n>.<m>`` / ``<SYMBOL><n>.<m>`` / ``<name> isoform <m>`` as ``<name> <n>`` when that
resolves, and records the reading so it is disclosed: the gene authority cannot tell isoforms apart
(an isoform-1-directed program would read the same).
"""

from __future__ import annotations

import re

POLICY = "DealScreen isoform-to-gene target reading v1"
#: "<Name> 18.2", "CLDN18.2": a letter-led base (>= 2 letters) ending in a number, then ".<n>". A base
#: ending in "-<number>" ("IL-2.5") is excluded: that shape is usually a dose or a variant label.
_DOT_ISOFORM = re.compile(r"^(?P<base>[A-Za-z][A-Za-z ]*[A-Za-z]\s?(?P<num>\d+))\s*\.\s*(?P<iso>\d+)$")
_WORD_ISOFORM = re.compile(r"^(?P<base>[A-Za-z][A-Za-z ]*[A-Za-z]\s?(?P<num>\d+))\s+isoform\s+(?P<iso>\d+)$",
                           re.IGNORECASE)


def _match(text: str):
    stripped = text.strip()
    return _DOT_ISOFORM.match(stripped) or _WORD_ISOFORM.match(stripped)


def isoform_base(text: str) -> str | None:
    """The gene-level name for an isoform-style target name, or None."""
    m = _match(text)
    return m.group("base").strip() if m else None


def isoform_number(text: str) -> str | None:
    m = _match(text)
    return m.group("iso") if m else None


def isoform_consistent(text: str, gene: str, requested: dict[str, str]) -> bool:
    """The gene reading is allowed: the gene symbol ends in the base's number (so "Claudin 1.2" cannot
    read as an unrelated gene), and when the buyer named an isoform of this gene, the text names the
    same isoform (review C1-3: "CLDN18.1" is not read for a buyer asking for CLDN18.2)."""
    m = _match(text)
    if m is None or not re.search(rf"{m.group('num')}$", gene):
        return False
    wanted = requested.get(gene)
    return wanted is None or wanted == m.group("iso")


def requested_isoforms(targets: list[tuple[str, str | None]]) -> dict[str, str]:
    """gene -> isoform number from buyer target terms (canonical id, label) such as (CLDN18, "Claudin 18.2")."""
    out = {}
    for gene, label in targets:
        if label and (number := isoform_number(label)):
            out[gene] = number
    return out


__all__ = ["POLICY", "isoform_base", "isoform_consistent", "isoform_number", "requested_isoforms"]
