"""
Tests for the data ingestion layer (Step 1).

All tests are offline — external calls are mocked.
Covers:
- RawEvent schema validation and checksum computation
- Deduplication key stability
- Parser correctness for each client
- Retry / timeout handling
- Schema validation (required fields present)
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bve.ingestion.raw_event import RawEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_event(**kwargs: Any) -> RawEvent:
    defaults: dict[str, Any] = {
        "source": "test_source",
        "record_type": "test_record",
        "source_url": "https://example.com/data",
        "payload": {"key": "value", "number": 42},
    }
    defaults.update(kwargs)
    return RawEvent(**defaults)


# ---------------------------------------------------------------------------
# RawEvent schema tests
# ---------------------------------------------------------------------------


class TestRawEvent:
    def test_required_fields_present(self):
        event = _make_event()
        assert event.source == "test_source"
        assert event.record_type == "test_record"
        assert event.source_url == "https://example.com/data"
        assert isinstance(event.payload, dict)
        assert isinstance(event.fetched_at, datetime)
        assert isinstance(event.checksum, str)
        assert len(event.checksum) == 64  # SHA-256 hex

    def test_checksum_computed_automatically(self):
        event = _make_event(payload={"a": 1, "b": 2})
        expected = hashlib.sha256(
            json.dumps({"a": 1, "b": 2}, sort_keys=True, default=str).encode()
        ).hexdigest()
        assert event.checksum == expected

    def test_checksum_is_deterministic(self):
        e1 = _make_event(payload={"x": 10, "y": 20})
        e2 = _make_event(payload={"y": 20, "x": 10})  # different insertion order
        assert e1.checksum == e2.checksum

    def test_different_payloads_different_checksums(self):
        e1 = _make_event(payload={"a": 1})
        e2 = _make_event(payload={"a": 2})
        assert e1.checksum != e2.checksum

    def test_dedup_key_format(self):
        event = _make_event(source="sec_edgar", record_type="10_k")
        key = event.dedup_key()
        assert key.startswith("sec_edgar:10_k:")
        assert len(key.split(":")) == 3
        assert len(key.split(":")[2]) == 64  # checksum part

    def test_dedup_key_stable_across_instances(self):
        e1 = _make_event(payload={"same": "data"})
        e2 = _make_event(payload={"same": "data"})
        assert e1.dedup_key() == e2.dedup_key()

    def test_entity_ids_defaults_empty(self):
        event = _make_event()
        assert event.entity_ids == []

    def test_entity_ids_stored(self):
        event = _make_event(entity_ids=["asset-123", "company-456"])
        assert "asset-123" in event.entity_ids
        assert "company-456" in event.entity_ids

    def test_fetched_at_is_utc(self):
        event = _make_event()
        assert event.fetched_at.tzinfo is not None

    def test_frozen_model_immutable(self):
        event = _make_event()
        with pytest.raises(Exception):
            event.source = "mutated"  # type: ignore[misc]

    def test_explicit_checksum_preserved(self):
        custom_checksum = "a" * 64
        event = RawEvent(
            source="s",
            record_type="r",
            source_url="https://x.com",
            payload={"k": "v"},
            checksum=custom_checksum,
        )
        assert event.checksum == custom_checksum

    def test_nested_payload_supported(self):
        nested = {"level1": {"level2": [1, 2, 3]}, "flag": True}
        event = _make_event(payload=nested)
        assert event.payload["level1"]["level2"] == [1, 2, 3]
        assert len(event.checksum) == 64


# ---------------------------------------------------------------------------
# SEC client tests
# ---------------------------------------------------------------------------


class TestSecClient:
    def _mock_company_tickers(self) -> dict:
        return {
            "0": {"cik_str": 12345, "ticker": "VKTX", "title": "Viking Therapeutics"},
        }

    def _mock_submissions(self) -> dict:
        return {
            "filings": {
                "recent": {
                    "form": ["10-K", "8-K", "10-Q"],
                    "accessionNumber": [
                        "0001234567-24-000001",
                        "0001234567-24-000002",
                        "0001234567-24-000003",
                    ],
                    "filingDate": ["2024-03-01", "2024-02-15", "2024-05-10"],
                    "primaryDocument": ["annual.htm", "press.htm", "quarterly.htm"],
                }
            }
        }

    def _mock_company_facts(self) -> dict:
        return {
            "entityName": "Viking Therapeutics",
            "facts": {
                "us-gaap": {
                    "CashAndCashEquivalentsAtCarryingValue": {
                        "units": {
                            "USD": [
                                {
                                    "end": "2024-12-31",
                                    "val": 500_000_000,
                                    "form": "10-K",
                                }
                            ]
                        }
                    },
                    "ResearchAndDevelopmentExpense": {
                        "units": {
                            "USD": [
                                {
                                    "end": "2024-12-31",
                                    "val": 120_000_000,
                                    "form": "10-K",
                                }
                            ]
                        }
                    },
                    "CommonStockSharesOutstanding": {
                        "units": {
                            "shares": [
                                {
                                    "end": "2024-12-31",
                                    "val": 85_000_000,
                                    "form": "10-K",
                                }
                            ]
                        }
                    },
                }
            },
        }

    @patch("bve.ingestion.sec_client._get")
    def test_fetch_recent_filings_returns_raw_events(self, mock_get):
        mock_get.side_effect = [
            self._mock_company_tickers(),
            self._mock_submissions(),
        ]
        from bve.ingestion.sec_client import fetch_recent_filings

        events = fetch_recent_filings("VKTX", form_types=["10-K", "8-K"], limit=5)
        assert len(events) == 2  # 10-K and 8-K only
        for ev in events:
            assert ev.source == "sec_edgar"
            assert ev.record_type in ("10_k", "8_k")
            assert "ticker" in ev.payload
            assert ev.payload["ticker"] == "VKTX"
            assert ev.source_url.startswith("https://")
            assert len(ev.checksum) == 64

    @patch("bve.ingestion.sec_client._resolve_cik", return_value="0000012345")
    @patch("bve.ingestion.sec_client._get")
    def test_fetch_cash_burn_extracts_values(self, mock_get, mock_cik):
        # _resolve_cik is mocked so _get is only called once (for company facts)
        mock_get.return_value = self._mock_company_facts()
        from bve.ingestion.sec_client import fetch_cash_and_burn

        events = fetch_cash_and_burn("VKTX")
        assert len(events) == 1
        ev = events[0]
        assert ev.record_type == "cash_burn_snapshot"
        assert ev.payload["cash_usd"] == 500_000_000
        assert ev.payload["rd_expense_usd"] == 120_000_000
        assert ev.payload["shares_outstanding"] == 85_000_000

    @patch("bve.ingestion.sec_client._get")
    def test_fetch_returns_empty_on_unknown_ticker(self, mock_get):
        mock_get.return_value = {}
        from bve.ingestion.sec_client import fetch_recent_filings

        events = fetch_recent_filings("ZZZZZ")
        assert events == []

    @patch("bve.ingestion.sec_client._resolve_cik", return_value="0000012345")
    @patch("bve.ingestion.sec_client._get")
    def test_entity_ids_propagated(self, mock_get, mock_cik):
        mock_get.return_value = self._mock_submissions()
        from bve.ingestion.sec_client import fetch_recent_filings

        events = fetch_recent_filings("VKTX", form_types=["10-K"], limit=5)
        assert len(events) == 1
        assert events[0].payload["ticker"] == "VKTX"

    def test_dedup_on_same_filing(self):
        e1 = RawEvent(
            source="sec_edgar",
            record_type="10_k",
            source_url="https://sec.gov/x",
            payload={"form_type": "10-K", "accession_number": "abc123"},
        )
        e2 = RawEvent(
            source="sec_edgar",
            record_type="10_k",
            source_url="https://sec.gov/x",
            payload={"form_type": "10-K", "accession_number": "abc123"},
        )
        assert e1.dedup_key() == e2.dedup_key()

    def test_dedup_differs_on_different_accession(self):
        e1 = RawEvent(
            source="sec_edgar",
            record_type="10_k",
            source_url="https://sec.gov/x",
            payload={"accession_number": "abc123"},
        )
        e2 = RawEvent(
            source="sec_edgar",
            record_type="10_k",
            source_url="https://sec.gov/x",
            payload={"accession_number": "xyz999"},
        )
        assert e1.dedup_key() != e2.dedup_key()


# ---------------------------------------------------------------------------
# CT.gov client tests
# ---------------------------------------------------------------------------


class TestCtgovClient:
    def _mock_study(self, nct_id: str = "NCT12345678") -> dict:
        return {
            "protocolSection": {
                "identificationModule": {
                    "nctId": nct_id,
                    "briefTitle": "A Phase 2 Study of Drug X",
                    "officialTitle": "Randomized Phase 2 Study",
                },
                "statusModule": {
                    "overallStatus": "RECRUITING",
                    "startDateStruct": {"date": "2023-01-15"},
                    "primaryCompletionDateStruct": {"date": "2025-06-30"},
                    "completionDateStruct": {"date": "2025-12-31"},
                },
                "designModule": {
                    "phases": ["PHASE2"],
                    "enrollmentInfo": {"count": 120},
                    "designInfo": {
                        "allocation": "RANDOMIZED",
                        "interventionModel": "PARALLEL",
                        "maskingInfo": {"masking": "DOUBLE"},
                    },
                },
                "armsInterventionsModule": {
                    "armGroups": [
                        {
                            "label": "Drug X",
                            "type": "EXPERIMENTAL",
                            "description": "10 mg QD",
                        },
                        {
                            "label": "Placebo",
                            "type": "PLACEBO_COMPARATOR",
                            "description": "matching placebo",
                        },
                    ]
                },
                "outcomesModule": {
                    "primaryOutcomes": [
                        {"measure": "Overall Response Rate", "timeFrame": "Week 24"}
                    ],
                    "secondaryOutcomes": [
                        {"measure": "PFS", "timeFrame": "Week 52"},
                    ],
                },
                "eligibilityModule": {
                    "eligibilityCriteria": "Inclusion: adults 18+",
                    "minimumAge": "18 Years",
                    "maximumAge": "N/A",
                },
                "contactsLocationsModule": {
                    "locations": [{"city": "Boston"}, {"city": "New York"}]
                },
            }
        }

    @patch("bve.ingestion.ctgov_client._get")
    def test_fetch_trial_returns_raw_event(self, mock_get):
        mock_get.return_value = self._mock_study()
        from bve.ingestion.ctgov_client import fetch_trial

        events = fetch_trial("NCT12345678")
        assert len(events) == 1
        ev = events[0]
        assert ev.source == "ctgov"
        assert ev.record_type == "trial_study"
        assert ev.payload["nct_id"] == "NCT12345678"
        assert ev.payload["status"] == "RECRUITING"
        assert ev.payload["phases"] == ["PHASE2"]
        assert ev.payload["enrollment"] == 120
        assert ev.payload["n_sites"] == 2
        assert len(ev.checksum) == 64

    @patch("bve.ingestion.ctgov_client._get")
    def test_fetch_trial_arms_normalized(self, mock_get):
        mock_get.return_value = self._mock_study()
        from bve.ingestion.ctgov_client import fetch_trial

        events = fetch_trial("NCT12345678")
        arms = events[0].payload["arms"]
        assert len(arms) == 2
        assert arms[0]["label"] == "Drug X"
        assert arms[1]["type"] == "PLACEBO_COMPARATOR"

    @patch("bve.ingestion.ctgov_client._get")
    def test_fetch_trial_outcomes_normalized(self, mock_get):
        mock_get.return_value = self._mock_study()
        from bve.ingestion.ctgov_client import fetch_trial

        events = fetch_trial("NCT12345678")
        primary = events[0].payload["primary_outcomes"]
        assert len(primary) == 1
        assert primary[0]["measure"] == "Overall Response Rate"

    @patch("bve.ingestion.ctgov_client._get")
    def test_search_trials_returns_events(self, mock_get):
        mock_get.return_value = {
            "studies": [self._mock_study("NCT11111111"), self._mock_study("NCT22222222")]
        }
        from bve.ingestion.ctgov_client import search_trials

        events = search_trials(drug_name="DrugX", limit=5)
        assert len(events) == 2
        assert all(ev.source == "ctgov" for ev in events)
        assert all(ev.record_type == "trial_study" for ev in events)

    @patch("bve.ingestion.ctgov_client._get")
    def test_returns_empty_on_empty_api_response(self, mock_get):
        mock_get.return_value = {}
        from bve.ingestion.ctgov_client import fetch_trial

        events = fetch_trial("NCT00000000")
        assert events == []

    def test_dedup_same_trial_same_data(self):
        payload = {"nct_id": "NCT12345678", "status": "RECRUITING"}
        e1 = RawEvent(
            source="ctgov",
            record_type="trial_study",
            source_url="https://clinicaltrials.gov/api/v2/studies/NCT12345678",
            payload=payload,
        )
        e2 = RawEvent(
            source="ctgov",
            record_type="trial_study",
            source_url="https://clinicaltrials.gov/api/v2/studies/NCT12345678",
            payload=payload,
        )
        assert e1.dedup_key() == e2.dedup_key()

    def test_dedup_differs_on_status_change(self):
        e1 = RawEvent(
            source="ctgov",
            record_type="trial_study",
            source_url="https://clinicaltrials.gov",
            payload={"nct_id": "NCT12345678", "status": "RECRUITING"},
        )
        e2 = RawEvent(
            source="ctgov",
            record_type="trial_study",
            source_url="https://clinicaltrials.gov",
            payload={"nct_id": "NCT12345678", "status": "COMPLETED"},
        )
        assert e1.dedup_key() != e2.dedup_key()


# ---------------------------------------------------------------------------
# FDA client tests
# ---------------------------------------------------------------------------


class TestFdaClient:
    def _mock_nda_result(self) -> dict:
        return {
            "results": [
                {
                    "application_number": "NDA212608",
                    "sponsor_name": "Example Pharma",
                    "products": [
                        {
                            "brand_name": "ExampleDrug",
                            "active_ingredients": [{"name": "examplimod"}],
                            "dosage_form": "TABLET",
                            "route": "ORAL",
                            "marketing_status": "Prescription",
                        }
                    ],
                    "submissions": [
                        {
                            "submission_type": "ORIG",
                            "submission_number": "001",
                            "submission_status": "AP",
                            "submission_status_date": "20231015",
                            "submission_class_code_description": "Type 1 - New Molecular Entity",
                        }
                    ],
                    "openfda": {"brand_name": ["ExampleDrug"]},
                }
            ]
        }

    @patch("bve.ingestion.fda_client._get")
    def test_fetch_approvals_returns_event(self, mock_get):
        mock_get.return_value = self._mock_nda_result()
        from bve.ingestion.fda_client import fetch_approvals

        events = fetch_approvals("ExampleDrug")
        assert len(events) == 1
        ev = events[0]
        assert ev.source == "openfda"
        assert ev.record_type == "drug_approval"
        assert ev.payload["application_number"] == "NDA212608"
        assert ev.payload["sponsor_name"] == "Example Pharma"
        assert len(ev.checksum) == 64

    @patch("bve.ingestion.fda_client._get")
    def test_fetch_approvals_products_normalized(self, mock_get):
        mock_get.return_value = self._mock_nda_result()
        from bve.ingestion.fda_client import fetch_approvals

        events = fetch_approvals("ExampleDrug")
        products = events[0].payload["products"]
        assert len(products) == 1
        assert products[0]["brand_name"] == "ExampleDrug"
        assert products[0]["dosage_form"] == "TABLET"

    @patch("bve.ingestion.fda_client._get")
    def test_fetch_approvals_empty_returns_empty(self, mock_get):
        mock_get.return_value = {"results": []}
        from bve.ingestion.fda_client import fetch_approvals

        events = fetch_approvals("UnknownDrug")
        assert events == []

    @patch("bve.ingestion.fda_client._get")
    def test_fetch_adverse_events(self, mock_get):
        mock_get.return_value = {
            "results": [
                {"term": "NAUSEA", "count": 500},
                {"term": "HEADACHE", "count": 200},
            ]
        }
        from bve.ingestion.fda_client import fetch_adverse_events

        events = fetch_adverse_events("ExampleDrug")
        assert len(events) == 1
        ev = events[0]
        assert ev.record_type == "adverse_event_summary"
        assert ev.payload["total_reactions"] == 700
        assert len(ev.payload["reaction_counts"]) == 2

    @patch("bve.ingestion.fda_client._get")
    def test_fetch_drug_label(self, mock_get):
        mock_get.return_value = {
            "results": [
                {
                    "indications_and_usage": ["For treatment of X"],
                    "warnings_and_cautions": ["May cause Y"],
                    "boxed_warning": [],
                    "dosage_and_administration": ["10 mg once daily"],
                    "contraindications": [],
                    "openfda": {"brand_name": ["ExampleDrug"]},
                }
            ]
        }
        from bve.ingestion.fda_client import fetch_drug_label

        events = fetch_drug_label("ExampleDrug")
        assert len(events) == 1
        ev = events[0]
        assert ev.record_type == "drug_label"
        assert "For treatment of X" in ev.payload["indications_and_usage"]

    def test_dedup_same_approval(self):
        payload = {"application_number": "NDA212608", "sponsor_name": "Pharma Co"}
        e1 = RawEvent(
            source="openfda",
            record_type="drug_approval",
            source_url="https://api.fda.gov/drug/nda.json",
            payload=payload,
        )
        e2 = RawEvent(
            source="openfda",
            record_type="drug_approval",
            source_url="https://api.fda.gov/drug/nda.json",
            payload=payload,
        )
        assert e1.dedup_key() == e2.dedup_key()


# ---------------------------------------------------------------------------
# PubMed client tests
# ---------------------------------------------------------------------------


class TestPubmedClient:
    _SAMPLE_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>38000001</PMID>
      <Article>
        <ArticleTitle>Phase 2 trial of examplimod in Type 2 diabetes</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Examplimod is a GLP-1 RA.</AbstractText>
          <AbstractText Label="RESULTS">Mean HbA1c reduction was -1.5%.</AbstractText>
        </Abstract>
        <Journal>
          <Title>New England Journal of Medicine</Title>
          <JournalIssue>
            <PubDate><Year>2024</Year></PubDate>
          </JournalIssue>
        </Journal>
        <AuthorList>
          <Author>
            <LastName>Smith</LastName>
            <ForeName>Jane</ForeName>
          </Author>
        </AuthorList>
      </Article>
      <MeshHeadingList>
        <MeshHeading>
          <DescriptorName>Diabetes Mellitus, Type 2</DescriptorName>
        </MeshHeading>
      </MeshHeadingList>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""

    def test_parse_articles_from_xml(self):
        from bve.ingestion.pubmed_client import _parse_articles

        articles = _parse_articles(self._SAMPLE_XML)
        assert len(articles) == 1
        art = articles[0]
        assert art["pmid"] == "38000001"
        assert "examplimod" in art["title"].lower()
        assert "HbA1c" in art["abstract"]
        assert art["journal"] == "New England Journal of Medicine"
        assert art["pub_year"] == "2024"
        assert art["authors"] == ["Jane Smith"]
        assert "Diabetes Mellitus, Type 2" in art["mesh_terms"]

    def test_parse_articles_empty_xml(self):
        from bve.ingestion.pubmed_client import _parse_articles

        assert _parse_articles("") == []

    def test_parse_articles_malformed_xml(self):
        from bve.ingestion.pubmed_client import _parse_articles

        assert _parse_articles("<broken>") == []

    @patch("bve.ingestion.pubmed_client._get_text")
    def test_search_and_fetch_returns_events(self, mock_get):
        import json

        search_json = json.dumps(
            {
                "esearchresult": {
                    "idlist": ["38000001"],
                    "webenv": "WENV",
                    "querykey": "1",
                }
            }
        )
        mock_get.side_effect = [search_json, self._SAMPLE_XML]
        from bve.ingestion.pubmed_client import search_and_fetch

        events = search_and_fetch("examplimod diabetes")
        assert len(events) == 1
        ev = events[0]
        assert ev.source == "pubmed"
        assert ev.record_type == "pubmed_abstract"
        assert ev.payload["pmid"] == "38000001"
        assert ev.source_url == "https://pubmed.ncbi.nlm.nih.gov/38000001/"

    @patch("bve.ingestion.pubmed_client._get_text")
    def test_search_returns_empty_on_no_results(self, mock_get):
        import json

        mock_get.return_value = json.dumps(
            {"esearchresult": {"idlist": [], "webenv": "", "querykey": ""}}
        )
        from bve.ingestion.pubmed_client import search_and_fetch

        events = search_and_fetch("zzz_nonexistent_drug_zzz")
        assert events == []

    def test_pubmed_event_checksum_stable(self):
        payload = {"pmid": "38000001", "title": "A trial", "abstract": "Results."}
        e1 = RawEvent(
            source="pubmed",
            record_type="pubmed_abstract",
            source_url="https://pubmed.ncbi.nlm.nih.gov/38000001/",
            payload=payload,
        )
        e2 = RawEvent(
            source="pubmed",
            record_type="pubmed_abstract",
            source_url="https://pubmed.ncbi.nlm.nih.gov/38000001/",
            payload=payload,
        )
        assert e1.dedup_key() == e2.dedup_key()


# ---------------------------------------------------------------------------
# News client tests
# ---------------------------------------------------------------------------


class TestNewsClient:
    _SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>BioSpace</title>
    <item>
      <title>VKTX Reports Positive Phase 2 Data</title>
      <link>https://biospace.com/article/vktx-phase2</link>
      <description>Viking Therapeutics VKTX announced positive results...</description>
      <pubDate>Mon, 15 Apr 2024 09:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Other Company News</title>
      <link>https://biospace.com/article/other</link>
      <description>Some other company announced...</description>
      <pubDate>Mon, 15 Apr 2024 08:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""

    def test_parse_rss_extracts_items(self):
        from bve.ingestion.news_client import _parse_rss

        items = _parse_rss(self._SAMPLE_RSS)
        assert len(items) == 2
        assert "VKTX" in items[0]["title"]
        assert items[0]["url"] == "https://biospace.com/article/vktx-phase2"

    def test_parse_rss_empty(self):
        from bve.ingestion.news_client import _parse_rss

        assert _parse_rss("") == []

    def test_parse_rss_malformed(self):
        from bve.ingestion.news_client import _parse_rss

        assert _parse_rss("<broken>") == []

    @patch("bve.ingestion.news_client._get_text")
    def test_fetch_biospace_filters_by_ticker(self, mock_get):
        mock_get.return_value = self._SAMPLE_RSS
        from bve.ingestion.news_client import fetch_biospace_news

        events = fetch_biospace_news("VKTX")
        # Only the VKTX item should be returned
        assert len(events) == 1
        ev = events[0]
        assert ev.source == "news"
        assert ev.record_type == "news_article"
        assert ev.payload["ticker"] == "VKTX"
        assert "VKTX" in ev.payload["title"]

    @patch("bve.ingestion.news_client._get_text")
    def test_fetch_biospace_no_match_returns_empty(self, mock_get):
        mock_get.return_value = self._SAMPLE_RSS
        from bve.ingestion.news_client import fetch_biospace_news

        events = fetch_biospace_news("AAPL")
        assert events == []

    @patch("bve.ingestion.news_client._get_json")
    def test_fetch_sec_press_releases(self, mock_get):
        mock_get.return_value = {
            "hits": {
                "hits": [
                    {
                        "_id": "/Archives/edgar/data/1234/press.htm",
                        "_source": {
                            "form_type": "8-K",
                            "file_date": "2024-03-15",
                            "entity_name": "Viking Therapeutics",
                            "period_of_report": "2024-03-15",
                        },
                    }
                ]
            }
        }
        from bve.ingestion.news_client import fetch_sec_press_releases

        events = fetch_sec_press_releases("VKTX")
        assert len(events) == 1
        ev = events[0]
        assert ev.source == "news"
        assert ev.record_type == "press_release"
        assert ev.payload["ticker"] == "VKTX"

    def test_news_event_dedup_stability(self):
        payload = {
            "ticker": "VKTX",
            "title": "Phase 2 Results",
            "url": "https://biospace.com/1",
        }
        e1 = RawEvent(
            source="news",
            record_type="news_article",
            source_url="https://biospace.com/1",
            payload=payload,
        )
        e2 = RawEvent(
            source="news",
            record_type="news_article",
            source_url="https://biospace.com/1",
            payload=payload,
        )
        assert e1.dedup_key() == e2.dedup_key()


# ---------------------------------------------------------------------------
# Market data client tests
# ---------------------------------------------------------------------------


class TestMarketDataClient:
    def _mock_fast_info(self) -> MagicMock:
        fi = MagicMock()
        fi.last_price = 42.50
        fi.market_cap = 5_000_000_000.0
        fi.shares = 117_000_000.0
        fi.currency = "USD"
        return fi

    def _mock_info(self) -> dict:
        return {
            "enterpriseValue": 4_800_000_000,
            "marketCap": 5_000_000_000,
            "totalCash": 600_000_000,
            "totalDebt": 0,
            "sharesOutstanding": 117_000_000,
            "floatShares": 110_000_000,
            "bookValue": 3.50,
            "priceToBook": 12.1,
            "beta": 1.8,
            "fiftyTwoWeekHigh": 85.0,
            "fiftyTwoWeekLow": 20.0,
            "averageVolume10days": 5_000_000,
            "totalRevenue": None,
            "grossProfits": None,
            "operatingCashflow": -200_000_000,
            "freeCashflow": -200_000_000,
            "currency": "USD",
            "sector": "Healthcare",
            "industry": "Biotechnology",
            "shortName": "Viking Therapeutics",
        }

    @patch("yfinance.Ticker")
    def test_fetch_price_snapshot(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.fast_info = self._mock_fast_info()
        mock_ticker_cls.return_value = mock_ticker

        from bve.ingestion.market_data_client import fetch_price_snapshot

        events = fetch_price_snapshot("VKTX")
        assert len(events) == 1
        ev = events[0]
        assert ev.source == "market_data"
        assert ev.record_type == "price_snapshot"
        assert ev.payload["ticker"] == "VKTX"
        assert ev.payload["last_price"] == 42.50
        assert ev.payload["market_cap_usd"] == 5_000_000_000.0

    @patch("yfinance.Ticker")
    def test_fetch_fundamentals(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = self._mock_info()
        mock_ticker_cls.return_value = mock_ticker

        from bve.ingestion.market_data_client import fetch_fundamentals

        events = fetch_fundamentals("VKTX")
        assert len(events) == 1
        ev = events[0]
        assert ev.record_type == "fundamentals_snapshot"
        assert ev.payload["market_cap_usd"] == 5_000_000_000
        assert ev.payload["total_cash_usd"] == 600_000_000
        assert ev.payload["sector"] == "Healthcare"

    @patch("yfinance.Ticker")
    def test_fetch_ev_snapshot_computes_correctly(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = self._mock_info()
        mock_ticker_cls.return_value = mock_ticker

        from bve.ingestion.market_data_client import fetch_ev_snapshot

        events = fetch_ev_snapshot("VKTX")
        assert len(events) == 1
        ev = events[0]
        assert ev.record_type == "ev_snapshot"
        # ev_computed = 5B + 0 - 600M = 4.4B
        assert ev.payload["ev_computed_usd"] == pytest.approx(4_400_000_000, rel=1e-3)
        assert ev.payload["net_cash_usd"] == 600_000_000

    @patch("yfinance.download")
    def test_fetch_price_history(self, mock_download):
        import pandas as pd

        df = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "Open": [40.0, 41.0],
                "High": [42.0, 43.0],
                "Low": [39.0, 40.0],
                "Close": [41.5, 42.0],
                "Volume": [3_000_000, 2_500_000],
            }
        ).set_index("Date")
        mock_download.return_value = df

        from bve.ingestion.market_data_client import fetch_price_history

        events = fetch_price_history("VKTX", start="2024-01-01", end="2024-01-31")
        assert len(events) == 1
        ev = events[0]
        assert ev.record_type == "price_history"
        assert ev.payload["ticker"] == "VKTX"
        assert ev.payload["n_bars"] == 2
        bars = ev.payload["bars"]
        assert bars[0]["close"] == 41.5

    @patch("yfinance.download")
    def test_fetch_price_history_empty_returns_empty(self, mock_download):
        import pandas as pd

        mock_download.return_value = pd.DataFrame()
        from bve.ingestion.market_data_client import fetch_price_history

        events = fetch_price_history("ZZZZZ")
        assert events == []

    def test_market_data_event_schema_complete(self):
        payload = {
            "ticker": "VKTX",
            "last_price": 42.50,
            "market_cap_usd": 5_000_000_000,
            "shares_outstanding": 117_000_000,
        }
        ev = RawEvent(
            source="market_data",
            record_type="price_snapshot",
            source_url="https://finance.yahoo.com/quote/VKTX",
            payload=payload,
        )
        assert ev.source == "market_data"
        assert len(ev.checksum) == 64


# ---------------------------------------------------------------------------
# Open Payments client tests
# ---------------------------------------------------------------------------


class TestOpenPaymentsClient:
    def _mock_cms_response(self) -> list:
        return [
            {
                "Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Name": "Pharma Co",
                "Total_Amount_of_Payment_USDollars": "15000.00",
                "Nature_of_Payment_or_Transfer_of_Value": "Consulting Fee",
                "Covered_Recipient_First_Name": "John",
                "Covered_Recipient_Last_Name": "Doe",
                "Covered_Recipient_Primary_Type_1": "Medical Doctor",
                "Program_Year": "2022",
                "Recipient_City": "Boston",
                "Recipient_State": "MA",
            },
            {
                "Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Name": "Pharma Co",
                "Total_Amount_of_Payment_USDollars": "8000.50",
                "Nature_of_Payment_or_Transfer_of_Value": "Honoraria",
                "Covered_Recipient_First_Name": "Jane",
                "Covered_Recipient_Last_Name": "Smith",
                "Covered_Recipient_Primary_Type_1": "Medical Doctor",
                "Program_Year": "2022",
                "Recipient_City": "New York",
                "Recipient_State": "NY",
            },
        ]

    @patch("bve.ingestion.openpayments_client._get")
    def test_fetch_general_payments_returns_event(self, mock_get):
        mock_get.return_value = self._mock_cms_response()
        from bve.ingestion.openpayments_client import fetch_general_payments

        events = fetch_general_payments("Pharma Co", year=2022)
        assert len(events) == 1
        ev = events[0]
        assert ev.source == "open_payments"
        assert ev.record_type == "open_payments_general"
        assert ev.payload["company_name"] == "Pharma Co"
        assert ev.payload["total_amount_usd"] == pytest.approx(23000.50, rel=1e-3)
        assert ev.payload["record_count"] == 2
        assert "Consulting Fee" in ev.payload["by_payment_type"]

    @patch("bve.ingestion.openpayments_client._get")
    def test_fetch_general_payments_top_recipients(self, mock_get):
        mock_get.return_value = self._mock_cms_response()
        from bve.ingestion.openpayments_client import fetch_general_payments

        events = fetch_general_payments("Pharma Co")
        recipients = events[0].payload["top_recipients"]
        # Sorted by amount descending — John Doe ($15k) should be first
        assert recipients[0]["name"] == "John Doe"
        assert recipients[0]["amount"] == 15000.0

    @patch("bve.ingestion.openpayments_client._get")
    def test_fetch_general_payments_empty_returns_empty(self, mock_get):
        mock_get.return_value = []
        from bve.ingestion.openpayments_client import fetch_general_payments

        events = fetch_general_payments("Unknown Corp")
        assert events == []

    @patch("bve.ingestion.openpayments_client._get")
    def test_fetch_research_payments(self, mock_get):
        mock_get.return_value = [
            {
                "Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Name": "Pharma Co",
                "Total_Amount_of_Payment_USDollars": "250000.00",
                "Name_of_Drug_or_Biological_or_Device_or_Medical_Supply_1": "ExampleDrug",
                "Principal_Investigator_1_First_Name": "Alice",
                "Principal_Investigator_1_Last_Name": "Johnson",
                "Research_Information_Institution_1": "Harvard Medical School",
                "Program_Year": "2022",
            }
        ]
        from bve.ingestion.openpayments_client import fetch_research_payments

        events = fetch_research_payments("Pharma Co")
        assert len(events) == 1
        ev = events[0]
        assert ev.record_type == "open_payments_research"
        assert ev.payload["total_amount_usd"] == 250000.0
        assert "ExampleDrug" in ev.payload["by_drug"]
        pis = ev.payload["principal_investigators"]
        assert pis[0]["name"] == "Alice Johnson"
        assert pis[0]["institution"] == "Harvard Medical School"

    def test_open_payments_checksum_stable(self):
        payload = {
            "company_name": "Pharma Co",
            "total_amount_usd": 23000.50,
            "record_count": 2,
        }
        e1 = RawEvent(
            source="open_payments",
            record_type="open_payments_general",
            source_url="https://openpaymentsdata.cms.gov/api/1/general-payment-data",
            payload=payload,
        )
        e2 = RawEvent(
            source="open_payments",
            record_type="open_payments_general",
            source_url="https://openpaymentsdata.cms.gov/api/1/general-payment-data",
            payload=payload,
        )
        assert e1.dedup_key() == e2.dedup_key()


# ---------------------------------------------------------------------------
# Cross-client schema invariants
# ---------------------------------------------------------------------------


class TestCrossClientInvariants:
    """Validate schema invariants that must hold across ALL client outputs."""

    REQUIRED_FIELDS = ("source", "record_type", "source_url", "checksum", "payload")

    def _all_sample_events(self) -> list[RawEvent]:
        return [
            RawEvent(
                source="sec_edgar",
                record_type="10_k",
                source_url="https://sec.gov/a",
                payload={"ticker": "VKTX"},
            ),
            RawEvent(
                source="ctgov",
                record_type="trial_study",
                source_url="https://clinicaltrials.gov/b",
                payload={"nct_id": "NCT123"},
            ),
            RawEvent(
                source="openfda",
                record_type="drug_approval",
                source_url="https://api.fda.gov/c",
                payload={"application_number": "NDA001"},
            ),
            RawEvent(
                source="pubmed",
                record_type="pubmed_abstract",
                source_url="https://pubmed.ncbi.nlm.nih.gov/1/",
                payload={"pmid": "1", "title": "Study"},
            ),
            RawEvent(
                source="news",
                record_type="news_article",
                source_url="https://biospace.com/x",
                payload={"ticker": "VKTX", "title": "News"},
            ),
            RawEvent(
                source="open_payments",
                record_type="open_payments_general",
                source_url="https://openpaymentsdata.cms.gov/x",
                payload={"company_name": "Pharma"},
            ),
            RawEvent(
                source="market_data",
                record_type="price_snapshot",
                source_url="https://finance.yahoo.com/quote/VKTX",
                payload={"ticker": "VKTX", "last_price": 42.0},
            ),
        ]

    def test_all_events_have_required_fields(self):
        for ev in self._all_sample_events():
            for field in self.REQUIRED_FIELDS:
                assert getattr(ev, field) is not None, f"Missing {field} on {ev.source}"

    def test_all_checksums_are_64_chars(self):
        for ev in self._all_sample_events():
            assert len(ev.checksum) == 64, f"Bad checksum length for {ev.source}"

    def test_all_dedup_keys_are_unique(self):
        events = self._all_sample_events()
        keys = [ev.dedup_key() for ev in events]
        assert len(keys) == len(set(keys)), "Duplicate dedup keys across different sources"

    def test_all_fetched_at_are_utc(self):
        for ev in self._all_sample_events():
            assert ev.fetched_at.tzinfo is not None

    def test_source_url_never_empty(self):
        for ev in self._all_sample_events():
            assert ev.source_url, f"Empty source_url on {ev.source}"
