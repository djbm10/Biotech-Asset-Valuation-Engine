"""
Tests for PubMedConnector (Wave 1C).

All network calls are mocked; no real HTTP traffic.
Covers: XML parsing, topic filter, structured abstract labels,
missing abstract skip, empty drug+indication guard, esearch error handling.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from bve.connectors.pubmed import PubMedConnector, _DEFAULT_TOPIC_KEYWORDS
from bve.intelligence.extraction.raw_document import EntityHints


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hints(drug: str = "TestDrug", indication: str = "cancer") -> EntityHints:
    return EntityHints(
        asset_id="test-asset",
        company_id="test-co",
        drug_name=drug,
        indication=indication,
    )


def _article_xml(
    pmid: str = "12345678",
    title: str = "A clinical trial of TestDrug",
    abstract: str = "This randomized phase 2 trial showed efficacy.",
    year: str = "2023",
    month: str = "Jan",
) -> str:
    return f"""
    <PubmedArticle>
      <MedlineCitation>
        <PMID>{pmid}</PMID>
        <Article>
          <ArticleTitle>{title}</ArticleTitle>
          <Abstract>
            <AbstractText>{abstract}</AbstractText>
          </Abstract>
          <Journal>
            <JournalIssue>
              <PubDate><Year>{year}</Year><Month>{month}</Month></PubDate>
            </JournalIssue>
          </Journal>
        </Article>
      </MedlineCitation>
    </PubmedArticle>"""


def _wrap_articles(*articles: str) -> str:
    return f"<PubmedArticleSet>{''.join(articles)}</PubmedArticleSet>"


def _make_connector(**kwargs) -> PubMedConnector:
    return PubMedConnector(**kwargs)


# ---------------------------------------------------------------------------
# Tests: XML parsing
# ---------------------------------------------------------------------------

class TestXmlParsing:
    def _parse(self, xml: str, keywords=None) -> list:
        connector = _make_connector()
        hints = _hints()
        kw = keywords or _DEFAULT_TOPIC_KEYWORDS
        return connector._parse_xml_abstracts(xml, hints, kw)

    def test_parses_single_article(self):
        xml = _wrap_articles(_article_xml())
        docs = self._parse(xml)
        assert len(docs) == 1
        assert "TestDrug" in docs[0].raw_text or "randomized" in docs[0].raw_text.lower()

    def test_document_source_is_pubmed(self):
        xml = _wrap_articles(_article_xml())
        docs = self._parse(xml)
        assert docs[0].source == "pubmed"

    def test_source_url_contains_pmid(self):
        xml = _wrap_articles(_article_xml(pmid="99887766"))
        docs = self._parse(xml)
        assert "99887766" in docs[0].source_url

    def test_skips_article_with_no_abstract(self):
        xml = """<PubmedArticleSet>
          <PubmedArticle>
            <MedlineCitation>
              <PMID>11111</PMID>
              <Article>
                <ArticleTitle>Title only</ArticleTitle>
              </Article>
            </MedlineCitation>
          </PubmedArticle>
        </PubmedArticleSet>"""
        docs = self._parse(xml, keywords=())
        assert len(docs) == 0

    def test_structured_abstract_labels_preserved(self):
        xml = """<PubmedArticleSet>
          <PubmedArticle>
            <MedlineCitation>
              <PMID>22222</PMID>
              <Article>
                <ArticleTitle>Structured trial</ArticleTitle>
                <Abstract>
                  <AbstractText Label="BACKGROUND">Phase 2 study.</AbstractText>
                  <AbstractText Label="RESULTS">Efficacy observed.</AbstractText>
                </Abstract>
              </Article>
            </MedlineCitation>
          </PubmedArticle>
        </PubmedArticleSet>"""
        docs = self._parse(xml)
        text = docs[0].raw_text
        assert "BACKGROUND" in text
        assert "RESULTS" in text

    def test_multiple_articles_parsed(self):
        xml = _wrap_articles(
            _article_xml(pmid="111", abstract="randomized efficacy study"),
            _article_xml(pmid="222", abstract="phase 3 clinical trial"),
        )
        docs = self._parse(xml)
        assert len(docs) == 2

    def test_malformed_xml_returns_empty(self):
        docs = self._parse("<not valid xml <<<", keywords=())
        assert docs == []


# ---------------------------------------------------------------------------
# Tests: topic filter
# ---------------------------------------------------------------------------

class TestTopicFilter:
    def test_passes_article_with_keyword(self):
        connector = _make_connector()
        xml = _wrap_articles(_article_xml(abstract="This is a randomized controlled trial."))
        docs = connector._parse_xml_abstracts(xml, _hints(), ("randomized",))
        assert len(docs) == 1

    def test_blocks_article_without_keyword(self):
        connector = _make_connector()
        xml = _wrap_articles(_article_xml(
            title="Mechanistic study in mice",
            abstract="Basic science preclinical mouse study only.",
        ))
        docs = connector._parse_xml_abstracts(xml, _hints(), ("clinical trial", "phase"))
        assert len(docs) == 0

    def test_empty_keywords_passes_all(self):
        connector = _make_connector()
        xml = _wrap_articles(_article_xml(abstract="Any text at all."))
        docs = connector._parse_xml_abstracts(xml, _hints(), ())
        assert len(docs) == 1

    def test_keyword_match_case_insensitive(self):
        connector = _make_connector()
        xml = _wrap_articles(_article_xml(abstract="RANDOMIZED trial."))
        docs = connector._parse_xml_abstracts(xml, _hints(), ("randomized",))
        assert len(docs) == 1


# ---------------------------------------------------------------------------
# Tests: fetch() — mocked HTTP
# ---------------------------------------------------------------------------

class TestFetch:
    @staticmethod
    def _mock_esearch(pmids: list[str]):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"esearchresult": {"idlist": pmids}}
        return resp

    @staticmethod
    def _mock_efetch(xml: str):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.text = xml
        return resp

    @staticmethod
    def _mock_429():
        import requests as _req
        resp = MagicMock()
        resp.status_code = 429
        resp.raise_for_status.side_effect = _req.HTTPError("429 Too Many Requests")
        return resp

    def test_returns_empty_when_no_drug_or_indication(self):
        connector = _make_connector()
        empty_hints = EntityHints(asset_id="x", company_id="y")
        result = connector.fetch(empty_hints)
        assert len(result.documents) == 0
        assert result.fetch_errors

    @patch("bve.connectors.pubmed.time.sleep")
    @patch("bve.connectors.pubmed.requests.get")
    def test_fetch_calls_esearch_then_efetch(self, mock_get, mock_sleep):
        xml = _wrap_articles(_article_xml(abstract="phase 2 randomized trial"))
        mock_get.side_effect = [
            self._mock_esearch(["12345"]),
            self._mock_efetch(xml),
        ]
        connector = _make_connector()
        result = connector.fetch(_hints(), limit=10)
        assert len(result.documents) == 1
        assert not result.fetch_errors

    @patch("bve.connectors.pubmed.time.sleep")
    @patch("bve.connectors.pubmed.requests.get")
    def test_empty_esearch_result_returns_no_docs(self, mock_get, mock_sleep):
        mock_get.return_value = self._mock_esearch([])
        connector = _make_connector()
        result = connector.fetch(_hints())
        assert len(result.documents) == 0

    @patch("bve.connectors.pubmed.time.sleep")
    @patch("bve.connectors.pubmed.requests.get")
    def test_esearch_network_error_collected(self, mock_get, mock_sleep):
        mock_get.side_effect = Exception("connection refused")
        connector = _make_connector()
        result = connector.fetch(_hints())
        assert any("esearch" in e.lower() for e in result.fetch_errors)

    @patch("bve.connectors.pubmed.time.sleep")
    @patch("bve.connectors.pubmed.requests.get")
    def test_limit_respected(self, mock_get, mock_sleep):
        # esearch returns 3 PMIDs; all 3 articles match filter; limit=2
        pmids = ["1", "2", "3"]
        articles = [_article_xml(pmid=p, abstract="phase 2 randomized") for p in pmids]
        xml = _wrap_articles(*articles)
        mock_get.side_effect = [
            self._mock_esearch(pmids),
            self._mock_efetch(xml),
        ]
        connector = _make_connector()
        result = connector.fetch(_hints(), limit=2)
        assert len(result.documents) == 2

    @patch("bve.connectors.pubmed.time.sleep")
    @patch("bve.connectors.pubmed.requests.get")
    def test_429_retried_then_succeeds(self, mock_get, mock_sleep):
        # First call returns 429; second returns success
        xml = _wrap_articles(_article_xml(abstract="phase 2 trial"))
        mock_get.side_effect = [
            self._mock_429(),           # esearch → 429
            self._mock_esearch(["1"]),  # esearch retry → success
            self._mock_efetch(xml),     # efetch → success
        ]
        connector = _make_connector()
        result = connector.fetch(_hints(), limit=5)
        assert len(result.documents) == 1
        # Sleep was called at least once for the 429 backoff
        assert mock_sleep.call_count >= 1

    @patch("bve.connectors.pubmed.time.sleep")
    @patch("bve.connectors.pubmed.requests.get")
    def test_429_all_retries_exhausted_collected_as_error(self, mock_get, mock_sleep):
        # All calls return 429 until retries exhausted
        from bve.connectors.pubmed import _MAX_RETRIES
        mock_get.side_effect = [self._mock_429()] * (_MAX_RETRIES + 2)
        connector = _make_connector()
        result = connector.fetch(_hints())
        # No documents; error captured
        assert len(result.documents) == 0
        assert result.fetch_errors
