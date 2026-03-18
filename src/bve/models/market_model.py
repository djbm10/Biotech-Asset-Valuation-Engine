"""
Market model: patient-based TAM/SAM/SOM → revenue curve.

Three modes:
  1. Multi-line: per-line-of-therapy patient pools, penetration, and launch timing
  2. Patient-based: builds up from epidemiology → addressable patients → revenue
  3. TAM-based: specify market size directly and apply penetration

Both 2 and 3 produce an annual revenue curve (USD millions) from launch through patent expiry.
Mode 1 is the recommended approach for oncology assets where 1L/2L/3L dynamics differ materially.
"""
from __future__ import annotations

import math
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from bve.config.constants import SGNA_RATE_LAUNCH, SGNA_RATE_MATURE, SGNA_RAMP_YEARS
from bve.entities.indication import Indication
from bve.models.competition_model import CompetitionModel


class LifecycleEvent(BaseModel):
    """
    A time-indexed event that modifies the effective revenue model post-launch.

    Three event types with distinct mechanics:

    label_expansion / combination_therapy
    --------------------------------------
    Represent a new indication approval or combination label that expands the
    addressable patient pool and/or penetration from trigger_year onward.

      tam_expansion_factor  ≥ 1.0 — multiplies the base revenue (equivalent to
          scaling addressable patients/TAM). Applied BEFORE the competition fraction,
          so competitive dynamics see the expanded market.
      penetration_boost     ≥ 0.0 — absolute additive boost to the uptake-curve
          penetration, clamped so total penetration ≤ 1.0. Applied in modes 2 and 3;
          not applicable in multi-line-of-therapy mode.

    new_formulation
    ---------------
    Represents an XR, depot, fixed-dose combination, or reformulation that earns
    its own NCE / NF regulatory exclusivity, extending effective patent life.

      loe_delay_years  ≥ 0 — extends effective patent_life_years by this amount.
          Revenue continues at plateau penetration during the extension window.
          LOE erosion tail (if any) begins after the extended life.

    Parameters
    ----------
    event_type : str
        "label_expansion" | "new_formulation" | "combination_therapy"
    trigger_year : int
        Years from primary launch when this event takes effect (1-indexed, inclusive).
    label : str
        Human-readable description, e.g. "Pediatric label (ages 2-5)" or "XR formulation".

    Examples
    --------
    # Dupilumab: asthma label expansion at year 2 post-primary approval
    LifecycleEvent(
        event_type="label_expansion",
        trigger_year=2,
        label="Asthma label",
        tam_expansion_factor=1.40,
    )

    # CF transmembrane combination: XR formulation adds 3-year exclusivity at year 5
    LifecycleEvent(
        event_type="new_formulation",
        trigger_year=5,
        label="Trikafta fixed-dose combination",
        loe_delay_years=3,
    )
    """
    event_type: str = Field(
        description="'label_expansion' | 'new_formulation' | 'combination_therapy'"
    )
    trigger_year: int = Field(ge=1, description="Years from primary launch (1-indexed)")
    label: str = ""

    # label_expansion / combination_therapy
    tam_expansion_factor: float = Field(
        default=1.0, ge=1.0,
        description="Multiplies addressable patient pool / TAM from trigger_year. "
                    "Applied before competition fraction."
    )
    penetration_boost: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Absolute additive boost to uptake-curve penetration. "
                    "Clamped so total penetration ≤ 1.0. Modes 2 and 3 only."
    )

    # new_formulation
    loe_delay_years: int = Field(
        default=0, ge=0,
        description="Extends effective patent_life_years by this amount."
    )

    @field_validator("event_type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        valid = {"label_expansion", "new_formulation", "combination_therapy"}
        if v not in valid:
            raise ValueError(f"event_type must be one of {valid!r}, got {v!r}")
        return v


class UptakeCurve(BaseModel):
    """Year-by-year penetration ramp as fraction of addressable market."""
    penetrations: list[float] = Field(
        description="Penetration fraction for each year from launch. Last value holds for remaining years."
    )

    @classmethod
    def linear_ramp(cls, years_to_peak: int, peak_penetration: float, patent_life: int) -> "UptakeCurve":
        """Build a simple linear ramp to peak, then flat."""
        percs = []
        for yr in range(1, patent_life + 1):
            if yr <= years_to_peak:
                percs.append(peak_penetration * yr / years_to_peak)
            else:
                percs.append(peak_penetration)
        return cls(penetrations=percs)

    @classmethod
    def s_curve(cls, years_to_peak: int, peak_penetration: float, patent_life: int) -> "UptakeCurve":
        """Logistic S-curve uptake — more realistic for specialty pharma."""
        percs = []
        k = 8.0 / years_to_peak  # steepness calibrated so ~peak at years_to_peak
        midpoint = years_to_peak / 2.0
        for yr in range(1, patent_life + 1):
            s = peak_penetration / (1.0 + math.exp(-k * (yr - midpoint)))
            percs.append(min(s, peak_penetration))
        return cls(penetrations=percs)

    def penetration_at_year(self, year: int) -> float:
        """1-indexed year from launch."""
        if year <= 0:
            return 0.0
        idx = min(year - 1, len(self.penetrations) - 1)
        return self.penetrations[idx]


class LineOfTherapySegment(BaseModel):
    """
    Revenue model for one line of therapy.

    In oncology (and other TAs with established treatment sequences), 1L/2L/3L markets
    are structurally different: patient pools shrink, unmet need rises (higher penetration
    achievable), and relative pricing may differ by line. Model each LOT separately and
    aggregate for a realistic total revenue curve.

    Example:
        # RLY-2608 in HR+/HER2- mBC
        - line: "2L"
          patients_annual: 12000    # ~70% of addressable H1047R pts are 2L-eligible
          net_price_per_patient_usd: 180000
          peak_penetration: 0.22
          years_to_peak: 5
        - line: "3L+"
          patients_annual: 5000     # 30% in 3L+; higher unmet need
          net_price_per_patient_usd: 180000
          peak_penetration: 0.40    # higher pen: limited options, better tolerability
          years_to_peak: 3
          launch_delay_years: 1     # 3L label typically filed after 2L data matures
    """
    line: str = Field(description="Label, e.g. '1L', '2L', '3L+', 'maintenance'")
    patients_annual: int = Field(gt=0, description="Addressable patients per year in this LOT")
    net_price_per_patient_usd: float = Field(gt=0.0, description="Annual net price (after G2N) per patient")
    peak_penetration: float = Field(gt=0.0, le=1.0, description="Peak market share in this LOT")
    years_to_peak: int = Field(default=5, gt=0)
    compliance_rate: float = Field(default=0.80, gt=0.0, le=1.0)
    launch_delay_years: float = Field(
        default=0.0, ge=0.0,
        description="Years after asset launch before this LOT indication is available (e.g., 2L label + 1yr -> 3L)"
    )
    use_s_curve: bool = Field(default=False)

    @property
    def peak_sales_millions(self) -> float:
        return (
            self.patients_annual
            * self.net_price_per_patient_usd
            * self.compliance_rate
            * self.peak_penetration
            / 1e6
        )

    def _get_uptake_curve(self, patent_life: int) -> UptakeCurve:
        if self.use_s_curve:
            return UptakeCurve.s_curve(self.years_to_peak, self.peak_penetration, patent_life)
        return UptakeCurve.linear_ramp(self.years_to_peak, self.peak_penetration, patent_life)

    def revenue_in_year(self, years_from_asset_launch: int, patent_life: int) -> float:
        """
        Revenue N years from the asset's first launch (accounting for launch_delay_years).
        Patent clock runs from asset launch, not LOT-specific launch.
        """
        lot_year = years_from_asset_launch - self.launch_delay_years
        if lot_year <= 0:
            return 0.0
        lot_year_int = int(lot_year)
        # Stop at patent expiry measured from asset launch
        if years_from_asset_launch > patent_life:
            return 0.0
        pen = self._get_uptake_curve(patent_life).penetration_at_year(max(1, lot_year_int))
        return (
            self.patients_annual
            * self.net_price_per_patient_usd
            * self.compliance_rate
            * pen
            / 1e6
        )


class MarketModel(BaseModel):
    asset_id: str

    # --- Mode 1: multi-line of therapy (recommended for oncology) ---
    lines_of_therapy: list[LineOfTherapySegment] = Field(
        default=[],
        description="Per-LOT segment configs. When set, overrides patient-based and TAM-based modes."
    )

    # --- Mode 2: patient-based ---
    addressable_patients_annual: Optional[int] = Field(
        default=None, gt=0,
        description="Eligible patients per year in target geography"
    )
    net_price_per_patient_usd: Optional[float] = Field(
        default=None, gt=0.0,
        description="Annual net price (after gross-to-net) per patient in USD"
    )
    compliance_rate: float = Field(
        default=0.80, gt=0.0, le=1.0,
        description="Average fraction of year patients remain on therapy"
    )

    # --- Mode 3: TAM-based (fallback) ---
    total_addressable_market_millions: Optional[float] = Field(
        default=None, gt=0.0,
        description="Total market size in USD millions (net of G2N)"
    )

    # --- Shared ---
    uptake_curve: Optional[UptakeCurve] = None
    peak_penetration: float = Field(
        default=0.10, gt=0.0, le=1.0,
        description="Peak market share fraction (used in modes 2 and 3)"
    )
    years_to_peak: int = Field(default=5, gt=0)
    patent_life_years: int = Field(default=12, gt=0)
    use_s_curve: bool = Field(default=False, description="Use S-curve instead of linear ramp")

    # --- Competitive dynamics (optional) ---
    competition_model: Optional[CompetitionModel] = Field(
        default=None,
        description="Competitor launch simulator. When set, revenue is adjusted by "
                    "our_available_market_fraction(year) to reflect competitive erosion."
    )

    # --- Lifecycle management ---
    lifecycle_events: list[LifecycleEvent] = Field(
        default=[],
        description=(
            "Time-indexed events that modify the revenue model post-launch. "
            "label_expansion / combination_therapy: scale TAM and/or penetration from trigger_year. "
            "new_formulation: extend effective patent life by loe_delay_years. "
            "Events are cumulative; multiple events of the same type stack multiplicatively "
            "(TAM factor) or additively (penetration boost). "
            "Default [] produces identical results to a model without lifecycle events."
        ),
    )

    # Cost structure
    cogs_rate: float = Field(default=0.18, ge=0.0, le=1.0)
    sgna_rate_launch: float = Field(default=SGNA_RATE_LAUNCH, ge=0.0, le=1.0)
    sgna_rate_mature: float = Field(default=SGNA_RATE_MATURE, ge=0.0, le=1.0)
    sgna_ramp_years: int = Field(default=SGNA_RAMP_YEARS, gt=0)

    @model_validator(mode="after")
    def _check_mode(self) -> "MarketModel":
        if self.lines_of_therapy:
            return self  # multi-line mode; segment-level validation is handled by LineOfTherapySegment
        patient_mode = self.addressable_patients_annual and self.net_price_per_patient_usd
        tam_mode = self.total_addressable_market_millions is not None
        if not patient_mode and not tam_mode:
            raise ValueError(
                "Provide one of: (1) lines_of_therapy segments, "
                "(2) addressable_patients_annual + net_price_per_patient_usd, "
                "or (3) total_addressable_market_millions"
            )
        return self

    @model_validator(mode="after")
    def _build_uptake_curve(self) -> "MarketModel":
        if self.lines_of_therapy:
            return self  # each segment builds its own curve
        if self.uptake_curve is None:
            if self.use_s_curve:
                self.uptake_curve = UptakeCurve.s_curve(
                    self.years_to_peak, self.peak_penetration, self.patent_life_years
                )
            else:
                self.uptake_curve = UptakeCurve.linear_ramp(
                    self.years_to_peak, self.peak_penetration, self.patent_life_years
                )
        return self

    @property
    def peak_sales_millions(self) -> float:
        """
        Peak annual revenue in USD millions.

        Slow path (iterate revenue curve) is used when:
          - competition_model is set (competition-adjusted peak), OR
          - lifecycle_events are present (TAM/penetration multipliers shift the peak
            and the static formula would understate post-event revenue).

        Fast path (static formula) is used otherwise for efficiency.
        """
        eff_life = self._effective_patent_life()
        use_slow_path = (
            (self.competition_model and self.competition_model.competitors)
            or bool(self.lifecycle_events)
        )
        if use_slow_path:
            curve = [self.revenue_in_year(y) for y in range(1, eff_life + 1)]
            return max(curve) if curve else 0.0
        if self.lines_of_therapy:
            return sum(seg.peak_sales_millions for seg in self.lines_of_therapy)
        if self.addressable_patients_annual and self.net_price_per_patient_usd:
            return (
                self.addressable_patients_annual
                * self.net_price_per_patient_usd
                * self.compliance_rate
                * self.peak_penetration
                / 1e6
            )
        return (self.total_addressable_market_millions or 0) * self.peak_penetration

    def _get_uptake_curve(self) -> UptakeCurve:
        """Return uptake_curve, rebuilding if None (e.g. after model_copy with update)."""
        if self.uptake_curve is not None:
            return self.uptake_curve
        if self.use_s_curve:
            return UptakeCurve.s_curve(self.years_to_peak, self.peak_penetration, self.patent_life_years)
        return UptakeCurve.linear_ramp(self.years_to_peak, self.peak_penetration, self.patent_life_years)

    # ------------------------------------------------------------------
    # Lifecycle event helpers
    # ------------------------------------------------------------------

    def _effective_patent_life(self) -> int:
        """
        Patent life extended by any new_formulation lifecycle events.

        Each new_formulation event contributes its loe_delay_years to the effective
        life, regardless of trigger_year (the formulation's exclusivity is appended
        to the primary patent, not conditioned on when it launches).
        """
        if not self.lifecycle_events:
            return self.patent_life_years
        delay = sum(
            e.loe_delay_years for e in self.lifecycle_events
            if e.event_type == "new_formulation"
        )
        return self.patent_life_years + delay

    def _lifecycle_tam_multiplier(self, year: int) -> float:
        """
        Cumulative TAM expansion multiplier active at this year.

        Collects all label_expansion and combination_therapy events whose
        trigger_year ≤ year and multiplies their tam_expansion_factors.
        Events with trigger_year > year have no effect yet.
        Returns 1.0 (no change) when no qualifying events are active.
        """
        if not self.lifecycle_events:
            return 1.0
        factors = [
            e.tam_expansion_factor for e in self.lifecycle_events
            if e.trigger_year <= year
            and e.event_type in ("label_expansion", "combination_therapy")
        ]
        result = 1.0
        for f in factors:
            result *= f
        return result

    def _lifecycle_penetration_boost(self, year: int) -> float:
        """
        Cumulative absolute penetration boost active at this year (modes 2 and 3 only).

        Additive: multiple events' penetration_boost values are summed.
        The caller clamps the total so base_pen + boost ≤ 1.0.
        Returns 0.0 when no qualifying events are active.
        """
        if not self.lifecycle_events:
            return 0.0
        return sum(
            e.penetration_boost for e in self.lifecycle_events
            if e.trigger_year <= year
            and e.event_type in ("label_expansion", "combination_therapy")
        )

    def revenue_in_year(self, years_from_launch: int) -> float:
        """
        Gross revenue (net of G2N, pre-COGS) in USD millions, N years from launch.

        Lifecycle event ordering (applied before competition fraction):
          1. Compute base revenue from uptake curve (patient × price × penetration)
             or TAM × penetration.
          2. Apply _lifecycle_penetration_boost() to penetration (modes 2 and 3 only),
             clamped to [0, 1.0], before computing base.
          3. Multiply base by _lifecycle_tam_multiplier() — TAM expansion reflects
             new addressable patients from label expansions / combination approvals.
          4. Apply competition_model.our_available_market_fraction() — competitive
             dynamics operate on the already-expanded TAM.

        LOE delay from new_formulation events is reflected by using
        _effective_patent_life() as the patent boundary instead of patent_life_years.
        In multi-LOT mode, the effective patent life is passed to each segment.
        """
        eff_life = self._effective_patent_life()

        if self.lines_of_therapy:
            base = sum(
                seg.revenue_in_year(years_from_launch, eff_life)
                for seg in self.lines_of_therapy
            )
            # TAM multiplier applies to aggregate LOT revenue (penetration boost is
            # per-segment and not applicable here — use tam_expansion_factor instead)
            base *= self._lifecycle_tam_multiplier(years_from_launch)
        elif years_from_launch <= 0 or years_from_launch > eff_life:
            return 0.0
        else:
            base_pen = self._get_uptake_curve().penetration_at_year(years_from_launch)
            pen = min(1.0, base_pen + self._lifecycle_penetration_boost(years_from_launch))
            if self.addressable_patients_annual and self.net_price_per_patient_usd:
                base = (
                    self.addressable_patients_annual
                    * self.net_price_per_patient_usd
                    * self.compliance_rate
                    * pen
                    / 1e6
                )
            else:
                base = (self.total_addressable_market_millions or 0) * pen
            base *= self._lifecycle_tam_multiplier(years_from_launch)

        if self.competition_model and years_from_launch > 0:
            base *= self.competition_model.our_available_market_fraction(years_from_launch)

        return base

    def revenue_by_lot(self) -> dict[str, list[float]]:
        """
        Revenue curve broken out by LOT segment.
        Returns {line_label: [rev_yr1, rev_yr2, ...]} — useful for stacked charts.
        Falls back to {"total": revenue_curve()} when not in multi-line mode.
        """
        if not self.lines_of_therapy:
            return {"total": self.revenue_curve()}
        return {
            seg.line: [
                seg.revenue_in_year(y, self.patent_life_years)
                for y in range(1, self.patent_life_years + 1)
            ]
            for seg in self.lines_of_therapy
        }

    def gross_profit_in_year(self, years_from_launch: int) -> float:
        """Revenue minus COGS."""
        return self.revenue_in_year(years_from_launch) * (1.0 - self.cogs_rate)

    def sgna_in_year(self, years_from_launch: int) -> float:
        """SG&A expense in USD millions — declines from launch rate to mature rate."""
        if years_from_launch <= 0:
            return 0.0
        rev = self.revenue_in_year(years_from_launch)
        if years_from_launch >= self.sgna_ramp_years:
            return rev * self.sgna_rate_mature
        blend = years_from_launch / self.sgna_ramp_years
        rate = self.sgna_rate_launch + blend * (self.sgna_rate_mature - self.sgna_rate_launch)
        return rev * rate

    def ebit_in_year(self, years_from_launch: int) -> float:
        """EBIT = gross profit - SG&A."""
        return self.gross_profit_in_year(years_from_launch) - self.sgna_in_year(years_from_launch)

    def revenue_curve(self) -> list[float]:
        """Full revenue curve from year 1 to effective_patent_life_years."""
        return [self.revenue_in_year(y) for y in range(1, self._effective_patent_life() + 1)]

    def ebit_curve(self) -> list[float]:
        return [self.ebit_in_year(y) for y in range(1, self._effective_patent_life() + 1)]

    @classmethod
    def from_indication(
        cls,
        asset_id: str,
        indication: Indication,
        net_price_usd: float,
        peak_penetration: float,
        **kwargs,
    ) -> "MarketModel":
        """Build a MarketModel from an Indication entity."""
        patients = indication.addressable_patients
        if patients is None:
            raise ValueError("Indication.addressable_patients is None; provide epidemiology data")
        return cls(
            asset_id=asset_id,
            addressable_patients_annual=patients,
            net_price_per_patient_usd=net_price_usd,
            peak_penetration=peak_penetration,
            **kwargs,
        )
