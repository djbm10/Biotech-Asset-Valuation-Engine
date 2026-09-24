"""Controls for ``docs/se_policies/asset_qualification_tiered_evidence_v3.md``.

Every name here was frozen in the policy, with its measured reason, before the rule was
written. The hard cases are hard because the v2 paired live run made them so: ``paper`` is a
genuine ChEMBL ``SYNONYM``, ``choice`` carries an Open Targets VKORC1 assertion, and bare
``Placebo`` has 35 trials and 30 owners. Nothing here may be satisfied by naming a string --
the negatives are asserted through the same function the positives use.
"""

from __future__ import annotations

import pytest

from bve.se.discovery import drug_name_shape
from bve.se.discovery.adapters import ArmRelationship, _arm_relationships
from bve.se.discovery.asset_qualification import (
    AssetEvidence,
    QualificationReason,
    is_comparator_only,
    qualification_reason,
    qualifies_as_asset,
)


class TestOntologyEvidenceIsTieredByAliasType:
    """§3a. A synonym resolves identity. It does not decide population membership."""

    @pytest.mark.parametrize("name", ["gemcitabine", "pomalidomide", "teclistamab", "AMG 420"])
    def test_an_identity_name_qualifies_directly(self, name: str) -> None:
        assert drug_name_shape.is_identity_bearing_drug_name(name) is True
        assert (
            qualification_reason(AssetEvidence(name=name))
            is QualificationReason.DIRECT_APPROVED_NAME
        )

    @pytest.mark.parametrize("name", ["paper", "choice", "frontline", "discase"])
    def test_a_corroborative_only_name_qualifies_nothing_alone(self, name: str) -> None:
        # Each is an ordinary English word the ontology carries as a synonym or a brand of
        # some other molecule. `paper` is the one v2 missed, and it reached shortlist
        # position 10 on a live run.
        assert drug_name_shape.is_corroborative_drug_name(name) is True
        assert drug_name_shape.is_identity_bearing_drug_name(name) is False
        assert qualification_reason(AssetEvidence(name=name)) is None

    @pytest.mark.parametrize("brand", ["Keytruda", "Enhertu", "Trodelvy", "Adcetris"])
    def test_a_real_brand_survives_once_something_supplies_an_entity(self, brand: str) -> None:
        # The declared trade-name cost in §4 is only a cost where the brand has no entity of
        # its own. Where it does, it keeps the default path with a named reason.
        assert qualification_reason(AssetEvidence(name=brand)) is None
        assert (
            qualification_reason(AssetEvidence(name=brand, entity_specific_link=True))
            is QualificationReason.ENTITY_CORROBORATED_SYNONYM
        )

    def test_a_name_in_both_tiers_is_treated_as_the_stronger_one(self) -> None:
        # One record's synonym is another record's approved name. The tiers must not
        # overlap, or the weaker reading of a real drug would demote it.
        direct = drug_name_shape.identity_bearing_drug_names()
        assert not (direct & drug_name_shape.corroborative_drug_names())
        assert "water" in direct  # an APPROVED_NAME, and so still directly qualifying


class TestConstructDescriptionIsCorroborationNotARoute:
    """§3b. ``choice`` is the mandatory negative control."""

    def test_a_construct_description_alone_qualifies_nothing(self) -> None:
        # Measured: `choice` reached the default path and carried a human-PoC PASS on this
        # route alone, having been matched to the warfarin brand and credited with VKORC1.
        assert qualification_reason(AssetEvidence(name="choice", identity_authority=True)) is None

    def test_a_construct_description_corroborates_once_an_entity_exists(self) -> None:
        assert (
            qualification_reason(
                AssetEvidence(
                    name="XYZ-cell product",
                    identity_authority=True,
                    entity_specific_link=True,
                )
            )
            is QualificationReason.CONSTRUCT_CORROBORATED
        )

    def test_a_target_assertion_is_not_an_entity_link(self) -> None:
        # `choice` carries target *assertions* from Open Targets and zero attributed
        # ``target_ids``; the distinction is the whole reason this control exists.
        assert qualifies_as_asset(AssetEvidence(name="choice", identity_authority=True)) is False


class TestComparatorEvidenceIsTriStateAndConservative:
    """§3c. Bare ``Placebo`` and ``HB2198`` are the opposite controls."""

    def test_an_unknown_observation_does_not_erase_a_comparator_one(self) -> None:
        # The exact v2 failure: 34 explicit placebo arms and one trial that types no arm.
        # ``all()`` read the silence as "not a comparator" and bare `Placebo` stayed #1.
        evidence = AssetEvidence(
            name="Placebo",
            structurally_typed_drug=True,
            comparator_observations=34,
            unknown_observations=1,
        )
        assert is_comparator_only(evidence) is True
        assert qualification_reason(evidence) is None

    def test_one_therapeutic_observation_establishes_a_therapy(self) -> None:
        # A marketed drug used as the control arm of one trial is still that drug.
        evidence = AssetEvidence(
            name="HB2198",
            structurally_typed_drug=True,
            comparator_observations=3,
            therapeutic_observations=1,
        )
        assert is_comparator_only(evidence) is False
        assert qualification_reason(evidence) is QualificationReason.STRUCTURED_THERAPEUTIC

    def test_structured_typing_alone_no_longer_qualifies(self) -> None:
        # Sponsors type placebo as a DRUG. That is true, and it is not the question.
        assert (
            qualification_reason(AssetEvidence(name="Novel Agent", structurally_typed_drug=True))
            is None
        )

    def test_comparator_evidence_does_not_reach_an_unobserved_name(self) -> None:
        # Counts are per asset. A name with no observations of its own is untouched by
        # another intervention's role in the same trial.
        assert is_comparator_only(AssetEvidence(name="teclistamab")) is False


class TestTheArmLinkageIsReadFromTheSourceNotAssumed:
    """§3c, last clause: verify intervention↔arm linkage directly."""

    @staticmethod
    def _protocol(arms: list[dict], interventions: list[dict] | None = None) -> dict:
        return {
            "armsInterventionsModule": {
                "armGroups": arms,
                "interventions": interventions or [],
            }
        }

    def test_a_placebo_only_arm_yields_a_comparator_observation(self) -> None:
        roles = _arm_relationships(
            self._protocol(
                [
                    {
                        "type": "EXPERIMENTAL",
                        "label": "Arm A",
                        "interventionNames": ["Drug: teclistamab"],
                    },
                    {
                        "type": "PLACEBO_COMPARATOR",
                        "label": "Arm B",
                        "interventionNames": ["Drug: Placebo"],
                    },
                ]
            )
        )
        assert roles["placebo"] is ArmRelationship.COMPARATOR
        assert roles["teclistamab"] is ArmRelationship.THERAPEUTIC

    def test_an_active_control_is_therapeutic_not_control_material(self) -> None:
        roles = _arm_relationships(
            self._protocol(
                [
                    {
                        "type": "ACTIVE_COMPARATOR",
                        "label": "Arm A",
                        "interventionNames": ["Drug: pembrolizumab"],
                    }
                ]
            )
        )
        assert roles["pembrolizumab"] is ArmRelationship.THERAPEUTIC

    def test_a_molecule_in_both_a_control_and_an_experimental_arm_is_therapeutic(self) -> None:
        roles = _arm_relationships(
            self._protocol(
                [
                    {
                        "type": "PLACEBO_COMPARATOR",
                        "label": "Arm A",
                        "interventionNames": ["Drug: Placebo", "Drug: pomalidomide"],
                    },
                    {
                        "type": "EXPERIMENTAL",
                        "label": "Arm B",
                        "interventionNames": ["Drug: pomalidomide"],
                    },
                ]
            )
        )
        assert roles["pomalidomide"] is ArmRelationship.THERAPEUTIC
        assert roles["placebo"] is ArmRelationship.COMPARATOR

    def test_a_cross_labelled_record_resolves_to_unknown_not_to_comparator(self) -> None:
        """NCT07439263, verbatim. The sponsor entered its two arms crosswise.

        The arm typed ``PLACEBO_COMPARATOR`` is *labelled* with the diluent and *lists* the
        real bispecific; the arm typed ``ACTIVE_COMPARATOR`` is labelled with the bispecific
        and lists the diluent. Both intervention linkages therefore agree with each other
        and are both wrong; only the arm labels dissent. v2 read one linkage, believed it,
        and typed a real tetravalent bispecific as control material.
        """

        drug = "HB2198, a Tetravalent Bispecific Anti-CD19/CD20 Antibody with Dual Fc Domains"
        roles = _arm_relationships(
            self._protocol(
                arms=[
                    {
                        "type": "ACTIVE_COMPARATOR",
                        "label": drug,
                        "interventionNames": ["Drug: Placebo comparator: HB2198 Diluent"],
                    },
                    {
                        "type": "PLACEBO_COMPARATOR",
                        "label": "HB2198 Diluent (IV)",
                        "interventionNames": [f"Drug: {drug}"],
                    },
                ],
                interventions=[
                    {"type": "DRUG", "name": drug, "armGroupLabels": ["HB2198 Diluent (IV)"]},
                ],
            )
        )
        key = "hb2198atetravalentbispecificanticd19cd20antibodywithdualfcdomains"
        assert roles[key] is ArmRelationship.UNKNOWN

    def test_an_arm_label_is_matched_exactly_and_never_as_a_substring(self) -> None:
        # "Arm A: drug X plus chemotherapy" names no intervention. Binding it would let an
        # arm's prose decide an asset's role.
        roles = _arm_relationships(
            self._protocol(
                [
                    {
                        "type": "PLACEBO_COMPARATOR",
                        "label": "Arm A: teclistamab plus chemotherapy",
                        "interventionNames": [],
                    }
                ]
            )
        )
        assert "teclistamab" not in roles


class TestEveryAdmissionHasANamedReason:
    """§3d. Anonymous admission is a defect, not a default."""

    def test_the_reason_enum_covers_every_route_the_authority_can_return(self) -> None:
        cases = {
            QualificationReason.DIRECT_APPROVED_NAME: AssetEvidence(name="gemcitabine"),
            QualificationReason.STRUCTURED_THERAPEUTIC: AssetEvidence(
                name="Novel Agent",
                structurally_typed_drug=True,
                therapeutic_observations=1,
            ),
            QualificationReason.ENTITY_CORROBORATED_SYNONYM: AssetEvidence(
                name="Keytruda", entity_specific_link=True
            ),
            QualificationReason.CONSTRUCT_CORROBORATED: AssetEvidence(
                name="anti-BCMA construct",
                identity_authority=True,
                entity_specific_link=True,
            ),
            QualificationReason.DEVELOPMENT_CODE_AUTHORITY: AssetEvidence(
                name="ZZQ-99817", entity_specific_link=True
            ),
            QualificationReason.ENTITY_CORROBORATED_PROSE: AssetEvidence(
                name="benzhexol", pharmacologic_documents=2, entity_specific_link=True
            ),
        }
        for expected, evidence in cases.items():
            assert qualification_reason(evidence) is expected, evidence.name
        assert set(cases) == set(QualificationReason)

    @pytest.mark.parametrize(
        "name", ["frontline", "bsAbs", "POD24", "ASCO 2023", "NEJM 2011", "WHO 2022", "IQR 124"]
    )
    def test_a_frozen_negative_has_no_reason_at_all(self, name: str) -> None:
        assert qualification_reason(AssetEvidence(name=name)) is None

    def test_a_gloss_only_name_has_no_reason_even_through_a_strong_route(self) -> None:
        assert (
            qualification_reason(
                AssetEvidence(
                    name="POD24",
                    structurally_typed_drug=True,
                    therapeutic_observations=1,
                    only_abbreviation_gloss=True,
                )
            )
            is None
        )
