"""Minimal package-boundary smoke test for a clean frozen checkout.

This deliberately uses an injected connector so the test proves the packaged runner can execute
and emit a serializable prediction-shaped result without requiring network access or holdout data.
"""

from __future__ import annotations

from bve.se.acquisition.corpus_store import CorpusStore
from bve.se.acquisition.runner import run_acquisition
from bve.se.acquisition.source_health import SourceHealth
from bve.se.schemas.contracts import BuyerProblemV2, SourceTier


def test_clean_environment_runner_emits_dummy_prediction(tmp_path) -> None:
    problem = BuyerProblemV2.model_validate(
        {
            "problem_id": "smoke-problem",
            "version": "1.0.0",
            "buyer": {"buyer_id": "smoke-buyer", "name": "Smoke Buyer", "as_of_date": "2026-07-11"},
            "strategic_gap": {
                "therapeutic_areas": ["oncology"],
                "target_expression": {
                    "operator": "ANY",
                    "targets": [{"canonical_id": "CD19", "label": "CD19"}],
                },
                "modalities": ["T_CELL_ENGAGER"],
            },
        }
    )

    class DummyConnector:
        source_family = "smoke_fixture"

        def acquire(self, store, *, targets, modality_terms, as_of_date):
            store.add(
                source_family=self.source_family,
                source_url="https://example.invalid/smoke",
                publisher="smoke",
                document_type="fixture",
                source_tier=SourceTier.PRIMARY,
                raw_payload={"case_id": "dummy-1", "disposition": "INCLUDE"},
                text="CD19 dummy evidence",
                title="dummy evidence",
                as_of_date=as_of_date,
            )
            return SourceHealth(
                source_family=self.source_family,
                connector_succeeded=True,
                query_returned_results=True,
                raw_record_count=1,
                documents_parsed=1,
                documents_indexed=1,
            )

    report = run_acquisition(problem, tmp_path / "corpus", connectors=[DummyConnector()])
    prediction = {
        "case_id": "dummy-1",
        "disposition": "INCLUDE",
        "documents_indexed": report.total_documents_indexed(),
    }

    assert prediction == {"case_id": "dummy-1", "disposition": "INCLUDE", "documents_indexed": 1}
    assert CorpusStore(tmp_path / "corpus").documents()[0].text == "CD19 dummy evidence"
