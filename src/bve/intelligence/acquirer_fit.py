"""Deterministic acquirer-fit scoring built on curated acquirer profiles."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import re
from typing import Optional

from bve.normalization.registries import lookup_indication

from pydantic import BaseModel, Field, model_validator

from bve.intelligence.acquirer_profiles import AcquirerProfile, AcquirerProfileLoader
from bve.intelligence.acquisition_screen import (
    DEFAULT_ACQUISITION_THRESHOLD,
    AcquisitionScreenConfig,
    AcquisitionScreenRow,
    AcquisitionScreener,
)
from bve.intelligence.comparable_deals import (
    ComparableDeal,
    ComparableDealAnalysis,
    ComparableDealLoader,
    ComparableDealMatcher,
)
from bve.analysis.deal_premium import DealPremiumEngine
from bve.analysis.synergy_graph import (
    SynergyAssetProfile,
    score_acquirer_portfolio_fit,
)

_LATE_STAGE = {"phase_3", "nda_bla", "approved", "commercial"}
_PRE_PHASE_2 = {"preclinical", "phase_1"}
_NEUTRAL_SCORE = 0.45

_CATEGORY_ALIASES: dict[str, set[str]] = {
    "ophthalmology": {"ophthalmology", "retina", "retinal", "ocular", "eye"},
    "immunology": {
        "immunology",
        "inflammation",
        "autoimmune",
        "dermatology",
        "atopic",
        "lupus",
        "vasculitis",
        "colitis",
        "crohn",
        "crohn's",
        "ulcerative colitis",
        "ibd",
    },
    "inflammatory_bowel_disease": {
        "ibd",
        "ulcerative colitis",
        "crohn",
        "crohn's",
        "colitis",
        "intestinal inflammation",
    },
    "obesity": {"obesity", "metabolic", "weight", "cardiometabolic", "glp1", "gip"},
    "kidney_disease": {
        "kidney",
        "renal",
        "nephrology",
        "nephropathy",
        "iga nephropathy",
        "igan",
        "proteinuria",
    },
    "liver_disease": {
        "liver",
        "hepatic",
        "hepatology",
        "hepatitis",
        "pbc",
        "primary biliary cholangitis",
        "mash",
        "nash",
        "fibrosis",
    },
    "respiratory": {
        "respiratory",
        "copd",
        "asthma",
        "pulmonary",
        "cough",
        "bronch",
        "lung",
    },
    "neuroscience": {
        "neuroscience",
        "cns",
        "schizophrenia",
        "depression",
        "anxiety",
        "alzheimers",
        "parkinsons",
        "migraine",
        "neurology",
        "neurological",
    },
    "neuropsychiatry": {"schizophrenia", "psychosis", "depression", "anxiety", "neuropsychiatry"},
    "vaccines": {"vaccine", "vaccines", "vaccination", "rsv", "influenza", "flu", "mrna"},
    "radiopharmaceutical": {
        "radiopharmaceutical",
        "radioligand",
        "radioligand therapy",
        "lutetium",
        "actinium",
        "isotope",
        "radiopharma",
        "rlt",
        "targeted radionuclide",
        "alpha therapy",
        "beta emitter",
    },
    "genetic_medicine": {
        "genetic",
        "genetics",
        "gene",
        "gene therapy",
        "aav",
        "editing",
        "rna",
        "oligo",
        "sirna",
        "rnai",
        "antisense",
        "oligonucleotide",
        "mrna therapy",
    },
    "sirna_rnai": {
        "sirna",
        "rnai",
        "rna interference",
        "antisense",
        "antisense oligonucleotide",
        "aso",
        "oligonucleotide",
        "rna silencing",
    },
    "fully_human_antibody": {"antibody", "monoclonal", "mab", "immunoglobulin", "igg"},
    "monoclonal_antibody": {"monoclonal antibody", "mab", "antibody", "immunoglobulin", "igg"},
    "fusion_protein": {"fusion protein", "trap", "receptor trap", "aflibercept", "etanercept"},
    "bispecific_antibody": {"bispecific", "antibody", "xcd3", "xcd28", "t cell engager", "t-cell engager"},
    "cell_therapy": {"cell", "car t", "cart", "tcr", "allogeneic", "autologous"},
    "data_genomics_platform": {"data", "genomics", "database", "biobank", "platform", "sequencing"},
    "oncology": {
        "oncology",
        "cancer",
        "tumor",
        "hematology",
        "radiopharma",
        "radioligand",
        "solid tumor",
        "lymphoma",
        "leukemia",
        "myeloma",
    },
    "rare_disease": {"rare", "orphan", "hearing", "ultra rare", "lysosomal storage"},
}

_EXPOSURE_LEVEL_SCORES = {
    "high": 1.0,
    "medium": 0.8,
    "low": 0.6,
}

_PREFERENCE_STRENGTH_SCORES = {
    "high": 1.0,
    "medium": 0.75,
    "low": 0.5,
}

_GENERIC_SIGNAL_TOKENS = {
    "a",
    "and",
    "an",
    "additional",
    "adjacency",
    "adjacent",
    "announcement",
    "approximately",
    "are",
    "around",
    "asset",
    "assets",
    "autoimmune",
    "bio",
    "biopharma",
    "bolt",
    "boltons",
    "bolt-on",
    "buildout",
    "but",
    "by",
    "capability",
    "capabilities",
    "cash",
    "category",
    "categories",
    "clinical",
    "combination",
    "combinations",
    "commercial",
    "completed",
    "condition",
    "conditions",
    "concrete",
    "costs",
    "deal",
    "deals",
    "described",
    "disease",
    "diseases",
    "disclosed",
    "diluted",
    "disorder",
    "disorders",
    "entry",
    "established",
    "enterprise",
    "equity",
    "extension",
    "explicit",
    "follow",
    "follow-on",
    "followon",
    "for",
    "from",
    "expansion",
    "franchise",
    "gen",
    "growth",
    "interest",
    "into",
    "is",
    "later",
    "leadership",
    "maintenance",
    "malignancies",
    "malignancy",
    "medicine",
    "medicines",
    "most",
    "next",
    "of",
    "or",
    "on",
    "platform",
    "plausible",
    "portfolio",
    "pre",
    "pre-commercial",
    "precommercial",
    "precision",
    "program",
    "programs",
    "registrational",
    "relevant",
    "remain",
    "remains",
    "signed",
    "selective",
    "stage",
    "strategic",
    "style",
    "syndrome",
    "syndromes",
    "the",
    "target",
    "targeted",
    "targeting",
    "therapeutic",
    "therapeutics",
    "therapy",
    "treatment",
    "used",
    "value",
    "willingness",
    "with",
}

_SUBAREA_SIGNAL_ALIASES: dict[str, set[str]] = {
    "aldosterone_synthase_resistant_htn": {
        "aldosterone synthase",
        "baxdrostat",
    },
    "alzheimers_disease_next_gen": {"alzheimers", "amyloid", "tau"},
    "bet_epigenetic_myelofibrosis": {"bet", "bromodomain", "epigenetic", "myelofibrosis"},
    "breast_cancer": {"breast cancer", "hr positive", "her2", "cdk"},
    "celmod_myeloma_degrader": {"celmod", "cereblon", "degrader", "myeloma", "plasma cell"},
    "cd47_macrophage_heme_io": {
        "cd47",
        "hematologic malignancies",
        "hematologic",
        "hematology",
        "heme",
        "lymphoma",
        "leukemia",
        "macrophage",
    },
    "copd_commercial_respiratory": {
        "copd",
        "maintenance",
        "bronchodilator",
    },
    "igan_kidney_fibrosis": {"iga nephropathy", "igan", "kidney fibrosis", "renal"},
    "inflammatory_bowel_disease": {
        "ibd",
        "ulcerative colitis",
        "crohn",
        "crohn's",
    },
    "migraine_cgrp": {"migraine", "cgrp"},
    "momelotinib_jak_mpn": {"jak", "momelotinib", "mpn"},
    "mpn_myelofibrosis_lsd1_heme": {
        "essential thrombocythemia",
        "et",
        "hematology",
        "heme",
        "lsd1",
        "mpn",
        "myelofibrosis",
    },
    "neuromuscular_rna_oligo_gene_editing": {
        "duchenne",
        "facioscapulohumeral",
        "fshd",
        "muscular dystrophy",
        "myotonic dystrophy",
        "neuromuscular",
    },
    "nsclc_ros1_alk_trk_kinase": {"alk", "kras", "nsclc", "ros1", "trk"},
    "neuropsychiatry_cns": {"schizophrenia", "psychosis", "depression", "mdd", "anxiety"},
    "oral_glp1": {"glp1", "glp-1", "gip", "oral glp-1", "obesity", "metabolic"},
    "precision_oncology_kinase": {"alk", "kras", "nsclc", "ros1", "trk"},
    "pulmonary_arterial_hypertension": {
        "actrii",
        "pah",
        "pulmonary arterial hypertension",
        "sotatercept",
    },
    "t_cell_engager_bispecific_io": {
        "bispecific",
        "cd3",
        "neuroendocrine",
        "small cell lung cancer",
        "sclc",
        "t cell engager",
        "t-cell engager",
    },
    "tl1a_ibd": {"tl1a", "pra023", "prometheus"},
    "geographic_atrophy_non_vegf": {
        "geographic atrophy",
        "ga complement",
        "complement inhibitor",
        "c1q",
        "c3 inhibitor",
        "htra1",
        "drusen",
        "rpe atrophy",
        "non vegf retinal",
        "complement mediated retinal",
    },
    "muscle_sparing_anabolic": {
        "myostatin",
        "gdf8",
        "activin",
        "activin receptor",
        "lean mass",
        "muscle preservation",
        "sarcopenia",
        "anabolic",
        "muscle sparing",
        "fat free mass",
    },
    "io_combination_warhead": {
        "radiopharma",
        "radioligand",
        "lutetium",
        "actinium",
        "warhead",
        "solid tumor io",
        "bispecific io",
        "payload delivery",
        "tumor targeting",
    },
    "oral_type2_inflammation": {
        "tyk2",
        "jak1 selective",
        "type 2 inflammation",
        "oral atopic",
        "oral il 4",
        "oral il 13",
        "thymic stromal",
        "tslp oral",
    },
    "anticoagulation_factor_xi_or_heme_onc_bispecific": {
        "fxi",
        "factor xi",
        "thrombosis",
        "anticoagulant",
        "clotting factor",
        "thromboembolic",
        "multiple myeloma bispecific",
        "b cell lymphoma bispecific",
    },
    "rgc_validated_targets": {
        "genetics validated",
        "rare genetic",
        "monogenic",
        "loss of function",
        "gain of function variant",
        "hereditary",
        "aadc",
        "ornithine",
    },
    "sirna_gene_silencing": {
        "sirna",
        "rnai",
        "rna interference",
        "rna silencing",
        "lipid nanoparticle sirna",
    },
}

SCORE_VERSIONS: dict[str, dict[str, float]] = {
    "v1.0": {
        "therapeutic_area": 0.25,
        "modality": 0.20,
        "stage": 0.15,
        "strategic_priority": 0.15,
        "valuation": 0.10,
        "budget": 0.15,
    }
}


def _normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = getattr(value, "value", value)
    normalized = str(value).strip().lower().replace("'", "")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = " ".join(normalized.split())
    return normalized or None


def _normalize_stage(value: Optional[str]) -> Optional[str]:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    mapping = {
        "phase 1": "phase_1",
        "phase i": "phase_1",
        "phase 2": "phase_2",
        "phase ii": "phase_2",
        "phase 3": "phase_3",
        "phase iii": "phase_3",
        "nda bla": "nda_bla",
        "nda/bla": "nda_bla",
        "filing": "nda_bla",
    }
    return mapping.get(normalized, normalized.replace(" ", "_"))


def _signal_tokens(value: Optional[str], *, include_category_aliases: bool = True) -> set[str]:
    normalized = _normalize_text(value)
    if normalized is None:
        return set()

    tokens = {
        token
        for token in normalized.split()
        if len(token) > 1 and token not in _GENERIC_SIGNAL_TOKENS and not token.isdigit()
    }
    tokens.add(normalized)
    if not include_category_aliases:
        return tokens

    for category, aliases in _CATEGORY_ALIASES.items():
        if category.replace("_", " ") in normalized:
            tokens.add(category)
            continue
        if any(alias in normalized for alias in aliases):
            tokens.add(category)
    return tokens


def _specific_signal_tokens(*values: Optional[str]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        normalized = _normalize_text(value)
        if normalized is None:
            continue
        matched_aliases = None
        for alias_key, alias_values in _SUBAREA_SIGNAL_ALIASES.items():
            if _normalize_text(alias_key) == normalized:
                matched_aliases = alias_values
                break
        if matched_aliases is None:
            tokens.update(_signal_tokens(normalized, include_category_aliases=False))
            continue
        for alias in matched_aliases:
            tokens.update(_signal_tokens(alias, include_category_aliases=False))
    return tokens


class AcquirerFitConfig(BaseModel):
    """Configurable scoring contract for acquirer-fit analysis."""

    score_version: str = "v1.0"
    require_acquisition_readiness: bool = True
    hard_fail_penalty_multiplier: float = Field(default=0.15, ge=0.0, le=1.0)
    comfortable_budget_to_net_cash: float = Field(default=0.50, gt=0.0)
    stretch_budget_to_net_cash: float = Field(default=1.00, gt=0.0)
    max_budget_to_net_cash: float = Field(default=1.25, gt=0.0)

    @model_validator(mode="after")
    def _validate_budget_ordering(self) -> "AcquirerFitConfig":
        if self.comfortable_budget_to_net_cash > self.stretch_budget_to_net_cash:
            raise ValueError("comfortable_budget_to_net_cash must be <= stretch_budget_to_net_cash")
        if self.stretch_budget_to_net_cash > self.max_budget_to_net_cash:
            raise ValueError("stretch_budget_to_net_cash must be <= max_budget_to_net_cash")
        return self

    def resolved_weights(self) -> dict[str, float]:
        try:
            return dict(SCORE_VERSIONS[self.score_version])
        except KeyError as exc:
            raise ValueError(
                f"Unknown score version {self.score_version!r}. Valid: {sorted(SCORE_VERSIONS)}"
            ) from exc


class AcquirerFitCandidate(BaseModel):
    """Normalized target context used by the acquirer-fit scorer."""

    asset_id: str
    company_id: str | None = None
    company_name: str | None = None
    ticker: str | None = None
    therapeutic_area: str | None = None
    indication: str | None = None
    modality: str | None = None
    stage: str | None = None
    model_rnpv_millions: float | None = None
    enterprise_value_millions: float | None = None
    acquisition_discount: float | None = None
    acquisition_ready: bool | None = None
    acquisition_readiness_bucket: str | None = None
    ev_to_peak_sales: float | None = Field(default=None, ge=0.0)
    priority_tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @classmethod
    def from_acquisition_row(
        cls,
        row,
        *,
        modality: Optional[str] = None,
        priority_tags: Optional[list[str]] = None,
        company_name: Optional[str] = None,
    ) -> "AcquirerFitCandidate":
        return cls(
            asset_id=row.asset_id,
            company_id=getattr(row, "company_id", None),
            company_name=company_name,
            ticker=getattr(row, "ticker", None),
            therapeutic_area=getattr(row, "therapeutic_area", None),
            indication=getattr(row, "indication", None),
            modality=modality,
            stage=getattr(row, "stage", None),
            model_rnpv_millions=getattr(row, "model_rnpv_millions", None),
            enterprise_value_millions=getattr(row, "enterprise_value_millions", None),
            acquisition_discount=getattr(row, "acquisition_discount", None),
            acquisition_ready=getattr(row, "acquisition_ready", None),
            acquisition_readiness_bucket=getattr(row, "acquisition_readiness_bucket", None),
            ev_to_peak_sales=getattr(row, "ev_to_peak_sales", None),
            priority_tags=list(priority_tags or []),
        )


class AcquirerFitScore(BaseModel):
    """Scored fit output for one target versus one acquirer."""

    acquirer_id: str
    asset_id: str
    ticker: str | None = None
    company_name: str | None = None
    score_version: str

    raw_fit_score: float
    fit_score: float
    passes_hard_filters: bool

    therapeutic_area_score: float
    modality_score: float
    stage_score: float
    strategic_priority_score: float
    valuation_score: float
    budget_score: float

    therapeutic_area_component: float
    modality_component: float
    stage_component: float
    strategic_priority_component: float
    valuation_component: float
    budget_component: float

    hard_fail_reasons: list[str] = Field(default_factory=list)
    matched_therapeutic_gap: str | None = None
    matched_modality: str | None = None
    matched_priorities: list[str] = Field(default_factory=list)
    matched_partnership_target: str | None = None

    valuation_source: str
    valuation_reference_median_ev_to_peak_sales: float | None = None
    valuation_reference_band_low_millions: float | None = None
    valuation_reference_band_high_millions: float | None = None

    budget_capacity_millions: float | None = None
    budget_required_millions: float | None = None
    budget_headroom_millions: float | None = None

    explanation: str


class AcquirerFitIntegrationConfig(BaseModel):
    """Config for scoring a screened target universe against one acquirer."""

    acquirer_profiles_path: str = "examples/research/acquirer_profiles"
    comparable_deals_path: str = "research/mna/comparable_deals.yaml"
    top_n: int = Field(default=25, ge=1)
    acquisition_threshold: float = Field(default=DEFAULT_ACQUISITION_THRESHOLD, gt=0.0)
    require_acquisition_readiness: bool = True
    persist_acquisition_snapshots: bool = False


class AcquirerFitRow(AcquirerFitScore):
    """Integrated acquirer-fit row with target-universe context attached."""

    rank: int = 0
    company_id: str | None = None
    therapeutic_area: str | None = None
    indication: str | None = None
    modality: str | None = None
    stage: str | None = None
    enterprise_value_millions: float | None = None
    acquisition_discount: float | None = None
    acquisition_ready: bool | None = None
    acquisition_readiness_bucket: str | None = None
    ev_to_peak_sales: float | None = None
    comparable_match_tier: str | None = None
    comparable_n: int = 0
    comparable_percentile_vs_peers: float | None = None
    comparable_peer_median_ev_to_peak_sales: float | None = None
    # Deal premium estimate (Block 3A/3B)
    deal_premium_ev_ps_p25: float | None = None
    deal_premium_ev_ps_median: float | None = None
    deal_premium_ev_ps_p75: float | None = None
    deal_premium_tier: str | None = None
    # Portfolio synergy score (Block 4B)
    portfolio_synergy_score: float | None = None
    portfolio_synergy_top_match: str | None = None


class AcquirerFitResult(BaseModel):
    """Stable ranked output for one acquirer across a screened target set."""

    scored_at: datetime
    as_of_date: date
    acquirer_id: str
    score_version: str
    n_assets: int
    n_ranked: int
    n_with_comps: int
    n_passing_hard_filters: int
    rows: list[AcquirerFitRow] = Field(default_factory=list)


class AcquirerFitScorer:
    """Score how well a target fits a specific acquirer's declared needs."""

    def __init__(self, config: Optional[AcquirerFitConfig] = None) -> None:
        self.config = config or AcquirerFitConfig()

    def score_target(
        self,
        *,
        acquirer: AcquirerProfile,
        target: AcquirerFitCandidate,
        comparable_analysis: Optional[ComparableDealAnalysis] = None,
    ) -> AcquirerFitScore:
        if _uses_pipeline_gap_formula(acquirer):
            return self._score_target_against_pipeline_gaps(
                acquirer=acquirer,
                target=target,
            )

        weights = self.config.resolved_weights()

        ta_score, matched_gap = self._score_therapeutic_area(acquirer=acquirer, target=target)
        modality_score, matched_modality = self._score_modality(acquirer=acquirer, target=target)
        stage_score, stage_hard_fails = self._score_stage(target=target)
        strategic_score, matched_priorities, matched_partnership = self._score_strategic_priority(
            acquirer=acquirer,
            target=target,
        )
        (
            valuation_score,
            valuation_source,
            valuation_median,
            valuation_low,
            valuation_high,
        ) = self._score_valuation(
            acquirer=acquirer,
            target=target,
            comparable_analysis=comparable_analysis,
        )
        (
            budget_score,
            budget_capacity,
            budget_headroom,
            budget_hard_fails,
        ) = self._score_budget(acquirer=acquirer, target=target)

        therapeutic_area_component = ta_score * weights["therapeutic_area"]
        modality_component = modality_score * weights["modality"]
        stage_component = stage_score * weights["stage"]
        strategic_priority_component = strategic_score * weights["strategic_priority"]
        valuation_component = valuation_score * weights["valuation"]
        budget_component = budget_score * weights["budget"]

        raw_fit_score = round(
            therapeutic_area_component
            + modality_component
            + stage_component
            + strategic_priority_component
            + valuation_component
            + budget_component,
            6,
        )

        hard_fail_reasons = list(dict.fromkeys(stage_hard_fails + budget_hard_fails))
        passes_hard_filters = not hard_fail_reasons
        fit_score = raw_fit_score
        if hard_fail_reasons:
            fit_score = round(raw_fit_score * self.config.hard_fail_penalty_multiplier, 6)

        return AcquirerFitScore(
            acquirer_id=acquirer.acquirer_id,
            asset_id=target.asset_id,
            ticker=target.ticker,
            company_name=target.company_name,
            score_version=self.config.score_version,
            raw_fit_score=raw_fit_score,
            fit_score=fit_score,
            passes_hard_filters=passes_hard_filters,
            therapeutic_area_score=round(ta_score, 6),
            modality_score=round(modality_score, 6),
            stage_score=round(stage_score, 6),
            strategic_priority_score=round(strategic_score, 6),
            valuation_score=round(valuation_score, 6),
            budget_score=round(budget_score, 6),
            therapeutic_area_component=round(therapeutic_area_component, 6),
            modality_component=round(modality_component, 6),
            stage_component=round(stage_component, 6),
            strategic_priority_component=round(strategic_priority_component, 6),
            valuation_component=round(valuation_component, 6),
            budget_component=round(budget_component, 6),
            hard_fail_reasons=hard_fail_reasons,
            matched_therapeutic_gap=matched_gap,
            matched_modality=matched_modality,
            matched_priorities=matched_priorities,
            matched_partnership_target=matched_partnership,
            valuation_source=valuation_source,
            valuation_reference_median_ev_to_peak_sales=valuation_median,
            valuation_reference_band_low_millions=valuation_low,
            valuation_reference_band_high_millions=valuation_high,
            budget_capacity_millions=budget_capacity,
            budget_required_millions=target.enterprise_value_millions,
            budget_headroom_millions=budget_headroom,
            explanation=_build_explanation(
                acquirer_id=acquirer.acquirer_id,
                fit_score=fit_score,
                matched_gap=matched_gap,
                matched_modality=matched_modality,
                matched_priorities=matched_priorities,
                matched_partnership_target=matched_partnership,
                valuation_source=valuation_source,
                comparable_analysis=comparable_analysis,
                budget_headroom=budget_headroom,
                hard_fail_reasons=hard_fail_reasons,
            ),
        )

    def _score_target_against_pipeline_gaps(
        self,
        *,
        acquirer: AcquirerProfile,
        target: AcquirerFitCandidate,
    ) -> AcquirerFitScore:
        best_match: dict[str, object] | None = None

        partnership = _match_existing_partnership(acquirer=acquirer, target=target)
        for gap in acquirer.therapeutic_area_gaps:
            ta_match = _gap_therapeutic_area_match(target=target, gap=gap)
            modality_match, matched_modality = _gap_modality_match(target=target, gap=gap)
            stage_score = _gap_stage_score(target.stage)
            budget_fit, budget_required, budget_headroom = _gap_budget_fit(
                target=target,
                gap=gap,
                acquirer=acquirer,
            )
            urgency_weight = _gap_urgency_weight(gap)
            partnership_score = 1.0 if partnership and partnership.acquisition_option else (
                0.85 if partnership else 0.0
            )

            therapeutic_area_component = round(ta_match * 0.35 * urgency_weight, 6)
            modality_component = round(modality_match * 0.25 * urgency_weight, 6)
            stage_component = round(stage_score * 0.20 * urgency_weight, 6)
            budget_component = round(budget_fit * 0.20 * urgency_weight, 6)
            partnership_component = round(partnership_score * 0.10, 6)
            raw_fit_score = round(
                min(
                    1.0,
                    therapeutic_area_component
                    + modality_component
                    + stage_component
                    + budget_component
                    + partnership_component,
                ),
                6,
            )
            hard_fail_reasons = self._pipeline_gap_hard_fail_reasons(target)
            fit_score = raw_fit_score
            if hard_fail_reasons:
                fit_score = round(raw_fit_score * self.config.hard_fail_penalty_multiplier, 6)

            gap_match = {
                "fit_score": fit_score,
                "raw_fit_score": raw_fit_score,
                "passes_hard_filters": not hard_fail_reasons,
                "therapeutic_area_score": round(ta_match, 6),
                "modality_score": round(modality_match, 6),
                "stage_score": round(stage_score, 6),
                "strategic_priority_score": round(max(urgency_weight, partnership_score), 6),
                "valuation_score": 0.0,
                "budget_score": round(budget_fit, 6),
                "therapeutic_area_component": therapeutic_area_component,
                "modality_component": modality_component,
                "stage_component": stage_component,
                "strategic_priority_component": partnership_component,
                "valuation_component": 0.0,
                "budget_component": budget_component,
                "hard_fail_reasons": hard_fail_reasons,
                "matched_therapeutic_gap": _gap_label(gap),
                "matched_modality": matched_modality,
                "matched_priorities": [],
                "matched_partnership_target": partnership.target if partnership is not None else None,
                "valuation_source": "pipeline_gap_formula",
                "valuation_reference_median_ev_to_peak_sales": None,
                "valuation_reference_band_low_millions": None,
                "valuation_reference_band_high_millions": None,
                "budget_capacity_millions": _effective_gap_budget_ceiling(
                    gap=gap,
                    acquirer=acquirer,
                ),
                "budget_required_millions": budget_required,
                "budget_headroom_millions": budget_headroom,
                "explanation": _build_gap_formula_explanation(
                    acquirer_id=acquirer.acquirer_id,
                    fit_score=raw_fit_score,
                    gap_label=_gap_label(gap),
                    urgency_weight=urgency_weight,
                    ta_match=ta_match,
                    modality_match=modality_match,
                    stage_score=stage_score,
                    budget_fit=budget_fit,
                    budget_headroom=budget_headroom,
                ),
            }

            if best_match is None or (
                gap_match["fit_score"],
                gap_match["therapeutic_area_score"],
                gap_match["modality_score"],
                gap_match["stage_score"],
                str(gap_match["matched_therapeutic_gap"]),
            ) > (
                best_match["fit_score"],
                best_match["therapeutic_area_score"],
                best_match["modality_score"],
                best_match["stage_score"],
                str(best_match["matched_therapeutic_gap"]),
            ):
                best_match = gap_match

        if best_match is None:
            return AcquirerFitScore(
                acquirer_id=acquirer.acquirer_id,
                asset_id=target.asset_id,
                ticker=target.ticker,
                company_name=target.company_name,
                score_version=self.config.score_version,
                raw_fit_score=0.0,
                fit_score=0.0,
                passes_hard_filters=True,
                therapeutic_area_score=0.0,
                modality_score=0.0,
                stage_score=0.0,
                strategic_priority_score=0.0,
                valuation_score=0.0,
                budget_score=0.0,
                therapeutic_area_component=0.0,
                modality_component=0.0,
                stage_component=0.0,
                strategic_priority_component=0.0,
                valuation_component=0.0,
                budget_component=0.0,
                hard_fail_reasons=[],
                matched_therapeutic_gap=None,
                matched_modality=None,
                matched_priorities=[],
                matched_partnership_target=None,
                valuation_source="pipeline_gap_formula",
                valuation_reference_median_ev_to_peak_sales=None,
                valuation_reference_band_low_millions=None,
                valuation_reference_band_high_millions=None,
                budget_capacity_millions=None,
                budget_required_millions=target.model_rnpv_millions,
                budget_headroom_millions=None,
                explanation=f"{acquirer.acquirer_id} fit 0.000: no pipeline gaps available",
            )

        return AcquirerFitScore(
            acquirer_id=acquirer.acquirer_id,
            asset_id=target.asset_id,
            ticker=target.ticker,
            company_name=target.company_name,
            score_version=self.config.score_version,
            **best_match,
        )

    def _pipeline_gap_hard_fail_reasons(self, target: AcquirerFitCandidate) -> list[str]:
        _stage_score, stage_hard_fails = self._score_stage(target=target)
        return list(dict.fromkeys(stage_hard_fails))

    def score_candidates(
        self,
        *,
        acquirer: AcquirerProfile,
        targets: list[AcquirerFitCandidate],
        comparable_analyses: Optional[dict[str, ComparableDealAnalysis]] = None,
    ) -> list[AcquirerFitScore]:
        comparable_analyses = comparable_analyses or {}
        scored = [
            self.score_target(
                acquirer=acquirer,
                target=target,
                comparable_analysis=comparable_analyses.get(target.asset_id),
            )
            for target in targets
        ]
        scored.sort(
            key=lambda score: (
                -score.fit_score,
                -score.raw_fit_score,
                0 if score.passes_hard_filters else 1,
                score.asset_id,
            )
        )
        return scored

    def _score_therapeutic_area(
        self,
        *,
        acquirer: AcquirerProfile,
        target: AcquirerFitCandidate,
    ) -> tuple[float, Optional[str]]:
        target_tokens = _signal_tokens(target.therapeutic_area)
        if not target_tokens:
            return _NEUTRAL_SCORE, None

        best_score = 0.0
        best_gap: Optional[str] = None
        for gap in acquirer.therapeutic_area_gaps:
            if target_tokens & _signal_tokens(gap.therapeutic_area):
                score = _EXPOSURE_LEVEL_SCORES.get(gap.exposure_level, 0.6)
                if score > best_score:
                    best_score = score
                    best_gap = gap.therapeutic_area
        return (best_score, best_gap) if best_gap is not None else (0.0, None)

    def _score_modality(
        self,
        *,
        acquirer: AcquirerProfile,
        target: AcquirerFitCandidate,
    ) -> tuple[float, Optional[str]]:
        target_tokens = _signal_tokens(target.modality)
        if not target_tokens:
            return _NEUTRAL_SCORE, None

        normalized_modality = _normalize_text(target.modality)
        best_score = 0.1
        best_match: Optional[str] = None
        for preferred in acquirer.preferred_modalities:
            preferred_tokens = _signal_tokens(preferred.modality)
            if not (target_tokens & preferred_tokens):
                continue
            strength_score = _PREFERENCE_STRENGTH_SCORES.get(preferred.preference_strength, 0.5)
            if normalized_modality == _normalize_text(preferred.modality):
                score = strength_score
            else:
                score = max(0.2, strength_score - 0.15)
            if score > best_score:
                best_score = score
                best_match = preferred.modality
        return best_score, best_match

    def _score_stage(self, *, target: AcquirerFitCandidate) -> tuple[float, list[str]]:
        stage = _normalize_stage(target.stage)
        hard_fails: list[str] = []

        if stage in _LATE_STAGE:
            return 1.0, hard_fails
        if stage in _PRE_PHASE_2:
            hard_fails.append("pre_phase_2_stage")
            return 0.0, hard_fails
        if stage == "phase_2":
            if target.acquisition_ready is True:
                return 0.8, hard_fails
            if target.acquisition_ready is False:
                if self.config.require_acquisition_readiness:
                    hard_fails.append("not_acquisition_ready")
                return 0.35, hard_fails
            return _NEUTRAL_SCORE, hard_fails
        if stage is None:
            return _NEUTRAL_SCORE, hard_fails
        return 0.25, hard_fails

    def _score_strategic_priority(
        self,
        *,
        acquirer: AcquirerProfile,
        target: AcquirerFitCandidate,
    ) -> tuple[float, list[str], Optional[str]]:
        target_signals: set[str] = set()
        target_signals.update(_signal_tokens(target.therapeutic_area))
        target_signals.update(_signal_tokens(target.modality))
        for tag in target.priority_tags:
            target_signals.update(_signal_tokens(tag))
        partnership = _match_existing_partnership(acquirer=acquirer, target=target)
        if not target_signals:
            if partnership is None:
                return _NEUTRAL_SCORE, [], None
            partnership_score = 1.0 if partnership.acquisition_option else 0.85
            return partnership_score, [], partnership.target

        matched_priorities: list[str] = []
        for priority in acquirer.strategic_priorities:
            if target_signals & _signal_tokens(priority.priority):
                matched_priorities.append(priority.priority)

        unique_matches = list(dict.fromkeys(matched_priorities))
        priority_score = 0.0
        if len(unique_matches) >= 2:
            priority_score = 1.0
        elif unique_matches:
            priority_score = 0.65

        if partnership is None:
            return priority_score, unique_matches, None

        partnership_score = 1.0 if partnership.acquisition_option else 0.85
        return max(priority_score, partnership_score), unique_matches, partnership.target

    def _score_valuation(
        self,
        *,
        acquirer: AcquirerProfile,
        target: AcquirerFitCandidate,
        comparable_analysis: Optional[ComparableDealAnalysis],
    ) -> tuple[float, str, Optional[float], Optional[float], Optional[float]]:
        if (
            comparable_analysis is not None
            and comparable_analysis.n_comps > 0
            and comparable_analysis.premium_discount_vs_median is not None
        ):
            premium = float(comparable_analysis.premium_discount_vs_median)
            if premium <= -0.25:
                score = 1.0
            elif premium <= 0.0:
                score = 0.85
            elif premium <= 0.25:
                score = 0.65
            elif premium <= 0.50:
                score = 0.35
            else:
                score = 0.1
            return (
                score,
                "comparable_deals",
                comparable_analysis.peer_median_ev_to_peak_sales,
                None,
                None,
            )

        reference_band = _reference_deal_band(acquirer=acquirer, target=target)
        if reference_band is None or target.enterprise_value_millions is None:
            return _NEUTRAL_SCORE, "neutral", None, None, None

        low, high = reference_band
        enterprise_value = float(target.enterprise_value_millions)
        if enterprise_value <= low:
            score = 1.0
        elif enterprise_value <= high:
            score = 0.8
        elif enterprise_value <= high * 1.5:
            score = 0.35
        else:
            score = 0.1
        return score, "recent_deal_history", None, low, high

    def _score_budget(
        self,
        *,
        acquirer: AcquirerProfile,
        target: AcquirerFitCandidate,
    ) -> tuple[float, Optional[float], Optional[float], list[str]]:
        explicit_capacity = getattr(acquirer, "acquisition_capacity_millions", None)
        if explicit_capacity is not None:
            max_budget = round(float(explicit_capacity), 6)
            comfortable_budget = max_budget * self.config.comfortable_budget_to_net_cash
            stretch_budget = max_budget * self.config.stretch_budget_to_net_cash
        else:
            budget_net_cash = float(acquirer.budget.net_cash_millions or 0.0)
            max_budget = round(budget_net_cash * self.config.max_budget_to_net_cash, 6)
            comfortable_budget = budget_net_cash * self.config.comfortable_budget_to_net_cash
            stretch_budget = budget_net_cash * self.config.stretch_budget_to_net_cash

        if target.enterprise_value_millions is None:
            return _NEUTRAL_SCORE, max_budget, None, []

        enterprise_value = float(target.enterprise_value_millions)
        headroom = round(max_budget - enterprise_value, 6)
        if enterprise_value <= comfortable_budget:
            return 1.0, max_budget, headroom, []
        if enterprise_value <= stretch_budget:
            return 0.7, max_budget, headroom, []
        if enterprise_value <= max_budget:
            return 0.35, max_budget, headroom, []
        return 0.0, max_budget, headroom, ["outside_budget"]


class AcquirerFitEngine:
    """Wire acquirer profiles, acquisition screening, and comp analysis together."""

    def __init__(
        self,
        *,
        knowledge_store=None,
        context_provider=None,
        fit_config: Optional[AcquirerFitConfig] = None,
        integration_config: Optional[AcquirerFitIntegrationConfig] = None,
    ) -> None:
        self.integration_config = integration_config or AcquirerFitIntegrationConfig()
        resolved_fit_config = fit_config or AcquirerFitConfig(
            require_acquisition_readiness=self.integration_config.require_acquisition_readiness
        )
        self.scorer = AcquirerFitScorer(resolved_fit_config)
        try:
            self.deal_premium_engine: Optional[DealPremiumEngine] = DealPremiumEngine.from_file(
                Path(self.integration_config.comparable_deals_path)
            )
        except Exception:
            self.deal_premium_engine = None
        self.acquisition_screener = AcquisitionScreener(
            AcquisitionScreenConfig(
                threshold=self.integration_config.acquisition_threshold,
                require_acquisition_readiness=self.integration_config.require_acquisition_readiness,
                persist_snapshots=self.integration_config.persist_acquisition_snapshots,
            ),
            knowledge_store=knowledge_store,
            context_provider=context_provider,
        )

    def screen_from_watchlist_config(
        self,
        watchlist_config,
        *,
        acquirer_id: str,
        snapshot_date: Optional[date] = None,
        top_n: Optional[int] = None,
    ) -> AcquirerFitResult:
        return self.screen_watchlist(
            list(getattr(watchlist_config, "watchlist", [])),
            acquirer_id=acquirer_id,
            snapshot_date=snapshot_date,
            top_n=top_n,
        )

    def screen_watchlist(
        self,
        watchlist: list[object],
        *,
        acquirer_id: str,
        snapshot_date: Optional[date] = None,
        top_n: Optional[int] = None,
        comparable_deals: Optional[list[ComparableDeal]] = None,
    ) -> AcquirerFitResult:
        as_of = snapshot_date or date.today()
        scored_at = datetime.now(timezone.utc)
        profile = AcquirerProfileLoader.get_acquirer(
            self.integration_config.acquirer_profiles_path,
            acquirer_id,
        )
        deals = comparable_deals or ComparableDealLoader.load(
            self.integration_config.comparable_deals_path
        ).deals
        acquisition_result = self.acquisition_screener.screen_watchlist(
            watchlist,
            snapshot_date=as_of,
            persist=self.integration_config.persist_acquisition_snapshots,
            comparable_deals=deals,
        )

        asset_by_id = {getattr(asset, "asset_id"): asset for asset in watchlist}
        acquirer_portfolio = self._build_acquirer_portfolio(profile)
        integrated_rows = [
            self._build_row(
                acquirer=profile,
                asset=asset_by_id[row.asset_id],
                acquisition_row=row,
                comparable_deals=deals,
                acquirer_portfolio=acquirer_portfolio,
            )
            for row in acquisition_result.rows
        ]
        integrated_rows.sort(
            key=lambda row: (
                -row.fit_score,
                -row.raw_fit_score,
                row.asset_id,
            )
        )
        limit = top_n or self.integration_config.top_n
        ranked_rows = [
            row.model_copy(update={"rank": idx + 1})
            for idx, row in enumerate(integrated_rows[:limit])
        ]

        return AcquirerFitResult(
            scored_at=scored_at,
            as_of_date=as_of,
            acquirer_id=profile.acquirer_id,
            score_version=self.scorer.config.score_version,
            n_assets=len(integrated_rows),
            n_ranked=len(ranked_rows),
            n_with_comps=sum(1 for row in integrated_rows if row.comparable_n > 0),
            n_passing_hard_filters=sum(1 for row in integrated_rows if row.passes_hard_filters),
            rows=ranked_rows,
        )

    @staticmethod
    def _build_acquirer_portfolio(acquirer: AcquirerProfile) -> list[SynergyAssetProfile]:
        """Build SynergyAssetProfile list from an acquirer's recent deal history."""
        portfolio: list[SynergyAssetProfile] = []
        for deal in acquirer.recent_deal_history:
            portfolio.append(SynergyAssetProfile(
                asset_id=deal.deal_name,
                therapeutic_area=deal.therapeutic_area,
                modality=deal.modality,
                signals=[deal.therapeutic_area, deal.modality],
            ))
        for partnership in acquirer.existing_partnerships:
            portfolio.append(SynergyAssetProfile(
                asset_id=partnership.target,
                therapeutic_area=partnership.therapeutic_area,
                signals=[partnership.therapeutic_area, partnership.partnership_type],
            ))
        return portfolio

    def _build_row(
        self,
        *,
        acquirer: AcquirerProfile,
        asset: object,
        acquisition_row: AcquisitionScreenRow,
        comparable_deals: list[ComparableDeal],
        acquirer_portfolio: Optional[list[SynergyAssetProfile]] = None,
    ) -> AcquirerFitRow:
        candidate = self._build_candidate(asset=asset, acquisition_row=acquisition_row)
        comparable_analysis = ComparableDealMatcher.analyze(
            asset_indication=candidate.indication,
            asset_therapeutic_area=candidate.therapeutic_area,
            asset_stage=candidate.stage,
            asset_ev_to_peak_sales=candidate.ev_to_peak_sales,
            deals=comparable_deals,
        )
        score = self.scorer.score_target(
            acquirer=acquirer,
            target=candidate,
            comparable_analysis=comparable_analysis,
        )
        # Portfolio synergy score (Block 4B)
        syn_score: Optional[float] = None
        syn_top_match: Optional[str] = None
        if acquirer_portfolio:
            try:
                candidate_profile = SynergyAssetProfile(
                    asset_id=candidate.asset_id,
                    therapeutic_area=candidate.therapeutic_area or "",
                    indication=candidate.indication or "",
                    modality=candidate.modality or "",
                    signals=list(candidate.priority_tags),
                )
                total_syn, syn_edges = score_acquirer_portfolio_fit(
                    candidate_profile, acquirer_portfolio
                )
                if total_syn > 0:
                    syn_score = total_syn
                    if syn_edges:
                        syn_top_match = syn_edges[0].asset_id_b
            except Exception:
                pass

        # Deal premium estimate (Block 3B)
        dp_p25 = dp_median = dp_p75 = dp_tier = None
        if self.deal_premium_engine is not None and candidate.stage:
            try:
                dp = self.deal_premium_engine.estimate(
                    phase=candidate.stage,
                    therapeutic_area=candidate.therapeutic_area or "oncology",
                    acquirer_fit_score=score.fit_score,
                )
                dp_p25 = dp.ev_to_peak_sales_p25
                dp_median = dp.ev_to_peak_sales_median
                dp_p75 = dp.ev_to_peak_sales_p75
                dp_tier = dp.premium_tier
            except Exception:
                pass

        return AcquirerFitRow(
            **score.model_dump(),
            company_id=candidate.company_id,
            therapeutic_area=candidate.therapeutic_area,
            indication=candidate.indication,
            modality=candidate.modality,
            stage=candidate.stage,
            enterprise_value_millions=candidate.enterprise_value_millions,
            acquisition_discount=candidate.acquisition_discount,
            acquisition_ready=candidate.acquisition_ready,
            acquisition_readiness_bucket=candidate.acquisition_readiness_bucket,
            ev_to_peak_sales=candidate.ev_to_peak_sales,
            comparable_match_tier=comparable_analysis.match_tier,
            comparable_n=comparable_analysis.n_comps,
            comparable_percentile_vs_peers=comparable_analysis.percentile_vs_comps,
            comparable_peer_median_ev_to_peak_sales=comparable_analysis.peer_median_ev_to_peak_sales,
            deal_premium_ev_ps_p25=dp_p25,
            deal_premium_ev_ps_median=dp_median,
            deal_premium_ev_ps_p75=dp_p75,
            deal_premium_tier=dp_tier,
            portfolio_synergy_score=syn_score,
            portfolio_synergy_top_match=syn_top_match,
        )

    def _build_candidate(
        self,
        *,
        asset: object,
        acquisition_row: AcquisitionScreenRow,
    ) -> AcquirerFitCandidate:
        company_name: Optional[str] = None
        therapeutic_area = acquisition_row.therapeutic_area
        stage = acquisition_row.stage
        indication = acquisition_row.indication or getattr(asset, "indication", None)
        modality: Optional[str] = None
        priority_tags: list[str] = []

        if indication:
            priority_tags.append(indication)
        if getattr(asset, "drug_name", None):
            priority_tags.append(str(getattr(asset, "drug_name")))

        try:
            context = self.acquisition_screener._get_context(asset)
        except Exception:
            context = None

        if context is not None:
            company_name = getattr(context.company, "name", None)
            if therapeutic_area is None:
                therapeutic_area = getattr(
                    getattr(context.asset, "therapeutic_area", None),
                    "value",
                    None,
                )
            if stage is None:
                stage = getattr(getattr(context.asset, "stage", None), "value", None)
            if indication is None:
                indication = getattr(context.asset, "indication", None)
            modality = _resolve_target_modality(
                raw_modality=getattr(getattr(context.asset, "modality", None), "value", None),
                mechanism_of_action=getattr(context.asset, "mechanism_of_action", None),
            )
            if getattr(context.asset, "mechanism_of_action", None):
                priority_tags.append(str(context.asset.mechanism_of_action))

        return AcquirerFitCandidate(
            asset_id=acquisition_row.asset_id,
            company_id=acquisition_row.company_id,
            company_name=company_name,
            ticker=acquisition_row.ticker,
            therapeutic_area=therapeutic_area,
            indication=indication,
            modality=modality,
            stage=stage,
            model_rnpv_millions=acquisition_row.model_rnpv_millions,
            enterprise_value_millions=acquisition_row.enterprise_value_millions,
            acquisition_discount=acquisition_row.acquisition_discount,
            acquisition_ready=acquisition_row.acquisition_ready,
            acquisition_readiness_bucket=acquisition_row.acquisition_readiness_bucket,
            ev_to_peak_sales=acquisition_row.ev_to_peak_sales,
            priority_tags=list(dict.fromkeys(tag for tag in priority_tags if tag)),
        )


def _reference_deal_band(
    *,
    acquirer: AcquirerProfile,
    target: AcquirerFitCandidate,
) -> Optional[tuple[float, float]]:
    target_signals = _signal_tokens(target.therapeutic_area) | _signal_tokens(target.modality)
    matched_bands: list[tuple[float, float]] = []
    fallback_bands: list[tuple[float, float]] = []

    for deal in acquirer.recent_deal_history:
        low = deal.implied_value_band_millions_low
        if low is None:
            low = deal.upfront_millions
        high = deal.implied_value_band_millions_high
        if high is None:
            high = deal.implied_value_band_millions_low or deal.upfront_millions
        if low is None or high is None:
            continue
        band = (float(low), float(high))
        fallback_bands.append(band)
        deal_signals = _signal_tokens(deal.therapeutic_area) | _signal_tokens(deal.modality)
        if target_signals and (target_signals & deal_signals):
            matched_bands.append(band)

    selected = matched_bands or fallback_bands
    if not selected:
        return None
    lows = [band[0] for band in selected]
    highs = [band[1] for band in selected]
    return round(min(lows), 6), round(max(highs), 6)


def _uses_pipeline_gap_formula(acquirer: AcquirerProfile) -> bool:
    return any(
        gap.budget_ceiling_millions is not None or bool(gap.preferred_modality)
        for gap in acquirer.therapeutic_area_gaps
    )


def _gap_label(gap) -> str:
    if getattr(gap, "sub_area", None):
        return f"{gap.therapeutic_area}:{gap.sub_area}"
    return str(gap.therapeutic_area)


def _gap_therapeutic_area_match(
    *,
    target: AcquirerFitCandidate,
    gap,
) -> float:
    target_area = _normalize_text(target.therapeutic_area)
    gap_area = _normalize_text(gap.therapeutic_area)
    if gap_area is None:
        return 0.0

    target_area_signals = _signal_tokens(target.therapeutic_area)
    target_context_signals = _specific_signal_tokens(
        target.indication,
        *target.priority_tags,
    )

    # Cross-TA enrichment: look up the indication in the canonical registry.
    # If it has secondary_therapeutic_areas or cross_ta_signals, add those to
    # the token sets so that e.g. IgA Nephropathy (immunology) also matches
    # ckd_pkd_renal (rare_disease) gaps.
    canonical_ind = lookup_indication(target.indication or "")
    if canonical_ind is not None:
        for secondary_ta in canonical_ind.secondary_therapeutic_areas:
            target_area_signals |= _signal_tokens(secondary_ta)
        for cross_signal in canonical_ind.cross_ta_signals:
            target_context_signals |= _specific_signal_tokens(cross_signal)
            target_context_signals.add(_normalize_text(cross_signal) or cross_signal)

    if not target_area_signals and not target_context_signals:
        return 0.0

    gap_signals = _signal_tokens(gap.therapeutic_area)
    gap_specific_signals = _specific_signal_tokens(getattr(gap, "sub_area", None))

    if gap_specific_signals and (target_context_signals & gap_specific_signals):
        return 1.0

    if target_area == gap_area:
        return 0.65 if gap_specific_signals else 1.0

    if target_area_signals & gap_signals:
        return 0.35 if gap_specific_signals else 0.65

    if target_context_signals & gap_signals:
        return 0.25 if gap_specific_signals else 0.45

    return 0.0


def _gap_modality_match(
    *,
    target: AcquirerFitCandidate,
    gap,
) -> tuple[float, Optional[str]]:
    target_modality = _normalize_text(target.modality)
    search_text = _normalize_text(
        " ".join(
            [
                target.modality or "",
                target.indication or "",
                *target.priority_tags,
            ]
        )
    ) or ""
    preferred_list = list(getattr(gap, "preferred_modality", []) or [])

    best_score = 0.0
    best_match: Optional[str] = None

    for preferred in preferred_list:
        preferred_normalized = _normalize_text(preferred)
        if preferred_normalized is None:
            continue
        score = 0.0

        # Exact canonical match
        if preferred_normalized == target_modality:
            score = 1.0
        elif preferred_normalized == "small molecule" and target_modality == "oral small molecule":
            score = 0.8
        elif preferred_normalized == "oral small molecule":
            if target_modality == "oral small molecule":
                score = 1.0
            elif target_modality == "small molecule" and "oral" in search_text:
                score = 1.0
        elif preferred_normalized == "adc" and target_modality == "adc":
            score = 1.0
        elif preferred_normalized == "peptide" and "peptide" in search_text:
            score = 1.0
        else:
            # Token-overlap fallback via _CATEGORY_ALIASES — catches sirna_rnai,
            # radiopharmaceutical, bispecific_antibody, monoclonal_antibody, etc.
            preferred_tokens = _signal_tokens(preferred)
            target_tokens_set = _signal_tokens(target.modality or "") | _signal_tokens(search_text)
            overlap = preferred_tokens & target_tokens_set
            if overlap:
                # Score is lower for partial match; boost if the category name itself matches
                pref_canon = preferred_normalized.replace(" ", "_")
                tgt_canon = (target_modality or "").replace(" ", "_")
                if pref_canon == tgt_canon or pref_canon in tgt_canon or tgt_canon in pref_canon:
                    score = 0.9
                else:
                    score = 0.7

        if score > best_score:
            best_score = score
            best_match = preferred.replace(" ", "_")

    return (best_score, best_match) if best_score > 0.0 else (0.0, None)


def _gap_stage_score(stage: Optional[str]) -> float:
    normalized = _normalize_stage(stage)
    if normalized in {"phase_2", "phase_3", "nda_bla", "approved", "commercial"}:
        return 1.0
    if normalized == "phase_1":
        return 0.5
    return 0.0


def _gap_budget_fit(
    *,
    target: AcquirerFitCandidate,
    gap,
    acquirer: Optional[AcquirerProfile] = None,
) -> tuple[float, Optional[float], Optional[float]]:
    budget_ceiling = _effective_gap_budget_ceiling(gap=gap, acquirer=acquirer)
    valuation_reference = (
        target.model_rnpv_millions
        if target.model_rnpv_millions is not None
        else target.enterprise_value_millions
    )
    if budget_ceiling is None or valuation_reference is None:
        return 1.0, valuation_reference, None
    headroom = round(float(budget_ceiling) - float(valuation_reference), 6)
    if float(valuation_reference) < float(budget_ceiling):
        return 1.0, float(valuation_reference), headroom
    return 0.5, float(valuation_reference), headroom


def _effective_gap_budget_ceiling(*, gap, acquirer: Optional[AcquirerProfile]) -> Optional[float]:
    budget_ceiling = getattr(gap, "budget_ceiling_millions", None)
    acquirer_capacity = getattr(acquirer, "acquisition_capacity_millions", None)
    if budget_ceiling is not None and acquirer_capacity is not None:
        return min(float(budget_ceiling), float(acquirer_capacity))
    if budget_ceiling is not None:
        return float(budget_ceiling)
    if acquirer_capacity is not None:
        return float(acquirer_capacity)
    return None


def _gap_urgency_weight(gap) -> float:
    urgency = _normalize_text(getattr(gap, "exposure_level", None)) or _normalize_text(
        getattr(gap, "urgency", None)
    )
    if urgency == "high":
        return 1.0
    if urgency == "medium":
        return 0.7
    if urgency == "low":
        return 0.4
    return 0.7


def _build_explanation(
    *,
    acquirer_id: str,
    fit_score: float,
    matched_gap: Optional[str],
    matched_modality: Optional[str],
    matched_priorities: list[str],
    matched_partnership_target: Optional[str],
    valuation_source: str,
    comparable_analysis: Optional[ComparableDealAnalysis],
    budget_headroom: Optional[float],
    hard_fail_reasons: list[str],
) -> str:
    parts: list[str] = []
    if matched_gap:
        parts.append(f"matches {matched_gap} gap")
    if matched_modality:
        parts.append(f"matches {matched_modality} modality")
    if matched_priorities:
        parts.append(f"aligns with {len(matched_priorities)} stated priorities")
    if matched_partnership_target:
        parts.append(f"existing partnership with {matched_partnership_target}")
    if valuation_source == "comparable_deals" and comparable_analysis is not None:
        premium = comparable_analysis.premium_discount_vs_median
        if premium is not None:
            parts.append(f"trades {premium:+.2f}x versus peer median")
    elif valuation_source == "recent_deal_history":
        parts.append("screened against recent deal-size band")

    if budget_headroom is not None:
        if budget_headroom >= 0:
            parts.append(f"budget headroom ${budget_headroom:.1f}M")
        else:
            parts.append(f"budget shortfall ${abs(budget_headroom):.1f}M")
    if hard_fail_reasons:
        parts.append("hard fails: " + ", ".join(hard_fail_reasons))
    if not parts:
        parts.append("limited fit context available")
    return f"{acquirer_id} fit {fit_score:.3f}: " + "; ".join(parts)


def _match_existing_partnership(
    *,
    acquirer: AcquirerProfile,
    target: AcquirerFitCandidate,
):
    target_keys = {
        _normalize_text(target.ticker),
        _normalize_text(target.company_name),
    }
    target_keys.discard(None)
    if not target_keys:
        return None

    matched = []
    for partnership in getattr(acquirer, "existing_partnerships", []) or []:
        partner_key = _normalize_text(getattr(partnership, "target", None))
        if partner_key is None or partner_key not in target_keys:
            continue
        matched.append(partnership)

    if not matched:
        return None
    matched.sort(
        key=lambda partnership: (
            1 if getattr(partnership, "acquisition_option", False) else 0,
            getattr(partnership, "year_initiated", 0) or 0,
        ),
        reverse=True,
    )
    return matched[0]


def _build_gap_formula_explanation(
    *,
    acquirer_id: str,
    fit_score: float,
    gap_label: str,
    urgency_weight: float,
    ta_match: float,
    modality_match: float,
    stage_score: float,
    budget_fit: float,
    budget_headroom: Optional[float],
) -> str:
    parts = [
        f"gap {gap_label}",
        f"urgency {urgency_weight:.1f}",
        f"ta {ta_match:.1f}",
        f"modality {modality_match:.1f}",
        f"stage {stage_score:.1f}",
        f"budget {budget_fit:.1f}",
    ]
    if budget_headroom is not None:
        if budget_headroom >= 0:
            parts.append(f"budget headroom ${budget_headroom:.1f}M")
        else:
            parts.append(f"budget shortfall ${abs(budget_headroom):.1f}M")
    return f"{acquirer_id} fit {fit_score:.3f}: " + "; ".join(parts)


def _resolve_target_modality(
    *,
    raw_modality: Optional[str],
    mechanism_of_action: Optional[str] = None,
) -> Optional[str]:
    normalized = _normalize_text(raw_modality)
    moa = _normalize_text(mechanism_of_action)
    if normalized is None:
        return None
    if normalized == "small molecule":
        if moa and "oral" in moa:
            return "oral_small_molecule"
        return "small_molecule"
    if normalized == "biologic":
        if moa and "bispecific" in moa:
            return "bispecific_antibody"
        return "fully_human_antibody"
    if normalized in {"gene therapy", "rna therapy", "aav gene therapy"}:
        return "genetic_medicine"
    if normalized == "cell therapy":
        return "cell_therapy"
    # siRNA / RNAi mappings
    if normalized in {"sirna", "rnai", "rna interference", "antisense oligonucleotide", "aso", "oligonucleotide"}:
        return "sirna_rnai"
    if normalized in {"sirna rnai", "rna silencing", "antisense"}:
        return "sirna_rnai"
    # Radiopharmaceutical mappings
    if normalized in {
        "radioligand therapy",
        "radioligand",
        "radiopharma",
        "targeted radionuclide",
        "alpha therapy",
        "beta emitter",
        "rlt",
    }:
        return "radiopharmaceutical"
    # Bispecific antibody mappings
    if normalized in {"bispecific antibody", "bispecific", "t cell engager", "t-cell engager"}:
        return "bispecific_antibody"
    # Monoclonal antibody / fusion protein
    if normalized in {"monoclonal antibody", "mab", "immunoglobulin"}:
        return "fully_human_antibody"
    if normalized in {"fusion protein", "receptor trap", "trap"}:
        return "fusion_protein"
    return normalized.replace(" ", "_")
