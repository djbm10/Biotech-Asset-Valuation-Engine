from __future__ import annotations

from datetime import datetime, timezone

from bve.dossier.asset_graph import CanonicalAssetGraph, GraphBackedDossierBuilder
from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase, TrialStatus
from bve.intelligence.evidence_ingestion import AutomatedEvidenceIngestionPipeline
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.knowledge_graph import NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore


def _company() -> Company:
    return Company(
        id="company-rly",
        name="Relay Therapeutics",
        ticker="RLAY",
        cash_millions=300.0,
        debt_millions=0.0,
        shares_outstanding_millions=90.0,
        burn_rate_millions_per_quarter=50.0,
        asset_ids=["asset-rly2608"],
    )


def _asset() -> Asset:
    return Asset(
        id="asset-rly2608",
        name="RLY-2608",
        indication="HR+/HER2- metastatic breast cancer",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        mechanism_of_action="mutant-selective PI3Ka inhibitor",
        biological_target="PD-1",
    )


def _trial() -> ClinicalTrial:
    return ClinicalTrial(
        asset_id="asset-rly2608",
        phase=TrialPhase.PHASE_2,
        nct_id="NCT05216432",
        title="ReDiscover-2",
        success_probability=0.49,
        primary_endpoint="ORR",
        endpoint_type=EndpointType.SURROGATE_VALIDATED,
        duration_years=2.0,
        cost_millions=45.0,
        enrollment=180,
        status=TrialStatus.RECRUITING,
        data_source="clinicaltrials_gov",
    )


def _hints() -> EntityHints:
    return EntityHints(
        asset_id="asset-rly2608",
        company_id="company-rly",
        drug_name="RLY-2608",
        indication="HR+/HER2- metastatic breast cancer",
        ticker="RLAY",
        nct_id="NCT05216432",
    )


def test_phase_c_ingests_clinical_trial_facts_into_graph_and_dossier() -> None:
    store = KnowledgeStore(":memory:")
    CanonicalAssetGraph(store).upsert_asset_bundle(company=_company(), asset=_asset(), trials=[_trial()])

    document = RawDocument.from_text(
        id="doc-ct-1",
        source="clinicaltrials_gov",
        title="NCT05216432",
        raw_text=(
            "NCT ID: NCT05216432\n"
            "Title: ReDiscover-2\n"
            "Status: Recruiting\n"
            "Phases: phase_2\n"
            "Enrollment: 180\n"
            "Primary outcomes: ORR\n"
        ),
        entity_hints=_hints(),
        source_url="https://clinicaltrials.gov/study/NCT05216432",
        retrieved_at=datetime(2026, 4, 17, tzinfo=timezone.utc),
        published_at=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )
    result = AutomatedEvidenceIngestionPipeline(store).ingest_documents([document])
    assert result.stored_documents == 1
    assert result.extracted_facts >= 4

    facts = store.get_evidence_facts(asset_id="asset-rly2608", fact_key="enrollment_target")
    assert len(facts) == 1
    assert facts[0]["value"] == 180

    dossier = GraphBackedDossierBuilder(store).build("RLY-2608")
    assert dossier.active_trials[0].nct_id == "NCT05216432"
    assert dossier.active_trials[0].enrollment_target == 180
    assert dossier.active_trials[0].primary_endpoint == "ORR"
    store.close()


def test_phase_c_resolves_financial_fact_conflicts_and_updates_financing_state() -> None:
    store = KnowledgeStore(":memory:")
    CanonicalAssetGraph(store).upsert_asset_bundle(company=_company(), asset=_asset(), trials=[_trial()])
    pipeline = AutomatedEvidenceIngestionPipeline(store)

    older = RawDocument.from_text(
        id="doc-sec-old",
        source="sec_filing",
        title="10-Q old",
        raw_text=(
            "The company reported cash and cash equivalents of $390 million. "
            "Shares outstanding were 93 million. "
            "Quarterly burn was approximately $55 million."
        ),
        entity_hints=_hints(),
        source_url="https://sec.example/old",
        retrieved_at=datetime(2026, 4, 17, tzinfo=timezone.utc),
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    newer = RawDocument.from_text(
        id="doc-sec-new",
        source="sec_filing",
        title="10-Q new",
        raw_text=(
            "The company reported cash and cash equivalents of $410 million. "
            "Shares outstanding were 93 million. "
            "Quarterly burn was approximately $55 million."
        ),
        entity_hints=_hints(),
        source_url="https://sec.example/new",
        retrieved_at=datetime(2026, 4, 17, tzinfo=timezone.utc),
        published_at=datetime(2026, 4, 12, tzinfo=timezone.utc),
    )
    pipeline.ingest_documents([older, newer])

    cash_facts = store.get_evidence_facts(asset_id="asset-rly2608", fact_key="cash_millions")
    statuses = {fact["value"]: fact["conflict_status"] for fact in cash_facts}
    assert statuses[410.0] == "winner"
    assert statuses[390.0] == "conflict"

    financing_node = store.find_node_by_external_id(NodeType.FINANCING_STATE, "financing:company-rly")
    assert financing_node is not None
    assert financing_node.properties["cash_millions"] == 410.0
    assert financing_node.properties["months_of_runway"] > 20

    dossier = GraphBackedDossierBuilder(store).build("RLY-2608")
    assert dossier.get_field_value("cash_runway_months") == financing_node.properties["months_of_runway"]
    store.close()


def test_phase_c_dedupes_processed_documents() -> None:
    store = KnowledgeStore(":memory:")
    CanonicalAssetGraph(store).upsert_asset_bundle(company=_company(), asset=_asset(), trials=[_trial()])
    document = RawDocument.from_text(
        id="doc-ct-1",
        source="clinicaltrials_gov",
        title="NCT05216432",
        raw_text="NCT ID: NCT05216432\nStatus: Recruiting\nPhases: phase_2\nEnrollment: 180\nPrimary outcomes: ORR\n",
        entity_hints=_hints(),
        source_url="https://clinicaltrials.gov/study/NCT05216432",
        retrieved_at=datetime(2026, 4, 17, tzinfo=timezone.utc),
        published_at=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )
    pipeline = AutomatedEvidenceIngestionPipeline(store)
    first = pipeline.ingest_documents([document])
    second = pipeline.ingest_documents([document])

    assert first.stored_documents == 1
    assert second.deduped_documents == 1
    assert len(store.get_evidence_facts(asset_id="asset-rly2608", fact_key="trial_phase")) == 1
    store.close()
