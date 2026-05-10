"""
Correlated sampling via Gaussian copula + Cholesky decomposition.

Monte Carlo draws for biotech valuation have meaningful correlations:
  - Larger markets → more competition → lower penetration
  - Higher WAC price → more payer friction → slower uptake / lower compliance
  - Strong Phase 2 signal → raises both POS and peak sales outlook

This module provides a clean interface for defining and sampling from
a joint distribution with arbitrary correlation structure.
"""
from __future__ import annotations

import warnings as _warnings

import numpy as np
from pydantic import BaseModel, Field, model_validator
from scipy.stats import norm


class CorrelationSpec(BaseModel):
    """
    Defines pairwise correlations between named simulation variables.
    Variables not listed default to independent (ρ = 0).

    Example
    -------
    CorrelationSpec(
        variables=["peak_sales", "penetration", "discount_rate"],
        pairs=[("peak_sales", "penetration", 0.40)],
    )
    """
    variables: list[str]
    pairs: list[tuple[str, str, float]] = Field(
        default_factory=list,
        description="(var_a, var_b, correlation) — only upper-triangle needed"
    )

    @model_validator(mode="after")
    def _check_correlations(self) -> "CorrelationSpec":
        for a, b, rho in self.pairs:
            if a not in self.variables:
                raise ValueError(f"Variable '{a}' not in variables list")
            if b not in self.variables:
                raise ValueError(f"Variable '{b}' not in variables list")
            if not -1.0 <= rho <= 1.0:
                raise ValueError(f"Correlation {rho} for ({a}, {b}) must be in [-1, 1]")
        return self

    def build_matrix(self) -> np.ndarray:
        """Return the n×n correlation matrix."""
        n = len(self.variables)
        idx = {v: i for i, v in enumerate(self.variables)}
        mat = np.eye(n)
        for a, b, rho in self.pairs:
            i, j = idx[a], idx[b]
            mat[i, j] = rho
            mat[j, i] = rho
        return mat

    def cholesky(self) -> np.ndarray:
        """
        Return lower Cholesky factor L such that L @ L.T = correlation_matrix.
        Raises if matrix is not positive-definite (incompatible correlations).
        """
        mat = self.build_matrix()
        try:
            return np.linalg.cholesky(mat)
        except np.linalg.LinAlgError:
            # Nearest positive-definite approximation
            eigvals, eigvecs = np.linalg.eigh(mat)
            eigvals = np.maximum(eigvals, 1e-8)
            mat_pd = eigvecs @ np.diag(eigvals) @ eigvecs.T
            return np.linalg.cholesky(mat_pd)


def correlated_uniform_samples(
    spec: CorrelationSpec,
    n: int,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """
    Generate n correlated uniform samples in [0, 1] for each variable in spec.

    Uses Gaussian copula: draw correlated normals via Cholesky, then apply Φ.

    Returns
    -------
    dict mapping variable name → array of n uniform samples
    """
    L = spec.cholesky()
    k = len(spec.variables)
    z = rng.standard_normal((k, n))         # independent standard normals
    z_corr = L @ z                           # apply correlation structure
    u = norm.cdf(z_corr)                     # map to [0, 1] via Φ
    return {v: u[i] for i, v in enumerate(spec.variables)}


def validate_correlation_consistency(
    spec: CorrelationSpec,
    driver_based: bool,
) -> None:
    """
    Warn when a DRIVER_BASED MC run specifies a direct ``peak_sales`` correlation.

    In DRIVER_BASED mode, peak_sales is derived from its component drivers
    (eligible_patients, net_price, peak_penetration, payer_access, geography).
    Specifying a separate ``peak_sales`` pair in the CorrelationSpec would
    correlate at both the aggregate level AND the driver level — double-coupling
    the same commercial uncertainty.

    Parameters
    ----------
    spec:
        The CorrelationSpec to inspect.
    driver_based:
        True when the MC run is using DRIVER_BASED mode with any driver flag active.
    """
    if not driver_based:
        return
    if "peak_sales" in spec.variables:
        _warnings.warn(
            "CorrelationSpec includes 'peak_sales' but MC mode is DRIVER_BASED. "
            "peak_sales is derived from driver components in this mode — specifying "
            "a peak_sales correlation double-couples commercial uncertainty. "
            "Remove 'peak_sales' from the correlation spec or set a driver-level "
            "correlation instead.",
            UserWarning,
            stacklevel=2,
        )


# Default correlation structure for biotech rNPV MC (SIMPLE mode)
DEFAULT_CORRELATION = CorrelationSpec(
    variables=["peak_sales", "penetration", "discount_rate", "years_to_peak"],
    pairs=[
        # Larger market → slightly higher competition → less penetration
        ("peak_sales", "penetration", -0.20),
        # Higher rate environments suppress commercial pricing power / payer access
        # (weak negative: rate environment affects peak revenue through pricing pressure)
        ("peak_sales", "discount_rate", -0.15),
        # Larger markets typically have more established launch infrastructure
        ("peak_sales", "years_to_peak", -0.10),
    ],
)


# Enhanced correlation structure — Sprint 32C
# Covers the full clinical→commercial causal chain and competitive/payer friction.
#
# Positive correlations (same direction):
#   Strong clinical data → broader label → more patients → more physician uptake → better payer access
#
# Negative correlations (opposite direction):
#   More competitors → lower penetration; more payer burden → lower uptake; safety issues → lower POS
#
# Independent (ρ ≈ 0):
#   WACC / discount_rate, base COGS rate, base SG&A rate, R&D cost multiplier
#   — macroeconomic and operational variables structurally independent of clinical outcomes
ENHANCED_CORRELATION = CorrelationSpec(
    variables=[
        # Clinical
        "phase_3_success_prob",
        # Regulatory / label
        "label_breadth_mult",
        # Commercial
        "eligible_patients_mult",
        "peak_penetration_mult",
        # Payer
        "payer_access_fraction",
        # Competition
        "competitor_share_mult",
        "prior_auth_burden_delta",
        # Cost / macro (independent)
        "discount_rate",
        "rd_cost_mult",
    ],
    pairs=[
        # ── Positive: clinical data quality chain ──────────────────────────
        # Strong phase 3 data → regulators grant broader label
        ("phase_3_success_prob", "label_breadth_mult", 0.40),
        # Strong data → physicians confident → faster peak penetration
        ("phase_3_success_prob", "peak_penetration_mult", 0.30),
        # Strong data → payers accept without heavy restrictions
        ("phase_3_success_prob", "payer_access_fraction", 0.25),
        # Broader label → larger eligible patient pool
        ("label_breadth_mult", "eligible_patients_mult", 0.50),
        # Broader label → more addressable patients → easier to reach peak
        ("label_breadth_mult", "peak_penetration_mult", 0.30),
        # Larger eligible population → more physician experience → higher uptake
        ("eligible_patients_mult", "peak_penetration_mult", 0.20),
        # Better payer access → higher actual penetration
        ("peak_penetration_mult", "payer_access_fraction", 0.35),

        # ── Negative: competitive and payer friction ───────────────────────
        # More competition → lower market share / penetration
        ("competitor_share_mult", "peak_penetration_mult", -0.40),
        # Competitors lobbying payers → our payer access declines
        ("competitor_share_mult", "payer_access_fraction", -0.25),
        # Higher prior auth burden → lower effective penetration
        ("prior_auth_burden_delta", "peak_penetration_mult", -0.35),
        # Prior auth and payer access are correlated payer-policy levers
        ("prior_auth_burden_delta", "payer_access_fraction", -0.50),

        # ── Independent: macroeconomic / operational ───────────────────────
        # discount_rate and rd_cost_mult have no pairs → ρ = 0 with all others
    ],
)
