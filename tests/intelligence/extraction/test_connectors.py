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
from unittest.mock import MagicMock, patch

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
        with patch("bve.ingestion.clinicaltrials_gov.fetch_trial_by_nct") as mock_fetch:
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

        assert len(result.documents) == 1
        assert result.documents[0].source == "clinicaltrials_gov"

    def test_fetch_no_drug_name_or_nct_id_returns_error(self):
        connector = ClinicalTrialsConnector()
        result = connector.fetch(_HINTS_MINIMAL)
        assert result.documents == []
        assert len(result.fetch_errors) > 0

    def test_fetch_api_error_returns_error_not_exception(self):
        connector = ClinicalTrialsConnector()
        with patch("bve.ingestion.clinicaltrials_gov.fetch_trial_by_nct") as mock_fetch:
            mock_fetch.side_effect = RuntimeError("Network error")
            result = connector.fetch(_HINTS_FULL)
        assert isinstance(result, FetchResult)
        assert result.documents == []
        assert len(result.fetch_errors) > 0

    def test_entity_hints_preserved_in_documents(self):
        connector = ClinicalTrialsConnector()
        with patch("bve.ingestion.clinicaltrials_gov.fetch_trial_by_nct") as mock_fetch:
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
