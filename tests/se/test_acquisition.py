from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest
import yaml

from bve.se.acquisition.connectors import (
    CONFERENCE_VENUES,
    AacrBulkProceedingsConnector,
    BulkArtifact,
    ClinicalTrialsGovConnector,
    CrossrefConferenceConnector,
    DeclaredUrlConnector,
    FdaLabelConnector,
    PubMedConnector,
    SecEdgarConnector,
    SecFiledPressReleaseConnector,
    TargetQuery,
)
from bve.se.acquisition.corpus_store import CorpusStore
from bve.se.acquisition.runner import (
    connectors_for_policy,
    modality_terms_for,
    run_acquisition,
    target_queries_for,
)
from bve.se.acquisition.policy import LiveSourcePolicy
from bve.se.schemas.contracts import BuyerProblemV2

AS_OF = date(2026, 7, 10)
TARGETS = [TargetQuery("BCMA", ["TNFRSF17", "CD269"])]
MODALITY = ["T_CELL_ENGAGER"]

_PROBLEM = {
    "schema_version": "se_buyer_problem_v2",
    "problem_id": "p",
    "version": "1.0.0",
    "buyer": {"buyer_id": "b", "name": "B", "as_of_date": "2026-07-10"},
    "strategic_gap": {
        "therapeutic_areas": ["oncology"],
        "indications": [],
        "target_expression": {
            "operator": "ANY",
            "targets": [
                {"canonical_id": "CD19", "label": "CD19", "aliases": ["CD-19"]},
                {"canonical_id": "BCMA", "label": "BCMA", "aliases": ["TNFRSF17"]},
            ],
        },
        "modalities": ["T_CELL_ENGAGER"],
        "required_biology": [],
        "capability_constraints": {
            "manufacturing": [], "delivery": [], "clinical_operations": [],
            "commercial": [], "integration": [],
        },
        "evidence_floor": {
            "minimum_stage": "PHASE_1", "human_poc_required": True,
            "required_evidence_types": ["HUMAN_CLINICAL_RESULT"],
        },
        "clinical_effect_bar": {},
        "acceptable_deal_routes": ["LICENSE"],
        "geographic_rights_requirements": [],
        "missing_evidence_policy": "REVIEW",
    },
    "output": {"landscape_mode": "SEPARATE", "group_by": "COHORT"},
    "ranking_cohort_required": True,
}


def _problem() -> BuyerProblemV2:
    return BuyerProblemV2.model_validate(_PROBLEM)


def test_ctgov_connector_generic_query_and_health(tmp_path) -> None:
    captured: list[str] = []

    def fake_search(term: str):
        captured.append(term)
        return [
            {
                "identificationModule": {"nctId": "NCT03486067", "briefTitle": "Alnuctamab study"},
                "armsInterventionsModule": {
                    "interventions": [{"name": "CC-93269", "otherNames": ["BMS-986349"]}]
                },
                "sponsorCollaboratorsModule": {"leadSponsor": {"name": "BMS"}},
                "descriptionModule": {"briefSummary": "BCMA CD3 bispecific"},
            }
        ]

    store = CorpusStore(tmp_path)
    health = ClinicalTrialsGovConnector(fake_search).acquire(
        store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF
    )
    # Query must be built only from target/modality vocabulary, never an asset name.
    assert captured and "BCMA" in captured[0] and "bispecific" in captured[0]
    assert "CC-93269" not in captured[0]
    assert health.connector_succeeded and health.query_returned_results
    assert health.documents_parsed == 1 and health.documents_indexed == 1
    doc = store.documents()[0]
    assert doc.native_snapshot and "CC-93269" in doc.text and "NCT03486067" in doc.text


def test_connector_crash_is_reported_not_raised(tmp_path) -> None:
    def boom(term: str):
        raise RuntimeError("network down")

    health = FdaLabelConnector(boom).acquire(
        CorpusStore(tmp_path), targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF
    )
    assert health.connector_succeeded is False
    assert health.query_returned_results is False
    assert "network down" in (health.error or "")


def test_fda_label_dedupes_by_setid(tmp_path) -> None:
    record = {
        "set_id": "abc-123",
        "openfda": {"brand_name": ["TECVAYLI"], "generic_name": ["TECLISTAMAB-CQYV"]},
        "description": ["BCMA-directed CD3 T-cell engager"],
    }

    def fake_search(query: str):
        return [record]

    store = CorpusStore(tmp_path)
    health = FdaLabelConnector(fake_search).acquire(
        store, targets=[TargetQuery("BCMA", ["TNFRSF17"]), TargetQuery("BCMA", [])],
        modality_terms=MODALITY, as_of_date=AS_OF,
    )
    assert health.raw_record_count == 1
    assert store.documents()[0].source_url.endswith("setid=abc-123")
    assert "teclistamab" in store.documents()[0].text.casefold()


def test_pubmed_connector_native_records(tmp_path) -> None:
    def fake_search(term: str):
        return [{"pmid": "999", "title": "AFM11 CD19 bispecific", "abstract": "Phase 1", "publication_date": "2019"}]

    store = CorpusStore(tmp_path)
    health = PubMedConnector(fake_search).acquire(
        store, targets=[TargetQuery("CD19", [])], modality_terms=MODALITY, as_of_date=AS_OF
    )
    assert health.documents_indexed == 1
    doc = store.documents()[0]
    assert doc.native_snapshot and doc.publication_date == date(2019, 1, 1)


_ASCO = CONFERENCE_VENUES[0]


def _crossref_item(doi: str, title: str, *, published: list[int] | None = None) -> dict:
    item = {
        "DOI": doi,
        "title": [title],
        "container-title": ["Journal of Clinical Oncology"],
        "type": "journal-article",
    }
    if published is not None:
        item["published"] = {"date-parts": [published]}
    return item


def test_crossref_conference_connector_indexes_abstract_metadata(tmp_path) -> None:
    def fake_search(container_title: str, query: str, as_of_date: date):
        assert container_title == "Journal of Clinical Oncology"
        return [_crossref_item("10.1200/JCO.2026.44.16_suppl.8500", "BCMA engager in myeloma", published=[2026, 6, 1])]

    store = CorpusStore(tmp_path)
    health = CrossrefConferenceConnector(_ASCO, fake_search).acquire(
        store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF
    )
    assert health.documents_indexed == 1
    doc = store.documents()[0]
    assert doc.source_family == "conference_asco"
    assert doc.source_url == "https://doi.org/10.1200/JCO.2026.44.16_suppl.8500"
    assert doc.publication_date == date(2026, 6, 1)
    # The source-native DOI and container title have to survive in the snapshot so a claim can
    # be traced back to the item Crossref actually returned.
    snapshot = json.loads((tmp_path / doc.snapshot_path).read_text())
    assert snapshot["container-title"] == ["Journal of Clinical Oncology"]
    assert snapshot["DOI"] == "10.1200/JCO.2026.44.16_suppl.8500"


def test_crossref_queries_target_vocabulary_not_asset_names(tmp_path) -> None:
    seen: list[str] = []

    def fake_search(container_title: str, query: str, as_of_date: date):
        seen.append(query)
        return []

    CrossrefConferenceConnector(_ASCO, fake_search).acquire(
        CorpusStore(tmp_path), targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF
    )
    # Target vocabulary only. Crossref relevance-ranks a bag of words, so appending the whole
    # modality vocabulary shrinks the result set instead of widening it; modality is judged
    # downstream where the asset is actually resolved.
    assert seen == ["BCMA TNFRSF17 CD269"]


def test_crossref_documents_reach_the_generated_source_index(tmp_path) -> None:
    # The regression that matters most here is silent: a document flagged as a native snapshot
    # is excluded from the exported index, so it would be acquired, hashed, receipted -- and
    # then never seen by the replay. Assert it actually arrives.
    def fake_search(container_title: str, query: str, as_of_date: date):
        return [_crossref_item("10.1200/d", "PD-1 antibody abstract", published=[2026, 5, 1])]

    store = CorpusStore(tmp_path)
    CrossrefConferenceConnector(_ASCO, fake_search).acquire(
        store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF
    )
    index_path = tmp_path / "index.yaml"
    store.export_source_index(index_path)
    index = yaml.safe_load(index_path.read_text())
    assert [record["url"] for record in index["conference_asco"]] == ["https://doi.org/10.1200/d"]


def test_crossref_items_published_after_the_as_of_date_are_refused(tmp_path) -> None:
    def fake_search(container_title: str, query: str, as_of_date: date):
        return [
            _crossref_item("10.1200/a", "Before", published=[2026, 6, 1]),
            _crossref_item("10.1200/b", "After", published=[2026, 9, 1]),
        ]

    store = CorpusStore(tmp_path)
    connector = CrossrefConferenceConnector(_ASCO, fake_search)
    connector.acquire(store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF)
    assert [doc.title for doc in store.documents()] == ["Before"]
    assert connector.withheld_as_of == ["10.1200/b"]


def test_crossref_undated_items_are_refused(tmp_path) -> None:
    def fake_search(container_title: str, query: str, as_of_date: date):
        return [_crossref_item("10.1200/c", "Undated")]

    store = CorpusStore(tmp_path)
    connector = CrossrefConferenceConnector(_ASCO, fake_search)
    connector.acquire(store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF)
    assert store.documents() == []
    assert connector.withheld_undated == ["10.1200/c"]


def test_crossref_one_mechanism_covers_every_declared_venue(tmp_path) -> None:
    # The point of parameterising by venue is that adding a conference is data, not code.
    families = []
    for venue in CONFERENCE_VENUES:
        def fake_search(container_title: str, query: str, as_of_date: date, _venue=venue):
            assert container_title in _venue.container_titles
            return [_crossref_item(f"10.1/{_venue.source_family}", "PD-1 abstract", published=[2026, 1, 1])]

        store = CorpusStore(tmp_path / venue.source_family)
        CrossrefConferenceConnector(venue, fake_search).acquire(
            store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF
        )
        families.append(store.documents()[0].source_family)
    assert families == ["conference_asco", "conference_aacr", "conference_ash"]


#: Two abstracts in the shape the real proceedings PDF prints them: a session header with no
#: delimiter of its own, a bare ``#NNNN`` line, a title that wraps, then authors and body.
_PROCEEDINGS_TEXT = """Sunday, April 19, 2026
: Immuno-oncology
Poster Session
#0001
A BCMA-directed T cell engager in relapsed myeloma: a dose
escalation study.
Some Author
, Another Author
Some Cancer Center, Boston, MA
Twelve patients received the agent. Responses were observed at all dose levels.
#0002
An unrelated abstract about mitochondrial metabolism.
Third Author
No target of interest is mentioned here.
"""


def _bulk_artifact(tmp_path, text: str = _PROCEEDINGS_TEXT, *, published=date(2026, 4, 13)):
    path = tmp_path / "proceedings.pdf"
    path.write_bytes(b"%PDF-1.7 fixture bytes")
    return BulkArtifact(
        source_url="https://www.aacr.org/proceedings/Part-1.pdf",
        local_path=path,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        published=published,
        publisher="AACR",
        source_family="conference_aacr",
    ), (lambda _path: text)


def test_bulk_proceedings_splits_on_printed_abstract_numbers(tmp_path) -> None:
    artifact, extract = _bulk_artifact(tmp_path)
    store = CorpusStore(tmp_path / "corpus")
    health = AacrBulkProceedingsConnector(artifact, extract_fn=extract).acquire(
        store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF
    )
    # Both abstracts were found; only the one matching the declared target vocabulary is
    # admitted, and the count of what was seen stays visible next to what was kept.
    assert health.raw_record_count == 2
    assert health.documents_indexed == 1
    doc = store.documents()[0]
    assert doc.source_family == "conference_aacr"
    assert doc.source_url.endswith("Part-1.pdf#0001")
    assert "Twelve patients received the agent." in doc.text
    # A wrapped title is joined to its sentence end, and the author list is not part of it.
    assert doc.title == (
        "A BCMA-directed T cell engager in relapsed myeloma: a dose escalation study."
    )
    assert "Some Author" not in doc.title


def test_bulk_proceedings_document_is_an_ordinary_conference_abstract(tmp_path) -> None:
    """A bulk route is an acquisition route, not a new authority.

    The abstract is printed by the society that ran the meeting, so it is tiered as a primary
    conference abstract exactly as a PubMed abstract is, and it must travel through the
    generated source index -- claiming a native snapshot would drop it out of replay silently.
    """

    artifact, extract = _bulk_artifact(tmp_path)
    store = CorpusStore(tmp_path / "corpus")
    AacrBulkProceedingsConnector(artifact, extract_fn=extract).acquire(
        store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF
    )
    doc = store.documents()[0]
    assert doc.document_type == "conference_abstract"
    assert doc.native_snapshot is False
    snapshot = json.loads((tmp_path / "corpus" / doc.snapshot_path).read_text())
    assert snapshot["delivery_channel"] == "PUBLISHER_BULK_DOWNLOAD"
    assert snapshot["bulk_sha256"] == artifact.sha256
    assert snapshot["matched_target_terms"] == ["bcma"]


def test_bulk_proceedings_dates_documents_from_the_verifiable_artifact_timestamp(
    tmp_path,
) -> None:
    # The session date printed inside the document is the document's own say-so; the artifact's
    # Last-Modified is what a third party can check, so that is what carries the date.
    artifact, extract = _bulk_artifact(tmp_path, published=date(2026, 4, 13))
    store = CorpusStore(tmp_path / "corpus")
    AacrBulkProceedingsConnector(artifact, extract_fn=extract).acquire(
        store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF
    )
    assert store.documents()[0].publication_date == date(2026, 4, 13)


def test_bulk_proceedings_published_after_the_as_of_date_admits_nothing(tmp_path) -> None:
    artifact, extract = _bulk_artifact(tmp_path, published=date(2026, 9, 1))
    store = CorpusStore(tmp_path / "corpus")
    health = AacrBulkProceedingsConnector(artifact, extract_fn=extract).acquire(
        store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF
    )
    assert store.documents() == []
    # Refused, not merely absent: a zero document count alone cannot distinguish "withheld by
    # the as-of policy" from "the filter never ran".
    assert health.raw_record_count == 2


def test_bulk_proceedings_refuses_bytes_the_receipt_does_not_describe(tmp_path) -> None:
    artifact, extract = _bulk_artifact(tmp_path)
    artifact.local_path.write_bytes(b"%PDF-1.7 different bytes")
    store = CorpusStore(tmp_path / "corpus")
    health = AacrBulkProceedingsConnector(artifact, extract_fn=extract).acquire(
        store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF
    )
    assert health.connector_succeeded is False
    assert "does not match" in (health.error or "")
    assert store.documents() == []


def _ex99_hit(
    doc: str = "ex991.htm",
    *,
    file_type: str = "EX-99.1",
    description: str = "EX-99.1",
    root_forms: list[str] | None = None,
    ciks: list[str] | None = None,
    file_date: str = "2024-03-07",
) -> dict:
    return {
        "_id": f"0000950170-24-029298:{doc}",
        "_source": {
            "ciks": ["0001796280"] if ciks is None else ciks,
            "display_names": ["ORIC (ORIC)"],
            "file_date": file_date,
            "file_type": file_type,
            "file_description": description,
            "root_forms": ["8-K"] if root_forms is None else root_forms,
        },
    }


def test_sec_filed_press_release_admits_an_exhibit_that_says_it_is_one(tmp_path) -> None:
    def fake_search(query: str):
        return [_ex99_hit(description="EX-99.1 - PRESS RELEASE DATED MARCH 7, 2024")]

    store = CorpusStore(tmp_path)
    health = SecFiledPressReleaseConnector(
        fake_search, fetch_fn=lambda url: "<html>ORIC-944 data</html>", max_searches=1
    ).acquire(store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF)

    assert health.documents_indexed == 1
    doc = store.documents()[0]
    assert doc.source_family == "company_press_release_sec_filed"
    snapshot = json.loads((tmp_path / doc.snapshot_path).read_text())
    # The channel is recorded so nobody later reads this family as a newsroom crawl.
    assert snapshot["delivery_channel"] == "SEC_EXHIBIT"
    assert snapshot["classification_basis"] == "file_description"


def test_sec_filed_press_release_accepts_a_release_that_only_its_header_declares(tmp_path) -> None:
    def fake_search(query: str):
        return [_ex99_hit()]

    store = CorpusStore(tmp_path)
    connector = SecFiledPressReleaseConnector(
        fake_search,
        fetch_fn=lambda url: "<html><p>FOR IMMEDIATE RELEASE</p><p>ORIC-944 data</p></html>",
        max_searches=1,
    )
    connector.acquire(store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF)
    assert [doc.source_family for doc in store.documents()] == ["company_press_release_sec_filed"]
    snapshot = json.loads((tmp_path / store.documents()[0].snapshot_path).read_text())
    assert snapshot["classification_basis"] == "document_header"


def test_sec_filed_press_release_refuses_a_bare_ex99_exhibit(tmp_path) -> None:
    # The point of the family: an EX-99 exhibit is whatever the issuer attached. A corporate
    # deck is not a press release, and calling it one would be a claim the filing never made.
    def fake_search(query: str):
        return [_ex99_hit(description="EX-99.1 - F-STAR CORPORATE PRESENTATION")]

    store = CorpusStore(tmp_path)
    connector = SecFiledPressReleaseConnector(
        fake_search,
        fetch_fn=lambda url: "<html>Slide 1. Corporate presentation. Forward-looking statements.</html>",
        max_searches=1,
    )
    health = connector.acquire(store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF)
    assert store.documents() == []
    assert health.parse_failures == 0
    assert [row["reason"] for row in connector.rejected] == ["no_press_release_indicator"]


@pytest.mark.parametrize(
    ("hit", "reason"),
    [
        (_ex99_hit(ciks=[]), "no_sec_registrant_cik"),
        (_ex99_hit(root_forms=["425"]), "form_not_eligible"),
        (_ex99_hit(file_type="EX-10.1"), "not_an_ex99_exhibit"),
        (_ex99_hit(file_date="2026-09-01"), "filed_after_as_of_date"),
    ],
)
def test_sec_filed_press_release_eligibility_chain_is_mechanical(tmp_path, hit, reason) -> None:
    def fake_search(query: str):
        return [hit]

    store = CorpusStore(tmp_path)
    connector = SecFiledPressReleaseConnector(
        fake_search, fetch_fn=lambda url: "PRESS RELEASE", max_searches=1
    )
    connector.acquire(store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF)
    # Every rejection names the step that failed, and no step is skipped by a later one
    # happening to succeed -- the fetched body here would otherwise classify as a release.
    assert store.documents() == []
    assert [row["reason"] for row in connector.rejected] == [reason]


def test_sec_filed_press_release_admits_a_foreign_issuers_6k_release(tmp_path) -> None:
    """6-K is the foreign private issuer's current report, and carries the same releases.

    Restricting the family to 8-K did not filter by genre, it filtered by the registrant's
    nationality: a 6-K EX-99.1 described "PRESS RELEASE" is mechanically indistinguishable
    from the 8-K one above, and excluding it made every non-US issuer invisible to a family
    whose entire subject is issuer-authored news.
    """

    def fake_search(query: str):
        return [_ex99_hit(root_forms=["6-K"], description="EX-99.1 - PRESS RELEASE")]

    store = CorpusStore(tmp_path)
    connector = SecFiledPressReleaseConnector(
        fake_search, fetch_fn=lambda url: "<html>data</html>", max_searches=1
    )
    health = connector.acquire(store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF)
    assert health.documents_indexed == 1, "a 6-K press release was refused on form alone"
    assert connector.rejected == []


def test_sec_filed_press_release_records_the_exact_filing_date(tmp_path) -> None:
    """EDGAR states the day, so the day is stored.

    The previous behaviour kept only the year and stamped January 1, which is both a date the
    document was not published on and an *earlier* one -- it made every filing look up to
    eleven months older than it is.
    """

    def fake_search(query: str):
        return [_ex99_hit(file_date="2024-03-07", description="EX-99.1 - PRESS RELEASE")]

    store = CorpusStore(tmp_path)
    SecFiledPressReleaseConnector(
        fake_search, fetch_fn=lambda url: "<html>data</html>", max_searches=1
    ).acquire(store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF)
    assert store.documents()[0].publication_date == date(2024, 3, 7)


def test_sec_filing_records_the_exact_filing_date(tmp_path) -> None:
    def fake_search(query: str):
        return [_ex99_hit(file_date="2024-03-07")]

    store = CorpusStore(tmp_path)
    SecEdgarConnector(fake_search, fetch_fn=lambda url: "<html>data</html>").acquire(
        store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF
    )
    assert store.documents()[0].publication_date == date(2024, 3, 7)


def test_sec_filed_press_release_rejections_carry_the_metadata_they_were_made_on(
    tmp_path,
) -> None:
    """A refusal census has to be answerable from the receipt, not from a second live run."""

    def fake_search(query: str):
        return [_ex99_hit(root_forms=["425"], description="EX-99.1 - MERGER MATERIAL")]

    store = CorpusStore(tmp_path)
    connector = SecFiledPressReleaseConnector(
        fake_search, fetch_fn=lambda url: "PRESS RELEASE", max_searches=1
    )
    connector.acquire(store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF)
    rejection = connector.rejected[0]
    assert rejection["reason"] == "form_not_eligible"
    assert rejection["file_type"] == "EX-99.1"
    assert rejection["file_description"] == "EX-99.1 - MERGER MATERIAL"
    assert rejection["file_date"] == "2024-03-07"


def test_sec_connector_fetches_bounded_documents(tmp_path) -> None:
    def fake_search(query: str):
        return [{"_id": "0000950170-24-029298:oric-20231231.htm", "_source": {"ciks": ["0001796280"], "display_names": ["ORIC (ORIC)"], "file_date": "2024-03-07"}}]

    def fake_fetch(url: str):
        return "<html><body>MK-6070 HPN217 BCMA bispecific</body></html>"

    store = CorpusStore(tmp_path)
    health = SecEdgarConnector(fake_search, fetch_fn=fake_fetch, max_documents=5).acquire(
        store, targets=TARGETS, modality_terms=MODALITY, as_of_date=AS_OF
    )
    assert health.documents_indexed == 1
    doc = store.documents()[0]
    assert "HPN217" in doc.text and "<html>" not in doc.text
    assert "edgar/data/1796280/" in doc.source_url


def test_sec_full_text_queries_ask_for_words_a_filing_could_contain() -> None:
    """An ontology identifier is not text. Phrase-searching one retrieves nothing.

    ``"PDCD1 ANTIBODY_DRUG_CONJUGATE"`` is unanswerable by a full-text index over prose, and
    an unanswerable query reads downstream as "this source holds no evidence" rather than as
    a defect in the asking, which is why the distinction is pinned here.
    """

    phrases = SecEdgarConnector._search_phrases(
        TargetQuery("PDCD1", ["PD-1", "CD279"]),
        ["ANTIBODY_DRUG_CONJUGATE", "antibody drug conjugate"],
    )

    assert not any("_" in phrase for phrase in phrases)
    # Target alone comes first: a preclinical program described without the ontology's
    # modality wording is exactly what the new source families are meant to reach.
    assert phrases[:3] == ['"PDCD1"', '"PD-1"', '"CD279"']
    assert '"PD-1" "antibody drug conjugate"' in phrases
    # Still generic. No asset name can enter the query for the source to then "find".
    assert not any("pembrolizumab" in phrase.casefold() for phrase in phrases)


def test_sec_search_traffic_is_bounded_independently_of_the_document_budget(
    tmp_path,
) -> None:
    """The alias x modality product is order 10^3 phrases; the source is a public service."""

    asked: list[str] = []

    def fake_search(query: str):
        asked.append(query)
        return []

    health = SecEdgarConnector(
        fake_search, fetch_fn=lambda url: "", max_documents=5, max_searches=4
    ).acquire(
        CorpusStore(tmp_path),
        targets=[TargetQuery("PDCD1", ["PD-1", "CD279"])],
        modality_terms=["bispecific antibody", "monoclonal antibody"],
        as_of_date=AS_OF,
    )

    assert len(asked) == 4
    assert health.connector_succeeded


def _edgar_hit(document: str, file_date: str) -> dict:
    return {
        "_id": f"0000001234-26-000001:{document}",
        "_source": {
            "ciks": ["0000001234"],
            "display_names": ["Example Therapeutics (EXM)"],
            "file_type": "10-K",
            "file_date": file_date,
        },
    }


def test_sec_refuses_filings_published_after_the_as_of_date(tmp_path) -> None:
    """A filing the run could not have read is lookahead, whatever the source returns.

    EDGAR full-text search answers as of today, not as of the benchmark date, so a run
    replaying an August question would otherwise be handed September disclosures and score
    as though it had found them. The filter is client-side because that is the guarantee;
    asking the service politely for a date range is only traffic reduction.
    """

    def fake_search(query: str):
        return [
            _edgar_hit("before.htm", "2026-07-01"),
            _edgar_hit("after.htm", "2026-09-01"),
            _edgar_hit("undated.htm", ""),
        ]

    store = CorpusStore(tmp_path)
    health = SecEdgarConnector(
        fake_search, fetch_fn=lambda url: "text", max_documents=10, max_searches=1
    ).acquire(
        store,
        targets=[TargetQuery("PDCD1", ["PD-1"])],
        modality_terms=["monoclonal antibody"],
        as_of_date=AS_OF,
    )

    documents = [doc.source_url.rsplit("/", 1)[-1] for doc in store.documents()]
    assert documents == ["before.htm"]
    # An undated hit is not admitted either: unknown is not known-to-be-earlier.
    assert health.raw_record_count == 1


def test_sec_document_budget_is_spread_across_phrases_not_spent_on_the_first(
    tmp_path,
) -> None:
    """Otherwise the search budget buys nothing.

    One broad alias phrase returns far more hits than the document budget, so taking hits in
    arrival order means every modality-qualified phrase is searched and then discarded. The
    budget is what decides which filings become evidence, so it has to sample the phrases
    that were actually asked.
    """

    asked: list[str] = []

    def fake_search(query: str):
        asked.append(query)
        slug = f"p{len(asked)}"
        return [_edgar_hit(f"{slug}_{n}.htm", "2026-07-01") for n in range(30)]

    store = CorpusStore(tmp_path)
    SecEdgarConnector(
        fake_search, fetch_fn=lambda url: "text", max_documents=6, max_searches=3
    ).acquire(
        store,
        targets=[TargetQuery("PDCD1", ["PD-1"])],
        modality_terms=["monoclonal antibody"],
        as_of_date=AS_OF,
    )

    assert len(asked) == 3
    phrases = {
        doc.source_url.rsplit("/", 1)[-1].split("_")[0] for doc in store.documents()
    }
    assert phrases == {"p1", "p2", "p3"}


def test_sec_search_ledger_records_why_these_documents_and_not_others(tmp_path) -> None:
    """The corpus records which filings became evidence; it cannot record why those.

    Whether a program is absent because no filing discusses it, because the filing postdates
    the as-of date, or because the document budget stopped one short are three different
    findings calling for three different responses, and only the ledger distinguishes them.
    """

    ledger = tmp_path / "ledger" / "sec_edgar_search.jsonl"

    def fake_search(query: str):
        return [
            _edgar_hit(f"{query.count(' ')}_admitted.htm", "2026-07-01"),
            _edgar_hit(f"{query.count(' ')}_future.htm", "2026-09-01"),
        ]

    SecEdgarConnector(
        fake_search,
        fetch_fn=lambda url: "text",
        max_documents=1,
        max_searches=2,
        search_ledger=ledger,
    ).acquire(
        CorpusStore(tmp_path / "corpus"),
        targets=[TargetQuery("PDCD1", ["PD-1"])],
        modality_terms=["monoclonal antibody"],
        as_of_date=AS_OF,
    )

    records = [json.loads(line) for line in ledger.read_text().splitlines()]
    summary = records[0]
    assert summary["phrases_searched"] == 2
    assert summary["search_budget_exhausted"] is True
    assert summary["documents_selected"] == 1

    phrases = [record for record in records if record["record"] == "phrase"]
    assert [record["hits_returned"] for record in phrases] == [2, 2]
    # The as-of refusal is counted, not silently folded into "the source had nothing".
    assert [record["withheld_after_as_of_date"] for record in phrases] == [1, 1]

    selected = [record for record in records if record["record"] == "selected"]
    assert len(selected) == 1
    assert selected[0]["selected_by_phrase"] == phrases[0]["phrase"]
    assert selected[0]["file_date"] == "2026-07-01"


def test_sec_writes_no_ledger_unless_asked(tmp_path) -> None:
    SecEdgarConnector(
        lambda query: [], fetch_fn=lambda url: "", max_searches=1
    ).acquire(
        CorpusStore(tmp_path),
        targets=[TargetQuery("PDCD1", [])],
        modality_terms=[],
        as_of_date=AS_OF,
    )
    assert not list(tmp_path.glob("*.jsonl"))


def test_runner_target_queries_have_no_asset_names() -> None:
    problem = _problem()
    targets = target_queries_for(problem)
    ids = {t.canonical_id for t in targets}
    assert ids == {"CD19", "BCMA"}
    all_terms = " ".join(t.or_group() for t in targets).casefold()
    for asset_code in ("cc-93269", "afm11", "teclistamab", "nct"):
        assert asset_code not in all_terms
    assert "T_CELL_ENGAGER" in modality_terms_for(problem)


def test_run_acquisition_aggregates_health(tmp_path) -> None:
    class StubConnector:
        source_family = "clinicaltrials_gov"

        def acquire(self, store, *, targets, modality_terms, as_of_date):
            return ClinicalTrialsGovConnector(
                lambda term: [
                    {
                        "identificationModule": {"nctId": "NCT1", "briefTitle": "t"},
                        "armsInterventionsModule": {"interventions": [{"name": "X-1"}]},
                        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "S"}},
                        "descriptionModule": {"briefSummary": "BCMA bispecific"},
                    }
                ]
            ).acquire(store, targets=targets, modality_terms=modality_terms, as_of_date=as_of_date)

    report = run_acquisition(_problem(), tmp_path, connectors=[StubConnector()])
    summary = report.stage_summary()
    assert summary["connector_succeeded"] == 1
    assert summary["documents_indexed"] == 1
    # Two target queries (CD19, BCMA) each return the record; the store dedups to one document
    # while retrieval-volume counts reflect both processed records.
    assert report.total_documents_indexed() == 2
    assert len(CorpusStore(tmp_path).documents()) == 1


def test_policy_constructs_exact_required_connector_set_and_rejects_missing() -> None:
    policy = LiveSourcePolicy.model_validate(
        {
            "policy_version": "test",
            "required_source_families": ["clinicaltrials_gov", "company_press_release"],
            "supported_targets": ["CD19", "BCMA"],
            "supported_modalities": ["T_CELL_ENGAGER"],
            "declared_sources": [
                {
                    "source_family": "company_press_release",
                    "urls": ["https://example.com/news"],
                }
            ],
        }
    )
    assert [connector.source_family for connector in connectors_for_policy(policy)] == [
        "clinicaltrials_gov",
        "company_press_release",
    ]

    missing = policy.model_copy(update={"declared_sources": ()})
    with pytest.raises(ValueError, match="no connector configuration"):
        connectors_for_policy(missing)


def _page(published_meta: str, body: str = "Ivonescimab data update") -> str:
    return f"<html><head>{published_meta}</head><body><p>{body}</p></body></html>"


def test_declared_url_pages_published_after_the_as_of_date_are_refused(tmp_path) -> None:
    """A live web page answers as of today, not as of the benchmark date.

    Company press and pipeline pages carry no server-side date filter, so a run replaying an
    August question would otherwise index September announcements and be credited with having
    found them. This is the same lookahead guarantee the filing search needs, enforced on the
    page's own published date.
    """

    pages = {
        "https://example.com/before": _page(
            '<meta property="article:published_time" content="2026-07-01T09:00:00Z">'
        ),
        "https://example.com/after": _page(
            '<meta property="article:published_time" content="2026-09-01T09:00:00Z">'
        ),
    }

    store = CorpusStore(tmp_path)
    health = DeclaredUrlConnector(
        "company_press_release", list(pages), fetch_fn=pages.__getitem__
    ).acquire(
        store,
        targets=[TargetQuery("PDCD1", ["PD-1"])],
        modality_terms=["monoclonal antibody"],
        as_of_date=AS_OF,
    )

    assert [doc.source_url for doc in store.documents()] == ["https://example.com/before"]
    # Withheld, not broken: the page read fine, it is simply inadmissible for this question.
    assert health.connector_succeeded
    assert health.parse_failures == 0


def test_declared_url_undated_pages_are_refused(tmp_path) -> None:
    """Unknown is not known-to-be-earlier.

    An undated page cannot be shown to predate the as-of date, and admitting it would let
    lookahead in through the one case the filter cannot see.
    """

    pages = {
        "https://example.com/dated": _page(
            '<meta itemprop="datePublished" content="2026-06-15">'
        ),
        "https://example.com/undated": _page("<title>Pipeline</title>"),
    }

    store = CorpusStore(tmp_path)
    connector = DeclaredUrlConnector(
        "company_pipeline_or_presentation", list(pages), fetch_fn=pages.__getitem__
    )
    connector.acquire(
        store,
        targets=[TargetQuery("PDCD1", ["PD-1"])],
        modality_terms=["monoclonal antibody"],
        as_of_date=AS_OF,
    )

    assert [doc.source_url for doc in store.documents()] == ["https://example.com/dated"]
    assert connector.withheld_undated == ["https://example.com/undated"]


def test_declared_url_records_the_page_publication_date_not_the_as_of_date(
    tmp_path,
) -> None:
    """The corpus should say when the page was published, so the claim can be dated later."""

    html = _page('<time datetime="2026-05-20">May 20, 2026</time>')
    store = CorpusStore(tmp_path)
    DeclaredUrlConnector(
        "company_press_release", ["https://example.com/pr"], fetch_fn=lambda url: html
    ).acquire(
        store,
        targets=[TargetQuery("PDCD1", ["PD-1"])],
        modality_terms=["monoclonal antibody"],
        as_of_date=AS_OF,
    )

    document = store.documents()[0]
    assert document.publication_date == date(2026, 5, 20)


def test_declared_url_follows_index_links_to_reach_dated_documents(tmp_path) -> None:
    """A newsroom index is undated, so on its own the family can contribute nothing.

    Under the as-of contract an index page is refused -- correctly, it carries no publication
    date -- which would make every declared-URL family silently empty. The evidence is on the
    dated articles the index links to, so the index is treated as a place to look rather than
    as a document.
    """

    pages = {
        "https://example.com/news": (
            '<a href="/news/one">One</a><a href="/news/two">Two</a>'
            '<a href="https://other.example.org/off">Off-site</a>'
        ),
        "https://example.com/news/one": _page(
            '<meta property="article:published_time" content="2026-06-01">', "AK112 update"
        ),
        "https://example.com/news/two": _page(
            '<meta property="article:published_time" content="2026-09-30">', "Later news"
        ),
    }

    store = CorpusStore(tmp_path)
    connector = DeclaredUrlConnector(
        "company_press_release",
        ["https://example.com/news"],
        fetch_fn=pages.__getitem__,
        follow_links=5,
    )
    connector.acquire(
        store,
        targets=[TargetQuery("PDCD1", ["PD-1"])],
        modality_terms=["monoclonal antibody"],
        as_of_date=AS_OF,
    )

    # The index itself is not evidence; the one article filed before the as-of date is.
    assert [doc.source_url for doc in store.documents()] == ["https://example.com/news/one"]
    # Off-host links are not followed: the declared URL scopes the crawl to that publisher.
    assert "https://other.example.org/off" not in connector.visited


def test_declared_url_link_following_is_bounded_per_index(tmp_path) -> None:
    """An index can link to hundreds of articles; the source is a public service."""

    links = "".join(f'<a href="/a/{n}">{n}</a>' for n in range(50))
    fetched: list[str] = []

    def fetch(url: str) -> str:
        fetched.append(url)
        if url.endswith("/news"):
            return links
        return _page('<meta property="article:published_time" content="2026-06-01">')

    connector = DeclaredUrlConnector(
        "conference_asco",
        ["https://example.com/news"],
        fetch_fn=fetch,
        follow_links=3,
    )
    connector.acquire(
        CorpusStore(tmp_path),
        targets=[TargetQuery("PDCD1", ["PD-1"])],
        modality_terms=["monoclonal antibody"],
        as_of_date=AS_OF,
    )

    # One index fetch plus the budgeted articles, and no more.
    assert len(fetched) == 4
