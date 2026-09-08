"""What an asset is documented to act on, kept separate from what was searched for.

A discovery run scoped to PDCD1 used to let every candidate it returned inherit PDCD1,
which is query membership masquerading as evidence. This module holds the other thing: a
table of drug -> target edges, each one carrying the upstream row it came from, so a
candidate's targets can be stated on its own evidence.

Three rules the shape of this module exists to enforce:

* **Authority silence is not a negative.** A drug with no mechanism row is ``UNRESOLVED``,
  never ``OTHER_TARGET``. Missing evidence and contrary evidence are different answers and
  are never allowed to collapse into each other.
* **A drug may act on more than one target.** Edges are a list, never a winner. A
  bispecific keeps every target its authority supports.
* **Disagreement survives.** Edges are per-source; a second source contradicting the first
  produces ``CONFLICTING``, not a silent election.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from enum import Enum
from typing import Any, Iterable, Mapping

from pydantic import Field

from bve.se.schemas.contracts import StrictModel

SOURCE_NAME = "chembl"


class TargetRelationship(str, Enum):
    """How the asset relates to the target, as far as the authority establishes."""

    #: The authority records the asset binding this target itself.
    DIRECT_TARGET = "DIRECT_TARGET"
    #: One arm of a multispecific, or one member of a documented complex.
    MULTISPECIFIC_COMPONENT = "MULTISPECIFIC_COMPONENT"
    #: A component of a coformulated product.
    FORMULATION_COMPONENT = "FORMULATION_COMPONENT"
    #: Co-administered, but not documented to act on the target.
    NON_TARGETING_COMBINATION_PARTNER = "NON_TARGETING_COMBINATION_PARTNER"
    #: An edge exists but the authority does not establish direct interaction.
    UNKNOWN = "UNKNOWN"


class EdgeStatus(str, Enum):
    """Whether an edge can be used as evidence about a target."""

    #: The edge resolves end to end: both drug and target are in the snapshot.
    USABLE = "USABLE"
    #: The mechanism names a target the snapshot cannot map — a protein complex, a
    #: non-human target, a protein family. The edge is real; it just cannot be compared
    #: to a canonical target id, so it must not be read as evidence either way.
    TARGET_NOT_IN_SNAPSHOT = "TARGET_NOT_IN_SNAPSHOT"
    #: The mechanism names a molecule the drug layer does not contain.
    DRUG_NOT_IN_SNAPSHOT = "DRUG_NOT_IN_SNAPSHOT"


class AssertionStatus(str, Enum):
    """What the authority layer concludes about one drug and one target of interest."""

    CONFIRMED_TARGET = "CONFIRMED_TARGET"
    #: The drug has usable edges, none of them to the target asked about.
    OTHER_TARGET = "OTHER_TARGET"
    #: Sources disagree. Preserved rather than elected.
    CONFLICTING = "CONFLICTING"
    #: No authority speaks to this drug. Not a negative.
    UNRESOLVED = "UNRESOLVED"


class MechanismRow(StrictModel):
    """One upstream mechanism record, before any canonical id is attached."""

    source: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    drug_source_id: str = Field(min_length=1)
    target_source_id: str | None = None
    action_type: str | None = None
    mechanism_of_action: str | None = None
    direct_interaction: bool = False
    evidence_hash: str = Field(min_length=1)


class DrugTargetEdge(StrictModel):
    """One authority-backed statement that a drug acts on a target."""

    canonical_drug_id: str = Field(min_length=1)
    canonical_target_id: str | None = None
    relationship_type: TargetRelationship
    action_type: str | None = None
    source: str = Field(min_length=1)
    source_release: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    evidence_hash: str = Field(min_length=1)
    status: EdgeStatus
    #: The upstream target id, kept even when it cannot be mapped, so an unmapped edge
    #: can be diagnosed rather than merely counted.
    target_source_id: str | None = None


def mechanism_evidence_hash(record: Mapping[str, Any]) -> str:
    """A stable digest of the upstream row, so an edge can be re-verified after a rebuild."""

    payload = {
        key: record.get(key)
        for key in (
            "mec_id",
            "molecule_chembl_id",
            "target_chembl_id",
            "action_type",
            "mechanism_of_action",
            "direct_interaction",
        )
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def parse_chembl_mechanism(record: Mapping[str, Any]) -> MechanismRow | None:
    """Convert one ChEMBL mechanism row; ``None`` when it names no molecule.

    ``parent_molecule_chembl_id`` is preferred over ``molecule_chembl_id`` where they
    differ: ChEMBL attaches mechanisms to salt and formulation children as well as to the
    parent, and the parent is the identity the drug layer indexes.
    """

    drug_id = record.get("parent_molecule_chembl_id") or record.get("molecule_chembl_id")
    if not isinstance(drug_id, str) or not drug_id.strip():
        return None
    mec_id = record.get("mec_id")
    if mec_id is None:
        return None

    target_id = record.get("target_chembl_id")
    return MechanismRow(
        source=SOURCE_NAME,
        source_record_id=str(mec_id),
        drug_source_id=drug_id,
        target_source_id=target_id if isinstance(target_id, str) and target_id.strip() else None,
        action_type=(record.get("action_type") or None),
        mechanism_of_action=(record.get("mechanism_of_action") or None),
        direct_interaction=bool(record.get("direct_interaction")),
        evidence_hash=mechanism_evidence_hash(record),
    )


def canonical_ids_by_source_id(
    entities: Iterable[Any], *, source: str
) -> dict[str, str]:
    """Map one source's ids onto canonical ids, straight from the snapshot records.

    The resolver indexes alias *strings*, not ``source_id``, so ``resolve("CHEMBL3307223")``
    does not find the record it names. Mechanism rows speak only in source ids, so the map
    is built from the source records the resolver grouped, rather than by looking anything
    up by name — which would reintroduce exactly the string matching this layer avoids.

    Takes ``CanonicalEntity`` objects; typed loosely to keep the resolver import one-way.
    """

    mapping: dict[str, str] = {}
    for entity in entities:
        for record in entity.source_records:
            if record.source == source:
                mapping[record.source_id] = entity.canonical_id
    return mapping


def build_edges(
    rows: Iterable[MechanismRow],
    *,
    source_release: str,
    drug_ids: Mapping[str, str],
    target_ids: Mapping[str, str],
) -> list[DrugTargetEdge]:
    """Attach canonical ids to mechanism rows, keeping the ones that do not map.

    An unmappable row is kept with an explanatory status instead of being dropped: a
    dropped row is indistinguishable from a drug the authority never mentioned, and that
    is exactly the distinction this layer exists to preserve.
    """

    edges: list[DrugTargetEdge] = []
    for row in rows:
        canonical_drug = drug_ids.get(row.drug_source_id)
        canonical_target = target_ids.get(row.target_source_id or "")
        if canonical_drug is None:
            status = EdgeStatus.DRUG_NOT_IN_SNAPSHOT
        elif canonical_target is None:
            status = EdgeStatus.TARGET_NOT_IN_SNAPSHOT
        else:
            status = EdgeStatus.USABLE
        edges.append(
            DrugTargetEdge(
                canonical_drug_id=canonical_drug or f"{row.source}:{row.drug_source_id}",
                canonical_target_id=canonical_target,
                relationship_type=(
                    TargetRelationship.DIRECT_TARGET
                    if row.direct_interaction
                    else TargetRelationship.UNKNOWN
                ),
                action_type=row.action_type,
                source=row.source,
                source_release=source_release,
                source_record_id=row.source_record_id,
                evidence_hash=row.evidence_hash,
                status=status,
                target_source_id=row.target_source_id,
            )
        )
    return edges


class DrugTargetAuthority:
    """Answers one question: what does authoritative evidence say this drug acts on?

    Deliberately narrow. It never sees a query, a trial, or a sponsor, so it cannot be
    talked into asserting a target because of the context an asset was found in.
    """

    def __init__(self, edges: Iterable[DrugTargetEdge]) -> None:
        self._by_drug: dict[str, list[DrugTargetEdge]] = defaultdict(list)
        for edge in edges:
            self._by_drug[edge.canonical_drug_id].append(edge)

    def edges_for(self, canonical_drug_id: str) -> tuple[DrugTargetEdge, ...]:
        return tuple(self._by_drug.get(canonical_drug_id, ()))

    def _evidence(self, canonical_drug_id: str) -> list[DrugTargetEdge]:
        """Edges that actually establish what the asset binds.

        An edge whose relationship is ``UNKNOWN`` is excluded. Upstream, those are the
        rows naming a protein family, complex or group: the row lists every member gene,
        so reading each one as a bound target asserts something the source never said.
        Two thirds of the Open Targets mechanism pairs are of that kind, so this is the
        difference between a second authority and a second source of inherited targets.
        Such an edge is not evidence *against* a target either -- it simply does not speak.
        """

        return [
            edge
            for edge in self.edges_for(canonical_drug_id)
            if edge.status is EdgeStatus.USABLE
            and edge.relationship_type is TargetRelationship.DIRECT_TARGET
        ]

    def targets_of(self, canonical_drug_id: str) -> tuple[str, ...]:
        """Every target the authority supports, in canonical id order.

        A list, never a winner: a bispecific keeps both arms.
        """

        return tuple(
            sorted(
                {
                    edge.canonical_target_id
                    for edge in self._evidence(canonical_drug_id)
                    if edge.canonical_target_id
                }
            )
        )

    def classify(self, canonical_drug_id: str, canonical_target_id: str) -> AssertionStatus:
        """Classify one drug against one target of interest.

        The ordering of the checks is the point. Silence is tested before mismatch, so a
        drug the authority has never heard of can never come back as a negative.
        """

        usable = self._evidence(canonical_drug_id)
        if not usable:
            # No mechanism at all, one naming a target the snapshot cannot map, or one
            # that does not establish direct binding. All three are absence of comparable
            # evidence, not evidence of absence.
            return AssertionStatus.UNRESOLVED

        supporting = {
            edge.source for edge in usable if edge.canonical_target_id == canonical_target_id
        }
        if not supporting:
            return AssertionStatus.OTHER_TARGET

        # A source that carries edges for this drug but none to this target contradicts a
        # source that does. With one source that cannot happen; with two it must be shown.
        contradicting = {edge.source for edge in usable} - supporting
        if contradicting:
            return AssertionStatus.CONFLICTING
        return AssertionStatus.CONFIRMED_TARGET
