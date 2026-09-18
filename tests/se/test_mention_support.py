"""The nomination boundary sorts candidates by evidential support, and never deletes.

M17 nominated 8,080 candidates, of which 4,480 were ordinary prose the shape model
mistook for molecules. The cost lands entirely on the default path: 7,966 unresolved
assets that an analyst would have to wade through.

The temptation is to drop low-support names. These tests exist to make that impossible.
The benchmark gold sets are cut from ontology DIRECT_TARGET edges, so every gold asset is
ontology-known by construction, and no benchmark can measure the false rejection of a
genuinely novel single-mention asset. A hard support threshold would score perfectly
against that blind spot while silently deleting exactly the assets a discovery engine
exists to find.

So support decides *routing*, not survival: everything is retained with its provenance,
and low-support unknowns are held in a review disposition instead of the default path.
"""

from __future__ import annotations

import pytest

from bve.se.discovery.mention_support import (
    MentionDisposition,
    classify_mention_support,
)


class TestProtectedNamesIgnoreSupportEntirely:
    """Exact ontology evidence and code shape outrank any amount of corpus counting."""

    def test_a_known_drug_seen_once_is_protected(self) -> None:
        # ATROPINE with a single mention is still ATROPINE. In M17 the known_molecule
        # class had a median of exactly one supporting document, so this is the common
        # case and not a corner.
        assert (
            classify_mention_support("atropine", support=1, drug_shaped=False)
            is MentionDisposition.PROTECTED
        )

    def test_a_development_code_seen_once_is_protected(self) -> None:
        assert (
            classify_mention_support("SB-773812", support=1, drug_shaped=False)
            is MentionDisposition.PROTECTED
        )

    def test_a_bare_code_without_punctuation_is_protected(self) -> None:
        assert (
            classify_mention_support("MK7622", support=1, drug_shaped=False)
            is MentionDisposition.PROTECTED
        )

    def test_protection_does_not_depend_on_drug_shape(self) -> None:
        # The exact route is stronger evidence than the learned one; a known name that
        # scores badly on shape (iferanserin, sarpogrelate) must not be demoted.
        assert (
            classify_mention_support("iferanserin", support=1, drug_shaped=False)
            is MentionDisposition.PROTECTED
        )


class TestSupportedUnknownsTakeTheNormalPath:
    def test_five_documents_is_enough_without_drug_shape(self) -> None:
        assert (
            classify_mention_support("benzhexol", support=5, drug_shaped=False)
            is MentionDisposition.SUPPORTED_UNKNOWN
        )

    def test_two_documents_is_enough_when_drug_shaped(self) -> None:
        assert (
            classify_mention_support("butylphthalide", support=2, drug_shaped=True)
            is MentionDisposition.SUPPORTED_UNKNOWN
        )

    def test_one_document_is_not_enough_even_when_drug_shaped(self) -> None:
        assert (
            classify_mention_support("butylphthalide", support=1, drug_shaped=True)
            is MentionDisposition.LOW_SUPPORT_UNKNOWN
        )


class TestLowSupportIsReviewNotDeletion:
    """The whole point of the disposition: suppressed from default, never discarded."""

    def test_prose_with_one_mention_is_low_support(self) -> None:
        assert (
            classify_mention_support("timeliness", support=1, drug_shaped=False)
            is MentionDisposition.LOW_SUPPORT_UNKNOWN
        )

    def test_non_english_prose_is_low_support(self) -> None:
        # The single largest surprise in the M17 audit: PubMed carries non-English
        # abstracts and the shape model has no opinion about Hungarian.
        for token in ("besserten", "analizaron", "szorong"):
            assert (
                classify_mention_support(token, support=1, drug_shaped=False)
                is MentionDisposition.LOW_SUPPORT_UNKNOWN
            )

    def test_low_support_is_a_disposition_and_not_a_falsey_absence(self) -> None:
        # Guards against a future refactor expressing "suppressed" as None/empty, which
        # is how provenance gets quietly dropped.
        disposition = classify_mention_support("wormhole", support=1, drug_shaped=False)
        assert disposition is MentionDisposition.LOW_SUPPORT_UNKNOWN
        assert bool(disposition.value)

    def test_every_disposition_is_retained_none_means_delete(self) -> None:
        assert set(MentionDisposition) == {
            MentionDisposition.PROTECTED,
            MentionDisposition.SUPPORTED_UNKNOWN,
            MentionDisposition.LOW_SUPPORT_UNKNOWN,
        }


class TestThresholdsAreDeclaredNotTuned:
    def test_thresholds_match_the_declared_design(self) -> None:
        from bve.se.discovery import mention_support

        assert mention_support.MIN_SUPPORT_UNKNOWN == 5
        assert mention_support.MIN_SUPPORT_DRUG_SHAPED == 2

    @pytest.mark.parametrize(
        "name",
        # One gold asset from each benchmark target drawn so far. None of these may be
        # referenced by the rule: the filter must be target-agnostic.
        ["pembrolizumab", "reboxetine", "ketotifen", "eplivanserin", "xanomeline"],
    )
    def test_no_benchmark_asset_is_named_in_the_rule(self, name: str) -> None:
        import inspect

        from bve.se.discovery import mention_support

        assert name not in inspect.getsource(mention_support).casefold()
