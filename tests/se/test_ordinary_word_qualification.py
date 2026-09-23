"""Controls for ``docs/se_policies/asset_nomination_evidence_v1.md``.

Every name here was frozen in the policy before the rule was written, and the policy's own
audit is what makes the hard cases hard: ``lestaurinib`` scores *below* ``bsAbs`` on drug
shape, ``gemcitabine`` occurs in *fewer* corpus documents than ``cornerstone``, and
``frontline`` is a genuine ChEMBL record. Nothing in this file may be satisfied by naming a
string, which is why the negatives are asserted through the same functions the positives use.
"""

from __future__ import annotations

import pytest

from bve.se.discovery import drug_name_shape
from bve.se.discovery.asset_qualification import (
    AssetEvidence,
    has_pharmacologic_context,
    is_abbreviation_gloss,
    is_development_code,
    qualifies_as_asset,
)


def _prose(name: str, documents: int = 2, **overrides) -> AssetEvidence:
    """A name whose only evidence is prose use in ``documents`` distinct documents."""

    # v2 adds the entity requirement: prose establishes a therapeutic *term*, and an
    # entity-specific link is what makes it an asset rather than a class. These helpers
    # supply one so the tests below keep testing what they were written to test.
    overrides.setdefault("entity_specific_link", True)
    return AssetEvidence(name=name, pharmacologic_documents=documents, **overrides)


class TestTheOntologyQualifierIsIdentityBearingNotAnyRecord:
    """Amendment 8a. ``FRONTLINE`` is a real record, so "has a record" cannot be the test."""

    @pytest.mark.parametrize("name", ["frontline", "choice", "discase"])
    def test_a_trade_name_only_record_does_not_qualify(self, name: str) -> None:
        # Each is an ordinary English word carried solely as a TRADE_NAME alias of some
        # other molecule -- frontline is FIPRONIL, a veterinary insecticide.
        assert drug_name_shape.is_known_drug_name(name) is True
        assert drug_name_shape.is_identity_bearing_drug_name(name) is False
        assert qualifies_as_asset(AssetEvidence(name=name)) is False

    @pytest.mark.parametrize(
        "name", ["gemcitabine", "pomalidomide", "busulfan", "teclistamab", "pembrolizumab"]
    )
    def test_an_identity_bearing_record_still_qualifies(self, name: str) -> None:
        assert drug_name_shape.is_identity_bearing_drug_name(name) is True
        assert qualifies_as_asset(AssetEvidence(name=name)) is True

    @pytest.mark.parametrize("brand", ["keytruda", "revlimid", "carvykti", "abecma"])
    def test_a_real_brand_is_not_qualified_by_the_ontology_either(self, brand: str) -> None:
        # Not a loss: a trade name is an alias of its parent, and the parent qualifies on
        # its own use context. Keytruda's occurrences are administration frames; FRONTLINE's
        # are attributive. Treating the two alike is the whole point of amendment 8a.
        assert drug_name_shape.is_identity_bearing_drug_name(brand) is False

    def test_the_parent_of_a_junk_trade_name_is_not_laundered_into_an_asset(self) -> None:
        # Resolving frontline -> FIPRONIL must not mint FIPRONIL from attributive prose.
        # Fipronil is a real molecule, so it is identity-bearing; what it must not get is
        # qualification from "frontline setting", which is not a mention of it at all.
        assert has_pharmacologic_context("in the frontline setting for myeloma", "fipronil") is False


class TestProseQualifiesOnlyInArgumentPosition:
    """Amendment 8b. The name must fill a slot only a noun can fill."""

    @pytest.mark.parametrize(
        ("name", "text"),
        [
            ("safer", "a safer therapy for these patients"),
            ("cornerstone", "remains the cornerstone treatment of myeloma"),
            ("refine", "to refine treatment for this population"),
            ("frontline", "patients receiving frontline chemotherapy"),
            ("frontline", "treated with frontline therapy and observed"),
            ("though", "though treatment was continued"),
        ],
    )
    def test_a_modifier_of_a_head_noun_qualifies_nothing(self, name: str, text: str) -> None:
        assert has_pharmacologic_context(text, name) is False

    @pytest.mark.parametrize(
        ("name", "text"),
        [
            ("pomalidomide", "patients treated with pomalidomide and dexamethasone"),
            ("gemcitabine", "gemcitabine 1000 mg was given on day 1"),
            ("benzhexol", "patients received benzhexol for tremor"),
            ("lestaurinib", "lestaurinib is a selective inhibitor of FLT3"),
            ("ibritumomab", "following administration of ibritumomab"),
        ],
    )
    def test_the_argument_of_an_administration_frame_qualifies(self, name: str, text: str) -> None:
        assert has_pharmacologic_context(text, name) is True

    def test_the_modifier_veto_applies_to_real_drugs_too(self) -> None:
        # Per-occurrence and intentionally blind to whether the name is real: the molecule
        # qualifies through its other occurrences, not through this one.
        assert has_pharmacologic_context("Pomalidomide capsules, 4 mg", "pomalidomide") is False
        assert has_pharmacologic_context("treatment with pomalidomide", "pomalidomide") is True


class TestProseNeedsCorroboration:
    """The rule the policy predicted ``bsAbs`` would fail on."""

    def test_one_document_is_not_enough(self) -> None:
        assert qualifies_as_asset(_prose("bsAbs", documents=1)) is False

    def test_two_independent_documents_are(self) -> None:
        assert qualifies_as_asset(_prose("benzhexol", documents=2)) is True

    def test_frequency_is_never_the_test(self) -> None:
        # gemcitabine occurs in fewer corpus documents than cornerstone, so no count can
        # separate them. Support appears in the model and must not reach the decision.
        assert qualifies_as_asset(AssetEvidence(name="cornerstone", support=9999)) is False


class TestAbbreviationGlossesAreNotAssets:
    """A parenthetical spelling out the phrase before it is a gloss, not a molecule."""

    @pytest.mark.parametrize(
        ("phrase", "name"),
        [
            ("progression of disease within 24 months (POD24)", "POD24"),
            ("bispecific antibodies (bsAbs)", "bsAbs"),
            ("minimal residual disease (MRD)", "MRD"),
        ],
    )
    def test_an_initialism_of_the_preceding_phrase_is_a_gloss(self, phrase, name) -> None:
        assert is_abbreviation_gloss(phrase, name) is True

    @pytest.mark.parametrize(
        ("phrase", "name"),
        [
            # A development code in apposition to its own molecule is a synonym, not an
            # abbreviation: its letters do not spell the preceding words.
            ("Inobrodib (CCS1477, p300/CBP inhibitor)", "CCS1477"),
            ("etentamig (ABBV-383) in adult participants", "ABBV-383"),
        ],
    )
    def test_a_development_code_beside_its_molecule_is_not_a_gloss(self, phrase, name) -> None:
        assert is_abbreviation_gloss(phrase, name) is False

    def test_a_gloss_only_name_does_not_qualify_through_the_code_route(self) -> None:
        # POD24 has the shape of a development code and must not be protected by it.
        assert is_development_code("POD24") is True
        assert qualifies_as_asset(AssetEvidence(name="POD24", only_abbreviation_gloss=True)) is False

    @pytest.mark.parametrize("statistic", ["IQR 72", "OS 24", "CI 95", "HR 58"])
    def test_a_statistic_beside_its_value_is_still_not_a_code(self, statistic: str) -> None:
        # Admitting a space as a separator for AMG 420 must not readmit the quartile range
        # the narrow form was written to exclude. A serial is not quoted to two digits.
        assert is_development_code(statistic) is False

    @pytest.mark.parametrize("code", ["ABBV-383", "AMG 420", "ALLO-715", "CCS1477", "SB-773812"])
    def test_real_development_codes_still_qualify_with_no_use_evidence(self, code: str) -> None:
        # Measured: AMG 420 and CCS1477 have zero pharmacologic context in the live corpus.
        # Requiring use evidence of a code would delete them, so the code route stays
        # unconditional and is vetoed only by the gloss rule.
        assert qualifies_as_asset(AssetEvidence(name=code)) is True


class TestTheComparatorArmIsNotATherapeuticAsset:
    """A registry really does declare placebo as an intervention. That is not an asset."""

    def test_a_structured_declaration_in_comparator_role_does_not_qualify(self) -> None:
        evidence = AssetEvidence(
            name="Placebo", structurally_typed_drug=True, comparator_role=True
        )
        assert qualifies_as_asset(evidence) is False

    def test_a_structured_declaration_otherwise_still_qualifies(self) -> None:
        assert qualifies_as_asset(
            AssetEvidence(name="belantamab mafodotin", structurally_typed_drug=True)
        ) is True


class TestOntologyMissingRealAssetsSurvive:
    """The controls the whole rule exists to protect. None is in the ontology at all."""

    @pytest.mark.parametrize("name", ["benzhexol", "ibritumomab", "lestaurinib"])
    def test_an_ontology_missing_drug_qualifies_on_use_alone(self, name: str) -> None:
        assert drug_name_shape.is_identity_bearing_drug_name(name) is False
        assert qualifies_as_asset(_prose(name, documents=2)) is True


class TestTheComparatorRoleIsReadFromTheSourcesOwnArms:
    """Where ``comparator_role`` comes from: declared arm typing, never a name list."""

    @staticmethod
    def _protocol(arms: list[dict]) -> dict:
        return {"armsInterventionsModule": {"armGroups": arms}}

    def test_an_intervention_only_in_a_placebo_arm_is_a_comparator(self) -> None:
        from bve.se.discovery.adapters import _comparator_roles, _normalized_lookup

        roles = _comparator_roles(
            self._protocol(
                [
                    {"type": "EXPERIMENTAL", "interventionNames": ["Drug: teclistamab"]},
                    {"type": "PLACEBO_COMPARATOR", "interventionNames": ["Drug: Placebo"]},
                ]
            )
        )
        assert _normalized_lookup("Placebo") in roles
        assert _normalized_lookup("teclistamab") not in roles

    def test_an_active_control_is_not_role_typed_as_a_comparator(self) -> None:
        # A marketed drug used as the control arm is still that drug. Only placebo and
        # sham arms are control *material*; ACTIVE_COMPARATOR is a therapy being compared.
        from bve.se.discovery.adapters import _comparator_roles

        assert _comparator_roles(
            self._protocol(
                [{"type": "ACTIVE_COMPARATOR", "interventionNames": ["Drug: pembrolizumab"]}]
            )
        ) == set()

    def test_a_molecule_co_administered_in_the_control_arm_keeps_its_role(self) -> None:
        from bve.se.discovery.adapters import _comparator_roles, _normalized_lookup

        roles = _comparator_roles(
            self._protocol(
                [
                    {
                        "type": "PLACEBO_COMPARATOR",
                        "interventionNames": ["Drug: Placebo", "Drug: pomalidomide"],
                    },
                    {"type": "EXPERIMENTAL", "interventionNames": ["Drug: pomalidomide"]},
                ]
            )
        )
        assert roles == {_normalized_lookup("Placebo")}
