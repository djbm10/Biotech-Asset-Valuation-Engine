"""A class label denotes a set of assets and cannot be a member of it (v5).

The cases here are drawn from the live `mint4_on` population rather than invented, because
the failure this milestone fixes was invisible to 1,361 passing tests: `CART19` had excellent
evidence for being a category and the engine had no way to ask whether a name denoted one
thing or many.
"""

from __future__ import annotations

import pytest

from bve.se.discovery import class_terms
from bve.se.discovery.asset_qualification import (
    AssetEvidence,
    QualificationReason,
    qualification_reason,
    qualifies_as_asset,
)


def _evidence(name: str, **overrides: object) -> AssetEvidence:
    """Evidence strong enough that only the class-term rule can refuse it."""

    fields: dict[str, object] = {
        "name": name,
        "trial_ids": 33,
        "company_ids": 14,
        "structurally_typed_drug": True,
        "therapeutic_observations": 12,
        "entity_specific_link": True,
        "identity_authority": True,
    }
    fields.update(overrides)
    return AssetEvidence(**fields)  # type: ignore[arg-type]


class TestAClassLabelIsNotAnAsset:
    """The rule, stated over names that individuate and names that do not."""

    @pytest.mark.parametrize(
        "name",
        [
            "CART19",
            "CAR19",
            "CAR-T",
            "CAR-T cells",
            "CD19 CAR-T cells",
            "anti-CD19 CAR-T",
            "CD19-CAR-NK/T",
            "Chimeric Antigen Receptor T-Cell Therapy",
            "anti-BCMA CAR-T",
            "BCMA/CD19 Dual-Target CAR-T",
            "CAR T-cell therapy",
        ],
    )
    def test_modality_and_target_alone_denote_a_category(self, name: str) -> None:
        assert class_terms.is_class_term(name) is True
        assert class_terms.individuating_residue(name) == ()

    @pytest.mark.parametrize(
        ("name", "residue"),
        [
            ("TAC01-CD19", ("TAC01",)),
            ("FIT-(BCMA+CD19)-CAR-T Cells", ("FIT",)),
            ("tisagenlecleucel", ("tisagenlecleucel",)),
            ("Descartes-08", ("Descartes", "08")),
        ],
    )
    def test_anything_left_over_individuates(
        self, name: str, residue: tuple[str, ...]
    ) -> None:
        assert class_terms.individuating_residue(name) == residue
        assert class_terms.is_class_term(name) is False

    def test_the_veto_outranks_the_ontologys_own_identity_claim(self) -> None:
        """`CART19` is an identity-bearing name in ChEMBL, which is how it got in.

        The ordering in :func:`qualification_reason` is the substance of the fix, not a
        detail: every route below ``DIRECT_APPROVED_NAME`` would have been unreachable.
        """

        assert qualification_reason(_evidence("CART19")) is None
        assert qualifies_as_asset(_evidence("CART19")) is False

    def test_a_real_asset_with_the_same_evidence_still_qualifies(self) -> None:
        """The control for the test above: the evidence is identical, the name is not."""

        reason = qualification_reason(_evidence("ABBV-383"))
        assert reason is QualificationReason.DIRECT_APPROVED_NAME


class TestASerialIsNotATargetDesignation:
    """What separates `CART19` from `CAR088`, given both are a modality and a number."""

    @pytest.mark.parametrize("name", ["CAR088", "CAR011", "CAR066"])
    def test_zero_padded_numerics_are_sponsor_serials(self, name: str) -> None:
        assert class_terms.is_class_term(name) is False
        assert class_terms.individuating_residue(name) == (name,)

    def test_a_bare_number_counts_only_when_cd_n_resolves(self) -> None:
        """`CD19` resolves in the ontology; `CD991` does not, so `CAR991` individuates."""

        assert class_terms.is_class_term("CART19") is True
        assert class_terms.is_class_term("CAR991") is False

    def test_the_ontology_is_the_authority_not_a_list_of_cd_numbers(self) -> None:
        """Written as a fact about the mechanism, so replacing it with a list fails here.

        `CD20` is *ambiguous* in the published snapshot and therefore does not resolve, so
        `CAR-20` is kept as an asset. That is the conservative direction and it is an
        ontology fact, not a rule: a hand-maintained CD list would have demoted it, and
        would then have been wrong in whichever direction the next snapshot moved.
        """

        from bve.se.ontology.targets import normalize_target

        assert normalize_target("CD19") is not None
        assert class_terms.is_class_term("CART19") is True
        if normalize_target("CD20") is None:
            assert class_terms.is_class_term("CAR-20") is False
        else:
            assert class_terms.is_class_term("CAR-20") is True


class TestTheRuleDoesNotBecomeAJunkFilter:
    """Class-term demotion answers *one thing or many*, not *drug or not a drug*."""

    def test_a_bare_target_symbol_is_not_a_class_of_therapies(self) -> None:
        """`CD19` names an antigen. It is not a category of drugs, and v5 is silent on it.

        Without the "at least one modality token" condition, every gene symbol in the corpus
        would be demoted by this rule instead of by the rule that actually governs it.
        """

        assert class_terms.is_class_term("CD19") is False

    def test_an_ordinary_word_is_not_a_class_term(self) -> None:
        """`choice` is refused, but by qualification evidence -- not by this rule."""

        assert class_terms.is_class_term("choice") is False

    @pytest.mark.parametrize("name", ["Placebo", "Matched Placebo"])
    def test_comparator_material_is_not_a_class_term(self, name: str) -> None:
        """v4's comparator veto keeps its own job. Two rules, two reasons, no overlap."""

        assert class_terms.is_class_term(name) is False


class TestTheDemotionIsAuditable:
    """v5 §5.7. A demotion must explain itself as precisely as an admission does."""

    def test_a_class_term_is_not_described_as_short_of_evidence(self) -> None:
        """The support-count sentence is true and irrelevant, which makes it misleading.

        `CD19 CAR-T cells` carries 24 trials. Telling a reviewer it lacks documents sends
        them looking for more of the one thing that cannot promote it.
        """

        from bve.se.pipeline import _low_support_review_reason
        from bve.se.schemas.contracts import CanonicalAsset

        asset = CanonicalAsset(
            asset_id="asset:0001",
            canonical_name="CD19 CAR-T cells",
            identity_keys=["cd19 car-t cells"],
        )
        reason = _low_support_review_reason(asset, {})

        assert "denotes a class of therapies" in reason
        assert "supporting document" not in reason
        assert "retained for grouping" in reason

    def test_a_genuinely_unsupported_name_still_reports_its_support(self) -> None:
        from bve.se.pipeline import _low_support_review_reason
        from bve.se.schemas.contracts import CanonicalAsset

        asset = CanonicalAsset(
            asset_id="asset:0002",
            canonical_name="zzyzxumab",
            identity_keys=["zzyzxumab"],
        )
        reason = _low_support_review_reason(asset, {"zzyzxumab": ("doc",)})

        assert "1 supporting document(s)" in reason
        assert "class of therapies" not in reason
