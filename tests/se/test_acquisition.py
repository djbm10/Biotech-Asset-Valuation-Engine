from __future__ import annotations

import json
from datetime import date

import pytest

from bve.se.acquisition.connectors import (
    ClinicalTrialsGovConnector,
    DeclaredUrlConnector,
    FdaLabelConnector,
    PubMedConnector,
    SecEdgarConnector,
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
