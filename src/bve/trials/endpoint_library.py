"""Disease-specific endpoint dictionaries: commonly accepted endpoints, surrogate status, meaningfulness thresholds, and historical precedent."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class EndpointEntry(BaseModel):
    name: str
    disease_area: str
    endpoint_type: str          # "primary" / "surrogate" / "co-primary" / "composite"
    is_surrogate: bool = False
    regulatory_acceptability: str   # "established" / "likely_acceptable" / "controversial" / "not_accepted"
    clinically_meaningful_threshold: Optional[str] = None   # e.g. "HR < 0.75" or "ORR > 30%"
    common_failure_modes: list[str] = Field(default_factory=list)
    historical_precedent: list[str] = Field(default_factory=list)   # approved drugs using this endpoint
    notes: Optional[str] = None


class EndpointLibrary:
    """
    Look up disease-specific endpoint information.
    Pre-seeded with oncology, rare disease, and immunology entries.
    """

    def __init__(self) -> None:
        self._entries: dict[str, list[EndpointEntry]] = {}
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        defaults: list[EndpointEntry] = [
            # Oncology
            EndpointEntry(name="Overall Survival", disease_area="oncology",
                endpoint_type="primary", is_surrogate=False,
                regulatory_acceptability="established",
                clinically_meaningful_threshold="HR < 0.80",
                historical_precedent=["bevacizumab OS improvement", "nivolumab OS in NSCLC"]),
            EndpointEntry(name="Progression-Free Survival", disease_area="oncology",
                endpoint_type="surrogate", is_surrogate=True,
                regulatory_acceptability="likely_acceptable",
                clinically_meaningful_threshold="HR < 0.75 or median PFS improvement >= 2 months",
                common_failure_modes=["Does not translate to OS benefit", "Investigator assessment bias"],
                notes="Accepted as primary for accelerated approval; OS confirmation often required"),
            EndpointEntry(name="Objective Response Rate", disease_area="oncology",
                endpoint_type="surrogate", is_surrogate=True,
                regulatory_acceptability="likely_acceptable",
                clinically_meaningful_threshold="ORR > 20-30% in relapsed/refractory",
                common_failure_modes=["Short duration of response", "No OS benefit"],
                notes="Used for accelerated approval in single-arm trials"),
            EndpointEntry(name="Complete Remission Rate", disease_area="hematology",
                endpoint_type="surrogate", is_surrogate=True,
                regulatory_acceptability="established",
                clinically_meaningful_threshold="CR > 20% in r/r setting",
                historical_precedent=["venetoclax", "enasidenib"]),
            # Rare disease
            EndpointEntry(name="Six-Minute Walk Distance", disease_area="rare_disease",
                endpoint_type="primary", is_surrogate=False,
                regulatory_acceptability="established",
                clinically_meaningful_threshold="Improvement >= 20-30 meters",
                common_failure_modes=["Ceiling effect", "High variability", "Placebo response"],
                historical_precedent=["macitentan in PAH", "selexipag"]),
            EndpointEntry(name="Forced Vital Capacity", disease_area="rare_disease",
                endpoint_type="primary", is_surrogate=False,
                regulatory_acceptability="established",
                clinically_meaningful_threshold="Slope improvement vs placebo",
                historical_precedent=["nintedanib in IPF"]),
            EndpointEntry(name="Annualized Relapse Rate", disease_area="neurology",
                endpoint_type="primary", is_surrogate=True,
                regulatory_acceptability="established",
                clinically_meaningful_threshold="Reduction >= 30-50% vs comparator",
                historical_precedent=["ocrelizumab", "natalizumab in MS"]),
            # Immunology
            EndpointEntry(name="ACR20/50/70", disease_area="rheumatology",
                endpoint_type="primary", is_surrogate=False,
                regulatory_acceptability="established",
                clinically_meaningful_threshold="ACR20 > 20% over placebo",
                common_failure_modes=["High placebo response", "Inadequate washout"]),
            EndpointEntry(name="PASI 75/90/100", disease_area="dermatology",
                endpoint_type="primary", is_surrogate=False,
                regulatory_acceptability="established",
                clinically_meaningful_threshold="PASI 75 > 70% vs placebo < 5%",
                historical_precedent=["secukinumab", "ixekizumab", "risankizumab"]),
        ]
        for e in defaults:
            self._entries.setdefault(e.disease_area, []).append(e)

    def add(self, entry: EndpointEntry) -> None:
        self._entries.setdefault(entry.disease_area, []).append(entry)

    def get(self, disease_area: str, endpoint_name: Optional[str] = None) -> list[EndpointEntry]:
        """Return all entries for a disease area, optionally filtered by name."""
        entries = self._entries.get(disease_area, [])
        if endpoint_name is not None:
            entries = [e for e in entries if endpoint_name.lower() in e.name.lower()]
        return entries

    def accepted_primary_endpoints(self, disease_area: str) -> list[EndpointEntry]:
        return [e for e in self.get(disease_area)
                if e.regulatory_acceptability == "established" and e.endpoint_type == "primary"]

    def surrogate_endpoints(self, disease_area: str) -> list[EndpointEntry]:
        return [e for e in self.get(disease_area) if e.is_surrogate]

    def all_disease_areas(self) -> list[str]:
        return list(self._entries.keys())
