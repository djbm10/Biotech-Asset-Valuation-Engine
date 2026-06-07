"""Phase D scientific diligence engine."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from bve.dossier.asset_graph import AssetGraphQueryService, GraphBackedDossierBuilder
from bve.dossier.dossier import AssetDossier
from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.similarity.scorer import SimilarityScorer
from bve.similarity.types import AssetSimilarityScore


class ScienceSubscore(BaseModel):
    name: str
    value: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class AnalogProgram(BaseModel):
    asset_id: str
    asset_name: str
    composite_score: float = Field(ge=0.0, le=1.0)
    explanation: str


class ScienceAssessment(BaseModel):
    asset_id: str
    asset_name: str
    science_score: float = Field(ge=0.0, le=1.0)
    design_score: float = Field(ge=0.0, le=1.0)
    confidence_band: str
    subscores: list[ScienceSubscore]
    top_positives: list[str] = Field(default_factory=list)
    top_risks: list[str] = Field(default_factory=list)
    nearest_analogs: list[AnalogProgram] = Field(default_factory=list)
    kill_criteria: list[str] = Field(default_factory=list)
    plain_english_summary: str


class ScienceDiligenceEngine:
    """Rule-based scientific diligence engine built on graph-backed dossiers."""

    def __init__(
        self,
        store: Optional[KnowledgeStore] = None,
        *,
        graph_query: Optional[AssetGraphQueryService] = None,
        dossier_builder: Optional[GraphBackedDossierBuilder] = None,
        similarity_scorer: Optional[SimilarityScorer] = None,
    ) -> None:
        self.store = store
        self.graph_query = graph_query or (AssetGraphQueryService(store) if store is not None else None)
        self.dossier_builder = dossier_builder or (
            GraphBackedDossierBuilder(store) if store is not None else None
        )
        self.similarity_scorer = similarity_scorer or SimilarityScorer()

    def assess_dossier(
        self,
        dossier: AssetDossier,
        *,
        anchor_asset: Optional[Asset] = None,
        analog_assets: Optional[list[Asset]] = None,
    ) -> ScienceAssessment:
        analog_assets = analog_assets or []
        positives: list[str] = []
        risks: list[str] = []
        kill_criteria = list(dossier.kill_criteria[:5])

        mechanism = self._score_mechanism_plausibility(dossier, positives, risks)
        target = self._score_target_validation(dossier, positives, risks)
        modality = self._score_modality_risk(dossier, positives, risks)
        biomarker = self._score_biomarker_logic(dossier, positives, risks)
        translational = self._score_translational_evidence(dossier, positives, risks)
        analogs, analog_score = self._score_analogs(dossier, anchor_asset=anchor_asset, analog_assets=analog_assets, positives=positives, risks=risks)
        safety = self._score_safety_signal(dossier, positives, risks, kill_criteria)
        design = self._score_trial_design(dossier, positives, risks)

        subscores = [
            mechanism,
            target,
            modality,
            biomarker,
            translational,
            analog_score,
            safety,
            design,
        ]
        science_score = round(
            (
                mechanism.value
                + target.value
                + modality.value
                + biomarker.value
                + translational.value
                + analog_score.value
                + safety.value
            )
            / 7.0,
            4,
        )
        design_score = round(design.value, 4)
        mean_confidence = round(sum(score.confidence for score in subscores) / len(subscores), 4)
        if mean_confidence >= 0.8:
            confidence_band = "high"
        elif mean_confidence >= 0.6:
            confidence_band = "medium"
        else:
            confidence_band = "low"

        if not kill_criteria:
            if design_score < 0.45:
                kill_criteria.append("Trial design remains too weak to justify a differentiated PoS view.")
            if safety.value < 0.45:
                kill_criteria.append("Safety burden overwhelms scientific upside.")
            if science_score < 0.45:
                kill_criteria.append("Combined science package does not clear minimum quality bar.")

        summary = (
            f"{dossier.asset_name} scores {science_score:.2f} on science and {design_score:.2f} on design. "
            f"The model {'likes' if science_score >= 0.6 else 'does not like'} the science because "
            f"{positives[0].lower() if positives else 'the evidence base is thin'}, while the main risk is "
            f"{risks[0].lower() if risks else 'limited differentiated evidence'}."
        )

        return ScienceAssessment(
            asset_id=dossier.program_id,
            asset_name=dossier.asset_name,
            science_score=science_score,
            design_score=design_score,
            confidence_band=confidence_band,
            subscores=subscores,
            top_positives=positives[:5],
            top_risks=risks[:5],
            nearest_analogs=analogs[:5],
            kill_criteria=kill_criteria[:5],
            plain_english_summary=summary,
        )

    def assess_asset(
        self,
        asset_ref: str,
        *,
        analog_assets: Optional[list[Asset]] = None,
    ) -> ScienceAssessment:
        if self.dossier_builder is None:
            raise ValueError("ScienceDiligenceEngine requires a KnowledgeStore-backed dossier builder.")
        dossier = self.dossier_builder.build(asset_ref)
        anchor_asset = self._asset_from_graph(asset_ref)
        return self.assess_dossier(dossier, anchor_asset=anchor_asset, analog_assets=analog_assets)

    def _asset_from_graph(self, asset_ref: str) -> Optional[Asset]:
        if self.graph_query is None:
            return None
        node = self.graph_query.resolve_asset_node(asset_ref)
        if node is None:
            return None
        props = node.properties
        try:
            stage = DevelopmentStage(str(props.get("stage") or "phase_2"))
        except ValueError:
            stage = DevelopmentStage.PHASE_2
        try:
            modality = Modality(str(props.get("modality") or "small_molecule"))
        except ValueError:
            modality = Modality.SMALL_MOLECULE
        try:
            ta = TherapeuticArea(str(props.get("therapeutic_area") or "other"))
        except ValueError:
            ta = TherapeuticArea.OTHER
        return Asset(
            id=node.external_id or node.node_id,
            name=node.name,
            indication=str(props.get("indication") or "unknown"),
            therapeutic_area=ta,
            stage=stage,
            modality=modality,
            mechanism_of_action=props.get("mechanism_of_action"),
            biological_target=props.get("biological_target"),
            differentiation_notes=props.get("differentiation_notes"),
        )

    def _score_mechanism_plausibility(self, dossier: AssetDossier, positives: list[str], risks: list[str]) -> ScienceSubscore:
        moa = dossier.get_field_value("mechanism_of_action")
        target = dossier.get_field_value("target")
        if moa and target:
            positives.append("Mechanism and target are both explicitly defined.")
            return ScienceSubscore(name="mechanism_plausibility", value=0.78, confidence=0.8, rationale="Named mechanism and biological target support a coherent efficacy hypothesis.")
        if moa:
            positives.append("Mechanism is articulated, even if target evidence is incomplete.")
            return ScienceSubscore(name="mechanism_plausibility", value=0.62, confidence=0.65, rationale="Mechanism is present but target-level corroboration is incomplete.")
        risks.append("Mechanism is not clearly articulated in the dossier.")
        return ScienceSubscore(name="mechanism_plausibility", value=0.32, confidence=0.55, rationale="Missing mechanism detail weakens causal confidence.")

    def _score_target_validation(self, dossier: AssetDossier, positives: list[str], risks: list[str]) -> ScienceSubscore:
        target = dossier.get_field_value("target")
        thesis = dossier.get_field_value("thesis_summary")
        if target and thesis:
            positives.append("Target biology is tied to an explicit thesis.")
            return ScienceSubscore(name="target_validation", value=0.75, confidence=0.75, rationale="Target is specified and linked to a stated scientific thesis.")
        if target:
            return ScienceSubscore(name="target_validation", value=0.62, confidence=0.68, rationale="Target is known, but validation evidence is only partially expressed.")
        risks.append("Target validation is under-specified.")
        return ScienceSubscore(name="target_validation", value=0.3, confidence=0.55, rationale="No explicit target evidence chain is visible.")

    def _score_modality_risk(self, dossier: AssetDossier, positives: list[str], risks: list[str]) -> ScienceSubscore:
        modality = str(dossier.get_field_value("modality") or "")
        if modality in {"small_molecule", "biologic"}:
            positives.append(f"{modality.replace('_', ' ').title()} modality carries relatively familiar development risk.")
            return ScienceSubscore(name="modality_specific_risk", value=0.72, confidence=0.8, rationale=f"{modality} modality is comparatively well-understood operationally.")
        if modality in {"adc", "rna_therapy"}:
            risks.append(f"{modality.replace('_', ' ').title()} modality carries more execution and safety complexity.")
            return ScienceSubscore(name="modality_specific_risk", value=0.52, confidence=0.72, rationale=f"{modality} modality adds complexity versus standard small molecules or biologics.")
        if modality:
            risks.append("Modality-specific risk is not well calibrated for this program.")
            return ScienceSubscore(name="modality_specific_risk", value=0.48, confidence=0.55, rationale="Non-standard modality with sparse explicit supporting evidence.")
        return ScienceSubscore(name="modality_specific_risk", value=0.45, confidence=0.45, rationale="Modality is missing, limiting modality-risk inference.")

    def _score_biomarker_logic(self, dossier: AssetDossier, positives: list[str], risks: list[str]) -> ScienceSubscore:
        biomarker = str(dossier.get_field_value("biomarker_strategy") or "")
        indication = str(dossier.get_field_value("indication") or "")
        if biomarker:
            positives.append("Biomarker strategy is explicit, which can sharpen signal detection.")
            return ScienceSubscore(name="biomarker_logic_quality", value=0.74, confidence=0.76, rationale="Explicit biomarker strategy supports enrichment logic.")
        if any(token in indication.lower() for token in ("mutation", "positive", "selected", "h1047r", "her2")):
            positives.append("Indication itself implies a selected population even without a separate biomarker field.")
            return ScienceSubscore(name="biomarker_logic_quality", value=0.64, confidence=0.62, rationale="Selected indication language implies some enrichment even without dedicated biomarker metadata.")
        risks.append("Biomarker logic is not explicit.")
        return ScienceSubscore(name="biomarker_logic_quality", value=0.38, confidence=0.55, rationale="Lack of explicit biomarker strategy leaves patient-selection logic weak.")

    def _score_translational_evidence(self, dossier: AssetDossier, positives: list[str], risks: list[str]) -> ScienceSubscore:
        thesis = str(dossier.get_field_value("thesis_summary") or "")
        active_trials = dossier.active_trials
        if thesis and active_trials:
            positives.append("There is an explicit thesis plus ongoing clinical testing.")
            return ScienceSubscore(name="translational_evidence_quality", value=0.68, confidence=0.7, rationale="Active clinical work plus a written thesis suggests some translational bridge.")
        if active_trials:
            return ScienceSubscore(name="translational_evidence_quality", value=0.56, confidence=0.62, rationale="Clinical activity exists, but translational reasoning is only partially captured.")
        risks.append("Translational evidence chain is thin.")
        return ScienceSubscore(name="translational_evidence_quality", value=0.34, confidence=0.5, rationale="No visible clinical activity or explicit translational bridge.")

    def _score_analogs(
        self,
        dossier: AssetDossier,
        *,
        anchor_asset: Optional[Asset],
        analog_assets: list[Asset],
        positives: list[str],
        risks: list[str],
    ) -> tuple[list[AnalogProgram], ScienceSubscore]:
        if anchor_asset is None or not analog_assets:
            risks.append("No analog set was provided, limiting comparative scientific context.")
            return [], ScienceSubscore(name="analog_winners_failures_similarity", value=0.45, confidence=0.4, rationale="Nearest-neighbor analog support is unavailable.")

        scored: list[tuple[Asset, AssetSimilarityScore]] = []
        for analog in analog_assets:
            scored.append((analog, self.similarity_scorer.score(anchor_asset, analog)))
        scored.sort(key=lambda item: item[1].composite_score, reverse=True)
        top = scored[:3]
        analogs = [
            AnalogProgram(
                asset_id=asset.id,
                asset_name=asset.name,
                composite_score=score.composite_score,
                explanation=(
                    f"Indication {score.indication_overlap.score:.2f}, target {score.target_overlap.score:.2f}, "
                    f"MOA {score.moa_overlap.score:.2f}."
                ),
            )
            for asset, score in top
        ]
        mean_score = sum(score.composite_score for _, score in top) / len(top)
        if mean_score >= 0.65:
            positives.append("Comparable analog programs are meaningfully similar.")
        else:
            risks.append("Nearest analog programs are only moderately similar.")
        return analogs, ScienceSubscore(name="analog_winners_failures_similarity", value=round(mean_score, 4), confidence=0.72, rationale="Analog support is based on structured similarity across indication, target, MOA, modality, and stage.")

    def _score_safety_signal(self, dossier: AssetDossier, positives: list[str], risks: list[str], kill_criteria: list[str]) -> ScienceSubscore:
        safety = str(dossier.get_field_value("safety_profile_summary") or "")
        lowered = safety.lower()
        if not safety:
            risks.append("Safety summary is missing, reducing confidence in the downside case.")
            return ScienceSubscore(name="safety_signal_seriousness", value=0.48, confidence=0.45, rationale="Missing safety summary makes seriousness hard to bound.")
        if any(token in lowered for token in ("clean", "well tolerated", "manageable", "no grade 4", "no dose limiting")):
            positives.append("Safety language suggests manageable tolerability so far.")
            return ScienceSubscore(name="safety_signal_seriousness", value=0.78, confidence=0.75, rationale="Current safety language points to manageable tolerability.")
        if any(token in lowered for token in ("grade 4", "grade 5", "serious adverse", "black box", "toxicity", "death")):
            risks.append("Safety language contains material seriousness flags.")
            kill_criteria.append("Any confirmatory signal of serious toxicity should invalidate the thesis.")
            return ScienceSubscore(name="safety_signal_seriousness", value=0.22, confidence=0.78, rationale="Serious safety language is a major scientific and regulatory headwind.")
        return ScienceSubscore(name="safety_signal_seriousness", value=0.55, confidence=0.6, rationale="Safety profile is mixed or not crisply characterized.")

    def _score_trial_design(self, dossier: AssetDossier, positives: list[str], risks: list[str]) -> ScienceSubscore:
        if not dossier.active_trials:
            risks.append("No active trials are available to support design assessment.")
            return ScienceSubscore(name="trial_design_quality", value=0.3, confidence=0.45, rationale="No active trial data available.")

        trial = dossier.active_trials[0]
        score = 0.55
        rationale_parts: list[str] = []
        endpoint = str(trial.primary_endpoint or "").lower()
        if any(token in endpoint for token in ("os", "overall survival", "efs", "pfs")):
            score += 0.15
            rationale_parts.append("endpoint has recognizable regulatory precedent")
            positives.append("Primary endpoint has clearer precedent than a novel biomarker-only endpoint.")
        elif endpoint:
            rationale_parts.append("endpoint is present but not clearly a hard-precedent endpoint")

        if trial.enrollment_target >= 150:
            score += 0.12
            rationale_parts.append("enrollment is reasonably sized")
        elif 0 < trial.enrollment_target < 80:
            score -= 0.12
            rationale_parts.append("small enrollment increases fragility")
            risks.append("Enrollment size looks fragile for a differentiated design view.")

        status = str(trial.status).lower()
        if "recruiting" in status or "active" in status:
            score += 0.05
            rationale_parts.append("trial is active")
        elif "terminated" in status or "withdrawn" in status:
            score -= 0.25
            rationale_parts.append("trial status is a major negative")
            risks.append("Trial status directly weakens confidence in the design package.")

        score = max(0.0, min(1.0, score))
        return ScienceSubscore(
            name="trial_design_quality",
            value=round(score, 4),
            confidence=0.72,
            rationale=", ".join(rationale_parts) if rationale_parts else "baseline design-quality estimate",
        )
