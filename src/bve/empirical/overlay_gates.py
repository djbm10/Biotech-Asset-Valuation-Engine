"""
Promotion gates for the fitted overlay — automated quality checks that must
all pass before a fitted overlay replaces the empirical_heuristic path.

Gates checked by check_promotion_gates():
    fitted_brier_vs_empirical_heuristic
        fitted Brier < empirical_heuristic Brier on the test set.
    safety_serious_sign
        safety_serious coefficient must not be sign-violated or sparse-clamped
        (i.e. the coefficient must be meaningful AND have the correct sign).
    ece_regression
        |fitted ECE - empirical_heuristic ECE| <= max_ece_regression (default 0.05).
    sparse_feature_count
        len(overlay.sparse_clamped) <= max_sparse_features (default 3).

Usage
-----
from bve.empirical.overlay_gates import check_promotion_gates, PromotionGateResult

gates = check_promotion_gates(
    comparison, overlay,
    empirical_heuristic_brier=0.2056,
)
all_pass = all(g.passed for g in gates)
for g in gates:
    print(f"{'PASS' if g.passed else 'FAIL'}  {g.gate}: {g.detail}")
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bve.empirical.comparison import POSModeComparison
    from bve.empirical.overlay_model import OverlayArtifact

_MODE_FITTED = "empirical_fitted"
_MODE_HEURISTIC_EMP = "empirical_heuristic"
_MODE_HEURISTIC = "heuristic_only"


@dataclass(frozen=True)
class PromotionGateResult:
    """
    Outcome of one automated promotion gate check.

    Attributes
    ----------
    gate:       Gate identifier string.
    passed:     True if the gate criterion is satisfied.
    value:      The observed metric value (float for comparability).
    threshold:  The threshold the value is compared against.
    detail:     Human-readable explanation of the outcome.
    """
    gate: str
    passed: bool
    value: float
    threshold: float
    detail: str

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}]  {self.gate}: {self.detail}"


def check_promotion_gates(
    comparison: "POSModeComparison",
    overlay: "OverlayArtifact",
    empirical_heuristic_brier: float,
    max_ece_regression: float = 0.05,
    max_sparse_features: int = 3,
) -> list[PromotionGateResult]:
    """
    Run all promotion gates and return one result per gate.

    A gate passes only if its criterion is strictly satisfied. The overall
    overlay is promotable only when every gate passes.

    Parameters
    ----------
    comparison:
        POSModeComparison from compare_all_modes() with fitted mode present.
    overlay:
        The OverlayArtifact being evaluated.
    empirical_heuristic_brier:
        Brier score of empirical_heuristic mode. The fitted overlay must beat
        this — not just the pure heuristic — to be eligible for promotion.
    max_ece_regression:
        Maximum tolerable absolute ECE increase (fitted vs empirical_heuristic).
        Default 0.05 (5 pp). Raise this to loosen; lower to tighten.
    max_sparse_features:
        Maximum number of features allowed to be sparse-clamped. If more
        features are zeroed due to insufficient data, the dataset needs
        expansion before promotion is considered. Default 3.

    Returns
    -------
    list[PromotionGateResult] in a fixed order:
        [0] fitted_brier_vs_empirical_heuristic
        [1] safety_serious_sign
        [2] ece_regression
        [3] sparse_feature_count
    """
    results: list[PromotionGateResult] = []

    # --- Locate mode eval results from the comparison ---
    fitted_eval = comparison.get(_MODE_FITTED)
    emp_h_eval = comparison.get(_MODE_HEURISTIC_EMP)

    # ── Gate 1: fitted Brier < empirical_heuristic Brier ────────────────────
    fitted_brier = fitted_eval.brier if fitted_eval is not None else float("inf")
    passed_brier = fitted_brier < empirical_heuristic_brier
    results.append(PromotionGateResult(
        gate="fitted_brier_vs_empirical_heuristic",
        passed=passed_brier,
        value=fitted_brier,
        threshold=empirical_heuristic_brier,
        detail=(
            f"fitted_brier={fitted_brier:.4f} "
            f"{'<' if passed_brier else '>='} "
            f"empirical_heuristic_brier={empirical_heuristic_brier:.4f}"
        ),
    ))

    # ── Gate 2: safety_serious coefficient is clean ──────────────────────────
    # Fails if: (a) coefficient was sign-violated (wrong sign, n >= min_obs),
    #           (b) coefficient was sparse-clamped (n < min_obs — not enough data),
    #           (c) neither, but sign_violated has an entry (legacy guard).
    ss_sign_ok = "safety_serious" not in overlay.sign_violated
    ss_not_sparse = "safety_serious" not in overlay.sparse_clamped
    # Gate passes only if: coefficient is well-identified AND not sign-violated.
    # Note: sparse-clamped (zeroed for lack of data) is also a FAIL because
    # the model has not demonstrated it can correctly sign this feature.
    ss_passed = ss_sign_ok and ss_not_sparse
    ss_value = 1.0 if ss_passed else 0.0
    detail_parts: list[str] = []
    if not ss_sign_ok:
        raw = overlay.sign_violated["safety_serious"]
        detail_parts.append(f"sign_violated (raw_coeff={raw:+.4f}; expected < 0)")
    if not ss_not_sparse:
        n_obs = overlay.sparse_clamped["safety_serious"]
        detail_parts.append(f"sparse_clamped (n_nonzero={n_obs} < {overlay.min_feature_obs})")
    if not detail_parts:
        coef = overlay.coefficients[overlay.feature_names.index("safety_serious")]
        detail_parts.append(f"coefficient={coef:+.4f} (correct sign, n sufficient)")
    results.append(PromotionGateResult(
        gate="safety_serious_sign",
        passed=ss_passed,
        value=ss_value,
        threshold=1.0,
        detail="; ".join(detail_parts),
    ))

    # ── Gate 3: ECE regression ───────────────────────────────────────────────
    fitted_ece = fitted_eval.ece if fitted_eval is not None else float("inf")
    emp_h_ece = emp_h_eval.ece if emp_h_eval is not None else 0.0
    ece_delta = abs(fitted_ece - emp_h_ece)
    passed_ece = ece_delta <= max_ece_regression
    results.append(PromotionGateResult(
        gate="ece_regression",
        passed=passed_ece,
        value=round(ece_delta, 4),
        threshold=max_ece_regression,
        detail=(
            f"|fitted_ece({fitted_ece:.4f}) - emp_heuristic_ece({emp_h_ece:.4f})| "
            f"= {ece_delta:.4f} {'<=' if passed_ece else '>'} {max_ece_regression:.4f}"
        ),
    ))

    # ── Gate 4: sparse feature count ─────────────────────────────────────────
    n_sparse = len(overlay.sparse_clamped)
    passed_sparse = n_sparse <= max_sparse_features
    sparse_names = list(overlay.sparse_clamped.keys())
    results.append(PromotionGateResult(
        gate="sparse_feature_count",
        passed=passed_sparse,
        value=float(n_sparse),
        threshold=float(max_sparse_features),
        detail=(
            f"n_sparse_clamped={n_sparse} "
            f"{'<=' if passed_sparse else '>'} max={max_sparse_features}"
            + (f"; features: {sparse_names}" if sparse_names else "")
        ),
    ))

    return results


def promotion_summary(gates: list[PromotionGateResult]) -> str:
    """
    Render a compact multi-line summary of all gate results.

    Parameters
    ----------
    gates:
        Output of check_promotion_gates().

    Returns
    -------
    str — formatted table with pass/fail indicators.
    """
    lines = [
        "=== Overlay Promotion Gate Summary ===",
        f"  {'Gate':<40}  {'Status':<6}  {'Value':>8}  {'Threshold':>9}",
        f"  {'-'*40}  {'-'*6}  {'-'*8}  {'-'*9}",
    ]
    for g in gates:
        status = "PASS ✓" if g.passed else "FAIL ✗"
        lines.append(
            f"  {g.gate:<40}  {status:<6}  {g.value:>8.4f}  {g.threshold:>9.4f}"
        )
    all_pass = all(g.passed for g in gates)
    lines += [
        "",
        f"  Verdict: {'PROMOTABLE' if all_pass else 'NOT PROMOTABLE'} "
        f"({'all gates pass' if all_pass else str(sum(1 for g in gates if not g.passed)) + ' gate(s) failed'})",
    ]
    for g in gates:
        if not g.passed:
            lines.append(f"  • {g.detail}")
    return "\n".join(lines)
