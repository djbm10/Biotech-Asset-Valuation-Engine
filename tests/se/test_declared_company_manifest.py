"""The company-pipeline source: declared attribution, and observed-at temporal semantics.

Two things separate this family from every source activated before it.

First, the manifest knows something the documents do not. An official pipeline page belongs
to the company whose page it is, and the operator knew that when they wrote the URL down.
Recovering it afterwards from the hostname or the prose discards a declared fact and gets it
wrong wherever a program is co-branded, in-licensed, or arrived with an acquisition that left
the former owner's name on the site.

Second, a pipeline page is not a publication. It states a current condition, is rewritten
without notice, and carries no publication date because it has none. Refusing it for that
makes the tier unreachable; stamping it with its retrieval date is worse, because it would
assert that today's pipeline also held on whatever earlier day the question was asked. So the
page is kept with its publication date genuinely unknown and the moment of observation
recorded as the only thing it can speak to.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from bve.se.acquisition.connectors import DeclaredUrlConnector
from bve.se.acquisition.corpus_store import CorpusStore
from bve.se.acquisition.policy import DeclaredSourceEntry
from bve.se.acquisition.runner import (
    OBSERVED_STATE_FAMILIES,
    _connector_for_entry,
    declared_connectors,
    manifest_digest,
)
from bve.se.discovery.adapters import IndexedDocumentAdapter
from bve.se.schemas.contracts import CompiledQuery, TemporalBasis

PIPELINE = "company_pipeline_or_presentation"
URL = "https://www.example-bio.com/pipeline"
AS_OF = date(2026, 9, 17)
MANIFEST = Path("research/se_benchmarks/company_pipeline/declared_sources.yaml")

UNDATED_PAGE = "<html><body><h1>Pipeline</h1><p>EXB-101 is in Phase 2.</p></body></html>"
DATED_PAGE = (
    '<html><head><meta property="article:published_time" content="2024-03-04"></head>'
    "<body><p>EXB-101 dosed its first patient.</p></body></html>"
)


def _query() -> CompiledQuery:
    return CompiledQuery(query_id="query:test", query="EXB-101", target_ids=[], modality_ids=[])


def _connector(**kwargs) -> DeclaredUrlConnector:
    kwargs.setdefault("fetch_fn", lambda url: UNDATED_PAGE)
    kwargs.setdefault("temporal_basis", TemporalBasis.OBSERVED_AT)
    kwargs.setdefault("companies_by_url", {URL: "Example Bio"})
    return DeclaredUrlConnector(PIPELINE, [URL], **kwargs)


def _acquire(connector: DeclaredUrlConnector, store: CorpusStore) -> None:
    connector.acquire(store, targets=(), modality_terms=(), as_of_date=AS_OF)


class TestCompanyAttributionIsDeclaredNotInferred:
    def test_a_manifest_may_declare_the_company_for_each_url(self) -> None:
        entry = DeclaredSourceEntry.model_validate(
            {
                "source_family": PIPELINE,
                "urls": [{"url": URL, "company": "Example Bio", "role": "pipeline"}],
            }
        )
        assert entry.company_by_url == {URL: "Example Bio"}
        assert entry.urls == (URL,)

    def test_a_bare_url_list_still_loads(self) -> None:
        # Every manifest written before attribution existed must keep working, declaring no
        # company rather than failing or acquiring a guessed one.
        entry = DeclaredSourceEntry.model_validate(
            {"source_family": PIPELINE, "urls": [URL]}
        )
        assert entry.urls == (URL,)
        assert entry.company_by_url == {}

    def test_attribution_survives_acquisition_into_the_corpus(self, tmp_path) -> None:
        store = CorpusStore(tmp_path / "corpus")
        _acquire(_connector(), store)
        assert [doc.declared_company for doc in store.documents()] == ["Example Bio"]

    def test_attribution_survives_into_the_source_index(self, tmp_path) -> None:
        # The index is what replay reads. Attribution that stops at the corpus is attribution
        # no downstream producer can ever see.
        store = CorpusStore(tmp_path / "corpus")
        _acquire(_connector(), store)
        record = store.documents()[0].indexable_record()
        assert record["declared_company"] == "Example Bio"

    def test_an_undeclared_url_is_left_unattributed(self, tmp_path) -> None:
        # Not inferred from the hostname: "example-bio.com" is a guess, and a blank field is
        # an honest statement that the manifest said nothing.
        store = CorpusStore(tmp_path / "corpus")
        _acquire(_connector(companies_by_url={}), store)
        assert store.documents()[0].declared_company == ""


class TestUndatedPagesAreObservedNotPublished:
    def test_an_undated_official_page_is_kept(self, tmp_path) -> None:
        store = CorpusStore(tmp_path / "corpus")
        connector = _connector()
        _acquire(connector, store)
        assert len(store.documents()) == 1
        assert connector.observed_undated == [URL]
        assert connector.withheld_undated == []

    def test_it_is_not_given_a_fabricated_publication_date(self, tmp_path) -> None:
        store = CorpusStore(tmp_path / "corpus")
        _acquire(_connector(), store)
        document = store.documents()[0]
        assert document.publication_date is None
        assert document.temporal_basis is TemporalBasis.OBSERVED_AT
        assert document.indexable_record()["observed_at"] == (
            document.retrieval_date.date().isoformat()
        )

    def test_a_dated_page_stays_a_publication(self, tmp_path) -> None:
        # The family's basis is a fallback for pages with nothing to declare. A page that
        # states its publication date has made the stronger claim, and keeps it.
        store = CorpusStore(tmp_path / "corpus")
        _acquire(_connector(fetch_fn=lambda url: DATED_PAGE), store)
        document = store.documents()[0]
        assert document.publication_date == date(2024, 3, 4)
        assert document.temporal_basis is TemporalBasis.PUBLISHED_AT
        assert "observed_at" not in document.indexable_record()

    def test_a_publishing_family_still_refuses_undated_pages(self, tmp_path) -> None:
        # The global date rule is untouched: only a family that declares itself a view of a
        # current state may keep an undated page.
        store = CorpusStore(tmp_path / "corpus")
        connector = _connector(temporal_basis=TemporalBasis.PUBLISHED_AT)
        _acquire(connector, store)
        assert store.documents() == []
        assert connector.withheld_undated == [URL]


class TestObservedEvidenceCannotAnswerAnEarlierQuestion:
    def _adapter(self, tmp_path, *, observed: str):
        index = [
            {
                "document_id": "doc:pipeline",
                "source_family": PIPELINE,
                "title": URL,
                "text": "EXB-101 is in Phase 2.",
                "temporal_basis": TemporalBasis.OBSERVED_AT.value,
                "observed_at": observed,
            }
        ]
        return IndexedDocumentAdapter(PIPELINE, index)

    def _hits(self, adapter, *, as_of: date):
        return adapter.search(_query(), as_of_date=as_of).hits

    def test_it_answers_a_question_asked_after_it_was_seen(self, tmp_path) -> None:
        adapter = self._adapter(tmp_path, observed="2026-09-01")
        assert self._hits(adapter, as_of=AS_OF)

    def test_it_is_silent_for_a_question_asked_before_it_was_seen(self, tmp_path) -> None:
        # The lookahead this whole distinction exists to prevent: an as-of run in March must
        # not be handed September's pipeline and credited with having found it.
        adapter = self._adapter(tmp_path, observed="2026-09-01")
        assert self._hits(adapter, as_of=date(2026, 3, 1)) == []

    def test_an_observed_record_without_a_timestamp_is_refused(self, tmp_path) -> None:
        # Fail closed: unknown is not known-to-be-earlier, and an observed page whose moment
        # of observation was lost can support nothing at all.
        adapter = self._adapter(tmp_path, observed="")
        assert self._hits(adapter, as_of=AS_OF) == []


class TestSourceFailuresStayVisible:
    def test_a_removed_url_is_an_explicit_failure(self, tmp_path) -> None:
        # A page that 404s must not look like a company with no pipeline. Disappearance and
        # absence are different facts and only one of them is about the science.
        def gone(url: str) -> str:
            raise RuntimeError("404 Not Found")

        store = CorpusStore(tmp_path / "corpus")
        health = _connector(fetch_fn=gone).acquire(
            store, targets=(), modality_terms=(), as_of_date=AS_OF
        )
        assert health.connector_succeeded is False
        assert health.parse_failures == 1
        assert health.error and URL in health.error

    def test_a_redirect_is_recorded(self) -> None:
        # The page still arrives, so nothing looks wrong -- which is exactly why a moved URL
        # would otherwise leave the manifest quietly stale.
        connector = _connector()
        connector._note_redirect(URL, "https://www.example-bio.com/programs")
        assert connector.redirected == {URL: "https://www.example-bio.com/programs"}


class TestTheManifestIsDeclaredAndFrozen:
    def _payload(self) -> dict:
        return yaml.safe_load(MANIFEST.read_text())

    def test_it_declares_a_version_and_hashes_deterministically(self) -> None:
        assert self._payload()["manifest_version"]
        assert manifest_digest(MANIFEST) == manifest_digest(MANIFEST)
        assert len(manifest_digest(MANIFEST)) == 64

    def test_every_declared_url_names_its_company(self) -> None:
        entry = next(
            e
            for e in (
                DeclaredSourceEntry.model_validate(s) for s in self._payload()["sources"]
            )
            if e.source_family == PIPELINE
        )
        assert len(entry.company_by_url) == len(entry.urls)

    def test_selection_is_target_independent(self) -> None:
        # The manifest is infrastructure, not a way of making one benchmark richer. A company
        # chosen for its CD19 or BCMA programs would contaminate the acceptance question the
        # source is about to be measured against.
        text = MANIFEST.read_text().lower()
        for term in ("cd19", "bcma", "car-t", "autoimmune"):
            assert term not in text
        assert self._payload()["selection_rule"]

    def test_the_pipeline_family_acquires_as_observed_state(self) -> None:
        connectors = {c.source_family: c for c in declared_connectors(MANIFEST)}
        assert connectors[PIPELINE].temporal_basis is TemporalBasis.OBSERVED_AT

    def test_a_publishing_family_is_unaffected_by_the_new_basis(self) -> None:
        entry = DeclaredSourceEntry.model_validate(
            {"source_family": "company_press_release", "urls": [URL]}
        )
        assert _connector_for_entry(entry).temporal_basis is TemporalBasis.PUBLISHED_AT
        assert "company_press_release" not in OBSERVED_STATE_FAMILIES


class TestAcquisitionStaysDeclaredOnly:
    def test_only_declared_urls_are_fetched(self, tmp_path) -> None:
        # No open-web crawling: the page below links elsewhere on its own host and the
        # connector must still visit exactly what the manifest listed.
        page = (
            '<html><body><a href="/pipeline/exb-101">EXB-101</a>'
            '<a href="https://elsewhere.example.com/x">x</a></body></html>'
        )
        connector = _connector(fetch_fn=lambda url: page)
        _acquire(connector, CorpusStore(tmp_path / "corpus"))
        assert connector.visited == [URL]

    def test_replay_is_deterministic_and_network_free(self, tmp_path) -> None:
        index = [
            {
                "document_id": "doc:pipeline",
                "source_family": PIPELINE,
                "title": URL,
                "text": "EXB-101 is in Phase 2.",
                "temporal_basis": TemporalBasis.OBSERVED_AT.value,
                "observed_at": "2026-09-01",
                "declared_company": "Example Bio",
            }
        ]
        adapter = IndexedDocumentAdapter(PIPELINE, index)
        # Retrieval timestamps differ between calls by construction; what must not differ is
        # what was found and which document it came from.
        def _stable(hits):
            return [(hit.asset_name, hit.source_document_id, hit.snippet) for hit in hits]

        first = _stable(adapter.search(_query(), as_of_date=AS_OF).hits)
        second = _stable(adapter.search(_query(), as_of_date=AS_OF).hits)
        assert first == second and first
