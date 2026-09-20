"""The source-capability policy: what a document type may establish, and who decides.

Until AACR, no conference route carried abstract *text* -- Crossref returned titles and DOIs,
so a conference document had nothing in it that a human-PoC reader could ever match. That made
"conference sources cannot establish human_poc" true without anything enforcing it. AACR ends
that: its Crossref records carry full abstract bodies, and efficacy prose is exactly what an
oncology abstract is made of.

So the property had to become a rule before the text arrived, or it would have stopped
holding silently. It was held for exactly one milestone, so that the question could be decided
against a corpus rather than inherited from what an API used to return.

**It has since been decided, and the exclusion is now empty** -- see
``docs/se_policies/conference_human_poc_admissibility_v1.md``. The AACR corpus contains
attributable human outcomes, and the standard in ``human_poc`` already separates those from
planned endpoints, safety reports and animal data without consulting the source type at all.

This module therefore no longer pins *which* types are excluded. It pins the mechanism, which
is the part that has to survive: that the policy exists, that it is permissive by default, and
that the pipeline actually asks it. The list being empty is the current answer; the mechanism
is what stops the next such property from being believed and unenforced.
"""

from __future__ import annotations

from bve.se.evidence.source_capability import may_establish_human_poc


class TestThePolicyIsPermissiveByDefault:
    def test_a_conference_abstract_may_establish_human_poc(self) -> None:
        # Decided by the admissibility milestone, on measured evidence. The abstract still
        # has to *satisfy* the standard, which is a separate matter entirely and is pinned
        # in ``test_conference_human_poc_admissibility``.
        assert may_establish_human_poc("conference_abstract") is True

    def test_a_title_only_conference_record_is_admissible_and_cannot_pass(self) -> None:
        # Permitted by the same rule, and incapable of using the permission: a title has no
        # population and no value in it. Worth keeping permissive rather than carving out a
        # second exception that would then need maintaining.
        assert may_establish_human_poc("conference_abstract_metadata") is True

    def test_a_peer_reviewed_publication_still_may(self) -> None:
        assert may_establish_human_poc("publication_abstract") is True

    def test_a_company_press_release_still_may(self) -> None:
        assert may_establish_human_poc("company_press_release") is True

    def test_an_unknown_document_type_is_permitted(self) -> None:
        # The policy names what it excludes, so a source it has never heard of is admitted.
        # A default of refusal would silently disqualify every future source -- the opposite
        # failure, and a much quieter one.
        assert may_establish_human_poc("some_future_source") is True


class TestNothingIsCurrentlyExcluded:
    """The list is empty, and that is a position rather than an absence.

    Admissibility is decided by what a document *reports*, not by what kind of document it is.
    Keeping the empty set -- rather than deleting the module -- leaves somewhere for the next
    exception to be written down, and keeps the call site that consults it.
    """

    def test_the_exclusion_list_is_empty(self) -> None:
        from bve.se.evidence import source_capability

        assert source_capability.NON_DECISIONAL_FOR_HUMAN_POC == frozenset()

    def test_the_predicate_still_reads_the_list_rather_than_returning_true(self) -> None:
        # Guards the obvious simplification. With the set empty, ``may_establish_human_poc``
        # could be reduced to ``return True`` and every test above would still pass -- and
        # the next exception would then have nowhere to go.
        from bve.se.evidence import source_capability

        patched = frozenset({"a_type_under_review"})
        original = source_capability.NON_DECISIONAL_FOR_HUMAN_POC
        source_capability.NON_DECISIONAL_FOR_HUMAN_POC = patched
        try:
            assert source_capability.may_establish_human_poc("a_type_under_review") is False
        finally:
            source_capability.NON_DECISIONAL_FOR_HUMAN_POC = original


class TestThePipelineActuallyConsultsThePolicy:
    """A predicate nothing calls is a comment.

    The unit tests above fix what the policy *says*. They would all still pass if the
    human-PoC stage never asked it, which is precisely the failure this whole module exists
    to prevent -- an invariant that reads as enforced and is not. So this asserts the call
    site, in the stage that reads document text.
    """

    def test_the_human_poc_stage_asks_before_reading_a_document(self) -> None:
        import inspect

        from bve.se import pipeline

        source = inspect.getsource(pipeline)
        stage = source.split('telemetry.stage("HUMAN_POC")', 1)
        assert len(stage) == 2, "the HUMAN_POC stage moved; this guard must follow it"
        assert "may_establish_human_poc(document.document_type)" in stage[1]
