from __future__ import annotations

from datetime import date

import pytest

from bve.se.acquisition.connectors import (
    ClinicalTrialsGovConnector,
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
        return [{"_id": "0000950170-24-029298:oric-20231231.htm", "_source": {"ciks": ["0001796280"], "display_names": ["ORIC (ORIC)"]}}]

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
