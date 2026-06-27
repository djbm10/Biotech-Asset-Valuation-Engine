"""Deterministic builder for Layer 0 ScienceThesis objects.

Phase 2 intentionally keeps this builder boring and honest: absent evidence is
reported as missing evidence and diligence questions, not inferred into a
positive thesis.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from bve.intelligence.science_thesis import (
    BeliefState,
    ClinicalMeaningfulnessContext,
    EvidenceResolution,
    EvidenceResolutionBasis,
    SafetyRiskContext,
    ScienceComponentScore,
    ScienceMode,
    ScienceQuestion,
    ScienceThesis,
    ScienceThesisScoringInput,
    score_evidence_quality,
    score_science_thesis,
    EvidenceQualityFactors,
)


class ScienceThesisBuilderInput(BaseModel):
    asset_id: str
    asset_name: str = ""
    indication: str = ""
    phase: str = "phase2"
    modality: str = ""
    target: str = ""
    mechanism: str = ""
    science_assessment: object | None = None
    science_result: object | None = None
    has_target_rationale: bool = False
    has_pkpd_evidence: bool = False
    has_human_pkpd_evidence: bool = False
    has_biomarker_validation: bool = False
    has_human_poc: bool = False
    has_clinically_meaningful_effect: bool = False
    has_safety_signal: bool = False
    clinical_meaningfulness_context: ClinicalMeaningfulnessContext = Field(
        default_factory=ClinicalMeaningfulnessContext
    )
    safety_context: SafetyRiskContext = Field(default_factory=SafetyRiskContext)
    evidence_quality_factors: EvidenceQualityFactors = Field(default_factory=EvidenceQualityFactors)
    warnings: list[str] = Field(default_factory=list)
    additional_missing_evidence: list[str] = Field(default_factory=list)
    additional_evidence_gaps: list[str] = Field(default_factory=list)
    additional_diligence_questions: list[str] = Field(default_factory=list)


class ScienceThesisBuilder:
    """Build a conservative ScienceThesis from local structured context."""

    def from_existing_evidence(
        self,
        *,
        asset_dossier: object | None = None,
        science_assessment: object | None = None,
        science_result: object | None = None,
        science_evidence_bundle: object | None = None,
        explicit_inputs: ScienceThesisBuilderInput | None = None,
    ) -> ScienceThesis:
        """Build a thesis from existing repo evidence objects plus explicit overrides.

        Conservative precedence is: explicit true evidence > mapped evidence > missing.
        Ambiguous existing subscores create warnings rather than positive credit.
        """
        warnings: list[str] = []
        extracted = self._extract_identity_from_dossier(asset_dossier)
        assessment_flags = self._extract_components_from_science_assessment(science_assessment, warnings)
        result_flags = self._extract_components_from_science_result(science_result, warnings)
        bundle_extracted, bundle_flags, bundle_missing, bundle_gaps = (
            self._extract_components_from_science_evidence_bundle(
                science_evidence_bundle, warnings
            )
        )
        mapped = self._merge_flag_maps(assessment_flags, result_flags, bundle_flags)
        builder_input = self._merge_with_explicit_inputs(
            extracted={**extracted, **bundle_extracted},
            mapped=mapped,
            explicit_inputs=explicit_inputs,
            warnings=warnings,
            additional_missing_evidence=bundle_missing,
            additional_evidence_gaps=bundle_gaps,
        )
        return self.build(builder_input)

    def from_evidence_bundle(
        self,
        bundle: object,
        explicit_inputs: ScienceThesisBuilderInput | None = None,
    ) -> ScienceThesis:
        """Build a ScienceThesis from a typed evidence bundle only."""
        return self.from_existing_evidence(
            science_evidence_bundle=bundle,
            explicit_inputs=explicit_inputs,
        )

    def build(self, inputs: ScienceThesisBuilderInput) -> ScienceThesis:
        missing: list[str] = []
        gaps: list[str] = []
        diligence_questions: list[str] = []

        components = self._build_components(inputs, missing, gaps, diligence_questions)
        for item in inputs.additional_missing_evidence:
            if item not in missing:
                missing.append(item)
        for item in inputs.additional_evidence_gaps:
            if item not in gaps:
                gaps.append(item)
        for item in inputs.additional_diligence_questions:
            if item not in diligence_questions:
                diligence_questions.append(item)
        binding_question = self._binding_question(components)
        next_readout = self._next_readout_requirement(binding_question)

        thesis = ScienceThesis(
            asset_id=inputs.asset_id,
            asset_name=inputs.asset_name,
            indication=inputs.indication,
            phase=inputs.phase,
            modality=inputs.modality,
            mode=ScienceMode.DISCOVERY_INVESTMENT,
            core_biological_hypothesis=self._core_hypothesis(inputs),
            binding_science_question=binding_question,
            secondary_science_questions=self._secondary_questions(binding_question, components),
            what_must_be_true=self._what_must_be_true(inputs),
            expected_biomarker_changes=[],
            expected_clinical_changes=[],
            key_readouts=[next_readout],
            key_failure_modes=missing[:3],
            missing_critical_evidence=missing,
            evidence_gaps=gaps,
            must_answer_before_next_stage=missing[:],
            clinical_meaningfulness_context=inputs.clinical_meaningfulness_context,
            safety_context=inputs.safety_context,
            components=components,
            belief_state=BeliefState(prior_belief=0.5, current_belief=0.5),
            next_readout_requirement=next_readout,
            bd_diligence_questions=diligence_questions,
        )
        scored = score_science_thesis(ScienceThesisScoringInput(thesis=thesis))
        if scored.modifier_result is not None and inputs.warnings:
            modifier = scored.modifier_result.model_copy(
                update={"warnings": [*scored.modifier_result.warnings, *inputs.warnings]}
            )
            scored = scored.model_copy(update={"modifier_result": modifier})
        return scored

    def _extract_identity_from_dossier(self, asset_dossier: object | None) -> dict[str, str]:
        if asset_dossier is None:
            return {}
        identity = getattr(asset_dossier, "identity", None)
        science = getattr(asset_dossier, "science", None)
        trials = getattr(asset_dossier, "trials", None) or []
        first_trial = trials[0] if trials else None
        return {
            "asset_id": self._first_text(
                self._dossier_value(asset_dossier, "program_id"),
                self._dossier_value(asset_dossier, "asset_id"),
                self._dossier_value(identity, "asset_id"),
            ),
            "asset_name": self._first_text(
                self._dossier_value(asset_dossier, "asset_name"),
                self._dossier_value(asset_dossier, "name"),
                self._dossier_value(identity, "drug_name"),
            ),
            "indication": self._first_text(
                self._dossier_value(asset_dossier, "indication"),
                self._dossier_value(identity, "indication"),
            ),
            "phase": self._first_text(
                self._dossier_value(asset_dossier, "current_phase"),
                self._dossier_value(asset_dossier, "phase"),
                self._dossier_value(asset_dossier, "stage"),
                self._dossier_value(first_trial, "phase"),
            ),
            "modality": self._first_text(
                self._dossier_value(asset_dossier, "modality"),
                self._dossier_value(identity, "modality"),
            ),
            "target": self._first_text(
                self._dossier_value(asset_dossier, "target"),
                self._dossier_value(science, "target"),
            ),
            "mechanism": self._first_text(
                self._dossier_value(asset_dossier, "mechanism_of_action"),
                self._dossier_value(asset_dossier, "mechanism"),
                self._dossier_value(science, "mechanism_summary"),
            ),
        }

    def _dossier_value(self, obj: object | None, field_name: str) -> object | None:
        if obj is None:
            return None
        get_field_value = getattr(obj, "get_field_value", None)
        if callable(get_field_value):
            value = get_field_value(field_name)
            if value is not None:
                return self._unwrap_value(value)
        return self._unwrap_value(getattr(obj, field_name, None))

    def _unwrap_value(self, value: object | None) -> object | None:
        if value is None:
            return None
        return getattr(value, "value", value)

    def _first_text(self, *values: object | None) -> str:
        for value in values:
            unwrapped = self._unwrap_value(value)
            if unwrapped is not None and str(unwrapped):
                return str(unwrapped)
        return ""

    def _extract_components_from_science_assessment(
        self, science_assessment: object | None, warnings: list[str]
    ) -> dict[str, bool]:
        flags = self._empty_flags()
        if science_assessment is None:
            return flags
        for subscore in getattr(science_assessment, "subscores", []) or []:
            self._map_existing_subscore(
                name=str(getattr(subscore, "name", "")),
                rationale=str(getattr(subscore, "rationale", "")),
                score=float(getattr(subscore, "value", 0.0)),
                flags=flags,
                warnings=warnings,
            )
        design_score = getattr(science_assessment, "design_score", None)
        if design_score is not None:
            flags["has_clinically_meaningful_effect"] = flags["has_clinically_meaningful_effect"] or False
            warnings.append("design_score_not_human_poc")
        return flags

    def _extract_components_from_science_result(
        self, science_result: object | None, warnings: list[str]
    ) -> dict[str, bool]:
        flags = self._empty_flags()
        if science_result is None:
            return flags
        for subscore in getattr(science_result, "sub_scores", {}) or {}:
            value = getattr(science_result, "sub_scores", {}).get(subscore)
            self._map_existing_subscore(
                name=str(getattr(value, "name", subscore)),
                rationale=str(getattr(value, "rationale", "")),
                score=float(getattr(value, "score", 0.0)),
                flags=flags,
                warnings=warnings,
            )
        return flags

    def _map_existing_subscore(
        self,
        *,
        name: str,
        rationale: str,
        score: float,
        flags: dict[str, bool],
        warnings: list[str],
    ) -> None:
        if score < 0.6:
            return
        name_l = name.lower()
        rationale_l = rationale.lower()
        text = f"{name_l} {rationale_l}"
        if "mechanism" in name_l or "target" in name_l or "analog" in name_l:
            flags["has_target_rationale"] = True
        elif "biomarker" in name_l:
            flags["has_biomarker_validation"] = True
        elif "translational" in name_l:
            if any(term in text for term in ["exposure", "pk", "pd", "dose", "tissue", "target engagement", "delivery"]):
                flags["has_pkpd_evidence"] = True
                if "human" in text or "clinical" in text:
                    flags["has_human_pkpd_evidence"] = True
            elif any(term in text for term in ["biomarker", "bridge", "translation", "clinical benefit"]):
                flags["has_biomarker_validation"] = True
            else:
                warnings.append("ambiguous_existing_science_subscore_mapping")
        elif "safety" in name_l:
            flags["has_safety_signal"] = score < 0.5
        elif "endpoint" in name_l:
            flags["has_clinically_meaningful_effect"] = True
        elif "trial_design" in name_l or "trial design" in name_l:
            warnings.append("design_score_not_human_poc")
        else:
            warnings.append("ambiguous_existing_science_subscore_mapping")

    def _merge_with_explicit_inputs(
        self,
        *,
        extracted: dict[str, str],
        mapped: dict[str, bool],
        explicit_inputs: ScienceThesisBuilderInput | None,
        warnings: list[str],
        additional_missing_evidence: list[str] | None = None,
        additional_evidence_gaps: list[str] | None = None,
    ) -> ScienceThesisBuilderInput:
        additional_missing_evidence = additional_missing_evidence or []
        additional_evidence_gaps = additional_evidence_gaps or []
        if explicit_inputs is None:
            return ScienceThesisBuilderInput(
                **{
                    "asset_id": "unknown_asset",
                    **extracted,
                    **mapped,
                    "warnings": warnings,
                    "additional_missing_evidence": additional_missing_evidence,
                    "additional_evidence_gaps": additional_evidence_gaps,
                }
            )

        explicit_data = explicit_inputs.model_dump()
        for key, mapped_value in mapped.items():
            explicit_value = explicit_data.get(key)
            if key in explicit_inputs.model_fields_set and explicit_value is False and mapped_value is True:
                warnings.append("conflicting_existing_science_evidence")
            explicit_data[key] = bool(explicit_value or mapped_value)
        for key, value in extracted.items():
            if not explicit_data.get(key) and value:
                explicit_data[key] = value
        explicit_data["warnings"] = [*explicit_inputs.warnings, *warnings]
        explicit_data["additional_missing_evidence"] = [
            *explicit_data.get("additional_missing_evidence", []),
            *additional_missing_evidence,
        ]
        explicit_data["additional_evidence_gaps"] = [
            *explicit_data.get("additional_evidence_gaps", []),
            *additional_evidence_gaps,
        ]
        return ScienceThesisBuilderInput.model_validate(explicit_data)

    def _merge_flag_maps(self, *flag_maps: dict[str, bool]) -> dict[str, bool]:
        merged = self._empty_flags()
        for flag_map in flag_maps:
            for key, value in flag_map.items():
                merged[key] = merged[key] or value
        return merged


    def _extract_components_from_science_evidence_bundle(
        self,
        bundle: object | None,
        warnings: list[str],
    ) -> tuple[dict[str, str], dict[str, bool], list[str], list[str]]:
        flags = self._empty_flags()
        if bundle is None:
            return {}, flags, [], []

        try:
            from bve.intelligence.science_evidence import (
                ScienceEvidenceDirection,
                ScienceEvidenceMappedComponent,
                ScienceEvidenceMappedField,
            )
        except Exception:  # pragma: no cover - defensive import guard
            return {}, flags, [], []

        extracted = {
            "asset_id": str(getattr(bundle, "asset_id", "") or ""),
            "asset_name": str(getattr(bundle, "asset_name", "") or ""),
            "indication": str(getattr(bundle, "indication", "") or ""),
            "phase": str(getattr(bundle, "phase", "") or ""),
            "modality": str(getattr(bundle, "modality", "") or ""),
            "target": str(getattr(bundle, "target", "") or ""),
            "mechanism": str(getattr(bundle, "mechanism", "") or ""),
        }
        extracted = {key: value for key, value in extracted.items() if value}
        missing = list(getattr(bundle, "unresolved_gaps", []) or [])
        gaps = list(getattr(bundle, "unresolved_gaps", []) or [])
        warnings.extend(getattr(bundle, "bundle_warnings", []) or [])

        for item in getattr(bundle, "items", []) or []:
            item_warnings = list(getattr(item, "warnings", []) or [])
            warnings.extend(item_warnings)
            confidence = float(getattr(item, "confidence", 0.0) or 0.0)
            direction = getattr(item, "direction", None)
            component = getattr(item, "mapped_component", None)
            mapped_field = getattr(item, "mapped_field", None)
            evidence_id = str(getattr(item, "evidence_id", "") or "unknown")

            if mapped_field == ScienceEvidenceMappedField.UNSUPPORTED:
                warnings.append("unsupported_extracted_science_claim")
                continue
            if direction in {
                ScienceEvidenceDirection.AMBIGUOUS,
                ScienceEvidenceDirection.MISSING,
            }:
                warnings.append("ambiguous_extracted_science_evidence")
                continue
            if confidence < 0.4:
                warnings.append("low_confidence_extracted_science_evidence")
                continue
            if direction == ScienceEvidenceDirection.NEGATIVE:
                if component == ScienceEvidenceMappedComponent.S:
                    flags["has_safety_signal"] = True
                else:
                    warnings.append("negative_extracted_science_evidence")
                continue
            if direction != ScienceEvidenceDirection.SUPPORTIVE:
                warnings.append("ambiguous_extracted_science_evidence")
                continue
            if confidence < 0.6:
                warnings.append("low_confidence_extracted_science_evidence")
                continue

            if component == ScienceEvidenceMappedComponent.T:
                flags["has_target_rationale"] = True
            elif component == ScienceEvidenceMappedComponent.D:
                if mapped_field in {
                    ScienceEvidenceMappedField.PKPD,
                    ScienceEvidenceMappedField.EXPOSURE,
                    ScienceEvidenceMappedField.TISSUE_DELIVERY,
                    ScienceEvidenceMappedField.TARGET_ENGAGEMENT,
                    ScienceEvidenceMappedField.DOSE_RESPONSE,
                    ScienceEvidenceMappedField.EXPOSURE_RESPONSE,
                }:
                    flags["has_pkpd_evidence"] = True
                    if self._evidence_item_is_human(item):
                        flags["has_human_pkpd_evidence"] = True
                else:
                    warnings.append("ambiguous_extracted_science_evidence")
            elif component == ScienceEvidenceMappedComponent.B:
                flags["has_biomarker_validation"] = True
            elif component == ScienceEvidenceMappedComponent.H:
                if mapped_field in {
                    ScienceEvidenceMappedField.HUMAN_POC,
                    ScienceEvidenceMappedField.EFFICACY_SIGNAL,
                }:
                    flags["has_human_poc"] = True
                else:
                    warnings.append("design_score_not_human_poc")
            elif component == ScienceEvidenceMappedComponent.M:
                flags["has_clinically_meaningful_effect"] = True
            elif component == ScienceEvidenceMappedComponent.S:
                # Supportive safety margin evidence should not be converted into
                # an observed safety signal; negative S evidence handled above.
                continue
            elif component == ScienceEvidenceMappedComponent.Q:
                if mapped_field == ScienceEvidenceMappedField.TRIAL_DESIGN:
                    warnings.append("design_score_not_human_poc")
                else:
                    warnings.append("evidence_quality_extracted_not_direct_science_credit")
            else:
                warnings.append(f"unmapped_science_evidence:{evidence_id}")

        return extracted, flags, missing, gaps

    def _evidence_item_is_human(self, item: object) -> bool:
        from bve.intelligence.science_evidence import ScienceEvidenceSourceType

        source_type = getattr(item, "source_type", None)
        if source_type in {
            ScienceEvidenceSourceType.CLINICAL_READOUT,
            ScienceEvidenceSourceType.CLINICAL_TRIAL_REGISTRY,
        }:
            return True
        text = " ".join(
            str(getattr(item, attr, "") or "")
            for attr in ("quote", "text_span", "rationale", "section")
        ).lower()
        return any(term in text for term in ["human", "clinical", "patient", "phase 1", "phase 2"])

    def _empty_flags(self) -> dict[str, bool]:
        return {
            "has_target_rationale": False,
            "has_pkpd_evidence": False,
            "has_human_pkpd_evidence": False,
            "has_biomarker_validation": False,
            "has_human_poc": False,
            "has_clinically_meaningful_effect": False,
            "has_safety_signal": False,
        }

    def _build_components(
        self,
        inputs: ScienceThesisBuilderInput,
        missing: list[str],
        gaps: list[str],
        diligence_questions: list[str],
    ) -> dict[str, ScienceComponentScore]:
        target_score = 0.65 if inputs.has_target_rationale else 0.40
        target_conf = 0.65 if inputs.has_target_rationale else 0.35
        if not inputs.has_target_rationale:
            self._add_gap(
                missing,
                gaps,
                diligence_questions,
                "target/pathway causal rationale",
                "Confirm target/pathway causal relevance in this indication.",
            )

        dose_score = 0.65 if inputs.has_pkpd_evidence else 0.35
        dose_conf = 0.70 if inputs.has_human_pkpd_evidence else (0.45 if inputs.has_pkpd_evidence else 0.25)
        dose_resolution = EvidenceResolution.PARTIALLY_RESOLVED if inputs.has_pkpd_evidence else EvidenceResolution.UNRESOLVED
        dose_basis = (
            EvidenceResolutionBasis.HUMAN_PKPD
            if inputs.has_human_pkpd_evidence
            else EvidenceResolutionBasis.PRECLINICAL
            if inputs.has_pkpd_evidence
            else EvidenceResolutionBasis.UNSPECIFIED
        )
        if not inputs.has_pkpd_evidence:
            self._add_gap(
                missing,
                gaps,
                diligence_questions,
                "PK/PD or exposure evidence",
                "Verify exposure, target engagement, and dose-response at feasible exposure.",
            )

        biomarker_score = 0.65 if inputs.has_biomarker_validation else 0.35
        biomarker_conf = 0.65 if inputs.has_biomarker_validation else 0.25
        if not inputs.has_biomarker_validation:
            self._add_gap(
                missing,
                gaps,
                diligence_questions,
                "biomarker/translational validation",
                "Determine whether biomarker is proximal to mechanism and predicts clinical benefit.",
            )

        human_score = 0.70 if inputs.has_human_poc else 0.35
        human_conf = 0.70 if inputs.has_human_poc else 0.25
        if not inputs.has_human_poc:
            self._add_gap(
                missing,
                gaps,
                diligence_questions,
                "human proof-of-concept",
                "Identify whether human data show clinically interpretable proof-of-concept.",
            )

        meaningful_score = 0.65 if inputs.has_clinically_meaningful_effect else 0.40
        meaningful_conf = 0.65 if inputs.has_clinically_meaningful_effect else 0.30
        if not inputs.has_clinically_meaningful_effect:
            self._add_gap(
                missing,
                gaps,
                diligence_questions,
                "clinical meaningfulness versus standard of care",
                "Benchmark effect size against standard of care and competitive threshold.",
            )

        safety_score = 0.45 if inputs.has_safety_signal else 0.60
        safety_conf = 0.60 if inputs.has_safety_signal else 0.45
        if inputs.has_safety_signal:
            diligence_questions.append("Determine whether safety signal is mechanism-linked and dose limiting.")

        q_component = score_evidence_quality(inputs.evidence_quality_factors)
        return {
            "T": ScienceComponentScore(
                name="T",
                score=target_score,
                confidence=target_conf,
                resolution=EvidenceResolution.PARTIALLY_RESOLVED if inputs.has_target_rationale else EvidenceResolution.UNRESOLVED,
                rationale="Target/pathway score from explicit target rationale only.",
            ),
            "D": ScienceComponentScore(
                name="D",
                score=dose_score,
                confidence=dose_conf,
                resolution=dose_resolution,
                resolution_basis=dose_basis,
                rationale="Dose/exposure score requires explicit PK/PD or exposure evidence.",
            ),
            "B": ScienceComponentScore(
                name="B",
                score=biomarker_score,
                confidence=biomarker_conf,
                resolution=EvidenceResolution.PARTIALLY_RESOLVED if inputs.has_biomarker_validation else EvidenceResolution.UNRESOLVED,
                rationale="Biomarker score requires explicit translational validation.",
            ),
            "H": ScienceComponentScore(
                name="H",
                score=human_score,
                confidence=human_conf,
                resolution=EvidenceResolution.PARTIALLY_RESOLVED if inputs.has_human_poc else EvidenceResolution.UNRESOLVED,
                resolution_basis=EvidenceResolutionBasis.HUMAN_CLINICAL_POC if inputs.has_human_poc else EvidenceResolutionBasis.UNSPECIFIED,
                rationale="Human POC score requires explicit human evidence.",
            ),
            "M": ScienceComponentScore(
                name="M",
                score=meaningful_score,
                confidence=meaningful_conf,
                resolution=EvidenceResolution.PARTIALLY_RESOLVED if inputs.has_clinically_meaningful_effect else EvidenceResolution.UNRESOLVED,
                rationale="Clinical meaningfulness score requires standard-of-care or competitor context.",
            ),
            "S": ScienceComponentScore(
                name="S",
                score=safety_score,
                confidence=safety_conf,
                resolution=EvidenceResolution.UNRESOLVED,
                rationale="Safety score is conservative absent clean observed safety context.",
            ),
            "Q": q_component,
        }

    def _binding_question(self, components: dict[str, ScienceComponentScore]) -> ScienceQuestion:
        component_to_question = {
            "T": ScienceQuestion.RIGHT_TARGET,
            "D": ScienceQuestion.ENOUGH_DRUG,
            "B": ScienceQuestion.BIOMARKER_TRANSLATION,
            "H": ScienceQuestion.HUMAN_POC,
            "M": ScienceQuestion.CLINICAL_MEANINGFULNESS,
            "S": ScienceQuestion.SAFETY_MARGIN,
        }
        key = min(component_to_question, key=lambda item: components[item].score)
        return component_to_question[key]

    def _secondary_questions(
        self, binding_question: ScienceQuestion, components: dict[str, ScienceComponentScore]
    ) -> list[ScienceQuestion]:
        question_by_component = {
            "T": ScienceQuestion.RIGHT_TARGET,
            "D": ScienceQuestion.ENOUGH_DRUG,
            "B": ScienceQuestion.BIOMARKER_TRANSLATION,
            "H": ScienceQuestion.HUMAN_POC,
            "M": ScienceQuestion.CLINICAL_MEANINGFULNESS,
            "S": ScienceQuestion.SAFETY_MARGIN,
        }
        questions = [
            question
            for key, question in question_by_component.items()
            if components[key].score < 0.50 and question != binding_question
        ]
        return questions

    def _next_readout_requirement(self, binding_question: ScienceQuestion) -> str:
        readouts = {
            ScienceQuestion.RIGHT_TARGET: "Show target/pathway causal relevance in the intended disease context.",
            ScienceQuestion.ENOUGH_DRUG: "Show dose-dependent target engagement at tolerable human exposure.",
            ScienceQuestion.BIOMARKER_TRANSLATION: "Show biomarker movement is proximal to mechanism and bridges to clinical benefit.",
            ScienceQuestion.HUMAN_POC: "Show interpretable human proof-of-concept with adequate design and dose.",
            ScienceQuestion.CLINICAL_MEANINGFULNESS: "Show effect size is clinically meaningful versus standard of care and competitors.",
            ScienceQuestion.SAFETY_MARGIN: "Show safety margin is acceptable at efficacious exposure.",
        }
        return readouts[binding_question]

    def _core_hypothesis(self, inputs: ScienceThesisBuilderInput) -> str:
        target = inputs.target or "the target/pathway"
        indication = inputs.indication or "the intended indication"
        mechanism = inputs.mechanism or "the proposed mechanism"
        return f"{mechanism} via {target} can produce clinically meaningful benefit in {indication}."

    def _what_must_be_true(self, inputs: ScienceThesisBuilderInput) -> list[str]:
        target = inputs.target or "target/pathway"
        return [
            f"{target} is causally relevant to the disease biology.",
            "The drug reaches the relevant tissue/cell at a feasible and safe exposure.",
            "Biomarker or translational evidence bridges mechanism to clinical benefit.",
            "Observed or expected clinical effect is meaningful versus standard of care.",
        ]

    def _add_gap(
        self,
        missing: list[str],
        gaps: list[str],
        diligence_questions: list[str],
        evidence_name: str,
        diligence_question: str,
    ) -> None:
        missing.append(evidence_name)
        gaps.append(f"Missing {evidence_name}.")
        diligence_questions.append(diligence_question)
