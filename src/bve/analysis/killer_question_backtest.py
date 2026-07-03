"""No-lookahead replay harness and scorer for killer-question backtests.

This module is intentionally measurement-only. It reconstructs a point-in-time
science snapshot and replays the existing killer-question picker in
openness-only mode; it does not score accuracy or feed POS/valuation/BD.

Scoring:
- M1 top-1: headline hit rate (decisive archetype == label archetype).
- M1 top-2: recall (label archetype in ranked top-2 candidates).
- M2: conviction-update direction accuracy (equal-weighted; silence excluded).
- M3: abstention appropriateness (abstained iff single_question_dominant=False).

All metrics are reported with N and refuse to claim calibration below
MIN_N_FOR_CALIBRATION. Only label_status=="clean" rows enter the headline.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from bve.intelligence.killer_question import (
    KillerArchetype,
    derive_killer_questions,
)
from bve.intelligence.science_thesis import (
    ClinicalMeaningfulnessContext,
    EvidenceResolution,
    EvidenceResolutionBasis,
    ScienceComponentScore,
    ScienceContext,
    ScienceGuardrail,
    ScienceScoredQuestions,
)


DEFAULT_KILLER_QUESTION_GROUND_TRUTH_CSV = Path(
    "research/data/killer_question_ground_truth.csv"
)
SCREENING_BACKTEST_MODE: Literal["screening_backtest"] = "screening_backtest"
SCREENING_BACKTEST_VOI_MODE: Literal["screening_backtest_voi"] = "screening_backtest_voi"
MIN_N_FOR_CALIBRATION = 10


@dataclass(frozen=True)
class KillerQuestionGroundTruthLabel:
    """Human ground-truth label for one resolved program."""

    program_id: str
    decision_date: date
    outcome: str
    decisive_archetype: KillerArchetype
    label_status: Literal["clean", "subjective", "excluded"]
    decisive_confidence: Literal["high", "medium", "low"]
    why_this_archetype_decided: str
    label_source: str
    label_date: date
    pivotal_evidence_event: str
    pivotal_evidence_date: date
    single_question_dominant: bool
    # Archetypes that were *also open* at the decision date but were not the
    # decisive one. Leaving these open in the reconstructed snapshot turns M1
    # into a real ranking challenge instead of a single-candidate walkover.
    competing_archetypes: tuple[KillerArchetype, ...] = ()

    @property
    def headline_eligible(self) -> bool:
        return self.label_status == "clean"


@dataclass(frozen=True)
class ReplayEvidenceFact:
    """Evidence item available, or accidentally included, in a replay snapshot."""

    fact_id: str
    known_at: date
    summary: str = ""


@dataclass(frozen=True)
class ReconstructedScienceSnapshot:
    """Point-in-time inputs for openness-only killer-question replay."""

    program_id: str
    as_of_date: date
    scored: ScienceScoredQuestions
    context: ScienceContext = field(default_factory=ScienceContext)
    guardrail: ScienceGuardrail = field(default_factory=ScienceGuardrail)
    indication: str | None = None
    claimed_effect: float | None = None
    target_has_precedent: bool = False
    novel_question: str | None = None
    company_focus: KillerArchetype | None = None
    evidence_facts: tuple[ReplayEvidenceFact, ...] = ()


@dataclass(frozen=True)
class KillerQuestionReplayPrediction:
    """Picker output captured for later M1/M3 scoring."""

    program_id: str
    as_of_date: date
    reconstruction_mode: Literal["screening_backtest", "screening_backtest_voi"]
    ranked_archetypes: tuple[KillerArchetype, ...]
    decisive_archetypes: tuple[KillerArchetype, ...]
    abstained: bool
    abstain_reason: str


def load_ground_truth_labels(
    csv_path: str | Path = DEFAULT_KILLER_QUESTION_GROUND_TRUTH_CSV,
) -> list[KillerQuestionGroundTruthLabel]:
    """Load curated killer-question ground-truth labels."""

    labels: list[KillerQuestionGroundTruthLabel] = []
    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            labels.append(
                KillerQuestionGroundTruthLabel(
                    program_id=row["program_id"].strip(),
                    decision_date=date.fromisoformat(row["decision_date"]),
                    outcome=row["outcome"].strip(),
                    decisive_archetype=_parse_archetype(row["decisive_archetype"]),
                    label_status=row["label_status"].strip(),  # type: ignore[arg-type]
                    decisive_confidence=row["decisive_confidence"].strip(),  # type: ignore[arg-type]
                    why_this_archetype_decided=row["why_this_archetype_decided"].strip(),
                    label_source=row["label_source"].strip(),
                    label_date=date.fromisoformat(row["label_date"]),
                    pivotal_evidence_event=row["pivotal_evidence_event"].strip(),
                    pivotal_evidence_date=date.fromisoformat(row["pivotal_evidence_date"]),
                    single_question_dominant=_parse_bool(row["single_question_dominant"]),
                    competing_archetypes=_parse_competing(row.get("competing_archetypes", "")),
                )
            )
    return labels


def replay_killer_questions_openness_only(
    snapshot: ReconstructedScienceSnapshot,
) -> KillerQuestionReplayPrediction:
    """Replay the existing picker without rNPV branch valuation.

    With no valuator, ``derive_killer_questions`` ranks live questions by
    openness only. This is the locked v1 `screening_backtest` reconstruction
    mode from the Idea 20 plan.
    """

    assert_no_lookahead(snapshot)
    question_set = derive_killer_questions(
        scored=snapshot.scored,
        context=snapshot.context,
        guardrail=snapshot.guardrail,
        indication=snapshot.indication,
        claimed_effect=snapshot.claimed_effect,
        target_has_precedent=snapshot.target_has_precedent,
        novel_question=snapshot.novel_question,
        company_focus=snapshot.company_focus,
        branch_valuator=None,
    )
    return KillerQuestionReplayPrediction(
        program_id=snapshot.program_id,
        as_of_date=snapshot.as_of_date,
        reconstruction_mode=SCREENING_BACKTEST_MODE,
        ranked_archetypes=tuple(question.archetype for question in question_set.candidates),
        decisive_archetypes=tuple(question.archetype for question in question_set.decisive),
        abstained=question_set.abstained,
        abstain_reason=question_set.abstain_reason,
    )


# ---------------------------------------------------------------------------
# Step 1.5: VOI (rNPV-swing) replay
# ---------------------------------------------------------------------------

_VOI_STUB_ASSET_ID = "KQ-VOI-STUB"


def voi_stub_program() -> tuple[object, list, object]:
    """A canonical minimal (asset, trials, market) for rNPV-swing valuation.

    The killer-question ground-truth corpus carries no per-program economics,
    so every program is valued against this **one shared** oncology stub. That
    means the VOI valuator does not (yet) add per-program value reasoning; it
    only re-weights archetypes by *which phase gate* each one governs, via
    ``RnpvBranchValuator._governing_index``:

    - DIFFERENTIATION governs the pivotal (latest) phase.
    - Every other archetype governs the earliest phase still carrying risk.

    So threading this valuator replaces the openness-only tie-break (draft
    order) with a value-at-stake ordering *between* the pivotal-phase question
    and the next-gate questions. Genuine per-program VOI needs real economics
    per labeled program (Step 2 corpus work). Import is local so the analysis
    module stays cheap to import when only openness-only replay is used.
    """
    from bve.entities.asset import (
        Asset,
        DevelopmentStage,
        Modality,
        TherapeuticArea,
    )
    from bve.entities.trial import ClinicalTrial, TrialPhase
    from bve.models.market_model import MarketModel

    asset = Asset(
        id=_VOI_STUB_ASSET_ID,
        name="KQ VOI stub",
        indication="oncology",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=0.10,
        royalty_rate=0.0,
    )
    trials = [
        ClinicalTrial(
            asset_id=_VOI_STUB_ASSET_ID, phase=TrialPhase.PHASE_2,
            success_probability=0.37, duration_years=2.5, cost_millions=80.0,
        ),
        ClinicalTrial(
            asset_id=_VOI_STUB_ASSET_ID, phase=TrialPhase.PHASE_3,
            success_probability=0.55, duration_years=3.5, cost_millions=250.0,
        ),
        ClinicalTrial(
            asset_id=_VOI_STUB_ASSET_ID, phase=TrialPhase.NDA_BLA,
            success_probability=0.87, duration_years=1.5, cost_millions=35.0,
        ),
    ]
    market = MarketModel(
        asset_id=_VOI_STUB_ASSET_ID, total_addressable_market_millions=8_000.0,
        peak_penetration=0.12, years_to_peak=5, patent_life_years=12,
        cogs_rate=0.18, sgna_rate_launch=0.40, sgna_rate_mature=0.20,
        adoption_curve_mode="s_curve",
    )
    return asset, trials, market


def replay_killer_questions_with_voi(
    snapshot: ReconstructedScienceSnapshot,
) -> KillerQuestionReplayPrediction:
    """Replay the picker with an rNPV-swing branch valuator wired in.

    Identical to :func:`replay_killer_questions_openness_only` except an
    ``RnpvBranchValuator`` (built from :func:`voi_stub_program`) is threaded in,
    so equal-openness questions are ordered by value-at-stake instead of by
    draft order. Same no-lookahead guard applies.
    """

    assert_no_lookahead(snapshot)
    asset, trials, market = voi_stub_program()
    question_set = derive_killer_questions(
        asset=asset,
        trials=trials,
        market_model=market,
        scored=snapshot.scored,
        context=snapshot.context,
        guardrail=snapshot.guardrail,
        indication=snapshot.indication,
        claimed_effect=snapshot.claimed_effect,
        target_has_precedent=snapshot.target_has_precedent,
        novel_question=snapshot.novel_question,
        company_focus=snapshot.company_focus,
    )
    return KillerQuestionReplayPrediction(
        program_id=snapshot.program_id,
        as_of_date=snapshot.as_of_date,
        reconstruction_mode=SCREENING_BACKTEST_VOI_MODE,
        ranked_archetypes=tuple(question.archetype for question in question_set.candidates),
        decisive_archetypes=tuple(question.archetype for question in question_set.decisive),
        abstained=question_set.abstained,
        abstain_reason=question_set.abstain_reason,
    )


def assert_no_lookahead(snapshot: ReconstructedScienceSnapshot) -> None:
    """Reject snapshots that include evidence known after the replay date."""

    future_facts = [
        fact for fact in snapshot.evidence_facts if fact.known_at > snapshot.as_of_date
    ]
    if future_facts:
        ids = ", ".join(fact.fact_id for fact in future_facts)
        raise ValueError(
            f"Snapshot {snapshot.program_id} includes post-decision evidence: {ids}"
        )


def make_component(
    name: str,
    *,
    score: float = 0.5,
    confidence: float = 0.5,
    resolution: EvidenceResolution = EvidenceResolution.UNRESOLVED,
    resolution_basis: EvidenceResolutionBasis = EvidenceResolutionBasis.UNSPECIFIED,
    rationale: str = "",
) -> ScienceComponentScore:
    """Small test/backtest helper for reconstructed science components."""

    return ScienceComponentScore(
        name=name,
        score=score,
        confidence=confidence,
        resolution=resolution,
        resolution_basis=resolution_basis,
        rationale=rationale,
    )


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"Expected true/false, got {value!r}")


def _parse_competing(value: str) -> tuple[KillerArchetype, ...]:
    """Parse a comma-separated ``competing_archetypes`` cell into archetypes.

    An empty (or missing) cell means no additional questions were open at the
    decision date beyond the decisive one.
    """
    tokens = [tok.strip() for tok in (value or "").split(",") if tok.strip()]
    return tuple(_parse_archetype(tok) for tok in tokens)


def _parse_archetype(value: str) -> KillerArchetype:
    normalized = value.strip()
    try:
        return KillerArchetype[normalized]
    except KeyError:
        return KillerArchetype(normalized)


def make_scored_questions_for_archetypes(
    *archetypes: KillerArchetype,
) -> tuple[ScienceScoredQuestions, ScienceContext, ScienceGuardrail, float | None]:
    """Build a minimal synthetic snapshot surface for tests and seed replays."""

    selected = set(archetypes)
    scored = ScienceScoredQuestions(
        right_target=make_component(
            "T",
            resolution=EvidenceResolution.UNRESOLVED
            if KillerArchetype.TARGET_VALIDITY in selected
            else EvidenceResolution.RESOLVED,
        ),
        enough_drug=make_component(
            "D",
            resolution=EvidenceResolution.UNRESOLVED
            if (
                KillerArchetype.DELIVERY_EXPOSURE in selected
                or KillerArchetype.DOSE_ADEQUACY in selected
            )
            else EvidenceResolution.RESOLVED,
            resolution_basis=(
                EvidenceResolutionBasis.PRECLINICAL
                if KillerArchetype.DELIVERY_EXPOSURE in selected
                else EvidenceResolutionBasis.HUMAN_PKPD
                if KillerArchetype.DOSE_ADEQUACY in selected
                else EvidenceResolutionBasis.UNSPECIFIED
            ),
        ),
        translation_bridge=make_component("B", resolution=EvidenceResolution.RESOLVED),
    )
    context = ScienceContext(
        clinical_meaningfulness=ClinicalMeaningfulnessContext(
            clinically_meaningful_delta=0.2
            if KillerArchetype.DIFFERENTIATION in selected
            else None
        )
    )
    guardrail = ScienceGuardrail(
        manageable_safety_concern=KillerArchetype.TOLERABILITY_CEILING in selected
    )
    claimed_effect = 0.1 if KillerArchetype.DIFFERENTIATION in selected else None
    return scored, context, guardrail, claimed_effect


# ---------------------------------------------------------------------------
# P3: Snapshot builder (label → ReconstructedScienceSnapshot)
# ---------------------------------------------------------------------------

def _snapshot_from_label(label: KillerQuestionGroundTruthLabel) -> ReconstructedScienceSnapshot:
    """Build the reconstructed snapshot from a ground-truth label.

    Openness-only: leave the decisive archetype AND every ``competing_archetype``
    UNRESOLVED (open), resolve everything else. When ``competing_archetypes`` is
    empty this degrades to the v1 single-candidate snapshot; when it is
    populated the picker must rank the decisive question above a real field of
    simultaneously-open questions, which is what makes M1 a non-trivial metric.

    Note: DELIVERY_EXPOSURE and DOSE_ADEQUACY both read the ENOUGH_DRUG
    component and cannot be opened independently in the same snapshot;
    ``make_scored_questions_for_archetypes`` resolves the basis to DELIVERY when
    both are requested. The current corpus contains neither as decisive, so this
    edge does not affect headline M1 today.
    """
    decisive = label.decisive_archetype
    open_archetypes = (decisive, *label.competing_archetypes)
    scored, context, guardrail, claimed_effect = make_scored_questions_for_archetypes(
        *open_archetypes
    )
    return ReconstructedScienceSnapshot(
        program_id=label.program_id,
        as_of_date=label.decision_date,
        scored=scored,
        context=context,
        guardrail=guardrail,
        claimed_effect=claimed_effect,
    )


# ---------------------------------------------------------------------------
# P3: Scoring dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProgramScore:
    """Per-program scoring outcome for M1 and M3."""

    program_id: str
    label_status: str  # "clean" | "subjective" | "excluded"
    label_archetype: KillerArchetype
    predicted_top1: KillerArchetype | None
    predicted_top2: tuple[KillerArchetype, ...]
    abstained: bool
    label_single_dominant: bool

    @property
    def m1_top1_hit(self) -> bool | None:
        """True/False for clean rows; None for subjective/excluded."""
        if self.label_status != "clean":
            return None
        if self.predicted_top1 is None:
            return False
        return self.predicted_top1 == self.label_archetype

    @property
    def m1_top2_hit(self) -> bool | None:
        if self.label_status != "clean":
            return None
        return self.label_archetype in self.predicted_top2

    @property
    def m3_correct(self) -> bool | None:
        """Abstention appropriate iff label says not dominant; vice versa."""
        if self.label_status != "clean":
            return None
        return self.abstained == (not self.label_single_dominant)


@dataclass
class KillerQuestionBacktestReport:
    """Aggregated M1/M3 report for a killer-question backtest run."""

    mode: str = SCREENING_BACKTEST_MODE
    program_scores: list[ProgramScore] = field(default_factory=list)

    # ---- M1 (headline: clean rows only) ----
    @property
    def m1_n(self) -> int:
        return sum(1 for s in self.program_scores if s.m1_top1_hit is not None)

    @property
    def m1_top1_rate(self) -> float | None:
        hits = [s.m1_top1_hit for s in self.program_scores if s.m1_top1_hit is not None]
        return sum(hits) / len(hits) if hits else None  # type: ignore[arg-type]

    @property
    def m1_top2_recall(self) -> float | None:
        hits = [s.m1_top2_hit for s in self.program_scores if s.m1_top2_hit is not None]
        return sum(hits) / len(hits) if hits else None  # type: ignore[arg-type]

    @property
    def m1_insufficient_n(self) -> bool:
        return self.m1_n < MIN_N_FOR_CALIBRATION

    # ---- M3 ----
    @property
    def m3_n(self) -> int:
        return sum(1 for s in self.program_scores if s.m3_correct is not None)

    @property
    def m3_rate(self) -> float | None:
        hits = [s.m3_correct for s in self.program_scores if s.m3_correct is not None]
        return sum(hits) / len(hits) if hits else None  # type: ignore[arg-type]

    @property
    def m3_insufficient_n(self) -> bool:
        return self.m3_n < MIN_N_FOR_CALIBRATION

    # ---- Appendix counts ----
    @property
    def n_clean(self) -> int:
        return sum(1 for s in self.program_scores if s.label_status == "clean")

    @property
    def n_subjective(self) -> int:
        return sum(1 for s in self.program_scores if s.label_status == "subjective")

    @property
    def n_excluded(self) -> int:
        return sum(1 for s in self.program_scores if s.label_status == "excluded")

    def summary_lines(self) -> list[str]:
        mode_note = (
            "rNPV-swing VOI reconstruction; shared stub economics — do not overclaim"
            if self.mode == SCREENING_BACKTEST_VOI_MODE
            else "openness-only reconstruction; do not overclaim"
        )
        lines = [
            f"Mode: {self.mode}  ({mode_note})",
            f"Total programs: {len(self.program_scores)}",
            f"  clean (headline): {self.n_clean}",
            f"  subjective (appendix): {self.n_subjective}",
            f"  excluded: {self.n_excluded}",
            "",
            "M1 — Killer-question hit rate (clean rows only)",
            f"  N = {self.m1_n}",
        ]
        if self.m1_insufficient_n:
            lines.append(
                f"  INSUFFICIENT N (<{MIN_N_FOR_CALIBRATION}): directional only"
            )
        if self.m1_top1_rate is not None:
            lines.append(f"  Top-1 hit rate (headline): {self.m1_top1_rate:.1%}")
            lines.append(f"  Top-2 recall  (secondary): {self.m1_top2_recall:.1%}")
        else:
            lines.append("  Top-1 hit rate: no scorable clean rows")
        lines += [
            "",
            "M3 — Abstention appropriateness (clean rows only)",
            f"  N = {self.m3_n}",
        ]
        if self.m3_insufficient_n:
            lines.append(
                f"  INSUFFICIENT N (<{MIN_N_FOR_CALIBRATION}): directional only"
            )
        if self.m3_rate is not None:
            lines.append(f"  Correct abstention rate: {self.m3_rate:.1%}")
        else:
            lines.append("  Correct abstention rate: no scorable clean rows")
        lines += [
            "",
            "M2 — Conviction direction accuracy",
            "  Not applicable in openness-only mode (requires wired producers).",
        ]
        return lines


# ---------------------------------------------------------------------------
# P3: score_program + run_killer_question_backtest
# ---------------------------------------------------------------------------

def score_program(
    label: KillerQuestionGroundTruthLabel,
    prediction: KillerQuestionReplayPrediction,
) -> ProgramScore:
    """Produce a ProgramScore from one label/prediction pair."""
    top2 = tuple(prediction.ranked_archetypes[:2])
    top1 = top2[0] if top2 else None
    return ProgramScore(
        program_id=label.program_id,
        label_status=label.label_status,
        label_archetype=label.decisive_archetype,
        predicted_top1=top1,
        predicted_top2=top2,
        abstained=prediction.abstained,
        label_single_dominant=label.single_question_dominant,
    )


def run_killer_question_backtest(
    labels_path: Path = DEFAULT_KILLER_QUESTION_GROUND_TRUTH_CSV,
    *,
    use_voi: bool = False,
) -> KillerQuestionBacktestReport:
    """Load labels, replay the picker, score, and return the report.

    ``use_voi=False`` (default) preserves the openness-only v1 reconstruction.
    ``use_voi=True`` threads an rNPV-swing branch valuator so equal-openness
    questions break by value-at-stake instead of draft order (Step 1.5).
    """
    labels = load_ground_truth_labels(labels_path)
    mode = SCREENING_BACKTEST_VOI_MODE if use_voi else SCREENING_BACKTEST_MODE
    replay = (
        replay_killer_questions_with_voi
        if use_voi
        else replay_killer_questions_openness_only
    )
    report = KillerQuestionBacktestReport(mode=mode)
    for label in labels:
        snapshot = _snapshot_from_label(label)
        prediction = replay(snapshot)
        report.program_scores.append(score_program(label, prediction))
    return report


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Backtest killer-question picker against ground-truth labels. "
            "Outputs M1 top-1/top-2 hit rates and M3 abstention rate."
        )
    )
    parser.add_argument(
        "labels_csv",
        nargs="?",
        default=str(DEFAULT_KILLER_QUESTION_GROUND_TRUTH_CSV),
        help="Path to killer_question_ground_truth.csv",
    )
    parser.add_argument(
        "--mode",
        choices=("openness", "voi", "both"),
        default="both",
        help=(
            "openness = v1 openness-only; voi = rNPV-swing VOI (Step 1.5); "
            "both = print each report plus a side-by-side delta (default)."
        ),
    )
    args = parser.parse_args()
    path = Path(args.labels_csv)

    if args.mode in ("openness", "both"):
        openness = run_killer_question_backtest(path, use_voi=False)
        print("\n".join(openness.summary_lines()))
    if args.mode in ("voi", "both"):
        if args.mode == "both":
            print("\n" + "=" * 60 + "\n")
        voi = run_killer_question_backtest(path, use_voi=True)
        print("\n".join(voi.summary_lines()))
    if args.mode == "both":
        print("\n" + "-" * 60)
        print("VOI vs openness-only (clean rows)")
        for label, o_val, v_val in (
            ("M1 top-1", openness.m1_top1_rate, voi.m1_top1_rate),
            ("M1 top-2", openness.m1_top2_recall, voi.m1_top2_recall),
            ("M3", openness.m3_rate, voi.m3_rate),
        ):
            if o_val is None or v_val is None:
                continue
            print(f"  {label:9s}: {o_val:6.1%} -> {v_val:6.1%}  ({v_val - o_val:+.1%})")


if __name__ == "__main__":
    main()
