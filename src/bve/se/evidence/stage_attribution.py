"""Whether a trial's phase belongs to one hit on that trial.

Policy: ``docs/se_policies/trial_stage_attribution.md`` with Amendments 1 and 2. Returns a reason
code; codes starting with ``STAGE_FROM_`` attribute the phase, codes starting with ``WITHHELD_``
do not. A trial title never grants stage; it only annotates a grant (Amendment 2, change A).
"""

from __future__ import annotations

import re
from typing import Any

from bve.se.discovery.adapters import (
    ArmRelationship,
    _arm_relationships,
    _extract_interventions,
    _normalized_lookup,
    _strip_intervention_type_prefix,
    extract_observed_asset_names,
)

_SUPPORT = re.compile(
    r"\b(lymphodeplet\w*|conditioning|bridging|pre-?medicat\w*|supportive care|prophyla\w*|rescue)\b"
)
_BEFORE_PRODUCT = re.compile(r"\b(?:prior to|before)\b.*\b(?:infusion|cells?|car|transplant\w*)\b")
#: A name separated from the support term by one of these is the clause's reference point.
_TEMPORAL = re.compile(r"\b(?:before|prior to|after|following|followed by|then|during|until)\b")
_CLAUSE = re.compile(r"[,;:]|(?<=\.)\s+|\n+")
#: Amendment 3: for arm-label matching only, a trailing formulation word may be dropped.
_FORMULATION_WORD = re.compile(
    r"\s+(?:cells?|injection|product|suspension|infusion)$", re.IGNORECASE
)
_CONTROL_ARM_TYPES = frozenset(
    {"ACTIVE_COMPARATOR", "PLACEBO_COMPARATOR", "SHAM_COMPARATOR", "NO_INTERVENTION"}
)


def is_attributed(reason: str) -> bool:
    return reason.startswith("STAGE_FROM_")


def _names(intervention: dict[str, Any]) -> set[str]:
    name = str(intervention.get("name") or "")
    other = intervention.get("otherNames") or []
    other = [str(value) for value in other] if isinstance(other, list) else [str(other)]
    found = {name, *other, *extract_observed_asset_names(name)}
    found.update(extract_observed_asset_names(" ".join(other), shape_scan=False))
    return {value for value in found if value.strip()}


def _named_in(names: set[str], text: str) -> list[int]:
    """Start positions of whole-word, case-insensitive occurrences of any name in ``text``."""
    lowered = text.casefold()
    positions: list[int] = []
    for name in names:
        if len(name) < 3:
            continue
        pattern = rf"(?<![\w-]){re.escape(name.casefold())}(?![\w-])"
        positions.extend(match.start() for match in re.finditer(pattern, lowered))
    return positions


def _is_agent_in(clause: str, position: int) -> bool:
    """Amendment 4: a temporal marker between name and support term makes it the reference."""
    terms = [match.start() for match in _SUPPORT.finditer(clause)]
    if terms:
        nearest = min(terms, key=lambda term: abs(term - position))
        low, high = sorted((position, nearest))
        return not _TEMPORAL.search(clause[low:high])
    before = _BEFORE_PRODUCT.search(clause)
    return before is not None and position < before.start()


def _is_support_agent(names: set[str], texts: list[str]) -> bool:
    for text in texts:
        for clause in _CLAUSE.split(text.casefold()):
            if not (_SUPPORT.search(clause) or _BEFORE_PRODUCT.search(clause)):
                continue
            if any(_is_agent_in(clause, position) for position in _named_in(names, clause)):
                return True
    return False


def _declares_support(intervention: dict[str, Any], names: set[str], texts: list[str]) -> bool:
    if _SUPPORT.search(str(intervention.get("name") or "").casefold()):
        return True
    return _is_support_agent(names, texts)


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
    links: dict[str, set[tuple[str, str]]] = {}
    for arm in module.get("armGroups", []) or []:
        entry = arms[_normalized_lookup(str(arm.get("label") or ""))]
        for name in arm.get("interventionNames") or []:
            key = _normalized_lookup(_strip_intervention_type_prefix(str(name)))
            links.setdefault(key, set()).add(entry)
    for intervention in _extract_interventions(protocol):
        key = _normalized_lookup(str(intervention.get("name") or ""))
        for label in intervention.get("armGroupLabels") or []:
            entry = arms.get(_normalized_lookup(str(label)))
            if entry:
                links.setdefault(key, set()).add(entry)
    return {key: sorted(value) for key, value in links.items() if key}


def _description_texts(protocol: dict[str, Any]) -> list[str]:
    module = protocol.get("armsInterventionsModule", {}) or {}
    texts = [str(i.get("description") or "") for i in _extract_interventions(protocol)]
    texts += [str(arm.get("description") or "") for arm in module.get("armGroups", []) or []]
    return [text for text in texts if text]


def _excluded(protocol, intervention, names, texts, links, relationships, multiple) -> str | None:
    """Rules 3 and 4: the withheld reason for one resolved intervention, or None."""
    if _declares_support(intervention, names, texts):
        return "WITHHELD_SUPPORT_ROLE"
    if not multiple:
        return None
    key = _normalized_lookup(str(intervention.get("name") or ""))
    arm_types = {arm_type for arm_type, _ in links.get(key, [])}
    if (
        "EXPERIMENTAL" not in arm_types
        or arm_types & _CONTROL_ARM_TYPES
        or relationships.get(key, ArmRelationship.UNKNOWN) is not ArmRelationship.THERAPEUTIC
    ):
        return "WITHHELD_NOT_EXPERIMENTAL"
    return None


def stage_attribution(protocol: dict[str, Any], asset_name: str | None) -> str:
    identification = protocol.get("identificationModule", {}) or {}
    if asset_name and asset_name == str(identification.get("briefTitle") or ""):
        return "STAGE_FROM_TRIAL_TITLE_SUBJECT"
    interventions = _extract_interventions(protocol)
    key = _normalized_lookup(asset_name or "")
    resolved = [(intervention, _names(intervention)) for intervention in interventions]
    match = next(
        (
            (intervention, names)
            for intervention, names in resolved
            if key and key in {_normalized_lookup(name) for name in names}
        ),
        None,
    )
    if match is None:
        return "WITHHELD_UNRESOLVED"
    intervention, names = match
    texts = _description_texts(protocol)
    links = _arm_links(protocol)
    relationships = _arm_relationships(protocol)
    multiple = len(interventions) > 1
    withheld = _excluded(protocol, intervention, names, texts, links, relationships, multiple)
    if withheld:
        return withheld
    if not multiple:
        return "STAGE_FROM_SOLE_INTERVENTION"
    survivors = [
        other
        for other, other_names in resolved
        if _excluded(protocol, other, other_names, texts, links, relationships, multiple) is None
    ]
    if len(survivors) == 1:
        return "STAGE_FROM_SOLE_PRODUCT"
    own_key = _normalized_lookup(str(intervention.get("name") or ""))
    experimental_labels = [
        label for arm_type, label in links.get(own_key, []) if arm_type == "EXPERIMENTAL"
    ]
    label_names = names | {
        stripped for name in names if len(stripped := _FORMULATION_WORD.sub("", name).strip()) >= 3
    }
    if any(_named_in(label_names, label) for label in experimental_labels):
        return "STAGE_FROM_ARM_LABEL"
    return "WITHHELD_AMBIGUOUS_PARTNER"


def stage_method(protocol: dict[str, Any], asset_name: str | None, reason: str) -> str:
    """``extraction_method`` for an attributed stage claim; the title only annotates."""
    identification = protocol.get("identificationModule", {}) or {}
    title = " ".join(
        str(identification.get(field) or "") for field in ("briefTitle", "officialTitle")
    )
    names: set[str] = {asset_name} if asset_name else set()
    key = _normalized_lookup(asset_name or "")
    for intervention in _extract_interventions(protocol):
        candidate = _names(intervention)
        if key and key in {_normalized_lookup(name) for name in candidate}:
            names |= candidate
    titled = reason != "STAGE_FROM_TRIAL_TITLE_SUBJECT" and bool(_named_in(names, title))
    return f"ctgov_stage:{reason}{'+TITLE' if titled else ''}"
