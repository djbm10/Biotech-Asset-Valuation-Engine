"""
Tests for source connectors.

Validates:
  1. All 4 connectors satisfy the SourceConnector Protocol.
  2. source_type property returns the correct SourceType string.
  3. fetch() always returns a FetchResult (never raises).
  4. FetchResult.documents contains RawDocument instances.
  5. Each RawDocument from a connector has entity_hints preserved.
  6. PressReleaseConnector.from_text() creates a valid RawDocument.
  7. Connectors record errors in FetchResult.fetch_errors on failure.
  8. Missing required entity_hints fields produce errors, not exceptions.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from bve.connectors.base import FetchResult, SourceConnector
from bve.connectors.clinicaltrials import ClinicalTrialsConnector
from bve.connectors.fda import FDAConnector
from bve.connectors.press_release import PressReleaseConnector
from bve.connectors.sec_edgar import SECEdgarConnector
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument


_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

_HINTS_FULL = EntityHints(
    asset_id="asset-001",
    company_id="company-001",
    drug_name="AXD-101",
    indication="Psoriasis",
    ticker="ACME",
    nct_id="NCT04567890",
)

_HINTS_MINIMAL = EntityHints(
    asset_id="asset-001",
    company_id="company-001",
)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

class TestSourceConnectorProtocol:
    """All 4 connectors must satisfy the SourceConnector structural Protocol."""

    @pytest.mark.parametrize("connector_class", [
        ClinicalTrialsConnector,
        FDAConnector,
        PressReleaseConnector,
        SECEdgarConnector,
    ])
    def test_implements_protocol(self, connector_class):
        connector = connector_class()
        assert isinstance(connector, SourceConnector)

    @pytest.mark.parametrize("connector_class,expected_source", [
        (ClinicalTrialsConnector, "clinicaltrials_gov"),
        (FDAConnector, "fda_website"),
        (PressReleaseConnector, "press_release"),
        (SECEdgarConnector, "sec_filing"),
    ])
    def test_source_type_property(self, connector_class, expected_source):
        connector = connector_class()
        assert connector.source_type == expected_source


# ---------------------------------------------------------------------------
# FetchResult model
# ---------------------------------------------------------------------------

class TestFetchResult:
    def test_empty_result_valid(self):
        result = FetchResult(source="manual")
        assert result.documents == []
        assert result.fetch_errors == []

    def test_frozen(self):
        result = FetchResult(source="manual")
        with pytest.raises(Exception):
            result.source = "press_release"  # type: ignore[misc]

    def test_round_trip(self):
        result = FetchResult(
            source="fda_website",
            fetch_errors=["some error"],
        )
        d = result.model_dump()
        result2 = FetchResult.model_validate(d)
        assert result2.source == "fda_website"
        assert result2.fetch_errors == ["some error"]


# ---------------------------------------------------------------------------
# PressReleaseConnector — from_text (no network)
# ---------------------------------------------------------------------------

class TestPressReleaseConnector:
    def test_from_text_basic(self):
        doc = PressReleaseConnector.from_text(
            text="Regeneron FDA approved DUPIXENT for atopic dermatitis.",
            title="FDA Approves DUPIXENT",
            entity_hints=_HINTS_FULL,
        )
        assert isinstance(doc, RawDocument)
        assert doc.source == "press_release"
        assert doc.title == "FDA Approves DUPIXENT"
        assert doc.entity_hints.asset_id == "asset-001"
        assert doc.entity_hints.drug_name == "AXD-101"

    def test_from_text_with_url(self):
        doc = PressReleaseConnector.from_text(
            text="Press release content here.",
            title="Test PR",
            entity_hints=_HINTS_FULL,
            source_url="https://example.com/pr/2024",
        )
        assert doc.source_url == "https://example.com/pr/2024"

    def test_from_text_word_count(self):
        doc = PressReleaseConnector.from_text(
            text="one two three four five six",
            title="Test",
            entity_hints=_HINTS_MINIMAL,
        )
        assert doc.word_count == 6

    def test_from_text_published_at(self):
        doc = PressReleaseConnector.from_text(
            text="content",
            title="Test",
            entity_hints=_HINTS_MINIMAL,
            published_at=_NOW,
        )
        assert doc.published_at == _NOW

    def test_fetch_missing_url_returns_error(self):
        connector = PressReleaseConnector()
        result = connector.fetch(_HINTS_FULL)  # no url kwarg
        assert isinstance(result, FetchResult)
        assert result.documents == []
        assert len(result.fetch_errors) > 0

    def test_fetch_bad_url_returns_error_not_exception(self):
        connector = PressReleaseConnector(timeout=2)
        result = connector.fetch(
            _HINTS_FULL,
            url="http://this-url-definitely-does-not-exist-12345.invalid/pr",
        )
        assert isinstance(result, FetchResult)
        assert result.documents == []
        assert len(result.fetch_errors) > 0


# ---------------------------------------------------------------------------
# ClinicalTrialsConnector — with mocked ingestion layer
# ---------------------------------------------------------------------------

class TestClinicalTrialsConnector:
    def _mock_raw_study(self) -> dict:
        return {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT04567890",
                    "briefTitle": "AXD-101 Phase 3 in Psoriasis",
                },
                "statusModule": {
                    "overallStatus": "COMPLETED",
                    "lastUpdatePostDateStruct": {"date": "2024-03-15"},
                },
                "descriptionModule": {
                    "briefSummary": "A Phase 3 trial of AXD-101 in psoriasis."
                },
                "designModule": {"phases": ["PHASE3"]},
                "conditionsModule": {"conditions": ["Psoriasis"]},
                "armsInterventionsModule": {
                    "interventions": [{"interventionType": "DRUG", "name": "axditinib"}]
                },
                "outcomesModule": {
                    "primaryOutcomes": [{"measure": "PASI 90 at Week 16"}]
                },
            }
        }

    def test_fetch_by_nct_id_success(self):
        connector = ClinicalTrialsConnector()
        with patch("bve.ingestion.clinicaltrials_gov.fetch_study") as mock_fetch:
            mock_fetch.return_value = self._mock_raw_study()
            result = connector.fetch(_HINTS_FULL)

        assert isinstance(result, FetchResult)
        assert len(result.documents) == 1
        doc = result.documents[0]
        assert doc.source == "clinicaltrials_gov"
        assert "NCT04567890" in doc.raw_text
        assert doc.entity_hints.asset_id == "asset-001"

    def test_fetch_by_drug_name_success(self):
        connector = ClinicalTrialsConnector()
        hints = EntityHints(asset_id="a", company_id="c", drug_name="AXD-101")
        with patch("bve.ingestion.clinicaltrials_gov.search_studies") as mock_search:
            mock_search.return_value = [self._mock_raw_study()]
            result = connector.fetch(hints)

        mock_search.assert_called_once_with(intervention="AXD-101", page_size=20)
        assert len(result.documents) == 1
        assert result.documents[0].source == "clinicaltrials_gov"

    def test_fetch_no_drug_name_or_nct_id_returns_empty(self):
        # No nct_id or drug_name: connector returns a clean empty result without
        # poisoning the health metric with a fetch_error.
        connector = ClinicalTrialsConnector()
        result = connector.fetch(_HINTS_MINIMAL)
        assert result.documents == []
        assert result.fetch_errors == []

    def test_fetch_api_error_returns_error_not_exception(self):
        connector = ClinicalTrialsConnector()
        with patch("bve.ingestion.clinicaltrials_gov.fetch_study") as mock_fetch:
            mock_fetch.side_effect = RuntimeError("Network error")
            result = connector.fetch(_HINTS_FULL)
        assert isinstance(result, FetchResult)
        assert result.documents == []
        assert len(result.fetch_errors) > 0

    def test_entity_hints_preserved_in_documents(self):
        connector = ClinicalTrialsConnector()
        with patch("bve.ingestion.clinicaltrials_gov.fetch_study") as mock_fetch:
            mock_fetch.return_value = self._mock_raw_study()
            result = connector.fetch(_HINTS_FULL)

        doc = result.documents[0]
        assert doc.entity_hints.asset_id == "asset-001"
        assert doc.entity_hints.company_id == "company-001"


# ---------------------------------------------------------------------------
# FDAConnector — with mocked ingestion layer
# ---------------------------------------------------------------------------

class TestFDAConnector:
    def _mock_raw_approval(self) -> dict:
        return {
            "application_number": "NDA217890",
            "sponsor_name": "ACME Pharma",
            "products": [{"brand_name": "LUMIVEX", "generic_name": "lumivexinib"}],
            "submissions": [
                {
                    "submission_type": "NDA",
                    "submission_status": "AP",
                    "submission_status_date": "20240601",
                    "review_priority": "PRIORITY",
                }
            ],
        }

    def test_fetch_success(self):
        connector = FDAConnector()
        hints = EntityHints(asset_id="a", company_id="c", drug_name="lumivexinib")
        with patch("bve.ingestion.fda.search_approvals") as mock_search:
            mock_search.return_value = [self._mock_raw_approval()]
            result = connector.fetch(hints)

        assert len(result.documents) == 1
        doc = result.documents[0]
        assert doc.source == "fda_website"
        assert "lumivexinib" in doc.raw_text.lower() or "LUMIVEX" in doc.raw_text

    def test_fetch_no_drug_name_returns_error(self):
        connector = FDAConnector()
        result = connector.fetch(_HINTS_MINIMAL)
        assert result.documents == []
        assert len(result.fetch_errors) > 0

    def test_fetch_api_error_returns_error_not_exception(self):
        connector = FDAConnector()
        hints = EntityHints(asset_id="a", company_id="c", drug_name="drug")
        with patch("bve.ingestion.fda.search_approvals") as mock_search:
            mock_search.side_effect = ConnectionError("API down")
            result = connector.fetch(hints)
        assert isinstance(result, FetchResult)
        assert result.documents == []
        assert len(result.fetch_errors) > 0

    def test_document_source_url_is_fda_accessdata(self):
        connector = FDAConnector()
        hints = EntityHints(asset_id="a", company_id="c", drug_name="lumivexinib")
        with patch("bve.ingestion.fda.search_approvals") as mock_search:
            mock_search.return_value = [self._mock_raw_approval()]
            result = connector.fetch(hints)

        doc = result.documents[0]
        assert doc.source_url is not None
        assert "accessdata" in doc.source_url or "fda" in doc.source_url.lower()


# ---------------------------------------------------------------------------
# SECEdgarConnector — with mocked requests
# ---------------------------------------------------------------------------

class TestSECEdgarConnector:
    def test_fetch_no_ticker_returns_error(self):
        connector = SECEdgarConnector()
        result = connector.fetch(_HINTS_MINIMAL)
        assert result.documents == []
        assert len(result.fetch_errors) > 0

    def test_fetch_cik_resolution_failure_returns_error(self):
        connector = SECEdgarConnector()
        hints = EntityHints(asset_id="a", company_id="c", ticker="ZZZZINVALID")
        with patch("bve.ingestion.sec_edgar.get_cik") as mock_cik:
            mock_cik.return_value = None  # not found
            result = connector.fetch(hints)
        assert result.documents == []
        assert len(result.fetch_errors) > 0

    def test_fetch_network_error_returns_error_not_exception(self):
        connector = SECEdgarConnector()
        hints = EntityHints(asset_id="a", company_id="c", ticker="REGN")
        with patch("bve.ingestion.sec_edgar.get_cik") as mock_cik, \
             patch("requests.get") as mock_get:
            mock_cik.return_value = "1336920"
            mock_get.side_effect = ConnectionError("Network timeout")
            result = connector.fetch(hints)
        assert isinstance(result, FetchResult)
        # May have no documents but should not raise
        assert result.documents == [] or isinstance(result.documents[0], RawDocument)

    def test_fetch_uses_sec_index_json_directory_listing(self):
        connector = SECEdgarConnector(form_types=["8-K"], max_filings_per_type=1)
        hints = EntityHints(asset_id="a", company_id="c", ticker="VRTX")

        submissions_payload = {
            "name": "Vertex Pharmaceuticals",
            "filings": {
                "recent": {
                    "form": ["8-K"],
                    "filingDate": ["2026-02-12"],
                    "accessionNumber": ["0000875320-26-000034"],
                }
            },
        }
        index_payload = {
            "directory": {
                "item": [
                    {"name": "0000875320-26-000034-index.html"},
                    {"name": "0000875320-26-000034.txt"},
                ]
            }
        }

        mock_responses = [
            Mock(status_code=200, json=Mock(return_value=submissions_payload)),
            Mock(status_code=200, json=Mock(return_value=index_payload)),
            Mock(status_code=200, text="SEC filing body text"),
        ]
        for response in mock_responses:
            response.raise_for_status = Mock()

        with patch("bve.ingestion.sec_edgar.get_cik", return_value="0000875320"), \
             patch("requests.get", side_effect=mock_responses) as mock_get:
            result = connector.fetch(hints, limit=1)

        assert len(result.documents) == 1
        assert result.documents[0].source == "sec_filing"
        fetched_urls = [call.args[0] for call in mock_get.call_args_list]
        assert fetched_urls[1].endswith("/000087532026000034/index.json")
        assert fetched_urls[2].endswith("/000087532026000034/0000875320-26-000034.txt")

    def test_8k_item_extraction_extracts_press_release_text(self):
        """8-K filings with Items 8.01/8.02 should have those sections extracted."""
        connector = SECEdgarConnector(form_types=["8-K"], max_filings_per_type=1)
        hints = EntityHints(asset_id="a", company_id="c", ticker="VRTX")

        submissions_payload = {
            "name": "Vertex Pharmaceuticals",
            "filings": {
                "recent": {
                    "form": ["8-K"],
                    "filingDate": ["2026-02-12"],
                    "accessionNumber": ["0000875320-26-000034"],
                }
            },
        }
        index_payload = {
            "directory": {
                "item": [{"name": "0000875320-26-000034.txt"}]
            }
        }
        # Filing text contains an Item 8.01 press-release section.
        filing_text = (
            "UNITED STATES SECURITIES AND EXCHANGE COMMISSION\n"
            "Item 1.01 Entry into Agreement.\nBlah blah agreement text.\n"
            "Item 8.01 Other Events.\nVertex announces positive Phase 3 data for VX-548.\n"
            "The trial met its primary endpoint with p<0.001.\n"
            "Item 9.01 Financial Statements.\nExhibit 99.1\n"
        )

        mock_responses = [
            Mock(status_code=200, json=Mock(return_value=submissions_payload)),
            Mock(status_code=200, json=Mock(return_value=index_payload)),
            Mock(status_code=200, text=filing_text),
        ]
        for r in mock_responses:
            r.raise_for_status = Mock()

        with patch("bve.ingestion.sec_edgar.get_cik", return_value="0000875320"), \
             patch("requests.get", side_effect=mock_responses):
            result = connector.fetch(hints, limit=1)

        assert len(result.documents) == 1
        doc = result.documents[0]
        assert "Item 8.01" in doc.raw_text or "VX-548" in doc.raw_text
        assert "Item 1.01" not in doc.raw_text  # pre-8.01 content excluded

    def test_8k_item_extraction_disabled_returns_full_text(self):
        """With extract_8k_items=False, full filing text is preserved."""
        connector = SECEdgarConnector(
            form_types=["8-K"], max_filings_per_type=1, extract_8k_items=False
        )
        hints = EntityHints(asset_id="a", company_id="c", ticker="VRTX")

        submissions_payload = {
            "name": "Vertex Pharmaceuticals",
            "filings": {
                "recent": {
                    "form": ["8-K"],
                    "filingDate": ["2026-02-12"],
                    "accessionNumber": ["0000875320-26-000034"],
                }
            },
        }
        index_payload = {
            "directory": {
                "item": [{"name": "0000875320-26-000034.txt"}]
            }
        }
        filing_text = (
            "Item 1.01 Entry into Agreement.\nAgreement text.\n"
            "Item 8.01 Other Events.\nPress release content.\n"
        )

        mock_responses = [
            Mock(status_code=200, json=Mock(return_value=submissions_payload)),
            Mock(status_code=200, json=Mock(return_value=index_payload)),
            Mock(status_code=200, text=filing_text),
        ]
        for r in mock_responses:
            r.raise_for_status = Mock()

        with patch("bve.ingestion.sec_edgar.get_cik", return_value="0000875320"), \
             patch("requests.get", side_effect=mock_responses):
            result = connector.fetch(hints, limit=1)

        assert len(result.documents) == 1
        assert "Item 1.01" in result.documents[0].raw_text

    def test_nct_id_fallback_to_drug_name_when_empty(self):
        """When nct_id fetch returns empty, connector falls back to drug_name search."""
        connector = ClinicalTrialsConnector()
        hints = EntityHints(
            asset_id="asset-001",
            company_id="company-001",
            drug_name="AXD-101",
            nct_id="NCT04567890",
        )
        with patch("bve.ingestion.clinicaltrials_gov.fetch_study") as mock_fetch, \
             patch("bve.ingestion.clinicaltrials_gov.search_studies") as mock_search:
            mock_fetch.return_value = None  # nct_id lookup returns nothing
            mock_search.return_value = [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT04567891",
                            "briefTitle": "AXD-101 Phase 2 in Eczema",
                        },
                        "statusModule": {
                            "overallStatus": "RECRUITING",
                            "lastUpdatePostDateStruct": {"date": "2024-01-01"},
                        },
                        "descriptionModule": {"briefSummary": "A trial of AXD-101."},
                        "designModule": {"phases": ["PHASE2"]},
                        "conditionsModule": {"conditions": ["Eczema"]},
                        "armsInterventionsModule": {
                            "interventions": [{"interventionType": "DRUG", "name": "AXD-101"}]
                        },
                        "outcomesModule": {"primaryOutcomes": []},
                    }
                }
            ]
            result = connector.fetch(hints)

        mock_search.assert_called_once()
        assert len(result.documents) == 1
        assert result.documents[0].source == "clinicaltrials_gov"
