"""
Weekly M&A screen — Block 2D.

Connects all scoring components into a single ranked output:

    enriched target profiles
  + enriched acquirer profiles
  + evidence ledger (baseline + event deltas)
  + baseline scorer
  + pair scorer
  + confidence bands
  = WeeklyMAScreenResult

Run::

    from bve.intelligence.weekly_ma_screen import WeeklyMAScreen
    from bve.ingestion.review_gate import ScoreMode

    screen = WeeklyMAScreen()
    result = screen.run(
        as_of_date=date.today(),
        targets=list(target_profiles.values()),
        acquirers=list(acquirer_profiles.values()),
        ledger=EvidenceLedger(),
    )

    for t in result.ranked_targets:
        print(f"{t.rank:2d}. {t.ticker:<8} P(M&A)={t.ma_probability:.2f}")
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from bve.ingestion.baseline_scorer import BaselineScorer, BaselineScore
from bve.ingestion.confidence_bands import ConfidenceBandEstimator
from bve.ingestion.evidence_ledger import DEFAULT_SEED_SCORES, EvidenceLedger
from bve.ingestion.profile_enricher import AcquirerProfileEnriched, TargetProfileEnriched
from bve.ingestion.review_gate import ScoreMode
from bve.intelligence.acquirer_pair_scorer import (
    AcquirerPairScorer,
    PairFeatures,
    ta_strategic_fit_score,
)


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TargetScreenResult:
    """Ranked score row for one target."""

    rank: int
    ticker: str
    name: str
    ma_probability: float
    probability_low: float
    probability_high: float
    confidence_label: str

    asset_quality: float
    seller_willingness: float
    financing_risk: float
    catalyst_timing: float
    ma_attractiveness: float
    evidence_coverage_overall: float
    profile_quality_score: float

    top_acquirer: Optional[str]
    top_acquirer_pair_score: Optional[float]

    main_drivers: list[str]
    key_risks: list[str]
    suppressed: bool
    suppression_reason: Optional[str]


@dataclass(frozen=True)
class AcquirerPairResult:
    """Score for one (target, acquirer) pair."""

    target_ticker: str
    acquirer_ticker: str
    pair_score: float
    ta_overlap: float
    modality_fit: float
    stage_fit: float
    deal_size_fit: float
    pipeline_gap_fill: float
    integration_complexity: float
    ta_fit_cap_applied: Optional[float] = None
    ta_fit_override_type: Optional[str] = None
    ta_fit_override_source: Optional[str] = None


@dataclass(frozen=True)
class AcquirerTAOverride:
    """Auditable reason to relax weak-TA pair-score caps for an acquirer."""

    acquirer_ticker: str
    therapeutic_area: str
    override_type: str
    source: str
    source_date: date
    recorded_at: date
    confidence: float = 0.70
    notes: str = ""


@dataclass(frozen=True)
class WeeklyMAScreenResult:
    """Full output of one weekly screen run."""

    as_of_date: date
    score_mode: str
    ranked_targets: list[TargetScreenResult]
    suppressed_targets: list[TargetScreenResult]
    top_acquirer_pairs: list[AcquirerPairResult]
    diagnostics: dict[str, Any]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Approximate enterprise value midpoints by market-cap bucket (USD millions)
_BUCKET_TO_EV: dict[str, float] = {
    "nano":  75.0,
    "micro": 350.0,
    "small": 1_500.0,
    "mid":   6_000.0,
    "large": 25_000.0,
}

# Map universe vocab → baseline scorer vocab where they differ
_PHASE_MAP: dict[str, str] = {"commercial": "approved"}
_TA_MAP: dict[str, str] = {
    "neuroscience": "cns",
    "infectious_disease": "infectious",
}

_TA_FIT_CAP_SEVERE_THRESHOLD = 0.20
_TA_FIT_CAP_WEAK_THRESHOLD = 0.30
_TA_FIT_CAP_SEVERE = 0.60
_TA_FIT_CAP_WEAK = 0.75

# Deal-size fit cap: a poor size fit (acquirer range doesn't match target EV/market-cap)
# prevents the pair from ranking highly even when TA and quality are strong.
_SIZE_FIT_CAP_WEAK_THRESHOLD = 0.30
_SIZE_FIT_CAP_WEAK = 0.85

_VALID_TA_OVERRIDE_TYPES = {
    "public_ta_expansion_statement",
    "adjacent_ta_deal_history",
    "active_clinical_program",
}
_TA_OVERRIDE_LOOKBACK_MONTHS = {
    "public_ta_expansion_statement": 24,
    "adjacent_ta_deal_history": 36,
    "active_clinical_program": 36,
}


def _jaccard(a: list[str], b: list[str]) -> float:
    """Jaccard similarity between two lists treated as sets."""
    set_a, set_b = set(a), set(b)
    if not set_a and not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _deal_size_fit(
    market_cap_bucket: Optional[str],
    deal_range: tuple[float, float],
    enterprise_value_millions: Optional[float] = None,
) -> float:
    """
    Fit score ∈ [0,1]: 1.0 if EV is inside the acquirer's preferred range,
    declining as EV falls outside the range.

    Prefers live enterprise_value_millions (market_cap + debt - cash from yfinance/SEC)
    when available; falls back to _BUCKET_TO_EV approximation otherwise.
    """
    if enterprise_value_millions is not None:
        ev = enterprise_value_millions
    else:
        ev = _BUCKET_TO_EV.get(market_cap_bucket) if market_cap_bucket else None
    if ev is None:
        return 0.5  # unknown → neutral
    lo, hi = deal_range
    if lo <= ev <= hi:
        return 1.0
    if ev < lo:
        # Too small — how far below the floor?
        return max(0.0, 1.0 - (lo - ev) / max(lo, 1.0))
    # Too large — how far above the ceiling?
    return max(0.0, 1.0 - (ev - hi) / max(hi, 1.0))


def _integration_complexity(target: TargetProfileEnriched) -> float:
    """Target-side integration difficulty ∈ [0.2, 0.6]."""
    complexity = 0.2
    if target.lead_modality in ("cell_gene", "gene_editing", "cell_therapy"):
        complexity += 0.2
    if target.has_partner_encumbrance:
        complexity += 0.2
    return min(complexity, 1.0)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _confidence_label(half_width: float) -> str:
    if half_width <= 0.05:
        return "high"
    if half_width <= 0.12:
        return "medium"
    return "low"


def _coverage_from_n_records(n: int) -> float:
    """Simple coverage estimate: 5 records = full coverage."""
    return min(1.0, n / 5.0)


def _months_between(later: date, earlier: date) -> int:
    """Whole-month difference used for override expiry checks."""
    return (later.year - earlier.year) * 12 + later.month - earlier.month


def _valid_ta_override(
    *,
    acquirer_ticker: str,
    target_tas: list[str],
    as_of_date: date,
    overrides: list[AcquirerTAOverride],
) -> Optional[AcquirerTAOverride]:
    """Return a non-expired, auditable TA override for this pair, if one exists."""
    normalized_tas = {ta.lower() for ta in target_tas}
    for override in overrides:
        if override.acquirer_ticker.upper() != acquirer_ticker.upper():
            continue
        if override.therapeutic_area.lower() not in normalized_tas:
            continue
        if override.override_type not in _VALID_TA_OVERRIDE_TYPES:
            continue
        lookback = _TA_OVERRIDE_LOOKBACK_MONTHS[override.override_type]
        if _months_between(as_of_date, override.source_date) > lookback:
            continue
        if override.confidence < 0.50:
            continue
        return override
    return None


def _apply_ta_fit_cap(
    pair_score: float,
    ta_overlap: float,
    override: Optional[AcquirerTAOverride],
) -> tuple[float, Optional[float]]:
    """Cap implausibly high pair scores when TA fit is weak and not overridden."""
    if override is not None:
        return pair_score, None
    if ta_overlap < _TA_FIT_CAP_SEVERE_THRESHOLD:
        return min(pair_score, _TA_FIT_CAP_SEVERE), _TA_FIT_CAP_SEVERE
    if ta_overlap < _TA_FIT_CAP_WEAK_THRESHOLD:
        return min(pair_score, _TA_FIT_CAP_WEAK), _TA_FIT_CAP_WEAK
    return pair_score, None


def _apply_size_fit_cap(pair_score: float, size_fit: float) -> float:
    """Cap pair score when deal-size fit is poor.

    Even a strong TA / quality pair is unlikely to close if the target's
    enterprise value falls well outside the acquirer's stated deal-size range.
    A cap at 0.85 prevents poor-size-fit pairs from ranking alongside
    genuinely well-matched pairs in the top-acquirer output.
    """
    if size_fit < _SIZE_FIT_CAP_WEAK_THRESHOLD:
        return min(pair_score, _SIZE_FIT_CAP_WEAK)
    return pair_score


def _build_baseline_features(target: TargetProfileEnriched) -> dict:
    """Map TargetProfileEnriched fields to BaselineScorer feature dict."""
    phase = target.lead_asset_phase
    phase = _PHASE_MAP.get(phase, phase)

    # Use primary TA
    ta_raw = target.therapeutic_areas[0] if target.therapeutic_areas else "other"
    ta = _TA_MAP.get(ta_raw, ta_raw)

    return {
        "phase": phase,
        "therapeutic_area": ta,
        "modality": target.lead_modality,
        "single_asset": target.is_single_asset_company,
        "platform_company": target.company_type == "platform",
        "cash_runway_months": target.cash_runway_months,
    }


def _build_evidence_records(
    ledger: EvidenceLedger,
    ticker: str,
    as_of_date: date,
) -> list[dict]:
    """Convert ledger records to ConfidenceBandEstimator input format."""
    records = ledger.get_records(ticker=ticker, until_date=as_of_date)
    result = []
    for r in records:
        try:
            event_date = date.fromisoformat(r.event_date)
            age_days = max(0, (as_of_date - event_date).days)
        except (ValueError, TypeError):
            age_days = 0
        result.append({"strength": float(r.confidence), "age_days": float(age_days)})
    return result


def _compute_current_scores(
    ticker: str,
    baseline: BaselineScore,
    ledger: EvidenceLedger,
    as_of_date: date,
) -> dict[str, float]:
    """
    Merge baseline structural priors with evidence-driven deltas.

    Priority: DEFAULT_SEED_SCORES (neutral) → baseline (structural) → ledger events.
    """
    merged_seeds = dict(DEFAULT_SEED_SCORES)
    merged_seeds.update(baseline.scores)   # baseline overrides neutral seeds
    return ledger.compute_score_state(
        ticker=ticker,
        as_of_date=as_of_date,
        seed_scores=merged_seeds,
    )


def _main_drivers(baseline: BaselineScore, current_scores: dict[str, float]) -> list[str]:
    """Top 3 positive structural contributors from the baseline breakdown."""
    positive = [
        (k, v) for k, v in baseline.feature_breakdown.items()
        if v > 0 and k != "base"
    ]
    positive.sort(key=lambda x: x[1], reverse=True)
    return [k.replace(":", " ") for k, _ in positive[:3]]


def _key_risks(
    target: TargetProfileEnriched,
    coverage: float,
    n_records: int,
) -> list[str]:
    """Risk flags for the target — max 4 returned."""
    risks: list[str] = []
    if coverage < 0.40:
        risks.append(f"low evidence coverage ({n_records} records)")
    if "cash_missing" in target.data_quality_flags:
        risks.append("cash position unknown")
    if target.has_partner_encumbrance:
        risks.append("partner encumbrance on lead asset")
    if target.lead_asset_phase in ("phase1", "preclinical"):
        risks.append(f"early stage ({target.lead_asset_phase})")
    if target.lead_modality in ("cell_gene", "gene_editing", "cell_therapy"):
        risks.append("high integration complexity modality")
    return risks[:4]


# ---------------------------------------------------------------------------
# Pair scoring
# ---------------------------------------------------------------------------


def _score_pair(
    target: TargetProfileEnriched,
    acquirer: AcquirerProfileEnriched,
    asset_quality: float,
    pair_scorer: AcquirerPairScorer,
    as_of_date: date,
    ta_overrides: list[AcquirerTAOverride],
) -> AcquirerPairResult:
    """Compute one (target, acquirer) pair result."""
    ta_overlap = _jaccard(target.therapeutic_areas, acquirer.therapeutic_areas)
    ta_fit = ta_strategic_fit_score(ta_overlap)
    modality_fit = 1.0 if target.lead_modality in acquirer.modalities else 0.0
    stage_fit = 1.0 if target.lead_asset_phase in acquirer.preferred_stages else 0.4
    dsf = _deal_size_fit(
        target.market_cap_bucket,
        acquirer.deal_size_range_millions,
        enterprise_value_millions=target.enterprise_value_millions,
    )
    pipeline_gap_fill = ta_overlap * acquirer.urgency
    complexity = _integration_complexity(target)

    features = PairFeatures(
        asset_quality=round(asset_quality, 4),
        acquirer_appetite=round(float(acquirer.bd_appetite), 4),
        ta_overlap=round(ta_overlap, 4),
        ta_strategic_fit=round(ta_fit, 4),
        size_fit=round(dsf, 4),
        acquirer_urgency=round(float(acquirer.urgency), 4),
        integration_capacity=round(float(acquirer.integration_capacity), 4),
        acquirer_id=acquirer.ticker,
        target_ticker=target.ticker,
        as_of_date=as_of_date.isoformat(),
    )
    ps = pair_scorer.score(features)
    override = _valid_ta_override(
        acquirer_ticker=acquirer.ticker,
        target_tas=target.therapeutic_areas,
        as_of_date=as_of_date,
        overrides=ta_overrides,
    )
    capped_pair_score, cap_applied = _apply_ta_fit_cap(
        pair_score=round(ps.probability, 4),
        ta_overlap=ta_overlap,
        override=override,
    )
    capped_pair_score = _apply_size_fit_cap(capped_pair_score, dsf)

    return AcquirerPairResult(
        target_ticker=target.ticker,
        acquirer_ticker=acquirer.ticker,
        pair_score=round(capped_pair_score, 4),
        ta_overlap=round(ta_overlap, 4),
        modality_fit=modality_fit,
        stage_fit=stage_fit,
        deal_size_fit=round(dsf, 4),
        pipeline_gap_fill=round(pipeline_gap_fill, 4),
        integration_complexity=round(complexity, 4),
        ta_fit_cap_applied=cap_applied,
        ta_fit_override_type=override.override_type if override else None,
        ta_fit_override_source=override.source if override else None,
    )


# ---------------------------------------------------------------------------
# WeeklyMAScreen
# ---------------------------------------------------------------------------


class WeeklyMAScreen:
    """
    Core M&A screen runner.

    All component dependencies are injectable for testing.

    Usage::

        screen = WeeklyMAScreen()
        result = screen.run(
            as_of_date=date(2026, 6, 1),
            targets=target_list,
            acquirers=acquirer_list,
            ledger=EvidenceLedger(),
        )
    """

    def __init__(
        self,
        baseline_scorer: Optional[BaselineScorer] = None,
        pair_scorer: Optional[AcquirerPairScorer] = None,
        confidence_band_estimator: Optional[ConfidenceBandEstimator] = None,
        ta_overrides: Optional[list[AcquirerTAOverride]] = None,
    ) -> None:
        self._baseline = baseline_scorer or BaselineScorer()
        self._pair_scorer = pair_scorer or AcquirerPairScorer()
        self._band_estimator = confidence_band_estimator or ConfidenceBandEstimator()
        self._ta_overrides = ta_overrides or []

    def run(
        self,
        as_of_date: date,
        targets: list[TargetProfileEnriched],
        acquirers: list[AcquirerProfileEnriched],
        ledger: EvidenceLedger,
        score_mode: ScoreMode = ScoreMode.PROVISIONAL,
        top_n_for_pairs: int = 40,
        min_coverage: float = 0.20,
    ) -> WeeklyMAScreenResult:
        """
        Run the full M&A screen.

        Parameters
        ----------
        as_of_date      : Snapshot date — no events after this date are used.
        targets         : Enriched target profiles.
        acquirers       : Enriched acquirer profiles.
        ledger          : Evidence ledger for score state replay.
        score_mode      : How pending events are counted.
        top_n_for_pairs : How many (target, acquirer) pairs appear in top_acquirer_pairs.
        min_coverage    : Targets below this coverage are moved to suppressed_targets.
        """
        ranked: list[TargetScreenResult] = []
        suppressed: list[TargetScreenResult] = []
        all_pairs: list[AcquirerPairResult] = []

        # Filter to included targets only
        screen_targets = [t for t in targets if t.include_in_screen]

        for target in screen_targets:
            result, pairs = self._score_target(
                target=target,
                acquirers=acquirers,
                as_of_date=as_of_date,
                ledger=ledger,
                score_mode=score_mode,
                min_coverage=min_coverage,
            )
            if result.suppressed:
                suppressed.append(result)
            else:
                ranked.append(result)
                all_pairs.extend(pairs)

        # Sort ranked targets descending by probability, then assign ranks
        ranked.sort(key=lambda r: r.ma_probability, reverse=True)
        ranked = [
            _replace_rank(r, i + 1) for i, r in enumerate(ranked)
        ]

        # Top acquirer pairs globally by pair_score
        all_pairs.sort(key=lambda p: p.pair_score, reverse=True)
        top_pairs = all_pairs[:top_n_for_pairs]

        diagnostics: dict[str, Any] = {
            "n_targets_input": len(targets),
            "n_targets_screened": len(screen_targets),
            "n_acquirers_input": len(acquirers),
            "n_ranked_targets": len(ranked),
            "n_suppressed_targets": len(suppressed),
            "n_pair_scores": len(all_pairs),
            "score_mode": score_mode.value,
            "as_of_date": as_of_date.isoformat(),
        }

        return WeeklyMAScreenResult(
            as_of_date=as_of_date,
            score_mode=score_mode.value,
            ranked_targets=ranked,
            suppressed_targets=suppressed,
            top_acquirer_pairs=top_pairs,
            diagnostics=diagnostics,
        )

    def _score_target(
        self,
        target: TargetProfileEnriched,
        acquirers: list[AcquirerProfileEnriched],
        as_of_date: date,
        ledger: EvidenceLedger,
        score_mode: ScoreMode,
        min_coverage: float,
    ) -> tuple[TargetScreenResult, list[AcquirerPairResult]]:
        """Score one target and produce pair results for each acquirer."""

        # 1. Compute baseline
        baseline_features = _build_baseline_features(target)
        baseline = self._baseline.compute(baseline_features, as_of_date=as_of_date.isoformat())

        # 2. Merge with ledger event deltas
        current_scores = _compute_current_scores(
            ticker=target.ticker,
            baseline=baseline,
            ledger=ledger,
            as_of_date=as_of_date,
        )

        asset_quality = float(current_scores.get("asset_quality", baseline.scores["asset_quality"]))
        seller_willingness = float(current_scores.get("seller_willingness", baseline.scores["seller_willingness"]))
        financing_risk = float(current_scores.get("financing_risk", baseline.scores.get("financing_risk", DEFAULT_SEED_SCORES["financing_risk"])))
        ma_attractiveness = float(current_scores.get("ma_attractiveness", baseline.scores["ma_attractiveness"]))
        catalyst_timing = float(current_scores.get("catalyst_timing", DEFAULT_SEED_SCORES["catalyst_timing"]))

        # 3. Evidence coverage
        ev_records = _build_evidence_records(ledger, target.ticker, as_of_date)
        n_records = len(ev_records)
        coverage = _coverage_from_n_records(n_records)

        # Suppression check — build structured reason codes for Coverage Recovery Queue
        suppressed = coverage < min_coverage
        if suppressed:
            reason_codes: list[str] = []
            if n_records == 0:
                reason_codes.append("no_evidence_records")
            else:
                reason_codes.append("low_evidence_coverage")
            for flag in ("cash_missing", "lead_asset_missing", "phase_missing_or_unknown",
                         "rd_expense_missing"):
                if flag in target.data_quality_flags:
                    reason_codes.append(flag)
            suppression_reason = (
                f"coverage:{coverage:.2f}<{min_coverage} [{','.join(reason_codes)}]"
            )
        else:
            suppression_reason = None

        # 4. Pair scoring (even for suppressed targets — omit from output)
        pairs: list[AcquirerPairResult] = []
        if not suppressed and acquirers:
            for acquirer in acquirers:
                if not acquirer.include_as_acquirer:
                    continue
                pairs.append(
                    _score_pair(
                        target=target,
                        acquirer=acquirer,
                        asset_quality=asset_quality,
                        pair_scorer=self._pair_scorer,
                        as_of_date=as_of_date,
                        ta_overrides=self._ta_overrides,
                    )
                )

        # 5. Compute M&A probability
        target_strength = (
            0.35 * asset_quality
            + 0.25 * seller_willingness
            + 0.20 * ma_attractiveness
            + 0.20 * catalyst_timing
        )
        best_pair_score = max((p.pair_score for p in pairs), default=0.0)
        raw_score = 0.65 * target_strength + 0.35 * best_pair_score
        ma_probability = round(_sigmoid(-2.0 + 4.0 * raw_score), 4)

        # 6. Confidence band
        band = self._band_estimator.compute(
            score=ma_probability,
            evidence_records=ev_records,
        )

        # 7. Top acquirer
        top_pair = max(pairs, key=lambda p: p.pair_score) if pairs else None
        top_acquirer = top_pair.acquirer_ticker if top_pair else None
        top_acquirer_pair_score = round(top_pair.pair_score, 4) if top_pair else None

        result = TargetScreenResult(
            rank=0,   # filled in after sorting
            ticker=target.ticker,
            name=target.name,
            ma_probability=ma_probability,
            probability_low=band.lower,
            probability_high=band.upper,
            confidence_label=_confidence_label(band.half_width),
            asset_quality=round(asset_quality, 4),
            seller_willingness=round(seller_willingness, 4),
            financing_risk=round(financing_risk, 4),
            catalyst_timing=round(catalyst_timing, 4),
            ma_attractiveness=round(ma_attractiveness, 4),
            evidence_coverage_overall=round(coverage, 4),
            profile_quality_score=round(target.quality_score, 4),
            top_acquirer=top_acquirer,
            top_acquirer_pair_score=top_acquirer_pair_score,
            main_drivers=_main_drivers(baseline, current_scores),
            key_risks=_key_risks(target, coverage, n_records),
            suppressed=suppressed,
            suppression_reason=suppression_reason,
        )
        return result, pairs


def _replace_rank(result: TargetScreenResult, rank: int) -> TargetScreenResult:
    """Return a new TargetScreenResult with updated rank (frozen dataclass)."""
    return TargetScreenResult(
        rank=rank,
        ticker=result.ticker,
        name=result.name,
        ma_probability=result.ma_probability,
        probability_low=result.probability_low,
        probability_high=result.probability_high,
        confidence_label=result.confidence_label,
        asset_quality=result.asset_quality,
        seller_willingness=result.seller_willingness,
        financing_risk=result.financing_risk,
        catalyst_timing=result.catalyst_timing,
        ma_attractiveness=result.ma_attractiveness,
        evidence_coverage_overall=result.evidence_coverage_overall,
        profile_quality_score=result.profile_quality_score,
        top_acquirer=result.top_acquirer,
        top_acquirer_pair_score=result.top_acquirer_pair_score,
        main_drivers=result.main_drivers,
        key_risks=result.key_risks,
        suppressed=result.suppressed,
        suppression_reason=result.suppression_reason,
    )


# ---------------------------------------------------------------------------
# CSV row helpers for Block 2E
# ---------------------------------------------------------------------------


def ranked_targets_to_rows(result: WeeklyMAScreenResult) -> list[dict[str, Any]]:
    """Convert ranked targets to flat dicts suitable for CSV writing."""
    rows = []
    for t in result.ranked_targets:
        rows.append({
            "rank": t.rank,
            "ticker": t.ticker,
            "name": t.name,
            "ma_probability": t.ma_probability,
            "probability_low": t.probability_low,
            "probability_high": t.probability_high,
            "confidence_label": t.confidence_label,
            "asset_quality": t.asset_quality,
            "seller_willingness": t.seller_willingness,
            "financing_risk": t.financing_risk,
            "catalyst_timing": t.catalyst_timing,
            "ma_attractiveness": t.ma_attractiveness,
            "evidence_coverage_overall": t.evidence_coverage_overall,
            "profile_quality_score": t.profile_quality_score,
            "top_acquirer": t.top_acquirer or "",
            "top_acquirer_pair_score": t.top_acquirer_pair_score or "",
            "main_drivers": "; ".join(t.main_drivers),
            "key_risks": "; ".join(t.key_risks),
            "score_mode": result.score_mode,
            "as_of_date": result.as_of_date.isoformat(),
        })
    return rows


def pair_results_to_rows(result: WeeklyMAScreenResult) -> list[dict[str, Any]]:
    """Convert top acquirer pairs to flat dicts suitable for CSV writing."""
    rows = []
    for p in result.top_acquirer_pairs:
        rows.append({
            "target_ticker": p.target_ticker,
            "acquirer_ticker": p.acquirer_ticker,
            "pair_score": p.pair_score,
            "ta_overlap": p.ta_overlap,
            "modality_fit": p.modality_fit,
            "stage_fit": p.stage_fit,
            "deal_size_fit": p.deal_size_fit,
            "pipeline_gap_fill": p.pipeline_gap_fill,
            "integration_complexity": p.integration_complexity,
            "ta_fit_cap_applied": p.ta_fit_cap_applied or "",
            "ta_fit_override_type": p.ta_fit_override_type or "",
            "ta_fit_override_source": p.ta_fit_override_source or "",
            "as_of_date": result.as_of_date.isoformat(),
        })
    return rows
