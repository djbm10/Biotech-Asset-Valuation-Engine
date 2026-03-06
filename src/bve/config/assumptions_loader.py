"""
AssumptionsLoader — single source of truth for all calibrated industry priors.

All calibrated values (phase success rates, trial design log-odds, LOE erosion
profiles, competition haircuts, etc.) live in industry_assumptions.yaml.
This module loads, validates, and caches those values.

Design
------
Singleton with lazy initialization. Constants that previously lived in
constants.py now delegate here. All existing import paths continue to work
because constants.py re-exports the same names sourced from this loader.

Usage
-----
Typical code should import familiar names from constants.py unchanged:

    from bve.config.constants import PHASE_SUCCESS_RATES, TRIAL_DESIGN_LOGODDS

For programmatic access to the full assumptions object:

    from bve.config.assumptions_loader import AssumptionsLoader
    a = AssumptionsLoader.get()
    rates = a.phase_success_rates("oncology")

For overriding in tests (alternate YAML file):

    AssumptionsLoader.reset(path=Path("tests/fixtures/test_assumptions.yaml"))

Validation
----------
load() validates:
  - Required top-level sections are present
  - phase_success_rates: all 4 phases present per TA, values in (0, 1)
  - loe_erosion_profiles: loss fractions in [0, 1)
  - trial_design caps: positive cap > 0, negative cap < 0
  - phase_scaling: all values in (0, 1]
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

_DEFAULT_PATH = Path(__file__).parent / "industry_assumptions.yaml"

_REQUIRED_SECTIONS = {
    "meta",
    "phase_success_rates",
    "phase_durations_years",
    "phase_costs_millions",
    "commercial",
    "wacc",
    "monte_carlo",
    "loe_erosion_profiles",
    "competition",
    "trial_design",
}

_REQUIRED_PHASES = ("phase_1", "phase_2", "phase_3", "nda_bla")


class AssumptionsValidationError(ValueError):
    """Raised when industry_assumptions.yaml fails schema validation."""


class AssumptionsLoader:
    """
    Loads, validates, and caches industry_assumptions.yaml.

    All properties return the underlying data structures directly (not copies),
    which is safe because they are treated as read-only by all consumers.
    """

    _instance: Optional["AssumptionsLoader"] = None

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        with open(path) as f:
            self._data: dict = yaml.safe_load(f)
        self._path = path
        self._validate()

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------

    @classmethod
    def get(cls) -> "AssumptionsLoader":
        """Return the cached singleton, loading from the default path if needed."""
        if cls._instance is None:
            cls._instance = cls(_DEFAULT_PATH)
        return cls._instance

    @classmethod
    def reset(cls, path: Optional[Path] = None) -> "AssumptionsLoader":
        """
        Replace the singleton with a freshly loaded instance.

        Use in tests to load an alternate YAML file. Pass None to reload the
        default file (e.g., after a test that mutated the singleton).
        """
        cls._instance = cls(path or _DEFAULT_PATH)
        return cls._instance

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self) -> None:
        errors: list[str] = []

        # Required top-level sections
        for section in _REQUIRED_SECTIONS:
            if section not in self._data:
                errors.append(f"Missing required section: '{section}'")

        if errors:
            self._raise(errors)

        # phase_success_rates: each TA has all 4 phases, values in (0, 1)
        psr = self._data.get("phase_success_rates", {})
        for ta, phases in psr.items():
            for ph in _REQUIRED_PHASES:
                if ph not in phases:
                    errors.append(f"phase_success_rates.{ta} missing phase '{ph}'")
                else:
                    v = phases[ph]
                    if not (0 < v < 1):
                        errors.append(
                            f"phase_success_rates.{ta}.{ph} = {v} must be in (0, 1)"
                        )

        # loe_erosion_profiles: loss fractions in [0, 1)
        for profile, vals in self._data.get("loe_erosion_profiles", {}).items():
            for key in ("year_1_loss", "year_2_loss", "year_3_loss", "terminal_loss"):
                if key not in vals:
                    errors.append(f"loe_erosion_profiles.{profile} missing '{key}'")
                else:
                    v = vals[key]
                    if not (0.0 <= v < 1.0):
                        errors.append(
                            f"loe_erosion_profiles.{profile}.{key} = {v} must be in [0, 1)"
                        )

        # trial_design caps
        td = self._data.get("trial_design", {})
        cap_pos = td.get("cap_logodds_positive")
        cap_neg = td.get("cap_logodds_negative")
        if cap_pos is not None and cap_pos <= 0:
            errors.append(f"trial_design.cap_logodds_positive = {cap_pos} must be > 0")
        if cap_neg is not None and cap_neg >= 0:
            errors.append(f"trial_design.cap_logodds_negative = {cap_neg} must be < 0")

        # phase_scaling: values in (0, 1]
        for phase, dims in td.get("phase_scaling", {}).items():
            for dim, v in dims.items():
                if not (0 < v <= 1.0):
                    errors.append(
                        f"trial_design.phase_scaling.{phase}.{dim} = {v} must be in (0, 1]"
                    )

        if errors:
            self._raise(errors)

    def _raise(self, errors: list[str]) -> None:
        msg = (
            f"industry_assumptions.yaml validation failed ({self._path}):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
        raise AssumptionsValidationError(msg)

    # ------------------------------------------------------------------
    # Accessors — phase success rates
    # ------------------------------------------------------------------

    @property
    def phase_success_rates(self) -> dict[str, dict[str, float]]:
        """Full table: {therapeutic_area: {phase: probability}}."""
        return self._data["phase_success_rates"]

    def phase_success_rates_for(self, therapeutic_area: str) -> dict[str, float]:
        """
        Phase success rates for a specific therapeutic area.
        Falls back to "other" if the TA is not in the table.
        """
        psr = self._data["phase_success_rates"]
        return psr.get(therapeutic_area, psr["other"])

    @property
    def prob_approval_from_phase(self) -> dict[str, dict[str, float]]:
        """
        Cumulative P(approval) from the start of each phase.
        Derived from phase_success_rates; not stored separately in YAML.
        """
        result: dict[str, dict[str, float]] = {}
        for ta, rates in self.phase_success_rates.items():
            p1 = rates["phase_1"]
            p2 = rates["phase_2"]
            p3 = rates["phase_3"]
            pn = rates["nda_bla"]
            result[ta] = {
                "phase_1": p1 * p2 * p3 * pn,
                "phase_2": p2 * p3 * pn,
                "phase_3": p3 * pn,
                "nda_bla": pn,
            }
        return result

    # ------------------------------------------------------------------
    # Accessors — phase durations and costs
    # ------------------------------------------------------------------

    @property
    def phase_durations_years(self) -> dict[str, float]:
        return self._data["phase_durations_years"]

    @property
    def phase_costs_millions(self) -> dict[str, float]:
        return self._data["phase_costs_millions"]

    # ------------------------------------------------------------------
    # Accessors — commercial defaults
    # ------------------------------------------------------------------

    @property
    def gross_to_net_by_modality(self) -> dict[str, float]:
        return self._data["commercial"]["gross_to_net_by_modality"]

    def gross_to_net(self, modality: str) -> float:
        """G2N rate for a modality; falls back to 'other'."""
        table = self.gross_to_net_by_modality
        return table.get(modality, table["other"])

    @property
    def cogs_rate_by_modality(self) -> dict[str, float]:
        return self._data["commercial"]["cogs_rate_by_modality"]

    def cogs_rate(self, modality: str) -> float:
        table = self.cogs_rate_by_modality
        return table.get(modality, table["other"])

    @property
    def sgna(self) -> dict[str, float]:
        """Keys: rate_launch, rate_mature, ramp_years."""
        return self._data["commercial"]["sgna"]

    # ------------------------------------------------------------------
    # Accessors — WACC
    # ------------------------------------------------------------------

    @property
    def wacc(self) -> dict[str, float]:
        """Keys: default, small_cap, large_cap, risk_free."""
        return self._data["wacc"]

    # ------------------------------------------------------------------
    # Accessors — Monte Carlo defaults
    # ------------------------------------------------------------------

    @property
    def mc_phase_ess(self) -> dict[str, int]:
        return {k: int(v) for k, v in self._data["monte_carlo"]["phase_ess"].items()}

    @property
    def mc_peak_sales_cv(self) -> float:
        return float(self._data["monte_carlo"]["peak_sales_cv"])

    @property
    def mc_discount_rate_std(self) -> float:
        return float(self._data["monte_carlo"]["discount_rate_std"])

    # ------------------------------------------------------------------
    # Accessors — LOE erosion profiles
    # ------------------------------------------------------------------

    @property
    def loe_erosion_profiles(self) -> dict[str, dict[str, float]]:
        """Full table: {modality: {year_1_loss, year_2_loss, ...}}."""
        return self._data["loe_erosion_profiles"]

    def loe_erosion_profile(self, modality: str) -> dict[str, float]:
        """
        LOE erosion profile for a modality.
        Falls back to 'other' (small_molecule-like) if not found.
        """
        profiles = self.loe_erosion_profiles
        if modality in profiles:
            return profiles[modality]
        return profiles.get("other", profiles["small_molecule"])

    # ------------------------------------------------------------------
    # Accessors — Competition
    # ------------------------------------------------------------------

    @property
    def competition(self) -> dict:
        return self._data["competition"]

    # ------------------------------------------------------------------
    # Accessors — Trial design
    # ------------------------------------------------------------------

    @property
    def trial_design_logodds(self) -> dict[str, dict[str, float]]:
        return self._data["trial_design"]["logodds"]

    @property
    def trial_design_cap_positive(self) -> float:
        return float(self._data["trial_design"]["cap_logodds_positive"])

    @property
    def trial_design_cap_negative(self) -> float:
        return float(self._data["trial_design"]["cap_logodds_negative"])

    @property
    def trial_design_phase_scaling(self) -> dict[str, dict[str, float]]:
        return self._data["trial_design"]["phase_scaling"]

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @property
    def version(self) -> str:
        return str(self._data["meta"]["version"])

    @property
    def sources(self) -> list[str]:
        return list(self._data["meta"].get("sources", []))
