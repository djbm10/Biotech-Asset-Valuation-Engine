"""Backtest the lead-asset ranker against the hand-authored universe seeds.

The 50 registry seeds are a labeled answer key: each has a known lead drug,
indication, stage, and modality. For every seed we query CT.gov by the company
name, cluster + rank its trials, and compare the predicted lead to truth. The
report this produces — coverage, lead accuracy, tier precision, a margin
threshold sweep, and a failure-mode histogram — is the go/no-go evidence for
enabling routing + auto-add in the next slice.

Pure over an injectable ``fetch_fn``, so the whole harness tests offline.
"""
from __future__ import annotations

from typing import Callable, Optional

from pydantic import BaseModel

from bve.discovery.drug_identity import share_identity
from bve.discovery.lead_ranker import MED_MARGIN, rank_leads
from bve.discovery.matching import (
    infer_modality,
    map_phase_to_stage,
    match_drug,
    match_indication,
    match_modality,
    match_stage,
)
from bve.discovery.program_cluster import cluster_programs
from bve.discovery.sponsor_trials import TrialRecord, fetch_sponsor_trials
from bve.pipeline.universe_registry import UniverseRegistryEntry

_SWEEP_MARGINS = (0.05, 0.10, 0.15, 0.20, 0.25)

# Failure modes (single label per seed, focused on lead correctness).
FM_NO_TRIALS = "no_trials"
FM_SPONSOR_MISS = "sponsor_resolution_miss"
FM_WRONG_LEAD = "wrong_lead_picked"
FM_AMBIGUOUS = "ambiguous_low_margin"
FM_DRUG_UNMATCHABLE = "drug_name_unmatchable"


def _default_fetch(company_name: str) -> list[TrialRecord]:
    return fetch_sponsor_trials(company_name)


class SeedBacktestResult(BaseModel, frozen=True):
    """One seed evaluated: prediction vs truth, with the failure label if wrong."""

    ticker: str
    company_name: str
    truth_drug: str
    truth_indication: str
    truth_stage: str
    truth_modality: str
    predicted_drug: Optional[str] = None
    predicted_stage: Optional[str] = None
    predicted_modality: Optional[str] = None
    n_programs: int = 0
    tier: Optional[str] = None
    margin: float = 0.0
    drug_match: bool = False
    drug_near: bool = False
    indication_match: bool = False
    stage_match: bool = False
    stage_understated: bool = False
    modality_match: bool = False
    lead_correct: bool = False
    failure_mode: Optional[str] = None


def evaluate_seed(
    seed: UniverseRegistryEntry,
    fetch_fn: Callable[[str], list[TrialRecord]],
) -> SeedBacktestResult:
    """Evaluate a single seed against CT.gov via ``fetch_fn``."""
    trials = fetch_fn(seed.company_name)
    programs = cluster_programs(trials)
    lead = rank_leads(programs)

    base = dict(
        ticker=seed.ticker,
        company_name=seed.company_name,
        truth_drug=seed.drug_name,
        truth_indication=seed.indication,
        truth_stage=seed.stage,
        truth_modality=seed.modality,
        n_programs=len(programs),
    )

    if lead is None:
        fm = FM_NO_TRIALS if not trials else FM_SPONSOR_MISS
        return SeedBacktestResult(**base, failure_mode=fm)

    prog = lead.program
    predicted_modality = infer_modality(
        prog.drug, list(prog.conditions),
        intervention_type=prog.intervention_type, aliases=list(prog.aliases),
    )
    # Match truth against the program's full variant set (display + CT.gov synonyms),
    # so code-vs-generic naming differences don't read as wrong leads.
    prog_names = [prog.drug, *prog.aliases]
    drug_match = share_identity(prog_names, [seed.drug_name])
    drug_near = False
    if not drug_match:
        drug_match, drug_near = match_drug(prog.drug, seed.drug_name)
    stage_match, stage_understated = match_stage(prog.max_phase, seed.stage)

    if drug_match:
        failure_mode = None
    elif lead.tier == "low" or lead.margin < MED_MARGIN:
        failure_mode = FM_AMBIGUOUS
    elif drug_near:
        failure_mode = FM_DRUG_UNMATCHABLE
    else:
        failure_mode = FM_WRONG_LEAD

    return SeedBacktestResult(
        **base,
        predicted_drug=prog.drug,
        predicted_stage=map_phase_to_stage(prog.max_phase),
        predicted_modality=predicted_modality,
        tier=lead.tier,
        margin=lead.margin,
        drug_match=drug_match,
        drug_near=drug_near,
        indication_match=match_indication(list(prog.conditions), seed.indication),
        stage_match=stage_match,
        stage_understated=stage_understated,
        modality_match=match_modality(predicted_modality, seed.modality),
        lead_correct=drug_match,
        failure_mode=failure_mode,
    )


class BacktestReport(BaseModel):
    """Aggregate metrics across all evaluated seeds."""

    n_seeds: int
    n_with_program: int
    coverage: float
    lead_drug_accuracy: float
    indication_accuracy: float
    stage_accuracy: float
    modality_accuracy: float
    stage_understated_count: int
    tier_counts: dict[str, int]
    auto_tier_precision: Optional[float]
    auto_tier_n: int
    threshold_sweep: list[dict[str, float]]
    failure_modes: dict[str, int]
    results: list[SeedBacktestResult]

    def to_dict(self) -> dict:
        return self.model_dump()

    def to_text(self) -> str:
        lines = [
            "=" * 64,
            "bve-discover — lead-asset ranker backtest",
            "=" * 64,
            f"seeds evaluated      : {self.n_seeds}",
            f"coverage (≥1 program): {self.n_with_program}/{self.n_seeds} "
            f"({self.coverage:.0%})",
            "",
            "Accuracy (conditional on a program being found)",
            f"  lead drug   : {self.lead_drug_accuracy:.0%}",
            f"  indication  : {self.indication_accuracy:.0%}",
            f"  stage       : {self.stage_accuracy:.0%}  "
            f"(+{self.stage_understated_count} seeds CT.gov can't stage, e.g. nda_bla)",
            f"  modality    : {self.modality_accuracy:.0%}",
            "",
            "Tier distribution",
        ]
        for tier in ("high", "medium", "low"):
            lines.append(f"  {tier:6s}: {self.tier_counts.get(tier, 0)}")
        gate = (
            f"{self.auto_tier_precision:.0%}" if self.auto_tier_precision is not None else "n/a"
        )
        lines += [
            "",
            f"AUTO-TIER PRECISION (gate, target ≥90%): {gate}  (n={self.auto_tier_n})",
            "",
            "Margin threshold sweep (high = margin ≥ t)",
            "  t       n_high   precision",
        ]
        for row in self.threshold_sweep:
            prec = row["precision"]
            prec_s = f"{prec:.0%}" if prec >= 0 else "n/a"
            lines.append(f"  {row['margin']:.2f}    {int(row['n_high']):>4d}     {prec_s}")
        lines += ["", "Failure modes"]
        if self.failure_modes:
            for fm, n in sorted(self.failure_modes.items(), key=lambda x: -x[1]):
                lines.append(f"  {fm:28s}: {n}")
        else:
            lines.append("  (none)")
        return "\n".join(lines)


def _safe_ratio(num: int, den: int) -> float:
    return num / den if den else 0.0


def build_report(results: list[SeedBacktestResult]) -> BacktestReport:
    """Aggregate per-seed results into a ``BacktestReport`` (pure)."""
    n = len(results)
    with_prog = [r for r in results if r.n_programs > 0]
    n_wp = len(with_prog)

    correct = sum(1 for r in with_prog if r.lead_correct)
    ind = sum(1 for r in with_prog if r.indication_match)
    stage_ok = sum(1 for r in with_prog if r.stage_match)
    modal = sum(1 for r in with_prog if r.modality_match)
    understated = sum(1 for r in results if r.stage_understated)

    tier_counts: dict[str, int] = {}
    for r in with_prog:
        if r.tier:
            tier_counts[r.tier] = tier_counts.get(r.tier, 0) + 1

    high = [r for r in with_prog if r.tier == "high"]
    auto_n = len(high)
    auto_precision = (
        _safe_ratio(sum(1 for r in high if r.lead_correct), auto_n) if auto_n else None
    )

    sweep: list[dict[str, float]] = []
    for t in _SWEEP_MARGINS:
        bucket = [r for r in with_prog if r.margin >= t]
        nb = len(bucket)
        prec = _safe_ratio(sum(1 for r in bucket if r.lead_correct), nb) if nb else -1.0
        sweep.append({"margin": t, "n_high": nb, "precision": prec})

    failure_modes: dict[str, int] = {}
    for r in results:
        if r.failure_mode:
            failure_modes[r.failure_mode] = failure_modes.get(r.failure_mode, 0) + 1

    return BacktestReport(
        n_seeds=n,
        n_with_program=n_wp,
        coverage=_safe_ratio(n_wp, n),
        lead_drug_accuracy=_safe_ratio(correct, n_wp),
        indication_accuracy=_safe_ratio(ind, n_wp),
        stage_accuracy=_safe_ratio(stage_ok, n_wp),
        modality_accuracy=_safe_ratio(modal, n_wp),
        stage_understated_count=understated,
        tier_counts=tier_counts,
        auto_tier_precision=auto_precision,
        auto_tier_n=auto_n,
        threshold_sweep=sweep,
        failure_modes=failure_modes,
        results=results,
    )


def run_backtest(
    seeds: list[UniverseRegistryEntry],
    *,
    fetch_fn: Callable[[str], list[TrialRecord]] = _default_fetch,
) -> BacktestReport:
    """Evaluate every seed and aggregate into a report."""
    results = [evaluate_seed(seed, fetch_fn) for seed in seeds]
    return build_report(results)
