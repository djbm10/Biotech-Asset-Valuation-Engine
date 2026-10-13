"""Synthetic structural controls, not authority assertions."""

import pytest
from certificates import classify


def test_conflict_cannot_be_overridden_by_other_agreement():
    assert (
        classify(
            {
                "scope": "PROPOSAL",
                "primary_conflicts": ["gene:A != gene:B"],
                "gene_identity_supported": True,
            }
        )[0]
        == "CONFLICT"
    )


@pytest.mark.parametrize("scope", ["PROPOSAL", "RESOLVER_GROUP"])
def test_union_or_synonym_does_not_inherit_gene_certificate(scope):
    assert (
        classify({"scope": scope, "primary_conflicts": [], "gene_identity_supported": True})[0]
        == "AMBIGUOUS"
    )


@pytest.mark.parametrize(
    "kind",
    [
        "CHIMERIC PROTEIN",
        "PROTEIN COMPLEX",
        "PROTEIN COMPLEX GROUP",
        "PROTEIN FAMILY",
        "PROTEIN-PROTEIN INTERACTION",
    ],
)
def test_typed_relations_never_certify_a_constituent(kind):
    assert classify(
        {
            "scope": "STRUCTURED_TARGET",
            "target_type": kind,
            "target_exists": True,
            "complete_membership": True,
        }
    )[0] == ("CERTIFIED_RELATIONAL_ENTITY")


def test_missing_evidence_and_incomplete_membership_abstain():
    assert classify({"scope": "STRUCTURED_TARGET", "target_exists": False})[0] == "UNRESOLVED"
    assert (
        classify(
            {
                "scope": "STRUCTURED_TARGET",
                "target_exists": True,
                "target_type": "PROTEIN COMPLEX",
                "complete_membership": False,
            }
        )[0]
        == "AMBIGUOUS"
    )


@pytest.mark.parametrize("supported", [True, False])
def test_positive_primary_and_protein_require_affirmative_evidence(supported):
    expected = "CERTIFIED_SINGLE_ENTITY" if supported else "AMBIGUOUS"
    assert (
        classify({"scope": "PRIMARY_ASSERTION", "gene_identity_supported": supported})[0]
        == expected
    )
    assert (
        classify({"scope": "PROTEIN_COMPONENT", "protein_identity_supported": supported})[0]
        == expected
    )
