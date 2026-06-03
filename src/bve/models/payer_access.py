"""
PayerAccessModel — models the gap between regulatory approval and effective market access.

Rationale
---------
Regulatory approval grants the right to sell, not the right to be reimbursed.
High-price speciality drugs routinely face:

  1. Formulary exclusion or coverage gaps (access_probability < 1.0)
     e.g., a PCSK9i that achieves only 60% formulary coverage at launch.

  2. Coverage delay (coverage_delay_months > 0)
     Time from approval to the first payer contracts taking effect.
     e.g., CMS or EU HTA review adds 6–12 months before broad reimbursement.

  3. Prior-authorisation burden (prior_auth_burden > 0)
     Persistent administrative friction that reduces the fraction of eligible
     patients whose prescriptions clear PA in practice.
     Modelled as a permanent penalty on effective peak penetration:
       factor = 1 − prior_auth_burden × 0.5
     (burden=0 → no effect; burden=1 → 50% penetration loss)

  4. Step-edit / step-therapy risk (step_edit_risk > 0)
     Payer-mandated failure on a first-line agent before the new drug is
     approved.  Most acute in Year 1 as PA pathways are being established;
     fully resolved by Year 3.  Modelled as a decaying ramp:
       Year 1 multiplier: 1 − step_edit_risk
       Year 2 multiplier: 1 − step_edit_risk × 0.5
       Year 3+ multiplier: 1.0

Anti-double-counting guidance
------------------------------
- step_edit_risk and the step_edit_restricted LaunchArchetype both suppress
  early uptake.  Use ONE or the other, not both.  The archetype modifies the
  uptake curve shape; step_edit_risk applies a multiplicative year-specific
  overlay on top.  Combining them will over-penalise Year-1–2 revenue.

- competition_model affects the available market fraction AFTER payer_access
  is applied; the two are independent and do not double-count.

Default behaviour
-----------------
All four fields default to their neutral values (1.0 / 0.0 / 0.0 / 0.0).
With all defaults, combined_multiplier(year) == 1.0 for all years.
Existing models without payer_access are entirely unaffected.

Formula (as given in Sprint C1 spec)
-------------------------------------
  effective_peak_penetration = peak_penetration
                               × access_probability
                               × (1 − prior_auth_burden × 0.5)

The coverage_delay and step_edit_risk modifiers are year-specific.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class PayerAccessModel(BaseModel, frozen=True):
    """
    Payer-access modifiers applied to the commercial revenue curve.

    All fields default to their neutral value — a model constructed with
    defaults has no effect on revenue.

    Parameters
    ----------
    access_probability : float, default 1.0
        Probability (fraction) that payers grant formulary coverage for
        the drug.  Multiplied into peak penetration.
        1.0 = full formulary coverage; 0.7 = 70% of payers cover the drug.

    coverage_delay_months : float, default 0.0
        Months from regulatory approval to meaningful reimbursement.
        During the delay window, revenue is zero.  Fractional years produce
        proportional partial-year revenue in the transition year.
        e.g., 6 months → Year 1 revenue is 50% of what it would be at full
        access; Year 2+ is unaffected.

    prior_auth_burden : float, default 0.0
        Persistent administrative friction (0.0 = none, 1.0 = maximum burden).
        Applied permanently as a multiplier on effective peak penetration:
          factor = 1 − prior_auth_burden × 0.5
        At burden=0.0: factor = 1.0 (no effect).
        At burden=1.0: factor = 0.5 (50% penetration loss, all years).

    step_edit_risk : float, default 0.0
        Risk that payers impose step-therapy requirements (0.0 = none,
        1.0 = maximum suppression).  Applied as a decaying year-specific
        multiplier:
          Year 1: 1 − step_edit_risk   (worst case; PA pathways not yet set up)
          Year 2: 1 − step_edit_risk × 0.5   (partial recovery)
          Year 3+: 1.0   (fully established step-edit pathways)
        Do NOT combine with step_edit_restricted LaunchArchetype.

    Examples
    --------
    Default (no effect):
        PayerAccessModel()  # combined_multiplier == 1.0 for all years

    High-cost specialty drug with:
      - 80% formulary coverage
      - 6-month coverage delay (EU HTA review)
      - moderate PA burden
        PayerAccessModel(
            access_probability=0.80,
            coverage_delay_months=6.0,
            prior_auth_burden=0.30,
        )

    PCSK9i-style scenario (step-edit + moderate access):
        PayerAccessModel(
            access_probability=0.70,
            prior_auth_burden=0.50,
            step_edit_risk=0.40,
        )
    """

    access_probability: float = Field(
        default=1.0,
        gt=0.0, le=1.0,
        description=(
            "Fraction of payers covering the drug on formulary at launch. "
            "Multiplied into effective peak penetration. Default 1.0 (no effect)."
        ),
    )
    coverage_delay_months: float = Field(
        default=0.0,
        ge=0.0, le=24.0,
        description=(
            "Months from regulatory approval to meaningful reimbursement. "
            "Revenue is zero during the delay window; the transition year earns "
            "proportional partial-year revenue. Default 0.0 (no delay)."
        ),
    )
    prior_auth_burden: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
        description=(
            "Persistent PA friction (0.0 = none, 1.0 = maximum). "
            "Applied as a permanent penetration multiplier: "
            "factor = 1 − prior_auth_burden × 0.5. "
            "Default 0.0 (no effect, factor = 1.0)."
        ),
    )
    step_edit_risk: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
        description=(
            "Step-therapy suppression risk (0.0 = none, 1.0 = maximum). "
            "Year-1 multiplier = 1 − step_edit_risk; Year-2 = 1 − risk×0.5; "
            "Year-3+ = 1.0. Do NOT combine with step_edit_restricted archetype."
        ),
    )

    # ------------------------------------------------------------------
    # Component multipliers
    # ------------------------------------------------------------------

    def effective_penetration_multiplier(self) -> float:
        """
        Permanent fractional reduction in peak penetration.

          access_probability × (1 − prior_auth_burden × 0.5)

        Returns 1.0 when all fields are at defaults (no effect).
        """
        return self.access_probability * (1.0 - self.prior_auth_burden * 0.5)

    def coverage_delay_fraction(self, year: int) -> float:
        """
        Fraction of post-launch year `year` during which the drug is reimbursed.

        Formula: max(0, min(1, year − delay_years))
          year=1, delay=0:     1.0   (full year covered)
          year=1, delay=6mo:   0.5   (half year covered)
          year=1, delay=12mo:  0.0   (not yet covered)
          year=2, delay=6mo:   1.0   (fully covered)
          year=2, delay=18mo:  0.5   (half year covered)

        Returns 1.0 when coverage_delay_months == 0.0 (no delay, no effect).
        """
        if self.coverage_delay_months == 0.0:
            return 1.0
        delay_years = self.coverage_delay_months / 12.0
        return max(0.0, min(1.0, year - delay_years))

    def step_edit_ramp_multiplier(self, year: int) -> float:
        """
        Year-specific ramp multiplier for step-edit suppression.

          Year 1:  1 − step_edit_risk          (PA pathways not yet established)
          Year 2:  1 − step_edit_risk × 0.5    (partially established)
          Year 3+: 1.0                          (fully mature, no suppression)

        Returns 1.0 when step_edit_risk == 0.0 (no effect).
        """
        if self.step_edit_risk == 0.0:
            return 1.0
        if year >= 3:
            return 1.0
        if year == 2:
            return 1.0 - self.step_edit_risk * 0.5
        # year == 1 (or ≤ 1)
        return 1.0 - self.step_edit_risk

    # ------------------------------------------------------------------
    # Combined multiplier (product of all components)
    # ------------------------------------------------------------------

    def combined_multiplier(self, year: int) -> float:
        """
        Product of all payer-access multipliers for post-launch year `year`.

        combined = effective_penetration_multiplier()
                   × coverage_delay_fraction(year)
                   × step_edit_ramp_multiplier(year)

        Returns 1.0 for all years when all fields are at defaults (no effect).
        Always ≥ 0.0.
        """
        return (
            self.effective_penetration_multiplier()
            * self.coverage_delay_fraction(year)
            * self.step_edit_ramp_multiplier(year)
        )
