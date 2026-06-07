from __future__ import annotations

from bve.dossier.asset_graph import CanonicalAssetGraph
from bve.dossier.builder import DossierBuilder
from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase, TrialStatus
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.science_engine import ScienceDiligenceEngine


def _today():
    from datetime import date

    return date(2026, 4, 17)


def _builder() -> DossierBuilder:
    builder = DossierBuilder("asset-rly2608", "RLY-2608", "Relay Therapeutics")
    builder.set_created_at(_today())
    builder.set_field("mechanism_of_action", "mutant-selective PI3Ka inhibitor", source="unit", confidence=0.9, extracted_at=_today())
    builder.set_field("target", "PI3K alpha", source="unit", confidence=0.9, extracted_at=_today())
    builder.set_field("modality", "small_molecule", source="unit", confidence=1.0, extracted_at=_today())
    builder.set_field("indication", "PIK3CA H1047R-positive HR+/HER2- metastatic breast cancer", source="unit", confidence=0.9, extracted_at=_today())
    builder.set_field("biomarker_strategy", "H1047R-selected population", source="unit", confidence=0.85, extracted_at=_today())
    builder.set_field("safety_profile_summary", "Safety profile appears manageable with no grade 4 events reported.", source="unit", confidence=0.8, extracted_at=_today())
    builder.set_field("thesis_summary", "Selective PI3Ka inhibition may improve tolerability in a biomarker-selected population.", source="unit", confidence=0.9, extracted_at=_today())
    builder.add_active_trial(
        __import__("bve.dossier.dossier", fromlist=["TrialSummary"]).TrialSummary(
            nct_id="NCT05216432",
            phase="phase_2",
            status="recruiting",
            primary_endpoint="PFS",
            enrollment_target=180,
            estimated_completion="2026-08",
        )
    )
    builder.add_kill_criterion("PFS advantage must remain clinically meaningful at the next readout.")
    return builder


def _analog_assets() -> list[Asset]:
    return [
        Asset(
            id="analog-1",
            name="Inavolisib",
            indication="PIK3CA H1047R-positive HR+/HER2- metastatic breast cancer",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.SMALL_MOLECULE,
            mechanism_of_action="PI3K alpha inhibitor",
            biological_target="PI3K alpha",
        ),
        Asset(
            id="analog-2",
            name="Alpelisib",
            indication="HR+/HER2- breast cancer",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            stage=DevelopmentStage.APPROVED,
            modality=Modality.SMALL_MOLECULE,
            mechanism_of_action="PI3K alpha inhibitor",
            biological_target="PI3K alpha",
        ),
    ]


def test_phase_d_assess_dossier_outputs_eight_subscores_and_explanations() -> None:
    dossier = _builder().build()
    anchor = Asset(
        id="asset-rly2608",
        name="RLY-2608",
        indication="PIK3CA H1047R-positive HR+/HER2- metastatic breast cancer",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        mechanism_of_action="mutant-selective PI3Ka inhibitor",
        biological_target="PI3K alpha",
    )

    assessment = ScienceDiligenceEngine().assess_dossier(
        dossier,
        anchor_asset=anchor,
        analog_assets=_analog_assets(),
    )

    assert len(assessment.subscores) == 8
    assert assessment.science_score > 0.6
    assert assessment.design_score > 0.6
    assert assessment.top_positives
    assert assessment.top_risks
    assert assessment.kill_criteria
    assert assessment.nearest_analogs
    assert "scores" in assessment.plain_english_summary


def test_phase_d_graph_backed_assessment() -> None:
    store = KnowledgeStore(":memory:")
    company = Company(
        id="company-rly",
        name="Relay Therapeutics",
        ticker="RLAY",
        cash_millions=410.0,
        debt_millions=0.0,
        shares_outstanding_millions=93.0,
        burn_rate_millions_per_quarter=55.0,
        asset_ids=["asset-rly2608"],
    )
    asset = Asset(
        id="asset-rly2608",
        name="RLY-2608",
        indication="PIK3CA H1047R-positive HR+/HER2- metastatic breast cancer",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        mechanism_of_action="mutant-selective PI3Ka inhibitor",
        biological_target="PI3K alpha",
    )
    trial = ClinicalTrial(
        asset_id="asset-rly2608",
        phase=TrialPhase.PHASE_2,
        nct_id="NCT05216432",
        title="ReDiscover-2",
        success_probability=0.49,
        primary_endpoint="PFS",
        endpoint_type=EndpointType.SURROGATE_VALIDATED,
        duration_years=2.0,
        cost_millions=45.0,
        enrollment=180,
        status=TrialStatus.RECRUITING,
        data_source="clinicaltrials_gov",
    )
    CanonicalAssetGraph(store).upsert_asset_bundle(
        company=company,
        asset=asset,
        trials=[trial],
        thesis_summary="Selective PI3Ka may improve tolerability in a biomarker-selected population.",
    )

    assessment = ScienceDiligenceEngine(store).assess_asset(
        "RLY-2608",
        analog_assets=_analog_assets(),
    )

    assert assessment.asset_id == "asset-rly2608"
    assert assessment.asset_name == "RLY-2608"
    assert len(assessment.subscores) == 8
    assert assessment.confidence_band in {"medium", "high"}
    store.close()
