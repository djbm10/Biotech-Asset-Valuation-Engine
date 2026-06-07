from __future__ import annotations

from bve.dossier.asset_graph import CanonicalAssetGraph, EntityResolver, GraphBackedDossierBuilder
from bve.entities.asset import Asset, Catalyst, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase, TrialStatus
from bve.intelligence.knowledge_graph import EdgeType, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore


def _build_company() -> Company:
    return Company(
        id="company-rly",
        name="Relay Therapeutics",
        ticker="RLAY",
        cash_millions=410.0,
        debt_millions=0.0,
        shares_outstanding_millions=93.0,
        burn_rate_millions_per_quarter=55.0,
        asset_ids=["asset-rly2608"],
    )


def _build_asset() -> Asset:
    return Asset(
        id="asset-rly2608",
        name="RLY-2608",
        indication="HR+/HER2- metastatic breast cancer",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        mechanism_of_action="mutant-selective PI3Ka inhibitor",
        biological_target="PI3K alpha",
        competitor_assets=["inavolisib", "alpelisib"],
        upcoming_catalysts=[
            Catalyst(
                description="Phase 2 updated efficacy readout",
                expected_date="2026-09-15",
                catalyst_type="readout",
                probability_positive=0.62,
            )
        ],
    )


def _build_trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id="asset-rly2608",
            phase=TrialPhase.PHASE_2,
            nct_id="NCT05216432",
            title="ReDiscover-2",
            success_probability=0.49,
            primary_endpoint="ORR",
            endpoint_type=EndpointType.SURROGATE_VALIDATED,
            duration_years=2.0,
            cost_millions=45.0,
            start_date="2024-01-01",
            primary_completion_date="2026-08-30",
            enrollment=180,
            status=TrialStatus.RECRUITING,
            data_source="clinicaltrials_gov",
        )
    ]


def test_phase_b_graph_creates_core_entities_and_edges() -> None:
    store = KnowledgeStore(":memory:")
    resolver = EntityResolver()
    graph = CanonicalAssetGraph(store, resolver=resolver)

    bundle = graph.upsert_asset_bundle(
        company=_build_company(),
        asset=_build_asset(),
        trials=_build_trials(),
        management_team="Relay executive team",
        thesis_summary="Selective PI3Ka may improve tolerability versus class precedent.",
    )

    assert bundle.company_node.node_type == NodeType.COMPANY
    assert bundle.asset_node.node_type == NodeType.ASSET
    node_types = {node.node_type for node in store.find_by_type(NodeType.TRIAL)}
    assert node_types == {NodeType.TRIAL}

    subgraph = store.get_subgraph(bundle.asset_node.node_id, depth=2)
    edge_types = {edge.edge_type for edge in subgraph["edges"]}
    assert EdgeType.COMPANY_OWNS_ASSET in edge_types
    assert EdgeType.ASSET_TREATS_INDICATION in edge_types
    assert EdgeType.ASSET_TARGETS_TARGET in edge_types
    assert EdgeType.TRIAL_BELONGS_TO_ASSET in edge_types
    assert EdgeType.COMPETITOR_OVERLAPS_ASSET in edge_types

    resolver_hit = resolver.resolve_graph_entity("RLAY", NodeType.COMPANY)
    assert resolver_hit.found is True
    assert resolver_hit.external_id == "company-rly"

    target_hit = resolver.resolve_target("PD-1")
    assert target_hit.canonical_id is not None
    store.close()


def test_graph_query_and_dossier_builder_auto_build_dossier() -> None:
    store = KnowledgeStore(":memory:")
    resolver = EntityResolver()
    graph = CanonicalAssetGraph(store, resolver=resolver)
    graph.upsert_asset_bundle(
        company=_build_company(),
        asset=_build_asset(),
        trials=_build_trials(),
        thesis_summary="The market is discounting tolerability and biomarker selection.",
    )

    dossier = GraphBackedDossierBuilder(store, resolver=resolver).build("RLY-2608")

    assert dossier.program_id == "asset-rly2608"
    assert dossier.asset_name == "RLY-2608"
    assert dossier.company == "Relay Therapeutics"
    assert dossier.get_field_value("target") in {"PI3K alpha", "PI3K alpha"}
    assert dossier.get_field_value("current_phase") == "phase_2"
    assert dossier.get_field_value("quarterly_burn_musd") == 55.0
    assert dossier.get_field_value("cash_runway_months") is not None
    assert dossier.active_trials[0].nct_id == "NCT05216432"
    assert dossier.completeness().completeness_score > 0.25
    store.close()
