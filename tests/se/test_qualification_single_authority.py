"""Controls for ``docs/se_policies/asset_qualification_single_authority_v2.md``.

Every name here was frozen in the policy before the rule was written, and each one is a name
that *survived* the previous attempt on a live paired run. The negatives are asserted through
the same functions the positives use, so none can be satisfied by naming a string.
"""

from __future__ import annotations

import pytest

from bve.se.discovery import drug_name_shape
from bve.se.discovery.adapters import _comparator_roles, _normalized_lookup
from bve.se.discovery.asset_qualification import (
    AssetEvidence,
    is_development_code,
    qualifies_as_asset,
    qualifies_by_authority,
)
from bve.se.discovery.mention_support import MentionDisposition, classify_mention_support

#: Observed holding canonical status in `mint_off`, and still holding it in `mint_on`.
SURVIVED_THE_LAST_FIX = ["frontline", "bsAbs", "POD24", "ASCO 2023", "NEJM 2011"]

#: Promoted by the spaced development-code widening the v2 policy removes.
PROMOTED_BY_THE_WIDENING = ["ASCO 2023", "NEJM 2011", "IQR 124", "WHO 2022", "PRISMA 2020"]


class TestThereIsOneQualificationAuthority:
    """The defect that made the other three invisible."""

    @pytest.mark.parametrize("name", SURVIVED_THE_LAST_FIX)
    def test_a_name_the_rule_rejects_is_not_protected_by_another_route(self, name) -> None:
        # `is_protected` used to answer first, with its own older definition of "drug".
        assert (
            classify_mention_support(name, support=40)
            is MentionDisposition.LOW_SUPPORT_UNKNOWN
        )

    def test_protection_and_qualification_cannot_disagree(self) -> None:
        from bve.se.discovery.mention_support import is_protected

        for evidence in (
            AssetEvidence(name="frontline", support=40),
            AssetEvidence(name="gemcitabine"),
            AssetEvidence(name="POD24", entity_specific_link=True),
            AssetEvidence(name="Placebo", structurally_typed_drug=True, comparator_role=True),
        ):
            assert is_protected(evidence) is qualifies_as_asset(evidence)


class TestIdentityComesFromAuthorityNotShape:
    @pytest.mark.parametrize("code", ["AMG 420", "ALLO-715"])
    def test_a_sponsor_code_is_recovered_by_separator_insensitive_lookup(self, code) -> None:
        # Measured: `amg 420` is absent from the lexicon and `amg-420` is present;
        # `allo-715` is absent and `allo 715` is present. Same record, two spellings.
        assert drug_name_shape.is_identity_bearing_drug_name(code) is True
        assert qualifies_as_asset(AssetEvidence(name=code)) is True

    @pytest.mark.parametrize("name", PROMOTED_BY_THE_WIDENING)
    def test_a_citation_is_not_recovered_by_that_lookup(self, name) -> None:
        assert drug_name_shape.is_identity_bearing_drug_name(name) is False
        assert qualifies_as_asset(AssetEvidence(name=name)) is False

    @pytest.mark.parametrize("name", PROMOTED_BY_THE_WIDENING)
    def test_the_spaced_code_shape_is_gone(self, name) -> None:
        assert is_development_code(name) is False

    def test_a_code_shape_alone_no_longer_qualifies(self) -> None:
        # POD24 has the shape and no authority record. It now needs an entity, and the
        # declared cost is that a genuinely new code without one goes to review.
        assert is_development_code("POD24") is True
        assert qualifies_as_asset(AssetEvidence(name="POD24")) is False
        assert qualifies_as_asset(AssetEvidence(name="POD24", entity_specific_link=True)) is True


class TestProseNeedsAnEntityNotJustAClass:
    """`bsAbs` is used in argument position across documents because the class really is given."""

    def test_treatment_context_alone_does_not_make_a_class_term_an_asset(self) -> None:
        assert qualifies_as_asset(
            AssetEvidence(name="bsAbs", pharmacologic_documents=9)
        ) is False

    def test_the_same_context_plus_an_entity_qualifies(self) -> None:
        assert qualifies_as_asset(
            AssetEvidence(
                name="benzhexol", pharmacologic_documents=2, entity_specific_link=True
            )
        ) is True

    def test_co_occurrence_is_not_an_entity_link(self) -> None:
        # The live artifact records a modality and discovery target context for `bsAbs`,
        # `frontline`, `cornerstone` and `ASCO 2023`. None of those is an entity, which is
        # why `_has_entity_link` reads trials, owners and attributed targets only.
        from bve.se.pipeline import _has_entity_link
        from bve.se.schemas.contracts import CanonicalAsset

        assert not _has_entity_link(
            CanonicalAsset(
                asset_id="asset:x",
                canonical_name="bsAbs",
                discovery_target_context=["CD19", "TNFRSF17"],
                modality_id="T_CELL_ENGAGER",
            )
        )


class TestTheComparatorRouteActuallyFires:
    """It did not fire once on 2,873 live candidates, because of a type prefix."""

    def test_the_type_prefix_does_not_defeat_the_match(self) -> None:
        roles = _comparator_roles(
            {
                "armsInterventionsModule": {
                    "armGroups": [
                        {"type": "PLACEBO_COMPARATOR", "interventionNames": ["Drug: Placebo"]},
                        {"type": "EXPERIMENTAL", "interventionNames": ["Drug: teclistamab"]},
                    ]
                }
            }
        )
        assert _normalized_lookup("Placebo") in roles
        assert _normalized_lookup("teclistamab") not in roles

    def test_a_comparator_does_not_qualify_through_structured_typing(self) -> None:
        assert qualifies_by_authority(
            AssetEvidence(name="Placebo", structurally_typed_drug=True, comparator_role=True)
        ) is False

    def test_a_comparator_with_many_trials_still_does_not_qualify(self) -> None:
        # `Placebo` carries 35 trials and 30 owners, so the entity route would admit it if
        # the comparator role did not answer first.
        assert qualifies_as_asset(
            AssetEvidence(
                name="Placebo",
                structurally_typed_drug=True,
                comparator_role=True,
                entity_specific_link=True,
                pharmacologic_documents=9,
            )
        ) is False


class TestTheProtectedRealAssetsSurvive:
    @pytest.mark.parametrize(
        "name",
        [
            "gemcitabine",
            "pomalidomide",
            "busulfan",
            "teclistamab",
            "pembrolizumab",
            "CCS1477",
            "ABBV-383",
            "SB-773812",
            "belantamab mafodotin",
            "idecabtagene vicleucel",
        ],
    )
    def test_an_authority_backed_molecule_needs_no_corroboration(self, name) -> None:
        assert qualifies_as_asset(AssetEvidence(name=name)) is True

    def test_a_structured_drug_declaration_still_qualifies(self) -> None:
        assert qualifies_as_asset(
            AssetEvidence(name="ALLO-501A", structurally_typed_drug=True)
        ) is True

    def test_a_described_construct_still_qualifies(self) -> None:
        assert qualifies_as_asset(
            AssetEvidence(name="BCMA/CD19 CAR T cells", identity_authority=True)
        ) is True
