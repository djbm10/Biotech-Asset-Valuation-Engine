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


# Default correlation structure for biotech rNPV MC
DEFAULT_CORRELATION = CorrelationSpec(
    variables=["peak_sales", "penetration", "discount_rate", "years_to_peak"],
    pairs=[
        # Larger market → slightly higher competition → less penetration
        ("peak_sales", "penetration", -0.20),
        # Bigger market assumptions tend to go with optimistic view → lower discount
        ("peak_sales", "discount_rate", -0.15),
        # Larger markets typically have more established launch infrastructure
        ("peak_sales", "years_to_peak", -0.10),
    ],
)
