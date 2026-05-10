"""
LaunchArchetype — named presets for UptakeCurve shape and ramp parameters.

Each archetype encapsulates the typical commercial launch dynamics for a
specific drug-market situation.  Use them via MarketModel.launch_archetype
or UptakeCurve.from_archetype() directly.

Any MarketModel field explicitly set by the caller (years_to_peak,
adoption_curve_mode, use_s_curve) overrides the archetype default for
that parameter, so archetypes function as intelligent defaults rather
than rigid constraints.

Archetype quick-reference
--------------------------

  rapid_orphan
    Shape: S-curve · Years-to-peak: 2
    Small rare-disease patient pool, high unmet need, specialist KOL-driven.
    Examples: Spinraza (SMA), Soliris (PNH).

  oncology_specialist
    Shape: S-curve · Years-to-peak: 4
    Targeted oncology with companion diagnostic and NCCN guideline path.
    Examples: osimertinib (EGFR+), palbociclib (HR+ BC), venetoclax (CLL).

  primary_care_slow
    Shape: linear · Years-to-peak: 7
    Mass-market chronic disease needing broad PCP coverage.
    Examples: SGLT2i, newer antidepressants, nasal steroids.

  competitive_late
    Shape: slow S-curve · Years-to-peak: 5
    2nd/3rd entrant in established class; suppressed early ramp.
    Examples: 2nd-gen PCSK9i, follower KRAS G12C inhibitor.

  step_edit_restricted
    Shape: slow S-curve · Years-to-peak: 4
    Prior-authorization or step-therapy payer gate produces flat Year 1.
    Examples: branded biologics in RA (step through DMARDs), specialty CNS.

  gene_therapy_bolus
    Shape: bolus · Years-to-peak: 1
    Year 1 = full peak (prevalent backlog); Year 2+ = ongoing_fraction × peak.
    Examples: Zolgensma (SMA), Luxturna (RPE65), Hemgenix (haemophilia B).

Shape vocabulary
----------------
  s_curve       Standard logistic (k = 8/ytp, midpoint = ytp/2).
                Inflection at years_to_peak/2; symmetric around midpoint.

  slow_s_curve  Flatter logistic (k = 6/ytp, midpoint = 0.65 × ytp).
                Suppresses Year 1-2 uptake; used for competitive_late and
                step_edit_restricted to model payer / switching barriers.

  linear        Simple linear ramp to peak, then plateau.
                Appropriate for primary care where adoption is PCP-rep driven,
                not specialist-opinion driven.

  bolus         Year 1 at peak_penetration; Year 2+ at ongoing_fraction × peak.
                Represents the prevalent-backlog absorption phenomenon of
                curative one-time treatments.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LaunchArchetype(str, Enum):
    """Named launch archetypes for UptakeCurve presets."""

    RAPID_ORPHAN = "rapid_orphan"
    ONCOLOGY_SPECIALIST = "oncology_specialist"
    PRIMARY_CARE_SLOW = "primary_care_slow"
    COMPETITIVE_LATE = "competitive_late"
    STEP_EDIT_RESTRICTED = "step_edit_restricted"
    GENE_THERAPY_BOLUS = "gene_therapy_bolus"


@dataclass(frozen=True)
class ArchetypeSpec:
    """
    Canonical defaults for a named launch archetype.

    Fields
    ------
    years_to_peak : int
        Default years from commercial launch to peak penetration.
    shape : str
        Curve shape: "s_curve" | "slow_s_curve" | "linear" | "bolus".
    bolus_ongoing_fraction : float
        For gene_therapy_bolus only: Year 2+ penetration = peak × fraction.
        Represents the ratio of annual incident patients to the initial backlog.
        Defaults to 0.08 (8%); adjust to match the disease's incidence/prevalence ratio.
    description : str
        One-line description.
    when_to_use : str
        Detailed guidance on when this archetype is appropriate.
    """
    years_to_peak: int
    shape: str
    bolus_ongoing_fraction: float = 0.08
    description: str = ""
    when_to_use: str = ""


ARCHETYPE_SPECS: dict[LaunchArchetype, ArchetypeSpec] = {
    LaunchArchetype.RAPID_ORPHAN: ArchetypeSpec(
        years_to_peak=2,
        shape="s_curve",
        description=(
            "Rapid uptake for orphan/rare-disease drugs targeting a small, "
            "well-identified specialist patient population."
        ),
        when_to_use=(
            "Use when: rare disease (US prevalence < 200k), strong unmet need, "
            "specialist-only prescribing, clear diagnostic biomarker, and active "
            "patient advocacy enabling fast identification. "
            "Payer dynamics: often favourable (rare disease exception, named-patient). "
            "Typical years_to_peak: 2–3. "
            "Examples: Spinraza (SMA), Soliris (PNH), Hemlibra (haemophilia A with inhibitors)."
        ),
    ),
    LaunchArchetype.ONCOLOGY_SPECIALIST: ArchetypeSpec(
        years_to_peak=4,
        shape="s_curve",
        description=(
            "Standard oncology specialist launch ramp for targeted solid-tumor "
            "or haematology drugs guided by a molecular biomarker."
        ),
        when_to_use=(
            "Use when: targeted oncology (NSCLC, HR+ BC, AML, CLL) with companion "
            "diagnostic, guideline incorporation expected within 2–3 years. "
            "Adoption path: ESMO/ASCO abstract → full presentation → NCCN guideline → "
            "tumor board standard of care. "
            "Typical years_to_peak: 3–5. "
            "Examples: osimertinib (EGFR+), palbociclib (HR+ BC), venetoclax (CLL)."
        ),
    ),
    LaunchArchetype.PRIMARY_CARE_SLOW: ArchetypeSpec(
        years_to_peak=7,
        shape="linear",
        description=(
            "Slow, broad-based linear adoption across a large primary care prescriber base."
        ),
        when_to_use=(
            "Use when: mass-market chronic disease (T2D, hypertension, COPD, MDD) "
            "requiring coverage of tens of thousands of PCPs. "
            "Adoption is PCP-rep driven, not specialist-KOL driven — linear ramp is "
            "appropriate because each rep call adds incremental prescribers rather "
            "than triggering a class-wide shift. Payer formulary placement (preferred "
            "brand negotiation) typically takes 12–24 months and limits early uptake. "
            "Typical years_to_peak: 6–9. "
            "Examples: SGLT2i class ramp, newer antidepressants, nasal corticosteroids."
        ),
    ),
    LaunchArchetype.COMPETITIVE_LATE: ArchetypeSpec(
        years_to_peak=5,
        shape="slow_s_curve",
        description=(
            "Late or 2nd-to-market entrant in an established therapeutic class, "
            "requiring differentiation data to displace incumbent preferred brands."
        ),
        when_to_use=(
            "Use when: drug enters a market where 1–2 entrenched competitors hold "
            "preferred formulary status and prescriber habits are set. "
            "Early uptake is suppressed by switching inertia, step-edit policies "
            "favouring incumbent, and need for direct head-to-head trial evidence. "
            "The slow S-curve (vs standard oncology_specialist) front-loads less and "
            "ramps more gradually before accelerating as differentiation data accumulates. "
            "Typical years_to_peak: 4–6. "
            "Examples: 2nd-generation PCSK9i, 2nd-wave KRAS G12C inhibitor, "
            "3rd-gen BTK inhibitor in CLL."
        ),
    ),
    LaunchArchetype.STEP_EDIT_RESTRICTED: ArchetypeSpec(
        years_to_peak=4,
        shape="slow_s_curve",
        description=(
            "Access restricted by step-therapy or prior-authorisation requirements, "
            "producing very low Year 1 penetration followed by a delayed ramp."
        ),
        when_to_use=(
            "Use when: payers require documented failure on a generic/preferred agent "
            "before approving the new drug. Year 1 penetration is very low (5–15% of "
            "peak) because most prescriptions are rejected until step-edit workflows "
            "are established with individual payer medical directors. "
            "Ramp accelerates in Years 2–3 as prior-auth processes mature and payer "
            "contracts are renegotiated at annual formulary cycles. "
            "Typical years_to_peak: 3–5. "
            "Examples: branded biologics in RA (step through DMARDs + MTX), "
            "specialty CNS agents (must fail 2 antidepressants), "
            "premium insulin analogues in T1D."
        ),
    ),
    LaunchArchetype.GENE_THERAPY_BOLUS: ArchetypeSpec(
        years_to_peak=1,
        shape="bolus",
        bolus_ongoing_fraction=0.08,
        description=(
            "One-time curative gene/cell therapy with a large Year 1 backlog spike, "
            "then drops to a low ongoing incident-patient steady state."
        ),
        when_to_use=(
            "Use when: single-administration curative or durable treatment (gene therapy, "
            "CAR-T, one-time surgical intervention) where Year 1 revenue is dominated "
            "by the backlog of prevalent patients who have been waiting for approval. "
            "Year 1: penetration = peak_penetration (backlog absorption). "
            "Year 2+: penetration = peak_penetration × bolus_ongoing_fraction "
            "(incident-only patients relative to initial backlog). "
            "bolus_ongoing_fraction default = 0.08; set to incidence/prevalence ratio "
            "of the specific disease (e.g., 0.03–0.05 for very-rare diseases). "
            "Pair with disease_model='incident_one_time' on PatientPool for full "
            "patient-flow consistency. "
            "Examples: Zolgensma (SMA, ~0.04 ratio), Luxturna (RPE65 retinal dystrophy), "
            "Hemgenix (haemophilia B, ~0.06 ratio)."
        ),
    ),
}
