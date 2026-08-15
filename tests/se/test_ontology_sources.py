"""Bulk source parsers, exercised against the real upstream record shapes."""

from __future__ import annotations

from datetime import date

from bve.se.ontology.records import AliasType, EntityType, SourceProvenance
from bve.se.ontology.resolver import BiomedicalEntityResolver
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.ontology.sources import parse_chembl_target, parse_open_targets_target

# Trimmed from the live ChEMBL response for CHEMBL3307223, preserving its quirks.
CHEMBL_PDCD1 = {
    "target_chembl_id": "CHEMBL3307223",
    "pref_name": "Programmed cell death protein 1",
    "target_type": "SINGLE PROTEIN",
    "organism": "Homo sapiens",
    "target_components": [
        {
            "accession": "Q15116",
            "component_type": "PROTEIN",
            "relationship": "SINGLE PROTEIN",
            "target_component_synonyms": [
                {"component_synonym": "CD_antigen=CD279", "syn_type": "UNIPROT"},
                {"component_synonym": "hPD-1", "syn_type": "UNIPROT"},
                {"component_synonym": "PD1", "syn_type": "GENE_SYMBOL_OTHER"},
                {"component_synonym": "PDCD1", "syn_type": "GENE_SYMBOL"},
                {"component_synonym": "Protein PD-1", "syn_type": "UNIPROT"},
                {"component_synonym": "Synonyms=PD1", "syn_type": "GENE_SYMBOL_OTHER"},
            ],
        }
    ],
}

OPEN_TARGETS_PDCD1 = {
    "id": "ENSG00000188389",
    "approvedSymbol": "PDCD1",
    "approvedName": "programmed cell death 1",
    "biotype": "protein_coding",
    "proteinIds": [
        {"id": "Q15116", "source": "uniprot_swissprot"},
        {"id": "ENSP00000335153", "source": "ensembl_PRO"},
    ],
    "synonyms": [
        {"label": "PD-1", "source": "HGNC"},
        {"label": "CD279", "source": "uniprot"},
    ],
    "symbolSynonyms": [{"label": "PD1", "source": "HGNC"}],
}


class TestChemblParser:
    def test_gene_symbol_becomes_the_canonical_symbol(self) -> None:
        record = parse_chembl_target(CHEMBL_PDCD1)
        assert record is not None
        assert record.canonical_symbol == "PDCD1"
        assert record.entity_type is EntityType.TARGET

    def test_uniprot_field_prefixes_are_stripped(self) -> None:
        record = parse_chembl_target(CHEMBL_PDCD1)
        assert record is not None
        values = {alias.value for alias in record.aliases}
        # The alias that only exists behind a "CD_antigen=" prefix must survive.
        assert "CD279" in values
        assert not any("=" in value for value in values)

    def test_accession_is_exposed_as_a_join_key(self) -> None:
        record = parse_chembl_target(CHEMBL_PDCD1)
        assert record is not None
        assert record.join_keys("uniprot") == ("Q15116",)

    def test_protein_complexes_are_not_joinable(self) -> None:
        """A complex must not union its member proteins into one entity."""

        record = parse_chembl_target(
            {
                "target_chembl_id": "CHEMBL2111445",
                "pref_name": "Interleukin-2 receptor",
                "target_type": "PROTEIN COMPLEX",
                "target_components": [
                    {"accession": "P01589", "target_component_synonyms": []},
                    {"accession": "P14784", "target_component_synonyms": []},
                ],
            }
        )
        assert record is not None
        assert record.join_keys("uniprot") == ()
        assert record.join_keys("uniprot_unjoinable") == ("P01589", "P14784")

    def test_record_without_an_id_is_skipped(self) -> None:
        assert parse_chembl_target({"pref_name": "orphan"}) is None


class TestOpenTargetsParser:
    def test_approved_symbol_and_name_are_captured(self) -> None:
        record = parse_open_targets_target(OPEN_TARGETS_PDCD1)
        assert record is not None
        assert record.canonical_symbol == "PDCD1"
        assert record.label == "programmed cell death 1"

    def test_only_uniprot_protein_ids_become_join_keys(self) -> None:
        record = parse_open_targets_target(OPEN_TARGETS_PDCD1)
        assert record is not None
        # The Ensembl protein ID would create false joins against ChEMBL accessions.
        assert record.join_keys("uniprot") == ("Q15116",)

    def test_symbol_synonyms_keep_symbol_specificity(self) -> None:
        record = parse_open_targets_target(OPEN_TARGETS_PDCD1)
        assert record is not None
        pd1 = next(alias for alias in record.aliases if alias.value == "PD1")
        assert pd1.alias_type is AliasType.SYMBOL

    def test_plain_string_synonym_lists_are_accepted(self) -> None:
        record = parse_open_targets_target(
            {"id": "ENSG1", "approvedSymbol": "ALPHA", "synonyms": ["A1", "A2"]}
        )
        assert record is not None
        assert {alias.value for alias in record.aliases} == {"A1", "A2"}

    def test_record_without_an_id_is_skipped(self) -> None:
        assert parse_open_targets_target({"approvedSymbol": "ALPHA"}) is None


class TestEndToEndFromRealShapes:
    def test_both_sources_resolve_to_one_entity_via_uniprot(self) -> None:
        snapshot = OntologySnapshot(
            sources=[
                SourceProvenance(
                    source="open_targets",
                    release="26.06",
                    retrieved_at=date(2026, 8, 15),
                    locator="ftp://ftp.ebi.ac.uk/pub/databases/opentargets/platform/26.06/target",
                ),
                SourceProvenance(
                    source="chembl",
                    release="36",
                    retrieved_at=date(2026, 8, 15),
                    locator="https://www.ebi.ac.uk/chembl/api/data/target",
                ),
            ],
            records=[
                parse_open_targets_target(OPEN_TARGETS_PDCD1),
                parse_chembl_target(CHEMBL_PDCD1),
            ],
        )
        resolver = BiomedicalEntityResolver(snapshot)

        assert len(resolver.entities()) == 1
        for spelling in ("PD-1", "PD1", "PDCD1", "CD279", "hPD-1", "pd 1"):
            result = resolver.resolve(spelling)
            assert result.canonical_id == "TARGET:PDCD1", spelling
        assert resolver.get("TARGET:PDCD1").contributing_sources == ("chembl", "open_targets")


class TestRealDataQuirks:
    def test_commas_in_uniprot_names_are_not_split(self) -> None:
        """Splitting on commas manufactured junk aliases like "mitochondrial"."""

        record = parse_chembl_target(
            {
                "target_chembl_id": "CHEMBL1",
                "target_type": "SINGLE PROTEIN",
                "target_components": [
                    {
                        "accession": "P80404",
                        "target_component_synonyms": [
                            {
                                "component_synonym": "4-aminobutyrate aminotransferase, mitochondrial",
                                "syn_type": "UNIPROT",
                            }
                        ],
                    }
                ],
            }
        )
        assert record is not None
        values = {alias.value for alias in record.aliases}
        assert values == {"4-aminobutyrate aminotransferase, mitochondrial"}
        assert "mitochondrial" not in values

    def test_semicolons_still_separate_multiple_values(self) -> None:
        record = parse_chembl_target(
            {
                "target_chembl_id": "CHEMBL1",
                "target_type": "SINGLE PROTEIN",
                "target_components": [
                    {
                        "accession": "Q1",
                        "target_component_synonyms": [
                            {"component_synonym": "Synonyms=PD1; hPD-1", "syn_type": "GENE_SYMBOL_OTHER"}
                        ],
                    }
                ],
            }
        )
        assert record is not None
        assert {alias.value for alias in record.aliases} == {"PD1", "hPD-1"}
