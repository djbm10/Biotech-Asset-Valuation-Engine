"""Explicit asset -> therapeutic-target relations, read from what a record says it binds.

The reader this replaces asserted a target whenever any symbol-shaped token sat within a
few words of any cue, and resolved that token through every alias the ontology holds. On
target-scoped CAR-T records that looked precise; on a registry's general population it
turned route abbreviations into genes (``PO``, ``IV``), sponsor code prefixes into genes
(``AMG``, ``GDC``), family names into one member (``HDAC``), metabolising enzymes into
targets, and armoring transgenes into binding arms. Those are not alias problems a word
list could fix -- Open Targets stores ``BCMA`` and ``IV`` as the same kind of synonym -- so
the boundary here is grammatical: a mention becomes a target only as the argument of a
closed set of attributive constructions, only in fields that describe the product itself,
and any slot the reader cannot fully resolve leaves the whole record silent.

Policy: ``docs/se_policies/target_relation_reader_v1.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

READER_VERSION = "target_relation_v1"


class Slot:
    """Closed set of constructions that attribute a target to the product (§3.1)."""

    ANTI_PREFIX = "S1_anti_prefix"
    ATTRIBUTIVE_SUFFIX = "S2_attributive_suffix"
    CAR_HEAD = "S3_car_head"
    VERBAL = "S4_verbal"
    ARM_NOTATION = "S5_arm_notation"


EXPLICIT_SLOTS = frozenset(
    {Slot.ANTI_PREFIX, Slot.ATTRIBUTIVE_SUFFIX, Slot.VERBAL, Slot.ARM_NOTATION}
)

#: Suffixes that make "X-<suffix>" a statement about what the product acts on.
_SUFFIX_CUES = frozenset(
    {"directed", "targeted", "targeting", "specific", "redirected", "binding"}
)

#: Verbs whose next token is what the product acts on.
_VERBAL_CUES = frozenset({"targeting", "targets"})

#: The chimeric-receptor head. Its hyphen tail (``-T``, ``-NK``) is the cell carrying it.
_CAR_HEADS = frozenset({"car", "cart"})

#: Words that are part of how a product is described and are never themselves a target.
_NEVER_MENTIONS = frozenset(
    {
        *_SUFFIX_CUES,
        *_VERBAL_CUES,
        *_CAR_HEADS,
        "anti",
        "cell",
        "cells",
        "nk",
        "t",
        "tcr",
        "antibody",
        "mab",
        "adc",
        "engager",
        "bispecific",
        "trispecific",
    }
)

#: The effector-recruiting arm of a T-cell engager. It binds the patient's T cells, not
#: the disease, so it is recorded but is not a therapeutic target (§3.2 M6).
_EFFECTOR_TERMS = frozenset({"CD3", "CD3E", "CD3Ε"})

#: A head noun naming a class of therapies rather than this product (§3.3 L4).
_CLASS_NOUNS = frozenset(
    {
        "therapy",
        "therapies",
        "treatment",
        "treatments",
        "agent",
        "agents",
        "drug",
        "drugs",
        "regimen",
        "regimens",
        "mabs",
        "antibodies",
        "biologics",
        "inhibitors",
    }
)

#: Words after which a slot in a description sentence may be about another therapy (L3).
_HISTORY_MARKERS = frozenset(
    {
        "prior",
        "previous",
        "previously",
        "after",
        "following",
        "failed",
        "refractory",
        "relapsed",
        "exposed",
        "naive",
        "naïve",
        "resistant",
        "intolerant",
        "underwent",
        "received",
        "pretreated",
        "pre-treated",
    }
)
_COMBINATION_MARKERS = frozenset({"combined", "combination", "plus", "+"})

#: A list coordinator. A slot fed by a list is ambiguous about which member the product is.
_LIST_COORDINATORS = frozenset({",", "and", "or"})

_TOKEN = re.compile(r",|\+(?=\s|$)|[^\s,;:()\[\]{}\"“”]+")
_SENTENCE_END = re.compile(r"(?<=[.。])\s+|;|\n|。")
_MENTION_BODY = re.compile(r"^[A-Za-z][A-Za-z0-9.εΕ]*$")
_ARM_SPLIT = re.compile(r"×|(?<=[A-Za-z0-9])x(?=[A-Z])")


@dataclass(frozen=True)
class TargetRelation:
    """One target the record attributes to the product, and exactly how (R4)."""

    slot: str
    locus: str
    surface: str
    matched_alias: str
    tier: str
    canonical_id: str

    def locator(self) -> str:
        return (
            f"{self.locus}#{self.slot}:{self.surface}->{self.canonical_id}"
            f"[{self.tier}:{self.matched_alias}]"
        )


@dataclass(frozen=True)
class RelationReading:
    """What one locus says. ``refusal`` set means the locus said something unreadable."""

    relations: tuple[TargetRelation, ...] = ()
    refusal: str | None = None

    @property
    def targets(self) -> frozenset[str]:
        return frozenset(relation.canonical_id for relation in self.relations)


class _Unreadable(Exception):
    """A slot exists but its argument cannot be read completely (R2)."""


def _tokens(text: str) -> list[str]:
    tokens = []
    for raw in _TOKEN.findall(text):
        token = raw if raw in {",", "+"} else raw.strip(".-'’")
        if token:
            tokens.append(token)
    return tokens


def first_sentence(text: str) -> str:
    """The description's opening sentence: where a registry says what the product is."""

    return _SENTENCE_END.split(text.strip(), maxsplit=1)[0] if text else ""


def _is_mention_shaped(value: str) -> bool:
    """Symbol-like: not a prose word. ``tumor`` in "anti-tumor" is not a slot argument.

    A ``/`` or arm-notation coordination is shaped when every member is (M4, M5).
    """

    members = [m for part in value.split("/") for m in _ARM_SPLIT.split(part)]
    if len(members) > 1:
        return all(_is_single_mention_shaped(member) for member in members)
    return _is_single_mention_shaped(value)


def _is_single_mention_shaped(value: str) -> bool:
    body = value.replace("-", "")
    if not body or not _MENTION_BODY.match(body):
        return False
    if any(part.casefold() in _NEVER_MENTIONS for part in value.split("-")):
        return False
    uppers = sum(1 for char in body if char.isupper())
    digits = any(char.isdigit() for char in body)
    return uppers >= 2 or (uppers >= 1 and digits)


def _resolve(mention: str):
    from bve.se.ontology.records import EntityType
    from bve.se.ontology.resolver import ResolutionStatus
    from bve.se.ontology.targets import get_resolver

    resolver = get_resolver()
    if resolver is None:
        return None
    result = resolver.resolve(mention, EntityType.TARGET)
    return result if result.status is ResolutionStatus.RESOLVED else None


def _normal(value: str) -> str:
    return value.replace("-", "").upper()


def _read_mention(mention: str, *, slot: str, locus: str) -> list[TargetRelation]:
    """Resolve one slot argument, whole first, then split only where every part resolves."""

    if _normal(mention) in _EFFECTOR_TERMS:
        return []
    result = _resolve(mention)
    if result is not None and result.canonical_id:
        matched = result.basis.matched_alias if result.basis else mention
        approved = _normal(matched) == _normal(result.canonical_symbol or "")
        if not approved and len(re.sub(r"[^A-Za-z0-9]", "", matched)) < 3:
            raise _Unreadable(f"short_synonym:{mention}")
        return [
            TargetRelation(
                slot=slot,
                locus=locus,
                surface=mention,
                matched_alias=matched,
                tier="APPROVED" if approved else "SYNONYM",
                canonical_id=result.canonical_id,
            )
        ]
    for separator in ("/", "arm", "-"):
        parts = (
            [part for part in _ARM_SPLIT.split(mention)]
            if separator == "arm"
            else mention.split(separator)
        )
        if len(parts) < 2:
            continue
        if not all(_is_mention_shaped(part) for part in parts):
            continue
        relations: list[TargetRelation] = []
        for part in parts:
            relations.extend(_read_mention(part, slot=slot, locus=locus))
        return relations
    raise _Unreadable(f"unresolved:{mention}")


def _car_head_index(token: str) -> int | None:
    """Index of the hyphen-part that is a CAR head, if this token contains one."""

    parts = token.split("-")
    for index, part in enumerate(parts):
        if part.casefold() in _CAR_HEADS:
            return index
    return None


def _slots(tokens: list[str]) -> list[tuple[int, str, str]]:
    """Every (token index, slot id, argument) the closed grammar finds."""

    found: list[tuple[int, str, str]] = []
    for index, token in enumerate(tokens):
        folded = token.casefold()
        parts = token.split("-")
        if folded.startswith("anti-") and len(token) > 5:
            argument = token[5:]
            head = _car_head_index(argument)
            if head is not None:
                argument = "-".join(argument.split("-")[:head])
            found.append((index, Slot.ANTI_PREFIX, argument))
            continue
        if len(parts) >= 2 and parts[-1].casefold() in _SUFFIX_CUES:
            found.append((index, Slot.ATTRIBUTIVE_SUFFIX, "-".join(parts[:-1])))
            continue
        head = _car_head_index(token)
        if head is not None and head > 0:
            found.append((index, Slot.CAR_HEAD, "-".join(parts[:head])))
            continue
        if head == 0:
            run: list[str] = []
            cursor = index - 1
            while cursor >= 0 and _is_mention_shaped(tokens[cursor]):
                run.insert(0, tokens[cursor])
                cursor -= 1
            if run:
                if cursor >= 0 and tokens[cursor].casefold() in _LIST_COORDINATORS:
                    found.append((cursor, "LIST", ""))
                for member in run:
                    found.append((index, Slot.CAR_HEAD, member))
            continue
        if folded in _SUFFIX_CUES and index > 0 and _is_mention_shaped(tokens[index - 1]):
            if index > 1 and tokens[index - 2].casefold() in _LIST_COORDINATORS:
                found.append((index - 2, "LIST", ""))
            found.append((index, Slot.ATTRIBUTIVE_SUFFIX, tokens[index - 1]))
            continue
        if index + 1 < len(tokens):
            follower = tokens[index + 1]
            verbal = folded in _VERBAL_CUES or (
                folded == "directed" and follower.casefold() == "against"
            )
            if folded == "directed" and follower.casefold() == "against":
                follower = tokens[index + 2] if index + 2 < len(tokens) else ""
            if verbal and _is_mention_shaped(follower):
                after = tokens.index(follower, index + 1) + 1
                if after < len(tokens) and tokens[after].casefold() in _LIST_COORDINATORS:
                    found.append((after, "LIST", ""))
                found.append((index, Slot.VERBAL, follower))
                continue
        if _ARM_SPLIT.search(token) and len(_ARM_SPLIT.split(token)) == 2:
            if all(_is_mention_shaped(side) for side in _ARM_SPLIT.split(token)):
                found.append((index, Slot.ARM_NOTATION, token))
    return found


def relations_in(text: str, locus: str, *, description: bool = False) -> RelationReading:
    """Read one locus. ``description`` applies the history/combination boundary (L3)."""

    tokens = _tokens(text)
    slots = _slots(tokens)
    if not slots:
        return RelationReading()
    if any(kind == "LIST" for _, kind, _ in slots):
        return RelationReading(refusal="list_coordinated_slot")
    if description:
        markers = [
            index
            for index, token in enumerate(tokens)
            if token.casefold() in _HISTORY_MARKERS | _COMBINATION_MARKERS
        ]
        if markers and any(index > markers[0] for index, _, _ in slots):
            return RelationReading(refusal="slot_after_history_or_combination_marker")
    relations: list[TargetRelation] = []
    for index, slot, argument in slots:
        if not _is_mention_shaped(argument):
            # "anti-tumor", "patient-specific": a construction, but not about a target.
            continue
        if slot in {Slot.ANTI_PREFIX, Slot.ATTRIBUTIVE_SUFFIX}:
            nxt = tokens[index + 1].casefold() if index + 1 < len(tokens) else ""
            if nxt in _CLASS_NOUNS:
                return RelationReading(refusal="class_noun_modifier")
        try:
            relations.extend(_read_mention(argument, slot=slot, locus=locus))
        except _Unreadable as error:
            return RelationReading(refusal=str(error))
    explicit = {r.canonical_id for r in relations if r.slot in EXPLICIT_SLOTS}
    juxtaposed = {r.canonical_id for r in relations if r.slot == Slot.CAR_HEAD}
    if explicit and juxtaposed and explicit != juxtaposed:
        return RelationReading(refusal="car_head_disagrees_with_explicit_slot")
    unique = {(r.canonical_id, r.slot, r.surface): r for r in relations}
    return RelationReading(relations=tuple(unique[key] for key in sorted(unique)))


@dataclass(frozen=True)
class RecordReading:
    """A whole intervention record: its target set, or why it has none."""

    targets: tuple[str, ...] = ()
    relations: tuple[TargetRelation, ...] = ()
    refusal: str | None = None


def read_record_loci(
    name: str, other_names: list[str], description: str
) -> RecordReading:
    """Read every product-describing locus and require them to agree (L1, L2, R2, R3)."""

    readings = [relations_in(name, "name")]
    readings.extend(
        relations_in(other, f"otherNames[{index}]") for index, other in enumerate(other_names)
    )
    readings.append(
        relations_in(first_sentence(description), "description[0]", description=True)
    )
    for reading in readings:
        if reading.refusal:
            return RecordReading(refusal=reading.refusal)
    spoken = [reading.targets for reading in readings if reading.targets]
    if not spoken:
        return RecordReading()
    if any(targets != spoken[0] for targets in spoken):
        return RecordReading(refusal="loci_disagree")
    relations = tuple(relation for reading in readings for relation in reading.relations)
    return RecordReading(targets=tuple(sorted(spoken[0])), relations=relations)
