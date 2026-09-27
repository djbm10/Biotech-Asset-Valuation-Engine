"""Whether a trial's phase belongs to one hit on that trial.

Policy: ``docs/se_policies/trial_stage_attribution_amendment_6.md`` (+ 6.1). Each intervention gets one
local role per trial from what that trial states explicitly. A bare record (``UNKNOWN``) keeps
stage unless the drug's *other* trials explicitly and repeatedly use it as support
(leave-one-out). Codes starting with ``STAGE_FROM_`` attribute the phase, codes starting with
``WITHHELD_`` do not. A trial title never grants or withholds stage; it only annotates a grant.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from fractions import Fraction
from typing import Any

from bve.se.discovery.adapters import (
    _extract_interventions,
    _normalized_lookup,
    _strip_intervention_type_prefix,
    extract_observed_asset_names,
)

CONTROL = "CONTROL"
NON_PRODUCT = "NON_PRODUCT"
SUPPORT = "SUPPORT"
INVESTIGATIONAL = "INVESTIGATIONAL"
UNKNOWN = "UNKNOWN"

#: Amendment 6, step 2: fixed before measurement, never tuned.
MIN_SUPPORT_TRIALS = 3
SUPPORT_SHARE = Fraction(2, 3)

_SUPPORT = re.compile(
    r"\b(lymphodeplet\w*|conditioning|bridging|pre-?medicat\w*|supportive care|prophyla\w*|rescue)\b"
)
_CONNECTIVE = re.compile(
    r"\b(?:before|prior to|after|following|follows|followed by|preceded by|post|subsequent to"
    r"|then|during|until)\b"
)
_BACKWARD_LINK = re.compile(r"\b(?:for|as)\b")
_BEFORE_PRODUCT = re.compile(r"\b(?:prior to|before)\b.*\b(?:infusion|cells?|car|transplant\w*)\b")
_DIAGNOSTIC = re.compile(r"\b(?:imaging agent|radiotracer|tracer|contrast agent|diagnostic|pet)\b")
_CONTROL_NAME = re.compile(r"\b(?:placebo|sham|vehicle)\b")
_INVESTIGATIONAL_WORDING = re.compile(r"\b(?:investigational|study drug|study product)\b")
_CLAUSE = re.compile(r"[,;:]|(?<=\.)\s+|\n+")
_SENTENCE_END = re.compile(r"(?<=\.)\s+|\n+")
_FORMULATION_WORD = re.compile(
    r"\s+(?:cells?|injection|product|suspension|infusion)$", re.IGNORECASE
)
_NON_PRODUCT_TYPES = frozenset(
    {"DIAGNOSTIC_TEST", "PROCEDURE", "BEHAVIORAL", "DEVICE", "RADIATION"}
)
_CONTROL_ARM_TYPES = frozenset(
    {"ACTIVE_COMPARATOR", "PLACEBO_COMPARATOR", "SHAM_COMPARATOR", "NO_INTERVENTION"}
)
#: Step 3: when several interventions resolve to one hit, the most favourable role decides.
_FAVOURABLE = (INVESTIGATIONAL, UNKNOWN, SUPPORT, NON_PRODUCT, CONTROL)
_REASON = {
    INVESTIGATIONAL: "STAGE_FROM_EXPLICIT_INVESTIGATIONAL",
    CONTROL: "WITHHELD_CONTROL_ROLE",
    NON_PRODUCT: "WITHHELD_NON_PRODUCT",
    SUPPORT: "WITHHELD_SUPPORT_ROLE",
}


def is_attributed(reason: str) -> bool:
    return reason.startswith("STAGE_FROM_")


def _names(intervention: dict[str, Any]) -> set[str]:
    name = str(intervention.get("name") or "")
    other = intervention.get("otherNames") or []
    other = [str(value) for value in other] if isinstance(other, list) else [str(other)]
    found = {name, *other, *extract_observed_asset_names(name)}
    found.update(extract_observed_asset_names(" ".join(other), shape_scan=False))
    return {value for value in found if value.strip()}


def _keys(names: Iterable[str]) -> set[str]:
    return {key for key in (_normalized_lookup(name) for name in names) if key}


def _spans(names: set[str], text: str) -> list[tuple[int, int]]:
    """(start, end) of whole-word, case-insensitive occurrences of any name in ``text``."""
    lowered = text.casefold()
    return [
        match.span()
        for name in names
        if len(name) >= 3
        for match in re.finditer(rf"(?<![\w-]){re.escape(name.casefold())}(?![\w-])", lowered)
    ]


def _arm_links(protocol: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    """Intervention key -> (arm type, arm label) for every arm it is linked to, both directions."""
    module = protocol.get("armsInterventionsModule", {}) or {}
    arms = {
        _normalized_lookup(str(arm.get("label") or "")): (
            str(arm.get("type") or "").strip().upper(),
            str(arm.get("label") or ""),
        )
        for arm in module.get("armGroups", []) or []
    }
    links: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for arm in module.get("armGroups", []) or []:
        entry = arms[_normalized_lookup(str(arm.get("label") or ""))]
        for name in arm.get("interventionNames") or []:
            links[_normalized_lookup(_strip_intervention_type_prefix(str(name)))].add(entry)
    for intervention in _extract_interventions(protocol):
        key = _normalized_lookup(str(intervention.get("name") or ""))
        for label in intervention.get("armGroupLabels") or []:
            if entry := arms.get(_normalized_lookup(str(label))):
                links[key].add(entry)
    return {key: sorted(value) for key, value in links.items() if key}


def _first_sentence(intervention: dict[str, Any]) -> str:
    description = str(intervention.get("description") or "").strip()
    return _SENTENCE_END.split(description, maxsplit=1)[0].casefold() if description else ""


def _support_referents(clause: str, owner: int | None, names: list[set[str]]) -> set[int]:
    """Indices of the interventions that the support phrases in ``clause`` refer to."""
    referents: set[int] = set()
    connectives = [match.start() for match in _CONNECTIVE.finditer(clause)]
    for support in _SUPPORT.finditer(clause):
        start = support.start()
        end = min([c for c in connectives if c > start] + [len(clause)])
        phrase = clause[start:end]
        inside = {i for i, own in enumerate(names) if _spans(own, phrase)}
        referents |= inside
        # Backward attachment: "<name> … for|as <support>", nothing sequencing in between.
        lead = clause[:start].split()[-4:]
        if any(_BACKWARD_LINK.fullmatch(word) for word in lead):
            before = [
                (span_end, i)
                for i, own in enumerate(names)
                for _, span_end in _spans(own, clause[:start])
            ]
            if before:
                span_end, nearest = max(before)
                if not _CONNECTIVE.search(clause[span_end:start]):
                    referents.add(nearest)
        # Self-reference, own description only: the phrase names nothing (not even a drug that is
        # not a registered intervention), no connective governs it, and no other intervention is
        # in the clause.
        if owner is None or inside or extract_observed_asset_names(phrase, shape_scan=False):
            continue
        others = any(_spans(own, clause) for i, own in enumerate(names) if i != owner)
        if not _CONNECTIVE.search(clause[:start]) and not others:
            referents.add(owner)
    # Before-product (Amendment 6.1): the description's subject precedes "prior to|before".
    before = _BEFORE_PRODUCT.search(clause)
    if owner is not None and before and not _SUPPORT.search(clause):
        lead = clause[: before.start()]
        others = any(_spans(own, lead) for i, own in enumerate(names) if i != owner)
        if lead.strip() and not others:
            referents.add(owner)
    return referents


def _support_set(protocol: dict[str, Any], interventions: list[dict[str, Any]], names) -> set[int]:
    module = protocol.get("armsInterventionsModule", {}) or {}
    texts: list[tuple[int | None, str]] = [
        (index, str(intervention.get("description") or ""))
        for index, intervention in enumerate(interventions)
    ]
    texts += [
        (None, str(arm.get("description") or "")) for arm in module.get("armGroups", []) or []
    ]
    support = {
        index
        for index, intervention in enumerate(interventions)
        if _SUPPORT.search(str(intervention.get("name") or "").casefold())
    }
    for owner, text in texts:
        for clause in _CLAUSE.split(text.casefold()):
            if clause.strip():
                support |= _support_referents(clause, owner, names)
    return support


def local_roles(protocol: dict[str, Any]) -> list[tuple[dict[str, Any], set[str], str]]:
    """Amendment 6, step 1: (intervention, names, local role) for each intervention."""
    interventions = _extract_interventions(protocol)
    names = [_names(intervention) for intervention in interventions]
    links = _arm_links(protocol)
    roles: list[str | None] = [None] * len(interventions)
    for index, intervention in enumerate(interventions):
        name = str(intervention.get("name") or "").casefold()
        key = _normalized_lookup(name)
        first = _first_sentence(intervention)
        if _CONTROL_NAME.search(name) or {t for t, _ in links.get(key, [])} & _CONTROL_ARM_TYPES:
            roles[index] = CONTROL
        elif (
            str(intervention.get("type") or "").strip().upper() in _NON_PRODUCT_TYPES
            or _DIAGNOSTIC.search(name)
            or _DIAGNOSTIC.search(first)
        ):
            roles[index] = NON_PRODUCT
    for index in _support_set(protocol, interventions, names):
        if roles[index] is None:
            roles[index] = SUPPORT
    remaining = [index for index, role in enumerate(roles) if role is None]
    for index in remaining:
        intervention = interventions[index]
        key = _normalized_lookup(str(intervention.get("name") or ""))
        labels = [label for arm_type, label in links.get(key, []) if arm_type == "EXPERIMENTAL"]
        label_names = names[index] | {
            stripped
            for name in names[index]
            if len(stripped := _FORMULATION_WORD.sub("", name).strip()) >= 3
        }
        description = str(intervention.get("description") or "").casefold()
        if (
            len(remaining) == 1
            or any(_spans(label_names, label) for label in labels)
            or _INVESTIGATIONAL_WORDING.search(description)
        ):
            roles[index] = INVESTIGATIONAL
    return [
        (intervention, names[index], roles[index] or UNKNOWN)
        for index, intervention in enumerate(interventions)
    ]


def _trial_id(protocol: dict[str, Any]) -> str:
    return str((protocol.get("identificationModule", {}) or {}).get("nctId") or "")


class StageRoleIndex:
    """Amendment 6, step 2: explicit SUPPORT / INVESTIGATIONAL roles per drug key per trial."""

    def __init__(self) -> None:
        self._roles: dict[str, dict[str, str]] = defaultdict(dict)

    @classmethod
    def from_protocols(cls, protocols: Iterable[dict[str, Any]]) -> StageRoleIndex:
        index = cls()
        seen: set[str] = set()
        for protocol in protocols:
            trial = _trial_id(protocol)
            if not trial or trial in seen:
                continue
            seen.add(trial)
            for _, names, role in local_roles(protocol):
                if role not in (SUPPORT, INVESTIGATIONAL):
                    continue
                for key in _keys(names):
                    # SUPPORT outranks INVESTIGATIONAL within one trial.
                    if index._roles[key].get(trial) != SUPPORT:
                        index._roles[key][trial] = role
        return index

    def support_dominant(self, keys: set[str], excluding_trial: str) -> bool:
        per_trial: dict[str, str] = {}
        for key in keys:
            for trial, role in self._roles.get(key, {}).items():
                if trial != excluding_trial and per_trial.get(trial) != SUPPORT:
                    per_trial[trial] = role
        support = sum(role == SUPPORT for role in per_trial.values())
        return support >= MIN_SUPPORT_TRIALS and Fraction(support, len(per_trial)) >= SUPPORT_SHARE


def _matching(protocol: dict[str, Any], asset_name: str | None):
    key = _normalized_lookup(asset_name or "")
    if not key:
        return []
    return [entry for entry in local_roles(protocol) if key in _keys(entry[1])]


def stage_attribution(
    protocol: dict[str, Any], asset_name: str | None, index: StageRoleIndex | None = None
) -> str:
    identification = protocol.get("identificationModule", {}) or {}
    if asset_name and asset_name == str(identification.get("briefTitle") or ""):
        return "STAGE_FROM_TRIAL_TITLE_SUBJECT"
    matches = _matching(protocol, asset_name)
    if not matches:
        return "WITHHELD_UNRESOLVED"
    role = min((entry[2] for entry in matches), key=_FAVOURABLE.index)
    if role in _REASON:
        return _REASON[role]
    keys = set().union(*(_keys(entry[1]) for entry in matches))
    if index is not None and index.support_dominant(keys, _trial_id(protocol)):
        return "WITHHELD_SUPPORT_DOMINANT"
    return "STAGE_FROM_STRUCTURED_INTERVENTION"


def stage_method(protocol: dict[str, Any], asset_name: str | None, reason: str) -> str:
    """``extraction_method`` for an attributed stage claim; the title only annotates."""
    identification = protocol.get("identificationModule", {}) or {}
    title = " ".join(
        str(identification.get(field) or "") for field in ("briefTitle", "officialTitle")
    )
    names: set[str] = {asset_name} if asset_name else set()
    for _, candidate, _ in _matching(protocol, asset_name):
        names |= candidate
    titled = reason != "STAGE_FROM_TRIAL_TITLE_SUBJECT" and bool(_spans(names, title))
    return f"ctgov_stage:{reason}{'+TITLE' if titled else ''}"
