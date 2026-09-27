"""Whether a trial's phase belongs to one hit on that trial.

Policy: ``docs/se_policies/trial_stage_attribution.md``. Returns a reason code; codes starting
with ``STAGE_FROM_`` attribute the phase, codes starting with ``WITHHELD_`` do not.
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
    r"(?<!following )(?<!after )\b(lymphodeplet\w*|conditioning|bridging|pre-?medicat\w*"
    r"|supportive care|prophyla\w*|rescue)\b"
)
_BEFORE_PRODUCT = re.compile(
    r"\b(?:prior to|before)\b[^.]*\b(?:infusion|cells?|car|transplant\w*)\b"
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


def _declares_support(intervention: dict[str, Any], names: set[str]) -> bool:
    if _SUPPORT.search(str(intervention.get("name") or "").casefold()):
        return True
    lowered_names = [name.casefold() for name in names if len(name) >= 3]
    description = str(intervention.get("description") or "").casefold()
    for sentence in re.split(r"(?<=[.;])\s+|\n+", description):
        if not any(name in sentence for name in lowered_names):
            continue
        if _SUPPORT.search(sentence) or _BEFORE_PRODUCT.search(sentence):
            return True
    return False


def _experimental(protocol: dict[str, Any]) -> set[str]:
    """Interventions linked to an EXPERIMENTAL arm through either CT.gov linkage."""
    module = protocol.get("armsInterventionsModule", {}) or {}
    labels: set[str] = set()
    linked: set[str] = set()
    for arm in module.get("armGroups", []) or []:
        if str(arm.get("type") or "").strip().upper() != "EXPERIMENTAL":
            continue
        labels.add(_normalized_lookup(str(arm.get("label") or "")))
        for name in arm.get("interventionNames") or []:
            linked.add(_normalized_lookup(_strip_intervention_type_prefix(str(name))))
    for intervention in _extract_interventions(protocol):
        if any(
            _normalized_lookup(str(label)) in labels
            for label in intervention.get("armGroupLabels") or []
        ):
            linked.add(_normalized_lookup(str(intervention.get("name") or "")))
    return linked - {""}


def stage_attribution(protocol: dict[str, Any], asset_name: str | None) -> str:
    identification = protocol.get("identificationModule", {}) or {}
    brief_title = str(identification.get("briefTitle") or "")
    if asset_name and asset_name == brief_title:
        return "STAGE_FROM_TRIAL_TITLE_SUBJECT"
    interventions = _extract_interventions(protocol)
    key = _normalized_lookup(asset_name or "")
    match = next(
        (
            (intervention, names)
            for intervention in interventions
            for names in [_names(intervention)]
            if key and key in {_normalized_lookup(name) for name in names}
        ),
        None,
    )
    if match is None:
        return "WITHHELD_UNRESOLVED"
    intervention, names = match
    if _declares_support(intervention, names):
        return "WITHHELD_SUPPORT_ROLE"
    if len(interventions) == 1:
        return "STAGE_FROM_SOLE_INTERVENTION"
    key = _normalized_lookup(str(intervention.get("name") or ""))
    relationship = _arm_relationships(protocol).get(key, ArmRelationship.UNKNOWN)
    # Amendment 1: ``_arm_relationships`` reads ACTIVE_COMPARATOR as therapeutic, which is
    # right for identity and wrong for stage. The experimental arm is read directly.
    if relationship is not ArmRelationship.THERAPEUTIC or key not in _experimental(protocol):
        return "WITHHELD_NOT_EXPERIMENTAL"
    title = _normalized_lookup(
        " ".join([brief_title, str(identification.get("officialTitle") or "")])
    )
    if any(len(name) >= 3 and _normalized_lookup(name) in title for name in names):
        return "STAGE_FROM_TITLED_INTERVENTION"
    return "WITHHELD_AMBIGUOUS_PARTNER"
