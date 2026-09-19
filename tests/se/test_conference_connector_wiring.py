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


class TestAshIsReachableFromProduction:
    def test_the_default_connector_set_includes_ash(self) -> None:
        assert "conference_ash" in _families()

    def test_ash_is_the_already_built_conference_connector(self) -> None:
        # Not a second implementation: the venue definition and the Crossref mechanism are
        # the ones M12 built and tested.
        connector = next(
            candidate
            for candidate in default_connectors()
            if candidate.source_family == "conference_ash"
        )
        assert isinstance(connector, CrossrefConferenceConnector)
        assert connector.venue.publisher == "ASH"
        assert connector.venue.container_titles == ("Blood",)

    def test_the_venue_is_taken_from_the_shared_table(self) -> None:
        # Wiring must read CONFERENCE_VENUES rather than restate a venue inline, so adding
        # EHA later is a table entry and not another edit to the runner.
        connector = next(
            candidate
            for candidate in default_connectors()
            if candidate.source_family == "conference_ash"
        )
        assert connector.venue in CONFERENCE_VENUES


class TestTheExistingSetIsUnchanged:
    def test_the_previously_wired_families_all_survive(self) -> None:
        families = _families()
        for family in ("clinicaltrials_gov", "fda_label", "pubmed", "sec_edgar"):
            assert family in families, f"{family} was dropped from the default set"

    def test_every_family_is_distinct(self) -> None:
        # ``run_acquisition`` refuses a duplicated family outright; catching it here names
        # the cause rather than failing inside a live acquisition.
        families = _families()
        assert len(families) == len(set(families))

    def test_no_venue_is_wired_before_it_is_validated(self) -> None:
        # ASH is the family under test. ASCO and AACR are wired in their own milestones,
        # each with its own live validation, so activating one venue must not quietly
        # activate the rest of the table.
        families = _families()
        assert "conference_asco" not in families
        assert "conference_aacr" not in families
