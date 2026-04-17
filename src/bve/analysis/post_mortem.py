"""
Post-mortem analysis system for biotech investment forecasts.

For every resolved investment thesis, records the predicted vs actual outcome
and decomposes the error into root-cause categories. Aggregates errors by
therapeutic area, phase, and modality to identify systematic biases.

Architecture
------------
PostMortemCase  →  analyze_case()      →  PostMortemAnalysis
list[PostMortemCase]  →  summarize()  →  PostMortemSummary

Error categories
----------------
pos_error           Model PoS was materially wrong (drug succeeded when we predicted < 25%,
                    or failed when we predicted > 75%)
timing_error        Outcome direction was right but timing was off by > 6 months
thesis_error        A non-PoS assumption was wrong (peak sales, label breadth, market access)
competitive_surprise A competitor event materially changed the market before we adjusted
financing_event     A dilutive raise or distress event destroyed equity upside
regulatory_surprise FDA action materially differed from expected (narrow label, CRL)
market_drift        Market re-rated the sector / valuation framework changed; model was right
                    but price never converged

Usage
-----
from bve.analysis.post_mortem import PostMortemCase, analyze_case, summarize

case = PostMortemCase(
    program_id="PROG-001",
    asset_name="Drug X",
    company="Acme Bio",
    therapeutic_area="oncology",
    phase="phase_3",
    modality="small_molecule",
    predicted_pos=0.65,
    actual_success=False,
    predicted_price_move_pct=0.55,
    actual_price_move_pct=-0.45,
    prediction_date="2024-06-01",
    resolution_date="2025-01-15",
)
analysis = analyze_case(case)
print(analysis.primary_error_category)  # "pos_error"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_POS_ERROR_HIGH_THRESHOLD = 0.75   # predicted > 75% but drug failed
_POS_ERROR_LOW_THRESHOLD  = 0.25   # predicted < 25% but drug succeeded
_TIMING_ERROR_MONTHS      = 6      # error counts if off by more than 6 months
_MATERIAL_PRICE_DIVERGENCE = 0.20  # >20pp divergence between predicted and actual move


# ---------------------------------------------------------------------------
# Input dataclass
# ---------------------------------------------------------------------------

@dataclass
class PostMortemCase:
    """
    All facts needed to perform a post-mortem on one investment thesis.

    All probability values in [0.0, 1.0].
    Price moves as fractions (0.55 = +55%, −0.45 = −45%).
    """
    program_id: str
    asset_name: str
    company: str
    therapeutic_area: str          # e.g. "oncology", "rare_disease"
    phase: str                     # "phase_2", "phase_3", "nda_bla"
    modality: str                  # "small_molecule", "biologic", "cell_gene"

    # Primary forecast
    predicted_pos: float           # model PoS at time of position initiation
    actual_success: bool           # whether the trial/FDA action was positive

    # Price prediction
    predicted_price_move_pct: float     # expected stock move if thesis plays out
    actual_price_move_pct: float        # observed stock move at resolution

    # Timing
    prediction_date: str               # ISO date string "YYYY-MM-DD"
    resolution_date: str               # ISO date string "YYYY-MM-DD"
    predicted_resolution_months: Optional[float] = None
    actual_resolution_months: Optional[float] = None

    # Context (optional enrichment for root-cause analysis)
    market_implied_pos_at_entry: Optional[float] = None
    competitor_event_before_resolution: bool = False
    dilutive_raise_before_resolution: bool = False
    regulatory_surprise: bool = False      # CRL / narrow label vs expected
    thesis_assumption_broken: bool = False  # non-PoS assumption proved wrong
    notes: str = ""


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

_ALL_CATEGORIES = [
    "pos_error",
    "timing_error",
    "thesis_error",
    "competitive_surprise",
    "financing_event",
    "regulatory_surprise",
    "market_drift",
    "correct",
]


@dataclass(frozen=True)
class PostMortemAnalysis:
    """
    Root-cause decomposition for one resolved investment thesis.

    primary_error_category is the dominant explanation for the divergence.
    contributing_factors lists additional partial explanations.
    """
    case: PostMortemCase
    directionally_correct: bool         # predicted direction matched actual
    pos_error_magnitude: float          # |predicted_pos - float(actual_success)|
    price_divergence: float             # |predicted_price_move - actual_price_move|
    primary_error_category: str         # one of _ALL_CATEGORIES
    contributing_factors: list[str]
    model_grade: str                    # "A" / "B" / "C" / "D" / "F"
    lessons: list[str]


@dataclass
class PostMortemSummary:
    """
    Aggregate post-mortem statistics across a set of resolved cases.

    Breaks down error rates and mean PoS magnitude error by
    therapeutic_area, phase, and modality.
    """
    n_cases: int
    n_correct: int
    directional_accuracy: float             # fraction directionally correct
    mean_pos_error_magnitude: float
    mean_price_divergence: float
    error_by_category: dict[str, int]       # category → count
    error_by_ta: dict[str, float]           # TA → mean pos_error_magnitude
    error_by_phase: dict[str, float]        # phase → mean pos_error_magnitude
    error_by_modality: dict[str, float]     # modality → mean pos_error_magnitude
    systematic_bias: Optional[str]          # human-readable bias description if detected


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_case(case: PostMortemCase) -> PostMortemAnalysis:
    """
    Perform root-cause decomposition for one resolved investment thesis.

    Parameters
    ----------
    case:
        PostMortemCase with predicted and actual values.

    Returns
    -------
    PostMortemAnalysis with primary error category, grade, and lessons.
    """
    pos_error_magnitude = abs(case.predicted_pos - float(case.actual_success))
    price_divergence = abs(case.predicted_price_move_pct - case.actual_price_move_pct)
    directionally_correct = (
        (case.predicted_pos >= 0.50) == case.actual_success
    )

    contributing_factors: list[str] = []
    lessons: list[str] = []

    # ── Identify active error types ────────────────────────────────────────
    active: dict[str, bool] = {cat: False for cat in _ALL_CATEGORIES}

    # PoS error
    if not case.actual_success and case.predicted_pos > _POS_ERROR_HIGH_THRESHOLD:
        active["pos_error"] = True
        contributing_factors.append(
            f"Model over-confident: predicted {case.predicted_pos:.0%} but drug failed"
        )
        lessons.append(
            "Review base-rate and adjuster calibration for similar phase/TA; "
            "consider tightening high-conviction POS thresholds"
        )
    elif case.actual_success and case.predicted_pos < _POS_ERROR_LOW_THRESHOLD:
        active["pos_error"] = True
        contributing_factors.append(
            f"Model under-confident: predicted {case.predicted_pos:.0%} but drug succeeded"
        )
        lessons.append(
            "Check for missing positive signal (biomarker, safety, precedent trial)"
        )

    # Timing error
    if (case.predicted_resolution_months is not None and
            case.actual_resolution_months is not None):
        timing_delta = abs(
            case.actual_resolution_months - case.predicted_resolution_months
        )
        if timing_delta > _TIMING_ERROR_MONTHS:
            active["timing_error"] = True
            contributing_factors.append(
                f"Timing off by {timing_delta:.0f} months "
                f"(predicted {case.predicted_resolution_months:.0f}mo, "
                f"actual {case.actual_resolution_months:.0f}mo)"
            )
            lessons.append(
                "Revisit timeline model for this modality/indication; "
                "enrollment and FDA review pace assumptions may need updating"
            )

    # Thesis error (non-PoS assumption)
    if case.thesis_assumption_broken:
        active["thesis_error"] = True
        contributing_factors.append(
            "A core thesis assumption outside of PoS proved incorrect "
            "(peak sales, label breadth, payer dynamics, or partnership economics)"
        )
        lessons.append(
            "Capture specific broken assumption; update analogous assumptions "
            "in similar programs"
        )

    # Competitive surprise
    if case.competitor_event_before_resolution:
        active["competitive_surprise"] = True
        contributing_factors.append(
            "Competitor event before resolution changed market dynamics "
            "(positive readout, approval, discontinuation)"
        )
        lessons.append(
            "Increase frequency of competitive landscape monitoring; "
            "integrate competitor catalyst calendar into active positions"
        )

    # Financing event
    if case.dilutive_raise_before_resolution:
        active["financing_event"] = True
        contributing_factors.append(
            "Dilutive equity raise before resolution eroded per-share upside"
        )
        lessons.append(
            "Review runway model; apply larger financing risk discount "
            "for companies with < 18 months cash at position initiation"
        )

    # Regulatory surprise
    if case.regulatory_surprise:
        active["regulatory_surprise"] = True
        contributing_factors.append(
            "FDA action materially differed from expected "
            "(narrow label, CRL, additional confirmatory study required)"
        )
        lessons.append(
            "Expand regulatory inference inputs; track AdCom precedents "
            "and endpoint-level approval history in this indication"
        )

    # Market drift (model right but price didn't converge)
    if (directionally_correct and
            price_divergence > _MATERIAL_PRICE_DIVERGENCE and
            not any(active[c] for c in active if c not in ("correct", "market_drift"))):
        active["market_drift"] = True
        contributing_factors.append(
            f"Direction correct but price diverged {price_divergence:.0%}: "
            "market re-rated or valuation framework shifted"
        )
        lessons.append(
            "Review catalyst payoff assumptions; ensure price-move calibration "
            "is based on recent sector comps, not historical averages"
        )

    # Mark correct if no errors detected
    if not any(v for v in active.values()):
        if directionally_correct:
            active["correct"] = True
        else:
            active["pos_error"] = True  # fallback: direction wrong → pos error

    # ── Primary category ──────────────────────────────────────────────────
    # Priority order: pos_error > regulatory_surprise > competitive_surprise
    # > financing_event > thesis_error > timing_error > market_drift > correct
    priority = [
        "pos_error", "regulatory_surprise", "competitive_surprise",
        "financing_event", "thesis_error", "timing_error", "market_drift", "correct",
    ]
    primary = next(cat for cat in priority if active.get(cat))

    # ── Grade ─────────────────────────────────────────────────────────────
    model_grade = _grade(
        directionally_correct=directionally_correct,
        pos_error_magnitude=pos_error_magnitude,
        price_divergence=price_divergence,
        n_errors=sum(1 for v in active.values() if v and primary != "correct"),
    )

    return PostMortemAnalysis(
        case=case,
        directionally_correct=directionally_correct,
        pos_error_magnitude=round(pos_error_magnitude, 4),
        price_divergence=round(price_divergence, 4),
        primary_error_category=primary,
        contributing_factors=contributing_factors,
        model_grade=model_grade,
        lessons=lessons,
    )


def summarize(analyses: list[PostMortemAnalysis]) -> PostMortemSummary:
    """
    Aggregate post-mortem statistics across a set of analyzed cases.

    Parameters
    ----------
    analyses:
        List of PostMortemAnalysis from analyze_case().

    Returns
    -------
    PostMortemSummary with accuracy, error breakdown, and bias detection.
    """
    if not analyses:
        return PostMortemSummary(
            n_cases=0,
            n_correct=0,
            directional_accuracy=0.0,
            mean_pos_error_magnitude=0.0,
            mean_price_divergence=0.0,
            error_by_category={c: 0 for c in _ALL_CATEGORIES},
            error_by_ta={},
            error_by_phase={},
            error_by_modality={},
            systematic_bias=None,
        )

    n = len(analyses)
    n_correct = sum(1 for a in analyses if a.directionally_correct)
    mean_pos_err = sum(a.pos_error_magnitude for a in analyses) / n
    mean_price_div = sum(a.price_divergence for a in analyses) / n

    # Error by category
    error_by_cat: dict[str, int] = {c: 0 for c in _ALL_CATEGORIES}
    for a in analyses:
        error_by_cat[a.primary_error_category] = (
            error_by_cat.get(a.primary_error_category, 0) + 1
        )

    # Breakdown helpers
    def _mean_err_by(key_fn) -> dict[str, float]:
        groups: dict[str, list[float]] = {}
        for a in analyses:
            k = key_fn(a.case)
            groups.setdefault(k, []).append(a.pos_error_magnitude)
        return {k: round(sum(v) / len(v), 4) for k, v in groups.items()}

    error_by_ta = _mean_err_by(lambda c: c.therapeutic_area)
    error_by_phase = _mean_err_by(lambda c: c.phase)
    error_by_modality = _mean_err_by(lambda c: c.modality)

    # Bias detection — flag if one category dominates (>40% of errors)
    systematic_bias: Optional[str] = None
    dominant = max(error_by_cat, key=lambda c: error_by_cat[c])
    if dominant != "correct" and error_by_cat[dominant] / n > 0.40:
        systematic_bias = (
            f"Systematic '{dominant}': {error_by_cat[dominant]}/{n} cases "
            f"({error_by_cat[dominant]/n:.0%}) share this primary error category"
        )

    return PostMortemSummary(
        n_cases=n,
        n_correct=n_correct,
        directional_accuracy=round(n_correct / n, 4),
        mean_pos_error_magnitude=round(mean_pos_err, 4),
        mean_price_divergence=round(mean_price_div, 4),
        error_by_category=error_by_cat,
        error_by_ta=error_by_ta,
        error_by_phase=error_by_phase,
        error_by_modality=error_by_modality,
        systematic_bias=systematic_bias,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _grade(
    directionally_correct: bool,
    pos_error_magnitude: float,
    price_divergence: float,
    n_errors: int,
) -> str:
    """
    A  — directionally correct, PoS error < 10pp, price divergence < 15pp
    B  — directionally correct, PoS error 10–20pp OR price divergence 15–30pp
    C  — directionally correct but ≥2 contributing errors
    D  — directionally wrong, PoS error < 30pp (edge case or unlucky)
    F  — directionally wrong, PoS error ≥ 30pp (model misfired)
    """
    if not directionally_correct:
        if pos_error_magnitude >= 0.30:
            return "F"
        return "D"
    if pos_error_magnitude < 0.10 and price_divergence < 0.15 and n_errors == 0:
        return "A"
    if n_errors >= 2:
        return "C"
    if pos_error_magnitude <= 0.20 or price_divergence <= 0.30:
        return "B"
    return "C"
