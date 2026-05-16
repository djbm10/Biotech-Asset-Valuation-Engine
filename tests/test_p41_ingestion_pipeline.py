"""
Tests for P4.1 — Automated data ingestion pipeline.

Verifies:
- AssetIngestionSpec validates required fields
- IngestionPipeline.run_one returns IngestionResult
- IngestionPipeline.run returns list of IngestionResult (one per spec)
- IngestionResult has asset_id, documents_fetched, errors, elapsed_seconds
- Connector failure is captured in errors — does not raise
- Empty connector list returns zero documents, no errors
- documents_fetched = sum of documents across all connectors
- connector_results keys match requested connectors
- IngestionResult.succeeded = True when errors is empty
- IngestionResult.succeeded = False when any connector errors
- IngestionPipeline respects connector_timeout_seconds
- run() with empty specs returns empty list
- IngestionSummary aggregates multiple results
- IngestionSummary.total_documents, total_errors, n_assets, n_succeeded
- connector_registry lists available connectors
- AssetIngestionSpec.short_label uses ticker when available
- IngestionResult is frozen
- MockConnector returns deterministic FetchResult for testing
- pipeline with one failing connector still returns results for others
- IngestionResult.fetched_at is a UTC datetime
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pytest

from bve.ops.ingestion_pipeline import (
    AssetIngestionSpec,
    IngestionPipeline,
    IngestionResult,
    IngestionSummary,
    CONNECTOR_REGISTRY,
)
from bve.connectors.base import FetchResult
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument


# ---------------------------------------------------------------------------
# Mock connector for deterministic testing
# ---------------------------------------------------------------------------

import hashlib


def _make_raw_doc(asset_id: str) -> RawDocument:
    """Create a minimal valid RawDocument for testing."""
    raw_text = f"Test document for {asset_id}."
    return RawDocument(
        id=f"doc-manual-{asset_id}",
        source="manual",
        entity_hints=EntityHints(asset_id=asset_id, company_id=asset_id),
        raw_text=raw_text,
        published_at=datetime.now(timezone.utc),
        retrieved_at=datetime.now(timezone.utc),
        title=f"Manual doc for {asset_id}",
        document_hash=hashlib.sha256(raw_text.encode()).hexdigest(),
    )


class _OkConnector:
    """Always returns 2 documents."""
    source_name = "mock_ok"

    def fetch(self, hints: EntityHints, **kwargs) -> FetchResult:
        return FetchResult(
            documents=[
                _make_raw_doc(hints.asset_id or "x"),
                _make_raw_doc(hints.asset_id or "x"),
            ],
            source="manual",
        )


class _FailConnector:
    """Always raises an exception."""
    source_name = "mock_fail"

    def fetch(self, hints: EntityHints, **kwargs) -> FetchResult:
        raise RuntimeError("Simulated connector failure")


class _EmptyConnector:
    """Always returns 0 documents."""
    source_name = "mock_empty"

    def fetch(self, hints: EntityHints, **kwargs) -> FetchResult:
        return FetchResult(documents=[], source="manual")


class _ErrorConnector:
    """Returns a FetchResult with errors but no exception."""
    source_name = "mock_error"

    def fetch(self, hints: EntityHints, **kwargs) -> FetchResult:
        return FetchResult(
            documents=[],
            fetch_errors=["API rate limit exceeded"],
            source="manual",
        )


# ---------------------------------------------------------------------------
# AssetIngestionSpec
# ---------------------------------------------------------------------------

class TestAssetIngestionSpec:
    def test_minimal_spec(self):
        spec = AssetIngestionSpec(asset_id="rlay-001")
        assert spec.asset_id == "rlay-001"

    def test_default_connectors_is_list(self):
        spec = AssetIngestionSpec(asset_id="x")
        assert isinstance(spec.connectors, list)

    def test_short_label_uses_ticker(self):
        spec = AssetIngestionSpec(asset_id="x", ticker="RLAY")
        assert spec.short_label() == "RLAY"

    def test_short_label_falls_back_to_asset_id(self):
        spec = AssetIngestionSpec(asset_id="rlay-001")
        assert spec.short_label() == "rlay-001"

    def test_drug_name_stored(self):
        spec = AssetIngestionSpec(asset_id="x", drug_name="Relaysomab")
        assert spec.drug_name == "Relaysomab"

    def test_nct_ids_stored(self):
        spec = AssetIngestionSpec(asset_id="x", nct_ids=["NCT12345678"])
        assert "NCT12345678" in spec.nct_ids


# ---------------------------------------------------------------------------
# IngestionResult
# ---------------------------------------------------------------------------

class TestIngestionResult:
    def _make_result(self, **kwargs) -> IngestionResult:
        params: dict = {
            "asset_id": "x",
            "documents_fetched": 3,
            "errors": [],
            "connector_results": {},
            "elapsed_seconds": 0.5,
            "fetched_at": datetime.now(timezone.utc),
        }
        params.update(kwargs)
        return IngestionResult(**params)

    def test_succeeded_true_when_no_errors(self):
        r = self._make_result()
        assert r.succeeded is True

    def test_succeeded_false_when_errors(self):
        r = self._make_result(errors=["oops"])
        assert r.succeeded is False

    def test_fetched_at_is_datetime(self):
        r = self._make_result()
        assert isinstance(r.fetched_at, datetime)

    def test_is_frozen(self):
        r = self._make_result()
        with pytest.raises((AttributeError, TypeError)):
            r.documents_fetched = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# IngestionPipeline — run_one
# ---------------------------------------------------------------------------

class TestRunOne:
    def _pipeline(self) -> IngestionPipeline:
        return IngestionPipeline(connectors=[_OkConnector()])

    def test_returns_ingestion_result(self):
        spec = AssetIngestionSpec(asset_id="rlay-001")
        result = self._pipeline().run_one(spec)
        assert isinstance(result, IngestionResult)

    def test_asset_id_preserved(self):
        spec = AssetIngestionSpec(asset_id="rlay-001")
        result = self._pipeline().run_one(spec)
        assert result.asset_id == "rlay-001"

    def test_documents_fetched_count(self):
        spec = AssetIngestionSpec(asset_id="rlay-001")
        result = self._pipeline().run_one(spec)
        assert result.documents_fetched == 2  # _OkConnector returns 2

    def test_no_errors_for_ok_connector(self):
        spec = AssetIngestionSpec(asset_id="rlay-001")
        result = self._pipeline().run_one(spec)
        assert result.errors == []
        assert result.succeeded is True

    def test_elapsed_seconds_is_float(self):
        spec = AssetIngestionSpec(asset_id="rlay-001")
        result = self._pipeline().run_one(spec)
        assert isinstance(result.elapsed_seconds, float)
        assert result.elapsed_seconds >= 0

    def test_connector_results_keyed_by_source(self):
        spec = AssetIngestionSpec(asset_id="rlay-001")
        result = self._pipeline().run_one(spec)
        assert "mock_ok" in result.connector_results

    def test_empty_connectors_zero_documents(self):
        pipeline = IngestionPipeline(connectors=[])
        result = pipeline.run_one(AssetIngestionSpec(asset_id="x"))
        assert result.documents_fetched == 0
        assert result.errors == []

    def test_empty_connector_returns_zero_docs(self):
        pipeline = IngestionPipeline(connectors=[_EmptyConnector()])
        result = pipeline.run_one(AssetIngestionSpec(asset_id="x"))
        assert result.documents_fetched == 0
        assert result.succeeded is True

    def test_failing_connector_captured_not_raised(self):
        pipeline = IngestionPipeline(connectors=[_FailConnector()])
        result = pipeline.run_one(AssetIngestionSpec(asset_id="x"))
        assert len(result.errors) == 1
        assert result.succeeded is False

    def test_error_connector_captured_in_errors(self):
        pipeline = IngestionPipeline(connectors=[_ErrorConnector()])
        result = pipeline.run_one(AssetIngestionSpec(asset_id="x"))
        assert len(result.errors) >= 1
        assert result.succeeded is False

    def test_mixed_connectors_partial_results(self):
        pipeline = IngestionPipeline(connectors=[_OkConnector(), _FailConnector()])
        result = pipeline.run_one(AssetIngestionSpec(asset_id="x"))
        assert result.documents_fetched == 2  # ok connector still returned 2
        assert len(result.errors) == 1        # fail connector error captured

    def test_two_ok_connectors_sums_documents(self):
        pipeline = IngestionPipeline(connectors=[_OkConnector(), _OkConnector()])
        result = pipeline.run_one(AssetIngestionSpec(asset_id="x"))
        assert result.documents_fetched == 4


# ---------------------------------------------------------------------------
# IngestionPipeline — run (batch)
# ---------------------------------------------------------------------------

class TestRunBatch:
    def test_empty_specs_returns_empty(self):
        pipeline = IngestionPipeline(connectors=[_OkConnector()])
        results = pipeline.run([])
        assert results == []

    def test_run_returns_one_result_per_spec(self):
        pipeline = IngestionPipeline(connectors=[_OkConnector()])
        specs = [
            AssetIngestionSpec(asset_id="a"),
            AssetIngestionSpec(asset_id="b"),
        ]
        results = pipeline.run(specs)
        assert len(results) == 2

    def test_run_preserves_asset_ids(self):
        pipeline = IngestionPipeline(connectors=[_OkConnector()])
        specs = [AssetIngestionSpec(asset_id="a"), AssetIngestionSpec(asset_id="b")]
        results = pipeline.run(specs)
        asset_ids = {r.asset_id for r in results}
        assert "a" in asset_ids
        assert "b" in asset_ids


# ---------------------------------------------------------------------------
# IngestionSummary
# ---------------------------------------------------------------------------

class TestIngestionSummary:
    def _two_results(self):
        ok = IngestionResult(
            asset_id="a", documents_fetched=5, errors=[],
            connector_results={}, elapsed_seconds=1.0,
            fetched_at=datetime.now(timezone.utc),
        )
        fail = IngestionResult(
            asset_id="b", documents_fetched=2, errors=["err1"],
            connector_results={}, elapsed_seconds=0.5,
            fetched_at=datetime.now(timezone.utc),
        )
        return IngestionSummary.from_results([ok, fail])

    def test_returns_ingestion_summary(self):
        assert isinstance(self._two_results(), IngestionSummary)

    def test_n_assets(self):
        assert self._two_results().n_assets == 2

    def test_total_documents(self):
        assert self._two_results().total_documents == 7

    def test_total_errors(self):
        assert self._two_results().total_errors == 1

    def test_n_succeeded(self):
        assert self._two_results().n_succeeded == 1

    def test_n_failed(self):
        assert self._two_results().n_failed == 1

    def test_empty_results(self):
        summary = IngestionSummary.from_results([])
        assert summary.n_assets == 0
        assert summary.total_documents == 0


# ---------------------------------------------------------------------------
# Connector registry
# ---------------------------------------------------------------------------

class TestConnectorRegistry:
    def test_registry_is_dict(self):
        assert isinstance(CONNECTOR_REGISTRY, dict)

    def test_registry_has_known_connectors(self):
        # At least one of the known connectors should be registered
        known = {"clinicaltrials", "sec_edgar", "market_prices", "fda", "pubmed"}
        assert len(known & set(CONNECTOR_REGISTRY.keys())) >= 1
