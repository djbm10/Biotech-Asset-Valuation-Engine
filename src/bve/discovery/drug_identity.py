"""Canonical drug identity — the clustering + matching key for an asset.

Biotech assets are identified by a code name (BEAM-201, RLY-2608, VX-121) that
CT.gov often buries inside descriptive intervention text or parentheticals:

    "BEAM-201"
    "BEAM 201"
    "BEAM-201 CAR-T"
    "Allogeneic anti-CD7 CAR-T cells (BEAM-201)"

All four denote the same program. This module extracts the code name (ignoring
biological *target* tokens like CD7 / IL-17 / PD-1, which look similar) and
normalizes it to a single key, falling back to a cleaned generic name when no
code name is present. Used by both `program_cluster` (to group trials) and
`matching` (to score predicted-vs-truth drug equality).
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

# Code name: alpha prefix + 2-6 digits, optional separator. Two+ digits required
# so single-digit target tokens (CD7, PD1, GD2) never match as code names.
_CODE_NAME_RE = re.compile(r"\b([A-Za-z]{2,6})[\s\-'’.]?(\d{2,6})\b")

# Alpha prefixes that denote biological targets/receptors, not asset code names.
_TARGET_PREFIXES = {
    "cd", "il", "pd", "pdl", "her", "tnf", "egfr", "vegf", "fgfr", "kras", "nras",
    "braf", "bcma", "cldn", "claudin", "trop", "ror", "dll", "ccr", "cxcr", "cxcl",
    "gprc", "ace", "hla", "ido", "lag", "tigit", "muc", "psma", "sstr", "ntrk",
    "alk", "ret", "met", "pik", "akt", "mtor", "cdk", "parp", "jak", "btk", "syk",
    "ros", "flt", "kit", "abl", "bcr", "myc", "tp", "apo", "lta", "ifn", "tgf",
    "covid", "sars", "hbv", "hcv", "hiv", "rsv", "hpv",
}

# Descriptive words to drop when no code name exists (generic-name fallback).
_NOISE_WORDS = {
    "allogeneic", "autologous", "recombinant", "humanized", "human", "chimeric",
    "anti", "cells", "cell", "therapy", "car", "cart", "tcr", "til", "nk",
    "monotherapy", "combination", "combo", "plus", "and", "with", "single", "dose",
    "doses", "multiple", "ascending", "administered", "intravenous", "iv", "oral",
    "subcutaneous", "sc", "injection", "infusion", "tablet", "tablets", "capsule",
    "capsules", "placebo", "matching", "study", "of", "the", "a", "an", "in", "to",
    "by", "for", "hydrochloride", "hcl", "sodium", "sulfate", "mesylate",
    "vaccine", "antibody", "monoclonal", "bispecific", "conjugate",
}


def extract_code_names(text: str) -> list[str]:
    """All asset code names in *text*, normalized (e.g. ``beam201``), order-stable.

    Target tokens (CD19, IL-17, …) are excluded via prefix denylist; single-digit
    tokens are excluded by the regex itself.
    """
    out: list[str] = []
    seen: set[str] = set()
    for m in _CODE_NAME_RE.finditer(text or ""):
        prefix, digits = m.group(1).lower(), m.group(2)
        if prefix in _TARGET_PREFIXES:
            continue
        key = f"{prefix}{digits}"
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _normalize_generic(name: str) -> str:
    """Cleaned generic/brand name key: drop parentheticals, noise, punctuation."""
    text = re.sub(r"\([^)]*\)", " ", (name or "").lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [t for t in text.split() if t and t not in _NOISE_WORDS and len(t) > 2]
    return " ".join(tokens).strip()


def canonical_drug_key(*names: str) -> str:
    """Single clustering/identity key from one or more name variants of a drug.

    Prefers the most frequently occurring code name across all variants (handles
    "anti-CD7 CAR-T (BEAM-201)" + "BEAM-201" → ``beam201``); falls back to the
    cleaned generic name; finally to the raw lowercased first name.
    """
    codes: list[str] = []
    for n in names:
        codes.extend(extract_code_names(n))
    if codes:
        return Counter(codes).most_common(1)[0][0]

    for n in names:
        generic = _normalize_generic(n)
        if generic:
            return generic

    for n in names:
        if n and n.strip():
            return n.strip().lower()
    return ""


def share_identity(names_a: Iterable[str], names_b: Iterable[str]) -> bool:
    """True when two sets of name variants denote the same asset.

    - If *both* sides are code-named, they must share a code (so BEAM-201 and
      BEAM-302 stay distinct).
    - Otherwise (at least one side has no code, e.g. a generic truth name vs. a
      coded program that also lists the generic) fall through to generic-name
      comparison: equal or one containing the other.
    """
    a_list, b_list = [n for n in names_a if n], [n for n in names_b if n]
    codes_a = {c for n in a_list for c in extract_code_names(n)}
    codes_b = {c for n in b_list for c in extract_code_names(n)}
    if codes_a and codes_b:
        return bool(codes_a & codes_b)

    ga = {g for n in a_list if (g := _normalize_generic(n))}
    gb = {g for n in b_list if (g := _normalize_generic(n))}
    if not ga or not gb:
        return False
    if ga & gb:
        return True
    return any(x in y or y in x for x in ga for y in gb)
