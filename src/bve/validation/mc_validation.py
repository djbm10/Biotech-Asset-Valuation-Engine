"""
Monte Carlo input validation rules — Sprint 33.

Provides ``validate_mc_params()`` which returns a list of ``ValidationIssue``
objects for ERROR and WARNING conditions.  After collection:

  - ERROR issues raise ``ValueError`` (hard blocking — inputs are inconsistent)
  - WARNING issues emit ``UserWarning`` (soft advisory — proceed with caution)

Rules
-----
1  [ERROR]   peak_sales sampling + driver-based sampling simultaneously
2  [WARNING] restricted launch archetype without explicit acknowledgement note
3  [ERROR]   probability values outside [0, 1]
4  [ERROR]   negative patient counts, prices, costs, or trial durations
5  [WARNING] global revenue > 5× US revenue without explicit us_revenue_fraction
6  [WARNING] ex-US geography launch year earlier than US launch year without flag
"""
from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Literal, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from bve.entities.asset import Asset
    from bve.entities.trial import ClinicalTrial
    from bve.models.market_model import MarketModel
    from bve.models.monte_carlo import MonteCarloParams


class ValidationIssue(BaseModel):
    """A single validation finding with a severity level."""

    rule: str                          # machine-readable rule identifier, e.g. "rule_1"
    level: Literal["ERROR", "WARNING"]
    message: str                       # human-readable explanation


def validate_mc_params(
    params: "MonteCarloParams",
    *,
    market_model: Optional["MarketModel"] = None,
    trials: Optional[list["ClinicalTrial"]] = None,
    asset: Optional["Asset"] = None,
    raise_on_errors: bool = True,
    emit_warnings: bool = True,
) -> list[ValidationIssue]:
    """
    Validate Monte Carlo parameters and optional model inputs.

    Parameters
    ----------
    params : MonteCarloParams
        The MC configuration to validate.
    market_model : MarketModel, optional
        When provided, Rules 2, 4, 5, 6 are checked against market inputs.
    trials : list[ClinicalTrial], optional
        When provided, Rule 3 (probability bounds) and Rule 4 (negative costs)
        are checked against trial parameters.
    asset : Asset, optional
        When provided, Rule 3 is checked against asset-level rates.
    raise_on_errors : bool
        If True (default), raises ``ValueError`` after collecting all issues
        when any ERROR-level issue is found.
    emit_warnings : bool
        If True (default), emits a ``UserWarning`` for each WARNING-level issue.

    Returns
    -------
    list[ValidationIssue]
        All issues found (both ERROR and WARNING).  Empty list = fully valid.
    """
    issues: list[ValidationIssue] = []

    # ── Rule 1 [ERROR]: peak_sales + driver-based double-counting ─────────
    # Note: MonteCarloParams also enforces this at construction time via
    # _validate_no_double_counting().  This rule surfaces the same constraint
    # in the validation-list form for programmatic inspection.
    driver_flags = [
        params.sample_eligible_patients,
        params.sample_net_price,
        params.sample_peak_penetration,
        params.sample_payer_access,
        params.sample_geography,
    ]
    if params.sample_peak_sales and any(driver_flags):
        active_drivers = [
            name for name, flag in zip(
                ["eligible_patients", "net_price", "peak_penetration",
                 "payer_access", "geography"],
                driver_flags,
            )
            if flag
        ]
        issues.append(ValidationIssue(
            rule="rule_1",
            level="ERROR",
            message=(
                f"sample_peak_sales=True cannot be combined with driver-based sampling "
                f"of {active_drivers}. This double-counts commercial uncertainty. "
                f"Set sample_peak_sales=False when using DRIVER_BASED mode."
            ),
        ))

    # ── Rule 2 [WARNING]: restricted launch archetype without acknowledgement
    if market_model is not None:
        _check_rule_2(market_model, issues)

    # ── Rule 3 [ERROR]: probability values outside [0, 1] ────────────────
    if trials is not None:
        for trial in trials:
            if not (0.0 <= trial.success_probability <= 1.0):
                issues.append(ValidationIssue(
                    rule="rule_3",
                    level="ERROR",
                    message=(
                        f"Trial {trial.phase.value} success_probability "
                        f"{trial.success_probability} is outside [0, 1]."
                    ),
                ))

    if asset is not None:
        if not (0.0 <= asset.effective_tax_rate <= 1.0):
            issues.append(ValidationIssue(
                rule="rule_3",
                level="ERROR",
                message=(
                    f"Asset effective_tax_rate {asset.effective_tax_rate} is outside [0, 1]."
                ),
            ))
        if not (0.0 <= asset.royalty_rate <= 1.0):
            issues.append(ValidationIssue(
                rule="rule_3",
                level="ERROR",
                message=(
                    f"Asset royalty_rate {asset.royalty_rate} is outside [0, 1]."
                ),
            ))

    for dist in params.phase_distributions:
        if not (0.0 < dist.mean < 1.0):
            issues.append(ValidationIssue(
                rule="rule_3",
                level="ERROR",
                message=(
                    f"PhaseSuccessDistribution for {dist.phase.value} has mean "
                    f"{dist.mean} outside (0, 1)."
                ),
            ))

    # ── Rule 4 [ERROR]: negative patient counts, prices, costs, durations ─
    if market_model is not None:
        _check_rule_4_market(market_model, issues)
    if trials is not None:
        for trial in trials:
            if trial.cost_millions < 0:
                issues.append(ValidationIssue(
                    rule="rule_4",
                    level="ERROR",
                    message=(
                        f"Trial {trial.phase.value} cost_millions "
                        f"{trial.cost_millions} is negative."
                    ),
                ))
            if trial.duration_years <= 0:
                issues.append(ValidationIssue(
                    rule="rule_4",
                    level="ERROR",
                    message=(
                        f"Trial {trial.phase.value} duration_years "
                        f"{trial.duration_years} must be positive."
                    ),
                ))

    # ── Rule 5 [WARNING]: global revenue > 5× US revenue ─────────────────
    if market_model is not None:
        _check_rule_5(market_model, issues)

    # ── Rule 6 [WARNING]: ex-US geography launch earlier than US ─────────
    if market_model is not None:
        _check_rule_6(market_model, issues)

    # ── Dispatch errors and warnings ──────────────────────────────────────
    error_issues = [i for i in issues if i.level == "ERROR"]
    warning_issues = [i for i in issues if i.level == "WARNING"]

    if emit_warnings:
        for issue in warning_issues:
            warnings.warn(
                f"[{issue.rule}] {issue.message}",
                UserWarning,
                stacklevel=2,
            )

    if raise_on_errors and error_issues:
        messages = "\n".join(f"  [{i.rule}] {i.message}" for i in error_issues)
        raise ValueError(
            f"MC validation found {len(error_issues)} error(s):\n{messages}"
        )

    return issues


# ---------------------------------------------------------------------------
# Rule helpers
# ---------------------------------------------------------------------------

def _check_rule_2(market_model: "MarketModel", issues: list[ValidationIssue]) -> None:
    """Rule 2: restricted launch archetype should be explicitly acknowledged."""
    from bve.models.launch_archetype import LaunchArchetype
    archetype = market_model.launch_archetype
    if archetype == LaunchArchetype.STEP_EDIT_RESTRICTED:
        issues.append(ValidationIssue(
            rule="rule_2",
            level="WARNING",
            message=(
                "LaunchArchetype.STEP_EDIT_RESTRICTED implies significant payer "
                "friction and step-therapy barriers, which compresses early uptake. "
                "Ensure peak_penetration and years_to_peak reflect this restriction. "
                "Consider documenting the rationale in a model note."
            ),
        ))


def _check_rule_4_market(market_model: "MarketModel",
                          issues: list[ValidationIssue]) -> None:
    """Rule 4: negative patient counts, prices, costs."""
    if market_model.addressable_patients_annual is not None:
        if market_model.addressable_patients_annual < 0:
            issues.append(ValidationIssue(
                rule="rule_4",
                level="ERROR",
                message=(
                    f"MarketModel.addressable_patients_annual "
                    f"{market_model.addressable_patients_annual} is negative."
                ),
            ))
    if market_model.net_price_per_patient_usd is not None:
        if market_model.net_price_per_patient_usd < 0:
            issues.append(ValidationIssue(
                rule="rule_4",
                level="ERROR",
                message=(
                    f"MarketModel.net_price_per_patient_usd "
                    f"{market_model.net_price_per_patient_usd} is negative."
                ),
            ))
    if market_model.total_addressable_market_millions is not None:
        if market_model.total_addressable_market_millions < 0:
            issues.append(ValidationIssue(
                rule="rule_4",
                level="ERROR",
                message=(
                    f"MarketModel.total_addressable_market_millions "
                    f"{market_model.total_addressable_market_millions} is negative."
                ),
            ))
    if market_model.peak_penetration <= 0 or market_model.peak_penetration > 1.0:
        issues.append(ValidationIssue(
            rule="rule_4",
            level="ERROR",
            message=(
                f"MarketModel.peak_penetration {market_model.peak_penetration} "
                f"must be in (0, 1]."
            ),
        ))
    if market_model.years_to_peak <= 0:
        issues.append(ValidationIssue(
            rule="rule_4",
            level="ERROR",
            message=(
                f"MarketModel.years_to_peak {market_model.years_to_peak} must be positive."
            ),
        ))


def _check_rule_5(market_model: "MarketModel",
                  issues: list[ValidationIssue]) -> None:
    """
    Rule 5: global revenue > 5× US revenue without explicit us_revenue_fraction.

    Detected via geography split: if a US geography is present and its revenue
    fraction implies ex-US is > 4× US revenue (total > 5×).
    """
    geo = getattr(market_model, "geography", None)
    if geo is None:
        return
    regions = getattr(geo, "regions", None) or getattr(geo, "splits", None) or []
    if not regions:
        return

    us_fraction: Optional[float] = None
    for region in regions:
        name = getattr(region, "region", "") or getattr(region, "name", "")
        if "us" in name.lower() or "united states" in name.lower():
            us_fraction = getattr(region, "revenue_fraction", None) or getattr(region, "fraction", None)
            break

    if us_fraction is not None and us_fraction > 0:
        global_multiplier = 1.0 / us_fraction
        if global_multiplier > 5.0:
            explicit_set = getattr(geo, "us_revenue_fraction_explicit", False)
            if not explicit_set:
                issues.append(ValidationIssue(
                    rule="rule_5",
                    level="WARNING",
                    message=(
                        f"Global revenue is {global_multiplier:.1f}× US revenue "
                        f"(US fraction = {us_fraction:.2%}). This is unusually high. "
                        f"Verify that geography splits reflect realistic ex-US uptake. "
                        f"Set us_revenue_fraction_explicit=True on the geography to "
                        f"suppress this warning."
                    ),
                ))


def _check_rule_6(market_model: "MarketModel",
                  issues: list[ValidationIssue]) -> None:
    """
    Rule 6: EU5/Japan/China launch year earlier than US unless explicitly flagged.

    Most drugs launch in the US first; ex-US launches typically lag by 1–3 years.
    An ex-US launch year equal to or earlier than US could indicate a data entry error.
    """
    geo = getattr(market_model, "geography", None)
    if geo is None:
        return
    regions = getattr(geo, "regions", None) or getattr(geo, "splits", None) or []
    if not regions:
        return

    us_launch_year: Optional[int] = None
    for region in regions:
        name = getattr(region, "region", "") or getattr(region, "name", "")
        if "us" in name.lower() or "united states" in name.lower():
            us_launch_year = getattr(region, "launch_year", None)
            break

    if us_launch_year is None:
        return

    ex_us_regions = ["eu5", "europe", "japan", "china"]
    for region in regions:
        name = (getattr(region, "region", "") or getattr(region, "name", "")).lower()
        if any(ex in name for ex in ex_us_regions):
            launch_yr = getattr(region, "launch_year", None)
            explicitly_flagged = getattr(region, "early_launch_flagged", False)
            if launch_yr is not None and launch_yr < us_launch_year and not explicitly_flagged:
                issues.append(ValidationIssue(
                    rule="rule_6",
                    level="WARNING",
                    message=(
                        f"Geography '{name}' has launch_year={launch_yr} which is "
                        f"before US launch_year={us_launch_year}. Most drugs launch "
                        f"in the US first. Verify this is intentional and set "
                        f"early_launch_flagged=True on the region to suppress this warning."
                    ),
                ))
