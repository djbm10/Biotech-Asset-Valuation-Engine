"""Conference abstracts against the human proof-of-concept standard.

Preregistered in ``docs/se_policies/conference_human_poc_admissibility_v1.md``, which is
committed and hashed ahead of these tests and ahead of the delta.

What is being asserted here is narrower than it may look. The standard is not new and is not
conference-specific: ``efficacy_statements`` has always required a human population, an
observed value, an attributable asset name and a disease-relevant endpoint, on every source.
These tests exercise that standard against *conference-shaped* prose, because that is the
input it has never had, and pin the one change the milestone makes -- that such a document is
allowed to be read at all.

So a failure here would not mean "conference abstracts need a different rule". It would mean
the standard is weaker than believed on every source that feeds it, which is a larger finding
and the reason this was worth testing rather than assuming.
"""

from __future__ import annotations

from bve.se.evidence.human_poc import efficacy_statements
from bve.se.evidence.source_capability import may_establish_human_poc

#: The asset names an abstract of this kind would have contributed to the registry.
NAMES = ["CTL019", "axicabtagene ciloleucel", "CART19/20"]


def _passes(text: str, names=None) -> list:
    return efficacy_statements(text, asset_names=names or NAMES, document_id="doc:1")


class TestTheObservedOutcomeRequirement:
    """Condition 3, and the distinction the whole milestone turns on.

    An endpoint is a ruler; a result is a reading. Conference abstracts contain both, often
    in adjacent sentences, and the difference is not a matter of degree.
    """

    def test_an_observed_complete_response_passes(self) -> None:
        text = (
            "Of 26 evaluable patients treated with CTL019, 18 of 26 achieved a "
            "complete response."
        )
        statements = _passes(text)
        assert len(statements) == 1
        assert statements[0].asset_name == "CTL019"
        assert "complete response" in statements[0].endpoint

    def test_a_planned_endpoint_alone_does_not_pass(self) -> None:
        # CT023's shape, and the mandatory negative control of this milestone.
        text = (
            "The primary endpoint was safety and the secondary endpoints were ORR, "
            "progression free survival (PFS), and overall survival (OS) in 11 patients "
            "treated with CART19/20."
        )
        assert _passes(text) == []

    def test_a_future_evaluation_does_not_pass(self) -> None:
        text = (
            "Efficacy of CTL019 will be evaluated in 40 patients using overall "
            "response rate."
        )
        assert _passes(text) == []

    def test_an_efficacy_claim_without_a_reported_value_does_not_pass(self) -> None:
        # No quantity is no reading, however confident the sentence sounds.
        text = "Patients treated with CTL019 achieved durable complete remission."
        assert _passes(text) == []


class TestWhatTheOutcomeHasToBe:
    """Condition 4, and the exclusions that keep 'a number near a good word' from passing."""

    def test_a_safety_only_human_study_does_not_pass(self) -> None:
        text = (
            "Among 26 patients treated with CTL019, 12 of 26 experienced grade 3 "
            "cytokine release syndrome and the regimen was well tolerated."
        )
        assert _passes(text) == []

    def test_a_correlative_biomarker_result_does_not_pass(self) -> None:
        text = (
            "In 26 patients treated with CTL019, peak biomarker expansion correlated "
            "with response in 18 of 26 cases."
        )
        assert _passes(text) == []

    def test_a_sponsor_adjective_is_not_a_result(self) -> None:
        text = (
            "CTL019 showed promising clinical benefit in 26 of 30 patients in this "
            "first-in-human experience."
        )
        assert _passes(text) == []


class TestTheResultHasToBeHumanAndAttributable:
    """Conditions 1, 2 and 6."""

    def test_animal_efficacy_does_not_pass(self) -> None:
        text = (
            "CTL019 produced complete tumor regression in 8 of 10 xenograft-bearing "
            "mice, with responses in 80% of animals."
        )
        assert _passes(text) == []

    def test_a_result_for_an_unnamed_asset_does_not_pass(self) -> None:
        # The asset has to be in the sentence carrying the result, not merely in the
        # document. Stitching the two is the inference this layer refuses.
        text = (
            "CTL019 was manufactured to specification. Separately, 18 of 26 patients "
            "achieved a complete response."
        )
        assert _passes(text) == []

    def test_combination_efficacy_does_not_transfer_to_a_component(self) -> None:
        text = (
            "CTL019 plus ibrutinib produced a complete response in 18 of 26 patients."
        )
        assert _passes(text) == []

    def test_a_second_named_asset_in_the_sentence_blocks_attribution(self) -> None:
        text = (
            "Patients receiving CTL019 and axicabtagene ciloleucel achieved a complete "
            "response in 18 of 26 cases."
        )
        assert _passes(text) == []


class TestTheStandardIsUnchangedForSourcesThatAlreadyHadIt:
    """The milestone must not alter what PubMed or a press release can establish.

    ``efficacy_statements`` never knew which source it was reading, which is why this is
    assertable at all: the same text yields the same statement regardless of provenance, and
    admissibility is decided one layer up.
    """

    def test_the_same_sentence_reads_identically_whatever_document_it_came_from(self) -> None:
        text = "Of 26 evaluable patients treated with CTL019, 18 of 26 achieved a complete response."
        from_abstract = efficacy_statements(text, asset_names=NAMES, document_id="conf:1")
        from_paper = efficacy_statements(text, asset_names=NAMES, document_id="pubmed:1")
        assert [s.sentence for s in from_abstract] == [s.sentence for s in from_paper]

    def test_publication_abstracts_and_press_releases_remain_admissible(self) -> None:
        assert may_establish_human_poc("publication_abstract")
        assert may_establish_human_poc("company_press_release")


class TestTheSourceExclusionIsLifted:
    """The one change this milestone makes.

    Held as a separate class because it is the only line of production code that moves; the
    rest of this module asserts a standard that predates the milestone.
    """

    def test_conference_abstracts_may_now_be_read_for_human_poc(self) -> None:
        assert may_establish_human_poc("conference_abstract")

    def test_title_only_conference_records_are_also_admissible_and_harmless(self) -> None:
        # Admissible by the same rule, and incapable of passing it: a title carries no
        # population and no value. The permission costs nothing and avoids a second
        # exception that would have to be maintained.
        assert may_establish_human_poc("conference_abstract_metadata")
        assert _passes("Abstract CT204: CTL019 in relapsed B-cell malignancies") == []

    def test_a_conference_mention_alone_still_does_not_make_a_name_an_asset(self) -> None:
        # "Conference source alone is not sufficient" holds through the identity layer, not
        # through this policy: a human-PoC fact is only produced for an asset that has
        # independently passed qualification. Asserted at the call site, which is where the
        # two are joined.
        import inspect

        from bve.se import pipeline

        stage = inspect.getsource(pipeline).split('telemetry.stage("HUMAN_POC")', 1)[1]
        assert "if not qualified:" in stage
        assert "continue" in stage


class TestTheEvidencePolicyGatesOneFactAndNotIdentity:
    """The coupling the determinism investigation found.

    The exclusion predicate used to sit at the top of the ``HUMAN_POC`` document loop,
    next to the registry-record skip, and the two read as the same kind of rule. They are
    not. Placed there it also withheld the document from ``has_pharmacologic_context``, so
    a policy about human proof-of-concept was deciding which strings count as assets --
    the one thing ``source_capability`` says it does not do.

    It cost four candidates in the measured delta ("bivalent", "tetravalent",
    "dopaminergic", and a run of table junk), which is how it was found: they appeared when
    the exclusion was lifted, and nothing about them concerns human efficacy.

    The exclusion is empty today, so this coupling is currently inert. That is exactly why
    it is pinned: an inert defect is one nobody notices re-introducing, and the next entry
    added to the list would silently move the asset registry again.
    """

    def _human_poc_stage(self) -> str:
        import inspect

        from bve.se import pipeline

        return inspect.getsource(pipeline).split('telemetry.stage("HUMAN_POC")', 1)[1]

    def test_the_identity_scan_is_not_behind_the_capability_check(self) -> None:
        stage = self._human_poc_stage()
        context_at = stage.index("has_pharmacologic_context(")
        policy_at = stage.index("may_establish_human_poc(")
        assert context_at < policy_at, (
            "has_pharmacologic_context must be reached before the evidence policy is "
            "consulted; behind it, a human_poc exclusion silently gates asset identity"
        )

    def test_the_capability_check_guards_the_efficacy_read_and_not_a_skip(self) -> None:
        stage = self._human_poc_stage()
        after = stage[stage.index("may_establish_human_poc(") :]
        head = after[: after.index("\n\n")] if "\n\n" in after else after
        # A bare ``continue`` under the predicate is the shape that caused the defect.
        assert "efficacy_statements(" in head
        assert "continue" not in head.split("efficacy_statements(", 1)[0]
