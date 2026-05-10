"""
Revenue model sanity checks — warn on unrealistic commercial assumptions.

These checks do NOT change model behavior.  They emit SanityWarning objects
that callers (e.g. ValuationEngine.run()) convert to Python warnings.warn()
calls so analysts see them without changing computed values.

Seven checks implemented
------------------------
1. global_peak_exceeds_5x_us       Global peak revenue > 5× US baseline peak
2. eu5_exceeds_us_revenue          EU5 revenue_ratio > 1.0 → EU5 peak > US peak
3. china_ratio_high                China revenue_ratio > 0.40 of US
4. payer_low_penetration_high      access_probability < 0.5 AND peak_penetration > 0.20
5. step_edit_double_counted        step_edit_restricted archetype + step_edit_risk > 0
6. gene_therapy_bolus_wrong_model  gene_therapy_bolus archetype + non-one-time disease model
7. incident_one_time_missing_data  incident_one_time disease model + missing annual_incidence_k
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bve.models.market_model import MarketModel


@dataclass(frozen=True)
class SanityWarning:
    """A non-fatal commercial assumption warning."""

    code: str
    """Machine-readable identifier, e.g. 'global_peak_exceeds_5x_us'."""

    message: str
    """Human-readable explanation with specific values."""

    severity: str = "warning"
    """'warning' (likely mis-specified) or 'info' (unusual but valid)."""


def check_commercial_assumptions(market_model: "MarketModel") -> list[SanityWarning]:
    """
    Run all sanity checks against a finalized MarketModel.

    Returns a (possibly empty) list of SanityWarning objects.  Does not
    modify the model or raise exceptions.

    Callers are responsible for converting warnings to warnings.warn() calls.
    """
    issues: list[SanityWarning] = []
    issues.extend(_check_global_exceeds_5x_us(market_model))
    issues.extend(_check_eu5_exceeds_us(market_model))
    issues.extend(_check_china_ratio_high(market_model))
    issues.extend(_check_payer_low_penetration_high(market_model))
    issues.extend(_check_step_edit_double_counted(market_model))
    issues.extend(_check_gene_therapy_bolus_wrong_model(market_model))
    issues.extend(_check_incident_one_time_missing_data(market_model))
    return issues


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_global_exceeds_5x_us(mm: "MarketModel") -> list[SanityWarning]:
    """Check 1: global peak > 5× US peak (requires geography_split)."""
    if mm.geography_split is None:
        return []
    eff_life = mm._effective_patent_life()
    # US-only peak: iterate _us_base_revenue_in_year (no geography scaling)
    us_peak = max(
        (mm._us_base_revenue_in_year(y) for y in range(1, eff_life + 1)),
        default=0.0,
    )
    global_peak = mm.peak_sales_millions  # already iterates all regions
    if us_peak > 1e-6 and global_peak > 5.0 * us_peak:
        ratio = global_peak / us_peak
        return [SanityWarning(
            code="global_peak_exceeds_5x_us",
            message=(
                f"Asset '{mm.asset_id}': global peak revenue (${global_peak:.1f}M) is "
                f"{ratio:.1f}× the US-only peak (${us_peak:.1f}M). "
                "A ratio above 5× is unusual for most therapeutic areas — verify that "
                "geography revenue_ratio values reflect realistic ex-US pricing. "
                "Typical global/US multipliers: oncology 1.5–2.2×, rare disease 1.3–1.8×."
            ),
        )]
    return []


def _check_eu5_exceeds_us(mm: "MarketModel") -> list[SanityWarning]:
    """Check 2: EU5 revenue_ratio > 1.0 → EU5 peak revenue exceeds US peak."""
    if mm.geography_split is None or mm.geography_split.eu5 is None:
        return []
    eu5 = mm.geography_split.eu5
    if eu5.revenue_ratio <= 1.0:
        return []
    return [SanityWarning(
        code="eu5_exceeds_us_revenue",
        message=(
            f"Asset '{mm.asset_id}': EU5 revenue_ratio={eu5.revenue_ratio:.2f} > 1.0. "
            "This means EU5 peak revenue exceeds the US peak, which is atypical — "
            "US pricing is generally higher than EU5 for specialty drugs. "
            "Verify this is intentional (e.g., rare disease with EU-first launch). "
            "If unintentional, typical EU5 revenue_ratio is 0.28–0.40. "
            "Suppress by setting allow_eu5_above_us=True in the geography config."
        ),
    )]


def _check_china_ratio_high(mm: "MarketModel") -> list[SanityWarning]:
    """Check 3: China revenue_ratio unusually high (> 0.40 of US)."""
    if mm.geography_split is None or mm.geography_split.china is None:
        return []
    china = mm.geography_split.china
    # Effective scalar includes reimbursement_probability and approval_probability
    effective_ratio = china.effective_revenue_scalar
    threshold = 0.40
    if effective_ratio <= threshold:
        return []
    return [SanityWarning(
        code="china_ratio_high",
        message=(
            f"Asset '{mm.asset_id}': China effective revenue ratio={effective_ratio:.2f} "
            f"(revenue_ratio={china.revenue_ratio:.2f} × reimbursement={china.reimbursement_probability:.2f} "
            f"× approval={china.probability_of_regional_approval:.2f}) "
            f"exceeds the {threshold:.0%} threshold. "
            "China net pricing is typically 20–35% of US for specialty drugs due to "
            "NRDL negotiations. Ratios above 40% imply volume assumptions that may "
            "be aggressive. Verify against comparator products' China revenue disclosures."
        ),
        severity="info",
    )]


def _check_payer_low_penetration_high(mm: "MarketModel") -> list[SanityWarning]:
    """Check 4: access_probability < 0.5 AND peak_penetration > 0.20."""
    if mm.payer_access is None:
        return []
    access = mm.payer_access.access_probability
    penetration = mm.peak_penetration
    access_threshold = 0.50
    penetration_threshold = 0.20
    if access >= access_threshold or penetration <= penetration_threshold:
        return []
    return [SanityWarning(
        code="payer_low_penetration_high",
        message=(
            f"Asset '{mm.asset_id}': access_probability={access:.0%} is below "
            f"{access_threshold:.0%} but peak_penetration={penetration:.0%} exceeds "
            f"{penetration_threshold:.0%}. "
            "Low payer access limits the addressable patient pool — a high gross penetration "
            "assumption may be optimistic when most plans haven't granted formulary access. "
            "Consider whether peak_penetration reflects the pre-access gross opportunity "
            "or the effective post-access share. "
            "PayerAccessModel scales peak penetration by access_probability × (1 − PA burden × 0.5), "
            "so the effective penetration will be lower than the stated peak_penetration."
        ),
    )]


def _check_step_edit_double_counted(mm: "MarketModel") -> list[SanityWarning]:
    """Check 5: step_edit_restricted archetype + step_edit_risk > 0."""
    from bve.models.launch_archetype import LaunchArchetype  # local import
    if mm.launch_archetype != LaunchArchetype.STEP_EDIT_RESTRICTED:
        return []
    if mm.payer_access is None or mm.payer_access.step_edit_risk == 0.0:
        return []
    return [SanityWarning(
        code="step_edit_double_counted",
        message=(
            f"Asset '{mm.asset_id}': launch_archetype='step_edit_restricted' combined with "
            f"payer_access.step_edit_risk={mm.payer_access.step_edit_risk:.0%}. "
            "The step_edit_restricted archetype already suppresses the Year 1–3 ramp via a "
            "slow S-curve (k=6/ytp, midpoint=0.65×ytp). Adding step_edit_risk on top applies "
            "an additional multiplicative suppression that likely double-counts the same barrier. "
            "Recommended: use step_edit_risk=0.0 with the archetype, OR use a different archetype "
            "(e.g., competitive_late) with an explicit step_edit_risk."
        ),
    )]


def _check_gene_therapy_bolus_wrong_model(mm: "MarketModel") -> list[SanityWarning]:
    """Check 6: gene_therapy_bolus archetype + non-one-time disease model."""
    from bve.models.launch_archetype import LaunchArchetype  # local import
    if mm.launch_archetype != LaunchArchetype.GENE_THERAPY_BOLUS:
        return []
    if mm.commercial_inputs is None:
        return []
    pool = getattr(mm.commercial_inputs, "patient_pool", None)
    if pool is None:
        return []
    if pool.disease_model == "incident_one_time":
        return []
    return [SanityWarning(
        code="gene_therapy_bolus_wrong_model",
        message=(
            f"Asset '{mm.asset_id}': launch_archetype='gene_therapy_bolus' is designed for "
            f"curative/one-time treatments, but patient_pool.disease_model='{pool.disease_model}'. "
            "gene_therapy_bolus produces a Year-1 peak (backlog absorption) followed by "
            "an ongoing fraction (~8% of peak) representing annual incident patients. "
            "This shape is only coherent when the disease model is 'incident_one_time'. "
            "If using 'prevalent' or 'incident_chronic', the bolus Year-1 spike will overstate "
            "revenue by treating a recurring patient population as a one-time treated cohort. "
            "Recommended: set patient_pool.disease_model='incident_one_time' or use a "
            "different launch_archetype."
        ),
    )]


def _check_incident_one_time_missing_data(mm: "MarketModel") -> list[SanityWarning]:
    """Check 7: incident_one_time disease model + missing annual_incidence_k."""
    if mm.commercial_inputs is None:
        return []
    pool = getattr(mm.commercial_inputs, "patient_pool", None)
    if pool is None:
        return []
    if pool.disease_model != "incident_one_time":
        return []
    if getattr(pool, "annual_incidence_k", None) is not None:
        return []
    return [SanityWarning(
        code="incident_one_time_missing_data",
        message=(
            f"Asset '{mm.asset_id}': patient_pool.disease_model='incident_one_time' but "
            "annual_incidence_k is not set. "
            "The incident_one_time model requires annual_incidence_k to size Year 2+ patient "
            "flow (annual incident cohort). Without it, Year 2+ revenue defaults to zero, "
            "producing a single-year revenue spike that understates total program value. "
            "Set annual_incidence_k to the estimated annual new eligible patients (thousands). "
            "Also verify: prevalence_thousands (for backlog sizing) and backlog_years "
            "(defaults to 1.0 = one year of prevalent patients absorbed at launch)."
        ),
        severity="warning",
    )]
