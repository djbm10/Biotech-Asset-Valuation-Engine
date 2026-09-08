"""Drug -> target authority: what it asserts, and what it refuses to assert."""

from __future__ import annotations


from bve.se.ontology.mechanisms import (
    AssertionStatus,
    DrugTargetAuthority,
    DrugTargetEdge,
    EdgeStatus,
    TargetRelationship,
    build_edges,
    canonical_ids_by_source_id,
    parse_chembl_mechanism,
)

PEMBROLIZUMAB_MECHANISM = {
    "mec_id": 2300,
    "molecule_chembl_id": "CHEMBL3137343",
    "parent_molecule_chembl_id": "CHEMBL3137343",
    "target_chembl_id": "CHEMBL3307223",
    "action_type": "INHIBITOR",
    "mechanism_of_action": "Programmed cell death protein 1 inhibitor",
    "direct_interaction": 1,
}


def _edge(drug, target, *, source="chembl", status=EdgeStatus.USABLE):
    return DrugTargetEdge(
        canonical_drug_id=drug,
        canonical_target_id=target,
        relationship_type=TargetRelationship.DIRECT_TARGET,
        source=source,
        source_release="ChEMBL_37",
        source_record_id="1",
        evidence_hash="hash",
        status=status,
    )


class TestMechanismParsing:
    def test_a_mechanism_row_carries_its_own_provenance(self) -> None:
        row = parse_chembl_mechanism(PEMBROLIZUMAB_MECHANISM)
        assert row is not None
        assert row.drug_source_id == "CHEMBL3137343"
        assert row.target_source_id == "CHEMBL3307223"
        assert row.action_type == "INHIBITOR"
        assert row.direct_interaction is True
        assert row.evidence_hash

    def test_the_hash_changes_when_the_upstream_row_changes(self) -> None:
        # The hash exists so a rebuilt edge can be checked against the row it claims to
        # come from; a hash that ignored the assertion would not do that.
        changed = {**PEMBROLIZUMAB_MECHANISM, "target_chembl_id": "CHEMBL3580522"}
        assert parse_chembl_mechanism(PEMBROLIZUMAB_MECHANISM).evidence_hash != (
            parse_chembl_mechanism(changed).evidence_hash
        )

    def test_a_salt_mechanism_attaches_to_the_parent_molecule(self) -> None:
        row = parse_chembl_mechanism(
            {**PEMBROLIZUMAB_MECHANISM, "molecule_chembl_id": "CHEMBL999", "parent_molecule_chembl_id": "CHEMBL1"}
        )
        assert row is not None
        assert row.drug_source_id == "CHEMBL1"

    def test_a_row_naming_no_molecule_is_skipped(self) -> None:
        assert parse_chembl_mechanism({"mec_id": 1, "target_chembl_id": "CHEMBL2"}) is None

    def test_an_indirect_mechanism_is_not_called_a_direct_target(self) -> None:
        row = parse_chembl_mechanism({**PEMBROLIZUMAB_MECHANISM, "direct_interaction": 0})
        edges = build_edges(
            [row],
            source_release="ChEMBL_37",
            drug_ids={"CHEMBL3137343": "DRUG:PEMBROLIZUMAB"},
            target_ids={"CHEMBL3307223": "TARGET:PDCD1"},
        )
        assert edges[0].relationship_type is TargetRelationship.UNKNOWN


class TestSourceIdMapping:
    def test_source_ids_map_through_the_records_not_the_alias_index(self) -> None:
        # resolve() indexes alias strings, so looking up "CHEMBL3307223" by name finds
        # nothing. The map has to come from the records the resolver grouped.
        class _Record:
            source = "chembl"
            source_id = "CHEMBL3307223"

        class _Entity:
            canonical_id = "TARGET:PDCD1"
            source_records = [_Record()]

        assert canonical_ids_by_source_id([_Entity()], source="chembl") == {
            "CHEMBL3307223": "TARGET:PDCD1"
        }


class TestEdgeConstruction:
    def test_an_unmappable_target_is_kept_and_labelled(self) -> None:
        # Dropping it would make it indistinguishable from a drug the authority never
        # mentioned, which is the one distinction this layer exists to preserve.
        row = parse_chembl_mechanism({**PEMBROLIZUMAB_MECHANISM, "target_chembl_id": "CHEMBL_COMPLEX"})
        edges = build_edges(
            [row],
            source_release="ChEMBL_37",
            drug_ids={"CHEMBL3137343": "DRUG:PEMBROLIZUMAB"},
            target_ids={},
        )
        assert edges[0].status is EdgeStatus.TARGET_NOT_IN_SNAPSHOT
        assert edges[0].target_source_id == "CHEMBL_COMPLEX"
        assert edges[0].canonical_target_id is None

    def test_a_usable_edge_records_the_release_it_came_from(self) -> None:
        edges = build_edges(
            [parse_chembl_mechanism(PEMBROLIZUMAB_MECHANISM)],
            source_release="ChEMBL_37",
            drug_ids={"CHEMBL3137343": "DRUG:PEMBROLIZUMAB"},
            target_ids={"CHEMBL3307223": "TARGET:PDCD1"},
        )
        assert edges[0].status is EdgeStatus.USABLE
        assert edges[0].source_release == "ChEMBL_37"
        assert edges[0].source_record_id == "2300"


class TestAuthorityClassification:
    def test_a_documented_target_is_confirmed(self) -> None:
        authority = DrugTargetAuthority([_edge("DRUG:PEMBROLIZUMAB", "TARGET:PDCD1")])
        assert authority.classify("DRUG:PEMBROLIZUMAB", "TARGET:PDCD1") is (
            AssertionStatus.CONFIRMED_TARGET
        )

    def test_a_different_documented_target_is_a_mismatch_not_a_confirmation(self) -> None:
        # Durvalumab is the sharpest case: same pathway, different gene.
        authority = DrugTargetAuthority([_edge("DRUG:DURVALUMAB", "TARGET:CD274")])
        assert authority.classify("DRUG:DURVALUMAB", "TARGET:PDCD1") is AssertionStatus.OTHER_TARGET

    def test_silence_is_unresolved_never_a_negative(self) -> None:
        authority = DrugTargetAuthority([])
        assert authority.classify("DRUG:IBI363", "TARGET:PDCD1") is AssertionStatus.UNRESOLVED

    def test_an_unmappable_target_leaves_the_drug_unresolved(self) -> None:
        # There is an edge, but nothing comparable to a canonical target, so the drug
        # must not fall through to OTHER_TARGET on the strength of it.
        authority = DrugTargetAuthority(
            [_edge("DRUG:X", None, status=EdgeStatus.TARGET_NOT_IN_SNAPSHOT)]
        )
        assert authority.classify("DRUG:X", "TARGET:PDCD1") is AssertionStatus.UNRESOLVED

    def test_every_supported_target_survives(self) -> None:
        # A bispecific keeps both arms; collapsing to one would discard half the evidence.
        authority = DrugTargetAuthority(
            [_edge("DRUG:IVONESCIMAB", "TARGET:PDCD1"), _edge("DRUG:IVONESCIMAB", "TARGET:VEGFA")]
        )
        assert authority.targets_of("DRUG:IVONESCIMAB") == ("TARGET:PDCD1", "TARGET:VEGFA")
        assert authority.classify("DRUG:IVONESCIMAB", "TARGET:PDCD1") is (
            AssertionStatus.CONFIRMED_TARGET
        )

    def test_sources_that_disagree_stay_in_conflict(self) -> None:
        authority = DrugTargetAuthority(
            [
                _edge("DRUG:X", "TARGET:PDCD1", source="chembl"),
                _edge("DRUG:X", "TARGET:CD274", source="open_targets"),
            ]
        )
        assert authority.classify("DRUG:X", "TARGET:PDCD1") is AssertionStatus.CONFLICTING

    def test_one_source_naming_two_targets_is_not_a_conflict(self) -> None:
        # Multiple targets from a single source is a multispecific, not a disagreement.
        authority = DrugTargetAuthority(
            [
                _edge("DRUG:X", "TARGET:PDCD1", source="chembl"),
                _edge("DRUG:X", "TARGET:VEGFA", source="chembl"),
            ]
        )
        assert authority.classify("DRUG:X", "TARGET:PDCD1") is AssertionStatus.CONFIRMED_TARGET
