from typing import Optional

from pydantic import BaseModel, Field


class Indication(BaseModel):
    """Epidemiological and clinical context for a disease indication."""

    id: str
    name: str
    icd10_codes: list[str] = Field(default_factory=list)

    # Epidemiology (US unless noted)
    prevalence: Optional[int] = Field(
        default=None, gt=0,
        description="Total patients living with condition (US)"
    )
    annual_incidence: Optional[int] = Field(
        default=None, gt=0,
        description="New cases per year (US)"
    )
    diagnosis_rate: float = Field(
        default=0.80, gt=0.0, le=1.0,
        description="Fraction of patients who receive a formal diagnosis"
    )
    treatment_rate: float = Field(
        default=0.70, gt=0.0, le=1.0,
        description="Fraction of diagnosed patients who receive systemic therapy"
    )
    eligible_fraction: float = Field(
        default=1.0, gt=0.0, le=1.0,
        description="Fraction of treated patients eligible for this specific drug (biomarker, line, etc.)"
    )

    unmet_need_score: int = Field(
        default=3, ge=1, le=5,
        description="1=low, 5=very high unmet need; informs pricing and penetration assumptions"
    )
    notes: Optional[str] = None

    @property
    def addressable_patients(self) -> Optional[int]:
        """Estimated addressable US patient pool per year."""
        base = self.annual_incidence or self.prevalence
        if base is None:
            return None
        return int(base * self.diagnosis_rate * self.treatment_rate * self.eligible_fraction)
