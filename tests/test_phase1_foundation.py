"""Tests for Phase 1 Foundation — 4 packages: biology, trials, regulatory, knowledge/dossiers."""
from __future__ import annotations
from datetime import date

# ── Biology ──────────────────────────────────────────────────────────────────
from bve.biology.pathway_graph import BiologicalNode, BiologicalEdge, PathwayGraph
from bve.biology.mechanism_reasoner import MechanismReasoner, MechanismReasoningResult

# ── Trials ────────────────────────────────────────────────────────────────────
from bve.trials.trial_parser import TrialParser, TrialDesignRecord
from bve.trials.endpoint_library import EndpointLibrary

# ── Regulatory ────────────────────────────────────────────────────────────────
from bve.regulatory.fda_precedent_store import FDAPrecedentStore, FDAPrecedentRecord
from bve.regulatory.adcom_monitor import AdcomMonitor, AdcomMeeting

# ── Knowledge / Dossiers ──────────────────────────────────────────────────────
from bve.knowledge.dossiers.target_dossier import TargetDossier, TargetDossierStore, KeyPaper
from bve.knowledge.dossiers.indication_dossier import IndicationDossier, IndicationDossierStore
from bve.knowledge.dossiers.asset_dossier import AssetDossier, AssetDossierStore, ClinicalDataPoint


# =============================================================================
# BIOLOGY — PathwayGraph (tests 1–5)
# =============================================================================

def test_pathway_graph_add_and_get_node():
    graph = PathwayGraph()
    node = BiologicalNode(node_id="n1", node_type="target", name="EGFR")
    graph.add_node(node)
    result = graph.get_node("n1")
    assert result is not None
    assert result.name == "EGFR"
    assert result.node_type == "target"


def test_pathway_graph_add_edge_and_get_neighbors():
    graph = PathwayGraph()
    n1 = BiologicalNode(node_id="m1", node_type="mechanism", name="EGFR inhibition")
    n2 = BiologicalNode(node_id="t1", node_type="target", name="EGFR")
    graph.add_node(n1)
    graph.add_node(n2)
    edge = BiologicalEdge(
        edge_id="e1", source_id="m1", target_id="t1",
        relationship="mechanism_activates_target",
    )
    graph.add_edge(edge)
    neighbors = graph.neighbors("m1")
    assert any(n.node_id == "t1" for n in neighbors)


def test_pathway_graph_neighbors_filtered_by_relationship():
    graph = PathwayGraph()
    mech = BiologicalNode(node_id="m1", node_type="mechanism", name="Mech A")
    target = BiologicalNode(node_id="t1", node_type="target", name="Target A")
    liability = BiologicalNode(node_id="l1", node_type="safety_liability", name="Hepatotoxicity")
    graph.add_node(mech)
    graph.add_node(target)
    graph.add_node(liability)
    graph.add_edge(BiologicalEdge(edge_id="e1", source_id="m1", target_id="t1",
                                   relationship="mechanism_activates_target"))
    graph.add_edge(BiologicalEdge(edge_id="e2", source_id="m1", target_id="l1",
                                   relationship="mechanism_causes_liability"))

    targets = graph.neighbors("m1", relationship="mechanism_activates_target")
    liabilities = graph.neighbors("m1", relationship="mechanism_causes_liability")
    assert len(targets) == 1 and targets[0].node_id == "t1"
    assert len(liabilities) == 1 and liabilities[0].node_id == "l1"


def test_pathway_graph_find_by_type():
    graph = PathwayGraph()
    graph.add_node(BiologicalNode(node_id="t1", node_type="target", name="KRAS"))
    graph.add_node(BiologicalNode(node_id="t2", node_type="target", name="BRAF"))
    graph.add_node(BiologicalNode(node_id="p1", node_type="pathway", name="MAPK"))
    targets = graph.find_by_type("target")
    assert len(targets) == 2
    pathways = graph.find_by_type("pathway")
    assert len(pathways) == 1 and pathways[0].name == "MAPK"


def test_pathway_graph_node_and_edge_count():
    graph = PathwayGraph()
    assert graph.node_count() == 0
    assert graph.edge_count() == 0
    graph.add_node(BiologicalNode(node_id="n1", node_type="target", name="A"))
    graph.add_node(BiologicalNode(node_id="n2", node_type="disease", name="B"))
    graph.add_edge(BiologicalEdge(edge_id="e1", source_id="n1", target_id="n2",
                                   relationship="target_in_pathway"))
    assert graph.node_count() == 2
    assert graph.edge_count() == 1


# =============================================================================
# BIOLOGY — MechanismReasoner (tests 6–8)
# =============================================================================

def test_mechanism_reasoner_returns_result():
    reasoner = MechanismReasoner()
    result = reasoner.reason(mechanism="EGFR inhibition", indication="NSCLC")
    assert isinstance(result, MechanismReasoningResult)
    assert result.mechanism == "EGFR inhibition"
    assert result.indication == "NSCLC"


def test_mechanism_reasoner_efficacy_hypotheses_non_empty():
    reasoner = MechanismReasoner()
    result = reasoner.reason(mechanism="BTK inhibition", indication="CLL")
    assert len(result.efficacy_hypotheses) >= 1
    hyp = result.efficacy_hypotheses[0]
    assert "BTK inhibition" in hyp.hypothesis
    assert "CLL" in hyp.hypothesis
    assert 0.0 <= hyp.confidence <= 1.0


def test_mechanism_reasoner_with_graph_pulls_liabilities():
    graph = PathwayGraph()
    mech_node = BiologicalNode(node_id="mech1", node_type="mechanism", name="JAK inhibition")
    liability_node = BiologicalNode(
        node_id="lib1", node_type="safety_liability", name="Immunosuppression",
        description="JAK pathway inhibition blunts immune surveillance",
    )
    graph.add_node(mech_node)
    graph.add_node(liability_node)
    graph.add_edge(BiologicalEdge(
        edge_id="e1", source_id="mech1", target_id="lib1",
        relationship="mechanism_causes_liability",
    ))
    reasoner = MechanismReasoner(graph=graph)
    result = reasoner.reason(
        mechanism="JAK inhibition", indication="RA",
        mechanism_node_id="mech1",
    )
    assert len(result.safety_liabilities) == 1
    assert result.safety_liabilities[0].liability_name == "Immunosuppression"
    assert "1 graph-linked liabilities" in result.summary


# =============================================================================
# TRIALS — TrialParser (tests 9–15)
# =============================================================================

def test_trial_parser_minimal_flat_dict():
    parser = TrialParser()
    raw = {"phase": "2", "status": "recruiting"}
    record = parser.parse(raw)
    assert isinstance(record, TrialDesignRecord)
    assert record.phase == "2"
    assert record.status == "recruiting"


def test_trial_parser_nct_id_parsed():
    parser = TrialParser()
    raw = {"nct_id": "NCT12345678", "phase": "3", "status": "active"}
    record = parser.parse(raw)
    assert record.nct_id == "NCT12345678"


def test_trial_parser_phase_from_flat_dict():
    parser = TrialParser()
    raw = {"phase": "1/2"}
    record = parser.parse(raw)
    assert record.phase == "1/2"


def test_trial_parser_double_blind_blinding_detected():
    parser = TrialParser()
    raw = {"phase": "3", "blinding": "DOUBLE_BLIND"}
    record = parser.parse(raw)
    assert record.blinding == "double_blind"


def test_trial_parser_enrollment_target_as_int():
    parser = TrialParser()
    raw = {"phase": "2", "enrollment_target": "240"}
    record = parser.parse(raw)
    assert record.enrollment_target == 240
    assert isinstance(record.enrollment_target, int)


def test_trial_parser_ctgov_v2_nested_shape():
    parser = TrialParser()
    raw = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT99999999"},
            "designModule": {
                "phases": ["PHASE3"],
                "designInfo": {
                    "allocation": "RANDOMIZED",
                    "maskingInfo": {"masking": "DOUBLE"},
                },
            },
            "statusModule": {
                "enrollmentInfo": {"count": 300},
                "primaryCompletionDateStruct": {"date": "2027-06-01"},
            },
            "outcomesModule": {
                "primaryOutcomes": [{"measure": "Overall Survival", "description": "OS in months"}],
                "secondaryOutcomes": [{"measure": "PFS"}],
            },
            "eligibilityModule": {},
        }
    }
    record = parser.parse(raw)
    assert record.nct_id == "NCT99999999"
    assert record.phase == "3"
    assert record.blinding == "double_blind"
    assert record.enrollment_target == 300
    assert record.primary_completion_date == date(2027, 6, 1)
    assert any(e.name == "Overall Survival" for e in record.endpoints)


def test_trial_parser_parse_batch():
    parser = TrialParser()
    raws = [
        {"phase": "1", "status": "recruiting"},
        {"phase": "2", "status": "completed"},
        {"phase": "3", "status": "active"},
    ]
    records = parser.parse_batch(raws)
    assert len(records) == 3
    assert records[0].phase == "1"
    assert records[2].phase == "3"


# =============================================================================
# TRIALS — EndpointLibrary (tests 16–18)
# =============================================================================

def test_endpoint_library_get_returns_oncology_entries():
    lib = EndpointLibrary()
    entries = lib.get("oncology")
    assert len(entries) >= 3
    names = [e.name for e in entries]
    assert "Overall Survival" in names


def test_endpoint_library_accepted_primary_endpoints_only_established():
    lib = EndpointLibrary()
    primaries = lib.accepted_primary_endpoints("oncology")
    for e in primaries:
        assert e.regulatory_acceptability == "established"
        assert e.endpoint_type == "primary"
    # Overall Survival should be present
    assert any(e.name == "Overall Survival" for e in primaries)
    # Progression-Free Survival should NOT appear (it's "likely_acceptable")
    assert not any(e.name == "Progression-Free Survival" for e in primaries)


def test_endpoint_library_surrogate_endpoints_only_surrogates():
    lib = EndpointLibrary()
    surrogates = lib.surrogate_endpoints("oncology")
    assert all(e.is_surrogate for e in surrogates)
    assert len(surrogates) >= 2
    names = [e.name for e in surrogates]
    assert "Progression-Free Survival" in names


# =============================================================================
# REGULATORY — FDAPrecedentStore (tests 19–24)
# =============================================================================

def test_fda_precedent_store_seeded_on_init():
    store = FDAPrecedentStore()
    records = store.all_records()
    assert len(records) >= 4
    drug_names = [r.drug_name for r in records]
    assert "pembrolizumab" in drug_names
    assert "venetoclax" in drug_names


def test_fda_precedent_store_query_by_therapeutic_area():
    store = FDAPrecedentStore()
    onco = store.query(therapeutic_area="oncology")
    assert all(r.therapeutic_area == "oncology" for r in onco)
    assert len(onco) >= 1


def test_fda_precedent_store_query_by_modality():
    store = FDAPrecedentStore()
    sm = store.query(modality="small_molecule")
    assert all(r.modality == "small_molecule" for r in sm)
    assert len(sm) >= 2


def test_fda_precedent_store_crl_records_only():
    store = FDAPrecedentStore()
    # Add a CRL record first
    store.add(FDAPrecedentRecord(
        record_id="crl_001", drug_name="test_drug", indication="Test",
        modality="biologic", therapeutic_area="oncology",
        action_type="crl", action_date=date(2023, 3, 15),
        crl_reason="Inadequate CMC data",
    ))
    crls = store.crl_records()
    assert all(r.action_type == "crl" for r in crls)
    assert any(r.record_id == "crl_001" for r in crls)


def test_fda_precedent_store_surrogate_approvals():
    store = FDAPrecedentStore()
    surrogates = store.surrogate_approvals()
    assert all(r.was_surrogate for r in surrogates)
    assert all(r.action_type in ("approval", "accelerated_approval") for r in surrogates)
    assert len(surrogates) >= 2


def test_fda_precedent_store_add_and_query():
    store = FDAPrecedentStore()
    new_record = FDAPrecedentRecord(
        record_id="test_001", drug_name="sotorasib",
        indication="NSCLC KRAS G12C", modality="small_molecule",
        therapeutic_area="oncology", action_type="accelerated_approval",
        action_date=date(2021, 5, 28), primary_endpoint_used="ORR",
        was_surrogate=True, label_breadth="biomarker_selected",
    )
    store.add(new_record)
    retrieved = store.get("test_001")
    assert retrieved is not None
    assert retrieved.drug_name == "sotorasib"
    kras = store.query(indication="KRAS")
    assert any(r.record_id == "test_001" for r in kras)


# =============================================================================
# REGULATORY — AdcomMonitor (tests 25–27)
# =============================================================================

def test_adcom_monitor_add_and_get():
    monitor = AdcomMonitor()
    meeting = AdcomMeeting(
        meeting_id="adcom_001",
        committee_name="Oncologic Drugs Advisory Committee",
        drug_name="examplezumab",
        indication="NSCLC",
        meeting_date=date(2026, 6, 15),
        status="scheduled",
    )
    monitor.add(meeting)
    result = monitor.get("adcom_001")
    assert result is not None
    assert result.drug_name == "examplezumab"
    assert result.meeting_date == date(2026, 6, 15)


def test_adcom_monitor_upcoming_filters_future_scheduled():
    monitor = AdcomMonitor()
    future_meeting = AdcomMeeting(
        meeting_id="m1", committee_name="ODAC", drug_name="futuredrug",
        indication="Cancer", meeting_date=date(2027, 1, 10), status="scheduled",
    )
    past_meeting = AdcomMeeting(
        meeting_id="m2", committee_name="ODAC", drug_name="pastdrug",
        indication="Cancer", meeting_date=date(2020, 1, 10), status="held",
    )
    cancelled_meeting = AdcomMeeting(
        meeting_id="m3", committee_name="ODAC", drug_name="canceleddrug",
        indication="Cancer", meeting_date=date(2027, 3, 10), status="cancelled",
    )
    monitor.add(future_meeting)
    monitor.add(past_meeting)
    monitor.add(cancelled_meeting)
    upcoming = monitor.upcoming(as_of=date(2026, 1, 1))
    assert len(upcoming) == 1
    assert upcoming[0].drug_name == "futuredrug"


def test_adcom_monitor_days_to_next_meeting():
    monitor = AdcomMonitor()
    meeting = AdcomMeeting(
        meeting_id="m1", committee_name="ODAC", drug_name="testdrug",
        indication="NSCLC", meeting_date=date(2026, 7, 1), status="scheduled",
    )
    monitor.add(meeting)
    days = monitor.days_to_next_meeting("testdrug", as_of=date(2026, 6, 1))
    assert days == 30


# =============================================================================
# KNOWLEDGE / DOSSIERS — TargetDossierStore (tests 28–29)
# =============================================================================

def test_target_dossier_store_upsert_and_get():
    store = TargetDossierStore()
    dossier = TargetDossier(
        target_id="EGFR",
        target_name="Epidermal Growth Factor Receptor",
        gene_symbol="EGFR",
        target_class="kinase",
        mechanism_summary="Receptor tyrosine kinase activated by EGF ligands.",
    )
    store.upsert(dossier)
    result = store.get("EGFR")
    assert result is not None
    assert result.target_name == "Epidermal Growth Factor Receptor"
    assert result.gene_symbol == "EGFR"


def test_target_dossier_store_find_by_name_case_insensitive():
    store = TargetDossierStore()
    store.upsert(TargetDossier(target_id="kras_1", target_name="KRAS Proto-Oncogene", gene_symbol="KRAS"))
    store.upsert(TargetDossier(target_id="braf_1", target_name="BRAF Serine/Threonine Kinase", gene_symbol="BRAF"))
    results = store.find_by_name("kras")
    assert len(results) == 1
    assert results[0].target_id == "kras_1"
    # Also test gene symbol matching
    results_sym = store.find_by_name("braf")
    assert len(results_sym) >= 1


# =============================================================================
# KNOWLEDGE / DOSSIERS — IndicationDossierStore (tests 30–31)
# =============================================================================

def test_indication_dossier_store_upsert_and_get():
    store = IndicationDossierStore()
    dossier = IndicationDossier(
        indication_id="nsclc_1l",
        indication_name="NSCLC First-Line",
        therapeutic_area="oncology",
        disease_biology_summary="Non-small cell lung cancer driven by multiple oncogenic alterations.",
    )
    store.upsert(dossier)
    result = store.get("nsclc_1l")
    assert result is not None
    assert result.indication_name == "NSCLC First-Line"
    assert result.therapeutic_area == "oncology"


def test_indication_dossier_store_find_by_name_partial_match():
    store = IndicationDossierStore()
    store.upsert(IndicationDossier(
        indication_id="cll_1", indication_name="Chronic Lymphocytic Leukemia",
        therapeutic_area="hematology",
    ))
    store.upsert(IndicationDossier(
        indication_id="nsclc_1", indication_name="Non-Small Cell Lung Cancer",
        therapeutic_area="oncology",
    ))
    results = store.find_by_name("leukemia")
    assert len(results) == 1
    assert results[0].indication_id == "cll_1"


# =============================================================================
# KNOWLEDGE / DOSSIERS — AssetDossierStore (tests 32–35)
# =============================================================================

def test_asset_dossier_store_upsert_and_get():
    store = AssetDossierStore()
    dossier = AssetDossier(
        asset_id="rly2608",
        asset_name="RLY-2608",
        company_id="relay_tx",
        company_name="Relay Therapeutics",
        indication="PIK3CA-mutant breast cancer",
        modality="small_molecule",
        current_phase="2",
    )
    store.upsert(dossier)
    result = store.get("rly2608")
    assert result is not None
    assert result.asset_name == "RLY-2608"
    assert result.company_id == "relay_tx"


def test_asset_dossier_store_find_by_indication_partial_match():
    store = AssetDossierStore()
    store.upsert(AssetDossier(
        asset_id="a1", asset_name="Drug A", indication="NSCLC adenocarcinoma",
    ))
    store.upsert(AssetDossier(
        asset_id="a2", asset_name="Drug B", indication="Colorectal Cancer",
    ))
    store.upsert(AssetDossier(
        asset_id="a3", asset_name="Drug C", indication="NSCLC squamous cell",
    ))
    results = store.find_by_indication("nsclc")
    assert len(results) == 2
    ids = {r.asset_id for r in results}
    assert ids == {"a1", "a3"}


def test_asset_dossier_store_find_by_company():
    store = AssetDossierStore()
    store.upsert(AssetDossier(
        asset_id="x1", asset_name="Drug X1", indication="CLL", company_id="company_a",
    ))
    store.upsert(AssetDossier(
        asset_id="x2", asset_name="Drug X2", indication="NHL", company_id="company_a",
    ))
    store.upsert(AssetDossier(
        asset_id="y1", asset_name="Drug Y1", indication="NSCLC", company_id="company_b",
    ))
    results = store.find_by_company("company_a")
    assert len(results) == 2
    assert all(r.company_id == "company_a" for r in results)


def test_asset_dossier_clinical_data_and_key_papers():
    store = AssetDossierStore()
    clinical_dp = ClinicalDataPoint(
        study_id="NCT12345", phase="2", population="Relapsed/Refractory CLL",
        n=50, primary_endpoint="ORR", result_summary="ORR 72%, CR 14%",
        key_safety_findings="Grade 3+ AEs in 28% of patients",
    )
    paper = KeyPaper(
        title="Phase 2 results of Drug Z in CLL",
        authors="Smith et al.", journal="NEJM", year=2024,
        pmid="12345678", evidence_type="clinical",
    )
    dossier = AssetDossier(
        asset_id="drugz",
        asset_name="Drug Z",
        indication="CLL",
        clinical_data=[clinical_dp],
        key_papers=[paper],
    )
    store.upsert(dossier)
    result = store.get("drugz")
    assert result is not None
    assert len(result.clinical_data) == 1
    assert result.clinical_data[0].primary_endpoint == "ORR"
    assert result.clinical_data[0].n == 50
    assert len(result.key_papers) == 1
    assert result.key_papers[0].evidence_type == "clinical"
    assert result.key_papers[0].pmid == "12345678"
