"""A conference abstract body may be read for identity, and not for proof of human efficacy.

Until AACR, no conference route carried abstract *text* -- Crossref returned titles and DOIs,
so a conference document had nothing in it that a human-PoC reader could ever match. That made
"conference sources cannot establish human_poc" true without anything enforcing it. AACR ends
that: its Crossref records carry full abstract bodies, and efficacy prose is exactly what an
oncology abstract is made of.

So the property has to become a rule before the text arrives, or it stops holding silently.
Whether a genuine conference abstract *should* be able to establish human PoC is a real
scientific question and a live one -- early oncology efficacy often appears here first -- but
it is a question about the evidence standard, to be answered with the corpus in hand. This
milestone keeps the answer it already had, and makes it explicit rather than incidental.
"""

from __future__ import annotations

from bve.se.evidence.source_capability import may_establish_human_poc


class TestConferenceAbstractBodiesAreNonDecisionalForHumanPoc:
    def test_a_conference_abstract_carrying_a_body_may_not_establish_human_poc(self) -> None:
        assert may_establish_human_poc("conference_abstract") is False

    def test_the_title_only_conference_record_may_not_either(self) -> None:
        # It never could in practice -- a title has no result in it. Stating it keeps the
        # two conference types answering the same question the same way.
        assert may_establish_human_poc("conference_abstract_metadata") is False

    def test_a_peer_reviewed_publication_still_may(self) -> None:
        assert may_establish_human_poc("publication_abstract") is True

    def test_a_company_press_release_still_may(self) -> None:
        assert may_establish_human_poc("company_press_release") is True

    def test_an_unknown_document_type_is_permitted(self) -> None:
        # The policy names what it excludes. A source this list has never heard of is not
        # thereby disqualified, because the exclusion is a claim about conference abstracts
        # specifically and says nothing about anything else.
        assert may_establish_human_poc("some_future_source") is True


class TestTheExclusionIsScopedToHumanPoc:
    """Everything else the abstract body can support, it still supports.

    The restriction is on one decisional fact, not on the document. Identity, target and
    development stage read the same text under the same rules they always did -- which is the
    entire reason for acquiring the body.
    """

    def test_identity_and_target_reading_is_not_restricted(self) -> None:
        from bve.se.evidence import source_capability

        assert source_capability.NON_DECISIONAL_FOR_HUMAN_POC == frozenset(
            {"conference_abstract_metadata", "conference_abstract"}
        )


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
