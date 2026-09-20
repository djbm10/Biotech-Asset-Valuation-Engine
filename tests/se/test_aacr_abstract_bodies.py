"""AACR is the first conference route that returns the abstract itself.

ASH, EHA and ASCO deposit titles and DOIs, so four venues in a row established a habit the
architecture had started to read as a fact: a conference record is a pointer. AACR deposits
full abstract bodies -- verified live, on every record sampled -- which makes two things
newly possible and one newly necessary.

Possible: real prose for identity, target and stage, from a venue that publishes early
oncology data. Necessary: the record must stop describing itself as metadata the moment it
stops being metadata, because a type is what a later reader consults to decide what a
document can support.
"""

from __future__ import annotations

from datetime import date

from bve.se.acquisition.connectors import (
    CONFERENCE_VENUES,
    CrossrefConferenceConnector,
    TargetQuery,
    _crossref_abstract_text,
    _leading_bibliographic_id,
)
from bve.se.acquisition.corpus_store import CorpusStore

AS_OF = date(2026, 9, 20)

AACR = next(v for v in CONFERENCE_VENUES if v.source_family == "conference_aacr")

#: Shaped exactly as Crossref returns it: a JATS fragment, headed by the publisher's own
#: label for the block, with the identifier printed at the front of the title.
AACR_ITEM = {
    "DOI": "10.1158/1538-7445.AM2024-CT204",
    "title": ["Abstract CT204: Efficacy of Bria-IMT regimen in inducing CNS metastasis regression"],
    "page": "CT204-CT204",
    "published": {"date-parts": [[2024, 4, 5]]},
    "abstract": (
        "<jats:title>Abstract</jats:title>\n"
        "<jats:p>Objectives: This retrospective analysis evaluates the efficacy of "
        "Bria-IMT as a monotherapy on CNS tumor regression.</jats:p>\n"
        "<jats:p>Results: Of 26 evaluable patients, 4 had a partial response.</jats:p>"
    ),
}


def _acquire(item: dict, tmp_path) -> tuple[CorpusStore, list]:
    store = CorpusStore(tmp_path / "corpus")
    connector = CrossrefConferenceConnector(
        AACR, search_fn=lambda _container, _query, _as_of: [item]
    )
    health = connector.acquire(
        store,
        targets=[TargetQuery("CD19", ["CD19"])],
        modality_terms=[],
        as_of_date=AS_OF,
    )
    assert health.connector_succeeded
    return store, list(store.documents())


class TestTheAbstractBodyIsWhatGetsStored:
    def test_the_body_reaches_the_indexed_text(self, tmp_path) -> None:
        _store, documents = _acquire(AACR_ITEM, tmp_path)
        assert len(documents) == 1
        assert "partial response" in documents[0].text
        assert "CNS tumor regression" in documents[0].text

    def test_the_title_still_leads_the_text(self, tmp_path) -> None:
        _store, documents = _acquire(AACR_ITEM, tmp_path)
        assert documents[0].text.startswith("Abstract CT204:")
        assert documents[0].title.startswith("Abstract CT204:")

    def test_a_record_carrying_a_body_is_not_called_metadata(self, tmp_path) -> None:
        _store, documents = _acquire(AACR_ITEM, tmp_path)
        assert documents[0].document_type == "conference_abstract"

    def test_a_title_only_record_keeps_the_metadata_type(self, tmp_path) -> None:
        # ASH, EHA and ASCO deposit no abstract. Their records are unchanged by this work,
        # and the type keeps saying so.
        item = {k: v for k, v in AACR_ITEM.items() if k != "abstract"}
        _store, documents = _acquire(item, tmp_path)
        assert documents[0].document_type == "conference_abstract_metadata"
        assert documents[0].text == documents[0].title


class TestJatsMarkupIsNotProse:
    def test_the_tags_are_removed(self) -> None:
        text = _crossref_abstract_text(AACR_ITEM["abstract"])
        assert "<jats:p>" not in text
        assert "jats" not in text.lower()

    def test_the_publishers_block_heading_is_not_kept(self) -> None:
        # "Abstract" here labels the block; it is not the abstract's first word, and leaving
        # it in puts a heading where the prose should start.
        assert _crossref_abstract_text(AACR_ITEM["abstract"]).startswith("Objectives:")

    def test_a_venue_depositing_nothing_yields_nothing(self) -> None:
        assert _crossref_abstract_text(None) == ""
        assert _crossref_abstract_text("   ") == ""


class TestTheAacrIdentifierIsMetadataNotAnAsset:
    def test_the_identifier_is_recorded_without_the_publishers_label(self, tmp_path) -> None:
        # "Abstract" is AACR's word for the number, not part of the number.
        _store, documents = _acquire(AACR_ITEM, tmp_path)
        assert documents[0].bibliographic_id == "CT204"

    def test_every_live_observed_shape_is_recognised(self) -> None:
        # Every one of these was read off a live AACR record. They are listed to show the
        # range the frame has to survive, not because the rule enumerates them: an earlier
        # version did enumerate prefixes and missed the last four outright.
        for identifier in ("3872", "LB253", "CT204", "NG06", "A042", "B038", "PR02",
                           "LB-138", "ND02", "DDT01-04", "P5-04-26"):
            title = f"Abstract {identifier}: A study of something"
            assert _leading_bibliographic_id(
                title, AACR.abstract_id_pattern, AACR.abstract_id_label
            ) == identifier

    def test_a_code_later_in_the_title_is_left_alone(self) -> None:
        # The identifier is metadata because of where AACR prints it. The same shape further
        # in is an ordinary word of the title, and often a real program code.
        assert _leading_bibliographic_id(
            "Abstract CT204: A phase 1 study of ABSK021 in solid tumors",
            AACR.abstract_id_pattern,
            AACR.abstract_id_label,
        ) == "CT204"

    def test_the_colon_is_required_where_the_venue_declares_a_frame(self) -> None:
        # AACR states label, identifier, colon. Without the colon the identifier has no
        # stated end, so nothing is claimed rather than something being guessed at.
        assert _leading_bibliographic_id(
            "Abstract 42 patients were enrolled in this analysis",
            AACR.abstract_id_pattern,
            AACR.abstract_id_label,
        ) == ""

    def test_an_identifier_must_contain_a_digit(self) -> None:
        # Guards the frame against a title that simply opens with a word and a colon.
        assert _leading_bibliographic_id(
            "Abstract Withdrawn: this submission was retracted",
            AACR.abstract_id_pattern,
            AACR.abstract_id_label,
        ) == ""

    def test_a_venue_declaring_no_label_is_unaffected(self) -> None:
        # EHA prints its number bare. Adding the label to the dataclass must not require it.
        eha = next(v for v in CONFERENCE_VENUES if v.source_family == "conference_eha")
        assert eha.abstract_id_label is None
        assert _leading_bibliographic_id(
            "PB1983: Trials in progress", eha.abstract_id_pattern, eha.abstract_id_label
        ) == "PB1983"


class TestTheVenueCitesItselfInsideTheAbstract:
    """AACR's own bibliographic record, deposited as the abstract's last paragraph.

    Found by the first live replay, not by any fixture: 98 of 334 new candidates were author
    names. The block reads ``Citation Format: <every author>. <title> [abstract]. In:
    Proceedings ...`` and an author list is a run of capitalised unfamiliar tokens -- which is
    indistinguishable, to an identity layer, from a list of development codes.

    It is the same ruling as the abstract number, applied to the same record's other
    bibliographic block: metadata carried by the document, never a statement about a drug.
    """

    #: A real block, trimmed. Two authors are enough to show the shape; the live records
    #: carry up to twenty.
    CITATION = (
        "<jats:p>Citation Format: Thierry Iraguha, Saurabh Dahiya, Stephanie Avila. "
        "Immune response to COVID-19 vaccination [abstract]. In: Proceedings of the "
        "American Association for Cancer Research Annual Meeting 2022; 2022 Apr 8-13. "
        "Philadelphia (PA): AACR; Cancer Res 2022;82(12_Suppl):Abstract nr 3586.</jats:p>"
    )

    def test_the_citation_block_is_not_part_of_the_abstract(self) -> None:
        text = _crossref_abstract_text(AACR_ITEM["abstract"] + "\n" + self.CITATION)
        assert "Citation Format" not in text
        assert "Proceedings of the American Association" not in text

    def test_the_authors_it_names_never_reach_the_corpus(self) -> None:
        # The point of removing it. Each of these was minted as an asset in the live run.
        text = _crossref_abstract_text(AACR_ITEM["abstract"] + "\n" + self.CITATION)
        for author in ("Thierry", "Iraguha", "Saurabh", "Dahiya", "Stephanie", "Avila"):
            assert author not in text

    def test_the_abstract_it_follows_is_untouched(self) -> None:
        # A rule that trims the end of a document can trim a result. This one must not.
        with_citation = _crossref_abstract_text(AACR_ITEM["abstract"] + "\n" + self.CITATION)
        without = _crossref_abstract_text(AACR_ITEM["abstract"])
        assert with_citation == without
        assert "4 had a partial response" in with_citation

    def test_prose_that_merely_mentions_a_citation_is_kept(self) -> None:
        # Matched as an element, so the words alone are not the trigger. An abstract is
        # entitled to discuss citation formats without losing its last paragraph.
        fragment = (
            "<jats:p>We followed the Citation Format described previously, and observed "
            "a complete response in 3 of 12 patients.</jats:p>"
        )
        text = _crossref_abstract_text(fragment)
        assert "complete response in 3 of 12 patients" in text

    def test_a_citation_that_is_not_last_is_left_alone(self) -> None:
        # The venue prints it last. Anchoring there means an unexpected layout is kept and
        # visible rather than silently truncating everything after it.
        fragment = self.CITATION + "<jats:p>Results: 4 of 26 responded.</jats:p>"
        assert "4 of 26 responded" in _crossref_abstract_text(fragment)

    def test_a_citation_appended_to_the_final_prose_paragraph_is_also_removed(self) -> None:
        # 15 of 198 live records do this: no wrapper, the citation simply continues the
        # conclusion sentence. An element-level rule reached the other 183 and looked done.
        fragment = (
            "<jats:p>Conclusions: the construct showed a superior therapeutic effect. "
            "Citation Format: Jiao Jiao. CD19/CD22 bispecific CAR-T cells are effective "
            "[abstract]. In: Proceedings of the American Association for Cancer Research "
            "Annual Meeting 2025; 2025 Apr 25-30; Chicago, IL.</jats:p>"
        )
        text = _crossref_abstract_text(fragment)
        assert "superior therapeutic effect" in text
        assert "Citation Format" not in text
        assert "Jiao" not in text

    def test_the_whole_frame_is_required_not_just_the_label(self) -> None:
        # Label alone is not the citation. Requiring "[abstract]. In: Proceedings" is what
        # keeps this from being a rule about two common words.
        fragment = "<jats:p>Citation Format: see methods. 4 of 26 responded.</jats:p>"
        assert "4 of 26 responded" in _crossref_abstract_text(fragment)
