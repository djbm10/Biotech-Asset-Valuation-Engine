"""M2 replay: does a conviction update point the right *direction* vs outcome?

M1 (killer_question_backtest) asks whether the engine picks the decisive question.
M2 asks the harder, POS-relevant question: when the expected-signature conviction
producer *fires* on pre-readout biomarker evidence, does it move confidence the way
the eventual outcome justifies?

For each program with sourced pre-readout biomarker data, this harness:
  1. builds a target-engagement killer question at a neutral prior,
  2. feeds the observed biomarker changes to the real (approved-gated)
     ``apply_expected_signature_conviction`` producer,
  3. reads the resulting posterior move — up = confirming, down = refuting,
  4. scores that direction against the program's actual outcome.

Silence (producer inert / untested — posterior unchanged) is **excluded** from the
M2 rate, never counted as a wrong call. No-lookahead is enforced: the biomarker
evidence date must precede the pivotal-readout date.

IMPORTANT: the seed dataset (`research/data/killer_question_m2_inputs.csv`) is
general-knowledge, primary-source-UNVERIFIED, and currently all confirming-success
cases. It exists to prove the harness fires correctly from day one, not to certify
an M2 accuracy number. A real M2 needs sourced inputs including failure/refuting
cases.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from bve.intelligence.conviction_update import apply_expected_signature_conviction
from bve.intelligence.killer_question import (
    KillerArchetype,
    KillerQuestion,
    KillerQuestionSet,
)

DEFAULT_M2_INPUTS_CSV = Path("research/data/killer_question_m2_inputs.csv")

# Posterior move below this magnitude counts as "no move" (untested / inert).
_MOVE_EPS = 1e-9

Outcome = Literal["success", "failure"]
Direction = Literal["confirming", "refuting", "silent"]


@dataclass(frozen=True)
class M2Input:
    """One program's sourced pre-readout biomarker evidence for M2 replay."""

    program_id: str
    mechanism_context: str
    open_archetype: KillerArchetype
    observed_biomarker_changes: tuple[dict[str, str], ...]
    prior: float
    outcome: Outcome
    evidence_date: date
    pivotal_date: date
    label_source: str = ""
    notes: str = ""


@dataclass(frozen=True)
class M2Prediction:
    """Producer output for one program, captured for scoring."""

    program_id: str
    direction: Direction
    prior: float
    posterior: float
    outcome: Outcome

    @property
    def scored(self) -> bool:
        """Silence is excluded from the M2 rate."""
        return self.direction != "silent"

    @property
    def correct(self) -> bool | None:
        """Confirming should precede success; refuting should precede failure."""
        if not self.scored:
            return None
        predicted_success = self.direction == "confirming"
        return predicted_success == (self.outcome == "success")


def _parse_changes(cell: str) -> tuple[dict[str, str], ...]:
    """Parse ``pCRKL:down;Ki67:down`` into producer-ready observed-change dicts."""
    changes: list[dict[str, str]] = []
    for token in (cell or "").split(";"):
        token = token.strip()
        if not token:
            continue
        biomarker, _, direction = token.partition(":")
        changes.append({"biomarker": biomarker.strip(), "direction": direction.strip()})
    return tuple(changes)


def load_m2_inputs(csv_path: str | Path = DEFAULT_M2_INPUTS_CSV) -> list[M2Input]:
    """Load sourced M2 biomarker inputs from CSV."""
    inputs: list[M2Input] = []
    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            inputs.append(
                M2Input(
                    program_id=row["program_id"].strip(),
                    mechanism_context=row["mechanism_context"].strip(),
                    open_archetype=KillerArchetype[row["open_archetype"].strip()],
                    observed_biomarker_changes=_parse_changes(row["observed_biomarker_changes"]),
                    prior=float(row["prior"]),
                    outcome=row["outcome"].strip(),  # type: ignore[arg-type]
                    evidence_date=date.fromisoformat(row["evidence_date"].strip()),
                    pivotal_date=date.fromisoformat(row["pivotal_date"].strip()),
                    label_source=row.get("label_source", "").strip(),
                    notes=row.get("notes", "").strip(),
                )
            )
    return inputs


def assert_no_lookahead(item: M2Input) -> None:
    """Biomarker evidence must predate the pivotal readout it is used to anticipate."""
    if item.evidence_date >= item.pivotal_date:
        raise ValueError(
            f"M2 input {item.program_id}: evidence_date {item.evidence_date} is not "
            f"before pivotal_date {item.pivotal_date} (lookahead)."
        )


def replay_m2(item: M2Input) -> M2Prediction:
    """Feed one program's evidence to the approved-signature producer and score direction."""
    assert_no_lookahead(item)
    question = KillerQuestion(
        archetype=item.open_archetype,
        question_text="Is the drug engaging its target in humans?",
        posterior=item.prior,
    )
    kqs = KillerQuestionSet(candidates=[question], decisive=[question])
    _new_set, records = apply_expected_signature_conviction(
        kqs,
        mechanism_context=item.mechanism_context,
        observed_changes=[dict(c) for c in item.observed_biomarker_changes],
    )

    posterior = item.prior
    moving = [r for r in records if abs(r.posterior - item.prior) > _MOVE_EPS]
    if moving:
        posterior = moving[0].posterior

    if posterior - item.prior > _MOVE_EPS:
        direction: Direction = "confirming"
    elif item.prior - posterior > _MOVE_EPS:
        direction = "refuting"
    else:
        direction = "silent"  # inert / untested — excluded from the rate

    return M2Prediction(
        program_id=item.program_id,
        direction=direction,
        prior=item.prior,
        posterior=posterior,
        outcome=item.outcome,
    )


@dataclass
class M2Report:
    """Aggregated M2 direction-accuracy report."""

    predictions: list[M2Prediction] = field(default_factory=list)

    @property
    def n_total(self) -> int:
        return len(self.predictions)

    @property
    def n_scored(self) -> int:
        return sum(1 for p in self.predictions if p.scored)

    @property
    def n_silent(self) -> int:
        return sum(1 for p in self.predictions if not p.scored)

    @property
    def direction_accuracy(self) -> float | None:
        scored = [p for p in self.predictions if p.scored]
        return sum(1 for p in scored if p.correct) / len(scored) if scored else None

    def summary_lines(self) -> list[str]:
        lines = [
            "M2 — Conviction direction accuracy (expected-signature producer)",
            "  SEED DATA — primary-source UNVERIFIED and CURATED (canonical successes +",
            "  hand-picked confirming-but-wrong failures). This is a discrimination demo,",
            "  NOT an unbiased M2 estimate — do not quote the rate as calibration.",
            f"  Programs: {self.n_total}  (scored: {self.n_scored}, silent/excluded: {self.n_silent})",
        ]
        acc = self.direction_accuracy
        if acc is None:
            lines.append("  Direction accuracy: no scorable (non-silent) programs")
        else:
            lines.append(f"  Direction accuracy (curated set): {acc:.1%}")
        # Outcome-aware breakdown so the rate cannot be misread as an estimate.
        conf_succ = sum(1 for p in self.predictions if p.direction == "confirming" and p.outcome == "success")
        conf_fail = sum(1 for p in self.predictions if p.direction == "confirming" and p.outcome == "failure")
        refuting = sum(1 for p in self.predictions if p.direction == "refuting")
        lines.append(
            f"  Breakdown: confirming+success={conf_succ} (correct), "
            f"confirming+failure={conf_fail} (wrong — engaged yet failed), "
            f"refuting={refuting}, silent={self.n_silent}"
        )
        if refuting == 0 and self.n_scored:
            lines.append("  GAP: no refuting-direction cases yet (biomarker moved wrong) — add for full coverage.")
        lines.append(
            "  MATCH CAVEAT: the producer matches on biomarker OR mechanism, so an "
            "off-target marker move can fire the wrong signature. Match logic likely "
            "needs AND / completeness-weighting before any M2 number is load-bearing."
        )
        return lines


def run_m2_replay(inputs_path: str | Path = DEFAULT_M2_INPUTS_CSV) -> M2Report:
    """Load M2 inputs, replay the producer, score direction vs outcome."""
    report = M2Report()
    for item in load_m2_inputs(inputs_path):
        report.predictions.append(replay_m2(item))
    return report


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "M2 replay: score whether expected-signature conviction updates point the "
            "right direction vs outcome. Seed inputs are primary-source unverified."
        )
    )
    parser.add_argument(
        "inputs_csv", nargs="?", default=str(DEFAULT_M2_INPUTS_CSV),
        help="Path to killer_question_m2_inputs.csv",
    )
    args = parser.parse_args()
    report = run_m2_replay(Path(args.inputs_csv))
    print("\n".join(report.summary_lines()))


if __name__ == "__main__":
    main()
