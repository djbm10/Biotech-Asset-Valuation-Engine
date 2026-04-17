"""
Asset dossier — single source of truth for one drug program.

Every material field is wrapped in a ProvenanceField that records where
the data came from, when it was extracted, and how confident we are.
Call dossier.completeness() to see which fields are missing before
using the dossier for valuation.

Usage
-----
from bve.dossier.dossier import AssetDossier, ProvenanceField
from bve.dossier.builder import DossierBuilder
from datetime import date

builder = DossierBuilder("PROG-001", "Pembrolizumab", "Merck")
builder.set_field("mechanism_of_action", "PD-1 inhibitor",
                  source="SEC 10-K", confidence=0.95,
                  extracted_at=date(2026, 1, 15))
dossier = builder.build()
report = dossier.completeness()
print(report)   # "Dossier PROG-001: 6% complete (1/17 fields) | Missing: ..."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


# ---------------------------------------------------------------------------
# Provenance wrapper
# ---------------------------------------------------------------------------

@dataclass
class ProvenanceField:
    """
    A single tracked field with full source attribution.

    Attributes
    ----------
    value:          The field value (str, float, bool, list, etc.)
    source:         Where this value came from, e.g. "ClinicalTrials.gov", "SEC 10-K"
    extracted_at:   Date the value was first extracted or recorded
    confidence:     0.0–1.0 extraction / attribution confidence
    last_verified:  Date the value was last checked against a primary source
    """
    value: object
    source: str
    extracted_at: date
    confidence: float
    last_verified: Optional[date] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"ProvenanceField.confidence must be in [0.0, 1.0], got {self.confidence}"
            )


# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------

@dataclass
class TrialSummary:
    """Lightweight trial descriptor stored inside a dossier."""
    nct_id: str
    phase: str
    status: str                         # recruiting, completed, terminated, etc.
    primary_endpoint: str
    enrollment_target: int
    estimated_completion: Optional[str] = None  # "YYYY-MM" or similar


# ---------------------------------------------------------------------------
# Completeness report
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DossierCompletenessReport:
    """
    Summary of how complete an AssetDossier is.

    A dossier used for valuation should have completeness_score >= 0.70
    and has_valuation == True before it is relied upon for investment decisions.
    """
    program_id: str
    completeness_score: float       # 0.0–1.0
    filled_fields: list[str]
    missing_fields: list[str]
    n_active_trials: int
    has_thesis: bool
    has_valuation: bool

    def __str__(self) -> str:
        pct = f"{self.completeness_score * 100:.0f}%"
        n_filled = len(self.filled_fields)
        n_total = n_filled + len(self.missing_fields)
        base = f"Dossier {self.program_id}: {pct} complete ({n_filled}/{n_total} fields)"
        if self.missing_fields:
            preview = ", ".join(self.missing_fields[:5])
            ellipsis = "…" if len(self.missing_fields) > 5 else ""
            base += f" | Missing: {preview}{ellipsis}"
        return base


# ---------------------------------------------------------------------------
# Core dossier
# ---------------------------------------------------------------------------

# Ordered list of material ProvenanceField attributes.
# Used by completeness() — order matters for consistent reporting.
_MATERIAL_FIELDS: list[str] = [
    "mechanism_of_action",
    "target",
    "modality",
    "current_phase",
    "indication",
    "biomarker_strategy",
    "endpoint_type",
    "safety_profile_summary",
    "peak_sales_estimate_musd",
    "addressable_patients",
    "competition_summary",
    "cash_runway_months",
    "quarterly_burn_musd",
    "next_catalyst_date",
    "model_pos",
    "model_rnpv_musd",
    "thesis_summary",
]


@dataclass
class AssetDossier:
    """
    Live, provenance-tracked dossier for one biotech drug program.

    Every material field is an Optional[ProvenanceField]. Fields that are
    None are explicitly missing and will appear in the completeness report.
    Use DossierBuilder to populate the dossier via a fluent API.

    Call completeness() before relying on a dossier for valuation or
    investment decisions.
    """

    # ── Identity ──────────────────────────────────────────────────────────
    program_id: str
    asset_name: str
    company: str

    # ── Core science ──────────────────────────────────────────────────────
    mechanism_of_action: Optional[ProvenanceField] = None   # str value
    target: Optional[ProvenanceField] = None                # str value
    modality: Optional[ProvenanceField] = None              # small_molecule / biologic / etc.

    # ── Development state ─────────────────────────────────────────────────
    current_phase: Optional[ProvenanceField] = None         # str
    indication: Optional[ProvenanceField] = None            # str (canonical)
    active_trials: list[TrialSummary] = field(default_factory=list)
    prior_trial_history: list[TrialSummary] = field(default_factory=list)

    # ── Clinical features ─────────────────────────────────────────────────
    biomarker_strategy: Optional[ProvenanceField] = None    # str
    endpoint_type: Optional[ProvenanceField] = None         # maps to EndpointType values
    safety_profile_summary: Optional[ProvenanceField] = None  # str

    # ── Commercial ────────────────────────────────────────────────────────
    peak_sales_estimate_musd: Optional[ProvenanceField] = None   # float
    addressable_patients: Optional[ProvenanceField] = None        # int
    competition_summary: Optional[ProvenanceField] = None         # str

    # ── Financials ────────────────────────────────────────────────────────
    cash_runway_months: Optional[ProvenanceField] = None    # float
    quarterly_burn_musd: Optional[ProvenanceField] = None   # float

    # ── Catalysts ─────────────────────────────────────────────────────────
    next_catalyst_date: Optional[ProvenanceField] = None            # str date
    next_catalyst_description: Optional[ProvenanceField] = None     # str

    # ── Valuation ─────────────────────────────────────────────────────────
    model_pos: Optional[ProvenanceField] = None             # float
    model_rnpv_musd: Optional[ProvenanceField] = None       # float
    market_implied_pos: Optional[ProvenanceField] = None    # float

    # ── Thesis ────────────────────────────────────────────────────────────
    thesis_summary: Optional[ProvenanceField] = None        # str
    variant_view: Optional[ProvenanceField] = None          # str
    key_risks: list[str] = field(default_factory=list)
    kill_criteria: list[str] = field(default_factory=list)

    # ── Meta ──────────────────────────────────────────────────────────────
    created_at: Optional[date] = None
    last_updated: Optional[date] = None
    analyst: Optional[str] = None

    # ── Public methods ────────────────────────────────────────────────────

    def completeness(self) -> DossierCompletenessReport:
        """
        Return a report describing which material fields are filled vs missing.

        The 17 material fields are defined in _MATERIAL_FIELDS. Fields outside
        that list (active_trials, key_risks, etc.) do not affect the score but
        are reflected in n_active_trials and has_thesis.
        """
        filled: list[str] = []
        missing: list[str] = []
        for fname in _MATERIAL_FIELDS:
            if getattr(self, fname, None) is not None:
                filled.append(fname)
            else:
                missing.append(fname)
        score = len(filled) / max(len(_MATERIAL_FIELDS), 1)
        return DossierCompletenessReport(
            program_id=self.program_id,
            completeness_score=round(score, 4),
            filled_fields=filled,
            missing_fields=missing,
            n_active_trials=len(self.active_trials),
            has_thesis=self.thesis_summary is not None,
            has_valuation=self.model_rnpv_musd is not None,
        )

    def get_field_value(self, field_name: str) -> object:
        """
        Return the raw value of a ProvenanceField, or None if not set.

        This avoids callers having to unwrap ProvenanceField.value manually.
        """
        attr = getattr(self, field_name, None)
        if attr is None:
            return None
        if isinstance(attr, ProvenanceField):
            return attr.value
        return attr
