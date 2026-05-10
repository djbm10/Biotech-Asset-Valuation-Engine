"""
ProbabilityModel — encapsulates all phase success probability computation.

Inputs:  Asset (for id/name), list[ClinicalTrial] with success_probability set.
Output:  ProbabilityResult with per-phase timing/probs and cumulative summary.

This model is stateless.  It has no knowledge of revenue, costs, or discounting.
It assumes all POS adjustments (pos_model, design_model) have already been applied
to the trials before calling compute().
"""
from __future__ import annotations

from pydantic import BaseModel

from bve.config.constants import PHASE_ORDER
from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, SpendProfile


# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------

class PhaseResult(BaseModel):
    """Timing and probability data for one clinical phase."""
    phase: str
    success_probability: float   # P(passing this phase | reaching it)
    prob_reaching: float         # P(reaching this phase) = ∏ success_prob[prior phases]
    year_start: float            # years from today when this phase begins
    year_end: float              # years from today when this phase ends
    cost_millions: float         # trial cost — carried for CostModel
    spend_profile: SpendProfile = SpendProfile.UNIFORM  # forwarded from ClinicalTrial


class ProbabilityResult(BaseModel):
    """Output of ProbabilityModel.compute()."""
    asset_id: str
    asset_name: str
    phases: list[PhaseResult]
    cumulative_approval_probability: float   # ∏ success_prob[all phases]
    years_to_approval: float                 # sum of all phase durations

    @property
    def expected_time_to_approval(self) -> float:
        """Explicit alias — used by Step 5 milestone triggers and deal economics."""
        return self.years_to_approval

    @property
    def phase_transition_times(self) -> dict[str, float]:
        """
        Year at which each phase ends (= when transition to next phase / approval occurs).

        Example: {"phase_2": 2.5, "phase_3": 6.0, "nda_bla": 7.5}
        The final entry equals years_to_approval.

        Used by: Step 5 milestone triggers, deal economics timeline.
        """
        return {p.phase: round(p.year_end, 4) for p in self.phases}


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class ProbabilityModel:
    """
    Stateless engine that walks through remaining clinical phases and computes
    per-phase timing, probability-of-reaching, and cumulative approval probability.

    Trials are filtered to the given asset and sorted by PHASE_ORDER before processing.
    """

    @staticmethod
    def compute(asset: Asset, trials: list[ClinicalTrial]) -> ProbabilityResult:
        """
        Walk forward through remaining clinical phases.

        For each phase i:
          - prob_reaching[i] = ∏ success_prob[j] for j < i   (1.0 for the first phase)
          - year_start[i]    = sum of durations for phases j < i
          - year_end[i]      = year_start[i] + duration[i]

        After all phases:
          - cumulative_approval_probability = ∏ success_prob[all phases]
          - years_to_approval = sum of all phase durations
        """
        asset_trials = [t for t in trials if t.asset_id == asset.id]
        sorted_trials = sorted(asset_trials, key=lambda t: PHASE_ORDER[t.phase.value])

        phases: list[PhaseResult] = []
        current_year: float = 0.0
        cum_prob: float = 1.0

        for trial in sorted_trials:
            year_start = current_year
            year_end = current_year + trial.duration_years

            phases.append(PhaseResult(
                phase=trial.phase.value,
                success_probability=trial.success_probability,
                prob_reaching=round(cum_prob, 4),
                year_start=year_start,
                year_end=year_end,
                cost_millions=trial.cost_millions,
                spend_profile=trial.spend_profile,
            ))

            current_year = year_end
            cum_prob *= trial.success_probability

        return ProbabilityResult(
            asset_id=asset.id,
            asset_name=asset.name,
            phases=phases,
            cumulative_approval_probability=round(cum_prob, 6),
            years_to_approval=round(current_year, 1),
        )
