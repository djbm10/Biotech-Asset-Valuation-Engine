"""Block 6I: Management Diligence Question Generation.

Generates prioritized diligence questions based on weak or missing
management quality components.

Design rules:
  - UNKNOWN management → baseline HIGH-priority questions across all categories
  - Weak component (<= 0.35) → HIGH/CRITICAL questions for that category
  - Strong management (all >= 0.70) → no questions generated
  - Questions are deterministic (stable order) for reproducibility
  - No duplicate question text within a result set
  - Each question carries: category, question, priority, owner, source_needed, trigger
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from bve.intelligence.ma_management_quality import (
    ManagementGate,
    ManagementQualityScore,
    ManagementRiskBand,
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ManagementDiligenceQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str
    question: str
    priority: str  # CRITICAL / HIGH / MEDIUM
    owner: str     # BD / Clinical / Regulatory / Finance / Legal
    source_needed: list[str]
    trigger: str
    expected_score_impact: Optional[str] = None


# ---------------------------------------------------------------------------
# Question banks
# ---------------------------------------------------------------------------

_TRIAL_DESIGN_QUESTIONS: list[dict] = [
    {
        "question": "Why was this endpoint chosen, and what FDA feedback supports it?",
        "priority": "HIGH",
        "owner": "Clinical",
        "source_needed": ["FDA meeting minutes", "SPA agreement", "clinical protocol"],
        "trigger": "trial_design_judgment < 0.35",
        "expected_score_impact": "Can upgrade trial_design_judgment if FDA alignment is confirmed",
    },
    {
        "question": "What would make the trial fail despite biological activity?",
        "priority": "HIGH",
        "owner": "Clinical",
        "source_needed": ["clinical protocol", "statistical analysis plan"],
        "trigger": "trial_design_judgment < 0.35",
        "expected_score_impact": "Identifies endpoint or design risk not captured in biology",
    },
    {
        "question": "Was the comparator selected to match the future standard of care?",
        "priority": "HIGH",
        "owner": "Clinical",
        "source_needed": ["clinical protocol", "competitive landscape analysis"],
        "trigger": "trial_design_judgment < 0.35",
        "expected_score_impact": "Comparator mismatch can invalidate regulatory strategy",
    },
    {
        "question": "How was the sample size powered, and what assumptions drive it?",
        "priority": "MEDIUM",
        "owner": "Clinical",
        "source_needed": ["statistical analysis plan", "protocol synopsis"],
        "trigger": "trial_design_judgment < 0.35",
        "expected_score_impact": "Underpowered trials destroy value at readout",
    },
    {
        "question": "How was the patient population defined, and was biomarker enrichment considered?",
        "priority": "MEDIUM",
        "owner": "Clinical",
        "source_needed": ["inclusion/exclusion criteria", "biomarker strategy document"],
        "trigger": "trial_design_judgment < 0.35",
        "expected_score_impact": "Enrichment can rescue marginal biology",
    },
]

_BD_PARTNERING_QUESTIONS: list[dict] = [
    {
        "question": "Would management partner before the next clinical readout?",
        "priority": "HIGH",
        "owner": "BD",
        "source_needed": ["management meeting note", "investor day transcript"],
        "trigger": "bd_partnering_judgment < 0.35",
        "expected_score_impact": "Willingness to partner before data is a key BD signal",
    },
    {
        "question": "What rights are management willing to retain vs. give up to a partner?",
        "priority": "HIGH",
        "owner": "BD",
        "source_needed": ["management meeting note", "prior deal term sheets"],
        "trigger": "bd_partnering_judgment < 0.35",
        "expected_score_impact": "Rights retained define the economics available to a buyer",
    },
    {
        "question": "How do they think about regional licensing vs. full global partnership?",
        "priority": "MEDIUM",
        "owner": "BD",
        "source_needed": ["management meeting note", "prior partnership agreements"],
        "trigger": "bd_partnering_judgment < 0.35",
        "expected_score_impact": "Regional deals can destroy global optionality",
    },
    {
        "question": "What deal structure preserves shareholder value without giving up too much upside?",
        "priority": "HIGH",
        "owner": "BD",
        "source_needed": ["investor presentations", "management meeting note"],
        "trigger": "bd_partnering_judgment < 0.35",
        "expected_score_impact": "Option-to-acquire or co-development may better align incentives",
    },
    {
        "question": "Have they previously licensed away key rights before a major value inflection?",
        "priority": "HIGH",
        "owner": "BD",
        "source_needed": ["SEC filings", "prior deal press releases"],
        "trigger": "bd_partnering_judgment < 0.35",
        "expected_score_impact": "Premature licensing is a pattern risk for BD value destruction",
    },
]

_CAPITAL_ALLOCATION_QUESTIONS: list[dict] = [
    {
        "question": "Does the company have cash runway through the next value-inflecting catalyst?",
        "priority": "HIGH",
        "owner": "Finance",
        "source_needed": ["10-Q/10-K cash burn", "upcoming catalyst timeline"],
        "trigger": "capital_allocation_discipline < 0.35",
        "expected_score_impact": "Capital shortfall before catalyst forces dilution or deal at wrong time",
    },
    {
        "question": "Would management raise equity before or after the next data readout?",
        "priority": "HIGH",
        "owner": "Finance",
        "source_needed": ["management meeting note", "earnings call transcript"],
        "trigger": "capital_allocation_discipline < 0.35",
        "expected_score_impact": "Pre-data raises preserve partnership leverage; post-data is riskier",
    },
    {
        "question": "What programs would be cut if capital markets remain closed for 18 months?",
        "priority": "HIGH",
        "owner": "Finance",
        "source_needed": ["R&D budget", "pipeline prioritization document"],
        "trigger": "capital_allocation_discipline < 0.35",
        "expected_score_impact": "Identifies which programs are strategic vs. funded opportunistically",
    },
    {
        "question": "Has management historically financed before or after major catalysts?",
        "priority": "MEDIUM",
        "owner": "Finance",
        "source_needed": ["SEC filings", "equity offering history"],
        "trigger": "capital_allocation_discipline < 0.35",
        "expected_score_impact": "Patterns predict future dilution behavior",
    },
    {
        "question": "What is the G&A spend relative to peers at the same stage?",
        "priority": "MEDIUM",
        "owner": "Finance",
        "source_needed": ["10-K/10-Q operating expenses", "peer benchmarks"],
        "trigger": "capital_allocation_discipline < 0.35",
        "expected_score_impact": "High G&A signals misaligned capital allocation",
    },
]

_DISCLOSURE_QUESTIONS: list[dict] = [
    {
        "question": "What safety events were excluded or downplayed in headline data presentations?",
        "priority": "HIGH",
        "owner": "Clinical",
        "source_needed": ["full clinical study report", "FDA briefing documents", "CSR appendices"],
        "trigger": "disclosure_transparency < 0.35",
        "expected_score_impact": "Hidden safety signals destroy regulatory and commercial value",
    },
    {
        "question": "Are investor-deck claims consistent with SEC filings and trial registry data?",
        "priority": "HIGH",
        "owner": "Legal",
        "source_needed": ["investor deck", "10-K/10-Q", "ClinicalTrials.gov registration"],
        "trigger": "disclosure_transparency < 0.35",
        "expected_score_impact": "Discrepancies indicate overpromotion risk",
    },
    {
        "question": "What subgroup analyses weakened the primary thesis?",
        "priority": "HIGH",
        "owner": "Clinical",
        "source_needed": ["full clinical study report", "supplementary data"],
        "trigger": "disclosure_transparency < 0.35",
        "expected_score_impact": "Selective subgroup reporting masks real effect size",
    },
    {
        "question": "What assumptions in the investor deck are most sensitive to revision?",
        "priority": "MEDIUM",
        "owner": "BD",
        "source_needed": ["investor presentation", "market research"],
        "trigger": "disclosure_transparency < 0.35",
        "expected_score_impact": "Key assumption sensitivity informs diligence priority",
    },
    {
        "question": "Has guidance on enrollment timelines, cash runway, or readout dates been revised downward more than once?",
        "priority": "HIGH",
        "owner": "Finance",
        "source_needed": ["earnings call transcripts", "prior guidance history"],
        "trigger": "disclosure_transparency < 0.35",
        "expected_score_impact": "Repeated guidance misses signal poor execution or opacity",
    },
]

_GOVERNANCE_QUESTIONS: list[dict] = [
    {
        "question": "Does the board appear aligned with minority shareholders, or are control provisions in place that block value-maximizing transactions?",
        "priority": "HIGH",
        "owner": "Legal",
        "source_needed": ["proxy statement", "certificate of incorporation", "shareholder rights plan"],
        "trigger": "governance_alignment < 0.35",
        "expected_score_impact": "Poison pills or staggered boards can block premium bids",
    },
    {
        "question": "Are insiders economically aligned with common shareholders (options vs. restricted shares vs. cash compensation)?",
        "priority": "HIGH",
        "owner": "Legal",
        "source_needed": ["proxy statement", "insider ownership filings"],
        "trigger": "governance_alignment < 0.35",
        "expected_score_impact": "Management incentives determine willingness to sell",
    },
    {
        "question": "Are there related-party transactions or board relationships that suggest governance risk?",
        "priority": "HIGH",
        "owner": "Legal",
        "source_needed": ["proxy statement", "10-K related party disclosures"],
        "trigger": "governance_alignment < 0.35",
        "expected_score_impact": "Related-party risk can complicate or block acquisition",
    },
    {
        "question": "Is there active activist pressure that might accelerate or complicate a deal?",
        "priority": "MEDIUM",
        "owner": "BD",
        "source_needed": ["13D/13G filings", "activist investor communications"],
        "trigger": "governance_alignment < 0.35",
        "expected_score_impact": "Activists can be allies or adversaries depending on deal structure",
    },
]

_BASELINE_UNKNOWN_QUESTIONS: list[tuple[str, dict]] = [
    ("clinical_execution", {
        "question": "What is management's track record on trial execution across prior programs?",
        "priority": "HIGH",
        "owner": "Clinical",
        "source_needed": ["prior clinical study reports", "ClinicalTrials.gov history"],
        "trigger": "management_quality_unknown",
        "expected_score_impact": "Establishes baseline for clinical_execution_quality",
    }),
    ("regulatory_execution", {
        "question": "Has management previously designed and run trials that succeeded at FDA review?",
        "priority": "HIGH",
        "owner": "Regulatory",
        "source_needed": ["FDA approval letters", "prior NDA/BLA filings"],
        "trigger": "management_quality_unknown",
        "expected_score_impact": "Establishes baseline for regulatory_execution",
    }),
    ("capital_allocation", {
        "question": "How has management historically financed the company relative to its cash needs?",
        "priority": "HIGH",
        "owner": "Finance",
        "source_needed": ["equity offering history", "10-K/10-Q cash statements"],
        "trigger": "management_quality_unknown",
        "expected_score_impact": "Establishes baseline for capital_allocation_discipline",
    }),
    ("bd_partnering", {
        "question": "Have they signed any prior partnerships, and if so, were the economics favorable?",
        "priority": "HIGH",
        "owner": "BD",
        "source_needed": ["prior deal press releases", "SEC filings for deal terms"],
        "trigger": "management_quality_unknown",
        "expected_score_impact": "Establishes baseline for bd_partnering_judgment",
    }),
    ("disclosure", {
        "question": "Is the information disclosed publicly consistent and complete, or are there gaps?",
        "priority": "HIGH",
        "owner": "Legal",
        "source_needed": ["SEC filings", "investor presentations", "ClinicalTrials.gov"],
        "trigger": "management_quality_unknown",
        "expected_score_impact": "Establishes baseline for disclosure_transparency",
    }),
]

# Category → question bank mapping
_QUESTION_BANKS: dict[str, list[dict]] = {
    "trial_design": _TRIAL_DESIGN_QUESTIONS,
    "bd_partnering": _BD_PARTNERING_QUESTIONS,
    "capital_allocation": _CAPITAL_ALLOCATION_QUESTIONS,
    "disclosure": _DISCLOSURE_QUESTIONS,
    "governance": _GOVERNANCE_QUESTIONS,
}

# Component → category mapping
_COMPONENT_TO_CATEGORY: dict[str, str] = {
    "trial_design_judgment": "trial_design",
    "bd_partnering_judgment": "bd_partnering",
    "capital_allocation_discipline": "capital_allocation",
    "disclosure_transparency": "disclosure",
    "governance_alignment": "governance",
}

# Trigger threshold for generating weak-component questions
_WEAK_THRESHOLD: float = 0.40


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_management_diligence_questions(
    management_quality: ManagementQualityScore,
    context: Optional[dict] = None,
) -> list[ManagementDiligenceQuestion]:
    """Generate prioritized diligence questions based on management quality score.

    Args:
        management_quality: Computed ManagementQualityScore.
        context: Optional dict (e.g. {"buyer": "pfizer"}) — reserved for future use.

    Returns:
        Ordered list of ManagementDiligenceQuestion (deterministic, no duplicates).
        Priority CRITICAL/HIGH first, then MEDIUM. Within same priority, stable insertion order.
    """
    questions: list[ManagementDiligenceQuestion] = []
    seen_questions: set[str] = set()

    def _add(category: str, bank_entry: dict) -> None:
        q_text = bank_entry["question"]
        if q_text in seen_questions:
            return
        seen_questions.add(q_text)
        questions.append(ManagementDiligenceQuestion(
            category=category,
            question=q_text,
            priority=bank_entry["priority"],
            owner=bank_entry["owner"],
            source_needed=list(bank_entry["source_needed"]),
            trigger=bank_entry["trigger"],
            expected_score_impact=bank_entry.get("expected_score_impact"),
        ))

    # UNKNOWN management → baseline list
    if management_quality.risk_band == ManagementRiskBand.UNKNOWN:
        for category, entry in _BASELINE_UNKNOWN_QUESTIONS:
            _add(category, entry)
        return _sorted(questions)

    # Strong management → no questions
    bd = management_quality.component_breakdown
    if not bd:
        return []

    # For each component below threshold, emit questions from its category bank
    for component, category in _COMPONENT_TO_CATEGORY.items():
        value = bd.get(component)
        if value is not None and value < _WEAK_THRESHOLD:
            bank = _QUESTION_BANKS.get(category, [])
            for entry in bank:
                _add(category, entry)

    return _sorted(questions)


def _sorted(questions: list[ManagementDiligenceQuestion]) -> list[ManagementDiligenceQuestion]:
    """Sort by priority (CRITICAL first, then HIGH, then MEDIUM), then stable insertion order."""
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
    return sorted(questions, key=lambda q: (priority_order.get(q.priority, 3), questions.index(q)))
