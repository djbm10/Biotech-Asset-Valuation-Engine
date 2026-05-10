"""
CommercialModelProfile — named SG&A ramp archetypes for Sprint D2.

Each profile maps to a calibrated set of (sgna_rate_launch, sgna_rate_mature,
sgna_ramp_years) values stored in industry_assumptions.yaml under
commercial.commercial_model_profiles.

Usage::

    from bve.models.commercial_model_profile import CommercialModelProfile

    market = MarketModel(
        ...,
        commercial_model=CommercialModelProfile.PARTNERED,
    )

Individual SG&A fields always override the profile on a per-field basis.
"""
from enum import Enum


class CommercialModelProfile(str, Enum):
    """Named commercial SG&A profile loaded from YAML at MarketModel construction."""

    SELF_COMMERCIALIZED_SPECIALTY = "self_commercialized_specialty"
    """Self-commercialized specialty product (oncology/immunology).

    Mirrors the existing specialty_pharma default (launch 40%, mature 20%, 5 yr).
    Use when you want to make the commercial intent explicit without changing numbers.
    """

    RARE_DISEASE_KOL = "rare_disease_kol"
    """Rare-disease KOL model: small targeted team, high MSL density.

    Lower absolute SG&A due to smaller team size; faster ramp maturation
    because the patient population is small and quickly saturated.
    (launch 25%, mature 12%, 4 yr)
    """

    PARTNERED = "partnered"
    """Partner bears commercial costs; company receives milestones and royalties.

    SG&A represents only co-promotion oversight, medical affairs, and G&A overlay.
    (launch 12%, mature 8%, 3 yr)
    """

    ROYALTY_ONLY = "royalty_only"
    """Pure royalty stream — no company commercial infrastructure.

    Essentially zero SG&A; a small G&A / IP maintenance allocation only.
    (launch 2%, mature 2%, 1 yr)
    """

    PRIMARY_CARE_SALESFORCE = "primary_care_salesforce"
    """Large primary-care indication requiring broad rep coverage.

    Highest SG&A profile; slow maturation as market develops and rep
    productivity builds.
    (launch 55%, mature 30%, 7 yr)
    """

    HOSPITAL_SPECIALTY = "hospital_specialty"
    """Hospital / account-based selling model.

    Smaller targeted sales force but significant medical affairs and
    market-access investment.
    (launch 20%, mature 12%, 4 yr)
    """
