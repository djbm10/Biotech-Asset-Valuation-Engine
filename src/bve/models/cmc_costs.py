"""
CMCCosts — manufacturing / Chemistry-Manufacturing-Controls investment model.

CMC spending (process development, formulation, manufacturing scale-up, and
regulatory CMC section preparation) is distinct from trial R&D costs and
typically commits before or during Phase 3.  Separating it allows analysts
to model the manufacturing investment profile independently.

Design
------
CMCCosts is a frozen Pydantic model with four cost components and a timing mode
that determines when the costs are discounted.  CostModel.compute() receives an
optional CMCCosts instance and adds its PV to the cost stream.

Timing modes
------------
PARALLEL_TO_PHASE_3 (default)
    Manufacturing scale-up runs in parallel with the Phase 3 trial.
    Discount anchor = Phase 3 midpoint.  Typical for small molecules and
    gene therapies where the drug is manufactured before trial start.

POST_PHASE_2
    Company commits to manufacturing after seeing positive Phase 2 data.
    Discount anchor = Phase 2 year_end (= Phase 3 year_start).

PRE_PHASE_3_START
    CMC must be complete before Phase 3 enrolment opens.
    Discount anchor = Phase 3 year_start.  Identical to POST_PHASE_2 when
    Phase 3 starts immediately after Phase 2.

CUSTOM_YEAR
    Analyst specifies an explicit year (from program start) for discounting.
    Useful for programs with unusual manufacturing timelines (e.g. cell
    therapy processes started in Phase 1).

Probability weighting
---------------------
CMC costs are weighted by prob_reaching_phase_3 (P(Phase 1 success) × P(Phase 2
success)).  This reflects the decision logic: the company commits to manufacturing
scale-up only after Phase 2 data, at which point the risk is Phase 3 + NDA.
If the program has no Phase 3 (e.g. accelerated approval or NDA-only), the
weight falls back to the last phase's prob_reaching.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CMCTimingMode(str, Enum):
    """When manufacturing/CMC costs are incurred relative to clinical timeline."""
    PARALLEL_TO_PHASE_3 = "parallel_to_phase_3"
    POST_PHASE_2 = "post_phase_2"
    PRE_PHASE_3_START = "pre_phase_3_start"
    CUSTOM_YEAR = "custom_year"


class CMCCosts(BaseModel):
    """
    Manufacturing / CMC investment separate from trial R&D costs.

    Parameters
    ----------
    api_development_millions
        Process development of the active pharmaceutical ingredient (API):
        synthesis routes, analytical methods, IND-enabling batches.
    formulation_millions
        Drug product formulation development: dosage form, stability studies,
        fill-finish, packaging.
    manufacturing_scale_up_millions
        Commercial-scale process validation: tech transfer to contract
        manufacturer, PPQ batches, facility qualification.
    regulatory_cmc_millions
        Regulatory CMC activities: NDA/BLA Module 3 preparation, FDA/EMA
        manufacturing site inspections, post-approval commitments.
    timing_mode
        Determines the discount anchor year. See module docstring.
    custom_year
        Required when timing_mode=CUSTOM_YEAR. Years from program start.
    """
    model_config = ConfigDict(frozen=True)

    api_development_millions: float = Field(default=0.0, ge=0.0)
    formulation_millions: float = Field(default=0.0, ge=0.0)
    manufacturing_scale_up_millions: float = Field(default=0.0, ge=0.0)
    regulatory_cmc_millions: float = Field(default=0.0, ge=0.0)

    timing_mode: CMCTimingMode = CMCTimingMode.PARALLEL_TO_PHASE_3
    custom_year: Optional[float] = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def _check_custom_year(self) -> "CMCCosts":
        if self.timing_mode == CMCTimingMode.CUSTOM_YEAR and self.custom_year is None:
            raise ValueError(
                "CMCCosts.custom_year must be set when timing_mode=CUSTOM_YEAR. "
                "Provide the year (from program start) at which CMC costs are incurred."
            )
        return self

    @property
    def total_millions(self) -> float:
        """Sum of all CMC cost components in USD millions."""
        return (
            self.api_development_millions
            + self.formulation_millions
            + self.manufacturing_scale_up_millions
            + self.regulatory_cmc_millions
        )
