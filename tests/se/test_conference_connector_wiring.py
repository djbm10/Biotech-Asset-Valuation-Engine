"""The conference connectors exist, are tested, and had no production caller.

``CrossrefConferenceConnector`` and ``CONFERENCE_VENUES`` were built and covered during M12,
but ``default_connectors()`` returned only CT.gov, FDA label, PubMed and SEC EDGAR. Every
reference to the conference machinery outside its own module was a test. A run therefore
reported ``conference_ash`` as having "no configured connector" while a working, exercised
connector for it sat in the same package -- the same shape of defect as ``bve.se.intent``,
which was importable and unimported since M9.

These tests pin the wiring itself, so a connector cannot be built, tested and then left
unreachable again. They assert what the production path *constructs*; the connectors'
behaviour is already covered by ``tests/se/test_acquisition.py`` and is not restated here.
"""

from __future__ import annotations

from bve.se.acquisition.connectors import CONFERENCE_VENUES, CrossrefConferenceConnector
from bve.se.acquisition.runner import default_connectors


def _families() -> list[str]:
    return [connector.source_family for connector in default_connectors()]


def _connector(family: str):
    return next(
        candidate
        for candidate in default_connectors()
        if candidate.source_family == family
    )


class TestAshIsReachableFromProduction:
    def test_the_default_connector_set_includes_ash(self) -> None:
        assert "conference_ash" in _families()

    def test_ash_is_the_already_built_conference_connector(self) -> None:
        # Not a second implementation: the venue definition and the Crossref mechanism are
        # the ones M12 built and tested.
        connector = _connector("conference_ash")
        assert isinstance(connector, CrossrefConferenceConnector)
        assert connector.venue.publisher == "ASH"
        assert connector.venue.container_titles == ("Blood",)

    def test_the_venue_is_taken_from_the_shared_table(self) -> None:
        # Wiring must read CONFERENCE_VENUES rather than restate a venue inline, so adding
        # EHA later is a table entry and not another edit to the runner.
        connector = _connector("conference_ash")
        assert connector.venue in CONFERENCE_VENUES


class TestEhaIsTheFirstVenueAddedByTable:
    """EHA is the extensibility test: a new venue should be a table entry, nothing more.

    ASH was already described in ``CONFERENCE_VENUES``; wiring it only proved the runner
    could read the table. EHA is the first venue the table did not already contain, so it
    is the one that shows whether the generic conference mechanism really absorbs a new
    conference without a bespoke connector or a branch in the runner.
    """

    def test_the_default_connector_set_includes_eha(self) -> None:
        assert "conference_eha" in _families()

    def test_eha_reuses_the_same_crossref_mechanism(self) -> None:
        connector = _connector("conference_eha")
        assert isinstance(connector, CrossrefConferenceConnector)
        assert connector.venue in CONFERENCE_VENUES

    def test_eha_names_the_congress_not_the_crossref_publisher(self) -> None:
        # ``publisher`` is stamped on every document as the source label, and it names the
        # society whose meeting produced the abstract. HemaSphere's Crossref publisher is
        # Wiley, which is who prints it, not whose congress it reports.
        assert _connector("conference_eha").venue.publisher == "EHA"

    def test_eha_abstracts_are_reached_through_hemasphere(self) -> None:
        # Verified against live Crossref metadata: container-title "HemaSphere" carries the
        # EHA congress abstract supplements, numbered P###/PB####. The casing matters --
        # "Hemasphere" is a distinct filter value and returns nothing.
        assert _connector("conference_eha").venue.container_titles == ("HemaSphere",)

    def test_no_venue_is_defined_twice(self) -> None:
        families = [venue.source_family for venue in CONFERENCE_VENUES]
        assert len(families) == len(set(families))


class TestAscoDeclaresNoTitleNumbering:
    """ASCO prints its abstract number somewhere EHA does not: the container's page field.

    EHA opens each title with S###/P####, which is why it declares a pattern and why the
    identifier-as-asset defect was possible there at all. ASCO does not. Verified against
    228 live Journal of Clinical Oncology titles: *none* begins with an abstract-number
    token, while the page field carries ####, e#####, TPS#### and LBA####.

    So ASCO declares no convention, and that is the documented fact rather than an absence
    nobody checked. Inventing a pattern here would be guessing at a numbering the titles do
    not carry, and an anchored pattern that never matches is indistinguishable from one
    that is wrong.
    """

    def test_the_default_connector_set_includes_asco(self) -> None:
        assert "conference_asco" in _families()

    def test_asco_reuses_the_same_crossref_mechanism(self) -> None:
        connector = _connector("conference_asco")
        assert isinstance(connector, CrossrefConferenceConnector)
        assert connector.venue in CONFERENCE_VENUES

    def test_asco_abstracts_are_reached_through_jco(self) -> None:
        connector = _connector("conference_asco")
        assert connector.venue.container_titles == ("Journal of Clinical Oncology",)
        assert connector.venue.publisher == "ASCO"

    def test_asco_declares_no_abstract_id_pattern(self) -> None:
        assert _connector("conference_asco").venue.abstract_id_pattern is None

    def test_an_asco_style_number_in_a_title_is_not_stripped(self) -> None:
        # The consequence of declaring nothing: a title that happens to open with something
        # shaped like an ASCO number keeps it. That is correct here -- ASCO does not print
        # its numbers in titles, so such a token is part of the title, and development codes
        # in this shape are common enough that stripping one would delete a real asset.
        from bve.se.acquisition.connectors import _leading_bibliographic_id

        venue = _connector("conference_asco").venue
        assert _leading_bibliographic_id("TPS2687 A study of X", venue.abstract_id_pattern) == ""


class TestAacrIsWiredAndUnlikeTheRest:
    """The fifth conference family, and the first that is not a pointer.

    ASH, EHA and ASCO deposit titles; the handoff expected AACR to be "the same mechanism".
    It is the same connector, but not the same document: AACR deposits full abstract bodies
    and prints its identifier in the title. Both facts were read off live records.
    """

    def test_the_default_connector_set_includes_aacr(self) -> None:
        assert "conference_aacr" in _families()

    def test_aacr_abstracts_are_reached_through_cancer_research(self) -> None:
        connector = _connector("conference_aacr")
        assert isinstance(connector, CrossrefConferenceConnector)
        assert connector.venue.container_titles == ("Cancer Research",)
        assert connector.venue.publisher == "AACR"

    def test_aacr_declares_its_numbering_where_asco_declares_none(self) -> None:
        venue = _connector("conference_aacr").venue
        assert venue.abstract_id_pattern is not None
        assert venue.abstract_id_label == "Abstract"


class TestTheExistingSetIsUnchanged:
    def test_the_previously_wired_families_all_survive(self) -> None:
        families = _families()
        for family in ("clinicaltrials_gov", "fda_label", "pubmed", "sec_edgar", "conference_ash"):
            assert family in families, f"{family} was dropped from the default set"

    def test_every_family_is_distinct(self) -> None:
        # ``run_acquisition`` refuses a duplicated family outright; catching it here names
        # the cause rather than failing inside a live acquisition.
        families = _families()
        assert len(families) == len(set(families))

    def test_no_venue_is_wired_before_it_is_validated(self) -> None:
        # Being present in ``CONFERENCE_VENUES`` describes what the connector supports; being
        # present in ``ACTIVE_CONFERENCE_FAMILIES`` is a decision to run it. The two must not
        # collapse into each other, or adding a venue entry silently activates it.
        #
        # AACR was the standing example and has now been validated and activated, so the
        # assertion is on the mechanism rather than on any one venue: activation is a
        # separate, explicit list, and a venue reaches a live source only by being named in
        # it. A future venue added to the table is inert until someone writes it down here.
        from bve.se.acquisition.runner import ACTIVE_CONFERENCE_FAMILIES

        supported = {venue.source_family for venue in CONFERENCE_VENUES}
        assert set(ACTIVE_CONFERENCE_FAMILIES) <= supported
        assert set(_families()) & supported == set(ACTIVE_CONFERENCE_FAMILIES)
