"""Conviction Update Layer (Batch 2, PR-1): kernel + readout interpreter.

A separate, auditable trail that updates ``KillerQuestion.posterior`` as evidence
arrives — and, crucially, can *lower* conviction (falsification). This is NOT POS
and NOT scoring: it never feeds ``compute_science_modifier`` or the POS stack. It
sits strictly downstream of the killer-question spine.

Kernel first (this module); evidence sources plug in after. ``interpret_readout``
(Idea 7) is the first, lowest-risk source and lives here; dose-response (Idea 6)
and expected-signature (Idea 4) are later PRs.

Design invariants (enforced by tests):
  * log-odds composition, so a strong refutation is never drowned by weak confirms;
  * every update carries provenance + rationale;
  * refuting updates are first-class;
  * silence / no data => no update (absence of evidence is not evidence of absence);
  * a human override exists from day one and is logged, not hidden.
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from bve.config.meaningfulness_bars import MeaningfulnessBars
from bve.intelligence.killer_question import KillerArchetype, KillerQuestion

_EPS = 1e-6  # keep posteriors in (0, 1) so logit / sigmoid never blow up


def _logit(p: float) -> float:
    p = min(max(p, _EPS), 1.0 - _EPS)
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    # numerically stable both tails
    if x >= 0.0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


def _clamp01(x: float) -> float:
    return min(max(x, _EPS), 1.0 - _EPS)


class EvidenceSource(str, Enum):
    READOUT = "readout"
    DOSE_RESPONSE = "dose_response"
    EXPECTED_SIGNATURE = "expected_signature"
    MANUAL = "manual"


class UpdateDirection(str, Enum):
    CONFIRMING = "confirming"
    REFUTING = "refuting"
    NEUTRAL = "neutral"


def _direction_of(likelihood_ratio: float) -> UpdateDirection:
    if likelihood_ratio > 1.0:
        return UpdateDirection.CONFIRMING
    if likelihood_ratio < 1.0:
        return UpdateDirection.REFUTING
    return UpdateDirection.NEUTRAL


class EvidenceUpdate(BaseModel):
    """One piece of evidence bearing on a killer question.

    ``likelihood_ratio`` > 1 raises conviction, < 1 lowers it, == 1 is a no-op.
    ``informativeness`` (Idea 5) scales the update in log-odds — a distal/spurious
    marker moves the posterior less than a proximal target-engagement marker.
    """

    model_config = ConfigDict(frozen=True)

    source: EvidenceSource
    likelihood_ratio: float = Field(gt=0.0)
    informativeness: float = Field(default=1.0, ge=0.0, le=1.0)
    rationale: str
    provenance: str
    as_of: str = ""
    direction: UpdateDirection = UpdateDirection.NEUTRAL
    label: str = ""  # human-facing bucket (e.g. readout outcome), for surfacing

    def log_odds_delta(self) -> float:
        return self.informativeness * math.log(self.likelihood_ratio)


class ConvictionRecord(BaseModel):
    """The separate audit trail for one killer question's posterior update."""

    model_config = ConfigDict(frozen=True)

    archetype: KillerArchetype
    prior: float
    posterior: float
    updates: list[EvidenceUpdate] = Field(default_factory=list)
    human_override: Optional[float] = None
    untested_flags: list[str] = Field(default_factory=list)


def _make_update(
    source: EvidenceSource,
    *,
    likelihood_ratio: float,
    informativeness: float,
    rationale: str,
    provenance: str,
    as_of: str = "",
    label: str = "",
) -> EvidenceUpdate:
    return EvidenceUpdate(
        source=source,
        likelihood_ratio=likelihood_ratio,
        informativeness=informativeness,
        rationale=rationale,
        provenance=provenance,
        as_of=as_of,
        direction=_direction_of(likelihood_ratio),
        label=label,
    )


def update_killer_question_posterior(
    question: KillerQuestion,
    updates: Optional[list[EvidenceUpdate]] = None,
    *,
    human_override: Optional[float] = None,
    override_rationale: str = "",
    untested_flags: Optional[list[str]] = None,
) -> tuple[KillerQuestion, ConvictionRecord]:
    """Apply evidence updates to a killer question's posterior (log-odds).

    Returns a NEW ``KillerQuestion`` (immutable copy) with the updated posterior,
    plus a ``ConvictionRecord`` holding the full audit trail. The spine's
    ``derive_killer_questions`` output is never mutated — this is strictly
    downstream, and it does not touch POS or ``compute_science_modifier``.
    """
    applied = list(updates or [])
    prior = question.posterior
    log_odds = _logit(prior)
    for update in applied:
        log_odds += update.log_odds_delta()
    posterior = _clamp01(_sigmoid(log_odds))

    if human_override is not None:
        # An SME override is logged as an explicit update, never a hidden mutation.
        applied = [
            *applied,
            _make_update(
                EvidenceSource.MANUAL,
                likelihood_ratio=1.0,
                informativeness=1.0,
                rationale=override_rationale or "human override",
                provenance="sme_override",
            ),
        ]
        posterior = _clamp01(human_override)

    record = ConvictionRecord(
        archetype=question.archetype,
        prior=prior,
        posterior=posterior,
        updates=applied,
        human_override=human_override,
        untested_flags=list(untested_flags or []),
    )
    return question.model_copy(update={"posterior": posterior}), record


# ---------------------------------------------------------------------------
# Idea 7 — readout interpreter (first, lowest-risk evidence source)
# ---------------------------------------------------------------------------

# Starting likelihood ratios. Conservative seeds and calibration targets for the
# Idea 20 backtest — deliberately NOT treated as final magic numbers.
_LR_CLEAN_HIT = 3.0
_LR_NEAR_MISS_TREND = 1.5
_LR_CLEAN_MISS = 0.33

_READOUT_NOISE = 0.05  # within 5% of the bar reads as "clears" (matches bar-noise tolerance)
_READOUT_NEAR_BAND = 0.15  # 5%..15% below the bar is a "near miss"; below that is a clean miss


class ReadoutOutcome(str, Enum):
    CLEAN_HIT = "clean_hit"
    NEAR_MISS_WITH_TREND = "near_miss_with_trend"
    CLEAN_MISS = "clean_miss"
    SILENCE = "silence"


def classify_readout(
    observed_effect: Optional[float],
    bar: Optional[float],
    *,
    trend_present: bool,
) -> ReadoutOutcome:
    """Bucket a readout vs the clinical-meaningfulness bar. Trend is the discriminator.

    A near miss WITH a dose-response / efficacy trend is a (smaller) confirming
    signal; the same near miss WITHOUT a trend is a clean miss. This is Harvey's
    "barely missed but the dose-response trended" case that must not revert to base
    rate.
    """
    if observed_effect is None or bar is None:
        return ReadoutOutcome.SILENCE
    if observed_effect >= bar * (1.0 - _READOUT_NOISE):
        return ReadoutOutcome.CLEAN_HIT
    if observed_effect >= bar * (1.0 - _READOUT_NEAR_BAND):
        return (
            ReadoutOutcome.NEAR_MISS_WITH_TREND if trend_present else ReadoutOutcome.CLEAN_MISS
        )
    return ReadoutOutcome.CLEAN_MISS


def interpret_readout(
    observed_effect: Optional[float],
    bar: Optional[float] = None,
    *,
    indication: Optional[str] = None,
    trend_present: bool = False,
    informativeness: float = 1.0,
    provenance: str = "readout",
    as_of: str = "",
) -> Optional[EvidenceUpdate]:
    """Map a clinical readout to an ``EvidenceUpdate`` (Idea 7). Silence => ``None``.

    ``bar`` may be passed explicitly or resolved from ``indication`` via the
    clinical-meaningfulness bars shipped in Batch A.
    """
    if bar is None and indication is not None:
        bar = MeaningfulnessBars.get().delta(indication)
    outcome = classify_readout(observed_effect, bar, trend_present=trend_present)
    if outcome is ReadoutOutcome.SILENCE:
        return None
    lr = {
        ReadoutOutcome.CLEAN_HIT: _LR_CLEAN_HIT,
        ReadoutOutcome.NEAR_MISS_WITH_TREND: _LR_NEAR_MISS_TREND,
        ReadoutOutcome.CLEAN_MISS: _LR_CLEAN_MISS,
    }[outcome]
    return _make_update(
        EvidenceSource.READOUT,
        likelihood_ratio=lr,
        informativeness=informativeness,
        rationale=f"readout classified as {outcome.value} (bar={bar})",
        provenance=provenance,
        as_of=as_of,
        label=outcome.value,
    )


# ---------------------------------------------------------------------------
# Idea 6 — dose-response producer (first in-pipeline producer)
# ---------------------------------------------------------------------------

# A human dose-/exposure-response trend is a confirming signal on dose adequacy.
# Applied as a log-odds update (not a flat +0.10): at a 0.5 prior this lands near
# the old +0.10, but it is bounded and principled at every prior. Seed/calibration
# constant for the Idea 20 backtest.
_LR_DOSE_RESPONSE_TREND = 1.5
_DOSE_RESPONSE_FLAG = "dose_response_trend"


def _dose_response_update() -> EvidenceUpdate:
    return _make_update(
        EvidenceSource.DOSE_RESPONSE,
        likelihood_ratio=_LR_DOSE_RESPONSE_TREND,
        informativeness=1.0,
        rationale="human dose-/exposure-response trend supports adequate target engagement",
        provenance="killer_question:dose_adequacy",
        label=_DOSE_RESPONSE_FLAG,
    )


def apply_dose_response_conviction(
    killer_question_set: object | None,
) -> tuple[object | None, list[ConvictionRecord]]:
    """Raise dose-adequacy conviction where a dose-response trend is flagged.

    Reads the spine's ``KillerQuestionSet``, finds DOSE_ADEQUACY questions carrying
    the ``dose_response_trend`` flag, and applies a DOSE_RESPONSE ``EvidenceUpdate``
    via the kernel — producing a raised posterior AND a ``ConvictionRecord``. Flat /
    no-trend questions are left untouched (no update, no record): silence is not a
    downgrade. Returns ``(updated_set, records)``; the set is unchanged when nothing
    fires. Strictly downstream — never touches POS, the science modifier, VOI
    selection (VOI = swing x openness; posterior is not an input), or BD scoring.
    """
    if killer_question_set is None:
        return killer_question_set, []

    candidates = list(getattr(killer_question_set, "candidates", []) or [])
    decisive = list(getattr(killer_question_set, "decisive", []) or [])
    records: list[ConvictionRecord] = []
    updated: dict[tuple, object] = {}

    def _maybe_update(question: object) -> object:
        key = (getattr(question, "archetype", None), getattr(question, "question_text", ""))
        if key in updated:
            return updated[key]
        flags = list(getattr(question, "flags", []) or [])
        is_dose = getattr(question, "archetype", None) == KillerArchetype.DOSE_ADEQUACY
        if is_dose and _DOSE_RESPONSE_FLAG in flags:
            new_question, record = update_killer_question_posterior(
                question, [_dose_response_update()]
            )
            updated[key] = new_question
            records.append(record)
            return new_question
        return question

    new_candidates = [_maybe_update(q) for q in candidates]
    new_decisive = [_maybe_update(q) for q in decisive]

    if not records:
        return killer_question_set, []

    new_set = killer_question_set.model_copy(
        update={"candidates": new_candidates, "decisive": new_decisive}
    )
    return new_set, records


# ---------------------------------------------------------------------------
# Surfacing — compact, JSON-safe rendering of the conviction trail
# ---------------------------------------------------------------------------


def _update_to_dict(update: object) -> dict:
    """One evidence update as a compact, JSON-safe row.

    Uses ``getattr`` so it renders anything update-shaped (mirrors the loose
    surfacing convention used for killer questions).
    """
    source = getattr(update, "source", None)
    direction = getattr(update, "direction", None)
    return {
        "source": getattr(source, "value", source),
        "direction": getattr(direction, "value", direction),
        "label": getattr(update, "label", ""),
        "likelihood_ratio": getattr(update, "likelihood_ratio", None),
        "informativeness": getattr(update, "informativeness", None),
        "rationale": getattr(update, "rationale", ""),
        "provenance": getattr(update, "provenance", ""),
        "as_of": getattr(update, "as_of", ""),
    }


def conviction_record_to_dict(record: object) -> dict:
    """One ``ConvictionRecord`` as a compact, JSON-safe dict for memo/JSON output.

    Surfaces the analyst-facing trail: prior posterior -> per-update
    (bucket / LR / informativeness / rationale) -> updated posterior. Pure
    presentation — carries no scoring authority.
    """
    archetype = getattr(record, "archetype", None)
    return {
        "archetype": getattr(archetype, "value", archetype),
        "prior": getattr(record, "prior", None),
        "posterior": getattr(record, "posterior", None),
        "human_override": getattr(record, "human_override", None),
        "untested_flags": list(getattr(record, "untested_flags", []) or []),
        "updates": [_update_to_dict(u) for u in (getattr(record, "updates", []) or [])],
    }


def build_conviction_summary(records: object | None) -> list[dict] | None:
    """Render a list of conviction records to JSON-safe dicts, or ``None`` if empty."""
    rows = [conviction_record_to_dict(r) for r in (records or [])]
    return rows or None
