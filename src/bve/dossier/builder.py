"""
DossierBuilder — fluent API for assembling an AssetDossier.

Usage
-----
from bve.dossier.builder import DossierBuilder
from bve.dossier.dossier import TrialSummary
from datetime import date

dossier = (
    DossierBuilder("PROG-001", "Pembrolizumab", "Merck")
    .set_field("mechanism_of_action", "PD-1 inhibitor",
               source="SEC 10-K", confidence=0.95,
               extracted_at=date(2026, 1, 15))
    .set_field("current_phase", "phase_3",
               source="ClinicalTrials.gov", confidence=0.99,
               extracted_at=date(2026, 3, 1))
    .add_active_trial(TrialSummary(
        nct_id="NCT01234567", phase="phase_3", status="recruiting",
        primary_endpoint="OS", enrollment_target=800,
    ))
    .set_analyst("djmann")
    .build()
)
print(dossier.completeness())
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from bve.dossier.dossier import (
    AssetDossier,
    DossierCompletenessReport,
    ProvenanceField,
    TrialSummary,
    _MATERIAL_FIELDS,
)

# All attributes on AssetDossier that accept a ProvenanceField value.
_PROVENANCE_ATTRS: frozenset[str] = frozenset([
    "mechanism_of_action", "target", "modality",
    "current_phase", "indication",
    "biomarker_strategy", "endpoint_type", "safety_profile_summary",
    "peak_sales_estimate_musd", "addressable_patients", "competition_summary",
    "cash_runway_months", "quarterly_burn_musd",
    "next_catalyst_date", "next_catalyst_description",
    "model_pos", "model_rnpv_musd", "market_implied_pos",
    "thesis_summary", "variant_view",
])


class DossierBuilder:
    """
    Fluent builder for AssetDossier.

    All set_field / add_* methods return self so calls can be chained.
    Call build() to produce the final, immutable-style AssetDossier.
    """

    def __init__(self, program_id: str, asset_name: str, company: str) -> None:
        self._program_id = program_id
        self._asset_name = asset_name
        self._company = company
        self._fields: dict[str, ProvenanceField] = {}
        self._active_trials: list[TrialSummary] = []
        self._prior_trials: list[TrialSummary] = []
        self._key_risks: list[str] = []
        self._kill_criteria: list[str] = []
        self._analyst: Optional[str] = None
        self._created_at: Optional[date] = None

    # ── Field setters ─────────────────────────────────────────────────────

    def set_field(
        self,
        field_name: str,
        value: object,
        source: str,
        confidence: float,
        extracted_at: date,
        last_verified: Optional[date] = None,
    ) -> "DossierBuilder":
        """
        Set a tracked ProvenanceField on the dossier.

        Parameters
        ----------
        field_name:
            One of the recognised ProvenanceField attributes (see _PROVENANCE_ATTRS).
        value:
            The field value (str, float, int, bool, list, etc.).
        source:
            Human-readable source description, e.g. "ClinicalTrials.gov".
        confidence:
            Extraction / attribution confidence in [0.0, 1.0].
        extracted_at:
            Date the value was first extracted or recorded.
        last_verified:
            Date the value was last checked against a primary source (optional).

        Returns
        -------
        self — for method chaining.

        Raises
        ------
        ValueError if field_name is not a recognised ProvenanceField attribute.
        """
        if field_name not in _PROVENANCE_ATTRS:
            raise ValueError(
                f"'{field_name}' is not a recognised ProvenanceField attribute. "
                f"Valid names: {sorted(_PROVENANCE_ATTRS)}"
            )
        self._fields[field_name] = ProvenanceField(
            value=value,
            source=source,
            extracted_at=extracted_at,
            confidence=confidence,
            last_verified=last_verified,
        )
        return self

    def add_active_trial(self, trial: TrialSummary) -> "DossierBuilder":
        """Add an ongoing clinical trial to the dossier."""
        self._active_trials.append(trial)
        return self

    def add_prior_trial(self, trial: TrialSummary) -> "DossierBuilder":
        """Add a completed or terminated trial to the historical record."""
        self._prior_trials.append(trial)
        return self

    def add_risk(self, risk: str) -> "DossierBuilder":
        """Add a key risk string to the dossier."""
        self._key_risks.append(risk)
        return self

    def add_kill_criterion(self, criterion: str) -> "DossierBuilder":
        """Add an explicit kill criterion (threshold that would invalidate the thesis)."""
        self._kill_criteria.append(criterion)
        return self

    def set_analyst(self, analyst: str) -> "DossierBuilder":
        """Record the analyst responsible for this dossier."""
        self._analyst = analyst
        return self

    def set_created_at(self, created_at: date) -> "DossierBuilder":
        self._created_at = created_at
        return self

    # ── Build ─────────────────────────────────────────────────────────────

    def build(self) -> AssetDossier:
        """
        Construct and return the AssetDossier.

        Fields that were not set via set_field() remain None in the dossier
        and will appear in the completeness report as missing.
        """
        kwargs: dict[str, object] = {
            "program_id": self._program_id,
            "asset_name": self._asset_name,
            "company": self._company,
            "active_trials": list(self._active_trials),
            "prior_trial_history": list(self._prior_trials),
            "key_risks": list(self._key_risks),
            "kill_criteria": list(self._kill_criteria),
            "analyst": self._analyst,
            "created_at": self._created_at,
        }
        # Inject all set ProvenanceFields
        for fname, pf in self._fields.items():
            kwargs[fname] = pf

        return AssetDossier(**kwargs)
