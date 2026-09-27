"""Whether a trial's phase belongs to one hit on that trial.

Policy: ``docs/se_policies/trial_stage_attribution_amendment_5.md``. A structured intervention
keeps the trial's stage unless its own record or arm links give positive evidence that it is not
the investigational program. Codes starting with ``STAGE_FROM_`` attribute the phase, codes
starting with ``WITHHELD_`` do not. A trial title never grants or withholds stage; it only
annotates a grant.
"""

from __future__ import annotations

import re
from typing import Any

from bve.se.discovery.adapters import (
    _extract_interventions,
    _normalized_lookup,
    _strip_intervention_type_prefix,
    extract_observed_asset_names,
)

_SUPPORT = re.compile(
    r"\b(lymphodeplet\w*|conditioning|bridging|pre-?medicat\w*|supportive care|prophyla\w*|rescue)\b"
)
_TEMPORAL = re.compile(r"\b(?:before|prior to|after|following|followed by|then|during|until)\b")
_DIAGNOSTIC = re.compile(
    r"\b(?:imaging agent|radiotracer|tracer|contrast agent|diagnostic|pet)\b"
)
_CONTROL_NAME = re.compile(r"\b(?:placebo|sham|vehicle)\b")
_SENTENCE_END = re.compile(r"(?<=\.)\s+|\n+")
_NON_PRODUCT_TYPES = frozenset({"DIAGNOSTIC_TEST", "PROCEDURE", "BEHAVIORAL", "DEVICE", "RADIATION"})
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


def _named_in(names: set[str], text: str) -> bool:
    lowered = text.casefold()
    return any(
        re.search(rf"(?<![\w-]){re.escape(name.casefold())}(?![\w-])", lowered)
        for name in names
        if len(name) >= 3
    )


def _control_arm_keys(protocol: dict[str, Any]) -> set[str]:
    """Keys of interventions linked, in either CT.gov direction, to a control arm."""
    module = protocol.get("armsInterventionsModule", {}) or {}
    control_labels = set()
    keys: set[str] = set()
    for arm in module.get("armGroups", []) or []:
        if str(arm.get("type") or "").strip().upper() not in _CONTROL_ARM_TYPES:
            continue
        control_labels.add(_normalized_lookup(str(arm.get("label") or "")))
        for name in arm.get("interventionNames") or []:
            keys.add(_normalized_lookup(_strip_intervention_type_prefix(str(name))))
    for intervention in _extract_interventions(protocol):
        labels = {_normalized_lookup(str(label)) for label in intervention.get("armGroupLabels") or []}
        if labels & control_labels:
            keys.add(_normalized_lookup(str(intervention.get("name") or "")))
    return keys


def _identifies_support(sentence: str) -> bool:
    """A support term the sentence describes, not one it refers to after a temporal marker."""
    return any(
        not _TEMPORAL.search(sentence[: match.start()]) for match in _SUPPORT.finditer(sentence)
    )


def _exclusion(intervention: dict[str, Any], control_keys: set[str]) -> str | None:
    """Rule 3: the withheld reason read from the intervention's own record, or None."""
    name = str(intervention.get("name") or "").casefold()
    description = str(intervention.get("description") or "").strip()
    first = _SENTENCE_END.split(description, maxsplit=1)[0].casefold() if description else ""
    if _CONTROL_NAME.search(name) or _normalized_lookup(name) in control_keys:
        return "WITHHELD_CONTROL_ROLE"
    kind = str(intervention.get("type") or "").strip().upper()
    if kind in _NON_PRODUCT_TYPES or _DIAGNOSTIC.search(name) or _DIAGNOSTIC.search(first):
        return "WITHHELD_NON_PRODUCT"
    if _identifies_support(name) or _identifies_support(first):
        return "WITHHELD_SUPPORT_ROLE"
    return None


def _matching(protocol: dict[str, Any], asset_name: str | None) -> list[dict[str, Any]]:
    key = _normalized_lookup(asset_name or "")
    if not key:
        return []
    return [
        intervention
        for intervention in _extract_interventions(protocol)
        if key in {_normalized_lookup(name) for name in _names(intervention)}
    ]


def stage_attribution(protocol: dict[str, Any], asset_name: str | None) -> str:
    identification = protocol.get("identificationModule", {}) or {}
    if asset_name and asset_name == str(identification.get("briefTitle") or ""):
        return "STAGE_FROM_TRIAL_TITLE_SUBJECT"
    matches = _matching(protocol, asset_name)
    if not matches:
        return "WITHHELD_UNRESOLVED"
    control_keys = _control_arm_keys(protocol)
    reasons = [_exclusion(intervention, control_keys) for intervention in matches]
    if any(reason is None for reason in reasons):
        return "STAGE_FROM_STRUCTURED_INTERVENTION"
    return str(reasons[0])


def stage_method(protocol: dict[str, Any], asset_name: str | None, reason: str) -> str:
    """``extraction_method`` for an attributed stage claim; the title only annotates."""
    identification = protocol.get("identificationModule", {}) or {}
    title = " ".join(
        str(identification.get(field) or "") for field in ("briefTitle", "officialTitle")
    )
    names: set[str] = {asset_name} if asset_name else set()
    for intervention in _matching(protocol, asset_name):
        names |= _names(intervention)
    titled = reason != "STAGE_FROM_TRIAL_TITLE_SUBJECT" and _named_in(names, title)
    return f"ctgov_stage:{reason}{'+TITLE' if titled else ''}"
