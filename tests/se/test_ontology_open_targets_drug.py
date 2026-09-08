"""Open Targets as a second drug authority, with the two safeguards it exists under."""

from __future__ import annotations

from bve.se.ontology.records import AliasType
from bve.se.ontology.sources.open_targets_drug import (
    expand_open_targets_moa,
    parse_open_targets_drug,
    parse_open_targets_moa,
)

IVONESCIMAB = {
    "id": "CHEMBL4650319",
    "name": "IVONESCIMAB",
    "synonyms": [
        {"label": "AK-112", "source": "chembl"},
        {"label": "ivonescimab plus chemotherapy", "source": "aact"},
    ],
    "tradeNames": [{"label": "Yiqijia", "source": "chembl"}],
    "inchiKey": None,
    "childChemblIds": ["CHEMBL9999999"],
}


def _alias_values(record, alias_type):
    return {alias.value for alias in record.aliases if alias.alias_type is alias_type}


class TestDrugIdentity:
    def test_chembl_sourced_labels_are_bound(self):
        record = parse_open_targets_drug(IVONESCIMAB)
        assert record.source_id == "CHEMBL4650319"
        assert _alias_values(record, AliasType.APPROVED_NAME) == {"IVONESCIMAB"}
        assert _alias_values(record, AliasType.SYNONYM) == {"AK-112"}
        assert _alias_values(record, AliasType.TRADE_NAME) == {"Yiqijia"}

    def test_aact_free_text_is_dropped(self):
        record = parse_open_targets_drug(IVONESCIMAB)
        assert all("chemotherapy" not in alias.value for alias in record.aliases)

    def test_bare_string_labels_carry_no_provenance_and_are_dropped(self):
        record = parse_open_targets_drug({**IVONESCIMAB, "synonyms": ["AK112"]})
        assert _alias_values(record, AliasType.SYNONYM) == set()

    def test_child_ids_are_provenance_never_a_join_key_or_alias(self):
        record = parse_open_targets_drug(IVONESCIMAB)
        assert record.xrefs["chembl"] == ["CHEMBL4650319"]
        assert record.xrefs["chembl_child"] == ["CHEMBL9999999"]
        # The identifier grouping keys off ``chembl``; a child id under its own namespace
        # cannot merge a coformulation with its components.
        assert "CHEMBL9999999" not in record.xrefs["chembl"]
        assert all(alias.value != "CHEMBL9999999" for alias in record.aliases)

    def test_rows_without_an_id_or_a_name_are_skipped(self):
        assert parse_open_targets_drug({"name": "thing"}) is None
        assert parse_open_targets_drug({"id": "CHEMBL1", "name": "  "}) is None


class TestMechanismExpansion:
    def test_single_protein_row_is_direct(self):
        row = parse_open_targets_moa(
            {
                "chemblIds": ["CHEMBL3137343"],
                "targets": ["ENSG00000188389"],
                "actionType": "INHIBITOR",
                "targetType": "single protein",
            }
        )
        assert row.is_single_protein
        assert expand_open_targets_moa([row])[0].direct_interaction is True

    def test_protein_family_row_is_not_direct(self):
        row = parse_open_targets_moa(
            {
                "chemblIds": ["CHEMBL1"],
                "targets": ["ENSG1", "ENSG2"],
                "targetType": "protein family",
            }
        )
        assert not row.is_single_protein
        assert [r.direct_interaction for r in expand_open_targets_moa([row])] == [False, False]

    def test_one_row_expands_to_every_pair_sharing_its_evidence_hash(self):
        row = parse_open_targets_moa(
            {
                "chemblIds": ["CHEMBL1", "CHEMBL2"],
                "targets": ["ENSG1", "ENSG2"],
                "targetType": "single protein",
            }
        )
        rows = expand_open_targets_moa([row])
        assert {(r.drug_source_id, r.target_source_id) for r in rows} == {
            ("CHEMBL1", "ENSG1"),
            ("CHEMBL1", "ENSG2"),
            ("CHEMBL2", "ENSG1"),
            ("CHEMBL2", "ENSG2"),
        }
        assert {r.evidence_hash for r in rows} == {row.evidence_hash}

    def test_rows_linking_nothing_are_skipped(self):
        assert parse_open_targets_moa({"chemblIds": [], "targets": ["ENSG1"]}) is None
        assert parse_open_targets_moa({"chemblIds": ["CHEMBL1"], "targets": []}) is None

    def test_hash_distinguishes_different_mechanisms(self):
        base = {"chemblIds": ["CHEMBL1"], "targets": ["ENSG1"], "targetType": "single protein"}
        assert (
            parse_open_targets_moa({**base, "actionType": "INHIBITOR"}).evidence_hash
            != parse_open_targets_moa({**base, "actionType": "AGONIST"}).evidence_hash
        )
