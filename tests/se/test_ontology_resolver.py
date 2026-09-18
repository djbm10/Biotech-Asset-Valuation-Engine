"""Target-agnostic entity resolution: grouping, provenance, conflicts, ambiguity."""

from __future__ import annotations

from datetime import date

import pytest

from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
    SourceProvenance,
    normalize_lookup_key,
)
from bve.se.ontology.resolver import (
    BiomedicalEntityResolver,
    ConflictType,
    ResolutionStatus,
)
from bve.se.ontology.snapshot import RESOLVER_VERSION, OntologySnapshot


def _provenance(source: str, release: str) -> SourceProvenance:
    return SourceProvenance(
        source=source,
        release=release,
        retrieved_at=date(2026, 8, 15),
        locator=f"https://example.invalid/{source}/{release}",
    )


def _target(
    source: str,
    source_id: str,
    *,
    symbol: str | None = None,
    label: str | None = None,
    synonyms: tuple[str, ...] = (),
    uniprot: tuple[str, ...] = (),
) -> SourceEntityRecord:
    return SourceEntityRecord(
        source=source,
        source_id=source_id,
        entity_type=EntityType.TARGET,
        canonical_symbol=symbol,
        label=label,
        aliases=[SourceAlias(value=value, alias_type=AliasType.SYNONYM) for value in synonyms],
        xrefs={"uniprot": list(uniprot)},
    )


def _snapshot(*records: SourceEntityRecord) -> OntologySnapshot:
    sources = sorted({record.source for record in records})
    return OntologySnapshot(
        sources=[_provenance(source, "26.06" if source == "open_targets" else "36") for source in sources],
        records=list(records),
    )


@pytest.fixture
def resolver() -> BiomedicalEntityResolver:
    """Two sources describing the same target, joined only by UniProt accession."""

    return BiomedicalEntityResolver(
        _snapshot(
            _target(
                "open_targets",
                "ENSG00000188389",
                symbol="PDCD1",
                label="programmed cell death protein 1",
                synonyms=("PD-1", "PD1", "CD279", "SLEB2"),
                uniprot=("Q15116",),
            ),
            _target(
                "chembl",
                "CHEMBL3307223",
                symbol="PDCD1",
                label="Programmed cell death protein 1",
                synonyms=("PD-1",),
                uniprot=("Q15116",),
            ),
            _target(
                "open_targets",
                "ENSG00000177455",
                symbol="CD19",
                label="B-lymphocyte antigen CD19",
                synonyms=("B4", "CVID3"),
                uniprot=("P15391",),
            ),
        )
    )


class TestLookupKeys:
    @pytest.mark.parametrize("value", ["PD-1", "PD_1", "pd 1", "  PD-1  ", "PD/1"])
    def test_separator_variants_collapse(self, value: str) -> None:
        assert normalize_lookup_key(value) == "pd 1"

    def test_distinct_numbers_stay_distinct(self) -> None:
        assert normalize_lookup_key("CD19") != normalize_lookup_key("CD199")


class TestResolution:
    @pytest.mark.parametrize(
        "query",
        ["PDCD1", "PD-1", "PD1", "pd 1", "CD279", "programmed cell death protein 1"],
    )
    def test_all_spellings_reach_one_canonical_entity(
        self, resolver: BiomedicalEntityResolver, query: str
    ) -> None:
        result = resolver.resolve(query)
        assert result.status is ResolutionStatus.RESOLVED
        assert result.canonical_symbol == "PDCD1"
        assert result.canonical_id == "TARGET:PDCD1"

    def test_unknown_string_is_unresolved_not_guessed(
        self, resolver: BiomedicalEntityResolver
    ) -> None:
        result = resolver.resolve("not-a-target")
        assert result.status is ResolutionStatus.UNRESOLVED
        assert result.entity is None
        assert result.rule == "no_alias_match"

    def test_result_carries_ontology_version(self, resolver: BiomedicalEntityResolver) -> None:
        assert resolver.resolve("PDCD1").ontology_version == resolver.ontology_version

    def test_resolution_is_not_hardcoded_to_a_benchmark_target(self) -> None:
        """A target absent from the shipped stub resolves purely from snapshot data."""

        resolver = BiomedicalEntityResolver(
            _snapshot(
                _target(
                    "open_targets",
                    "ENSG00000133703",
                    symbol="KRAS",
                    label="GTPase KRas",
                    synonyms=("K-RAS", "KRAS2", "c-Ki-ras"),
                    uniprot=("P01116",),
                )
            )
        )
        assert resolver.resolve("K-RAS").canonical_id == "TARGET:KRAS"
        assert resolver.resolve("CD19").status is ResolutionStatus.UNRESOLVED


class TestCrossSourceGrouping:
    def test_records_join_on_identifier_not_name(self, resolver: BiomedicalEntityResolver) -> None:
        entity = resolver.get("TARGET:PDCD1")
        assert entity is not None
        assert entity.contributing_sources == ("chembl", "open_targets")
        assert len(entity.source_records) == 2

    def test_source_records_are_preserved_under_the_normalized_view(
        self, resolver: BiomedicalEntityResolver
    ) -> None:
        entity = resolver.get("TARGET:PDCD1")
        assert entity is not None
        assert {record.source_id for record in entity.source_records} == {
            "ENSG00000188389",
            "CHEMBL3307223",
        }

    def test_records_without_a_shared_identifier_stay_separate(self) -> None:
        resolver = BiomedicalEntityResolver(
            _snapshot(
                _target("open_targets", "ENSG1", symbol="PDCD1", uniprot=("Q15116",)),
                _target("chembl", "CHEMBL1", symbol="PDCD1LG2", uniprot=("Q9BQ51",)),
            )
        )
        assert len(resolver.entities()) == 2

    def test_alias_provenance_names_every_asserting_source(
        self, resolver: BiomedicalEntityResolver
    ) -> None:
        entity = resolver.get("TARGET:PDCD1")
        assert entity is not None
        shared = next(alias for alias in entity.aliases if alias.value == "PD-1")
        assert sorted(shared.sources) == ["chembl", "open_targets"]
        unique = next(alias for alias in entity.aliases if alias.value == "CD279")
        assert unique.sources == ["open_targets"]


class TestConflictPreservation:
    def test_symbol_disagreement_is_flagged_not_silently_resolved(self) -> None:
        resolver = BiomedicalEntityResolver(
            _snapshot(
                _target("open_targets", "ENSG1", symbol="TNFRSF17", uniprot=("Q02223",)),
                _target("chembl", "CHEMBL1", symbol="BCMA", uniprot=("Q02223",)),
            )
        )
        entity = resolver.get("TARGET:TNFRSF17")
        assert entity is not None
        conflict = next(
            flag
            for flag in entity.conflicts
            if flag.conflict_type is ConflictType.CANONICAL_SYMBOL_DISAGREEMENT
        )
        # The authority order decides the normalized value, but both survive.
        assert entity.canonical_symbol == "TNFRSF17"
        assert conflict.values == ["BCMA", "TNFRSF17"]

    def test_homonym_across_entities_is_ambiguous_not_guessed(self) -> None:
        resolver = BiomedicalEntityResolver(
            _snapshot(
                _target("open_targets", "ENSG1", symbol="ALPHA", synonyms=("SHARED",), uniprot=("P1",)),
                _target("open_targets", "ENSG2", symbol="BETA", synonyms=("SHARED",), uniprot=("P2",)),
            )
        )
        result = resolver.resolve("SHARED")
        assert result.status is ResolutionStatus.AMBIGUOUS
        assert result.entity is None
        assert [candidate.canonical_id for candidate in result.candidates] == [
            "TARGET:ALPHA",
            "TARGET:BETA",
        ]
        assert result.rule == "homonym_requires_escalation"

    def test_symbol_beats_synonym_when_that_leaves_one_candidate(self) -> None:
        resolver = BiomedicalEntityResolver(
            _snapshot(
                _target("open_targets", "ENSG1", symbol="MET", uniprot=("P1",)),
                _target("open_targets", "ENSG2", symbol="OTHER", synonyms=("MET",), uniprot=("P2",)),
            )
        )
        result = resolver.resolve("MET")
        assert result.status is ResolutionStatus.RESOLVED
        assert result.canonical_id == "TARGET:MET"
        assert result.rule == "alias_type_precedence:SYMBOL"

    def test_shared_alias_is_flagged_on_both_entities(self) -> None:
        resolver = BiomedicalEntityResolver(
            _snapshot(
                _target("open_targets", "ENSG1", symbol="ALPHA", synonyms=("SHARED",), uniprot=("P1",)),
                _target("open_targets", "ENSG2", symbol="BETA", synonyms=("SHARED",), uniprot=("P2",)),
            )
        )
        for canonical_id in ("TARGET:ALPHA", "TARGET:BETA"):
            entity = resolver.get(canonical_id)
            assert entity is not None
            assert any(
                flag.conflict_type is ConflictType.ALIAS_SHARED_ACROSS_ENTITIES
                for flag in entity.conflicts
            )


class TestQuerySeam:
    def test_aliases_for_returns_queryable_strings(self, resolver: BiomedicalEntityResolver) -> None:
        aliases = resolver.aliases_for("PDCD1")
        assert "PDCD1" in aliases
        assert "CD279" in aliases

    def test_aliases_for_unknown_target_degrades_to_empty(
        self, resolver: BiomedicalEntityResolver
    ) -> None:
        assert resolver.aliases_for("NOT_A_TARGET") == ()

    def test_descriptions_are_not_expanded_into_queries(self) -> None:
        record = SourceEntityRecord(
            source="open_targets",
            source_id="ENSG1",
            entity_type=EntityType.TARGET,
            canonical_symbol="ALPHA",
            aliases=[
                SourceAlias(value="a cell surface receptor", alias_type=AliasType.DESCRIPTION),
            ],
            xrefs={"uniprot": ["P1"]},
        )
        resolver = BiomedicalEntityResolver(_snapshot(record))
        assert resolver.aliases_for("ALPHA") == ("ALPHA",)


class TestSnapshotVersioning:
    def test_version_token_names_every_upstream_release(
        self, resolver: BiomedicalEntityResolver
    ) -> None:
        assert resolver.ontology_version == f"chembl_36__open_targets_26.06__{RESOLVER_VERSION}"

    def test_version_is_independent_of_source_order(self) -> None:
        records = (
            _target("open_targets", "ENSG1", symbol="ALPHA", uniprot=("P1",)),
            _target("chembl", "CHEMBL1", symbol="ALPHA", uniprot=("P1",)),
        )
        forward = OntologySnapshot(
            sources=[_provenance("open_targets", "26.06"), _provenance("chembl", "36")],
            records=list(records),
        )
        reverse = OntologySnapshot(
            sources=[_provenance("chembl", "36"), _provenance("open_targets", "26.06")],
            records=list(records),
        )
        assert forward.ontology_version == reverse.ontology_version

    def test_round_trip_through_disk_preserves_resolution(self, tmp_path) -> None:
        snapshot = _snapshot(
            _target(
                "open_targets",
                "ENSG1",
                symbol="PDCD1",
                synonyms=("PD-1", "CD279"),
                uniprot=("Q15116",),
            )
        )
        snapshot.write(tmp_path / "snap")
        reloaded = OntologySnapshot.read(tmp_path / "snap")

        assert reloaded.ontology_version == snapshot.ontology_version
        assert BiomedicalEntityResolver(reloaded).resolve("CD279").canonical_id == "TARGET:PDCD1"

    def test_records_must_declare_a_provenance_entry(self) -> None:
        with pytest.raises(ValueError, match="no provenance entry"):
            OntologySnapshot(
                sources=[_provenance("open_targets", "26.06")],
                records=[_target("chembl", "CHEMBL1", symbol="ALPHA", uniprot=("P1",))],
            )


class TestSharedClassifiers:
    def test_shared_ec_numbers_are_not_conflicts(self) -> None:
        """Every enzyme in a class carries the same EC number by design."""

        def enzyme(source_id: str, symbol: str, uniprot: str) -> SourceEntityRecord:
            return SourceEntityRecord(
                source="chembl",
                source_id=source_id,
                entity_type=EntityType.TARGET,
                canonical_symbol=symbol,
                aliases=[SourceAlias(value="6.4.1.2", alias_type=AliasType.XREF)],
                xrefs={"uniprot": [uniprot]},
            )

        resolver = BiomedicalEntityResolver(
            _snapshot(enzyme("CHEMBL1", "ACACA", "Q13085"), enzyme("CHEMBL2", "ACACB", "O00763"))
        )
        for canonical_id in ("TARGET:ACACA", "TARGET:ACACB"):
            entity = resolver.get(canonical_id)
            assert entity is not None
            assert entity.conflicts == []

    def test_a_shared_ec_number_still_resolves_as_ambiguous(self) -> None:
        """Not flagging it as a conflict must not make the resolver guess."""

        def enzyme(source_id: str, symbol: str, uniprot: str) -> SourceEntityRecord:
            return SourceEntityRecord(
                source="chembl",
                source_id=source_id,
                entity_type=EntityType.TARGET,
                canonical_symbol=symbol,
                aliases=[SourceAlias(value="6.4.1.2", alias_type=AliasType.XREF)],
                xrefs={"uniprot": [uniprot]},
            )

        resolver = BiomedicalEntityResolver(
            _snapshot(enzyme("CHEMBL1", "ACACA", "Q13085"), enzyme("CHEMBL2", "ACACB", "O00763"))
        )
        assert resolver.resolve("6.4.1.2").status is ResolutionStatus.AMBIGUOUS


class TestResolutionBasis:
    def test_basis_names_the_matched_alias_and_who_asserted_it(
        self, resolver: BiomedicalEntityResolver
    ) -> None:
        basis = resolver.resolve("CD279").basis
        assert basis is not None
        assert basis.observed_query == "CD279"
        assert basis.matched_alias == "CD279"
        assert basis.matched_alias_type is AliasType.SYNONYM
        assert basis.asserted_by == ["open_targets"]
        assert basis.asserting_record_keys == ["open_targets:ENSG00000188389"]

    def test_basis_reports_the_identifier_edge_that_merged_the_records(
        self, resolver: BiomedicalEntityResolver
    ) -> None:
        basis = resolver.resolve("PD-1").basis
        assert basis is not None
        assert basis.identifier_edges == ["uniprot:Q15116"]

    def test_single_source_entity_has_no_merge_edge(
        self, resolver: BiomedicalEntityResolver
    ) -> None:
        basis = resolver.resolve("CD19").basis
        assert basis is not None
        assert basis.identifier_edges == []

    def test_basis_records_the_precedence_tie_break(self) -> None:
        resolver = BiomedicalEntityResolver(
            _snapshot(
                _target("open_targets", "ENSG1", symbol="MET", uniprot=("P1",)),
                _target("open_targets", "ENSG2", symbol="OTHER", synonyms=("MET",), uniprot=("P2",)),
            )
        )
        basis = resolver.resolve("MET").basis
        assert basis is not None
        assert basis.rule == "alias_type_precedence:SYMBOL"
        assert basis.matched_alias_type is AliasType.SYMBOL

    def test_explain_renders_a_readable_derivation(
        self, resolver: BiomedicalEntityResolver
    ) -> None:
        result = resolver.resolve("PD-1")
        assert result.basis is not None
        rendered = result.basis.explain(result.canonical_symbol)
        assert rendered == (
            "'PD-1' -> synonym alias 'PD-1' asserted by chembl, open_targets -> PDCD1 "
            "-> merged on uniprot:Q15116"
        )

    def test_unresolved_and_ambiguous_carry_no_basis(self) -> None:
        resolver = BiomedicalEntityResolver(
            _snapshot(
                _target("open_targets", "ENSG1", symbol="ALPHA", synonyms=("SHARED",), uniprot=("P1",)),
                _target("open_targets", "ENSG2", symbol="BETA", synonyms=("SHARED",), uniprot=("P2",)),
            )
        )
        assert resolver.resolve("SHARED").basis is None
        assert resolver.resolve("nothing").basis is None


class TestWidelySharedAlias:
    """A junk alias shared by thousands of entities is normal in real bulk data.

    Open Targets 26.06 gives ``novel transcript`` to tens of thousands of genes.
    Flagging that must cost work proportional to the sharing group, not to its
    square, and the flags themselves must not change.
    """

    @staticmethod
    def _shared(count: int) -> BiomedicalEntityResolver:
        return BiomedicalEntityResolver(
            _snapshot(
                *(
                    _target(
                        "open_targets",
                        f"ENSG{index:011d}",
                        symbol=f"SYM{index}",
                        synonyms=("novel transcript",),
                        uniprot=(f"U{index:06d}",),
                    )
                    for index in range(count)
                )
            )
        )

    def test_every_sharer_is_flagged_once_with_the_full_id_set(self) -> None:
        resolver = self._shared(40)
        entities = resolver.entities_of_type(EntityType.TARGET)
        assert len(entities) == 40
        expected = sorted(entity.canonical_id for entity in entities)
        for entity in entities:
            shared = [
                flag
                for flag in entity.conflicts
                if flag.conflict_type is ConflictType.ALIAS_SHARED_ACROSS_ENTITIES
            ]
            assert len(shared) == 1
            assert list(shared[0].values) == expected
            assert "novel transcript" in shared[0].detail

    def test_flagging_does_not_scale_quadratically(self) -> None:
        # The quadratic form did one full sort and one whole-list copy per member,
        # so an 8x bigger group cost ~64x. Linear work leaves a wide margin here.
        import time

        def elapsed(count: int) -> float:
            start = time.perf_counter()
            self._shared(count)
            return time.perf_counter() - start

        small = elapsed(250)
        large = elapsed(2000)
        assert large < max(small * 24.0, 0.5), f"{small=:.3f}s {large=:.3f}s"
