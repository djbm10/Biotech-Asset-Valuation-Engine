"""A source-native bibliographic identifier is metadata, not an asset mention.

EHA prints its congress abstract number as a leading title token --
``PB1983: TRIAL-IN-PROGRESS: PHASE II STUDY OF PHE885, ...`` -- and letters-then-digits is
exactly the shape the drug-code model learned. The identity layer therefore nominated 16 EHA
abstract numbers as assets, and in ``PB1983``'s case took the abstract number *instead of* the
real BCMA CAR-T the title names.

The fix is a boundary, not a filter. ``PB1983`` is not rejected because of how it looks; it is
rejected because the source structurally declared it to be the document's own identifier. The
same string appearing anywhere else -- in prose, in another corpus, as a genuine development
code -- is still a perfectly good asset candidate. Nothing about the shape model changes, and
nothing about the raw bytes changes: the title is preserved exactly, and the identifier is
recorded alongside it rather than cut out of it.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from bve.se.acquisition.connectors import (
    CONFERENCE_VENUES,
    ConferenceVenue,
    CrossrefConferenceConnector,
    TargetQuery,
)
from bve.se.acquisition.corpus_store import CorpusStore
from bve.se.discovery.adapters import IndexedDocumentAdapter
from bve.se.schemas.contracts import CompiledQuery

AS_OF = date(2026, 9, 17)
TARGETS = (TargetQuery(canonical_id="TNFRSF17", aliases=("BCMA",)),)

#: The real EHA record that exposed the defect: the abstract number leads, and the asset the
#: title is actually about appears several words in.
PB1983 = (
    "PB1983: TRIAL-IN-PROGRESS: PHASE II STUDY OF PHE885, A B-CELL MATURATION "
    "ANTIGEN-DIRECTED CHIMERIC ANTIGEN RECEPTOR T-CELL THERAPY"
)


def _nominated(record: dict, *, source: str = "conference_eha") -> set[str]:
    """The asset names this one record nominates, with no target/modality narrowing."""

    query = CompiledQuery(query_id="query:test", query="BCMA", target_ids=[], modality_ids=[])
    result = IndexedDocumentAdapter(source, [record]).search(query, as_of_date=AS_OF)
    return {hit.asset_name for hit in result.hits}


def _venue(family: str) -> ConferenceVenue:
    return next(v for v in CONFERENCE_VENUES if v.source_family == family)


def _item(doi: str, title: str) -> dict:
    return {
        "DOI": doi,
        "title": [title],
        "container-title": ["HemaSphere"],
        "published": {"date-parts": [[2026, 6, 1]]},
        "type": "journal-article",
    }


def _acquire(tmp_path, venue: ConferenceVenue, titles: list[str]) -> CorpusStore:
    items = [_item(f"10.1/{i}", t) for i, t in enumerate(titles)]

    def fake_search(container_title: str, query: str, as_of_date: date):
        return items

    store = CorpusStore(tmp_path / venue.source_family)
    CrossrefConferenceConnector(venue, fake_search).acquire(
        store, targets=TARGETS, modality_terms=(), as_of_date=AS_OF
    )
    return store


class TestTheIdentifierIsRecordedNotRemoved:
    def test_the_anchored_abstract_number_is_captured_as_metadata(self, tmp_path) -> None:
        document = _acquire(tmp_path, _venue("conference_eha"), [PB1983]).documents()[0]
        assert document.bibliographic_id == "PB1983"

    def test_the_raw_title_is_preserved_byte_for_byte(self, tmp_path) -> None:
        # The identifier is recorded *alongside* the title, never cut out of it. Custody must
        # keep what the source said, and a reader must still see the abstract number.
        document = _acquire(tmp_path, _venue("conference_eha"), [PB1983]).documents()[0]
        assert document.title == PB1983
        assert document.text == PB1983

    def test_the_sealed_payload_is_untouched(self, tmp_path) -> None:
        store = _acquire(tmp_path, _venue("conference_eha"), [PB1983])
        document = store.documents()[0]
        snapshot = json.loads(Path(document.snapshot_path).read_text())
        assert snapshot["title"] == [PB1983]

    def test_native_provenance_is_unchanged(self, tmp_path) -> None:
        document = _acquire(tmp_path, _venue("conference_eha"), [PB1983]).documents()[0]
        assert document.source_url == "https://doi.org/10.1/0"

    def test_the_identifier_reaches_discovery_on_the_indexed_record(self, tmp_path) -> None:
        document = _acquire(tmp_path, _venue("conference_eha"), [PB1983]).documents()[0]
        assert document.indexable_record()["bibliographic_id"] == "PB1983"


class TestNominationSkipsTheIdentifierAndKeepsTheAsset:
    """The defect and its opposite, on one document."""

    def _names(self, record: dict) -> set[str]:
        return _nominated(record)

    def test_the_abstract_number_cannot_become_an_asset(self, tmp_path) -> None:
        document = _acquire(tmp_path, _venue("conference_eha"), [PB1983]).documents()[0]
        assert "PB1983" not in self._names(document.indexable_record())

    def test_vetoing_the_identifier_does_not_veto_the_document(self, tmp_path) -> None:
        # The whole point: the veto removes one token, not the record. A real development code
        # in the same title is still nominated.
        title = "PB1983: TRIAL-IN-PROGRESS: PHASE II STUDY OF CC-95266 IN MYELOMA"
        document = _acquire(tmp_path, _venue("conference_eha"), [title]).documents()[0]
        names = self._names(document.indexable_record())
        assert "PB1983" not in names
        assert "CC-95266" in names

    @pytest.mark.xfail(
        reason=(
            "Separate pre-existing recall gap, deliberately not fixed here: the drug-shape "
            "model does not accept unhyphenated letters-then-digits codes, so PHE885 is not "
            "nominated in any context -- with or without the abstract number, before or "
            "after this change. Removing PB1983 therefore does not reveal PHE885, and "
            "widening the shape model to reach it is a recall/precision decision about the "
            "recognizer, which this boundary fix is specifically not allowed to touch."
        ),
        strict=True,
    )
    def test_the_asset_the_title_is_actually_about_is_reachable(self, tmp_path) -> None:
        document = _acquire(tmp_path, _venue("conference_eha"), [PB1983]).documents()[0]
        assert "PHE885" in self._names(document.indexable_record())

    @pytest.mark.parametrize("identifier", ["PS941", "PF155", "S898", "PB2209"])
    def test_every_eha_numbering_prefix_behaves_the_same(self, tmp_path, identifier) -> None:
        # S###/P###/PB####/PF###/PS#### are all EHA congress numbering, so the fix must be
        # structural rather than a list of the four prefixes that happened to appear.
        title = f"{identifier} ANTI-CD19 CAR-T THERAPY WITH CC-95266 IN MYELOMA"
        document = _acquire(tmp_path, _venue("conference_eha"), [title]).documents()[0]
        assert document.bibliographic_id == identifier
        names = self._names(document.indexable_record())
        assert identifier not in names
        assert "CC-95266" in names


class TestTheShapeModelIsNotWeakened:
    _names = staticmethod(_nominated)

    def test_the_same_string_in_prose_is_not_vetoed(self, tmp_path) -> None:
        # This is the constraint that rules out a blacklist. A real development program could
        # legitimately be named PB1983; only the *metadata position* disqualifies it, and here
        # the string occupies no such position.
        title = "A STUDY OF PB1983 IN RELAPSED MYELOMA"
        document = _acquire(tmp_path, _venue("conference_eha"), [title]).documents()[0]
        assert document.bibliographic_id == ""
        assert "PB1983" in self._names(document.indexable_record())

    def test_a_mid_title_identifier_shaped_token_is_not_metadata(self, tmp_path) -> None:
        title = "COMBINATION THERAPY WITH PS941 AND DEXAMETHASONE"
        document = _acquire(tmp_path, _venue("conference_eha"), [title]).documents()[0]
        assert document.bibliographic_id == ""

    def test_a_venue_without_a_documented_convention_captures_nothing(self, tmp_path) -> None:
        # Blood's Crossref titles are not numbered, which is the only reason ASH looked clean.
        # Absent a documented convention the connector must not guess at one.
        assert _venue("conference_ash").abstract_id_pattern is None
        document = _acquire(tmp_path, _venue("conference_ash"), [PB1983]).documents()[0]
        assert document.bibliographic_id == ""
        assert "PB1983" in self._names(document.indexable_record())


class TestOtherSourcesAreUnaffected:
    def test_a_record_with_no_identifier_field_nominates_as_before(self) -> None:
        # Every non-conference family emits records without the field at all; absence must
        # mean "no metadata declared", not an error and not a veto.
        record = {
            "url": "https://example.test/x",
            "title": "A trial of BMS-986393",
            "text": "A trial of BMS-986393 in myeloma.",
            "publisher": "PubMed",
            "document_type": "abstract",
            "publication_date": "2026-01-01",
        }
        assert "BMS-986393" in _nominated(record, source="pubmed")
