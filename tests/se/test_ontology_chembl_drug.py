"""ChEMBL molecule parsing: drug identity, and what it refuses to assert."""

from __future__ import annotations

from bve.se.ontology.records import AliasType, EntityType, normalize_lookup_key
from bve.se.ontology.sources.chembl_drug import parse_chembl_molecule

# Trimmed from the live ChEMBL_37 record. Budigalimab is the case that motivated the
# layer: the trial registry calls it ABBV-181, and only an upstream source can say that
# is the same asset.
BUDIGALIMAB = {
    "molecule_chembl_id": "CHEMBL4297858",
    "pref_name": "BUDIGALIMAB",
    "molecule_type": "Antibody",
    "max_phase": 2.0,
    "molecule_structures": None,
    "molecule_synonyms": [
        {"molecule_synonym": "Abbv-181", "syn_type": "OTHER"},
        {"molecule_synonym": "ABBV-181", "syn_type": "RESEARCH_CODE"},
        {"molecule_synonym": "ABBV181", "syn_type": "RESEARCH_CODE"},
        {"molecule_synonym": "Budigalimab", "syn_type": "INN"},
        {"molecule_synonym": "Budigalimab", "syn_type": "USAN"},
        {"molecule_synonym": "PR-1648817", "syn_type": "RESEARCH_CODE"},
    ],
}


def _alias_types(record, value):
    return {
        alias.alias_type for alias in record.all_aliases() if alias.normalized == normalize_lookup_key(value)
    }


class TestMoleculeIdentity:
    def test_a_named_molecule_becomes_a_drug_entity(self) -> None:
        record = parse_chembl_molecule(BUDIGALIMAB)
        assert record is not None
        assert record.entity_type is EntityType.DRUG
        assert record.source_id == "CHEMBL4297858"
        assert record.xrefs["chembl"] == ["CHEMBL4297858"]

    def test_development_codes_are_typed_as_such(self) -> None:
        # The registry spelling of an early asset is almost always the research code, so
        # losing this type would mean losing the only string that ever matches.
        record = parse_chembl_molecule(BUDIGALIMAB)
        assert record is not None
        assert AliasType.DEVELOPMENT_CODE in _alias_types(record, "ABBV-181")
        assert AliasType.DEVELOPMENT_CODE in _alias_types(record, "PR-1648817")

    def test_inn_and_usan_names_are_approved_names(self) -> None:
        record = parse_chembl_molecule(BUDIGALIMAB)
        assert record is not None
        assert AliasType.APPROVED_NAME in _alias_types(record, "Budigalimab")

    def test_case_variants_of_one_synonym_collapse(self) -> None:
        # "Abbv-181" and "ABBV-181" are one string to the resolver; carrying both would
        # inflate the alias count without adding a reachable identity.
        record = parse_chembl_molecule(BUDIGALIMAB)
        assert record is not None
        research_codes = [
            alias.normalized
            for alias in record.aliases
            if alias.alias_type is AliasType.DEVELOPMENT_CODE
        ]
        assert research_codes.count("abbv 181") == 1

    def test_a_structure_contributes_an_inchikey_join_key(self) -> None:
        record = parse_chembl_molecule(
            {
                "molecule_chembl_id": "CHEMBL1351",
                "pref_name": "CARBOPLATIN",
                "molecule_structures": {"standard_inchi_key": "OLESAACUTLOWQZ-UHFFFAOYSA-L"},
            }
        )
        assert record is not None
        assert record.join_keys("inchikey") == ("OLESAACUTLOWQZ-UHFFFAOYSA-L",)

    def test_an_antibody_without_a_structure_still_resolves(self) -> None:
        record = parse_chembl_molecule(BUDIGALIMAB)
        assert record is not None
        assert "inchikey" not in record.xrefs

    def test_an_unnamed_structure_is_skipped(self) -> None:
        assert parse_chembl_molecule({"molecule_chembl_id": "CHEMBL9", "pref_name": None}) is None

    def test_a_row_without_an_identifier_is_skipped(self) -> None:
        assert parse_chembl_molecule({"pref_name": "SOMETHING"}) is None

    def test_an_unknown_synonym_type_degrades_to_synonym(self) -> None:
        # A new ``syn_type`` upstream must not crash the build, and must not be promoted
        # to a stronger claim than "this string was associated with the molecule".
        record = parse_chembl_molecule(
            {
                "molecule_chembl_id": "CHEMBL1",
                "pref_name": "THING",
                "molecule_synonyms": [{"molecule_synonym": "Zed", "syn_type": "NEW_KIND"}],
            }
        )
        assert record is not None
        assert _alias_types(record, "Zed") == {AliasType.SYNONYM}
