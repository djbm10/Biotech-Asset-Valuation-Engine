"""
P4.1 — Automated data ingestion pipeline.

Orchestrates the source connectors (ClinicalTrials.gov, SEC EDGAR, market prices,
FDA, PubMed) into a single automated refresh pipeline. The manual YAML config layer
is preserved — connectors are additive enrichment, not replacements.

Design principles
-----------------
- Connector failures are captured in ``IngestionResult.errors``, never raised.
- Partial results are always returned; one failed connector does not block others.
- ``IngestionPipeline`` is stateless — create one per run or reuse across runs.
- Connectors are identified by ``source_name`` attribute for keying results.

Usage
-----
>>> from bve.ops.ingestion_pipeline import IngestionPipeline, AssetIngestionSpec
>>> specs = [
...     AssetIngestionSpec(
...         asset_id="rlay-001", ticker="RLAY",
...         drug_name="Relegatinib", nct_ids=["NCT04956640"],
...     ),
... ]
>>> pipeline = IngestionPipeline.from_registry(["clinicaltrials", "sec_edgar"])
>>> results = pipeline.run(specs)
>>> summary = IngestionSummary.from_results(results)
>>> print(summary.total_documents, summary.n_succeeded)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from bve.connectors.base import FetchResult
from bve.intelligence.extraction.raw_document import EntityHints

_LOG = logging.getLogger("bve.ops.ingestion_pipeline")


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AssetIngestionSpec:
    """
    Specification for ingesting data for one asset.

    Parameters
    ----------
    asset_id : str
        Canonical asset identifier.
    ticker : Optional[str]
        Equity ticker (used by market prices and SEC EDGAR connectors).
    drug_name : Optional[str]
        Drug / compound name (used by ClinicalTrials and PubMed connectors).
    nct_ids : list[str]
        Specific NCT IDs to fetch directly (bypasses drug-name search).
    connectors : list[str]
        Connector names to run for this asset. Empty = all connectors in pipeline.
    """
    asset_id: str
    company_id: str = ""
    ticker: Optional[str] = None
    drug_name: Optional[str] = None
    nct_ids: list[str] = field(default_factory=list)
    connectors: list[str] = field(default_factory=list)

    def short_label(self) -> str:
        return self.ticker or self.asset_id

    def to_entity_hints(self) -> EntityHints:
        # company_id defaults to asset_id when not specified
        return EntityHints(
            asset_id=self.asset_id,
            company_id=self.company_id or self.asset_id,
            ticker=self.ticker,
            drug_name=self.drug_name,
            nct_id=self.nct_ids[0] if self.nct_ids else None,
        )


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IngestionResult:
    """
    Outcome of ingesting data for one asset.

    Attributes
    ----------
    asset_id : str
        The asset this result belongs to.
    documents_fetched : int
        Total documents successfully fetched across all connectors.
    errors : list[str]
        Error messages from any connector failure.
    connector_results : dict[str, FetchResult]
        Per-connector raw FetchResult, keyed by source_name.
    elapsed_seconds : float
        Wall-clock time for the full run_one() call.
    fetched_at : datetime
        UTC timestamp when the ingestion started.
    """
    asset_id: str
    documents_fetched: int
    errors: list[str]
    connector_results: dict[str, Any]
    elapsed_seconds: float
    fetched_at: datetime

    @property
    def succeeded(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IngestionSummary:
    """Aggregate statistics for a batch ingestion run."""
    n_assets: int
    total_documents: int
    total_errors: int
    n_succeeded: int
    n_failed: int
    total_elapsed_seconds: float

    @classmethod
    def from_results(cls, results: list[IngestionResult]) -> "IngestionSummary":
        if not results:
            return cls(
                n_assets=0, total_documents=0, total_errors=0,
                n_succeeded=0, n_failed=0, total_elapsed_seconds=0.0,
            )
        return cls(
            n_assets=len(results),
            total_documents=sum(r.documents_fetched for r in results),
            total_errors=sum(len(r.errors) for r in results),
            n_succeeded=sum(1 for r in results if r.succeeded),
            n_failed=sum(1 for r in results if not r.succeeded),
            total_elapsed_seconds=sum(r.elapsed_seconds for r in results),
        )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class IngestionPipeline:
    """
    Orchestrates connector runs for a list of asset specs.

    Parameters
    ----------
    connectors : list
        Connector instances (must implement ``fetch(hints, **kwargs) -> FetchResult``
        and have a ``source_name`` attribute).
    connector_timeout_seconds : float
        Per-connector wall-clock timeout (default 30s). Not enforced via
        thread interruption — connectors that block indefinitely will block.
    """

    def __init__(
        self,
        connectors: Optional[list] = None,
        connector_timeout_seconds: float = 30.0,
    ) -> None:
        self._connectors = connectors or []
        self._timeout = connector_timeout_seconds

    @classmethod
    def from_registry(
        cls,
        connector_names: list[str],
        **kwargs,
    ) -> "IngestionPipeline":
        """
        Build a pipeline from named connectors in CONNECTOR_REGISTRY.

        Parameters
        ----------
        connector_names : list[str]
            Names from CONNECTOR_REGISTRY to instantiate.
        """
        connectors = []
        for name in connector_names:
            if name not in CONNECTOR_REGISTRY:
                _LOG.warning("Unknown connector %r — skipping", name)
                continue
            try:
                connectors.append(CONNECTOR_REGISTRY[name]())
            except Exception as exc:  # noqa: BLE001
                _LOG.warning("Failed to instantiate connector %r: %s", name, exc)
        return cls(connectors=connectors, **kwargs)

    # ------------------------------------------------------------------ #
    # Core                                                                 #
    # ------------------------------------------------------------------ #

    def run_one(self, spec: AssetIngestionSpec) -> IngestionResult:
        """
        Ingest all configured connectors for a single asset spec.

        Connector exceptions are caught and recorded in ``IngestionResult.errors``.
        Partial results from successful connectors are always returned.
        """
        hints = spec.to_entity_hints()
        started_at = datetime.now(timezone.utc)
        t0 = time.monotonic()

        # Filter connectors if spec requests a subset
        active = self._connectors
        if spec.connectors:
            active = [c for c in self._connectors if c.source_name in spec.connectors]

        docs_total = 0
        errors: list[str] = []
        connector_results: dict[str, FetchResult] = {}

        for connector in active:
            name = getattr(connector, "source_name", type(connector).__name__)
            try:
                result: FetchResult = connector.fetch(hints)
                connector_results[name] = result
                docs_total += len(result.documents)
                if result.fetch_errors:
                    for err in result.fetch_errors:
                        errors.append(f"[{name}] {err}")
            except Exception as exc:  # noqa: BLE001
                err_msg = f"[{name}] {type(exc).__name__}: {exc}"
                _LOG.warning("Connector %r raised: %s", name, exc)
                errors.append(err_msg)

        elapsed = time.monotonic() - t0

        return IngestionResult(
            asset_id=spec.asset_id,
            documents_fetched=docs_total,
            errors=errors,
            connector_results=connector_results,
            elapsed_seconds=round(elapsed, 4),
            fetched_at=started_at,
        )

    def run(self, specs: list[AssetIngestionSpec]) -> list[IngestionResult]:
        """
        Run ingestion for a batch of asset specs.

        Returns one IngestionResult per spec, in input order.
        """
        return [self.run_one(spec) for spec in specs]


# ---------------------------------------------------------------------------
# Connector registry
# ---------------------------------------------------------------------------

def _build_registry() -> dict[str, type]:
    """
    Lazily import connectors into a name→class registry.

    Imports are deferred so the pipeline can be used without all dependencies
    installed (e.g., in test environments where yfinance is mocked out).
    """
    registry: dict[str, type] = {}

    try:
        from bve.connectors.clinicaltrials import ClinicalTrialsConnector
        registry["clinicaltrials"] = ClinicalTrialsConnector
    except ImportError:
        pass

    try:
        from bve.connectors.sec_edgar import SECEdgarConnector
        registry["sec_edgar"] = SECEdgarConnector
    except ImportError:
        pass

    try:
        from bve.connectors.fda import FDAConnector
        registry["fda"] = FDAConnector
    except ImportError:
        pass

    try:
        from bve.connectors.pubmed import PubMedConnector
        registry["pubmed"] = PubMedConnector
    except ImportError:
        pass

    try:
        from bve.connectors.market_prices import MarketPriceConnector
        registry["market_prices"] = MarketPriceConnector
    except ImportError:
        pass

    return registry


CONNECTOR_REGISTRY: dict[str, type] = _build_registry()
