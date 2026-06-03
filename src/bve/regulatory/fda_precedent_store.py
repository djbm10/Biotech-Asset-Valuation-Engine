"""Store and query FDA approval/CRL precedent for indication-modality pairs."""
from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class FDAPrecedentRecord(BaseModel):
    record_id: str
    drug_name: str
    indication: str
    modality: str               # "small_molecule" / "biologic" / "cell_therapy" / "gene_therapy" / "adc" / "rna"
    therapeutic_area: str
    action_type: str            # "approval" / "crl" / "accelerated_approval" / "breakthrough" / "fast_track" / "rtor"
    action_date: date
    primary_endpoint_used: Optional[str] = None
    was_surrogate: bool = False
    label_breadth: str = "standard"     # "broad" / "standard" / "narrow" / "biomarker_selected"
    adcom_held: bool = False
    adcom_vote: Optional[str] = None    # e.g. "14-1 in favor"
    crl_reason: Optional[str] = None    # only for CRL records
    safety_issue: bool = False
    safety_description: Optional[str] = None
    post_market_commitment: bool = False
    notes: Optional[str] = None
    source: str = "manual"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FDAPrecedentStore:
    """In-memory FDA precedent library with query methods."""

    def __init__(self) -> None:
        self._records: dict[str, FDAPrecedentRecord] = {}
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        seeds = [
            FDAPrecedentRecord(record_id="fda_001", drug_name="pembrolizumab",
                indication="NSCLC first-line PD-L1 >= 50%", modality="biologic",
                therapeutic_area="oncology", action_type="approval",
                action_date=date(2016, 10, 24), primary_endpoint_used="PFS",
                was_surrogate=True, label_breadth="biomarker_selected"),
            FDAPrecedentRecord(record_id="fda_002", drug_name="venetoclax",
                indication="CLL 17p deletion", modality="small_molecule",
                therapeutic_area="hematology", action_type="accelerated_approval",
                action_date=date(2016, 4, 11), primary_endpoint_used="ORR",
                was_surrogate=True, label_breadth="biomarker_selected"),
            FDAPrecedentRecord(record_id="fda_003", drug_name="ivacaftor",
                indication="CF G551D", modality="small_molecule",
                therapeutic_area="rare_disease", action_type="breakthrough",
                action_date=date(2012, 1, 31), primary_endpoint_used="FEV1",
                was_surrogate=False, label_breadth="biomarker_selected"),
            FDAPrecedentRecord(record_id="fda_004", drug_name="tisagenlecleucel",
                indication="r/r ALL", modality="cell_therapy",
                therapeutic_area="hematology", action_type="accelerated_approval",
                action_date=date(2017, 8, 30), primary_endpoint_used="CR rate",
                was_surrogate=True, label_breadth="narrow", safety_issue=True,
                safety_description="CRS and neurotoxicity; REMS required"),
        ]
        for s in seeds:
            self._records[s.record_id] = s

    def add(self, record: FDAPrecedentRecord) -> None:
        self._records[record.record_id] = record

    def get(self, record_id: str) -> Optional[FDAPrecedentRecord]:
        return self._records.get(record_id)

    def query(
        self,
        *,
        therapeutic_area: Optional[str] = None,
        indication: Optional[str] = None,
        modality: Optional[str] = None,
        action_type: Optional[str] = None,
    ) -> list[FDAPrecedentRecord]:
        results = list(self._records.values())
        if therapeutic_area:
            results = [r for r in results if r.therapeutic_area == therapeutic_area]
        if indication:
            results = [r for r in results if indication.lower() in r.indication.lower()]
        if modality:
            results = [r for r in results if r.modality == modality]
        if action_type:
            results = [r for r in results if r.action_type == action_type]
        return sorted(results, key=lambda r: r.action_date, reverse=True)

    def crl_records(self, therapeutic_area: Optional[str] = None) -> list[FDAPrecedentRecord]:
        return self.query(therapeutic_area=therapeutic_area, action_type="crl")

    def surrogate_approvals(self, therapeutic_area: Optional[str] = None) -> list[FDAPrecedentRecord]:
        return [r for r in self.query(therapeutic_area=therapeutic_area)
                if r.was_surrogate and r.action_type in ("approval", "accelerated_approval")]

    def all_records(self) -> list[FDAPrecedentRecord]:
        return list(self._records.values())
