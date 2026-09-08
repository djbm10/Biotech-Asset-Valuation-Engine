"""Versioned, on-disk ontology snapshots.

A snapshot is the production input to :class:`~bve.se.ontology.resolver.BiomedicalEntityResolver`.
It is built once from bulk upstream data, stamped with the upstream releases it came
from, and then read deterministically. Pinning the snapshot version into a run manifest
is what lets an S&E run be reproduced months later even after the upstream databases move.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field, model_validator

from bve.se.ontology.mechanisms import DrugTargetAuthority, DrugTargetEdge
from bve.se.ontology.records import EntityType, SourceEntityRecord, SourceProvenance
from bve.se.schemas.contracts import StrictModel

#: Bumped whenever resolution semantics change in a way that could alter output for
#: an unchanged upstream snapshot.
#:
#: ``resolver_v2`` adds DRUG entities and canonicalized drug -> target mechanism edges.
#: The upstream releases did not move, so without a bump the combined artifact would
#: carry the same token as the target-only one it replaces while answering questions
#: that one could not answer at all.
RESOLVER_VERSION = "resolver_v2"

_RECORDS_FILENAME = "records.jsonl"
_EDGES_FILENAME = "edges.jsonl"
_MANIFEST_FILENAME = "snapshot.json"


class OntologySnapshot(StrictModel):
    """An immutable, versioned set of source records plus their provenance."""

    sources: list[SourceProvenance] = Field(min_length=1)
    resolver_version: str = RESOLVER_VERSION
    records: list[SourceEntityRecord] = Field(default_factory=list)
    #: Drug -> target mechanism edges, canonicalized at build time. Kept in the snapshot
    #: rather than derived on read so that what a published artifact asserts about an
    #: asset is fixed by the artifact, not by whichever resolver happens to load it.
    edges: list[DrugTargetEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_sources(self) -> "OntologySnapshot":
        names = [source.source for source in self.sources]
        if len(names) != len(set(names)):
            raise ValueError("OntologySnapshot cannot carry two provenance entries for one source")
        known = set(names)
        unknown = sorted({record.source for record in self.records} - known)
        if unknown:
            raise ValueError(f"records reference sources with no provenance entry: {', '.join(unknown)}")
        unknown_edges = sorted({edge.source for edge in self.edges} - known)
        if unknown_edges:
            raise ValueError(
                f"edges reference sources with no provenance entry: {', '.join(unknown_edges)}"
            )
        return self

    @property
    def ontology_version(self) -> str:
        """A stable version token, e.g. ``open_targets_26.06__chembl_36__resolver_v1``.

        Sources are sorted by name so the token does not depend on build order.
        """

        tokens = sorted(source.version_token for source in self.sources)
        return "__".join([*tokens, self.resolver_version])

    @property
    def drug_target_authority(self) -> "DrugTargetAuthority":
        """The authority view over this snapshot's edges."""

        return DrugTargetAuthority(self.edges)

    def records_for(self, entity_type: EntityType) -> tuple[SourceEntityRecord, ...]:
        return tuple(record for record in self.records if record.entity_type == entity_type)

    def write(self, directory: Path) -> Path:
        """Write the snapshot as a manifest plus a newline-delimited record stream."""

        directory.mkdir(parents=True, exist_ok=True)
        manifest = self.model_dump(mode="json", exclude={"records", "edges"})
        manifest["ontology_version"] = self.ontology_version
        (directory / _MANIFEST_FILENAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        with (directory / _RECORDS_FILENAME).open("w", encoding="utf-8") as handle:
            for record in self.records:
                handle.write(json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n")
        with (directory / _EDGES_FILENAME).open("w", encoding="utf-8") as handle:
            for edge in self.edges:
                handle.write(json.dumps(edge.model_dump(mode="json"), sort_keys=True) + "\n")
        return directory

    @classmethod
    def read(cls, directory: Path) -> "OntologySnapshot":
        manifest_path = directory / _MANIFEST_FILENAME
        if not manifest_path.is_file():
            raise FileNotFoundError(f"no ontology snapshot manifest at {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        # ``ontology_version`` is derived on read; it is written only for human inspection.
        manifest.pop("ontology_version", None)

        records: list[SourceEntityRecord] = []
        records_path = directory / _RECORDS_FILENAME
        if records_path.is_file():
            with records_path.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        records.append(SourceEntityRecord.model_validate_json(line))
        edges: list[DrugTargetEdge] = []
        edges_path = directory / _EDGES_FILENAME
        if edges_path.is_file():
            with edges_path.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        edges.append(DrugTargetEdge.model_validate_json(line))
        return cls(**manifest, records=records, edges=edges)
